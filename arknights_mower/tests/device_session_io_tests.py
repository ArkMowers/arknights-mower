import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from arknights_mower.tests.device_session_tests import ADB, Clock
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.session import (
    DeviceSession,
    InstanceObservation,
    RecoveryPolicy,
)
from arknights_mower.utils.device.session_io import (
    QUERY_TIMEOUT,
    ProductionSessionADB,
    ProductionSimulator,
)


class SessionADBTests(unittest.TestCase):
    def test_session_adapter_preserves_an_incompatible_shared_server(self):
        run = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, b"Android Debug Bridge version 1.0.40", b""
            )
        )
        adapter = ProductionSessionADB(run=run, probe=lambda timeout: 41)
        with self.assertRaises(SharedADBError):
            adapter.devices("chosen-adb", 5)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["chosen-adb", "version"])

    def test_invalid_saved_adb_falls_back_within_the_same_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = str(Path(folder) / "bad-adb")
            good = str(Path(folder) / "adb.exe")
            run = Mock(
                side_effect=[
                    subprocess.CompletedProcess(
                        [], 0, b"", b"error: invalid executable"
                    ),
                    subprocess.CompletedProcess(
                        [], 0, b"Android Debug Bridge version 1.0.41", b""
                    ),
                ]
            )
            self.assertEqual(
                ProductionSessionADB(probe=lambda timeout: None, run=run).resolve_adb(
                    DeviceProfile(
                        preset_id="windows.ldplayer9",
                        installation_path=folder,
                        adb_path=bad,
                    ),
                    5,
                ),
                good,
            )

    def test_unregistered_tcp_endpoint_can_connect_after_targeted_missing_error(self):
        for error in (
            subprocess.CalledProcessError(
                1,
                ["adb", "disconnect", "127.0.0.1:16384"],
                stderr=b"error: no such device '127.0.0.1:16384'",
            ),
            subprocess.CompletedProcess(
                [], 0, b"error: no such device '127.0.0.1:16384'", b""
            ),
            subprocess.CompletedProcess(
                [], 0, b"", b"error: no such device '127.0.0.1:16384'"
            ),
        ):
            with self.subTest(error=error):
                run = Mock(
                    side_effect=[
                        error,
                        subprocess.CompletedProcess(
                            [], 0, b"connected to 127.0.0.1:16384", b""
                        ),
                    ]
                )
                self.assertTrue(
                    ProductionSessionADB(probe=lambda timeout: None, run=run).recover(
                        "adb", "127.0.0.1:16384", 5
                    )
                )
                self.assertEqual(
                    run.call_args.args[0], ["adb", "connect", "127.0.0.1:16384"]
                )

    def test_error_on_stderr_is_not_success_even_with_zero_exit(self):
        run = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, b"reconnecting USB_123 [device]", b"error: device not found"
            )
        )
        with self.assertRaisesRegex(RuntimeError, "device not found"):
            ProductionSessionADB(probe=lambda timeout: None, run=run).recover(
                "adb", "USB_123", 5
            )

    def test_usb_reconnect_output_for_other_target_or_failure_is_rejected(self):
        for output in (b"reconnecting other [device]", b"reconnecting USB_123 failed"):
            with self.subTest(output=output):
                run = Mock(return_value=subprocess.CompletedProcess([], 0, output, b""))
                self.assertFalse(
                    ProductionSessionADB(probe=lambda timeout: None, run=run).recover(
                        "adb", "USB_123", 5
                    )
                )

    def test_exhausted_deadline_never_sends_the_second_tcp_command(self):
        now = [0]

        def run(argv, **kwargs):
            now[0] = 5
            return subprocess.CompletedProcess(
                [], 0, b"disconnected 127.0.0.1:16384", b""
            )

        runner = Mock(side_effect=run)
        with self.assertRaises(SharedADBError):
            ProductionSessionADB(
                probe=lambda timeout: None, run=runner, monotonic=lambda: now[0]
            ).recover("adb", "127.0.0.1:16384", 5)
        self.assertEqual(runner.call_count, 1)

    def test_saved_adb_is_validated_once_and_kept_for_the_session(self):
        run = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, b"Android Debug Bridge version 1.0.41", b""
            )
        )
        with tempfile.TemporaryDirectory() as folder:
            adb_path = Path(folder) / "chosen-adb.exe"
            profile = DeviceProfile(adb_path=str(adb_path))
            self.assertEqual(
                ProductionSessionADB(probe=lambda timeout: None, run=run).resolve_adb(
                    profile, 5
                ),
                str(adb_path),
            )
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], [str(adb_path), "version"])

    def test_usb_and_emulator_recovery_only_address_the_pinned_target(self):
        for serial, response, command in (
            (
                "USB_123",
                b"reconnecting USB_123 [device]",
                ["adb", "-s", "USB_123", "reconnect"],
            ),
            (
                "emulator-5554",
                b"Connected to emulator on ports 5554,5555",
                ["adb", "connect", "emu:5554,5555"],
            ),
        ):
            with self.subTest(serial=serial):
                run = Mock(
                    return_value=subprocess.CompletedProcess([], 0, response, b"")
                )
                self.assertTrue(
                    ProductionSessionADB(probe=lambda timeout: None, run=run).recover(
                        "adb", serial, 5
                    )
                )
                self.assertEqual(run.call_args.args[0], command)
                self.assertEqual(run.call_count, 1)

    def test_recovery_rejects_misleading_zero_exit_and_nonzero_exit(self):
        for output, code in (
            (b"failed to connect to 127.0.0.1:16384", 0),
            (b"connected to 127.0.0.1:5555", 0),
            (b"connected to 127.0.0.1:16384", 1),
        ):
            with self.subTest(output=output, code=code):
                run = Mock(
                    side_effect=[
                        subprocess.CompletedProcess(
                            [], 0, b"disconnected 127.0.0.1:16384", b""
                        ),
                        subprocess.CompletedProcess([], code, output, b""),
                    ]
                )
                adb = ProductionSessionADB(probe=lambda timeout: None, run=run)
                if code:
                    with self.assertRaises(subprocess.CalledProcessError):
                        adb.recover("adb", "127.0.0.1:16384", 5)
                else:
                    self.assertFalse(adb.recover("adb", "127.0.0.1:16384", 5))

    def test_both_tcp_commands_share_one_deadline(self):
        now = [0]
        calls = []

        def run(argv, **kwargs):
            calls.append(kwargs["timeout"])
            now[0] += 3 if argv[1] == "disconnect" else 1
            output = (
                b"disconnected 127.0.0.1:16384"
                if argv[1] == "disconnect"
                else b"connected to 127.0.0.1:16384"
            )
            return subprocess.CompletedProcess(argv, 0, output, b"")

        self.assertTrue(
            ProductionSessionADB(
                probe=lambda timeout: None, run=run, monotonic=lambda: now[0]
            ).recover("adb", "127.0.0.1:16384", 5)
        )
        self.assertEqual(calls, [5, 2])

    def test_observation_never_connects_or_restarts_the_server(self):
        run = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, b"List of devices attached\nother\tdevice\nphone\toffline\n", b""
            )
        )
        self.assertEqual(
            ProductionSessionADB(probe=lambda timeout: None, run=run).devices(
                "chosen-adb", 5
            ),
            [("other", "device"), ("phone", "offline")],
        )
        self.assertEqual(run.call_args.args[0], ["chosen-adb", "devices"])
        self.assertEqual(run.call_count, 1)

    def test_tcp_recovery_only_disconnects_and_connects_the_pinned_endpoint(self):
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            output = (
                b"disconnected 127.0.0.1:16384"
                if argv[1] == "disconnect"
                else b"connected to 127.0.0.1:16384"
            )
            return subprocess.CompletedProcess(argv, 0, output, b"")

        adb = ProductionSessionADB(probe=lambda timeout: None, run=run)
        self.assertTrue(adb.recover("chosen-adb", "127.0.0.1:16384", 10))
        self.assertEqual(
            [argv for argv, _ in calls],
            [
                ["chosen-adb", "disconnect", "127.0.0.1:16384"],
                ["chosen-adb", "connect", "127.0.0.1:16384"],
            ],
        )
        self.assertTrue(all(0 < args["timeout"] <= 10 for _, args in calls))
        self.assertTrue(all(not args.get("shell", False) for _, args in calls))


