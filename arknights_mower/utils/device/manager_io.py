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


class CommandOutputLimit(subprocess.SubprocessError, ValueError):
    """A captured command exceeded its byte budget.

    An output budget is a device-command verdict: the owning session reports it
    and keeps running instead of treating it as an application fault. The
    ValueError base preserves callers that classify command input and output
    problems as value errors.
    """


def _capture_stream(stack):
    writer = stack.enter_context(tempfile.NamedTemporaryFile())
    # Reopening gives the reader its own offset; duplicated handles share one.
    # Windows readers also share delete access with the temporary writer.
    reader = stack.enter_context(
        open(
            writer.name,
            "rb",
            opener=lambda path, flags: os.open(
                path, flags | getattr(os, "O_TEMPORARY", 0)
            ),
        )
    )
    return writer, reader


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
    universal_newlines=None,
    encoding=None,
    errors=None,
    max_output=MAX_COMMAND_OUTPUT,
    **kwargs,
):
    """Wait only for the owned command; capture bounded regular-file output.

    PIPE options select temporary files, never pipe readers. Timeout cleanup
    targets this process only and has a separate one-second reaping allowance.
    ``stdin=PIPE`` receives EOF at once, matching the ``communicate()`` close
    that has no input to write, so ``input`` stays unsupported and rejected.
    ``universal_newlines`` selects text output exactly like ``text``, and that
    selection covers the partial output a timeout carries.
    """
    if not math.isfinite(timeout):
        raise ValueError("设备命令需要有限的超时时间")
    if timeout <= 0:
        raise subprocess.TimeoutExpired(argv, timeout)
    if type(max_output) is not int or max_output <= 0:
        raise ValueError("设备命令输出上限必须为正整数")
    if kwargs.get("shell"):
        raise ValueError("设备命令不能使用主机 shell")
    if "input" in kwargs:
        raise ValueError("设备命令不支持 input，请改用 stdin 或临时文件")
    text = text or bool(universal_newlines)
    decode_text = text or encoding is not None or errors is not None
    codec = encoding or ("utf-8" if sys.flags.utf8_mode else locale.getencoding())

    def decode(data):
        if data is None:
            return None
        return (
            data.decode(codec, errors or "strict")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

    if capture_output:
        if stdout is not None or stderr is not None:
            raise ValueError("capture_output 不能与 stdout/stderr 同时指定")
        stdout = stderr = subprocess.PIPE
    deadline = time.monotonic() + timeout
    with ExitStack() as stack:
        output, output_reader = (
            _capture_stream(stack) if stdout == subprocess.PIPE else (None, None)
        )
        error, error_reader = (
            _capture_stream(stack) if stderr == subprocess.PIPE else (None, None)
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
            if process.stdin is not None:
                # No input is accepted, so the reader sees the same EOF a
                # subprocess.run() call produced by closing its stdin pipe.
                process.stdin.close()
            while True:
                if (
                    sum(os.fstat(stream.fileno()).st_size for stream in streams)
                    > max_output
                ):
                    raise CommandOutputLimit(f"设备命令输出超过 {max_output} 字节上限")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout)
                if process.poll() is not None:
                    break
                try:
                    process.wait(timeout=min(0.02, remaining))
                except subprocess.TimeoutExpired:
                    continue
            stdout_data = _read_output(output_reader, max_output + 1)
            remaining_output = max_output - len(stdout_data or b"")
            if remaining_output < 0:
                raise CommandOutputLimit(f"设备命令输出超过 {max_output} 字节上限")
            stderr_data = _read_output(error_reader, remaining_output + 1)
            if len(stderr_data or b"") > remaining_output:
                raise CommandOutputLimit(f"设备命令输出超过 {max_output} 字节上限")
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
                    output_data = _read_output(output_reader, max_output)
                    stderr_data = _read_output(
                        error_reader, max_output - len(output_data or b"")
                    )
                    if decode_text:
                        # A timeout fragment follows the same binary/text
                        # selection as a returned result. A fragment that cannot
                        # be decoded stays raw, because the timeout remains the
                        # failure this device command reports.
                        try:
                            output_data, stderr_data = (
                                decode(output_data),
                                decode(stderr_data),
                            )
                        except UnicodeDecodeError as exc:
                            failure.add_note(f"设备命令超时输出解码失败：{exc}")
                    failure.output, failure.stderr = output_data, stderr_data
                except OSError as exc:
                    failure.add_note(f"设备命令超时输出读取失败：{exc}")
    if decode_text:
        stdout_data, stderr_data = decode(stdout_data), decode(stderr_data)
    result = subprocess.CompletedProcess(
        argv, process.returncode, stdout_data, stderr_data
    )
    if check:
        result.check_returncode()
    return result


def run_manager_command(argv, *, timeout, **kwargs):
    """Retain the manager's checked, merged binary output and 1 MiB limit.

    The merged channel and the return-code check are this function's own
    contract, so the ``stdout``, ``stderr`` and ``check`` of the shared command
    call shape are satisfied here, while ``creationflags`` and ``env`` reach
    process creation. Any other option is rejected instead of being dropped.
    """
    unsupported = sorted(
        set(kwargs) - {"check", "creationflags", "env", "stdout", "stderr"}
    )
    if unsupported:
        raise ValueError(f"模拟器管理器命令不支持参数：{unsupported}")
    try:
        result = run_command(
            argv,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            max_output=MAX_OUTPUT,
            creationflags=kwargs.get("creationflags", 0),
            env=kwargs.get("env"),
        )
    except CommandOutputLimit as exc:
        # A manager budget overrun is the vendor's own verdict, so its caller
        # needs the repair step rather than the generic capture wording.
        raise CommandOutputLimit(
            f"模拟器管理器输出超过 {MAX_OUTPUT} 字节上限，请检查管理器后重试。"
        ) from exc
    result.stderr = b""
    result.check_returncode()
    return result
