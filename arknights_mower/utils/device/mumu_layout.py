"""Shared MuMu 12 installation layout for discovery, IPC and ADB resolution.

MuMu 12 installs its manager below a runtime directory pair in some builds
(``temp/main``, ``temp/shell``) and keeps a copy under ``.backup``. The
installation root is therefore two levels above those directories, not the
directories themselves.
"""

from pathlib import Path

# Directories holding the manager one level below the installation root.
INSTALL_ROOT_LEVEL_LAYOUTS = frozenset({"shell", "nx_main"})
# Runtime directory pairs holding the manager two levels below the root.
INSTALL_RUNTIME_LEVEL_LAYOUTS = frozenset({"temp", "backup"})
MANAGER_FILENAME = "MuMuManager.exe"

_MANAGER_LOCATIONS = (
    "shell/MuMuManager.exe",
    "nx_main/MuMuManager.exe",
    "temp/main/MuMuManager.exe",
    "temp/shell/MuMuManager.exe",
    "MuMuManager.exe",
)


def runtime_pair_root(folder: Path) -> Path | None:
    """Return the installation root when *folder* is ``temp/<pair>`` or ``.backup/<pair>``."""
    parent = folder.parent
    if parent.name.lstrip(".").lower() not in INSTALL_RUNTIME_LEVEL_LAYOUTS:
        return None
    if folder.name.lower() not in INSTALL_ROOT_LEVEL_LAYOUTS | {"main"}:
        return None
    return parent.parent


def manager_candidates(root: Path) -> list[Path]:
    """Return every known manager location for one installation *root*."""
    return [root / location for location in _MANAGER_LOCATIONS]
