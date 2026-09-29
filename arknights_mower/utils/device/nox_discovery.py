"""Read-only Nox inventory: official VM names plus validated VBox identities.

Only the known BignoxVMS layout is accepted. Unsupported/moved layouts remain
manual; a console row or a reusable multi-instance number is never enough.
"""

import csv
import io
import os
import re
import stat
import time
import xml.etree.ElementTree as ET
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from arknights_mower.utils.device.manager_io import MAX_INSTANCES, MAX_OUTPUT
from arknights_mower.utils.device.preflight import PreflightError
from arknights_mower.utils.device.windows_discovery import WindowsInstallationDiscovery
from arknights_mower.utils.path import resolve_config_path

VM_NAME = r"[A-Za-z][A-Za-z0-9_-]*"
VBOX_NS = "{http://www.innotek.de/VirtualBox-settings}"


def parse_nox_list(output):
    if isinstance(output, bytes):
        if len(output) > MAX_OUTPUT:
            raise ValueError("夜神管理器输出超过 1 MiB。")
        try:
            output = output.decode("utf-8-sig")
        except UnicodeDecodeError:
            output = output.decode("gb18030")
    if len(output.encode("utf-8")) > MAX_OUTPUT:
        raise ValueError("夜神管理器输出超过 1 MiB。")
    instances = {}
    try:
        for row in csv.reader(io.StringIO(output), strict=True):
            if not row:
                continue
            row = [value.strip() for value in row]
            modern = len(row) in {7, 8} and row[0].isdecimal()
            if modern:
                row = row[1:]
            pid_count = 2 if modern else 1
            if (
                len(row) not in ({6, 7} if modern else {6})
                or not re.fullmatch(VM_NAME, row[0])
                or row[0].casefold() in instances
                or not row[1]
                or any(
                    not re.fullmatch(r"(?:0x)?[0-9A-Fa-f]+", value)
                    for value in row[2:-pid_count]
                )
                or any(
                    not re.fullmatch(r"-1|[0-9]+", value) for value in row[-pid_count:]
                )
            ):
                raise ValueError("夜神 list 未返回唯一 VM 名称、标题和进程状态。")
            instances[row[0].casefold()] = {
                "instance_id": row[0],
                "instance_name": row[1],
                "state": (
                    "running"
                    if all(int(pid) > 0 for pid in row[-pid_count:])
                    else "starting"
                    if any(int(pid) > 0 for pid in row[-pid_count:])
                    else "stopped"
                ),
                "pid": tuple(int(pid) for pid in row[-pid_count:]),
                "serial": "",
            }
            if len(instances) > MAX_INSTANCES:
                raise ValueError("夜神实例超过 64 个，无法完整确认拓扑。")
    except csv.Error as exc:
        raise ValueError("夜神 list 格式无效。") from exc
    return list(instances.values())


def read_nox_vm(manager, name):
    if not re.fullmatch(VM_NAME, name):
        raise ValueError("夜神 VM 名称无效，请重新检测。")
    root = Path(manager).parent.resolve()
    path = (root / "BignoxVMS" / name / f"{name}.vbox").resolve()
    if not path.is_relative_to(root):
        raise ValueError("夜神 VM 配置不在已验证的安装目录，请使用手动配置。")
    with path.open("rb") as stream:
        content = stream.read(MAX_OUTPUT + 1)
    if len(content) > MAX_OUTPUT:
        raise ValueError("夜神 VM 配置超过 1 MiB。")
    # Reject declarations before parsing, including UTF-16/32 encodings.
    declarations = content.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in declarations or b"<!ENTITY" in declarations:
        raise ValueError("夜神 VM 配置含不支持的 XML 声明。")
    try:
        document = ET.fromstring(content)
        machines = document.findall(f"{VBOX_NS}Machine")
        if document.tag != f"{VBOX_NS}VirtualBox" or len(machines) != 1:
            raise ValueError("夜神 VM 配置缺少唯一 Machine。")
        machine = machines[0]
        identity = UUID(machine.attrib["uuid"].strip("{}"))
        if identity.int == 0 or machine.attrib["name"] != name:
            raise ValueError("夜神 VM 名称或 UUID 与管理器不一致。")
    except (ET.ParseError, KeyError, ValueError) as exc:
        raise ValueError(f"夜神 VM 身份无法验证：{exc}") from exc
    return str(identity), machine


def nox_inventory(manager, output, *, deadline=None, monotonic=time.monotonic):
    instances = parse_nox_list(output)
    identities = set()
    for instance in instances:
        if deadline is not None and monotonic() >= deadline:
            raise TimeoutError("夜神拓扑复核超时。")
        identity, _ = read_nox_vm(manager, instance["instance_id"])
        if identity in identities:
            raise ValueError("夜神多个 VM 使用相同 UUID，请修复后重新检测。")
        identities.add(identity)
        instance["instance_uuid"] = identity
    snapshot = "\n".join(
        sorted(f"{item['instance_id']}:{item['instance_uuid']}" for item in instances)
    )
    fingerprint = sha256(snapshot.encode()).hexdigest()
    for instance in instances:
        instance["topology_fingerprint"] = fingerprint
    return instances


def locate_nox_manager(candidate):
    path = Path(resolve_config_path(str(candidate))).resolve()
    if path.suffix.lower() == ".exe":
        if path.name.lower() not in {"nox.exe", "noxconsole.exe"}:
            return None, None
        roots = [path.parent]
    else:
        roots = [path, path / "bin"]
    for root in roots:
        manager = root / "NoxConsole.exe"
        try:
            if stat.S_ISREG(manager.stat().st_mode):
                return manager, root
        except FileNotFoundError:
            continue
    return None, path


class NoxDiscoveryIO(WindowsInstallationDiscovery):
    product = "夜神模拟器"
    preset_id = "windows.nox"
    process_names = ("Nox.exe", "NoxConsole.exe")
    _manager_candidate = staticmethod(locate_nox_manager)

    def _instances(self, manager, timeout):
        deadline = self._monotonic() + timeout
        result = self._command([str(manager), "list"], timeout)
        if result.stderr.strip():
            raise ValueError("夜神管理器报告错误，请检查管理程序。")
        return nox_inventory(
            manager, result.stdout, deadline=deadline, monotonic=self._monotonic
        ), []

    @staticmethod
    def _read_fixed_paths():
        return [
            str(Path(root) / "Nox/bin")
            for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")
            if (root := os.environ.get(name))
        ]

    @classmethod
    def _read_registry_paths(cls):
        from arknights_mower.utils.device.windows_discovery import uninstall_executable

        base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        for entry in cls._iterate_registry_keys(base, ("Nox", "Nox64"), cls._failure):
            if isinstance(entry, PreflightError):
                yield entry
                continue
            try:
                location = entry.get("InstallLocation")
            except KeyError:
                location = ""
            if isinstance(location, str) and location.strip():
                yield location.strip().strip('"')
                continue
            uninstall = entry.get("UninstallString")
            if not isinstance(uninstall, str):
                raise ValueError("夜神卸载注册信息不是有效路径。")
            # Extract only the executable path; never execute registry command
            # text or treat its arguments as installation paths.
            executable = uninstall_executable(uninstall)
            if executable is None:
                raise ValueError("夜神卸载注册信息无法解析为程序路径。")
            found = False
            for root in (executable.parent, executable.parent.parent):
                manager, _ = locate_nox_manager(root)
                if manager is not None:
                    found = True
                    yield str(manager)
            if not found:
                raise ValueError("夜神卸载注册信息附近缺少有效管理器。")
