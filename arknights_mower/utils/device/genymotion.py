"""Genymotion Desktop's verified gmtool contract, limited to Linux records."""

import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.manager_io import (
    MAX_INSTANCES,
    MAX_OUTPUT,
    run_manager_command,
)
from arknights_mower.utils.device.preflight import PreflightError
from arknights_mower.utils.device.session import InstanceObservation
from arknights_mower.utils.path import resolve_config_path

GENYMOTION_PRESET = "linux.genymotion"
COMMAND_TIMEOUT = 3.0
DISCOVERY_TIMEOUT = 10.0
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def genymotion_repair(error):
    return PreflightError(error.code, str(error), "manual", error.fields)


def _invalid_output():
    return InstanceBindingError(
        "manager_output_invalid",
        "gmtool 输出不完整或格式不兼容，无法确认 VM 与当前端点；请使用高级手动配置。",
        [],
    )


class GenymotionController:
    def __init__(self, *, run=None, which=None, host=None, monotonic=time.monotonic):
        self.run = run or run_manager_command
        self.which = which or shutil.which
        self.host = host or sys.platform
        self.monotonic = monotonic

    def _manager(self, profile):
        if self.host != "linux":
            raise InstanceBindingError(
                "unsupported_host",
                "Genymotion 兼容性记录预设仅用于 Linux。",
                ["preset_id"],
            )
        if profile.manager_path.strip():
            candidates = [Path(resolve_config_path(profile.manager_path))]
        elif profile.installation_path.strip():
            candidates = [
                Path(resolve_config_path(profile.installation_path)) / "gmtool"
            ]
        else:
            candidates = [
                Path.home() / "genymotion/gmtool",
                Path("/opt/genymotion/gmtool"),
            ]
            path = self.which("gmtool")
            if path:
                candidates.append(Path(path))
        for candidate in candidates:
            try:
                if candidate.is_file():
                    if not os.access(candidate, os.X_OK):
                        raise PermissionError("gmtool is not executable")
                    return str(candidate.resolve())
            except OSError as exc:
                raise InstanceBindingError(
                    "discovery_permission_denied",
                    "无法读取或执行 gmtool，请检查管理程序路径与权限，或使用高级手动配置。",
                    ["manager_path"],
                ) from exc
        raise InstanceBindingError(
            "missing_installation",
            "未找到官方 gmtool，请填写管理程序路径或使用高级手动配置。",
            ["manager_path"],
        )

    def _command(self, manager, arguments, deadline, *, launch=False):
        shared = io_timeout(deadline - self.monotonic())
        if shared <= 0:
            raise InstanceBindingError(
                "manager_timeout", "gmtool 操作时间预算已耗尽。", []
            )
        try:
            result = self.run(
                [manager, *arguments],
                timeout=shared if launch else min(shared, COMMAND_TIMEOUT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                env={**os.environ, "LC_ALL": "C", "LANG": "C"},
            )
            result.check_returncode()
        except (TimeoutError, subprocess.TimeoutExpired) as exc:
            raise InstanceBindingError(
                "manager_timeout",
                "gmtool 响应超时，请检查所选 VM 或使用高级手动配置。",
                [],
            ) from exc
        except PermissionError as exc:
            raise InstanceBindingError(
                "discovery_permission_denied",
                "无法执行 gmtool，请检查权限或使用高级手动配置。",
                ["manager_path"],
            ) from exc
        except subprocess.CalledProcessError as exc:
            message = (
                "当前 gmtool 许可无法查询 VM 详情，请使用高级手动配置。"
                if exc.returncode in {9, 10, 14}
                else "gmtool 无法确认所选 VM，请检查管理工具与 VM，或使用高级手动配置。"
            )
            raise InstanceBindingError("genymotion_unavailable", message, []) from exc
        except OSError as exc:
            raise InstanceBindingError(
                "genymotion_unavailable",
                "无法运行 gmtool，请检查路径或使用高级手动配置。",
                ["manager_path"],
            ) from exc
        except ValueError as exc:
            raise _invalid_output() from exc
        if self.monotonic() >= deadline:
            raise InstanceBindingError(
                "manager_timeout", "gmtool 操作时间预算已耗尽。", []
            )
        output, error = result.stdout or b"", result.stderr or b""
        if len(output) + len(error) > MAX_OUTPUT or error.strip():
            raise _invalid_output()
        try:
            return output.decode("utf-8", "strict")
        except UnicodeError as exc:
            raise _invalid_output() from exc

    def _version(self, manager, deadline):
        fields = self._fields(self._command(manager, ["version"], deadline))
        # Exact contract evidence is 3.9.0. Later versions add cloud VM support.
        if fields.get("Version") != "3.9.0":
            raise InstanceBindingError(
                "genymotion_version_unsupported",
                "此 gmtool 版本尚无已核验输出契约；当前仅自动识别 3.9.0，请使用高级手动配置。",
                [],
            )

    @staticmethod
    def _fields(output):
        fields = {}
        for line in output.splitlines():
            if not line.strip():
                continue
            key, separator, value = line.partition(":")
            key = key.strip()
            if not separator or not key or key in fields:
                raise _invalid_output()
            fields[key] = value.strip()
        return fields

    @staticmethod
    def _instance(identity, name, state, serial):
        if (
            not isinstance(identity, str)
            or not _UUID.fullmatch(identity)
            or identity == "00000000-0000-0000-0000-000000000000"
            or not isinstance(name, str)
            or not name.strip()
            or any(ord(char) < 32 for char in name)
            or state not in ("on", "off")
        ):
            raise _invalid_output()
        if state == "off":
            serial = ""
        else:
            if not isinstance(serial, str):
                raise _invalid_output()
            host, separator, port = serial.rpartition(":")
            try:
                address = ipaddress.ip_address(host.strip("[]"))
                if (
                    not separator
                    or address.is_unspecified
                    or address.is_multicast
                    or not re.fullmatch(r"[0-9]{1,5}", port)
                    or not 0 < int(port) < 65536
                    or (address.version == 6 and host != f"[{address}]")
                    or (address.version == 4 and host != str(address))
                ):
                    raise ValueError()
            except ValueError as exc:
                raise _invalid_output() from exc
        return {
            "instance_id": identity,
            "instance_name": name,
            "state": "running" if state == "on" else "stopped",
            "serial": serial,
        }

    def discover(self, profile, host, timeout=DISCOVERY_TIMEOUT):
        result = {"installations": [], "errors": []}
        try:
            manager = self._manager(profile)
            deadline = self.monotonic() + max(timeout, 0)
            self._version(manager, deadline)
            try:
                document = json.loads(
                    self._command(
                        manager, ["--format", "json", "admin", "list"], deadline
                    )
                )
            except (ValueError, TypeError) as exc:
                if isinstance(exc, InstanceBindingError):
                    raise
                raise _invalid_output() from exc
            if (
                not isinstance(document, dict)
                or type(document.get("exit_code")) is not int
                or document["exit_code"] != 0
            ):
                raise _invalid_output()
            rows = document.get("instances")
            if not isinstance(rows, list) or len(rows) > MAX_INSTANCES:
                raise _invalid_output()
            instances = []
            for row in rows:
                if not isinstance(row, dict):
                    raise _invalid_output()
                instances.append(
                    self._instance(
                        row.get("uuid"),
                        row.get("name"),
                        row.get("state"),
                        row.get("adb_serial"),
                    )
                )
            if len({row["instance_id"] for row in instances}) != len(instances):
                raise _invalid_output()
            if not instances:
                raise InstanceBindingError(
                    "no_genymotion",
                    "gmtool 未列出 VM，请在 Genymotion 中创建实例或使用高级手动配置。",
                    [],
                )
            result["installations"].append(
                {
                    "preset_id": GENYMOTION_PRESET,
                    "installation_path": str(Path(manager).parent),
                    "manager_path": manager,
                    "instances": instances,
                }
            )
        except InstanceBindingError as exc:
            result["errors"].append(genymotion_repair(exc))
        return result

    def _bound(self, profile, deadline):
        if not profile.manager_path.strip() or not _UUID.fullmatch(profile.instance_id):
            raise InstanceBindingError(
                "genymotion_binding_changed",
                "请重新检测并选择 Genymotion VM，保存 gmtool 路径与完整 UUID；也可使用高级手动配置。",
                ["manager_path", "instance_id"],
            )
        manager = self._manager(profile)
        self._version(manager, deadline)
        fields = self._fields(
            self._command(manager, ["admin", "details", profile.instance_id], deadline)
        )
        if fields.get("UUID") != profile.instance_id:
            raise InstanceBindingError(
                "genymotion_binding_changed",
                "gmtool 未返回所选 VM 的 UUID，请重新选择实例或使用高级手动配置。",
                ["instance_id"],
            )
        state = fields.get("State")
        if state not in {"On", "Off"}:
            raise _invalid_output()
        instance = self._instance(
            fields.get("UUID"),
            fields.get("Name"),
            state.lower(),
            fields.get("ADB Serial"),
        )
        return manager, instance

    def inspect(self, profile, timeout):
        _, instance = self._bound(profile, self.monotonic() + timeout)
        return InstanceObservation(instance["state"], instance["serial"] or None)

    def start_confirmed(self, profile, timeout):
        deadline = self.monotonic() + timeout
        manager, instance = self._bound(profile, deadline)
        if instance["state"] == "stopped":
            self._command(
                manager, ["admin", "start", profile.instance_id], deadline, launch=True
            )
        # A zero exit alone is not readiness. DeviceControl checks details for
        # this UUID again, then the exact ADB target and the read-only preflight.
        return True

    def start(self, profile, timeout):
        return False

    def stop(self, profile, timeout):
        return False
