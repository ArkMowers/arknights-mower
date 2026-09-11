import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils.software_update_worker import Worker


class UpdateBackupTests(unittest.TestCase):
    def test_only_verified_restart_retires_recorded_source_and_bundle_backups(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current, saved, bundle, unrelated = [
                root / name
                for name in (
                    "current",
                    "runtime.backup",
                    "app.backup-job",
                    "config-backups",
                )
            ]
            for path in (current, saved, bundle, unrelated):
                path.mkdir()
                (path / "keep.txt").write_text("data")
            worker = Worker.__new__(Worker)
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
            saved = root / "app.backup-job"
            saved.mkdir()
            worker = Worker.__new__(Worker)
            worker.backups = []
            worker.bundle_backup = saved
            worker.verified_restart = True
            with patch(
                "arknights_mower.utils.software_update_worker.shutil.rmtree",
                side_effect=PermissionError("locked"),
            ):
                worker.cleanup_verified_backups()
            self.assertTrue(saved.exists())
