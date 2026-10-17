"""Own desktop MAA libraries in a disposable process, outside the scheduler."""

import atexit
import hashlib
import hmac
import importlib
import json
import ntpath
import os
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import weakref
from collections import deque
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace

from arknights_mower.utils.maa_backup import MaaCallError

COMMAND_TIMEOUT = 90
CLOSE_TIMEOUT = 3
MAX_MESSAGE = 8 * 1024 * 1024
MAX_EVENTS = 4096
_processes = weakref.WeakSet()
_registry_lock = threading.RLock()
_METHODS = {
    "connect",
    "get_version",
    "set_instance_option",
    "append_task",
    "set_task_params",
    "start",
    "running",
    "stop",
    "get_tasks_list",
}


class MaaProcessError(RuntimeError):
    code = "maa_worker_failed"


def worker_command():
    from arknights_mower.utils.update_runtime import frozen

    if frozen():
        return [sys.executable, "--maa-runtime-worker"]
    return [sys.executable, "-m", "arknights_mower.utils.maa_process"]


def _receive(channel, deadline=None):
    def read(size):
        result = bytearray()
        while len(result) < size:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("MAA 工作进程响应超时")
                channel.settimeout(remaining)
            chunk = channel.recv(size - len(result))
            if not chunk:
                raise EOFError("MAA 工作进程已断开")
            result.extend(chunk)
        return bytes(result)

    size = struct.unpack("!I", read(4))[0]
    if not 0 < size <= MAX_MESSAGE:
        raise MaaProcessError("MAA 工作进程消息长度无效")
    return json.loads(read(size))


def _send(channel, message, timeout=None):
    payload = json.dumps(message, ensure_ascii=True).encode("ascii")
    if len(payload) > MAX_MESSAGE:
        raise MaaProcessError("MAA 工作进程消息过大")
    channel.settimeout(timeout)
    channel.sendall(struct.pack("!I", len(payload)) + payload)


