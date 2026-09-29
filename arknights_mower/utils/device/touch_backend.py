"""Selected input backend failures never authorize another input delivery."""

from pathlib import Path

from arknights_mower import __rootdir__
from arknights_mower.utils.device.recovery import DeviceRecoveryError

TOUCH_LABELS = {"scrcpy": "scrcpy 1.21", "maatouch": "MaaTouch", "mumu_ipc": "MuMu IPC"}

# Bundled files each backend pushes to the target before it can deliver input.
MAATOUCH_ASSET = Path(__rootdir__) / "vendor" / "maatouch" / "maatouch"
SCRCPY_JAR = (
    Path(__rootdir__) / "vendor" / "scrcpy-server-novideo" / "scrcpy-server-novideo.jar"
)


def _asset_missing(asset):
    """An unreadable bundled file is reported as missing, never raised here.

    This runs while settings status is assembled, before discovery, so a
    permission or path error must not replace the caller's own failure.
    """
    try:
        return not asset.is_file()
    except OSError:
        return True


def _missing_asset(profile):
    """Report a missing helper; the selected backend itself never changes."""
    if profile.touch_backend == "maatouch" and _asset_missing(MAATOUCH_ASSET):
        return f"未找到 MaaTouch 可执行文件 {MAATOUCH_ASSET}。"
    if profile.touch_backend == "scrcpy" and _asset_missing(SCRCPY_JAR):
        return f"未找到 scrcpy 服务端文件 {SCRCPY_JAR}。"
    return None


def _ipc_reason(profile, host):
    if host != "windows" or profile.preset_id != "windows.mumu12":
        return (
            "MuMu IPC 触控仅适用于 Windows 上的 MuMu 12，且需同时选择 MuMu IPC 截图。"
        )
    return None


def touch_backends(profile, host):
    options = []
    for backend, label in TOUCH_LABELS.items():
        reason = _ipc_reason(profile, host) if backend == "mumu_ipc" else ""
        if backend == profile.touch_backend and not reason:
            reason = _missing_asset(profile) or ""
        options.append(
            {
                "backend": backend,
                "label": label,
                "available": not reason,
                "reason": reason,
            }
        )
    return options


class TouchFailure(DeviceRecoveryError):
    def __init__(self, profile, host, cause, *, delivery_unknown=False, transport=None):
        self.backend = profile.touch_backend
        self.transport = transport or self.backend
        self.delivery_unknown = delivery_unknown
        self.cleanup_failed = getattr(cause, "cleanup_failed", False)
        self.code = (
            "touch_result_unknown"
            if delivery_unknown
            else "touch_initialization_failed"
        )
        if self.transport == "adb":
            self.alternatives = []
            label = "ADB"
            remedy = "请结束本次运行并检查 ADB 连接和设备状态，确认后重试。"
        else:
            self.alternatives = [
                {"backend": item["backend"], "label": item["label"]}
                for item in touch_backends(profile, host)
                if item["available"] and item["backend"] != self.backend
            ]
            label = TOUCH_LABELS[self.backend]
            remedy = (
                "请结束本次运行并检查设备状态，确认后重试或手动选择其他兼容触控后端。"
            )
        reason = (
            "输入发送结果不明确，已停止本次会话，不会自动重复动作"
            if delivery_unknown
            else "触控初始化失败"
        )
        super().__init__(f"{label} {reason}：{cause}。{remedy}")

    def to_dict(self):
        return {
            "code": self.code,
            "message": str(self),
            "action": "configure",
            "fields": ["adb_path"] if self.transport == "adb" else ["touch_backend"],
            "backend": self.backend,
            "transport": self.transport,
            "alternatives": self.alternatives,
            "delivery_unknown": self.delivery_unknown,
        }
