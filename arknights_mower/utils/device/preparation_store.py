"""Durable serial-scoped records and host process locks for temporary sizing."""

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def preparation_root() -> Path:
    """Share serial ownership across installations and configuration spaces."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return base / "arknights-mower/device-preparation"


class RecoveryRecordError(ValueError):
    """An existing record cannot safely authorize a restoration."""


class SerialLockError(RuntimeError):
    """The serial is already leased or its lock cannot be acquired."""


def _serial_key(serial: str) -> str:
    if not isinstance(serial, str) or not serial.strip() or serial != serial.strip():
        raise ValueError("整备恢复记录需要明确的设备 serial")
    return hashlib.sha256(serial.encode("utf-8")).hexdigest()


def _validate_record(record: dict, serial: str) -> None:
    def dimensions(value):
        return (
            isinstance(value, list)
            and len(value) == 2
            and all(type(side) is int and side > 0 for side in value)
        )

    def timestamp(value):
        if not isinstance(value, str):
            return False
        try:
            return datetime.fromisoformat(value).tzinfo is not None
        except ValueError:
            return False

    try:
        valid = (
            isinstance(record, dict)
            and type(record["schema"]) is int
            and record["schema"] == 1
            and record["serial"] == serial
            and isinstance(record["run_id"], str)
            and bool(record["run_id"].strip())
            and dimensions(record["physical"])
            and type(record["override_existed"]) is bool
            and (
                dimensions(record["original_override"])
                if record["override_existed"]
                else record["original_override"] is None
            )
            and dimensions(record["written"])
            and record["written"] in ([1920, 1080], [1080, 1920])
            and record["stage"]
            in ("intent", "written", "validated", "restoring", "pending", "conflict")
            and timestamp(record["created_at"])
            and timestamp(record["updated_at"])
            and (record["last_error"] is None or isinstance(record["last_error"], str))
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise RecoveryRecordError(f"设备 {serial} 的整备恢复记录无效，需要人工检查")


def _unique_json_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryRecordError("整备恢复记录包含重复字段")
        result[key] = value
    return result


def _sync_directory(path: Path) -> None:
    # On POSIX the directory entry must be durable as well as the file contents.
    # Windows does not expose directory fsync through Python's file descriptors.
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class RecoveryStore:
    """Callers hold the serial lease while reading or changing its record."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def load(self, serial: str) -> dict | None:
        path = self.root / f"{_serial_key(serial)}.json"
        try:
            record = json.loads(
                path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_fields
            )
        except FileNotFoundError:
            return None
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RecoveryRecordError(f"设备 {serial} 的整备恢复记录无法解析") from exc
        _validate_record(record, serial)
        return record

    def save(self, record: dict) -> None:
        path = self.root / f"{_serial_key(record['serial'])}.json"
        _validate_record(record, record["serial"])
        self.root.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.root, suffix=".tmp", delete=False
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(record, handle, ensure_ascii=False, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            _sync_directory(self.root)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def clear(self, serial: str) -> None:
        path = self.root / f"{_serial_key(serial)}.json"
        try:
            path.unlink()
        except FileNotFoundError:
            return
        _sync_directory(self.root)


class _SerialLease:
    def __init__(self, handle):
        self._handle = handle

    def close(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class SerialLocks:
    """Nonblocking OS leases; lock files persist to prevent inode replacement races."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def acquire(self, serial: str) -> _SerialLease:
        path = self.root / f"{_serial_key(serial)}.lock"
        self.root.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                if os.fstat(handle.fileno()).st_size == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise SerialLockError(f"设备 {serial} 的整备锁已被占用或无法取得") from exc
        return _SerialLease(handle)
