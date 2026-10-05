"""An owned process bounds MuMu native input and disconnect calls."""

import multiprocessing
import os
import subprocess
import time
from threading import Event, Lock

from arknights_mower.utils import config
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.manager_io import MAX_OUTPUT, run_command
from arknights_mower.utils.device.mumu12ipc.core import (
    MuMu12IPC,
    MuMuIpcError,
    bind_display,
)
from arknights_mower.utils.device.mumu12ipc.paths import resolve_mumu_paths
from arknights_mower.utils.device.owned import close_process
from arknights_mower.utils.log import logger

INPUT_TIMEOUT = 10
_INPUT_EVENTS = frozenset(
    (
        "key_down",
        "key_up",
        "touch_down",
        "touch_up",
        "finger_touch_down",
        "finger_touch_up",
    )
)


def _input_worker(root, instance, package, new_coordinates, channel):
    """Vendor handles stay in this process, including a blocking disconnect."""
    ipc = object.__new__(MuMu12IPC)
    ipc._conn = 0
    ipc._dll = None
    try:
        ipc._emu_root = root
        ipc._is_new_coord = new_coordinates
        ipc._load_renderer()
        connection = ipc._dll.nemu_connect(root, int(instance))
        if connection <= 0:
            raise MuMuIpcError(
                f"MuMu IPC 连接失败：原生返回码 {connection}",
                return_code=connection,
            )
        ipc._conn = connection
        ipc._display_id = bind_display(ipc._dll, connection, package)
        channel.send(("ok", "", None))
        while True:
            event, arguments = channel.recv()
            if event not in _INPUT_EVENTS:
                raise MuMuIpcError("MuMu IPC 收到未知输入事件")
            getattr(ipc, event)(*arguments)
            channel.send(("ok", "", None))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            channel.send(
                (
                    "error",
                    str(exc).encode("utf-8")[:1024].decode("utf-8", "ignore"),
                    getattr(exc, "return_code", None),
                )
            )
        except (EOFError, BrokenPipeError, OSError):
            pass
    finally:
        try:
            ipc.disconnect()
        finally:
            channel.close()


