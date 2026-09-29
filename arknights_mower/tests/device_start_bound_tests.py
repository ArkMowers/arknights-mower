"""Start-and-verify for an instance the bound preset's own manager can launch."""

import unittest
from unittest.mock import patch

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Adapter, Clock, Simulator
from arknights_mower.utils import config
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy

SERIAL = "127.0.0.1:16384"
INSTALLATION = "C:/MuMuPlayer"
MANAGER = "C:/MuMuPlayer/nx_main/MuMuManager.exe"
BOUND = {
    "preset_id": "windows.mumu12",
    "installation_path": INSTALLATION,
    "manager_path": MANAGER,
    "instance_id": "0",
    "instance_name": "粥",
    "last_serial": SERIAL,
}


class StartBoundTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        self.io, self.clock = PreflightIO(), Clock()
        self.adb, self.simulator = ADB(), Simulator()
        self.io.host = "windows"
        self.io.installed.update({INSTALLATION, MANAGER})
        self.io.paths.add("verified-adb")
        self.simulator.state = "stopped"
        self.simulator.on_start = self.mark_started
        self.control = DeviceControl(
            lambda: config.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            session=DeviceSession(
                self.adb,
                self.simulator,
                clock=self.clock,
                policy=RecoveryPolicy(timeout=6, poll_interval=1),
            ),
        )
        self.main.device_control = self.control
        self.addCleanup(self.control.close)

    def mark_started(self):
        self.simulator.state = "running"
        self.simulator.serial = SERIAL
        self.adb.rows = [(SERIAL, "device")]
        self.adb.boot = "1"
        self.io.targets = [(SERIAL, "device")]

    def start(self, device=None, **payload):
        response = self.client.post(
            "/device/start",
            headers=self.headers,
            json={"device": BOUND if device is None else device, **payload},
        )
        self.assertEqual(response.status_code, 200)
        return response.json

    def test_stopped_instance_is_launched_then_verified_without_persisting(self):
        before = self.path.read_bytes()
        ready = self.start()
        self.assertTrue(ready["ok"], ready["error"])
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["serial"], SERIAL)
        self.assertEqual(self.simulator.actions, ["start"])
        self.assertEqual(config.conf.device.preset_id, "manual.other")
        self.assertEqual(self.path.read_bytes(), before)

    def test_running_instance_is_verified_without_a_second_launch(self):
        self.mark_started()
        ready = self.start()
        self.assertTrue(ready["ok"], ready["error"])
        self.assertEqual(self.simulator.actions, [])

    def test_repeated_start_request_preserves_configured_startup_interval(self):
        config.conf.simulator.wait_time = 47
        self.control._session.policy = RecoveryPolicy(timeout=60)
        self.assertTrue(self.start()["ok"])
        self.adb.rows = [(SERIAL, "offline")]
        stopped_at = []
        stop = self.simulator.stop

        def record_stop(profile, timeout):
            stopped_at.append(self.clock.now)
            return stop(profile, timeout)

        with patch.object(self.simulator, "stop", side_effect=record_stop):
            ready = self.start()
        self.assertTrue(ready["ok"], ready["error"])
        self.assertEqual(stopped_at, [47])
        self.assertEqual(self.simulator.actions, ["start", "stop", "start"])

    def test_macos_mumu_pro_selected_instance_uses_shared_launch_route(self):
        self.io.host = "macos"
        before = self.path.read_bytes()
        ready = self.start(
            device={
                "preset_id": "macos.mumu_pro",
                "instance_id": "1",
                "topology_fingerprint": "a" * 64,
                "adb_path": "verified-adb",
            }
        )
        self.assertTrue(ready["ok"], ready["error"])
        self.assertEqual(self.simulator.actions, ["start"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_linux_waydroid_selected_session_uses_shared_launch_route(self):
        self.io.host = "linux"
        self.io.installed.update({"/usr/bin/waydroid", "/var/lib/waydroid"})
        ready = self.start(
            device={
                "preset_id": "linux.waydroid",
                "instance_id": "waydroid:501",
                "manager_path": "/usr/bin/waydroid",
                "installation_path": "/var/lib/waydroid",
                "config_path": "/var/lib/waydroid/waydroid.cfg",
                "adb_path": "verified-adb",
            }
        )
        self.assertTrue(ready["ok"], ready["error"])
        self.assertEqual(self.simulator.actions, ["start"])

    def test_presets_without_a_manager_are_rejected_without_starting(self):
        rejected = self.start(
            device={
                "preset_id": "windows.bluestacks5",
                "installation_path": INSTALLATION,
                "manager_path": MANAGER,
                "config_path": "C:/BlueStacks_nxt/bluestacks.conf",
                "instance_id": "Pie64",
                "last_serial": "127.0.0.1:5555",
            }
        )
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["code"], "start_unsupported")
        self.assertEqual(self.simulator.actions, [])

    def test_unknown_payload_keys_are_rejected_before_any_launch(self):
        response = self.client.post(
            "/device/start",
            headers=self.headers,
            json={"device": BOUND, "confirmed_instance": "0"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.simulator.actions, [])

    def test_active_session_rejects_the_launch(self):
        self.mark_started()
        started = self.control.start()
        self.assertTrue(started.ok, started.error)
        rejected = self.start()
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["code"], "device_session_active")
        self.assertEqual(self.simulator.actions, [])

    def test_a_closing_session_rejects_the_launch(self):
        self.control.begin_shutdown()
        rejected = self.start()
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["code"], "session_closing")
        self.assertEqual(self.simulator.actions, [])

    def test_a_missing_adapter_is_reported_without_touching_the_device(self):
        control = DeviceControl(lambda: config.conf, Adapter())
        self.main.device_control = control
        with patch("arknights_mower.utils.device.application.__system__", "windows"):
            rejected = self.start()
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["code"], "start_unavailable")
        self.assertEqual(self.simulator.actions, [])

    def test_an_unsupported_host_is_reported_before_a_missing_adapter(self):
        control = DeviceControl(lambda: config.conf, Adapter())
        self.main.device_control = control
        for host in ("linux", "darwin"):
            with (
                self.subTest(host=host),
                patch("arknights_mower.utils.device.application.__system__", host),
            ):
                rejected = self.start()
                self.assertFalse(rejected["ok"])
                self.assertEqual(rejected["error"]["code"], "start_unsupported")
        self.assertEqual(self.simulator.actions, [])

    def test_the_boss_key_route_needs_a_token_and_triggers_only_the_given_hotkey(self):
        triggered = {"ok": True, "message": "已触发模拟器老板键：alt+q"}
        with patch(
            "arknights_mower.utils.device.window.trigger_simulator_boss_key",
            return_value=triggered,
        ) as trigger:
            response = self.client.post(
                "/device/boss_key", headers=self.headers, json={"hotkey": "alt+q"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, triggered)
        trigger.assert_called_once_with("alt+q", delay=0.0)
        denied = self.client.post("/device/boss_key", json={"hotkey": "alt+q"})
        self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
