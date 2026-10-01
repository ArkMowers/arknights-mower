"""scrcpy ownership and delivery through the device application boundary."""

import errno
import os
import socket
import struct
import unittest
from threading import Event, Lock, RLock, Thread
from unittest.mock import MagicMock, patch

from arknights_mower.tests.device_session_tests import ADB, Clock, Preflight, Simulator
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.socket import Socket
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.scrcpy import Scrcpy
from arknights_mower.utils.device.scrcpy.core import Client
from arknights_mower.utils.device.session import DeviceSession


class Wire:
    def __init__(self, owner, role, data=b""):
        self.owner, self.role, self.data = owner, role, data
        self.closed = 0
        self.sent = []
        self.timeout = None
        self.failure = None
        self.close_failure = None

    def settimeout(self, seconds):
        self.timeout = seconds

    def recv(self, size):
        if self.failure:
            raise self.failure
        if self.owner.fragment and self.role == "video":
            size = min(size, 3)
        data, self.data = self.data[:size], self.data[size:]
        return data

    def recv_into(self, target, size):
        data = self.recv(size)
        target[: len(data)] = data
        return len(data)

    def sendall(self, data):
        self.sent.append(data)
        if self.failure:
            raise self.failure

    def close(self):
        self.closed += 1
        self.owner.events.append(("close", self.role))
        if self.close_failure:
            raise self.close_failure

    def shutdown(self, how):
        pass


class Transport:
    def __init__(self):
        self.wires = []
        self.events = []
        self.commands = []
        self.streams = 0
        self.fragment = False
        self.video = (
            b"\0" + b"Android".ljust(64, b"\0") + struct.pack(">HH", 1920, 1080)
        )

    def push(self, path, data):
        self.events.append(("deploy", path))

    def socket(self, role, data):
        wire = Wire(self, role, data)
        self.wires.append(wire)
        result = object.__new__(Socket)
        result.owner_pid, result._close_lock = os.getpid(), Lock()
        result._interrupted = False
        result.sock, result.timeout = wire, 5
        return result

    def stream_shell(self, command):
        self.commands.append(command)
        return self.socket("server", b"[server] started")

    def stream(self, command):
        role = "video" if self.streams % 2 == 0 else "control"
        self.streams += 1
        return self.socket(role, self.video if role == "video" else b"")


class Handle:
    device_id = "USB-A"

    def __init__(self, transport, **options):
        self.scrcpy = Scrcpy(transport, **options)

    def close(self):
        self.scrcpy.stop()


class Adapter:
    def __init__(self, transport, **options):
        self.transport, self.options = transport, options

    def open_verified(self, configuration, result):
        return Handle(self.transport, **self.options)

    def rebind(self, handle, result):
        handle.scrcpy.start()
        handle.device_id = result.serial


