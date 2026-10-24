"""Read-only adapter and pinned transport contracts, with external I/O replaced."""

import ctypes
import gzip
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from arknights_mower.tests.device_droidcast_tests import HTTP, Android
from arknights_mower.tests.screenshot_adb_tests import CaptureSocket
from arknights_mower.tests.screenshot_fixtures import rgba_frame
from arknights_mower.utils import config
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.adb_client.core import Client
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.droidcast import DroidCastError
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.mumu12ipc.core import MuMu12IPC
from arknights_mower.utils.device.preflight_io import (
    ProductionPreflightIO,
    _capture_mumu_worker,
)
from arknights_mower.utils.device.recovery import DeviceRecoveryError


def configure_mumu_capture(context, *, error=""):
    """Model a child completing its shared output before bounded join returns."""
    context.RawArray.side_effect = lambda kind, length: (kind * length)()
    context.RawValue.side_effect = lambda kind, value: kind(value)
    process = context.Process.return_value
    process.is_alive.return_value = False
    process.exitcode = 0
    process.pid = 123

    def capture():
        _, _, _, frame, succeeded, message = context.Process.call_args.kwargs["args"]
        succeeded.value = not error
        message.value = error.encode("utf-8")
        frame[0] = 42

    process.start.side_effect = capture
    return process


class StrictTransportTests(unittest.TestCase):
    def test_strict_device_passes_pinned_transport_and_never_restarts_emulator(self):
        from threading import Event

        with (
            patch.object(config, "stop_mower", Event()),
            patch.object(config.conf, "mumu12IPC", False),
            patch.object(config.conf.droidcast, "enable", False),
            patch("arknights_mower.utils.device.device.ADBClient") as client,
            patch("arknights_mower.utils.device.device.Device.Control"),
            patch("arknights_mower.utils.device.device.atexit.register"),
            patch("arknights_mower.utils.device.recovery.csleep"),
            patch("arknights_mower.utils.simulator.restart_simulator") as restart,
        ):
            client.return_value.device_id = "chosen-usb"
            client.return_value.cmd_shell.return_value = "Physical size: 1920x1080"
            device = Device(
                "chosen-usb",
                adb_bin="chosen-adb",
                strict_target=True,
                wait_for_device=False,
            )
            client.assert_called_once_with(
                "chosen-usb",
                None,
                wait_for_device=False,
                adb_bin="chosen-adb",
                strict_target=True,
            )
            operation = MagicMock(side_effect=ConnectionError("offline"))
            with self.assertRaises(DeviceRecoveryError):
                device.recover(operation)
            restart.assert_not_called()
            self.assertEqual(operation.call_count, 4)
            self.assertEqual(device.device_id, "chosen-usb")
            device.close()

    def test_empty_serial_is_rejected_before_any_adb_access(self):
        with patch("arknights_mower.utils.device.adb_client.core.run_command") as run:
            with self.assertRaises(ValueError):
                Client("", adb_bin="chosen-adb", strict_target=True)
        run.assert_not_called()

    def test_unready_or_duplicate_target_is_never_replaced_with_another_device(self):
        for rows in (
            [("other", "device")],
            [("chosen", "offline"), ("other", "device")],
            [("chosen", "unauthorized"), ("other", "device")],
            [("chosen", "device"), ("chosen", "device")],
        ):
            with (
                self.subTest(rows=rows),
                patch(
                    "arknights_mower.utils.device.adb_client.core.Session"
                ) as session,
                patch("arknights_mower.utils.device.adb_client.core.run_command"),
            ):
                session.return_value.devices_list.return_value = rows
                with self.assertRaisesRegex(ConnectionError, "pinned target"):
                    Client("chosen", adb_bin="chosen-adb", strict_target=True)
                session.return_value.connect.assert_not_called()

    def test_usb_transport_stays_pinned_and_never_uses_tcp_connect(self):
        with (
            patch("arknights_mower.utils.device.adb_client.core.Session") as session,
            patch("arknights_mower.utils.device.adb_client.core.run_command") as run,
            patch("arknights_mower.utils.device.adb_client.core.csleep"),
            patch(
                "arknights_mower.utils.device.adb_client.core.query_mumu_adb_port"
            ) as discover,
        ):
            session.return_value.devices_list.return_value = [
                ("other-phone", "device"),
                ("chosen-phone", "device"),
            ]
            client = Client(
                "chosen-phone",
                adb_bin="chosen-adb",
                strict_target=True,
                wait_for_device=False,
            )
            client.reconnect(wait_for_device=False)
            self.assertEqual(client.refresh_target(), "chosen-phone")
            self.assertEqual(client.adb_bin, "chosen-adb")
            session.return_value.connect.assert_not_called()
            discover.assert_not_called()
            run.assert_not_called()


class ReadOnlyCaptureTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch(
                "arknights_mower.utils.device.adb_client.server.probe_adb_server",
                return_value=None,
            )
        )

    def configure_droidcast(self, version="1.3.0", *, adb_path):
        android, http = Android(adb_path=adb_path), HTTP()
        android.version = version
        module = "arknights_mower.utils.device.droidcast"
        run = self.enterContext(patch(f"{module}.run_adb", side_effect=android.run))
        spawn = self.enterContext(
            patch(f"{module}.subprocess.Popen", side_effect=android.spawn)
        )
        self.enterContext(patch(f"{module}.guard_adb"))
        self.enterContext(patch(f"{module}.requests.Session", return_value=http))
        self.enterContext(patch(f"{module}.get_new_port", return_value=54321))
        return android, http, run, spawn

    def test_missing_or_old_droidcast_requests_repair_without_installing(self):
        for version, missing_error in ((None, False), (None, True), ("1.2.1", False)):
            with self.subTest(version=version, missing_error=missing_error):
                android, http, run, spawn = self.configure_droidcast(
                    version, adb_path="chosen-adb"
                )
                if missing_error:
                    run.side_effect = subprocess.CalledProcessError(
                        1, "pm path", output=b""
                    )
                with self.assertRaisesRegex(
                    DroidCastError,
                    "需要 DroidCast 1.3.0。测试截图不会自动安装应用",
                ) as raised:
                    ProductionPreflightIO().capture_frame(
                        "chosen-adb",
                        "USB-A",
                        DeviceProfile(screenshot_backend="droidcast"),
                    )
                self.assertEqual(raised.exception.code, "droidcast_version_required")
                queries = [call.args[0][3:] for call in run.call_args_list]
                expected = [["shell", "pm", "path", "com.rayworks.droidcast"]]
                if version:
                    expected.append(
                        ["shell", "dumpsys", "package", "com.rayworks.droidcast"]
                    )
                self.assertEqual(queries, expected)
                self.assertEqual(android.version, version)
                spawn.assert_not_called()
                self.assertEqual(http.calls, [])

    def test_custom_wrong_target_or_mutating_command_never_executes(self):
        for command in (
            "adb -s other shell screencap -p",
            "adb shell input tap 1 2",
            "adb shell screencap -p;input tap 1 2",
            "adb shell screencap /sdcard/output.png",
        ):
            configuration = SimpleNamespace(
                custom_screenshot=SimpleNamespace(command=command)
            )
            with (
                self.subTest(command=command),
                patch("arknights_mower.utils.device.preflight_io.run_command") as run,
            ):
                with self.assertRaises(ValueError):
                    ProductionPreflightIO(lambda: configuration).capture_frame(
                        "chosen-adb", "usb1", DeviceProfile(screenshot_backend="custom")
                    )
                run.assert_not_called()

    def test_corrupt_adb_frame_is_not_reshaped_as_a_valid_canvas(self):
        for raw in (
            struct.pack("<III", 1920, 1080, 1) + b"short",
            struct.pack("<III", 1, 1, 999) + b"data",
            struct.pack("<III", 0, 1, 1),
        ):
            with (
                self.subTest(raw=raw),
                patch(
                    "arknights_mower.utils.device.screenshot.socket.create_connection",
                    side_effect=[
                        CaptureSocket(b"26"),
                        CaptureSocket(gzip.compress(raw)),
                    ],
                ),
            ):
                with self.assertRaises(ValueError):
                    ProductionPreflightIO().capture_frame(
                        "chosen-adb",
                        "usb1",
                        DeviceProfile(screenshot_backend="adb_gzip"),
                    )

    def test_adb_capture_decodes_valid_frame_using_only_pinned_transport(self):
        connections = [
            CaptureSocket(b"27"),
            CaptureSocket(gzip.compress(rgba_frame(modern=True))),
        ]
        profile = DeviceProfile(screenshot_backend="adb_gzip")
        with patch(
            "arknights_mower.utils.device.screenshot.socket.create_connection",
            side_effect=connections,
        ):
            frame = ProductionPreflightIO().capture_frame("chosen-adb", "usb1", profile)
        self.assertEqual(frame.shape, (1080, 1920, 3))
        self.assertEqual(frame[0, 0].tolist(), [255, 128, 0])
        for connection in connections:
            self.assertTrue(connection.closed)
            self.assertIn(b"host:transport:usb1", connection.sent[0])

    def test_custom_adb_capture_uses_verified_binary_and_explicit_target(self):
        configuration = SimpleNamespace(
            custom_screenshot=SimpleNamespace(
                command="adb -s usb1 shell screencap -p 2>/dev/null"
            )
        )
        png = cv2.imencode(".png", np.zeros((2, 3, 3), dtype=np.uint8))[1].tobytes()
        with patch(
            "arknights_mower.utils.device.preflight_io.run_command",
            return_value=SimpleNamespace(stdout=png),
        ) as run:
            frame = ProductionPreflightIO(lambda: configuration).capture_frame(
                "verified-adb", "usb1", DeviceProfile(screenshot_backend="custom")
            )
        self.assertEqual(frame.shape, (2, 3, 3))
        self.assertEqual(
            run.call_args.args[0],
            ["verified-adb", "-s", "usb1", "shell", "screencap", "-p"],
        )

    def test_droidcast_reads_current_version_and_cleans_its_owned_resources(self):
        configuration = SimpleNamespace(droidcast=SimpleNamespace(rotate=False))
        android, http, run, spawn = self.configure_droidcast(adb_path="verified-adb")
        frame = ProductionPreflightIO(lambda: configuration).capture_frame(
            "verified-adb", "USB-A", DeviceProfile(screenshot_backend="droidcast")
        )
        self.assertEqual(frame.shape, (1080, 1920, 3))
        self.assertIn(
            ["shell", "dumpsys", "package", "com.rayworks.droidcast"], android.commands
        )
        self.assertFalse(any(args[0] == "install" for args in android.commands))
        self.assertIn(
            ["forward", "--no-rebind", "tcp:54321", "tcp:54321"], android.commands
        )
        self.assertEqual(android.commands[-1], ["forward", "--remove", "tcp:54321"])
        self.assertIn(["shell", "cat", "/proc/101/cmdline"], android.commands)
        self.assertIn(["shell", "kill", "101"], android.commands)
        self.assertEqual(android.remote, {})
        self.assertEqual(android.forwards, {})
        self.assertEqual(android.processes[0].terminated, 1)
        helper = spawn.call_args.args[0]
        self.assertEqual(helper[:4], ["verified-adb", "-s", "USB-A", "shell"])
        self.assertTrue(
            any(arg.startswith("--nice-name=mower-droidcast-") for arg in helper)
        )
        self.assertEqual(http.closed, 1)
        self.assertFalse(http.trust_env)
        self.assertEqual(len(http.calls), 1)
        self.assertTrue(http.calls[0][1]["stream"])
        self.assertFalse(http.calls[0][1]["allow_redirects"])
        commands = [call.args[0] for call in run.call_args_list]
        inventory = ["verified-adb", "forward", "--list"]
        self.assertIn(inventory, commands)
        self.assertTrue(
            all(
                command == inventory or command[:3] == ["verified-adb", "-s", "USB-A"]
                for command in commands
            )
        )
        self.assertTrue(all(0 < timeout <= 10 for timeout in android.timeouts))

    def test_droidcast_failed_frame_closes_helper_without_removing_foreign_forward(
        self,
    ):
        configuration = SimpleNamespace(droidcast=SimpleNamespace(rotate=False))
        android, http, _, _ = self.configure_droidcast(adb_path="chosen-adb")
        http.data = b"invalid image"
        get = http.get

        def change_mapping(*args, **kwargs):
            android.forwards["tcp:54321"] = ("other-device", "tcp:54321")
            return get(*args, **kwargs)

        with patch.object(http, "get", side_effect=change_mapping):
            with self.assertRaises(DroidCastError) as raised:
                ProductionPreflightIO(lambda: configuration).capture_frame(
                    "chosen-adb", "USB-A", DeviceProfile(screenshot_backend="droidcast")
                )
        self.assertEqual(raised.exception.code, "droidcast_frame_failed")
        self.assertEqual(android.processes[0].terminated, 1)
        self.assertEqual(http.closed, 1)
        self.assertEqual(android.remote, {})
        self.assertEqual(android.forwards, {"tcp:54321": ("other-device", "tcp:54321")})
        self.assertFalse(any("--remove" in args for args in android.commands))

    def test_droidcast_reused_remote_pid_is_not_killed_during_preflight_cleanup(self):
        configuration = SimpleNamespace(droidcast=SimpleNamespace(rotate=False))
        android, _, run, _ = self.configure_droidcast(adb_path="chosen-adb")

        def recycle_pid(argv, **kwargs):
            if argv[3:5] == ["shell", "cat"]:
                android.remote[101] = "another-helper"
            return android.run(argv, **kwargs)

        run.side_effect = recycle_pid
        frame = ProductionPreflightIO(lambda: configuration).capture_frame(
            "chosen-adb", "USB-A", DeviceProfile(screenshot_backend="droidcast")
        )
        self.assertEqual(frame.shape, (1080, 1920, 3))
        self.assertEqual(android.remote, {101: "another-helper"})
        self.assertFalse(
            any(args[:2] == ["shell", "kill"] for args in android.commands)
        )
        self.assertEqual(android.forwards, {})
        self.assertEqual(android.processes[0].terminated, 1)

    @patch.object(ProductionPreflightIO, "host_platform", lambda _: "windows")
    def test_ipc_failure_is_reported_without_switching_to_adb(self):
        profile = DeviceProfile(
            preset_id="windows.mumu12",
            screenshot_backend="mumu_ipc",
            touch_backend="mumu_ipc",
            instance_id="0",
        )
        with (
            patch(
                "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
            ) as context,
            patch(
                "arknights_mower.utils.device.preflight_io.run_command",
                return_value=SimpleNamespace(stdout=b'{"0":{"adb_port":16384}}'),
            ) as run,
        ):
            configure_mumu_capture(
                context.return_value, error="MuMu capture returned 7"
            )
            with self.assertRaisesRegex(RuntimeError, "returned 7"):
                ProductionPreflightIO().capture_frame(
                    "chosen-adb", "127.0.0.1:16384", profile
                )
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-3:], ["info", "-v", "all"])

    @patch.object(ProductionPreflightIO, "host_platform", lambda _: "windows")
    def test_ipc_cannot_capture_a_different_instance_or_usb_target(self):
        profile = DeviceProfile(
            preset_id="windows.mumu12",
            screenshot_backend="mumu_ipc",
            touch_backend="mumu_ipc",
            instance_id="0",
        )
        for serial in ("usb1", "127.0.0.1:9999"):
            with (
                self.subTest(serial=serial),
                patch(
                    "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
                ) as context,
                patch(
                    "arknights_mower.utils.device.preflight_io.run_command",
                    return_value=SimpleNamespace(stdout=b'{"0":{"adb_port":16384}}'),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "实例端点"):
                    ProductionPreflightIO().capture_frame("chosen-adb", serial, profile)
                context.assert_not_called()

    @patch.object(ProductionPreflightIO, "host_platform", lambda _: "windows")
    def test_ipc_hung_worker_uses_remaining_budget_and_is_terminated(self):
        profile = DeviceProfile(
            preset_id="windows.mumu12",
            screenshot_backend="mumu_ipc",
            touch_backend="mumu_ipc",
            instance_id="0",
        )
        with (
            patch(
                "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
            ) as context,
            patch(
                "arknights_mower.utils.device.preflight_io.run_command",
                return_value=SimpleNamespace(stdout=b'{"0":{"adb_port":16384}}'),
            ),
        ):
            process = configure_mumu_capture(context.return_value)
            process.is_alive.return_value = True
            now = 0.0

            def remaining():
                if now >= 0.25:
                    raise DeviceRecoveryError("shared deadline exhausted")
                return 0.25 - now

            def join(*, timeout):
                nonlocal now
                now += timeout

            process.join.side_effect = join
            process.terminate.side_effect = lambda: setattr(
                process.is_alive, "return_value", False
            )
            with (
                self.assertRaisesRegex(TimeoutError, "限定时间"),
                device_io_budget(remaining),
            ):
                ProductionPreflightIO().capture_frame(
                    "chosen-adb", "127.0.0.1:16384", profile
                )
            self.assertEqual(process.join.call_args_list[0].kwargs, {"timeout": 0.25})
            context.return_value.Pipe.assert_not_called()
            process.terminate.assert_called_once_with()
            process.kill.assert_not_called()
            process.close.assert_called_once_with()

    @patch.object(ProductionPreflightIO, "host_platform", lambda _: "windows")
    def test_ipc_completed_worker_returns_the_shared_frame(self):
        profile = DeviceProfile(
            preset_id="windows.mumu12",
            screenshot_backend="mumu_ipc",
            touch_backend="mumu_ipc",
            instance_id="0",
        )
        with (
            patch(
                "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
            ) as context,
            patch(
                "arknights_mower.utils.device.preflight_io.run_command",
                return_value=SimpleNamespace(stdout=b'{"0":{"adb_port":16384}}'),
            ),
        ):
            process = configure_mumu_capture(context.return_value)
            frame = ProductionPreflightIO().capture_frame(
                "chosen-adb", "127.0.0.1:16384", profile
            )
        self.assertEqual(frame.shape, (1080, 1920, 3))
        self.assertEqual(frame[0, 0, 0], 42)
        self.assertEqual(
            [call.kwargs["timeout"] for call in process.join.call_args_list],
            [10, 1],
        )
        process.terminate.assert_not_called()
        process.close.assert_called_once_with()

    @patch.object(ProductionPreflightIO, "host_platform", lambda _: "windows")
    def test_ipc_single_instance_dict_payload_returns_frame(self):
        profile = DeviceProfile(
            preset_id="windows.mumu12",
            screenshot_backend="mumu_ipc",
            touch_backend="mumu_ipc",
            instance_id="0",
            instance_name="明日方舟-MuMu模拟器12",
        )
        with (
            patch(
                "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
            ) as context,
            patch(
                "arknights_mower.utils.device.preflight_io.run_command",
                return_value=SimpleNamespace(
                    stdout=b'{"index":0,"name":"\xe6\x98\x8e\xe6\x97\xa5\xe6\x96\xb9\xe8\x88\x9f-MuMu\xe6\xa8\xa1\xe6\x8b\x9f\xe5\x99\xa812","adb_port":16384,"adb_host_ip":"127.0.0.1"}'
                ),
            ),
        ):
            process = configure_mumu_capture(context.return_value)
            frame = ProductionPreflightIO().capture_frame(
                "chosen-adb", "127.0.0.1:16384", profile
            )
        self.assertEqual(frame.shape, (1080, 1920, 3))
        process.close.assert_called_once_with()

    @patch.object(ProductionPreflightIO, "host_platform", lambda _: "windows")
    def test_ipc_cancellation_after_spawn_still_joins_before_termination(self):
        profile = DeviceProfile(
            preset_id="windows.mumu12",
            screenshot_backend="mumu_ipc",
            touch_backend="mumu_ipc",
            instance_id="0",
        )
        with (
            patch(
                "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
            ) as context,
            patch(
                "arknights_mower.utils.device.preflight_io.run_command",
                return_value=SimpleNamespace(stdout=b'{"0":{"adb_port":16384}}'),
            ),
        ):
            process = configure_mumu_capture(context.return_value)
            process.is_alive.return_value = True
            cancelled = False
            events = []

            def start():
                nonlocal cancelled
                events.append("start")
                cancelled = True

            def remaining():
                if cancelled:
                    raise DeviceRecoveryError("cancelled after spawn")
                return 10

            def terminate():
                events.append("terminate")
                process.is_alive.return_value = False

            process.start.side_effect = start
            process.join.side_effect = lambda **kwargs: events.append("join")
            process.terminate.side_effect = terminate
            process.close.side_effect = lambda: events.append("close")
            with (
                self.assertRaisesRegex(DeviceRecoveryError, "cancelled after spawn"),
                device_io_budget(remaining),
            ):
                ProductionPreflightIO().capture_frame(
                    "chosen-adb", "127.0.0.1:16384", profile
                )
            self.assertEqual(events, ["start", "join", "terminate", "join", "close"])
            self.assertTrue(
                all(call.kwargs["timeout"] == 1 for call in process.join.call_args_list)
            )

    @patch.object(ProductionPreflightIO, "host_platform", lambda _: "windows")
    def test_ipc_failed_spawn_closes_unstarted_owned_process(self):
        profile = DeviceProfile(
            preset_id="windows.mumu12",
            screenshot_backend="mumu_ipc",
            touch_backend="mumu_ipc",
            instance_id="0",
        )
        with (
            patch(
                "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
            ) as context,
            patch(
                "arknights_mower.utils.device.preflight_io.run_command",
                return_value=SimpleNamespace(stdout=b'{"0":{"adb_port":16384}}'),
            ),
        ):
            process = configure_mumu_capture(context.return_value)
            process.pid = None
            process.start.side_effect = OSError("spawn failed")
            with self.assertRaisesRegex(OSError, "spawn failed"):
                ProductionPreflightIO().capture_frame(
                    "chosen-adb", "127.0.0.1:16384", profile
                )
            process.join.assert_not_called()
            process.terminate.assert_not_called()
            process.close.assert_called_once_with()


class MumuFrameWorkerTests(unittest.TestCase):
    def test_worker_copies_the_flipped_frame_before_reporting_success(self):
        frame = (ctypes.c_ubyte * (1920 * 1080 * 3))()
        succeeded = ctypes.c_bool(False)
        error = (ctypes.c_char * 1024)()
        dll = MagicMock()
        dll.nemu_connect.return_value = 7
        dll.nemu_get_display_id.return_value = 1

        def capture(connection, display, size, width, height, pixels):
            ctypes.cast(width, ctypes.POINTER(ctypes.c_int))[0] = 1920
            ctypes.cast(height, ctypes.POINTER(ctypes.c_int))[0] = 1080
            rgba = np.frombuffer(pixels, np.uint8).reshape(1080, 1920, 4)
            rgba[-1, 0] = (10, 20, 30, 255)
            return 0

        dll.nemu_capture_display.side_effect = capture
        with patch.object(
            MuMu12IPC, "_load_renderer", lambda ipc: setattr(ipc, "_dll", dll)
        ):
            _capture_mumu_worker("root", "0", "game", frame, succeeded, error)
        self.assertTrue(succeeded.value)
        self.assertEqual(bytes(frame[:3]), bytes((10, 20, 30)))
        self.assertEqual(error.value, b"")
        dll.nemu_disconnect.assert_called_once_with(7)

    def test_worker_error_is_bounded_and_does_not_mark_the_frame_ready(self):
        frame = (ctypes.c_ubyte * (1920 * 1080 * 3))()
        succeeded = ctypes.c_bool(False)
        error = (ctypes.c_char * 1024)()
        dll = MagicMock()
        dll.nemu_connect.side_effect = RuntimeError("x" * 2000)
        with patch.object(
            MuMu12IPC, "_load_renderer", lambda ipc: setattr(ipc, "_dll", dll)
        ):
            _capture_mumu_worker("root", "0", "game", frame, succeeded, error)
        self.assertFalse(succeeded.value)
        self.assertEqual(error.value, b"x" * 1023)
        dll.nemu_disconnect.assert_not_called()


class DiscoveryIOTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch(
                "arknights_mower.utils.device.adb_client.server.probe_adb_server",
                return_value=None,
            )
        )

    @patch.object(ProductionPreflightIO, "host_platform", lambda _: "windows")
    def test_preflight_and_runtime_resolve_the_same_mumu_manager_and_library_root(self):
        for layout, explicit in (
            ("", False),
            ("shell", False),
            ("nx_main", False),
            ("", True),
        ):
            with (
                self.subTest(layout=layout, explicit=explicit),
                tempfile.TemporaryDirectory() as folder,
            ):
                root = Path(folder)
                installation = root / layout
                installation.mkdir(exist_ok=True)
                manager = root / (
                    "tools/CustomManager.exe" if explicit else "shell/MuMuManager.exe"
                )
                manager.parent.mkdir(exist_ok=True)
                manager.touch()
                profile = DeviceProfile(
                    installation_path=str(installation),
                    manager_path=str(manager) if explicit else "",
                    instance_id="0",
                    preset_id="windows.mumu12",
                    screenshot_backend="mumu_ipc",
                    touch_backend="mumu_ipc",
                )
                configuration = SimpleNamespace(
                    device=profile,
                    simulator=SimpleNamespace(
                        simulator_folder=str(installation), index="0"
                    ),
                )
                commands = []

                def run(argv, **kwargs):
                    commands.append(argv)
                    return SimpleNamespace(
                        stdout=b'{"0":{"adb_port":16384}}'
                        if argv[1] == "info"
                        else "5.0.0"
                    )

                with (
                    patch.object(config, "conf", configuration),
                    patch(
                        "arknights_mower.utils.device.preflight_io.run_command",
                        side_effect=run,
                    ),
                    patch(
                        "arknights_mower.utils.device.mumu12ipc.core.subprocess.run",
                        side_effect=run,
                    ),
                    patch(
                        "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
                    ) as context,
                    patch(
                        "arknights_mower.utils.device.mumu12ipc.core.ctypes.CDLL"
                    ) as load_library,
                ):
                    configure_mumu_capture(context.return_value)
                    ProductionPreflightIO().capture_frame(
                        "chosen-adb", "127.0.0.1:16384", profile
                    )
                    runtime = MuMu12IPC(MagicMock())
                    self.assertEqual(runtime.get_setting_core_version(), "5.0.0")
                self.assertEqual(
                    [argv[0] for argv in commands], [str(manager), str(manager)]
                )
                self.assertEqual(
                    Path(load_library.call_args.args[0]),
                    root / "shell/sdk/external_renderer_ipc.dll",
                )

    def test_adb_probe_uses_bounded_version_and_checks_identity(self):
        for output, valid in (
            (b"Android Debug Bridge version 1.0.41\n", True),
            (b"some other tool", False),
        ):
            with (
                self.subTest(output=output),
                patch(
                    "arknights_mower.utils.device.preflight_io.run_command",
                    return_value=SimpleNamespace(stdout=output),
                ) as run,
            ):
                self.assertEqual(
                    ProductionPreflightIO().validate_adb("custom-adb"), valid
                )
                self.assertEqual(run.call_args.args[0][-1], "version")
                self.assertGreater(run.call_args.kwargs["timeout"], 0)

    def test_absent_usb_never_gets_a_tcp_connect_or_implicit_selection(self):
        with patch(
            "arknights_mower.utils.device.preflight_io.run_command",
            return_value=SimpleNamespace(
                stdout=b"List of devices attached\nother\tdevice\n"
            ),
        ) as run:
            self.assertEqual(
                ProductionPreflightIO().devices("chosen-adb", "usb1"),
                [("other", "device")],
            )
        self.assertEqual(run.call_args.args[0], ["chosen-adb", "devices"])
        self.assertEqual(run.call_count, 1)

    def test_missing_tcp_endpoint_connects_only_the_requested_endpoint(self):
        with patch(
            "arknights_mower.utils.device.preflight_io.run_command",
            side_effect=[
                SimpleNamespace(stdout=output)
                for output in (
                    b"List of devices attached\nother\tdevice\n",
                    b"connected to 127.0.0.1:5555",
                    b"List of devices attached\nother\tdevice\n127.0.0.1:5555\tunauthorized\n",
                )
            ],
        ) as run:
            self.assertEqual(
                ProductionPreflightIO().devices("chosen-adb", "127.0.0.1:5555")[-1],
                ("127.0.0.1:5555", "unauthorized"),
            )
        self.assertEqual(
            run.call_args_list[1].args[0], ["chosen-adb", "connect", "127.0.0.1:5555"]
        )


if __name__ == "__main__":
    unittest.main()
