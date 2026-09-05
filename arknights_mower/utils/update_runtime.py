"""Installation-wide update coordination, independent of config and GUI imports.

Only registered Mower launchers receive shutdown requests. No process-name scan
or global Python/ADB termination is used. State lives outside the installation.
"""

import atexit
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


def frozen():
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def installation_root():
    if not frozen():
        return Path(__file__).resolve().parents[2]
    executable = Path(sys.executable).resolve()
    for parent in executable.parents:
        if parent.suffix == ".app":
            return parent
    return executable.parent


def state_dir(root=None):
    root = Path(root or installation_root()).resolve()
    key = hashlib.sha256(os.fsencode(root)).hexdigest()[:20]
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "arknights-mower/updates" / key


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied: conservatively alive.
        try:
            code = wintypes.DWORD()
            return (
                not kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                or code.value == 259
            )
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def active_job(directory=None):
    directory = Path(directory or state_dir())
    owner = read_json(directory / "active/owner.json", {})
    return bool(owner and process_alive(owner.get("pid")))


@contextmanager
def submission_lock(directory):
    """Serialize admission, including recovery of a dead updater's active lock."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "submission.lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("其他实例正在提交更新任务") from exc
        try:
            yield
        finally:
            if sys.platform == "win32":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def instances(directory=None):
    directory = Path(directory or state_dir())
    result = []
    for path in (directory / "instances").glob("*.json"):
        record = read_json(path, {})
        if record and process_alive(record.get("pid")):
            result.append(record)
        else:
            path.unlink(missing_ok=True)
    return result


class RuntimeRegistration:
    def __init__(self, kind, *, space="", name="", port=None, running=None):
        self.directory = state_dir()
        self.id = uuid4().hex
        self.path = self.directory / "instances" / f"{self.id}.json"
        self.request = self.directory / "shutdown" / f"{self.id}.json"
        self.running = running or (lambda: False)
        self.closed = threading.Event()
        self.record = {
            "id": self.id,
            "pid": os.getpid(),
            "kind": kind,
            "space": str(space or ""),
            "name": name,
            "port": port,
            "root": str(installation_root()),
            "data_dir": os.environ.get("MOWER_DATA_DIR", ""),
            "ready": False,
            "restart_job": os.environ.get("MOWER_RESTART_JOB", ""),
        }
        self.publish()
        atexit.register(self.close)
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()

    def publish(self):
        self.record.update(running=bool(self.running()), heartbeat=time.time())
        write_json(self.path, self.record)

    def _heartbeat(self):
        while not self.closed.wait(1):
            self.publish()

    def shutdown_requested(self):
        return self.request.exists()

    def close(self):
        self.closed.set()
        self.thread.join(timeout=3)
        self.path.unlink(missing_ok=True)
        self.request.unlink(missing_ok=True)


def hide_macos_dock_icon():
    """Auxiliary Cocoa/Tk/tray processes are accessory apps, with no Dock tile."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except ImportError:
        pass  # Headless/source installations need not have Cocoa installed.


def detached_options():
    if sys.platform == "win32":
        return {"creationflags": 0x00000008 | 0x00000200 | 0x08000000}
    return {"start_new_session": True}


def launch_environment(record, job_id="", background=False):
    env = os.environ.copy()
    # A frozen child must initialize its own bootloader/runtime, including after
    # replacement of the bundle. System subprocesses must not inherit private libs.
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for name in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        if name + "_ORIG" in env:
            env[name] = env[name + "_ORIG"]
        else:
            env.pop(name, None)
    env.update(
        MOWER_RESTART_JOB=job_id,
        MOWER_BACKGROUND="1" if background else "0",
        MOWER_RESUME_RUN="1" if record.get("running") else "0",
        MOWER_RESTART_PORT=str(record.get("port") or ""),
    )
    if record.get("data_dir"):
        env["MOWER_DATA_DIR"] = record["data_dir"]
    else:
        env.pop("MOWER_DATA_DIR", None)
    return env
