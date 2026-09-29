"""Owned native touch worker lifecycle, replacing vendor and process I/O."""

import os
import unittest
from threading import Event, Thread
from unittest.mock import MagicMock, call, patch

from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.mumu12ipc.core import MuMuIpcError
from arknights_mower.utils.device.mumu12ipc.input import MuMuInputSession, _input_worker


class MuMuInputSessionTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch.object(
                config,
                "conf",
                Conf(
                    device={
                        "preset_id": "windows.mumu12",
                        "installation_path": "MuMu",
                        "manager_path": "MuMu/MuMuManager.exe",
                        "instance_id": "3",
                        "game_package": "com.hypergryph.arknights",
                    }
                ),
            )
        )
        self.manager = self.enterContext(
            patch("arknights_mower.utils.device.mumu12ipc.input.subprocess.run")
        )
        self.manager.return_value.stdout = "4.1.21"
        self.context = self.enterContext(
            patch(
                "arknights_mower.utils.device.mumu12ipc.input.multiprocessing.get_context"
            )
        ).return_value
        self.channel, self.child = MagicMock(), MagicMock()
        self.context.Pipe.return_value = self.channel, self.child
        self.process = self.context.Process.return_value
        self.process.pid = 123
        self.process.is_alive.return_value = False
        self.channel.poll.return_value = True
        self.channel.recv.return_value = ("ok", "", None)

    def session(self):
        result = MuMuInputSession(MagicMock(profile=config.conf.device))
        self.addCleanup(result.close)
        return result

    def test_worker_uses_the_verified_runtime_package(self):
        profile = config.conf.device.model_copy(
            update={"game_package": "com.hypergryph.arknights.bilibili"}
        )
        session = MuMuInputSession(MagicMock(profile=profile))
        self.addCleanup(session.close)
        self.assertEqual(
            self.context.Process.call_args.kwargs["args"][2], profile.game_package
        )
        self.assertEqual(config.conf.device.game_package, "com.hypergryph.arknights")

    def test_close_releases_owned_finished_worker_once_and_rejects_new_input(self):
        session = self.session()
        session.tap(20, 30, hold_time=0)
        self.assertEqual(
            self.channel.send.call_args_list[0].args, (("touch_down", (20, 30)),)
        )
        session.close()
        session.close()
        self.process.join.assert_called_once_with(timeout=1)
        self.process.terminate.assert_not_called()
        self.process.close.assert_called_once_with()
        self.channel.close.assert_called_once_with()
        self.child.close.assert_called_once_with()
        with self.assertRaisesRegex(MuMuIpcError, "关闭"):
            session.tap(20, 30)

    def test_worker_failure_keeps_native_code_and_prevents_replay(self):
        session = self.session()
        self.channel.recv.return_value = ("error", "touch_down failed: -5", -5)
        for _ in range(2):
            with self.assertRaises(MuMuIpcError) as raised:
                session.tap(20, 30)
            self.assertEqual(raised.exception.return_code, -5)
        self.channel.send.assert_called_once_with(("touch_down", (20, 30)))
        self.process.start.assert_called_once_with()

    def test_native_input_timeout_is_finite_and_never_replayed(self):
        session = self.session()
        self.channel.poll.return_value = False
        with patch("arknights_mower.utils.device.mumu12ipc.input.INPUT_TIMEOUT", 0.01):
            for _ in range(2):
                with self.assertRaisesRegex(TimeoutError, "结果未知"):
                    session.touch_down(20, 30)
        self.channel.send.assert_called_once_with(("touch_down", (20, 30)))

    def test_manager_query_has_finite_budget_and_invalid_version_starts_no_worker(self):
        self.manager.return_value.stdout = "invalid version"
        with self.assertRaises(ValueError):
            self.session()
        self.assertLessEqual(self.manager.call_args.kwargs["timeout"], 5)
        self.context.Process.assert_not_called()
        self.context.Pipe.assert_not_called()

    def test_initialization_failure_closes_owned_worker_and_cannot_send_input(self):
        self.channel.recv.return_value = ("error", "native connect failed", -2)
        with self.assertRaises(MuMuIpcError) as raised:
            self.session()
        self.assertEqual(raised.exception.return_code, -2)
        self.channel.send.assert_not_called()
        self.channel.close.assert_called_once_with()
        self.process.close.assert_called_once_with()

    def test_failed_process_construction_closes_both_pipe_ends(self):
        self.context.Process.side_effect = OSError("create failed")
        with self.assertRaisesRegex(OSError, "create failed"):
            self.session()
        self.child.close.assert_called_once_with()
        self.channel.close.assert_called_once_with()

    def test_failed_start_closes_unstarted_process_without_join_or_termination(self):
        self.process.start.side_effect = OSError("start failed")
        self.process.pid = None
        with self.assertRaisesRegex(OSError, "start failed"):
            self.session()
        self.process.close.assert_called_once_with()
        self.process.join.assert_not_called()
        self.process.terminate.assert_not_called()
        self.child.close.assert_called_once_with()
        self.channel.close.assert_called_once_with()

    def test_inherited_session_never_closes_foreign_process_or_pipe(self):
        session = self.session()
        with patch("os.getpid", return_value=os.getpid() + 1):
            session.close()
            with self.assertRaisesRegex(MuMuIpcError, "不属于"):
                session.tap(20, 30)
        self.process.join.assert_not_called()
        self.process.terminate.assert_not_called()
        self.process.close.assert_not_called()
        self.channel.close.assert_not_called()

    def test_close_interrupts_pending_native_reply_without_waiting_for_input_lock(self):
        session = self.session()
        polling = Event()

        def pending(timeout):
            polling.set()
            return False

        self.channel.poll.side_effect = pending
        errors = []

        def touch():
            try:
                session.tap(20, 30)
            except Exception as exc:
                errors.append(exc)

        worker = Thread(target=touch)
        worker.start()
        try:
            self.assertTrue(polling.wait(1))
            self.process.is_alive.return_value = True
            self.process.terminate.side_effect = lambda: setattr(
                self.process.is_alive, "return_value", False
            )
            session.interrupt()
            worker.join(1)
            self.assertFalse(worker.is_alive())
            self.process.join.assert_not_called()
            self.channel.close.assert_not_called()
            session.close()
        finally:
            worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.process.terminate.assert_called_once_with()
        self.process.kill.assert_not_called()
        self.channel.send.assert_called_once_with(("touch_down", (20, 30)))
        for join_call in self.process.join.call_args_list:
            self.assertLessEqual(join_call.kwargs["timeout"], 1)

    def test_close_interrupts_long_hold_without_sending_remaining_gesture(self):
        session = self.session()
        pressed = Event()
        self.channel.send.side_effect = lambda command: pressed.set()
        errors = []

        def tap():
            try:
                session.tap(20, 30, hold_time=60)
            except Exception as exc:
                errors.append(exc)

        worker = Thread(target=tap)
        worker.start()
        try:
            self.assertTrue(pressed.wait(1))
            session.close()
        finally:
            worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.channel.send.assert_called_once_with(("touch_down", (20, 30)))

    def test_failed_pipe_close_does_not_skip_process_cleanup_or_repeat(self):
        session = MuMuInputSession(MagicMock())
        self.channel.close.side_effect = OSError("pipe failed")
        for _ in range(2):
            with self.assertRaisesRegex(OSError, "pipe failed"):
                session.close()
        # A latched failure remains visible without retrying cleanup.
        self.channel.close.assert_called_once_with()
        self.process.close.assert_called_once_with()


