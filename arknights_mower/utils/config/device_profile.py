"""Stable device selections and the compatibility mapping for legacy Conf files."""

import os
import shutil
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from arknights_mower.utils.path import get_path


def default_adb_path():
    name = "adb.exe" if sys.platform == "win32" else "adb"
    bundled = get_path(f"@internal/platform-tools/{name}")
    if bundled.is_file() or sys.platform == "darwin":
        return f"@internal/platform-tools/{name}"
    if sys.platform.startswith("linux"):
        return os.environ.get("MOWER_ADB_BIN") or shutil.which("adb") or ""
    return ""


PresetId = Literal[
    "windows.mumu12",
    "windows.ldplayer9",
    "windows.ldplayer14",
    "windows.nox",
    "windows.bluestacks5",
    "macos.bluestacks_air",
    "macos.avd",
    "macos.mumu_pro",
    "linux.waydroid",
    "linux.avd",
    "linux.redroid",
    "linux.genymotion",
    "manual.other",
    "manual.physical",
]
ScreenshotBackend = Literal["adb_gzip", "droidcast", "mumu_ipc", "ld_native", "custom"]
TouchBackend = Literal["scrcpy", "maatouch", "mumu_ipc"]
GamePackage = Literal["com.hypergryph.arknights", "com.hypergryph.arknights.bilibili"]

NATIVE_CAPTURE_PRESETS = {
    "mumu_ipc": {"windows.mumu12"},
    "ld_native": {"windows.ldplayer9", "windows.ldplayer14"},
}


def capture_compatibility_error(preset, backend, host=None):
    required = NATIVE_CAPTURE_PRESETS.get(backend)
    if required and (
        preset not in required or (host is not None and host != "windows")
    ):
        return (
            "MuMu 截图增强仅适用于 Windows 的 MuMu 12。"
            if backend == "mumu_ipc"
            else "LD 截图增强仅适用于 Windows 的雷电模拟器 9 或 14。"
        )
    return ""


# The first name is also the spelling understood by the old runtime.
LEGACY_NAMES = {
    "windows.mumu12": (
        "MuMu12",
        "MuMu 12",
        "MuMu模拟器12",
        "MuMu模拟器 12",
        "明日方舟-MuMu模拟器12",
        "YXArkNights-12.0",
        "YXArkNights",
    ),
    # Retired preset aliases are accepted only for configuration migration.
    "windows.mumu6": (
        "MuMu6",
        "MuMu 6",
        "MuMu模拟器6",
        "MuMu模拟器 6",
        "Nemu",
        "NemuPlayer",
    ),
    "windows.ldplayer9": (
        "雷电9",
        "雷电模拟器9",
        "LDPlayer9",
        "LDPlayer 9",
        "雷电",
        "雷电模拟器",
        "LDPlayer",
    ),
    "windows.ldplayer14": (
        "雷电14",
        "雷电模拟器14",
        "LDPlayer14",
        "LDPlayer 14",
    ),
    "windows.nox": ("夜神", "夜神模拟器", "Nox", "NoxPlayer"),
    "windows.bluestacks5": ("BlueStacks5", "BlueStacks 5", "蓝叠5"),
    "macos.bluestacks_air": ("BlueStacksAir", "BlueStacks Air", "bluestacks_air"),
    "macos.mumu_pro": ("MuMuPro", "MuMu Pro", "mumu_pro"),
    "linux.waydroid": ("Waydroid",),
    "linux.redroid": ("ReDroid", "redroid"),
    "linux.genymotion": ("Genymotion",),
}
_PRESET_BY_ALIAS = {
    alias.casefold(): preset
    for preset, aliases in LEGACY_NAMES.items()
    for alias in aliases
}

