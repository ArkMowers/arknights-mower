"""Worker cancellation waits for restoration without racing live device I/O."""

import importlib
import unittest
from threading import Event
from unittest.mock import patch

from arknights_mower.solvers import record
from arknights_mower.utils import config
from arknights_mower.utils.lifecycle import Shutdown


class DeviceShutdownTests(unittest.TestCase):
    def setUp(self):
        self.server = importlib.import_module("server")
        self.enterContext(patch.object(config, "stop_mower", Event()))
        self.enterContext(patch.object(record, "current_state", return_value={}))
        self.enterContext(patch.object(record, "save_state_to_db"))
        self.enterContext(patch.object(self.server, "set_mower_thread"))
        self.enterContext(patch.object(self.server, "mower_thread", None))
        self.client = self.server.app.test_client()
        self.headers = {"token": getattr(self.server.app, "token", "")}

    def test_stopping_without_worker_still_cancels_pending_work(self):
        for _ in range(2):
            response = self.client.get("/stop", headers=self.headers)
            self.assertEqual(response.get_data(as_text=True), "true")
            self.assertTrue(config.stop_mower.is_set())

    def test_process_exit_rejects_new_and_scheduled_starts(self):
        shutdown = Shutdown()
        shutdown.request("tray")
        with patch.object(self.server, "shutdown", shutdown):
            response = self.client.get("/start/0", headers=self.headers)
            self.assertEqual(response.get_data(as_text=True), "false")
            response = self.client.put(
                "/scheduled-start", json={"delay_seconds": 60}, headers=self.headers
            )
            self.assertEqual(response.status_code, 409)

    def test_stop_waits_for_worker_restoration_and_leaves_timed_out_worker_owned(self):
        for times_out in (False, True):
            with self.subTest(times_out=times_out):
                config.stop_mower.clear()
                observed = []

                class Worker:
                    alive = True

                    def join(self, timeout):
                        observed.append((config.stop_mower.is_set(), timeout))
                        if not times_out:
                            # The worker's finally restores its display before exit.
                            observed.append("restored")
                            self.alive = False

                    def is_alive(self):
                        return self.alive

                worker = Worker()
                self.server.mower_thread = worker
                response = self.client.get("/stop", headers=self.headers)
                self.assertEqual(
                    response.get_data(as_text=True), str(not times_out).lower()
                )
                self.assertTrue(observed[0][0])
                self.assertGreater(observed[0][1], 0)
                self.assertLessEqual(observed[0][1], 10)
                if times_out:
                    self.assertIs(self.server.mower_thread, worker)
                    self.assertNotIn("restored", observed)
                else:
                    self.assertIsNone(self.server.mower_thread)
                    self.assertIn("restored", observed)

    def test_worker_thread_does_not_die_with_the_device_verdict(self):
        import tempfile
        import threading
        from pathlib import Path

        from arknights_mower import __main__ as mower
        from arknights_mower.utils.device.session import (
            ReadinessResult,
            SessionFailure,
        )

        verdict = SessionFailure(
            ReadinessResult("offline", "USB-A", code="recovery_exhausted"),
            "设备恢复命令失败：模拟器启动命令被拒绝（退出码 -506）",
        )
        unhandled = []
        previous, threading.excepthook = threading.excepthook, unhandled.append
        try:
            with (
                tempfile.TemporaryDirectory() as folder,
                patch.object(self.server, "get_path", return_value=Path(folder)),
                patch.object(self.server, "load_state", return_value={}),
                patch.object(mower, "main", side_effect=verdict),
            ):
                self.assertTrue(self.server._start_mower("2"))
                worker = self.server.mower_thread
                worker.join(5)
                self.assertFalse(worker.is_alive())
        finally:
            threading.excepthook = previous
        # The field report was an unhandled "Exception in thread" traceback that
        # ended the run without a reason the user could act on.
        self.assertEqual(unhandled, [])

    def test_worker_boundary_reports_only_classified_device_verdicts(self):
        from unittest.mock import patch

        from arknights_mower import __main__ as mower
        from arknights_mower.utils.device.session import (
            ReadinessResult,
            SessionFailure,
        )

        verdict = SessionFailure(
            ReadinessResult("offline", "USB-A", code="recovery_exhausted"),
            "设备恢复命令失败：模拟器启动命令被拒绝（退出码 -506）",
        )
        forwarded = []

        def run(saved_state, *, preparation_serial=None):
            forwarded.append((saved_state, preparation_serial))
            raise verdict

        with (
            patch.object(mower, "main", side_effect=run),
            self.assertLogs(self.server.logger, level="ERROR") as logs,
        ):
            self.server._run_mower_worker({"tasks": []}, "USB-123")
        self.assertEqual(forwarded, [({"tasks": []}, "USB-123")])
        self.assertTrue(
            any("启动命令被拒绝（退出码 -506）" in line for line in logs.output)
        )
        # A software fault keeps its traceback for the developer.
        with (
            patch.object(mower, "main", side_effect=RuntimeError("unrelated")),
            self.assertRaises(RuntimeError),
        ):
            self.server._run_mower_worker({})


if __name__ == "__main__":
    unittest.main()
