"""HTTP admission, cancellation and cleanup use offline device adapters."""

import unittest
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit


class GamePerformanceRouteTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        self.enterContext(patch.object(config, "stop_mower", Event()))
        self.enterContext(patch.object(self.server, "performance_test_cancel", Event()))
        self.enterContext(
            patch.object(
                self.server, "performance_test_job", {"status": "idle", "id": None}
            )
        )
        self.enterContext(patch.object(self.server, "active_job", return_value=None))
        self.enterContext(
            patch.object(self.server.resource_update, "running", return_value=False)
        )
        self.enterContext(patch.object(self.server, "_job_running", return_value=False))
        self.thread = self.enterContext(patch.object(self.server, "Thread"))
        self.thread.return_value.is_alive.return_value = True
        self.enterContext(patch.object(self.server, "set_mower_thread"))
        self.enterContext(patch.object(self.server, "_cancel_scheduled_start"))
        self.enterContext(patch.object(self.server, "_collect_maa_check_result"))
        self.enterContext(
            patch.object(self.server, "maa_check_job", {"status": "idle"})
        )
        self.enterContext(
            patch(
                "arknights_mower.utils.performance.is_android_runtime",
                return_value=False,
            )
        )

    def start(self):
        return self.client.post(
            "/device/performance-test", headers=self.headers, json={}
        )

    def test_requires_auth_and_saved_configuration_then_reserves_worker(self):
        before = self.path.read_bytes()
        self.assertEqual(
            self.client.post("/device/performance-test", json={}).status_code, 403
        )
        response = self.client.post(
            "/device/performance-test", headers=self.headers, json={"device": {}}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.start().status_code, 202)
        self.thread.return_value.start.assert_called_once()
        self.assertEqual(self.path.read_bytes(), before)
        response = self.client.get("/device/performance-test", headers=self.headers)
        self.assertEqual(response.json["status"], "running")
        self.assertEqual(response.json["device"], config.conf.device.model_dump())
        self.assertFalse(self.server._start_mower("2"))
        self.assertEqual(self.start().status_code, 409)
        self.assertEqual(
            self.client.post(
                "/device/preflight", headers=self.headers, json={}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.patch(
                "/conf", headers=self.headers, json={"selection_poll_interval": 0.8}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.patch(
                "/conf", headers=self.headers, json={"device": {"last_serial": "OTHER"}}
            ).status_code,
            409,
        )

    def test_active_session_and_android_reject_before_worker_creation(self):
        self.control.start()
        self.assertEqual(self.start().status_code, 409)
        self.control.close()
        with patch(
            "arknights_mower.utils.performance.is_android_runtime", return_value=True
        ):
            self.assertEqual(self.start().status_code, 400)
        self.thread.assert_not_called()

    def test_cancellation_is_bound_to_test_id_and_does_not_stop_later_run(self):
        job = self.start().json
        response = self.client.delete(
            "/device/performance-test", headers=self.headers, json={"id": "old"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.server.performance_test_cancel.is_set())
        response = self.client.delete(
            "/device/performance-test", headers=self.headers, json={"id": job["id"]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.server.performance_test_cancel.is_set())
        self.assertFalse(config.stop_mower.is_set())
        self.server.performance_test_job["status"] = "passed"
        self.assertEqual(
            self.client.delete(
                "/device/performance-test", headers=self.headers, json={"id": job["id"]}
            ).status_code,
            409,
        )

    def test_preview_requires_auth_and_only_serves_frames_from_current_test(self):
        store = MagicMock()
        with patch("arknights_mower.views.screenshot._get_store", return_value=store):
            self.assertEqual(
                self.client.get(
                    "/device/performance-test/screenshot?id=old"
                ).status_code,
                403,
            )
            job = self.start().json
            url = f"/device/performance-test/screenshot?id={job['id']}"
            self.assertEqual(
                self.client.get(
                    "/device/performance-test/screenshot?id=old", headers=self.headers
                ).status_code,
                404,
            )
            store.latest.assert_not_called()
            store.latest.return_value = SimpleNamespace(
                captured_ns=job["started_ns"] - 1, data=b"previous task"
            )
            self.assertEqual(
                self.client.get(url, headers=self.headers).status_code, 204
            )
            store.latest.return_value = None
            self.assertEqual(
                self.client.get(url, headers=self.headers).status_code, 204
            )
            store.latest.return_value = SimpleNamespace(
                captured_ns=job["started_ns"], data=b"test frame"
            )
            with patch.object(
                self.control, "execute", side_effect=AssertionError("no device input")
            ):
                response = self.client.get(url, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"test frame")
            self.assertEqual(response.mimetype, "image/jpeg")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            conditional = {**self.headers, "If-None-Match": response.headers["ETag"]}
            self.assertEqual(self.client.get(url, headers=conditional).status_code, 304)
            self.server.performance_test_job["status"] = "passed"
            self.assertEqual(
                self.client.get(url, headers=self.headers).status_code, 404
            )
            self.server.performance_test_job.update(status="running", id="replacement")
            self.assertEqual(
                self.client.get(url, headers=self.headers).status_code, 404
            )

    def test_worker_uses_session_boundary_and_preserves_saved_configuration(self):
        before = self.path.read_bytes()
        result = {"status": "passed", "recommended_mode": "xhigh"}
        with patch(
            "arknights_mower.solvers.performance_test.SelectionPerformanceTest"
        ) as solver:
            solver.return_value.run.return_value = result
            self.server._run_performance_test(config.conf.model_copy(deep=True))
        self.assertEqual(self.server.performance_test_job["recommended_mode"], "xhigh")
        self.assertFalse(self.control.active)
        self.assertFalse(self.control.run_active)
        self.assertEqual(self.path.read_bytes(), before)

    def test_worker_fault_and_cancellation_never_leave_a_recommendation(self):
        for error, status in (
            (MowerExit("cancelled"), "cancelled"),
            (OSError("capture failed"), "failed"),
        ):
            with (
                self.subTest(status=status),
                patch(
                    "arknights_mower.solvers.performance_test.SelectionPerformanceTest"
                ) as solver,
            ):
                solver.return_value.run.side_effect = error
                self.server._run_performance_test(config.conf.model_copy(deep=True))
                self.assertEqual(self.server.performance_test_job["status"], status)
                self.assertIsNone(self.server.performance_test_job["recommended_mode"])
                self.assertFalse(self.control.active)

    def test_cancellation_during_device_io_keeps_session_for_discard(self):
        from arknights_mower.solvers.performance_test import SelectionPerformanceTest
        from arknights_mower.utils.device.io_budget import io_timeout

        opened = []
        discarded = []

        def initialize(solver, device, configuration, cancelled, report):
            solver.configuration = configuration
            solver.cancelled = cancelled
            solver.report = report
            solver.entered_room = True
            solver.trials = []
            opened.append(device)

        def trial(*_):
            def interrupted(device):
                self.server.performance_test_cancel.set()
                io_timeout(1)

            self.control.execute(interrupted).unwrap()

        def discard(solver):
            with solver.budget(1, cleanup=True):
                discarded.append(
                    self.control.execute(lambda device: device.tap((1, 2))).unwrap()
                )

        with (
            patch.object(SelectionPerformanceTest, "__init__", initialize),
            patch.object(SelectionPerformanceTest, "open_selection"),
            patch.object(
                SelectionPerformanceTest, "prepare_round", return_value=([], [])
            ),
            patch.object(SelectionPerformanceTest, "trial", trial),
            patch.object(SelectionPerformanceTest, "cancel_selection", discard),
        ):
            self.server._run_performance_test(config.conf.model_copy(deep=True))
        self.assertEqual(discarded, [(1, 2)])
        self.assertEqual(self.server.performance_test_job["status"], "cancelled")
        self.assertIsNone(self.server.performance_test_job["recommended_mode"])
        self.assertTrue(opened[0].closed)
        self.assertFalse(self.control.run_active)

    def test_worker_does_not_limit_elapsed_startup_and_trial_time(self):
        from types import SimpleNamespace

        from arknights_mower.solvers import performance_test as module
        from arknights_mower.utils.csleep import csleep
        from arknights_mower.utils.device.io_budget import io_timeout

        clock = [0.0]
        discarded = []

        def initialize(solver, device, configuration, cancelled, report):
            solver.configuration = configuration
            solver.cancelled = cancelled
            solver.report = report
            solver.entered_room = True
            solver.trials = []
            clock[0] += 300

        def trial(*_):
            clock[0] += 300
            self.control.execute(lambda device: io_timeout(10)).unwrap()
            csleep(0)

        def discard(solver):
            with solver.budget(1, cleanup=True):
                discarded.append(self.control.execute(lambda d: d.tap((1, 2))).unwrap())

        with (
            patch.object(
                self.server, "time", SimpleNamespace(monotonic=lambda: clock[0])
            ),
            patch.object(module, "monotonic", lambda: clock[0]),
            patch.object(module.SelectionPerformanceTest, "__init__", initialize),
            patch.object(module.SelectionPerformanceTest, "open_selection"),
            patch.object(
                module.SelectionPerformanceTest, "prepare_round", return_value=([], [])
            ),
            patch.object(module.SelectionPerformanceTest, "trial", trial),
            patch.object(module.SelectionPerformanceTest, "cancel_selection", discard),
        ):
            self.server._run_performance_test(config.conf.model_copy(deep=True))
        self.assertEqual(self.server.performance_test_job["recommended_mode"], "xhigh")
        self.assertEqual(self.server.performance_test_job["status"], "passed")
        self.assertEqual(discarded, [(1, 2)])
        self.assertFalse(self.control.run_active)
        self.assertFalse(self.control.active)

    def test_status_and_cancel_do_not_wait_for_device_configuration_lock(self):
        self.server.performance_test_job.update(status="running", id="test")
        guard = MagicMock()
        guard.acquire.side_effect = AssertionError("must not wait for device I/O")
        with patch.object(self.control, "configuration_lock", guard):
            self.assertEqual(
                self.client.get(
                    "/device/performance-test", headers=self.headers
                ).status_code,
                200,
            )
            self.assertEqual(
                self.client.delete(
                    "/device/performance-test",
                    headers=self.headers,
                    json={"id": "test"},
                ).status_code,
                200,
            )

    def test_maa_check_and_updates_cannot_interrupt_test(self):
        self.start()
        self.assertEqual(
            self.client.get("/check-maa", headers=self.headers).json["status"], "error"
        )
        self.assertFalse(self.server._mower_busy_response()["ok"])

    def test_running_maa_check_and_worker_start_failure_release_admission(self):
        self.server.maa_check_job["status"] = "running"
        self.assertEqual(self.start().status_code, 409)
        self.thread.assert_not_called()
        self.server.maa_check_job["status"] = "idle"
        self.thread.return_value.start.side_effect = RuntimeError("thread unavailable")
        self.assertEqual(self.start().status_code, 500)
        self.assertEqual(self.server.performance_test_job["status"], "failed")
        self.assertIsNone(self.server.mower_thread)
