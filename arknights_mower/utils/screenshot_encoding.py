"""Shared JPEG encoding with an idle-reclaimed auxiliary preview process."""

import mmap
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Event, Lock, RLock, Thread

from arknights_mower.utils.jpeg_codec import MAX_JPEG_BYTES, MAX_RAW_BYTES, frame_shape
from arknights_mower.utils.jpeg_process import WindowsJpegProcess, launch_jpeg_process
from arknights_mower.utils.jpeg_worker import (
    MAPPING_BYTES,
    MAX_ERROR_BYTES,
    REQUEST,
    RESPONSE,
    authenticate,
    receive_exact,
)

ENCODE_TIMEOUT = 5
REAP_TIMEOUT = 0.2
AUXILIARY_IDLE_TIMEOUT = 30


def worker_command(mapping_path, port, token):
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--jpeg-encode-worker"]
    else:
        command = [sys.executable, "-m", "arknights_mower.utils.jpeg_worker"]
    return [*command, str(mapping_path), str(port), token]


class _EncodingSlot:
    def __init__(self, process_factory, command_factory, timeout):
        self._process_factory = process_factory
        self._command_factory = command_factory
        self.timeout = timeout
        self._lock = Lock()
        self._state = RLock()
        self._closed = Event()
        self._process = None
        self._channel = None
        self._listener = None
        self._mapping = None
        self._file = None
        self._mapping_path = None
        self._last_used = 0.0
        self.owner_pid = os.getpid()

    def _remaining(self, deadline):
        if self._closed.is_set() or self.owner_pid != os.getpid():
            raise RuntimeError("截图编码进程已关闭或所有权不匹配")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("截图编码超过执行预算")
        return remaining

    def _start(self, deadline):
        with self._state:
            self._remaining(deadline)
            path = (
                Path(tempfile.gettempdir()) / f"mower-jpeg-{secrets.token_hex(16)}.bin"
            )
            flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_BINARY", 0)
            # Both ends use O_TEMPORARY: Windows deletes on the last kernel handle.
            flags |= getattr(os, "O_TEMPORARY", 0)
            descriptor = os.open(path, flags, 0o600)
            self._mapping_path = path
            self._file = os.fdopen(descriptor, "w+b")
            self._file.truncate(MAPPING_BYTES)
            self._mapping = mmap.mmap(self._file.fileno(), MAPPING_BYTES)
            self._listener = socket.socket()
            self._listener.bind(("127.0.0.1", 0))
            self._listener.listen(1)
            self._listener.settimeout(self._remaining(deadline))
            port = self._listener.getsockname()[1]
            token = secrets.token_hex(32)
            env = os.environ.copy()
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            self._process = self._process_factory(
                self._command_factory(path, port, token),
                cwd=Path(__file__).resolve().parents[2],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            listener = self._listener
        while True:
            listener.settimeout(min(0.05, self._remaining(deadline)))
            try:
                channel, _ = listener.accept()
                break
            except socket.timeout:
                if self._process.poll() is not None:
                    raise RuntimeError("截图编码工作进程在启动时退出")
        with self._state:
            self._channel = channel
            channel.settimeout(self._remaining(deadline))
        authenticate(channel, token, deadline=deadline)
        with self._state:
            if isinstance(self._process, WindowsJpegProcess):
                self._process.capture_members()
            listener.close()
            self._listener = None

    def _dispose(self, deadline):
        # Callers hold _state; retaining a live child prevents a replacement leak.
        for name in ("_listener", "_channel"):
            channel = getattr(self, name)
            if channel is not None:
                try:
                    channel.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                channel.close()
                setattr(self, name, None)
        process = self._process
        if process is not None:
            if isinstance(process, WindowsJpegProcess) or process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError("截图编码工作进程未在退出预算内结束") from exc
            self._process = None
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None
        if self._file is not None:
            self._file.close()
            self._file = None
        if self._mapping_path is not None:
            if sys.platform != "win32":
                self._mapping_path.unlink(missing_ok=True)
            self._mapping_path = None

    def encode(self, rgb, *, deadline=None, wait=True):
        started = time.monotonic()
        expires = started + self.timeout
        if deadline is not None:
            expires = min(expires, deadline)
        work_deadline = expires - min(REAP_TIMEOUT, self.timeout / 5)
        remaining = self._remaining(work_deadline)
        acquired = (
            self._lock.acquire(timeout=remaining)
            if wait
            else self._lock.acquire(blocking=False)
        )
        if not acquired:
            if wait:
                raise TimeoutError("截图编码前一帧超过执行预算")
            return None
        try:
            width, height, channels = frame_shape(rgb)
            if self._process is None:
                self._start(work_deadline)
            elif self._process.poll() is not None:
                with self._state:
                    self._dispose(min(work_deadline, time.monotonic() + REAP_TIMEOUT))
                self._start(work_deadline)
            elif self._channel is None:
                raise RuntimeError("旧截图编码工作进程尚未退出")
            with self._state:
                self._remaining(work_deadline)
                shared, channel = self._mapping, self._channel
                shared.seek(0)
                if rgb.flags.c_contiguous:
                    shared.write(memoryview(rgb).cast("B"))
                else:
                    shared.write(rgb.tobytes())
            channel.settimeout(self._remaining(work_deadline))
            channel.sendall(REQUEST.pack(width, height, channels))
            status, size = RESPONSE.unpack(
                receive_exact(channel, RESPONSE.size, deadline=work_deadline)
            )
            if status:
                if size > MAX_ERROR_BYTES:
                    raise ValueError("截图编码错误响应超过上限")
                raise RuntimeError(
                    receive_exact(channel, size, deadline=work_deadline).decode(
                        "utf-8", errors="replace"
                    )
                )
            if not 0 < size <= MAX_JPEG_BYTES:
                raise ValueError("JPEG 编码结果为空或超过单帧上限")
            with self._state:
                self._remaining(work_deadline)
                data = shared[MAX_RAW_BYTES : MAX_RAW_BYTES + size]
            if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
                raise ValueError("截图编码工作进程返回无效 JPEG")
            return data
        except Exception as exc:
            with self._state:
                try:
                    self._dispose(expires)
                except Exception as cleanup_error:
                    exc.add_note(f"截图编码资源清理失败：{cleanup_error}")
            raise
        finally:
            self._last_used = time.monotonic()
            self._lock.release()

    def reap_idle(self, idle_timeout):
        if (
            self.owner_pid != os.getpid()
            or self._closed.is_set()
            or not self._lock.acquire(blocking=False)
        ):
            return
        try:
            with self._state:
                if (
                    self._process is not None
                    and time.monotonic() - self._last_used >= idle_timeout
                ):
                    try:
                        self._dispose(time.monotonic() + REAP_TIMEOUT)
                    finally:
                        # Failed cleanup retains ownership and retries after cooldown.
                        self._last_used = time.monotonic()
        finally:
            self._lock.release()

    def close(self, deadline):
        if self.owner_pid != os.getpid():
            return
        self._closed.set()
        for channel in (self._listener, self._channel):
            if channel is not None:
                try:
                    channel.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        if not self._state.acquire(timeout=max(0, deadline - time.monotonic())):
            raise TimeoutError("截图编码资源未在退出预算内释放")
        try:
            self._dispose(deadline)
        finally:
            self._state.release()


class ScreenshotEncoding:
    def __init__(
        self,
        *,
        timeout=ENCODE_TIMEOUT,
        auxiliary_idle_timeout=AUXILIARY_IDLE_TIMEOUT,
        process_factory=launch_jpeg_process,
        command_factory=worker_command,
    ):
        if timeout <= 0 or auxiliary_idle_timeout <= 0:
            raise ValueError("截图编码和空闲回收预算必须大于 0")
        self._slots = [
            _EncodingSlot(process_factory, command_factory, timeout) for _ in range(2)
        ]
        self._auxiliary_idle_timeout = auxiliary_idle_timeout
        self._closing = Event()
        self._reaper_lock = Lock()
        self._reaper = None

    def encode(self, rgb, *, preview=False, deadline=None):
        primary = self._slots[0]
        expires = time.monotonic() + primary.timeout
        deadline = expires if deadline is None else min(expires, deadline)
        data = primary.encode(rgb, deadline=deadline, wait=not preview)
        if data is not None:
            return data
        # A busy history frame never holds newer previews behind its deadline.
        with self._reaper_lock:
            if self._closing.is_set():
                raise RuntimeError("截图编码进程已关闭")
            if self._reaper is None:
                reaper = Thread(
                    target=self._reap_auxiliary, name="jpeg-idle-reaper", daemon=True
                )
                reaper.start()
                self._reaper = reaper
        return self._slots[1].encode(rgb, deadline=deadline)

    def _reap_auxiliary(self):
        interval = min(1.0, self._auxiliary_idle_timeout)
        while not self._closing.wait(interval):
            try:
                self._slots[1].reap_idle(self._auxiliary_idle_timeout)
            except Exception:
                # Logging imports this module through ScreenshotStore.
                from arknights_mower.utils.log import logger

                logger.exception("空闲截图编码进程清理失败，保留所有权等待重试")

    def remaining_workers(self):
        processes = [
            slot._process for slot in self._slots if slot.owner_pid == os.getpid()
        ]
        return [
            process.pid
            for process in processes
            if process is not None and process.poll() is None
        ]

    def close(self, *, deadline=None):
        if self._slots[0].owner_pid != os.getpid():
            return
        if deadline is None:
            deadline = time.monotonic() + 2 * REAP_TIMEOUT
        self._closing.set()
        errors = []
        for slot in self._slots:
            try:
                slot.close(deadline)
            except Exception as exc:
                errors.append(exc)
        if self._reaper is not None:
            self._reaper.join(max(0, deadline - time.monotonic()))
            if self._reaper.is_alive():
                errors.append(TimeoutError("截图编码空闲回收线程未在退出预算内结束"))
        if errors:
            for error in errors[1:]:
                errors[0].add_note(str(error))
            raise errors[0]
