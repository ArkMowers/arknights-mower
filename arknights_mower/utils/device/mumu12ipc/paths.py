"""Shared installation layout for verified capture and the running IPC adapter."""

from pathlib import Path

from arknights_mower.utils.path import resolve_config_path


def resolve_mumu_paths(installation: str, manager: str = "") -> tuple[str, str]:
    if manager:
        executable = Path(resolve_config_path(manager))
    else:
        executable = None

    if installation:
        folder = Path(resolve_config_path(installation))
        root = folder.parent if folder.name.lower() in {"shell", "nx_main"} else folder
    elif executable:
        root = (
            executable.parent.parent
            if executable.parent.name.lower() in {"shell", "nx_main"}
            else executable.parent
        )
    else:
        root = Path()

    if not executable:
        candidates = (
            root / "shell/MuMuManager.exe",
            root / "nx_main/MuMuManager.exe",
            root / "MuMuManager.exe",
        )
        executable = next(
            (path for path in candidates if path.is_file()), candidates[0]
        )
    return str(root), str(executable)
