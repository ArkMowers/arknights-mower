"""Idle shutdown selects the same verified lifecycle adapter on every host."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl, PreflightRejected
from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.session_io import ProductionSimulator


class IdleLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.conf = Conf(
            close_simulator_when_idle=True,
            device={
                "preset_id": "windows.mumu12",
                "instance_id": "1",
                "manager_path": "selected-manager",
                "last_serial": "127.0.0.1:16416",
            },
        )
        self.simulator = Mock()
        self.simulator.stop.return_value = True
        self.control = DeviceControl(
            lambda: self.conf,
            Mock(),
            session=SimpleNamespace(simulator=self.simulator),
        )
        self.enterContext(
            patch(
                "arknights_mower.utils.device.application.is_android_runtime",
                return_value=False,
                create=True,
            )
        )

    def test_desktop_presets_share_authoritative_profile_and_stop_adapter(self):
        for preset in (
            "windows.mumu12",
            "windows.ldplayer9",
            "windows.ldplayer14",
            "windows.nox",
            "macos.mumu_pro",
            "linux.waydroid",
            "linux.redroid",
            "linux.genymotion",
        ):
            with self.subTest(preset=preset):
                self.conf.device.preset_id = preset
                self.conf.device.topology_fingerprint = "a" * 64
                self.simulator.reset_mock()
                before = self.conf.model_dump()

                self.assertTrue(self.control.stop_bound_simulator())

                self.simulator.stop.assert_called_once_with(self.conf.device, 10)
                self.assertEqual(self.conf.model_dump(), before)

    def test_disabled_idle_policy_and_physical_devices_never_stop(self):
        self.conf.close_simulator_when_idle = False
        self.assertFalse(self.control.stop_bound_simulator())
        self.conf.close_simulator_when_idle = True
        self.conf.device.preset_id = "manual.physical"
        self.assertFalse(self.control.stop_bound_simulator())
        self.simulator.stop.assert_not_called()

    def test_android_never_executes_desktop_lifecycle_control(self):
        with patch(
            "arknights_mower.utils.device.application.is_android_runtime",
            return_value=True,
        ):
            self.assertFalse(self.control.stop_bound_simulator())
        self.simulator.stop.assert_not_called()

    def test_shutdown_and_pending_close_never_stop_instance(self):
        for cancellation in (self.control._shutdown, self.control._pending_close):
            with self.subTest(cancellation=cancellation):
                cancellation.set()
                self.assertFalse(self.control.stop_bound_simulator())
                cancellation.clear()
        self.simulator.stop.assert_not_called()

    def test_unverified_mumu_pro_never_stops(self):
        self.conf.device.preset_id = "macos.mumu_pro"
        self.assertFalse(self.control.stop_bound_simulator())
        self.simulator.stop.assert_not_called()

    def test_changed_binding_stops_dispatch_with_classified_verdict(self):
        failure = InstanceBindingError("binding_changed", "所选实例身份已改变")
        self.simulator.stop.side_effect = failure
        before = self.conf.model_dump()

        with self.assertRaises(PreflightRejected) as raised:
            self.control.stop_bound_simulator()

        self.assertEqual(raised.exception.code, "binding_changed")
        self.assertIs(raised.exception.__cause__, failure)
        self.assertEqual(self.conf.model_dump(), before)
        self.simulator.stop.assert_called_once_with(self.conf.device, 10)

    def test_avd_stop_keeps_owned_instance_restriction(self):
        avd = Mock()
        self.control._avd = avd
        avd.stop_owned.return_value = False
        for preset in ("macos.avd", "linux.avd"):
            with self.subTest(preset=preset):
                self.conf.device.preset_id = preset
                avd.reset_mock()

                self.assertFalse(self.control.stop_bound_simulator())

                avd.stop_owned.assert_called_once_with(self.conf.device, 10)
                avd.stop.assert_not_called()
        self.simulator.stop.assert_not_called()

    def test_owned_avd_binding_failure_uses_same_classified_stop_boundary(self):
        self.conf.device.preset_id = "macos.avd"
        self.control._avd = Mock()
        self.control._avd.stop_owned.side_effect = InstanceBindingError(
            "avd_binding_changed", "所选 AVD 身份已改变"
        )

        with self.assertRaises(PreflightRejected) as raised:
            self.control.stop_bound_simulator()

        self.assertEqual(raised.exception.code, "avd_binding_changed")
        self.simulator.stop.assert_not_called()

    def test_missing_session_or_failed_stop_does_not_report_success(self):
        self.control._session = None
        self.assertFalse(self.control.stop_bound_simulator())
        self.control._session = SimpleNamespace(simulator=self.simulator)
        self.simulator.stop.return_value = False
        self.assertFalse(self.control.stop_bound_simulator())

    def test_unsupported_presets_do_not_execute_any_manager_command(self):
        run = Mock(side_effect=AssertionError("unsupported lifecycle"))
        self.control._session = SimpleNamespace(simulator=ProductionSimulator(run=run))
        for preset in ("windows.bluestacks5", "macos.bluestacks_air", "manual.other"):
            with self.subTest(preset=preset):
                self.conf.device.preset_id = preset
                self.assertFalse(self.control.stop_bound_simulator())
        run.assert_not_called()

    def test_mumu_stop_uses_selected_manager_not_legacy_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = Path(directory) / "MuMuManager.exe"
            manager.touch()
            self.conf.device.manager_path = str(manager)
            self.conf.simulator.simulator_folder = "missing-legacy-folder"
            self.conf.simulator.index = "9"
            run = Mock(
                side_effect=[
                    subprocess.CompletedProcess(
                        [],
                        0,
                        b'{"1":{"index":1,"name":"chosen","is_process_started":true,"is_android_started":true,"adb_port":16416}}',
                        b"",
                    ),
                    subprocess.CompletedProcess([], 0, b'{"code":0}', b""),
                ]
            )
            self.control._session = SimpleNamespace(
                simulator=ProductionSimulator(run=run)
            )
            before = self.conf.model_dump()

            self.assertTrue(self.control.stop_bound_simulator())

            self.assertEqual(run.call_count, 2)
            self.assertEqual(
                run.call_args_list[0].args[0],
                [str(manager.resolve()), "info", "-v", "1"],
            )
            self.assertEqual(
                run.call_args.args[0],
                [str(manager.resolve()), "api", "-v", "1", "shutdown_player"],
            )
            self.assertLessEqual(run.call_args.kwargs["timeout"], 10)
            self.assertEqual(self.conf.model_dump(), before)
