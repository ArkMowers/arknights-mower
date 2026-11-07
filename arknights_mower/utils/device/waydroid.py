"""Official single-system Waydroid status and immutable user/data binding.

The CLI has no instance selector. GetSession supplies the data directory that
status omits; neither an old serial nor unrelated ADB devices can identify it.
"""

import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from arknights_mower.utils.device.endpoint_identity import (
    InstanceBindingError,
    InstanceEndpointPending,
)
from arknights_mower.utils.device.manager_io import MAX_OUTPUT, run_manager_command
from arknights_mower.utils.device.preflight import PreflightError
from arknights_mower.utils.device.session import InstanceObservation
from arknights_mower.utils.path import resolve_config_path

WAYDROID_PRESET = "linux.waydroid"
COMMAND_TIMEOUT = 3.0
DISCOVERY_TIMEOUT = 10.0


def waydroid_repair(error):
    action = {
        "waydroid_uninitialized": "initialize",
        "instance_stopped": "start",
        "endpoint_ambiguous": "select",
        "waydroid_binding_changed": "select",
    }.get(error.code, "retry")
    return PreflightError(error.code, str(error), action, error.fields)


@dataclass(frozen=True)
class _Environment:
    state: str
    uid: str
    name: str
    data_path: str
    addresses: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Startup:
    manager: str
    uid: str
    data_path: str
    deadline: float


