"""在临时目录中验证截图读写隔离、故障恢复和清理并发。"""

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

    def wait_idle(self):
        deadline = time.monotonic() + 3
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
        self.wait_idle()
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
        self.limit_store(max_pending_count=4)
        important = [
            self.store.submit(b"important", folder)
            for folder in ("run_order", "workshop", "solve_captcha")
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
            self.store.submit(b"debug", "terminal_main")
        self.assertEqual(self.store.latest().filename, filename)
        self.assertEqual(self.store.latest().data, b"preview")
        self.assertEqual(self.store.stats()["pending_count"], 0)
        self.assertEqual(self.store.stats()["pending_bytes"], 0)
        self.assertEqual(self.store.stats()["dropped"], 0)
        self.assertFalse(self.root.exists())

    def test_disabled_history_preserves_important_frames_and_can_be_reenabled(self):
        self.retention = 0
        files = [
            self.store.submit(b"important", folder)
            for folder in ("run_order", "workshop", "solve_captcha")
        ]
        self.store.start()
        self.wait_idle()
        self.assertTrue(all((self.root / file).exists() for file in files))
        self.assertEqual(self.store.last_saved(), "")
        self.retention = 1
        filename = self.store.submit(b"ordinary")
        self.wait_idle()
        self.assertEqual((self.root / filename).read_bytes(), b"ordinary")

    def test_cleanup_resumes_after_new_write_in_an_empty_store(self):
        first, resumed = Event(), Event()
        cleanup = self.store.cleanup

        def track_cleanup():
            if first.is_set():
                resumed.set()
            result = cleanup()
            first.set()
            return result

        with patch.object(self.store, "cleanup", side_effect=track_cleanup):
            self.store.start()
            self.assertTrue(first.wait(2))
            self.assertFalse(resumed.wait(0.06))
            self.store.submit(b"new history")
            self.wait_idle()
            self.assertTrue(resumed.wait(2))

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

    def test_short_retention_cleans_until_history_expires_then_backs_off(self):
        self.retention = 0.02
        path = self.seed(self.epoch_ns - 10 * 10**9)
        calls = self.run_cleaner_until(900)
        self.assertEqual(calls, [0, 60, 120])
        self.assertFalse(path.exists())
        self.logger.debug.assert_not_called()

    def test_cleanup_interval_adapts_to_retention_without_thirty_second_scans(self):
        for retention, interval in ((0.1, 180), (1, 1800), (24, 3600)):
            with self.subTest(retention=retention):
                self.now = 0
                self.retention = retention
                self.seed(self.epoch_ns + 48 * 3600 * 10**9)
                calls = self.run_cleaner_until(interval * 2 + 1)
                self.assertEqual(calls, [0, interval, interval * 2])

    def test_shortening_retention_triggers_cleanup_at_next_poll(self):
        path = self.seed(self.epoch_ns - 120 * 10**9)

        def shorten():
            if self.now >= 60:
                self.retention = 0.02

        calls = self.run_cleaner_until(121, shorten)
        self.assertEqual(calls, [0, 60])
        self.assertFalse(path.exists())

    def test_cleanup_errors_are_reported_and_retried(self):
        with patch(
            "arknights_mower.utils.screenshot.os.scandir",
            side_effect=PermissionError("denied"),
        ):
            self.retention = 0.02
            calls = self.run_cleaner_until(121)
        self.assertEqual(calls, [0, 60, 120])
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
