"""One owned process and shared frame slot for vendor capture adapters."""

import ctypes
import multiprocessing
import os
import time
from threading import Event, Lock, RLock

import numpy as np

from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.owned import close_process

CAPTURE_TIMEOUT = 10
JOIN_TIMEOUT = 1


class NativeCaptureSession:
    """Reuse native capture state; the caller alone may rebuild after failure."""

    def __init__(self, worker, args, *, label, error_type=RuntimeError):
        self._worker = worker
        self._args = args
        self._label = label
        self._error_type = error_type
        self._process = None
        self._channel = None
        self._buffer = None
        self._failure = None
        self._closed = False
        self._interrupted = Event()
        self._lock = Lock()
        self.owner_pid = os.getpid()
        self._state_lock = RLock()

    def _start(self):
        if self._closed or self.owner_pid != os.getpid():
            raise self._error_type(f"{self._label} 截图会话已关闭或所有权不匹配")
        context = multiprocessing.get_context("spawn")
        self._buffer = context.RawArray(ctypes.c_ubyte, 1920 * 1080 * 3)
        self._channel, child = context.Pipe()
        self._process = context.Process(
            target=self._worker,
            args=(*self._args, self._buffer, child),
            daemon=True,
        )
        try:
            self._process.start()
        finally:
            child.close()

    def _remaining(self, deadline):
        if self._interrupted.is_set():
            raise self._error_type(f"{self._label} 截图会话已关闭或中断")
        remaining = io_timeout(min(CAPTURE_TIMEOUT, deadline - time.monotonic()))
        if remaining <= 0:
            raise TimeoutError(f"{self._label} 未在限定时间返回截图")
        return remaining

    def capture_frame(self) -> np.ndarray:
        deadline = time.monotonic() + io_timeout(CAPTURE_TIMEOUT)
        if not self._lock.acquire(timeout=self._remaining(deadline)):
            raise TimeoutError(f"{self._label} 未在限定时间完成前一张截图")
        try:
            if self._closed:
                raise self._error_type(f"{self._label} 截图会话已关闭")
            if self._failure is not None:
                raise self._failure
            try:
                with self._state_lock:
                    if self._closed or self.owner_pid != os.getpid():
                        raise self._error_type(
                            f"{self._label} 截图会话已关闭或所有权不匹配"
                        )
                    if self._process is None:
                        self._start()
                self._remaining(deadline)
                self._channel.send("capture")
                while not self._channel.poll(min(0.05, self._remaining(deadline))):
                    pass
                status, message, code, size = self._channel.recv()
                if status != "ok":
                    failure = self._error_type(message)
                    failure.return_code = code
                    failure.actual_size = size
                    raise failure
                self._remaining(deadline)
                return (
                    np.frombuffer(self._buffer, np.uint8).reshape(1080, 1920, 3).copy()
                )
            except Exception as exc:
                if isinstance(exc, (EOFError, BrokenPipeError)):
                    self._failure = self._error_type(
                        f"{self._label} 截图工作进程意外退出"
                    )
                    raise self._failure from exc
                self._failure = exc
                raise
        finally:
            self._lock.release()

    def close(self):
        """Stop only this worker, escalating only after bounded joins."""
        with self._state_lock:
            if self._closed or self.owner_pid != os.getpid():
                return
            self._closed = True
            self._interrupted.set()
            process, self._process = self._process, None
            channel, self._channel = self._channel, None
        errors = []
        # EOF wakes an idle worker. Never write another message to a pipe whose
        # reader may be stuck in a native call; even a close message can block.
        try:
            if channel is not None:
                channel.close()
        except Exception as exc:
            errors.append(exc)
        try:
            close_process(
                process,
                self.owner_pid,
                timeout=JOIN_TIMEOUT,
                error_type=self._error_type,
            )
        except Exception as exc:
            errors.append(exc)
        if errors:
            for error in errors[1:]:
                errors[0].add_note(str(error))
            raise errors[0]

    def interrupt(self):
        if self.owner_pid == os.getpid():
            self._interrupted.set()
