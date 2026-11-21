"""Local redroid launch consent and same-container sessions through HTTP."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_redroid_tests import DockerFixture
from arknights_mower.tests.device_session_tests import ADB, Adapter, Clock, Simulator
from arknights_mower.utils import config
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
from arknights_mower.utils.device.session_io import ProductionSimulator

CONTAINER_ID = "a" * 64
TARGET_SERIAL = "127.0.0.1:32788"


class RedroidIO(Simulator):
    def __init__(self):
        super().__init__()
        self.state = "stopped"
        self.launches = []

    def start_confirmed(self, profile, timeout):
        self.launches.append(profile.instance_id)
        self.state = "running"
        self.serial = TARGET_SERIAL
        self.on_start()
        return True


class RedroidRouteTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        self.io, self.redroid = PreflightIO(), RedroidIO()
        self.clock, self.adb = Clock(), ADB()
        self.io.installed.update({"/usr/bin", "/usr/bin/docker"})
        self.io.paths.add("verified-adb")
        self.adb.rows = [("127.0.0.1:5555", "device"), (TARGET_SERIAL, "device")]
        self.adb.boot = "1"
        self.io.targets = self.adb.rows
        config.conf = config.Conf(
            device={
                "preset_id": "linux.redroid",
                "instance_id": CONTAINER_ID,
                "instance_name": "mower-redroid",
                "installation_path": "/usr/bin",
                "manager_path": "/usr/bin/docker",
                "config_path": "unix:///var/run/docker.sock",
                "last_serial": "127.0.0.1:5555",
            }
        )
        config.save_conf()
        self.control = DeviceControl(
            lambda: config.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(), self.redroid, redroid=self.redroid
            ),
            redroid=self.redroid,
            session=DeviceSession(
                self.adb,
                self.redroid,
                clock=self.clock,
                policy=RecoveryPolicy(timeout=5, poll_interval=1),
            ),
        )
        self.main.device_control = self.control
        self.addCleanup(self.control.close)

    def launch(self, **kwargs):
        return self.client.post(
            "/device/redroid/start",
            headers=self.headers,
            json={"confirmed_instance": CONTAINER_ID, **kwargs},
        )

    def test_stopped_container_requires_consent_without_any_automatic_launch(self):
        before = self.path.read_bytes()
        rejected = self.control.start()
        self.assertFalse(rejected.ok)
        self.assertEqual(rejected.error.code, "start_confirmation_required")
        self.assertEqual(self.redroid.actions, [])
        self.assertEqual(self.redroid.launches, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_read_only_preflight_never_starts_and_refreshes_only_current_container(
        self,
    ):
        before = self.path.read_bytes()
        stopped = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertEqual(stopped.status_code, 200)
        self.assertFalse(stopped.json["ok"])
        self.assertEqual(stopped.json["error"]["code"], "start_confirmation_required")
        self.assertEqual(stopped.json["serial"], "")
        self.redroid.state, self.redroid.serial = "running", TARGET_SERIAL
        running = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertTrue(running.json["ok"], running.json["error"])
        self.assertEqual(running.json["serial"], TARGET_SERIAL)
        self.assertEqual(self.redroid.launches, [])
        self.assertEqual(self.redroid.actions, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_authentication_and_malformed_or_mismatched_consent_never_start(self):
        before = self.path.read_bytes()
        missing_token = self.client.post(
            "/device/redroid/start", json={"confirmed_instance": CONTAINER_ID}
        )
        self.assertEqual(missing_token.status_code, 403)
        for payload in (
            {},
            [],
            None,
            {"confirmed_instance": True},
            {"confirmed_instance": " "},
            {"confirmed_instance": CONTAINER_ID, "remember": True},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/device/redroid/start", headers=self.headers, json=payload
                )
                self.assertEqual(response.status_code, 400)
        wrong = self.launch(confirmed_instance="b" * 64)
        self.assertEqual(wrong.status_code, 200)
        self.assertFalse(wrong.json["ok"])
        self.assertEqual(wrong.json["error"]["code"], "start_confirmation_required")
        self.assertEqual(self.redroid.launches, [])
        self.assertEqual(self.redroid.bindings, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_active_worker_or_session_rejects_launch_before_container_io(self):
        worker = MagicMock()
        worker.is_alive.return_value = True
        with patch.object(self.server, "mower_thread", worker):
            self.assertEqual(self.launch().status_code, 409)
        with self.control.run():
            rejected = self.launch()
            self.assertEqual(rejected.json["error"]["code"], "device_session_active")
        self.assertEqual(self.redroid.launches, [])

    def test_confirmation_expires_and_readiness_failure_never_restarts_or_switches(
        self,
    ):
        self.adb.rows = [("127.0.0.1:5555", "device")]
        before = self.path.read_bytes()
        failed = self.launch()
        self.assertFalse(failed.json["ok"])
        self.assertEqual(self.clock.now, 5)
        self.assertEqual(self.redroid.launches, [CONTAINER_ID])
        self.assertEqual(self.redroid.actions, [])
        self.assertEqual(self.adb.actions, [TARGET_SERIAL])
        self.redroid.state, self.redroid.serial = "stopped", None
        retry = self.control.start()
        self.assertFalse(retry.ok)
        self.assertEqual(retry.error.code, "start_confirmation_required")
        self.assertEqual(self.redroid.launches, [CONTAINER_ID])
        self.assertEqual(self.path.read_bytes(), before)

    def test_confirmed_launch_still_rejects_an_unreadable_size(self):
        self.io.size = "Physical size: not-a-size"
        before = self.path.read_bytes()
        failed = self.launch()
        self.assertFalse(failed.json["ok"])
        self.assertEqual(failed.json["error"]["code"], "invalid_size")
        self.assertEqual(self.redroid.launches, [CONTAINER_ID])
        self.assertEqual(self.path.read_bytes(), before)

    def test_nonstandard_container_start_preserves_manual_repair_action(self):
        with patch.object(
            self.redroid,
            "start_confirmed",
            side_effect=InstanceBindingError(
                "redroid_manual_required", "请使用高级手动配置", []
            ),
        ):
            rejected = self.launch()
        self.assertFalse(rejected.json["ok"])
        self.assertEqual(rejected.json["error"]["action"], "manual")

    def test_docker_discovery_binding_and_verified_changed_port_survive_http_save(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        docker = DockerFixture(root)
        self.io.installed.update({str(root), str(docker.manager)})
        self.io.targets.extend(
            [("127.0.0.1:15555", "device"), ("127.0.0.1:25555", "device")]
        )
        simulator = ProductionSimulator(redroid=docker.controller)
        control = DeviceControl(
            lambda: config.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(), simulator, redroid=docker.controller
            ),
            redroid=docker.controller,
        )
        self.main.device_control = control
        self.addCleanup(control.close)
        config.conf = config.Conf(device={})
        config.save_conf()
        before = self.path.read_bytes()
        discovered = self.client.post(
            "/device/discover",
            headers=self.headers,
            json={"device": {"preset_id": "linux.redroid"}},
        )
        self.assertTrue(discovered.json["ok"], discovered.json["error"])
        candidate = discovered.json["candidates"][0]
        self.assertEqual(discovered.json["selected_key"], candidate["key"])
        self.assertEqual(self.path.read_bytes(), before)
        saved = self.client.patch(
            "/conf", headers=self.headers, json={"device": candidate["binding"]}
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json["device"]["instance_id"], CONTAINER_ID)
        self.assertEqual(saved.json["device"]["last_serial"], "")
        before = self.path.read_bytes()
        checked = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertTrue(checked.json["ok"], checked.json["error"])
        self.assertEqual(checked.json["serial"], "127.0.0.1:15555")
        self.assertEqual(self.path.read_bytes(), before)
        docker.rows[0]["NetworkSettings"]["Ports"]["5555/tcp"] = docker.fixtures[
            "changed_port"
        ]
        checked = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertTrue(checked.json["ok"], checked.json["error"])
        self.assertEqual(checked.json["serial"], "127.0.0.1:25555")
        saved = self.client.patch(
            "/conf",
            headers=self.headers,
            json={
                "device": {
                    "last_serial": checked.json["serial"],
                    "adb_path": checked.json["adb_path"],
                    "game_package": checked.json["game_package"],
                    "game_package_confirmed": True,
                }
            },
        )
        self.assertEqual(saved.status_code, 200)
        config.load_conf()
        reloaded = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(reloaded["device"]["instance_id"], CONTAINER_ID)
        self.assertEqual(reloaded["device"]["last_serial"], "127.0.0.1:25555")
        self.assertEqual(
            reloaded["device"]["config_path"], "unix:///var/run/docker.sock"
        )
        self.assertNotIn("confirmed_instance", reloaded["device"])
        self.assertFalse(any("start" in argv for argv, _ in docker.calls))

    def test_confirmed_launch_validates_current_port_and_does_not_save_consent(self):
        before = self.path.read_bytes()
        ready = self.launch()
        self.assertEqual(ready.status_code, 200)
        self.assertTrue(ready.json["ok"], ready.json["error"])
        self.assertEqual(ready.json["serial"], TARGET_SERIAL)
        self.assertEqual(ready.json["observations"]["effective"], [1920, 1080])
        self.assertEqual(ready.json["observations"]["frame"], [1920, 1080])
        self.assertEqual(self.redroid.launches, [CONTAINER_ID])
        self.assertEqual(self.redroid.actions, [])
        self.assertTrue(
            all(
                binding == ("linux.redroid", CONTAINER_ID)
                for binding in self.redroid.bindings
            )
        )
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
