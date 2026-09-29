"""BlueStacks Air detection and repair at the application boundary."""

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


class BlueStacksAirTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.app = self.root / "BlueStacks.app"
        self.io = PreflightIO()
        self.io.host = "macos"
        self.conf = Conf(
            device={
                "preset_id": "macos.bluestacks_air",
                "installation_path": str(self.app),
                "last_serial": "",
            }
        )
        self.control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(DiscoveryIO()),
        )

    def install(self):
        (self.app / "Contents/MacOS").mkdir(parents=True)
        (self.app / "Contents/Info.plist").write_bytes(b"fixture application")
        self.io.installed.add(str(self.app))

    def test_adb_disabled_returns_enable_steps_and_endpoint_repair(self):
        self.install()
        self.io.targets = []
        result = self.control.discover().to_dict()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "air_adb_unavailable")
        self.assertEqual(result["error"]["fields"], ["last_serial"])
        self.assertEqual(result["error"]["action"], "retry")
        for text in ("Settings", "Advanced", "ADB", "保存", "重试"):
            self.assertIn(text, result["error"]["message"])
        self.assertEqual(result["profile_patch"], {})
        self.assertEqual(self.conf.device.last_serial, "")

    def test_missing_application_returns_installation_repair_without_changing_conf(
        self,
    ):
        before = self.conf.model_dump()
        result = self.control.discover().to_dict()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "missing_installation")
        self.assertEqual(result["error"]["fields"], ["installation_path"])
        self.assertEqual(result["error"]["action"], "retry")
        self.assertEqual(result["candidates"], [])
        self.assertEqual(self.conf.model_dump(), before)


if __name__ == "__main__":
    unittest.main()
