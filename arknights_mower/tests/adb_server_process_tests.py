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
        rows6=[],
    )

    def table(buffer, size_pointer, ordered, family, table_class, reserved):
        assert family in (socket.AF_INET, socket.AF_INET6)
        assert (table_class, reserved) == (3, 0)
        if family == socket.AF_INET6:
            rows, row_format = host.rows6, "<16sII16sIIII"
        else:
            row_format = "<6I"
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
            struct.pack(row_format, *row) for row in rows
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


def test_absence_query_checks_both_families_without_opening_processes(process):
    process.host.owners = []
    assert server_process.adb_listener_absent(remaining=lambda: 5)
    assert {call.args[3] for call in process.query.call_args_list} == {
        socket.AF_INET,
        socket.AF_INET6,
    }
    process.kernel.OpenProcess.assert_not_called()
    process.kernel.TerminateProcess.assert_not_called()


def test_existing_ipv4_listener_never_confirms_absence(process):
    assert server_process.adb_listener_absent(remaining=lambda: 5) is False
    process.kernel.OpenProcess.assert_not_called()
    process.kernel.TerminateProcess.assert_not_called()


@pytest.mark.parametrize("address", ["::", "::1", "::ffff:127.0.0.1"])
def test_ipv6_listener_preserves_possible_shared_port_occupancy(process, address):
    process.host.owners = []
    process.host.rows6 = [
        (
            socket.inet_pton(socket.AF_INET6, address),
            0,
            socket.htons(5037),
            b"\0" * 16,
            0,
            0,
            2,
            421,
        )
    ]
    assert server_process.adb_listener_absent(remaining=lambda: 5) is False
    process.kernel.OpenProcess.assert_not_called()
    process.kernel.TerminateProcess.assert_not_called()


@pytest.mark.parametrize("state,port", [(2, 5038), (5, 5037)])
def test_unrelated_ipv6_rows_do_not_block_absence_confirmation(process, state, port):
    process.host.owners = []
    process.host.rows6 = [
        (b"\0" * 16, 0, socket.htons(port), b"\0" * 16, 0, 0, state, 421)
    ]
    assert server_process.adb_listener_absent(remaining=lambda: 5)
    process.kernel.OpenProcess.assert_not_called()


@pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6])
def test_native_query_failure_never_confirms_absence(process, family):
    process.host.owners = []
    table = process.query.side_effect

    def denied(buffer, pointer, ordered, observed_family, table_class, reserved):
        if observed_family == family:
            return 5
        return table(buffer, pointer, ordered, observed_family, table_class, reserved)

    process.query.side_effect = denied
    with pytest.raises(SharedADBError):
        server_process.adb_listener_absent(remaining=lambda: 5)
    process.kernel.OpenProcess.assert_not_called()


def test_truncated_ipv6_table_never_confirms_absence(process):
    process.host.owners = []
    table = process.query.side_effect

    def truncated(buffer, pointer, ordered, family, table_class, reserved):
        if family == socket.AF_INET:
            return table(buffer, pointer, ordered, family, table_class, reserved)
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32)).contents.value = 4
        if buffer is None:
            return 122
        ctypes.memmove(buffer, struct.pack("<I", 1), 4)
        return 0

    process.query.side_effect = truncated
    with pytest.raises(SharedADBError, match="记录无效"):
        server_process.adb_listener_absent(remaining=lambda: 5)
    process.kernel.OpenProcess.assert_not_called()


@pytest.mark.parametrize("cause", ["cancelled", "budget"])
def test_absence_query_checks_budget_after_native_call(process, cause):
    process.host.owners = []
    table = process.query.side_effect

    def interrupted(*args):
        result = table(*args)
        if args[0] is not None and args[3] == socket.AF_INET6:
            process.host.cancelled = True
            process.host.now = 5
        return result

    def remaining():
        if cause == "cancelled" and process.host.cancelled:
            raise MowerExit
        if process.host.now >= 5:
            raise SharedADBError("query budget exhausted")
        return 5 - process.host.now

    process.query.side_effect = interrupted
    with pytest.raises(MowerExit if cause == "cancelled" else SharedADBError):
        server_process.adb_listener_absent(remaining=remaining)
    process.kernel.OpenProcess.assert_not_called()


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
