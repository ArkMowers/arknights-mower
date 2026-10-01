"""Read-only endpoint verification for one explicitly bound LDPlayer instance."""

import csv
import ipaddress
import os
import subprocess
import time
from pathlib import Path

from arknights_mower.utils.device.adb_client.server import current_adb_server, guard_adb
from arknights_mower.utils.device.endpoint_identity import (
    BOOT_ID_COMMAND,
    InstanceBindingError,
    connect_endpoint_candidates,
    parse_adb_devices,
    parse_boot_id,
    run_endpoint_command,
)
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.manager_io import (
    MAX_INSTANCES,
    run_manager_command,
)

# Compatibility name for existing adapter callers.
LDPlayerBindingError = InstanceBindingError


class LDPlayerEndpointResolver:
    """Manager identity must agree with the selected ADB's exact endpoint."""

    def __init__(
        self, *, run=None, probe=None, monotonic=time.monotonic, listener_ports=None
    ):
        self._run = run or run_manager_command
        self._probe = probe
        self._monotonic = monotonic
        self._listener_ports = listener_ports

    def inspect(self, profile, manager, timeout):
        from arknights_mower.utils.device.ldplayer_discovery import (
            InstanceNameChanged,
            parse_ldplayer_instances,
        )
        from arknights_mower.utils.device.session import InstanceObservation

        deadline = self._monotonic() + max(0, timeout)

        def remaining():
            available = deadline - self._monotonic()
            if available <= 0:
                raise TimeoutError("雷电实例验证时间预算已耗尽")
            return io_timeout(min(3, available))

        def run(argv, *, adb=False, delegated_adb=False):
            output = run_endpoint_command(
                argv,
                timeout=remaining(),
                run=self._run,
                probe=self._probe,
                monotonic=self._monotonic,
                adb=adb,
                delegated_adb=delegated_adb,
            )
            remaining()
            return output

        def observe_instance():
            try:
                instances, _ = parse_ldplayer_instances(
                    run([str(manager), "list2"]),
                    profile.instance_id,
                    profile.instance_name,
                )
                return instances[0]
            except (ValueError, csv.Error) as exc:
                if isinstance(exc, LDPlayerBindingError):
                    raise
                # The index alone cannot prove this is still the saved instance;
                # a re-created index must send the caller back to detection.
                if isinstance(exc, InstanceNameChanged):
                    raise LDPlayerBindingError(
                        "binding_changed",
                        str(exc),
                        ["instance_id", "instance_name"],
                    ) from exc
                raise LDPlayerBindingError(
                    "manager_output", str(exc), ["manager_path", "instance_id"]
                ) from exc

        instance = observe_instance()
        if instance["state"] != "running":
            return InstanceObservation(instance["state"])
        if not profile.adb_path:
            raise LDPlayerBindingError(
                "missing_adb", "请指定有效的 ADB 程序", ["adb_path"]
            )
        bundled_adb = Path(manager).parent / "adb.exe"
        if not bundled_adb.is_file():
            raise LDPlayerBindingError(
                "missing_adb",
                "雷电管理器目录缺少 adb.exe",
                ["manager_path", "adb_path"],
            )
        # ldconsole delegates its adb command to the bundled executable. Check
        # that client before it can implicitly replace a shared ADB server.
        guard_adb(
            str(bundled_adb),
            timeout=remaining(),
            run=self._run,
            probe=self._probe,
            monotonic=self._monotonic,
        )

        def manager_boot_id():
            boot_id = parse_boot_id(
                run(
                    [
                        str(manager),
                        "adb",
                        "--index",
                        profile.instance_id,
                        "--command",
                        BOOT_ID_COMMAND,
                    ],
                    delegated_adb=True,
                )
            )
            if not boot_id:
                raise LDPlayerBindingError(
                    "endpoint_unresolved",
                    "雷电管理器未返回可验证的实例启动标识，请手动检查 ADB 地址",
                )
            return boot_id

        owned = current_adb_server() is not None
        boot_id = None if owned else manager_boot_id()
        output = run([profile.adb_path, "devices", "-l"], adb=True)
        rows = parse_adb_devices(output)
        index = int(profile.instance_id)
        candidates = [profile.last_serial]
        if 5555 + index * 2 < 65536:
            candidates.extend(
                [f"emulator-{5554 + index * 2}", f"127.0.0.1:{5555 + index * 2}"]
            )
        # Only sockets owned by this list2 VBox process can supply additional
        # candidates. Never probe every online ADB device looking for a match.
        listener_error = None
        ports = []
        try:
            ports = (
                self._listener_ports(instance["vbox_pid"], remaining())
                if self._listener_ports is not None
                else self._windows_listeners(instance["vbox_pid"], run)
            )
            if len(ports) > MAX_INSTANCES:
                raise ValueError("所选雷电实例的监听端口超过 64 个")
            candidates.extend(ports)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            listener_error = str(exc)
        if owned:
            candidates = list(
                dict.fromkeys(
                    candidate for candidate in [*ports, *candidates] if candidate
                )
            )
            candidates.sort(key=lambda serial: serial.startswith("emulator-"))
            connect_endpoint_candidates(
                profile.adb_path,
                [serial for serial in candidates if rows.get(serial) != ["device"]],
                run,
            )
            boot_id = manager_boot_id()
            rows = parse_adb_devices(run([profile.adb_path, "devices", "-l"], adb=True))
        states = []
        matches = []
        for serial in dict.fromkeys(candidate for candidate in candidates if candidate):
            target_states = rows.get(serial, [])
            if len(target_states) > 1:
                raise LDPlayerBindingError(
                    "endpoint_ambiguous", "ADB 返回重复端点，请手动检查 ADB 地址"
                )
            if not target_states:
                continue
            state = target_states[0]
            states.append(state)
            if state != "device":
                continue
            try:
                candidate_boot = parse_boot_id(
                    run(
                        [profile.adb_path, "-s", serial, *BOOT_ID_COMMAND.split()],
                        adb=True,
                    )
                )
            except (ValueError, subprocess.CalledProcessError):
                # A stale endpoint may disappear after the device-list read.
                # Keep checking only this instance's remaining candidates.
                continue
            if candidate_boot == boot_id:
                matches.append(serial)
        confirmed = observe_instance()
        if (
            confirmed["state"] != "running"
            or confirmed["pid"] != instance["pid"]
            or confirmed["vbox_pid"] != instance["vbox_pid"]
        ):
            raise LDPlayerBindingError(
                "binding_changed",
                "雷电实例在验证期间重启或停止，请重新检测",
                ["instance_id"],
            )
        if profile.last_serial in matches:
            return InstanceObservation("running", profile.last_serial)
        if len(matches) == 1:
            return InstanceObservation("running", matches[0])
        if len(matches) > 1:
            raise LDPlayerBindingError(
                "endpoint_ambiguous", "所选雷电实例有多个有效 ADB 地址，请手动选择"
            )
        if "unauthorized" in states:
            raise LDPlayerBindingError(
                "device_unauthorized", "所选雷电实例的 ADB 尚未授权", []
            )
        if "offline" in states:
            raise LDPlayerBindingError(
                "device_offline", "所选雷电实例的 ADB 处于 offline 状态", []
            )
        message = "无法将 ADB 地址与所选雷电实例对应，请手动检查地址后重试"
        if listener_error:
            message += "；无法读取该实例的当前监听端口"
        raise LDPlayerBindingError("endpoint_unresolved", message)

    @staticmethod
    def _windows_listeners(vbox_pid, run):
        if os.name != "nt":
            return []
        if type(vbox_pid) is not int or vbox_pid <= 0:
            raise ValueError("雷电 VBox 进程 ID 无效")
        command = (
            "$ErrorActionPreference='Stop'; "
            "Get-NetTCPConnection -State Listen -OwningProcess "
            f"{vbox_pid} | ForEach-Object "
            "{ '{0},{1}' -f $_.LocalAddress,$_.LocalPort }"
        )
        powershell = (
            Path(os.environ.get("SystemRoot", "C:/Windows"))
            / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        output = run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", command]
        )
        candidates = []
        for line in output.decode("ascii", "strict").splitlines():
            if not line.strip():
                continue
            host, port = line.strip().split(",")
            address = ipaddress.ip_address(host)
            if not port.isdecimal() or not 0 < int(port) < 65536:
                raise ValueError("雷电进程监听端口无效")
            if address.is_unspecified:
                address = ipaddress.ip_address(
                    "127.0.0.1" if address.version == 4 else "::1"
                )
            if address.is_loopback:
                host = str(address) if address.version == 4 else f"[{address}]"
                candidates.append(f"{host}:{port}")
                if int(port) % 2 == 0:
                    candidates.append(f"emulator-{port}")
        return candidates
