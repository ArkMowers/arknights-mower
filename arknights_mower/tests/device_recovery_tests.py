"""统一连接入口的调用链回归：使用真实恢复/ADB 选择/scrcpy 启动逻辑，替换外部 I/O。"""

import unittest
from threading import Event
from unittest.mock import MagicMock, call, patch

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.core import Client as ADBClient
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.recovery import (
    DeviceRecoveryError,
    recover_connection,
)


def disconnected_device():
    device = object.__new__(Device)
    device.device_id = None
    device.connect = None
    device.client = None
    device.control = None
    device._recovery_active = False
    device._recovery_error = None
    return device


class TestRecoveryPolicy(unittest.TestCase):
    def setUp(self):
        self.stop = Event()
        self.enterContext(patch.object(config, "stop_mower", self.stop))
        self.restart = self.enterContext(
            patch(
                "arknights_mower.utils.device.recovery.restart_simulator",
                return_value=True,
            )
        )
        self.sleep = self.enterContext(
            patch("arknights_mower.utils.device.recovery.csleep")
        )
        self.device = disconnected_device()
        self.device._connect_once = MagicMock()

    def test_third_reconnection_is_verified_before_restart(self):
        self.device._connect_once.side_effect = [ConnectionError("offline")] * 2 + [
            None
        ]
        operation = MagicMock(side_effect=[ConnectionError("closed"), "ok"])
        self.assertEqual(self.device.recover(operation), "ok")
        self.assertEqual(operation.call_count, 2)
        self.assertEqual(self.device._connect_once.call_count, 3)
        self.restart.assert_not_called()
        self.assertFalse(self.device._recovery_active)

    def test_failed_verification_counts_towards_same_three_attempts(self):
        operation = MagicMock(side_effect=[ConnectionError("closed")] * 3 + ["ok"])
        self.assertEqual(self.device.recover(operation), "ok")
        self.assertEqual(self.device._connect_once.call_count, 3)
        self.restart.assert_not_called()

    def test_last_restart_also_gets_a_full_connection_group(self):
        connect = MagicMock(side_effect=[ConnectionError("offline")] * 8 + ["ok"])
        self.assertEqual(recover_connection(connect), "ok")
        self.assertEqual(connect.call_count, 9)
        self.assertEqual(self.restart.call_count, 2)
        self.assertEqual(self.sleep.call_count, 6)

    def test_failed_reconnection_never_repeats_operation(self):
        self.device._connect_once.side_effect = ConnectionError("offline")
        operation = MagicMock(side_effect=ConnectionError("closed"))
        with self.assertRaises(DeviceRecoveryError):
            self.device.recover(operation, restarts=0)
        operation.assert_called_once_with()
        self.assertEqual(self.device._connect_once.call_count, 3)
        self.sleep.assert_has_calls([call(1), call(1)])
        self.assertEqual(self.sleep.call_count, 2)
        self.restart.assert_not_called()

    def test_nested_run_has_one_recovery_budget(self):
        self.device.client = MagicMock()
        self.device.client.run.side_effect = ConnectionError("closed")
        with self.assertRaises(DeviceRecoveryError):
            self.device.recover(lambda: self.device.run("screencap"), restarts=0)
        self.assertEqual(self.device.client.run.call_count, 4)
        self.assertEqual(self.device._connect_once.call_count, 3)
        self.restart.assert_not_called()

    def test_exhausted_device_cannot_be_recovered_again_by_outer_handlers(self):
        self.device._connect_once.side_effect = ConnectionError("offline")
        operation = MagicMock(side_effect=ConnectionError("closed"))
        with self.assertRaises(DeviceRecoveryError) as initial:
            self.device.recover(operation, restarts=0)
        for retry in (lambda: self.device.recover(operation), self.device.reconnect):
            with self.assertRaises(DeviceRecoveryError) as repeated:
                retry()
            self.assertIs(repeated.exception, initial.exception)
        self.assertEqual(self.device._connect_once.call_count, 3)
        operation.assert_called_once_with()
        self.restart.assert_not_called()

    def test_failed_restart_stops_without_new_connections(self):
        self.restart.return_value = False
        connect = MagicMock(side_effect=ConnectionError("offline"))
        with self.assertRaisesRegex(DeviceRecoveryError, "模拟器重启失败"):
            recover_connection(connect)
        self.assertEqual(connect.call_count, 3)
        self.restart.assert_called_once_with()

    def test_stop_before_operation_skips_all_device_access(self):
        self.stop.set()
        operation = MagicMock()
        for action in (lambda: self.device.recover(operation), self.device.reconnect):
            with self.assertRaises(MowerExit):
                action()
        operation.assert_not_called()
        self.device._connect_once.assert_not_called()
        self.restart.assert_not_called()

    def test_stop_after_failed_attempt_skips_wait_and_restart(self):
        def fail(**kwargs):
            self.stop.set()
            raise ConnectionError("closed")

        connect = MagicMock(side_effect=fail)
        with self.assertRaises(MowerExit):
            recover_connection(connect, first_attempts=1)
        connect.assert_called_once_with(wait_for_device=True)
        self.sleep.assert_not_called()
        self.restart.assert_not_called()

    def test_stop_between_attempts_skips_next_attempt(self):
        self.sleep.side_effect = MowerExit
        connect = MagicMock(side_effect=ConnectionError("offline"))
        with self.assertRaises(MowerExit):
            recover_connection(connect)
        connect.assert_called_once_with(wait_for_device=True)
        self.restart.assert_not_called()

    def test_background_check_propagates_terminal_and_stop_errors(self):
        for error in (MowerExit(), DeviceRecoveryError("exhausted")):
            with (
                self.subTest(error=type(error)),
                patch.object(self.device, "run", side_effect=error),
            ):
                with self.assertRaises(type(error)):
                    self.device.is_app_running_in_background()


