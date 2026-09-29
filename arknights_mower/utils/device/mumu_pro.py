"""Read-only MuMu Pro instance observations from the bundled mumutool."""

import json
import os
import subprocess
import time
from hashlib import sha256
from pathlib import Path

from arknights_mower.utils.device.endpoint_identity import (
    InstanceBindingError,
    run_endpoint_command,
)
from arknights_mower.utils.path import resolve_config_path

MUMU_PRO_PRESET = "macos.mumu_pro"
DEFAULT_APP = Path("/Applications/MuMuPlayer.app")
MANAGER_RELATIVE_PATH = Path("Contents/MacOS/mumutool")
MAX_INSTANCES = 64


def _instance(raw):
    if not isinstance(raw, dict):
        raise ValueError("MuMu Pro 实例信息不是对象")
    index = raw.get("index")
    name = raw.get("name")
    bundle = raw.get("bundle_path")
    state = raw.get("state")
    port = raw.get("adb_port")
    if type(index) is not int or index < 0 or not isinstance(name, str):
        raise ValueError("MuMu Pro 实例序号或名称无效")
    if (
        not name.strip()
        or not isinstance(bundle, str)
        or not Path(bundle).is_absolute()
    ):
        raise ValueError("MuMu Pro 实例文件路径无效")
    if "\x00" in bundle or state not in {"running", "starting", "stopped"}:
        raise ValueError("MuMu Pro 实例状态无效")
    if state in {"running", "starting"}:
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("MuMu Pro ADB 端口无效")
        serial = f"127.0.0.1:{port}"
    else:
        serial = ""
    return {
        "instance_id": str(index),
        "instance_name": name.strip(),
        "bundle_path": bundle,
        "topology_fingerprint": sha256(bundle.encode("utf-8")).hexdigest(),
        "state": state,
        "serial": serial,
    }


def parse_mumu_pro_info(output: bytes, *, selected_id: str | None = None) -> list[dict]:
    """Reject incomplete or ambiguous manager output before exposing an endpoint."""
    try:
        document = json.loads(output)
        if (
            not isinstance(document, dict)
            or type(document.get("errcode")) is not int
            or document["errcode"] != 0
        ):
            raise ValueError("MuMu Pro 管理工具未确认请求成功")
        payload = document.get("return")
        if selected_id is None:
            count = payload.get("count") if isinstance(payload, dict) else None
            rows = payload.get("results") if isinstance(payload, dict) else None
            if (
                type(count) is not int
                or not 0 <= count <= MAX_INSTANCES
                or not isinstance(rows, list)
                or len(rows) != count
            ):
                raise ValueError("MuMu Pro 实例列表不完整")
        else:
            if not selected_id.isdecimal() or not isinstance(payload, dict):
                raise ValueError("MuMu Pro 实例查询无效")
            rows = [payload]
        instances = [_instance(row) for row in rows]
        if selected_id is not None and (
            len(instances) != 1 or instances[0]["instance_id"] != selected_id
        ):
            raise ValueError("MuMu Pro 返回了其他实例")
        if len({item["instance_id"] for item in instances}) != len(instances):
            raise ValueError("MuMu Pro 实例序号重复")
        if len({item["bundle_path"] for item in instances}) != len(instances):
            raise ValueError("MuMu Pro 实例文件路径重复")
        serials = [item["serial"] for item in instances if item["serial"]]
        if len(set(serials)) != len(serials):
            raise ValueError("MuMu Pro ADB 端口重复")
        return instances
    except (UnicodeError, json.JSONDecodeError, TypeError, AttributeError) as exc:
        raise ValueError("MuMu Pro 管理工具输出格式无效") from exc


class MuMuProController:
    def __init__(self, *, run=subprocess.run, monotonic=time.monotonic):
        self._run = run
        self._monotonic = monotonic

    def _manager(self, profile):
        manager = profile.manager_path.strip()
        if manager:
            path = Path(resolve_config_path(manager))
        else:
            root = profile.installation_path.strip()
            path = (
                Path(resolve_config_path(root)) if root else DEFAULT_APP
            ) / MANAGER_RELATIVE_PATH
        if (
            path.name != "mumutool"
            or not path.is_file()
            or not os.access(path, os.X_OK)
        ):
            raise InstanceBindingError(
                "mumu_pro_manager_missing",
                "未找到 MuMu Pro 的 mumutool，请检查安装目录或管理程序路径。",
                ["installation_path", "manager_path"],
            )
        return path.resolve()

    def _query(self, path, target, timeout):
        try:
            output = run_endpoint_command(
                [str(path), "info", target],
                timeout=timeout,
                run=self._run,
                probe=None,
                monotonic=self._monotonic,
            )
            return parse_mumu_pro_info(
                output, selected_id=None if target == "all" else target
            )
        except InstanceBindingError:
            raise
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            raise InstanceBindingError(
                "mumu_pro_output_invalid",
                f"无法确认 MuMu Pro 实例信息：{exc}",
                ["manager_path", "instance_id"],
            ) from exc

    def discover(self, profile, timeout=6):
        path = self._manager(profile)
        instances = self._query(path, "all", timeout)
        return {
            "installations": [
                {
                    "preset_id": MUMU_PRO_PRESET,
                    "installation_path": str(path.parent.parent.parent),
                    "manager_path": str(path),
                    "instances": instances,
                }
            ],
            "errors": [],
        }

    def inspect(self, profile, timeout):
        from arknights_mower.utils.device.session import InstanceObservation

        if not profile.topology_fingerprint:
            return InstanceObservation("unknown")
        path = self._manager(profile)
        instances = self._query(path, profile.instance_id, timeout)
        instance = instances[0]
        if instance["topology_fingerprint"] != profile.topology_fingerprint:
            raise InstanceBindingError(
                "mumu_pro_binding_changed",
                "MuMu Pro 实例文件已变化，请重新检测并选择目标实例。",
                ["instance_id", "topology_fingerprint"],
            )
        return InstanceObservation(instance["state"], instance["serial"] or None)
