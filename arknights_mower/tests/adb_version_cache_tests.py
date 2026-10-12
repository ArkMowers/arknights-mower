"""Local executable reuse keeps every shared-server observation fresh."""

import os
import socket
import struct
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from arknights_mower.tests.device_maatouch_tests import OwnedProcess
from arknights_mower.utils.device import manager_io
from arknights_mower.utils.device.adb_client import server
from arknights_mower.utils.device.maatouch import session as maatouch

NATIVE_HEADER = b"MZ" + bytes(58) + (64).to_bytes(4, "little") + b"PE\0\0"
UNIVERSAL_FORMATS = [
    (byteorder, wide) for byteorder in (">", "<") for wide in (False, True)
]


def universal_macho(byteorder, wide):
    image = bytearray(320)
    magic = 0xCAFEBABF if wide else 0xCAFEBABE
    entry_format = f"{byteorder}IIQQII" if wide else f"{byteorder}IIIII"
    entries = []
    for cpu, offset in ((0x1000007, 128), (0x100000C, 256)):
        fields = [cpu, 0, offset, 64, 7]
        if wide:
            fields.append(0)
        entries.append(struct.pack(entry_format, *fields))
        image[offset : offset + 64] = (
            struct.pack("<IIIIIIII", 0xFEEDFACF, cpu, 0, 2, 0, 0, 0, 0)
            + b"client41"
            + bytes(24)
        )
    table = struct.pack(f"{byteorder}II", magic, 2) + b"".join(entries)
    image[: len(table)] = table
    return image


@pytest.fixture(autouse=True)
def isolated_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External process or socket I/O was not mocked")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    for name in (
        "ADB_SERVER_SOCKET",
        "ANDROID_ADB_SERVER_ADDRESS",
        "ANDROID_ADB_SERVER_PORT",
        "ADB_SERVER_PORT",
    ):
        monkeypatch.delenv(name, raising=False)
    cache = getattr(server, "_ADB_VERSION_CACHE", {})
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def executable(tmp_path):
    path = tmp_path / "adb.exe"
    path.write_bytes(NATIVE_HEADER)
    return str(path)


@pytest.fixture
def command_io(monkeypatch):
    state = SimpleNamespace(
        calls=[],
        output=b"Android Debug Bridge version 1.0.41\n",
        returncode=0,
        after_version=None,
        touch_processes=[],
    )

    def popen(argv, *, stdout=None, stderr=None, **kwargs):
        state.calls.append(list(argv))
        if "com.shxyke.MaaTouch.App" in argv:
            process = OwnedProcess()
            state.touch_processes.append(process)
            return process
        if argv[-1] == "version":
            stdout.write(state.output)
            stdout.flush()
            if state.after_version is not None:
                state.after_version()
        return SimpleNamespace(
            stdin=None,
            returncode=state.returncode,
            poll=lambda: state.returncode,
        )

    monkeypatch.setattr(subprocess, "Popen", popen)
    return state


@pytest.mark.parametrize("explicit_default", [False, True])
def test_default_command_path_reuses_unchanged_local_version(
    executable, command_io, explicit_default
):
    options = {"run": manager_io.run_command} if explicit_default else {}
    for _ in range(2):
        assert server.adb_client_version(executable, timeout=5, **options) == 41
    assert command_io.calls == [[executable, "version"]]


@pytest.mark.parametrize("clock_start", [0.0, 510.2])
def test_local_identity_cannot_inflate_version_command_budget(
    monkeypatch, executable, command_io, clock_start
):
    timeouts = []

    def run(argv, **kwargs):
        timeouts.append(kwargs["timeout"])
        return manager_io.run_command(argv, **kwargs)

    monkeypatch.setattr(server, "run_command", run)
    monkeypatch.setattr(server, "_DEFAULT_RUN_COMMAND", run)
    monkeypatch.setattr(server.time, "monotonic", lambda: clock_start)
    assert server.adb_client_version(executable, timeout=5) == 41
    assert timeouts == [5]
    assert command_io.calls == [[executable, "version"]]