class TestDeviceConnectionChain(unittest.TestCase):
    TARGET = "127.0.0.1:16928"

    def setUp(self):
        self.stop = Event()
        self.enterContext(patch.object(config, "stop_mower", self.stop))
        self.enterContext(patch.object(config.conf, "adb", self.TARGET))
        self.enterContext(patch.object(config.conf.simulator, "wait_time", 4))
        self.enterContext(patch.object(config.conf, "touch_method", "scrcpy"))
        self.enterContext(patch.object(config.conf, "mumu12IPC", False))
        self.enterContext(patch.object(config.conf.droidcast, "enable", False))
        self.enterContext(patch.object(config.droidcast, "process", None))
        self.register = self.enterContext(
            patch("arknights_mower.utils.device.device.atexit.register")
        )
        self.enterContext(
            patch.object(ADBClient, "_Client__check_adb", return_value=True)
        )
        self.enterContext(patch.object(ADBClient, "_Client__exec"))
        self.enterContext(
            patch(
                "arknights_mower.utils.device.adb_client.core.query_mumu_adb_port",
                return_value=None,
            )
        )
        self.session = self.enterContext(
            patch("arknights_mower.utils.device.adb_client.core.Session")
        ).return_value
        self.session.devices_list.return_value = [(self.TARGET, "device")]
        self.enterContext(patch("arknights_mower.utils.device.adb_client.core.csleep"))
        self.scrcpy_sleep = self.enterContext(
            patch("arknights_mower.utils.device.scrcpy.core.csleep")
        )
        self.retry_sleep = self.enterContext(
            patch("arknights_mower.utils.device.recovery.csleep")
        )
        self.restart = self.enterContext(
            patch(
                "arknights_mower.utils.device.recovery.restart_simulator",
                return_value=True,
            )
        )
        self.push = self.enterContext(patch.object(ADBClient, "push"))
        self.shell = self.enterContext(
            patch.object(
                ADBClient, "cmd_shell", return_value="Physical size: 1920x1080"
            )
        )
        self.servers = []

        def server_stream(*args):
            stream = MagicMock()
            stream.recv.return_value = b"[server] started"
            self.servers.append(stream)
            return stream

        self.server = self.enterContext(
            patch.object(ADBClient, "stream_shell", side_effect=server_stream)
        )
        self.stream = self.enterContext(
            patch.object(
                ADBClient, "stream", side_effect=ConnectionError("scrcpy unavailable")
            )
        )

    def test_offline_missing_unauthorized_or_wrong_device_never_initializes_services(
        self,
    ):
        for devices in (
            [],
            [(self.TARGET, "offline")],
            [(self.TARGET, "unauthorized")],
            [("127.0.0.1:16416", "device")],
        ):
            for wait in (False, True):
                with (
                    self.subTest(devices=devices, wait=wait),
                    patch.object(config.conf.droidcast, "enable", True),
                    patch.object(Device, "start_droidcast") as droidcast,
                    patch("arknights_mower.utils.device.device.Scrcpy") as scrcpy,
                    patch("arknights_mower.utils.device.device.MuMu12IPC") as ipc,
                ):
                    self.session.devices_list.return_value = devices
                    with self.assertRaisesRegex(
                        RuntimeError, "Device connection failure"
                    ):
                        Device(wait_for_device=wait)
                    droidcast.assert_not_called()
                    scrcpy.assert_not_called()
                    ipc.assert_not_called()
        self.shell.assert_not_called()
        self.push.assert_not_called()
        self.register.assert_not_called()

    def test_runtime_adb_failure_stops_old_control_without_starting_scrcpy(self):
        device = disconnected_device()
        device.client = ADBClient(adb_bin="adb", wait_for_device=False)
        old_control = MagicMock()
        old_control.mumu12IPC = None
        device.control = old_control
        self.session.devices_list.return_value = [(self.TARGET, "offline")]
        with self.assertRaises(DeviceRecoveryError):
            device.reconnect(restarts=0)
        self.assertIsNone(device.control)
        old_control.scrcpy.stop.assert_called_once_with()
        self.push.assert_not_called()
        self.server.assert_not_called()
        self.restart.assert_not_called()

    def test_three_reconnections_start_scrcpy_three_times_not_nine(self):
        device = disconnected_device()
        with self.assertRaises(DeviceRecoveryError):
            device.reconnect(restarts=0)
        self.assertEqual(self.push.call_count, 3)
        self.assertEqual(self.stream.call_count, 3)
        self.assertEqual(len(self.servers), 3)
        for server in self.servers:
            server.close.assert_called_once_with()
        self.assertEqual(self.scrcpy_sleep.call_args_list, [call(0), call(0.5)] * 3)
        self.assertEqual(self.retry_sleep.call_args_list, [call(1), call(1)])
        self.restart.assert_not_called()
        self.assertIsNone(device.control)

    def test_solver_initializes_scrcpy_only_once(self):
        from arknights_mower.utils.solver import BaseSolver

        video, control = MagicMock(), MagicMock()
        video.recv.side_effect = [b"\x00", b"emulator", b"\x07\x80\x04\x38"]
        self.stream.side_effect = [video, control]
        with patch("arknights_mower.utils.solver.Recognizer"):
            solver = BaseSolver(connection_retries=1)
        self.addCleanup(solver.device.close)
        self.assertEqual(solver.device.control.scrcpy.device_name, "emulator")
        self.push.assert_called_once()
        self.assertEqual(self.stream.call_count, 2)
        self.restart.assert_not_called()
        self.register.assert_called_once()

    def test_droidcast_must_succeed_before_touch_and_recognition(self):
        from arknights_mower.utils.solver import BaseSolver

        video, control = MagicMock(), MagicMock()
        video.recv.side_effect = [b"\x00", b"emulator", b"\x07\x80\x04\x38"]
        self.stream.side_effect = [video, control]
        actions = MagicMock()
        with (
            patch.object(config.conf.droidcast, "enable", True),
            patch.object(
                Device, "start_droidcast", side_effect=[False, False, True]
            ) as droidcast,
            patch("arknights_mower.utils.solver.Recognizer") as recog,
        ):
            actions.attach_mock(droidcast, "droidcast")
            actions.attach_mock(self.push, "push")
            actions.attach_mock(recog, "recognize")
            solver = BaseSolver()
        self.addCleanup(solver.device.close)
        self.assertEqual(
            [action[0] for action in actions.mock_calls],
            ["droidcast"] * 3 + ["push", "recognize"],
        )
        self.restart.assert_not_called()

    def test_failed_droidcast_never_starts_touch_service(self):
        with (
            patch.object(config.conf.droidcast, "enable", True),
            patch.object(Device, "start_droidcast", return_value=False) as droidcast,
            self.assertRaises(DeviceRecoveryError) as raised,
        ):
            disconnected_device().reconnect(restarts=0)
        self.assertEqual(droidcast.call_count, 3)
        self.assertEqual(str(raised.exception.__cause__), "DroidCast启动失败")
        self.push.assert_not_called()
        self.restart.assert_not_called()

    def test_stop_during_scrcpy_start_closes_stream_without_retry(self):
        self.scrcpy_sleep.side_effect = [None, MowerExit()]
        with self.assertRaises(MowerExit):
            Device.create()
        self.push.assert_called_once()
        self.servers[0].close.assert_called_once_with()
        self.stream.assert_not_called()
        self.retry_sleep.assert_not_called()
        self.restart.assert_not_called()
        self.register.assert_not_called()

    def test_service_failure_cleans_up_droidcast_process(self):
        process = MagicMock()

        def start_droidcast(device):
            config.droidcast.process = process
            return True

        with (
            patch.object(config.conf.droidcast, "enable", True),
            patch.object(Device, "start_droidcast", start_droidcast),
            self.assertRaisesRegex(ConnectionError, "scrcpy unavailable"),
        ):
            Device()
        process.terminate.assert_called_once_with()
        self.assertIsNone(config.droidcast.process)
        self.register.assert_not_called()

    def test_resolution_failure_does_not_start_scrcpy_or_restart(self):
        self.shell.return_value = "Physical size: 1280x720"
        with self.assertRaises(MowerExit):
            Device.create()
        self.push.assert_not_called()
        self.restart.assert_not_called()

    def test_ipc_stays_lazy_and_adb_reconnect_preserves_its_instance(self):
        with (
            patch.object(config.conf, "mumu12IPC", True),
            patch("arknights_mower.utils.device.device.MuMu12IPC") as ipc,
            patch.object(Device, "check_current_focus") as focus,
        ):
            device = Device(wait_for_device=False)
            self.addCleanup(device.close)
            original_control = device.control
            device.reconnect(restarts=0)
            device.close()
            self.assertIs(device.control, original_control)
            self.assertIs(device.control.mumu12IPC, ipc.return_value)
            ipc.assert_called_once_with(device)
            self.assertEqual(ipc.return_value.mock_calls, [])
            focus.assert_not_called()
        self.push.assert_not_called()
        self.restart.assert_not_called()

    def test_ipc_inputs_keep_their_existing_recovery(self):
        device = disconnected_device()
        with (
            patch.object(config.conf, "mumu12IPC", True),
            patch("arknights_mower.utils.device.device.MuMu12IPC") as ipc,
            patch.object(device, "recover") as recover,
        ):
            device.control = Device.Control(device)
            ipc.return_value.tap.side_effect = RuntimeError("IPC input failure")
            ipc.return_value.swipe.side_effect = RuntimeError("IPC input failure")
            operations = (
                lambda: device.tap((1, 2)),
                lambda: device.swipe((1, 2), (3, 4)),
                lambda: device.swipe_ext([(1, 2), (3, 4)], [100]),
            )
            for operation in operations:
                with self.assertRaisesRegex(RuntimeError, "IPC input failure"):
                    operation()
            recover.assert_not_called()
            ipc.return_value.tap.assert_called_once_with(1, 2)
            self.assertEqual(ipc.return_value.swipe.call_count, 2)
        self.restart.assert_not_called()


if __name__ == "__main__":
    unittest.main()
