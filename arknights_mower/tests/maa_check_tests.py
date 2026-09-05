import json
import unittest
from unittest.mock import MagicMock, patch

from arknights_mower.utils.maa_check import (
    MAA_CHECK_SCRIPT,
    maa_check_params,
    maa_check_timeout_result,
    parse_maa_check_output,
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


if __name__ == "__main__":
    unittest.main()
