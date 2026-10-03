"""Input delivery and backend selection at the device application boundary."""

import io
import struct
import tempfile
import unittest
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from typing import get_args
from unittest.mock import MagicMock, call, patch

from arknights_mower.tests.device_maatouch_tests import OwnedProcess
from arknights_mower.tests.device_mumu_frame_tests import NativeRenderer, connected_ipc
from arknights_mower.tests.device_session_tests import ADB, Clock, Preflight, Simulator
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.device_profile import PresetId
from arknights_mower.utils.device.application import DeviceControl, LegacyDeviceAdapter
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.maatouch.core import Client as MaaTouchClient
from arknights_mower.utils.device.preflight import PreflightError
from arknights_mower.utils.device.recovery import (
    DeviceRecoveryError,
    input_reconciliation_scope,
)
from arknights_mower.utils.device.scrcpy import Scrcpy
from arknights_mower.utils.device.session import DeviceSession
from arknights_mower.utils.device.touch_backend import TouchFailure


class InputBackend:
    def __init__(self):
        self.sent = []
        self.error = None
        self.closed = 0

    def tap(self, *args, **kwargs):
        self.sent.append(args)
        if self.error:
            raise self.error

    swipe = tap

    def stop(self):
        self.closed += 1

    close = stop


class InputADB:
    device_id = "USB-A"
    adb_bin = "verified-adb"

    def __init__(self):
        self.sent = []
        self.error = None

    def cmd_shell(self, command, decode=False):
        return "Physical size: 1920x1080"

    def run(self, command):
        self.sent.append(command)
        if self.error:
            raise self.error
        return b""