class DisplayProbeTests(unittest.TestCase):
    """The readiness probes reuse the read-only preflight I/O plumbing."""

    def test_standard_probe_uses_the_verified_endpoint_without_the_selected_helper(
        self,
    ):
        adapter = ProductionSessionADB()
        adapter.bind(DeviceProfile(screenshot_backend="droidcast"))
        with (
            patch(
                "arknights_mower.utils.device.session_io.capture_adb_frame",
                return_value=np.zeros((1080, 1920, 3), dtype=np.uint8),
            ) as capture,
            patch.object(
                adapter, "_capture_frame", side_effect=AssertionError("selected helper")
            ),
        ):
            self.assertEqual(
                adapter.standard_frame_size("chosen-adb", "USB-A", 2), (1920, 1080)
            )
        capture.assert_called_once_with("chosen-adb", "USB-A")

    def test_standard_probe_rejects_completion_after_its_deadline(self):
        now = [0]
        adapter = ProductionSessionADB(monotonic=lambda: now[0])

        def capture(*args):
            now[0] = 3
            return np.zeros((1080, 1920, 3), dtype=np.uint8)

        with (
            patch(
                "arknights_mower.utils.device.session_io.capture_adb_frame",
                side_effect=capture,
            ),
            self.assertRaises(TimeoutError),
        ):
            adapter.standard_frame_size("chosen-adb", "USB-A", 2)

    def test_display_probe_reuses_the_pinned_adb_command(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(
                argv, 0, b"Physical size: 1920x1080\n", b""
            )

        adapter = ProductionSessionADB(run=run, probe=lambda timeout: None)
        self.assertEqual(
            adapter.display_size("chosen-adb", "USB-A", 5),
            "Physical size: 1920x1080",
        )
        self.assertEqual(calls, [["chosen-adb", "-s", "USB-A", "shell", "wm", "size"]])

    def test_frame_probe_reports_width_and_height_of_the_decoded_frame(self):
        from arknights_mower.utils.device import preflight_io

        profile = DeviceProfile(
            adb_path="chosen-adb",
            last_serial="USB-A",
            screenshot_backend="adb_gzip",
        )
        adapter = ProductionSessionADB(probe=lambda timeout: None)
        adapter.bind(profile)
        with patch.object(
            preflight_io,
            "capture_adb_frame",
            return_value=np.zeros((1080, 1920, 3), dtype=np.uint8),
        ):
            self.assertEqual(adapter.frame_size("chosen-adb", "USB-A", 5), (1920, 1080))

    def test_frame_probe_rejects_a_frame_that_is_not_landscape_1920_by_1080(self):
        from arknights_mower.utils.device import preflight_io
        from arknights_mower.utils.device.screenshot_backend import FrameSizeMismatch

        adapter = ProductionSessionADB(probe=lambda timeout: None)
        adapter.bind(
            DeviceProfile(
                adb_path="chosen-adb",
                last_serial="USB-A",
                screenshot_backend="adb_gzip",
            )
        )
        with (
            patch.object(
                preflight_io,
                "capture_adb_frame",
                return_value=np.zeros((720, 1280, 3), dtype=np.uint8),
            ),
            self.assertRaises(FrameSizeMismatch),
        ):
            adapter.frame_size("chosen-adb", "USB-A", 5)

    def test_unbound_frame_probe_reports_the_missing_binding(self):
        adapter = ProductionSessionADB(probe=lambda timeout: None)
        with self.assertRaises(RuntimeError):
            adapter.frame_size("chosen-adb", "USB-A", 5)


class SimulatorStopBindingTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.presets = ("windows.mumu12", "windows.ldplayer9", "windows.ldplayer14")

    def profile(self, preset):
        manager = self.folder / (
            "MuMuManager.exe" if preset == "windows.mumu12" else "ldconsole.exe"
        )
        manager.touch()
        return DeviceProfile(
            preset_id=preset,
            manager_path=str(manager),
            instance_id="2",
            instance_name="chosen",
            adb_path="unavailable-adb",
            last_serial="127.0.0.1:5559",
        )

    def information(self, profile):
        if profile.preset_id == "windows.mumu12":
            return json.dumps(
                {
                    "2": {
                        "index": 2,
                        "name": profile.instance_name,
                        "is_process_started": True,
                        "is_android_started": True,
                        "adb_port": 16448,
                    }
                }
            ).encode()
        return f"2,{profile.instance_name},0,0,1,223,224\n".encode()

    def commands(self, profile):
        if profile.preset_id == "windows.mumu12":
            return [
                [profile.manager_path, "info", "-v", "2"],
                [profile.manager_path, "api", "-v", "2", "shutdown_player"],
            ]
        return [
            [profile.manager_path, "list2"],
            [profile.manager_path, "quit", "--index", "2"],
        ]

    def test_offline_adb_does_not_block_manager_verified_stop(self):
        for preset in self.presets:
            with self.subTest(preset=preset):
                profile = self.profile(preset)
                before = profile.model_dump()
                run = Mock(
                    side_effect=[
                        subprocess.CompletedProcess(
                            [], 0, self.information(profile), b""
                        ),
                        subprocess.CompletedProcess([], 0, b'{"code":0}', b""),
                    ]
                )
                probe = Mock(side_effect=AssertionError("shutdown cannot use ADB"))
                listeners = Mock(
                    side_effect=AssertionError("shutdown cannot use ports")
                )
                simulator = ProductionSimulator(
                    run=run, probe=probe, listener_ports=listeners
                )

                self.assertTrue(simulator.stop(profile, 10))

                self.assertEqual(
                    [command.args[0] for command in run.call_args_list],
                    self.commands(profile),
                )
                probe.assert_not_called()
                listeners.assert_not_called()
                self.assertEqual(profile.model_dump(), before)
                for command in run.call_args_list:
                    self.assertGreater(command.kwargs["timeout"], 0)
                    self.assertLessEqual(command.kwargs["timeout"], 10)
                    self.assertFalse(command.kwargs.get("shell", False))

    def test_changed_or_ambiguous_identity_never_authorizes_stop(self):
        for preset in self.presets:
            profile = self.profile(preset)
            valid = self.information(profile)
            invalid = (
                valid.replace(b"chosen", b"recreated"),
                b"{}" if preset == "windows.mumu12" else b"0,other,0,0,1,123,124\n",
                b'[{"index":2},{"index":2}]'
                if preset == "windows.mumu12"
                else valid + valid,
                b'{"2":{"index":3}}'
                if preset == "windows.mumu12"
                else b'2,"unterminated,0,0,1,223,224',
            )
            for output in invalid:
                with self.subTest(preset=preset, output=output):
                    before = profile.model_dump()
                    run = Mock(
                        return_value=subprocess.CompletedProcess([], 0, output, b"")
                    )

                    with self.assertRaises(InstanceBindingError):
                        ProductionSimulator(run=run).stop(profile, 10)

                    run.assert_called_once()
                    self.assertEqual(run.call_args.args[0], self.commands(profile)[0])
                    self.assertEqual(profile.model_dump(), before)

    def test_binding_query_and_stop_share_one_deadline(self):
        for preset in self.presets:
            with self.subTest(preset=preset):
                profile = self.profile(preset)
                clock = Clock()
                calls = []

                def run(argv, **options):
                    calls.append((argv, options["timeout"]))
                    query = argv == self.commands(profile)[0]
                    clock.now += 2 if query else 1
                    output = self.information(profile) if query else b'{"code":0}'
                    return subprocess.CompletedProcess(argv, 0, output, b"")

                self.assertTrue(
                    ProductionSimulator(run=run, monotonic=clock.monotonic).stop(
                        profile, 4
                    )
                )

                self.assertEqual([argv for argv, _ in calls], self.commands(profile))
                self.assertEqual([timeout for _, timeout in calls], [3, 2])

    def test_exhausted_query_deadline_never_issues_stop(self):
        for preset in self.presets:
            with self.subTest(preset=preset):
                profile = self.profile(preset)
                clock = Clock()
                calls = []

                def run(argv, **options):
                    calls.append(argv)
                    clock.now += options["timeout"]
                    return subprocess.CompletedProcess(
                        argv, 0, self.information(profile), b""
                    )

                with self.assertRaises(TimeoutError):
                    ProductionSimulator(run=run, monotonic=clock.monotonic).stop(
                        profile, 3
                    )

                self.assertEqual(calls, [self.commands(profile)[0]])

    def test_query_failure_never_issues_stop(self):
        for preset in self.presets:
            with self.subTest(preset=preset):
                profile = self.profile(preset)
                run = Mock(side_effect=subprocess.TimeoutExpired("manager query", 3))

                with self.assertRaises(subprocess.TimeoutExpired):
                    ProductionSimulator(run=run).stop(profile, 10)

                run.assert_called_once()
                self.assertEqual(run.call_args.args[0], self.commands(profile)[0])

    def test_start_keeps_one_lifecycle_command_without_binding_query(self):
        for preset in self.presets:
            with self.subTest(preset=preset):
                profile = self.profile(preset)
                run = Mock(
                    return_value=subprocess.CompletedProcess([], 0, b'{"code":0}', b"")
                )

                self.assertTrue(ProductionSimulator(run=run).start(profile, 10))

                run.assert_called_once()
                expected = self.commands(profile)[1]
                expected = [
                    "launch_player"
                    if argument == "shutdown_player"
                    else "launch"
                    if argument == "quit"
                    else argument
                    for argument in expected
                ]
                self.assertEqual(run.call_args.args[0], expected)

    def test_ldplayer_gb18030_instance_name_remains_verifiable(self):
        for preset in self.presets[1:]:
            with self.subTest(preset=preset):
                profile = self.profile(preset)
                profile.instance_name = "日常号"
                run = Mock(
                    side_effect=[
                        subprocess.CompletedProcess(
                            [], 0, "2,日常号,0,0,1,223,224\n".encode("gb18030"), b""
                        ),
                        subprocess.CompletedProcess([], 0, b"", b""),
                    ]
                )

                self.assertTrue(ProductionSimulator(run=run).stop(profile, 10))

                self.assertEqual(
                    [command.args[0] for command in run.call_args_list],
                    self.commands(profile),
                )


class SimulatorIOTests(unittest.TestCase):
    def test_manager_zero_exit_error_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = Path(folder) / "MuMuManager.exe"
            manager.touch()
            profile = DeviceProfile(
                preset_id="windows.mumu12", manager_path=str(manager), instance_id="2"
            )
            for output in (
                b"launch failed",
                b'{"error_code":7}',
                b'{"2":{"err_code":7}}',
            ):
                with self.subTest(output=output):
                    run = Mock(
                        return_value=subprocess.CompletedProcess([], 0, output, b"")
                    )
                    self.assertFalse(ProductionSimulator(run=run).start(profile, 5))

    def test_ldplayer_observes_and_starts_only_the_bound_index(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = Path(folder) / "ldconsole.exe"
            manager.touch()
            profile = DeviceProfile(
                preset_id="windows.ldplayer9",
                manager_path=str(manager),
                instance_id="2",
                last_serial="emulator-5558",
            )
            run = Mock(
                side_effect=[
                    subprocess.CompletedProcess(
                        [], 0, b"0,other,0,0,1,123,124\n2,chosen,0,0,0,-1,-1\n", b""
                    ),
                    subprocess.CompletedProcess([], 0, b"", b""),
                ]
            )
            simulator = ProductionSimulator(run=run)
            result = simulator.inspect(profile, 3)
            self.assertEqual(result.state, "stopped")
            self.assertIsNone(result.serial)
            self.assertTrue(simulator.start(profile, 3))
            self.assertEqual(
                run.call_args.args[0], [str(manager), "launch", "--index", "2"]
            )

    def test_redroid_lifecycle_and_identity_use_shared_controller(self):
        profile = DeviceProfile(preset_id="linux.redroid", instance_id="a" * 64)
        redroid = Mock()
        redroid.inspect.return_value = InstanceObservation("running", "127.0.0.1:32788")
        redroid.start.return_value = False
        redroid.stop.return_value = False
        run = Mock(side_effect=AssertionError("Legacy Docker command"))
        simulator = ProductionSimulator(run=run, redroid=redroid)
        self.assertEqual(simulator.inspect(profile, 3).serial, "127.0.0.1:32788")
        self.assertFalse(simulator.start(profile, 3))
        self.assertFalse(simulator.stop(profile, 3))
        redroid.inspect.assert_called_once_with(profile, 3)
        redroid.start.assert_called_once_with(profile, 3)
        redroid.stop.assert_called_once_with(profile, 3)
        run.assert_not_called()

    def test_mumu_states_never_treat_missing_status_as_stopped(self):
        for entry, expected in (
            ({"is_process_started": False, "adb_port": 16384}, "stopped"),
            ({"is_process_started": True, "is_android_started": False}, "starting"),
        ):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as folder:
                manager = Path(folder) / "MuMuManager.exe"
                manager.touch()
                profile = DeviceProfile(
                    preset_id="windows.mumu12",
                    manager_path=str(manager),
                    instance_id="2",
                )
                run = Mock(
                    return_value=subprocess.CompletedProcess(
                        [], 0, json.dumps({"2": entry}).encode(), b""
                    )
                )
                result = ProductionSimulator(run=run).inspect(profile, 3)
                self.assertEqual(result.state, expected)
                self.assertIsNone(result.serial)

    def test_mumu_invalid_or_ambiguous_binding_cannot_select_another_instance(self):
        for payload in (
            {"0": {"is_process_started": True, "adb_port": 16384}},
            [{"index": 2}, {"index": 2}],
            {"2": {"index": 3}},
            {"2": {"adb_port": 16384}},
            {"2": {"is_process_started": "false"}},
            {
                "2": {
                    "is_process_started": True,
                    "is_android_started": True,
                    "adb_port": 99999,
                }
            },
        ):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as folder:
                manager = Path(folder) / "MuMuManager.exe"
                manager.touch()
                profile = DeviceProfile(
                    preset_id="windows.mumu12",
                    manager_path=str(manager),
                    instance_id="2",
                )
                run = Mock(
                    return_value=subprocess.CompletedProcess(
                        [], 0, json.dumps(payload).encode(), b""
                    )
                )
                with self.assertRaises(ValueError):
                    ProductionSimulator(run=run).inspect(profile, 3)

    def test_mumu_lifecycle_is_one_manager_action_without_adb_waits(self):
        """A launch spends the transaction, not the read-only query bound.

        The field run granted ``launch_player`` the 3.0 s query bound, killed
        the command while it was still handing the instance to a cold-booting
        player, and ended the run after one of three allowed actions while
        177 s of the transaction budget were unused.
        """
        with tempfile.TemporaryDirectory() as folder:
            manager = Path(folder) / "MuMuManager.exe"
            manager.touch()
            profile = DeviceProfile(
                preset_id="windows.mumu12", manager_path=str(manager), instance_id="2"
            )
            run = Mock(
                side_effect=[
                    subprocess.CompletedProcess([], 0, b'{"code":0}', b""),
                    subprocess.CompletedProcess(
                        [], 0, b'{"2":{"is_process_started":false}}', b""
                    ),
                    subprocess.CompletedProcess([], 0, b'{"code":0}', b""),
                ]
            )
            simulator = ProductionSimulator(run=run)
            self.assertTrue(simulator.start(profile, 30))
            self.assertTrue(simulator.stop(profile, 30))
            self.assertEqual(
                [call.args[0] for call in run.call_args_list],
                [
                    [str(manager), "api", "-v", "2", "launch_player"],
                    [str(manager), "info", "-v", "2"],
                    [str(manager), "api", "-v", "2", "shutdown_player"],
                ],
            )
            self.assertTrue(
                all(
                    QUERY_TIMEOUT < call.kwargs["timeout"] <= 30
                    for call in run.call_args_list
                    if call.args[0][1] == "api"
                )
            )
            self.assertLessEqual(run.call_args_list[1].kwargs["timeout"], QUERY_TIMEOUT)

    def test_mumu_state_query_keeps_its_own_short_bound(self):
        """``info`` answers a readiness poll; it never holds the transaction."""
        with tempfile.TemporaryDirectory() as folder:
            manager = Path(folder) / "MuMuManager.exe"
            manager.touch()
            profile = DeviceProfile(
                preset_id="windows.mumu12", manager_path=str(manager), instance_id="2"
            )
            run = Mock(
                return_value=subprocess.CompletedProcess(
                    [], 0, b'{"2":{"is_process_started":false}}', b""
                )
            )
            self.assertEqual(
                ProductionSimulator(run=run).inspect(profile, 30).state, "stopped"
            )
            self.assertLessEqual(run.call_args.kwargs["timeout"], QUERY_TIMEOUT)

    def test_rejected_lifecycle_command_is_reported_with_its_signed_exit_code(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = Path(folder) / "MuMuManager.exe"
            manager.touch()
            profile = DeviceProfile(
                preset_id="windows.mumu12", manager_path=str(manager), instance_id="2"
            )
            for code, expected in ((7, "7"), (-506 % 2**32, "-506")):
                with self.subTest(code=code):

                    def run(argv, **_options):
                        if argv[1] == "info":
                            return subprocess.CompletedProcess(
                                argv, 0, b'{"2":{"is_process_started":false}}', b""
                            )
                        return subprocess.CompletedProcess(argv, code, b"", b"")

                    simulator = ProductionSimulator(run=run)
                    # The vendor's own rejection stays a named, actionable
                    # verdict instead of a subprocess exception.
                    with self.assertRaisesRegex(
                        RuntimeError, f"启动命令被拒绝（退出码 {expected}）"
                    ):
                        simulator.start(profile, 5)
                    with self.assertRaisesRegex(
                        RuntimeError, f"关闭命令被拒绝（退出码 {expected}）"
                    ):
                        simulator.stop(profile, 5)

    def test_unknown_manual_environment_has_no_automatic_lifecycle(self):
        run = Mock()
        simulator = ProductionSimulator(run=run)
        profile = DeviceProfile(last_serial="other-online")
        self.assertEqual(simulator.inspect(profile, 3).state, "unknown")
        self.assertIsNone(simulator.inspect(profile, 3).serial)
        self.assertFalse(simulator.start(profile, 3))
        self.assertFalse(simulator.stop(profile, 3))
        run.assert_not_called()

    def test_mumu_refreshes_only_selected_instance(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = Path(folder) / "MuMuManager.exe"
            manager.touch()
            profile = DeviceProfile(
                preset_id="windows.mumu12",
                installation_path=folder,
                manager_path=str(manager),
                instance_id="2",
                last_serial="127.0.0.1:16384",
            )
            run = Mock(
                return_value=subprocess.CompletedProcess(
                    [],
                    0,
                    b'{"0":{"is_process_started":true,"is_android_started":true,"adb_port":16384},"2":{"is_process_started":true,"is_android_started":true,"adb_port":16448}}',
                    b"",
                )
            )
            result = ProductionSimulator(run=run).inspect(profile, 5)
            self.assertEqual(result.state, "running")
            self.assertEqual(result.serial, "127.0.0.1:16448")
            self.assertEqual(run.call_args.args[0], [str(manager), "info", "-v", "2"])


class MuMuManagerReplay:
    """The captured manager sequence of one complete restart.

    MuMu 6.8.1 acknowledges shutdown_player with exit 0 while the player process
    is still closing: in the field trace the state stayed ``stopping`` for 8.8 s
    and the launch issued 0.7 s after the shutdown was rejected with -506
    (reported by Windows as 4294966790). The replay keeps that timing, so a
    launch inside the window fails exactly as the field run did.
    """

    HANDOFF = 9.0
    BOOT = 4.0
    PORT = 16384

    def __init__(self, clock):
        self._clock = clock
        self.stopping_at = None
        self.launched_at = None
        # The game was already running and its ADB endpoint was unreachable.
        self.process = True
        self.calls = []

    def state(self):
        if self.stopping_at is not None:
            if self._clock.now - self.stopping_at < self.HANDOFF:
                return "stopping"
            self.stopping_at = None
            self.process = False
        if not self.process:
            return "stopped"
        if (
            self.launched_at is not None
            and self._clock.now - self.launched_at < self.BOOT
        ):
            return "starting"
        return "running"

    def info(self):
        # The vendor reports both flags together: a closing instance keeps a
        # live process while its Android side is already down.
        state = self.state()
        entry = {"index": "0", "name": "粥", "is_process_started": state != "stopped"}
        if state == "running":
            entry.update(is_android_started=True, adb_port=self.PORT)
        elif state != "stopped":
            entry.update(is_android_started=False)
        return json.dumps(entry).encode()

    def __call__(self, argv, **kwargs):
        action = argv[-1]
        if argv[1] == "info":
            return subprocess.CompletedProcess(argv, 0, self.info(), b"")
        self.calls.append((action, self.state()))
        if action == "shutdown_player":
            self.stopping_at = self._clock.now
            return subprocess.CompletedProcess(argv, 0, b'{"code":0}', b"")
        if action == "launch_player" and self.state() == "stopping":
            # A negative vendor code arrives as an unsigned 32-bit exit status.
            return subprocess.CompletedProcess(argv, -506 % 2**32, b"", b"")
        self.process, self.launched_at = True, self._clock.now
        return subprocess.CompletedProcess(argv, 0, b'{"code":0}', b"")


class RestartedTransportADB(ADB):
    """The endpoint is reachable only once the instance was fully restarted."""

    def __init__(self, vendor):
        super().__init__()
        self.vendor = vendor

    def devices(self, adb_path, timeout):
        return [("127.0.0.1:16384", "device")] if self.vendor.launched_at else []

    def boot_completed(self, adb_path, serial, timeout):
        return "1" if self.vendor.launched_at else "0"


class MuMuRestartReplayTests(unittest.TestCase):
    """A shutdown acknowledgement is not a confirmed stop."""

    def setUp(self):
        self.clock = Clock()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        manager = Path(folder) / "MuMuManager.exe"
        manager.touch()
        self.profile = DeviceProfile(
            preset_id="windows.mumu12",
            installation_path=folder,
            manager_path=str(manager),
            instance_id="0",
            last_serial="127.0.0.1:16384",
        )
        self.vendor = MuMuManagerReplay(self.clock)
        self.session = DeviceSession(
            RestartedTransportADB(self.vendor),
            ProductionSimulator(run=self.vendor, monotonic=self.clock.monotonic),
            clock=self.clock,
            policy=RecoveryPolicy(
                attempts=3, timeout=60, local_wait=2, poll_interval=1
            ),
        )

    def test_paired_launch_waits_for_the_manager_to_report_the_instance_stopped(self):
        self.session.bind(self.profile)
        ready = self.session.ensure_ready()
        self.assertEqual(ready.state, "ready")
        self.assertEqual(ready.serial, "127.0.0.1:16384")
        # The rejected launch must never be issued into the stopping window.
        self.assertEqual(
            [state for action, state in self.vendor.calls if action == "launch_player"],
            ["stopped"],
        )
        self.assertEqual(
            [action for action, _ in self.vendor.calls if action == "shutdown_player"],
            ["shutdown_player"],
        )


class MuMuColdBootReplay:
    """The field trace: a stopped instance and a launch slower than a query bound.

    ``MuMuManager launch_player`` hands the instance to a player that is still
    cold-booting, so the command needs longer than the 3 s a read-only query is
    granted. This replay enforces the granted timeout the way the production
    runner does (it kills the command and raises ``TimeoutExpired``) and moves
    the virtual clock by the time each command really needed.
    """

    INFO = 0.2
    LAUNCH = 5.0
    BOOT = 4.0
    PORT = 16384

    def __init__(self, clock):
        self._clock = clock
        self.launched_at = None
        self.granted = []

    def state(self):
        if self.launched_at is None:
            return "stopped"
        if self._clock.now - self.launched_at < self.BOOT:
            return "starting"
        return "running"

    def info(self):
        state = self.state()
        entry = {"index": "0", "name": "粥", "is_process_started": state != "stopped"}
        if state == "running":
            entry.update(is_android_started=True, adb_port=self.PORT)
        elif state != "stopped":
            entry.update(is_android_started=False)
        return json.dumps(entry).encode()

    def __call__(self, argv, **kwargs):
        # ``info -v N`` ends in the instance index, not in the operation name.
        action = "info" if argv[1] == "info" else argv[-1]
        timeout = kwargs["timeout"]
        self.granted.append((action, timeout))
        if action == "info":
            elapsed = self.INFO
        elif action == "launch_player":
            elapsed = self.LAUNCH
        else:
            elapsed = 0.5
        if elapsed > timeout:
            self._clock.now += timeout
            raise subprocess.TimeoutExpired(argv, timeout)
        self._clock.now += elapsed
        if action == "launch_player":
            self.launched_at = self._clock.now
        return subprocess.CompletedProcess(
            argv, 0, self.info() if action == "info" else b'{"code":0}', b""
        )


class ColdBootTransportADB(ADB):
    """The endpoint answers as soon as the player exists, boot still pending."""

    def __init__(self, vendor):
        super().__init__()
        self.vendor = vendor

    def devices(self, adb_path, timeout):
        if self.vendor.launched_at is None:
            return []
        return [("127.0.0.1:16384", "device")]

    def boot_completed(self, adb_path, serial, timeout):
        return "1" if self.vendor.state() == "running" else "0"


class MuMuColdBootReplayTests(unittest.TestCase):
    """A launch that outlives the query bound must not end the transaction."""

    def setUp(self):
        self.clock = Clock()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        manager = Path(folder) / "MuMuManager.exe"
        manager.touch()
        self.profile = DeviceProfile(
            preset_id="windows.mumu12",
            installation_path=folder,
            manager_path=str(manager),
            instance_id="0",
            last_serial="127.0.0.1:16384",
        )
        self.vendor = MuMuColdBootReplay(self.clock)
        self.session = DeviceSession(
            ColdBootTransportADB(self.vendor),
            ProductionSimulator(run=self.vendor, monotonic=self.clock.monotonic),
            clock=self.clock,
            policy=RecoveryPolicy(
                attempts=3, timeout=60, local_wait=2, poll_interval=1
            ),
        )

    def test_a_cold_booting_player_is_waited_for_instead_of_cut_off(self):
        self.session.bind(self.profile)
        ready = self.session.ensure_ready()
        self.assertEqual(ready.state, "ready")
        self.assertEqual(ready.serial, "127.0.0.1:16384")
        granted = dict(self.vendor.granted)
        # The launch is one deliberate action inside the transaction budget.
        self.assertGreater(granted["launch_player"], QUERY_TIMEOUT)
        # The poll that follows keeps answering on its own short bound.
        self.assertLessEqual(granted["info"], QUERY_TIMEOUT)


class SessionCommandChannelTests(unittest.TestCase):
    """A vendor manager is not ADB: the shared-server guard must not see it.

    ``run_adb`` rejects every binary whose ``version`` is not an ADB version as
    soon as a shared server answers. Routing ``MuMuManager`` through it failed
    the whole first-frame probe while a shared server was running.
    """

    MANAGER = r"D:\Mumu\MuMuPlayer\nx_main\MuMuManager.exe"
    INFO_ALL = b'{"0": {"adb_host_ip": "127.0.0.1", "adb_port": 16384}}'

    def adapter(self, run):
        return ProductionSessionADB(run=run, probe=lambda timeout: 41)

    def profile(self):
        return DeviceProfile(
            preset_id="windows.mumu12",
            installation_path=r"D:\Mumu\MuMuPlayer",
            manager_path=self.MANAGER,
            instance_id="0",
            last_serial="127.0.0.1:16384",
            screenshot_backend="mumu_ipc",
            touch_backend="mumu_ipc",
        )

    def vendor_run(self, argv, **kwargs):
        if argv[-1] == "version":
            return subprocess.CompletedProcess(argv, 0, b'{"version": "6.8.1.0"}', b"")
        return subprocess.CompletedProcess(argv, 0, self.INFO_ALL, b"")

    def test_manager_command_never_reaches_the_shared_server_guard(self):
        adapter = self.adapter(self.vendor_run)
        adapter.bind(self.profile())
        io = adapter._preflight_io(5)
        self.assertEqual(io._run([self.MANAGER, "info", "-v", "all"]), self.INFO_ALL)

    def test_adb_channel_keeps_the_shared_server_guard(self):
        adapter = self.adapter(self.vendor_run)
        adapter.bind(self.profile())
        io = adapter._preflight_io(5)
        with self.assertRaises(SharedADBError):
            io._run_adb(["chosen-adb", "devices"])

    def test_session_frame_probe_captures_through_the_manager_channel(self):
        from arknights_mower.tests.device_preflight_io_tests import (
            configure_mumu_capture,
        )

        adapter = self.adapter(self.vendor_run)
        adapter.bind(self.profile())
        with (
            patch(
                "arknights_mower.utils.device.preflight_io.ProductionPreflightIO.host_platform",
                return_value="windows",
            ),
            patch(
                "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
            ) as context,
        ):
            configure_mumu_capture(context.return_value)
            self.assertEqual(
                adapter.frame_size("chosen-adb", "127.0.0.1:16384", 5), (1920, 1080)
            )

    def test_frame_probe_keeps_manager_errors_and_contains_adb_errors(self):
        def failing(argv, **kwargs):
            if argv[-1] == "version":
                return subprocess.CompletedProcess(
                    argv, 0, b'{"version": "6.8.1.0"}', b""
                )
            raise RuntimeError("MuMu IPC 无法确认已选择实例")

        adapter = self.adapter(failing)
        adapter.bind(self.profile())
        io = adapter._preflight_io(5, frame=True)
        with self.assertRaisesRegex(RuntimeError, "无法确认已选择实例"):
            io._run([self.MANAGER, "info", "-v", "all"])
        self.assertEqual(io._run_adb(["chosen-adb", "devices"]), b"")


if __name__ == "__main__":
    unittest.main()
