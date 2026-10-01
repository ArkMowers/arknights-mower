"""Revalidate a Nox binding before exposing its current ADB endpoint."""

import ipaddress
import time
from pathlib import Path

from arknights_mower.utils.device.adb_client.server import guard_adb
from arknights_mower.utils.device.endpoint_identity import (
    BOOT_ID_COMMAND,
    InstanceBindingError,
    InstanceEndpointPending,
    parse_adb_devices,
    parse_boot_id,
    run_endpoint_command,
)
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.manager_io import run_manager_command
from arknights_mower.utils.device.nox_discovery import (
    VBOX_NS,
    nox_inventory,
    read_nox_vm,
)


class NoxBindingReader:
    def __init__(self, run=None, probe=None, monotonic=time.monotonic):
        self.run = run or run_manager_command
        self.probe = probe
        self.monotonic = monotonic

    def open(self, profile, manager, timeout):
        return _NoxObservation(self, profile, manager, timeout)

    def inspect(self, profile, manager, timeout):
        from arknights_mower.utils.device.session import InstanceObservation

        current = self.open(profile, manager, timeout)
        instance = current.instance()
        if instance["state"] != "running":
            return InstanceObservation(instance["state"])
        serial = current.endpoint(instance)
        return InstanceObservation("running", serial)

    def recover(self, profile, manager, timeout, reconnect):
        current = self.open(profile, manager, timeout)
        instance = current.instance()
        if instance["state"] != "running":
            return False
        try:
            current.endpoint(instance)
            return True
        except InstanceEndpointPending:
            pass
        candidates = current.candidates()
        for serial in candidates:
            current.confirm(instance, candidates)
            reconnect(profile.adb_path, serial, current.remaining())
        current.confirm(instance, candidates)
        try:
            current.endpoint(instance)
        except InstanceEndpointPending:
            return False
        return True


