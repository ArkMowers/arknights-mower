"""在临时目录中验证截图读写隔离、故障恢复和清理并发。"""

import json
import os
import tempfile
import time
import unittest
import weakref
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock, patch

import numpy as np

from arknights_mower.utils.log_retention import RUNTIME_LOG_RETENTION_HOURS
from arknights_mower.utils.screenshot import ScreenshotStore
from arknights_mower.views import screenshot as views


class ScreenshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "screenshots"
        self.logger = Mock()
        self.retention = 1
        self.store = ScreenshotStore(
            self.root, lambda: self.retention, self.logger, cleanup_interval=0.02
        )
        self.addCleanup(self.store.close)

    def wait_idle(self, timeout=3):
        deadline = time.monotonic() + timeout
        while self.store.stats()["pending_count"] and time.monotonic() < deadline:
            Event().wait(0.005)
        self.assertEqual(self.store.stats()["pending_count"], 0)
        self.assertEqual(self.store.stats()["pending_bytes"], 0)

    def seed(self, folder, timestamp, contents=b"old"):
        path = self.root / folder / f"{timestamp}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return path

    def limit_store(self, **limits):
        self.store = ScreenshotStore(
            self.root, lambda: self.retention, self.logger, **limits
        )
        self.addCleanup(self.store.close)

    def test_error_window_archives_existing_and_future_screenshots(self):
        event_time = time.time_ns()
        previous_time = event_time - 2 * 60 * 10**9
        old_time = event_time - 6 * 60 * 10**9
        previous = self.seed(
            datetime.fromtimestamp(previous_time / 10**9).strftime("%Y%m%d-%H"),
            previous_time,
        )
        too_old = self.seed(
            datetime.fromtimestamp(old_time / 10**9).strftime("%Y%m%d-%H"),
            old_time,
        )
        archive_id = self.store.mark_error(event_time, "设备连接失败")
        self.store.start()
        future = self.store.submit(b"after error")
        self.wait_idle()
        archive = self.root / "errors" / archive_id
        deadline = time.monotonic() + 3
        while not (archive / previous.name).exists() and time.monotonic() < deadline:
            Event().wait(0.01)
        self.assertEqual((archive / previous.name).read_bytes(), b"old")
        self.assertEqual((archive / Path(future).name).read_bytes(), b"after error")
        self.assertFalse((archive / too_old.name).exists())
        self.assertIn(
            "设备连接失败", (archive / "event.json").read_text(encoding="utf-8")
        )

        self.retention = 0
        self.store.cleanup()
        self.assertFalse(previous.exists())
        self.assertTrue((archive / previous.name).exists())
        self.assertTrue((archive / Path(future).name).exists())

    def test_overlapping_errors_share_archive_and_backfill_extended_window(self):
        second = time.time_ns()
        first = second - 9 * 60 * 10**9
        gap_time = second - 3 * 60 * 10**9
        gap = self.seed(
            datetime.fromtimestamp(gap_time / 10**9).strftime("%Y%m%d-%H"),
            gap_time,
        )
        first_id = self.store.mark_error(first, "首次失败")
        second_id = self.store.mark_error(second, "再次失败")
        self.assertEqual(second_id, first_id)
        self.assertEqual(len(self.store._error_windows), 1)
        self.assertEqual(self.store._error_windows[0][1], second + 5 * 60 * 10**9)

        self.store.start()
        archive = self.root / "errors" / first_id
        deadline = time.monotonic() + 3
        while (
            not (archive / gap.name).exists() or not (archive / "event.json").exists()
        ) and time.monotonic() < deadline:
            Event().wait(0.01)
        event = json.loads((archive / "event.json").read_text(encoding="utf-8"))
        self.assertEqual(event["error_count"], 2)
        self.assertEqual(event["last_error_ns"], second)
        self.assertEqual((archive / gap.name).read_bytes(), b"old")
        self.assertEqual(len(list((self.root / "errors").iterdir())), 1)

    def test_non_overlapping_errors_create_separate_archives(self):
        now = time.time_ns()
        first = self.store.mark_error(now - 11 * 60 * 10**9, "先前错误")
        second = self.store.mark_error(now, "新错误")
        self.assertNotEqual(first, second)

    def test_later_error_invalidates_saved_logs_for_merged_window(self):
        now = time.time_ns()
        first_id = self.store.mark_error(now - 8 * 60 * 10**9, "首次失败")
        self.store.start()
        archive = self.root / "errors" / first_id
        manifest = archive / "event.json"
        deadline = time.monotonic() + 3
        while not manifest.exists() and time.monotonic() < deadline:
            Event().wait(0.01)
        self.assertTrue(manifest.exists())
        saved = archive / "logs.json"
        deadline = time.monotonic() + 3
        while not saved.exists() and time.monotonic() < deadline:
            Event().wait(0.01)
        self.assertTrue(saved.exists())

        self.assertEqual(self.store.mark_error(now, "再次失败"), first_id)
        deadline = time.monotonic() + 3
        while saved.exists() and time.monotonic() < deadline:
            Event().wait(0.01)
        self.assertFalse(saved.exists())
        event = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(event["error_count"], 2)
        self.assertEqual(event["last_error_ns"], now)

    def test_existing_archived_frame_is_not_replaced_during_recovery(self):
        archive_id = self.store.mark_error(time.time_ns(), "运行失败")
        filename = self.store.submit(b"new frame")
        destination = self.root / "errors" / archive_id / Path(filename).name
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"archived frame")
        with patch(
            "arknights_mower.utils.screenshot.os.replace",
            side_effect=AssertionError("不应重复替换已归档截图"),
        ):
            self.store._archive_frame(self.store.latest())
            self.store._copy_to_archive(self.root / filename, destination)
        self.assertEqual(destination.read_bytes(), b"archived frame")

    def test_restart_continues_merging_recent_errors(self):
        now = time.time_ns()
        archive_id = self.store.mark_error(now - 2 * 60 * 10**9, "首次失败")
        self.assertEqual(self.store.mark_error(now, "再次失败"), archive_id)
        self.store.start()
        manifest = self.root / "errors" / archive_id / "event.json"
        deadline = time.monotonic() + 3
        event = None
        while time.monotonic() < deadline:
            if manifest.exists():
                event = json.loads(manifest.read_text(encoding="utf-8"))
                if event.get("error_count") == 2:
                    break
            Event().wait(0.01)
        self.assertIsNotNone(event)
        self.assertEqual(event["error_count"], 2)
        self.store.close()

        self.store = ScreenshotStore(self.root, lambda: self.retention, self.logger)
        self.addCleanup(self.store.close)
        self.store.start()
        self.assertEqual(
            self.store.mark_error(time.time_ns(), "第三次失败"), archive_id
        )

    def test_deleted_error_archive_is_not_recreated_by_pending_work(self):
        event_time = time.time_ns()
        archive_id = self.store.mark_error(event_time, "运行失败")
        archive = self.root / "errors" / archive_id
        archive.mkdir(parents=True)
        (archive / "event.json").write_text(
            json.dumps({"time_ns": event_time, "message": "运行失败"}),
            encoding="utf-8",
        )
        (archive / f"{event_time}.jpg").write_bytes(b"archived")

        self.assertTrue(self.store.delete_error_archive(archive_id))
        self.assertFalse(archive.exists())
        self.assertFalse(self.store.delete_error_archive(archive_id))
        self.store.start()
        filename = self.store.submit(b"new frame")
        self.wait_idle()
        self.store._copy_to_archive(self.root / filename, archive / Path(filename).name)
        self.store._save_error_logs(archive_id)
        self.assertFalse(archive.exists())

    def test_error_log_archive_keeps_links_to_copied_screenshots(self):
        event_time = time.time_ns()
        image_time = event_time - 2 * 10**9
        image = self.seed(
            datetime.fromtimestamp(image_time / 10**9).strftime("%Y%m%d-%H"),
            image_time,
        )
        log_folder = self.root.parent / "log"
        log_folder.mkdir()
        when = datetime.fromtimestamp(event_time / 10**9)
        (log_folder / "runtime.log").write_text(
            f"{when:%Y-%m-%d %H:%M:%S} task.py:1 ERROR 任务失败\n",
            encoding="utf-8",
        )
        archive_id = self.store.mark_error(event_time, "任务失败")
        self.store.start()
        archived = self.root / "errors" / archive_id / image.name
        deadline = time.monotonic() + 3
        while not archived.exists() and time.monotonic() < deadline:
            Event().wait(0.01)
        self.assertTrue(archived.exists())
        image.unlink()
        self.store._save_error_logs(archive_id)
        rows = json.loads((archived.parent / "logs.json").read_text(encoding="utf-8"))
        self.assertEqual(rows[0]["screenshot"], f"errors/{archive_id}/{image.name}")

    def test_pending_screenshots_in_error_window_are_not_evicted(self):
        self.limit_store(max_pending_count=2)
        before = self.store.submit(b"before")
        self.store.mark_error(time.time_ns(), "任务失败")
        after = self.store.submit(b"after")
        dropped = self.store.submit(b"later")
        self.assertEqual(
            [frame.filename for frame in self.store._queue], [before, after]
        )
        self.assertEqual(self.store.stats()["dropped"], 1)
        self.store.start()
        self.wait_idle()
        self.assertTrue((self.root / before).exists())
        self.assertTrue((self.root / after).exists())
        self.assertFalse((self.root / dropped).exists())

    def test_restart_continues_error_window(self):
        archive_id = self.store.mark_error(time.time_ns(), "运行出错")
        self.store.start()
        manifest = self.root / "errors" / archive_id / "event.json"
        deadline = time.monotonic() + 3
        while not manifest.exists() and time.monotonic() < deadline:
            Event().wait(0.01)
        self.assertTrue(manifest.exists())
        self.store.close()

        self.store = ScreenshotStore(self.root, lambda: self.retention, self.logger)
        self.addCleanup(self.store.close)
        self.store.start()
        screenshot = self.store.submit(b"after restart")
        self.wait_idle()
        self.assertEqual(
            (self.root / "errors" / archive_id / Path(screenshot).name).read_bytes(),
            b"after restart",
        )

    def test_restart_skips_expired_error_archive(self):
        now = time.time_ns()
        expired_id = str(now - (RUNTIME_LOG_RETENTION_HOURS + 1) * 3600 * 10**9)
        archive = self.root / "errors" / expired_id
        archive.mkdir(parents=True)
        (archive / "event.json").write_text(
            json.dumps({"time_ns": int(expired_id), "message": "旧错误"}),
            encoding="utf-8",
        )
        self.store._recover_error_windows()
        self.assertEqual(self.store._error_windows, [])
        self.assertEqual(list(self.store._archive_queue), [])
        self.assertEqual(self.store._log_archive_queue, [])

    def test_limits_must_be_positive(self):
        for field in ("max_pending_count", "max_pending_bytes"):
            for value in (0, -1):
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(ValueError),
                ):
                    self.limit_store(**{field: value})

    def test_default_count_limit_keeps_recent_frames_and_releases_evicted_data(self):
        oldest = self.store.submit(b"old")
        reference = weakref.ref(self.store.latest())
        files = [self.store.submit(b"new") for _ in range(1000)]
        stats = self.store.stats()
        self.assertEqual(stats["max_pending_count"], 128)
        self.assertEqual(stats["max_pending_bytes"], 64 * 1024**2)
        self.assertEqual(stats["pending_count"], 128)
        self.assertEqual(stats["pending_bytes"], 128 * 3)
        self.assertEqual(stats["dropped"], 873)
        self.assertEqual(stats["dropped_bytes"], 873 * 3)
        self.assertEqual(self.store.latest().filename, files[-1])
        self.assertIsNone(reference())
        self.store.start()
        # Windows CI 写入 128 个文件可能超过 3 秒；此处验证队列与文件完整性。
        self.wait_idle(timeout=15)
        self.assertFalse((self.root / oldest).exists())
        self.assertFalse((self.root / files[-129]).exists())
        self.assertTrue(all((self.root / file).exists() for file in files[-128:]))

    def test_byte_limit_evicts_enough_old_frames_and_keeps_fifo_order(self):
        self.limit_store(max_pending_bytes=10)
        files = [self.store.submit(b"abc") for _ in range(3)]
        latest = self.store.submit(b"1234567")
        stats = self.store.stats()
        self.assertEqual(stats["pending_count"], 2)
        self.assertEqual(stats["pending_bytes"], 10)
        self.assertEqual(stats["dropped"], 2)
        written = []
        with patch.object(
            self.store, "_write", side_effect=lambda f: written.append(f.filename)
        ):
            self.store.start()
            self.wait_idle()
        self.assertEqual(written, [files[-1], latest])

    def test_pressure_preserves_each_important_folder_and_evicts_debug_frames(self):
        self.limit_store(max_pending_count=5)
        important = [
            self.store.submit(b"important", folder)
            for folder in ("run_order", "workshop", "furniture", "solve_captcha")
        ]
        debug = self.store.submit(b"debug", "terminal_main")
        latest = self.store.submit(b"latest")
        self.assertEqual(self.store.stats()["dropped_important"], 0)
        self.store.start()
        self.wait_idle()
        self.assertTrue(all((self.root / file).exists() for file in important))
        self.assertFalse((self.root / debug).exists())
        self.assertTrue((self.root / latest).exists())

    def test_important_frame_can_replace_an_ordinary_frame_in_a_full_queue(self):
        self.limit_store(max_pending_count=1)
        ordinary = self.store.submit(b"ordinary")
        latest = self.store.latest()
        important = self.store.submit(b"order", "run_order")
        self.assertIs(self.store.latest(), latest)
        self.store.start()
        self.wait_idle()
        self.assertFalse((self.root / ordinary).exists())
        self.assertEqual((self.root / important).read_bytes(), b"order")

    def test_full_important_queue_rejects_new_frames_but_updates_preview(self):
        self.limit_store(max_pending_count=1)
        kept = self.store.submit(b"order", "run_order")
        normal = self.store.submit(b"preview")
        rejected = self.store.submit(b"captcha", "solve_captcha")
        self.assertEqual(self.store.latest().filename, normal)
        self.assertEqual(self.store.latest().data, b"preview")
        stats = self.store.stats()
        self.assertEqual(stats["pending_count"], 1)
        self.assertEqual(stats["dropped"], 2)
        self.assertEqual(stats["dropped_important"], 1)
        self.store.start()
        self.wait_idle()
        self.assertTrue((self.root / kept).exists())
        self.assertFalse((self.root / normal).exists())
        self.assertFalse((self.root / rejected).exists())

    def test_oversized_frame_does_not_disturb_queue_or_block_preview(self):
        self.limit_store(max_pending_bytes=5)
        kept = self.store.submit(b"small")
        oversized = self.store.submit(b"oversized")
        self.assertEqual(self.store.latest().filename, oversized)
        self.assertEqual(self.store.stats()["pending_bytes"], 5)
        self.assertEqual(self.store.stats()["dropped_bytes"], 9)
        self.store.start()
        self.wait_idle()
        self.assertTrue((self.root / kept).exists())
        self.assertFalse((self.root / oversized).exists())

    def test_limits_include_inflight_frame_and_rejection_keeps_existing_queue(self):
        self.limit_store(max_pending_count=2, max_pending_bytes=10)
        entered, release = Event(), Event()
        write = self.store._write

        def slow_write(frame):
            entered.set()
            self.assertTrue(release.wait(3))
            write(frame)

        with patch.object(self.store, "_write", side_effect=slow_write):
            active = self.store.submit(b"active")
            self.store.start()
            try:
                self.assertTrue(entered.wait(2))
                old = self.store.submit(b"aa")
                rejected = self.store.submit(b"large")
                self.assertEqual(self.store.stats()["pending_bytes"], 8)
                self.assertEqual([f.filename for f in self.store._queue], [old])
                newest = self.store.submit(b"bb")
                self.assertEqual(self.store.stats()["pending_count"], 2)
                self.assertEqual(self.store.stats()["pending_bytes"], 8)
                self.assertEqual(self.store.stats()["dropped"], 2)
            finally:
                release.set()
                self.wait_idle()
        self.assertEqual(self.store.stats()["saved"], 2)
        self.assertTrue((self.root / active).exists())
        self.assertTrue((self.root / newest).exists())
        self.assertFalse((self.root / old).exists())
        self.assertFalse((self.root / rejected).exists())

    def test_concurrent_producers_respect_limits_and_account_for_every_frame(self):
        self.limit_store(max_pending_count=8, max_pending_bytes=100)
        entered, release = Event(), Event()
        write = self.store._write

        def slow_write(frame):
            entered.set()
            self.assertTrue(release.wait(5))
            write(frame)

        def produce(worker):
            for i in range(50):
                folder = "run_order" if i % 25 == 0 else None
                self.store.submit(f"{worker}-{i}".encode(), folder)
                stats = self.store.stats()
                self.assertLessEqual(stats["pending_count"], 8)
                self.assertLessEqual(stats["pending_bytes"], 100)

        with patch.object(self.store, "_write", side_effect=slow_write):
            active = self.store.submit(b"active")
            self.store.start()
            try:
                self.assertTrue(entered.wait(2))
                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(produce, range(4)))
                expected = {active, *(f.filename for f in self.store._queue)}
            finally:
                release.set()
                self.wait_idle()
        stats = self.store.stats()
        self.assertEqual(stats["saved"] + stats["dropped"], 201)
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(
            {p.relative_to(self.root).as_posix() for p in self.root.rglob("*.jpg")},
            expected,
        )

    def test_drop_warning_is_throttled_without_losing_counts(self):
        self.limit_store(max_pending_count=1)
        with patch("arknights_mower.utils.screenshot.time.monotonic", return_value=100):
            for _ in range(5):
                self.store.submit(b"frame")
        self.logger.warning.assert_called_once()
        with patch("arknights_mower.utils.screenshot.time.monotonic", return_value=131):
            self.store.submit(b"frame")
        self.assertEqual(self.logger.warning.call_count, 2)
        self.assertEqual(self.store.stats()["dropped"], 5)

    def test_close_at_capacity_returns_on_timeout_then_drains_after_disk_recovers(self):
        self.limit_store(max_pending_count=2)
        entered, release = Event(), Event()
        write = self.store._write

        def slow_write(frame):
            entered.set()
            self.assertTrue(release.wait(3))
            write(frame)

        with patch.object(self.store, "_write", side_effect=slow_write):
            self.store.submit(b"active")
            self.store.start()
            closer = Thread(target=lambda: self.store.close(timeout=0.02), daemon=True)
            try:
                self.assertTrue(entered.wait(2))
                self.store.submit(b"queued")
                closer.start()
                closer.join(0.5)
                self.assertFalse(closer.is_alive())
                with self.assertRaises(RuntimeError):
                    self.store.submit(b"closed")
            finally:
                release.set()
                self.store.close()
        self.assertEqual(self.store.stats()["saved"], 2)
        self.assertEqual(self.store.stats()["pending_bytes"], 0)
        self.assertTrue(all(not thread.is_alive() for thread in self.store._threads))

    def test_close_wakes_idle_writer(self):
        self.store.start()
        self.store.close(timeout=0.5)
        self.assertTrue(all(not thread.is_alive() for thread in self.store._threads))

    def test_preview_is_an_immutable_copy_without_filesystem_access(self):
        data = np.asarray([1, 2, 3], dtype=np.uint8)
        with patch.object(Path, "mkdir", side_effect=AssertionError("同步访问磁盘")):
            filename = self.store.submit(data)
        data[:] = 0
        self.assertEqual(self.store.latest().data, b"\x01\x02\x03")
        self.assertEqual(self.store.latest().filename, filename)
        self.assertFalse(self.root.exists())
        self.assertEqual(self.store.stats()["pending_bytes"], 3)

    def test_disabled_history_keeps_preview_without_queueing_or_dropping(self):
        self.retention = 0
        with patch.object(
            Path, "mkdir", side_effect=AssertionError("关闭保存仍访问磁盘")
        ):
            filename = self.store.submit(b"preview")
            for folder in (
                "terminal_main",
                "run_order",
                "workshop",
                "furniture",
                "solve_captcha",
            ):
                self.store.submit(b"debug", folder)
        self.assertEqual(self.store.latest().filename, filename)
        self.assertEqual(self.store.latest().data, b"preview")
        self.assertEqual(self.store.stats()["pending_count"], 0)
        self.assertEqual(self.store.stats()["pending_bytes"], 0)
        self.assertEqual(self.store.stats()["dropped"], 0)
        self.assertFalse(self.root.exists())

    def test_disabled_history_skips_all_folders_and_can_be_reenabled(self):
        self.retention = 0
        files = [
            self.store.submit(b"important", folder)
            for folder in ("run_order", "workshop", "furniture", "solve_captcha")
        ]
        self.store.start()
        self.wait_idle()
        self.assertTrue(all(not (self.root / file).exists() for file in files))
        self.assertEqual(self.store.stats()["saved"], 0)
        self.assertEqual(self.store.last_saved(), "")
        self.retention = 1
        filename = self.store.submit(b"ordinary")
        important = self.store.submit(b"order", "run_order")
        self.wait_idle()
        self.assertEqual((self.root / filename).read_bytes(), b"ordinary")
        self.assertEqual((self.root / important).read_bytes(), b"order")

    def test_disabled_history_archives_current_and_following_error_frames(self):
        self.retention = 0
        current = self.store.submit(b"current screen")
        error_time = time.time_ns()
        archive_id = self.store.mark_error(error_time, "画面异常")
        following = self.store.submit(b"next screen")
        self.store.start()
        self.wait_idle()

        archive = self.root / "errors" / archive_id
        self.assertEqual((archive / Path(current).name).read_bytes(), b"current screen")
        self.assertEqual((archive / Path(following).name).read_bytes(), b"next screen")
        self.assertFalse((self.root / current).exists())
        self.assertFalse((self.root / following).exists())
        self.assertEqual(self.store.last_saved(), "")

        with patch(
            "arknights_mower.utils.screenshot.time.time_ns",
            return_value=error_time + 5 * 60 * 10**9 + 1,
        ):
            late = self.store.submit(b"after window")
        self.assertEqual(self.store.stats()["pending_count"], 0)
        self.assertFalse((archive / Path(late).name).exists())

    def test_queued_frame_is_archived_when_history_is_disabled_at_error(self):
        current = self.store.submit(b"current screen")
        self.retention = 0
        archive_id = self.store.mark_error(time.time_ns(), "画面异常")
        self.assertEqual(self.store.stats()["pending_count"], 1)
        self.store.start()
        self.wait_idle()

        self.assertFalse((self.root / current).exists())
        self.assertEqual(
            (self.root / "errors" / archive_id / Path(current).name).read_bytes(),
            b"current screen",
        )

    def test_delayed_error_record_recovers_frames_captured_after_error(self):
        self.retention = 0
        error_time = time.time_ns()
        with patch(
            "arknights_mower.utils.screenshot.time.time_ns",
            side_effect=(
                error_time - 2 * 10**9,
                error_time + 10**9,
                error_time + 2 * 10**9,
            ),
        ):
            current = self.store.submit(b"error screen")
            first = self.store.submit(b"first after error")
            second = self.store.submit(b"second after error")
        self.assertEqual(self.store.stats()["pending_count"], 0)
        archive_id = self.store.mark_error(error_time, "画面异常")
        self.assertEqual(self.store.stats()["pending_count"], 3)
        self.store.start()
        self.wait_idle()

        archive = self.root / "errors" / archive_id
        self.assertEqual((archive / Path(current).name).read_bytes(), b"error screen")
        self.assertEqual(
            (archive / Path(first).name).read_bytes(), b"first after error"
        )
        self.assertEqual(
            (archive / Path(second).name).read_bytes(), b"second after error"
        )
        self.assertFalse((self.root / current).exists())
        self.assertFalse((self.root / first).exists())
        self.assertFalse((self.root / second).exists())

    def test_disabling_storage_skips_queued_frames_after_current_write(self):
        entered, release = Event(), Event()
        write = self.store._write

        def slow_write(frame):
            entered.set()
            self.assertTrue(release.wait(3))
            write(frame)

        with patch.object(self.store, "_write", side_effect=slow_write):
            active = self.store.submit(b"in flight", "run_order")
            self.store.start()
            try:
                self.assertTrue(entered.wait(2))
                queued = [
                    self.store.submit(b"queued", folder)
                    for folder in (
                        None,
                        "run_order",
                        "workshop",
                        "furniture",
                        "solve_captcha",
                    )
                ]
                self.retention = 0
            finally:
                release.set()
                self.wait_idle()
        self.assertTrue((self.root / active).exists())
        self.assertTrue(all(not (self.root / file).exists() for file in queued))
        self.assertEqual(self.store.stats()["saved"], 1)
        self.assertEqual(self.store.stats()["failed"], 0)
        self.assertEqual(self.store.stats()["dropped"], 0)

    def test_queue_within_capacity_keeps_every_frame_and_important_folder(self):
        files = [self.store.submit(b"jpeg" * 256) for _ in range(30)]
        latest = self.store.latest()
        important = self.store.submit(b"order", "run_order")
        self.assertIs(self.store.latest(), latest)
        self.assertEqual(self.store.stats()["pending_count"], 31)
        self.assertEqual(Path(important).parent.as_posix(), "run_order")
        # 跑单历史支持纳秒时间戳文件名（长度大于 19）。
        self.assertGreater(len(Path(important).name), 19)
        self.store.start()
        self.wait_idle()
        self.assertEqual(self.store.stats()["saved"], 31)
        self.assertTrue(all((self.root / file).exists() for file in files))
        self.assertEqual((self.root / important).read_bytes(), b"order")
        self.assertEqual(self.store.last_saved(), files[-1])

    def test_slow_disk_does_not_block_capture_or_memory_preview(self):
        entered, release = Event(), Event()
        write = self.store._write

        def slow_write(frame):
            entered.set()
            self.assertTrue(release.wait(3))
            write(frame)

        with patch.object(self.store, "_write", side_effect=slow_write):
            self.store.submit(b"first")
            self.store.start()
            try:
                self.assertTrue(entered.wait(2))
                filename = self.store.submit(b"latest")
                self.assertEqual(self.store.latest().filename, filename)
                self.assertEqual(self.store.latest().data, b"latest")
                self.assertEqual(self.store.last_saved(), "")
                self.assertEqual(self.store.stats()["pending_count"], 2)
                self.assertEqual(self.store.stats()["pending_bytes"], 11)
            finally:
                release.set()
                self.wait_idle()

    def test_slow_cleanup_does_not_block_writer(self):
        entered, release = Event(), Event()

        def slow_cleanup():
            entered.set()
            release.wait(3)

        with patch.object(self.store, "cleanup", side_effect=slow_cleanup):
            self.store.start()
            try:
                self.assertTrue(entered.wait(2))
                filename = self.store.submit(b"saved while cleaning")
                self.wait_idle()
                self.assertEqual(
                    (self.root / filename).read_bytes(), b"saved while cleaning"
                )
            finally:
                release.set()

    def test_disk_failure_is_counted_and_next_frame_is_saved(self):
        write = self.store._write
        calls = 0

        def fail_once(frame):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("disk full")
            write(frame)

        with patch.object(self.store, "_write", side_effect=fail_once):
            failed = self.store.submit(b"first", "run_order")
            saved = self.store.submit(b"second")
            self.store.start()
            self.wait_idle()
        self.assertFalse((self.root / failed).exists())
        self.assertEqual((self.root / saved).read_bytes(), b"second")
        self.assertEqual(self.store.stats()["failed"], 1)
        self.logger.error.assert_called_once()
        self.assertIn(failed, self.logger.error.call_args.args[1])

    def test_completed_frame_is_not_retained_by_waiting_writer(self):
        self.store.submit(b"first", "run_order")
        reference = weakref.ref(self.store._queue[0])
        self.store.start()
        self.wait_idle()
        self.assertIsNone(reference())

    def test_atomic_write_and_cleanup_leave_inflight_file_alone(self):
        self.retention = 0
        filename = self.store.submit(b"complete image")
        frame = self.store.latest()
        replace = os.replace

        def inspect_before_publish(source, destination):
            self.assertFalse(destination.exists())
            self.assertEqual(source.read_bytes(), b"complete image")
            self.store.cleanup()
            self.assertTrue(source.exists())
            replace(source, destination)

        with patch(
            "arknights_mower.utils.screenshot.os.replace",
            side_effect=inspect_before_publish,
        ):
            self.store._write(frame)
        self.assertEqual((self.root / filename).read_bytes(), b"complete image")
        self.assertEqual(list(self.root.rglob("*.tmp")), [])

    def test_failed_atomic_publish_removes_temporary_file(self):
        self.store.submit(b"image")
        with (
            patch(
                "arknights_mower.utils.screenshot.os.replace",
                side_effect=PermissionError("denied"),
            ),
            self.assertRaises(PermissionError),
        ):
            self.store._write(self.store.latest())
        self.assertEqual(list(self.root.rglob("*.tmp")), [])
        self.assertEqual(list(self.root.rglob("*.jpg")), [])

    def test_cleanup_uses_retention_and_preserves_unrelated_and_important_files(self):
        now = time.time_ns()
        old = now - 2 * 3600 * 10**9
        hour = datetime.fromtimestamp(old / 10**9).strftime("%Y%m%d-%H")
        expired = self.seed(hour, old)
        legacy = self.seed("", old)
        fresh = self.seed("", now)
        debug = self.seed("terminal_main", old)
        self.seed("run_order", old)
        unknown = self.root / "notes.txt"
        unknown.write_text("keep")
        self.store.cleanup()
        self.assertFalse(expired.exists())
        self.assertFalse(expired.parent.exists())
        self.assertFalse(legacy.exists())
        self.assertFalse(debug.exists())
        self.assertTrue(fresh.exists())
        self.assertTrue(unknown.exists())
        self.assertEqual(len(list((self.root / "run_order").glob("*.jpg"))), 1)

    def test_cleanup_expires_error_archives_with_runtime_logs(self):
        now = time.time_ns()
        hour_ns = 3600 * 10**9
        cutoff = now - RUNTIME_LOG_RETENTION_HOURS * hour_ns
        archive_root = self.root / "errors"
        expired = archive_root / str(cutoff - 1)
        recent = archive_root / str(cutoff)
        extended = archive_root / str(cutoff - hour_ns)
        unrelated = archive_root / "notes"
        for archive in (expired, recent, extended):
            archive.mkdir(parents=True)
            last_error = now if archive == extended else int(archive.name)
            (archive / "event.json").write_text(
                json.dumps(
                    {
                        "time_ns": int(archive.name),
                        "last_error_ns": last_error,
                        "message": "测试错误",
                    }
                ),
                encoding="utf-8",
            )
            (archive / "frame.jpg").write_bytes(b"frame")
        unrelated.mkdir()
        (unrelated / "keep.txt").write_text("keep", encoding="utf-8")
        ordinary = self.seed("", now - 2 * hour_ns)
        with patch("arknights_mower.utils.screenshot.time.time_ns", return_value=now):
            self.store.cleanup()
        self.assertFalse(expired.exists())
        self.assertTrue(recent.exists())
        self.assertTrue(extended.exists())
        self.assertTrue(unrelated.exists())
        self.assertFalse(ordinary.exists())

    def test_important_retention_keeps_latest_100_including_new_arrival(self):
        old = time.time_ns() - 2 * 3600 * 10**9
        paths = [self.seed("run_order", old + i) for i in range(105)]
        images = self.store._images
        scans = 0

        def with_new_arrival(folder):
            nonlocal scans
            scans += 1
            if scans == 2:
                self.seed("run_order", old + 200)
            yield from images(folder)

        with patch.object(self.store, "_images", side_effect=with_new_arrival):
            self.store._remove_expired(self.root / "run_order", 0, keep_latest=100)
        self.assertTrue(all(not path.exists() for path in paths[:5]))
        self.assertTrue(all(path.exists() for path in paths[5:]))
        self.assertTrue((self.root / "run_order" / f"{old + 200}.jpg").exists())

    def test_furniture_cleanup_retains_latest_100_evidence_frames(self):
        old = time.time_ns() - 2 * 3600 * 10**9
        paths = [self.seed("furniture", old + i) for i in range(105)]
        self.store.cleanup()
        self.assertTrue(all(not path.exists() for path in paths[:5]))
        self.assertTrue(all(path.exists() for path in paths[5:]))

    def test_cleanup_failure_does_not_prevent_later_cleanup(self):
        expired = self.seed("", time.time_ns() - 2 * 3600 * 10**9)
        with patch(
            "arknights_mower.utils.screenshot.os.scandir",
            side_effect=PermissionError("temporarily unavailable"),
        ):
            self.store.cleanup()
        self.assertEqual(self.store.stats()["cleanup_failed"], 1)
        self.store.cleanup()
        self.assertFalse(expired.exists())

    def test_close_flushes_queue_and_stops_both_threads(self):
        filename = self.store.submit(b"last frame")
        self.store.start()
        self.store.close()
        self.assertEqual((self.root / filename).read_bytes(), b"last frame")
        self.assertTrue(all(not thread.is_alive() for thread in self.store._threads))


class ScreenshotMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "screenshots"
        self.logger = Mock()
        self.retention = 1
        self.store = ScreenshotStore(self.root, lambda: self.retention, self.logger)
        self.addCleanup(self.store.close)
        self.now = 0
        self.epoch_ns = time.time_ns()

    def run_cleaner_until(self, end, on_wait=None):
        calls = []
        cleanup = self.store.cleanup

        def track_cleanup():
            calls.append(self.now)
            return cleanup()

        def advance(seconds):
            self.now = min(end, self.now + seconds)
            if on_wait:
                on_wait()
            return self.now >= end

        with (
            patch(
                "arknights_mower.utils.screenshot.time.monotonic",
                side_effect=lambda: self.now,
            ),
            patch(
                "arknights_mower.utils.screenshot.time.time_ns",
                side_effect=lambda: self.epoch_ns + int(self.now * 10**9),
            ),
            patch.object(self.store._stop, "wait", side_effect=advance),
            patch.object(self.store, "cleanup", side_effect=track_cleanup),
        ):
            self.store._cleaner()
        return calls

    def seed(self, timestamp):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{timestamp}.jpg"
        path.write_bytes(b"history")
        return path

    def test_empty_idle_store_scans_hourly_without_status_noise(self):
        calls = self.run_cleaner_until(7201)
        self.assertEqual(calls, [0, 3600, 7200])
        self.logger.debug.assert_not_called()

    def test_expired_history_is_removed_on_hourly_cleanup(self):
        self.retention = 0.02
        path = self.seed(self.epoch_ns - 10 * 10**9)

        def before_cleanup():
            if self.now < 3600:
                self.assertTrue(path.exists())

        calls = self.run_cleaner_until(7201, before_cleanup)
        self.assertEqual(calls, [0, 3600, 7200])
        self.assertFalse(path.exists())
        self.logger.debug.assert_not_called()

    def test_retention_does_not_change_hourly_cleanup_interval(self):
        for retention in (0, 0.02, 0.1, 1, 24):
            with self.subTest(retention=retention):
                self.now = 0
                self.retention = retention
                self.seed(self.epoch_ns + 48 * 3600 * 10**9)
                calls = self.run_cleaner_until(7201)
                self.assertEqual(calls, [0, 3600, 7200])

    def test_retention_changes_take_effect_at_next_hourly_cleanup(self):
        path = self.seed(self.epoch_ns - 120 * 10**9)

        def shorten():
            if self.now >= 60:
                self.retention = 0.02

        calls = self.run_cleaner_until(3601, shorten)
        self.assertEqual(calls, [0, 3600])
        self.assertFalse(path.exists())

    def test_cleanup_errors_are_reported_and_retried(self):
        with patch(
            "arknights_mower.utils.screenshot.os.scandir",
            side_effect=PermissionError("denied"),
        ):
            calls = self.run_cleaner_until(7201)
        self.assertEqual(calls, [0, 3600, 7200])
        self.assertEqual(self.store.stats()["cleanup_failed"], 3)
        self.assertEqual(self.logger.error.call_count, 3)
        self.assertEqual(self.logger.debug.call_count, 3)

    def test_changing_cleanup_duration_alone_does_not_print_status(self):
        stats = self.store.stats()
        with patch.object(
            self.store,
            "stats",
            side_effect=[
                {**stats, "cleanup_ms": value} for value in (12.2, 8.53, 64.96)
            ],
        ):
            for _ in range(3):
                self.store._report_status()
        self.logger.debug.assert_not_called()

    def test_new_activity_is_reported_once_and_pending_work_remains_visible(self):
        stats = self.store.stats()
        states = [
            {**stats, "saved": 1},
            {**stats, "saved": 1, "cleanup_ms": 10},
            {**stats, "saved": 1, "pending_count": 1, "pending_bytes": 10},
            {**stats, "saved": 1, "pending_count": 1, "pending_bytes": 10},
            {**stats, "saved": 2},
            {**stats, "saved": 2, "cleanup_ms": 20},
        ]
        with patch.object(self.store, "stats", side_effect=states):
            for _ in states:
                self.store._report_status()
        self.assertEqual(self.logger.debug.call_count, 4)


