"""MuMu Pro manual ADB binding and manager lifecycle isolation."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Adapter, Clock, Simulator
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import (
    DeviceSession,
    RecoveryPolicy,
    SessionFailure,
)
from arknights_mower.utils.device.session_io import ProductionSimulator


class MuMuProTests(unittest.TestCase):
    def setUp(self):
        self.io = PreflightIO()
        self.io.host = "macos"
        self.conf = Conf(
            device={
                "preset_id": "macos.mumu_pro",
                "instance_id": "0",
                "last_serial": "127.0.0.1:16384",
                "adb_path": "product-adb",
            }
        )
        self.command = Mock(side_effect=AssertionError("no confirmed manager contract"))
        self.simulator = ProductionSimulator(run=self.command)
        self.control = DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(DiscoveryIO(), self.simulator),
        )

    def assert_manual_required(self, result, code="mumu_pro_manual_required"):
        self.assertFalse(result["ok"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"]["code"], code)
        self.assertEqual(result["error"]["action"], "manual")

    def test_missing_manager_offers_manual_setup_without_adb_guess(self):
        with TemporaryDirectory() as directory:
            self.conf.device.manager_path = str(Path(directory) / "mumutool")
            before = self.conf.model_dump()
            self.assert_manual_required(
                self.control.discover().to_dict(), "mumu_pro_manager_missing"
            )
        self.assertEqual(self.conf.model_dump(), before)
        self.command.assert_not_called()

    def test_preflight_verifies_only_saved_endpoint_even_with_other_devices(self):
        self.io.targets = [("127.0.0.1:16384", "device"), ("USB-123", "device")]
        self.conf.device.installation_path = "/old/MuMuPro.app"
        self.conf.device.manager_path = "/old/mumutool"
        original_devices = self.io.devices
        self.io.devices = Mock(side_effect=original_devices)
        before = self.conf.model_dump()
        result = self.control.preflight().to_dict()
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["serial"], "127.0.0.1:16384")
        self.io.devices.assert_called_once_with("product-adb", "127.0.0.1:16384")
        self.assertEqual(result["observations"]["frame"], [1920, 1080])
        self.assertEqual(self.conf.model_dump(), before)

    def test_new_session_uses_saved_serial_without_manager_commands(self):
        self.io.paths.add("verified-adb")
        self.io.targets = [("127.0.0.1:16384", "device"), ("USB-123", "device")]
        adb = ADB()
        adb.rows = [("127.0.0.1:16384", "device"), ("USB-123", "device")]
        adb.boot = "1"
        control = DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            session=DeviceSession(
                adb, self.simulator, clock=Clock(), policy=RecoveryPolicy(timeout=5)
            ),
        )
        before = self.conf.model_dump()
        result = control.start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.readiness.serial, "127.0.0.1:16384")
        self.assertEqual(adb.actions, [])
        self.command.assert_not_called()
        self.assertEqual(self.conf.model_dump(), before)

    def test_missing_target_never_adopts_another_online_device(self):
        self.conf.device.last_serial = ""
        self.io.targets = [("USB-123", "device")]
        result = self.control.preflight()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "target_required")
        self.assertEqual(result.serial, "")
        self.command.assert_not_called()

    def test_saved_target_absent_does_not_adopt_another_online_instance(self):
        self.io.targets = [("127.0.0.1:16416", "device")]
        result = self.control.preflight()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "target_absent")
        self.assertEqual(result.serial, "127.0.0.1:16384")
        self.command.assert_not_called()

    def test_selected_instance_cannot_bypass_missing_binding_checker(self):
        self.conf.device.topology_fingerprint = "a" * 64
        self.io.targets = [("127.0.0.1:16384", "device")]
        original_devices = self.io.devices
        self.io.devices = Mock(side_effect=original_devices)
        control = DeviceControl(
            lambda: self.conf, Adapter(), preflight=PreflightService(self.io)
        )
        result = control.preflight()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "binding_failed")
        self.io.devices.assert_not_called()

    def test_stopped_or_unresponsive_instance_never_receives_manager_commands(self):
        for state in ("stopped", "running"):
            with self.subTest(state=state):
                adb = ADB()
                simulator = Simulator()
                simulator.state = state
                simulator.serial = "127.0.0.1:16384" if state == "running" else None
                session = DeviceSession(
                    adb,
                    simulator,
                    clock=Clock(),
                    policy=RecoveryPolicy(
                        timeout=5, attempts=2, local_wait=1, poll_interval=1
                    ),
                )
                session.bind(self.conf.device)
                with self.assertRaises(SessionFailure):
                    session.ensure_ready()
                self.assertEqual(simulator.actions, [])

    def test_selected_stopped_instance_automatically_starts_without_adopting_others(
        self,
    ):
        adb, simulator = ADB(), Simulator()
        simulator.state = "stopped"
        serial = "127.0.0.1:16416"

        def started():
            simulator.state = "running"
            simulator.serial = serial
            adb.rows = [("127.0.0.1:16384", "device"), (serial, "device")]
            adb.boot = "1"

        simulator.on_start = started
        session = DeviceSession(
            adb, simulator, clock=Clock(), policy=RecoveryPolicy(timeout=5)
        )
        profile = self.conf.device.model_copy(
            update={"instance_id": "1", "topology_fingerprint": "a" * 64}
        )
        session.bind(profile)
        self.assertEqual(session.ensure_ready().serial, serial)
        self.assertEqual(simulator.actions, ["start"])

    def test_starting_without_port_is_booting_and_does_not_connect_stale_serial(self):
        adb, simulator = ADB(), Simulator()
        simulator.state = "starting"
        simulator.serial = None
        session = DeviceSession(adb, simulator, clock=Clock())
        session.bind(
            self.conf.device.model_copy(update={"topology_fingerprint": "a" * 64})
        )
        observation = session.observe()
        self.assertEqual(observation.state, "booting")
        self.assertEqual(observation.instance_state, "starting")
        self.assertEqual(observation.serial, "")
        self.assertEqual(simulator.actions, [])

    def test_manager_preparation_failure_preserves_verdict_without_vm_action(self):
        adb, simulator = ADB(), Simulator()
        simulator.prepare_mumu_pro = Mock(
            side_effect=InstanceBindingError(
                "mumu_pro_manager_start_failed", "管理器尚未就绪"
            )
        )
        session = DeviceSession(adb, simulator, clock=Clock())
        session.bind(
            self.conf.device.model_copy(update={"topology_fingerprint": "a" * 64})
        )
        with self.assertRaises(SessionFailure) as raised:
            session.ensure_ready()
        self.assertEqual(
            raised.exception.observation.code, "mumu_pro_manager_start_failed"
        )
        self.assertEqual(simulator.actions, [])
        result = self.control._failure("connection_failed", raised.exception)
        self.assertEqual(result.error.code, "mumu_pro_manager_start_failed")

    def test_manual_start_and_idle_stop_require_verified_selection(self):
        self.conf.close_simulator_when_idle = True
        self.assertEqual(
            self.control.start_bound().error.code, "mumu_pro_selection_required"
        )
        self.assertFalse(self.control.stop_bound_mumu_pro())
        self.command.assert_not_called()

    def test_manual_entry_still_requires_explicit_target_and_read_only_preflight(self):
        self.conf = Conf(device={"preset_id": "manual.other", "last_serial": ""})
        missing = self.control.preflight()
        self.assertEqual(missing.error.code, "target_required")
        self.conf.device.last_serial = "USB-123"
        checked = self.control.preflight()
        self.assertTrue(checked.ok, checked.error)
        self.assertEqual(checked.serial, "USB-123")
        self.assertEqual(checked.observations["frame"], [1920, 1080])


if __name__ == "__main__":
    unittest.main()
