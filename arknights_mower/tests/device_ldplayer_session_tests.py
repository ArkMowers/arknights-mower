import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import Adapter, Clock
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.ldplayer_endpoint import LDPlayerBindingError
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
from arknights_mower.utils.device.session_io import (
    ProductionSessionADB,
    ProductionSimulator,
)

CHOSEN_BOOT = "42e9de7c-0aa1-4a25-aec5-81d7e8a1acef"
OTHER_BOOT = "59d349d4-68a1-4c9e-aa90-7b48ac0b7685"
RUNNING = "0,other,0,0,1,123,124\n2,chosen,0,0,1,223,224\n"


class LDPlayerTransport:
    """Fixture transport for the public simulator/session application seams."""

    def __init__(self, folder):
        self.manager = Path(folder) / "ldconsole.exe"
        self.bundled_adb = Path(folder) / "adb.exe"
        self.adb = Path(folder) / "chosen-adb.exe"
        for path in (self.manager, self.bundled_adb, self.adb):
            path.touch()
        self.profile = DeviceProfile(
            preset_id="windows.ldplayer9",
            manager_path=str(self.manager),
            adb_path=str(self.adb),
            instance_id="2",
            last_serial="emulator-5558",
        )
        self.listings = [RUNNING]
        self.states = {"emulator-5558": "device", "emulator-5554": "device"}
        self.boot_ids = {"emulator-5558": CHOSEN_BOOT, "emulator-5554": OTHER_BOOT}
        self.manager_boot = CHOSEN_BOOT
        self.calls = []
        self.listeners = Mock(return_value=[])
        self.version = "Android Debug Bridge version 1.0.41"
        self.display = "Physical size: 1920x1080"
        self.lifecycle = []

    def run(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[1] == "list2":
            output = self.listings[0]
            if len(self.listings) > 1:
                self.listings.pop(0)
        elif argv[0] == str(self.manager) and argv[1] in {"launch", "quit"}:
            self.lifecycle.append((argv[1], argv[-1]))
            self.listings = [RUNNING if argv[1] == "launch" else "2,chosen,0,0,0,-1,-1"]
            output = ""
        elif argv[0] == str(self.manager):
            output = self.manager_boot
        elif argv[1] == "version":
            output = self.version
        elif argv[1] == "devices":
            output = "List of devices attached\n" + "\n".join(
                f"{serial}\t{state}" for serial, state in self.states.items()
            )
        elif "wm" in argv:
            output = self.display
        elif argv[1] == "-s":
            output = "1" if "getprop" in argv else self.boot_ids[argv[2]]
        else:
            raise AssertionError(f"Unexpected fixture command: {argv}")
        return subprocess.CompletedProcess(argv, 0, output.encode(), b"")

    def simulator(self, *, probe=None):
        return ProductionSimulator(
            run=self.run,
            probe=probe or (lambda timeout: None),
            listener_ports=self.listeners,
        )


class LDPlayerSessionTests(unittest.TestCase):
    def test_online_formula_endpoint_cannot_replace_the_bound_instance(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = Path(folder) / "ldconsole.exe"
            manager.touch()
            adb = Path(folder) / "adb.exe"
            adb.touch()
            profile = DeviceProfile(
                preset_id="windows.ldplayer9",
                manager_path=str(manager),
                adb_path=str(adb),
                instance_id="2",
                last_serial="emulator-5558",
            )
            calls = []

            def run(argv, **kwargs):
                calls.append(argv)
                if argv[1] == "list2":
                    output = b"0,other,0,0,1,123,124\n2,chosen,0,0,1,223,224\n"
                elif argv[0] == str(manager):
                    output = b"42e9de7c-0aa1-4a25-aec5-81d7e8a1acef"
                elif argv[1] == "version":
                    output = b"Android Debug Bridge version 1.0.41"
                elif argv[1] == "devices":
                    output = (
                        b"List of devices attached\n"
                        b"emulator-5554\tdevice\nemulator-5558\tdevice\n"
                    )
                else:
                    output = b"59d349d4-68a1-4c9e-aa90-7b48ac0b7685"
                return subprocess.CompletedProcess(argv, 0, output, b"")

            with self.assertRaises(ValueError) as failure:
                ProductionSimulator(
                    run=run,
                    probe=lambda timeout: None,
                    listener_ports=lambda pid, timeout: [],
                ).inspect(profile, 3)
            self.assertEqual(failure.exception.code, "endpoint_unresolved")
            self.assertFalse(any("emulator-5554" in argv for argv in calls))

    def test_reused_index_with_a_different_name_never_rebinds_the_saved_instance(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = LDPlayerTransport(folder)
            fixture.profile.instance_name = "renamed"
            with self.assertRaises(LDPlayerBindingError) as failure:
                fixture.simulator().inspect(fixture.profile, 6)
            self.assertEqual(failure.exception.code, "binding_changed")
            self.assertEqual(failure.exception.fields, ["instance_id", "instance_name"])
            fixture.profile.instance_name = "chosen"
            result = fixture.simulator().inspect(fixture.profile, 6)
            self.assertEqual(result.serial, "emulator-5558")

    def test_saved_name_absent_still_binds_the_same_index(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = LDPlayerTransport(folder)
            result = fixture.simulator().inspect(fixture.profile, 6)
            self.assertEqual(
                (result.state, result.serial), ("running", "emulator-5558")
            )

    def test_changed_port_refreshes_only_the_original_vbox_process(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = LDPlayerTransport(folder)
            fixture.boot_ids["emulator-5558"] = OTHER_BOOT
            fixture.states["127.0.0.1:16789"] = "device"
            fixture.boot_ids["127.0.0.1:16789"] = CHOSEN_BOOT
            fixture.listeners.return_value = ["127.0.0.1:16789"]
            result = fixture.simulator().inspect(fixture.profile, 6)
            self.assertEqual(
                (result.state, result.serial), ("running", "127.0.0.1:16789")
            )
            self.assertEqual(fixture.listeners.call_args.args[0], 224)
            self.assertFalse(any("emulator-5554" in argv for argv, _ in fixture.calls))
            self.assertTrue(
                all(0 < options["timeout"] <= 3 for _, options in fixture.calls)
            )
            self.assertEqual(fixture.profile.last_serial, "emulator-5558")

    def test_stopped_and_starting_instances_never_reuse_an_online_old_endpoint(self):
        for row, expected in (
            ("2,chosen,0,0,0,-1,-1", "stopped"),
            ("2,chosen,0,0,0,223,224", "starting"),
        ):
            with self.subTest(state=expected), tempfile.TemporaryDirectory() as folder:
                fixture = LDPlayerTransport(folder)
                fixture.listings = [row]
                result = fixture.simulator().inspect(fixture.profile, 6)
                self.assertEqual((result.state, result.serial), (expected, None))
                self.assertEqual(len(fixture.calls), 1)

    def test_deleted_or_malformed_binding_never_falls_back_to_other_online_instances(
        self,
    ):
        for listing in (
            "0,other,0,0,1,123,124\n",
            "2,chosen,0,0,banana,223,224\n",
            "2,chosen,0,0,1,223,224\n2,duplicate,0,0,1,323,324\n",
            '2,"unterminated',
        ):
            with self.subTest(listing=listing), tempfile.TemporaryDirectory() as folder:
                fixture = LDPlayerTransport(folder)
                fixture.listings = [listing]
                with self.assertRaises(LDPlayerBindingError) as failure:
                    fixture.simulator().inspect(fixture.profile, 6)
                self.assertEqual(failure.exception.code, "manager_output")
                self.assertEqual(len(fixture.calls), 1)

    def test_known_adb_failures_are_structured_without_shelling_offline_devices(self):
        scenarios = json.loads(
            (
                Path(__file__).parent / "fixtures/ldplayer9_endpoint_failures.json"
            ).read_text(encoding="utf-8")
        )
        for scenario in scenarios:
            with (
                self.subTest(scenario=scenario),
                tempfile.TemporaryDirectory() as folder,
            ):
                fixture = LDPlayerTransport(folder)
                fixture.states["emulator-5558"] = scenario["state"]
                if "boot_id" in scenario:
                    fixture.boot_ids["emulator-5558"] = scenario["boot_id"]
                with self.assertRaises(LDPlayerBindingError) as failure:
                    fixture.simulator().inspect(fixture.profile, 6)
                self.assertEqual(failure.exception.code, scenario["expected_code"])
                self.assertEqual(failure.exception.fields, scenario["fields"])
                if scenario["state"] != "device":
                    self.assertFalse(any(argv[1] == "-s" for argv, _ in fixture.calls))

    def test_invalid_manager_identity_and_restart_during_probe_do_not_bind(self):
        for source, expected in (
            ("identity", "endpoint_unresolved"),
            ("restart", "binding_changed"),
        ):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as folder:
                fixture = LDPlayerTransport(folder)
                if source == "identity":
                    fixture.manager_boot = "permission denied"
                else:
                    fixture.listings = [RUNNING, "2,chosen,0,0,1,323,324\n"]
                with self.assertRaises(LDPlayerBindingError) as failure:
                    fixture.simulator().inspect(fixture.profile, 6)
                self.assertEqual(failure.exception.code, expected)

    def test_multiple_verified_aliases_require_an_explicit_saved_endpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = LDPlayerTransport(folder)
            fixture.states["127.0.0.1:5559"] = "device"
            fixture.boot_ids["127.0.0.1:5559"] = CHOSEN_BOOT
            fixture.profile.last_serial = ""
            with self.assertRaises(LDPlayerBindingError) as failure:
                fixture.simulator().inspect(fixture.profile, 6)
            self.assertEqual(failure.exception.code, "endpoint_ambiguous")
            fixture.profile.last_serial = "127.0.0.1:5559"
            result = fixture.simulator().inspect(fixture.profile, 6)
            self.assertEqual(result.serial, "127.0.0.1:5559")

    def test_incompatible_bundled_adb_cannot_let_manager_replace_shared_server(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = LDPlayerTransport(folder)
            fixture.version = "Android Debug Bridge version 1.0.40"
            with self.assertRaises(SharedADBError):
                fixture.simulator(probe=lambda timeout: 41).inspect(fixture.profile, 6)
            self.assertEqual(
                [argv for argv, _ in fixture.calls],
                [
                    [str(fixture.manager), "list2"],
                    [str(fixture.bundled_adb), "version"],
                ],
            )

    def test_new_sessions_resolve_one_adb_and_recheck_the_original_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = LDPlayerTransport(folder)
            fixture.profile.adb_path = "stale-adb"
            adb = Mock()
            adb.resolve_adb.return_value = str(fixture.adb)
            adb.devices.return_value = [("emulator-5558", "device")]
            adb.boot_completed.return_value = "1"
            # The ready gate also confirms the display and first frame; both are
            # observations of this double, not of a capture backend.
            adb.display_size.return_value = "Physical size: 1920x1080"
            adb.frame_size.return_value = (1920, 1080)
            session = DeviceSession(adb, fixture.simulator())
            session.bind(fixture.profile)
            first = session.observe()
            self.assertEqual((first.state, first.adb_path), ("ready", str(fixture.adb)))
            self.assertFalse(any("stale-adb" in argv for argv, _ in fixture.calls))
            fixture.listings = ["0,other,0,0,1,123,124\n"]
            session.bind(fixture.profile)
            second = session.observe()
            self.assertEqual(
                (second.state, second.serial, second.code),
                ("offline", "", "manager_output"),
            )
            self.assertEqual(adb.resolve_adb.call_count, 2)
            adb.recover.assert_not_called()


class LDPlayerControlTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.fixture = LDPlayerTransport(folder)
        self.configuration = Conf(device=self.fixture.profile.model_dump())
        self.io = PreflightIO()
        self.io.host = "windows"
        self.io.paths.add(str(self.fixture.adb))
        self.io.installed.update([folder, str(self.fixture.manager)])
        self.io.targets = list(self.fixture.states.items())
        self.adapter = Mock(wraps=Adapter())
        self.control = DeviceControl(
            lambda: self.configuration,
            self.adapter,
            preflight=PreflightService(self.io),
            session=DeviceSession(
                ProductionSessionADB(
                    run=self.fixture.run,
                    probe=lambda timeout: None,
                    # The frame probe belongs to the capture backends; this test
                    # owns binding and ADB-path decisions only.
                    frame=lambda adb_path, serial, timeout: (1920, 1080),
                ),
                self.fixture.simulator(),
                clock=Clock(),
                policy=RecoveryPolicy(timeout=12, local_wait=1),
            ),
        )
        self.addCleanup(self.control.close)

    def test_new_control_sessions_follow_only_the_bound_instances_changed_port(self):
        self.fixture.boot_ids["emulator-5558"] = OTHER_BOOT
        saved_profile = self.configuration.device.model_dump()
        for serial in ("127.0.0.1:16789", "127.0.0.1:17899"):
            with self.subTest(serial=serial):
                self.fixture.states[serial] = "device"
                self.fixture.boot_ids[serial] = CHOSEN_BOOT
                self.fixture.listeners.return_value = [serial]
                self.io.targets = list(self.fixture.states.items())
                try:
                    result = self.control.start()
                    self.assertTrue(result.ok, result.error)
                    self.assertEqual(result.serial, serial)
                    self.assertEqual(
                        self.configuration.device.model_dump(), saved_profile
                    )
                    runtime, verified = self.adapter.open_verified.call_args.args
                    self.assertEqual(runtime.device.last_serial, serial)
                    self.assertEqual(runtime.device.instance_id, "2")
                    self.assertEqual(
                        (verified.adb_path, verified.serial),
                        (str(self.fixture.adb), serial),
                    )
                    self.assertEqual(verified.observations["frame"], [1920, 1080])
                finally:
                    self.control.close()
                self.fixture.boot_ids[serial] = OTHER_BOOT
        self.assertEqual(self.adapter.open_verified.call_count, 2)
        self.assertEqual(self.fixture.lifecycle, [])
        self.assertFalse(any("emulator-5554" in argv for argv, _ in self.fixture.calls))

    def test_deleted_instance_is_reported_before_opening_a_device(self):
        self.fixture.listings = ["0,other,0,0,1,123,124\n"]
        result = self.control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "manager_output")
        self.adapter.open_verified.assert_not_called()
        self.assertEqual(self.fixture.lifecycle, [])

    def test_stopped_instance_launches_once_then_opens_verified_original_target(self):
        self.fixture.listings = ["2,chosen,0,0,0,-1,-1\n"]
        result = self.control.start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "emulator-5558")
        self.assertEqual(self.fixture.lifecycle, [("launch", "2")])
        self.assertEqual(self.adapter.open_verified.call_count, 1)

    def test_unverified_endpoint_never_opens_a_device(self):
        self.fixture.boot_ids["emulator-5558"] = OTHER_BOOT
        self.io.size = "Physical size: 1920x1080"
        result = self.control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "endpoint_unresolved")
        self.adapter.open_verified.assert_not_called()
        self.control.close()

    def test_a_portrait_reported_size_still_opens_the_verified_target(self):
        # The decoded frame is authoritative, so a portrait report is accepted.
        self.io.size = "Physical size: 1280x720"
        self.io.frame = np.zeros((1080, 1920, 3), np.uint8)
        result = self.control.start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "emulator-5558")
        self.adapter.open_verified.assert_called_once()
        self.control.close()


if __name__ == "__main__":
    unittest.main()
