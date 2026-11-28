"""Nox fixture behavior at the device-control application boundary."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.nox_discovery import NoxDiscoveryIO
from arknights_mower.utils.device.preflight import PreflightService

FIXTURES = Path(__file__).parent / "fixtures"
VM_UUID = "5e1aaadc-7991-419d-a2b6-f030b497b282"


class NoxDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = self.root / "NoxConsole.exe"
        self.manager.touch()
        self.configuration = Conf()
        self.listing = (FIXTURES / "nox_single.txt").read_bytes()
        self.vm = self.root / "BignoxVMS/Nox_2/Nox_2.vbox"
        self.vm.parent.mkdir(parents=True)
        self.vm.write_bytes((FIXTURES / "nox_vm.vbox").read_bytes())
        io = PreflightIO()
        io.host = "windows"
        self.sources = [str(self.root)]
        self.run = Mock(side_effect=self.command)
        self.control = DeviceControl(
            lambda: self.configuration,
            Mock(),
            preflight=PreflightService(io),
            discovery=DiscoveryService(
                NoxDiscoveryIO(
                    run=self.run,
                    registry_paths=lambda: self.sources,
                    process_paths=lambda: [],
                    fixed_paths=lambda: [],
                    platform="windows",
                )
            ),
        )

    def command(self, argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, self.listing, b"")

    def test_single_vm_saves_vendor_identity_and_name_without_a_guessed_endpoint(self):
        result = self.control.discover().to_dict()
        self.assertTrue(result["ok"], result["error"])
        candidate = result["candidates"][0]
        self.assertEqual(result["selected_key"], candidate["key"])
        self.configuration = self.configuration.updated(
            {"device": candidate["binding"]}
        )
        profile = self.configuration.device
        self.assertEqual(
            (profile.instance_id, profile.instance_name), ("Nox_2", "日常号")
        )
        self.assertEqual(profile.instance_uuid, VM_UUID)
        self.assertTrue(profile.topology_fingerprint)
        self.assertEqual(profile.last_serial, "")

    def test_multiple_reordered_vms_keep_identity_but_topology_change_requires_selection(
        self,
    ):
        self.listing = (FIXTURES / "nox_multiple.txt").read_bytes()
        other = self.root / "BignoxVMS/nox/nox.vbox"
        other.parent.mkdir(parents=True)
        other.write_text(
            self.vm.read_text(encoding="utf-8")
            .replace("Nox_2", "nox")
            .replace(VM_UUID, "e37758fb-810a-482b-939b-9d89e90c5b15"),
            encoding="utf-8",
        )
        first = self.control.discover().to_dict()
        self.assertIsNone(first["selected_key"])
        chosen = first["candidates"][1]
        self.configuration = self.configuration.updated({"device": chosen["binding"]})
        self.listing = b"\n".join(reversed(self.listing.splitlines()))
        reordered = self.control.discover().to_dict()
        self.assertEqual(reordered["candidates"][0]["binding"], chosen["binding"])
        self.listing = (FIXTURES / "nox_single.txt").read_bytes()
        changed = self.control.discover().to_dict()
        self.assertIsNone(changed["selected_key"])
        self.assertEqual(changed["error"]["code"], "topology_changed")
        self.assertEqual(changed["status"], "selection_required")

    def test_modern_list_ignores_index_and_accepts_hex_window_handles(self):
        for listing in (
            "7,Nox_2,日常号,00210D2E,00371542,2732,23876",
            "7,Nox_2,日常号,0,0,0,-1,-1",
        ):
            with self.subTest(listing=listing):
                self.listing = listing.encode()
                result = self.control.discover().to_dict()
                self.assertTrue(result["ok"], result["error"])
                self.assertEqual(result["candidates"][0]["instance_id"], "Nox_2")

    def test_stopped_vm_is_selectable_without_an_endpoint(self):
        self.listing = (FIXTURES / "nox_stopped.txt").read_bytes()
        result = self.control.discover().to_dict()
        self.assertTrue(result["ok"])
        self.assertEqual(result["candidates"][0]["state"], "stopped")
        self.assertEqual(result["candidates"][0]["serial"], "")

    def test_permission_timeout_and_command_failure_keep_manual_repair(self):
        for failure, code in (
            (PermissionError("denied"), "discovery_permission"),
            (subprocess.TimeoutExpired("NoxConsole.exe", 3), "discovery_timeout"),
            (subprocess.CalledProcessError(1, "list"), "manager_output"),
        ):
            with self.subTest(code=code):
                self.run.side_effect = failure
                result = self.control.discover().to_dict()
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"]["code"], code)
                self.assertTrue(result["error"]["fields"])
                self.assertEqual(result["candidates"], [])
        self.run.side_effect = self.command
        with patch.object(Path, "open", side_effect=PermissionError("denied")):
            self.assertEqual(self.control.discover().error.code, "discovery_permission")

    def test_malformed_duplicate_and_oversized_lists_never_partially_bind(self):
        for listing in (
            b"not a VM",
            b'"unterminated',
            self.listing + self.listing,
            b"x" * (1024 * 1024 + 1),
            b"../escape,title,1,2,3,123",
            b"Nox_2,title,0,0,0,banana",
        ):
            with self.subTest(listing=listing[:60]):
                self.listing = listing
                result = self.control.discover().to_dict()
                self.assertEqual(result["error"]["code"], "manager_output")
                self.assertEqual(result["candidates"], [])

    def test_missing_malformed_or_wrong_identity_xml_requires_repair(self):
        original = self.vm.read_text(encoding="utf-8")
        for xml in (
            "<broken",
            original.replace("Nox_2", "nox"),
            original.replace(VM_UUID, "not-uuid"),
            '<!DOCTYPE x [<!ENTITY payload "data">]>' + original,
        ):
            with self.subTest(xml=xml[:60]):
                self.vm.write_text(xml, encoding="utf-8")
                result = self.control.discover().to_dict()
                self.assertEqual(result["error"]["code"], "manager_output")
                self.assertEqual(result["candidates"], [])
        self.vm.unlink()
        self.assertFalse(self.control.discover().ok)


if __name__ == "__main__":
    unittest.main()
