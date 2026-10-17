"""截图清理通过有限扫描批次推进，不占用整目录大小的内存。"""

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from arknights_mower.utils.screenshot_cleanup import ScreenshotCleanup


class ScreenshotCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 2 * 3600 * 10**9

    def cleaner(self, **kwargs):
        cleaner = ScreenshotCleanup(
            self.root, lambda: 1, time_ns=lambda: self.now, **kwargs
        )
        self.addCleanup(cleaner.close)
        return cleaner

    def finish(self, cleaner):
        for _ in range(1000):
            result = cleaner.step()
            self.assertLessEqual(result["scanned"], cleaner.batch_size)
            self.assertLessEqual(result["deleted"], cleaner.batch_size)
            if result["complete"]:
                return
        self.fail("清理轮次未能结束")

    def test_each_batch_bounds_all_entries_and_resumes_until_complete(self):
        for index in range(11):
            (self.root / f"{index}.jpg").write_bytes(b"old")
            (self.root / f"{index}.txt").write_text("keep")
        cleaner = self.cleaner(batch_size=3)
        scanned = deleted = 0
        for _ in range(20):
            result = cleaner.step()
            self.assertLessEqual(result["scanned"], 3)
            self.assertLessEqual(result["deleted"], 3)
            self.assertEqual(result["errors"], ())
            scanned += result["scanned"]
            deleted += result["deleted"]
            if result["complete"]:
                break
        else:
            self.fail("有限目录未能完成一轮清理")
        self.assertEqual(scanned, 22)
        self.assertEqual(deleted, 11)
        self.assertEqual(len(list(self.root.iterdir())), 11)

    def test_retention_preserves_new_frames_errors_and_latest_important_images(self):
        self.now = int(datetime(2026, 9, 27, 12).timestamp() * 10**9)
        old = self.now - 2 * 3600 * 10**9
        fresh = self.now - 10**9
        paths = {}
        for folder in ("", "20260927-10", "ordinary", "errors", "ordinary/nested"):
            directory = self.root / folder
            directory.mkdir(parents=True, exist_ok=True)
            paths[folder] = directory / f"{old}.jpg"
            paths[folder].write_bytes(b"old")
        (self.root / "20260927100000.jpg").write_bytes(b"legacy")
        (self.root / "20260927-11").mkdir()
        recent = self.root / "20260927-11" / f"{fresh}.jpg"
        recent.write_bytes(b"fresh")
        for name in ("run_order", "workshop", "furniture", "solve_captcha"):
            folder = self.root / name
            folder.mkdir()
            for index in range(104):
                (folder / f"{old + index}.jpg").write_bytes(b"important")
        self.finish(self.cleaner(batch_size=7))
        for name in ("", "20260927-10", "ordinary"):
            self.assertFalse(paths[name].exists())
        self.assertFalse((self.root / "20260927-10").exists())
        self.assertFalse((self.root / "20260927100000.jpg").exists())
        self.assertTrue(recent.exists())
        self.assertTrue(paths["errors"].exists())
        self.assertTrue(paths["ordinary/nested"].exists())
        for name in ("run_order", "workshop", "furniture", "solve_captcha"):
            remaining = {int(path.stem) for path in (self.root / name).iterdir()}
            self.assertEqual(remaining, set(range(old + 4, old + 104)))

    def test_directory_delete_errors_are_reported_and_next_cycle_can_retry(self):
        self.now = int(datetime(2026, 9, 27, 12).timestamp() * 10**9)
        folder = self.root / "20260927-10"
        folder.mkdir()
        cleaner = self.cleaner()
        failure = PermissionError("locked directory")
        with patch.object(Path, "rmdir", side_effect=failure):
            result = cleaner.step()
        self.assertEqual(result["errors"], (failure,))
        self.assertTrue(result["complete"])
        self.assertTrue(folder.exists())
        result = cleaner.step()
        self.assertEqual(result["errors"], ())
        self.assertEqual(result["deleted"], 1)
        self.assertFalse(folder.exists())

    def test_failed_and_disappearing_files_do_not_stop_other_deletions(self):
        locked = self.root / "1.jpg"
        missing = self.root / "2.jpg"
        healthy = self.root / "3.jpg"
        for path in (locked, missing, healthy):
            path.write_bytes(b"old")
        unlink = Path.unlink
        failure = PermissionError("locked screenshot")

        def flaky_unlink(path, *args, **kwargs):
            if path == locked:
                raise failure
            if path == missing:
                unlink(path)
            return unlink(path, *args, **kwargs)

        cleaner = self.cleaner()
        with patch.object(Path, "unlink", flaky_unlink):
            result = cleaner.step()
        self.assertTrue(result["complete"])
        self.assertEqual(result["errors"], (failure,))
        self.assertEqual(result["scanned"], 3)
        self.assertEqual(result["deleted"], 1)
        self.assertFalse(healthy.exists())
        self.assertFalse(missing.exists())
        self.assertTrue(locked.exists())
        self.finish(cleaner)
        self.assertFalse(locked.exists())

    def test_close_releases_root_and_child_handles_and_rejects_more_work(self):
        folder = self.root / "ordinary"
        folder.mkdir()
        for index in range(3):
            (folder / f"{index}.jpg").write_bytes(b"old")
        scandir = os.scandir
        opened = []

        class DirectoryHandle:
            def __init__(self, path):
                self.iterator = scandir(path)
                self.closed = False
                opened.append(self)

            def __enter__(self):
                return self.iterator

            def __exit__(self, *args):
                self.iterator.close()
                self.closed = True

        cleaner = self.cleaner(batch_size=2)
        with patch("os.scandir", DirectoryHandle):
            result = cleaner.step()
            self.assertFalse(result["complete"])
            self.assertEqual(len(opened), 2)
            cleaner.close()
            cleaner.close()
            self.assertTrue(all(handle.closed for handle in opened))
            result = cleaner.step()
        self.assertTrue(result["complete"])
        self.assertEqual(result["scanned"], 0)
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(len(list(folder.iterdir())), 2)

    def test_scan_failure_reports_once_and_next_cycle_recovers(self):
        old = self.root / "1.jpg"
        old.write_bytes(b"old")
        cleaner = self.cleaner()
        failure = PermissionError("unreadable screenshot directory")
        with patch("os.scandir", side_effect=failure):
            result = cleaner.step()
        self.assertTrue(result["complete"])
        self.assertEqual(result["errors"], (failure,))
        self.assertTrue(old.exists())
        self.finish(cleaner)
        self.assertFalse(old.exists())

    def test_retention_uses_clock_and_keeps_five_minutes_for_error_archives(self):
        old = self.root / f"{self.now - 301 * 10**9}.jpg"
        fresh = self.root / f"{self.now - 299 * 10**9}.jpg"
        old.write_bytes(b"old")
        fresh.write_bytes(b"fresh")
        cleaner = ScreenshotCleanup(self.root, lambda: 1 / 60, time_ns=lambda: self.now)
        self.addCleanup(cleaner.close)
        self.finish(cleaner)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())
        self.now += 2 * 10**9
        self.finish(cleaner)
        self.assertFalse(fresh.exists())

    def test_missing_root_is_a_successful_empty_cycle(self):
        self.root.rmdir()
        result = self.cleaner().step()
        self.assertEqual(
            result, {"scanned": 0, "deleted": 0, "complete": True, "errors": ()}
        )

    def test_directory_replaced_by_symlink_between_batches_is_not_followed(self):
        external = tempfile.TemporaryDirectory()
        self.addCleanup(external.cleanup)
        target = Path(external.name)
        protected = target / "1.jpg"
        protected.write_bytes(b"external")
        folder = self.root / "ordinary"
        folder.mkdir()
        cleaner = self.cleaner(batch_size=1)
        self.assertEqual(cleaner.step()["scanned"], 1)
        folder.rmdir()
        folder.symlink_to(target, target_is_directory=True)
        self.finish(cleaner)
        self.assertEqual(protected.read_bytes(), b"external")
        self.assertTrue(folder.is_symlink())

    def test_file_and_directory_symlinks_are_untouched(self):
        protected = self.root / "errors"
        protected.mkdir()
        image = protected / "1.jpg"
        image.write_bytes(b"protected")
        directory_link = self.root / "ordinary"
        file_link = self.root / "1.jpg"
        directory_link.symlink_to(protected, target_is_directory=True)
        file_link.symlink_to(image)
        self.finish(self.cleaner(batch_size=1))
        self.assertEqual(image.read_bytes(), b"protected")
        self.assertTrue(directory_link.is_symlink())
        self.assertTrue(file_link.is_symlink())

    def test_open_directory_replaced_by_link_does_not_delete_from_link_target(self):
        external = tempfile.TemporaryDirectory()
        self.addCleanup(external.cleanup)
        target = Path(external.name)
        folder = self.root / "ordinary"
        folder.mkdir()
        for name in ("1.jpg", "2.jpg", "3.jpg"):
            (target / name).write_bytes(b"protected")
            (folder / name).write_bytes(b"old")
        cleaner = self.cleaner(batch_size=2)
        self.assertEqual(cleaner.step()["deleted"], 1)
        folder.rename(self.root / "moved")
        folder.symlink_to(target, target_is_directory=True)
        self.finish(cleaner)
        self.assertEqual(len(list(target.iterdir())), 3)

    def test_retention_or_clock_failure_does_not_poison_the_next_cycle(self):
        for dependency in ("retention", "clock"):
            with self.subTest(dependency=dependency):
                old = self.root / "1.jpg"
                old.write_bytes(b"old")
                failure = ValueError("invalid settings or unavailable clock")
                retention = Mock(return_value=1)
                clock = Mock(return_value=self.now)
                if dependency == "retention":
                    retention.side_effect = [failure, 1]
                else:
                    clock.side_effect = [failure, self.now]
                cleaner = ScreenshotCleanup(self.root, retention, time_ns=clock)
                self.addCleanup(cleaner.close)
                result = cleaner.step()
                self.assertTrue(result["complete"])
                self.assertEqual(result["errors"], (failure,))
                self.assertTrue(old.exists())
                result = cleaner.step()
                self.assertTrue(result["complete"])
                self.assertEqual(result["errors"], ())
                self.assertFalse(old.exists())


if __name__ == "__main__":
    unittest.main()
