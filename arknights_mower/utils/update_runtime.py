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
        replace_with_retry(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def replace_with_retry(source, destination):
    """Atomically replace ``destination``, tolerating transient Windows locks.

    ``os.replace`` is atomic, but on Windows it fails with a sharing violation
    (WinError 5/32) when another handle keeps the destination open without
    ``FILE_SHARE_DELETE`` — for example a concurrent ``instances()`` directory
    scan reading the same JSON. Retrying briefly is enough for the reader to
    release the file. POSIX ``os.replace`` never contends this way, so it
    always re-raises immediately.
    """
    deadline = time.monotonic() + 5
    while True:
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            if sys.platform != "win32" or winerror not in (5, 32):
                raise
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.05)


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


def registration_key(record):
    """Stable identity for matching an instance's registration across a restart.

    Space, name and port only mean something together as the identity of an
    instance. Matching on them is independent of the process id, which on some
    Windows launchers differs from the registered ``os.getpid()``.
    """
    return (record.get("space") or "", record.get("name") or "", record.get("port"))


class InstanceScanError(RuntimeError):
    """A complete registration snapshot could not be read safely."""


def instances(directory=None, *, timeout=5, strict=True):
    """Read registrations without treating an unreadable file as a dead process.

    The entire scan shares one retry budget. Update admission and shutdown need
    a complete snapshot; tray rendering can explicitly request a best-effort one.
    """
    directory = Path(directory or state_dir()) / "instances"
    deadline = time.monotonic() + timeout
    while True:
        result = []
        failures = []
        try:
            paths = sorted(p for p in directory.iterdir() if p.suffix == ".json")
        except FileNotFoundError:
            return []
        except OSError as exc:
            paths = []
            failures.append((directory, exc))
        for path in paths:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if (
                    not isinstance(record, dict)
                    or type(record.get("pid")) is not int
                    or record["pid"] <= 0
                ):
                    raise ValueError("实例登记缺少有效的进程编号")
                if process_alive(record["pid"]):
                    result.append(record)
                else:
                    path.unlink(missing_ok=True)
            except FileNotFoundError:
                pass  # The instance may have removed its registration on exit.
            except (OSError, ValueError) as exc:
                failures.append((path, exc))
        if not failures:
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if not strict:
                return result
            path, error = failures[0]
            raise InstanceScanError(
                f"无法完整读取实例登记，请稍后重试或检查文件权限：{path}（{error}）"
            ) from error
        time.sleep(min(0.05, remaining))


def managed_instances(directory=None, data_dir=None):
    data_dir = os.environ.get("MOWER_DATA_DIR", "") if data_dir is None else data_dir
    return [
        record
        for record in instances(directory, timeout=0, strict=False)
        if record.get("kind") == "instance"
        and record.get("managed")
        and record.get("data_dir", "") == data_dir
    ]


def unified_managers(directory=None, data_dir=None):
    data_dir = os.environ.get("MOWER_DATA_DIR", "") if data_dir is None else data_dir
    return [
        record
        for record in instances(directory, timeout=0, strict=False)
        if record.get("kind") == "manager"
        and record.get("unified_tray")
        and record.get("data_dir", "") == data_dir
    ]


def send_instance_command(record, action, directory=None):
    """Address only the registered instance selected by the manager."""
    directory = Path(directory or state_dir())
    if action == "exit":
        write_json(directory / "shutdown" / f"{record['id']}.json", {"manager": True})
    elif action in ("toggle", "browser", "show"):
        write_json(
            directory / "commands" / record["id"] / f"{uuid4().hex}.json",
            {"action": action},
        )
    else:
        raise ValueError(f"Unknown instance command: {action}")


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
            "executable": sys.executable,
            "argv": list(sys.argv),
            "cwd": os.getcwd(),
            "background": os.environ.get("MOWER_BACKGROUND") == "1",
            "managed": kind == "instance" and os.environ.get("MOWER_MANAGED") == "1",
            "ready": False,
            "restart_job": os.environ.get("MOWER_RESTART_JOB", ""),
        }
        self.publish()
        atexit.register(self.close)
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()
        threading.Thread(
            target=self._retry_backups, name="mower-backup-cleanup", daemon=True
        ).start()

    def _retry_backups(self):
        try:
            from .software_update_worker import retry_backup_cleanup

            retry_backup_cleanup(self.directory, self.record["root"])
        except Exception:
            # This optional maintenance cannot prevent registration or startup.
            import logging

            logging.getLogger(__name__).warning("历史更新备份暂无法清理")

    def publish(self):
        self.record.update(running=bool(self.running()), heartbeat=time.time())
        write_json(self.path, self.record)

    def _heartbeat(self):
        while not self.closed.wait(1):
            self.publish()

    def shutdown_requested(self):
        return self.request.exists()

    def take_commands(self):
        actions = []
        for path in sorted((self.directory / "commands" / self.id).glob("*.json")):
            command = read_json(path, {})
            path.unlink(missing_ok=True)
            if command.get("action") in ("toggle", "browser", "show"):
                actions.append(command["action"])
        return actions

    def close(self):
        from shutil import rmtree

        self.closed.set()
        self.thread.join(timeout=3)
        self.path.unlink(missing_ok=True)
        self.request.unlink(missing_ok=True)
        rmtree(self.directory / "commands" / self.id, ignore_errors=True)


def hide_macos_dock_icon():
    """The tray process is an accessory app, with no Dock tile."""
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
    # Set these before starting source Python children. Frozen workers also
    # configure their streams explicitly, since bootloaders may ignore them.
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    for name in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        if name + "_ORIG" in env:
            env[name] = env[name + "_ORIG"]
        else:
            env.pop(name, None)
    # os._Environ normalizes variable names to uppercase on Windows, so a plain
    # copy can change the casing of proxy variables. Normalize them to lowercase
    # so subprocesses and callers see a deterministic environment on every platform.
    for name in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        matches = [key for key in env if key.lower() == name]
        if matches:
            # requests/urllib prefer the exact lowercase spelling, even when
            # its value is empty. Never let insertion order overwrite it.
            key = name if name in env else name.upper()
            value = env[key] if key in env else env[sorted(matches)[0]]
            for key in matches:
                del env[key]
            env[name] = value
    env.update(
        MOWER_RESTART_JOB=job_id,
        MOWER_BACKGROUND="1" if background else "0",
        MOWER_RESUME_RUN="1" if record.get("running") else "0",
        MOWER_RESTART_PORT=str(record.get("port") or ""),
        MOWER_MANAGED="1" if record.get("managed") else "0",
    )
    if record.get("data_dir"):
        env["MOWER_DATA_DIR"] = record["data_dir"]
    else:
        env.pop("MOWER_DATA_DIR", None)
    return env


@contextmanager
def utf8_output(log_path):
    """Use UTF-8 for worker logs, including windowed/frozen standard streams."""
    original = sys.stdout, sys.stderr
    log = None
    try:
        if any(stream is None for stream in original):
            log = Path(log_path).open("a", encoding="utf-8", buffering=1)
        for name, stream in zip(("stdout", "stderr"), original):
            if stream is None:
                setattr(sys, name, log)
            elif hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        yield
    finally:
        sys.stdout, sys.stderr = original
        if log is not None:
            log.close()
