"""在临时目录中验证截图读写隔离、故障恢复和清理并发。"""

import os
import tempfile
import time
import unittest
import weakref
from datetime import datetime
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

import numpy as np
from flask import Flask

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

    def test_preview_is_an_immutable_copy_without_filesystem_access(self):
        data = np.asarray([1, 2, 3], dtype=np.uint8)
        with patch.object(Path, "mkdir", side_effect=AssertionError("同步访问磁盘")):
            filename = self.store.submit(data)
        data[:] = 0
        self.assertEqual(self.store.latest().data, b"\x01\x02\x03")
        self.assertEqual(self.store.latest().filename, filename)
        self.assertFalse(self.root.exists())
        self.assertEqual(self.store.stats()["pending_bytes"], 3)

    def test_unbounded_queue_keeps_every_frame_and_preserves_important_folder(self):
        files = [self.store.submit(b"jpeg" * 256) for _ in range(300)]
        latest = self.store.latest()
        important = self.store.submit(b"order", "run_order")
        self.assertIs(self.store.latest(), latest)
        self.assertEqual(self.store.stats()["pending_count"], 301)
        self.assertEqual(Path(important).parent.as_posix(), "run_order")
        # 跑单历史支持纳秒时间戳文件名（长度大于 19）。
        self.assertGreater(len(Path(important).name), 19)
        self.store.start()
        self.wait_idle()
        self.assertEqual(self.store.stats()["saved"], 301)
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
        reference = weakref.ref(self.store.queue.queue[0])
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


class ScreenshotRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ScreenshotStore(Path(self.tmp.name), lambda: 1)
        app = Flask(__name__)
        app.token = "test-token"
        app.add_url_rule(
            "/screenshot/latest", view_func=views.latest_screenshot_response
        )
        self.client = app.test_client()
        self.headers = {"token": "test-token"}
        store_patch = patch.object(views, "_get_store", return_value=self.store)
        store_patch.start()
        self.addCleanup(store_patch.stop)

    def test_preview_requires_configured_token(self):
        self.assertEqual(self.client.get("/screenshot/latest").status_code, 403)

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
