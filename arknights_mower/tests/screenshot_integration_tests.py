"""Recognition and HTTP preview use the bounded screenshot pipeline separately."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from arknights_mower.utils import config, log
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.screenshot import ScreenshotStore
from arknights_mower.views import screenshot as views


class RecognitionPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.rgb = np.full((1080, 1920, 3), (255, 0, 0), dtype=np.uint8)
        self.capture = Mock(return_value=SimpleNamespace(unwrap=lambda: self.rgb))
        self.device = object.__new__(Device)
        self.device.session_control = SimpleNamespace(capture=self.capture)
        self.store = Mock()
        self.store.submit_frame.return_value = "frame.jpg"
        self.enterContext(patch.object(log, "_store", return_value=self.store))
        self.enterContext(patch.object(config, "screenshot_time", datetime.min))
        self.enterContext(patch.object(config, "screenshot_avg", None))
        self.enterContext(patch.object(config, "screenshot_count", 0))

    def test_current_rgb_and_gray_are_available_without_jpeg_encoding(self):
        recog = Recognizer(self.device)
        with patch("cv2.imencode", side_effect=AssertionError("synchronous JPEG")):
            self.assertIs(recog.img, self.rgb)
            self.assertEqual(int(recog.gray[0, 0]), 76)
            recog.save_screencap("workshop")
        self.capture.assert_called_once()
        self.assertEqual(self.store.submit_frame.call_count, 2)
        self.assertIs(self.store.submit_frame.call_args.args[0], self.rgb)
        self.assertEqual(self.store.submit_frame.call_args.args[1], "workshop")
        self.store.submit.assert_not_called()

    def test_explicit_bytes_encode_current_frame_once_without_recapture(self):
        recog = Recognizer(self.device)
        self.assertIs(recog.img, self.rgb)
        encoded = np.frombuffer(b"jpeg", dtype=np.uint8)
        with patch("cv2.imencode", return_value=(True, encoded)) as encode:
            self.assertEqual(recog.screencap, b"jpeg")
            self.assertEqual(recog.screencap, b"jpeg")
        encode.assert_called_once()
        self.capture.assert_called_once()

    def test_recognition_continues_while_background_encoder_or_disk_is_blocked(self):
        for blocked_stage in ("encode", "write"):
            with (
                self.subTest(blocked_stage=blocked_stage),
                tempfile.TemporaryDirectory() as folder,
            ):
                entered, release, observed = Event(), Event(), Event()
                errors = []

                def encoder(rgb):
                    if blocked_stage == "encode":
                        entered.set()
                        release.wait(3)
                    return b"jpeg"

                def writer(frame):
                    entered.set()
                    release.wait(3)

                store = ScreenshotStore(
                    Path(folder), lambda: 1, encoder=encoder, writer=writer
                )
                store.start()
                recog = Recognizer(self.device)

                def observe():
                    try:
                        self.assertIs(recog.img, self.rgb)
                        self.assertEqual(int(recog.gray[0, 0]), 76)
                    except Exception as exc:
                        errors.append(exc)
                    finally:
                        observed.set()

                worker = Thread(target=observe, daemon=True)
                try:
                    with patch.object(log, "_store", return_value=store):
                        worker.start()
                        self.assertTrue(
                            entered.wait(2), "background work did not start"
                        )
                        self.assertTrue(
                            observed.wait(1), "recognition waited for persistence"
                        )
                        self.assertEqual(errors, [])
                        self.assertFalse(release.is_set())
                finally:
                    release.set()
                    worker.join(2)
                    self.assertEqual(store.close()["remaining_threads"], [])


class ScreenshotMetricsTests(unittest.TestCase):
    def test_metrics_require_token_and_read_only_existing_store(self):
        import server

        with (
            patch.object(server.app, "token", "secret", create=True),
            patch.object(views, "_get_store") as get_store,
        ):
            client = server.app.test_client()
            self.assertEqual(client.get("/screenshot/stats").status_code, 403)
            get_store.assert_not_called()
            get_store.return_value = None
            response = client.get("/screenshot/stats", headers={"token": "secret"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, {})
            get_store.return_value = SimpleNamespace(
                stats=lambda: {"pending_count": 2, "preview_age": 0.15}
            )
            response = client.get("/screenshot/stats", headers={"token": "secret"})
            self.assertEqual(response.json["pending_count"], 2)
            self.assertEqual(response.json["preview_age"], 0.15)


class ScreenshotShutdownTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(log, "_store_closed", False))

    def test_shutdown_without_capture_does_not_start_store(self):
        with (
            patch.object(log, "_store_instance", None),
            patch.object(log, "_store") as create,
        ):
            self.assertEqual(log.close_screenshot_store(), {"remaining_threads": []})
        create.assert_not_called()

    def test_shutdown_records_workers_that_exceed_join_budget(self):
        store = Mock()
        store.close.return_value = {"remaining_threads": ["screenshot-writer"]}
        with (
            patch.object(log, "_store_instance", store),
            patch.object(log.logger, "warning") as warning,
        ):
            result = log.close_screenshot_store(timeout=0.1)
        self.assertEqual(result["remaining_threads"], ["screenshot-writer"])
        store.close.assert_called_once_with(timeout=0.1)
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
