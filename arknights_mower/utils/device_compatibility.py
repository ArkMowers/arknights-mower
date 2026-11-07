"""Pure preset names and native capture compatibility, without loading configuration."""

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