# Only submitted legacy selections participate in a partial update. In
# particular, changing a capture command must not replace the selected backend.
LEGACY_PROFILE_FIELDS = {
    ("simulator", "name"): ("preset_id",),
    ("simulator", "simulator_folder"): ("installation_path",),
    ("simulator", "index"): ("instance_id",),
    ("simulator", "hotkey"): ("simulator_hotkey",),
    ("simulator", "hotkey_delay"): ("simulator_hotkey_delay",),
    ("maa_adb_path",): ("adb_path",),
    ("adb",): ("last_serial",),
    ("package_type",): ("game_package",),
    ("mumu12IPC",): ("screenshot_backend", "touch_backend"),
    ("droidcast", "enable"): ("screenshot_backend", "touch_backend"),
    ("custom_screenshot", "enable"): ("screenshot_backend", "touch_backend"),
    ("touch_method",): ("touch_backend",),
}


def updated_legacy_profile_fields(updates: dict) -> set[str]:
    fields = set()
    for path, targets in LEGACY_PROFILE_FIELDS.items():
        value = updates
        for key in path:
            if not isinstance(value, dict) or key not in value:
                break
            value = value[key]
        else:
            fields.update(targets)
    return fields


class DeviceProfile(BaseModel):
    # Discovery results and runtime state must never become persisted fields.
    model_config = ConfigDict(extra="forbid")

    preset_id: PresetId = "manual.other"
    installation_path: str = ""
    manager_path: str = ""
    config_path: str = ""
    adb_path: str = Field(default_factory=default_adb_path)
    instance_id: str = "-1"
    instance_name: str = ""
    # Nox VM UUID and the topology explicitly confirmed with this binding.
    instance_uuid: str = ""
    topology_fingerprint: str = ""
    last_serial: str = ""
    game_package: GamePackage = "com.hypergryph.arknights"
    game_package_confirmed: bool = False
    screenshot_backend: ScreenshotBackend = "droidcast"
    touch_backend: TouchBackend = "scrcpy"
    recovery_timeout: float = 180.0
    recovery_attempts: int = 3
    recovery_local_wait: float = 10.0
    recovery_shutdown_wait: float = 30.0
    manager_query_timeout: float = 3.0
    simulator_hotkey: str = ""
    simulator_hotkey_delay: float = 3.0

    @model_validator(mode="before")
    @classmethod
    def migrate_retired_mumu(cls, value):
        if isinstance(value, dict) and value.get("preset_id") == "windows.mumu6":
            return {
                **value,
                "preset_id": "manual.other",
                "last_serial": "",
                "game_package_confirmed": False,
            }
        return value

    @model_validator(mode="after")
    def validate_ipc_pair(self):
        if (self.screenshot_backend == "mumu_ipc") != (
            self.touch_backend == "mumu_ipc"
        ):
            raise ValueError("MuMu IPC 必须同时用于截图与触控")
        return self


def profile_from_legacy(data: dict) -> DeviceProfile:
    """Map effective old runtime behavior, including conflicting capture flags."""
    simulator = data.get("simulator", {})
    name = simulator.get("name", "").strip().casefold()
    if data.get("mumu12IPC", False):
        screenshot, touch = "mumu_ipc", "mumu_ipc"
    else:
        touch = "maatouch" if data.get("touch_method") == "maatouch" else "scrcpy"
        if data.get("droidcast", {}).get("enable", True):
            screenshot = "droidcast"
        elif data.get("custom_screenshot", {}).get("enable", False):
            screenshot = "custom"
        else:
            screenshot = "adb_gzip"
    return DeviceProfile(
        preset_id=_PRESET_BY_ALIAS.get(name, "manual.other"),
        installation_path=simulator.get("simulator_folder", ""),
        adb_path=data.get("maa_adb_path", ""),
        instance_id=str(simulator.get("index", "-1")),
        last_serial=data.get("adb", "127.0.0.1:16384"),
        game_package=(
            "com.hypergryph.arknights"
            if data.get("package_type", 1) == 1
            else "com.hypergryph.arknights.bilibili"
        ),
        screenshot_backend=screenshot,
        touch_backend=touch,
        recovery_shutdown_wait=float(data.get("recovery_shutdown_wait", 30.0)),
        manager_query_timeout=float(data.get("manager_query_timeout", 3.0)),
        simulator_hotkey=simulator.get("hotkey", ""),
        simulator_hotkey_delay=float(
            simulator.get("hotkey_delay", data.get("simulator_hotkey_delay", 3.0))
        ),
    )
