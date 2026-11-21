import os
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

    def test_update_restarts_stopped_instance_with_original_reservation(self):
        from arknights_mower.utils.lifecycle import Shutdown

        job = "a" * 32
        old_process = Shutdown()
        new_process = Shutdown()
        with (
            TemporaryDirectory() as folder,
            patch.object(self.server, "state_dir", return_value=Path(folder)),
            patch.object(self.server, "shutdown", old_process),
            patch.object(self.server, "mower_thread", None),
            patch.object(self.server, "active_job", return_value=True) as updating,
            patch.object(self.server, "_start_mower", return_value=True) as start,
        ):
            response = self.client.put(
                "/scheduled-start", json={"delay_seconds": 1800}, headers=self.headers
            )
            original = FakeTimer.instances[-1]
            self.server._shutdown_for_software_update(job)
            self.assertTrue(old_process.closing)
            self.assertTrue(original.cancelled)
            self.assertIsNone(self.server.scheduled_start_at)
            with patch.object(self.server, "shutdown", new_process):
                self.server._restore_scheduled_start(job)
                self.assertEqual(
                    self.client.get("/status", headers=self.headers).json[
                        "scheduled_start_at"
                    ],
                    response.json["scheduled_start_at"],
                )
                current = FakeTimer.instances[-1]
                self.assertAlmostEqual(current.delay, 1800, delta=3)
                current.callback()
                start.assert_not_called()
                self.assertIsNotNone(self.server.scheduled_start_at)
                updating.return_value = False
                FakeTimer.instances[-1].callback()
                current.callback()
                start.assert_called_once_with("2")
                self.assertFalse(self.server._scheduled_start_transfer(job).exists())

    def test_overdue_update_reservation_keeps_saved_queue_mode(self):
        from arknights_mower.utils.lifecycle import Shutdown

        job = "b" * 32
        startup_ready = Event()
        with (
            TemporaryDirectory() as folder,
            patch.object(self.server, "state_dir", return_value=Path(folder)),
            patch.object(self.server, "shutdown", Shutdown()),
            patch.object(self.server, "mower_thread", None),
            patch.object(self.server, "active_job", return_value=False),
            patch.object(self.server, "_start_mower", return_value=True) as start,
        ):
            self.server._schedule_start(30, start_type="0")
            self.server._shutdown_for_software_update(job)
            due = datetime.fromisoformat(
                self.server.json.loads(
                    self.server._scheduled_start_transfer(job).read_text(
                        encoding="utf-8"
                    )
                )["at"]
            )
            with (
                patch.object(self.server, "shutdown", Shutdown()),
                patch.object(
                    self.server.time, "time", return_value=due.timestamp() + 60
                ),
            ):
                self.server._restore_scheduled_start(job, startup_ready=startup_ready)
                self.assertEqual(FakeTimer.instances[-1].delay, 0)
                FakeTimer.instances[-1].callback()
                start.assert_not_called()
                self.assertEqual(self.server.scheduled_start_at, due)
                startup_ready.set()
                FakeTimer.instances[-1].callback()
            start.assert_called_once_with("0")

    def test_update_handoff_is_scoped_to_job_instance_and_profile(self):
        from arknights_mower.utils import config_profiles
        from arknights_mower.utils.lifecycle import Shutdown

        job = "c" * 32
        with (
            TemporaryDirectory() as folder,
            patch.object(self.server, "state_dir", return_value=Path(folder)),
            patch.object(self.server, "shutdown", Shutdown()),
            patch.object(config_profiles, "current_generation", return_value="old"),
        ):
            self.server._schedule_start(60)
            self.server._shutdown_for_software_update(job)
            self.server._restore_scheduled_start("d" * 32)
            with patch.object(self.server, "tmp_dir", Path(folder) / "other"):
                self.server._restore_scheduled_start(job)
            self.assertIsNone(self.server.scheduled_start_at)
            with patch.object(
                config_profiles, "current_generation", return_value="new"
            ):
                self.server._restore_scheduled_start(job)
            self.assertIsNone(self.server.scheduled_start_at)
            self.assertFalse(self.server._scheduled_start_transfer(job).exists())

    def test_cancel_restored_reservation_requires_token_and_survives_relaunch(self):
        from arknights_mower.utils.lifecycle import Shutdown

        job = "e" * 32
        with (
            TemporaryDirectory() as folder,
            patch.object(self.server, "state_dir", return_value=Path(folder)),
            patch.object(self.server, "shutdown", Shutdown()),
            patch.object(self.server.app, "token", "fixture-token", create=True),
            patch.object(self.server, "mower_thread", None),
        ):
            self.server._schedule_start(60)
            self.server._shutdown_for_software_update(job)
            with patch.object(self.server, "shutdown", Shutdown()):
                self.server._restore_scheduled_start(job)
                for headers in ({}, {"token": "incorrect"}):
                    self.assertEqual(
                        self.client.delete(
                            "/scheduled-start", headers=headers
                        ).status_code,
                        403,
                    )
                    self.assertEqual(
                        self.client.put(
                            "/scheduled-start",
                            json={"delay_seconds": 120},
                            headers=headers,
                        ).status_code,
                        403,
                    )
                    self.assertTrue(self.server._scheduled_start_transfer(job).exists())
                    self.assertEqual(
                        self.client.get("/stop", headers=headers).status_code, 403
                    )
                response = self.client.delete(
                    "/scheduled-start", headers={"token": "fixture-token"}
                )
                self.assertEqual(response.status_code, 200)
                self.server._restore_scheduled_start(job)
                self.assertIsNone(self.server.scheduled_start_at)
                self.assertFalse(self.server._scheduled_start_transfer(job).exists())

    def test_native_restart_failure_preserves_timer_until_host_accepts(self):
        from arknights_mower.utils.lifecycle import Shutdown

        with (
            TemporaryDirectory() as folder,
            patch.object(self.server, "shutdown", Shutdown()),
        ):
            transfer = Path(folder) / "reservation.json"
            expected = self.server._schedule_start(600, start_type="0")
            original = FakeTimer.instances[-1]

            def reject(pending):
                self.assertTrue(pending)
                self.assertTrue(transfer.is_file())
                raise self.server.RestartHandoffRejected("host declined")

            with self.assertRaises(self.server.RestartHandoffRejected):
                self.server.handoff_scheduled_start(transfer, before_shutdown=reject)
            self.assertFalse(self.server.shutdown.closing)
            self.assertFalse(transfer.exists())
            self.assertFalse(original.cancelled)
            self.assertEqual(self.server.scheduled_start_at.isoformat(), expected)
            accept = Mock()
            self.assertTrue(
                self.server.handoff_scheduled_start(transfer, before_shutdown=accept)
            )
            accept.assert_called_once_with(True)
            self.assertTrue(original.cancelled)
            self.assertTrue(self.server.shutdown.closing)
            with patch.object(self.server, "shutdown", Shutdown()):
                self.assertTrue(self.server.restore_scheduled_start(transfer))
                self.assertEqual(self.server.scheduled_start_at.isoformat(), expected)
                self.assertEqual(self.server.scheduled_start_type, "0")

    def test_unconfirmed_host_reply_preserves_transfer_and_local_cancellation(self):
        with TemporaryDirectory() as folder:
            transfer = Path(folder) / "reservation.json"
            expected = self.server._schedule_start(600)
            with self.assertRaises(TimeoutError):
                self.server.handoff_scheduled_start(
                    transfer, before_shutdown=Mock(side_effect=TimeoutError)
                )
            self.assertTrue(transfer.is_file())
            self.assertFalse(FakeTimer.instances[-1].cancelled)
            self.assertEqual(self.server.scheduled_start_at.isoformat(), expected)
            self.assertTrue(self.server._cancel_scheduled_start())
            self.assertFalse(transfer.exists())

    def test_cancel_requires_readable_update_owner_before_disarming(self):
        from arknights_mower.utils import update_runtime as runtime

        record = {"id": "instance", "kind": "instance", "pid": os.getpid()}
        job = "a" * 32
        for fault in ("permission", "invalid_json", "invalid_owner"):
            with self.subTest(fault=fault), TemporaryDirectory() as folder:
                directory = Path(folder)
                owner = directory / "active/owner.json"
                runtime.write_json(owner, {"pid": os.getpid(), "id": job})
                runtime.write_json(directory / "instances/instance.json", record)
                if fault == "invalid_json":
                    owner.write_text("{", encoding="utf-8")
                elif fault == "invalid_owner":
                    runtime.write_json(owner, {"pid": os.getpid()})
                read = Path.read_text

                def read_owner(path, *args, **kwargs):
                    if path == owner and fault == "permission":
                        raise PermissionError(path)
                    return read(path, *args, **kwargs)

                with patch.object(runtime, "state_dir", return_value=directory):
                    self.server._schedule_start(60)
                    timer = FakeTimer.instances[-1]
                    with patch.object(Path, "read_text", read_owner):
                        response = self.client.delete(
                            "/scheduled-start", headers=self.headers
                        )
                    self.assertEqual(response.status_code, 503)
                    self.assertFalse(timer.cancelled)
                    self.assertIsNotNone(self.server.scheduled_start_at)
                    runtime.write_json(owner, {"pid": os.getpid(), "id": job})
                    response = self.client.delete(
                        "/scheduled-start", headers=self.headers
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(timer.cancelled)
                    self.assertTrue(runtime.task_stop_requested(record, job, directory))

    def test_failed_cancel_marker_keeps_reservation_for_retry(self):
        self.server._schedule_start(60)
        with patch(
            "arknights_mower.utils.update_runtime.record_task_stop", side_effect=OSError
        ):
            response = self.client.delete("/scheduled-start", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(FakeTimer.instances[-1].cancelled)
        self.assertIsNotNone(self.server.scheduled_start_at)
        self.assertEqual(
            self.client.delete("/scheduled-start", headers=self.headers).status_code,
            200,
        )

    def test_failed_update_handoff_does_not_close_or_cancel_reservation(self):
        from arknights_mower.utils.lifecycle import Shutdown

        with (
            patch.object(self.server, "shutdown", Shutdown()) as lifecycle,
            patch.object(self.server, "write_json", side_effect=PermissionError),
        ):
            expected = self.server._schedule_start(120)
            self.server._shutdown_for_software_update("f" * 32)
            self.assertFalse(lifecycle.closing)
            self.assertFalse(FakeTimer.instances[-1].cancelled)
            self.assertEqual(self.server.scheduled_start_at.isoformat(), expected)

    def test_put_checks_shutdown_after_acquiring_reservation_lock(self):
        from arknights_mower.utils.lifecycle import Shutdown

        job = "c" * 32
        server = self.server
        lock = server.scheduled_start_lock

        class HandoffLock:
            started = False

            def __enter__(self):
                if not self.started:
                    self.started = True
                    server._shutdown_for_software_update(job)
                lock.acquire()

            def __exit__(self, *exc):
                lock.release()

        with (
            TemporaryDirectory() as folder,
            patch.object(self.server, "state_dir", return_value=Path(folder)),
            patch.object(self.server, "shutdown", Shutdown()),
            patch.object(self.server, "mower_thread", None),
        ):
            original = self.server._schedule_start(60)
            with patch.object(self.server, "scheduled_start_lock", HandoffLock()):
                response = self.client.put(
                    "/scheduled-start",
                    json={"delay_seconds": 120},
                    headers=self.headers,
                )
            self.assertEqual(response.status_code, 409)
            self.assertIsNone(self.server.scheduled_start_at)
            self.assertEqual(
                self.server.json.loads(
                    self.server._scheduled_start_transfer(job).read_text(
                        encoding="utf-8"
                    )
                )["at"],
                original,
            )

    def test_stop_before_handoff_is_preserved_and_stop_after_is_rejected(self):
        from arknights_mower.solvers import record
        from arknights_mower.utils import update_runtime
        from arknights_mower.utils.lifecycle import Shutdown

        for stop_first in (True, False):
            with (
                self.subTest(stop_first=stop_first),
                TemporaryDirectory() as folder,
                patch.object(self.server, "state_dir", return_value=Path(folder)),
                patch.object(self.server, "shutdown", Shutdown()),
                patch.object(self.server, "mower_thread", None),
                patch.object(self.server, "_request_mower_stop"),
                patch.object(
                    self.server, "_wait_mower_stop", return_value=True
                ) as wait,
                patch.object(record, "save_state_to_db"),
                patch.object(update_runtime, "record_task_stop") as record_stop,
            ):
                job = "a" * 32
                self.server._schedule_start(60)
                if not stop_first:
                    self.server._shutdown_for_software_update(job)
                response = self.client.get("/stop", headers=self.headers)
                if stop_first:
                    self.assertEqual(response.get_data(as_text=True), "true")
                    record_stop.assert_called_once_with()
                    wait.assert_called_once_with()
                    self.server._shutdown_for_software_update(job)
                else:
                    self.assertEqual(response.status_code, 409)
                    record_stop.assert_not_called()
                    wait.assert_not_called()
                self.assertEqual(
                    self.server._scheduled_start_transfer(job).exists(), not stop_first
                )

    def test_user_stop_signals_before_worker_can_schedule_maintenance_resume(self):
        from arknights_mower import __main__ as main
        from arknights_mower.solvers import record
        from arknights_mower.utils import (
            crash_recovery,
            instance_supervisor,
            update_runtime,
        )
        from arknights_mower.utils.news_checker import MaintenanceInfo

        now = datetime.now()
        info = MaintenanceInfo(
            now, now + timedelta(minutes=10), "major", "停服更新", "", "fixture"
        )
        server = self.server
        wait = server._wait_mower_stop

        def finish_worker(*args, **kwargs):
            self.assertFalse(server.scheduled_start_lock._is_owned())
            server._run_mower_worker({})
            return wait(*args, **kwargs)

        with (
            patch.object(server, "mower_thread", None),
            patch.object(server.config, "stop_mower", Event()),
            patch.object(server.round_stop, "_requested", False),
            patch.object(crash_recovery, "_cancelled", False),
            patch.object(crash_recovery, "_progress", {}),
            patch.object(crash_recovery, "notice_path", return_value=None),
            patch.object(instance_supervisor, "task_intent"),
            patch.object(record, "save_state_to_db"),
            patch.object(update_runtime, "record_task_stop"),
            patch.object(main, "main", return_value=info) as run,
            patch.object(server, "_wait_mower_stop", side_effect=finish_worker),
        ):
            server._schedule_start(120)
            response = self.client.get("/stop", headers=self.headers)
            self.assertEqual(response.get_data(as_text=True), "true")
            run.assert_called_once()
            self.assertEqual(len(FakeTimer.instances), 1)
            self.assertIsNone(server.scheduled_start_at)

    def test_start_exception_discards_restored_reservation(self):
        from arknights_mower.utils.lifecycle import Shutdown

        job = "a" * 32
        with (
            TemporaryDirectory() as folder,
            patch.object(self.server, "state_dir", return_value=Path(folder)),
            patch.object(self.server, "shutdown", Shutdown()),
            patch.object(self.server, "active_job", return_value=False),
            patch.object(self.server, "_start_mower", side_effect=OSError) as start,
        ):
            self.server._schedule_start(60)
            self.server._shutdown_for_software_update(job)
            with patch.object(self.server, "shutdown", Shutdown()):
                self.server._restore_scheduled_start(job)
                timer = FakeTimer.instances[-1]
                with self.assertLogs("arknights_mower.utils.log", level="ERROR"):
                    timer.callback()
                timer.callback()
                start.assert_called_once_with("2")
                self.assertTrue(timer.cancelled)
                self.assertIsNone(self.server.scheduled_start_at)
                self.assertFalse(self.server._scheduled_start_transfer(job).exists())
                self.server._shutdown_for_software_update(job)
            self.assertFalse(self.server._restore_scheduled_start(job))

    def test_cancel_with_undeletable_handoff_does_not_restore_same_reservation(self):
        from arknights_mower.utils.lifecycle import Shutdown

        job = "d" * 32
        unlink = Path.unlink
        with (
            TemporaryDirectory() as folder,
            patch.object(self.server, "state_dir", return_value=Path(folder)),
            patch.object(self.server, "shutdown", Shutdown()),
            patch.object(self.server, "mower_thread", None),
            patch.object(self.server, "_start_mower") as start,
        ):
            self.server._schedule_start(60)
            self.server._shutdown_for_software_update(job)
            transfer = self.server._scheduled_start_transfer(job)

            def locked_file(path, **kwargs):
                if path == transfer:
                    raise PermissionError("handoff is locked")
                return unlink(path, **kwargs)

            with (
                patch.object(self.server, "shutdown", Shutdown()),
                patch.object(Path, "unlink", locked_file),
            ):
                self.server._restore_scheduled_start(job)
                timer = FakeTimer.instances[-1]
                response = self.client.delete("/scheduled-start", headers=self.headers)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(timer.cancelled)
                timer.callback()
                start.assert_not_called()
                self.assertTrue(transfer.exists())
                self.server._restore_scheduled_start(job)
                self.assertIsNone(self.server.scheduled_start_at)

                new_time = self.server._schedule_start(120)
                self.server._shutdown_for_software_update(job)
                with patch.object(self.server, "shutdown", Shutdown()):
                    self.server._restore_scheduled_start(job)
                    self.assertEqual(
                        self.server.scheduled_start_at.isoformat(), new_time
                    )
                    self.server._cancel_scheduled_start()

    def test_manual_start_reports_success_even_if_handoff_cleanup_fails(self):
        from arknights_mower.utils.lifecycle import Shutdown

        job = "f" * 32
        with (
            TemporaryDirectory() as folder,
            patch.object(self.server, "state_dir", return_value=Path(folder)),
            patch.object(self.server, "shutdown", Shutdown()),
            patch.object(self.server, "mower_thread", None),
            patch.object(self.server, "active_job", return_value=False),
            patch.object(self.server, "_job_running", return_value=False),
            patch.object(self.server, "get_path", return_value=Path(folder)),
            patch.object(self.server, "load_state", return_value={}),
            patch.object(self.server, "log_stream"),
            patch.object(self.server, "Thread") as worker,
            patch.object(self.server, "set_mower_thread"),
        ):
            self.server._schedule_start(60)
            self.server._shutdown_for_software_update(job)
            with patch.object(self.server, "shutdown", Shutdown()):
                self.server._restore_scheduled_start(job)
                timer = FakeTimer.instances[-1]
                with (
                    patch.object(Path, "unlink", side_effect=PermissionError),
                    patch.object(
                        self.server, "write_json", side_effect=PermissionError
                    ),
                ):
                    response = self.client.get("/start/0", headers=self.headers)
                    self.assertEqual(response.get_data(as_text=True), "true")
                    worker.return_value.start.assert_called_once_with()
                    self.assertTrue(timer.cancelled)
                    self.assertIsNone(self.server.scheduled_start_at)
                    response = self.client.delete(
                        "/scheduled-start", headers=self.headers
                    )
                    self.assertEqual(response.status_code, 503)
                self.server._cancel_scheduled_start()

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
