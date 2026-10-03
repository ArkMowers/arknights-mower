"""Verified MuMu Pro instance control through the bundled mumutool."""

import json
import os
import re
import socket
import subprocess
import time
from hashlib import sha256
from pathlib import Path

from arknights_mower.utils.csleep import csleep
from arknights_mower.utils.device.endpoint_identity import (
    InstanceBindingError,
    run_endpoint_command,
)
from arknights_mower.utils.device.manager_io import MAX_OUTPUT
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
    if "\x00" in bundle or state not in {"running", "starting", "stopped", "error"}:
        raise ValueError("MuMu Pro 实例状态无效")
    if state == "starting" and (port is None or type(port) is int and port == 0):
        serial = ""
    elif state in {"running", "starting"}:
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
            if not re.fullmatch(r"0|[1-9][0-9]*", selected_id) or not isinstance(
                payload, dict
            ):
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
    def __init__(
        self,
        *,
        run=subprocess.run,
        monotonic=time.monotonic,
        sleep=csleep,
        connect=socket.create_connection,
    ):
        self._run = run
        self._monotonic = monotonic
        self._sleep = sleep
        self._connect = connect

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

    def prepare_manager(self, profile, timeout=6):
        """Open the manager application once when its official port is absent."""
        deadline = self._monotonic() + timeout
        path = self._manager(profile)

        def port_available():
            csleep(0)
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise TimeoutError("MuMu Pro 管理服务启动时间预算已耗尽")
            try:
                output = run_endpoint_command(
                    [str(path), "port"],
                    timeout=remaining,
                    run=self._run,
                    probe=None,
                    monotonic=self._monotonic,
                )
            except subprocess.CalledProcessError as exc:
                if (exc.stderr or b"").strip() == b"Error: invalidPort":
                    return False
                raise
            document = json.loads(output)
            port = document.get("server-port") if isinstance(document, dict) else None
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError("MuMu Pro 管理服务端口无效")
            return True

        try:
            opened = not port_available()
            if opened:
                app = path.parent.parent.parent
                if app.suffix != ".app" or not (app / "Contents/Info.plist").is_file():
                    raise ValueError("请指定 MuMu Pro 应用内的 mumutool 路径")
                csleep(0)
                run_endpoint_command(
                    ["/usr/bin/open", "-a", str(app)],
                    timeout=deadline - self._monotonic(),
                    run=self._run,
                    probe=None,
                    monotonic=self._monotonic,
                )
            empty_inventory = False
            while True:
                csleep(0)
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    if empty_inventory:
                        return True
                    raise TimeoutError("MuMu Pro 管理服务尚未就绪")
                try:
                    instances = self._query(path, "all", remaining)
                    csleep(0)
                    if instances or not opened:
                        return True
                    empty_inventory = True
                except InstanceBindingError as exc:
                    empty_inventory = False
                    if not isinstance(exc.__cause__, subprocess.CalledProcessError):
                        raise
                self._sleep(min(0.2, max(0, deadline - self._monotonic())))
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            raise InstanceBindingError(
                "mumu_pro_manager_start_failed",
                "无法启动 MuMu Pro 管理服务，请检查应用路径或手动打开 MuMu Pro 后重试。",
                ["installation_path", "manager_path"],
            ) from exc

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
        except subprocess.CalledProcessError as exc:
            if (exc.stderr or b"").strip() == b"Error: invalidPort":
                raise InstanceBindingError(
                    "mumu_pro_manager_stopped",
                    "MuMu Pro 应用未打开。检测实例可尝试打开应用并启动所选实例；只读测试需先手动打开应用。",
                    ["manager_path"],
                ) from exc
            raise InstanceBindingError(
                "mumu_pro_output_invalid",
                "MuMu Pro 管理工具查询失败，请检查应用状态。",
                ["manager_path"],
            ) from exc
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

    def _verified_instance(self, profile, path, timeout):
        if (
            not re.fullmatch(r"0|[1-9][0-9]*", profile.instance_id or "")
            or not profile.topology_fingerprint
        ):
            raise InstanceBindingError(
                "mumu_pro_selection_required",
                "请先检测并选择 MuMu Pro 实例，再启动或关闭该实例。",
                ["instance_id", "topology_fingerprint"],
            )
        instance = self._query(path, profile.instance_id, timeout)[0]
        if instance["topology_fingerprint"] != profile.topology_fingerprint:
            raise InstanceBindingError(
                "mumu_pro_binding_changed",
                "MuMu Pro 实例文件已变化，请重新检测并选择目标实例。",
                ["instance_id", "topology_fingerprint"],
            )
        return instance

    @staticmethod
    def _check_instance_error(instance):
        if instance["state"] == "error":
            raise InstanceBindingError(
                "mumu_pro_instance_error",
                "MuMu Pro 管理器报告所选实例操作失败，请在管理器中处理该实例的错误提示后重试。",
                ["instance_id"],
            )

    def start(self, profile, timeout):
        return self._act(profile, timeout, starting=True)

    def stop(self, profile, timeout):
        return self._act(profile, timeout, starting=False)

    def _act(self, profile, timeout, *, starting):
        deadline = self._monotonic() + timeout
        path = self._manager(profile)
        instance = self._verified_instance(profile, path, deadline - self._monotonic())
        self._check_instance_error(instance)
        if starting and instance["state"] in {"running", "starting"}:
            return True
        if not starting and instance["state"] == "stopped":
            return True
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise InstanceBindingError(
                "mumu_pro_action_timeout", "MuMu Pro 实例操作时间预算已耗尽。"
            )
        try:
            result = self._run(
                [str(path), "open" if starting else "close", profile.instance_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=remaining,
            )
            result.check_returncode()
            output, error = result.stdout, result.stderr or b""
            if len(output) + len(error) > MAX_OUTPUT or error.strip():
                raise ValueError("MuMu Pro 操作输出异常")
            document = json.loads(output)
            if (
                not isinstance(document, dict)
                or type(document.get("errcode")) is not int
                or document["errcode"] != 0
            ):
                raise ValueError("MuMu Pro 管理工具未确认操作成功")
            return True
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            raise InstanceBindingError(
                "mumu_pro_action_failed",
                "MuMu Pro 未确认实例操作成功，请检查所选实例状态后重试。",
                ["manager_path", "instance_id"],
            ) from exc

    def inspect(self, profile, timeout):
        from arknights_mower.utils.device.session import InstanceObservation

        if not profile.topology_fingerprint:
            return InstanceObservation("unknown")
        deadline = self._monotonic() + timeout
        path = self._manager(profile)
        instance = self._verified_instance(profile, path, timeout)
        self._check_instance_error(instance)
        if instance["serial"]:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise InstanceBindingError(
                    "mumu_pro_action_timeout", "MuMu Pro 实例查询时间预算已耗尽。"
                )
            # The manager reports running before the guest starts listening.
            # Wait without spending recovery attempts or exposing a stale serial.
            try:
                with self._connect(
                    ("127.0.0.1", int(instance["serial"].rsplit(":", 1)[1])),
                    timeout=min(1, remaining),
                ):
                    pass
            except OSError:
                return InstanceObservation("starting")
        return InstanceObservation(instance["state"], instance["serial"] or None)
