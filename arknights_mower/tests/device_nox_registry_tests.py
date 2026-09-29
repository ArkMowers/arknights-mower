"""Modeled registry values exercised through application discovery, not live captures."""

import subprocess
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.nox_discovery import NoxDiscoveryIO
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
        expected = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" + "\\"
        if not path.startswith(expected):
            raise FileNotFoundError(path)
        key = (hive, access, path[len(expected) :])
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


class NoxRegistryDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.installation = self.root / "Custom Nox" / "bin"
        self.installation.mkdir(parents=True)
        self.manager = self.installation / "NoxConsole.exe"
        self.manager.touch()
        vm = self.installation / "BignoxVMS/Nox_2/Nox_2.vbox"
        vm.parent.mkdir(parents=True)
        vm.write_bytes((FIXTURES / "nox_vm.vbox").read_bytes())
        self.registry = RegistryFixture()
        self.enterContext(patch.dict("sys.modules", {"winreg": self.registry}))
        io = PreflightIO()
        io.host = "windows"
        self.run = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, (FIXTURES / "nox_single.txt").read_bytes(), b""
            )
        )
        self.control = DeviceControl(
            Conf,
            Mock(),
            preflight=PreflightService(io),
            discovery=DiscoveryService(
                NoxDiscoveryIO(
                    run=self.run,
                    process_paths=lambda: [],
                    fixed_paths=lambda: [],
                    platform="windows",
                )
            ),
        )

    def register(self, values, name="Nox", hive=1, view=8):
        self.registry.entries = {(hive, self.registry.KEY_READ | view, name): values}

    def test_uninstall_strings_find_only_the_verified_neighbor_installation(self):
        # Synthetic examples model quoting, spaces and ignored arguments.
        executable = self.installation / "uninstall" / "Nox_unload.exe"
        for name, command in (
            ("Nox", f'"{executable}" /S /D="C:/do not execute"'),
            ("Nox64", f"{executable} /S & arbitrary-command"),
        ):
            with self.subTest(name=name):
                self.register({"UninstallString": command}, name=name)
                result = self.control.discover().to_dict()
                self.assertTrue(result["ok"], result["error"])
                self.assertEqual(len(result["candidates"]), 1)
                binding = result["candidates"][0]["binding"]
                self.assertEqual(Path(binding["manager_path"]), self.manager)
                self.assertEqual(binding["instance_id"], "Nox_2")
                self.assertEqual(binding["last_serial"], "")

    def test_install_location_takes_priority_in_both_hives_and_registry_views(self):
        for hive in (1, 2):
            for view in (8, 16):
                with self.subTest(hive=hive, view=view):
                    self.register(
                        {
                            "InstallLocation": str(self.installation),
                            "UninstallString": PermissionError(
                                "must not read fallback"
                            ),
                        },
                        hive=hive,
                        view=view,
                    )
                    result = self.control.discover().to_dict()
                    self.assertTrue(result["ok"], result["error"])
                    self.assertEqual(len(result["candidates"]), 1)

    def test_empty_install_location_uses_uninstall_executable_neighbor(self):
        self.register(
            {
                "InstallLocation": " ",
                "UninstallString": f'"{self.installation / "Nox_unload.exe"}"',
            }
        )
        self.assertTrue(self.control.discover().ok)

    def test_similar_registry_names_do_not_supply_installations(self):
        self.register({"InstallLocation": str(self.installation)}, name="NoxBeta")
        result = self.control.discover().to_dict()
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"]["code"], "missing_installation")
        self.assertEqual(result["error"]["fields"], ["installation_path"])

    def test_invalid_or_stale_uninstall_strings_return_repair_without_running(self):
        for command in (
            "",
            "Nox_unload.exe /S",
            '"unterminated.exe /S',
            123,
            f'"{self.root / "missing/Nox_unload.exe"}" {self.manager}',
            f'"{self.manager}"\nsecond-command.exe',
        ):
            with self.subTest(command=command):
                self.register({"UninstallString": command})
                result = self.control.discover().to_dict()
                self.assertFalse(result["ok"])
                self.assertEqual(result["candidates"], [])
                self.assertEqual(result["error"]["code"], "manager_output")
                self.assertTrue(result["error"]["fields"])
        self.run.assert_not_called()

    def test_registry_access_denied_keeps_manual_repair(self):
        for values in (
            PermissionError("entry denied"),
            {"InstallLocation": PermissionError("location denied")},
            {"UninstallString": PermissionError("uninstall denied")},
        ):
            with self.subTest(values=values):
                self.register(values)
                result = self.control.discover().to_dict()
                self.assertFalse(result["ok"])
                self.assertEqual(result["candidates"], [])
                self.assertEqual(result["error"]["code"], "discovery_permission")
                self.assertEqual(result["error"]["fields"], ["installation_path"])
        self.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
