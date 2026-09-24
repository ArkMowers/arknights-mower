import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class FakeTimer:
    instances = []

    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.daemon = False
        self.cancelled = False
        self.instances.append(self)

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True


class ScheduledStartTests(unittest.TestCase):
    def setUp(self):
        import server

        self.server = server
        self.client = server.app.test_client()
        self.headers = {"token": getattr(server.app, "token", "")}
        FakeTimer.instances.clear()
        server._cancel_scheduled_start()
        self.timer_patch = patch.object(server, "Timer", FakeTimer)
        self.timer_patch.start()

    def tearDown(self):
        self.server._cancel_scheduled_start()
        self.timer_patch.stop()

    def test_invalid_delay_is_rejected(self):
        for value in (0, -1, True, "60", 31 * 86400):
            with self.subTest(value=value):
                response = self.client.put(
                    "/scheduled-start",
                    json={"delay_seconds": value},
                    headers=self.headers,
                )
                self.assertEqual(response.status_code, 400)
        self.assertIsNone(self.client.get("/status").json["scheduled_start_at"])

    def test_replace_cancel_and_status(self):
        with patch.object(self.server, "mower_thread", None):
            first = self.client.put(
                "/scheduled-start", json={"delay_seconds": 900}, headers=self.headers
            )
            self.assertEqual(first.status_code, 200)
            self.assertEqual(
                self.client.get("/status").json["scheduled_start_at"],
                first.json["scheduled_start_at"],
            )
            second = self.client.put(
                "/scheduled-start", json={"delay_seconds": 1800}, headers=self.headers
            )
            self.assertEqual(second.status_code, 200)
            self.assertTrue(FakeTimer.instances[0].cancelled)
            self.assertNotEqual(first.json, second.json)
            self.client.delete("/scheduled-start", headers=self.headers)
            self.assertTrue(FakeTimer.instances[1].cancelled)
            self.assertIsNone(self.client.get("/status").json["scheduled_start_at"])

    def test_only_current_timer_starts_mower(self):
        with (
            patch.object(self.server, "mower_thread", None),
            patch.object(self.server, "_start_mower", return_value=True) as start,
        ):
            for delay in (900, 1800):
                self.client.put(
                    "/scheduled-start",
                    json={"delay_seconds": delay},
                    headers=self.headers,
                )
            FakeTimer.instances[0].callback()
            start.assert_not_called()
            FakeTimer.instances[1].callback()
            start.assert_called_once_with("2")
            self.assertIsNone(self.client.get("/status").json["scheduled_start_at"])

    def test_manual_start_cancels_reservation(self):
        with (
            TemporaryDirectory() as folder,
            patch.object(self.server, "mower_thread", None),
            patch.object(self.server, "active_job", return_value=False),
            patch.object(self.server, "_job_running", return_value=False),
            patch.object(self.server, "get_path", return_value=Path(folder)),
            patch.object(self.server, "load_state", return_value={}),
            patch.object(self.server, "log_stream"),
            patch.object(self.server, "Thread"),
            patch.object(self.server, "set_mower_thread"),
        ):
            self.client.put(
                "/scheduled-start", json={"delay_seconds": 900}, headers=self.headers
            )
            response = self.client.get("/start/0", headers=self.headers)
            self.assertEqual(response.get_data(as_text=True), "true")
            self.assertTrue(FakeTimer.instances[0].cancelled)
            self.assertIsNone(self.client.get("/status").json["scheduled_start_at"])


if __name__ == "__main__":
    unittest.main()
