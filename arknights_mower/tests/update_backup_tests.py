import errno
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import Worker, retry_backup_cleanup


class UpdateBackupTests(unittest.TestCase):
    def test_competing_process_skips_cleanup_and_retries_after_lock_release(self):
        child = (
            "import sys\n"
            "from types import SimpleNamespace\n"
            "if sys.argv[3] == 'worker':\n"
            "    sys.path.insert(0, sys.argv[4])\n"
            "    from software_update_worker import retry_backup_cleanup\n"
            "else:\n"
            "    from arknights_mower.utils.software_update_worker import retry_backup_cleanup\n"
            "logger = SimpleNamespace(warning=print, exception=print) if sys.argv[3] == 'app' else None\n"
            "retry_backup_cleanup(sys.argv[1], sys.argv[2], logger=logger)\n"
        )
        for caller in ("app", "worker"):
            with self.subTest(caller=caller), tempfile.TemporaryDirectory() as folder:
                state = Path(folder)
                root = state / "app"
                runner = state / "runner"
                runner.mkdir()
                for name in (
                    "software_update_worker.py",
                    "update_runtime.py",
                    "github_download.py",
                ):
                    shutil.copy2(Path(runtime.__file__).parent / name, runner / name)
                command = [
                    sys.executable,
                    "-c",
                    child,
                    str(state),
                    str(root),
                    caller,
                    str(runner),
                ]
                backup = state / "jobs/one/runtime-0.backup"
                backup.mkdir(parents=True)
                (backup / "keep.txt").write_text("rollback data")
                identity = backup.stat()
                manifest = backup.parent / "cleanup.json"
                runtime.write_json(
                    manifest,
                    {
                        "verified": True,
                        "root": str(root),
                        "id": "one",
                        "paths": [
                            {
                                "path": str(backup),
                                "identity": [identity.st_dev, identity.st_ino],
                            }
                        ],
                    },
                )
                before = manifest.read_bytes()
                with runtime.submission_lock(state / "backup-cleanup"):
                    result = subprocess.run(
                        command,
                        cwd=Path(__file__).resolve().parents[2],
                        env=runtime.launch_environment({}),
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr, "")
                    self.assertEqual(manifest.read_bytes(), before)
                    self.assertEqual((backup / "keep.txt").read_text(), "rollback data")
                result = subprocess.run(
                    command,
                    cwd=Path(__file__).resolve().parents[2],
                    env=runtime.launch_environment({}),
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")
                self.assertFalse(backup.exists())
                self.assertFalse(manifest.exists())
                self.assertTrue((state / "backup-cleanup/submission.lock").exists())

    def test_real_lock_failure_remains_diagnostic_and_preserves_records(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            manifest = state / "jobs/one/cleanup.json"
            runtime.write_json(manifest, {"verified": True})
            before = manifest.read_bytes()
            for caller in ("app", "worker"):
                logger = Mock() if caller == "app" else None
                with (
                    self.subTest(caller=caller),
                    patch(
                        "arknights_mower.utils.software_update_worker.submission_lock",
                        side_effect=PermissionError(errno.EACCES, "access denied"),
                    ),
                    patch(
                        "arknights_mower.utils.software_update_worker.traceback.print_exc"
                    ) as diagnostic,
                ):
                    retry_backup_cleanup(state, state / "app", logger=logger)
                    if logger is not None:
                        logger.exception.assert_called_once()
                        diagnostic.assert_not_called()
                    else:
                        diagnostic.assert_called_once()
                    self.assertEqual(manifest.read_bytes(), before)

    def test_verified_release_removes_downloads_and_runner_but_keeps_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            root = state / "app"
            work = state / "jobs/one"
            work.mkdir(parents=True)
            runner = work / "runner"
            runner.mkdir()
            (runner / "mower.exe").write_text("old updater")
            for name in ("full.zip", "delta.zip"):
                (work / name).write_text("download")
            (work / "update.log").write_text("update succeeded")
            worker = Worker.__new__(Worker)
            worker.root, worker.work, worker.state, worker.job = (
                root,
                work,
                state,
                {
                    "id": "one",
                    "deployment": "release",
                    "asset": {"name": "full.zip"},
                    "ota_asset": {"name": "delta.zip"},
                },
            )
            worker.backups = []
            worker.bundle_backup = root.with_name("app.backup-one")
            worker.verified_restart = False
            worker.cleanup_verified_backups()
            self.assertTrue(runner.exists())
            self.assertTrue((work / "full.zip").exists())

            worker.verified_restart = True
            worker.cleanup_verified_backups()
            self.assertFalse(runner.exists())
            self.assertFalse((work / "full.zip").exists())
            self.assertFalse((work / "delta.zip").exists())
            self.assertEqual((work / "update.log").read_text(), "update succeeded")

    def test_locked_runner_is_retried_on_next_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            root = state / "app"
            work = state / "jobs/one"
            runner = work / "runner"
            runner.mkdir(parents=True)
            worker = Worker.__new__(Worker)
            worker.root, worker.work, worker.state, worker.job = (
                root,
                work,
                state,
                {"id": "one", "deployment": "release", "asset": {"name": "full.zip"}},
            )
            worker.backups = []
            worker.bundle_backup = root.with_name("app.backup-one")
            worker.verified_restart = True
            with patch(
                "arknights_mower.utils.software_update_worker.shutil.rmtree",
                side_effect=PermissionError("locked"),
            ):
                worker.cleanup_verified_backups()
            self.assertTrue((work / "cleanup.json").exists())
            retry_backup_cleanup(state, root)
            self.assertFalse(runner.exists())
            self.assertFalse((work / "cleanup.json").exists())

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
