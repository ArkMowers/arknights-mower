"""Shared installation layout for verified capture and the running IPC adapter."""

from pathlib import Path

from arknights_mower.utils.device.mumu_layout import (
    manager_candidates,
    runtime_pair_root,
)
from arknights_mower.utils.path import resolve_config_path


def resolve_mumu_paths(installation: str, manager: str = "") -> tuple[str, str]:
    if manager:
        executable = Path(resolve_config_path(manager))
    else:
        executable = None

    if installation:
        folder = Path(resolve_config_path(installation))
        if folder.name.lower() in {"shell", "nx_main"}:
            root = folder.parent
        else:
            root = runtime_pair_root(folder) or folder
    elif executable:
        if executable.parent.name.lower() in {"shell", "nx_main"}:
            root = executable.parent.parent
        else:
            root = runtime_pair_root(executable.parent) or executable.parent
    else:
        root = Path()

    if not executable:
        candidates = manager_candidates(root)
        executable = next(
            (path for path in candidates if path.is_file()), candidates[0]
        )
    return str(root), str(executable)
