import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask

from arknights_mower.utils import software_update as update
from arknights_mower.utils import software_update_worker as worker
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.views.software_update import software_update_bp


class SoftwareAutoUpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)
        state = patch.object(runtime, "state_dir", return_value=self.state)
        state.start()
        self.addCleanup(state.stop)
        env = patch.dict(os.environ, {"MOWER_RESTART_JOB": ""})
        env.start()
        self.addCleanup(env.stop)
        settings = patch.object(
            update, "settings_path", return_value=self.state / "settings.json"
        )
        settings.start()
        self.addCleanup(settings.stop)
        self.records = [
            {"kind": "instance", "ready": True, "idle": True, "heartbeat": time.time()}
        ]
        registrations = patch.object(runtime, "instances", return_value=self.records)
        registrations.start()
        self.addCleanup(registrations.stop)

    def test_default_does_not_check_or_install(self):
        with patch.object(update, "check") as check:
            update.check_on_launch()
        check.assert_not_called()

    def test_install_setting_enables_check_and_validates_booleans(self):
        result = update.save_settings({"auto_update": True})
        self.assertTrue(result["settings"]["auto_check"])
        with self.assertRaises(ValueError):
            update.save_settings({"auto_check": "false"})
        update.save_settings({"auto_check": False, "auto_update": False})
        self.assertFalse(update.get_settings()["auto_update"])

    def test_simultaneous_instance_launches_only_check_once(self):
        update.save_settings({"auto_check": True, "channel": "dev"})
        with (
            patch.object(update, "check", return_value={"available": True}) as check,
            patch.object(update, "submit") as submit,
        ):
            for _ in range(3):
                update.check_on_launch()
        check.assert_called_once_with("dev")
        submit.assert_not_called()

    def test_automatic_install_uses_selected_channel_and_restart_mode(self):
        update.save_settings(
            {"auto_update": True, "channel": "dev", "background": False}
        )
        with (
            patch.object(
                update, "check", return_value={"available": True, "check_id": "checked"}
            ) as check,
            patch.object(update, "submit") as submit,
        ):
            update.check_on_launch()
        check.assert_called_once_with("dev")
        submit.assert_called_once_with("checked", False, automatic=True)

    def test_busy_instances_do_not_check_until_all_are_idle(self):
        update.save_settings({"auto_update": True})
        self.records.append({**self.records[0], "idle": False})
        with (
            patch.object(
                update, "check", return_value={"available": True, "check_id": "idle"}
            ) as check,
            patch.object(update, "submit", return_value={"ok": True}) as submit,
        ):
            for _ in range(3):
                update.check_on_launch()
            check.assert_not_called()
            submit.assert_not_called()
            self.assertFalse((self.state / "auto-check.json").exists())
            self.records[1]["idle"] = True
            update.check_on_launch()
        submit.assert_called_once_with("idle", False, automatic=True)

    def test_unknown_or_stale_instances_cannot_authorize_automatic_updates(self):
        update.save_settings({"auto_update": True})
        for changes in (
            {"ready": False},
            {"idle": None},
            {"heartbeat": time.time() - 6},
        ):
            with self.subTest(changes=changes), patch.object(update, "check") as check:
                self.records[:] = [
                    {
                        "kind": "instance",
                        "ready": True,
                        "idle": True,
                        "heartbeat": time.time(),
                        **changes,
                    }
                ]
                update.check_on_launch()
                check.assert_not_called()

    def test_busy_after_check_defers_submission_and_next_idle_rechecks(self):
        update.save_settings({"auto_update": True})

        def check(_channel):
            self.records[0]["idle"] = False
            check_id = update.remember_check(
                {"available": True, "created_at": time.time()}
            )
            return {"available": True, "check_id": check_id}

        with (
            patch.object(update, "check", side_effect=check),
            patch.object(update, "_start_job") as start,
        ):
            update.check_on_launch()
        start.assert_not_called()
        self.assertFalse((self.state / "auto-check.json").exists())
        self.records[0]["idle"] = True
        with (
            patch.object(
                update, "check", return_value={"available": True, "check_id": "fresh"}
            ) as checker,
            patch.object(update, "submit", return_value={"ok": True}) as submit,
        ):
            update.check_on_launch()
        checker.assert_called_once()
        submit.assert_called_once()

    def test_busy_during_preflight_does_not_launch_installer(self):
        def details():
            self.records[0]["idle"] = False
            return {"blockers": []}

        with (
            patch.object(update, "info", side_effect=details),
            patch.object(update.network_settings, "apply_http_proxy"),
            patch.object(update.subprocess, "Popen") as launch,
        ):
            result = update.start_job({"deployment": "release"}, automatic=True)
        self.assertTrue(result["deferred"])
        launch.assert_not_called()
        self.assertFalse((self.state / "active").exists())

    def test_manual_submission_retains_existing_admission(self):
        self.records[0]["idle"] = False
        with patch.object(update, "_start_job", return_value={"ok": True}) as start:
            self.assertTrue(update.start_job({"deployment": "release"})["ok"])
        start.assert_called_once()
        self.assertFalse(start.call_args.kwargs["automatic"])

    def test_busy_during_preparation_cancels_before_any_shutdown(self):
        updater = object.__new__(worker.Worker)
        updater.job = {"id": "automatic", "automatic": True}
        updater.state = self.state
        updater.work = self.state / "job"
        updater.report = Mock()
        self.records.append({**self.records[0], "idle": False})
        runtime.write_json(self.state / "auto-check.json", {"started_at": time.time()})
        with patch.object(worker, "instances", return_value=self.records):
            with self.assertRaises(worker.UpdateCancelled):
                updater.stop_instances()
        self.assertEqual(updater.original, [])
        self.assertFalse((self.state / "shutdown").exists())
        self.assertFalse((self.state / "auto-check.json").exists())

    def test_instance_idle_requires_a_sleeping_scheduler_or_stopped_worker(self):
        scheduler = SimpleNamespace(sleeping=False)
        server = SimpleNamespace(
            mower_thread=Mock(is_alive=lambda: True),
            _performance_test_status=lambda: {"status": "idle"},
            maa_check_job={"status": "idle"},
            maa_update_job={"status": "idle"},
            maa_resource_update_job={"status": "idle"},
            _job_running=lambda job: job["status"] == "running",
            resource_update=SimpleNamespace(running=lambda: False),
            configuration_test_active_requests=0,
            device_operation_active_requests=0,
            chat_active_requests=0,
            _recycling_reports_running=lambda: False,
            _configuration_recovery_pending=lambda: False,
        )
        main = SimpleNamespace(base_scheduler=None)
        with patch.dict(
            sys.modules,
            {
                "arknights_mower.__main__": main,
                "arknights_mower.utils.maa_backup": SimpleNamespace(
                    maa_in_use=lambda: False
                ),
            },
        ):
            self.assertFalse(update.instance_idle(server))
            main.base_scheduler = scheduler
            self.assertFalse(update.instance_idle(server))
            scheduler.sleeping = True
            self.assertTrue(update.instance_idle(server))
            for field in (
                "chat_active_requests",
                "configuration_test_active_requests",
                "device_operation_active_requests",
            ):
                setattr(server, field, 1)
                self.assertFalse(update.instance_idle(server))
                setattr(server, field, 0)
            server.maa_update_job["status"] = "running"
            self.assertFalse(update.instance_idle(server))
            server.maa_update_job["status"] = "idle"
            server.mower_thread = None
            main.base_scheduler = None
            self.assertTrue(update.instance_idle(server))

    def test_automatic_shutdown_requests_preserve_running_state_and_include_ocr(self):
        updater = object.__new__(worker.Worker)
        updater.job = {"id": "automatic", "automatic": True}
        updater.state = self.state
        updater.work = self.state / "job"
        updater.report = Mock()
        records = [
            {**self.records[0], "id": "mower", "pid": 123, "running": True},
            {"kind": "ocr-service", "id": "ocr", "pid": 456},
        ]
        with (
            patch.object(worker, "instances", return_value=records),
            patch.object(worker, "registered_process_alive", return_value=False),
            patch.object(worker, "wait_for_supervisor_release"),
        ):
            updater.stop_instances()
        self.assertEqual(updater.original, records)
        self.assertTrue(updater.original[0]["running"])
        for record in records:
            self.assertEqual(
                runtime.read_json(self.state / "shutdown" / f"{record['id']}.json"),
                {"job": "automatic", "idle_only": True},
            )

    def test_automatic_shutdown_keeps_ocr_until_all_instances_exit(self):
        updater = object.__new__(worker.Worker)
        updater.job = {"id": "automatic", "automatic": True}
        updater.state = self.state
        updater.work = self.state / "job"
        updater.report = Mock()
        records = [
            {**self.records[0], "id": "mower", "pid": 123},
            {**self.records[0], "id": "second", "pid": 124},
            {"kind": "ocr-service", "id": "ocr", "pid": 456},
            {"kind": "ocr-worker", "id": "model", "pid": 457},
        ]
        stopped = set()
        observations = []

        def advance(_seconds):
            self.assertTrue((self.state / "shutdown/mower.json").exists())
            if len(stopped) < 2:
                self.assertFalse((self.state / "shutdown/ocr.json").exists())
                self.assertFalse((self.state / "shutdown/model.json").exists())
                observations.append("task continues with OCR")
                stopped.add(123 if not stopped else 124)
            else:
                self.assertTrue((self.state / "shutdown/ocr.json").exists())
                self.assertTrue((self.state / "shutdown/model.json").exists())
                observations.append("OCR exits after instances")
                stopped.update((456, 457))

        with (
            patch.object(worker, "instances", return_value=records),
            patch.object(
                worker,
                "registered_process_alive",
                side_effect=lambda record: record["pid"] not in stopped,
            ),
            patch.object(worker, "wait_for_supervisor_release"),
            patch.object(
                worker, "time", SimpleNamespace(monotonic=time.monotonic, sleep=advance)
            ),
        ):
            updater.stop_instances()
        self.assertEqual(
            observations,
            ["task continues with OCR"] * 2 + ["OCR exits after instances"],
        )
        self.assertEqual(updater.stopped, records)

    def test_automatic_shutdown_timeout_does_not_stop_ocr_for_busy_instance(self):
        updater = object.__new__(worker.Worker)
        updater.job = {"id": "automatic", "automatic": True}
        updater.state = self.state
        updater.work = self.state / "job"
        updater.report = Mock()
        records = [
            {**self.records[0], "id": "mower", "pid": 123},
            {"kind": "ocr-service", "id": "ocr", "pid": 456},
        ]
        clock = iter((0, 0, 91))
        with (
            patch.object(worker, "instances", return_value=records),
            patch.object(worker, "registered_process_alive", return_value=True),
            patch.object(
                worker,
                "time",
                SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "90 秒"):
                updater.stop_instances()
        self.assertTrue((self.state / "shutdown/mower.json").exists())
        self.assertFalse((self.state / "shutdown/ocr.json").exists())

    def test_restart_checks_without_immediately_reinstalling(self):
        update.save_settings({"auto_update": True})
        for status in ("succeeded", "failed", "cancelled"):
            with self.subTest(status=status):
                (self.state / "auto-check.json").unlink(missing_ok=True)
                runtime.write_json(
                    self.state / "status.json",
                    {
                        "id": "restart-fixture",
                        "status": status,
                        "updated_at": time.time(),
                    },
                )
                with (
                    patch.dict(os.environ, {"MOWER_RESTART_JOB": "restart-fixture"}),
                    patch.object(
                        update,
                        "check",
                        return_value={"available": True, "check_id": "new"},
                    ) as check,
                    patch.object(update, "submit") as submit,
                ):
                    update.check_on_launch()
                check.assert_called_once()
                submit.assert_not_called()

    def test_active_operation_defers_automatic_check(self):
        update.save_settings({"auto_check": True})
        with (
            patch.object(runtime, "active_job", return_value=True),
            patch.object(update, "check") as check,
        ):
            update.check_on_launch()
        check.assert_not_called()

    def test_preflight_failure_is_visible_without_losing_settings(self):
        update.save_settings({"auto_update": True})
        with (
            patch.object(
                update, "check", return_value={"available": True, "check_id": "fixture"}
            ),
            patch.object(update, "submit", side_effect=ValueError("本地文件需要备份")),
        ):
            update.check_on_launch()
        result = update.status()["last_check"]
        self.assertFalse(result["ok"])
        self.assertIn("本地文件需要备份", result["message"])
        self.assertTrue(update.get_settings()["auto_update"])

    def test_enabling_install_and_changing_channel_bypass_previous_check_dedup(self):
        update.save_settings({"auto_check": True, "channel": "beta"})
        with (
            patch.object(
                update, "check", return_value={"available": True, "check_id": "new"}
            ) as check,
            patch.object(update, "submit") as submit,
        ):
            update.check_on_launch()
            submit.assert_not_called()
            update.save_settings({"auto_update": True})
            update.check_on_launch()
            submit.assert_called_once()
            update.save_settings({"channel": "stable"})
            update.check_on_launch()
        self.assertEqual(
            [call.args[0] for call in check.call_args_list], ["beta", "beta", "stable"]
        )

    def test_disabling_auto_update_during_check_prevents_stale_install(self):
        update.save_settings({"auto_update": True})

        def check(_channel):
            update.save_settings({"auto_update": False, "auto_check": False})
            return {"available": True, "check_id": "obsolete"}

        with (
            patch.object(update, "check", side_effect=check),
            patch.object(update, "submit") as submit,
        ):
            update.check_on_launch()
        submit.assert_not_called()

    def test_request_defers_until_restart_operation_releases_its_lock(self):
        update.save_settings({"auto_check": True})
        checked = Event()
        with (
            patch.object(runtime, "active_job", side_effect=[True, None]),
            patch.dict(os.environ, {"MOWER_RESTART_JOB": "process-restart"}),
            patch.object(
                update,
                "check",
                side_effect=lambda _: checked.set() or {"available": False},
            ) as check,
        ):
            result = update.request_auto_check()
            thread = update._auto_check_thread
            self.assertTrue(result["scheduled"])
            self.assertTrue(checked.wait(3))
            if thread:
                thread.join(3)
                self.assertFalse(thread.is_alive())
            check.assert_called_once()

    def test_simultaneous_requests_coalesce_and_saved_changes_are_not_lost(self):
        update.save_settings({"auto_check": True, "channel": "beta"})
        entered = Event()
        release = Event()
        rechecked = Event()

        def check(channel):
            if channel == "beta":
                entered.set()
                if not release.wait(3):
                    raise TimeoutError("test did not release check")
            else:
                rechecked.set()
            return {"available": False}

        with patch.object(update, "check", side_effect=check) as checker:
            update.request_auto_check()
            thread = update._auto_check_thread
            try:
                self.assertTrue(entered.wait(2))
                for _ in range(3):
                    update.request_auto_check()
                    self.assertIs(update._auto_check_thread, thread)
                update.save_settings({"channel": "stable"})
                update.request_auto_check()
            finally:
                release.set()
                thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertTrue(rechecked.is_set())
            self.assertEqual(
                [call.args[0] for call in checker.call_args_list], ["beta", "stable"]
            )

    def test_disabled_setting_does_not_start_worker(self):
        with patch.object(update, "Thread") as thread:
            self.assertFalse(update.request_auto_check()["scheduled"])
        thread.assert_not_called()

    def test_auto_check_route_requires_token_and_update_header_after_forwarding(self):
        app = Flask(__name__)
        app.token = "test-token"
        app.register_blueprint(software_update_bp)
        client = app.test_client()
        headers = {"token": "test-token", "X-Mower-Update": "1"}
        with patch.object(
            update, "request_auto_check", return_value={"ok": True, "scheduled": True}
        ) as schedule:
            for denied in (
                {},
                {"token": "test-token"},
                {**headers, "token": "wrong", "Origin": "https://mower.example:8443"},
            ):
                self.assertEqual(
                    client.post(
                        "/software-update/auto-check", json={}, headers=denied
                    ).status_code,
                    403,
                )
            schedule.assert_not_called()
            response = client.post(
                "/software-update/auto-check",
                json={},
                headers={
                    **headers,
                    "Host": "127.0.0.1:58000",
                    "Origin": "https://mower.example:8443",
                },
            )
            self.assertTrue(response.json["scheduled"])
            schedule.assert_called_once()