class MuMuInputWorkerTests(unittest.TestCase):
    def run_worker(self, commands, *, version="4.1.21", result=0):
        channel = MagicMock()
        channel.recv.side_effect = [*commands, EOFError()]
        dll = MagicMock()
        dll.nemu_connect.return_value = 7
        dll.nemu_get_display_id.return_value = 0
        dll.nemu_input_event_touch_down.return_value = result
        dll.nemu_input_event_touch_up.return_value = 0
        dll.nemu_input_event_key_down.return_value = 0
        dll.nemu_input_event_key_up.return_value = 0
        with (
            patch("ctypes.CDLL", return_value=dll),
            patch("arknights_mower.utils.device.mumu12ipc.core.logger"),
        ):
            _input_worker(
                "MuMu",
                "3",
                "com.hypergryph.arknights",
                tuple(int(value) for value in version.split(".")) >= (4, 1, 21),
                channel,
            )
        return dll, channel

    def test_worker_delivers_native_back_key_down_and_up(self):
        dll, channel = self.run_worker([("key_down", (1,)), ("key_up", (1,))])
        dll.assert_has_calls(
            [
                call.nemu_input_event_key_down(7, 0, 1),
                call.nemu_input_event_key_up(7, 0, 1),
            ]
        )
        self.assertEqual(channel.send.call_args_list, [call(("ok", "", None))] * 3)
        dll.nemu_disconnect.assert_called_once_with(7)

    def test_worker_preserves_existing_native_coordinate_mapping(self):
        for version, expected in (
            ("4.1.21", (7, 0, 20, 30)),
            ("4.1.20", (7, 0, 1050, 20)),
        ):
            with self.subTest(version=version):
                dll, channel = self.run_worker(
                    [("touch_down", (20, 30)), ("touch_up", ())], version=version
                )
                dll.nemu_input_event_touch_down.assert_called_once_with(*expected)
                dll.nemu_input_event_touch_up.assert_called_once_with(7, 0)
                dll.nemu_disconnect.assert_called_once_with(7)
                self.assertEqual(channel.send.call_count, 3)
                channel.close.assert_called_once_with()

    def test_native_error_stops_input_and_releases_only_its_connection(self):
        dll, channel = self.run_worker(
            [("touch_down", (20, 30)), ("touch_up", ())], result=-5
        )
        self.assertEqual(
            channel.send.call_args.args[0], ("error", "touch_down failed: -5", -5)
        )
        dll.nemu_input_event_touch_up.assert_not_called()
        dll.nemu_disconnect.assert_called_once_with(7)
        channel.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
