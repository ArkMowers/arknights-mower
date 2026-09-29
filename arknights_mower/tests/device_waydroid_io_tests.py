"""Waydroid command failures through the application discovery boundary."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session_io import ProductionSimulator
from arknights_mower.utils.device.waydroid import WaydroidController


class WaydroidIOTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = self.root / "waydroid"
        self.busctl = self.root / "busctl"
        for executable in (self.manager, self.busctl):
            executable.touch()
            executable.chmod(0o700)
        fixtures = json.loads(
            (Path(__file__).parent / "fixtures/waydroid.json").read_text(
                encoding="utf-8"
            )
        )
        self.running = fixtures["running"]["status"].encode()
        self.metadata = fixtures["running"]["session"]
        self.uninitialized = fixtures["uninitialized"]["status"].encode()
        self.responses = {
            "status": subprocess.CompletedProcess([], 0, self.running, b""),
            "session": subprocess.CompletedProcess(
                [],
                0,
                json.dumps({"type": "a{ss}", "data": [self.metadata]}).encode(),
                b"",
            ),
        }
        self.calls = []
        self.conf = Conf(device={"preset_id": "linux.waydroid"})

    def run_command(self, argv, **options):
        self.calls.append((argv, options))
        response = self.responses[
            "status" if argv[0] == str(self.manager) else "session"
        ]
        if isinstance(response, BaseException):
            raise response
        return response

    def control(self, *, host="linux", controller_host="linux"):
        io = PreflightIO()
        io.host = host
        controller = WaydroidController(
            run=self.run_command,
            which=lambda name: str(self.root / name),
            host=controller_host,
            uid=lambda: 1000,
            data_path=self.metadata["waydroid_data"],
        )
        simulator = ProductionSimulator(waydroid=controller)
        return DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(io),
            discovery=DiscoveryService(DiscoveryIO(), simulator, waydroid=controller),
        )

    def test_other_hosts_reject_waydroid_before_command_execution(self):
        for host, controller_host in (("windows", "linux"), ("linux", "win32")):
            with self.subTest(host=host, controller_host=controller_host):
                result = self.control(
                    host=host, controller_host=controller_host
                ).discover()
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, "unsupported_host")
                self.assertEqual(result.error.fields, ["preset_id"])
                self.assertEqual(self.calls, [])

    def test_missing_busctl_requires_official_session_support_without_adb_guess(self):
        self.busctl.unlink()
        result = self.control().discover()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "waydroid_session_unavailable")
        self.assertIn("busctl", result.error.message)
        self.assertEqual(result.candidates, [])
        self.assertEqual(len(self.calls), 1)

    def test_zero_exit_uninitialized_message_on_either_stream_requires_init(self):
        for stdout, stderr in (
            (self.uninitialized, b""),
            (b"", self.uninitialized),
        ):
            with self.subTest(stderr=bool(stderr)):
                self.responses["status"] = subprocess.CompletedProcess(
                    [], 0, stdout, stderr
                )
                self.calls.clear()
                result = self.control().discover()
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, "waydroid_uninitialized")
                self.assertEqual(result.error.action, "initialize")
                self.assertEqual(result.error.fields, [])
                self.assertEqual(result.candidates, [])
                self.assertEqual(len(self.calls), 1)

    def test_command_failures_and_unsafe_output_are_structured_without_saving(self):
        valid = self.responses.copy()
        failures = (
            (subprocess.TimeoutExpired("waydroid", 3), "manager_timeout"),
            (PermissionError("permission denied"), "discovery_permission_denied"),
            (
                subprocess.CalledProcessError(1, "waydroid", stderr=b"failed"),
                "waydroid_status_failed",
            ),
            (
                subprocess.CompletedProcess([], 1, b"unexpected success", b""),
                "waydroid_status_failed",
            ),
            (
                subprocess.CompletedProcess([], 0, b"", b"access denied"),
                "waydroid_status_failed",
            ),
            (
                subprocess.CompletedProcess([], 0, b"\xff", b""),
                "manager_output_invalid",
            ),
            (
                subprocess.CompletedProcess([], 0, b"x" * (1024 * 1024 + 1), b""),
                "manager_output_invalid",
            ),
        )
        before = self.conf.model_dump()
        for stage in ("status", "session"):
            for response, code in failures:
                with self.subTest(stage=stage, code=code, response=type(response)):
                    self.responses = {**valid, stage: response}
                    result = self.control().discover()
                    self.assertFalse(result.ok)
                    self.assertEqual(result.error.code, code)
                    self.assertTrue(result.error.message)
                    self.assertEqual(result.error.action, "retry")
                    self.assertEqual(result.candidates, [])
                    self.assertEqual(self.conf.model_dump(), before)

    def test_getsession_rejects_invalid_signatures_shapes_and_value_types(self):
        invalid = (
            b"not json",
            b"null",
            b"[]",
            b"{}",
            json.dumps({"type": "s", "data": [self.metadata]}).encode(),
            json.dumps({"type": "a{ss}", "data": []}).encode(),
            json.dumps({"type": "a{ss}", "data": [self.metadata, {}]}).encode(),
            json.dumps({"type": "a{ss}", "data": ["session"]}).encode(),
            json.dumps(
                {"type": "a{ss}", "data": [["user_id", "1000", "state", "RUNNING"]]}
            ).encode(),
            json.dumps(
                {"type": "a{ss}", "data": [{**self.metadata, "user_id": 1000}]}
            ).encode(),
            json.dumps(
                {"type": "a{ss}", "data": [{"user_id": {"type": "s", "data": "1000"}}]}
            ).encode(),
        )
        for output in invalid:
            with self.subTest(output=output):
                self.responses["session"] = subprocess.CompletedProcess(
                    [], 0, output, b""
                )
                result = self.control().discover()
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, "waydroid_session_unavailable")
                self.assertEqual(result.candidates, [])

    def test_discovery_commands_cannot_start_services_or_request_authorization(self):
        result = self.control().discover()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(self.calls), 2)
        for argv, options in self.calls:
            self.assertIsInstance(argv, list)
            self.assertTrue(all(isinstance(argument, str) for argument in argv))
            self.assertTrue(Path(argv[0]).is_absolute())
            self.assertFalse(options.get("shell", False))
            self.assertGreater(options["timeout"], 0)
            self.assertLessEqual(options["timeout"], 3)
            self.assertTrue(options["check"])
        self.assertEqual(self.calls[0][0][1:], ["status"])
        bus_argv = self.calls[1][0]
        self.assertIn("--system", bus_argv)
        self.assertIn("--json=short", bus_argv)
        self.assertIn("--auto-start=no", bus_argv)
        self.assertIn("--allow-interactive-authorization=no", bus_argv)
        self.assertEqual(
            bus_argv[-5:],
            [
                "call",
                "id.waydro.Container",
                "/ContainerManager",
                "id.waydro.ContainerManager",
                "GetSession",
            ],
        )

    def test_status_and_official_session_must_agree_on_running_user_and_data(self):
        for changes in (
            {"user_id": "1001"},
            {"state": "STOPPED"},
            {"state": "FROZEN"},
            {"waydroid_data": "relative/data"},
            {"waydroid_data": ""},
        ):
            with self.subTest(changes=changes):
                output = json.dumps(
                    {"type": "a{ss}", "data": [{**self.metadata, **changes}]}
                ).encode()
                self.responses["session"] = subprocess.CompletedProcess(
                    [], 0, output, b""
                )
                result = self.control().discover()
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, "waydroid_session_unavailable")
                self.assertEqual(result.candidates, [])


if __name__ == "__main__":
    unittest.main()
