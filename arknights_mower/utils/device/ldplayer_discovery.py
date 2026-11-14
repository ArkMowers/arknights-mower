"""LDPlayer 9 observations from registered applications and official list2.

The index is the vendor identity, never the row position. No list2 field is an
ADB endpoint; endpoint verification is deferred until an instance is selected.
"""

import csv
import io
import re
import stat
from collections import Counter
from pathlib import Path

from arknights_mower.utils.device.manager_io import MAX_INSTANCES, MAX_OUTPUT
from arknights_mower.utils.device.preflight import PreflightError
from arknights_mower.utils.device.windows_discovery import (
    RegistryValues,
    WindowsInstallationDiscovery,
)
from arknights_mower.utils.path import resolve_config_path


class InstanceNameChanged(ValueError):
    """The saved instance name no longer identifies the selected index."""


def parse_ldplayer_instances(output, selected_id=None, instance_name=None):
    if isinstance(output, bytes):
        if len(output) > MAX_OUTPUT:
            raise ValueError("雷电管理器输出超过 1 MiB。")
        try:
            output = output.decode("utf-8-sig")
        except UnicodeDecodeError:
            output = output.decode("gb18030")
    if len(output.encode("utf-8")) > MAX_OUTPUT:
        raise ValueError("雷电管理器输出超过 1 MiB。")
    rows = list(csv.reader(io.StringIO(output), strict=True))
    rows = [row for row in rows if row]
    counts = Counter(row[0].strip() for row in rows)
    errors = []
    instances = []
    for row in rows:
        try:
            row = [field.strip() for field in row]
            index = row[0]
            if (
                len(row) not in {7, 10}
                or not re.fullmatch(r"0|[1-9][0-9]*", index)
                or counts[index] != 1
                or not row[1]
                or any(not re.fullmatch(r"[0-9]+", value) for value in row[2:4])
                or row[4] not in {"0", "1"}
                or any(not re.fullmatch(r"-1|[0-9]+", value) for value in row[5:7])
                or any(not re.fullmatch(r"[1-9][0-9]*", value) for value in row[7:])
            ):
                raise ValueError("雷电 list2 未返回明确且唯一的实例身份或运行状态。")
            pid, vbox_pid = int(row[5]), int(row[6])
            if row[4] == "1" and (pid <= 0 or vbox_pid <= 0):
                raise ValueError("雷电 list2 的 Android 状态与进程状态不一致。")
            state = (
                "stopped"
                if pid <= 0 and vbox_pid <= 0
                else "running"
                if row[4] == "1"
                else "starting"
            )
            instances.append(
                {
                    "instance_id": index,
                    "instance_name": row[1],
                    "state": state,
                    "serial": "",
                    "pid": pid,
                    "vbox_pid": vbox_pid,
                    **(
                        {"display_size": [int(row[7]), int(row[8])]}
                        if len(row) == 10
                        else {}
                    ),
                }
            )
        except ValueError as exc:
            errors.append(
                PreflightError("manager_output", str(exc), fields=["manager_path"])
            )
    if selected_id is not None:
        matches = [item for item in instances if item["instance_id"] == selected_id]
        if len(matches) != 1:
            raise ValueError("雷电管理器无法确认原实例仍然存在，请检查绑定或重新检测。")
        # An index may be reused by a different instance after create, clone,
        # delete or restore. A saved name that no longer matches is not a binding.
        if (
            isinstance(instance_name, str)
            and instance_name.strip()
            and matches[0]["instance_name"] != instance_name.strip()
        ):
            raise InstanceNameChanged(
                f"雷电实例 {selected_id} 的名称已不再是「{instance_name.strip()}」，"
                "无法确认原实例，请重新查找并选择实例。"
            )
        return matches, []
    if len(instances) > MAX_INSTANCES:
        errors.append(
            PreflightError("discovery_limit", "雷电实例超过 64 个，请缩小检测范围。")
        )
    return instances[:MAX_INSTANCES], errors


def locate_ldplayer_manager(candidate):
    path = Path(resolve_config_path(str(candidate))).resolve()
    if path.suffix.lower() == ".exe":
        # Only official console/player names are executable-path candidates.
        if path.name.lower() not in {
            "ldconsole.exe",
            "dnconsole.exe",
            "dnplayer.exe",
            "ldplayer.exe",
        }:
            return None, None
        root = path.parent
    else:
        root = path
    names = (
        (path.name,)
        if path.name.lower() in {"ldconsole.exe", "dnconsole.exe"}
        else ("ldconsole.exe", "dnconsole.exe")
    )
    for name in names:
        manager = root / name
        try:
            if stat.S_ISREG(manager.stat().st_mode):
                return manager, root
        except FileNotFoundError:
            continue
    return None, root


class LDPlayerDiscoveryIO(WindowsInstallationDiscovery):
    product = "雷电模拟器"
    preset_id = "windows.ldplayer9"
    process_names = ("dnplayer.exe", "ldplayer.exe", "ldconsole.exe", "dnconsole.exe")
    _manager_candidate = staticmethod(locate_ldplayer_manager)

    def _preset_for(self, root):
        normalized = str(root).replace("\\", "/").casefold()
        if re.search(r"(?:ldplayer|leidian|ld|雷电)[\w\s-]*14\b", normalized) or (
            "14" in normalized
            and any(
                k in normalized
                for k in ("ldplayer", "leidian", "ldconsole", "dnplayer")
            )
        ):
            return "windows.ldplayer14"
        return "windows.ldplayer9"

    def _instances(self, manager, timeout):
        result = self._command([str(manager), "list2"], timeout)
        try:
            return parse_ldplayer_instances(result.stdout)
        except csv.Error as exc:
            raise ValueError("雷电 list2 格式无效。") from exc

    @classmethod
    def _read_registry_paths(cls):
        import winreg

        base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        # This product has no fixed uninstall record name; only the documented
        # DisplayName/DisplayVersion pair identifies an entry.
        for entry in WindowsInstallationDiscovery._iterate_registry_keys(
            base, None, cls._failure
        ):
            if isinstance(entry, PreflightError):
                yield entry
                continue
            try:
                for index in range(winreg.QueryInfoKey(entry.handle)[0]):
                    yield from cls._registered_installation(entry, index)
            except FileNotFoundError:
                continue
            except KeyError:
                # Most uninstall entries have no DisplayName; only a matching
                # pair identifies this product, so a missing value is not an error.
                continue
            except OSError as exc:
                yield cls._failure(exc)

    @classmethod
    def _registered_installation(cls, entry, index):
        import winreg

        name = winreg.EnumKey(entry.handle, index)
        with winreg.OpenKey(entry.handle, name) as product:
            values = RegistryValues(product, winreg)
            display = values.get("DisplayName")
            version = values.get("DisplayVersion")
            if (
                not isinstance(display, str)
                or not re.fullmatch(
                    r"(?:LDPlayer|雷电模拟器)(?:\s*(?:9|14)(?:\.[0-9]+)*)?",
                    display,
                    re.I,
                )
                or not re.match(r"^(?:9|14)(?:\.|$)", str(version))
            ):
                return
            location = values.get("InstallLocation")
            if isinstance(location, str) and location.strip():
                yield location.strip().strip('"')
