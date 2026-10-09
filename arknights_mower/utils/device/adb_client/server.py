"""Guard commands against implicit shared ADB server replacement.

An ADB CLI can kill an existing server on a protocol-version mismatch. The
host:version socket request and local `adb version` command do not do that.
"""

import hashlib
import math
import os
import re
import socket
import stat
import subprocess
import time
from collections import OrderedDict
from threading import Lock

from arknights_mower.utils.device.manager_io import run_command

ADB_SERVER_ADDRESS = ("127.0.0.1", 5037)
_DEFAULT_RUN_COMMAND = run_command
_ADB_VERSION_CACHE = OrderedDict()
_ADB_VERSION_CACHE_LOCK = Lock()
_ADB_VERSION_CACHE_CAPACITY = 16
_ADB_VERSION_MAX_FILE_SIZE = 32 * 1024 * 1024


class SharedADBError(RuntimeError):
    """The shared server cannot safely be used by the selected ADB executable."""


class SharedADBHandshakeTimeout(SharedADBError):
    """A local listener was addressed but answered no host handshake.

    The host never completed the TCP connect or never replied once connected.
    Neither observation alone proves absence. Recovery confirms absence
    independently for a known connect phase or retains the restart window.
    """

    def __init__(self, *args, phase=None):
        super().__init__(*args)
        self.phase = phase


class SharedADBStopTimeout(SharedADBError):
    """The explicit protocol stop receives no answer within its budget."""


def _remaining(deadline, monotonic, timeout):
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise SharedADBError("共享 ADB 检查或命令的时间预算已耗尽")
    return min(timeout, remaining)


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


def _receive(connection, length, deadline, monotonic, timeout):
    output = bytearray()
    while len(output) < length:
        connection.settimeout(_remaining(deadline, monotonic, timeout))
        data = connection.recv(length - len(output))
        if not data:
            raise SharedADBError("共享 ADB server 提前关闭了响应")
        output.extend(data)
    _remaining(deadline, monotonic, timeout)
    return bytes(output)


