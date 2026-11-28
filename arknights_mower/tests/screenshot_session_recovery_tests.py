"""Hermetic capture incidents retain independent recovery and resource boundaries."""

import unittest
from unittest.mock import Mock

import numpy as np

from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.droidcast import DroidCastError
from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.device.screenshot_backend import (
    ScreenshotFailure,
    ScreenshotSession,
)


class ScreenshotSessionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.profile = DeviceProfile(
            last_serial="USB-A", screenshot_backend="droidcast"
        )
        self.before = self.profile.model_dump()
        self.session = ScreenshotSession(self.profile, "linux")
        self.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.rebuild = Mock()
        self.recover = Mock(return_value=False)
        self.standard = Mock(return_value=self.frame)

    def test_helper_stage_codes_allow_verified_adb_degradation(self):
        for stage in (
            "version_required",
            "version_failed",
            "install_failed",
            "signature_conflict",
            "forward_failed",
            "start_failed",
            "start_timeout",
            "frame_failed",
            "http_failed",
            "http_timeout",
        ):
            with self.subTest(stage=stage):
                session = ScreenshotSession(self.profile, "linux")
                cause = DroidCastError(stage, "helper original diagnosis")
                capture = Mock(side_effect=cause)
                rebuild = Mock(side_effect=cause)
                recover = Mock(return_value=False)
                standard = Mock(return_value=self.frame)

                result = session.capture(capture, rebuild, recover, standard)

                self.assertIs(result, self.frame)
                self.assertTrue(session.degraded)
                self.assertEqual(session.backend, "adb_gzip")
                self.assertFalse(session.rebuilt)
                self.assertEqual(session.failure.code, cause.code)
                self.assertIs(session.failure.cause, cause)
                self.assertIn("helper original diagnosis", str(session.failure))
                self.assertEqual(capture.call_count, 1)
                rebuild.assert_called_once_with()
                recover.assert_called_once_with()
                standard.assert_called_once_with()
                self.assertEqual(self.profile.model_dump(), self.before)
                self.assertEqual(session.profile.model_dump(), self.before)

    def test_successful_incident_rebuild_renews_next_incident_only(self):
        capture = Mock(
            side_effect=[
                RuntimeError("first"),
                self.frame,
                RuntimeError("second"),
                self.frame,
            ]
        )
        for _ in range(2):
            result = self.session.capture(
                capture, self.rebuild, self.recover, self.standard
            )
            self.assertIs(result, self.frame)
            self.assertFalse(self.session.rebuilt)
            self.assertIsNone(self.session.failure)
        self.assertEqual(self.rebuild.call_count, 2)
        self.assertEqual(self.recover.call_count, 2)
        self.standard.assert_not_called()

    def test_failed_incident_does_not_latch_future_capture(self):
        cause = DroidCastError("http_timeout", "original timeout")
        capture = Mock(side_effect=[cause, cause, cause, self.frame])
        self.standard.side_effect = RuntimeError("ADB temporarily offline")
        with self.assertRaises(ScreenshotFailure) as raised:
            self.session.capture(capture, self.rebuild, self.recover, self.standard)
        self.assertEqual(raised.exception.code, cause.code)
        self.assertIn("original timeout", str(raised.exception))
        self.assertIn("ADB temporarily offline", str(raised.exception))

        result = self.session.capture(
            capture, self.rebuild, self.recover, self.standard
        )

        self.assertIs(result, self.frame)
        self.assertEqual(capture.call_count, 4)
        self.assertEqual(self.rebuild.call_count, 2)
        self.assertIsNone(self.session.failure)
        self.assertFalse(self.session.degraded)

    def test_degraded_capture_failure_does_not_prevent_next_verified_frame(self):
        cause = DroidCastError("http_failed", "helper unavailable")
        capture = Mock(side_effect=cause)
        self.session.capture(capture, self.rebuild, self.recover, self.standard)
        self.standard.side_effect = [RuntimeError("temporary ADB failure"), self.frame]

        with self.assertRaises(ScreenshotFailure) as raised:
            self.session.capture(capture, self.rebuild, self.recover, self.standard)
        self.assertEqual(raised.exception.code, cause.code)
        self.assertIn("helper unavailable", str(raised.exception))
        self.assertIn("temporary ADB failure", str(raised.exception))
        self.assertIs(
            self.session.capture(capture, self.rebuild, self.recover, self.standard),
            self.frame,
        )
        self.assertEqual(capture.call_count, 2)
        self.assertEqual(self.rebuild.call_count, 1)
        self.assertEqual(self.standard.call_count, 3)
        self.assertTrue(self.session.degraded)
        self.assertIs(self.session.failure.cause, cause)
        self.assertIsNone(self.session.failure.fallback)

    def test_resource_failure_never_rebuilds_or_degrades(self):
        cleanup = RuntimeError("owned resource cleanup failed")
        cleanup.cleanup_failed = True
        for cause in (
            DroidCastError("ownership_conflict", "foreign owner"),
            DroidCastError("cleanup_failed", "owned mapping remains"),
            DroidCastError("closed", "session closing"),
            cleanup,
        ):
            with self.subTest(cause=str(cause)):
                capture = Mock(side_effect=cause)
                with self.assertRaises(ScreenshotFailure):
                    ScreenshotSession(self.profile, "linux").capture(
                        capture, self.rebuild, self.recover, self.standard
                    )
                capture.assert_called_once_with()
        self.rebuild.assert_not_called()
        self.recover.assert_not_called()
        self.standard.assert_not_called()

    def test_rebuild_cleanup_failure_preserves_resource_guard(self):
        cause = DroidCastError("cleanup_failed", "cannot remove owned mapping")
        self.rebuild.side_effect = cause
        with self.assertRaises(ScreenshotFailure) as raised:
            self.session.capture(
                Mock(side_effect=RuntimeError("capture failed")),
                self.rebuild,
                self.recover,
                self.standard,
            )
        self.assertEqual(raised.exception.code, cause.code)
        self.assertTrue(raised.exception.cleanup_failed)
        self.standard.assert_not_called()

    def test_recovery_helper_start_failure_can_use_verified_adb_frame(self):
        cause = DroidCastError("start_failed", "rebind helper exited")
        self.recover.side_effect = cause
        self.assertIs(
            self.session.capture(
                Mock(side_effect=RuntimeError("capture failed")),
                self.rebuild,
                self.recover,
                self.standard,
            ),
            self.frame,
        )
        self.rebuild.assert_not_called()
        self.assertEqual(self.session.failure.code, cause.code)

    def test_recovery_rebind_already_rebuilds_the_selected_helper(self):
        self.recover.return_value = True
        capture = Mock(side_effect=[RuntimeError("capture failed"), self.frame])
        self.assertIs(
            self.session.capture(capture, self.rebuild, self.recover, self.standard),
            self.frame,
        )
        self.recover.assert_called_once_with()
        self.rebuild.assert_not_called()
        self.standard.assert_not_called()
        self.assertFalse(self.session.rebuilt)

    def test_recovery_resource_failure_cannot_be_hidden_by_adb_success(self):
        cause = DroidCastError("ownership_conflict", "foreign helper resources")
        self.recover.side_effect = cause
        with self.assertRaises(ScreenshotFailure) as raised:
            self.session.capture(
                Mock(side_effect=RuntimeError("capture failed")),
                self.rebuild,
                self.recover,
                self.standard,
            )
        self.assertEqual(raised.exception.code, cause.code)
        self.rebuild.assert_not_called()
        self.standard.assert_not_called()

    def test_degradation_requires_an_actual_valid_adb_frame(self):
        self.standard.return_value = None
        capture = Mock(side_effect=DroidCastError("http_failed", "HTTP failed"))
        with self.assertRaises(ScreenshotFailure) as raised:
            self.session.capture(capture, self.rebuild, self.recover, self.standard)
        self.assertIn("uint8 RGB", str(raised.exception))
        self.assertFalse(self.session.degraded)
        self.assertEqual(self.session.backend, "droidcast")
        self.assertEqual(self.profile.model_dump(), self.before)

    def test_binding_shared_adb_and_cancellation_errors_never_degrade(self):
        for error in (
            MowerExit("cancelled"),
            InstanceBindingError("binding_changed", "different target"),
            SharedADBError("incompatible shared server"),
            DeviceRecoveryError("recovery budget exhausted"),
        ):
            for stage in ("capture", "recover", "rebuild", "standard"):
                with self.subTest(error=type(error).__name__, stage=stage):
                    capture = Mock(side_effect=RuntimeError("capture failed"))
                    rebuild = Mock()
                    recover = Mock(return_value=False)
                    standard = Mock(return_value=self.frame)
                    {
                        "capture": capture,
                        "rebuild": rebuild,
                        "recover": recover,
                        "standard": standard,
                    }[stage].side_effect = error
                    with self.assertRaises(type(error)) as raised:
                        ScreenshotSession(self.profile, "linux").capture(
                            capture, rebuild, recover, standard
                        )
                    self.assertIs(raised.exception, error)
                    if stage != "standard":
                        standard.assert_not_called()

    def test_wrong_size_is_reported_without_recovery_but_not_permanently_latched(self):
        capture = Mock(
            side_effect=[np.zeros((720, 1280, 3), dtype=np.uint8), self.frame]
        )
        with self.assertRaises(ScreenshotFailure) as raised:
            self.session.capture(capture, self.rebuild, self.recover, self.standard)
        self.assertEqual(raised.exception.code, "frame_size_mismatch")
        self.assertEqual(raised.exception.to_dict()["action"], "fix_size")
        self.assertIs(
            self.session.capture(capture, self.rebuild, self.recover, self.standard),
            self.frame,
        )
        self.rebuild.assert_not_called()
        self.recover.assert_not_called()
        self.standard.assert_not_called()

    def test_wrong_size_fallback_keeps_size_verdict_and_helper_diagnosis(self):
        cause = DroidCastError("http_failed", "helper HTTP failed")
        self.standard.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)
        with self.assertRaises(ScreenshotFailure) as raised:
            self.session.capture(
                Mock(side_effect=cause), self.rebuild, self.recover, self.standard
            )
        self.assertEqual(raised.exception.code, "frame_size_mismatch")
        self.assertIn("helper HTTP failed", str(raised.exception))
        self.assertIn("1280×720", str(raised.exception))
        self.assertFalse(self.session.degraded)

    def test_non_droidcast_backends_never_switch_to_adb(self):
        for backend in ("adb_gzip", "custom", "ld_native", "mumu_ipc"):
            with self.subTest(backend=backend):
                profile = self.profile.model_copy(
                    update={"screenshot_backend": backend}
                )
                session = ScreenshotSession(profile, "windows")
                capture = Mock(side_effect=RuntimeError("selected capture failed"))
                rebuild = Mock()
                with self.assertRaises(ScreenshotFailure):
                    session.capture(capture, rebuild, self.recover, self.standard)
                self.assertEqual(session.backend, backend)
                self.assertFalse(session.degraded)
                rebuild.assert_called_once_with()
        self.standard.assert_not_called()


if __name__ == "__main__":
    unittest.main()
