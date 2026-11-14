"""Capture selection is checked at save and preflight boundaries offline."""

import unittest
from unittest.mock import MagicMock

from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.preflight import PreflightService


class CaptureCompatibilityTests(unittest.TestCase):
    def test_save_rejects_vendor_capture_for_other_presets(self):
        for preset, backend in (
            ("manual.other", "mumu_ipc"),
            ("windows.ldplayer9", "mumu_ipc"),
            ("windows.mumu6", "mumu_ipc"),
            ("windows.mumu12", "ld_native"),
            ("windows.ldplayer14", "mumu_ipc"),
            ("windows.nox", "ld_native"),
        ):
            with self.subTest(preset=preset, backend=backend):
                conf = Conf(device={"preset_id": preset})
                with self.assertRaisesRegex(ValueError, "仅适用于"):
                    conf.updated(
                        {
                            "device": {
                                "screenshot_backend": backend,
                                "touch_backend": "mumu_ipc"
                                if backend == "mumu_ipc"
                                else "scrcpy",
                            }
                        }
                    )

    def test_ld_selection_round_trips_without_changing_touch(self):
        for preset in ("windows.ldplayer9", "windows.ldplayer14"):
            with self.subTest(preset=preset):
                conf = Conf(device={"preset_id": preset, "touch_backend": "maatouch"})
                updated = conf.updated({"device": {"screenshot_backend": "ld_native"}})
                loaded = Conf(**updated.model_dump())
                self.assertEqual(loaded.device.preset_id, preset)
                self.assertEqual(loaded.device.screenshot_backend, "ld_native")
                self.assertEqual(loaded.device.touch_backend, "maatouch")
                self.assertFalse(loaded.mumu12IPC)

    def test_preflight_rejects_incompatible_legacy_profile_without_io(self):
        for preset, host in (("manual.other", "windows"), ("windows.mumu12", "linux")):
            io = MagicMock()
            profile = DeviceProfile(
                preset_id=preset,
                screenshot_backend="mumu_ipc",
                touch_backend="mumu_ipc",
            )
            io.host_platform.return_value = host
            result = PreflightService(io).check(profile)
            self.assertFalse(result.ok)
            self.assertEqual(result.error.code, "screenshot_backend_incompatible")
            io.capture_frame.assert_not_called()
            io.validate_adb.assert_not_called()
