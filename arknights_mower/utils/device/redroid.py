"""Local Docker redroid discovery and immutable container identity."""

import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

from arknights_mower.utils.device.endpoint_identity import (
    InstanceBindingError,
    InstanceEndpointPending,
)
from arknights_mower.utils.device.manager_io import (
    MAX_INSTANCES,
    MAX_OUTPUT,
    run_manager_command,
)
from arknights_mower.utils.device.preflight import PreflightError
from arknights_mower.utils.device.session import InstanceObservation
from arknights_mower.utils.path import resolve_config_path

REDROID_PRESET = "linux.redroid"
LOCAL_DOCKER = "unix:///var/run/docker.sock"
COMMAND_TIMEOUT = 3.0
DISCOVERY_TIMEOUT = 10.0
_CONTAINER_ID = re.compile(r"[0-9a-f]{64}")
_IMAGE = re.compile(
    r"(?:(?:docker\.io|index\.docker\.io)/)?redroid/redroid"
    r"(?::[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?(?:@sha256:[0-9a-f]{64})?"
)


def _invalid_output():
    return InstanceBindingError(
        "manager_output_invalid",
        "Docker inspect 或管理输出格式异常，请检查 Docker 版本后重试。",
        [],
    )


def _manual(message):
    return InstanceBindingError(
        "redroid_manual_required",
        message + "请使用“其他模拟器”的高级手动配置。",
        ["preset_id"],
    )


def redroid_repair(error):
    action = {
        "redroid_manual_required": "manual",
        "no_redroid": "manual",
        "redroid_binding_changed": "select",
        "endpoint_unresolved": "manual",
    }.get(error.code, "retry")
    return PreflightError(error.code, str(error), action, error.fields)


