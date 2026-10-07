import os
import socket
import subprocess
import unittest
from unittest.mock import MagicMock, Mock, patch

from arknights_mower.utils.device.adb_client.server import (
    SharedADBError,
    SharedADBHandshakeTimeout,
    guard_adb,
    kill_adb_server,
    probe_adb_server,
    run_adb,
)
from arknights_mower.utils.device.endpoint_identity import emulator_connect_target


class SharedADBTests(unittest.TestCase):
    def test_unverified_client_version_never_executes_device_command(self):
        for output in (
            b"unknown executable",
            b"Android Debug Bridge version 1.0.41\nAndroid Debug Bridge version 1.0.40\n",
        ):
            with self.subTest(output=output):
                run = Mock(return_value=subprocess.CompletedProcess([], 0, output, b""))
                with self.assertRaises(SharedADBError):
                    run_adb(
                        ["adb", "devices"], timeout=5, run=run, probe=lambda timeout: 41
                    )
                self.assertEqual(run.call_count, 1)

    def test_redirected_server_environment_is_not_probed_as_local(self):
        run, probe = Mock(), Mock()
        with patch.dict(os.environ, {"ADB_SERVER_SOCKET": "tcp:other:5037"}):
            with self.assertRaises(SharedADBError):
                run_adb(["adb", "devices"], timeout=5, run=run, probe=probe)
        run.assert_not_called()
        probe.assert_not_called()

    def test_time_spent_checking_version_cannot_extend_command_budget(self):
        now = [0]

        def run(argv, **kwargs):
            now[0] = 5
            return subprocess.CompletedProcess(
                [], 0, b"Android Debug Bridge version 1.0.41", b""
            )

        runner = Mock(side_effect=run)
        with self.assertRaises(SharedADBError):
            run_adb(
                ["adb", "devices"],
                timeout=5,
                run=runner,
                probe=lambda timeout: 41,
                monotonic=lambda: now[0],
            )
        self.assertEqual(runner.call_count, 1)

    def test_compatible_server_is_observed_without_start_or_stop_commands(self):
        run = Mock(
            side_effect=[
                subprocess.CompletedProcess(
                    [], 0, b"Android Debug Bridge version 1.0.41\n", b""
                ),
                subprocess.CompletedProcess([], 0, "devices response", ""),
            ]
        )
        result = run_adb(
            ["adb", "devices"],
            timeout=5,
            run=run,
            probe=lambda timeout: 41,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(result.stdout, "devices response")
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [["adb", "version"], ["adb", "devices"]],
        )
        self.assertTrue(run.call_args.kwargs["text"])
        self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_only_confirmed_absent_server_skips_the_client_comparison(self):
        run = Mock(return_value=subprocess.CompletedProcess([], 0, b"", b""))
        run_adb(
            ["adb", "connect", "127.0.0.1:5555"],
            timeout=5,
            run=run,
            probe=lambda timeout: None,
        )
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["adb", "connect", "127.0.0.1:5555"])

    def test_failed_probe_never_executes_cli(self):
        for error in (socket.timeout("late"), SharedADBError("malformed")):
            with self.subTest(error=error):
                run = Mock()
                with self.assertRaises(SharedADBError):
                    run_adb(
                        ["adb", "devices"],
                        timeout=5,
                        run=run,
                        probe=Mock(side_effect=error),
                    )
                run.assert_not_called()

    def test_probe_version_and_command_share_one_deadline(self):
        now = [0]
        timeouts = []

        def probe(timeout):
            timeouts.append(timeout)
            now[0] += 2
            return 41

        def run(argv, **kwargs):
            timeouts.append(kwargs["timeout"])
            now[0] += 1
            return subprocess.CompletedProcess(
                [], 0, b"Android Debug Bridge version 1.0.41\n", b""
            )

        run_adb(
            ["adb", "devices"],
            timeout=5,
            run=run,
            probe=probe,
            monotonic=lambda: now[0],
        )
        self.assertEqual(timeouts, [5, 3, 2])

    def test_guard_returns_remaining_budget_for_popen_callers(self):
        now = [0]

        def probe(timeout):
            now[0] = 2
            return None

        self.assertEqual(
            guard_adb("adb", timeout=5, probe=probe, monotonic=lambda: now[0]), 3
        )

    def test_global_server_commands_and_redirect_options_are_rejected(self):
        for args in (
            ["kill-server"],
            ["start-server"],
            ["server"],
            ["fork-server"],
            ["nodaemon", "server"],
            ["-H", "other", "devices"],
            ["-P5556", "devices"],
        ):
            with self.subTest(args=args):
                run = Mock()
                probe = Mock()
                with self.assertRaises(SharedADBError):
                    run_adb(["adb", *args], timeout=5, run=run, probe=probe)
                run.assert_not_called()
                probe.assert_not_called()

    def test_mismatching_client_never_executes_a_server_command(self):
        run = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, b"Android Debug Bridge version 1.0.40\n", b""
            )
        )
        with self.assertRaisesRegex(SharedADBError, "版本不一致"):
            run_adb(["adb", "devices"], timeout=5, run=run, probe=lambda timeout: 41)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["adb", "version"])


