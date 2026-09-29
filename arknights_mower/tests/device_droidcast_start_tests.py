"""DroidCast installation is confined to a validated runtime start."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from arknights_mower.tests.device_droidcast_tests import HTTP, MODULE, Android
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import Adapter
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.application import (
    DeviceControl,
    prepare_droidcast_capture,
)
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.preflight_io import ProductionPreflightIO


class CapturePreflightIO(PreflightIO):
    def __init__(self, capture):
        super().__init__()
        self.capture = capture

    def capture_frame(self, adb_path, serial, profile):
        if profile.screenshot_backend == "droidcast":
            return self.capture.capture_frame(adb_path, serial, profile)
        return super().capture_frame(adb_path, serial, profile)


class RecordingAdapter(Adapter):
    def __init__(self):
        self.opened = []

    def open_verified(self, configuration, result):
        self.opened.append(result.serial)
        return super().open_verified(configuration, result)


class DroidCastStartTests(unittest.TestCase):
    def setUp(self):
        self.android, self.http = Android(), HTTP()
        self.android.version = "1.3.0"
        for name, value in (
            ("run_adb", self.android.run),
            ("guard_adb", lambda *args, **kwargs: None),
            ("subprocess.Popen", self.android.spawn),
            ("requests.Session", lambda: self.http),
        ):
            self.enterContext(patch(f"{MODULE}.{name}", value))
        self.profile = DeviceProfile(
            last_serial="USB-A",
            adb_path="manual-adb",
            screenshot_backend="droidcast",
        )
        self.configuration = Conf(device=self.profile)
        self.io = CapturePreflightIO(ProductionPreflightIO(lambda: self.configuration))
        self.io.targets = [("USB-A", "device")]
        self.service = PreflightService(self.io)
        self.adapter = RecordingAdapter()

    def control(self, **options):
        self.configuration = Conf(device=self.profile)
        options.setdefault("prepare_capture", prepare_droidcast_capture)
        control = DeviceControl(
            lambda: self.configuration,
            self.adapter,
            preflight=self.service,
            **options,
        )
        self.addCleanup(control.close)
        return control

    def installs(self):
        return [args for args in self.android.commands if args[0] == "install"]

    def test_prepare_capture_receives_validated_target_and_selected_game_package(self):
        prepared = []

        def prepare(adb_path, serial, profile):
            prepared.append((adb_path, serial, profile.game_package))
            prepare_droidcast_capture(adb_path, serial, profile)

        result = self.service.check(self.profile, prepare_capture=prepare)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(
            prepared,
            [("manual-adb", "USB-A", "com.hypergryph.arknights.bilibili")],
        )
        self.assertEqual(result.observations["frame"], [1920, 1080])
        self.assertEqual(self.installs(), [])

    def test_runtime_start_upgrades_before_the_first_capture(self):
        self.android.version = "1.2.1"
        control = self.control()
        result = control.start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(self.android.version, "1.3.0")
        self.assertEqual(len(self.installs()), 1)
        self.assertEqual(self.adapter.opened, ["USB-A"])
        self.assertEqual(
            control.settings_status()["preflight"]["observations"]["frame"],
            [1920, 1080],
        )

    def test_runtime_start_installs_a_missing_package_before_capture(self):
        self.android.version = None
        result = self.control().start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(self.android.version, "1.3.0")
        self.assertEqual(len(self.installs()), 1)
        self.assertEqual(self.adapter.opened, ["USB-A"])
        self.assertEqual(len(self.http.calls), 1)

    def test_read_only_preflight_does_not_install_a_missing_helper(self):
        self.android.version = None
        result = self.control().preflight()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "droidcast_version_required")
        self.assertIn("测试截图不会自动安装应用", result.error.message)
        self.assertEqual(result.error.backend, "droidcast")
        self.assertEqual(self.installs(), [])
        self.assertIsNone(self.android.version)
        self.assertEqual(self.android.processes, [])
        self.assertEqual(self.http.calls, [])
        self.assertTrue(self.android.commands)

    def test_invalid_target_display_or_package_never_installs_helper(self):
        self.android.version = None
        cases = (
            ("targets", [], "target_absent"),
            ("boot", "0", "boot_incomplete"),
            # Only an unreadable or ambiguous size still stops before capture; a
            # parsed size is diagnostic and the decoded frame decides.
            ("size", "Physical size: not-a-size", "invalid_size"),
            ("installed_packages", [], "package_missing"),
        )
        for field, value, code in cases:
            with self.subTest(code=code), patch.object(self.io, field, value):
                result = self.control().start()
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, code)
                # A rejected target never installs or launches the helper. The
                # later frame gate may still have probed the installed version.
                self.assertEqual(self.installs(), [])
                self.assertEqual(self.android.processes, [])
                self.assertEqual(self.adapter.opened, [])

    def test_signature_conflict_preserves_repair_through_start_and_settings(self):
        self.android.version = "1.2.1"
        self.android.install_output = b"Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]"
        control = self.control()
        result = control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "droidcast_signature_conflict")
        self.assertIn("签名冲突", result.error.message)
        self.assertIn("手动卸载", result.error.message)
        settings = control.settings_status()
        detail = settings["error"]
        self.assertEqual(detail["code"], "droidcast_signature_conflict")
        self.assertEqual(detail["message"], result.error.message)
        self.assertEqual(detail["backend"], "droidcast")
        self.assertEqual(detail["action"], "retry")
        self.assertEqual(detail["fields"], ["screenshot_backend"])
        self.assertEqual(settings["preflight"]["error"], detail)
        self.assertEqual(
            {option["backend"] for option in detail["alternatives"]},
            {"adb_gzip", "custom"},
        )
        self.assertEqual(self.configuration.device.screenshot_backend, "droidcast")
        self.assertEqual(self.android.version, "1.2.1")
        self.assertEqual(len(self.installs()), 1)
        self.assertFalse(any(args[0] == "uninstall" for args in self.android.commands))
        self.assertEqual(self.adapter.opened, [])
        self.assertEqual(self.android.processes, [])
        self.assertEqual(self.http.calls, [])

    def test_prepare_runs_once_when_capture_rebuilds(self):
        prepared = []
        get = self.http.get
        attempts = []

        def response(*args, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise requests.ReadTimeout("first helper failed")
            return get(*args, **kwargs)

        def prepare(adb_path, serial, profile):
            prepared.append((adb_path, serial))
            prepare_droidcast_capture(adb_path, serial, profile)

        self.http.get = response
        result = self.service.check(self.profile, prepare_capture=prepare)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(prepared, [("manual-adb", "USB-A")])
        self.assertEqual(len(self.android.processes), 2)
        self.assertEqual(self.android.forwards, {})

    def test_other_selected_backend_does_not_prepare_droidcast(self):
        self.profile.screenshot_backend = "adb_gzip"
        self.android.version = None
        result = self.control().start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(self.android.commands, [])

    def test_air_runtime_prepares_only_the_verified_bound_target(self):
        self.android.version = "1.2.1"
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        app = root / "BlueStacks.app"
        (app / "Contents/MacOS").mkdir(parents=True)
        (app / "Contents/Info.plist").write_bytes(b"fixture application")
        self.io.host = "macos"
        self.io.installed.add(str(app.resolve()))
        self.profile.preset_id = "macos.bluestacks_air"
        self.profile.installation_path = str(app)
        result = self.control(discovery=DiscoveryService(None)).start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(self.android.version, "1.3.0")
        self.assertEqual(len(self.installs()), 1)
        self.assertEqual(self.adapter.opened, ["USB-A"])


if __name__ == "__main__":
    unittest.main()
