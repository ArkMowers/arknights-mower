"""Shared installation layout for verified capture and the running IPC adapter."""

from pathlib import Path

from arknights_mower.utils.device.mumu_layout import (
    installation_root,
    manager_candidates,
)
from arknights_mower.utils.path import resolve_config_path


def resolve_mumu_paths(installation: str, manager: str = "") -> tuple[str, str]:
    if manager:
        executable = Path(resolve_config_path(manager))
    else:
        executable = None

    if installation:
        folder = Path(resolve_config_path(installation))
    elif executable:
        folder = executable.parent
    else:
        folder = Path()
    root = installation_root(folder)

    if not executable:
        candidates = manager_candidates(root)
        executable = next(
            (path for path in candidates if path.is_file()), candidates[0]
        )
    return str(root), str(executable)
