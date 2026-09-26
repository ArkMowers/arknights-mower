import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils.software_update_worker import Worker, retry_backup_cleanup


class UpdateBackupTests(unittest.TestCase):
    def test_only_verified_restart_retires_recorded_source_and_bundle_backups(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "jobs/one"
            work.mkdir(parents=True)
            current, saved, bundle, unrelated = [
                root / name
                for name in (
                    "current",
                    "jobs/one/runtime-0.backup",
                    "current.backup-one",
                    "config-backups",
                )
            ]
            for path in (current, saved, bundle, unrelated):
                path.mkdir()
                (path / "keep.txt").write_text("data")
            worker = Worker.__new__(Worker)
            worker.root, worker.work, worker.state, worker.job = (
                current,
                work,
                root,
                {"id": "one"},
            )
            worker.backups = [(current, saved)]
            worker.bundle_backup = bundle
            worker.verified_restart = False
            worker.cleanup_verified_backups()
            self.assertTrue(saved.exists())
            self.assertTrue(bundle.exists())
            worker.verified_restart = True
            worker.cleanup_verified_backups()
            self.assertFalse(saved.exists())
            self.assertFalse(bundle.exists())
            self.assertTrue((current / "keep.txt").exists())
            self.assertTrue((unrelated / "keep.txt").exists())

    def test_locked_backup_is_retained_without_raising_or_touching_current_install(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            saved = root / "app.backup-one"
            work = root / "jobs/one"
            work.mkdir(parents=True)
            saved.mkdir()
            worker = Worker.__new__(Worker)
            worker.root, worker.work, worker.state, worker.job = (
                root / "app",
                work,
                root,
                {"id": "one"},
            )
            worker.backups = []
            worker.bundle_backup = saved
            worker.verified_restart = True
            with patch(
                "arknights_mower.utils.software_update_worker.shutil.rmtree",
                side_effect=PermissionError("locked"),
            ):
                worker.cleanup_verified_backups()
            self.assertTrue(saved.exists())

            self.assertTrue((work / "cleanup.json").exists())
            retry_backup_cleanup(root, root / "app")
            self.assertFalse(saved.exists())
            self.assertFalse((work / "cleanup.json").exists())

    def test_retry_skips_unverified_replaced_and_unrelated_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            root = state / "app"
            work = state / "jobs/one"
            work.mkdir(parents=True)
            saved = work / "runtime-0.backup"
            saved.mkdir()
            identity = saved.stat()
            unrelated = state / "user-data"
            unrelated.mkdir()
            record = {
                "verified": False,
                "root": str(root),
                "id": "one",
                "paths": [
                    {"path": str(saved), "identity": [identity.st_dev, identity.st_ino]}
                ],
            }
            manifest = work / "cleanup.json"
            manifest.write_text(json.dumps(record))
            retry_backup_cleanup(state, root)
            self.assertTrue(saved.exists())
            saved.rename(work / "retained-original")
            saved.mkdir()
            other = unrelated.stat()
            record["verified"] = True
            record["paths"].append(
                {"path": str(unrelated), "identity": [other.st_dev, other.st_ino]}
            )
            manifest.write_text(json.dumps(record))
            retry_backup_cleanup(state, root)
            self.assertTrue(saved.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue((work / "retained-original").exists())