def test_maatouch_start_uses_cached_client_but_new_shared_socket_probes(
    monkeypatch, executable, command_io
):
    probe = Mock(return_value=41)
    monkeypatch.setattr(server, "probe_adb_server", probe)
    client = SimpleNamespace(adb_bin=executable, device_id="USB-123")
    for _ in range(2):
        with maatouch.Session(client) as session:
            assert session.pid == "123"
    assert probe.call_count == 2
    assert sum(argv[-1] == "version" for argv in command_io.calls) == 1
    assert len(command_io.touch_processes) == 2
    for process in command_io.touch_processes:
        assert process.events == ["terminate", "wait"]
        assert process.stdout.closed and process.stdin.closed


def test_changed_executable_rereads_protocol_version(executable, command_io):
    assert server.adb_client_version(executable, timeout=5) == 41
    with open(executable, "ab") as stream:
        stream.write(b" changed")
    command_io.output = b"Android Debug Bridge version 1.0.40\n"
    assert server.adb_client_version(executable, timeout=5) == 40
    assert len(command_io.calls) == 2


def test_replacement_with_same_size_and_mtime_rereads_version(
    executable, command_io, tmp_path
):
    assert server.adb_client_version(executable, timeout=5) == 41
    original = os.stat(executable)
    replacement = tmp_path / "replacement.exe"
    replacement.write_bytes(NATIVE_HEADER)
    os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
    os.replace(replacement, executable)
    command_io.output = b"Android Debug Bridge version 1.0.40\n"
    assert server.adb_client_version(executable, timeout=5) == 40
    assert len(command_io.calls) == 2


def test_same_inode_overwrite_with_restored_timestamps_blocks_input(
    monkeypatch, executable, command_io
):
    with open(executable, "ab") as stream:
        stream.write(b"client41")
    original_stat = os.stat
    original = original_stat(executable)

    def stat(path, *args, **kwargs):
        result = original_stat(path, *args, **kwargs)
        if os.fspath(path) != executable:
            return result
        # Windows reports creation time as ctime. Preserve it on every host to
        # expose an in-place replacement that restores the original mtime.
        return SimpleNamespace(
            **{
                field: original.st_ctime_ns
                if field == "st_ctime_ns"
                else getattr(result, field)
                for field in (
                    "st_dev",
                    "st_ino",
                    "st_mode",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                )
            }
        )

    monkeypatch.setattr(server.os, "stat", stat)
    assert server.adb_client_version(executable, timeout=5) == 41
    with open(executable, "r+b") as stream:
        stream.seek(-len(b"client41"), os.SEEK_END)
        stream.write(b"client40")
    os.utime(executable, ns=(original.st_atime_ns, original.st_mtime_ns))
    command_io.output = b"Android Debug Bridge version 1.0.40\n"
    with pytest.raises(server.SharedADBError, match="版本不一致"):
        server.run_adb(
            [executable, "shell", "input", "tap", "10", "20"],
            timeout=5,
            probe=lambda _: 41,
        )
    assert command_io.calls == [[executable, "version"], [executable, "version"]]


@pytest.mark.parametrize("field", ["st_mtime_ns", "st_ctime_ns", "st_ino", "st_dev"])
def test_each_file_identity_change_invalidates_version(
    monkeypatch, executable, command_io, field
):
    assert server.adb_client_version(executable, timeout=5) == 41
    original_stat = os.stat
    original = original_stat(executable)
    identity = SimpleNamespace(
        **{
            name: getattr(original, name)
            for name in (
                "st_mode",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
                "st_ino",
                "st_dev",
            )
        }
    )
    setattr(identity, field, getattr(identity, field) + 1)

    def stat(path, *args, **kwargs):
        return (
            identity
            if os.fspath(path) == executable
            else original_stat(path, *args, **kwargs)
        )

    monkeypatch.setattr(server.os, "stat", stat)
    command_io.output = b"Android Debug Bridge version 1.0.40\n"
    assert server.adb_client_version(executable, timeout=5) == 40
    assert len(command_io.calls) == 2


