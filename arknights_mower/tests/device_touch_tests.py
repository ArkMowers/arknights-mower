"""Input delivery and backend selection at the device application boundary."""

import tempfile
import unittest
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from arknights_mower.tests.device_mumu_frame_tests import NativeRenderer, connected_ipc
from arknights_mower.tests.device_session_tests import ADB, Clock, Preflight, Simulator
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl, LegacyDeviceAdapter
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
        self.backend.error = OSError("delivery unknown")
        result = self.control.execute(lambda target: target.tap((20, 30)))
        self.assertEqual(result.error.code, "touch_result_unknown")
        self.assertFalse(self.control.execute(lambda target: target.tap((20, 30))).ok)
        self.assertFalse(self.control.recover().ok)
        self.assertFalse(self.control.start().ok)
        self.assertEqual(self.backend.sent, [(20, 30)])
        self.assertEqual(self.conf.model_dump(), before)
        self.assertEqual(self.adb.actions, [])
        self.assertEqual(self.simulator.actions, [])
        self.peer.assert_not_called()
        error = self.control.settings_status()["error"]
        self.assertTrue(error["delivery_unknown"])
        self.assertEqual(error["backend"], "scrcpy")
        self.assertEqual(
            error["alternatives"], [{"backend": "maatouch", "label": "MaaTouch"}]
        )
        self.assertEqual(device.device_id, "USB-A")

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
                self.assertFalse(self.control.recover().ok)
                self.assertFalse(self.control.start().ok)
                self.assertEqual(channel.send.call_args_list, expected)
                self.assertEqual(self.io.sent, [])
                context.Process.return_value.start.assert_called_once()
                channel.close.assert_called_once()

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
