import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils.device.preparation_store import (
    RecoveryRecordError,
    RecoveryStore,
    SerialLockError,
    SerialLocks,
)


def recovery_record(serial="USB_123"):
    return {
        "schema": 1,
        "serial": serial,
        "run_id": "run-123",
        "physical": [1440, 2560],
        "original_override": None,
        "override_existed": False,
        "written": [1080, 1920],
        "stage": "intent",
        "created_at": "2026-09-26T08:00:00+00:00",
        "updated_at": "2026-09-26T08:00:00+00:00",
        "last_error": None,
    }


class RecoveryStoreTests(unittest.TestCase):
    def test_recovery_record_survives_new_store_and_is_serial_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = RecoveryStore(root)
            record = recovery_record()
            self.assertIsNone(store.load("USB_123"))
            store.save(record)
            self.assertEqual(RecoveryStore(root).load("USB_123"), record)
            self.assertIsNone(store.load("other"))
            store.clear("USB_123")
            self.assertIsNone(RecoveryStore(root).load("USB_123"))
            store.clear("USB_123")

    def test_malformed_record_is_preserved_and_never_looks_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            store = RecoveryStore(Path(folder))
            store.save(recovery_record())
            path = next(Path(folder).glob("*.json"))
            variants = [
                {"schema": 1},
                recovery_record("another-serial"),
                {**recovery_record(), "schema": True},
                {**recovery_record(), "physical": [True, 2560]},
                {**recovery_record(), "written": [720, 1280]},
                {**recovery_record(), "original_override": [1440, 2560]},
                {**recovery_record(), "override_existed": 0},
                {**recovery_record(), "stage": "unknown"},
                {**recovery_record(), "created_at": "invalid"},
                {**recovery_record(), "updated_at": "2026-09-26T08:00:00"},
                {**recovery_record(), "last_error": {}},
            ]
            payloads = [json.dumps(record) for record in variants]
            payloads.extend(
                [
                    "not-json",
                    "[]",
                    json.dumps(recovery_record()).replace(
                        '"schema": 1', '"schema": 2, "schema": 1'
                    ),
                ]
            )
            for payload in payloads:
                with self.subTest(payload=payload):
                    path.write_text(payload, encoding="utf-8")
                    with self.assertRaises(RecoveryRecordError):
                        store.load("USB_123")
                    self.assertEqual(path.read_text(encoding="utf-8"), payload)

    def test_failed_atomic_replace_preserves_prior_record(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = RecoveryStore(root)
            record = recovery_record()
            store.save(record)
            with patch("os.replace", side_effect=OSError("disk unavailable")):
                with self.assertRaises(OSError):
                    store.save({**record, "stage": "written"})
            self.assertEqual(RecoveryStore(root).load("USB_123"), record)
            self.assertEqual(list(root.glob("*.tmp")), [])

    def test_failed_flush_preserves_original_override_record(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = RecoveryStore(root)
            record = {
                **recovery_record(),
                "override_existed": True,
                "original_override": [1200, 2200],
            }
            store.save(record)
            with patch("os.fsync", side_effect=OSError("flush failed")):
                with self.assertRaises(OSError):
                    store.save({**record, "stage": "written"})
            self.assertEqual(RecoveryStore(root).load("USB_123"), record)
            self.assertEqual(list(root.glob("*.tmp")), [])

    def test_invalid_update_cannot_replace_a_recovery_record(self):
        with tempfile.TemporaryDirectory() as folder:
            store = RecoveryStore(Path(folder))
            record = recovery_record()
            store.save(record)
            with self.assertRaises(RecoveryRecordError):
                store.save({**record, "written": [0, 0]})
            self.assertEqual(store.load("USB_123"), record)

    def test_serial_is_a_literal_identity_and_never_a_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "records"
            store = RecoveryStore(root)
            serial = "../sibling:5555"
            record = recovery_record(serial)
            store.save(record)
            self.assertEqual(store.load(serial), record)
            self.assertEqual(len(list(root.glob("*.json"))), 1)
            self.assertEqual(list(Path(folder).glob("*.json")), [])


class SerialLockTests(unittest.TestCase):
    def child_attempt(self, root, serial, *, crash=False):
        program = """
import os
import sys
from pathlib import Path
from arknights_mower.utils.device.preparation_store import SerialLocks, SerialLockError
try:
    lease = SerialLocks(Path(sys.argv[1])).acquire(sys.argv[2])
except SerialLockError:
    sys.exit(23)
if sys.argv[3] == "crash":
    os._exit(0)
lease.close()
"""
        return subprocess.run(
            [
                sys.executable,
                "-c",
                program,
                str(root),
                serial,
                "crash" if crash else "",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    def test_other_process_is_blocked_until_lease_closes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lease = SerialLocks(root).acquire("USB_123")
            try:
                conflict = self.child_attempt(root, "USB_123")
                self.assertEqual(conflict.returncode, 23, conflict.stderr)
                unrelated = self.child_attempt(root, "other")
                self.assertEqual(unrelated.returncode, 0, unrelated.stderr)
            finally:
                lease.close()
            lease.close()
            released = self.child_attempt(root, "USB_123")
            self.assertEqual(released.returncode, 0, released.stderr)

    def test_abrupt_process_exit_releases_os_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exited = self.child_attempt(root, "USB_123", crash=True)
            self.assertEqual(exited.returncode, 0, exited.stderr)
            lease = SerialLocks(root).acquire("USB_123")
            lease.close()

    def test_two_sessions_in_one_process_cannot_lease_same_serial(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lease = SerialLocks(root).acquire("USB_123")
            try:
                with self.assertRaises(SerialLockError):
                    SerialLocks(root).acquire("USB_123")
            finally:
                lease.close()
            next_lease = SerialLocks(root).acquire("USB_123")
            next_lease.close()


if __name__ == "__main__":
    unittest.main()
