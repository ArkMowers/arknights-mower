"""Startup helpers consume one deadline, including fragmented socket I/O."""

import socket
import unittest
from unittest.mock import MagicMock, patch

from arknights_mower.utils.device.adb_client.session import Session
from arknights_mower.utils.device.adb_client.socket import Socket
from arknights_mower.utils.device.adb_client.utils import run_cmd
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.device.scrcpy.core import Client as Scrcpy


class Clock:
    def __init__(self, deadline=1):
        self.now = 0
        self.deadline = deadline

    def remaining(self):
        if self.now >= self.deadline:
            raise DeviceRecoveryError("shared deadline exhausted")
        return self.deadline - self.now

    def sleep(self, seconds):
        self.now += seconds


class DeviceIOBudgetTests(unittest.TestCase):
    def test_fragmented_reads_recalculate_the_remaining_deadline(self):
        for method in (
            lambda stream: stream.recv_exactly(3),
            lambda stream: stream.recv_all(),
        ):
            with self.subTest(method=method):
                clock = Clock()
                raw = MagicMock()

                def fragment(buffer, size):
                    clock.now += 0.6
                    buffer[0] = 42
                    return 1

                raw.recv_into.side_effect = fragment
                with (
                    patch(
                        "arknights_mower.utils.device.adb_client.socket.socket.create_connection",
                        return_value=raw,
                    ),
                    self.assertRaisesRegex(DeviceRecoveryError, "shared deadline"),
                    device_io_budget(clock.remaining),
                ):
                    stream = Socket(("127.0.0.1", 5037), 5)
                    method(stream)
                self.assertEqual(raw.recv_into.call_count, 2)
                self.assertEqual(raw.settimeout.call_args_list[0].args, (1,))
                self.assertAlmostEqual(raw.settimeout.call_args_list[1].args[0], 0.4)
                stream.close()

    def test_persistent_socket_restores_its_normal_timeout_after_startup(self):
        clock = Clock()
        raw = MagicMock()
        with patch(
            "arknights_mower.utils.device.adb_client.socket.socket.create_connection",
            return_value=raw,
        ) as connect:
            with device_io_budget(clock.remaining):
                stream = Socket(("127.0.0.1", 5037), 5)
                clock.now = 0.75
                stream.send(b"request")
            stream.send(b"next request")
        connect.assert_called_once_with(("127.0.0.1", 5037), timeout=1)
        self.assertEqual(
            [call.args[0] for call in raw.settimeout.call_args_list], [0.25, 5]
        )
        self.assertEqual(raw.sendall.call_count, 2)
        stream.close()

    def test_expired_request_does_not_open_a_fresh_retry_socket(self):
        clock = Clock()
        transport = MagicMock()

        def timed_out(data):
            clock.now = 1
            raise socket.timeout("deadline")

        transport.send.side_effect = timed_out
        with (
            patch(
                "arknights_mower.utils.device.adb_client.session.Socket",
                return_value=transport,
            ) as connect,
            self.assertRaisesRegex(DeviceRecoveryError, "shared deadline"),
            device_io_budget(clock.remaining),
        ):
            Session().run("host:devices")
        connect.assert_called_once()
        transport.close.assert_called_once()

    def test_subprocess_uses_remaining_time_and_rejects_a_late_result(self):
        clock = Clock()

        def late_result(*args, **kwargs):
            self.assertGreater(kwargs["timeout"], 0)
            self.assertLessEqual(kwargs["timeout"], 1)
            clock.now = 1
            return b"success"

        with (
            patch(
                "arknights_mower.utils.device.adb_client.server.probe_adb_server",
                return_value=None,
            ),
            patch(
                "arknights_mower.utils.device.adb_client.utils.subprocess.check_output",
                side_effect=late_result,
            ) as command,
            self.assertRaisesRegex(DeviceRecoveryError, "shared deadline"),
            device_io_budget(clock.remaining),
        ):
            run_cmd(["verified-adb", "-s", "USB-123", "shell", "wm", "size"])
        command.assert_called_once()

    def test_scrcpy_startup_wait_cannot_outlive_the_session_deadline(self):
        clock = Clock(0.2)
        client = MagicMock()
        stream = client.stream_shell.return_value
        stream.recv.return_value = b"[server] started"
        with (
            patch("pathlib.Path.read_bytes", return_value=b"jar"),
            patch(
                "arknights_mower.utils.device.io_budget.csleep", side_effect=clock.sleep
            ),
            self.assertRaisesRegex(DeviceRecoveryError, "shared deadline"),
            device_io_budget(clock.remaining),
        ):
            Scrcpy(client)
        self.assertEqual(clock.now, 0.2)
        stream.close.assert_called_once()
        client.stream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
