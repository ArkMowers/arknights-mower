import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.usefixtures("offline_maintenance")


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
        self.assertIsNone(
            self.client.get("/status", headers=self.headers).json["scheduled_start_at"]
        )

    def test_replace_cancel_and_status(self):
        with patch.object(self.server, "mower_thread", None):
            first = self.client.put(
                "/scheduled-start", json={"delay_seconds": 900}, headers=self.headers
            )
            self.assertEqual(first.status_code, 200)
            self.assertEqual(
                self.client.get("/status", headers=self.headers).json[
                    "scheduled_start_at"
                ],
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
            self.assertIsNone(
                self.client.get("/status", headers=self.headers).json[
                    "scheduled_start_at"
                ]
            )

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
            self.assertIsNone(
                self.client.get("/status", headers=self.headers).json[
                    "scheduled_start_at"
                ]
            )

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
            self.assertIsNone(
                self.client.get("/status", headers=self.headers).json[
                    "scheduled_start_at"
                ]
            )

    def test_server_downtime_stops_worker_then_schedules_saved_queue_restart(self):
        from arknights_mower import __main__ as main
        from arknights_mower.solvers import record
        from arknights_mower.utils import crash_recovery, instance_supervisor
        from arknights_mower.utils.news_checker import MaintenanceInfo

        now = datetime.now()
        info = MaintenanceInfo(
            now - timedelta(minutes=4),
            now + timedelta(minutes=6),
            "major",
            "停服更新",
            "",
            "manual-test",
            manual=True,
        )
        order = []
        save = Mock(side_effect=lambda: order.append("save") or True)
        worker = Mock(is_alive=Mock(return_value=False))
        with (
            patch.object(main.config, "stop_mower", Event()),
            patch.object(main, "base_scheduler", SimpleNamespace(tasks=[])),
            patch.object(main.device_control, "run", return_value=nullcontext()),
            patch.object(main, "resource_task_session", return_value=nullcontext()),
            patch.object(
                main,
                "_main",
                side_effect=lambda _: main._handle_maintenance(info, Mock()),
            ),
            patch.object(
                main, "_close_device_session", side_effect=lambda: order.append("close")
            ),
            patch.object(main, "_cancel_maintenance_timer"),
            patch.object(record, "save_current_state", save),
            patch.object(self.server, "mower_thread", worker),
            patch.object(
                instance_supervisor,
                "task_intent",
                side_effect=lambda _: order.append("stop"),
            ),
            patch.object(crash_recovery, "_cancelled", False),
            patch.object(
                crash_recovery, "cancel", side_effect=lambda: order.append("cancel")
            ),
            patch.object(self.server, "_start_mower", return_value=True) as start,
        ):
            self.server._run_mower_worker({})
            self.assertEqual(order, ["save", "close", "stop", "cancel"])
            self.assertTrue(main.config.stop_mower.is_set())
            self.assertEqual(len(FakeTimer.instances), 1)
            timer = FakeTimer.instances[0]
            self.assertAlmostEqual(timer.delay, 360, delta=2)
            status = self.client.get("/status", headers=self.headers).json
            self.assertEqual(status["status"], "stopped")
            self.assertAlmostEqual(
                (
                    datetime.fromisoformat(status["scheduled_start_at"]).replace(
                        tzinfo=None
                    )
                    - info.end
                ).total_seconds(),
                0,
                delta=1,
            )
            start.assert_not_called()
            timer.callback()
            worker.join.assert_called_once_with(10)
            start.assert_called_once_with("0")
            self.assertIsNone(self.server.scheduled_start_at)

    def test_user_stop_during_downtime_handoff_prevents_reservation(self):
        from arknights_mower import __main__ as main
        from arknights_mower.utils import crash_recovery
        from arknights_mower.utils.news_checker import MaintenanceInfo

        now = datetime.now()
        info = MaintenanceInfo(
            now,
            now + timedelta(minutes=10),
            "major",
            "停服更新",
            "",
            "manual-test",
            manual=True,
        )
        with (
            patch.object(main, "main", return_value=info),
            patch.object(crash_recovery, "cancelled", return_value=True),
        ):
            self.server._run_mower_worker({})
        self.assertEqual(FakeTimer.instances, [])

    def test_explicit_stop_cancels_downtime_reservation(self):
        from arknights_mower.utils import crash_recovery, instance_supervisor

        with (
            patch.object(self.server, "mower_thread", None),
            patch.object(instance_supervisor, "task_intent"),
            patch.object(crash_recovery, "cancel"),
            patch.object(self.server.config, "stop_mower", Event()),
        ):
            self.server._schedule_start(600, start_type="0")
            self.assertTrue(self.server._stop_mower())
            self.assertTrue(FakeTimer.instances[0].cancelled)
            self.assertIsNone(self.server.scheduled_start_at)

    def test_snapshot_failure_stops_without_timer_or_automatic_recovery(self):
        from arknights_mower import __main__ as main
        from arknights_mower.solvers import record
        from arknights_mower.utils import crash_recovery, instance_supervisor
        from arknights_mower.utils.news_checker import MaintenanceInfo

        now = datetime.now()
        info = MaintenanceInfo(
            now,
            now + timedelta(minutes=10),
            "major",
            "停服更新",
            "",
            "manual-test",
            manual=True,
        )
        with (
            patch.object(main.config, "stop_mower", Event()),
            patch.object(
                main,
                "_main",
                side_effect=lambda _: main._handle_maintenance(info, Mock()),
            ),
            patch.object(main, "base_scheduler", SimpleNamespace(tasks=[])),
            patch.object(main.device_control, "run", return_value=nullcontext()),
            patch.object(main, "resource_task_session", return_value=nullcontext()),
            patch.object(main, "_close_device_session"),
            patch.object(record, "save_current_state", return_value=False),
            patch.object(instance_supervisor, "task_intent") as intent,
            patch.object(crash_recovery, "cancel") as cancel,
            patch.object(crash_recovery, "activate") as recover,
        ):
            self.server._run_mower_worker({})
            self.assertTrue(main.config.stop_mower.is_set())
            intent.assert_called_once_with(False)
            cancel.assert_called_once_with()
            recover.assert_not_called()
            self.assertEqual(FakeTimer.instances, [])

    def test_zero_duration_saves_queue_then_closes_process_without_timer(self):
        from arknights_mower import __main__ as main
        from arknights_mower.solvers import record
        from arknights_mower.utils import crash_recovery, instance_supervisor
        from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

        task = SchedulerTask(datetime.now(), task_type=TaskTypes.SERVER_UPDATE)
        task.duration_minutes = 0
        pending = SchedulerTask(datetime.now(), task_type=TaskTypes.MAIL)
        state = {"tasks": [task, pending]}
        order = []
        with (
            patch.object(main.config, "stop_mower", Event()),
            patch.object(main, "base_scheduler", None),
            patch.object(main.device_control, "run", return_value=nullcontext()),
            patch.object(main, "resource_task_session", return_value=nullcontext()),
            patch.object(
                main,
                "_main",
                side_effect=lambda _: main._handle_maintenance(
                    task.maintenance_info, None
                ),
            ),
            patch.object(
                main, "_close_device_session", side_effect=lambda: order.append("close")
            ),
            patch.object(
                record,
                "save_state_to_db",
                side_effect=lambda _: order.append("save") or True,
            ) as save,
            patch.object(
                instance_supervisor,
                "task_intent",
                side_effect=lambda _: order.append("stop"),
            ),
            patch.object(crash_recovery, "_cancelled", False),
            patch.object(crash_recovery, "cancel"),
            patch.object(
                self.server.shutdown,
                "request",
                side_effect=lambda _: order.append("exit"),
            ) as exit_process,
        ):
            self.server._run_mower_worker(state)
            self.assertEqual(order, ["save", "close", "stop", "exit"])
            save.assert_called_once_with({"tasks": [pending]})
            exit_process.assert_called_once_with("manual_server_update")
            self.assertEqual(FakeTimer.instances, [])
            self.assertIsNone(self.server.scheduled_start_at)


if __name__ == "__main__":
    unittest.main()
