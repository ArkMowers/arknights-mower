"""MuMu 12 manager locations and installation roots shared by discovery and IPC."""

from pathlib import Path

_MANAGER_LOCATIONS = (
    "shell/MuMuManager.exe",
    "nx_main/MuMuManager.exe",
    "temp/main/MuMuManager.exe",
    "temp/shell/MuMuManager.exe",
    "MuMuManager.exe",
)


def installation_root(folder: Path) -> Path:
    """Resolve runtime directory pairs before root-level ``shell``/``nx_main``."""
    name = folder.name.lower()
    if folder.parent.name.lower() in {"temp", ".backup"} and name in {
        "main",
        "shell",
        "nx_main",
    }:
        return folder.parent.parent
    return folder.parent if name in {"shell", "nx_main"} else folder


def manager_candidates(root: Path) -> list[Path]:
    """Return every known manager location for one installation *root*."""
    return [root / location for location in _MANAGER_LOCATIONS]
