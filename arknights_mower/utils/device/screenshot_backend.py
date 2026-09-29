"""Validation, one owned-resource rebuild and one ADB fallback per capture session."""

import numpy as np

from arknights_mower.utils.config.device_profile import capture_compatibility_error
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.droidcast import DroidCastError
from arknights_mower.utils.device.recovery import DeviceRecoveryError

BACKEND_LABELS = {
    "adb_gzip": "ADB gzip",
    "droidcast": "DroidCast",
    "mumu_ipc": "MuMu IPC",
    "ld_native": "LD 截图增强",
    "custom": "自定义命令",
}

# The minimum degradation rung always ends on the same plain ADB screencap.
STANDARD_ADB_BACKEND = "adb_gzip"
# Only a capture failure of a helper backend can be answered by the plain ADB
# path; the plain path itself has no lower rung.
DEGRADABLE_BACKEND = "droidcast"
# Stage failures that already name their own repair. Degrading would replace a
# precise code with a generic capture failure, so the selected backend latches.
# These are DroidCastError's own codes, which carry the "droidcast_" prefix.
# The HTTP interface is the helper's own transport: by the time it fails, the
# helper has already answered through it, so a plain screencap cannot recover it.
TERMINAL_BACKEND_CODES = frozenset(
    {
        "droidcast_version_required",
        "droidcast_version_failed",
        "droidcast_install_failed",
        "droidcast_signature_conflict",
        "droidcast_forward_failed",
        "droidcast_start_failed",
        "droidcast_start_timeout",
        "droidcast_frame_failed",
        "droidcast_http_failed",
        "droidcast_http_timeout",
        "droidcast_cleanup_failed",
        "droidcast_ownership_conflict",
    }
)
SIZE_GUIDANCE = (
    "请在设备或模拟器设置中把有效逻辑尺寸改为横屏 1920×1080，"
    "重启目标设备后重试；只读检查不会修改设备尺寸。"
)
RETRY_GUIDANCE = "请检查所选后端后重试，或手动选择其他兼容截图后端。"


def screenshot_alternatives(profile, host):
    return [
        {"backend": backend, "label": label}
        for backend, label in BACKEND_LABELS.items()
        if backend != profile.screenshot_backend
        and not capture_compatibility_error(profile.preset_id, backend, host)
    ]


class FrameSizeMismatch(ValueError):
    pass


def validate_frame(frame):
    if (
        not isinstance(frame, np.ndarray)
        or frame.dtype != np.uint8
        or frame.ndim != 3
        or frame.shape[2] != 3
        or frame.size == 0
    ):
        raise ValueError("截图后端未返回有效的 uint8 RGB 实际帧")
    if frame.shape != (1080, 1920, 3):
        raise FrameSizeMismatch(
            f"截图实际帧尺寸为 {frame.shape[1]}×{frame.shape[0]}，必须为横屏 1920×1080"
        )
    # A successful, correctly sized black frame is legitimate. Pixel color alone
    # says nothing about capture health or whether the game is loading.
    return frame


class ScreenshotFailure(DeviceRecoveryError):
    def __init__(self, profile, host, cause, *, degraded=False, fallback=None):
        self.backend = profile.screenshot_backend
        self.alternatives = screenshot_alternatives(profile, host)
        self.degraded = degraded
        # A resolution mismatch is a deterministic configuration error. It never
        # enters the screenshot retry, transport or restart loops.
        self.size_mismatch = isinstance(cause, FrameSizeMismatch)
        self.code = (
            "frame_size_mismatch"
            if self.size_mismatch
            else cause.code
            if isinstance(cause, DroidCastError)
            else "screenshot_failed"
        )
        cause_text = str(cause).rstrip("。")
        if self.size_mismatch:
            message = f"{cause_text}。{SIZE_GUIDANCE}"
        else:
            message = f"{BACKEND_LABELS[self.backend]} 截图失败：{cause_text}。{RETRY_GUIDANCE}"
        if fallback is not None:
            message += f" 标准 ADB 截图也失败：{fallback}"
        super().__init__(message)

    def to_dict(self):
        # The keys map onto the structured preflight error and the settings UI
        # knows them, so only the repair action changes for a size mismatch.
        return {
            "code": self.code,
            "message": str(self),
            "action": "fix_size" if self.size_mismatch else "retry",
            "fields": ["screenshot_backend"],
            "backend": self.backend,
            "alternatives": self.alternatives,
        }


class ScreenshotSession:
    """One rebuild of the selected backend, then one standard ADB fallback."""

    def __init__(self, profile, host):
        self.profile = profile.model_copy(deep=True)
        self.host = host
        self.backend = profile.screenshot_backend
        self.rebuilt = False
        self.degraded = False
        self.failure = None

    def capture(self, capture, rebuild, recover, standard_adb=None):
        if self.failure is not None:
            raise self.failure
        if self.degraded:
            return self._standard_frame(standard_adb)
        try:
            return validate_frame(capture())
        except (MowerExit, DeviceRecoveryError):
            raise
        except FrameSizeMismatch as exc:
            # A wrong-size frame is deterministic and came from a working capture
            # path, so it is terminal without another rebuild.
            self._latch_failure(exc)
            return None
        except Exception as exc:
            cause = exc
        if not self.rebuilt:
            # Readiness/recovery belongs to the application, never the helper.
            self.rebuilt = True
            rebuilt_by_recovery = recover()
            try:
                if not rebuilt_by_recovery:
                    rebuild()
                return validate_frame(capture())
            except MowerExit:
                raise
            except FrameSizeMismatch as exc:
                self._latch_failure(exc)
                return None
            except Exception as exc:
                cause = exc
        # An install, package, forward or helper-start failure already carries its
        # own code; a plain screencap cannot observe it and would hide that stage.
        if getattr(cause, "code", None) in TERMINAL_BACKEND_CODES:
            self._latch_failure(cause)
            return None
        # The rung only helps a transport-level failure of the selected capture.
        if self.backend != DEGRADABLE_BACKEND or standard_adb is None:
            self._latch_failure(cause)
            return None
        return self._standard_frame(standard_adb, cause)

    def _standard_frame(self, standard_adb, cause=None):
        """One plain ADB screencap, recorded as this session's degradation."""
        if standard_adb is None:
            self._latch_failure(cause or RuntimeError("无法降级到标准 ADB 截图"))
            return None
        try:
            frame = validate_frame(standard_adb())
        except MowerExit:
            raise
        except DeviceRecoveryError:
            raise
        except FrameSizeMismatch as exc:
            # A wrong-size fallback is the terminal verdict, not a peer failure.
            self._latch_failure(exc if cause is None else cause, exc)
            return None
        except Exception as exc:
            self._latch_failure(cause, exc)
            return None
        self.backend = STANDARD_ADB_BACKEND
        self.degraded = True
        return frame

    def _latch_failure(self, cause, fallback=None):
        """A latched failure remains visible without retrying cleanup."""
        failure = ScreenshotFailure(
            self.profile, self.host, cause, degraded=self.degraded, fallback=fallback
        )
        self.failure = failure
        raise failure from cause
