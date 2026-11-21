"""Read-only MuMu 12 discovery from finite Windows installation sources.

The manager's documented ``info`` command is the instance authority. Registry
and process paths are candidates only; no port is inferred from an index.
"""

import os
import re
import stat
from collections import Counter
from pathlib import Path

from arknights_mower.utils.device.endpoint_identity import (
    InstanceBindingError,
    ManagerQueryTimeout,
)
from arknights_mower.utils.device.manager_io import (
    MAX_INSTANCES,
    run_manager_command,
)
from arknights_mower.utils.device.mumu_info import (
    MuMuEndpointUnavailable,
    mumu_endpoint_with_fallback,
    mumu_entries,
    verify_mumu_created_timestamp,
)
from arknights_mower.utils.device.mumu_layout import (
    installation_root,
    manager_candidates,
)
from arknights_mower.utils.device.preflight import PreflightError
from arknights_mower.utils.device.windows_discovery import WindowsInstallationDiscovery
from arknights_mower.utils.path import resolve_config_path

# Retain the existing adapter import while sharing bounded command execution.
run_mumu_command = run_manager_command


def _error(code, message, fields=None):
    return PreflightError(code, message, fields=fields or [])


def _confirmed_name(entry, key, saved_name, require_name):
    """Return the reported name only when it still identifies the saved instance.

    An index may be reused by a different instance after create, clone, delete or
    restore. A saved name that no longer matches is not a binding. Enumeration
    needs a name to offer; a saved binding without one still binds by index.
    """
    name = entry.get("name", "")
    if not isinstance(name, str):
        raise ValueError(f"MuMu 实例 {key} 缺少可识别名称。")
    name = name.strip()
    if require_name and not name:
        raise ValueError(f"MuMu 实例 {key} 缺少可识别名称。")
    if saved_name and name != saved_name:
        raise ValueError(
            f"MuMu 实例 {key} 的名称已不再是「{saved_name}」，"
            "无法确认原实例，请重新查找并选择实例。"
        )
    return name


def parse_mumu_instances(
    output,
    selected_id=None,
    instance_name=None,
    *,
    manager="",
    run=None,
    manual_serial="",
    expected_created="",
    require_endpoint=True,
):
    """Return valid observations plus individual parse failures.

    Both keyed ``info -v all`` and the direct object from ``info -v N`` are
    accepted. Repeated or conflicting identifiers never become a binding, and a
    saved ``instance_name`` must still match the manager's own report.
    """
    entries = mumu_entries(output)
    errors = []
    # Enumeration must offer a name; a saved binding without one binds by index.
    binding = instance_name is not None
    saved_name = instance_name.strip() if isinstance(instance_name, str) else ""
    if selected_id is not None:
        entries = [(key, entry) for key, entry in entries if key == selected_id]
        if len(entries) != 1:
            raise ValueError("管理器无法唯一确认已绑定的 MuMu 实例。")
    duplicates = {
        key for key, count in Counter(key for key, _ in entries).items() if count > 1
    }
    if len(entries) > MAX_INSTANCES:
        errors.append(
            _error("discovery_limit", "MuMu 实例超过 64 个，请缩小检测范围。")
        )
        entries = entries[:MAX_INSTANCES]
    instances = []
    for key, entry in entries:
        try:
            if (
                not re.fullmatch(r"0|[1-9][0-9]*", key)
                or key in duplicates
                or not isinstance(entry, dict)
                or ("index" in entry and str(entry["index"]) != key)
            ):
                raise ValueError("MuMu 管理器返回的实例身份不明确。")
            if entry.get("error_code", 0) != 0:
                raise ValueError(f"MuMu 管理器无法读取实例 {key}。")
            process = entry.get("is_process_started")
            android = entry.get("is_android_started")
            if not isinstance(process, bool) or (
                process and not isinstance(android, bool)
            ):
                raise ValueError(f"MuMu 实例 {key} 没有明确的运行状态。")
            name = _confirmed_name(entry, key, saved_name, not binding)
            created = verify_mumu_created_timestamp(entry, key, expected_created)
            state = "stopped" if not process else "running" if android else "starting"
            serial = ""
            if (
                require_endpoint
                and process
                and not ((manual_serial or expected_created) and state == "starting")
                and (entry.get("adb_port") or state == "running")
            ):
                try:
                    serial, created = mumu_endpoint_with_fallback(
                        entry,
                        key,
                        manager,
                        run,
                        manual_serial,
                        verify_conflicts=bool(expected_created),
                    )
                except ManagerQueryTimeout as exc:
                    exc.mumu_created_timestamp = created
                    raise
                except MuMuEndpointUnavailable as exc:
                    if selected_id is not None:
                        exc.mumu_created_timestamp = created
                        raise
                    errors.append(
                        PreflightError(
                            exc.code, str(exc), action="manual", fields=exc.fields
                        )
                    )
            instances.append(
                {
                    "instance_id": key,
                    "instance_name": name.strip() or f"MuMu 实例 {key}",
                    "state": state,
                    "serial": serial,
                    "mumu_created_timestamp": created,
                }
            )
        except ValueError as exc:
            if selected_id is not None:
                raise
            if isinstance(exc, InstanceBindingError):
                errors.append(
                    PreflightError(
                        exc.code,
                        str(exc),
                        action="manual"
                        if isinstance(exc, MuMuEndpointUnavailable)
                        else "retry",
                        fields=exc.fields,
                    )
                )
            else:
                errors.append(_error("manager_output", str(exc), ["manager_path"]))
    return instances, errors


