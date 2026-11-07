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


def renderer_candidates(root: str) -> list[str]:
    root_path = Path(root)
    renderer = root_path / "nx_device/12.0/shell/sdk/external_renderer_ipc.dll"
    if renderer.is_file():
        return [str(renderer)]
    locations = (
        "shell/sdk/external_renderer_ipc.dll",
        "nx_main/sdk/external_renderer_ipc.dll",
        "sdk/external_renderer_ipc.dll",
        "nx_device/12.0/shell/sdk/external_renderer_ipc.dll",
        "nx_device/15.0/shell/sdk/external_renderer_ipc.dll",
    )
    parents = (
        "shell/sdk/external_renderer_ipc.dll",
        "nx_main/sdk/external_renderer_ipc.dll",
        "sdk/external_renderer_ipc.dll",
    )
    return [str(root_path / path) for path in locations] + [
        str(root_path.parent / path) for path in parents
    ]
