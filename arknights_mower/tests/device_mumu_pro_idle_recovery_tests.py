"""MuMu Pro idle wake tolerates delayed ADB readiness within one budget."""

import unittest
from unittest.mock import Mock, patch

from arknights_mower.tests.device_session_tests import ADB, Clock, Simulator
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.session import (
    DeviceSession,
    RecoveryPolicy,
    SessionFailure,
)


class MuMuProIdleRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("arknights_mower.utils.device.session.logger"))
        self.clock = Clock()
        self.adb = ADB()
        self.simulator = Simulator()
        self.simulator.state = "stopped"
        self.serial = "127.0.0.1:16448"
        self.other_serial = "127.0.0.1:16384"
        self.profile = DeviceProfile(
            preset_id="macos.mumu_pro",
            instance_id="2",
            topology_fingerprint="a" * 64,
            last_serial="127.0.0.1:16416",
        )
        self.adb.rows = [(self.other_serial, "device"), (self.serial, "offline")]
        self.simulator.on_start = self.started
        self.session = DeviceSession(
            self.adb,
            self.simulator,
            clock=self.clock,
            policy=RecoveryPolicy(
                timeout=60, attempts=3, local_wait=10, poll_interval=1
            ),
        )
        self.session.bind(self.profile)

    def started(self):
        self.simulator.state = "running"
        self.simulator.serial = self.serial

    def ready(self):
        self.adb.rows = [(self.other_serial, "device"), (self.serial, "device")]
        self.adb.boot = "1"

    def test_first_reconnect_failure_retries_only_selected_instance(self):
        def reconnect(adb_path, serial, timeout):
            self.adb.actions.append(serial)
            self.clock.sleep(10)
            if len(self.adb.actions) == 1:
                return False
            self.ready()
            return True

        self.adb.recover = reconnect
        result = self.session.ensure_ready()
        self.assertEqual(result.serial, self.serial)
        self.assertEqual(self.simulator.actions, ["start"])
        self.assertEqual(self.adb.actions, [self.serial, self.serial])
        self.assertEqual(self.session.actions, 3)
        self.assertGreaterEqual(self.clock.now, 30)
        self.assertLess(self.clock.now, 60)
        self.assertEqual(self.profile.last_serial, "127.0.0.1:16416")

    def test_failed_reconnect_can_become_ready_during_local_wait(self):
        self.adb.recover = Mock(return_value=False)
        original_devices = self.adb.devices

        def devices(adb_path, timeout):
            if self.clock.now >= 4:
                self.ready()
            return original_devices(adb_path, timeout)

        self.adb.devices = devices
        self.assertEqual(self.session.ensure_ready().serial, self.serial)
        self.adb.recover.assert_called_once()
        self.assertEqual(self.simulator.actions, ["start"])
        self.assertEqual(self.clock.now, 4)

    def test_persistent_failure_waits_with_bounded_actions_and_deadline(self):
        self.adb.recover = Mock(return_value=False)
        with self.assertRaises(SessionFailure) as failure:
            self.session.ensure_ready()
        self.assertIn("设备恢复时间预算已耗尽", str(failure.exception))
        self.assertEqual(self.clock.now, 60)
        self.assertEqual(self.adb.recover.call_count, 2)
        self.assertEqual(self.session.actions, 3)
        self.assertEqual(self.simulator.actions, ["start"])
        self.assertTrue(
            all(call.args[1] == self.serial for call in self.adb.recover.call_args_list)
        )

    def test_binding_change_during_wait_stops_before_another_reconnect(self):
        self.adb.recover = Mock(return_value=False)
        inspect = self.simulator.inspect

        def changed_binding(profile, timeout):
            if self.clock.now >= 2:
                raise InstanceBindingError("mumu_pro_binding_changed", "实例文件已变化")
            return inspect(profile, timeout)

        self.simulator.inspect = changed_binding
        with self.assertRaises(SessionFailure) as failure:
            self.session.ensure_ready()
        self.assertEqual(failure.exception.observation.code, "mumu_pro_binding_changed")
        self.adb.recover.assert_called_once()
        self.assertEqual(self.simulator.actions, ["start"])

    def test_shared_adb_error_is_terminal_without_retry(self):
        self.adb.recover = Mock(side_effect=SharedADBError("共享 ADB 服务不可用"))
        with self.assertRaises(SessionFailure) as failure:
            self.session.ensure_ready()
        self.assertEqual(failure.exception.observation.code, "adb_server_unavailable")
        self.adb.recover.assert_called_once()
        self.assertEqual(self.clock.now, 0)

    def test_stop_during_wait_does_not_retry_or_restart(self):
        self.adb.recover = Mock(return_value=False)

        def stop_when_waiting(seconds):
            if seconds > 0:
                raise MowerExit

        self.clock.sleep = stop_when_waiting
        with self.assertRaises(MowerExit):
            self.session.ensure_ready()
        self.adb.recover.assert_called_once()
        self.assertEqual(self.simulator.actions, ["start"])