def _reap(process, channel, lease=None):
    try:
        if channel is not None:
            channel.close()
        if process is None:
            return
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(CLOSE_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(CLOSE_TIMEOUT)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(CLOSE_TIMEOUT)
    finally:
        if process is not None and process.stderr is not None:
            process.stderr.close()
        if lease is not None:
            lease.close()


def installation_lease(target, *, exclusive=False):
    """Coordinate native workers and installation across Mower instances."""
    target = Path(target).expanduser().resolve()
    lock_path = target.parent / f".{target.name}.mower-maa.lock"
    stream = lock_path.open("a+b")
    try:
        if os.name == "nt":
            import ctypes
            import msvcrt
            from ctypes import wintypes

            class Overlapped(ctypes.Structure):
                _fields_ = [
                    ("Internal", ctypes.c_size_t),
                    ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD),
                    ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE),
                ]

            lock = ctypes.WinDLL("kernel32", use_last_error=True).LockFileEx
            lock.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(Overlapped),
            ]
            lock.restype = wintypes.BOOL
            overlapped = Overlapped()
            if not lock(
                msvcrt.get_osfhandle(stream.fileno()),
                1 | (2 if exclusive else 0),
                0,
                1,
                0,
                ctypes.byref(overlapped),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            import fcntl

            fcntl.flock(
                stream, fcntl.LOCK_NB | (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            )
        return stream
    except OSError as error:
        stream.close()
        from arknights_mower.utils.maa_update import MaaUpdateError

        raise MaaUpdateError(
            "MAA 安装目录正在被其他实例使用或无法锁定，请稍后再试"
        ) from error


def maa_client_mutex_name(path):
    """Match the Windows client's Bootstrapper.InstanceKey and StableHash."""
    normalized = ntpath.abspath(str(path)).rstrip("\\/").upper()
    return "MAA_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper()


def _windows_mutex_api():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    for function, arguments, result in (
        (
            kernel.CreateMutexW,
            [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR],
            wintypes.HANDLE,
        ),
        (kernel.WaitForSingleObject, [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        (kernel.ReleaseMutex, [wintypes.HANDLE], wintypes.BOOL),
        (kernel.CloseHandle, [wintypes.HANDLE], wintypes.BOOL),
    ):
        function.argtypes, function.restype = arguments, result
    return kernel


@contextmanager
def _maa_client_mutex(name):
    from arknights_mower.utils.maa_update import MaaUpdateError

    kernel = _windows_mutex_api()
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise MaaUpdateError("无法取得 MAA 客户端互斥锁，请检查目录权限")
    acquired = False
    try:
        acquired = kernel.WaitForSingleObject(handle, 0) in (0, 0x80)
        if not acquired:
            raise MaaUpdateError(
                "独立 MAA 客户端或更新器正在使用此目录，请先关闭后重试"
            )
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


@contextmanager
def maa_client_guard(target):
    """Protect shared files from a loaded client and hold Windows startup mutexes."""
    with ExitStack() as stack:
        target = Path(target).expanduser().absolute()
        if os.name == "nt" and os.environ.get("MOWER_ANDROID") != "1":
            roots = (target, target / ".old", target.with_name(target.name + ".old"))
            names = {
                maa_client_mutex_name(path)
                for root in roots
                for path in (root, root.resolve())
            }
            for name in sorted(names):
                stack.enter_context(_maa_client_mutex(name))
        elif sys.platform == "darwin" and os.environ.get("MOWER_ANDROID") != "1":
            from arknights_mower.utils.device.manager_io import run_command
            from arknights_mower.utils.maa_update import MaaUpdateError

            files = [
                str(root / "libMaaCore.dylib")
                for root in (
                    target,
                    target / ".old",
                    target.with_name(target.name + ".old"),
                )
                if (root / "libMaaCore.dylib").is_file()
            ]
            if files:
                try:
                    result = run_command(
                        [
                            shutil.which("lsof") or "/usr/sbin/lsof",
                            "-nP",
                            "-Fpn",
                            "--",
                            *files,
                        ],
                        timeout=5,
                        capture_output=True,
                        max_output=1024 * 1024,
                    )
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    raise MaaUpdateError(
                        "无法核验 MAA 核心占用，保留安装和备份，请关闭客户端后重试"
                    ) from error
                if result.returncode not in (0, 1) or result.stderr:
                    raise MaaUpdateError(
                        "无法核验 MAA 核心占用，保留安装和备份，请关闭客户端后重试"
                    )
                if result.stdout.strip():
                    raise MaaUpdateError(
                        "MAA 核心仍被其他进程使用，请关闭客户端或旧 Mower 后重试"
                    )
        yield


@contextmanager
def maa_installation_transaction(target):
    if os.environ.get("MOWER_ANDROID") == "1":
        yield
        return
    close_idle_maa_processes(target)
    with installation_lease(target, exclusive=True), maa_client_guard(target):
        yield


def close_idle_maa_processes(target=None):
    """Release native file locks before installing or shutting down Mower."""
    with _registry_lock:
        instances = list(_processes)
    for instance in instances:
        if (
            target is None
            or instance.target.resolve() == Path(target).expanduser().resolve()
        ):
            instance.close()


class MaaProcess:
    _mower_process_isolated = True

    def __init__(self, target, callback, *, timeout=COMMAND_TIMEOUT):
        self.target = Path(target).expanduser().absolute()
        self._callback = callback
        self._timeout = timeout
        self._lock = threading.RLock()
        self._events = deque()
        self._event_bytes = 0
        self._draining = False
        self._closed = False
        self._process = None
        self._channel = None
        self._lease = None
        self._stderr = deque(maxlen=20)
        deadline = time.monotonic() + timeout
        token = secrets.token_hex(32)
        try:
            self._lease = installation_lease(self.target)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(4)
                env = os.environ.copy()
                env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
                kwargs = {}
                if os.name == "nt":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                self._process = subprocess.Popen(
                    worker_command(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    cwd=str(Path(__file__).resolve().parents[2]),
                    env=env,
                    **kwargs,
                )
                process = self._process
                errors = self._stderr

                def collect_errors():
                    try:
                        for line in iter(lambda: process.stderr.readline(4096), b""):
                            errors.append(
                                line.decode("utf-8", errors="replace").rstrip()
                            )
                    except (OSError, ValueError):
                        pass

                threading.Thread(target=collect_errors, daemon=True).start()
                startup = {
                    "port": listener.getsockname()[1],
                    "token": token,
                    "target": str(self.target),
                }
                process.stdin.write(json.dumps(startup).encode("utf-8") + b"\n")
                process.stdin.flush()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("MAA 工作进程启动超时")
                    listener.settimeout(min(remaining, 0.1))
                    try:
                        channel, _ = listener.accept()
                    except socket.timeout:
                        if process.poll() is not None:
                            raise MaaProcessError("MAA 工作进程启动失败")
                        continue
                    try:
                        hello = _receive(channel, deadline)
                        if not hmac.compare_digest(str(hello.get("token", "")), token):
                            channel.close()
                            continue
                        self._channel = channel
                        break
                    except BaseException:
                        channel.close()
                        raise
            self._finalize = weakref.finalize(
                self, _reap, process, self._channel, self._lease
            )
            ready = self._call("initialize")
            self.instance_options = SimpleNamespace(**ready["options"])
            self.version = ready["version"]
            with _registry_lock:
                _processes.add(self)
        except BaseException:
            self._closed = True
            _reap(self._process, self._channel, self._lease)
            finalizer = getattr(self, "_finalize", None)
            if finalizer is not None:
                finalizer.detach()
            raise

    def _call(self, method, *args):
        with self._lock:
            if self._closed:
                raise MaaProcessError("MAA 工作进程已关闭，请重新初始化 MAA")
            try:
                timeout = (
                    min(self._timeout, CLOSE_TIMEOUT)
                    if method == "close"
                    else self._timeout
                )
                deadline = time.monotonic() + timeout
                _send(self._channel, {"method": method, "args": args}, timeout)
                response = _receive(self._channel, deadline)
                events = response.get("events", [])
                event_bytes = sum(len(detail.encode("utf-8")) for _, detail in events)
                if (
                    len(self._events) + len(events) > MAX_EVENTS
                    or self._event_bytes + event_bytes > MAX_MESSAGE // 2
                ):
                    raise MaaProcessError("MAA 回调缓冲区溢出，当前任务不能确认完成")
                self._events.extend(events)
                self._event_bytes += event_bytes
                if not response.get("ok"):
                    if response.get("operation") == "load":
                        raise MaaCallError("load", detail=response["error"])
                    raise MaaProcessError(response.get("error", "MAA 工作进程调用失败"))
            except (
                OSError,
                EOFError,
                ValueError,
                MaaProcessError,
                MaaCallError,
            ) as error:
                self._closed = True
                self._events.clear()
                self._event_bytes = 0
                self._finalize()
                if isinstance(error, (MaaCallError, MaaProcessError)):
                    raise
                raise MaaProcessError(f"MAA 工作进程通信失败：{error}") from error
            # Native callbacks are drained in order before returning the result.
            # Reentrant task-parameter changes append events to this same queue.
            if not self._draining:
                self._draining = True
                try:
                    while self._events:
                        msg, detail = self._events.popleft()
                        self._event_bytes -= len(detail.encode("utf-8"))
                        if self._callback is not None:
                            self._callback(msg, detail.encode("utf-8"), None)
                finally:
                    self._draining = False
            if self._closed:
                raise MaaProcessError("MAA 回调处理期间工作进程已关闭")
            return response.get("result")

    def __getattr__(self, name):
        if name not in _METHODS:
            raise AttributeError(name)
        return lambda *args: self._call(name, *args)

    def close(self):
        with self._lock:
            if self._closed:
                return
            try:
                self._call("close")
            finally:
                self._closed = True
                self._finalize()


def worker_main():
    """Serve only the MAA instance API; never initialize a GUI or device session."""
    parent_input = os.fdopen(os.dup(0), "rb", buffering=0)
    startup = json.loads(parent_input.readline(16384))
    with socket.create_connection(
        ("127.0.0.1", startup["port"]), COMMAND_TIMEOUT
    ) as channel:
        _send(channel, {"token": startup["token"]}, COMMAND_TIMEOUT)

        def parent_exit():
            # The inherited pipe also works on Windows and closes after parent death.
            parent_input.read(1)
            os._exit(0)

        threading.Thread(target=parent_exit, daemon=True).start()
        target = Path(startup["target"])
        pending = deque()
        event_lock = threading.Lock()
        overflow = False
        pending_bytes = 0
        instance = callback = None

        def event(message, detail, argument):
            nonlocal overflow, pending_bytes
            detail = (detail or b"{}").decode("utf-8", errors="replace")
            with event_lock:
                size = len(detail.encode("utf-8"))
                if (
                    len(pending) >= MAX_EVENTS
                    or pending_bytes + size > MAX_MESSAGE // 2
                ):
                    overflow = True
                    return
                pending.append((message, detail))
                pending_bytes += size

        while True:
            channel.settimeout(None)
            try:
                request = _receive(channel)
            except EOFError:
                break
            method = request["method"]
            response = {"ok": True}
            try:
                if overflow:
                    raise MaaProcessError("MAA 回调缓冲区溢出，当前任务不能确认完成")
                if method == "initialize":
                    sys.path.insert(0, str(target / "Python"))
                    asst_type = importlib.import_module("asst.asst").Asst
                    options = importlib.import_module("asst.utils").InstanceOptionType
                    if not asst_type.load(
                        path=target, incremental_path=target / "cache"
                    ):
                        from arknights_mower.utils.maa_runtime import (
                            resource_load_error,
                        )

                        raise resource_load_error(target)
                    from ctypes import CFUNCTYPE, c_char_p, c_int, c_void_p

                    callback = CFUNCTYPE(None, c_int, c_char_p, c_void_p)(event)
                    instance = asst_type(callback=callback)
                    response["result"] = {
                        "version": instance.get_version(),
                        "options": {
                            name: int(getattr(options, name))
                            for name in (
                                "touch_type",
                                "adblite_enabled",
                                "kill_on_adb_exit",
                            )
                            if hasattr(options, name)
                        },
                    }
                elif method == "close":
                    if instance is not None:
                        instance.stop()
                    response["result"] = True
                elif method in _METHODS and instance is not None:
                    response["result"] = getattr(instance, method)(*request["args"])
                else:
                    raise MaaProcessError("MAA 工作进程操作无效")
            except Exception as error:
                response.update(
                    ok=False,
                    error=getattr(error, "detail", None) or str(error),
                    operation=getattr(error, "operation", None),
                )
            with event_lock:
                response["events"] = list(pending)
                pending.clear()
                pending_bytes = 0
                if overflow:
                    response.update(
                        ok=False, error="MAA 回调缓冲区溢出，当前任务不能确认完成"
                    )
            _send(channel, response, COMMAND_TIMEOUT)
            if method == "close" or not response["ok"]:
                break


atexit.register(close_idle_maa_processes)

if __name__ == "__main__":
    worker_main()
