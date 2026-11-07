"""Device readiness policy with an optional runtime-only capture preparation."""

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Protocol, TypeVar

import numpy as np

from arknights_mower.utils.config.device_profile import (
    DeviceProfile,
    capture_compatibility_error,
)
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.screenshot_backend import (
    ScreenshotFailure,
    ScreenshotSession,
)

GAME_PACKAGES = (
    "com.hypergryph.arknights",
    "com.hypergryph.arknights.bilibili",
)
T = TypeVar("T")


class PreflightIO(Protocol):
    """Bounded external observations; implementations must not change settings."""

    def host_platform(self) -> str: ...
    def installation_exists(self, path: str) -> bool: ...
    def product_adb_paths(self, profile: DeviceProfile) -> list[str]: ...
    def sdk_adb_paths(self) -> list[str]: ...
    def path_adb_paths(self) -> list[str]: ...
    def normalize_adb_path(self, path: str) -> str: ...
    def validate_adb(self, path: str) -> bool: ...
    def devices(self, adb_path: str, serial: str) -> list[tuple[str, str]]: ...
    def boot_completed(self, adb_path: str, serial: str) -> str: ...
    def performance_info(self, adb_path: str, serial: str) -> dict[str, int]: ...
    def display_size(self, adb_path: str, serial: str) -> str: ...
    def capture_frame(
        self, adb_path: str, serial: str, profile: DeviceProfile
    ) -> np.ndarray: ...
    def packages(self, adb_path: str, serial: str) -> list[str]: ...


@dataclass(frozen=True)
class PreflightError:
    code: str
    message: str
    action: str = "retry"
    fields: list[str] = field(default_factory=list)
    backend: str = ""
    alternatives: list[dict[str, str]] = field(default_factory=list)


def mumu_pro_manual_error() -> PreflightError:
    """Describe a missing MuMu Pro discovery adapter and manual serial entry."""
    return PreflightError(
        "mumu_pro_manual_required",
        "当前运行环境未提供 MuMu Pro 实例检测。请在目标实例的“开发者 → 打开 ADB”"
        "菜单确认端口，在高级设备设置中填写该实例的 ADB serial 后测试连接。",
        "manual",
    )


@dataclass
class PreflightResult:
    ok: bool
    host_platform: str
    status: str
    serial: str
    adb_path: str = ""
    game_package: str = ""
    packages: list[str] = field(default_factory=list)
    candidates: list[dict[str, str]] = field(default_factory=list)
    observations: dict = field(default_factory=dict)
    error: PreflightError | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class _ObservationError(Exception):
    def __init__(self, error: PreflightError):
        super().__init__(error.message)
        self.error = error


class ScreenshotUnavailable(RuntimeError):
    """An adapter's actionable explanation for an unavailable capture helper."""


def parse_display_size(output: str) -> dict[str, list[int]]:
    """Parse one unambiguous default-display Physical and optional Override."""
    dimensions = {}
    for line in output.strip().splitlines():
        match = re.fullmatch(r"\s*(Physical|Override) size:\s*(\d+)x(\d+)\s*", line)
        if match is None or match[1] in dimensions:
            raise ValueError("无法确认设备逻辑尺寸，请检查设备显示设置后重试。")
        dimensions[match[1]] = [int(match[2]), int(match[3])]
    if "Physical" not in dimensions or any(
        min(dimension) <= 0 for dimension in dimensions.values()
    ):
        raise ValueError("无法读取设备 Physical 尺寸，请检查设备显示设置后重试。")
    return dimensions


