"""Resolve only the bound BlueStacks keyword, never the first matching port."""

import re
import subprocess
import time

from arknights_mower.utils.device.bluestacks_discovery import (
    INSTANCE_KEY,
    configuration_error,
    locate_bluestacks_player,
    read_bluestacks_config,
)
from arknights_mower.utils.device.endpoint_identity import (
    InstanceBindingError,
    parse_adb_devices,
    run_endpoint_command,
)
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.manager_io import run_manager_command


def unreachable_endpoint():
    return InstanceBindingError(
        "endpoint_unreachable",
        "所选 BlueStacks 实例端点不可达。请手动启动该实例，在设置 → 高级启用 ADB 后重试。",
        [],
    )


class BlueStacksEndpointResolver:
    def __init__(self, *, run=None, probe=None, monotonic=time.monotonic):
        self.run = run or run_manager_command
        self.probe = probe
        self.monotonic = monotonic

    @staticmethod
    def _target(profile):
        locate_bluestacks_player(profile.manager_path or profile.installation_path)
        if not re.fullmatch(INSTANCE_KEY, profile.instance_id):
            raise InstanceBindingError(
                "instance_required",
                "请选择明确的 BlueStacks 实例关键字。",
                ["instance_id"],
            )
        if not profile.config_path:
            raise InstanceBindingError(
                "missing_config",
                "请重新检测 BlueStacks 产品配置路径。",
                ["config_path"],
            )
        values, instances = read_bluestacks_config(profile.config_path)
        # These bluestacks.conf fields are not a published vendor contract, and
        # BlueStacks may rename or remove them in any release. A missing or
        # changed field is therefore an expected failure mode that surfaces as a
        # configuration error below, never as a silently guessed endpoint.
        target = instances.get(profile.instance_id)
        if target is None:
            raise InstanceBindingError(
                "instance_missing",
                "配置中已没有绑定的 BlueStacks 实例，请重新查找并选择实例。",
                ["instance_id"],
            )
        switches = [values.get("bst.enable_adb_access")]
        if "enable_adb_access" in target:
            switches.append(target["enable_adb_access"])
        if any(value not in {"0", "1"} for value in switches):
            raise InstanceBindingError(
                "adb_disabled",
                "BlueStacks 配置缺少有效 ADB 开关。请打开所选实例的设置 → 高级 → Android debug bridge，启用并保存后重试。",
                [],
            )
        if "0" in switches:
            raise InstanceBindingError(
                "adb_disabled",
                "请在所选 BlueStacks 实例的设置 → 高级中启用 Android debug bridge，保存后重试。",
                [],
            )
        # status.adb_port is the current endpoint, including Hyper-V mode.
        # Its presence forbids falling back to a stale ordinary adb_port.
        port = target.get("status.adb_port", target.get("adb_port", ""))
        if not re.fullmatch(r"[0-9]{1,5}", port) or not 0 < int(port) < 65536:
            raise configuration_error("所选实例当前 ADB 端口无效，请先启动该实例")
        identity = target.get("android_id", "").lower()
        if not re.fullmatch(r"[0-9a-f]{16}", identity) or int(identity, 16) == 0:
            raise configuration_error("所选实例缺少可验证的 Android ID")
        if (
            sum(
                row.get("android_id", "").lower() == identity
                for row in instances.values()
            )
            != 1
        ):
            raise InstanceBindingError(
                "endpoint_ambiguous",
                "多个 BlueStacks 实例的 Android ID 相同，无法安全验证目标。请使用其他模拟器手动入口明确配置。",
                [],
            )
        serial = f"127.0.0.1:{int(port)}"
        for keyword, row in instances.items():
            if (
                keyword != profile.instance_id
                and row.get("status.adb_port", row.get("adb_port", "")) == port
            ):
                raise configuration_error("多个实例使用同一当前端口")
        return serial, identity

    def inspect(self, profile, timeout):
        from arknights_mower.utils.device.session import InstanceObservation

        deadline = self.monotonic() + max(0, timeout)

        def remaining():
            available = deadline - self.monotonic()
            if available <= 0:
                raise TimeoutError("BlueStacks 端点验证时间预算已耗尽。")
            return io_timeout(min(3, available))

        def command(args):
            try:
                output = run_endpoint_command(
                    [profile.adb_path, *args],
                    timeout=remaining(),
                    run=self.run,
                    probe=self.probe,
                    monotonic=self.monotonic,
                    adb=True,
                )
            except (subprocess.SubprocessError, TimeoutError, ValueError) as exc:
                raise unreachable_endpoint() from exc
            remaining()
            return output

        serial, identity = self._target(profile)
        remaining()
        if not profile.adb_path:
            raise InstanceBindingError("missing_adb", "请选择有效 ADB。", ["adb_path"])
        rows = parse_adb_devices(command(["devices", "-l"]))
        if serial not in rows:
            # Connect only this configured candidate. A successful connect string
            # alone never proves readiness or the identity of the Android guest.
            response = command(["connect", serial]).decode("utf-8", "replace").strip()
            if response not in {
                f"connected to {serial}",
                f"already connected to {serial}",
            }:
                raise unreachable_endpoint()
            rows = parse_adb_devices(command(["devices", "-l"]))
        states = rows.get(serial, [])
        if states != ["device"]:
            code = (
                "endpoint_ambiguous"
                if len(states) > 1
                else "device_unauthorized"
                if states == ["unauthorized"]
                else "device_offline"
                if states == ["offline"]
                else "endpoint_unreachable"
            )
            raise InstanceBindingError(
                code,
                f"所选 BlueStacks 实例的 ADB 未就绪（{code}）。请手动启动该实例并检查设置 → 高级中的 ADB 开关及授权后重试。",
                [],
            )
        observed = (
            command(
                [
                    "-s",
                    serial,
                    "shell",
                    "settings",
                    "--user",
                    "0",
                    "get",
                    "secure",
                    "android_id",
                ]
            )
            .decode("ascii", "replace")
            .strip()
            .lower()
        )
        if observed != identity:
            raise InstanceBindingError(
                "endpoint_mismatch",
                "当前 ADB 端点的 Android ID 与绑定实例不符。请启动所选实例并重新检测；不会使用其他在线设备。",
                [],
            )
        if self._target(profile) != (serial, identity):
            raise InstanceBindingError(
                "binding_changed", "BlueStacks 配置在端点验证期间发生变化，请重试。", []
            )
        remaining()
        # No lifecycle commands are available for BlueStacks. A verified serial
        # with unknown manager state permits only target-local ADB recovery.
        return InstanceObservation("unknown", serial)
