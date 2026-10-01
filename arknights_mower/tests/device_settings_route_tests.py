"""Device settings contracts through HTTP and the application session boundary."""

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

from arknights_mower.tests.device_application_tests import ManualAdapter, ManualDevice
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.touch_backend import TouchFailure


class DeviceSettingsRouteTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch.dict(sys.modules, {"arknights_mower.utils.skland": MagicMock()})
        )
        self.main = importlib.import_module("arknights_mower.__main__")
        self.server = importlib.import_module("server")
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "conf.yml"
        self.enterContext(patch.object(config, "conf_path", self.path))
        self.enterContext(patch.object(config, "conf", config.Conf(adb="USB-123")))
        self.control = DeviceControl(lambda: config.conf, ManualAdapter())
        self.enterContext(patch.object(self.main, "device_control", self.control))
        self.enterContext(patch.object(self.server, "mower_thread", None))
        self.enterContext(
            patch.object(self.server.app, "token", "device-token", create=True)
        )
        manager = MagicMock()
        manager.get_active_plan_key.return_value = ""
        self.enterContext(
            patch(
                "arknights_mower.utils.config.weekly_plan_loader.get_weekly_plan_manager",
                return_value=manager,
            )
        )
        self.enterContext(
            patch(
                "arknights_mower.utils.workshop_config.get_path",
                return_value=Path(directory) / "no-workshop.json",
            )
        )
        config.save_conf()
        self.client = self.server.app.test_client()
        self.headers = {"token": "device-token"}

    def test_active_session_locks_target_but_allows_unrelated_partial_save(self):
        self.control.start()
        before = self.path.read_bytes()
        for payload in (
            {"device": {"last_serial": "USB-other"}},
            {"adb": "USB-other"},
            {"device": {"touch_backend": "maatouch"}},
            {"custom_screenshot": {"command": "different-capture"}},
        ):
            with self.subTest(payload=payload):
                response = self.client.patch(
                    "/conf", headers=self.headers, json=payload
                )
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json["error"], "device_session_active")
                self.assertEqual(self.path.read_bytes(), before)
        response = self.client.patch(
            "/conf", headers=self.headers, json={"theme": "dark"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["theme"], "dark")
        self.assertEqual(response.json["device"]["last_serial"], "USB-123")

    def test_metadata_reports_host_and_activity_without_device_io(self):
        response = self.client.get("/device/status", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.json["host_platform"], ("windows", "macos", "linux"))
        self.assertFalse(response.json["active"])
        self.control.start()
        response = self.client.get("/device/status", headers=self.headers)
        self.assertTrue(response.json["active"])
        self.assertEqual(response.json["serial"], "USB-123")
        self.assertEqual(self.client.get("/device/status").status_code, 403)

    def test_screenshot_failure_exposes_native_reason_and_peers_without_saving(self):
        io = PreflightIO()
        self.main.device_control = DeviceControl(
            lambda: config.conf, ManualAdapter(), preflight=PreflightService(io)
        )
        before = self.path.read_bytes()
        with patch.object(
            io, "capture_frame", side_effect=RuntimeError("native code=7; 1280x720")
        ):
            response = self.client.post(
                "/device/preflight", headers=self.headers, json={}
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["ok"])
        error = response.json["error"]
        self.assertEqual(error["code"], "frame_failed")
        self.assertEqual(error["backend"], config.conf.device.screenshot_backend)
        self.assertIn("native code=7", error["message"])
        self.assertIn("1280x720", error["message"])
        self.assertEqual(
            {item["backend"] for item in error["alternatives"]}, {"adb_gzip", "custom"}
        )
        self.assertEqual(error["fields"], ["screenshot_backend"])
        self.assertEqual(self.path.read_bytes(), before)
        status = self.client.get("/device/status", headers=self.headers)
        self.assertEqual(status.json["preflight"]["error"], error)

    def test_touch_status_exposes_failure_peers_and_capabilities_without_saving(self):
        config.conf = config.Conf(
            device={"last_serial": "USB-123", "touch_backend": "maatouch"}
        )
        config.save_conf()
        before = self.path.read_bytes()
        for delivery_unknown, code in (
            (False, "touch_initialization_failed"),
            (True, "touch_result_unknown"),
        ):
            with self.subTest(code=code):
                failure = TouchFailure(
                    config.conf.device,
                    "linux",
                    RuntimeError("helper exited=9"),
                    delivery_unknown=delivery_unknown,
                )

                class FailingDevice(ManualDevice):
                    def tap(self, point):
                        raise failure

                class FailingAdapter(ManualAdapter):
                    def open(self, configuration, *, connection_retries):
                        if delivery_unknown:
                            return FailingDevice(configuration.adb)
                        raise failure

                control = DeviceControl(lambda: config.conf, FailingAdapter())
                self.addCleanup(control.close)
                self.main.device_control = control
                result = control.start()
                if delivery_unknown:
                    self.assertTrue(result.ok, result.error)
                    result = control.execute(lambda device: device.tap((120, 240)))
                self.assertFalse(result.ok)
                response = self.client.get("/device/status", headers=self.headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["status"], "failed")
                error = response.json["error"]
                self.assertEqual(error["code"], code)
                self.assertEqual(error["backend"], "maatouch")
                self.assertEqual(error["fields"], ["touch_backend"])
                self.assertEqual(error["action"], "configure")
                self.assertEqual(error["delivery_unknown"], delivery_unknown)
                self.assertIn("helper exited=9", error["message"])
                self.assertEqual(
                    error["alternatives"],
                    [{"backend": "scrcpy", "label": "scrcpy 1.21"}],
                )
                if delivery_unknown:
                    self.assertIn("不会自动重复输入", error["message"])
                    self.assertIn("相关任务已暂停", error["message"])
                self.assertEqual(response.json["touch_backend_profile"], "manual.other")
                capabilities = {
                    item["backend"]: item for item in response.json["touch_backends"]
                }
                self.assertEqual(set(capabilities), {"scrcpy", "maatouch", "mumu_ipc"})
                self.assertTrue(capabilities["scrcpy"]["available"])
                self.assertTrue(capabilities["maatouch"]["available"])
                self.assertFalse(capabilities["mumu_ipc"]["available"])
                self.assertIn("Windows", capabilities["mumu_ipc"]["reason"])
                self.assertIn("MuMu 12", capabilities["mumu_ipc"]["reason"])
                self.assertEqual(config.conf.device.touch_backend, "maatouch")
                self.assertEqual(self.path.read_bytes(), before)

    def test_temporary_preparation_consent_is_exact_and_only_for_one_start(self):
        config.conf = config.Conf(
            device={"preset_id": "manual.physical", "last_serial": "USB-123"}
        )
        config.save_conf()
        before = self.path.read_bytes()
        runs = []

        class Worker:
            def __init__(self, target, args, daemon, kwargs=None):
                self.target, self.args, self.kwargs = target, args, kwargs or {}

            def start(self):
                self.target(*self.args, **self.kwargs)

            def is_alive(self):
                return False

        def main(state, *, preparation_serial=None):
            runs.append(preparation_serial)

        with (
            patch.object(self.server, "active_job", return_value=False),
            patch.object(self.server, "_job_running", return_value=False),
            patch.object(self.server.resource_update, "running", return_value=False),
            patch.object(self.server, "get_path", return_value=self.path.parent),
            patch.object(self.server, "load_state", return_value={}),
            patch.object(self.server, "log_stream"),
            patch.object(self.server, "Thread", Worker),
            patch.object(self.server, "set_mower_thread"),
            patch.object(self.main, "main", main),
        ):
            response = self.client.post(
                "/start/0", headers=self.headers, json={"preparation_serial": "USB-123"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_data(as_text=True), "true")
            self.assertEqual(runs, ["USB-123"])
            self.client.get("/start/0", headers=self.headers)
            self.assertEqual(runs, ["USB-123", None])
        self.assertEqual(self.path.read_bytes(), before)

    def test_temporary_preparation_rejects_implicit_or_different_targets(self):
        config.conf = config.Conf(
            device={"preset_id": "manual.physical", "last_serial": "USB-123"}
        )
        with patch.object(self.server, "Thread") as worker:
            for payload in (
                {},
                {"preparation_serial": ""},
                {"preparation_serial": "USB-other"},
                {"preparation_serial": True},
                {"preparation_serial": "USB-123", "remember": True},
            ):
                with self.subTest(payload=payload):
                    response = self.client.post(
                        "/start/0", headers=self.headers, json=payload
                    )
                    self.assertEqual(response.status_code, 400)
            config.conf = config.conf.updated(
                {"device": {"preset_id": "manual.other", "last_serial": "USB-123"}}
            )
            response = self.client.post(
                "/start/0", headers=self.headers, json={"preparation_serial": "USB-123"}
            )
            self.assertEqual(response.status_code, 400)
            worker.assert_not_called()
        self.assertEqual(
            self.client.post(
                "/start/0", json={"preparation_serial": "USB-123"}
            ).status_code,
            403,
        )

    def test_game_choice_is_remembered_only_for_its_target(self):
        response = self.client.patch(
            "/conf",
            headers=self.headers,
            json={"device": {"game_package": "com.hypergryph.arknights.bilibili"}},
        )
        self.assertTrue(response.json["device"]["game_package_confirmed"])
        response = self.client.patch(
            "/conf", headers=self.headers, json={"device": {"last_serial": "USB-456"}}
        )
        self.assertFalse(response.json["device"]["game_package_confirmed"])

    def test_legacy_full_save_does_not_confirm_a_default_game_package(self):
        payload = config.conf.model_dump()
        payload.pop("device")
        payload["theme"] = "dark"
        response = self.client.post("/conf", headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200)
        io = PreflightIO()
        io.installed_packages = [
            "com.hypergryph.arknights",
            "com.hypergryph.arknights.bilibili",
        ]
        result = PreflightService(io).check(config.conf.device)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "package_ambiguous")

    def test_preflight_uses_application_contract_and_does_not_save(self):
        io = PreflightIO()
        self.control = DeviceControl(
            lambda: config.conf, ManualAdapter(), preflight=PreflightService(io)
        )
        self.main.device_control = self.control
        before = self.path.read_bytes()
        response = self.client.post(
            "/device/preflight",
            headers=self.headers,
            json={"device": {"last_serial": "USB-123"}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"])
        self.assertEqual(response.json["host_platform"], "linux")
        self.assertEqual(
            response.json["game_package"], "com.hypergryph.arknights.bilibili"
        )
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(config.conf.device.game_package, "com.hypergryph.arknights")
        self.assertEqual(
            self.client.post("/device/preflight", json={}).status_code, 403
        )

    def test_discovery_is_authorized_read_only_and_selection_uses_conf(self):
        from arknights_mower.tests.device_discovery_tests import DiscoveryIO
        from arknights_mower.utils.device.discovery import DiscoveryService

        io = PreflightIO()
        io.host = "windows"
        sources = DiscoveryIO()
        sources.installations = [
            {
                "installation_path": "C:/MuMu12",
                "manager_path": "C:/MuMu12/shell/MuMuManager.exe",
                "instances": [
                    {
                        "instance_id": "3",
                        "instance_name": "日常号",
                        "state": "stopped",
                        "serial": "",
                    }
                ],
            }
        ]
        self.main.device_control = DeviceControl(
            lambda: config.conf,
            ManualAdapter(),
            preflight=PreflightService(io),
            discovery=DiscoveryService(sources),
        )
        before = self.path.read_bytes()
        self.client.get("/device/status", headers=self.headers)
        self.assertEqual(sources.calls, 0)
        self.assertEqual(self.client.post("/device/discover", json={}).status_code, 403)
        response = self.client.post("/device/discover", headers=self.headers, json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.path.read_bytes(), before)
        candidate = response.json["candidates"][0]
        self.assertEqual(response.json["selected_key"], candidate["key"])
        saved = self.client.patch(
            "/conf", headers=self.headers, json={"device": candidate["binding"]}
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json["device"]["instance_name"], "日常号")
        self.assertEqual(saved.json["device"]["last_serial"], "")
        self.assertEqual(config.Conf.model_validate(saved.json).device.instance_id, "3")

    def test_discovery_rejects_invalid_drafts_and_active_workers(self):
        for body in (
            None,
            [],
            {"device": []},
            {"launch": True},
            {"device": {"preset_id": "bad"}},
        ):
            with self.subTest(body=body):
                response = self.client.post(
                    "/device/discover", headers=self.headers, json=body
                )
                self.assertEqual(response.status_code, 400)
        with patch.object(self.server, "mower_thread", MagicMock()) as worker:
            worker.is_alive.return_value = True
            response = self.client.post(
                "/device/discover", headers=self.headers, json={}
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json["error"]["code"], "device_session_active")

    def configure_ldplayer_discovery(self):
        from arknights_mower.tests.device_discovery_tests import DiscoveryIO
        from arknights_mower.tests.device_session_tests import Simulator
        from arknights_mower.utils.device.discovery import DiscoveryService

        io = PreflightIO()
        io.host = "windows"
        io.installed.update(
            ["D:/LDPlayer/LDPlayer9", "D:/LDPlayer/LDPlayer9/ldconsole.exe"]
        )
        io.targets = [
            ("127.0.0.1:5555", "device"),
            ("127.0.0.1:5561", "device"),
        ]
        sources = DiscoveryIO()
        sources.installations = [
            {
                "preset_id": "windows.ldplayer9",
                "installation_path": "D:/LDPlayer/LDPlayer9",
                "manager_path": "D:/LDPlayer/LDPlayer9/ldconsole.exe",
                "instances": [
                    {
                        "instance_id": "0",
                        "instance_name": "其他账号",
                        "state": "running",
                        "serial": "127.0.0.1:5555",
                    },
                    {
                        "instance_id": "3",
                        "instance_name": "日常号",
                        "state": "running",
                        "serial": "127.0.0.1:5561",
                    },
                ],
            }
        ]
        simulator = Simulator()
        simulator.state = "running"
        simulator.serial = "127.0.0.1:5561"
        self.main.device_control = DeviceControl(
            lambda: config.conf,
            ManualAdapter(),
            preflight=PreflightService(io),
            discovery=DiscoveryService(sources, simulator),
        )
        return sources, simulator, io

    def test_ldplayer_choice_save_reload_and_refresh_keep_the_selected_instance(self):
        from arknights_mower.utils.device.discovery import DiscoveryService

        sources, simulator, io = self.configure_ldplayer_discovery()
        before = self.path.read_bytes()
        response = self.client.post("/device/discover", headers=self.headers, json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIsNone(response.json["selected_key"])
        self.assertEqual(response.json["candidates"][0]["instance_id"], "0")
        chosen = next(
            item for item in response.json["candidates"] if item["instance_id"] == "3"
        )
        self.assertEqual(chosen["preset_id"], "windows.ldplayer9")
        saved = self.client.patch(
            "/conf", headers=self.headers, json={"device": chosen["binding"]}
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json["device"]["instance_id"], "3")
        self.assertEqual(saved.json["device"]["last_serial"], "")
        self.assertEqual(saved.json["adb"], "")
        binding_saved = self.path.read_bytes()
        checked = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertEqual(checked.status_code, 200)
        self.assertTrue(checked.json["ok"], checked.json["error"])
        self.assertEqual(checked.json["serial"], "127.0.0.1:5561")
        self.assertEqual(checked.json["adb_path"], "product-adb")
        self.assertEqual(self.path.read_bytes(), binding_saved)
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
        reloaded = self.client.get("/conf", headers=self.headers)
        self.assertEqual(reloaded.json["device"]["preset_id"], "windows.ldplayer9")
        self.assertEqual(reloaded.json["device"]["instance_id"], "3")
        self.assertEqual(reloaded.json["device"]["last_serial"], "127.0.0.1:5561")
        self.assertEqual(reloaded.json["device"]["adb_path"], "product-adb")

        simulator.serial = "127.0.0.1:5601"
        io.targets.append(("127.0.0.1:5601", "device"))
        self.main.device_control = DeviceControl(
            lambda: config.conf,
            ManualAdapter(),
            preflight=PreflightService(io),
            discovery=DiscoveryService(sources, simulator),
        )
        checked = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertTrue(checked.json["ok"], checked.json["error"])
        self.assertEqual(checked.json["serial"], "127.0.0.1:5601")
        self.assertEqual(config.conf.device.last_serial, "127.0.0.1:5561")
        self.assertEqual(simulator.bindings, [("windows.ldplayer9", "3")] * 2)
        self.assertEqual(sources.calls, 1)

    def test_ldplayer_endpoint_failure_never_saves_another_online_instance(self):
        sources, simulator, io = self.configure_ldplayer_discovery()
        config.conf = config.conf.updated(
            {
                "device": {
                    "preset_id": "windows.ldplayer9",
                    "installation_path": "D:/LDPlayer/LDPlayer9",
                    "manager_path": "D:/LDPlayer/LDPlayer9/ldconsole.exe",
                    "instance_id": "3",
                    "last_serial": "127.0.0.1:5599",
                }
            }
        )
        config.save_conf()
        before = self.path.read_bytes()
        io.targets = [
            ("127.0.0.1:5555", "device"),
            ("127.0.0.1:5599", "device"),
        ]
        for _ in range(2):
            checked = self.client.post(
                "/device/preflight", headers=self.headers, json={}
            )
            self.assertEqual(checked.status_code, 200)
            self.assertFalse(checked.json["ok"])
            self.assertEqual(checked.json["error"]["code"], "target_absent")
            self.assertEqual(checked.json["serial"], "127.0.0.1:5561")
            self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(config.conf.device.last_serial, "127.0.0.1:5599")
        self.assertEqual(simulator.bindings, [("windows.ldplayer9", "3")] * 2)
        self.assertEqual(sources.calls, 0)

    def test_missing_screenshot_helper_returns_install_guidance_without_saving(self):
        from arknights_mower.utils.device.preflight import ScreenshotUnavailable

        io = PreflightIO()
        self.main.device_control = DeviceControl(
            lambda: config.conf, ManualAdapter(), preflight=PreflightService(io)
        )
        before = self.path.read_bytes()
        with patch.object(
            io,
            "capture_frame",
            side_effect=ScreenshotUnavailable(
                "请先安装 DroidCast APK，或选择 ADB gzip 后重试。"
            ),
        ):
            response = self.client.post(
                "/device/preflight", headers=self.headers, json={}
            )
        self.assertEqual(response.json["error"]["code"], "frame_failed")
        self.assertIn("安装 DroidCast", response.json["error"]["message"])
        self.assertEqual(response.json["error"]["fields"], ["screenshot_backend"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_start_runs_preflight_and_pins_its_verified_adb_and_package(self):
        class VerifiedAdapter(ManualAdapter):
            def open_verified(self, configuration, result):
                device = ManualDevice(result.serial)
                device.adb_path = result.adb_path
                device.package = configuration.device.game_package
                return device

        io = PreflightIO()
        control = DeviceControl(
            lambda: config.conf, VerifiedAdapter(), preflight=PreflightService(io)
        )
        opened = control.start()
        self.assertTrue(opened.ok, opened.error)
        self.assertEqual(opened.value.adb_path, "product-adb")
        self.assertEqual(opened.value.package, "com.hypergryph.arknights.bilibili")
        io.paths.clear()
        self.assertIs(control.start().value, opened.value)
        control.close()
        failed = control.start()
        self.assertFalse(failed.ok)
        self.assertEqual(failed.error.code, "missing_adb")
        with self.assertRaises(MowerExit):
            failed.unwrap()

    def test_preflight_failures_keep_actionable_http_contracts(self):
        cases = (
            (
                {"installation_path": "/missing"},
                {},
                "missing_installation",
                ["installation_path"],
            ),
            ({}, {"paths": set()}, "missing_adb", ["adb_path"]),
            (
                {"last_serial": ""},
                {"targets": [("a", "device"), ("b", "device")]},
                "multiple_devices",
                ["last_serial"],
            ),
            ({}, {"targets": [("USB-123", "unauthorized")]}, "device_unauthorized", []),
            (
                {},
                {"size": "Physical size: not-a-size"},
                "invalid_size",
                [],
            ),
            ({}, {"frame": None}, "frame_failed", ["screenshot_backend"]),
            (
                {},
                {
                    "installed_packages": [
                        "com.hypergryph.arknights",
                        "com.hypergryph.arknights.bilibili",
                    ]
                },
                "package_ambiguous",
                ["game_package"],
            ),
        )
        for profile, observations, code, fields in cases:
            with self.subTest(code=code):
                io = PreflightIO()
                for name, value in observations.items():
                    setattr(io, name, value)
                self.main.device_control = DeviceControl(
                    lambda: config.conf, ManualAdapter(), preflight=PreflightService(io)
                )
                response = self.client.post(
                    "/device/preflight", headers=self.headers, json={"device": profile}
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json["ok"])
                self.assertEqual(response.json["error"]["code"], code)
                self.assertEqual(response.json["error"]["fields"], fields)
                self.assertEqual(response.json["error"]["action"], "retry")
                self.assertTrue(response.json["error"]["message"])

    def test_physical_preflight_retains_failure_until_cancel_without_simulator_start(
        self,
    ):
        config.conf = config.conf.updated({"device": {"preset_id": "manual.physical"}})
        config.conf.close_simulator_when_idle = True
        io = PreflightIO()
        self.main.device_control = DeviceControl(
            lambda: config.conf, ManualAdapter(), preflight=PreflightService(io)
        )
        stop = Event()

        def cancel(seconds):
            self.assertEqual(seconds, 30)
            stop.set()
            raise MowerExit()

        with (
            patch.object(config, "stop_mower", stop),
            patch.object(self.main, "csleep", side_effect=cancel) as cooldown,
            patch.object(self.main, "base_scheduler", None),
            patch(
                "arknights_mower.utils.simulator.restart_simulator",
                side_effect=AssertionError(
                    "physical device has no simulator lifecycle"
                ),
            ),
        ):
            self.main.simulate(None)
        cooldown.assert_called_once_with(30)
        self.assertFalse(self.main.device_control.shutdown_requested)
        self.assertEqual(
            self.main.device_control.settings_status()["preflight"]["error"]["code"],
            "target_required",
        )

    def test_android_managed_factory_keeps_its_existing_device_adapter(self):
        from arknights_mower.utils.device.application import create_device_control

        with (
            patch.dict("os.environ", {"MOWER_ANDROID": "1"}),
            patch(
                "arknights_mower.utils.device.device.Device.create",
                return_value=ManualDevice("android-managed"),
            ),
            patch(
                "arknights_mower.utils.device.preflight_io.ProductionPreflightIO",
                side_effect=AssertionError(
                    "managed Android must not probe desktop ADB"
                ),
            ),
        ):
            control = create_device_control()
            self.assertEqual(control.start().serial, "android-managed")
            control.close()


if __name__ == "__main__":
    unittest.main()
