"""Guard shared ADB and route simulator operations through an owned server.

An ADB CLI can kill an existing server on a protocol-version mismatch. The
host:version socket request and local `adb version` command do not do that.
"""

import os
import re
import socket
import subprocess
import time
from contextlib import contextmanager
from contextvars import ContextVar

_owned_server = ContextVar("owned_adb_server", default=None)


@contextmanager
def adb_server_scope(server):
    token = _owned_server.set(server)
    try:
        yield
    finally:
        _owned_server.reset(token)


def current_adb_server():
    return _owned_server.get()


def adb_server_address():
    server = current_adb_server()
    return server.address if server is not None else ("127.0.0.1", 5037)


def emulator_connect_target(serial):
    match = re.fullmatch(r"emulator-([0-9]{1,5})", serial)
    if match is None:
        return None
    port = int(match[1])
    if port % 2 or not 1024 <= port < 65535:
        return None
    return f"emu:{port},{port + 1}"


def adb_command(argv):
    server = current_adb_server()
    if server is None:
        return argv
    index = 1
    while index < len(argv) and argv[index].startswith("-"):
        option = argv[index]
        if option.startswith(("-H", "-P", "-L")):
            raise SharedADBError("自有 ADB 命令不能重定向服务地址")
        index += 2 if option in {"-s", "-t"} else 1
    if index < len(argv) and argv[index] in {
        "kill-server",
        "start-server",
        "server",
        "fork-server",
        "nodaemon",
    }:
        raise SharedADBError("ADB 服务生命周期只能由其进程所有者管理")
    host, port = server.address
    return [argv[0], "-H", host, "-P", str(port), *argv[1:]]


def adb_subprocess_options(environment=None):
    server = current_adb_server()
    if server is None:
        return {}
    host, port = server.address
    environment = dict(os.environ if environment is None else environment)
    environment.update(
        ADB_SERVER_SOCKET=f"tcp:{host}:{port}",
        ANDROID_ADB_SERVER_ADDRESS=host,
        ANDROID_ADB_SERVER_PORT=str(port),
        ADB_SERVER_PORT=str(port),
    )
    return {"env": environment}


class SharedADBError(RuntimeError):
    """The shared server cannot safely be used by the selected ADB executable."""


def _remaining(deadline, monotonic):
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise SharedADBError("共享 ADB 检查或命令的时间预算已耗尽")
    return remaining


def _check_server_environment(environment):
    expected = {
        "ADB_SERVER_SOCKET": "tcp:127.0.0.1:5037",
        "ANDROID_ADB_SERVER_ADDRESS": "127.0.0.1",
        "ANDROID_ADB_SERVER_PORT": "5037",
        "ADB_SERVER_PORT": "5037",
    }
    for name, value in expected.items():
        if environment.get(name) and environment[name] != value:
            raise SharedADBError(f"{name} 重定向了 ADB server，无法安全验证共享 server")


def probe_adb_server(
    timeout, *, monotonic=time.monotonic, socket_factory=None, address=None
):
    """Return its protocol version; only a refused connect means no server."""
    deadline = monotonic() + max(0, timeout)
    factory = socket_factory or socket.socket
    try:
        with factory(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.settimeout(_remaining(deadline, monotonic))
            try:
                connection.connect(address or ("127.0.0.1", 5037))
            except ConnectionRefusedError:
                return None
            connection.settimeout(_remaining(deadline, monotonic))
            connection.sendall(b"000chost:version")

            def receive(length):
                output = bytearray()
                while len(output) < length:
                    connection.settimeout(_remaining(deadline, monotonic))
                    data = connection.recv(length - len(output))
                    if not data:
                        raise SharedADBError("共享 ADB server 提前关闭了版本响应")
                    output.extend(data)
                _remaining(deadline, monotonic)
                return bytes(output)

            if receive(4) != b"OKAY" or receive(4) != b"0004":
                raise SharedADBError("共享 ADB server 返回的版本响应格式无效")
            version = receive(4)
            if re.fullmatch(rb"[0-9a-fA-F]{4}", version) is None:
                raise SharedADBError("共享 ADB server 返回的协议版本无效")
            return int(version, 16)
    except OSError as exc:
        raise SharedADBError(f"无法安全读取共享 ADB server 状态：{exc}") from exc


def guard_adb(adb_path, *, timeout, run=None, probe=None, monotonic=time.monotonic):
    """Check the existing server and return the same deadline's remaining time."""
    _check_server_environment(os.environ)
    deadline = monotonic() + max(0, timeout)
    runner = run or subprocess.run
    owned = current_adb_server()
    if owned is not None:
        owned.check(adb_path, timeout=_remaining(deadline, monotonic))
        return _remaining(deadline, monotonic)
    try:
        if probe is None:
            version = probe_adb_server(
                _remaining(deadline, monotonic), monotonic=monotonic
            )
        else:
            version = probe(_remaining(deadline, monotonic))
    except OSError as exc:
        raise SharedADBError(f"无法安全读取共享 ADB server 状态：{exc}") from exc
    if version is not None:
        if type(version) is not int or version <= 0:
            raise SharedADBError("共享 ADB server 的协议版本无效")
        result = runner(
            [adb_path, "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=_remaining(deadline, monotonic),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        result.check_returncode()
        output = result.stdout
        if isinstance(output, str):
            output = output.encode("utf-8")
        matches = re.findall(
            rb"^Android Debug Bridge version 1\.0\.(\d+)\s*$", output, re.M
        )
        if len(matches) != 1:
            raise SharedADBError("无法确认所选 ADB 程序的协议版本，保留共享 server")
        if int(matches[0]) != version:
            raise SharedADBError(
                "所选 ADB 与已运行的共享 server 版本不一致；请使用兼容的 ADB，mower 不会重启共享 server"
            )
    return _remaining(deadline, monotonic)


def run_adb(argv, *, timeout, run=None, probe=None, monotonic=time.monotonic, **kwargs):
    """Run one ADB CLI command without its implicit server-restart behavior."""
    if not argv or not isinstance(argv, (list, tuple)):
        raise ValueError("ADB 命令必须为非空参数数组")
    if kwargs.get("shell"):
        raise ValueError("ADB 命令不能使用主机 shell")
    deadline = monotonic() + max(0, timeout)
    _check_server_environment(kwargs.get("env") or os.environ)
    index = 1
    while index < len(argv) and argv[index].startswith("-"):
        option = argv[index]
        if option.startswith(("-H", "-P", "-L")):
            raise SharedADBError("ADB server 地址必须与已验证的本地共享 server 一致")
        index += 2 if option in {"-s", "-t"} else 1
    command = argv[index] if index < len(argv) else ""
    if command in {"kill-server", "start-server", "server", "fork-server"}:
        raise SharedADBError("mower 不会重启或停止共享 ADB server")
    runner = run or subprocess.run
    if command != "version":
        guard_adb(
            argv[0],
            timeout=_remaining(deadline, monotonic),
            run=runner,
            probe=probe,
            monotonic=monotonic,
        )
    if current_adb_server() is not None and command != "version":
        kwargs.update(adb_subprocess_options(kwargs.get("env")))
        argv = adb_command(argv)
    result = runner(argv, timeout=_remaining(deadline, monotonic), **kwargs)
    _remaining(deadline, monotonic)
    return result
