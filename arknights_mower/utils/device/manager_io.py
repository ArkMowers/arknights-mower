"""Bounded output and process lifetime for vendor manager commands."""

import os
import subprocess
import tempfile
import time

MAX_OUTPUT = 1024 * 1024
MAX_INSTANCES = 64


def run_manager_command(argv, *, timeout, **kwargs):
    """Bound output and time without leaving a blocked pipe reader behind.

    The temporary output file is monitored while the owned command runs; only
    the bounded accepted output is read into memory. No background reader can
    outlive this call when a child unexpectedly inherits the output handle.
    """
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryFile() as stream:
        process = subprocess.Popen(
            argv,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=kwargs.get("creationflags", 0),
            env=kwargs.get("env"),
        )
        try:
            while True:
                if os.fstat(stream.fileno()).st_size > MAX_OUTPUT:
                    raise ValueError("模拟器管理器输出超过 1 MiB，请检查管理器后重试。")
                if process.poll() is not None:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout)
                try:
                    process.wait(timeout=min(0.02, remaining))
                except subprocess.TimeoutExpired:
                    continue
            stream.seek(0)
            output = stream.read(MAX_OUTPUT + 1)
            if len(output) > MAX_OUTPUT:
                raise ValueError("模拟器管理器输出超过 1 MiB，请检查管理器后重试。")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=1)
    result = subprocess.CompletedProcess(argv, process.returncode, output, b"")
    result.check_returncode()
    return result
