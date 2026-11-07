"""Genymotion discovery failures and target isolation through DeviceControl."""

import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_genymotion_tests import (
    OTHER_ID,
    VM_ID,
    GenymotionFixture,
)
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session_io import ProductionSimulator


class TargetRecordingIO(PreflightIO):
    def __init__(self):
        super().__init__()
        self.probed = []

    def devices(self, adb_path, serial):
        self.probed.append(serial)
        return super().devices(adb_path, serial)


class GenymotionIOTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.gm = GenymotionFixture(root)
        self.io = TargetRecordingIO()
        self.io.installed.update({str(root), str(self.gm.manager)})
        self.io.targets = [("USB-123", "device"), ("127.0.0.1:6555", "device")]
        self.conf = Conf(
            device={
                "preset_id": "linux.genymotion",
                "manager_path": str(self.gm.manager),
            }
        )
        simulator = ProductionSimulator(genymotion=self.gm.controller)
        self.control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(), simulator, genymotion=self.gm.controller
            ),
        )

    def bind(self):
        found = self.control.discover()
        self.assertTrue(found.ok, found.error)
        self.conf = self.conf.updated({"device": found.candidates[0]["binding"]})
        self.gm.calls.clear()

    def assert_manual(self, result, code):
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, code)
        self.assertEqual(result.error.action, "manual")
        self.assertTrue(result.error.message)

    def test_missing_explicit_manager_does_not_fall_back_to_another_installation(self):
        self.conf.device.manager_path = str(self.gm.manager.parent / "missing-gmtool")
        result = self.control.discover()
        self.assert_manual(result, "missing_installation")
        self.assertEqual(result.error.fields, ["manager_path"])
        self.assertEqual(result.candidates, [])
        self.assertEqual(self.gm.calls, [])

    def test_permission_failure_and_timeout_offer_manual_repair(self):
        cases = (
            (PermissionError("denied"), "discovery_permission_denied"),
            (subprocess.TimeoutExpired(["gmtool"], 3), "manager_timeout"),
        )
        for failure, code in cases:
            with self.subTest(code=code):
                self.gm.responses["version"] = failure
                self.assert_manual(self.control.discover(), code)

    def test_unreadable_manager_path_returns_repair_before_running_any_command(self):
        with patch.object(Path, "is_file", side_effect=PermissionError("denied")):
            self.assert_manual(self.control.discover(), "discovery_permission_denied")
        self.assertEqual(self.gm.calls, [])

    def test_unverified_versions_cannot_become_automatic_candidates(self):
        for version in ("3.4.0", "3.5.0", "3.9.1", "3.10.0", "4.0.0", "unknown"):
            with self.subTest(version=version):
                self.gm.version = f"Version : {version}\n"
                self.gm.calls.clear()
                result = self.control.discover()
                self.assert_manual(result, "genymotion_version_unsupported")
                self.assertEqual(result.candidates, [])
                self.assertFalse(any("list" in argv for argv, _ in self.gm.calls))

    def test_malformed_json_and_unsuccessful_envelopes_are_not_empty_successes(self):
        cases = (
            b"not json",
            b"\xff",
            b"[]",
            b'{"exit_code":false,"instances":[]}',
            b'{"exit_code":3,"instances":[]}',
            b'{"exit_code":0,"instances":null}',
        )
        for output in cases:
            with self.subTest(output=output):
                self.gm.responses["list"] = subprocess.CompletedProcess(
                    ["gmtool"], 0, output, b""
                )
                result = self.control.discover()
                self.assert_manual(result, "manager_output_invalid")
                self.assertEqual(result.candidates, [])

    def test_nonzero_exit_and_stderr_even_with_zero_exit_remain_failures(self):
        cases = (
            (3, b"", "genymotion_unavailable"),
            (0, b"Unable to query virtual devices", "manager_output_invalid"),
        )
        for returncode, stderr, code in cases:
            with self.subTest(returncode=returncode):
                self.gm.responses["list"] = subprocess.CompletedProcess(
                    ["gmtool"], returncode, json.dumps(self.gm.listing).encode(), stderr
                )
                self.assert_manual(self.control.discover(), code)

    def test_no_candidates_and_duplicate_uuid_never_select_an_instance(self):
        row = deepcopy(self.gm.listing["instances"][0])
        for rows, code in (
            ([], "no_genymotion"),
            ([row, deepcopy(row)], "manager_output_invalid"),
        ):
            with self.subTest(code=code):
                self.gm.listing["instances"] = rows
                result = self.control.discover()
                self.assert_manual(result, code)
                self.assertIsNone(result.selected_key)
                self.assertEqual(result.candidates, [])

    def test_incomplete_instance_fields_do_not_create_partial_candidates(self):
        original = deepcopy(self.gm.listing["instances"][0])
        for field in ("uuid", "name", "state", "adb_serial"):
            with self.subTest(field=field):
                row = deepcopy(original)
                del row[field]
                self.gm.listing["instances"] = [row]
                self.assert_manual(self.control.discover(), "manager_output_invalid")

    def test_official_ipv4_host_endpoint_survives_selection_and_preflight(self):
        serial = "192.168.56.101:5555"
        self.gm.listing["instances"][0]["adb_serial"] = serial
        self.gm.details = self.gm.details.replace("127.0.0.1:6555", serial)
        self.io.targets.append((serial, "device"))
        self.bind()
        result = self.control.preflight()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, serial)
        self.assertEqual(self.io.probed, [serial])

    def test_invalid_or_unusable_endpoint_requires_manual_configuration(self):
        for serial in (
            "",
            "localhost:6555",
            "0.0.0.0:6555",
            "224.0.0.1:5555",
            "127.0.0.1:0",
            "127.0.0.1:65536",
            "127.0.0.1:5555 extra",
            "::1:6555",
        ):
            with self.subTest(serial=serial):
                self.gm.listing["instances"][0]["adb_serial"] = serial
                self.assert_manual(self.control.discover(), "manager_output_invalid")

    def test_failed_selected_vm_never_uses_old_serial_or_lists_another_vm(self):
        self.bind()
        self.conf.device.last_serial = "USB-123"
        before = self.conf.model_dump()
        for details, response, code in (
            (
                self.gm.details.replace(VM_ID, OTHER_ID),
                None,
                "genymotion_binding_changed",
            ),
            (
                self.gm.details,
                subprocess.CompletedProcess(["gmtool"], 5, b"", b"VM not found"),
                "genymotion_unavailable",
            ),
        ):
            with self.subTest(code=code):
                self.gm.details = details
                self.gm.responses["details"] = response
                self.gm.calls.clear()
                result = self.control.preflight()
                self.assert_manual(result, code)
                self.assertEqual(result.serial, "")
                self.assertEqual(self.io.probed, [])
                self.assertEqual(self.conf.model_dump(), before)
                self.assertFalse(any("list" in argv for argv, _ in self.gm.calls))
                for argv, _ in self.gm.calls:
                    if "details" in argv:
                        self.assertEqual(argv[-1], VM_ID)

    def test_details_license_and_incomplete_output_retain_manual_entry(self):
        self.bind()
        for response, code in (
            (
                subprocess.CompletedProcess(["gmtool"], 14, b"", b"License required"),
                "genymotion_unavailable",
            ),
            (
                subprocess.CompletedProcess(
                    ["gmtool"],
                    0,
                    f"UUID : {VM_ID}\nName : VM\nState : On\n".encode(),
                    b"",
                ),
                "manager_output_invalid",
            ),
        ):
            with self.subTest(code=code):
                self.gm.responses["details"] = response
                self.assert_manual(self.control.preflight(), code)
                self.assertEqual(self.io.probed, [])

    def test_manager_io_has_bounded_output_timeout_and_argument_arrays(self):
        found = self.control.discover()
        self.assertTrue(found.ok, found.error)
        for argv, options in self.gm.calls:
            self.assertIsInstance(argv, list)
            self.assertTrue(all(isinstance(value, str) for value in argv))
            self.assertFalse(options.get("shell", False))
            self.assertGreater(options["timeout"], 0)
            self.assertLessEqual(options["timeout"], 3)
        output = json.dumps(self.gm.listing).encode() + b" " * (1024 * 1024)
        self.gm.responses["list"] = subprocess.CompletedProcess(
            ["gmtool"], 0, output, b""
        )
        self.assert_manual(self.control.discover(), "manager_output_invalid")

    def test_other_hosts_do_not_execute_linux_manager(self):
        self.bind()
        for host in ("windows", "macos"):
            with self.subTest(host=host):
                self.io.host = host
                for operation in (self.control.discover, self.control.preflight):
                    result = operation()
                    self.assertFalse(result.ok)
                    self.assertEqual(result.error.code, "unsupported_host")
                self.assertEqual(self.gm.calls, [])
                self.assertEqual(self.io.probed, [])


if __name__ == "__main__":
    unittest.main()
