import datetime
import os
import unittest
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.io_budget import budget_sleep
from arknights_mower.utils.device.preflight import PreflightService


class ServerStatusTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        self.enterContext(patch.object(self.main, "base_scheduler", None))
        self.enterContext(patch.object(config, "stop_mower", Event()))
        self.enterContext(patch.object(self.server, "scheduled_start_at", None))
        self.enterContext(patch.dict(os.environ, {"MOWER_RESTART_JOB": ""}))
        self.worker = Mock()
        self.worker.is_alive.return_value = True
        self.server.mower_thread = self.worker
        self.enterContext(
            patch.object(
                self.control,
                "readiness",
                side_effect=AssertionError("status performs no device I/O"),
            )
        )
        self.enterContext(
            patch.object(
                self.control,
                "recover",
                side_effect=AssertionError("status never initiates recovery"),
            )
        )

    def scheduler(self, *, sleeping=False, initialized=True):
        return SimpleNamespace(
            op_data=(
                SimpleNamespace(
                    plan_condition=[True, False, True],
                    backup_plans=[
                        SimpleNamespace(name="first"),
                        SimpleNamespace(name="inactive"),
                        SimpleNamespace(name="second"),
                    ],
                )
                if initialized
                else None
            ),
            sleeping=sleeping,
            tasks=[],
        )

    def test_alive_worker_without_scheduler_reports_starting_or_recovering(self):
        for state, expected in (
            ("idle", "starting"),
            ("starting", "starting"),
            ("connected", "starting"),
            ("failed", "recovering"),
            ("paused", "recovering"),
            ("closed", "starting"),
        ):
            with self.subTest(state=state), patch.object(self.control, "_state", state):
                response = self.client.get("/status")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["status"], expected)
                self.assertEqual(response.json["plan_condition"], [])
                self.assertIsNone(response.json["next_task_time"])
                self.assertIsNone(response.json["remaining_seconds"])
                status = self.client.get("/device/status", headers=self.headers)
                self.assertTrue(status.json["active"])

    def test_scheduler_without_operator_data_still_reports_starting(self):
        self.main.base_scheduler = self.scheduler(initialized=False)
        response = self.client.get("/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "starting")
        self.assertEqual(response.json["plan_condition"], [])

    def test_ready_scheduler_preserves_work_sleep_and_task_metadata(self):
        now = datetime.datetime(2026, 10, 1, 12)
        next_task = now + datetime.timedelta(seconds=90)
        self.main.base_scheduler = self.scheduler()
        self.main.base_scheduler.tasks = [SimpleNamespace(time=next_task)]
        clock = SimpleNamespace(datetime=SimpleNamespace(now=lambda: now))
        with patch.object(self.server, "datetime", clock):
            for sleeping, expected in ((False, "working"), (True, "sleeping")):
                with self.subTest(sleeping=sleeping):
                    self.main.base_scheduler.sleeping = sleeping
                    response = self.client.get("/status")
                    self.assertEqual(response.json["status"], expected)
                    self.assertEqual(
                        response.json["plan_condition"], ["first", "second"]
                    )
                    self.assertEqual(
                        response.json["next_task_time"], "2026-10-01 12:01:30"
                    )
                    self.assertEqual(response.json["remaining_seconds"], 90)

    def test_recovery_overrides_scheduler_work_or_sleep_without_losing_metadata(self):
        for sleeping in (False, True):
            self.main.base_scheduler = self.scheduler(sleeping=sleeping)
            for state in ("starting", "failed", "paused"):
                with (
                    self.subTest(sleeping=sleeping, state=state),
                    patch.object(self.control, "_state", state),
                ):
                    response = self.client.get("/status")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json["status"], "recovering")
                    self.assertEqual(
                        response.json["plan_condition"], ["first", "second"]
                    )

    def test_missing_or_dead_worker_reports_stopped_despite_stale_state(self):
        self.main.base_scheduler = self.scheduler(sleeping=True)
        self.worker.is_alive.return_value = False
        for worker in (None, self.worker):
            for state in ("starting", "failed", "paused", "closed"):
                with (
                    self.subTest(worker=worker, state=state),
                    patch.object(self.server, "mower_thread", worker),
                    patch.object(self.control, "_state", state),
                ):
                    response = self.client.get("/status")
                    self.assertEqual(response.json["status"], "stopped")
                    self.assertEqual(response.json["plan_condition"], [])
                    self.assertIsNone(response.json["next_task_time"])
                    self.assertIsNone(response.json["remaining_seconds"])

    def test_alive_startup_and_recovery_lock_target_and_settings_operations(self):
        before = self.path.read_bytes()
        for state in ("idle", "starting", "failed", "paused"):
            with self.subTest(state=state), patch.object(self.control, "_state", state):
                for payload in (
                    {"device": {"last_serial": "USB-other"}},
                    {"device": {"touch_backend": "maatouch"}},
                ):
                    response = self.client.patch(
                        "/conf", headers=self.headers, json=payload
                    )
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.json["error"], "device_session_active")
                for route in ("/device/preflight", "/device/discover", "/device/start"):
                    response = self.client.post(route, headers=self.headers, json={})
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(
                        response.json["error"]["code"], "device_session_active"
                    )
                self.assertEqual(self.path.read_bytes(), before)

    def test_stopped_worker_allows_settings_without_clearing_task_cancellation(self):
        self.worker.is_alive.return_value = False
        config.stop_mower.set()
        io = PreflightIO()
        io.targets = [("USB-other", "device")]
        self.control._preflight = PreflightService(io)
        capture = io.capture_frame

        def capture_after_wait(*args):
            budget_sleep(0)
            return capture(*args)

        with patch.object(self.control, "_state", "failed"):
            self.assertFalse(
                self.client.get("/device/status", headers=self.headers).json["active"]
            )
            response = self.client.patch(
                "/conf",
                headers=self.headers,
                json={"device": {"last_serial": "USB-other"}},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(config.conf.device.last_serial, "USB-other")
            with patch.object(
                io, "capture_frame", side_effect=capture_after_wait
            ) as capture_frame:
                response = self.client.post(
                    "/device/preflight", headers=self.headers, json={}
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json["ok"], response.json["error"])
                self.assertEqual(response.json["serial"], "USB-other")
                capture_frame.assert_called_once()
        self.assertTrue(config.stop_mower.is_set())
        with self.assertRaises(MowerExit):
            budget_sleep(0)

    def test_stop_remains_reachable_during_startup_and_recovery(self):
        for state in ("idle", "failed", "paused"):
            with self.subTest(state=state), patch.object(self.control, "_state", state):
                self.server.mower_thread = self.worker
                self.worker.is_alive.return_value = True
                config.stop_mower.clear()
                response = self.client.get("/stop", headers=self.headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_data(as_text=True), "false")
                self.assertTrue(config.stop_mower.is_set())
                self.assertIs(self.server.mower_thread, self.worker)
                self.assertNotEqual(
                    self.client.get("/status").json["status"], "stopped"
                )
                self.assertTrue(
                    self.client.get("/device/status", headers=self.headers).json[
                        "active"
                    ]
                )
                response = self.client.patch(
                    "/conf",
                    headers=self.headers,
                    json={"device": {"last_serial": "USB-other"}},
                )
                self.assertEqual(response.status_code, 409)
        self.worker.is_alive.return_value = False
        with patch.object(self.server, "set_mower_thread") as set_thread:
            response = self.client.get("/stop", headers=self.headers)
            self.assertEqual(response.get_data(as_text=True), "true")
            set_thread.assert_called_once_with(None)
        self.assertEqual(self.client.get("/status").json["status"], "stopped")
