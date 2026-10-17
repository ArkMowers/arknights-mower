"""Screenshot pipeline contracts with controlled encoding, I/O and time."""

import gc
import tempfile
import time
import unittest
import weakref
from pathlib import Path
from threading import Event, Thread, current_thread
from unittest.mock import Mock, patch

import numpy as np

from arknights_mower.utils.screenshot import ScreenshotStore


def wait_until(predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        Event().wait(0.001)
    if not predicate():
        raise AssertionError("background work did not finish")


class ScreenshotPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def store(self, retention=1, **options):
        store = ScreenshotStore(self.root, lambda: retention, logger=Mock(), **options)
        self.addCleanup(store.close)
        return store

    @staticmethod
    def frame(value):
        return np.full((2, 3, 3), value, dtype=np.uint8)

    def test_pending_preview_is_replaced_without_waiting_for_encoder(self):
        entered, release = Event(), Event()
        encoded = []

        def encode(rgb):
            value = int(rgb[0, 0, 0])
            preview = current_thread().name == "screenshot-preview"
            if preview:
                encoded.append(value)
            if preview and value == 1:
                entered.set()
                if not release.wait(3):
                    raise TimeoutError("test encoder stuck")
            return bytes([value])

        store = self.store(retention=0, encoder=encode)
        original_writer = store._writer

        def writer_after_preview():
            self.assertTrue(entered.wait(2))
            original_writer()

        store._writer = writer_after_preview
        store.start()
        try:
            store.submit_frame(self.frame(1))
            self.assertTrue(entered.wait(2))
            store.submit_frame(self.frame(2))
            newest = self.frame(3)
            filename = store.submit_frame(newest)
            newest[:] = 9
            self.assertEqual(store.stats()["preview_pending_count"], 1)
            self.assertEqual(store.stats()["preview_replaced"], 1)
        finally:
            release.set()
        wait_until(lambda: store.latest() and store.latest().filename == filename)
        self.assertEqual(store.latest().data, b"\x03")
        self.assertEqual(encoded.count(1), 1)
        self.assertNotIn(2, encoded)
        wait_until(lambda: store.stats()["pending_count"] == 0)
        self.assertEqual(store.stats()["pending_count"], 0)
        self.assertEqual(list(self.root.glob("**/*.jpg")), [])

    def test_preview_and_history_share_one_encoding_of_the_same_frame(self):
        both_consumers, release = Event(), Event()
        encodings = []

        def encode(rgb):
            encodings.append(int(rgb[0, 0, 0]))
            self.assertTrue(release.wait(3))
            return b"shared JPEG"

        store = self.store(encoder=encode)
        original = store._encode
        consumers = []

        def observe(frame, **kwargs):
            consumers.append(current_thread().name)
            if len(consumers) == 2:
                both_consumers.set()
            return original(frame, **kwargs)

        store._encode = observe
        store.start()
        try:
            filename = store.submit_frame(self.frame(1))
            self.assertTrue(both_consumers.wait(2))
        finally:
            release.set()
        wait_until(lambda: store.stats()["pending_count"] == 0)
        wait_until(lambda: store.latest() and store.latest().filename == filename)
        self.assertEqual(encodings, [1])
        self.assertEqual((self.root / filename).read_bytes(), store.latest().data)

    def test_slow_writer_does_not_retain_the_private_rgb_snapshot(self):
        entered, release = Event(), Event()
        raw_references = []

        def encode(rgb):
            raw_references.append(weakref.ref(rgb))
            return b"JPEG"

        def write(frame):
            entered.set()
            self.assertTrue(release.wait(3))

        store = self.store(encoder=encode, writer=write)
        store.start()
        try:
            store.submit_frame(np.zeros((1080, 1920, 3), np.uint8))
            self.assertTrue(entered.wait(2))
            wait_until(lambda: store.stats()["preview_active_count"] == 0)
            gc.collect()
            self.assertTrue(raw_references)
            self.assertTrue(all(reference() is None for reference in raw_references))
            self.assertEqual(store.stats()["raw_pending_bytes"], 0)
            self.assertEqual(store.stats()["pending_bytes"], len(b"JPEG"))
        finally:
            release.set()

    def test_shared_encoding_failure_is_not_retried_or_retained_by_error_logging(self):
        raw_references = []

        def encode(rgb):
            raw_references.append(weakref.ref(rgb))
            raise ValueError("broken encoder")

        store = self.store(encoder=encode)
        store.start()
        store.submit_frame(self.frame(1))
        wait_until(lambda: store.stats()["pending_count"] == 0)
        wait_until(
            lambda: (
                store.stats()["preview_pending_count"] == 0
                and store.stats()["preview_active_count"] == 0
            )
        )
        gc.collect()
        self.assertEqual(len(raw_references), 1)
        self.assertTrue(all(reference() is None for reference in raw_references))
        self.assertTrue(store.logger.error.call_args_list)
        self.assertEqual(store.stats()["encode_failed"], 1)
        self.assertIsNone(store.latest())

    def test_oversized_encoding_keeps_preview_without_exceeding_history_budget(self):
        encoded = b"JPEG" * 10
        store = self.store(encoder=lambda rgb: encoded, max_pending_bytes=36)
        store.start()
        filename = store.submit_frame(self.frame(1))
        wait_until(lambda: store.stats()["pending_count"] == 0)
        wait_until(lambda: store.latest() is not None)
        self.assertEqual(store.latest().data, encoded)
        self.assertFalse((self.root / filename).exists())
        self.assertEqual(store.stats()["pending_bytes"], 0)
        self.assertEqual(store.stats()["dropped"], 1)

    def test_encoding_growth_evicts_ordinary_waiting_frame_before_exceeding_budget(
        self,
    ):
        entered, release = Event(), Event()
        written = []

        def write(frame):
            written.append(frame.data)
            if frame.data[0] == 1:
                entered.set()
                self.assertTrue(release.wait(3))

        store = self.store(
            encoder=lambda rgb: bytes([int(rgb[0, 0, 0])]) * 20,
            writer=write,
            max_pending_bytes=54,
        )
        store.submit_frame(self.frame(1), "run_order")
        store.submit_frame(self.frame(2), "debug")
        store.submit_frame(self.frame(3), "debug")
        store.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(store.stats()["pending_bytes"], 38)
            self.assertEqual(store.stats()["dropped"], 1)
        finally:
            release.set()
        wait_until(lambda: store.stats()["pending_count"] == 0)
        self.assertEqual([data[0] for data in written], [1, 3])

    def test_encoding_growth_preserves_other_important_pending_frames(self):
        written = []
        store = self.store(
            encoder=lambda rgb: bytes([int(rgb[0, 0, 0])]) * 20,
            writer=lambda frame: written.append(frame.data[0]),
            max_pending_bytes=54,
        )
        store.submit_frame(self.frame(1), "debug")
        store.submit_frame(self.frame(2), "run_order")
        store.submit_frame(self.frame(3), "workshop")
        store.start()
        wait_until(lambda: store.stats()["pending_count"] == 0)
        self.assertEqual(written, [2, 3])
        self.assertEqual(store.stats()["dropped"], 1)
        self.assertEqual(store.stats()["dropped_important"], 0)
        self.assertEqual(store.stats()["pending_bytes"], 0)

    def test_close_releases_writer_waiting_for_preview_owned_encoding(self):
        entered, release = Event(), Event()

        def encode(rgb):
            entered.set()
            self.assertTrue(release.wait(3))
            return b"late shared result"

        store = self.store(encoder=encode)
        original_writer = store._writer

        def writer_after_preview():
            self.assertTrue(entered.wait(2))
            original_writer()

        store._writer = writer_after_preview
        store.start()
        try:
            filename = store.submit_frame(self.frame(1))
            self.assertTrue(entered.wait(2))
            wait_until(lambda: store._active is not None)
            started = time.monotonic()
            result = store.close(timeout=0.01)
            self.assertLess(time.monotonic() - started, 0.5)
            self.assertIn("screenshot-preview", result["remaining_threads"])
            wait_until(lambda: store.stats()["pending_count"] == 0)
            self.assertFalse(release.is_set())
        finally:
            release.set()
        self.assertEqual(store.close()["remaining_threads"], [])
        self.assertEqual(store.stats()["shutdown_dropped"], 1)
        self.assertEqual(store.stats()["pending_bytes"], 0)
        self.assertIsNone(store.latest())
        self.assertFalse((self.root / filename).exists())

    def test_preview_completion_after_history_eviction_does_not_change_its_charge(self):
        disk_entered, disk_release = Event(), Event()
        encoder_entered, encoder_release = Event(), Event()

        def encode(rgb):
            value = int(rgb[0, 0, 0])
            if value == 2:
                encoder_entered.set()
                self.assertTrue(encoder_release.wait(3))
            return bytes([value])

        def write(frame):
            if frame.data == b"\x01":
                disk_entered.set()
                self.assertTrue(disk_release.wait(3))

        store = self.store(encoder=encode, writer=write, max_pending_count=2)
        store.start()
        try:
            store.submit_frame(self.frame(1), "run_order")
            self.assertTrue(disk_entered.wait(2))
            store.submit_frame(self.frame(2))
            self.assertTrue(encoder_entered.wait(2))
            latest = store.submit_frame(self.frame(3))
            encoder_release.set()
            wait_until(lambda: store.latest() and store.latest().filename == latest)
            self.assertEqual(store.stats()["pending_count"], 2)
            self.assertEqual(store.stats()["pending_bytes"], 2)
            self.assertEqual(store.stats()["dropped"], 1)
        finally:
            encoder_release.set()
            disk_release.set()
        wait_until(lambda: store.stats()["pending_count"] == 0)
        self.assertEqual(store.stats()["pending_bytes"], 0)

    def test_writer_encoding_old_preview_does_not_block_a_newer_preview(self):
        entered, release, preview_tried = Event(), Event(), Event()

        def encode(rgb):
            value = int(rgb[0, 0, 0])
            if value == 1:
                entered.set()
                self.assertTrue(release.wait(3))
            return bytes([value])

        store = self.store(encoder=encode)
        original = store._preview_encoder
        original_encode = store._encode

        def observe_preview(frame, **kwargs):
            if kwargs.get("preview"):
                preview_tried.set()
            return original_encode(frame, **kwargs)

        store._encode = observe_preview

        def preview_after_writer():
            self.assertTrue(entered.wait(2))
            original()

        store._preview_encoder = preview_after_writer
        store.start()
        try:
            store.submit_frame(self.frame(1))
            self.assertTrue(entered.wait(2))
            self.assertTrue(preview_tried.wait(1))
            newest = store.submit_frame(self.frame(2))
            wait_until(lambda: store.latest() and store.latest().filename == newest)
            self.assertFalse(release.is_set())
        finally:
            release.set()
        wait_until(lambda: store.stats()["pending_count"] == 0)
        self.assertEqual(store.latest().filename, newest)

    def test_slow_disk_bounds_raw_history_but_does_not_delay_preview(self):
        entered, release = Event(), Event()
        written = []
        now = [10.0]

        def encode(rgb):
            return bytes([int(rgb[0, 0, 0])])

        def write(frame):
            if frame.data == b"\x01":
                entered.set()
                if not release.wait(3):
                    raise TimeoutError("test disk stuck")
            written.append(frame.data)

        store = self.store(
            encoder=encode,
            writer=write,
            clock=lambda: now[0],
            max_pending_count=2,
            max_pending_bytes=36,
        )
        store.start()
        try:
            store.submit_frame(self.frame(1), capture_ms=12)
            self.assertTrue(entered.wait(2))
            now[0] = 12
            store.submit_frame(self.frame(2))
            now[0] = 15
            last = store.submit_frame(self.frame(3))
            wait_until(lambda: store.latest() and store.latest().filename == last)
            stats = store.stats()
            self.assertEqual(stats["pending_count"], 2)
            self.assertEqual(stats["pending_bytes"], 2)
            self.assertEqual(stats["raw_pending_count"], 0)
            self.assertEqual(stats["dropped"], 1)
            self.assertEqual(stats["oldest_pending_age"], 5)
            self.assertEqual(stats["capture_ms"], 12)
            now[0] = 18
            self.assertEqual(store.stats()["preview_age"], 3)
        finally:
            release.set()
        wait_until(lambda: store.stats()["pending_count"] == 0)
        self.assertEqual(written, [b"\x01", b"\x03"])
        self.assertEqual(store.stats()["write_ms"], 0)
        self.assertEqual(store.stats()["latest_persisted_age"], 3)
        self.assertEqual(store.stats()["oldest_pending_age"], 0)

    def test_preview_slot_never_moves_back_to_an_older_capture(self):
        from arknights_mower.utils.screenshot import Screenshot

        store = self.store(
            retention=0,
            encoder=lambda rgb: b"jpeg",
            wall_time_ns=lambda: 10**18,
        )
        # Admission keeps capture times ordered, so the only way an older frame
        # can ask for the slot is when it carries that older time itself. The
        # slots that feed the preview are exactly the shapes exercised below.
        with store._lock:
            older = Screenshot(
                "run_order/1000000000000000001.jpg",
                b"backlog",
                10**18 - 1,
                0.0,
                True,
                False,
            )
            newer = Screenshot(
                "run_order/1000000000000000002.jpg",
                b"newer",
                10**18 + 2,
                0.0,
                True,
                False,
            )
        store._latest = newer
        store.submit(older.data)
        self.assertEqual(store.latest().data, b"newer")
        store._preview_pending = older
        store.submit(b"backlog again")
        self.assertEqual(store.latest().data, b"newer")
        self.assertEqual(store.stats()["preview_pending_count"], 0)
        self.assertEqual(store.stats()["preview_replaced"], 1)

    def test_close_discards_backlog_after_deadline_and_records_active_io(self):
        entered, release = Event(), Event()
        written = []

        def write(frame):
            entered.set()
            if not release.wait(3):
                raise TimeoutError("test disk stuck")
            written.append(frame.data)

        store = self.store(writer=write)
        store.start()
        try:
            store.submit(b"active")
            self.assertTrue(entered.wait(2))
            store.submit(b"waiting")
            result = store.close(timeout=0.01)
            self.assertIn("screenshot-writer", result["remaining_threads"])
            self.assertEqual(store.stats()["shutdown_dropped"], 1)
            self.assertEqual(store.stats()["pending_count"], 1)
            with self.assertRaises(RuntimeError):
                store.submit_frame(self.frame(2))
            store.mark_error(time.time_ns(), "closed")
            self.assertEqual(store.stats()["archive_pending_count"], 0)
        finally:
            release.set()
        self.assertEqual(store.close()["remaining_threads"], [])
        self.assertEqual(written, [b"active"])
        self.assertEqual(store.stats()["pending_bytes"], 0)

    def test_close_before_start_releases_all_pending_frames(self):
        store = self.store()
        store.submit_frame(self.frame(1))
        store.mark_error(time.time_ns(), "pending")
        result = store.close()
        self.assertEqual(result["remaining_threads"], [])
        self.assertEqual(store.stats()["pending_count"], 0)
        self.assertEqual(store.stats()["preview_pending_count"], 0)
        self.assertEqual(store.stats()["archive_pending_count"], 0)
        self.assertEqual(store.stats()["shutdown_dropped"], 1)
        self.assertEqual(store.stats()["shutdown_preview_dropped"], 1)
        store.start()
        self.assertEqual(store.close()["remaining_threads"], [])

    def test_slow_history_encoder_cannot_hold_up_new_preview(self):
        entered, release = Event(), Event()
        written = []

        def encode(rgb):
            value = int(rgb[0, 0, 0])
            if value == 1:
                entered.set()
                if not release.wait(3):
                    raise TimeoutError("test encoder stuck")
            return bytes([value])

        store = self.store(encoder=encode, writer=lambda f: written.append(f.data))
        store.start()
        try:
            store.submit_frame(self.frame(1), "run_order")
            self.assertTrue(entered.wait(2))
            name = store.submit_frame(self.frame(2))
            wait_until(lambda: store.latest() and store.latest().filename == name)
            self.assertEqual(store.latest().data, b"\x02")
            self.assertEqual(written, [])
            self.assertEqual(store.stats()["raw_pending_bytes"], 18)
            self.assertEqual(store.stats()["pending_bytes"], 19)
        finally:
            release.set()
        wait_until(lambda: store.stats()["pending_count"] == 0)
        self.assertEqual(written, [b"\x01", b"\x02"])

    def test_fake_clock_distinguishes_queue_encoding_write_and_frame_ages(self):
        now = [10.0]

        def encode(rgb):
            now[0] += 0.025
            return b"jpeg"

        def write(frame):
            now[0] += 0.1

        store = self.store(
            encoder=encode,
            writer=write,
            clock=lambda: now[0],
            wall_time_ns=lambda: 1000000000000000000,
        )
        # A special-purpose frame has no competing preview encoder clock.
        store.submit_frame(self.frame(1), "run_order")
        now[0] = 12.0
        store.start()
        wait_until(lambda: store.stats()["pending_count"] == 0)
        stats = store.stats()
        self.assertEqual(stats["queue_wait_ms"], 2000)
        self.assertEqual(stats["encode_ms"], 25)
        self.assertEqual(stats["write_ms"], 100)
        self.assertIsNone(stats["preview_age"])

    def test_failed_encoder_and_disk_release_capacity_without_retries(self):
        written = []

        def encode(rgb):
            value = int(rgb[0, 0, 0])
            if value == 1:
                raise ValueError("bad JPEG")
            return bytes([value])

        def write(frame):
            if frame.data == b"\x02":
                raise OSError("disk full")
            written.append(frame.data)

        store = self.store(encoder=encode, writer=write)
        for value in (1, 2, 3):
            store.submit_frame(self.frame(value), "run_order")
        store.start()
        wait_until(lambda: store.stats()["pending_count"] == 0)
        self.assertEqual(written, [b"\x03"])
        self.assertEqual(store.stats()["encode_failed"], 1)
        self.assertEqual(store.stats()["failed"], 2)
        self.assertEqual(store.stats()["saved"], 1)
        self.assertEqual(store.stats()["raw_pending_bytes"], 0)

    def test_error_storm_metadata_is_bounded_and_dropped_on_close(self):
        store = self.store(max_pending_count=2)
        for timestamp in range(100):
            store.mark_error(timestamp, "failure")
        stats = store.stats()
        self.assertEqual(stats["archive_pending_count"], 2)
        self.assertEqual(stats["archive_log_pending_count"], 1)
        self.assertEqual(stats["archive_window_count"], 1)
        self.assertEqual(stats["archive_dropped"], 98)
        store.close()
        self.assertEqual(store.stats()["shutdown_archive_dropped"], 3)

    def test_rgb_recent_cache_retains_sixteen_encoded_full_resolution_frames(self):
        import cv2

        store = self.store(
            retention=0, encoder=lambda rgb: cv2.imencode(".jpg", rgb)[1]
        )
        store.start()
        names = []
        for value in range(16):
            names.append(store.submit_frame(np.full((1080, 1920, 3), value, np.uint8)))
            wait_until(lambda: store.stats()["pending_count"] == 0)
        self.assertEqual(len(store._recent_frames), 16)
        self.assertTrue(
            all(isinstance(frame.data, bytes) for frame in store._recent_frames)
        )
        self.assertLess(store._recent_bytes, store.max_recent_bytes)
        self.assertEqual(list(self.root.glob("**/*.jpg")), [])
        archive = self.root / "errors" / store.mark_error(time.time_ns(), "frame error")
        wait_until(lambda: all((archive / Path(name).name).exists() for name in names))
        self.assertTrue(all(not (self.root / name).exists() for name in names))

    def test_disabled_history_raw_backlog_is_bounded_and_survives_error_during_encoding(
        self,
    ):
        entered, release = Event(), Event()

        def encode(rgb):
            if current_thread().name == "screenshot-writer" and int(rgb[0, 0, 0]) == 1:
                entered.set()
                self.assertTrue(release.wait(3))
            return bytes([int(rgb[0, 0, 0])])

        store = self.store(
            retention=0, encoder=encode, max_pending_count=2, max_pending_bytes=36
        )
        store.start()
        try:
            first = store.submit_frame(self.frame(1), "run_order")
            self.assertTrue(entered.wait(2))
            dropped = store.submit_frame(self.frame(2), "debug")
            last = store.submit_frame(self.frame(3), "debug")
            self.assertEqual(store.stats()["raw_pending_count"], 2)
            self.assertEqual(store.stats()["raw_pending_bytes"], 36)
            self.assertEqual(store.stats()["dropped"], 1)
            self.assertEqual(store._recent_bytes, 0)
            archive = (
                self.root / "errors" / store.mark_error(time.time_ns(), "frame error")
            )
        finally:
            release.set()
        wait_until(lambda: store.stats()["pending_count"] == 0)
        wait_until(
            lambda: (
                (archive / Path(first).name).exists()
                and (archive / Path(last).name).exists()
            )
        )
        self.assertFalse((archive / Path(dropped).name).exists())
        self.assertTrue(
            all(isinstance(frame.data, bytes) for frame in store._recent_frames)
        )

    def test_close_drains_admitted_rgb_error_frame_before_deadline(self):
        entered, release = Event(), Event()

        def encode(rgb):
            if current_thread().name == "screenshot-writer":
                entered.set()
                self.assertTrue(release.wait(3))
            return b"error frame"

        store = self.store(retention=0, encoder=encode)
        store.start()
        archive = self.root / "errors" / store.mark_error(time.time_ns(), "frame error")
        wait_until(lambda: (archive / "event.json").exists())
        closed = []
        closer = Thread(target=lambda: closed.append(store.close(timeout=2)))
        try:
            filename = store.submit_frame(self.frame(1), "run_order")
            self.assertTrue(entered.wait(2))
            closer.start()
            self.assertTrue(store._stop.wait(1))
        finally:
            release.set()
            if closer.ident is not None:
                closer.join(3)
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["remaining_threads"], [])
        self.assertEqual((archive / Path(filename).name).read_bytes(), b"error frame")

    def test_close_drains_queued_error_event_and_existing_history_before_deadline(self):
        entered, release = Event(), Event()
        store = self.store(encoder=lambda rgb: b"ordinary frame")
        original = store._archiver

        def delayed_archiver():
            entered.set()
            self.assertTrue(release.wait(3))
            original()

        store._archiver = delayed_archiver
        store.start()
        closed = []
        closer = Thread(target=lambda: closed.append(store.close(timeout=2)))
        try:
            self.assertTrue(entered.wait(1))
            filename = store.submit_frame(self.frame(1))
            wait_until(lambda: store.stats()["pending_count"] == 0)
            archive = (
                self.root / "errors" / store.mark_error(time.time_ns(), "queued error")
            )
            closer.start()
            self.assertTrue(store._stop.wait(1))
        finally:
            release.set()
            if closer.ident is not None:
                closer.join(3)
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["remaining_threads"], [])
        self.assertTrue((archive / "event.json").exists())
        self.assertEqual(
            (archive / Path(filename).name).read_bytes(), b"ordinary frame"
        )

    def test_late_rgb_encoding_does_not_start_writes_after_close_deadline(self):
        entered, release = Event(), Event()

        def encode(rgb):
            entered.set()
            self.assertTrue(release.wait(3))
            return b"too late"

        store = self.store(encoder=encode)
        store.start()
        try:
            filename = store.submit_frame(self.frame(1), "run_order")
            self.assertTrue(entered.wait(2))
            result = store.close(timeout=0.01)
            self.assertIn("screenshot-writer", result["remaining_threads"])
        finally:
            release.set()
        self.assertEqual(store.close()["remaining_threads"], [])
        self.assertFalse((self.root / filename).exists())
        self.assertEqual(store.stats()["shutdown_dropped"], 1)
        self.assertEqual(store.stats()["pending_count"], 0)
        self.assertEqual(store._recent_bytes, 0)

    def test_late_encoding_keeps_newer_byte_frames_in_capture_order(self):
        entered, release = Event(), Event()

        def encode(rgb):
            entered.set()
            self.assertTrue(release.wait(3))
            return b"old frame"

        store = self.store(retention=0, encoder=encode, max_recent_count=2)
        store.start()
        try:
            store.submit_frame(self.frame(1), "run_order")
            self.assertTrue(entered.wait(2))
            newer = store.submit(b"newer")
            newest = store.submit(b"newest")
        finally:
            release.set()
        wait_until(lambda: store.stats()["pending_count"] == 0)
        self.assertEqual(
            [frame.filename for frame in store._recent_frames], [newer, newest]
        )
        self.assertEqual(store._recent_bytes, len(b"newernewest"))

    def test_close_deadline_does_not_wait_for_archive_lock_or_start_late_archive(self):
        store = self.store()
        store.start()
        # The cleaner also uses this lock; do not rely on which worker reaches
        # it first. A popped event identifies the archive worker's pending wait.
        with store._archive_lock:
            archive = self.root / "errors" / store.mark_error(time.time_ns(), "queued")
            wait_until(lambda: store.stats()["archive_pending_count"] == 0)
            started = time.monotonic()
            result = store.close(timeout=0.01)
            self.assertLess(time.monotonic() - started, 0.5)
            self.assertIn("screenshot-archiver", result["remaining_threads"])
        self.assertEqual(store.close()["remaining_threads"], [])
        self.assertFalse((archive / "event.json").exists())
        self.assertGreaterEqual(store.stats()["shutdown_archive_dropped"], 1)

    def test_close_deadline_prevents_manifest_write_after_capacity_check(self):
        entered, release = Event(), Event()
        store = self.store()

        def delayed_capacity(*args):
            entered.set()
            self.assertTrue(release.wait(3))
            return True

        store._ensure_archive_capacity_locked = delayed_capacity
        store.start()
        try:
            archive = self.root / "errors" / store.mark_error(time.time_ns(), "queued")
            self.assertTrue(entered.wait(2))
            result = store.close(timeout=0.01)
            self.assertIn("screenshot-archiver", result["remaining_threads"])
        finally:
            release.set()
        self.assertEqual(store.close()["remaining_threads"], [])
        self.assertFalse((archive / "event.json").exists())
        self.assertEqual(store.stats()["shutdown_archive_dropped"], 2)

    def test_close_deadline_prevents_write_after_directory_creation(self):
        entered, release = Event(), Event()
        store = self.store()
        original_mkdir = Path.mkdir

        def delayed_mkdir(folder, *args, **kwargs):
            if folder == self.root / "run_order":
                entered.set()
                self.assertTrue(release.wait(3))
            return original_mkdir(folder, *args, **kwargs)

        store.start()
        with patch.object(Path, "mkdir", delayed_mkdir):
            try:
                filename = store.submit(b"late frame", "run_order")
                self.assertTrue(entered.wait(2))
                result = store.close(timeout=0.01)
                self.assertIn("screenshot-writer", result["remaining_threads"])
            finally:
                release.set()
            self.assertEqual(store.close()["remaining_threads"], [])
        self.assertFalse((self.root / filename).exists())
        self.assertEqual(list(self.root.glob("**/*.tmp")), [])
        self.assertEqual(store.stats()["shutdown_dropped"], 1)

    def test_close_saves_due_log_snapshot_and_defers_future_snapshot_to_restart(self):
        for elapsed_minutes in (0, 6):
            with self.subTest(elapsed_minutes=elapsed_minutes):
                entered, release = Event(), Event()
                store = self.store()
                original = store._archiver

                def delayed_archiver():
                    entered.set()
                    self.assertTrue(release.wait(3))
                    original()

                store._archiver = delayed_archiver
                store._save_error_logs = Mock()
                store.start()
                closed = []
                closer = Thread(target=lambda: closed.append(store.close(timeout=2)))
                try:
                    self.assertTrue(entered.wait(1))
                    archive_id = store.mark_error(
                        time.time_ns() - elapsed_minutes * 60 * 10**9, "queued"
                    )
                    closer.start()
                    self.assertTrue(store._stop.wait(1))
                finally:
                    release.set()
                    if closer.ident is not None:
                        closer.join(3)
                self.assertEqual(len(closed), 1)
                self.assertEqual(closed[0]["remaining_threads"], [])
                if elapsed_minutes:
                    store._save_error_logs.assert_called_once_with(archive_id)
                else:
                    store._save_error_logs.assert_not_called()
                self.assertTrue(
                    (self.root / "errors" / archive_id / "event.json").exists()
                )

    def test_close_counts_active_log_snapshot_that_finishes_reading_after_deadline(
        self,
    ):
        entered, release = Event(), Event()
        store = self.store()

        def delayed_timeline(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(3))
            return []

        with patch("arknights_mower.utils.diagnostics.timeline", delayed_timeline):
            store.start()
            try:
                archive = (
                    self.root
                    / "errors"
                    / store.mark_error(time.time_ns() - 6 * 60 * 10**9, "past error")
                )
                self.assertTrue(entered.wait(2))
                result = store.close(timeout=0.01)
                self.assertIn("screenshot-archiver", result["remaining_threads"])
            finally:
                release.set()
            self.assertEqual(store.close()["remaining_threads"], [])
        self.assertTrue((archive / "event.json").exists())
        self.assertFalse((archive / "logs.json").exists())
        self.assertEqual(store.stats()["shutdown_archive_dropped"], 1)

    def test_cleanup_batch_metrics_and_preview_are_independent_of_slow_delete(self):
        now = [10.0]
        store = self.store(
            retention=0,
            encoder=lambda rgb: b"jpeg",
            clock=lambda: now[0],
            cleanup_batch_size=2,
        )
        for timestamp in range(5):
            (self.root / f"{timestamp}.jpg").write_bytes(b"old")
        batch = store.cleanup()
        self.assertFalse(batch["complete"])
        self.assertEqual(batch["scanned"], 2)
        self.assertEqual(batch["deleted"], 2)
        entered, release = Event(), Event()
        unlink = Path.unlink

        def slow_unlink(path, *args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise TimeoutError("test cleanup stuck")
            now[0] = 11
            return unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", slow_unlink):
            store.start()
            try:
                self.assertTrue(entered.wait(2))
                name = store.submit_frame(self.frame(1))
                wait_until(lambda: store.latest() and store.latest().filename == name)
                self.assertEqual(store.latest().data, b"jpeg")
            finally:
                release.set()
            wait_until(lambda: store.stats()["cleanup_deleted"] == 5)
        self.assertEqual(store.stats()["cleanup_scanned"], 5)

    def test_close_records_then_releases_active_encoder_without_publishing_it(self):
        entered, release = Event(), Event()

        def encode(rgb):
            entered.set()
            if not release.wait(3):
                raise TimeoutError("test encoder stuck")
            return b"jpeg"

        store = self.store(retention=0, encoder=encode)
        original_writer = store._writer

        def writer_after_preview():
            self.assertTrue(entered.wait(2))
            original_writer()

        store._writer = writer_after_preview
        store.start()
        try:
            store.submit_frame(self.frame(1))
            self.assertTrue(entered.wait(2))
            store.submit_frame(self.frame(2))
            result = store.close(timeout=0.01)
            self.assertIn("screenshot-preview", result["remaining_threads"])
            self.assertEqual(result["shutdown_preview_dropped"], 1)
        finally:
            release.set()
        self.assertEqual(store.close()["remaining_threads"], [])
        self.assertIsNone(store.latest())
        self.assertEqual(store.stats()["preview_active_count"], 0)


if __name__ == "__main__":
    unittest.main()