def probe_adb_server(
    timeout, *, monotonic=time.monotonic, socket_factory=None, address=None
):
    """Return its protocol version; only a refused connect means no server.

    A refused connect is the one answer that proves no listener owns the port.
    Any other connect failure or an unanswered handshake leaves the listener
    unproven rather than absent.
    """
    deadline = monotonic() + max(0, timeout)
    factory = socket_factory or socket.socket
    phase = "connect"
    try:
        with factory(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.settimeout(_remaining(deadline, monotonic, timeout))
            try:
                connection.connect(address or ADB_SERVER_ADDRESS)
            except ConnectionRefusedError:
                return None
            phase = "response"
            connection.settimeout(_remaining(deadline, monotonic, timeout))
            connection.sendall(b"000chost:version")

            def receive(length):
                return _receive(connection, length, deadline, monotonic, timeout)

            if receive(4) != b"OKAY" or receive(4) != b"0004":
                raise SharedADBError("共享 ADB server 返回的版本响应格式无效")
            version = receive(4)
            if re.fullmatch(rb"[0-9a-fA-F]{4}", version) is None:
                raise SharedADBError("共享 ADB server 返回的协议版本无效")
            return int(version, 16)
    except socket.timeout as exc:
        raise SharedADBHandshakeTimeout(
            "共享 ADB server 未完成主机握手：连接或应答超时", phase=phase
        ) from exc
    except OSError as exc:
        raise SharedADBError(f"无法安全读取共享 ADB server 状态：{exc}") from exc


def kill_adb_server(timeout, *, monotonic=time.monotonic, socket_factory=None):
    """Send an explicit host:kill request to the shared loopback server only."""
    deadline = monotonic() + max(0, timeout)
    factory = socket_factory or socket.socket
    try:
        with factory(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.settimeout(_remaining(deadline, monotonic, timeout))
            connection.connect(ADB_SERVER_ADDRESS)
            connection.settimeout(_remaining(deadline, monotonic, timeout))
            connection.sendall(b"0009host:kill")
            response = _receive(connection, 4, deadline, monotonic, timeout)
            if response == b"FAIL":
                raise SharedADBError("共享 ADB server 拒绝显式停止请求（FAIL）")
            if response != b"OKAY":
                raise SharedADBError("共享 ADB server 返回无效的停止响应")
    except socket.timeout as exc:
        raise SharedADBStopTimeout(f"无法显式停止共享 ADB server：{exc}") from exc
    except OSError as exc:
        raise SharedADBError(f"无法显式停止共享 ADB server：{exc}") from exc


def _adb_file_state(path):
    identity = os.stat(path)
    if (
        not stat.S_ISREG(identity.st_mode)
        or not identity.st_ino
        or not 0 < identity.st_size <= _ADB_VERSION_MAX_FILE_SIZE
    ):
        return None
    return (
        path,
        identity.st_dev,
        identity.st_ino,
        identity.st_mode,
        identity.st_size,
        identity.st_mtime_ns,
        identity.st_ctime_ns,
    )


def _adb_executable_identity(adb_path):
    try:
        path = os.fspath(adb_path)
        if not os.path.isabs(path) or (
            os.name == "nt" and not os.path.splitdrive(path)[0]
        ):
            return None
        path = os.path.realpath(path, strict=True)
        identity = _adb_file_state(path)
        if identity is None or not _is_native_adb(path):
            return None
        with open(path, "rb") as executable:
            content = executable.read(identity[4] + 1)
        if len(content) != identity[4] or _adb_file_state(path) != identity:
            return None
        return (*identity, hashlib.sha256(content).digest())
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _is_native_adb(path):
    try:
        with open(path, "rb") as executable:
            header = executable.read(64)
            if header[:4] in {
                b"\x7fELF",
                b"\xfe\xed\xfa\xce",
                b"\xce\xfa\xed\xfe",
                b"\xfe\xed\xfa\xcf",
                b"\xcf\xfa\xed\xfe",
            }:
                return True
            if len(header) == 64 and header[:2] == b"MZ":
                offset = int.from_bytes(header[60:64], "little")
                if 64 <= offset <= 1024 * 1024:
                    executable.seek(offset)
                    return executable.read(4) == b"PE\0\0"
    except OSError:
        pass
    return False


def adb_client_version(adb_path, *, timeout, run=None):
    """Reuse only an unchanged native executable's local protocol version.

    Shared-server observations are never cached. Relative paths, wrappers,
    unavailable file identities and injected runners retain a fresh command.
    """
    runner = run or run_command
    deadline = (
        time.monotonic() + timeout
        if runner is _DEFAULT_RUN_COMMAND and math.isfinite(timeout) and timeout > 0
        else None
    )
    identity = _adb_executable_identity(adb_path) if deadline is not None else None
    if identity is not None:
        with _ADB_VERSION_CACHE_LOCK:
            cached = _ADB_VERSION_CACHE.get(identity)
            if cached is not None:
                _ADB_VERSION_CACHE.move_to_end(identity)
        if cached is not None:
            if _adb_executable_identity(adb_path) != identity:
                raise SharedADBError(
                    "所选 ADB 文件在版本检查期间发生变化，保留共享 server"
                )
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired([adb_path, "version"], timeout)
            return cached
    remaining = (
        timeout if deadline is None else min(timeout, deadline - time.monotonic())
    )
    if deadline is not None and remaining <= 0:
        raise subprocess.TimeoutExpired([adb_path, "version"], timeout)
    result = runner(
        [adb_path, "version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=remaining,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    result.check_returncode()
    output = result.stdout
    if isinstance(output, str):
        output = output.encode("utf-8")
    matches = re.findall(
        rb"^Android Debug Bridge version 1\.0\.(\d+)\s*$", output, re.M
    )
    if len(matches) != 1 or int(matches[0]) <= 0:
        raise SharedADBError("无法确认所选 ADB 程序的协议版本，保留共享 server")
    version = int(matches[0])
    if identity is not None:
        if _adb_executable_identity(adb_path) != identity:
            raise SharedADBError("所选 ADB 文件在版本检查期间发生变化，保留共享 server")
    if deadline is not None and time.monotonic() >= deadline:
        raise subprocess.TimeoutExpired([adb_path, "version"], timeout)
    if identity is not None:
        with _ADB_VERSION_CACHE_LOCK:
            _ADB_VERSION_CACHE[identity] = version
            _ADB_VERSION_CACHE.move_to_end(identity)
            while len(_ADB_VERSION_CACHE) > _ADB_VERSION_CACHE_CAPACITY:
                _ADB_VERSION_CACHE.popitem(last=False)
    return version


def check_adb_version(client_version, server_version):
    if type(server_version) is not int or server_version <= 0:
        raise SharedADBError("共享 ADB server 的协议版本无效")
    if client_version != server_version:
        raise SharedADBError(
            "所选 ADB 与已运行的共享 server 版本不一致；请使用兼容的 ADB，mower 不会重启共享 server"
        )


def guard_adb(adb_path, *, timeout, run=None, probe=None, monotonic=time.monotonic):
    """Check the existing server and return the same deadline's remaining time."""
    _check_server_environment(os.environ)
    deadline = monotonic() + max(0, timeout)
    runner = run or run_command
    try:
        if probe is None:
            version = probe_adb_server(
                _remaining(deadline, monotonic, timeout), monotonic=monotonic
            )
        else:
            version = probe(_remaining(deadline, monotonic, timeout))
    except OSError as exc:
        raise SharedADBError(f"无法安全读取共享 ADB server 状态：{exc}") from exc
    if version is not None:
        if type(version) is not int or version <= 0:
            raise SharedADBError("共享 ADB server 的协议版本无效")
        client_version = adb_client_version(
            adb_path,
            timeout=_remaining(deadline, monotonic, timeout),
            run=runner,
        )
        check_adb_version(client_version, version)
    return _remaining(deadline, monotonic, timeout)


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
    if command in {"kill-server", "start-server", "server", "fork-server", "nodaemon"}:
        raise SharedADBError("共享 ADB 服务生命周期只能由恢复协调器管理")
    runner = run or run_command
    if command != "version":
        guard_adb(
            argv[0],
            timeout=_remaining(deadline, monotonic, timeout),
            run=runner,
            probe=probe,
            monotonic=monotonic,
        )
    result = runner(argv, timeout=_remaining(deadline, monotonic, timeout), **kwargs)
    _remaining(deadline, monotonic, timeout)
    return result
