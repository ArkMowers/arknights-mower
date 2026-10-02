"""Bounded device command output without inherited pipe EOF waits."""

import locale
import math
import os
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack

MAX_OUTPUT = 1024 * 1024
MAX_INSTANCES = 64
MAX_COMMAND_OUTPUT = 32 * 1024 * 1024
COMMAND_CLEANUP_TIMEOUT = 1


def _read_output(stream, limit):
    if stream is None:
        return None
    stream.seek(0)
    return stream.read(limit)


def run_command(
    argv,
    *,
    timeout,
    stdout=None,
    stderr=None,
    capture_output=False,
    check=False,
    text=False,
    encoding=None,
    errors=None,
    max_output=MAX_COMMAND_OUTPUT,
    **kwargs,
):
    """Wait only for the owned command; capture bounded regular-file output.

    PIPE options select temporary files, never pipe readers. Timeout cleanup
    targets this process only and has a separate one-second reaping allowance.
    """
    if not math.isfinite(timeout):
        raise ValueError("设备命令需要有限的超时时间")
    if timeout <= 0:
        raise subprocess.TimeoutExpired(argv, timeout)
    if type(max_output) is not int or max_output <= 0:
        raise ValueError("设备命令输出上限必须为正整数")
    if kwargs.get("shell"):
        raise ValueError("设备命令不能使用主机 shell")
    if capture_output:
        if stdout is not None or stderr is not None:
            raise ValueError("capture_output 不能与 stdout/stderr 同时指定")
        stdout = stderr = subprocess.PIPE
    deadline = time.monotonic() + timeout
    with ExitStack() as stack:
        output = (
            stack.enter_context(tempfile.TemporaryFile())
            if stdout == subprocess.PIPE
            else None
        )
        error = (
            stack.enter_context(tempfile.TemporaryFile())
            if stderr == subprocess.PIPE
            else None
        )
        streams = [stream for stream in (output, error) if stream is not None]
        process = subprocess.Popen(
            argv,
            stdout=output if output is not None else stdout,
            stderr=error if error is not None else stderr,
            **kwargs,
        )
        failure = None
        try:
            while True:
                if (
                    sum(os.fstat(stream.fileno()).st_size for stream in streams)
                    > max_output
                ):
                    raise ValueError(f"设备命令输出超过 {max_output} 字节上限")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout)
                if process.poll() is not None:
                    break
                try:
                    process.wait(timeout=min(0.02, remaining))
                except subprocess.TimeoutExpired:
                    continue
            stdout_data = _read_output(output, max_output + 1)
            remaining_output = max_output - len(stdout_data or b"")
            if remaining_output < 0:
                raise ValueError(f"设备命令输出超过 {max_output} 字节上限")
            stderr_data = _read_output(error, remaining_output + 1)
            if len(stderr_data or b"") > remaining_output:
                raise ValueError(f"设备命令输出超过 {max_output} 字节上限")
        except BaseException as exc:
            failure = exc
            raise
        finally:
            if process.poll() is None:
                try:
                    process.kill()
                    process.wait(timeout=COMMAND_CLEANUP_TIMEOUT)
                except Exception as exc:
                    if failure is None:
                        raise
                    failure.add_note(f"设备命令进程清理失败：{exc}")
                    failure.cleanup_failed = True
            if isinstance(failure, subprocess.TimeoutExpired):
                try:
                    failure.output = _read_output(output, max_output)
                    failure.stderr = _read_output(
                        error, max_output - len(failure.output or b"")
                    )
                except OSError as exc:
                    failure.add_note(f"设备命令超时输出读取失败：{exc}")
    if text or encoding is not None or errors is not None:
        codec = encoding or ("utf-8" if sys.flags.utf8_mode else locale.getencoding())

        def decode(data):
            if data is None:
                return None
            return (
                data.decode(codec, errors or "strict")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
            )

        stdout_data, stderr_data = decode(stdout_data), decode(stderr_data)
    result = subprocess.CompletedProcess(
        argv, process.returncode, stdout_data, stderr_data
    )
    if check:
        result.check_returncode()
    return result


def run_manager_command(argv, *, timeout, **kwargs):
    """Retain the manager's checked, merged binary output and 1 MiB limit."""
    result = run_command(
        argv,
        timeout=timeout,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        max_output=MAX_OUTPUT,
        creationflags=kwargs.get("creationflags", 0),
        env=kwargs.get("env"),
    )
    result.stderr = b""
    result.check_returncode()
    return result
