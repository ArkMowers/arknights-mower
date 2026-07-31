import json
import unittest
from unittest.mock import MagicMock, patch

import arknights_mower.__main__ as mower_main
import arknights_mower.solvers.base_schedule as base_schedule
from arknights_mower.utils.config.conf import MaaPart
from arknights_mower.utils.maa_check import (
    MAA_CHECK_SCRIPT,
    is_maa_connectivity_check_enabled,
    maa_check_params,
    maa_check_timeout_result,
    parse_maa_check_output,
    run_maa_connectivity_check,
)


class TestMaaCheck(unittest.TestCase):
    def test_check_uses_configured_device(self):
        mock_conf = MagicMock(
            maa_path="/maa",
            maa_adb_path="adb",
            adb="configured-device",
            maa_conn_preset="CompatMac",
            maa_touch_option="maatouch",
        )

        with patch("arknights_mower.utils.maa_check.config.conf", mock_conf):
            params = maa_check_params()

        self.assertEqual(params["adb"], "configured-device")

    def test_check_loads_incremental_resources_used_by_runtime(self):
        self.assertIn(
            'Asst.load(path=maa_path, incremental_path=maa_path / "cache")',
            MAA_CHECK_SCRIPT,
        )

    def test_check_distinguishes_connection_failure_from_test_error(self):
        self.assertIn('"status": "connection_failed"', MAA_CHECK_SCRIPT)
        self.assertIn('"status": "error"', MAA_CHECK_SCRIPT)

    def test_abnormal_process_exit_is_not_reported_as_connection_failure(self):
        result = parse_maa_check_output("", "  <no Python frame>\n", 1)

        self.assertEqual(result["status"], "error")
        self.assertIn("Maa测试进程异常退出：1", result["message"])

    def test_timeout_has_distinct_status(self):
        self.assertEqual(
            maa_check_timeout_result(5),
            {
                "status": "timeout",
                "message": "Maa连通性测试超时（5秒），已终止测试进程",
            },
        )

    def test_check_params_are_json_serializable(self):
        mock_conf = MagicMock(
            maa_path="/maa",
            maa_adb_path="adb",
            adb="configured-device",
            maa_conn_preset="CompatMac",
            maa_touch_option="maatouch",
        )

        with patch("arknights_mower.utils.maa_check.config.conf", mock_conf):
            params = maa_check_params()

        json.dumps(params)

    def test_automatic_check_option_is_serialized(self):
        conf = MaaPart(maa_startup_check=True)

        self.assertTrue(conf.model_dump()["maa_startup_check"])

    def test_automatic_check_uses_connected_device(self):
        completed = MagicMock(
            stdout='{"status": "success", "message": "ok"}\n',
            stderr="",
            returncode=0,
        )

        with (
            patch("arknights_mower.utils.maa_check.__system__", "linux"),
            patch(
                "arknights_mower.utils.maa_check.subprocess.run",
                return_value=completed,
            ) as mock_run,
        ):
            result = run_maa_connectivity_check(adb="connected-device")

        self.assertEqual(result, {"status": "success", "message": "ok"})
        command = mock_run.call_args.args[0]
        self.assertEqual(json.loads(command[-1])["adb"], "connected-device")
        self.assertFalse(mock_run.call_args.kwargs["close_fds"])
        self.assertNotIn("creationflags", mock_run.call_args.kwargs)

    def test_windows_check_hides_console_without_posix_options(self):
        completed = MagicMock(
            stdout='{"status": "success", "message": "ok"}\n',
            stderr="",
            returncode=0,
        )

        with (
            patch("arknights_mower.utils.maa_check.__system__", "windows"),
            patch(
                "arknights_mower.utils.maa_check.subprocess.CREATE_NO_WINDOW",
                0x08000000,
                create=True,
            ),
            patch(
                "arknights_mower.utils.maa_check.subprocess.run",
                return_value=completed,
            ) as mock_run,
        ):
            result = run_maa_connectivity_check()

        self.assertEqual(result, {"status": "success", "message": "ok"})
        self.assertEqual(mock_run.call_args.kwargs["creationflags"], 0x08000000)
        self.assertNotIn("close_fds", mock_run.call_args.kwargs)

    def test_automatic_check_setting_is_read_from_config(self):
        with patch(
            "arknights_mower.utils.maa_check.config.conf.maa_startup_check", True
        ):
            self.assertTrue(is_maa_connectivity_check_enabled())

    def test_initialize_maa_checks_before_loading_maa(self):
        scheduler = object.__new__(base_schedule.BaseSchedulerSolver)
        scheduler.MAA = object()
        scheduler.check_maa_connectivity = MagicMock(
            side_effect=RuntimeError("preflight failed")
        )

        with (
            patch.object(
                base_schedule,
                "is_maa_connectivity_check_enabled",
                return_value=True,
            ),
            self.assertRaisesRegex(RuntimeError, "preflight failed"),
        ):
            scheduler.initialize_maa()

        self.assertIsNone(scheduler.MAA)
        scheduler.check_maa_connectivity.assert_called_once_with("调用前")

    def test_disabled_automatic_check_preserves_existing_maa(self):
        scheduler = object.__new__(base_schedule.BaseSchedulerSolver)
        existing_maa = object()
        scheduler.MAA = existing_maa
        scheduler.check_maa_connectivity = MagicMock()

        with (
            patch.object(
                base_schedule,
                "is_maa_connectivity_check_enabled",
                return_value=False,
            ),
            patch.object(base_schedule.config.stop_maa, "clear") as mock_clear,
            patch.object(
                base_schedule.pathlib, "Path", side_effect=RuntimeError("stop")
            ),
            self.assertRaisesRegex(RuntimeError, "stop"),
        ):
            scheduler.initialize_maa()

        mock_clear.assert_called_once_with()
        scheduler.check_maa_connectivity.assert_not_called()
        self.assertIs(scheduler.MAA, existing_maa)

    def test_disabled_automatic_check_preserves_maa_until_after_rest(self):
        scheduler = object.__new__(base_schedule.BaseSchedulerSolver)
        existing_maa = object()
        scheduler.MAA = existing_maa
        scheduler.rest_until_next_task = MagicMock(
            side_effect=lambda: self.assertIs(scheduler.MAA, existing_maa)
        )

        with patch.object(
            base_schedule,
            "is_maa_connectivity_check_enabled",
            return_value=False,
        ):
            scheduler.rest_after_maa()

        scheduler.rest_until_next_task.assert_called_once_with()
        self.assertIsNone(scheduler.MAA)

    def test_enabled_automatic_check_releases_maa_before_rest(self):
        scheduler = object.__new__(base_schedule.BaseSchedulerSolver)
        scheduler.MAA = object()
        scheduler.rest_until_next_task = MagicMock(
            side_effect=lambda: self.assertIsNone(scheduler.MAA)
        )

        with patch.object(
            base_schedule,
            "is_maa_connectivity_check_enabled",
            return_value=True,
        ):
            scheduler.rest_after_maa()

        scheduler.rest_until_next_task.assert_called_once_with()

    def test_scheduler_check_uses_connected_device(self):
        scheduler = object.__new__(base_schedule.BaseSchedulerSolver)
        scheduler.device = MagicMock()
        scheduler.device.client.device_id = "connected-device"

        with patch.object(
            base_schedule,
            "run_maa_connectivity_check",
            return_value={"status": "success", "message": "ok"},
        ) as mock_check:
            scheduler.check_maa_connectivity("启动预检")

        mock_check.assert_called_once_with(adb="connected-device")

    def test_scheduler_blocks_every_non_success_result(self):
        scheduler = object.__new__(base_schedule.BaseSchedulerSolver)
        scheduler.device = MagicMock()
        scheduler.device.client.device_id = "connected-device"

        with (
            patch.object(
                base_schedule,
                "run_maa_connectivity_check",
                return_value={"status": "error", "message": "checker crashed"},
            ),
            self.assertRaisesRegex(RuntimeError, "checker crashed"),
        ):
            scheduler.check_maa_connectivity("调用前")

        with (
            patch.object(
                base_schedule,
                "run_maa_connectivity_check",
                return_value={
                    "status": "connection_failed",
                    "message": "connect returned false",
                },
            ),
            self.assertRaisesRegex(RuntimeError, "connect returned false"),
        ):
            scheduler.check_maa_connectivity("调用前")

        with (
            patch.object(
                base_schedule,
                "run_maa_connectivity_check",
                return_value={"status": "timeout", "message": "timed out"},
            ),
            self.assertRaisesRegex(RuntimeError, "timed out"),
        ):
            scheduler.check_maa_connectivity("调用前")

    def test_startup_check_runs_after_device_initialization(self):
        calls = []
        scheduler = MagicMock()

        def initialize(_tasks):
            calls.append("initialize")
            return scheduler

        def check_maa_connectivity(context):
            calls.append(("maa_check", context))
            raise RuntimeError("preflight failed")

        scheduler.check_maa_connectivity.side_effect = check_maa_connectivity

        with (
            patch.object(mower_main, "initialize", side_effect=initialize),
            patch.object(
                mower_main,
                "is_maa_connectivity_check_enabled",
                return_value=True,
            ),
            patch.object(mower_main, "send_message") as mock_send_message,
        ):
            mower_main.simulate(None)

        self.assertEqual(calls, ["initialize", ("maa_check", "启动预检")])
        scheduler.initialize_operators.assert_not_called()
        mock_send_message.assert_called_once_with(
            "preflight failed",
            "Mower启动中止：Maa连接测试失败",
            level="ERROR",
        )


if __name__ == "__main__":
    unittest.main()
