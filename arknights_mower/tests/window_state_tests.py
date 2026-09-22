"""Regression tests for the existing native window state and normal bounds."""

import os
import unittest
from unittest import mock

from arknights_mower.utils import window_shell


class TestWindowSizing(unittest.TestCase):
    def test_restore_default_smaller_than_small_work_area(self):
        with mock.patch.object(
            window_shell,
            "_screen_work_area",
            return_value=window_shell.WindowSize(1280, 680),
        ):
            size = window_shell.default_desktop_window_size()
        self.assertEqual(size, window_shell.WindowSize(1024, 612))

    def test_non_windows_state_uses_existing_native_events(self):
        win = mock.Mock()
        bridge = window_shell.WindowShellBridge(win, system="linux")
        bridge._on_maximized()
        self.assertTrue(bridge.get_window_state()["maximized"])


@unittest.skipUnless(os.name == "nt", "Win32 native window probe")
class TestWindowsLiveState(unittest.TestCase):
    def test_native_state_supersedes_early_stale_event(self):
        from arknights_mower.utils import windows_frameless

        user32 = mock.Mock()
        user32.IsWindow.return_value = 1
        user32.IsIconic.return_value = 0
        user32.IsZoomed.return_value = 1
        win = mock.Mock()
        bridge = window_shell.WindowShellBridge(win, system="Windows")
        # A restored callback arriving before the JS listener must not force
        # the title bar to send another maximize command.
        bridge._on_restored()
        with (
            mock.patch.object(windows_frameless, "_winforms_hwnd", return_value=42),
            mock.patch("ctypes.WinDLL", return_value=user32),
        ):
            self.assertTrue(bridge.get_window_state()["maximized"])
            user32.IsZoomed.return_value = 0
            self.assertFalse(bridge.get_window_state()["maximized"])

    def test_unavailable_native_handle_falls_back_to_last_event(self):
        from arknights_mower.utils import windows_frameless

        bridge = window_shell.WindowShellBridge(mock.Mock(), system="Windows")
        bridge._on_maximized()
        with mock.patch.object(
            windows_frameless, "_winforms_hwnd", side_effect=RuntimeError("gone")
        ):
            self.assertTrue(bridge.get_window_state()["maximized"])