def test_different_executable_paths_keep_separate_versions(
    executable, command_io, tmp_path
):
    assert server.adb_client_version(executable, timeout=5) == 41
    other = tmp_path / "other-adb.exe"
    other.write_bytes(NATIVE_HEADER + b"other")
    command_io.output = b"Android Debug Bridge version 1.0.40\n"
    assert server.adb_client_version(str(other), timeout=5) == 40
    assert server.adb_client_version(executable, timeout=5) == 41
    assert len(command_io.calls) == 2


def test_unreadable_stat_cannot_reuse_cached_version(
    monkeypatch, executable, command_io
):
    assert server.adb_client_version(executable, timeout=5) == 41
    original_stat = os.stat

    def stat(path, *args, **kwargs):
        if os.fspath(path) == executable:
            raise PermissionError("file identity unavailable")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(server.os, "stat", stat)
    command_io.output = b"Android Debug Bridge version 1.0.40\n"
    assert server.adb_client_version(executable, timeout=5) == 40
    assert len(command_io.calls) == 2


@pytest.mark.parametrize(
    "header",
    [b"#!/bin/sh\necho dynamic version\n", b"MZ incomplete", b"unknown format"],
)
def test_wrappers_and_unverified_formats_are_not_cached(executable, command_io, header):
    with open(executable, "wb") as stream:
        stream.write(header)
    assert server.adb_client_version(executable, timeout=5) == 41
    command_io.output = b"Android Debug Bridge version 1.0.40\n"
    assert server.adb_client_version(executable, timeout=5) == 40
    assert len(command_io.calls) == 2


