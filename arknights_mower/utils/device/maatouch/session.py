from __future__ import annotations

import os
import subprocess
import time
from threading import Event, RLock, Thread

from arknights_mower import __system__
from arknights_mower.utils.device.adb_client.core import Client as ADBClient
from arknights_mower.utils.device.adb_client.server import guard_adb
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.manager_io import run_command
from arknights_mower.utils.log import logger


class MaaTouchCleanupError(RuntimeError):
    cleanup_failed = True


class Session:
    def __init__(self, client: ADBClient, *, defer_start: bool = False) -> None:
        self.client = client
        self.owner_pid = os.getpid()
        self.process = None
        self._closed = False
        self._lock = RLock()
        self._closed_event = Event()
        self._io_thread = None
        self.input_started = False
        if not defer_start:
            self.__enter__()

    def start(self) -> None:
        if self._closed_event.is_set() or self.owner_pid != os.getpid():
            raise ConnectionError("MaaTouch 会话已关闭")
        if self.process is not None:
            return
        client = self.client
        deadline = time.monotonic() + io_timeout(10)
        guard_adb(client.adb_bin, timeout=io_timeout(10), run=run_command)
        with self._lock:
            if self._closed_event.is_set() or self.owner_pid != os.getpid():
                raise ConnectionError("MaaTouch 会话已关闭")
            if time.monotonic() >= deadline:
                raise TimeoutError("MaaTouch 初始化超时")
            self.process = subprocess.Popen(
                [
                    client.adb_bin,
                    "-s",
                    client.device_id,
                    "shell",
                    "CLASSPATH=/data/local/tmp/maatouch",
                    "app_process",
                    "/",
                    "com.shxyke.MaaTouch.App",
                ],
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
                if __system__ == "windows"
                else 0,
            )

        def read_header():
            # Limit each line as well as the total handshake time.
            return [self.process.stdout.readline(1024).split() for _ in range(2)]

        header, identity = self._io(read_header, deadline - time.monotonic())
        if len(header) != 5 or header[0] != "^":
            raise ConnectionError("MaaTouch 触控能力响应无效")
        if len(identity) != 2 or identity[0] != "$":
            raise ConnectionError("MaaTouch 进程响应无效")
        _, max_contacts, max_x, max_y, max_pressure = header
        if any(not value.isdecimal() or int(value) <= 0 for value in header[1:]):
            raise ConnectionError("MaaTouch 触控能力响应无效")
        if not identity[1].isdecimal() or int(identity[1]) <= 0:
            raise ConnectionError("MaaTouch 进程响应无效")
        self.max_contacts = max_contacts
        self.max_x = max_x
        self.max_y = max_y
        self.max_pressure = max_pressure

        self.pid = identity[1]

        logger.debug(f"maatouch running, pid: {self.pid}")
        logger.debug(
            f"max_contact: {max_contacts}; max_x: {max_x}; max_y: {max_y}; max_pressure: {max_pressure}"
        )

    def _io(self, operation, timeout=10, *, input_operation=False):
        """Bound pipe operations on Windows too; closing reaps their process."""
        done = Event()
        result = []
        errors = []
        deadline = time.monotonic() + io_timeout(max(0, timeout))

        def run():
            try:
                result.append(operation())
            except BaseException as exc:
                errors.append(exc)
            finally:
                done.set()

        with self._lock:
            if self._closed_event.is_set() or self.owner_pid != os.getpid():
                raise ConnectionError("MaaTouch 会话已关闭")
            if self.process.poll() is not None:
                raise ConnectionError("MaaTouch 进程提前退出")
            if time.monotonic() >= deadline:
                raise TimeoutError("MaaTouch I/O 超时")
            self._io_thread = Thread(target=run, daemon=True, name="maatouch-io")
            if input_operation:
                self.input_started = True
            self._io_thread.start()
        while not done.is_set():
            remaining = min(deadline - time.monotonic(), io_timeout(10))
            if remaining <= 0:
                raise TimeoutError("MaaTouch I/O 超时")
            if self._closed_event.wait(min(0.01, remaining)):
                raise ConnectionError("MaaTouch 会话已关闭")
        if self._closed:
            raise ConnectionError("MaaTouch 会话已关闭")
        if time.monotonic() >= deadline:
            raise TimeoutError("MaaTouch I/O 超时")
        io_timeout(0)
        if errors:
            raise errors[0]
        if self.process.poll() is not None:
            raise ConnectionError("MaaTouch 进程提前退出，发送结果无法确认")
        return result[0]

    def __enter__(self) -> Session:
        try:
            self.start()
        except BaseException as exc:
            self.__exit__(type(exc), exc, exc.__traceback__)
            raise
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        try:
            self.close()
        except Exception as cleanup_error:
            if exc_value is None:
                raise
            exc_value.cleanup_failed = True
            exc_value.add_note(f"MaaTouch 清理失败：{cleanup_error}")

    def close(self) -> None:
        with self._lock:
            if self._closed or self.owner_pid != os.getpid():
                return
            self._closed = True
            self._closed_event.set()
            process = self.process
            worker = self._io_thread
        if process is None:
            return
        failures = []
        # MaaTouch dereferences null on stdin EOF. Stop the owned process before
        # closing its pipes, also allowing blocked I/O to release the stream lock.
        for attempt, action in enumerate((process.terminate, process.kill)):
            returncode = process.poll()
            if returncode is not None:
                if attempt == 0 and returncode != 0:
                    failures.append(
                        RuntimeError(f"MaaTouch 进程异常退出：{returncode}")
                    )
                break
            try:
                action()
            except Exception as exc:
                failures.append(exc)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            except Exception as exc:
                failures.append(exc)
        if worker is not None:
            worker.join(timeout=1)
        if process.poll() is None:
            failures.append(RuntimeError("MaaTouch 进程在有限等待后仍未退出"))
        elif worker is not None and worker.is_alive():
            failures.append(RuntimeError("MaaTouch I/O 在进程退出后仍未结束"))
        else:
            for pipe in (process.stdin, process.stdout):
                if pipe is not None and not pipe.closed:
                    try:
                        pipe.close()
                    except Exception as exc:
                        failures.append(exc)
        if failures:
            raise MaaTouchCleanupError("；".join(str(exc) for exc in failures))

    def interrupt(self):
        if self.owner_pid == os.getpid():
            self._closed_event.set()

    def send(self, content: str):
        def write():
            if self.process.stdin.write(content) != len(content):
                raise ConnectionError("MaaTouch 写入不完整，发送结果无法确认")
            self.process.stdin.flush()

        self._io(write, input_operation=True)

    def wait(self, seconds: float) -> None:
        """Wait for the requested gesture, while keeping shutdown interruptible."""
        timeout = io_timeout(min(seconds, 10))
        if self._closed_event.wait(timeout):
            raise ConnectionError("MaaTouch 会话已关闭")
        if timeout < seconds:
            raise TimeoutError("MaaTouch 操作等待超时，发送结果无法确认")
        io_timeout(0)
        if self.process.poll() is not None:
            raise ConnectionError("MaaTouch 进程提前退出，发送结果无法确认")