class ScreenshotRouteTests(unittest.TestCase):
    def setUp(self):
        import server

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ScreenshotStore(Path(self.tmp.name), lambda: 1)
        # 使用实际路由，确保覆盖 server.py 上的 require_token 装饰器接线。
        self.app = server.app
        token_patch = patch.object(self.app, "token", "test-token", create=True)
        token_patch.start()
        self.addCleanup(token_patch.stop)
        self.client = self.app.test_client()
        self.headers = {"token": "test-token"}
        store_patch = patch.object(views, "_get_store", return_value=self.store)
        store_patch.start()
        self.addCleanup(store_patch.stop)

    def test_preview_requires_configured_token(self):
        self.assertEqual(self.client.get("/screenshot/latest").status_code, 403)

    def test_wrong_token_cannot_read_a_frame_or_use_a_matching_etag(self):
        self.store.submit(b"private frame")
        headers = {
            "token": "wrong-token",
            "If-None-Match": f'"{self.store.latest().captured_ns}"',
        }
        with patch.object(self.store, "latest") as latest:
            response = self.client.get("/screenshot/latest", headers=headers)
        self.assertEqual(response.status_code, 403)
        latest.assert_not_called()

    def test_preview_without_configured_token(self):
        del self.app.token
        try:
            self.store.submit(b"frame")
            response = self.client.get("/screenshot/latest")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"frame")
        finally:
            self.app.token = "test-token"

    def test_no_frame_returns_no_content(self):
        response = self.client.get("/screenshot/latest", headers=self.headers)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_preview_still_works_with_storage_disabled(self):
        self.store.retention_hours = lambda: 0
        self.store.submit(b"preview without disk")
        response = self.client.get("/screenshot/latest", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"preview without disk")
        self.assertEqual(self.store.stats()["pending_count"], 0)

    def test_preview_before_write_and_etag_when_unchanged(self):
        self.store.submit(b"jpeg bytes")
        with patch.object(Path, "open", side_effect=AssertionError("预览读取磁盘")):
            response = self.client.get("/screenshot/latest", headers=self.headers)
        self.assertEqual(response.data, b"jpeg bytes")
        self.assertEqual(response.mimetype, "image/jpeg")
        etag = response.headers["ETag"]
        conditional = {**self.headers, "If-None-Match": etag}
        response = self.client.get("/screenshot/latest", headers=conditional)
        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.data, b"")
        self.store.submit(b"next frame")
        response = self.client.get("/screenshot/latest", headers=conditional)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"next frame")
        self.assertNotEqual(response.headers["ETag"], etag)


if __name__ == "__main__":
    unittest.main()
