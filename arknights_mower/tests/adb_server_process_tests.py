"""Verified shared-port termination stays bounded and preserves foreign owners."""

import ctypes
import socket
import struct
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client import server_process
from arknights_mower.utils.device.adb_client.server import (
    SharedADBError,
    SharedADBHandshakeTimeout,
)


@pytest.fixture
def process(tmp_path, monkeypatch):
    binary = tmp_path / "selected tools" / "adb.exe"
    binary.parent.mkdir()
    binary.touch()
    host = SimpleNamespace(
        path=str(binary),
        now=0.0,
        owners=[421],
        alive=True,
        cancelled=False,
        terminated=False,
        rows=None,
    )

    def table(buffer, size_pointer, ordered, family, table_class, reserved):
        assert (family, table_class, reserved) == (socket.AF_INET, 3, 0)
        rows = (
            host.rows
            if host.rows is not None
            else [
                (
                    2,
                    struct.unpack("<I", socket.inet_aton("127.0.0.1"))[0],
                    socket.htons(5037),
                    0,
                    0,
                    owner,
                )
                for owner in host.owners
            ]
        )
        data = struct.pack("<I", len(rows)) + b"".join(
            struct.pack("<6I", *row) for row in rows
        )
        ctypes.cast(size_pointer, ctypes.POINTER(ctypes.c_uint32)).contents.value = len(
            data
        )
        if buffer is None:
            return 122
        ctypes.memmove(buffer, data, len(data))
        return 0

    def image(handle, flags, buffer, size_pointer):
        buffer.value = host.path
        return True

    def terminate(handle, code):
        host.terminated = True
        return True

    def wait(handle, milliseconds):
        if milliseconds == 0:
            return 258 if host.alive else 0
        return 0 if host.terminated else 258

    kernel = SimpleNamespace(
        OpenProcess=Mock(return_value=777),
        CloseHandle=Mock(return_value=True),
        QueryFullProcessImageNameW=Mock(side_effect=image),
        TerminateProcess=Mock(side_effect=terminate),
        WaitForSingleObject=Mock(side_effect=wait),
    )
    query = Mock(side_effect=table)
    monkeypatch.setattr(server_process, "_windows_api", lambda: (kernel, query))

    def stalled(timeout):
        host.now += min(0.5, timeout)
        raise SharedADBHandshakeTimeout("no host response")

    probe = Mock(side_effect=stalled)

    def stop():
        return server_process.terminate_verified_adb(
            str(binary),
            5,
            probe=probe,
            monotonic=lambda: host.now,
            cancelled=lambda: host.cancelled,
        )

    return SimpleNamespace(
        binary=binary,
        host=host,
        kernel=kernel,
        query=query,
        probe=probe,
        stop=stop,
    )


def test_verified_listener_uses_one_retained_handle_and_waits_for_exit(process):
    assert process.stop()
    process.kernel.OpenProcess.assert_called_once_with(0x101001, False, 421)
    process.kernel.TerminateProcess.assert_called_once_with(777, 1)
    process.kernel.CloseHandle.assert_called_once_with(777)
    handle, milliseconds = process.kernel.WaitForSingleObject.call_args.args
    assert handle == 777 and 0 < milliseconds <= 4500


@pytest.mark.parametrize(
    "state,address,port",
    [(2, "127.0.0.1", 5038), (2, "192.168.1.1", 5037), (5, "127.0.0.1", 5037)],
)
def test_unrelated_tcp_rows_never_open_a_process(process, state, address, port):
    process.host.rows = [
        (
            state,
            struct.unpack("<I", socket.inet_aton(address))[0],
            socket.htons(port),
            0,
            0,
            421,
        )
    ]
    assert process.stop()
    process.kernel.OpenProcess.assert_not_called()
    process.kernel.TerminateProcess.assert_not_called()


def test_wildcard_and_loopback_rows_for_one_owner_allow_verified_stop(process):
    process.host.rows = [
        (
            2,
            struct.unpack("<I", socket.inet_aton(address))[0],
            socket.htons(5037),
            0,
            0,
            421,
        )
        for address in ("127.0.0.1", "0.0.0.0")
    ]
    assert process.stop()
    process.kernel.OpenProcess.assert_called_once_with(0x101001, False, 421)
    process.kernel.TerminateProcess.assert_called_once_with(777, 1)