class MuMuInputSession:
    """Do not replay uncertain input or rebuild a failed native worker."""

    def __init__(self, device):
        self.device = device
        self._owner_pid = os.getpid()
        self._closed = Event()
        self._cancelled = Event()
        self._close_lock = Lock()
        self._request_lock = Lock()
        self._failure = None
        self._close_error = None
        self._process = None
        self._channel = None
        profile = getattr(device, "profile", config.conf.device).model_copy(deep=True)
        root, manager = resolve_mumu_paths(
            profile.installation_path, profile.manager_path
        )
        # Read the coordinate-version flag before spawning the native worker.
        # Killing that worker must never orphan its own manager subprocess.
        timeout = io_timeout(5)
        logger.debug(
            f"MuMu 输入版本查询开始：实例 {profile.instance_id}，超时 {timeout:.3f} 秒"
        )
        result = run_command(
            [
                manager,
                "setting",
                "-v",
                str(profile.instance_id),
                "get_key",
                "core_version",
            ],
            capture_output=True,
            text=True,
            # A version query is read for its ASCII answer; a stray byte in the
            # vendor's own diagnostics must not replace that answer with a
            # decoding failure.
            errors="replace",
            check=True,
            timeout=timeout,
            max_output=MAX_OUTPUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        logger.debug(f"MuMu 输入版本查询完成：实例 {profile.instance_id}")
        version = tuple(int(value) for value in result.stdout.strip().split(".")[:3])
        self._check_open()
        io_timeout(0)
        context = multiprocessing.get_context("spawn")
        self._channel, child = context.Pipe()
        try:
            try:
                self._process = context.Process(
                    target=_input_worker,
                    args=(
                        root,
                        profile.instance_id,
                        profile.game_package or config.conf.APPNAME,
                        version >= (4, 1, 21),
                        child,
                    ),
                    daemon=True,
                )
                self._process.start()
            finally:
                child.close()
            self._receive(time.monotonic() + io_timeout(INPUT_TIMEOUT))
        except BaseException as exc:
            try:
                self.close()
            except Exception as cleanup_error:
                exc.add_note(str(cleanup_error))
                exc.cleanup_failed = True
            raise

    def _check_open(self):
        if self._owner_pid != os.getpid():
            raise MuMuIpcError("MuMu IPC 输入会话不属于当前进程")
        if self._closed.is_set() or self._cancelled.is_set():
            raise MuMuIpcError("MuMu IPC 输入会话已关闭")
        if self._failure is not None:
            raise self._failure

    def _remaining(self, deadline):
        self._check_open()
        remaining = io_timeout(min(INPUT_TIMEOUT, deadline - time.monotonic()))
        if remaining <= 0:
            raise TimeoutError("MuMu IPC 输入未在限定时间完成，结果未知")
        return remaining

    def _receive(self, deadline):
        while not self._channel.poll(min(0.05, self._remaining(deadline))):
            pass
        self._check_open()
        status, message, code = self._channel.recv()
        if status != "ok":
            raise MuMuIpcError(message, return_code=code)

    def _input_event(self, event, *args):
        deadline = time.monotonic() + io_timeout(INPUT_TIMEOUT)
        while not self._request_lock.acquire(
            timeout=min(0.05, self._remaining(deadline))
        ):
            pass
        try:
            self._check_open()
            try:
                self._channel.send((event, args))
                self._receive(deadline)
            except Exception as exc:
                if isinstance(
                    exc, (EOFError, BrokenPipeError, OSError)
                ) and not isinstance(exc, TimeoutError):
                    exc = MuMuIpcError("MuMu IPC 输入工作进程意外退出，结果未知")
                self._failure = exc
                raise exc
        finally:
            self._request_lock.release()

    def _wait(self, seconds):
        self._check_open()
        if self._cancelled.wait(max(0, io_timeout(seconds))):
            self._check_open()
        io_timeout(0)

    def key_down(self, key_code):
        self._input_event("key_down", int(key_code))

    def key_up(self, key_code):
        self._input_event("key_up", int(key_code))

    def touch_down(self, x, y):
        self._input_event("touch_down", int(x), int(y))

    def touch_up(self):
        self._input_event("touch_up")

    def finger_touch_down(self, finger_id, x, y):
        self._input_event("finger_touch_down", int(finger_id), int(x), int(y))

    def finger_touch_up(self, finger_id):
        self._input_event("finger_touch_up", int(finger_id))

    def tap(self, x, y, hold_time=0.07):
        self.touch_down(x, y)
        self._wait(hold_time)
        self.touch_up()

    def send_keyevent(self, key_code, hold_time=0.1):
        self.key_down(key_code)
        self._wait(hold_time)
        self.key_up(key_code)

    def back(self):
        self.send_keyevent(1)

    def swipe(
        self, x0, y0, x1, y1, duration=0.5, steps=30, fall=True, lift=True, interval=0.0
    ):
        if fall:
            self.touch_down(x0, y0)
        for step in range(1, steps + 1):
            self.touch_down(
                int(x0 + (x1 - x0) * step / steps),
                int(y0 + (y1 - y0) * step / steps),
            )
            self._wait(duration / steps)
        if lift:
            self._wait(interval)
            self.touch_up()

    def swipe_ext(self, points, durations, update=False, interval=0.0, func=None):
        if len(points) < 2 or len(durations) != len(points) - 1:
            raise ValueError(
                "swipe_ext requires at least 2 points and len(durations)==len(points)-1"
            )
        for index, (start, end, duration) in enumerate(
            zip(points[:-1], points[1:], durations)
        ):
            self.swipe(
                *start,
                *end,
                duration=max(0.01, duration / 1000),
                fall=index == 0,
                lift=index == len(durations) - 1,
                interval=interval if index == len(durations) - 1 else 0,
            )

    def close(self):
        """Close pipes first; never wait for an input lock held by native I/O."""
        with self._close_lock:
            if self._owner_pid != os.getpid():
                return
            if self._closed.is_set():
                if self._close_error is not None:
                    raise self._close_error
                return
            self._closed.set()
            self._cancelled.set()
            failures = []
            if self._channel is not None:
                try:
                    self._channel.close()
                except Exception as exc:
                    failures.append(exc)
            try:
                close_process(self._process, self._owner_pid, error_type=MuMuIpcError)
            except Exception as exc:
                failures.append(exc)
            if failures:
                self._close_error = failures[0]
                for error in failures[1:]:
                    self._close_error.add_note(str(error))
                raise self._close_error

    disconnect = close

    def interrupt(self):
        if self._owner_pid == os.getpid():
            self._cancelled.set()
