import os
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from flask import Flask

from arknights_mower.utils import software_update as update
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
        submit.assert_called_once_with("checked", False)

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

    def test_auto_check_route_requires_token_and_same_origin_update_header(self):
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
                {**headers, "Origin": "https://other.test"},
            ):
                self.assertEqual(
                    client.post(
                        "/software-update/auto-check", json={}, headers=denied
                    ).status_code,
                    403,
                )
            schedule.assert_not_called()
            response = client.post(
                "/software-update/auto-check", json={}, headers=headers
            )
            self.assertTrue(response.json["scheduled"])
            schedule.assert_called_once()