def test_foreign_executable_with_same_name_is_preserved(process, tmp_path):
    foreign = tmp_path / "another tool" / "adb.exe"
    foreign.parent.mkdir()
    foreign.touch()
    process.host.path = str(foreign)
    with pytest.raises(SharedADBError, match="其他程序"):
        process.stop()
    process.kernel.TerminateProcess.assert_not_called()
    process.kernel.CloseHandle.assert_called_once_with(777)
    process.probe.assert_not_called()


def test_changed_port_owner_during_reprobe_is_preserved(process):
    def changed(timeout):
        process.host.owners = [422]
        raise SharedADBHandshakeTimeout("no answer")

    process.probe.side_effect = changed
    with pytest.raises(SharedADBError, match="占用进程已改变"):
        process.stop()
    process.kernel.TerminateProcess.assert_not_called()
    process.kernel.CloseHandle.assert_called_once_with(777)


def test_exited_retained_process_never_redirects_termination_by_pid(process):
    def exited(timeout):
        process.host.alive = False
        raise SharedADBHandshakeTimeout("no answer")

    process.probe.side_effect = exited
    with pytest.raises(SharedADBError, match="占用进程已改变"):
        process.stop()
    process.kernel.TerminateProcess.assert_not_called()
    process.kernel.CloseHandle.assert_called_once_with(777)


@pytest.mark.parametrize("version", [None, 41])
def test_answered_or_absent_reprobe_never_terminates(process, version):
    process.probe.side_effect = None
    process.probe.return_value = version
    assert process.stop() is (version is None)
    process.kernel.TerminateProcess.assert_not_called()
    process.kernel.CloseHandle.assert_called_once_with(777)


def test_malformed_reprobe_preserves_the_verified_process(process):
    process.probe.side_effect = SharedADBError("malformed reply")
    with pytest.raises(SharedADBError, match="malformed"):
        process.stop()
    process.kernel.TerminateProcess.assert_not_called()
    process.kernel.CloseHandle.assert_called_once_with(777)


@pytest.mark.parametrize("owners", [[], [421, 422], [0]])
def test_missing_or_ambiguous_listener_never_opens_a_process(process, owners):
    process.host.owners = owners
    if owners:
        with pytest.raises(SharedADBError):
            process.stop()
    else:
        assert process.stop()
    process.kernel.OpenProcess.assert_not_called()
    process.kernel.TerminateProcess.assert_not_called()


@pytest.mark.parametrize("cause", ["cancelled", "budget"])
def test_cancelled_or_expired_reprobe_never_terminates(process, cause):
    def expired(timeout):
        if cause == "cancelled":
            process.host.cancelled = True
        else:
            process.host.now = 5
        raise SharedADBHandshakeTimeout("no answer")

    process.probe.side_effect = expired
    with pytest.raises(MowerExit if cause == "cancelled" else SharedADBError):
        process.stop()
    process.kernel.TerminateProcess.assert_not_called()
    process.kernel.CloseHandle.assert_called_once_with(777)


@pytest.mark.parametrize("failure", ["open", "image", "terminate", "wait"])
def test_native_failures_preserve_handle_cleanup_and_report_failure(process, failure):
    if failure == "open":
        process.kernel.OpenProcess.return_value = None
    elif failure == "image":
        process.kernel.QueryFullProcessImageNameW.side_effect = None
        process.kernel.QueryFullProcessImageNameW.return_value = False
    elif failure == "terminate":
        process.kernel.TerminateProcess.side_effect = None
        process.kernel.TerminateProcess.return_value = False
    else:
        process.kernel.WaitForSingleObject.side_effect = lambda *args: 258
    with pytest.raises(SharedADBError):
        process.stop()
    if failure == "open":
        process.kernel.CloseHandle.assert_not_called()
    else:
        process.kernel.CloseHandle.assert_called_once_with(777)


@pytest.mark.parametrize("size", [0, 3, 1024 * 1024 + 1])
def test_invalid_or_unbounded_native_table_never_opens_a_process(process, size):
    def invalid(buffer, pointer, *args):
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32)).contents.value = size
        return 122

    process.query.side_effect = invalid
    with pytest.raises(SharedADBError):
        process.stop()
    process.kernel.OpenProcess.assert_not_called()


def test_missing_selected_binary_never_loads_process_api(process, monkeypatch):
    process.binary.unlink()
    api = Mock(side_effect=AssertionError("native API must not be used"))
    monkeypatch.setattr(server_process, "_windows_api", api)
    with pytest.raises(SharedADBError, match="所选 ADB"):
        process.stop()
    api.assert_not_called()