class PreflightService:
    def __init__(self, io: PreflightIO):
        self._io = io

    def host_platform(self) -> str:
        return self._io.host_platform()

    def resolve_adb(self, profile: DeviceProfile) -> str:
        """Choose and validate the executable before resolving a vendor endpoint."""
        sources = (
            lambda: [profile.adb_path] if profile.adb_path.strip() else [],
            lambda: self._io.product_adb_paths(profile),
            self._io.sdk_adb_paths,
            self._io.path_adb_paths,
        )
        seen = set()
        for source in sources:
            try:
                candidates = source()
            except MowerExit:
                raise
            except Exception:
                continue
            for path in candidates:
                try:
                    path = self._io.normalize_adb_path(path)
                    if path in seen:
                        continue
                    seen.add(path)
                    valid = self._io.validate_adb(path)
                except MowerExit:
                    raise
                except Exception:
                    continue
                if valid:
                    return path
        raise ValueError("没有可用的 ADB，请指定有效的 ADB 程序。")

    def check(
        self,
        profile: DeviceProfile,
        *,
        confirmed_package: str | None = None,
        prepared_size: list[int] | None = None,
        resolved_adb: str | None = None,
        require_unique_target: bool = False,
        prepare_capture: Callable[[str, str, DeviceProfile], None] | None = None,
    ) -> PreflightResult:
        result = PreflightResult(
            False,
            self.host_platform(),
            "failed",
            profile.last_serial.strip(),
            adb_path=resolved_adb or "",
        )
        if reason := capture_compatibility_error(
            profile.preset_id, profile.screenshot_backend, result.host_platform
        ):
            result.error = PreflightError(
                "screenshot_backend_incompatible", reason, fields=["screenshot_backend"]
            )
            return result
        try:
            return self._check(
                profile,
                result,
                confirmed_package,
                prepared_size,
                require_unique_target,
                prepare_capture,
            )
        except _ObservationError as exc:
            result.error = exc.error
            return result

    def _check(
        self,
        profile: DeviceProfile,
        result: PreflightResult,
        confirmed_package: str | None,
        prepared_size: list[int] | None,
        require_unique_target: bool,
        prepare_capture: Callable[[str, str, DeviceProfile], None] | None,
    ) -> PreflightResult:
        # Manual MuMu Pro binding needs only an explicit ADB serial. Verified
        # instance selection checks its manager path before this preflight.
        path_fields = (
            ()
            if profile.preset_id == "macos.mumu_pro"
            else ("installation_path", "manager_path")
        )
        for name in path_fields:
            path = getattr(profile, name).strip()
            exists = not path or self._observe(
                lambda: self._io.installation_exists(path),
                "missing_installation",
                "无法访问指定的安装目录或管理程序，请检查路径与访问权限后重试。",
                [name],
            )
            if not exists:
                return self._fail(
                    result,
                    "missing_installation",
                    "找不到指定的安装目录或管理程序，请修正路径后重试。",
                    [name],
                )
        try:
            if result.adb_path:
                if not self._io.validate_adb(result.adb_path):
                    raise ValueError("已选择的 ADB 不再有效")
            else:
                result.adb_path = self.resolve_adb(profile)
        except MowerExit:
            raise
        except Exception:
            result.adb_path = ""
        if not result.adb_path:
            return self._fail(
                result,
                "missing_adb",
                "没有可用的 ADB，请安装 Android SDK platform-tools 或指定有效的 ADB 程序。",
                ["adb_path"],
            )
        result.candidates = self._observe(
            lambda: [
                {"serial": serial, "state": state}
                for serial, state in self._io.devices(result.adb_path, result.serial)
            ],
            "device_probe_failed",
            "无法读取 ADB 设备状态，请检查设备连接后重试。",
        )
        if not result.serial or (require_unique_target and len(result.candidates) > 1):
            result.serial = ""
            multiple = len(result.candidates) > 1
            return self._fail(
                result,
                "multiple_devices" if multiple else "target_required",
                "请选择一个明确的设备 serial 后重试。",
                ["last_serial"],
                status="selection_required",
            )
        matches = [
            item for item in result.candidates if item["serial"] == result.serial
        ]
        if len(matches) != 1:
            return self._fail(
                result,
                "target_ambiguous" if matches else "target_absent",
                "目标设备不唯一，请检查 serial。"
                if matches
                else "未找到目标设备，请检查连接与 serial。",
                ["last_serial"],
                status="selection_required" if matches else "absent",
            )
        state = matches[0]["state"]
        if state == "unauthorized":
            return self._fail(
                result,
                "device_unauthorized",
                "请在目标设备上允许此计算机进行 USB 调试，然后重试。",
                status="unauthorized",
            )
        if state != "device":
            return self._fail(
                result,
                "device_offline",
                "目标设备尚未在线，请检查 USB 或网络连接、启用 ADB 后重试。",
                status="offline",
            )
        boot = self._observe(
            lambda: self._io.boot_completed(result.adb_path, result.serial),
            "boot_failed",
            "无法确认 Android 启动状态，请等待设备进入桌面后重试。",
        )
        if boot.strip() != "1":
            return self._fail(
                result,
                "boot_incomplete",
                "Android 尚未启动完成，请等待设备进入桌面后重试。",
                status="booting",
            )
        try:
            info = self._io.performance_info(result.adb_path, result.serial)
            result.observations["performance"] = {
                "status": "available",
                **info,
            }
        except MowerExit:
            raise
        except Exception:
            result.observations["performance"] = {
                "status": "unavailable",
                "message": "未能读取设备资源信息，可重试测试连接；不影响游戏内性能测试。",
            }
        size = self._observe(
            lambda: self._io.display_size(result.adb_path, result.serial),
            "invalid_size",
            "无法读取设备逻辑尺寸，请检查设备显示设置后重试。",
        )
        try:
            dimensions = parse_display_size(size)
        except ValueError as exc:
            return self._fail(result, "invalid_size", str(exc))
        result.observations.update(
            physical=dimensions["Physical"],
            override=dimensions.get("Override"),
            effective=dimensions.get("Override", dimensions["Physical"]),
        )
        packages = self._observe(
            lambda: self._io.packages(result.adb_path, result.serial),
            "package_probe_failed",
            "无法读取目标设备的游戏包，请等待系统就绪后重试。",
        )
        result.packages = [package for package in GAME_PACKAGES if package in packages]
        if not result.packages:
            return self._fail(
                result,
                "package_missing",
                "目标设备未安装明日方舟，请安装官服或哔哩哔哩版并完成首次启动后重试。",
            )
        if confirmed_package is None and getattr(
            profile, "game_package_confirmed", False
        ):
            confirmed_package = profile.game_package
        if len(result.packages) > 1 and confirmed_package not in result.packages:
            return self._fail(
                result,
                "package_ambiguous",
                "目标设备同时安装了两个游戏包，请选择本次使用的版本。",
                ["game_package"],
                status="selection_required",
            )
        result.game_package = (
            result.packages[0] if len(result.packages) == 1 else confirmed_package
        )
        # IPC backends may select a display using the installed game package.
        # Do not change the authoritative profile during this read-only action.
        capture_profile = profile.model_copy(
            update={"game_package": result.game_package}
        )

        def ready_for_retry():
            targets = self._io.devices(result.adb_path, result.serial)
            states = [state for serial, state in targets if serial == result.serial]
            if (
                states != ["device"]
                or self._io.boot_completed(result.adb_path, result.serial).strip()
                != "1"
            ):
                raise RuntimeError("截图失败后目标设备不再 ready，请检查连接后重试")

        try:
            # Only runtime start supplies preparation. Read-only preflight never
            # installs a helper, and an invalid target or display never reaches it.
            if prepare_capture is not None:
                prepare_capture(result.adb_path, result.serial, capture_profile)
            # Each read-only capture owns and releases its ephemeral helper.
            # A second invocation therefore rebuilds only that same backend.
            # Backend degradation belongs to the ongoing device session, not to
            # this one-shot read-only capture.
            frame = ScreenshotSession(capture_profile, result.host_platform).capture(
                lambda: self._io.capture_frame(
                    result.adb_path, result.serial, capture_profile
                ),
                lambda: None,
                ready_for_retry,
                None,
            )
        except MowerExit:
            raise
        except Exception as exc:
            failure = (
                exc
                if isinstance(exc, ScreenshotFailure)
                else ScreenshotFailure(capture_profile, result.host_platform, exc)
            )
            detail = failure.to_dict()
            if detail["code"] == "screenshot_failed":
                detail["code"] = "frame_failed"
            result.error = PreflightError(**detail)
            return result
        result.observations["frame"] = [frame.shape[1], frame.shape[0]]
        result.ok, result.status = True, "ready"
        return result

    @staticmethod
    def _observe(
        operation: Callable[[], T],
        code: str,
        message: str,
        fields: list[str] | None = None,
    ) -> T:
        try:
            return operation()
        except MowerExit:
            raise
        except ScreenshotUnavailable as exc:
            raise _ObservationError(
                PreflightError("frame_failed", str(exc), fields=["screenshot_backend"])
            ) from exc
        except Exception as exc:
            raise _ObservationError(
                PreflightError(code, message, fields=fields or [])
            ) from exc

    @staticmethod
    def _fail(
        result: PreflightResult,
        code: str,
        message: str,
        fields: list[str] | None = None,
        *,
        status: str = "failed",
    ) -> PreflightResult:
        result.status = status
        result.error = PreflightError(code, message, fields=fields or [])
        return result
