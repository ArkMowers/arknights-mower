import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from arknights_mower.utils import maa_backup as backup


class FakeAsst:
    def __init__(self, callback):
        self.callback = callback
        self.messages = []
        self.accepted = True

    def start(self):
        return self.accepted

    def running(self):
        messages, self.messages = self.messages, []
        for message in messages:
            self.callback(message, b"{}", None)
        return False

    def stop(self):
        self.callback(10004, b"{}", None)
        return True


class MaaBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "maa"
        (self.target / "resource").mkdir(parents=True)
        (self.target / "resource/version.json").write_text("new")
        (self.target / "libMaaCore.so").write_text("new core")
        self.old = self.root / "maa.old"
        self.old.mkdir()
        (self.old / "old.bin").write_text("old core")
        self.old_resource = self.target / "resource.old"
        self.old_resource.mkdir()
        (self.old_resource / "old.bin").write_text("old resource")
        self.settings = self.target / "config.json"
        self.settings.write_text("keep user data")
        self.environment = patch.dict(os.environ, {"MOWER_ANDROID": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def asst(self):
        self.consumer = Mock()
        self.instance = backup.VerifiedAsst(FakeAsst, self.target, self.consumer)
        return self.instance

    def finish(self, instance, messages=(10001, 10002, 3)):
        instance._asst.messages = list(messages)
        self.assertFalse(instance.running())
        if instance._cleanup_thread is not None:
            instance._cleanup_thread.join(3)
            self.assertFalse(instance._cleanup_thread.is_alive())

    def test_success_removes_core_and_resource_backups_for_desktop_layouts(self):
        for library in ("libMaaCore.so", "libMaaCore.dylib", "MaaCore.dll"):
            with self.subTest(library=library):
                (self.target / library).write_text("core")
                self.old.mkdir(exist_ok=True)
                self.old_resource.mkdir(exist_ok=True)
                instance = self.asst()
                self.assertTrue(
                    self.old.exists()
                )  # construction/connection is insufficient
                instance.start()
                (self.target / "cache").mkdir(exist_ok=True)
                self.finish(instance)
                self.assertFalse(self.old.exists())
                self.assertFalse(self.old_resource.exists())
                self.assertEqual(self.settings.read_text(), "keep user data")
                self.assertEqual(self.consumer.call_count, 3)

    def test_failed_stopped_empty_or_rejected_runs_keep_backups(self):
        for messages in ((10001, 10000, 10002, 3), (10001, 10004, 3), (3,)):
            with self.subTest(messages=messages):
                instance = self.asst()
                instance.start()
                self.finish(instance, messages)
                self.assertTrue(self.old.exists())
        instance = self.asst()
        instance._asst.accepted = False
        self.assertFalse(instance.start())
        self.finish(instance)
        self.assertTrue(self.old.exists())
        instance = self.asst()
        instance.start()
        instance.stop()
        self.finish(instance)
        self.assertTrue(self.old.exists())

    def test_old_task_cannot_delete_a_new_installations_backup(self):
        instance = self.asst()
        instance.start()
        self.target.rename(self.root / "previous-running")
        self.target.mkdir()
        (self.target / "resource").mkdir()
        self.finish(instance)
        self.assertTrue(self.old.exists())

    def test_update_in_progress_defers_cleanup_without_blocking_callbacks(self):
        instance = self.asst()
        instance.start()
        acquired, release = threading.Event(), threading.Event()

        def update():
            with backup._update_lock:
                acquired.set()
                release.wait(5)

        thread = threading.Thread(target=update)
        thread.start()
        try:
            self.assertTrue(acquired.wait(2))
            self.finish(instance)
            self.assertTrue(self.old.exists())
        finally:
            release.set()
            thread.join()
        self.assertFalse(instance.running())
        if instance._cleanup_thread is not None:
            instance._cleanup_thread.join(3)
            self.assertFalse(instance._cleanup_thread.is_alive())
        self.assertFalse(self.old.exists())

    def test_cleanup_failure_does_not_fail_task_or_prevent_retry(self):
        instance = self.asst()
        instance.start()
        with patch.object(backup.shutil, "rmtree", side_effect=PermissionError):
            self.finish(instance)
        self.assertTrue(self.old.exists())
        self.assertFalse(instance.running())
        if instance._cleanup_thread is not None:
            instance._cleanup_thread.join(3)
            self.assertFalse(instance._cleanup_thread.is_alive())
        self.assertFalse(self.old.exists())

    def test_android_uses_verified_host_identity_and_old_hosts_remain_usable(self):
        host = SimpleNamespace(
            capture_current=lambda: "a" * 64, confirm_task=Mock(return_value=True)
        )
        with (
            patch.dict(os.environ, {"MOWER_ANDROID": "1"}),
            patch.dict(
                "sys.modules",
                {
                    "mower_android": SimpleNamespace(backup_cleanup=host),
                    "mower_android.backup_cleanup": host,
                },
            ),
        ):
            instance = self.asst()
            instance.start()
            self.finish(instance)
            host.confirm_task.assert_called_once_with("a" * 64)
            self.assertTrue(self.old.exists())  # the host owns Android storage
        with (
            patch.dict(os.environ, {"MOWER_ANDROID": "1"}),
            patch.dict(
                "sys.modules",
                {"mower_android": None, "mower_android.backup_cleanup": None},
            ),
        ):
            instance = self.asst()
            instance.start()
            self.finish(instance)
            self.assertTrue(self.old.exists())

    def test_stop_after_success_does_not_invalidate_verified_run(self):
        instance = self.asst()
        instance.start()
        for message in (10001, 10002, 3):
            instance._message(message, b"{}", None)
        instance.stop()
        instance._cleanup_thread.join(3)
        self.assertFalse(self.old.exists())

    def test_unreadable_backup_metadata_does_not_prevent_tasks(self):
        with patch.object(backup, "BackupCheckpoint", side_effect=PermissionError):
            instance = self.asst()
        instance.start()
        self.finish(instance)
        self.assertTrue(self.old.exists())

    def test_stop_cleanup_failure_can_retry_after_completion(self):
        instance = self.asst()
        instance.start()
        for message in (10001, 10002, 3):
            instance._message(message, b"{}", None)
        with patch.object(backup.shutil, "rmtree", side_effect=PermissionError):
            instance.stop()
            if instance._cleanup_thread is not None:
                instance._cleanup_thread.join(3)
        self.assertTrue(self.old.exists())
        instance.running()
        instance._cleanup_thread.join(3)
        self.assertFalse(self.old.exists())

    def test_configured_symlink_does_not_select_another_paths_sibling_backup(self):
        alias = self.root / "configured-maa"
        try:
            alias.symlink_to(self.target, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable on this host")
        saved = self.root / "configured-maa.old"
        saved.mkdir()
        instance = backup.VerifiedAsst(FakeAsst, alias, Mock())
        instance.start()
        self.finish(instance)
        self.assertFalse(saved.exists())
        self.assertTrue(self.old.exists())
        self.assertTrue(self.settings.exists())

    def test_slow_cleanup_never_blocks_task_status_or_stop(self):
        instance = self.asst()
        entered, release = threading.Event(), threading.Event()

        def slow_cleanup():
            entered.set()
            release.wait(5)
            return True

        instance._retire = slow_cleanup
        instance.start()
        instance._asst.messages = [10001, 10002, 3]
        try:
            self.assertFalse(instance.running())
            self.assertTrue(entered.wait(2))
            self.assertTrue(instance.stop())
            self.assertTrue(instance._cleanup_thread.is_alive())
        finally:
            release.set()
            instance._cleanup_thread.join(3)
