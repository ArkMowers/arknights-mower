import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
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


def run_worker(mode, params):
    if mode == "frozen":
        return run_maa_check(params)
    output = io.StringIO()
    with (
        patch.object(sys, "argv", ["-c", json.dumps(params)]),
        patch.object(sys, "path", list(sys.path)),
        redirect_stdout(output),
    ):
        exec(MAA_CHECK_SCRIPT, {})
    return json.loads(output.getvalue())


class TestMaaCheck(unittest.TestCase):
    def test_frozen_version_probe_never_imports_sdk_or_connects(self):
        with patch(
            "arknights_mower.utils.maa_update.read_installed_version",
            return_value="v6.test",
        ) as probe:
            self.assertEqual(
                run_maa_check({"version_only": True, "maa_path": "/MAA"}),
                {"status": "success", "message": "v6.test"},
            )
        probe.assert_called_once_with("/MAA")

    def test_source_version_probe_only_calls_native_version_function(self):
        version = MagicMock(return_value=b"v6.test")
        params = {"version_only": True, "core_path": "/MAA/core"}
        output = io.StringIO()
        with (
            patch(
                "ctypes.CDLL", return_value=SimpleNamespace(AsstGetVersion=version)
            ) as load,
            patch.object(sys, "argv", ["-c", json.dumps(params)]),
            redirect_stdout(output),
            self.assertRaises(SystemExit),
        ):
            exec(MAA_CHECK_SCRIPT, {})
        self.assertEqual(
            json.loads(output.getvalue()), {"status": "success", "message": "v6.test"}
        )
        load.assert_called_once_with("/MAA/core")
        version.assert_called_once_with()

    def test_resource_load_failure_prevents_connection_in_both_worker_modes(self):
        asst = MagicMock()
        asst.load.return_value = False
        params = {
            "maa_path": "/MAA",
            "adb": "device",
            "maa_adb_path": "adb",
            "maa_conn_preset": "General",
            "maa_touch_option": "maatouch",
        }
        for mode in ("source", "frozen"):
            with (
                self.subTest(mode=mode),
                patch.dict(
                    sys.modules,
                    {
                        "asst": SimpleNamespace(),
                        "asst.asst": SimpleNamespace(Asst=asst),
                    },
                ),
            ):
                result = run_worker(mode, params)
                self.assertEqual(result["status"], "error")
                self.assertIn("资源加载失败", result["message"])
                asst.assert_not_called()

    def test_check_route_keeps_the_active_application_sessions_transport(self):
        import server
        from arknights_mower.utils.device.application import DeviceControl

        conf = SimpleNamespace(
            maa_path="/maa",
            maa_adb_path="missing-manual-adb",
            adb="stale-device",
            maa_conn_preset="General",
            maa_touch_option="maatouch",
        )
        device = SimpleNamespace(
            device_id="USB-123",
            client=SimpleNamespace(adb_bin="sdk-adb", device_id="USB-123"),
            close=lambda: None,
        )
        adapter = SimpleNamespace(open=lambda conf, **kwargs: device)
        control = DeviceControl(lambda: conf, adapter)
        self.assertTrue(control.start().ok)
        self.addCleanup(control.close)
        with (
            patch.dict(
                sys.modules,
                {"arknights_mower.__main__": SimpleNamespace(device_control=control)},
            ),
            patch.object(server.config, "conf", conf),
            patch.object(server.app, "token", "maa-test-token", create=True),
            patch.dict(server.maa_check_job, {"status": "idle", "process": None}),
            patch.object(server.subprocess, "Popen") as process,
        ):
            response = server.app.test_client().get(
                "/check-maa", headers={"token": "maa-test-token"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "running")
        params = json.loads(process.call_args.args[0][-1])
        self.assertEqual(params["maa_adb_path"], "sdk-adb")
        self.assertEqual(params["adb"], "USB-123")

    def test_session_check_uses_verified_adb_and_serial(self):
        for configured_adb in ("", "missing-manual-adb"):
            with self.subTest(configured_adb=configured_adb):
                conf = SimpleNamespace(
                    maa_path="/maa",
                    maa_adb_path=configured_adb,
                    adb="stale-device",
                    maa_conn_preset="General",
                    maa_touch_option="maatouch",
                )
                device = SimpleNamespace(
                    client=SimpleNamespace(adb_bin="sdk-adb", device_id="USB-123")
                )
                with patch("arknights_mower.utils.maa_check.config.conf", conf):
                    command = maa_check_command(maa_check_params(device=device))
                params = json.loads(command[-1])
                self.assertEqual(params["maa_adb_path"], "sdk-adb")
                self.assertEqual(params["adb"], "USB-123")

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

    def test_workers_load_incremental_resources_and_report_connection_outcomes(self):
        params = {
            "maa_path": "/MAA",
            "maa_adb_path": "sdk-adb",
            "adb": "bound-device",
            "maa_conn_preset": "General",
            "maa_touch_option": "maatouch",
        }
        outcomes = (
            (True, None, {"status": "success", "message": "MAA v6.test 连接成功"}),
            (
                False,
                None,
                {"status": "connection_failed", "message": "连接失败，请检查MAA日志！"},
            ),
            (
                None,
                RuntimeError("SDK failure"),
                {"status": "error", "message": "MAA测试异常：SDK failure"},
            ),
        )
        for mode in ("source", "frozen"):
            for connected, error, expected in outcomes:
                with self.subTest(mode=mode, status=expected["status"]):
                    asst = MagicMock()
                    asst.load.return_value = True
                    instance = asst.return_value
                    instance.get_version.return_value = "v6.test"
                    instance.connect.return_value = connected
                    instance.connect.side_effect = error
                    with patch.dict(
                        sys.modules,
                        {
                            "asst": SimpleNamespace(),
                            "asst.asst": SimpleNamespace(Asst=asst),
                        },
                    ):
                        self.assertEqual(run_worker(mode, params), expected)
                    asst.load.assert_called_once_with(
                        path=Path("/MAA"), incremental_path=Path("/MAA/cache")
                    )
                    instance.set_instance_option.assert_called_once_with(2, "maatouch")
                    instance.connect.assert_called_once_with(
                        "sdk-adb", "bound-device", "General"
                    )

    def test_abnormal_process_exit_is_not_reported_as_connection_failure(self):
        result = parse_maa_check_output("", "  <no Python frame>\n", 1)

        self.assertEqual(result["status"], "error")
        self.assertIn("MAA测试进程异常退出：1", result["message"])

    def test_timeout_has_distinct_status(self):
        self.assertEqual(
            maa_check_timeout_result(5),
            {
                "status": "timeout",
                "message": "MAA连通性测试超时（5秒），已终止测试进程",
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
