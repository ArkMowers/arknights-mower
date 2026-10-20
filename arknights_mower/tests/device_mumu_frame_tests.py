"""MuMu native frame contracts, with only the DLL boundary replaced offline."""

import ctypes
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from arknights_mower.utils import config
from arknights_mower.utils.device.mumu12ipc.core import MuMu12IPC, MuMuIpcError


class NativeRenderer:
    def __init__(
        self, *, code=0, width=1920, height=1080, pixels=(), connection=7, display=0
    ):
        self.code = code
        self.width = width
        self.height = height
        self.pixels = pixels
        self.connection = connection
        self.display = display
        self.connect_calls = 0
        self.disconnected = []

    def nemu_connect(self, root, index):
        self.connect_calls += 1
        return self.connection

    def nemu_disconnect(self, connection):
        self.disconnected.append(connection)

    def nemu_get_display_id(self, connection, package, index):
        return self.display

    def nemu_capture_display(self, connection, display, size, width, height, buffer):
        if self.width is not None:
            ctypes.cast(width, ctypes.POINTER(ctypes.c_int))[0] = self.width
        if self.height is not None:
            ctypes.cast(height, ctypes.POINTER(ctypes.c_int))[0] = self.height
        ctypes.memset(buffer, 0, size)
        for offset, *pixel in self.pixels:
            buffer[offset : offset + 4] = pixel
        return self.code


def connected_ipc(renderer):
    ipc = object.__new__(MuMu12IPC)
    ipc._dll = renderer
    ipc._conn = 7
    ipc._display_id = 0
    ipc._buffer = None
    ipc._manager = "MuMuManager.exe"
    ipc._index = 0
    ipc._app_index = 0
    ipc._emu_root = "MuMu"
    return ipc


class MuMuFrameTests(unittest.TestCase):
    def test_native_capture_error_reaches_caller_instead_of_a_black_frame(self):
        ipc = connected_ipc(NativeRenderer(code=-5, width=1280, height=720))
        with self.assertRaises(MuMuIpcError) as caught:
            ipc.capture_display()
        self.assertEqual(caught.exception.return_code, -5)
        self.assertEqual(caught.exception.actual_size, (1280, 720))
        self.assertIn("-5", str(caught.exception))
        self.assertIn("1280×720", str(caught.exception))

    def test_native_success_with_wrong_dimensions_is_rejected(self):
        for width, height in ((1280, 720), (1080, 1920), (0, 0)):
            with self.subTest(width=width, height=height):
                ipc = connected_ipc(NativeRenderer(width=width, height=height))
                with self.assertRaises(MuMuIpcError) as caught:
                    ipc.capture_display()
                self.assertEqual(caught.exception.return_code, 0)
                self.assertEqual(caught.exception.actual_size, (width, height))

    def test_short_native_buffer_is_reported_as_frame_failure(self):
        ipc = connected_ipc(NativeRenderer())
        ipc._buffer = (ctypes.c_ubyte * 8)()
        with self.assertRaises(MuMuIpcError) as caught:
            ipc.capture_display()
        self.assertIn("8", str(caught.exception))

    def test_offline_frames_preserve_errors_black_pixels_and_owned_rgb(self):
        fixtures = json.loads(
            (Path(__file__).parent / "fixtures/mumu_frames.json").read_text()
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture["name"]):
                renderer = NativeRenderer(
                    **{key: value for key, value in fixture.items() if key != "name"}
                )
                ipc = connected_ipc(renderer)
                if fixture["name"] in ("native_error", "wrong_dimensions"):
                    with self.assertRaises(MuMuIpcError):
                        ipc.capture_display()
                    continue
                frame = ipc.capture_display()
                self.assertEqual(frame.shape, (1080, 1920, 3))
                self.assertEqual(frame.dtype, np.uint8)
                if fixture["name"] == "valid_black":
                    self.assertFalse(np.any(frame))
                else:
                    self.assertEqual(frame[1079, 0].tolist(), [255, 31, 17])
                    self.assertEqual(frame[0, 1919].tolist(), [11, 22, 233])
                    renderer.pixels = ()
                    self.assertFalse(np.any(ipc.capture_display()))
                    self.assertEqual(frame[1079, 0].tolist(), [255, 31, 17])

    def test_failed_connection_reports_native_error_without_nested_rebuild(self):
        for code in (0, -2):
            with (
                self.subTest(code=code),
                patch(
                    "arknights_mower.utils.device.mumu12ipc.core.subprocess.run",
                    return_value=SimpleNamespace(
                        stdout="player index: 0\nstate: state=start_finished\n"
                    ),
                ),
            ):
                renderer = NativeRenderer(connection=code)
                ipc = connected_ipc(renderer)
                ipc._conn = 0
                ipc._display_id = -1
                with self.assertRaises(MuMuIpcError) as caught:
                    ipc.capture_display()
                self.assertEqual(caught.exception.return_code, code)
                self.assertEqual(renderer.connect_calls, 1)
                ipc.disconnect()
                self.assertEqual(renderer.disconnected, [])

    def test_display_binding_error_keeps_native_code_and_owned_connection(self):
        renderer = NativeRenderer(display=-4)
        ipc = connected_ipc(renderer)
        ipc._display_id = -1
        with self.assertRaises(MuMuIpcError) as caught:
            ipc.capture_display()
        self.assertEqual(caught.exception.return_code, -4)
        self.assertIn("-4", str(caught.exception))
        ipc.disconnect()
        self.assertEqual(renderer.disconnected, [7])

    def test_success_without_native_dimensions_is_not_assumed_to_be_1080p(self):
        ipc = connected_ipc(NativeRenderer(width=None, height=None))
        with self.assertRaises(MuMuIpcError) as caught:
            ipc.capture_display()
        self.assertEqual(caught.exception.actual_size, (0, 0))


class MuMuRendererSelectionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.generic = self.root / "nx_main/sdk/external_renderer_ipc.dll"
        self.generic.parent.mkdir(parents=True)
        self.generic.touch()
        self.legacy = self.root / "shell/sdk/external_renderer_ipc.dll"
        self.legacy.parent.mkdir(parents=True)
        self.legacy.touch()
        self.sdk = self.root / "nx_device/12.0/shell/sdk/external_renderer_ipc.dll"
        self.sdk.parent.mkdir(parents=True)
        self.sdk.touch()
        self.manager = self.root / "nx_main/MuMuManager.exe"
        self.manager.touch()

    def load(self, adb_path="", *, broken=None):
        def load_library(path):
            if Path(path) == broken or not Path(path).is_file():
                raise OSError("Native library unavailable")
            return MagicMock()

        library = self.enterContext(patch("ctypes.CDLL", side_effect=load_library))
        configuration = SimpleNamespace(
            simulator=SimpleNamespace(simulator_folder=str(self.root), index="0"),
            device=SimpleNamespace(
                manager_path=str(self.manager), adb_path=str(adb_path)
            ),
        )
        with patch.object(config, "conf", configuration):
            MuMu12IPC(MagicMock())
        return library

    def test_android12_sdk_wins_for_default_generic_and_external_adb(self):
        for adb_path in (
            "",
            self.root / "nx_main/adb.exe",
            self.root.parent / "platform-tools/adb.exe",
            self.root.parent / "other/nx_device/12.0/shell/adb.exe",
        ):
            with self.subTest(adb_path=adb_path):
                library = self.load(adb_path)
                self.assertEqual(
                    [Path(call.args[0]) for call in library.call_args_list], [self.sdk]
                )

    def test_missing_android12_sdk_keeps_legacy_shell_sdk(self):
        self.sdk.unlink()
        library = self.load()
        self.assertEqual(Path(library.call_args.args[0]), self.legacy)

    def test_missing_device_and_legacy_sdks_keeps_generic_candidate_fallback(self):
        self.sdk.unlink()
        self.legacy.unlink()
        library = self.load()
        self.assertEqual(Path(library.call_args.args[0]), self.generic)

    def test_unloadable_android12_sdk_does_not_fall_back_to_other_libraries(self):
        with self.assertRaises(MuMuIpcError):
            self.load(broken=self.sdk)


if __name__ == "__main__":
    unittest.main()