class TouchTests(unittest.TestCase):
    def setUp(self):
        self.conf = Conf(
            device={"last_serial": "USB-A", "screenshot_backend": "adb_gzip"}
        )
        self.enterContext(patch.object(config, "conf", self.conf))
        self.enterContext(patch.object(config, "stop_mower", Event()))
        self.enterContext(patch.object(config, "MNT_COMPATIBILITY_MODE", False))
        self.io, self.backend = InputADB(), InputBackend()
        self.enterContext(
            patch("arknights_mower.utils.device.device.ADBClient", return_value=self.io)
        )
        self.factory = self.enterContext(
            patch(
                "arknights_mower.utils.device.device.Scrcpy", return_value=self.backend
            )
        )
        self.peer = self.enterContext(
            patch("arknights_mower.utils.device.device.MaaTouch")
        )
        self.enterContext(patch("arknights_mower.utils.device.device.atexit.register"))
        self.adb, self.simulator = ADB(), Simulator()
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        self.control = DeviceControl(
            lambda: self.conf,
            LegacyDeviceAdapter(),
            preflight=Preflight(),
            session=DeviceSession(self.adb, self.simulator, clock=Clock()),
        )
        self.addCleanup(self.control.close)

    def test_uncertain_tap_latches_failure_without_replay_or_peer_switch(self):
        device = self.control.start().unwrap()
        before = self.conf.model_dump()
        capture = MagicMock()
        device._droidcast = capture
        client = device.client
        self.backend.error = OSError("delivery unknown")
        result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertEqual(result.error.code, "touch_result_unknown")
        error = self.control.settings_status()["error"]
        self.assertFalse(self.control.execute(lambda target: target.tap((20, 30))).ok)
        self.assertFalse(self.control.start().ok)
        self.assertEqual(self.backend.sent, [(20, 30)])
        self.assertEqual(self.conf.model_dump(), before)
        self.assertEqual(self.adb.actions, [])
        self.assertEqual(self.simulator.actions, [])
        self.peer.assert_not_called()
        self.assertTrue(error["delivery_unknown"])
        self.assertEqual(error["backend"], "scrcpy")
        self.assertEqual(
            error["alternatives"], [{"backend": "maatouch", "label": "MaaTouch"}]
        )
        self.assertEqual(device.device_id, "USB-A")
        replacement = InputBackend()
        self.factory.return_value = replacement
        self.assertTrue(self.control.recover().ok)
        self.assertIs(device.client, client)
        self.assertIs(device._droidcast, capture)
        capture.close.assert_not_called()
        self.assertEqual(self.backend.sent, [(20, 30)])
        self.assertEqual(replacement.sent, [])
        self.assertFalse(self.control.start().ok)
        self.assertFalse(self.control.execute(lambda target: target.tap((40, 50))).ok)
        with self.assertRaises(TouchFailure) as raised:
            device.tap((40, 50))
        self.assertIs(raised.exception, result.error.cause)
        self.assertEqual(self.backend.sent, [(20, 30)])
        self.assertEqual(replacement.sent, [])

    def test_scene_unknown_recovery_does_not_replay_original_navigation(self):
        device = self.control.start().unwrap()
        self.backend.error = OSError("navigation delivery unknown")
        with input_reconciliation_scope("scene"):
            result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertEqual(result.error.cause.reconciliation, "scene")
        replacement = InputBackend()
        self.factory.return_value = replacement
        self.assertTrue(self.control.recover().ok)
        self.assertEqual(self.backend.sent, [(20, 30)])
        self.assertEqual(replacement.sent, [])
        self.assertTrue(self.control.start().ok)
        with input_reconciliation_scope("scene"):
            device.tap((40, 50))
        self.assertEqual(replacement.sent, [(40, 50)])

    def test_closed_scrcpy_is_rebuilt_before_input_even_when_target_is_ready(self):
        device = self.control.start().unwrap()
        before = self.conf.model_dump()
        self.backend.check_control_alive = lambda: False
        replacement = InputBackend()
        replacement.check_control_alive = lambda: True

        def rebuild(client):
            self.assertEqual(self.backend.closed, 1)
            self.assertEqual(self.backend.sent, [])
            self.assertEqual(client.device_id, "USB-A")
            return replacement

        self.factory.side_effect = rebuild
        device.tap((20, 30))
        self.assertEqual(replacement.sent, [(20, 30)])
        self.assertEqual(self.factory.call_count, 2)
        self.assertEqual(self.control._session.actions, 1)
        self.assertEqual(self.adb.actions, [])
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.conf.model_dump(), before)
        self.peer.assert_not_called()

    def test_explicit_readiness_recovery_does_not_reuse_known_closed_scrcpy(self):
        self.control.start().unwrap()
        self.backend.check_control_alive = lambda: False
        replacement = InputBackend()
        self.factory.return_value = replacement
        self.assertTrue(self.control.recover().ok)
        self.assertEqual(self.backend.closed, 1)
        self.assertEqual(self.factory.call_count, 2)
        self.assertEqual(replacement.sent, [])

    def test_healthy_scrcpy_is_not_rebuilt_before_input_or_ready_recovery(self):
        device = self.control.start().unwrap()
        self.backend.check_control_alive = lambda: True
        device.tap((20, 30))
        self.assertTrue(self.control.recover().ok)
        self.assertEqual(self.backend.sent, [(20, 30)])
        self.assertEqual(self.backend.closed, 0)
        self.assertEqual(self.factory.call_count, 1)

    def test_closed_scrcpy_without_recovery_attempts_sends_no_input(self):
        self.conf.device.recovery_attempts = 0
        self.control.start().unwrap()
        self.backend.check_control_alive = lambda: False
        result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertFalse(result.ok)
        self.assertEqual(self.backend.sent, [])
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.adb.actions, [])
        self.assertEqual(self.simulator.actions, [])

    def test_replacement_scrcpy_dead_rebuilds_only_within_budget_without_input(self):
        self.control.start().unwrap()
        self.backend.check_control_alive = lambda: False
        replacement = InputBackend()
        replacement.check_control_alive = lambda: False
        self.factory.return_value = replacement
        result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertFalse(result.ok)
        self.assertEqual(self.backend.sent, [])
        self.assertEqual(replacement.sent, [])
        self.assertEqual(
            self.factory.call_count, self.conf.device.recovery_attempts + 1
        )
        self.assertFalse(self.control.execute(lambda target: target.tap((20, 30))).ok)
        self.assertEqual(
            self.factory.call_count, self.conf.device.recovery_attempts + 1
        )

    def test_closed_scrcpy_cleanup_failure_blocks_input_and_replacement(self):
        self.control.start().unwrap()
        self.backend.check_control_alive = lambda: False

        def broken_stop():
            self.backend.closed += 1
            raise OSError("owned control remains live")

        self.backend.stop = broken_stop
        result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertFalse(result.ok)
        self.assertEqual(self.backend.sent, [])
        self.assertEqual(self.factory.call_count, 1)
        self.assertFalse(self.control.close().ok)
        self.assertFalse(self.control.start().ok)

    def test_unconfirmed_probe_repair_exhausts_budget_without_sending_input(self):
        self.control.start().unwrap()

        def unknown_probe():
            raise TimeoutError("scrcpy probe unconfirmed")

        self.backend.check_control_alive = unknown_probe
        with patch("arknights_mower.utils.device.device.budget_sleep"):
            result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "touch_initialization_failed")
        self.assertFalse(result.error.cause.delivery_unknown)
        self.assertEqual(self.backend.sent, [])
        self.assertEqual(
            self.factory.call_count, self.conf.device.recovery_attempts + 1
        )
        self.assertEqual(
            self.control._session.actions, self.conf.device.recovery_attempts
        )
        self.assertEqual(self.adb.actions, [])
        self.assertEqual(self.simulator.actions, [])

    def test_transient_probe_timeout_rechecks_before_sending_once(self):
        device = self.control.start().unwrap()
        probe = MagicMock(
            side_effect=[TimeoutError("busy"), TimeoutError("busy"), True]
        )
        self.backend.check_control_alive = probe
        with patch("arknights_mower.utils.device.device.budget_sleep"):
            device.tap((20, 30))
        self.assertEqual(probe.call_count, 3)
        self.assertEqual(self.backend.sent, [(20, 30)])
        self.assertEqual(self.factory.call_count, 1)

    def test_unconfirmed_probe_stops_after_bounded_attempts_without_assuming_alive(
        self,
    ):
        device = self.control.start().unwrap()
        probe = MagicMock(side_effect=TimeoutError("busy"))
        self.backend.check_control_alive = probe
        with patch("arknights_mower.utils.device.device.budget_sleep"):
            with self.assertRaises(TouchFailure) as raised:
                device.input_alive()
        self.assertEqual(probe.call_count, self.conf.device.recovery_attempts + 1)
        self.assertEqual(raised.exception.phase, "probe")
        self.assertTrue(raised.exception.retryable)
        self.assertFalse(raised.exception.delivery_unknown)
        self.assertEqual(self.backend.sent, [])

    def test_probe_cancelled_during_recheck_never_sends_input(self):
        from arknights_mower.utils.csleep import MowerExit

        device = self.control.start().unwrap()
        self.backend.check_control_alive = MagicMock(side_effect=TimeoutError("busy"))
        with patch(
            "arknights_mower.utils.device.device.budget_sleep",
            side_effect=MowerExit("cancelled"),
        ):
            with self.assertRaises(MowerExit):
                device.input_alive()
        self.assertEqual(self.backend.sent, [])

    def test_local_input_rebuild_preserves_capture_and_adb(self):
        device = self.control.start().unwrap()
        before = self.conf.model_dump()
        capture = MagicMock()
        device._droidcast = capture
        old_client = device.client
        replacement = InputBackend()
        self.factory.return_value = replacement
        self.assertTrue(device.rebuild_input())
        self.assertIs(device.client, old_client)
        self.assertIs(device._droidcast, capture)
        capture.close.assert_not_called()
        self.assertEqual(self.backend.closed, 1)
        self.assertEqual(self.factory.call_count, 2)
        self.assertEqual(self.conf.model_dump(), before)

    def test_local_input_rebuild_refuses_to_split_ipc_pair(self):
        device, channel, _ = self.start_mumu_input()
        old_control = device.control
        old_client = device.client
        self.assertFalse(device.rebuild_input())
        self.assertIs(device.control, old_control)
        self.assertIs(device.client, old_client)
        channel.close.assert_not_called()

    def test_local_input_rebuild_does_not_replace_failed_cleanup(self):
        device = self.control.start().unwrap()

        def failed_close():
            raise OSError("owned helper remains live")

        self.backend.stop = failed_close
        with self.assertRaises(TouchFailure) as raised:
            device.rebuild_input()
        self.assertTrue(raised.exception.cleanup_failed)
        self.assertEqual(self.factory.call_count, 1)
        self.backend.stop = lambda: None

    def test_cancelled_input_rebuild_retains_failed_partial_cleanup(self):
        from arknights_mower.utils.csleep import MowerExit

        device = self.control.start().unwrap()
        replacement = InputBackend()
        replacement.stop = MagicMock(side_effect=OSError("new helper remains live"))
        self.factory.return_value = replacement
        with patch(
            "arknights_mower.utils.device.device.budget_sleep",
            side_effect=[None, MowerExit("cancelled")],
        ):
            with self.assertRaises(MowerExit) as raised:
                device.rebuild_input()
        self.assertTrue(raised.exception.cleanup_failed)
        replacement.stop.assert_called_once()
        self.assertIsNone(device.control)
        with self.assertRaises(MowerExit):
            device.resume_verified()
        self.assertEqual(replacement.sent, [])

    def test_input_probe_retains_outer_deadline(self):
        device = self.control.start().unwrap()
        clock = self.control._session.clock
        self.backend.check_control_alive = MagicMock(side_effect=TimeoutError("busy"))

        def remaining():
            available = 0.1 - clock.now
            if available <= 0:
                raise TimeoutError("outer deadline")
            return available

        with self.assertRaises(TimeoutError):
            with (
                patch(
                    "arknights_mower.utils.device.device.time.monotonic",
                    clock.monotonic,
                ),
                patch("arknights_mower.utils.device.io_budget.csleep", clock.sleep),
                device_io_budget(remaining),
            ):
                with self.assertRaises(TouchFailure) as raised:
                    device.input_alive()
        self.assertEqual(clock.now, 0.1)
        self.assertEqual(raised.exception.phase, "probe")
        self.assertEqual(self.backend.sent, [])

    def test_resume_verified_releases_non_touch_failure_without_replaying_input(self):
        device = self.control.start().unwrap()
        device._recovery_error = DeviceRecoveryError("previous readiness failed")
        device.resume_verified()
        self.assertIsNone(device._recovery_error)
        self.assertEqual(self.backend.sent, [])
        self.assertEqual(self.factory.call_count, 1)

    def test_local_input_rebuild_releases_non_touch_failure_only_after_cleanup(self):
        device = self.control.start().unwrap()
        device._recovery_error = DeviceRecoveryError("previous readiness failed")
        replacement = InputBackend()
        self.factory.return_value = replacement
        self.assertTrue(device.rebuild_input())
        self.assertIsNone(device._recovery_error)
        self.assertEqual(self.backend.closed, 1)
        self.assertEqual(replacement.sent, [])

    def test_resume_verified_keeps_cleanup_failure_latched(self):
        device = self.control.start().unwrap()
        failure = TouchFailure(self.conf.device, "windows", OSError("owned helper"))
        failure.cleanup_failed = True
        device._recovery_error = failure
        with self.assertRaises(TouchFailure):
            device.resume_verified()
        self.assertIs(device._recovery_error, failure)
        self.assertEqual(self.backend.sent, [])

    def test_verified_rebind_releases_old_non_touch_failure_after_cleanup(self):
        device = self.control.start().unwrap()
        device._recovery_error = DeviceRecoveryError("previous readiness failed")
        replacement = InputBackend()
        self.factory.return_value = replacement
        device.rebind_target("USB-A", "verified-adb")
        self.assertIsNone(device._recovery_error)
        self.assertEqual(self.backend.closed, 1)
        self.assertEqual(replacement.sent, [])

    def test_maatouch_display_preparation_failure_is_not_delivery_unknown(self):
        self.conf.device.touch_backend = "maatouch"
        self.conf.sync_legacy_device_fields()
        self.peer.return_value = self.backend
        device = self.control.start().unwrap()
        with patch.object(
            device, "display_frames", side_effect=ValueError("invalid geometry")
        ):
            with self.assertRaises(TouchFailure) as raised:
                device.tap((20, 30))
        self.assertEqual(raised.exception.phase, "preparation")
        self.assertEqual(raised.exception.code, "touch_preparation_failed")
        self.assertFalse(raised.exception.delivery_unknown)
        self.assertEqual(raised.exception.transport, "adb")
        self.assertEqual(self.backend.sent, [])

    def real_maatouch(self, process):
        self.conf.device.touch_backend = "maatouch"
        self.conf.sync_legacy_device_fields()
        with patch.object(MaaTouchClient, "start"):
            self.peer.return_value = MaaTouchClient(self.io)
        self.enterContext(
            patch(
                "arknights_mower.utils.device.maatouch.session.subprocess.Popen",
                return_value=process,
            )
        )
        self.enterContext(
            patch("arknights_mower.utils.device.maatouch.session.guard_adb")
        )
        return self.control.start().unwrap()

    def test_real_maatouch_handshake_timeout_is_not_input_delivery_unknown(self):
        process = OwnedProcess()
        device = self.real_maatouch(process)
        with patch(
            "arknights_mower.utils.device.maatouch.session.Session._io",
            side_effect=TimeoutError("header timed out before input"),
        ):
            result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertFalse(result.ok)
        self.assertFalse(result.error.cause.delivery_unknown)
        self.assertEqual(result.error.cause.phase, "preparation")
        self.assertTrue(result.error.cause.retryable)
        self.assertIsNotNone(device.control)
        self.assertTrue(process.stdin.closed)

    def test_real_maatouch_swipe_builds_integer_millisecond_commands(self):
        commands = []

        class CommandPipe(io.StringIO):
            def write(self, content):
                commands.append(content)
                return super().write(content)

        process = OwnedProcess()
        process.stdin = CommandPipe()
        device = self.real_maatouch(process)
        with patch("arknights_mower.utils.device.maatouch.session.Session.wait"):
            device.swipe_ext([(20, 30), (40, 50)], [100], up_wait=200)
        waits = [
            line
            for command in commands
            for line in command.splitlines()
            if line.startswith("w ")
        ]
        self.assertIn("w 200", waits)
        self.assertIn("w 10", waits)
        self.assertTrue(all(line[2:].isdecimal() for line in waits))
        self.assertTrue(process.stdin.closed)

    def test_real_maatouch_preparation_after_down_remains_unknown_without_replay(self):
        commands = []

        class CommandPipe(io.StringIO):
            def write(self, content):
                commands.append(content)
                return super().write(content)

        process = OwnedProcess()
        process.stdin = CommandPipe()
        device = self.real_maatouch(process)
        with (
            patch("arknights_mower.utils.device.maatouch.session.Session.wait"),
            patch(
                "arknights_mower.utils.device.maatouch.command.CommandBuilder.move",
                side_effect=ValueError("move preparation after down"),
            ),
        ):
            result = self.control.execute(
                lambda target: target.swipe_ext([(20, 30), (40, 50)], [100])
            )
        self.assertTrue(result.error.cause.delivery_unknown)
        self.assertEqual(len(commands), 1)
        self.assertTrue(commands[0].startswith("d 0 20 30 100\n"))
        self.assertTrue(process.stdin.closed)
        with self.assertRaises(TouchFailure):
            device.swipe_ext([(20, 30), (40, 50)], [100])
        self.assertEqual(len(commands), 1)

    def test_real_maatouch_presend_cleanup_failure_stays_permanently_blocked(self):
        process = OwnedProcess()
        process.stdout = io.StringIO("invalid header\n")
        process.exit_on_eof = 3
        self.real_maatouch(process)
        result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertFalse(result.error.cause.delivery_unknown)
        self.assertTrue(result.error.cause.cleanup_failed)
        self.assertFalse(self.control.recover().ok)
        self.assertFalse(self.control.start().ok)
        self.assertFalse(self.control.execute(lambda target: target.tap((20, 30))).ok)
        self.assertEqual(self.peer.call_count, 1)

    def test_scrcpy_coordinate_range_matches_signed_packet_fields(self):
        device, helper = self.real_scrcpy()
        wire = helper.control_socket
        for coordinate in (-(2**31) - 1, 2**31):
            with self.subTest(coordinate=coordinate):
                with self.assertRaises(ValueError):
                    device._prepare_touch([(coordinate, 30)])
        with patch("arknights_mower.utils.device.scrcpy.control.budget_sleep"):
            device.tap((2**31 - 1, -(2**31)))
        packet = wire.sendall.call_args_list[0].args[0]
        self.assertEqual(struct.unpack(">ii", packet[10:18]), (2**31 - 1, 0))

    def real_scrcpy(self):
        with patch.object(Scrcpy, "start"):
            helper = Scrcpy(self.io)
        helper.resolution = (1920, 1080)
        helper.control_socket = MagicMock()
        helper.control_socket.sendall.return_value = None
        helper.check_control_alive = lambda: True
        self.factory.return_value = helper
        return self.control.start().unwrap(), helper

    def test_real_scrcpy_packet_construction_failure_is_not_delivery_unknown(self):
        device, helper = self.real_scrcpy()
        wire = helper.control_socket
        helper.resolution = (65536, 1080)
        result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertFalse(result.ok)
        self.assertFalse(result.error.cause.delivery_unknown)
        self.assertEqual(result.error.cause.phase, "preparation")
        wire.sendall.assert_not_called()
        self.assertIs(device.control.scrcpy, helper)

    def test_scrcpy_packet_failure_after_down_remains_unknown_without_replay(self):
        device, helper = self.real_scrcpy()
        wire = helper.control_socket
        wire.sendall.side_effect = lambda packet: setattr(helper, "resolution", None)
        with patch("arknights_mower.utils.device.scrcpy.control.budget_sleep"):
            result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertFalse(result.ok)
        self.assertTrue(result.error.cause.delivery_unknown)
        wire.sendall.assert_called_once()
        self.assertEqual(wire.sendall.call_args.args[0][:2], b"\x02\x00")
        with self.assertRaises(TouchFailure):
            device.tap((20, 30))
        wire.sendall.assert_called_once()

    def test_scrcpy_later_segment_preparation_failure_keeps_prior_delivery_unknown(
        self,
    ):
        device, helper = self.real_scrcpy()
        wire = helper.control_socket
        swipe = helper.swipe

        def invalidate_after_first_segment(*args, **kwargs):
            swipe(*args, **kwargs)
            helper.resolution = None

        helper.swipe = invalidate_after_first_segment
        with patch("arknights_mower.utils.device.scrcpy.core.budget_sleep"):
            result = self.control.execute(
                lambda target: target.swipe_ext([(20, 30), (40, 50), (60, 70)], [0, 0])
            )
        self.assertFalse(result.ok)
        self.assertTrue(result.error.cause.delivery_unknown)
        self.assertEqual(wire.sendall.call_count, 2)
        with self.assertRaises(TouchFailure):
            device.swipe_ext([(20, 30), (40, 50), (60, 70)], [0, 0])
        self.assertEqual(wire.sendall.call_count, 2)

    def test_invalid_later_swipe_point_fails_before_any_segment_is_sent(self):
        device = self.control.start().unwrap()
        with self.assertRaises(TouchFailure) as raised:
            device.swipe_ext([(20, 30), (40, 50), ("invalid", 70)], [100, 100])
        self.assertFalse(raised.exception.delivery_unknown)
        self.assertEqual(raised.exception.phase, "preparation")
        self.assertEqual(self.backend.sent, [])

    def test_maatouch_display_preparation_is_performed_once_before_each_send(self):
        self.conf.device.touch_backend = "maatouch"
        self.conf.sync_legacy_device_fields()
        self.peer.return_value = self.backend
        device = self.control.start().unwrap()
        geometry = (1920, 1080, 1)
        with patch.object(device, "display_frames", return_value=geometry) as display:
            device.tap((20, 30))
            device.swipe((20, 30), (40, 50))
            device.swipe_ext([(20, 30), (40, 50), (60, 70)], [100, 100])
        self.assertEqual(display.call_count, 3)
        self.assertEqual(len(self.backend.sent), 3)
        self.assertTrue(all(sent[1] == geometry for sent in self.backend.sent))

    def test_maatouch_send_timeout_remains_delivery_unknown_without_replay(self):
        self.conf.device.touch_backend = "maatouch"
        self.conf.sync_legacy_device_fields()
        self.peer.return_value = self.backend
        device = self.control.start().unwrap()
        self.backend.error = TimeoutError("send not acknowledged")
        result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertEqual(result.error.code, "touch_result_unknown")
        self.assertTrue(result.error.cause.delivery_unknown)
        self.assertEqual(result.error.cause.phase, "delivery")
        self.assertEqual(self.backend.sent, [([(20, 30)], None)])
        with self.assertRaises(TouchFailure):
            device.tap((20, 30))
        self.assertEqual(self.backend.sent, [([(20, 30)], None)])

    def test_touch_failure_captures_reconciliation_without_changing_delivery_verdict(
        self,
    ):
        task_failure = TouchFailure(
            self.conf.device, "windows", OSError("unknown"), delivery_unknown=True
        )
        with input_reconciliation_scope("scene"):
            scene_failure = TouchFailure(
                self.conf.device, "windows", OSError("unknown"), delivery_unknown=True
            )
        self.assertEqual(task_failure.reconciliation, "task")
        self.assertEqual(scene_failure.reconciliation, "scene")
        self.assertEqual(scene_failure.to_dict()["reconciliation"], "scene")
        self.assertTrue(scene_failure.delivery_unknown)
        self.assertEqual(scene_failure.code, "touch_result_unknown")

    def test_missing_runtime_input_control_is_not_considered_healthy(self):
        device = self.control.start().unwrap()
        device._stop_control()
        self.assertIsNone(device.control)
        self.assertFalse(device.input_alive())
        self.assertEqual(self.backend.closed, 1)

    def test_closed_scrcpy_rebuild_revalidates_before_opening_helpers(self):
        self.control.start().unwrap()
        before = self.conf.model_dump()
        self.backend.check_control_alive = lambda: False
        check = self.control._preflight.check

        def reject(profile, **options):
            result = check(profile, **options)
            result.ok = False
            result.error = PreflightError("binding_failed", "binding changed")
            return result

        self.control._preflight.check = reject
        result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "binding_failed")
        self.assertEqual(self.backend.sent, [])
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.conf.model_dump(), before)

    def test_closed_scrcpy_recovery_is_shared_by_all_device_presets(self):
        for preset in get_args(PresetId):
            with self.subTest(preset=preset):
                self.control.close()
                self.conf.device.preset_id = preset
                self.conf.sync_legacy_device_fields()
                self.simulator.state = "running"
                self.simulator.serial = "USB-A"
                self.backend = InputBackend()
                self.factory.return_value = self.backend
                device = self.control.start().unwrap()
                self.backend.check_control_alive = lambda: False
                replacement = InputBackend()
                self.factory.return_value = replacement
                before = self.conf.model_dump()
                device.tap((20, 30))
                self.assertEqual(self.backend.sent, [])
                self.assertEqual(self.backend.closed, 1)
                self.assertEqual(replacement.sent, [(20, 30)])
                self.assertEqual(self.conf.model_dump(), before)
                self.assertEqual(self.adb.actions, [])
                self.assertEqual(self.simulator.actions, [])
                self.peer.assert_not_called()

    def test_closed_scrcpy_rebuild_cannot_exceed_recovery_deadline(self):
        self.control.start().unwrap()
        self.backend.check_control_alive = lambda: False
        replacement = InputBackend()

        def late_rebuild(client):
            self.control._session.clock.now += self.conf.device.recovery_timeout
            return replacement

        self.factory.side_effect = late_rebuild
        result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertFalse(result.ok)
        self.assertEqual(self.backend.sent, [])
        self.assertEqual(replacement.sent, [])
        self.assertEqual(self.factory.call_count, 2)

    def test_uncertain_key_does_not_send_again_from_outer_solver(self):
        device = self.control.start().unwrap()
        self.io.error = TimeoutError("key result unknown")
        result = self.control.execute(lambda target: target.send_keyevent(4))
        self.assertEqual(result.error.code, "touch_result_unknown")
        with self.assertRaises(TouchFailure):
            device.send_keyevent(4)
        self.assertEqual(self.io.sent, ["input keyevent 4"])

    def start_mumu_input(self):
        self.conf.device.preset_id = "windows.mumu12"
        self.conf.device.installation_path = "MuMu"
        self.conf.device.manager_path = "MuMu/MuMuManager.exe"
        self.conf.device.instance_id = "0"
        self.conf.device.touch_backend = self.conf.device.screenshot_backend = (
            "mumu_ipc"
        )
        self.conf.sync_legacy_device_fields()
        context = MagicMock()
        channel, child = MagicMock(), MagicMock()
        context.Pipe.return_value = channel, child
        context.Process.return_value.is_alive.return_value = False
        channel.poll.return_value = True
        channel.recv.return_value = ("ok", "", None)
        self.enterContext(
            patch("arknights_mower.utils.device.device.__system__", "windows"),
        )
        self.enterContext(
            patch(
                "arknights_mower.utils.device.mumu12ipc.input.subprocess.run",
                return_value=SimpleNamespace(stdout="4.1.21"),
            )
        )
        self.enterContext(
            patch(
                "arknights_mower.utils.device.mumu12ipc.input.multiprocessing.get_context",
                return_value=context,
            )
        )
        return self.control.start().unwrap(), channel, context

    def test_mumu_back_uses_native_input_when_adb_exec_is_closed(self):
        device, channel, context = self.start_mumu_input()
        before = self.conf.model_dump()
        self.io.error = ConnectionError(b"closed")
        device.send_keyevent(4)
        self.assertEqual(
            channel.send.call_args_list,
            [call(("key_down", (1,))), call(("key_up", (1,)))],
        )
        self.assertEqual(self.io.sent, [])
        self.assertEqual(self.conf.model_dump(), before)
        self.assertEqual(self.adb.actions, [])
        self.assertEqual(self.simulator.actions, [])
        context.Process.return_value.start.assert_called_once()

    def test_mumu_back_failure_never_replays_or_sends_adb_input(self):
        for failed_event in ("key_down", "key_up"):
            with self.subTest(failed_event=failed_event):
                self.control.close()
                device, channel, context = self.start_mumu_input()
                before = self.conf.model_dump()
                capture = MagicMock()
                device._mumu_capture = capture
                replies = [("error", f"{failed_event} failed: -5", -5)]
                expected = [call(("key_down", (1,)))]
                if failed_event == "key_up":
                    replies.insert(0, ("ok", "", None))
                    expected.append(call(("key_up", (1,))))
                channel.recv.side_effect = replies
                result = self.control.execute(lambda target: target.send_keyevent(4))
                self.assertEqual(result.error.code, "touch_result_unknown")
                self.assertIn("MuMu IPC", result.error.message)
                self.assertIn(failed_event, result.error.message)
                with self.assertRaises(TouchFailure):
                    device.send_keyevent(4)
                self.assertFalse(self.control.start().ok)
                self.assertEqual(channel.send.call_args_list, expected)
                self.assertEqual(self.io.sent, [])
                context.Process.return_value.start.assert_called_once()
                channel.close.assert_called_once()
                channel.recv.side_effect = None
                channel.recv.return_value = ("ok", "", None)
                self.assertTrue(self.control.recover().ok)
                self.assertEqual(context.Process.return_value.start.call_count, 2)
                self.assertEqual(channel.send.call_args_list, expected)
                capture.close.assert_called_once()
                self.assertEqual(self.io.sent, [])
                self.assertEqual(device.device_id, "USB-A")
                self.assertEqual(self.conf.model_dump(), before)

    def test_mumu_back_waiting_for_recovery_keeps_native_transport(self):
        device, channel, _ = self.start_mumu_input()
        waiting = Event()
        errors = []
        execute = self.control.execute

        def queued(operation):
            waiting.set()
            return execute(operation)

        def back():
            try:
                device.send_keyevent(4)
            except Exception as exc:
                errors.append(exc)

        worker = Thread(target=back)
        with patch.object(self.control, "execute", side_effect=queued):
            try:
                with self.control.configuration_lock:
                    native_control = device.control
                    device.control = None
                    try:
                        worker.start()
                        self.assertTrue(waiting.wait(1))
                    finally:
                        device.control = native_control
            finally:
                worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.io.sent, [])
        self.assertEqual(
            channel.send.call_args_list,
            [call(("key_down", (1,))), call(("key_up", (1,)))],
        )

    def test_mumu_other_keys_keep_android_keycodes_on_adb(self):
        device, channel, _ = self.start_mumu_input()
        device.send_keyevent(3)
        device.send_keyevent(66)
        self.assertEqual(self.io.sent, ["input keyevent 3", "input keyevent 66"])
        channel.send.assert_not_called()

    def test_adb_input_failure_reports_actual_transport_without_peer_advice(self):
        for operation, expected in (
            (lambda device: device.send_keyevent(3), "input keyevent 3"),
            (lambda device: device.send_text("abc"), 'input text "abc"'),
            (lambda device: device.launch(), "input tap 20 30"),
        ):
            with self.subTest(command=expected):
                self.control.close()
                device, channel, _ = self.start_mumu_input()
                self.conf.tap_to_launch_game.mode = "tap"
                self.conf.tap_to_launch_game.x = 20
                self.conf.tap_to_launch_game.y = 30
                before = self.conf.model_dump()
                self.io.sent.clear()
                self.io.error = ConnectionError(b"closed")
                result = self.control.execute(operation)
                self.assertEqual(result.error.code, "touch_result_unknown")
                self.assertTrue(result.error.message.startswith("ADB "))
                self.assertNotIn("MuMu IPC", result.error.message)
                self.assertNotIn("其他兼容触控后端", result.error.message)
                error = self.control.settings_status()["error"]
                self.assertEqual(error["transport"], "adb")
                self.assertEqual(error["backend"], "mumu_ipc")
                self.assertEqual(error["alternatives"], [])
                with self.assertRaises(TouchFailure):
                    operation(device)
                self.assertEqual(self.io.sent, [expected])
                channel.send.assert_not_called()
                self.assertEqual(self.conf.model_dump(), before)

    def test_initialization_failure_lists_peers_and_preserves_configuration(self):
        self.factory.side_effect = ConnectionError("server handshake failed")
        before = self.conf.model_dump()
        result = self.control.start()
        self.assertEqual(result.error.code, "touch_initialization_failed")
        self.assertFalse(self.control.start().ok)
        self.assertEqual(self.factory.call_count, 1)
        error = self.control.settings_status()["error"]
        self.assertFalse(error["delivery_unknown"])
        self.assertEqual(error["fields"], ["touch_backend"])
        self.assertEqual(
            error["alternatives"], [{"backend": "maatouch", "label": "MaaTouch"}]
        )
        self.assertEqual(self.conf.model_dump(), before)
        self.peer.assert_not_called()

    def test_failed_initialization_cleanup_cannot_be_reset_by_close_and_start(self):
        from arknights_mower.utils.device.scrcpy.core import ScrcpyCleanupError

        self.factory.side_effect = ScrcpyCleanupError("owned server close failed")
        self.assertFalse(self.control.start().ok)
        self.assertFalse(self.control.close().ok)
        self.assertFalse(self.control.start().ok)
        self.assertFalse(self.control.recover().ok)
        self.assertEqual(self.factory.call_count, 1)

    def test_validation_failure_keeps_partial_startup_cleanup_error_latched(self):
        def invalid_surface():
            raise ValueError("input surface invalid")

        def broken_stop():
            self.backend.closed += 1
            raise OSError("owned server remains live")

        self.backend.stop = broken_stop
        preflight = Preflight()
        preflight.resolve_adb = MagicMock(return_value=self.io.adb_bin)
        control = DeviceControl(
            lambda: self.conf,
            LegacyDeviceAdapter(),
            preflight=preflight,
            preparation=SimpleNamespace(
                prepared_size=None,
                begin=lambda *args: None,
                validate=invalid_surface,
                close=lambda: None,
            ),
        )
        self.addCleanup(control.close)
        self.assertFalse(control.start().ok)
        self.assertFalse(control.close().ok)
        self.assertFalse(control.start().ok)
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.backend.closed, 1)
        preflight.resolve_adb.assert_called_once()

    def test_application_close_releases_maatouch_once(self):
        self.conf.device.touch_backend = "maatouch"
        self.conf.sync_legacy_device_fields()
        self.peer.return_value = self.backend
        self.control.start().unwrap()
        self.assertTrue(self.control.close().ok)
        self.assertTrue(self.control.close().ok)
        self.assertEqual(self.backend.closed, 1)

    def test_uncertain_swipes_stop_remaining_segments_and_outer_retries(self):
        for extended in (False, True):
            with self.subTest(extended=extended):
                self.control.close()
                self.backend.sent.clear()
                device = self.control.start().unwrap()
                self.backend.error = OSError("partial swipe")

                def swipe(target):
                    if extended:
                        target.swipe_ext([(10, 20), (30, 40), (50, 60)], [100, 100])
                    else:
                        target.swipe((10, 20), (30, 40), 100)

                result = self.control.execute(swipe)
                self.assertEqual(result.error.code, "touch_result_unknown")
                with self.assertRaises(TouchFailure):
                    swipe(device)
                self.assertEqual(len(self.backend.sent), 1)

    def test_legacy_device_key_failure_is_also_never_replayed(self):
        device = self.control.start().unwrap()
        device.session_control = None
        self.io.error = TimeoutError("unknown ADB response")
        for _ in range(2):
            with self.assertRaises(TouchFailure):
                device.send_keyevent(4)
        self.assertEqual(self.io.sent, ["input keyevent 4"])

    def test_repeated_start_reuses_control_and_explicit_recovery_releases_old_one(self):
        device = self.control.start().unwrap()
        self.assertIs(self.control.start().unwrap(), device)
        self.assertEqual(self.factory.call_count, 1)
        replacement = InputBackend()

        def rebuild(client):
            self.assertEqual(self.backend.closed, 1)
            return replacement

        self.factory.side_effect = rebuild
        self.adb.rows = [("USB-A", "offline")]
        self.adb.on_recover = lambda: setattr(self.adb, "rows", [("USB-A", "device")])
        self.assertTrue(self.control.recover().ok)
        self.assertEqual(self.factory.call_count, 2)
        device.tap((30, 40))
        self.assertEqual(replacement.sent, [(30, 40)])
        self.peer.assert_not_called()

    def test_unavailable_ipc_reports_reason_before_constructing_the_backend(self):
        self.conf.device.touch_backend = "mumu_ipc"
        self.conf.device.screenshot_backend = "mumu_ipc"
        self.conf.sync_legacy_device_fields()
        with patch("arknights_mower.utils.device.device.MuMu12IPC") as ipc:
            result = self.control.start()
        self.assertEqual(result.error.code, "touch_initialization_failed")
        self.assertIn("Windows", result.error.message)
        self.assertIn("MuMu 12", result.error.message)
        ipc.assert_not_called()
        self.assertEqual(
            {
                item["backend"]
                for item in self.control.settings_status()["error"]["alternatives"]
            },
            {"scrcpy", "maatouch"},
        )

    def test_missing_maatouch_asset_reports_reason_before_construction(self):
        from arknights_mower.utils.device import touch_backend

        self.conf.device.touch_backend = "maatouch"
        self.conf.sync_legacy_device_fields()
        missing = Path(tempfile.gettempdir()) / "arknights-mower-missing" / "maatouch"
        with patch.object(touch_backend, "MAATOUCH_ASSET", missing):
            capabilities = {
                item["backend"]: item
                for item in touch_backend.touch_backends(self.conf.device, "windows")
            }
            result = self.control.start()
            self.assertEqual(result.error.code, "touch_initialization_failed")
            self.assertIn(str(missing), result.error.message)
            self.peer.assert_not_called()
        self.assertFalse(capabilities["maatouch"]["available"])
        self.assertIn(str(missing), capabilities["maatouch"]["reason"])
        self.assertTrue(capabilities["scrcpy"]["available"])
        self.assertEqual(capabilities["scrcpy"]["reason"], "")
        self.assertEqual(result.error.cause.backend, "maatouch")
        self.assertEqual(
            result.error.cause.alternatives,
            [{"backend": "scrcpy", "label": "scrcpy 1.21"}],
        )

    def test_missing_scrcpy_asset_keeps_maatouch_as_the_available_peer(self):
        from arknights_mower.utils.device import touch_backend

        self.conf.device.touch_backend = self.conf.device.screenshot_backend = "scrcpy"
        self.conf.sync_legacy_device_fields()
        missing = Path(tempfile.gettempdir()) / "arknights-mower-missing" / "scrcpy.jar"
        with patch.object(touch_backend, "SCRCPY_JAR", missing):
            result = self.control.start()
            self.assertEqual(result.error.code, "touch_initialization_failed")
            self.assertIn(str(missing), result.error.message)
            # The selection order never changes: the peer is offered, not chosen.
            self.assertEqual(self.factory.call_count, 0)
            self.peer.assert_not_called()
            capabilities = {
                item["backend"]: item
                for item in touch_backend.touch_backends(self.conf.device, "windows")
            }
        self.assertFalse(capabilities["scrcpy"]["available"])
        self.assertTrue(capabilities["maatouch"]["available"])
        self.assertEqual(
            result.error.cause.alternatives,
            [{"backend": "maatouch", "label": "MaaTouch"}],
        )

    def test_bundled_backends_stay_available_without_a_reason(self):
        from arknights_mower.utils.device import touch_backend

        capabilities = {
            item["backend"]: item
            for item in touch_backend.touch_backends(self.conf.device, "windows")
        }
        self.assertTrue(capabilities["scrcpy"]["available"])
        self.assertTrue(capabilities["maatouch"]["available"])

    def test_native_ipc_failure_stops_swipe_and_preserves_owned_connection_for_close(
        self,
    ):
        class NativeInput(NativeRenderer):
            def __init__(self):
                super().__init__()
                self.sent = []

            def nemu_input_event_touch_down(self, *args):
                self.sent.append(args)
                return -5

            def nemu_input_event_touch_up(self, *args):
                self.sent.append(args)
                return 0

        native = NativeInput()
        ipc = connected_ipc(native)
        ipc._is_new_coord = True
        self.conf.device.preset_id = "windows.mumu12"
        self.conf.device.touch_backend = self.conf.device.screenshot_backend = (
            "mumu_ipc"
        )
        self.conf.sync_legacy_device_fields()
        with (
            patch("arknights_mower.utils.device.device.MuMu12IPC", return_value=ipc),
            patch("arknights_mower.utils.device.device.__system__", "windows"),
        ):
            self.control.start().unwrap()
            result = self.control.execute(
                lambda device: device.swipe((10, 20), (30, 40), 1)
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.error.code, "touch_result_unknown")
            self.assertIn("-5", result.error.message)
            self.assertFalse(
                self.control.execute(lambda device: device.tap((10, 20))).ok
            )
        self.assertEqual(native.sent, [(7, 0, 10, 20)])
        self.assertEqual(native.disconnected, [7])
        self.assertEqual(native.connect_calls, 0)

    def test_close_rejects_rebuild_until_the_old_backend_finishes_stopping(self):
        self.control.start().unwrap()
        entered, release = Event(), Event()

        def stop():
            entered.set()
            release.wait(2)
            self.backend.closed += 1

        self.backend.stop = stop
        self.adb.rows = [("USB-A", "offline")]
        self.adb.on_recover = lambda: setattr(self.adb, "rows", [("USB-A", "device")])
        results = []
        closer = Thread(target=lambda: results.append(self.control.close()))
        closer.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertFalse(self.control.recover().ok)
            self.assertFalse(self.control.start().ok)
            self.assertFalse(
                self.control.execute(lambda device: device.tap((10, 20))).ok
            )
            self.assertEqual(self.factory.call_count, 1)
            self.assertEqual(self.adb.actions, [])
        finally:
            release.set()
            closer.join(2)
        self.assertFalse(closer.is_alive())
        self.assertTrue(results[0].ok)
        self.assertEqual(self.backend.closed, 1)

    def test_close_cancels_recovery_already_waiting_for_transport(self):
        self.control.start().unwrap()
        recovering, recovered, stopping, stopped = Event(), Event(), Event(), Event()

        def recover():
            recovering.set()
            recovered.wait(2)
            self.adb.rows = [("USB-A", "device")]

        def stop():
            stopping.set()
            stopped.wait(2)
            self.backend.closed += 1

        self.backend.stop = stop
        # Cancellation wakes the blocked application operation; final helper
        # release still waits until recovery has unwound and restoration runs.
        self.backend.interrupt = stopping.set
        self.adb.rows = [("USB-A", "offline")]
        self.adb.on_recover = recover
        recovery_results, close_results = [], []
        recovery = Thread(
            target=lambda: recovery_results.append(self.control.recover())
        )
        closer = Thread(target=lambda: close_results.append(self.control.close()))
        recovery.start()
        try:
            self.assertTrue(recovering.wait(1))
            closer.start()
            self.assertTrue(stopping.wait(1))
            recovered.set()
            recovery.join(1)
            self.assertFalse(recovery.is_alive())
            self.assertFalse(recovery_results[0].ok)
            self.assertEqual(self.factory.call_count, 1)
        finally:
            recovered.set()
            stopped.set()
            recovery.join(2)
            if closer.ident is not None:
                closer.join(2)
        self.assertTrue(close_results[0].ok)
        self.assertEqual(self.backend.closed, 1)

    def test_real_device_successful_close_supersedes_interrupt_failure(self):
        device = self.control.start().unwrap()
        interrupt_error = OSError("interrupt failed")
        self.backend.interrupt = MagicMock(side_effect=interrupt_error)
        self.io.close = MagicMock()
        capture = MagicMock()
        device._droidcast = capture

        self.assertTrue(self.control.close().ok)
        self.assertTrue(self.control.close().ok)

        self.assertEqual(self.backend.closed, 1)
        self.io.close.assert_called_once_with()
        capture.close.assert_called_once_with()
        self.assertIsNone(device._close_error)
        self.assertIsNone(device._interrupt_error)
        self.assertIsNone(self.control._helper_cleanup_error)
        replacement = self.control.start().unwrap()
        self.assertIsNot(replacement, device)
        self.assertEqual(replacement.device_id, "USB-A")
        self.assertEqual(self.factory.call_count, 2)
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.backend.sent, [])

    def test_real_device_cleanup_failure_retains_interrupt_diagnostic(self):
        device = self.control.start().unwrap()
        interrupt_error = OSError("interrupt failed")
        cleanup_error = OSError("owned control could not be closed")
        self.backend.interrupt = MagicMock(side_effect=interrupt_error)
        self.backend.stop = MagicMock(side_effect=cleanup_error)
        self.io.close = MagicMock()
        capture = MagicMock()
        device._droidcast = capture

        result = self.control.close()

        self.assertFalse(result.ok)
        self.assertIs(result.error.cause, cleanup_error)
        self.assertTrue(cleanup_error.cleanup_failed)
        self.assertIn("interrupt failed", " ".join(cleanup_error.__notes__))
        self.assertIs(device._close_error, cleanup_error)
        self.assertIs(self.control._helper_cleanup_error, cleanup_error)
        self.io.close.assert_called_once_with()
        capture.close.assert_called_once_with()
        self.backend.stop.assert_called_once_with()
        self.assertFalse(self.control.close().ok)
        self.assertFalse(self.control.start().ok)
        self.assertFalse(self.control.recover().ok)
        self.assertEqual(self.factory.call_count, 1)

    def test_real_device_interrupt_does_not_overwrite_prior_cleanup_failure(self):
        device = self.control.start().unwrap()
        cleanup_error = OSError("owned control could not be closed")
        interrupt_error = OSError("capture interrupt failed")
        capture = MagicMock()
        capture.interrupt.side_effect = interrupt_error
        device._droidcast = capture
        self.backend.stop = MagicMock(side_effect=cleanup_error)

        with self.assertRaises(TouchFailure) as raised:
            device.rebuild_input()
        self.assertTrue(raised.exception.cleanup_failed)
        self.assertIs(device._close_error, cleanup_error)

        with self.assertRaises(OSError) as raised:
            device.interrupt_io()
        self.assertIs(raised.exception, interrupt_error)
        self.assertIs(device._close_error, cleanup_error)

        result = self.control.close()
        self.assertFalse(result.ok)
        self.assertIs(result.error.cause, cleanup_error)
        self.assertTrue(cleanup_error.cleanup_failed)
        self.assertIn("capture interrupt failed", " ".join(cleanup_error.__notes__))
        capture.close.assert_called_once_with()
        self.assertFalse(self.control.start().ok)
        self.assertFalse(self.control.recover().ok)
        self.assertEqual(self.factory.call_count, 1)

    def test_failed_control_cleanup_remains_visible_and_blocks_replacement(self):
        self.control.start().unwrap()

        def broken_stop():
            self.backend.closed += 1
            raise OSError("owned control could not be closed")

        self.backend.stop = broken_stop
        self.adb.rows = [("USB-A", "offline")]
        self.adb.on_recover = lambda: setattr(self.adb, "rows", [("USB-A", "device")])
        self.assertFalse(self.control.recover().ok)
        self.assertFalse(self.control.close().ok)
        self.assertFalse(self.control.close().ok)
        self.assertFalse(self.control.start().ok)
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.backend.closed, 1)


if __name__ == "__main__":
    unittest.main()