class WaydroidController:
    def __init__(
        self,
        *,
        run=None,
        spawn=None,
        which=None,
        uid=None,
        host=None,
        data_path=None,
        monotonic=time.monotonic,
    ):
        self.run = run or run_manager_command
        self.spawn = spawn or subprocess.Popen
        self.which = which or shutil.which
        self.uid = uid or (lambda: os.getuid())
        self.host = host or sys.platform
        self.data_path = data_path
        self.monotonic = monotonic
        self._startup: _Startup | None = None

    def _local_data(self):
        return self.data_path or str(
            Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
            / "waydroid/data"
        )

    def _linux(self):
        if self.host != "linux":
            raise InstanceBindingError(
                "unsupported_host",
                "Waydroid 只能在 Linux 主机检测与连接。",
                ["preset_id"],
            )

    def _manager(self, profile):
        self._linux()
        candidate = profile.manager_path.strip()
        if not candidate and profile.installation_path.strip():
            candidate = str(
                Path(resolve_config_path(profile.installation_path)) / "waydroid"
            )
        candidate = candidate or self.which("waydroid")
        if not candidate or not Path(resolve_config_path(candidate)).is_file():
            raise InstanceBindingError(
                "missing_installation",
                "未找到 Waydroid，请安装官方 Waydroid，或填写 waydroid 管理程序路径。",
                ["manager_path"],
            )
        path = Path(resolve_config_path(candidate)).resolve()
        if not os.access(path, os.X_OK):
            raise InstanceBindingError(
                "discovery_permission_denied",
                "Waydroid 管理程序不可执行，请检查访问权限。",
                ["manager_path"],
            )
        return str(path)

    def _remaining(self, deadline):
        remaining = deadline - self.monotonic()
        if remaining <= 0:
            raise InstanceBindingError(
                "manager_timeout", "Waydroid 操作时间预算已耗尽，请检查服务后重试。", []
            )
        return remaining

    def _command(self, argv, deadline):
        try:
            result = self.run(
                argv,
                timeout=min(self._remaining(deadline), COMMAND_TIMEOUT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            result.check_returncode()
        except (TimeoutError, subprocess.TimeoutExpired) as exc:
            raise InstanceBindingError(
                "manager_timeout", "Waydroid 状态查询超时，请检查服务后重试。", []
            ) from exc
        except PermissionError as exc:
            raise InstanceBindingError(
                "discovery_permission_denied",
                "无法读取 Waydroid 官方状态，请检查程序与系统 D-Bus 访问权限。",
                [],
            ) from exc
        except (OSError, subprocess.CalledProcessError) as exc:
            raise InstanceBindingError(
                "waydroid_status_failed",
                "无法读取 Waydroid 官方状态，请在终端检查 waydroid status 与系统 D-Bus 服务后重试。",
                [],
            ) from exc
        self._remaining(deadline)
        output, error = result.stdout or b"", result.stderr or b""
        if len(output) + len(error) > MAX_OUTPUT:
            raise InstanceBindingError(
                "manager_output_invalid", "Waydroid 状态输出超过 1 MiB。", []
            )
        try:
            output = output.decode("utf-8", "strict")
            error = error.decode("utf-8", "strict")
        except UnicodeError as exc:
            raise InstanceBindingError(
                "manager_output_invalid", "Waydroid 状态编码无效。", []
            ) from exc
        if 'Waydroid is not initialized, run "waydroid init"' in output + error:
            raise InstanceBindingError(
                "waydroid_uninitialized",
                "Waydroid 尚未初始化。请按官方安装说明在终端完成 waydroid init，再重新检测。mower 不会请求管理员权限或自动初始化。",
                [],
            )
        if error.strip():
            raise InstanceBindingError(
                "waydroid_status_failed",
                "Waydroid 状态命令报告错误，请在终端检查官方状态后重试。",
                [],
            )
        return output

    def _session(self, deadline):
        busctl = self.which("busctl")
        if not busctl or not Path(busctl).is_file() or not os.access(busctl, os.X_OK):
            raise InstanceBindingError(
                "waydroid_session_unavailable",
                "需要 busctl 读取 Waydroid 官方会话身份。请安装发行版提供的 busctl 并加入 PATH，或使用其他模拟器手动配置。",
                [],
            )
        output = self._command(
            [
                str(Path(busctl).resolve()),
                "--system",
                "--json=short",
                "--auto-start=no",
                "--allow-interactive-authorization=no",
                "call",
                "id.waydro.Container",
                "/ContainerManager",
                "id.waydro.ContainerManager",
                "GetSession",
            ],
            deadline,
        )
        try:
            value = json.loads(output)
            data = value["data"]
            if value["type"] != "a{ss}" or not isinstance(data, list) or len(data) != 1:
                raise ValueError()
            session = data[0]
            if not isinstance(session, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in session.items()
            ):
                raise ValueError()
            return session
        except (ValueError, KeyError, TypeError) as exc:
            raise InstanceBindingError(
                "waydroid_session_unavailable",
                "无法解析官方 GetSession 身份信息，请检查系统 D-Bus 与 busctl 版本；可修复后重试或使用其他模拟器手动配置。",
                [],
            ) from exc

    def _environment(self, manager, deadline):
        output = re.sub(
            r"\x1b\[[0-9;]*m", "", self._command([manager, "status"], deadline)
        )
        fields = {}
        for line in output.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                fields.setdefault(key.strip(), []).append(value.strip())
        if fields.get("Session") == ["STOPPED"]:
            if self._session(deadline):
                raise InstanceBindingError(
                    "waydroid_session_unavailable",
                    "Waydroid 状态与官方会话信息不一致，请等待状态稳定后重试。",
                    [],
                )
            return _Environment(
                "stopped", str(self.uid()), f"UID {self.uid()}", self._local_data()
            )
        if fields.get("Session") != ["RUNNING"]:
            raise InstanceBindingError(
                "manager_output_invalid",
                "无法确认 Waydroid 会话状态，请在终端检查 waydroid status。",
                [],
            )
        users = fields.get("Session user", [])
        user = re.fullmatch(r"(.+)\(([0-9]+)\)", users[0]) if len(users) == 1 else None
        if user is None:
            raise InstanceBindingError(
                "instance_required",
                "官方状态未提供唯一的 Waydroid 会话用户，请检查 waydroid status 后重试。",
                [],
            )
        container = fields.get("Container")
        if container not in (["RUNNING"], ["STOPPED"]):
            raise InstanceBindingError(
                "waydroid_container_not_running",
                "Waydroid 会话存在，但容器未运行或处于冻结状态。请在 Waydroid 中恢复运行后重试。",
                [],
            )
        session = self._session(deadline)
        data_path = session.get("waydroid_data", "")
        if (
            session.get("user_id") != str(int(user[2]))
            or session.get("state") != container[0]
            or not PurePosixPath(data_path).is_absolute()
        ):
            raise InstanceBindingError(
                "waydroid_session_unavailable",
                "Waydroid 官方状态与会话身份不一致，请等待会话稳定后重新检测。",
                [],
            )
        return _Environment(
            "running" if container == ["RUNNING"] else "starting",
            session["user_id"],
            f"{user[1]} ({user[2]})",
            data_path,
            tuple(fields.get("IP address", [])),
        )

    @staticmethod
    def _endpoint(environment, profile):
        candidates = []
        for value in environment.addresses:
            try:
                ip = ipaddress.ip_address(value)
                if ip.is_unspecified or ip.is_multicast or ip.is_loopback:
                    raise ValueError()
            except ValueError:
                continue
            host = f"[{ip}]" if ip.version == 6 else str(ip)
            candidates.append(f"{host}:5555")
        if len(candidates) == 1 and len(environment.addresses) == 1:
            return candidates[0]
        if len(candidates) > 1 and len(set(candidates)) == len(candidates):
            if profile.last_serial in candidates:
                return profile.last_serial
            raise InstanceBindingError(
                "endpoint_ambiguous",
                "官方状态返回多个 Waydroid 地址，请核对 Android 设置并填写其中一个明确的 IP:5555："
                + "、".join(candidates),
                ["last_serial"],
            )
        raise InstanceBindingError(
            "endpoint_unresolved",
            "官方状态未提供唯一可用的 Waydroid IP。请启动 Waydroid 并核对 waydroid status 与 Android 设置中的 IP 后重试；无法由官方状态验证的地址请进入其他模拟器手动配置。",
            ["last_serial"],
        )

    def discover(self, profile, host, timeout=DISCOVERY_TIMEOUT):
        result = {"installations": [], "errors": []}
        try:
            if host != "linux":
                raise InstanceBindingError(
                    "unsupported_host",
                    "Waydroid 只能在 Linux 主机检测。",
                    ["preset_id"],
                )
            deadline = self.monotonic() + max(timeout, 0)
            manager = self._manager(profile)
            environment = self._environment(manager, deadline)
            instance = {
                "state": environment.state,
                "instance_id": f"waydroid:{environment.uid}",
                "instance_name": f"Waydroid {environment.name}",
                "serial": "",
            }
            result["installations"].append(
                {
                    "preset_id": WAYDROID_PRESET,
                    "installation_path": str(Path(manager).parent),
                    "manager_path": manager,
                    "config_path": environment.data_path,
                    "instances": [instance],
                }
            )
            if environment.state == "running":
                instance["serial"] = self._endpoint(environment, profile)
        except InstanceBindingError as exc:
            result["errors"].append(waydroid_repair(exc))
        except OSError as exc:
            result["errors"].append(
                PreflightError(
                    "discovery_permission_denied",
                    f"无法访问 Waydroid 程序：{exc}",
                    fields=["manager_path"],
                )
            )
        return result

    def _bound(self, profile, deadline):
        if (
            not profile.manager_path.strip()
            or not re.fullmatch(r"waydroid:[0-9]+", profile.instance_id)
            or not PurePosixPath(profile.config_path).is_absolute()
        ):
            raise InstanceBindingError(
                "instance_required",
                "请重新检测并选择 Waydroid 环境，保存管理程序、会话用户和数据目录绑定。",
                ["manager_path", "instance_id", "config_path"],
            )
        manager = self._manager(profile)
        environment = self._environment(manager, deadline)
        if (
            profile.instance_id != f"waydroid:{environment.uid}"
            or profile.config_path != environment.data_path
        ):
            raise InstanceBindingError(
                "waydroid_binding_changed",
                "当前 Waydroid 会话用户或数据目录与绑定不同。请恢复原环境，或重新检测并明确选择新的环境。",
                [],
            )
        return manager, environment

    def inspect(self, profile, timeout):
        manager, environment = self._bound(profile, self.monotonic() + max(timeout, 0))
        if environment.state != "running":
            return InstanceObservation(environment.state)
        try:
            serial = self._endpoint(environment, profile)
        except InstanceBindingError as exc:
            startup = self._startup
            if (
                exc.code == "endpoint_unresolved"
                and startup is not None
                and startup.manager == manager
                and startup.uid == environment.uid
                and startup.data_path == environment.data_path
                and self.monotonic() < startup.deadline
            ):
                # Only our current launch may wait for an official IP. Ordinary
                # discovery still asks for repair, and ambiguous IPs need a choice.
                raise InstanceEndpointPending(exc.code, str(exc), exc.fields) from exc
            raise
        self._startup = None
        return InstanceObservation("running", serial)

    def start(self, profile, timeout):
        deadline = self.monotonic() + max(timeout, 0)
        manager, environment = self._bound(profile, deadline)
        if environment.state != "stopped":
            return False
        self._startup = None
        self._remaining(deadline)
        process = self.spawn(
            [manager, "show-full-ui"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self._remaining(deadline)
        succeeded = process.poll() in (None, 0)
        if succeeded:
            self._startup = _Startup(
                manager, environment.uid, environment.data_path, deadline
            )
        return succeeded

    def stop(self, profile, timeout):
        deadline = self.monotonic() + max(timeout, 0)
        manager, environment = self._bound(profile, deadline)
        if environment.state == "stopped":
            return True
        # session stop can fall back to the system container. Authorize it only
        # for the current user's exact data environment, freshly rechecked above.
        if (
            environment.uid != str(self.uid())
            or environment.data_path != self._local_data()
        ):
            raise InstanceBindingError(
                "waydroid_binding_changed",
                "不能从当前用户会话重启该 Waydroid 环境，请以绑定用户在原数据目录下启动 mower。",
                [],
            )
        self._command([manager, "session", "stop"], deadline)
        _, stopped = self._bound(profile, deadline)
        return stopped.state == "stopped"
