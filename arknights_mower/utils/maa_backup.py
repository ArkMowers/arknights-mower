"""Retire MAA rollback copies only after a completed, successful task run."""

import functools
import logging
import os
import shutil
import threading
from ctypes import CFUNCTYPE, c_char_p, c_int, c_void_p
from pathlib import Path

_update_lock = threading.RLock()


def configure_update_lock(lock):
    """Allow a host to share one update lock before starting worker threads."""
    global _update_lock
    _update_lock = lock


def update_transaction(function):
    @functools.wraps(function)
    def locked(*args, **kwargs):
        with _update_lock:
            return function(*args, **kwargs)

    return locked


def identity(path):
    try:
        value = path.lstat()
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns
    except FileNotFoundError:
        return None


def installation_identity(target):
    # Directory replacement identifies new core/resource installs without hashing
    # hundreds of MB on each task. Do not include mutable user logs/cache files.
    directories = tuple(
        (identity(target / name) or ())[:2] for name in (".", "resource")
    )
    files = tuple(
        identity(target / name)
        for name in (
            "resource/version.json",
            "MaaCore.dll",
            "libMaaCore.so",
            "libMaaCore.dylib",
        )
    )
    return directories + files


class BackupCheckpoint:
    def __init__(self, target):
        self.target = Path(target).expanduser().absolute()
        with _update_lock:
            self.installation = installation_identity(self.target)
            self.backups = {
                path: identity(path)
                for path in (
                    self.target.with_name(self.target.name + ".old"),
                    self.target / "resource.old",
                )
            }

    def retire(self):
        if not _update_lock.acquire(blocking=False):
            return False
        try:
            if self.installation != installation_identity(self.target):
                return False
            for path, expected in self.backups.items():
                if expected is None or expected != identity(path):
                    continue
                if path.is_symlink():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
            return True
        except OSError:
            logging.getLogger(__name__).warning("MAA 任务已完成，旧备份暂无法清理")
            return False
        finally:
            _update_lock.release()


class RunOutcome:
    def __init__(self):
        self.lock = threading.RLock()
        self.begin()

    def begin(self):
        with self.lock:
            self.accepted = self.chain_started = self.chain_completed = False
            self.completed = self.failed = False

    def accept(self, value):
        with self.lock:
            self.accepted = bool(value)

    def event(self, message):
        with self.lock:
            if message in (0, 1, 10000, 10004):
                self.failed = True
            elif message == 10001:
                self.chain_started = True
            elif message == 10002:
                self.chain_completed = True
            elif message == 3:
                self.completed = True

    @property
    def successful(self):
        with self.lock:
            return (
                self.accepted
                and self.chain_started
                and self.chain_completed
                and self.completed
                and not self.failed
            )

    def cancel(self):
        with self.lock:
            if not self.successful:
                self.failed = True


class VerifiedAsst:
    """Preserve the Asst API and callback while checking actual task completion."""

    def __init__(self, asst_type, target, callback):
        self._outcome = RunOutcome()
        self._consumer = callback
        self._callback = CFUNCTYPE(None, c_int, c_char_p, c_void_p)(self._message)
        self._asst = asst_type(callback=self._callback)
        self._retired = False
        self._verified = False
        self._cleanup_thread = None
        self._cleanup_lock = threading.Lock()
        if os.environ.get("MOWER_ANDROID") == "1":
            # Older APKs remain usable; storage cleanup is an optional host hook.
            try:
                from mower_android import backup_cleanup as host

                component = (
                    host.capture_task(self._asst)
                    if hasattr(host, "capture_task")
                    else host.capture_current()
                )
                self._retire = lambda: host.confirm_task(component)
            except (ImportError, OSError, RuntimeError):
                self._retire = lambda: False
        else:
            try:
                self._retire = BackupCheckpoint(target).retire
            except OSError:
                logging.getLogger(__name__).warning("MAA 备份状态无法读取，保留备份")
                self._retire = lambda: False

    def __getattr__(self, name):
        return getattr(self._asst, name)

    def _message(self, message, details, argument):
        self._outcome.event(message)
        if self._consumer is not None:
            self._consumer(message, details, argument)

    def start(self):
        self._outcome.begin()
        self._verified = False
        result = self._asst.start()
        self._outcome.accept(result)
        return result

    def _cleanup(self, verified=False):
        self._verified = self._verified or verified or self._outcome.successful
        if self._retired or not self._verified:
            return
        with self._cleanup_lock:
            if self._cleanup_thread is not None and self._cleanup_thread.is_alive():
                return

            def retire():
                try:
                    self._retired = self._retire()
                except Exception:
                    logging.getLogger(__name__).warning(
                        "MAA 任务已完成，旧备份清理暂不可用"
                    )

            self._cleanup_thread = threading.Thread(
                target=retire, name="maa-backup-cleanup", daemon=True
            )
            self._cleanup_thread.start()

    def running(self):
        running = self._asst.running()
        if not running:
            self._cleanup()
        return running

    def stop(self):
        verified = self._outcome.successful
        self._outcome.cancel()
        result = self._asst.stop()
        self._cleanup(verified=verified)
        return result
