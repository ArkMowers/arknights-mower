"""Read-only preflight contracts with deterministic host and device adapters."""

import unittest
from unittest.mock import patch

import numpy as np

from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.preflight import PreflightService


class PreflightIO:
    def __init__(self):
        self.host = "linux"
        self.paths = {"manual-adb", "product-adb", "sdk-adb", "path-adb"}
        self.product_paths = ["product-adb"]
        self.sdk_paths = ["sdk-adb"]
        self.path_paths = ["path-adb"]
        self.installed = {"/installed"}
        self.targets = [("USB-123", "device")]
        self.boot = "1"
        self.size = "Physical size: 1920x1080"
        self.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.installed_packages = ["com.hypergryph.arknights.bilibili"]

    def host_platform(self):
        return self.host

    def installation_exists(self, path):
        return path in self.installed

    def product_adb_paths(self, profile):
        return self.product_paths

    def sdk_adb_paths(self):
        return self.sdk_paths

    def path_adb_paths(self):
        return self.path_paths

    def validate_adb(self, path):
        return path in self.paths

    def normalize_adb_path(self, path):
        return path

    def devices(self, adb_path, serial):
        return self.targets

    def boot_completed(self, adb_path, serial):
        return self.boot

    def display_size(self, adb_path, serial):
        return self.size

    def capture_frame(self, adb_path, serial, profile):
        return self.frame

    def packages(self, adb_path, serial):
        return self.installed_packages


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.io = PreflightIO()
        self.profile = DeviceProfile(last_serial="USB-123", adb_path="manual-adb")
        self.service = PreflightService(self.io)

    def test_explicit_ready_target_returns_host_and_only_installed_package(self):
        result = self.service.check(self.profile).to_dict()
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["host_platform"], "linux")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["serial"], "USB-123")
        self.assertEqual(result["adb_path"], "manual-adb")
        self.assertEqual(result["game_package"], "com.hypergryph.arknights.bilibili")
        self.assertEqual(result["observations"]["physical"], [1920, 1080])
        self.assertEqual(result["observations"]["frame"], [1920, 1080])

    def test_only_an_explicit_unique_online_target_can_be_probed(self):
        cases = (
            ("", [("USB-123", "device")], "target_required", ["last_serial"]),
            (
                "",
                [("USB-123", "device"), ("USB-456", "device")],
                "multiple_devices",
                ["last_serial"],
            ),
            ("USB-123", [("USB-456", "device")], "target_absent", ["last_serial"]),
            (
                "USB-123",
                [("USB-123", "device"), ("USB-123", "device")],
                "target_ambiguous",
                ["last_serial"],
            ),
            ("USB-123", [("USB-123", "offline")], "device_offline", []),
            ("USB-123", [("USB-123", "unauthorized")], "device_unauthorized", []),
        )
        for serial, targets, code, fields in cases:
            with self.subTest(code=code):
                self.profile.last_serial = serial
                self.io.targets = targets
                result = self.service.check(self.profile)
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, code)
                self.assertEqual(result.error.fields, fields)
                self.assertEqual(result.error.action, "retry")
                self.assertTrue(result.error.message)
                self.assertEqual(result.observations, {})

    def test_explicit_target_does_not_require_other_online_devices_to_disconnect(self):
        self.io.targets = [("USB-456", "device"), ("USB-123", "device")]
        result = self.service.check(self.profile)
        self.assertTrue(result.ok)
        self.assertEqual(result.serial, "USB-123")

    def test_uses_first_verified_adb_in_manual_product_sdk_path_order(self):
        for expected in ("manual-adb", "product-adb", "sdk-adb", "path-adb"):
            with self.subTest(expected=expected):
                result = self.service.check(self.profile)
                self.assertTrue(result.ok)
                self.assertEqual(result.adb_path, expected)
                self.io.paths.remove(expected)
        missing = self.service.check(self.profile)
        self.assertFalse(missing.ok)
        self.assertEqual(missing.error.code, "missing_adb")
        self.assertEqual(missing.error.fields, ["adb_path"])

    def test_only_invalid_supplied_installation_reference_needs_repair(self):
        for field in ("installation_path", "manager_path"):
            with self.subTest(field=field):
                profile = self.profile.model_copy(update={field: "/not-installed"})
                result = self.service.check(profile)
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, "missing_installation")
                self.assertEqual(result.error.fields, [field])
        self.profile.installation_path = "/installed"
        self.assertTrue(self.service.check(self.profile).ok)

    def test_android_must_finish_booting_before_preflight_accepts_it(self):
        for value in ("0", "", "unknown"):
            with self.subTest(value=value):
                self.io.boot = value
                result = self.service.check(self.profile)
                self.assertFalse(result.ok)
                self.assertEqual(result.status, "booting")
                self.assertEqual(result.error.code, "boot_incomplete")
                self.assertEqual(result.error.fields, [])
                self.assertEqual(result.observations, {})

    def test_override_is_effective_size_and_physical_observation_is_retained(self):
        self.io.size = "Physical size: 2560x1440\nOverride size: 1920x1080"
        result = self.service.check(self.profile)
        self.assertTrue(result.ok)
        self.assertEqual(result.observations["physical"], [2560, 1440])
        self.assertEqual(result.observations["override"], [1920, 1080])
        self.assertEqual(result.observations["effective"], [1920, 1080])

    def test_unreadable_or_ambiguous_logical_sizes_stop_before_capture(self):
        for value in (
            "Physical size: not-a-size",
            "Physical size: 1920x1080\nOverride size: unavailable",
            "Physical size: 1920x1080\nPhysical size: 1920x1080",
            "Override size: 1920x1080",
            "unavailable",
        ):
            with self.subTest(value=value):
                self.io.size = value
                result = self.service.check(self.profile)
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, "invalid_size")
                self.assertEqual(result.error.fields, [])
                self.assertNotIn("frame", result.observations)

    def test_a_valid_landscape_frame_is_accepted_at_any_reported_size(self):
        # A tablet presentation or a not-yet-rotated game reports portrait while
        # it already renders the frame the templates need.
        for value in (
            "Physical size: 1280x720",
            "Physical size: 2560x1440",
            "Physical size: 1080x1920",
            "Physical size: 1920x1080\nOverride size: 1280x720",
        ):
            with self.subTest(value=value):
                self.io.size = value
                result = self.service.check(self.profile)
                self.assertTrue(result.ok, result.error)
                self.assertEqual(result.observations["frame"], [1920, 1080])

    def test_actual_frame_must_be_decoded_rgb_and_horizontal_1920_by_1080(self):
        cases = (
            (None, "frame_failed"),
            (b"malformed screenshot", "frame_failed"),
            (np.zeros((1080, 1920), dtype=np.uint8), "frame_failed"),
            (np.zeros((1080, 1920, 3), dtype=np.float32), "frame_failed"),
            (np.zeros((0, 0, 3), dtype=np.uint8), "frame_failed"),
            (np.zeros((720, 1280, 3), dtype=np.uint8), "frame_size_mismatch"),
            (np.zeros((1920, 1080, 3), dtype=np.uint8), "frame_size_mismatch"),
        )
        for frame, code in cases:
            with self.subTest(code=code, shape=getattr(frame, "shape", None)):
                self.io.frame = frame
                result = self.service.check(self.profile)
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, code)
                self.assertEqual(result.error.fields, ["screenshot_backend"])
                self.assertEqual(
                    result.error.action,
                    "fix_size" if code == "frame_size_mismatch" else "retry",
                )

    def test_game_packages_require_one_installation_or_explicit_confirmation(self):
        self.io.installed_packages = []
        missing = self.service.check(self.profile)
        self.assertFalse(missing.ok)
        self.assertEqual(missing.error.code, "package_missing")
        self.assertEqual(missing.error.fields, [])
        self.assertIn("安装", missing.error.message)
        self.io.installed_packages = [
            "com.hypergryph.arknights",
            "com.hypergryph.arknights.bilibili",
        ]
        ambiguous = self.service.check(self.profile)
        self.assertFalse(ambiguous.ok)
        self.assertEqual(ambiguous.error.code, "package_ambiguous")
        self.assertEqual(ambiguous.error.fields, ["game_package"])
        self.assertEqual(ambiguous.packages, self.io.installed_packages)
        for selected in self.io.installed_packages:
            with self.subTest(selected=selected):
                result = self.service.check(self.profile, confirmed_package=selected)
                self.assertTrue(result.ok)
                self.assertEqual(result.game_package, selected)
        invalid = self.service.check(self.profile, confirmed_package="uninstalled")
        self.assertFalse(invalid.ok)
        self.assertEqual(invalid.error.code, "package_ambiguous")

    def test_failed_observations_return_stable_minimal_repairs(self):
        cases = (
            ("installation_exists", "missing_installation", ["installation_path"]),
            ("devices", "device_probe_failed", []),
            ("boot_completed", "boot_failed", []),
            ("display_size", "invalid_size", []),
            ("capture_frame", "frame_failed", ["screenshot_backend"]),
            ("packages", "package_probe_failed", []),
        )
        self.profile.installation_path = "/installed"
        for method, code, fields in cases:
            with (
                self.subTest(method=method),
                patch.object(
                    self.io, method, side_effect=TimeoutError("internal limit")
                ),
            ):
                result = self.service.check(self.profile)
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, code)
                self.assertEqual(result.error.fields, fields)
                self.assertEqual(result.error.action, "retry")
                if method == "capture_frame":
                    self.assertIn("internal limit", result.error.message)
                else:
                    self.assertNotIn("internal limit", result.error.message)

    def test_adb_discovery_does_not_visit_lower_priority_sources_after_success(self):
        with patch.object(self.io, "product_adb_paths", side_effect=PermissionError):
            self.assertTrue(self.service.check(self.profile).ok)

    def test_unavailable_adb_source_or_executable_does_not_mask_working_path(self):
        self.profile.adb_path = ""
        with patch.object(self.io, "product_adb_paths", side_effect=PermissionError):
            result = self.service.check(self.profile)
            self.assertTrue(result.ok)
            self.assertEqual(result.adb_path, "sdk-adb")

    def test_cancelled_probe_propagates_cancellation(self):
        with patch.object(self.io, "capture_frame", side_effect=MowerExit):
            with self.assertRaises(MowerExit):
                self.service.check(self.profile)

    def test_capture_uses_resolved_game_package_without_mutating_profile(self):
        def capture(adb_path, serial, profile):
            if profile.game_package != "com.hypergryph.arknights.bilibili":
                raise ValueError("wrong game display")
            return self.io.frame

        with patch.object(self.io, "capture_frame", side_effect=capture):
            result = self.service.check(self.profile)
            self.assertTrue(result.ok, result.error)
        self.assertEqual(self.profile.game_package, "com.hypergryph.arknights")

    def test_dual_packages_can_reuse_confirmed_persisted_selection(self):
        self.io.installed_packages = [
            "com.hypergryph.arknights",
            "com.hypergryph.arknights.bilibili",
        ]
        self.profile = self.profile.model_copy(
            update={
                "game_package": "com.hypergryph.arknights.bilibili",
                "game_package_confirmed": True,
            }
        )
        result = self.service.check(self.profile)
        self.assertTrue(result.ok)
        self.assertEqual(result.game_package, "com.hypergryph.arknights.bilibili")

    def test_one_normalized_adb_and_target_are_used_for_every_observation(self):
        expected_path = "/verified/platform-tools/adb"
        self.io.paths = {expected_path}
        observations = {
            "devices": self.io.targets,
            "boot_completed": self.io.boot,
            "display_size": self.io.size,
            "packages": self.io.installed_packages,
            "capture_frame": self.io.frame,
        }

        def observe(value):
            def read(path, serial, *args):
                if path != expected_path or serial != "USB-123":
                    raise ValueError("observation switched executable or target")
                return value

            return read

        for method, value in observations.items():
            patcher = patch.object(self.io, method, side_effect=observe(value))
            patcher.start()
            self.addCleanup(patcher.stop)
        with patch.object(self.io, "normalize_adb_path", return_value=expected_path):
            result = self.service.check(self.profile)
            self.assertTrue(result.ok, result.error)
            self.assertEqual(result.adb_path, expected_path)

    def test_physical_device_keeps_read_only_and_reports_the_frame_verdict(self):
        self.profile.preset_id = "manual.physical"
        self.io.size = "Physical size: 1080x1920"
        # The frame decides: a portrait reported size with the required
        # landscape frame is usable, and the wrong frame names the repair.
        result = self.service.check(self.profile)
        self.assertTrue(result.ok, result.error)
        self.io.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = self.service.check(self.profile)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "frame_size_mismatch")

    def test_prepared_portrait_physical_display_requires_horizontal_actual_frame(self):
        self.profile.preset_id = "manual.physical"
        self.io.size = "Physical size: 1440x2560\nOverride size: 1080x1920"
        result = self.service.check(self.profile, prepared_size=[1080, 1920])
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.observations["effective"], [1080, 1920])
        self.assertEqual(result.observations["frame"], [1920, 1080])
        self.io.frame = np.zeros((1920, 1080, 3), dtype=np.uint8)
        result = self.service.check(self.profile, prepared_size=[1080, 1920])
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "frame_size_mismatch")

    def test_the_reported_size_never_relaxes_the_frame_requirement(self):
        for preset, size, prepared in (
            ("manual.other", "1080x1920", [1080, 1920]),
            ("manual.physical", "1080x1920", None),
            ("manual.physical", "1280x720", [1280, 720]),
            ("manual.physical", "720x1280", [1080, 1920]),
        ):
            with self.subTest(preset=preset, size=size, prepared=prepared):
                self.profile.preset_id = preset
                self.io.size = f"Physical size: 1440x2560\nOverride size: {size}"
                self.io.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                result = self.service.check(self.profile, prepared_size=prepared)
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, "frame_size_mismatch")

    def test_invalid_physical_dimensions_cannot_be_hidden_by_an_override(self):
        self.io.size = "Physical size: 0x1080\nOverride size: 1920x1080"
        result = self.service.check(self.profile)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "invalid_size")


if __name__ == "__main__":
    unittest.main()
