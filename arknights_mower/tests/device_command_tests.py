"""Offline process fixtures exercise inherited stdout/stderr ownership."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils.device import manager_io

FIXTURE = Path(__file__).parent / "fixtures" / "inherited_command.py"


def wait_for(path, timeout, *, exists=True):
    deadline = time.monotonic() + timeout
    while path.exists() != exists and time.monotonic() < deadline:
        time.sleep(0.01)
    return path.exists() == exists


@pytest.mark.parametrize(
    ("adapter", "outcome"),
    [
        (adapter, outcome)
        for adapter in ("preflight", "adb")
        for outcome in ("timeout", "success", "failure")
    ]
    + [
        (adapter, "timeout")
        for adapter in ("guard_version", "shared_start", "mumu_input")
    ],
)
def test_inherited_output_does_not_extend_command_deadline(tmp_path, adapter, outcome):
    process = subprocess.Popen(
        [sys.executable, "-B", str(FIXTURE), "probe", str(tmp_path), outcome, adapter],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        assert wait_for(tmp_path / "probe.ready", 10), "probe import failed"
        (tmp_path / "go").touch()
        completed = wait_for(tmp_path / "result.json", 5)
        assert wait_for(tmp_path / "descendant.ready", 3)
        assert not (tmp_path / "descendant.stopped").exists()
    finally:
        (tmp_path / "release").touch()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
        assert wait_for(tmp_path / "descendant.stopped", 5)
    assert completed, "a one-second command still waits for inherited output"
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["elapsed"] < 2
    assert result["reaped"]
    assert result["streams_closed"]
    if adapter == "mumu_input":
        assert not result["worker_started"]
    if outcome == "timeout":
        assert result["error"] == "TimeoutExpired"
    elif outcome == "failure":
        assert result["error"] == "CalledProcessError"
    else:
        assert result["error"] is None
        assert result["stdout"] == "command stdout\n"


def run_python(script, **options):
    return manager_io.run_command(
        [sys.executable, "-B", "-c", script],
        timeout=options.pop("timeout", 3),
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        **options,
    )


def record_processes(monkeypatch):
    processes, streams = [], []
    original = subprocess.Popen

    def open_reader(*args, **kwargs):
        stream = open(*args, **kwargs)
        streams.append(stream)
        return stream

    def spawn(*args, **kwargs):
        streams.extend(
            stream
            for stream in (kwargs["stdout"], kwargs["stderr"])
            if hasattr(stream, "fileno")
        )
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(manager_io.subprocess, "Popen", spawn)
    monkeypatch.setattr(manager_io, "open", open_reader, raising=False)
    return processes, streams


@pytest.mark.parametrize("outcome", ["success", "failure", "timeout"])
@pytest.mark.parametrize("stderr", [subprocess.PIPE, subprocess.STDOUT])
def test_inherited_writes_during_collection_preserve_existing_output(
    monkeypatch, tmp_path, outcome, stderr
):
    processes, streams = record_processes(monkeypatch)
    original_read = manager_io._read_output
    channels = iter(("stdout", "stderr"))

    def read_with_inherited_write(stream, limit):
        if stream is None:
            return original_read(stream, limit)
        channel = next(channels)

        def seek(offset):
            position = stream.seek(offset)
            writing = (
                ("stdout", "stderr") if stderr == subprocess.STDOUT else (channel,)
            )
            for name in writing:
                (tmp_path / f"write.{name}").touch()
                assert wait_for(tmp_path / f"wrote.{name}", 3)
            return position

        return original_read(SimpleNamespace(seek=seek, read=stream.read), limit)

    monkeypatch.setattr(manager_io, "_read_output", read_with_inherited_write)
    started = time.monotonic()
    try:
        try:
            result = manager_io.run_command(
                [
                    sys.executable,
                    "-B",
                    str(FIXTURE),
                    "writer_command",
                    str(tmp_path),
                    outcome,
                ],
                stdout=subprocess.PIPE,
                stderr=stderr,
                check=True,
                timeout=0.5 if outcome == "timeout" else 3,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.TimeoutExpired as exc:
            assert outcome == "timeout"
            result = exc
        except subprocess.CalledProcessError as exc:
            assert outcome == "failure"
            assert exc.returncode == 7
            result = exc
        else:
            assert outcome == "success"
            assert result.returncode == 0
        assert time.monotonic() - started < 2
        assert not (tmp_path / "descendant.stopped").exists()
        if stderr == subprocess.STDOUT:
            assert result.stdout == (
                b"command stdout\ncommand stderr\n"
                b"descendant stdout\ndescendant stderr\n"
            )
            assert result.stderr is None
        else:
            assert result.stdout == b"command stdout\ndescendant stdout\n"
            assert result.stderr == b"command stderr\ndescendant stderr\n"
        assert all(process.poll() is not None for process in processes)
        assert all(stream.closed for stream in streams)
    finally:
        (tmp_path / "release").touch()
        assert wait_for(tmp_path / "descendant.stopped", 3)
    assert all(wait_for(Path(stream.name), 3, exists=False) for stream in streams)


def test_captured_binary_streams_preserve_bytes_and_close(monkeypatch):
    processes, streams = record_processes(monkeypatch)
    result = run_python(
        "import os; os.write(1, b'\\x00\\xff\\r\\n'); os.write(2, b'diagnostic\\r\\n')",
        capture_output=True,
        check=True,
    )
    assert result.stdout == b"\x00\xff\r\n"
    assert result.stderr == b"diagnostic\r\n"
    assert all(process.poll() is not None for process in processes)
    assert all(stream.closed for stream in streams)


def test_text_decoding_keeps_stderr_separate_and_normalizes_newlines():
    result = run_python(
        "import os; os.write(1, b'a\\r\\nb\\rc\\n\\xff'); os.write(2, b'error\\r\\n')",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.stdout == "a\nb\nc\n\ufffd"
    assert result.stderr == "error\n"


def test_encoding_alone_enables_text_output():
    result = run_python("print('version')", stdout=subprocess.PIPE, encoding="ascii")
    assert result.stdout == "version\n"
    assert result.stderr is None


def test_default_text_decoding_honors_python_utf8_mode(monkeypatch):
    monkeypatch.setattr(
        manager_io,
        "sys",
        SimpleNamespace(flags=SimpleNamespace(utf8_mode=1)),
        raising=False,
    )
    monkeypatch.setattr(manager_io.locale, "getencoding", lambda: "cp1252")
    result = run_python(
        "import os; os.write(1, b'\\xe4\\xb8\\xad')", capture_output=True, text=True
    )
    assert result.stdout == "中"


def test_nonzero_returncode_preserves_separate_error_output():
    with pytest.raises(subprocess.CalledProcessError) as raised:
        run_python(
            "import os; os.write(1, b'output'); os.write(2, b'error'); raise SystemExit(7)",
            capture_output=True,
            check=True,
        )
    assert raised.value.returncode == 7
    assert raised.value.output == b"output"
    assert raised.value.stderr == b"error"


def test_optional_check_and_merged_output_retain_subprocess_semantics():
    result = run_python(
        "import os; os.write(1, b'output'); os.write(2, b'error'); raise SystemExit(7)",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert result.returncode == 7
    assert result.stdout == b"outputerror"
    assert result.stderr is None


def test_binary_capture_above_manager_limit_is_accepted():
    result = run_python(
        "import os; os.write(1, b'x' * (2 * 1024 * 1024))",
        capture_output=True,
        check=True,
    )
    assert len(result.stdout) == 2 * 1024 * 1024


@pytest.mark.parametrize("stderr", [subprocess.PIPE, subprocess.STDOUT])
def test_combined_output_limit_reaps_running_command_and_closes_streams(
    monkeypatch, stderr
):
    processes, streams = record_processes(monkeypatch)
    with pytest.raises(manager_io.CommandOutputLimit, match="1024") as raised:
        run_python(
            "import os, time; os.write(1, b'x' * 600); os.write(2, b'y' * 500); time.sleep(15)",
            stdout=subprocess.PIPE,
            stderr=stderr,
            max_output=1024,
        )
    assert isinstance(raised.value, subprocess.SubprocessError)
    assert isinstance(raised.value, ValueError)
    assert all(process.poll() is not None for process in processes)
    assert all(stream.closed for stream in streams)


def test_output_limit_is_a_device_verdict_not_an_application_fault():
    from arknights_mower.utils.device.application import RECOVERABLE_DEVICE_ERRORS

    error = manager_io.CommandOutputLimit("设备命令输出超过 1 字节上限")
    assert isinstance(error, RECOVERABLE_DEVICE_ERRORS)


def test_manager_output_limit_states_the_limit_and_the_repair_step(monkeypatch):
    monkeypatch.setattr(manager_io, "MAX_OUTPUT", 4096)
    with pytest.raises(manager_io.CommandOutputLimit) as raised:
        manager_io.run_manager_command(
            [
                sys.executable,
                "-B",
                "-c",
                "import os, time; os.write(1, b'x' * 8192); time.sleep(15)",
            ],
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    assert "4096" in str(raised.value)
    assert "请检查管理器后重试" in str(raised.value)
    assert isinstance(raised.value, subprocess.SubprocessError)


def test_manager_runner_satisfies_the_shared_capture_shape():
    result = manager_io.run_manager_command(
        [
            sys.executable,
            "-B",
            "-c",
            "import os; os.write(1, b'out'); os.write(2, b'err')",
        ],
        timeout=3,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.stdout == b"outerr"
    assert result.stderr == b""


@pytest.mark.parametrize("option", [{"text": True}, {"max_output": 1}, {"shell": True}])
def test_manager_runner_rejects_options_it_cannot_honor(monkeypatch, option):
    spawn = Mock()
    monkeypatch.setattr(manager_io.subprocess, "Popen", spawn)
    with pytest.raises(ValueError, match="不支持参数"):
        manager_io.run_manager_command(["manager", "info"], timeout=1, **option)
    spawn.assert_not_called()


def test_stdin_pipe_sees_eof_like_subprocess_run_without_input():
    argv = [
        sys.executable,
        "-B",
        "-c",
        "import sys; print('got', len(sys.stdin.read()))",
    ]
    options = dict(
        stdin=subprocess.PIPE,
        capture_output=True,
        text=True,
        timeout=3,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    reference = subprocess.run(argv, check=True, **options)
    result = manager_io.run_command(argv, check=True, **options)
    assert reference.stdout == "got 0\n"
    assert result.stdout == reference.stdout
    assert result.stderr == reference.stderr == ""


def test_input_argument_is_rejected_before_process_creation(monkeypatch):
    spawn = Mock()
    monkeypatch.setattr(manager_io.subprocess, "Popen", spawn)
    with pytest.raises(ValueError, match="input"):
        manager_io.run_command(["manager", "info"], timeout=1, input=b"payload")
    spawn.assert_not_called()


def test_universal_newlines_alias_selects_text_output():
    result = run_python(
        "import os; os.write(1, b'text\\r\\n')",
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )
    assert result.stdout == "text\n"


@pytest.mark.parametrize("text", [False, True])
def test_timeout_partial_output_follows_the_text_selection(monkeypatch, text):
    processes, streams = record_processes(monkeypatch)
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        run_python(
            "import os, time; os.write(1, b'output\\r\\n'); os.write(2, b'error\\r\\n'); time.sleep(15)",
            timeout=0.5,
            capture_output=True,
            text=text,
        )
    assert raised.value.timeout == 0.5
    if text:
        assert raised.value.output == "output\n"
        assert raised.value.stderr == "error\n"
    else:
        assert raised.value.output == b"output\r\n"
        assert raised.value.stderr == b"error\r\n"
    assert all(process.poll() is not None for process in processes)
    assert all(stream.closed for stream in streams)


def test_undecodable_timeout_fragment_keeps_the_timeout_as_the_failure():
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        run_python(
            "import os, time; os.write(1, b'\\xff'); time.sleep(15)",
            timeout=0.5,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    assert raised.value.output == b"\xff"
    assert raised.value.stderr == b""
    assert any("解码失败" in note for note in raised.value.__notes__)


def test_launch_failure_closes_every_temporary_stream(monkeypatch, tmp_path):
    streams = []
    original = manager_io.tempfile.NamedTemporaryFile

    def open_stream():
        stream = original()
        streams.append(stream)
        return stream

    monkeypatch.setattr(manager_io.tempfile, "NamedTemporaryFile", open_stream)
    with pytest.raises(OSError):
        manager_io.run_command(
            [str(tmp_path / "missing-command")],
            timeout=1,
            capture_output=True,
        )
    assert len(streams) == 2
    assert all(stream.closed for stream in streams)
    assert all(not Path(stream.name).exists() for stream in streams)


def test_reader_open_failure_closes_output_before_process_creation(monkeypatch):
    streams = []
    original = manager_io.tempfile.NamedTemporaryFile

    def open_stream():
        stream = original()
        streams.append(stream)
        return stream

    spawn = Mock()
    monkeypatch.setattr(manager_io.tempfile, "NamedTemporaryFile", open_stream)
    monkeypatch.setattr(
        manager_io,
        "open",
        Mock(side_effect=OSError("reader unavailable")),
        raising=False,
    )
    monkeypatch.setattr(manager_io.subprocess, "Popen", spawn)
    with pytest.raises(OSError, match="reader unavailable"):
        manager_io.run_command(["manager", "info"], timeout=1, capture_output=True)
    spawn.assert_not_called()
    assert len(streams) == 1
    assert streams[0].closed
    assert not Path(streams[0].name).exists()


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_budget_starts_no_process(monkeypatch, timeout):
    spawn = Mock()
    monkeypatch.setattr(manager_io.subprocess, "Popen", spawn)
    with pytest.raises((ValueError, subprocess.TimeoutExpired)):
        manager_io.run_command(["manager", "info"], timeout=timeout)
    spawn.assert_not_called()


def test_cleanup_failure_preserves_primary_timeout_and_reports_cleanup(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    process.wait.side_effect = subprocess.TimeoutExpired("manager", 1)
    monkeypatch.setattr(manager_io.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(manager_io.time, "monotonic", Mock(side_effect=[0, 2]))
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        manager_io.run_command(["manager", "info"], timeout=1, capture_output=True)
    assert raised.value.timeout == 1
    assert raised.value.cleanup_failed
    assert raised.value.__notes__
    process.kill.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=1)