class _NoxObservation:
    def __init__(self, reader, profile, manager, timeout):
        self.reader = reader
        self.profile = profile
        self.manager = str(manager)
        self.deadline = reader.monotonic() + max(0, timeout)

    def remaining(self):
        available = self.deadline - self.reader.monotonic()
        if available <= 0:
            raise TimeoutError("夜神实例复核超时。")
        return io_timeout(min(3, available))

    def command(self, argv, *, adb=False):
        try:
            output = run_endpoint_command(
                argv,
                timeout=self.remaining(),
                run=self.reader.run,
                probe=self.reader.probe,
                monotonic=self.reader.monotonic,
                adb=adb,
            )
        except ValueError as exc:
            raise InstanceBindingError(
                "manager_output",
                f"夜神命令输出异常：{exc}",
                ["manager_path", "adb_path"],
            ) from exc
        self.remaining()
        return output

    def instance(self):
        profile = self.profile
        if not profile.instance_uuid or not profile.topology_fingerprint:
            raise InstanceBindingError(
                "topology_changed",
                "夜神绑定尚未确认 VM 身份，请重新查找并选择实例。",
                [],
            )
        try:
            instances = nox_inventory(
                self.manager,
                self.command([self.manager, "list"]),
                deadline=self.deadline,
                monotonic=self.reader.monotonic,
            )
        except FileNotFoundError as exc:
            raise InstanceBindingError(
                "topology_changed",
                "夜神 VM 配置已移动或删除，请重新查找并选择实例。",
                [],
            ) from exc
        except ValueError as exc:
            raise InstanceBindingError(
                "manager_output", str(exc), ["manager_path"]
            ) from exc
        matches = [
            item for item in instances if item["instance_id"] == profile.instance_id
        ]
        if (
            len(matches) != 1
            or matches[0]["instance_uuid"] != profile.instance_uuid
            or matches[0]["topology_fingerprint"] != profile.topology_fingerprint
        ):
            raise InstanceBindingError(
                "topology_changed",
                "夜神 VM 拓扑或身份已变化，请重新查找并选择实例。",
                [],
            )
        instance = matches[0]
        # The documented -name argument addresses the display title, not VM name.
        if (
            sum(
                item["instance_name"] == instance["instance_name"] for item in instances
            )
            != 1
        ):
            raise InstanceBindingError(
                "binding_failed",
                "夜神实例标题重复，请在多开管理器中设置唯一标题后重试。",
                [],
            )
        self.remaining()
        return instance

    def candidates(self):
        identity, machine = read_nox_vm(self.manager, self.profile.instance_id)
        if identity != self.profile.instance_uuid:
            raise InstanceBindingError(
                "topology_changed", "夜神 VM 身份已变化，请重新选择。", []
            )
        serials = []
        for adapter in machine.findall(
            f"{VBOX_NS}Hardware/{VBOX_NS}Network/{VBOX_NS}Adapter"
        ):
            if adapter.get("enabled") != "true":
                continue
            for rule in adapter.findall(f"{VBOX_NS}NAT/{VBOX_NS}Forwarding"):
                if rule.get("proto") != "1" or rule.get("guestport") != "5555":
                    continue
                host = ipaddress.ip_address(rule.get("hostip") or "127.0.0.1")
                port = rule.get("hostport", "")
                if not port.isdecimal() or not 0 < int(port) < 65536:
                    raise ValueError("夜神当前 ADB 转发端口无效。")
                if host.is_unspecified:
                    host = ipaddress.ip_address(
                        "127.0.0.1" if host.version == 4 else "::1"
                    )
                if not host.is_loopback:
                    continue
                address = str(host) if host.version == 4 else f"[{host}]"
                serials.append(f"{address}:{int(port)}")
        return list(dict.fromkeys(serials))

    def endpoint(self, instance):
        bundled = Path(self.manager).parent / "nox_adb.exe"
        if not bundled.is_file() or not self.profile.adb_path:
            raise InstanceBindingError(
                "missing_adb",
                "夜神目录需要有效的 nox_adb.exe，并选择可用 ADB。",
                ["adb_path", "manager_path"],
            )
        guard_adb(
            str(bundled),
            timeout=self.remaining(),
            run=self.reader.run,
            probe=self.reader.probe,
            monotonic=self.reader.monotonic,
        )
        candidates = self.candidates()
        vendor = parse_adb_devices(
            self.command([str(bundled), "devices", "-l"], adb=True)
        )
        selected = parse_adb_devices(
            self.command([self.profile.adb_path, "devices", "-l"], adb=True)
        )
        usable = []
        states = []
        for serial in candidates:
            observations = (vendor.get(serial, []), selected.get(serial, []))
            if any(len(rows) > 1 for rows in observations):
                raise InstanceBindingError(
                    "endpoint_ambiguous", "ADB 返回重复端点，请修复后重试。"
                )
            states.extend(state for rows in observations for state in rows)
            if all(rows == ["device"] for rows in observations):
                usable.append(serial)
        matches = []
        if usable:
            boot = parse_boot_id(
                self.command(
                    [
                        self.manager,
                        "adb",
                        f"-name:{instance['instance_name']}",
                        f"-command:{BOOT_ID_COMMAND}",
                    ]
                )
            )
            if boot:
                for serial in usable:
                    candidate_boot = parse_boot_id(
                        self.command(
                            [
                                self.profile.adb_path,
                                "-s",
                                serial,
                                *BOOT_ID_COMMAND.split(),
                            ],
                            adb=True,
                        )
                    )
                    if boot == candidate_boot:
                        matches.append(serial)
        self.confirm(instance, candidates)
        if self.profile.last_serial in matches:
            return self.profile.last_serial
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise InstanceBindingError(
                "endpoint_ambiguous", "所选夜神 VM 有多个验证通过的端点，请明确选择。"
            )
        if "unauthorized" in states:
            raise InstanceBindingError(
                "device_unauthorized", "所选夜神 VM 的 ADB 尚未授权。", []
            )
        if candidates and not usable and set(states) <= {"device", "offline"}:
            raise InstanceEndpointPending(
                "device_offline" if "offline" in states else "endpoint_unresolved",
                "已确认所选夜神 VM，正在等待它的 ADB 端点就绪。",
                [],
            )
        if "offline" in states:
            raise InstanceBindingError(
                "device_offline", "所选夜神 VM 的 ADB 处于 offline 状态。", []
            )
        raise InstanceBindingError(
            "endpoint_unresolved",
            "无法将当前 ADB 端点与所选夜神 VM 对应，请检查 ADB 或使用其他模拟器手动入口。",
        )

    def confirm(self, instance, candidates):
        confirmed = self.instance()
        if (confirmed["pid"], confirmed["instance_name"], confirmed["state"]) != (
            instance["pid"],
            instance["instance_name"],
            instance["state"],
        ) or self.candidates() != candidates:
            raise InstanceBindingError(
                "binding_changed", "夜神实例在验证期间变化，请重试。", []
            )