@pytest.mark.parametrize(
    "header",
    [b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xcf\xfa\xed\xfe"],
)
def test_supported_native_headers_reuse_local_version(executable, command_io, header):
    with open(executable, "wb") as stream:
        stream.write(header)
    for _ in range(2):
        assert server.adb_client_version(executable, timeout=5) == 41
    assert command_io.calls == [[executable, "version"]]


@pytest.mark.parametrize(("byteorder", "wide"), UNIVERSAL_FORMATS)
@pytest.mark.parametrize("explicit_default", [False, True])
def test_universal_macho_reuses_local_version_on_default_command_path(
    executable, command_io, byteorder, wide, explicit_default
):
    with open(executable, "wb") as stream:
        stream.write(universal_macho(byteorder, wide))
    options = {"run": manager_io.run_command} if explicit_default else {}
    for _ in range(2):
        assert server.adb_client_version(executable, timeout=5, **options) == 41
    assert command_io.calls == [[executable, "version"]]


@pytest.mark.parametrize(("byteorder", "wide"), UNIVERSAL_FORMATS)
def test_universal_macho_content_change_rereads_version(
    executable, command_io, byteorder, wide
):
    with open(executable, "wb") as stream:
        stream.write(universal_macho(byteorder, wide))
    original = os.stat(executable)
    assert server.adb_client_version(executable, timeout=5) == 41
    with open(executable, "r+b") as stream:
        stream.seek(128 + 32)
        stream.write(b"client40")
    os.utime(executable, ns=(original.st_atime_ns, original.st_mtime_ns))
    command_io.output = b"Android Debug Bridge version 1.0.40\n"
    assert server.adb_client_version(executable, timeout=5) == 40
    assert server.adb_client_version(executable, timeout=5) == 40
    assert command_io.calls == [[executable, "version"], [executable, "version"]]


@pytest.mark.parametrize(("byteorder", "wide"), UNIVERSAL_FORMATS)
@pytest.mark.parametrize(
    "failure",
    [
        "java-class",
        "truncated-header",
        "empty-table",
        "excessive-table",
        "truncated-table",
        "inside-table",
        "short-slice",
        "outside-file",
        "past-file-end",
        "overlapping-slices",
        "invalid-slice-header",
        "misaligned-slice",
        "excessive-alignment",
    ],
)
def test_invalid_universal_macho_is_not_cached(
    executable, command_io, byteorder, wide, failure
):
    image = universal_macho(byteorder, wide)
    width = 8 if wide else 4
    entry_size = 32 if wide else 20
    if failure == "java-class":
        image = b"\xca\xfe\xba\xbe\x00\x00\x00\x3d" + bytes(64)
    elif failure == "truncated-header":
        image = image[:6]
    elif failure == "empty-table":
        image[4:8] = struct.pack(f"{byteorder}I", 0)
    elif failure == "excessive-table":
        image[4:8] = struct.pack(f"{byteorder}I", 17)
    elif failure == "truncated-table":
        image = image[: 8 + 2 * entry_size - 1]
    elif failure == "invalid-slice-header":
        image[256:260] = b"\x7fELF"
    else:
        field, value = {
            "inside-table": (16, 8),
            "short-slice": (16 + width, 28),
            "outside-file": (16, 512),
            "past-file-end": (16 + width, 512),
            "overlapping-slices": (16 + entry_size, 128),
            "misaligned-slice": (16, 129),
            "excessive-alignment": (16 + 2 * width, 64),
        }[failure]
        field_width = 4 if failure == "excessive-alignment" else width
        number_format = "Q" if field_width == 8 else "I"
        image[field : field + field_width] = struct.pack(
            f"{byteorder}{number_format}", value
        )
    with open(executable, "wb") as stream:
        stream.write(image)
    assert server.adb_client_version(executable, timeout=5) == 41
    command_io.output = b"Android Debug Bridge version 1.0.40\n"
    assert server.adb_client_version(executable, timeout=5) == 40
    assert command_io.calls == [[executable, "version"], [executable, "version"]]


@pytest.mark.parametrize("byteorder", [">", "<"])
def test_universal_macho_64_invalid_reserved_field_is_not_cached(
    executable, command_io, byteorder
):
    image = universal_macho(byteorder, True)
    image[36:40] = struct.pack(f"{byteorder}I", 1)
    with open(executable, "wb") as stream:
        stream.write(image)
    for _ in range(2):
        assert server.adb_client_version(executable, timeout=5) == 41
    assert command_io.calls == [[executable, "version"], [executable, "version"]]


def test_unreadable_binary_header_does_not_cache_version(
    monkeypatch, executable, command_io
):
    monkeypatch.setattr(
        server, "open", Mock(side_effect=PermissionError()), raising=False
    )
    for _ in range(2):
        assert server.adb_client_version(executable, timeout=5) == 41
    assert len(command_io.calls) == 2


def test_binary_above_content_limit_is_not_read_or_cached(
    monkeypatch, executable, command_io
):
    with open(executable, "r+b") as stream:
        stream.truncate(32 * 1024 * 1024 + 1)
    read = Mock(side_effect=AssertionError("oversized executable must not be read"))
    monkeypatch.setattr(server, "open", read, raising=False)
    for _ in range(2):
        assert server.adb_client_version(executable, timeout=5) == 41
    read.assert_not_called()
    assert len(command_io.calls) == 2


def test_resolved_path_change_rereads_version(
    monkeypatch, executable, command_io, tmp_path
):
    assert server.adb_client_version(executable, timeout=5) == 41
    other = tmp_path / "other.exe"
    other.write_bytes(NATIVE_HEADER)
    monkeypatch.setattr(server.os.path, "realpath", lambda path, **kwargs: str(other))
    command_io.output = b"Android Debug Bridge version 1.0.40\n"
    assert server.adb_client_version(executable, timeout=5) == 40
    assert len(command_io.calls) == 2


def test_cached_identity_is_checked_again_before_use(
    monkeypatch, executable, command_io
):
    assert server.adb_client_version(executable, timeout=5) == 41
    original_stat = os.stat
    reads = []

    def stat(path, *args, **kwargs):
        if os.fspath(path) == executable:
            reads.append(path)
            if len(reads) == 4:
                with open(executable, "ab") as stream:
                    stream.write(b"changed between cache checks")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(server.os, "stat", stat)
    with pytest.raises(server.SharedADBError):
        server.run_adb([executable, "shell", "getprop"], timeout=5, probe=lambda _: 41)
    assert len(reads) == 4
    assert command_io.calls == [[executable, "version"]]


def test_post_command_stat_failure_blocks_device_command(
    monkeypatch, executable, command_io
):
    original_stat = os.stat

    def stat(path, *args, **kwargs):
        if os.fspath(path) == executable:
            raise PermissionError("identity became unavailable")
        return original_stat(path, *args, **kwargs)

    command_io.after_version = lambda: monkeypatch.setattr(server.os, "stat", stat)
    with pytest.raises(server.SharedADBError):
        server.run_adb([executable, "shell", "getprop"], timeout=5, probe=lambda _: 41)
    assert command_io.calls == [[executable, "version"]]


@pytest.mark.parametrize("path", ["adb", "relative/adb", "./adb"])
def test_path_search_and_relative_executables_are_always_reread(path, command_io):
    assert server.adb_client_version(path, timeout=5) == 41
    command_io.output = b"Android Debug Bridge version 1.0.40\n"
    assert server.adb_client_version(path, timeout=5) == 40
    assert len(command_io.calls) == 2


def test_injected_runner_cannot_read_or_poison_default_cache(executable, command_io):
    assert server.adb_client_version(executable, timeout=5) == 41
    injected = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, b"Android Debug Bridge version 1.0.40\n", b""
        )
    )
    for _ in range(2):
        assert server.adb_client_version(executable, timeout=5, run=injected) == 40
    assert injected.call_count == 2
    assert server.adb_client_version(executable, timeout=5) == 41
    assert len(command_io.calls) == 1


