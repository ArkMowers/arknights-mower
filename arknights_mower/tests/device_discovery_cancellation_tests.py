"""Settings cancellation crosses real parallel discovery and Air probe boundaries."""

import tempfile
import threading
import unittest
from contextvars import ContextVar
from pathlib import Path
from unittest.mock import Mock, patch

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.bluestacks_air import (
    AIR_ENDPOINT,
    AIR_PRESET,
    BlueStacksAirDiscovery,
)
from arknights_mower.utils.device.discovery import DiscoveryService, _concurrent
from arknights_mower.utils.device.preflight import PreflightService


class ParallelDiscoveryCancellationTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        self.stop = threading.Event()
        self.enterContext(patch.object(config, "stop_mower", self.stop))
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        application = root / "BlueStacks.app"
        (application / "Contents/MacOS").mkdir(parents=True)
        (application / "Contents/Info.plist").write_bytes(b"fixture application")
        config.conf = config.Conf(device={"preset_id": "manual.other"})
        self.io = PreflightIO()
        self.io.host = "macos"
        self.io.installed.add(str(application.resolve()))
        self.io.targets = [(AIR_ENDPOINT, "device")]
        self.avd = Mock(discover=Mock(return_value={"installations": [], "errors": []}))
        self.control = DeviceControl(
            lambda: config.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(),
                avd=self.avd,
                air=BlueStacksAirDiscovery(application_paths=[application]),
            ),
        )
        self.main.device_control = self.control
        self.worker_threads = []
        self.on_capture = lambda: None
        self.enterContext(patch.object(self.io, "capture_frame", self.capture_frame))

    def capture_frame(self, adb_path, serial, profile):
        self.worker_threads.append(threading.get_ident())
        self.assertEqual(serial, AIR_ENDPOINT)
        self.assertEqual(profile.preset_id, AIR_PRESET)
        self.on_capture()
        csleep(0)
        return self.io.frame

    def assert_parallel_air_probe(self):
        self.avd.discover.assert_called_once()
        self.assertEqual(len(self.worker_threads), 1)
        self.assertNotEqual(self.worker_threads[0], threading.get_ident())

    def test_stopped_task_does_not_cancel_parallel_air_capture_wait(self):
        self.stop.set()
        before = config.conf.model_dump()
        result = self.control.discover()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, AIR_ENDPOINT)
        self.assertTrue(self.stop.is_set())
        self.assertEqual(config.conf.model_dump(), before)
        self.assert_parallel_air_probe()
        with self.assertRaises(MowerExit):
            csleep(0)

    def test_shutdown_cancels_parallel_air_capture_wait(self):
        self.on_capture = self.control.begin_shutdown
        with self.assertRaises(MowerExit):
            self.control.discover()
        self.assertFalse(self.stop.is_set())
        self.assert_parallel_air_probe()

    def test_pending_close_cancels_parallel_air_capture_wait(self):
        self.on_capture = self.control._pending_close.set
        with self.assertRaises(MowerExit):
            self.control.discover()
        self.assertFalse(self.stop.is_set())
        self.assert_parallel_air_probe()

    def test_shutdown_during_parallel_discovery_returns_http_cancellation(self):
        before = config.conf.model_dump()
        saved = self.path.read_bytes()
        self.on_capture = self.control.begin_shutdown
        response = self.client.post("/device/discover", headers=self.headers, json={})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["ok"])
        self.assertEqual(response.json["status"], "cancelled")
        self.assertEqual(response.json["error"]["code"], "device_operation_cancelled")
        self.assertFalse(self.stop.is_set())
        self.assertEqual(config.conf.model_dump(), before)
        self.assertEqual(self.path.read_bytes(), saved)
        self.assert_parallel_air_probe()


class ProviderContextTests(unittest.TestCase):
    def test_parallel_providers_have_independent_copies_of_the_callers_context(self):
        selection = ContextVar("discovery_selection", default="unscoped")
        barrier = threading.Barrier(2)
        token = selection.set("settings")

        def discover_provider(name):
            inherited = selection.get()
            selection.set(name)
            barrier.wait(timeout=2)
            return inherited, selection.get()

        try:
            results = _concurrent(
                (
                    lambda: discover_provider("avd"),
                    lambda: discover_provider("air"),
                )
            )
            self.assertEqual(results, [("settings", "avd"), ("settings", "air")])
            self.assertEqual(selection.get(), "settings")
        finally:
            selection.reset(token)


if __name__ == "__main__":
    unittest.main()
