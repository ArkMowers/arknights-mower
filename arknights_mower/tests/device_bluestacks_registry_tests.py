"""Modeled BlueStacks registry records exercised through application discovery."""

import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.bluestacks_discovery import BlueStacksDiscoveryIO
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService

FIXTURES = Path(__file__).parent / "fixtures"


class RegistryFixture:
    HKEY_LOCAL_MACHINE = 1
    HKEY_CURRENT_USER = 2
    KEY_READ = 4
    KEY_WOW64_64KEY = 8
    KEY_WOW64_32KEY = 16

    def __init__(self):
        self.entries = {}

    def OpenKey(self, hive, path, reserved, access):
        key = (hive, access, path)
        if key not in self.entries:
            raise FileNotFoundError(path)
        values = self.entries[key]
        if isinstance(values, Exception):
            raise values
        return nullcontext(values)

    def QueryValueEx(self, values, name):
        if name not in values:
            raise FileNotFoundError(name)
        value = values[name]
        if isinstance(value, Exception):
            raise value
        return value, 1


class BlueStacksRegistryDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.player = self.root / "BlueStacks program/HD-Player.exe"
        self.player.parent.mkdir()
        self.player.touch()
        self.config_path = self.root / "BlueStacks data/bluestacks.conf"
        self.config_path.parent.mkdir()
        self.config_path.write_bytes(
            (FIXTURES / "bluestacks5_single.conf").read_bytes()
        )
        self.values = {
            "InstallDir": str(self.player.parent),
            "UserDefinedDir": str(self.config_path.parent),
        }
        self.registry = RegistryFixture()
        self.enterContext(patch.dict("sys.modules", {"winreg": self.registry}))
        preflight = PreflightIO()
        preflight.host = "windows"
        self.control = DeviceControl(
            Conf,
            Mock(),
            preflight=PreflightService(preflight),
            discovery=DiscoveryService(BlueStacksDiscoveryIO(platform="windows")),
        )

    def register(self, values, name="BlueStacks_nxt", hive=1, view=8):
        self.registry.entries[(hive, 4 | view, "SOFTWARE\\" + name)] = values

    def test_official_product_records_are_read_in_both_hives_and_registry_views(self):
        for name in ("BlueStacks_nxt", "BlueStacks_nxt_cn"):
            for hive in (1, 2):
                for view in (8, 16):
                    with self.subTest(name=name, hive=hive, view=view):
                        self.registry.entries.clear()
                        self.register(self.values, name=name, hive=hive, view=view)
                        result = self.control.discover().to_dict()
                        self.assertTrue(result["ok"], result["error"])
                        self.assertEqual(len(result["candidates"]), 1)
                        candidate = result["candidates"][0]
                        self.assertEqual(result["selected_key"], candidate["key"])
                        self.assertEqual(
                            Path(candidate["binding"]["manager_path"]), self.player
                        )
                        self.assertEqual(
                            Path(candidate["binding"]["config_path"]), self.config_path
                        )
                        self.assertEqual(candidate["instance_id"], "Pie64")
                        self.assertEqual(candidate["binding"]["last_serial"], "")

    def test_duplicate_product_records_offer_one_instance(self):
        for name in ("BlueStacks_nxt", "BlueStacks_nxt_cn"):
            for hive in (1, 2):
                for view in (8, 16):
                    self.register(self.values, name=name, hive=hive, view=view)
        result = self.control.discover().to_dict()
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["selected_key"], result["candidates"][0]["key"])

    def test_independent_installations_keep_program_and_data_paths_paired(self):
        alternate_player = self.root / "China program/HD-Player.exe"
        alternate_player.parent.mkdir()
        alternate_player.touch()
        alternate_config = self.root / "China data/bluestacks.conf"
        alternate_config.parent.mkdir()
        alternate_config.write_text(
            self.config_path.read_text(encoding="utf-8").replace("Pie64", "Nougat64"),
            encoding="utf-8",
        )
        self.register(self.values)
        self.register(
            {
                "InstallDir": str(alternate_player.parent),
                "UserDefinedDir": str(alternate_config.parent),
            },
            name="BlueStacks_nxt_cn",
            hive=2,
            view=16,
        )
        result = self.control.discover().to_dict()
        self.assertTrue(result["ok"], result["error"])
        self.assertIsNone(result["selected_key"])
        self.assertEqual(len(result["candidates"]), 2)
        actual = {
            (
                Path(candidate["binding"]["manager_path"]),
                Path(candidate["binding"]["config_path"]),
                candidate["instance_id"],
            )
            for candidate in result["candidates"]
        }
        self.assertEqual(
            actual,
            {
                (self.player, self.config_path, "Pie64"),
                (alternate_player, alternate_config, "Nougat64"),
            },
        )
        self.assertEqual(len({item["key"] for item in result["candidates"]}), 2)

    def test_stale_registered_paths_request_the_matching_source_repair(self):
        for name, value, code, field in (
            (
                "InstallDir",
                str(self.root / "removed program"),
                "missing_installation",
                "installation_path",
            ),
            (
                "UserDefinedDir",
                str(self.root / "removed data"),
                "missing_config",
                "config_path",
            ),
        ):
            with self.subTest(name=name):
                self.register({**self.values, name: value})
                result = self.control.discover().to_dict()
                self.assertFalse(result["ok"])
                self.assertEqual(result["candidates"], [])
                self.assertEqual(result["error"]["code"], code)
                self.assertEqual(result["error"]["fields"], [field])

    def test_access_denied_is_reported_without_silent_source_fallback(self):
        for values, field in (
            (PermissionError("key denied"), "installation_path"),
            (
                {**self.values, "InstallDir": PermissionError("denied")},
                "installation_path",
            ),
            (
                {**self.values, "UserDefinedDir": PermissionError("denied")},
                "config_path",
            ),
        ):
            with self.subTest(values=values):
                self.register(values)
                result = self.control.discover().to_dict()
                self.assertFalse(result["ok"])
                self.assertEqual(result["candidates"], [])
                self.assertEqual(result["error"]["code"], "discovery_permission")
                self.assertIn(field, result["error"]["fields"])
                self.assertIn("BlueStacks", result["error"]["message"])

    def test_missing_registered_values_identify_the_missing_source(self):
        for name, field in (
            ("InstallDir", "installation_path"),
            ("UserDefinedDir", "config_path"),
        ):
            with self.subTest(name=name):
                self.register(
                    {key: value for key, value in self.values.items() if key != name}
                )
                result = self.control.discover().to_dict()
                self.assertFalse(result["ok"])
                self.assertEqual(result["candidates"], [])
                self.assertEqual(result["error"]["code"], "config_invalid")
                self.assertEqual(result["error"]["fields"], [field])
                self.assertIn("BlueStacks", result["error"]["message"])

    def test_relative_empty_and_nonstring_values_are_rejected_with_source_repair(self):
        for name, field in (
            ("InstallDir", "installation_path"),
            ("UserDefinedDir", "config_path"),
        ):
            for value in ("BlueStacks_nxt", "../BlueStacks_nxt", "", " ", 42, None):
                with self.subTest(name=name, value=value):
                    self.register({**self.values, name: value})
                    result = self.control.discover().to_dict()
                    self.assertFalse(result["ok"])
                    self.assertEqual(result["candidates"], [])
                    self.assertEqual(result["error"]["code"], "config_invalid")
                    self.assertEqual(result["error"]["fields"], [field])

    def test_unrecognized_product_name_is_not_an_installation_source(self):
        self.register(self.values, name="BlueStacks_unverified")
        result = self.control.discover().to_dict()
        self.assertFalse(result["ok"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"]["code"], "missing_installation")


if __name__ == "__main__":
    unittest.main()