@pytest.mark.parametrize("failure", ["invalid-output", "nonzero", "timeout"])
def test_failed_version_is_not_cached(executable, command_io, failure):
    if failure == "invalid-output":
        command_io.output = b"unknown executable\n"
        expected = server.SharedADBError
    elif failure == "nonzero":
        command_io.returncode = 1
        expected = subprocess.CalledProcessError
    else:
        expected = subprocess.TimeoutExpired

        def timeout():
            raise subprocess.TimeoutExpired([executable, "version"], 5)

        command_io.after_version = timeout
    with pytest.raises(expected):
        server.adb_client_version(executable, timeout=5)
    command_io.output = b"Android Debug Bridge version 1.0.41\n"
    command_io.returncode = 0
    command_io.after_version = None
    assert server.adb_client_version(executable, timeout=5) == 41
    assert server.adb_client_version(executable, timeout=5) == 41
    assert len(command_io.calls) == 2


def test_version_change_during_probe_blocks_device_command(executable, command_io):
    def mutate():
        with open(executable, "ab") as stream:
            stream.write(b" replaced during version")

    command_io.after_version = mutate
    with pytest.raises(server.SharedADBError):
        server.run_adb(
            [executable, "shell", "input", "tap", "10", "20"],
            timeout=5,
            probe=lambda timeout: 41,
        )
    assert command_io.calls == [[executable, "version"]]


def test_cached_guard_rechecks_server_version_and_blocks_input_on_mismatch(
    monkeypatch, executable, command_io
):
    probe = Mock(side_effect=[41, 40])
    monkeypatch.setattr(server, "probe_adb_server", probe)
    assert server.guard_adb(executable, timeout=5) > 0
    with pytest.raises(server.SharedADBError, match="版本不一致"):
        server.run_adb([executable, "shell", "input", "tap", "10", "20"], timeout=5)
    assert probe.call_count == 2
    assert command_io.calls == [[executable, "version"]]


