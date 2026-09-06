import json
import sys
import unittest
from unittest.mock import MagicMock, patch

from arknights_mower.utils.maa_check import (
    MAA_CHECK_SCRIPT,
    maa_check_command,
    maa_check_params,
    maa_check_timeout_result,
    parse_maa_check_output,
    run_maa_check,
    worker_main,
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

    def test_command_uses_c_for_source_mode(self):
        with patch("arknights_mower.utils.maa_check.frozen", return_value=False):
            command = maa_check_command({"adb": "device"})
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[1], "-c")
        self.assertEqual(command[2], MAA_CHECK_SCRIPT)
        self.assertEqual(command[3], json.dumps({"adb": "device"}, ensure_ascii=False))

    def test_command_routes_frozen_to_worker_subcommand(self):
        with patch("arknights_mower.utils.maa_check.frozen", return_value=True):
            command = maa_check_command({"adb": "device"})
        self.assertEqual(
            command,
            [
                sys.executable,
                "--maa-check-worker",
                json.dumps({"adb": "device"}, ensure_ascii=False),
            ],
        )

    def test_run_maa_check_reports_error_when_asst_missing(self):
        # run_maa_check must load `asst` from maa_path/Python; a bogus path makes
        # the import fail, and the en-route exception becomes an "error" result.
        before = list(sys.path)
        result = run_maa_check(
            {
                "maa_path": "/missing",
                "maa_adb_path": "adb",
                "adb": "device",
                "maa_conn_preset": "CompatMac",
                "maa_touch_option": "maatouch",
            }
        )
        self.assertEqual(result["status"], "error")
        # The MAA dir is only needed to load `asst`; it must not leak onto the
        # shared sys.path of a process that keeps running (e.g. the test runner).
        self.assertEqual(sys.path, before)

    def test_run_maa_check_tolerates_missing_maa_path(self):
        # A payload lacking "maa_path" must surface as an "error" result, not a
        # NameError from the sys.path cleanup in the finally block.
        result = run_maa_check({"adb": "device"})
        self.assertEqual(result["status"], "error")

    def test_worker_main_prints_json_result(self):
        payload = json.dumps(
            {
                "maa_path": "/missing",
                "maa_adb_path": "adb",
                "adb": "device",
                "maa_conn_preset": "CompatMac",
                "maa_touch_option": "maatouch",
            }
        )
        with patch("builtins.print") as mock_print:
            worker_main(payload)
        text = mock_print.call_args.args[0]
        self.assertEqual(json.loads(text)["status"], "error")
        # ensure_ascii keeps the payload pure-ASCII so a windowed frozen launcher
        # with a locale-dependent (e.g. GBK) console still round-trips.
        self.assertTrue(text.isascii())


if __name__ == "__main__":
    unittest.main()
