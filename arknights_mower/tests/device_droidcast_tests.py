"""DroidCast lifecycle observed through the device-control capture boundary."""

import gzip
import io
import os
import re
import struct
import subprocess
import unittest
from datetime import datetime
from pathlib import Path
from threading import Event, RLock
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np
import requests
from urllib3.exceptions import ReadTimeoutError

from arknights_mower.tests.device_screenshot_backend_tests import CaptureAdapter
from arknights_mower.tests.device_session_tests import (
    ADB,
    Adapter,
    Clock,
    Preflight,
    Simulator,
)
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device import droidcast
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.adb_client.server import run_adb as guarded_run_adb
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.session import DeviceSession
from arknights_mower.utils.device.touch_backend import TouchFailure

MODULE = "arknights_mower.utils.device.droidcast"
SCREENSHOT_MODULE = "arknights_mower.utils.device.screenshot"


class Process:
    def __init__(self):
        self.exited = False
        self.terminated = 0

    def poll(self):
        return 0 if self.exited else None

    def terminate(self):
        self.terminated += 1
        self.exited = True

    kill = terminate

    def wait(self, timeout):
        if not self.exited:
            raise subprocess.TimeoutExpired("helper", timeout)


class Android:
    def __init__(self, *, adb_path):
        self.adb_path = adb_path
        self.serial = "USB-A"
        self.version = "1.2.1"
        self.install_output = b"Success\n"
        self.commands = []
        self.timeouts = []
        self.forwards = {}
        self.remote = {}
        self.processes = []
        self.spawned = []
        self.spawn_error = None
        self.transport_error = None

    def run(self, argv, **kwargs):
        assert argv[0] == self.adb_path, argv
        self.timeouts.append(kwargs["timeout"])
        if argv[1:] == ["forward", "--list"]:
            serial, args = None, argv[1:]
        else:
            serial, args = argv[2], argv[3:]
            assert serial == self.serial, argv
        self.commands.append(args)
        if serial is not None and self.transport_error:
            raise subprocess.CalledProcessError(
                1, argv, output=b"", stderr=self.transport_error
            )
        output = b""
        if args[:3] == ["shell", "pm", "path"]:
            output = b"package:/data/app/droidcast/base.apk\n" if self.version else b""
        elif args[:3] == ["shell", "dumpsys", "package"]:
            output = f"versionCode={146 if self.version == '1.3.0' else 121}\nversionName={self.version}\n".encode()
        elif args[0] == "install":
            output = self.install_output
            if output.strip() == b"Success":
                self.version = "1.3.0"
        elif args[:2] == ["forward", "--no-rebind"]:
            if args[2] in self.forwards:
                raise subprocess.CalledProcessError(1, argv, b"cannot rebind")
            self.forwards[args[2]] = (serial, args[3])
        elif args == ["forward", "--list"]:
            output = "\n".join(
                f"{s} {p} {r}" for p, (s, r) in self.forwards.items()
            ).encode()
        elif args[:2] == ["forward", "--remove"]:
            del self.forwards[args[2]]
        elif args[:2] == ["shell", "pidof"]:
            output = " ".join(
                str(pid) for pid, name in self.remote.items() if name == args[2]
            ).encode()
        elif args[:2] == ["shell", "cat"]:
            pid = int(args[2].split("/")[2])
            output = self.remote.get(pid, "foreign").encode() + b"\x00"
        elif args[:2] == ["shell", "kill"]:
            self.remote.pop(int(args[-1]), None)
        else:
            raise AssertionError(args)
        return SimpleNamespace(stdout=output, returncode=0)

    def spawn(self, argv, **kwargs):
        assert argv[:4] == [self.adb_path, "-s", self.serial, "shell"]
        if self.spawn_error:
            raise self.spawn_error
        name = next(
            arg.split("=", 1)[1] for arg in argv if arg.startswith("--nice-name=")
        )
        self.spawned.append(list(argv))
        process = Process()
        self.processes.append(process)
        self.remote[100 + len(self.processes)] = name
        return process


class HTTP:
    trust_env = True

    def __init__(self):
        self.failure = None
        self.closed = 0
        self.calls = []
        self.data = cv2.imencode(".png", np.zeros((1080, 1920, 3), np.uint8))[
            1
        ].tobytes()

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.failure:
            raise self.failure
        return SimpleNamespace(
            status_code=200, headers={}, raw=io.BytesIO(self.data), close=lambda: None
        )

    def close(self):
        self.closed += 1


class StandardADB:
    def __init__(self):
        self.frame = np.full((1080, 1920, 3), 123, dtype=np.uint8)
        self.commands = []
        self.guards = []
        self.failure = None

    def guard(self, adb_path, *, timeout):
        assert adb_path == "chosen-adb"
        assert 0 < timeout <= 10
        self.guards.append((adb_path, timeout))

    def output(self, serial, command, limit, remaining):
        assert serial == "USB-A"
        timeout = remaining()
        assert 0 < timeout <= 10
        self.commands.append((serial, command, timeout))
        if self.failure is not None:
            raise self.failure
        if command == "getprop ro.build.version.sdk":
            return b"30\n"
        assert command == "screencap 2>/dev/null | gzip -1"
        height, width, _ = self.frame.shape
        output = gzip.compress(
            struct.pack("<IIII", width, height, 3, 1) + self.frame.tobytes()
        )
        assert len(output) <= limit
        return output


