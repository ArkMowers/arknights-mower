import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils import software_update as update
from arknights_mower.utils import update_runtime as runtime


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

    def test_restart_does_not_loop_into_another_automatic_update(self):
        update.save_settings({"auto_update": True})
        with (
            patch.dict(os.environ, {"MOWER_RESTART_JOB": "restart-fixture"}),
            patch.object(update, "check") as check,
        ):
            update.check_on_launch()
        check.assert_not_called()

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
