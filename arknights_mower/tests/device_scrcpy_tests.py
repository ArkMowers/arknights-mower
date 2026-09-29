"""scrcpy ownership and delivery through the device application boundary."""

import os
import socket
import struct
import unittest
from threading import Lock
from unittest.mock import patch

from arknights_mower.tests.device_session_tests import ADB, Clock, Preflight, Simulator
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.adb_client.socket import Socket
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.scrcpy import Scrcpy
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
