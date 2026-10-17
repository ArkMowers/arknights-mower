"""LDPlayer manager fixtures observed through the application interface."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.ldplayer_discovery import LDPlayerDiscoveryIO
from arknights_mower.utils.device.preflight import PreflightService

FIXTURES = Path(__file__).parent / "fixtures"


class LDPlayerDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = self.root / "ldconsole.exe"
        self.manager.touch()
        self.configuration = Conf()
        self.output = (FIXTURES / "ldplayer9_single.txt").read_bytes()
        self.preflight_io = PreflightIO()
        self.preflight_io.host = "windows"
        self.sources = [str(self.root)]
        self.run = Mock(side_effect=self.command)
        self.control = DeviceControl(
            lambda: self.configuration,
            Mock(),
            preflight=PreflightService(self.preflight_io),
            discovery=DiscoveryService(
                LDPlayerDiscoveryIO(
                    run=self.run,
                    registry_paths=lambda: self.sources,
                    process_paths=lambda: [],
                    platform="windows",
                )
            ),
        )

    def command(self, argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, self.output, b"")

    def test_single_instance_binding_uses_vendor_index_without_saving_a_guess(self):
        before = self.configuration.model_dump()
        result = self.control.discover().to_dict()
        self.assertTrue(result["ok"], result["error"])
        candidate = result["candidates"][0]
        self.assertEqual(result["selected_key"], candidate["key"])
        self.assertEqual(candidate["preset_id"], "windows.ldplayer9")
        self.assertEqual(candidate["instance_id"], "3")
        self.assertEqual(candidate["instance_name"], "日常号")
        self.assertEqual(candidate["binding"]["last_serial"], "")
        self.assertEqual(self.configuration.model_dump(), before)

    def test_multiple_instances_keep_vendor_keys_after_reordering(self):
        self.output = (FIXTURES / "ldplayer9_multiple.txt").read_bytes()
        original = self.control.discover().to_dict()
        self.assertIsNone(original["selected_key"])
        self.assertEqual(original["status"], "selection_required")
        self.output = b"\n".join(reversed(self.output.splitlines()))
        reordered = self.control.discover().to_dict()
        self.assertEqual(
            {item["instance_id"]: item["key"] for item in original["candidates"]},
            {item["instance_id"]: item["key"] for item in reordered["candidates"]},
        )
        chosen = next(
            item for item in reordered["candidates"] if item["instance_id"] == "8"
        )
        self.configuration = self.configuration.updated({"device": chosen["binding"]})
        self.assertEqual(self.configuration.device.instance_id, "8")
        self.assertEqual(self.configuration.simulator.index, "8")
        self.assertEqual(self.configuration.device.last_serial, "")

    def test_stopped_instance_is_selectable_but_has_no_endpoint(self):
        self.output = (FIXTURES / "ldplayer9_stopped.txt").read_bytes()
        result = self.control.discover().to_dict()
        candidate = result["candidates"][0]
        self.assertEqual(candidate["state"], "stopped")
        self.assertEqual(candidate["serial"], "")
        self.assertEqual(result["selected_key"], candidate["key"])

    def test_deleted_and_invalid_manager_rows_never_reappear_by_list_order(self):
        self.output = (FIXTURES / "ldplayer9_deleted.txt").read_bytes()
        result = self.control.discover().to_dict()
        self.assertEqual([item["instance_id"] for item in result["candidates"]], ["8"])
        for output in (
            (FIXTURES / "ldplayer9_malformed.txt").read_bytes(),
            self.output + self.output,
            b"error: unknown command",
            b'3,"unterminated,301,302,1,3301,3302',
        ):
            with self.subTest(output=output):
                self.output = output
                result = self.control.discover().to_dict()
                self.assertFalse(result["ok"])
                self.assertEqual(result["candidates"], [])
                self.assertEqual(result["error"]["code"], "manager_output")

    def test_empty_manager_and_missing_installation_offer_distinct_repairs(self):
        self.output = b""
        result = self.control.discover().to_dict()
        self.assertEqual(result["error"]["code"], "instance_required")
        self.sources.clear()
        self.run.reset_mock()
        result = self.control.discover().to_dict()
        self.assertEqual(result["error"]["code"], "missing_installation")
        self.assertEqual(result["error"]["fields"], ["installation_path"])
        self.run.assert_not_called()

    def test_manager_gbk_names_are_preserved_and_nonzero_exits_fail(self):
        self.output = "3,日常号,301,302,1,3301,3302".encode("gb18030")
        self.assertEqual(
            self.control.discover().candidates[0]["instance_name"], "日常号"
        )
        self.run.side_effect = subprocess.CalledProcessError(1, "list2")
        self.assertEqual(self.control.discover().error.code, "manager_output")

    def test_source_errors_keep_other_installations_but_prevent_automatic_selection(
        self,
    ):
        from arknights_mower.utils.device.preflight import PreflightError

        self.sources.append(
            PreflightError(
                "discovery_permission",
                "无法访问另一处安装",
                fields=["installation_path"],
            )
        )
        result = self.control.discover().to_dict()
        self.assertEqual(len(result["candidates"]), 1)
        self.assertIsNone(result["selected_key"])
        self.assertEqual(result["error"]["code"], "discovery_permission")

    def test_manual_console_path_and_source_deduplication_keep_installation_identity(
        self,
    ):
        self.sources.extend([str(self.manager), str(self.root)])
        self.configuration = Conf(
            device={"preset_id": "windows.ldplayer9", "manager_path": str(self.manager)}
        )
        result = self.control.discover().to_dict()
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["manager_path"], str(self.manager))
        self.assertEqual(self.run.call_count, 1)

    def test_settings_load_and_non_windows_discovery_do_not_run_managers(self):
        self.control.settings_status()
        self.run.assert_not_called()
        self.preflight_io.host = "linux"
        self.assertEqual(self.control.discover().error.code, "discovery_unavailable")
        self.run.assert_not_called()

    def test_output_limits_and_timeouts_return_structured_repairs(self):
        for failure, code in (
            (subprocess.TimeoutExpired("list2", 3), "discovery_timeout"),
            (PermissionError("denied"), "discovery_permission"),
        ):
            with self.subTest(code=code):
                self.run.side_effect = failure
                self.assertEqual(self.control.discover().error.code, code)
        self.run.side_effect = self.command
        self.output = b"x" * (1024 * 1024 + 1)
        self.assertEqual(self.control.discover().error.code, "manager_output")
        self.output = "\n".join(
            f"{index},instance {index},0,0,0,-1,-1" for index in range(65)
        ).encode()
        result = self.control.discover().to_dict()
        self.assertEqual(len(result["candidates"]), 64)
        self.assertEqual(result["error"]["code"], "discovery_limit")
        self.assertIsNone(result["selected_key"])

    def test_two_installations_with_the_same_index_remain_distinct(self):
        other = self.root / "other installation"
        other.mkdir()
        (other / "dnconsole.exe").touch()
        self.sources.append(str(other))
        result = self.control.discover().to_dict()
        self.assertEqual(len({item["key"] for item in result["candidates"]}), 2)
        self.assertIsNone(result["selected_key"])

    def test_selected_adb_disappearing_does_not_switch_clients_after_endpoint_verification(
        self,
    ):
        from arknights_mower.utils.device.session import InstanceObservation

        self.configuration = Conf(
            device={
                "preset_id": "windows.ldplayer9",
                "adb_path": "manual-adb",
                "instance_id": "3",
            }
        )
        self.preflight_io.targets = [("emulator-5560", "device")]

        def inspect(profile, timeout):
            self.assertEqual(profile.adb_path, "manual-adb")
            self.preflight_io.paths.remove("manual-adb")
            return InstanceObservation("running", "emulator-5560")

        simulator = Mock()
        simulator.inspect.side_effect = inspect
        control = DeviceControl(
            lambda: self.configuration,
            Mock(),
            preflight=PreflightService(self.preflight_io),
            discovery=DiscoveryService(Mock(), simulator),
        )
        result = control.preflight()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "missing_adb")
        self.assertEqual(result.adb_path, "")

    def test_process_access_denial_is_a_repair_result_without_starting_a_manager(self):
        run = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, b"@@MOWER_PROCESS_PERMISSION@@\n", b""
            )
        )
        control = DeviceControl(
            lambda: self.configuration,
            Mock(),
            preflight=PreflightService(self.preflight_io),
            discovery=DiscoveryService(
                LDPlayerDiscoveryIO(
                    run=run,
                    registry_paths=lambda: [],
                    platform="windows",
                )
            ),
        )
        result = control.discover()
        self.assertEqual(result.error.code, "discovery_permission")
        self.assertEqual(result.error.fields, ["installation_path"])
        self.assertEqual(result.candidates, [])
        self.assertEqual(run.call_count, 1)

    def test_incompatible_manager_adb_exposes_only_the_adb_repair(self):
        from arknights_mower.utils.device.adb_client.server import SharedADBError

        self.configuration = Conf(
            device={"preset_id": "windows.ldplayer9", "instance_id": "3"}
        )
        simulator = Mock()
        simulator.inspect.side_effect = SharedADBError("共享 ADB 版本不兼容")
        control = DeviceControl(
            lambda: self.configuration,
            Mock(),
            preflight=PreflightService(self.preflight_io),
            discovery=DiscoveryService(Mock(), simulator),
        )
        result = control.preflight()
        self.assertEqual(result.error.code, "adb_server_unavailable")
        self.assertEqual(result.error.fields, ["adb_path"])
        self.assertEqual(result.serial, "")

    def test_combined_windows_discovery_keeps_both_products_and_manual_paths(self):
        from arknights_mower.utils.device.mumu_discovery import MuMuDiscoveryIO
        from arknights_mower.utils.device.windows_discovery import WindowsDiscoveryIO

        mumu = self.root / "MuMuManager.exe"
        mumu.touch()

        def run(argv, **kwargs):
            output = (
                self.output
                if argv[1] == "list2"
                else b'{"3":{"index":3,"name":"MuMu","is_process_started":false}}'
            )
            return subprocess.CompletedProcess(argv, 0, output, b"")

        options = dict(
            run=run,
            registry_paths=lambda: self.sources,
            process_paths=lambda: [],
            fixed_paths=lambda: [],
            platform="windows",
        )
        self.control = DeviceControl(
            lambda: self.configuration,
            Mock(),
            preflight=PreflightService(self.preflight_io),
            discovery=DiscoveryService(
                WindowsDiscoveryIO(
                    (MuMuDiscoveryIO(**options), LDPlayerDiscoveryIO(**options))
                )
            ),
        )
        result = self.control.discover().to_dict()
        self.assertEqual(
            {item["preset_id"] for item in result["candidates"]},
            {"windows.mumu12", "windows.ldplayer9"},
        )
        self.assertEqual(len({item["key"] for item in result["candidates"]}), 2)
        self.assertIsNone(result["selected_key"])

    def test_ldplayer14_discovery_resolves_ldplayer14_preset(self):
        ld14_root = self.root / "LDPlayer14"
        ld14_root.mkdir()
        (ld14_root / "ldconsole.exe").touch()
        discovery_io = LDPlayerDiscoveryIO(
            run=self.run,
            registry_paths=lambda: [str(ld14_root)],
            process_paths=lambda: [],
            platform="windows",
        )
        control = DeviceControl(
            lambda: self.configuration,
            Mock(),
            preflight=PreflightService(self.preflight_io),
            discovery=DiscoveryService(discovery_io),
        )
        result = control.discover().to_dict()
        self.assertTrue(result["ok"])
        candidate = result["candidates"][0]
        self.assertEqual(candidate["preset_id"], "windows.ldplayer14")


if __name__ == "__main__":
    unittest.main()