class ScrcpyTests(unittest.TestCase):
    def setUp(self):
        self.transport, self.clock = Transport(), Clock()
        self.conf = Conf(device={"last_serial": "USB-A"})
        self.enterContext(
            patch("arknights_mower.utils.device.io_budget.csleep", self.clock.sleep)
        )
        self.enterContext(patch("pathlib.Path.read_bytes", return_value=b"bundled jar"))
        self.enterContext(
            patch(
                "arknights_mower.utils.device.scrcpy.core.time.monotonic",
                self.clock.monotonic,
            )
        )

    def control(self, session=None, **options):
        app = DeviceControl(
            lambda: self.conf,
            Adapter(self.transport, **options),
            preflight=Preflight(),
            session=session,
        )
        self.addCleanup(app.close)
        return app

    def test_reinitialization_closes_owned_streams_before_deploying_again(self):
        app = self.control()
        self.assertTrue(app.start().ok)
        first = list(self.transport.wires)
        self.transport.events.clear()
        self.assertTrue(app.execute(lambda handle: handle.scrcpy.start()).ok)
        self.assertTrue(all(wire.closed == 1 for wire in first))
        self.assertEqual(
            [event[0] for event in self.transport.events],
            ["close", "close", "close", "deploy"],
        )
        self.assertEqual(sum(wire.closed == 0 for wire in self.transport.wires), 3)
        self.assertTrue(all("Server 1.21 " in cmd for cmd in self.transport.commands))
        self.assertTrue(app.close().ok)
        self.assertTrue(app.close().ok)
        self.assertTrue(all(wire.closed == 1 for wire in self.transport.wires))

    def probe_client(self, stream):
        helper = object.__new__(Client)
        helper.owner_pid = os.getpid()
        helper._interrupted = False
        helper.control_socket_lock = RLock()
        helper.control_socket = stream
        helper.stop = lambda: None
        return helper

    def test_control_probe_detects_eof_without_sending_input(self):
        local, peer = socket.socketpair()
        self.addCleanup(local.close)
        peer.close()
        helper = self.probe_client(type("Stream", (), {"sock": local})())
        self.assertFalse(helper.check_control_alive())

    def test_control_probe_is_nonblocking_and_preserves_pending_data(self):
        local, peer = socket.socketpair()
        self.addCleanup(local.close)
        self.addCleanup(peer.close)
        local.settimeout(7)
        helper = self.probe_client(type("Stream", (), {"sock": local})())
        self.assertTrue(helper.check_control_alive())
        peer.sendall(b"pending clipboard")
        self.assertTrue(helper.check_control_alive())
        self.assertEqual(local.gettimeout(), 7)
        self.assertEqual(local.recv(64), b"pending clipboard")

    def test_control_probe_detects_detached_stream(self):
        helper = self.probe_client(type("Stream", (), {"sock": None})())
        self.assertFalse(helper.check_control_alive())

    def test_control_probe_keeps_unknown_read_failures_terminal(self):
        connection = MagicMock()
        connection.fileno.return_value = 7
        helper = self.probe_client(type("Stream", (), {"sock": connection})())
        for failure in (socket.timeout("probe timeout"), OSError("probe denied")):
            with self.subTest(failure=type(failure).__name__):
                connection.recv.side_effect = failure
                with self.assertRaises(type(failure)):
                    helper.check_control_alive()
                connection.sendall.assert_not_called()

    def test_control_probe_detects_reset_but_not_would_block(self):
        connection = MagicMock()
        connection.fileno.return_value = 7
        helper = self.probe_client(type("Stream", (), {"sock": connection})())
        for failure, alive in (
            (ConnectionResetError("peer reset"), False),
            (BlockingIOError("no pending data"), True),
        ):
            with self.subTest(alive=alive):
                connection.recv.side_effect = failure
                self.assertEqual(helper.check_control_alive(), alive)

    def test_control_probe_concurrent_close_is_known_before_input(self):
        connection = MagicMock()
        connection.fileno.return_value = 7
        helper = self.probe_client(type("Stream", (), {"sock": connection})())

        def closed(*args):
            connection.fileno.return_value = -1
            raise OSError(errno.EBADF, "socket closed")

        connection.recv.side_effect = closed
        self.assertFalse(helper.check_control_alive())
        connection.settimeout.assert_called_once_with(0)
        connection.sendall.assert_not_called()

    def test_control_probe_close_during_timeout_restore_is_not_hidden_failure(self):
        connection = MagicMock()
        connection.gettimeout.return_value = 7
        connection.fileno.return_value = 7
        connection.recv.return_value = b"pending"
        helper = self.probe_client(type("Stream", (), {"sock": connection})())

        def settimeout(seconds):
            if seconds != 0:
                connection.fileno.return_value = -1
                raise OSError(errno.EBADF, "socket closed")

        connection.settimeout.side_effect = settimeout
        self.assertFalse(helper.check_control_alive())
        connection.sendall.assert_not_called()

    def test_control_probe_checks_cancellation_after_restoring_timeout(self):
        connection = MagicMock()
        connection.gettimeout.return_value = 7
        connection.fileno.return_value = 7
        connection.recv.return_value = b"pending"
        helper = self.probe_client(type("Stream", (), {"sock": connection})())
        with patch(
            "arknights_mower.utils.device.scrcpy.core.budget_sleep",
            side_effect=[None, MowerExit("cancelled")],
        ):
            with self.assertRaises(MowerExit):
                helper.check_control_alive()
        connection.settimeout.assert_any_call(0)
        connection.settimeout.assert_any_call(7)
        connection.recv.assert_called_once_with(1, socket.MSG_PEEK)
        connection.sendall.assert_not_called()

    def test_control_probe_busy_lock_is_unknown_without_reading_or_sending(self):
        connection = MagicMock()
        connection.fileno.return_value = 7
        connection.recv.return_value = b"pending"
        helper = self.probe_client(type("Stream", (), {"sock": connection})())
        acquired, release = Event(), Event()

        def clipboard_reader():
            with helper.control_socket_lock:
                acquired.set()
                release.wait(1)

        worker = Thread(target=clipboard_reader)
        worker.start()
        try:
            self.assertTrue(acquired.wait(1))
            with self.assertRaises(TimeoutError):
                helper.check_control_alive()
        finally:
            release.set()
            worker.join(1)
        self.assertFalse(worker.is_alive())
        connection.recv.assert_not_called()
        connection.sendall.assert_not_called()
        connection.settimeout.assert_not_called()

    def test_broken_pipe_after_touch_down_never_restarts_or_replays(self):
        app = self.control()
        helper = app.start().unwrap().scrcpy
        wire = self.transport.wires[-1]
        sendall = wire.sendall

        def send(data):
            if wire.sent:
                wire.failure = BrokenPipeError("touch up delivery unknown")
            sendall(data)

        wire.sendall = send
        result = app.execute(lambda handle: handle.scrcpy.tap(23, 45))
        self.assertFalse(result.ok)
        self.assertEqual(len(wire.sent), 2)
        self.assertEqual(wire.sent[0][:2], b"\x02\x00")
        self.assertEqual(wire.sent[1][:2], b"\x02\x01")
        self.assertEqual(len(self.transport.commands), 1)
        self.assertIs(helper, app._device.scrcpy)

    def test_close_failure_does_not_skip_remaining_owned_resources(self):
        app = self.control()
        self.assertTrue(app.start().ok)
        self.transport.wires[-1].close_failure = OSError("control close failed")
        result = app.close()
        self.assertFalse(result.ok)
        self.assertIn("control close failed", result.error.message)
        self.assertTrue(all(wire.closed == 1 for wire in self.transport.wires))
        self.assertFalse(app.close().ok)
        self.assertTrue(all(wire.closed == 1 for wire in self.transport.wires))

    def test_startup_deadline_closes_the_owned_server_without_opening_input(self):
        app = self.control(connection_timeout=100)
        result = app.start()
        self.assertFalse(result.ok)
        self.assertIn("scrcpy", result.error.message)
        self.assertEqual(self.clock.now, 0.1)
        self.assertEqual(len(self.transport.wires), 1)
        self.assertEqual(self.transport.wires[0].closed, 1)

    def test_disconnected_key_operation_fails_instead_of_silently_succeeding(self):
        app = self.control()
        self.assertTrue(app.start().ok)

        def disconnected_key(handle):
            handle.scrcpy.stop()
            handle.scrcpy.control.keycode(4)

        result = app.execute(disconnected_key)
        self.assertFalse(result.ok)
        self.assertIn("scrcpy", result.error.message)
        self.assertEqual(sum(len(wire.sent) for wire in self.transport.wires), 0)

    def test_fragmented_handshake_still_accepts_the_original_control_protocol(self):
        self.transport.fragment = True
        app = self.control()
        self.assertTrue(app.start().ok)
        self.assertTrue(app.execute(lambda handle: handle.scrcpy.tap(23, 45)).ok)
        sent = self.transport.wires[-1].sent
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0][:2], b"\x02\x00")
        self.assertEqual(sent[1][:2], b"\x02\x01")
        self.assertEqual(struct.unpack(">iiHH", sent[0][10:22]), (23, 45, 1920, 1080))

    def test_truncated_handshake_closes_every_partially_initialized_resource(self):
        self.transport.video = self.transport.video[:-1]
        app = self.control()
        self.assertFalse(app.start().ok)
        self.assertEqual(len(self.transport.wires), 3)
        self.assertTrue(all(wire.closed == 1 for wire in self.transport.wires))
        app.close()
        self.assertTrue(all(wire.closed == 1 for wire in self.transport.wires))

    def test_unknown_tap_swipe_or_key_send_is_not_repeated(self):
        operations = (
            lambda helper: helper.tap(23, 45),
            lambda helper: helper.swipe(23, 45, 46, 90, 0.02),
            lambda helper: helper.control.keycode(4),
        )
        for operation in operations:
            with self.subTest(operation=operations.index(operation)):
                app = self.control()
                self.assertTrue(app.start().ok)
                wire = self.transport.wires[-1]
                wire.failure = socket.timeout("delivery unknown")
                starts = len(self.transport.commands)
                result = app.execute(lambda handle: operation(handle.scrcpy))
                self.assertFalse(result.ok)
                self.assertIn("delivery unknown", result.error.message)
                self.assertEqual(len(wire.sent), 1)
                self.assertEqual(len(self.transport.commands), starts)
                self.assertEqual(self.conf.device.touch_backend, "scrcpy")
                self.assertTrue(app.close().ok)

    def test_disconnect_recovery_replaces_owned_resources_without_duplicate_server(
        self,
    ):
        adb, simulator = ADB(), Simulator()
        adb.rows, adb.boot = [("USB-A", "device")], "1"
        app = self.control(session=DeviceSession(adb, simulator, clock=self.clock))
        self.assertTrue(app.start().ok)
        first = list(self.transport.wires)
        adb.rows = [("USB-A", "offline")]
        adb.on_recover = lambda: setattr(adb, "rows", [("USB-A", "device")])
        self.transport.events.clear()
        self.assertTrue(app.recover().ok)
        self.assertTrue(all(wire.closed == 1 for wire in first))
        self.assertEqual(
            [event[0] for event in self.transport.events],
            ["close", "close", "close", "deploy"],
        )
        self.assertEqual(sum(wire.closed == 0 for wire in self.transport.wires), 3)
        self.assertEqual(adb.actions, ["USB-A"])
        self.assertEqual(simulator.actions, [])


if __name__ == "__main__":
    unittest.main()