class MuMuDiscoveryIO(WindowsInstallationDiscovery):
    product = "MuMu"
    preset_id = "windows.mumu12"
    process_names = (
        "MuMuPlayer.exe",
        "MuMuNxDevice.exe",
        "MuMuManager.exe",
        "YXArkNights.exe",
    )

    def _instances(self, manager, timeout):
        deadline = self._monotonic() + timeout

        def run(argv):
            remaining = min(timeout, deadline - self._monotonic())
            if remaining <= 0:
                raise TimeoutError("MuMu 实例查询超时")
            return self._command(argv, remaining).stdout

        output = run([str(manager), "info", "-v", "all"])
        return parse_mumu_instances(output, manager=str(manager), run=run)

    @staticmethod
    def _manager_candidate(candidate):
        path = Path(resolve_config_path(str(candidate))).resolve()

        def is_file(value):
            try:
                return stat.S_ISREG(value.stat().st_mode)
            except FileNotFoundError:
                return False

        if path.name.lower() == "mumumanager.exe":
            root = installation_root(path.parent)
            return (path, root) if is_file(path) else (None, root)
        if path.name.lower() == "mumunxdevice.exe":
            if (
                len(path.parents) < 4
                or path.parent.name.lower() != "shell"
                or path.parents[2].name.lower() != "nx_device"
            ):
                return None, None
            root = path.parents[3]
        else:
            folder = path.parent if path.suffix.lower() == ".exe" else path
            root = installation_root(folder)
        for manager in manager_candidates(root):
            if is_file(manager):
                return manager, root
        return None, root

    @classmethod
    def _read_registry_paths(cls):
        from arknights_mower.utils.device.windows_discovery import uninstall_executable

        # Verified MuMu 12 uninstall entries; no recursive registry/disk search.
        base = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\"
        names = (
            "MuMuPlayer-12.0",
            "MuMuPlayer",
            "MuMuPlayerGlobal-12.0",
            "YXArkNights-12.0",
            "YXArkNights",
            "MuMuPlayer-YXArkNights-12.0",
            "MuMuPlayer-YXArkNights",
        )
        for entry in cls._iterate_registry_keys(base, names, cls._failure):
            if isinstance(entry, PreflightError):
                yield entry
                continue
            for field in ("InstallLocation", "UninstallString"):
                try:
                    value = entry.get(field)
                except KeyError:
                    continue
                if not isinstance(value, str) or not value.strip():
                    continue
                if field == "UninstallString":
                    executable = uninstall_executable(value)
                    if executable is None:
                        continue
                    value = str(executable.parent)
                yield value.strip().strip('"')

    @staticmethod
    def _read_fixed_paths():
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            folder = os.environ.get(variable)
            if folder:
                for name in (
                    "MuMuPlayer-12.0",
                    "MuMuPlayer",
                    "YXArkNights-12.0",
                    "YXArkNights",
                ):
                    yield str(Path(folder) / "Netease" / name)
