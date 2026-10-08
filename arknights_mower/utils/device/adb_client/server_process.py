"""Inspect Windows shared listeners and stop only a verified retained handle."""

import ctypes
import os
import socket
import struct
import time
from pathlib import Path

from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.server import (
    ADB_SERVER_ADDRESS,
    SharedADBError,
    SharedADBHandshakeTimeout,
)


class _TCP6Row(ctypes.Structure):
    _fields_ = [
        ("local_address", ctypes.c_ubyte * 16),
        ("local_scope", ctypes.c_uint32),
        ("local_port", ctypes.c_uint32),
        ("remote_address", ctypes.c_ubyte * 16),
        ("remote_scope", ctypes.c_uint32),
        ("remote_port", ctypes.c_uint32),
        ("state", ctypes.c_uint32),
        ("pid", ctypes.c_uint32),
    ]


class _TCP6Table(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint32), ("rows", _TCP6Row * 1)]


def _windows_api():
    if os.name != "nt":
        raise SharedADBError("当前平台不支持核验共享 ADB 端口占用进程")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    tcp = ctypes.WinDLL("iphlpapi", use_last_error=True).GetExtendedTcpTable
    dword, handle, boolean = ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int
    signatures = (
        (kernel.OpenProcess, [dword, boolean, dword], handle),
        (kernel.CloseHandle, [handle], boolean),
        (
            kernel.QueryFullProcessImageNameW,
            [handle, dword, ctypes.c_wchar_p, ctypes.POINTER(dword)],
            boolean,
        ),
        (kernel.TerminateProcess, [handle, dword], boolean),
        (kernel.WaitForSingleObject, [handle, dword], dword),
        (tcp, [handle, ctypes.POINTER(dword), boolean, dword, dword, dword], dword),
    )
    for function, arguments, result in signatures:
        function.argtypes, function.restype = arguments, result
    return kernel, tcp


def _tcp_table(query, remaining, family, row_size, *, offset=4):
    """Read one bounded owner table without accepting a partial snapshot."""
    size = ctypes.c_uint32()
    remaining()
    status = query(None, ctypes.byref(size), False, family, 3, 0)
    for _ in range(3):
        remaining()
        if status != 122 or not 4 <= size.value <= 1024 * 1024:
            raise SharedADBError("无法核验共享 ADB 端口的进程归属")
        buffer = ctypes.create_string_buffer(size.value)
        capacity = len(buffer)
        status = query(buffer, ctypes.byref(size), False, family, 3, 0)
        remaining()
        if status == 0:
            break
    else:
        raise SharedADBError("共享 ADB 端口归属持续变化，保留现有进程")
    if status != 0 or not 4 <= size.value <= capacity:
        raise SharedADBError("共享 ADB 端口归属读取失败")
    count = struct.unpack_from("<I", buffer)[0]
    if size.value < offset or count > (size.value - offset) // row_size:
        raise SharedADBError("共享 ADB 端口归属记录无效")
    return buffer, count


def _listener_pid(query, remaining):
    """Read a bounded IPv4 listener table; reject ambiguous loopback ownership."""
    buffer, count = _tcp_table(query, remaining, socket.AF_INET, 24)
    owners = set()
    for index in range(count):
        remaining()
        state, address, port, _, _, pid = struct.unpack_from(
            "<6I", buffer, 4 + index * 24
        )
        host = socket.inet_ntoa(struct.pack("<I", address))
        if (
            state == 2
            and host in {ADB_SERVER_ADDRESS[0], "0.0.0.0"}
            and socket.ntohs(port & 0xFFFF) == ADB_SERVER_ADDRESS[1]
        ):
            if pid == 0:
                raise SharedADBError("共享 ADB 端口占用进程无效")
            owners.add(pid)
    if len(owners) > 1:
        raise SharedADBError("共享 ADB 端口占用进程不唯一，保留现有进程")
    return next(iter(owners), None)


def adb_listener_absent(*, remaining):
    """Confirm absence through both Windows tables within the caller's budget.

    Any IPv6 listener on the shared port preserves possible dual-stack
    occupancy. Query failure never supplies absence evidence.
    """
    remaining()
    _, query = _windows_api()
    remaining()
    pid = _listener_pid(query, remaining)
    remaining()
    if pid is not None:
        return False
    row_size, offset = ctypes.sizeof(_TCP6Row), _TCP6Table.rows.offset
    buffer, count = _tcp_table(
        query, remaining, socket.AF_INET6, row_size, offset=offset
    )
    for index in range(count):
        remaining()
        row = _TCP6Row.from_buffer(buffer, offset + index * row_size)
        if (
            row.state == 2
            and socket.ntohs(row.local_port & 0xFFFF) == ADB_SERVER_ADDRESS[1]
        ):
            return False
    remaining()
    return True


def terminate_verified_adb(
    adb_path, timeout, *, probe, monotonic=time.monotonic, cancelled=None
):
    """Return false for a recovered service; never terminate an unverified owner."""
    deadline = monotonic() + max(0, timeout)

    def remaining():
        if cancelled is not None and cancelled():
            raise MowerExit
        value = deadline - monotonic()
        if value <= 0:
            raise SharedADBError("共享 ADB 进程停止的时间预算已耗尽")
        return value

    remaining()
    try:
        expected = Path(adb_path).resolve(strict=True)
        if not expected.is_file():
            raise OSError("所选 ADB 路径不是文件")
    except OSError as exc:
        raise SharedADBError("无法核验所选 ADB 可执行文件，保留现有进程") from exc
    kernel, query = _windows_api()
    pid = _listener_pid(query, remaining)
    if pid is None:
        return True
    remaining()
    # Query, terminate and wait rights; no process-tree or name-based action.
    handle = kernel.OpenProcess(0x1000 | 0x0001 | 0x100000, False, pid)
    if not handle:
        raise SharedADBError("无法取得共享 ADB 端口占用进程的核验与停止权限")
    try:
        remaining()
        if kernel.WaitForSingleObject(handle, 0) != 258:
            raise SharedADBError("共享 ADB 端口占用进程已改变，取消进程停止")
        image = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_uint32(len(image))
        if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            raise SharedADBError("无法读取共享 ADB 端口占用进程的可执行文件")
        try:
            observed = Path(image.value).resolve(strict=True)
        except OSError as exc:
            raise SharedADBError("无法核验共享 ADB 进程的可执行文件") from exc
        if os.path.normcase(str(observed)) != os.path.normcase(str(expected)):
            raise SharedADBError("共享 ADB 端口由其他程序占用，保留现有进程")
        if _listener_pid(query, remaining) != pid:
            raise SharedADBError("共享 ADB 端口占用进程已改变，取消进程停止")
        try:
            version = probe(min(1, remaining()))
        except SharedADBHandshakeTimeout:
            pass
        else:
            if version is not None:
                return False
            return True
        remaining()
        if (
            kernel.WaitForSingleObject(handle, 0) != 258
            or _listener_pid(query, remaining) != pid
        ):
            raise SharedADBError("共享 ADB 端口占用进程已改变，取消进程停止")
        remaining()
        if not kernel.TerminateProcess(handle, 1):
            raise SharedADBError("无法终止已核验的共享 ADB 进程")
        waited = kernel.WaitForSingleObject(handle, max(1, int(remaining() * 1000)))
        remaining()
        if waited != 0:
            raise SharedADBError("共享 ADB 进程未在时间预算内停止")
        return True
    finally:
        kernel.CloseHandle(handle)