def test_cached_guard_opens_a_new_shared_socket_for_each_command(
    monkeypatch, executable, command_io
):
    connections = [MagicMock(), MagicMock()]
    for connection in connections:
        connection.__enter__.return_value = connection
        connection.recv.side_effect = [b"OKAY", b"0004", b"0029"]
    factory = Mock(side_effect=connections)
    monkeypatch.setattr(server.socket, "socket", factory)
    for _ in range(2):
        server.run_adb([executable, "shell", "getprop"], timeout=5)
    assert factory.call_count == 2
    for connection in connections:
        connection.connect.assert_called_once_with(server.ADB_SERVER_ADDRESS)
        connection.sendall.assert_called_once_with(b"000chost:version")
        connection.__exit__.assert_called_once()
    assert command_io.calls == [
        [executable, "version"],
        [executable, "shell", "getprop"],
        [executable, "shell", "getprop"],
    ]


def test_cached_guard_budget_exhaustion_prevents_shell(executable, command_io):
    assert server.adb_client_version(executable, timeout=5) == 41
    now = [0]

    def probe(timeout):
        now[0] = timeout
        return 41

    with pytest.raises(server.SharedADBError, match="时间预算"):
        server.run_adb(
            [executable, "shell", "getprop"],
            timeout=5,
            probe=probe,
            monotonic=lambda: now[0],
        )
    assert command_io.calls == [[executable, "version"]]


def test_cached_guard_environment_redirect_is_still_rejected(
    monkeypatch, executable, command_io
):
    assert server.adb_client_version(executable, timeout=5) == 41
    probe = Mock(return_value=41)
    monkeypatch.setenv("ADB_SERVER_SOCKET", "tcp:other:5037")
    with pytest.raises(server.SharedADBError, match="重定向"):
        server.run_adb([executable, "shell", "getprop"], timeout=5, probe=probe)
    probe.assert_not_called()
    assert command_io.calls == [[executable, "version"]]


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_cached_result_does_not_bypass_timeout_validation(
    executable, command_io, timeout
):
    assert server.adb_client_version(executable, timeout=5) == 41
    with pytest.raises((ValueError, subprocess.TimeoutExpired)):
        server.adb_client_version(executable, timeout=timeout)
    assert command_io.calls == [[executable, "version"]]


def test_cached_stat_time_consumes_local_version_budget(
    monkeypatch, executable, command_io
):
    assert server.adb_client_version(executable, timeout=5) == 41
    now = [0]
    original_stat = os.stat

    def stat(path, *args, **kwargs):
        if os.fspath(path) == executable:
            now[0] += 3
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(server.os, "stat", stat)
    with pytest.raises(subprocess.TimeoutExpired):
        server.adb_client_version(executable, timeout=5)
    assert command_io.calls == [[executable, "version"]]


def test_uncached_stat_time_cannot_start_command_after_budget(
    monkeypatch, executable, command_io
):
    now = [0]
    original_stat = os.stat

    def stat(path, *args, **kwargs):
        if os.fspath(path) == executable:
            now[0] = 6
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(server.os, "stat", stat)
    with pytest.raises(subprocess.TimeoutExpired):
        server.adb_client_version(executable, timeout=5)
    assert command_io.calls == []


def test_local_version_cache_has_fixed_capacity(executable, command_io, tmp_path):
    assert server.adb_client_version(executable, timeout=5) == 41
    for index in range(16):
        other = tmp_path / f"adb-{index}.exe"
        other.write_bytes(NATIVE_HEADER)
        assert server.adb_client_version(str(other), timeout=5) == 41
    assert server.adb_client_version(executable, timeout=5) == 41
    assert len(command_io.calls) == 18
