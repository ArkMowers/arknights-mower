"""Unverified MuMu Pro bindings must require an explicit manual target."""

import unittest
from unittest.mock import Mock

from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Adapter, Clock
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
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

    def assert_manual_required(self, result):
        self.assertFalse(result["ok"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"]["code"], "mumu_pro_manual_required")
        self.assertEqual(result["error"]["action"], "manual")
        self.assertEqual(result["error"]["fields"], [])

    def test_unverified_discovery_offers_manual_setup_without_air_or_adb_guess(self):
        before = self.conf.model_dump()
        self.assert_manual_required(self.control.discover().to_dict())
        self.assertEqual(self.conf.model_dump(), before)
        self.command.assert_not_called()

    def test_preflight_rejects_saved_endpoint_even_when_an_adb_target_is_ready(self):
        self.io.targets = [("127.0.0.1:16384", "device"), ("USB-123", "device")]
        self.io.devices = Mock(side_effect=AssertionError("must not probe old serial"))
        before = self.conf.model_dump()
        result = self.control.preflight().to_dict()
        self.assert_manual_required(result)
        self.assertEqual(result["serial"], "")
        self.assertEqual(result["observations"], {})
        self.assertEqual(self.conf.model_dump(), before)

    def test_new_session_never_adopts_old_serial_or_controls_another_instance(self):
        adb = ADB()
        adb.rows = [("127.0.0.1:16384", "device"), ("USB-123", "device")]
        adb.boot = "1"
        adb.devices = Mock(side_effect=AssertionError("must not adopt old serial"))
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
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "mumu_pro_manual_required")
        self.assertEqual(result.readiness.code, "mumu_pro_manual_required")
        self.assertEqual(result.readiness.serial, "")
        self.assertEqual(adb.actions, [])
        self.command.assert_not_called()
        self.assertEqual(self.conf.model_dump(), before)

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
