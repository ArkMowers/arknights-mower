"""LD native ABI, binding and ownership tests without emulator I/O."""

import ctypes
import os
import tempfile
import unittest
from pathlib import Path
from threading import Event, RLock
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device import ldplayer_capture as ld
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.preflight_io import ProductionPreflightIO
from arknights_mower.utils.device.screenshot_backend import FrameSizeMismatch


class LDRendererTests(unittest.TestCase):
    def test_x64_vtable_capture_converts_bottom_up_bgr_and_releases_once(self):
        pixels = np.zeros((1080, 1920, 3), np.uint8)
        pixels[-1, 0] = [17, 31, 255]
        pixels[0, 0] = [9, 8, 7]
        released, captured = [], []
        cap = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)(
            lambda this: captured.append(this) or pixels.ctypes.data
        )
        release = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(released.append)
        table = (ctypes.c_void_p * 3)(
            0, ctypes.cast(cap, ctypes.c_void_p), ctypes.cast(release, ctypes.c_void_p)
        )
        instance = ctypes.pointer(table)
        address = ctypes.addressof(instance)
        dll = MagicMock()
        dll.CreateScreenShotInstance.return_value = address
        with patch.object(ld.ctypes, "CDLL", return_value=dll):
            renderer = ld._LDRenderer("ldopengl64.dll", 3, 42)
        frame = renderer.capture_frame()
        self.assertEqual(frame[0, 0].tolist(), [255, 31, 17])
        self.assertEqual(frame[-1, 0].tolist(), [7, 8, 9])
        pixels[:] = 0
        self.assertEqual(frame[0, 0].tolist(), [255, 31, 17])
        self.assertEqual(captured, [address])
        dll.CreateScreenShotInstance.assert_called_once_with(3, 42)
        renderer.close()
        renderer.close()
        self.assertEqual(released, [address])

    def test_null_handle_reports_failure(self):
        dll = MagicMock()
        dll.CreateScreenShotInstance.return_value = None
        with patch.object(ld.ctypes, "CDLL", return_value=dll):
            with self.assertRaisesRegex(ld.LDCaptureError, "无法连接"):
                ld._LDRenderer("ldopengl64.dll", 3, 42)

    def test_worker_reuses_renderer_and_always_releases_it(self):
        channel = MagicMock()
        channel.recv.side_effect = ["capture", "capture", EOFError()]
        shared = (ctypes.c_ubyte * (1080 * 1920 * 3))()
        renderer = MagicMock()
        renderer.capture_frame.return_value = np.zeros((1080, 1920, 3), np.uint8)
        with patch.object(ld, "_LDRenderer", return_value=renderer) as factory:
            ld._capture_worker("dll", 3, 42, shared, channel)
        factory.assert_called_once_with("dll", 3, 42)
        self.assertEqual(renderer.capture_frame.call_count, 2)
        self.assertEqual(channel.send.call_count, 2)
        renderer.close.assert_called_once()
        channel.close.assert_called_once()

    def test_worker_bounds_errors_and_releases_renderer(self):
        channel = MagicMock()
        channel.recv.return_value = "capture"
        renderer = MagicMock()
        renderer.capture_frame.side_effect = ld.LDCaptureError("失败" * 2000)
        shared = (ctypes.c_ubyte * (1080 * 1920 * 3))()
        with patch.object(ld, "_LDRenderer", return_value=renderer):
            ld._capture_worker("dll", 3, 42, shared, channel)
        status, message, _, _ = channel.send.call_args.args[0]
        self.assertEqual(status, "error")
        self.assertLessEqual(len(message.encode()), 1024)
        renderer.close.assert_called_once()


class LDCaptureSessionTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root / "ldopengl64.dll").touch()
        self.enterContext(
            patch.object(
                ld,
                "locate_ldplayer_manager",
                return_value=(root / "ldconsole.exe", root),
            )
        )
        self.enterContext(patch.object(ld.platform, "system", return_value="Windows"))
        self.enterContext(patch.object(ld.platform, "machine", return_value="AMD64"))
        self.run = self.enterContext(patch.object(ld, "run_manager_command"))
        self.row = b"3,mower,123,456,1,42,84,1920,1080,240"
        self.run.return_value = SimpleNamespace(stdout=self.row)
        self.resolver = self.enterContext(
            patch.object(ld, "LDPlayerEndpointResolver")
        ).return_value
        self.resolver.inspect.return_value = SimpleNamespace(
            state="running", serial="emulator-5560"
        )
        self.factory = self.enterContext(patch.object(ld, "NativeCaptureSession"))
        self.native = self.factory.return_value
        self.native.capture_frame.return_value = np.zeros((1080, 1920, 3), np.uint8)
        self.profile = DeviceProfile(
            preset_id="windows.ldplayer9",
            instance_id="3",
            instance_name="mower",
            screenshot_backend="ld_native",
        )
        self.session = ld.LDCaptureSession(self.profile, "adb.exe", "emulator-5560")
        self.addCleanup(self.session.close)

    def test_reuses_worker_without_persisting_observed_pid_or_endpoint(self):
        self.session.capture_frame()
        self.session.capture_frame()
        self.factory.assert_called_once()
        self.assertEqual(self.factory.call_args.args[1][1:], (3, 42))
        self.assertEqual(self.profile.last_serial, "")
        self.assertEqual(self.native.capture_frame.call_count, 2)
        self.resolver.inspect.assert_called_once()
        self.session.close()
        self.native.close.assert_called_once()

    def test_mismatched_endpoint_never_starts_worker(self):
        self.resolver.inspect.return_value.serial = "other-device"
        with self.assertRaisesRegex(ld.LDCaptureError, "不一致"):
            self.session.capture_frame()
        self.factory.assert_not_called()

    def test_pid_change_during_frame_discards_it_and_latches_failure(self):
        self.run.side_effect = [
            SimpleNamespace(stdout=row)
            for row in (self.row, self.row, self.row.replace(b",42,84,", b",43,85,"))
        ]
        with self.assertRaisesRegex(ld.LDCaptureError, "进程已变化"):
            self.session.capture_frame()
        with self.assertRaisesRegex(ld.LDCaptureError, "进程已变化"):
            self.session.capture_frame()
        self.native.capture_frame.assert_called_once()

    def test_wrong_size_never_reads_native_memory(self):
        self.run.return_value.stdout = self.row.replace(b"1920,1080", b"1280,720")
        with self.assertRaises(FrameSizeMismatch):
            self.session.capture_frame()
        self.factory.assert_not_called()

    def test_oversized_instance_id_never_wraps_into_a_different_vendor_target(self):
        self.session._profile.instance_id = str(2**32 + 3)
        self.run.return_value.stdout = self.row.replace(b"3,mower", b"4294967299,mower")
        with self.assertRaisesRegex(ld.LDCaptureError, "超出"):
            self.session.capture_frame()
        self.factory.assert_not_called()
        self.resolver.inspect.assert_not_called()

    def test_unreported_size_never_reads_native_memory(self):
        self.run.return_value.stdout = b"3,mower,123,456,1,42,84"
        with self.assertRaisesRegex(ld.LDCaptureError, "未报告画面尺寸"):
            self.session.capture_frame()
        self.factory.assert_not_called()

    def test_parent_budget_bounds_manager_queries_and_native_capture(self):
        with device_io_budget(lambda: 0.25):
            self.session.capture_frame()
        self.assertTrue(
            all(call.kwargs["timeout"] <= 0.25 for call in self.run.call_args_list)
        )
        self.assertLessEqual(self.resolver.inspect.call_args.args[2], 0.25)

    def test_close_before_first_frame_prevents_binding(self):
        self.session.close()
        with self.assertRaisesRegex(ld.LDCaptureError, "关闭"):
            self.session.capture_frame()
        self.run.assert_not_called()

    def test_wrong_preset_rejected_without_manager_or_native_calls(self):
        self.session._profile.preset_id = "windows.mumu12"
        with self.assertRaisesRegex(ld.LDCaptureError, "仅适用于"):
            self.session.capture_frame()
        self.run.assert_not_called()
        self.factory.assert_not_called()

    def test_ldplayer14_uses_verified_instance_capture(self):
        self.session._profile.preset_id = "windows.ldplayer14"
        frame = self.session.capture_frame()
        self.assertIs(frame, self.native.capture_frame.return_value)
        self.resolver.inspect.assert_called_once()
        self.assertEqual(self.factory.call_args.args[1][1:], (3, 42))

    def test_preflight_closes_capture_after_failure(self):
        with patch(
            "arknights_mower.utils.device.preflight_io.LDCaptureSession"
        ) as factory:
            factory.return_value.capture_frame.side_effect = TimeoutError("capture")
            with self.assertRaises(TimeoutError):
                ProductionPreflightIO().capture_frame(
                    "adb.exe", "emulator-5560", self.profile
                )
            factory.return_value.close.assert_called_once()

    def test_runtime_reuses_rebuilds_interrupts_and_closes_ld_capture(self):
        device = object.__new__(Device)
        device.device_id = "emulator-5560"
        device.client = MagicMock(adb_bin="adb.exe")
        device.control = MagicMock()
        device.owner_pid = os.getpid()
        device._resource_lock = RLock()
        device._interrupted = Event()
        device._close_error = None
        first, second = MagicMock(), MagicMock()
        first.capture_frame.return_value = self.native.capture_frame.return_value
        second.capture_frame.return_value = self.native.capture_frame.return_value
        with (
            patch(
                "arknights_mower.utils.device.device.config.conf",
                SimpleNamespace(device=self.profile),
            ),
            patch("arknights_mower.utils.device.device.__system__", "windows"),
            patch(
                "arknights_mower.utils.device.device.LDCaptureSession",
                side_effect=[first, second],
            ) as factory,
        ):
            device.capture_frame()
            device.capture_frame()
            factory.assert_called_once_with(self.profile, "adb.exe", "emulator-5560")
            device.rebuild_screenshot()
            first.close.assert_called_once()
            device.capture_frame()
            self.assertEqual(factory.call_count, 2)
            device.interrupt_io()
            second.interrupt.assert_called_once()
            device.close()
            second.close.assert_called_once()
            self.assertIsNone(device._ld_capture)