class DroidCastTests(unittest.TestCase):
    def setUp(self):
        self.android, self.http, self.clock = (
            Android(adb_path="chosen-adb"),
            HTTP(),
            Clock(),
        )
        self.standard = StandardADB()
        self.enterContext(patch(f"{SCREENSHOT_MODULE}.guard_adb", self.standard.guard))
        self.enterContext(
            patch(f"{SCREENSHOT_MODULE}._adb_output", self.standard.output)
        )
        for name, value in (
            ("run_adb", self.android.run),
            ("guard_adb", lambda *args, **kwargs: None),
            ("get_new_port", Mock(side_effect=range(50000, 50064))),
            ("subprocess.Popen", self.android.spawn),
            ("requests.Session", lambda: self.http),
            ("time.monotonic", self.clock.monotonic),
            ("budget_sleep", self.clock.sleep),
        ):
            self.enterContext(patch(f"{MODULE}.{name}", value))
        self.conf = Conf(
            device={"last_serial": "USB-A", "screenshot_backend": "droidcast"}
        )
        self.enterContext(patch.object(config, "conf", self.conf))
        self.device = object.__new__(Device)
        self.device.owner_pid = os.getpid()
        self.device._resource_lock = RLock()
        self.device._interrupted = Event()
        self.device._close_error = None
        self.input_control = SimpleNamespace(
            input_alive=Mock(return_value=True), close=Mock(), interrupt=Mock()
        )
        self.device.control = self.input_control
        self.device.device_id = "USB-A"
        self.device.client = SimpleNamespace(adb_bin="chosen-adb", device_id="USB-A")
        self.adb, self.simulator = ADB(), Simulator()
        self.adb.resolve_adb = lambda profile, timeout: "chosen-adb"
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        self.control = DeviceControl(
            lambda: self.conf,
            CaptureAdapter(self.device),
            preflight=Preflight(),
            session=DeviceSession(self.adb, self.simulator, clock=self.clock),
        )
        self.assertTrue(self.control.start().ok)
        self.addCleanup(self.control.close)
        self.before = self.conf.model_dump()

    def assert_adb_degraded(self, result, code, diagnosis=None):
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value.shape, (1080, 1920, 3))
        self.assertEqual(result.value.dtype, np.uint8)
        self.assertTrue(np.array_equal(result.value, self.standard.frame))
        self.assertEqual(result.serial, "USB-A")
        self.assertEqual(self.control.serial, "USB-A")
        self.assertEqual(self.conf.model_dump(), self.before)
        status = self.control.settings_status()
        self.assertEqual(status["screenshot_backend"]["selected"], "droidcast")
        self.assertEqual(status["screenshot_backend"]["effective"], "adb_gzip")
        self.assertTrue(status["screenshot_backend"]["degraded"])
        self.assertEqual(status["error"]["code"], code)
        if diagnosis is not None:
            self.assertIn(diagnosis, status["error"]["message"])
        self.assertTrue(self.standard.guards)
        self.assertTrue(self.standard.commands)
        self.assertEqual({serial for serial, _, _ in self.standard.commands}, {"USB-A"})
        self.assertTrue(
            any(
                command.startswith("screencap ")
                for _, command, _ in self.standard.commands
            )
        )
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.adb.actions, [])

    def test_old_version_is_replaced_before_a_real_sized_frame_is_accepted(self):
        result = self.control.capture()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value.shape, (1080, 1920, 3))
        self.assertEqual(self.android.version, "1.3.0")
        installs = [args for args in self.android.commands if args[0] == "install"]
        self.assertEqual(len(installs), 1)
        self.assertIn("-r", installs[0])
        self.assertTrue(all(0 < timeout <= 60 for timeout in self.android.timeouts))
        self.assertEqual(self.simulator.actions, [])

    def test_missing_package_installs_and_current_package_is_not_reinstalled(self):
        self.android.version = None
        self.assertTrue(self.control.capture().ok)
        self.assertTrue(self.control.capture().ok)
        self.assertEqual(sum(args[0] == "install" for args in self.android.commands), 1)

    def test_current_package_skips_install(self):
        self.android.version = "1.3.0"
        self.assertTrue(self.control.capture().ok)
        self.assertFalse(any(args[0] == "install" for args in self.android.commands))

    def test_signature_conflict_is_actionable_and_never_uninstalls(self):
        self.android.install_output = b"Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]"
        result = self.control.capture()
        self.assert_adb_degraded(result, "droidcast_signature_conflict", "手动卸载")
        self.assertEqual(self.android.version, "1.2.1")
        self.assertFalse(any(args[0] == "uninstall" for args in self.android.commands))
        self.assertEqual(self.android.processes, [])
        self.assertEqual(self.android.forwards, {})

    def test_failed_helper_start_releases_forward_and_does_not_restart_emulator(self):
        self.android.spawn_error = OSError("spawn failed")
        result = self.control.capture()
        self.assert_adb_degraded(result, "droidcast_start_failed", "spawn failed")
        self.assertEqual(self.android.forwards, {})
        self.assertEqual(self.simulator.actions, [])

    def test_http_timeout_rebuilds_once_and_keeps_selected_backend(self):
        self.http.failure = requests.ReadTimeout("read stalled")
        with patch.object(
            self.control._adapter, "rebind", wraps=self.control._adapter.rebind
        ) as rebind:
            result = self.control.capture()
        rebind.assert_not_called()
        self.input_control.input_alive.assert_called_once_with()
        self.assert_adb_degraded(result, "droidcast_http_timeout", "超时")
        self.assertEqual(len(self.android.processes), 2)
        self.assertEqual(self.android.processes[0].terminated, 1)
        calls = len(self.http.calls)
        self.assert_adb_degraded(
            self.control.capture(), "droidcast_http_timeout", "超时"
        )
        self.assertEqual(len(self.android.processes), 2)
        self.assertEqual(len(self.http.calls), calls)
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.conf.device.screenshot_backend, "droidcast")
        self.assertFalse(self.http.trust_env)
        self.assertTrue(
            all(
                call[1]["timeout"][0] <= 2 and call[1]["timeout"][1] <= 3
                for call in self.http.calls
            )
        )

    def test_repeated_rebuild_and_close_leave_no_owned_resources(self):
        self.assertTrue(self.control.capture().ok)
        foreign = ("OTHER", "tcp:12345")
        self.android.forwards["tcp:23456"] = foreign
        self.android.remote[456] = "other-program"
        for _ in range(3):
            self.device.rebuild_screenshot()
            self.assertTrue(self.control.capture().ok)
            self.assertEqual(len(self.android.forwards), 2)
            self.assertEqual(len(self.android.remote), 2)
        self.assertTrue(self.control.close().ok)
        self.assertTrue(self.control.close().ok)
        self.assertEqual(self.android.forwards, {"tcp:23456": foreign})
        self.assertEqual(self.android.remote, {456: "other-program"})
        self.assertTrue(
            all(process.terminated == 1 for process in self.android.processes)
        )

    def test_changed_forward_and_remote_process_are_preserved_at_close(self):
        self.assertTrue(self.control.capture().ok)
        port = next(iter(self.android.forwards))
        self.android.forwards[port] = ("OTHER", "tcp:23456")
        self.android.remote[101] = "foreign-process"
        self.assertTrue(self.control.close().ok)
        self.assertEqual(self.android.forwards[port], ("OTHER", "tcp:23456"))
        self.assertEqual(self.android.remote, {101: "foreign-process"})

    def test_gone_remote_helper_is_already_clean_and_forward_is_still_removed(self):
        self.assertTrue(self.control.capture().ok)
        self.android.remote.clear()
        run = self.android.run

        def exited(argv, **kwargs):
            if argv[3:5] == ["shell", "pidof"]:
                raise subprocess.CalledProcessError(1, argv, output=b"", stderr=b"")
            return run(argv, **kwargs)

        with patch(f"{MODULE}.run_adb", exited):
            self.assertTrue(self.control.close().ok)
        self.assertEqual(self.android.forwards, {})

    def test_absent_device_cleanup_is_idempotent_and_preserves_foreign_resources(self):
        self.assertTrue(self.control.capture().ok)
        foreign = ("OTHER", "tcp:12345")
        self.android.forwards = {"tcp:23456": foreign}
        self.android.remote.clear()
        self.android.transport_error = b"adb: device 'USB-A' not found\n"
        self.assertTrue(self.control.close().ok)
        self.assertTrue(self.control.close().ok)
        self.assertEqual(self.android.forwards, {"tcp:23456": foreign})
        self.assertEqual(self.android.processes[0].terminated, 1)
        self.assertEqual(self.http.closed, 1)

    def test_absent_device_cleanup_allows_the_next_verified_instance_start(self):
        self.conf.device.preset_id = "windows.mumu12"
        self.conf.device.instance_id = "0"
        before = self.conf.model_dump()
        self.assertTrue(self.control.capture().ok)
        self.android.remote.clear()
        self.android.forwards.clear()
        self.android.transport_error = b"adb: device 'USB-A' not found\n"
        self.assertTrue(self.control.close().ok)
        self.simulator.state = "stopped"
        self.adb.rows = []

        def start_selected():
            self.simulator.state = "running"
            self.simulator.serial = "USB-A"
            self.adb.rows = [("USB-A", "device")]

        self.simulator.on_start = start_selected
        self.control._adapter = Adapter()
        started = self.control.start()
        self.assertTrue(started.ok, started.error)
        self.assertEqual(started.serial, "USB-A")
        self.assertEqual(self.simulator.actions, ["start"])
        self.assertEqual(self.conf.model_dump(), before)

    def test_unreachable_device_with_owned_forward_remains_a_cleanup_failure(self):
        self.assertTrue(self.control.capture().ok)
        self.android.remote.clear()
        self.android.transport_error = b"adb: device 'USB-A' not found\n"
        self.assertFalse(self.control.close().ok)
        self.assertEqual(self.control.start().error.code, "close_failed")
        self.assertEqual(len(self.android.forwards), 1)
        self.assertEqual(self.android.processes[0].terminated, 1)
        self.assertEqual(self.http.closed, 1)

    def test_offline_transport_is_not_assumed_to_have_no_remote_resources(self):
        self.assertTrue(self.control.capture().ok)
        self.android.forwards.clear()
        self.android.transport_error = b"error: device offline\n"
        self.assertFalse(self.control.close().ok)
        self.assertEqual(self.control.start().error.code, "close_failed")
        self.assertEqual(self.android.processes[0].terminated, 1)
        self.assertEqual(self.http.closed, 1)

    def test_offline_cleanup_recovery_releases_old_owners_before_new_start(self):
        self.assertTrue(self.control.capture().ok)
        before = self.conf.model_dump()
        helper = self.control._device._droidcast
        old_name, old_port = helper.name, helper.port
        self.android.transport_error = b"adb: device offline\n"
        self.assertFalse(self.control.close().ok)
        self.assertFalse(self.control.close().ok)
        self.assertFalse(self.control.recover().ok)
        self.assertEqual(len(self.android.processes), 1)
        self.assertTrue(helper._remote_cleanup_pending)
        self.assertEqual(helper.port, old_port)
        self.assertEqual(self.http.closed, 1)

        self.android.transport_error = None
        self.android.remote[456] = "foreign-process"
        self.android.forwards["tcp:23456"] = ("OTHER", "tcp:12345")
        self.control._adapter = Adapter()
        recovered = self.control.recover()
        self.assertTrue(recovered.ok, recovered.error)
        self.assertEqual(recovered.serial, "USB-A")
        self.assertNotIn(old_name, self.android.remote.values())
        self.assertNotIn(f"tcp:{old_port}", self.android.forwards)
        self.assertEqual(self.android.remote, {456: "foreign-process"})
        self.assertEqual(self.android.forwards, {"tcp:23456": ("OTHER", "tcp:12345")})
        self.assertFalse(helper._remote_cleanup_pending)
        self.assertIsNone(helper._cleanup_error)
        self.assertIsNone(self.control._helper_cleanup_error)
        self.assertIsNone(self.control._cleanup_device)
        self.assertEqual(self.android.processes[0].terminated, 1)
        self.assertEqual(self.http.closed, 1)
        self.assertEqual(self.conf.model_dump(), before)

    def test_cleanup_recovery_preserves_uncertain_input_pause(self):
        self.assertTrue(self.control.capture().ok)
        self.android.transport_error = b"adb: device offline\n"
        self.assertFalse(self.control.close().ok)
        pause = TouchFailure(
            self.conf.device,
            "linux",
            ConnectionError("unverified input"),
            delivery_unknown=True,
        )
        self.control.pause_dispatch(pause)
        self.android.transport_error = None
        self.control._adapter = Adapter()
        recovered = self.control.recover()
        self.assertTrue(recovered.ok, recovered.error)
        self.assertEqual(recovered.status, "paused")
        self.assertIs(self.control._dispatch_pause, pause)

    def test_cleanup_retry_rechecks_replaced_forward_and_remote_identity(self):
        self.assertTrue(self.control.capture().ok)
        helper = self.control._device._droidcast
        port = f"tcp:{helper.port}"
        self.android.transport_error = b"adb: device offline\n"
        self.assertFalse(self.control.close().ok)
        self.android.transport_error = None
        self.android.remote[101] = "foreign-process"
        self.android.forwards[port] = ("OTHER", "tcp:12345")
        self.assertTrue(self.control.close().ok)
        self.assertEqual(self.android.remote, {101: "foreign-process"})
        self.assertEqual(self.android.forwards[port], ("OTHER", "tcp:12345"))
        self.assertTrue(self.control.close().ok)
        self.assertEqual(self.http.closed, 1)

    def test_forward_disappearance_during_remove_is_confirmed_before_success(self):
        self.assertTrue(self.control.capture().ok)
        run = self.android.run

        def disconnected_during_remove(argv, **options):
            if argv[3:5] == ["forward", "--remove"]:
                self.android.forwards.clear()
                raise subprocess.CalledProcessError(
                    1, argv, output=b"", stderr=b"adb: device 'USB-A' not found\n"
                )
            return run(argv, **options)

        with patch(f"{MODULE}.run_adb", disconnected_during_remove):
            self.assertTrue(self.control.close().ok)
        self.assertEqual(self.android.forwards, {})

    def test_device_disappearance_during_process_identity_check_is_already_clean(self):
        self.assertTrue(self.control.capture().ok)
        run = self.android.run

        def disconnected_during_identity(argv, **options):
            if argv[3:5] == ["shell", "cat"]:
                self.android.remote.clear()
                self.android.forwards.clear()
                self.android.transport_error = b"adb: device 'USB-A' not found\n"
            return run(argv, **options)

        with patch(f"{MODULE}.run_adb", disconnected_during_identity):
            self.assertTrue(self.control.close().ok)
        self.assertEqual(self.http.closed, 1)

    def test_other_device_not_found_error_is_not_ignored(self):
        self.assertTrue(self.control.capture().ok)
        self.android.forwards.clear()
        self.android.transport_error = b"adb: device 'USB-B' not found\n"
        self.assertFalse(self.control.close().ok)
        self.assertEqual(self.control.start().error.code, "close_failed")

    def test_unverified_host_inventory_keeps_cleanup_failed(self):
        self.assertTrue(self.control.capture().ok)
        run = self.android.run
        self.android.forwards.clear()
        self.android.remote.clear()
        self.android.transport_error = b"adb: device 'USB-A' not found\n"

        def unavailable_inventory(argv, **options):
            if "--list" in argv:
                raise SharedADBError("共享 ADB 检查失败")
            return run(argv, **options)

        with patch(f"{MODULE}.run_adb", unavailable_inventory):
            self.assertFalse(self.control.close().ok)
        self.assertEqual(self.control.start().error.code, "close_failed")
        self.assertEqual(self.android.processes[0].terminated, 1)
        self.assertEqual(self.http.closed, 1)

    def test_cleanup_inventory_is_a_guarded_host_read_and_mutations_remain_selected(
        self,
    ):
        self.assertTrue(self.control.capture().ok)
        commands = []

        def run_cli(argv, **options):
            commands.append(argv)
            if argv[1:] == ["version"]:
                return subprocess.CompletedProcess(
                    argv, 0, b"Android Debug Bridge version 1.0.41\n", b""
                )
            return self.android.run(argv, **options)

        with (
            patch(f"{MODULE}.run_adb", guarded_run_adb),
            patch(f"{MODULE}.run_command", run_cli),
            patch(
                "arknights_mower.utils.device.adb_client.server.probe_adb_server",
                return_value=41,
            ) as probe,
        ):
            self.assertTrue(self.control.close().ok)
        self.assertGreater(probe.call_count, 0)
        self.assertIn(["chosen-adb", "forward", "--list"], commands)
        for command in commands:
            if command[1:] not in (["version"], ["forward", "--list"]):
                self.assertEqual(command[:3], ["chosen-adb", "-s", "USB-A"])

    def test_malformed_host_inventory_is_not_evidence_of_completed_cleanup(self):
        self.assertTrue(self.control.capture().ok)
        run = self.android.run

        def malformed_inventory(argv, **options):
            if "--list" in argv:
                return SimpleNamespace(stdout=b"invalid inventory output", returncode=0)
            return run(argv, **options)

        with patch(f"{MODULE}.run_adb", malformed_inventory):
            self.assertFalse(self.control.close().ok)
        self.assertEqual(self.control.start().error.code, "close_failed")
        self.assertEqual(self.android.processes[0].terminated, 1)
        self.assertEqual(self.http.closed, 1)

    def test_absent_device_does_not_suppress_host_cleanup_failure(self):
        self.assertTrue(self.control.capture().ok)
        self.android.remote.clear()
        self.android.forwards.clear()
        self.android.transport_error = b"adb: device 'USB-A' not found\n"
        with patch.object(self.http, "close", side_effect=OSError("HTTP close failed")):
            self.assertFalse(self.control.close().ok)
        self.assertEqual(self.control.start().error.code, "close_failed")
        self.assertEqual(self.android.processes[0].terminated, 1)

    def test_stream_read_timeout_is_structured(self):
        def response(*args, **kwargs):
            def stalled(size):
                raise ReadTimeoutError(None, "/screenshot", "body stalled")

            return SimpleNamespace(
                status_code=200, raw=SimpleNamespace(read1=stalled), close=lambda: None
            )

        self.http.get = response
        result = self.control.capture()
        self.assert_adb_degraded(result, "droidcast_http_timeout", "超时")

    def test_adb_install_timeout_and_install_failure_do_not_start_helpers(self):
        run = self.android.run

        def timed_out(argv, **kwargs):
            if argv[3] == "install":
                self.assertLessEqual(kwargs["timeout"], 60)
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            return run(argv, **kwargs)

        with patch(f"{MODULE}.run_adb", timed_out):
            result = self.control.capture()
        self.assert_adb_degraded(result, "droidcast_install_failed", "超时")
        self.assertEqual(self.android.processes, [])
        self.assertEqual(self.android.forwards, {})

    def test_install_failure_degrades_without_starting_a_helper(self):
        self.android.install_output = b"Failure [INSTALL_FAILED_INSUFFICIENT_STORAGE]"
        result = self.control.capture()
        self.assert_adb_degraded(
            result, "droidcast_install_failed", "INSTALL_FAILED_INSUFFICIENT_STORAGE"
        )
        self.assertEqual(self.android.version, "1.2.1")
        self.assertEqual(self.android.processes, [])
        self.assertEqual(self.android.forwards, {})

    def test_zero_exit_without_install_success_is_rejected(self):
        self.android.install_output = b"Failure [INSTALL_FAILED_INTERNAL_ERROR]"
        result = self.control.capture()
        self.assert_adb_degraded(
            result, "droidcast_install_failed", "INSTALL_FAILED_INTERNAL_ERROR"
        )
        self.assertEqual(self.android.version, "1.2.1")
        self.assertEqual(self.android.processes, [])

    def test_frame_request_keeps_the_helper_default_payload(self):
        # `?format=png` measured 180-290ms per frame more than the default
        # JPEG on the same device, with a decoded frame that stays equivalent
        # for recognition. The default is also what the pre-refactor capture
        # path requested, so the query string is part of the hot path contract.
        self.assertTrue(self.control.capture().ok)
        self.assertEqual(len(self.http.calls), 1)
        url = self.http.calls[0][0]
        self.assertTrue(url.endswith("/screenshot"), url)
        self.assertNotIn("format=png", url)

    def test_frame_request_payload_stays_inside_the_vendored_protocol_note(self):
        # The vendored helper's README is the source of truth for this
        # interface: a query parameter it documents that this module also sends
        # is a payload choice, and the default must stay the one it sends. The
        # scan reads code only, so a comment may still name the rejected
        # parameter while explaining why it is rejected.
        note = (
            Path(droidcast.__file__).parent.parent.parent / "vendor/droidcast/README.md"
        )
        documented = set(
            re.findall(r"\?format=([a-z]+)", note.read_text(encoding="utf-8"))
        )
        source = Path(droidcast.__file__).read_text(encoding="utf-8")
        code = "\n".join(
            line.split("#", 1)[0]
            for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )
        used = set(re.findall(r"[?&]format=([a-z]+)", code))
        self.assertIn("png", documented, "README 必须记录 helper 的 PNG 查询参数")
        self.assertEqual(used, set(), "取帧请求只使用 helper 的默认载荷")

    def test_query_failure_never_becomes_an_install_or_uninstall(self):
        self.standard.failure = ConnectionError("device offline")

        def inaccessible(argv, **kwargs):
            self.android.commands.append(argv[3:])
            raise subprocess.CalledProcessError(1, argv, output=b"device offline")

        with patch(f"{MODULE}.run_adb", inaccessible):
            result = self.control.capture()
        self.assertEqual(result.error.code, "droidcast_version_failed")
        self.assertTrue(
            all(args[:3] == ["shell", "pm", "path"] for args in self.android.commands)
        )

    def test_missing_package_exit_one_installs(self):
        self.android.version = None
        run = self.android.run

        def absent(argv, **kwargs):
            if argv[3:6] == ["shell", "pm", "path"] and self.android.version is None:
                raise subprocess.CalledProcessError(1, argv, output=b"", stderr=b"")
            return run(argv, **kwargs)

        with patch(f"{MODULE}.run_adb", absent):
            self.assertTrue(self.control.capture().ok)
        self.assertEqual(self.android.version, "1.3.0")

    def test_matching_foreign_forward_is_not_claimed_or_removed(self):
        self.android.forwards["tcp:54321"] = ("USB-A", "tcp:54321")
        self.android.remote[456] = "foreign-process"
        with patch(f"{MODULE}.get_new_port", return_value=54321):
            result = self.control.capture()
        self.assert_adb_degraded(result, "droidcast_forward_failed", "cannot rebind")
        self.assertEqual(self.android.forwards, {"tcp:54321": ("USB-A", "tcp:54321")})
        self.assertEqual(self.android.remote, {456: "foreign-process"})
        self.assertEqual(self.android.processes, [])

    def test_forward_timeout_does_not_launch_a_helper(self):
        run = self.android.run

        def stalled(argv, **kwargs):
            if argv[3:5] == ["forward", "--no-rebind"]:
                self.assertLessEqual(kwargs["timeout"], 10)
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            return run(argv, **kwargs)

        with patch(f"{MODULE}.run_adb", stalled):
            result = self.control.capture()
        self.assert_adb_degraded(result, "droidcast_forward_failed", "超时")
        self.assertEqual(self.android.processes, [])

    def test_nonzero_install_signature_conflict_keeps_actionable_error(self):
        run = self.android.run

        def incompatible(argv, **kwargs):
            if argv[3] == "install":
                raise subprocess.CalledProcessError(
                    1,
                    argv,
                    output=b"",
                    stderr=b"Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]",
                )
            return run(argv, **kwargs)

        with patch(f"{MODULE}.run_adb", incompatible):
            result = self.control.capture()
        self.assert_adb_degraded(result, "droidcast_signature_conflict", "手动卸载")
        self.assertEqual(self.android.version, "1.2.1")
        self.assertEqual(self.android.processes, [])
        self.assertEqual(self.android.forwards, {})
        self.assertFalse(any(args[0] == "uninstall" for args in self.android.commands))

    def test_wrong_actual_frame_is_rejected_without_switch_or_restart(self):
        self.http.data = cv2.imencode(".png", np.zeros((540, 960, 3), np.uint8))[
            1
        ].tobytes()
        result = self.control.capture()
        self.assertEqual(result.error.code, "frame_size_mismatch")
        # A deterministic size error is terminal: the first helper answered, so
        # no rebuild and no second helper may follow.
        self.assertEqual(len(self.android.processes), 1)
        self.assertEqual(self.simulator.actions, [])

    def test_cleanup_failure_still_closes_host_process_forward_and_http(self):
        self.assertTrue(self.control.capture().ok)
        run = self.android.run

        def failed_kill(argv, **kwargs):
            if argv[3:5] == ["shell", "kill"]:
                raise subprocess.CalledProcessError(
                    1, argv, output=b"permission denied"
                )
            return run(argv, **kwargs)

        with patch(f"{MODULE}.run_adb", failed_kill):
            self.assertFalse(self.control.close().ok)
        self.assertEqual(self.android.forwards, {})
        self.assertEqual(self.android.processes[0].terminated, 1)
        self.assertEqual(self.http.closed, 1)

    def test_actual_cleanup_failure_never_degrades_to_healthy_adb(self):
        self.assertTrue(self.control.capture().ok)
        self.android.forwards["tcp:23456"] = ("OTHER", "tcp:12345")
        self.android.remote[456] = "foreign-process"
        self.http.failure = requests.ReadTimeout("helper capture failed")
        run = self.android.run

        def failed_kill(argv, **kwargs):
            if argv[3:5] == ["shell", "kill"]:
                raise subprocess.CalledProcessError(
                    1, argv, output=b"permission denied"
                )
            return run(argv, **kwargs)

        with patch(f"{MODULE}.run_adb", failed_kill):
            result = self.control.capture()
            self.assertFalse(result.ok)
            self.assertTrue(result.error.cause.cleanup_failed)
            self.assertIn("permission denied", result.error.message)
            self.assertFalse(self.control.recover().ok)
        self.assertEqual(self.standard.commands, [])
        self.assertEqual(self.standard.guards, [])
        self.assertEqual(len(self.android.processes), 1)
        self.assertEqual(self.android.forwards, {"tcp:23456": ("OTHER", "tcp:12345")})
        self.assertEqual(self.android.remote[456], "foreign-process")
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.conf.model_dump(), self.before)

    def test_foreign_helper_ownership_never_rebuilds_or_degrades(self):
        self.assertTrue(self.control.capture().ok)
        self.device._droidcast.owner = os.getpid() + 1
        forwards = dict(self.android.forwards)
        remote = dict(self.android.remote)
        commands = list(self.android.commands)
        result = self.control.capture()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "droidcast_closed")
        self.assertIn("所有权", result.error.message)
        self.assertEqual(self.standard.commands, [])
        self.assertEqual(self.standard.guards, [])
        self.assertEqual(self.android.forwards, forwards)
        self.assertEqual(self.android.remote, remote)
        self.assertEqual(self.android.commands, commands)
        self.assertEqual(len(self.android.processes), 1)
        self.assertEqual(self.android.processes[0].terminated, 0)
        self.assertEqual(self.http.closed, 0)
        self.assertEqual(self.conf.model_dump(), self.before)

    def test_degraded_capture_does_not_adopt_another_online_target(self):
        self.http.failure = requests.ReadTimeout("helper unavailable")
        self.assert_adb_degraded(self.control.capture(), "droidcast_http_timeout")
        commands = list(self.standard.commands)
        self.adb.rows = [("OTHER", "device")]
        result = self.control.capture()
        self.assertFalse(result.ok)
        self.assertEqual(self.standard.commands, commands)
        self.assertEqual(self.control.serial, "USB-A")
        self.assertEqual(self.control._session.profile.last_serial, "USB-A")
        self.assertEqual(self.conf.model_dump(), self.before)
        self.assertEqual(len(self.android.processes), 2)

    def test_interruption_keeps_helper_and_forward_owned_until_final_close(self):
        self.assertTrue(self.control.capture().ok)
        expected_forwards = dict(self.android.forwards)
        expected_helpers = dict(self.android.remote)
        self.device.interrupt_io()
        self.device.interrupt_io()
        self.assertEqual(self.android.forwards, expected_forwards)
        self.assertEqual(self.android.remote, expected_helpers)
        self.assertIsNone(self.android.processes[0].poll())
        self.assertEqual(self.http.closed, 0)
        self.assertTrue(self.control.close().ok)
        self.assertEqual(self.android.forwards, {})
        self.assertEqual(self.android.remote, {})
        self.assertEqual(self.http.closed, 1)

    def test_closed_device_does_not_reuse_the_previous_serial_on_reopen(self):
        self.assertTrue(self.control.capture().ok)
        self.device.close()
        self.android.serial = self.device.device_id = "USB-B"
        self.device.client = SimpleNamespace(adb_bin="chosen-adb", device_id="USB-B")
        self.assertTrue(self.device.start_droidcast())
        self.assertEqual(
            {mapping[0] for mapping in self.android.forwards.values()}, {"USB-B"}
        )

    def test_forward_success_is_owned_even_if_post_command_deadline_expires(self):
        def postcheck(argv, **kwargs):
            if argv[3:5] == ["forward", "--no-rebind"]:
                runner = kwargs.pop("run")
                runner(argv, **kwargs)
                raise SharedADBError("post-command deadline exhausted")
            return self.android.run(argv, **kwargs)

        with (
            patch(f"{MODULE}.run_adb", postcheck),
            patch(f"{MODULE}.run_command", self.android.run),
        ):
            result = self.control.capture()
        self.assert_adb_degraded(
            result, "droidcast_forward_failed", "post-command deadline exhausted"
        )
        self.assertEqual(self.android.forwards, {})
        self.assertEqual(self.android.processes, [])

    # A frame is the hot path: the ownership check runs per frame before, and
    # each run is an `adb forward --list` subprocess. Reading the mapping is
    # counted here so the cadence is asserted instead of assumed.
    def forward_reads(self):
        return sum(args == ["forward", "--list"] for args in self.android.commands)

    def test_steady_capture_reads_the_mapping_once_not_once_per_frame(self):
        self.assertTrue(self.control.capture().ok)
        after_session = self.forward_reads()
        self.assertEqual(after_session, 1)
        for _ in range(5):
            self.assertTrue(self.control.capture().ok)
        self.assertEqual(
            self.forward_reads(),
            after_session,
            "每帧都读转发映射会让一个 adb 子进程进入取帧热路径",
        )

    def test_mapping_is_revalidated_once_per_configured_interval(self):
        with patch.object(droidcast, "MAPPING_CHECK_FRAMES", 5):
            self.assertTrue(self.control.capture().ok)
            self.assertEqual(self.forward_reads(), 1)
            for _ in range(3):
                self.assertTrue(self.control.capture().ok)
            self.assertEqual(self.forward_reads(), 1, "周期检查不得提前触发")
            self.assertTrue(self.control.capture().ok)
            self.assertEqual(self.forward_reads(), 2, "周期检查必须按配置的帧数触发")

    def test_changed_mapping_is_recovered_with_one_rebuild(self):
        # The claim is proven by the first frame after the start.
        self.assertTrue(self.control.capture().ok)
        self.assertEqual(len(self.android.processes), 1)
        port = next(iter(self.android.forwards))
        del self.android.forwards[port]
        # Arm the next periodic read: a rebuilt session arms it the same way,
        # and the constant is read when an interval is armed.
        self.device._droidcast._frames_until_mapping_check = 0
        result = self.control.capture()
        # A changed mapping must still be noticed and answered by exactly one
        # rebuild: a check that stopped noticing would be worse than none.
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(self.android.processes), 2, "映射变化必须触发一次重建")
        self.assertEqual(len(self.android.forwards), 1, "重建后只保留一条自己的转发")
        serial, _ = next(iter(self.android.forwards.values()))
        self.assertEqual(serial, "USB-A")
        self.assertEqual(self.android.processes[0].terminated, 1)

    def test_missing_mapping_and_input_eof_rebuild_capture_before_degradation(self):
        self.assertTrue(self.control.capture().ok)
        helper = self.device._droidcast
        del self.android.forwards[f"tcp:{helper.port}"]
        helper._frames_until_mapping_check = 0
        self.android.forwards["tcp:23456"] = ("OTHER", "tcp:12345")
        self.input_control.input_alive.return_value = False

        def repair_input():
            self.input_control.input_alive.return_value = True

        self.device.rebuild_input = Mock(side_effect=repair_input)
        rebind = self.control._adapter.rebind

        self.control._adapter.rebind = Mock(wraps=rebind)
        result = self.control.capture()
        self.assertTrue(result.ok, result.error)
        self.assertFalse(
            self.control.settings_status()["screenshot_backend"]["degraded"]
        )
        self.assertTrue(np.all(result.value == 0))
        self.assertEqual(len(self.android.processes), 2)
        self.device.rebuild_input.assert_called_once()
        self.control._adapter.rebind.assert_not_called()
        self.assertEqual(self.android.forwards["tcp:23456"], ("OTHER", "tcp:12345"))
        self.assertEqual(self.conf.model_dump(), self.before)
        self.assertEqual(self.simulator.actions, [])

    def test_held_swipe_keeps_degraded_backend_and_releases_once(self):
        self.http.failure = requests.ReadTimeout("read stalled")
        self.assert_adb_degraded(self.control.capture(), "droidcast_http_timeout")
        self.android.forwards.clear()
        self.android.forwards["tcp:23456"] = ("OTHER", "tcp:12345")
        self.device._droidcast._frames_until_mapping_check = 0
        helper_calls = len(self.android.commands), len(self.http.calls)
        events = []

        def swipe(*args, before_release, **kwargs):
            events.append("down")
            before_release()
            events.append("up")

        self.input_control.swipe_ext = swipe
        for name, value in (
            ("screenshot_time", datetime.min),
            ("screenshot_avg", None),
            ("screenshot_count", 0),
        ):
            self.enterContext(patch.object(config, name, value))
        self.conf.screenshot_interval = 0
        before = self.conf.model_dump()
        with (
            patch("arknights_mower.utils.device.device.budget_sleep", self.clock.sleep),
            patch("arknights_mower.utils.device.device.save_screenshot_frame"),
        ):
            result = self.control.execute(
                lambda device: device.swipe_ext(
                    [(900, 970), (800, 970)], [0], up_wait=400, capture=True
                )
            )
        self.assertTrue(result.ok, result.error)
        self.assertTrue(np.array_equal(result.value[1], self.standard.frame))
        self.assertEqual(events, ["down", "up"])
        self.assertEqual(
            (len(self.android.commands), len(self.http.calls)), helper_calls
        )
        self.assertEqual(self.conf.model_dump(), before)
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.adb.actions, [])
        self.assertEqual(self.android.forwards, {"tcp:23456": ("OTHER", "tcp:12345")})

    def test_held_degraded_capture_failure_releases_without_helper_recovery(self):
        self.http.failure = requests.ReadTimeout("read stalled")
        self.assert_adb_degraded(self.control.capture(), "droidcast_http_timeout")
        self.standard.failure = OSError("ADB capture unavailable")
        helper_calls = len(self.android.commands), len(self.http.calls)
        events = []

        def swipe(*args, before_release, **kwargs):
            before_release()
            events.append("up")

        self.input_control.swipe_ext = swipe
        self.conf.screenshot_interval = 0
        with patch(
            "arknights_mower.utils.device.device.budget_sleep", self.clock.sleep
        ):
            result = self.control.execute(
                lambda device: device.swipe_ext(
                    [(900, 970), (800, 970)], [0], up_wait=400, capture=True
                )
            )
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "screenshot_failed")
        self.assertEqual(events, ["up"])
        self.assertIsNone(getattr(self.device, "_recovery_error", None))
        self.assertEqual(
            (len(self.android.commands), len(self.http.calls)), helper_calls
        )
        self.assertEqual(self.simulator.actions, [])

    def test_held_capture_cancellation_does_not_close_resources_before_release(self):
        self.assertTrue(self.control.capture().ok)
        helper_calls = len(self.android.commands), len(self.http.calls)
        events = []

        def swipe(*args, before_release, **kwargs):
            self.control._pending_close.set()
            self.control._deferred_close = True
            before_release()
            self.input_control.close.assert_not_called()
            self.assertEqual(
                (len(self.android.commands), len(self.http.calls)), helper_calls
            )
            events.append("up")

        self.input_control.swipe_ext = swipe
        self.conf.screenshot_interval = 0
        with patch(
            "arknights_mower.utils.device.device.budget_sleep", self.clock.sleep
        ):
            result = self.control.execute(
                lambda device: device.swipe_ext(
                    [(900, 970), (800, 970)], [0], up_wait=400, capture=True
                )
            )
        self.assertFalse(result.ok)
        self.assertEqual(events, ["up"])
        self.assertIsNone(self.control._device)
        self.assertEqual(self.simulator.actions, [])


if __name__ == "__main__":
    unittest.main()