class RedroidController:
    def __init__(self, *, run=None, which=None, host=None, monotonic=time.monotonic):
        self.run = run or run_manager_command
        self.which = which or shutil.which
        self.host = host or sys.platform
        self.monotonic = monotonic
        self._startup = None

    def _manager(self, profile):
        if self.host != "linux":
            raise InstanceBindingError(
                "unsupported_host",
                "redroid 自动发现仅支持 Linux 本机 Docker。",
                ["preset_id"],
            )
        if profile.config_path and profile.config_path != LOCAL_DOCKER:
            raise _manual(
                "自动发现只访问本机默认 Docker socket；远程和自定义 socket 不受支持。"
            )
        candidate = profile.manager_path.strip() or self.which("docker")
        if not candidate or not Path(resolve_config_path(candidate)).is_file():
            raise InstanceBindingError(
                "missing_installation",
                "未找到 Docker，请安装 Docker Engine，或填写 docker 管理程序路径。",
                ["manager_path"],
            )
        path = Path(resolve_config_path(candidate)).resolve()
        if not os.access(path, os.X_OK):
            raise InstanceBindingError(
                "discovery_permission_denied",
                "Docker 管理程序不可执行，请检查权限。",
                ["manager_path"],
            )
        return str(path)

    def _command(self, manager, arguments, deadline):
        remaining = deadline - self.monotonic()
        if remaining <= 0:
            raise InstanceBindingError(
                "manager_timeout", "Docker 操作时间预算已耗尽。", []
            )
        # Never follow a remote context or inherit TLS settings from another daemon.
        env = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "DOCKER_HOST",
                "DOCKER_CONTEXT",
                "DOCKER_TLS",
                "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH",
                "DOCKER_API_VERSION",
            }
        }
        try:
            result = self.run(
                [manager, "--host", LOCAL_DOCKER, *arguments],
                timeout=min(remaining, COMMAND_TIMEOUT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                env=env,
            )
            result.check_returncode()
        except (TimeoutError, subprocess.TimeoutExpired) as exc:
            raise InstanceBindingError(
                "manager_timeout", "本机 Docker 响应超时，请检查服务后重试。", []
            ) from exc
        except PermissionError as exc:
            raise InstanceBindingError(
                "discovery_permission_denied",
                "无法访问 Docker，请检查当前用户的程序与 socket 权限。",
                [],
            ) from exc
        except (OSError, subprocess.CalledProcessError) as exc:
            raise InstanceBindingError(
                "docker_unavailable",
                "无法访问本机 Docker Engine，请检查服务及 socket 权限；其他环境请使用高级手动配置。",
                [],
            ) from exc
        except ValueError as exc:
            # The bounded production runner rejects excessive output before it
            # returns a CompletedProcess, including the plain-text ID listing.
            raise _invalid_output() from exc
        if self.monotonic() >= deadline:
            raise InstanceBindingError(
                "manager_timeout", "Docker 操作时间预算已耗尽。", []
            )
        output, error = result.stdout or b"", result.stderr or b""
        if len(output) + len(error) > MAX_OUTPUT:
            raise _invalid_output()
        if error.strip():
            raise InstanceBindingError(
                "docker_unavailable",
                "Docker 命令报告错误，请在终端检查本机服务后重试。",
                [],
            )
        try:
            return output.decode("utf-8", "strict")
        except UnicodeError as exc:
            raise _invalid_output() from exc

    def _json(self, manager, arguments, deadline):
        try:
            return json.loads(self._command(manager, arguments, deadline))
        except (ValueError, TypeError) as exc:
            if isinstance(exc, InstanceBindingError):
                raise
            raise _invalid_output() from exc

    def _engine(self, manager, deadline):
        server = self._json(
            manager, ["version", "--format", "{{json .Server}}"], deadline
        )
        if not isinstance(server, dict):
            raise _invalid_output()
        platform = server.get("Platform")
        components = server.get("Components")
        if not (
            isinstance(platform, dict)
            and isinstance(platform.get("Name"), str)
            and platform["Name"].startswith("Docker Engine")
            and isinstance(components, list)
            and any(
                isinstance(item, dict) and item.get("Name") == "Engine"
                for item in components
            )
        ):
            raise _manual(
                "当前服务无法确认为 Docker Engine，Podman 等兼容服务不参与自动发现。"
            )

    def _inspect_rows(self, manager, ids, deadline):
        rows = self._json(manager, ["container", "inspect", *ids], deadline)
        if not isinstance(rows, list) or len(rows) != len(ids):
            raise _invalid_output()
        if any(
            not isinstance(row, dict) or not isinstance(row.get("Id"), str)
            for row in rows
        ):
            raise _invalid_output()
        if {row["Id"] for row in rows} != set(ids):
            raise InstanceBindingError(
                "redroid_binding_changed",
                "Docker 返回的容器身份与绑定不一致，请重新选择容器。",
                ["instance_id"],
            )
        return rows

    def _container(self, row):
        try:
            identity, name, config = row["Id"], row["Name"], row["Config"]
            if (
                not _CONTAINER_ID.fullmatch(identity)
                or not isinstance(name, str)
                or not re.fullmatch(r"/[A-Za-z0-9][A-Za-z0-9_.-]*", name)
            ):
                raise ValueError()
            image = config["Image"]
            if not isinstance(image, str):
                raise ValueError()
            if not _IMAGE.fullmatch(image):
                return None
            labels = config.get("Labels")
            if labels is None:
                labels = {}
            if not isinstance(labels, dict) or any(
                not isinstance(key, str) for key in labels
            ):
                raise ValueError()
            if any(
                key.startswith(("io.kubernetes.", "com.docker.swarm."))
                for key in labels
            ):
                raise _manual("Kubernetes 与集群管理的容器不参与自动发现。")
            if row["HostConfig"]["NetworkMode"] not in {"default", "bridge"}:
                raise _manual("此容器使用非标准网络。")
            state = row["State"]
            status, running = state["Status"], state["Running"]
            if not isinstance(running, bool):
                raise ValueError()
            if status in {"created", "exited"} and not running:
                observed, serial = "stopped", ""
            elif status == "restarting" and running:
                observed, serial = "starting", ""
            elif (
                status == "running"
                and running
                and state.get("Paused") is False
                and state.get("Restarting") is False
            ):
                observed = "running"
                serial = self._endpoint(row["NetworkSettings"]["Ports"])
            elif status in {"paused", "dead", "removing"}:
                raise _manual(
                    "容器当前暂停、损坏或正在删除，请先在 Docker 中处理状态。"
                )
            else:
                raise ValueError()
            return {
                "instance_id": identity,
                "instance_name": name[1:],
                "state": observed,
                "serial": serial,
            }
        except InstanceBindingError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise _invalid_output() from exc

    def _endpoint(self, ports):
        if not isinstance(ports, dict):
            raise _invalid_output()
        bindings = ports.get("5555/tcp")
        if not isinstance(bindings, list) or not bindings:
            raise InstanceBindingError(
                "endpoint_unresolved",
                "容器没有当前的 5555/tcp 发布端口；请配置端口映射或使用高级手动配置。",
                ["preset_id"],
            )
        endpoints = set()
        for binding in bindings:
            if not isinstance(binding, dict):
                raise _invalid_output()
            host, port = binding.get("HostIp"), binding.get("HostPort")
            if (
                not isinstance(host, str)
                or not isinstance(port, str)
                or not re.fullmatch(r"[0-9]{1,5}", port)
                or not 0 < int(port) < 65536
            ):
                raise _invalid_output()
            try:
                address = ipaddress.ip_address(host)
            except ValueError as exc:
                raise _invalid_output() from exc
            if address.is_unspecified:
                host = "127.0.0.1" if address.version == 4 else "::1"
            elif not address.is_loopback:
                raise _manual("容器端口绑定到非回环地址。")
            endpoints.add((host, int(port)))
        # Docker's normal dual-stack publication denotes one local port.
        if len({port for _, port in endpoints}) != 1:
            raise _manual("容器具有多个不同的 ADB 发布端口，无法唯一确认端点。")
        ipv4 = sorted(item for item in endpoints if ":" not in item[0])
        if len(ipv4) > 1:
            raise _manual("容器具有多个 ADB 发布地址，无法唯一确认端点。")
        host, port = ipv4[0] if ipv4 else sorted(endpoints)[0]
        return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"

    def discover(self, profile, host, timeout=DISCOVERY_TIMEOUT):
        result = {"installations": [], "errors": []}
        try:
            manager = self._manager(profile)
            deadline = self.monotonic() + max(timeout, 0)
            self._engine(manager, deadline)
            ids = self._command(
                manager, ["container", "ls", "--all", "--quiet", "--no-trunc"], deadline
            ).split()
            if (
                len(ids) > MAX_INSTANCES
                or len(set(ids)) != len(ids)
                or any(not _CONTAINER_ID.fullmatch(value) for value in ids)
            ):
                raise _invalid_output()
            rows = self._inspect_rows(manager, ids, deadline) if ids else []
            instances = []
            for row in rows:
                try:
                    instance = self._container(row)
                except InstanceBindingError as exc:
                    # One unsupported container must not hide usable siblings.
                    # The discovery service keeps explicit selection required
                    # when any container still needs repair/manual setup.
                    repair = redroid_repair(exc)
                    name = row.get("Name")
                    label = name if isinstance(name, str) else row["Id"]
                    result["errors"].append(
                        replace(repair, message=f"{label}: {repair.message}")
                    )
                    continue
                if instance is not None:
                    instances.append(instance)
            if not instances:
                if result["errors"]:
                    return result
                raise InstanceBindingError(
                    "no_redroid",
                    "本机 Docker 未发现 redroid/redroid 镜像容器；自定义镜像请使用高级手动配置。",
                    ["preset_id"],
                )
            result["installations"].append(
                {
                    "preset_id": REDROID_PRESET,
                    "installation_path": str(Path(manager).parent),
                    "manager_path": manager,
                    "config_path": LOCAL_DOCKER,
                    "instances": instances,
                }
            )
        except InstanceBindingError as exc:
            result["errors"].append(redroid_repair(exc))
        return result

    def _bound(self, profile, deadline):
        manager = self._manager(profile)
        if (
            not _CONTAINER_ID.fullmatch(profile.instance_id)
            or profile.config_path != LOCAL_DOCKER
        ):
            raise InstanceBindingError(
                "redroid_binding_changed",
                "请重新检测并选择本机 Docker 容器，保存完整容器 ID 与本机绑定。",
                ["instance_id"],
            )
        self._engine(manager, deadline)
        rows = self._inspect_rows(manager, [profile.instance_id], deadline)
        try:
            instance = self._container(rows[0])
        except InstanceBindingError as exc:
            if (
                exc.code == "endpoint_unresolved"
                and self._startup is not None
                and self._startup[:2] == (manager, profile.instance_id)
                and self.monotonic() < self._startup[2]
            ):
                raise InstanceEndpointPending(
                    "endpoint_unresolved", "等待已确认启动的同一容器发布 ADB 端口。", []
                ) from exc
            raise
        if instance is None:
            raise _manual("已绑定容器使用自定义镜像。")
        return manager, instance

    def inspect(self, profile, timeout):
        _, instance = self._bound(profile, self.monotonic() + timeout)
        return InstanceObservation(instance["state"], instance["serial"] or None)

    def start_confirmed(self, profile, timeout):
        deadline = self.monotonic() + timeout
        manager, instance = self._bound(profile, deadline)
        if instance["state"] != "stopped":
            return True
        output = self._command(
            manager, ["container", "start", profile.instance_id], deadline
        )
        if output.strip() != profile.instance_id:
            raise InstanceBindingError(
                "redroid_start_failed",
                "Docker 未确认已绑定容器启动成功，请检查容器后重试。",
                [],
            )
        self._startup = (manager, profile.instance_id, deadline)
        return True

    def start(self, profile, timeout):
        # Scheduled starts and recovery cannot reuse a prior launch confirmation.
        return False

    def stop(self, profile, timeout):
        return False