class ServerProbeTests(unittest.TestCase):
    def connection(self):
        factory = MagicMock()
        connection = factory.return_value.__enter__.return_value
        return factory, connection

    def test_raw_probe_reads_fragmented_version_with_remaining_receive_timeouts(self):
        factory, connection = self.connection()
        now = [0]
        chunks = iter([b"OK", b"AY", b"00", b"04", b"00", b"29"])

        def receive(length):
            now[0] += 1
            return next(chunks)

        connection.recv.side_effect = receive
        self.assertEqual(
            probe_adb_server(10, socket_factory=factory, monotonic=lambda: now[0]), 41
        )
        connection.connect.assert_called_once_with(("127.0.0.1", 5037))
        connection.sendall.assert_called_once_with(b"000chost:version")
        self.assertEqual(
            [call.args[0] for call in connection.settimeout.call_args_list],
            [10, 10, 10, 9, 8, 7, 6, 5],
        )

    def test_refused_connect_is_the_only_absence_result(self):
        for error in (ConnectionRefusedError(), socket.timeout(), PermissionError()):
            with self.subTest(error=error):
                factory, connection = self.connection()
                connection.connect.side_effect = error
                if isinstance(error, ConnectionRefusedError):
                    self.assertIsNone(probe_adb_server(5, socket_factory=factory))
                else:
                    with self.assertRaises(SharedADBError):
                        probe_adb_server(5, socket_factory=factory)
                connection.sendall.assert_not_called()

    def test_malformed_or_truncated_response_is_never_absence(self):
        for chunks in (
            [b"FAIL"],
            [b"OKAY", b"ffff"],
            [b"OKAY", b"0004", b"oops"],
            [b""],
        ):
            with self.subTest(chunks=chunks):
                factory, connection = self.connection()
                connection.recv.side_effect = chunks
                with self.assertRaises(SharedADBError):
                    probe_adb_server(5, socket_factory=factory)

    def test_an_unanswered_listener_supplies_recovery_evidence_at_either_phase(self):
        for stage in ("connect", "handshake"):
            with self.subTest(stage=stage):
                factory, connection = self.connection()
                if stage == "connect":
                    connection.connect.side_effect = socket.timeout("connect stalled")
                else:
                    connection.recv.side_effect = socket.timeout("stalled")
                with self.assertRaises(SharedADBHandshakeTimeout) as raised:
                    probe_adb_server(5, socket_factory=factory)
                # One verdict names both phases without claiming a connection.
                self.assertIn("未完成主机握手", str(raised.exception))
                self.assertNotIn("已连接", str(raised.exception))

    def test_connect_failure_that_is_not_a_timeout_stays_unverified(self):
        for error in (PermissionError(), OSError("network unreachable")):
            with self.subTest(error=error):
                factory, connection = self.connection()
                connection.connect.side_effect = error
                with self.assertRaises(SharedADBError) as raised:
                    probe_adb_server(5, socket_factory=factory)
                self.assertNotIsInstance(raised.exception, SharedADBHandshakeTimeout)

    def test_protocol_errors_and_eof_are_not_recoverable_timeouts(self):
        for chunks in ([b"FAIL"], [b"OKAY", b"0004", b"oops"], [b""]):
            factory, connection = self.connection()
            connection.recv.side_effect = chunks
            with self.assertRaises(SharedADBError) as raised:
                probe_adb_server(5, socket_factory=factory)
            self.assertNotIsInstance(raised.exception, SharedADBHandshakeTimeout)

    def test_explicit_stop_targets_shared_socket_and_validates_fragmented_ack(self):
        factory, connection = self.connection()
        connection.recv.side_effect = [b"OK", b"AY"]
        kill_adb_server(5, socket_factory=factory)
        connection.connect.assert_called_once_with(("127.0.0.1", 5037))
        connection.sendall.assert_called_once_with(b"0009host:kill")
        self.assertEqual(connection.recv.call_count, 2)
        factory.return_value.__exit__.assert_called_once()

    def test_explicit_stop_rejection_or_invalid_ack_fails_promptly(self):
        for response in (b"FAIL", b"oops", b""):
            factory, connection = self.connection()
            connection.recv.return_value = response
            with self.assertRaises(SharedADBError):
                kill_adb_server(5, socket_factory=factory)
            connection.recv.assert_called_once_with(4)
            factory.return_value.__exit__.assert_called_once()

    def test_explicit_stop_ack_timeout_closes_socket(self):
        factory, connection = self.connection()
        connection.recv.side_effect = socket.timeout("ACK stalled")
        with self.assertRaises(SharedADBError):
            kill_adb_server(5, socket_factory=factory)
        factory.return_value.__exit__.assert_called_once()

    def test_explicit_stop_send_error_is_bounded_and_closes_socket(self):
        factory, connection = self.connection()
        connection.sendall.side_effect = socket.timeout("stalled")
        with self.assertRaises(SharedADBError):
            kill_adb_server(5, socket_factory=factory)
        factory.return_value.__exit__.assert_called_once()

    def test_emulator_serial_helper_remains_available_without_routing(self):
        self.assertEqual(emulator_connect_target("emulator-5554"), "emu:5554,5555")
        for serial in (
            "emulator-5555",
            "emulator-1022",
            "emulator-65536",
            "127.0.0.1:5555",
        ):
            self.assertIsNone(emulator_connect_target(serial))


if __name__ == "__main__":
    unittest.main()
