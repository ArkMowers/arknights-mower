"""BlueStacks configuration fixtures through the device application seam."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.bluestacks_discovery import BlueStacksDiscoveryIO
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService

FIXTURES = Path(__file__).parent / "fixtures"


class BlueStacksDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.player = self.root / "program/HD-Player.exe"
        self.player.parent.mkdir()
        self.player.touch()
        self.config_path = self.root / "data/bluestacks.conf"
        self.config_path.parent.mkdir()
        self.config_path.write_bytes(
            (FIXTURES / "bluestacks5_single.conf").read_bytes()
        )
        self.configuration = Conf()
        io = PreflightIO()
        io.host = "windows"
        self.sources = [(str(self.player.parent), str(self.config_path))]
        self.discovery = BlueStacksDiscoveryIO(
            registry_installations=lambda: self.sources, platform="windows"
        )
        self.control = DeviceControl(
            lambda: self.configuration,
            Mock(),
            preflight=PreflightService(io),
            discovery=DiscoveryService(self.discovery),
        )

    def test_single_instance_binds_exact_keyword_and_data_source_without_endpoint(self):
        result = self.control.discover().to_dict()
        self.assertTrue(result["ok"], result["error"])
        candidate = result["candidates"][0]
        self.assertEqual(result["selected_key"], candidate["key"])
        self.configuration = self.configuration.updated(
            {"device": candidate["binding"]}
        )
        self.assertEqual(self.configuration.device.instance_id, "Pie64")
        self.assertEqual(self.configuration.device.instance_name, "日常号")
        self.assertEqual(self.configuration.device.config_path, str(self.config_path))
        self.assertEqual(self.configuration.device.last_serial, "")

    def test_multiple_instances_require_selection_and_keep_keyword_when_reordered(self):
        content = (FIXTURES / "bluestacks5_multiple.conf").read_text(encoding="utf-8")
        self.config_path.write_text(content, encoding="utf-8")
        result = self.control.discover().to_dict()
        self.assertIsNone(result["selected_key"])
        self.assertEqual(result["status"], "selection_required")
        chosen = result["candidates"][1]
        self.assertEqual(chosen["instance_id"], "Pie64_2")
        self.configuration = self.configuration.updated({"device": chosen["binding"]})
        self.config_path.write_text(
            "\n".join(reversed(content.splitlines())), encoding="utf-8"
        )
        refreshed = self.control.discover().to_dict()
        self.assertIsNone(refreshed["selected_key"])
        self.assertEqual(refreshed["candidates"][0]["binding"], chosen["binding"])
        self.assertEqual(refreshed["candidates"][0]["key"], chosen["key"])

    def test_missing_config_and_invalid_fields_return_repair_without_candidates(self):
        original = self.config_path.read_text(encoding="utf-8")
        for content in (
            "not a BlueStacks configuration",
            original + original,
            original.replace("Pie64", "../Pie64"),
            original.replace('display_name="日常号"', 'display_name=""'),
            "x" * (1024 * 1024 + 1),
        ):
            with self.subTest(content=content[:40]):
                self.config_path.write_text(content, encoding="utf-8")
                result = self.control.discover().to_dict()
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"]["code"], "config_invalid")
                self.assertEqual(result["error"]["fields"], ["config_path"])
                self.assertEqual(result["candidates"], [])
        self.config_path.unlink()
        self.assertEqual(self.control.discover().error.code, "missing_config")

    def test_missing_program_and_permission_errors_are_not_valid_installations(self):
        self.player.unlink()
        self.assertEqual(self.control.discover().error.code, "missing_installation")
        self.player.touch()
        with patch.object(Path, "open", side_effect=PermissionError("denied")):
            result = self.control.discover()
        self.assertEqual(result.error.code, "discovery_permission")
        self.assertEqual(result.candidates, [])

    def test_same_program_with_distinct_data_sources_never_has_the_same_candidate_key(
        self,
    ):
        alternate = self.root / "other-data/bluestacks.conf"
        alternate.parent.mkdir()
        alternate.write_bytes(self.config_path.read_bytes())
        self.sources.append((str(self.player.parent), str(alternate)))
        result = self.control.discover()
        self.assertIsNone(result.selected_key)
        self.assertEqual(len({item["key"] for item in result.candidates}), 2)

    def test_non_windows_does_not_read_product_sources(self):
        source = Mock(side_effect=AssertionError("unexpected registry access"))
        discovery = DiscoveryService(
            BlueStacksDiscoveryIO(registry_installations=source, platform="other")
        )
        self.assertEqual(
            discovery.discover(self.configuration.device, "linux").error.code,
            "discovery_unavailable",
        )
        source.assert_not_called()


if __name__ == "__main__":
    unittest.main()
