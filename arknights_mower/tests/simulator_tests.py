"""Legacy lifecycle callers delegate startup/recovery to the application."""

import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from arknights_mower.utils import config, simulator
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.recovery import DeviceRecoveryError


class TestSimulatorSessionDelegation(unittest.TestCase):
    def setUp(self):
        self.control = MagicMock()
        self.control.start.return_value.ok = True
        self.control.recover.return_value.ok = True
        self.enterContext(
            patch.dict(
                sys.modules,
                {
                    "arknights_mower.__main__": SimpleNamespace(
                        device_control=self.control
                    )
                },
            )
        )
        self.conf = SimpleNamespace(
            device=SimpleNamespace(preset_id="windows.mumu12"),
            fix_mumu12_adb_disconnect=False,
            simulator=SimpleNamespace(name="MuMu12", index="0", simulator_folder=""),
        )
        self.enterContext(patch.object(config, "conf", self.conf))
        self.command = self.enterContext(
            patch.object(simulator, "run_command", return_value=True)
        )

    def test_start_only_delegates_without_issuing_a_stop(self):
        self.assertTrue(simulator.restart_simulator(stop=False))
        self.control.start.assert_called_once_with()
        self.control.recover.assert_not_called()
        self.command.assert_not_called()

    def test_restart_request_uses_the_session_recovery_budget(self):
        self.assertTrue(simulator.restart_simulator())
        self.control.recover.assert_called_once_with()
        self.control.start.assert_not_called()
        self.command.assert_not_called()

    def test_exhausted_session_error_reaches_the_caller(self):
        self.control.recover.return_value.unwrap.side_effect = DeviceRecoveryError(
            "shared budget exhausted"
        )
        with self.assertRaisesRegex(DeviceRecoveryError, "shared budget exhausted"):
            simulator.restart_simulator()
        self.command.assert_not_called()

    def test_explicit_idle_stop_remains_stop_only(self):
        self.assertTrue(simulator.restart_simulator(start=False))
        self.command.assert_called_once_with(
            ["MuMuManager.exe", "api", "-v", "0", "shutdown_player"], "", 10, True
        )
        self.control.start.assert_not_called()
        self.control.recover.assert_not_called()

    def test_physical_devices_never_receive_simulator_commands(self):
        self.conf.device.preset_id = "manual.physical"
        self.assertFalse(simulator.restart_simulator())
        self.assertFalse(simulator.restart_simulator(start=False))
        self.command.assert_not_called()
        self.control.recover.assert_not_called()

    def test_failed_stop_is_not_reported_as_success(self):
        self.command.return_value = False
        self.assertFalse(simulator.restart_simulator(start=False))

    def test_mumu_pro_idle_stop_never_uses_unverified_manager_command(self):
        self.conf.device.preset_id = "macos.mumu_pro"
        self.conf.simulator.name = "MuMuPro"
        self.assertFalse(simulator.restart_simulator(start=False))
        self.command.assert_not_called()


class TestMuMuTransportCleanup(unittest.TestCase):
    def setUp(self):
        self.conf = SimpleNamespace(
            adb="127.0.0.1:16384",
            maa_adb_path="saved-adb.exe",
            device=SimpleNamespace(preset_id="windows.mumu12"),
            fix_mumu12_adb_disconnect=True,
            simulator=SimpleNamespace(name="MuMu12", index="0", simulator_folder=""),
        )
        self.enterContext(patch.object(config, "conf", self.conf))
        self.device = SimpleNamespace(
            device_id="127.0.0.1:16416",
            client=SimpleNamespace(
                device_id="127.0.0.1:16416", adb_bin="verified-adb.exe"
            ),
        )
        self.device.close = lambda: setattr(self.device, "client", None)
        self.control = DeviceControl(
            lambda: self.conf,
            SimpleNamespace(open=lambda *_args, **_kwargs: self.device),
        )
        self.control.start().unwrap()
        self.addCleanup(self.control.close)
        self.enterContext(
            patch.dict(
                sys.modules,
                {
                    "arknights_mower.__main__": SimpleNamespace(
                        device_control=self.control
                    )
                },
            )
        )
        self.stop = self.enterContext(
            patch.object(simulator, "run_command", return_value=True)
        )
        self.disconnect = self.enterContext(patch.object(simulator, "run_adb"))

    def test_idle_stop_disconnects_only_the_verified_runtime_endpoint(self):
        self.assertTrue(simulator.restart_simulator(start=False))

        self.stop.assert_called_once()
        self.disconnect.assert_called_once()
        self.assertEqual(
            self.disconnect.call_args.args[0],
            ["verified-adb.exe", "disconnect", "127.0.0.1:16416"],
        )
        self.assertEqual(self.conf.adb, "127.0.0.1:16384")
        self.assertEqual(self.conf.maa_adb_path, "saved-adb.exe")

    def test_closed_session_never_disconnects_the_saved_endpoint(self):
        self.control.close()

        self.assertTrue(simulator.restart_simulator(start=False))

        self.disconnect.assert_not_called()

    def test_released_client_never_disconnects_the_saved_endpoint(self):
        self.device.close()

        self.assertTrue(simulator.restart_simulator(start=False))

        self.disconnect.assert_not_called()

    def test_failed_disconnect_does_not_recover_the_stopped_instance(self):
        self.disconnect.side_effect = subprocess.TimeoutExpired("adb", 5)
        with patch.object(self.control, "recover") as recover:
            self.assertTrue(simulator.restart_simulator(start=False))
        recover.assert_not_called()


if __name__ == "__main__":
    unittest.main()
