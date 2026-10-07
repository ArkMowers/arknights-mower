"""Offline vendor observations through the device application boundary."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.mumu_discovery import (
    MuMuDiscoveryIO,
    run_mumu_command,
)
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session_io import ProductionSimulator

FIXTURES = Path(__file__).parent / "fixtures"


def vendor_output(name):
    return (FIXTURES / f"mumu12_{name}.json").read_bytes()


class MuMuDiscoveryIOTests(unittest.TestCase):
    def setUp(self):
        self.folder = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.folder)
        self.manager = self.add_installation(self.root)
        self.configuration = SimpleNamespace(device=DeviceProfile(), adb="")
        self.preflight_io = PreflightIO()
        self.preflight_io.host = "windows"

    def add_installation(self, root, layout="shell"):
        manager = root / layout / "MuMuManager.exe"
        manager.parent.mkdir(parents=True)
        manager.touch()
        return manager

    def control(
        self, *, output=None, run=None, registry=None, process=None, clock=None
    ):
        self.run = run or Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, output if output is not None else vendor_output("single"), b""
            )
        )
        options = {
            "run": self.run,
            "registry_paths": registry or (lambda: [self.folder]),
            "process_paths": process or (lambda: []),
            "fixed_paths": lambda: [],
            "platform": "windows",
        }
        if clock is not None:
            options["monotonic"] = clock
        return DeviceControl(
            lambda: self.configuration,
            Mock(),
            preflight=PreflightService(self.preflight_io),
            discovery=DiscoveryService(MuMuDiscoveryIO(**options)),
        )

    def test_no_installation_requests_only_installation_repair(self):
        result = self.control(registry=lambda: []).discover().to_dict()
        self.assertFalse(result["ok"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"]["code"], "missing_installation")
        self.assertEqual(result["error"]["fields"], ["installation_path"])
        self.run.assert_not_called()

    def test_single_instance_is_selected_with_name_and_stable_binding(self):
        control = self.control()
        result = control.discover().to_dict()
        candidate = result["candidates"][0]
        self.assertTrue(result["ok"])
        self.assertEqual(result["selected_key"], candidate["key"])
        self.assertEqual(candidate["instance_name"], "明日方舟 主号")
        self.assertEqual(candidate["instance_id"], "0")
        self.assertEqual(candidate["binding"]["last_serial"], "")
        self.assertEqual(candidate["serial"], "127.0.0.1:16384")
        self.assertEqual(control.discover().selected_key, candidate["key"])
        self.assertEqual(self.configuration.device.preset_id, "manual.other")

    def test_multiple_instances_never_select_first_online_target(self):
        result = self.control(output=vendor_output("multiple")).discover().to_dict()
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "selection_required")
        self.assertIsNone(result["selected_key"])
        self.assertEqual(
            [item["instance_id"] for item in result["candidates"]], ["0", "2"]
        )

    def test_stopped_instance_has_no_stale_or_guessed_endpoint(self):
        result = self.control(output=vendor_output("stopped")).discover().to_dict()
        candidate = result["candidates"][0]
        self.assertEqual(candidate["instance_name"], "明日方舟 小号")
        self.assertEqual(candidate["state"], "stopped")
        self.assertEqual(candidate["serial"], "")
        self.assertEqual(candidate["binding"]["last_serial"], "")

    def test_invalid_instance_preserves_valid_candidates_and_requires_selection(self):
        result = self.control(output=vendor_output("partial")).discover().to_dict()
        self.assertEqual([item["instance_id"] for item in result["candidates"]], ["0"])
        self.assertIsNone(result["selected_key"])
        self.assertEqual(result["error"]["code"], "manager_output")
        self.assertEqual(result["error"]["fields"], ["manager_path"])

    def test_permission_denied_source_keeps_candidates_from_other_sources(self):
        result = (
            self.control(
                registry=Mock(side_effect=PermissionError("denied")),
                process=lambda: [self.folder],
            )
            .discover()
            .to_dict()
        )
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["error"]["code"], "discovery_permission")
        self.assertEqual(result["error"]["fields"], ["installation_path"])

    def test_timeout_keeps_other_installation_without_switching_to_it(self):
        other = self.root / "another"
        self.add_installation(other, "nx_main")
        run = Mock(
            side_effect=[
                subprocess.CompletedProcess([], 0, vendor_output("single"), b""),
                subprocess.TimeoutExpired("MuMuManager.exe", 3),
            ]
        )
        result = (
            self.control(run=run, registry=lambda: [self.folder, str(other)])
            .discover()
            .to_dict()
        )
        self.assertEqual(len(result["candidates"]), 1)
        self.assertIsNone(result["selected_key"])
        self.assertEqual(result["error"]["code"], "discovery_timeout")
        self.assertTrue(
            all(0 < call.kwargs["timeout"] <= 3 for call in run.call_args_list)
        )

    def test_malformed_oversized_and_duplicate_outputs_are_not_bindings(self):
        for output in (
            b"{broken",
            b"x" * (1024 * 1024 + 1),
            b'{"0":{},"0":{}}',
            b'{"0":{"name":"bad","is_process_started":"false"}}',
            b'[{"index":"0"},{"index":"0"}]',
        ):
            with self.subTest(output=output[:50]):
                result = self.control(output=output).discover().to_dict()
                self.assertEqual(result["candidates"], [])
                self.assertEqual(result["error"]["code"], "manager_output")

    def test_deeply_nested_output_keeps_other_installations_available(self):
        other = self.root / "another"
        self.add_installation(other, "nx_main")
        run = Mock(
            side_effect=[
                subprocess.CompletedProcess([], 0, vendor_output("single"), b""),
                subprocess.CompletedProcess(
                    [], 0, b"[" * 10000 + b"0" + b"]" * 10000, b""
                ),
            ]
        )
        result = (
            self.control(run=run, registry=lambda: [self.folder, str(other)])
            .discover()
            .to_dict()
        )
        self.assertEqual(len(result["candidates"]), 1)
        self.assertIsNone(result["selected_key"])
        self.assertEqual(result["error"]["code"], "manager_output")
        self.assertEqual(result["error"]["fields"], ["manager_path"])

    def test_process_layouts_and_registry_duplicates_produce_one_installation(self):
        for executable in (
            self.root / "shell/MuMuPlayer.exe",
            self.root / "nx_device/12.0/shell/MuMuNxDevice.exe",
        ):
            with self.subTest(executable=executable):
                control = self.control(process=lambda: [str(executable)])
                result = control.discover().to_dict()
                self.assertEqual(len(result["candidates"]), 1)
                self.assertEqual(len(self.run.call_args_list), 1)

    def test_unrecognized_shallow_process_path_does_not_abort_discovery(self):
        shallow = Path(self.root.anchor) / "shell/MuMuNxDevice.exe"
        result = (
            self.control(registry=lambda: [str(shallow), self.folder])
            .discover()
            .to_dict()
        )
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["errors"], [])

    def test_manual_installation_repair_is_verified_before_product_selection(self):
        self.configuration.device.installation_path = self.folder
        result = self.control(registry=lambda: []).discover().to_dict()
        self.assertTrue(result["ok"])
        self.assertEqual(result["candidates"][0]["preset_id"], "windows.mumu12")

    def test_explicit_manager_keeps_its_installation_identity_with_both_layouts(self):
        selected = self.add_installation(self.root, "nx_main")
        self.configuration.device.manager_path = str(selected)
        self.configuration.device.installation_path = self.folder
        result = self.control().discover().to_dict()
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["manager_path"], str(selected))
        self.assertEqual(len(self.run.call_args_list), 1)

    def test_runtime_sources_resolve_and_deduplicate_the_installation(self):
        for pair in ("main", "shell"):
            root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
            manager = self.add_installation(root, f"temp/{pair}")
            for source in (
                root,
                root / "uninstall.exe",
                manager.parent,
                manager.parent / "MuMuPlayer.exe",
                manager,
            ):
                for processes in ([], [str(manager)]):
                    with self.subTest(pair=pair, source=source, processes=processes):
                        result = (
                            self.control(
                                registry=lambda: [str(source)],
                                process=lambda: processes,
                            )
                            .discover()
                            .to_dict()
                        )
                        self.assertEqual(len(result["candidates"]), 1)
                        binding = result["candidates"][0]["binding"]
                        self.assertEqual(Path(binding["installation_path"]), root)
                        self.assertEqual(Path(binding["manager_path"]), manager)
                        self.assertEqual(len(self.run.call_args_list), 1)

    def test_explicit_runtime_manager_keeps_priority_over_other_layouts(self):
        for layout in ("temp/main", "temp/shell", ".backup/main", ".backup/shell"):
            with self.subTest(layout=layout):
                manager = self.add_installation(self.root, layout).resolve()
                self.configuration.device.manager_path = str(manager)
                result = self.control().discover().to_dict()
                self.assertEqual(len(result["candidates"]), 1)
                binding = result["candidates"][0]["binding"]
                self.assertEqual(
                    Path(binding["installation_path"]), self.root.resolve()
                )
                self.assertEqual(Path(binding["manager_path"]), manager)
                self.assertEqual(len(self.run.call_args_list), 1)

    def test_all_installs_share_maximum_64_instance_limit(self):
        row = json.loads(vendor_output("single"))["0"]
        output = json.dumps(
            {str(index): {**row, "index": str(index)} for index in range(70)}
        ).encode()
        result = self.control(output=output).discover().to_dict()
        self.assertEqual(len(result["candidates"]), 64)
        self.assertEqual(result["error"]["code"], "discovery_limit")
        self.assertIsNone(result["selected_key"])

    def test_discovery_never_queries_past_shared_six_second_deadline(self):
        now = [0.0]

        def processes():
            now[0] = 6.0
            return []

        result = (
            self.control(process=processes, clock=lambda: now[0]).discover().to_dict()
        )
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"]["code"], "discovery_timeout")
        self.run.assert_not_called()

    def test_bound_instance_refresh_accepts_direct_object_and_dynamic_port(self):
        entries = json.loads(vendor_output("dynamic"))
        run = Mock(
            side_effect=[
                subprocess.CompletedProcess([], 0, json.dumps(entry).encode(), b"")
                for entry in entries
            ]
        )
        profile = DeviceProfile(
            preset_id="windows.mumu12",
            installation_path=self.folder,
            manager_path=str(self.manager),
            instance_id="2",
            last_serial="127.0.0.1:16384",
        )
        simulator = ProductionSimulator(run=run)
        self.assertEqual(simulator.inspect(profile, 3).serial, "127.0.0.1:16448")
        self.assertEqual(simulator.inspect(profile, 3).serial, "127.0.0.1:16512")
        self.assertTrue(all(call.args[0][-1] == "2" for call in run.call_args_list))

    def test_reused_index_with_a_different_name_never_rebinds_the_saved_instance(self):
        renamed = json.dumps(
            {
                "index": "2",
                "name": "另一个实例",
                "is_process_started": True,
                "is_android_started": True,
                "adb_port": 16448,
            }
        ).encode()
        profile = DeviceProfile(
            preset_id="windows.mumu12",
            installation_path=self.folder,
            manager_path=str(self.manager),
            instance_id="2",
            instance_name="明日方舟 小号",
            last_serial="127.0.0.1:16384",
        )
        run = Mock(return_value=subprocess.CompletedProcess([], 0, renamed, b""))
        with self.assertRaises(InstanceBindingError) as failure:
            ProductionSimulator(run=run).inspect(profile, 3)
        self.assertEqual(failure.exception.code, "binding_changed")
        self.assertEqual(failure.exception.fields, ["instance_id", "instance_name"])

    def test_a_profile_without_a_saved_name_still_binds_the_same_index(self):
        entry = json.loads(vendor_output("single"))["0"]
        entry.update(adb_port=16384)
        for saved in ("", "   "):
            with self.subTest(saved=saved):
                profile = DeviceProfile(
                    preset_id="windows.mumu12",
                    installation_path=self.folder,
                    manager_path=str(self.manager),
                    instance_id="0",
                    instance_name=saved,
                    last_serial="127.0.0.1:16384",
                )
                run = Mock(
                    return_value=subprocess.CompletedProcess(
                        [], 0, json.dumps(entry).encode(), b""
                    )
                )
                observation = ProductionSimulator(run=run).inspect(profile, 3)
                self.assertEqual(observation.state, "running")
                self.assertEqual(observation.serial, "127.0.0.1:16384")

    def test_manager_response_without_a_name_still_binds_a_saved_index(self):
        entry = json.loads(vendor_output("single"))["0"]
        entry.pop("name")
        profile = DeviceProfile(
            preset_id="windows.mumu12",
            installation_path=self.folder,
            manager_path=str(self.manager),
            instance_id="0",
            instance_name="",
            last_serial="127.0.0.1:16384",
        )
        run = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, json.dumps(entry).encode(), b""
            )
        )
        observation = ProductionSimulator(run=run).inspect(profile, 3)
        self.assertEqual(observation.state, "running")
        self.assertEqual(observation.serial, "127.0.0.1:16384")


class MuMuCommandOwnershipTests(unittest.TestCase):
    def test_bounded_command_reaps_its_process_and_closes_output_on_every_exit(self):
        for script, timeout, expected in (
            ("print('valid-output')", 3, None),
            (
                "import sys; sys.stdout.buffer.write(b'x' * (1024*1024+1))",
                3,
                ValueError,
            ),
            ("import time; time.sleep(20)", 0.1, subprocess.TimeoutExpired),
        ):
            with self.subTest(expected=expected):
                processes = []
                streams = []
                popen = subprocess.Popen

                def launch(*args, **kwargs):
                    streams.append(kwargs["stdout"])
                    process = popen(*args, **kwargs)
                    processes.append(process)
                    return process

                with patch(
                    "arknights_mower.utils.device.manager_io.subprocess.Popen",
                    side_effect=launch,
                ):

                    def run():
                        return run_mumu_command(
                            [sys.executable, "-c", script],
                            timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW
                            if os.name == "nt"
                            else 0,
                        )

                    if expected:
                        with self.assertRaises(expected):
                            run()
                    else:
                        self.assertEqual(run().stdout.strip(), b"valid-output")
                self.assertTrue(
                    all(process.poll() is not None for process in processes)
                )
                self.assertTrue(all(stream.closed for stream in streams))


if __name__ == "__main__":
    unittest.main()
