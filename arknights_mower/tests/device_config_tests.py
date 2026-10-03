"""Stable device settings through the configuration and HTTP boundaries."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from pydantic import BaseModel, Field
from yamlcore import CoreLoader

from arknights_mower.utils import config


class LegacyDeviceConfig(BaseModel):
    """Frozen device fields from the pre-#238 Conf, ignoring unknown new keys."""

    class Simulator(BaseModel):
        name: str = ""
        index: str | int = "-1"
        simulator_folder: str = ""

    class DroidCast(BaseModel):
        enable: bool = True

    class CustomScreenshot(BaseModel):
        enable: bool = False

    simulator: Simulator = Field(default_factory=Simulator)
    adb: str = "127.0.0.1:16384"
    maa_adb_path: str = ""
    package_type: int = 1
    mumu12IPC: bool = False
    droidcast: DroidCast = Field(default_factory=DroidCast)
    custom_screenshot: CustomScreenshot = Field(default_factory=CustomScreenshot)
    touch_method: str = "scrcpy"


FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures/device_config_legacy.json").read_text(
        encoding="utf-8"
    )
)


class DeviceConfigurationTests(unittest.TestCase):
    def test_retired_mumu_profile_requires_manual_rebinding(self):
        original = {
            "preset_id": "windows.mumu6",
            "installation_path": "C:/Nemu",
            "adb_path": "C:/Nemu/adb.exe",
            "last_serial": "127.0.0.1:7555",
            "game_package_confirmed": True,
        }
        conf = config.Conf(device=original)
        self.assertEqual(conf.device.preset_id, "manual.other")
        self.assertEqual(conf.device.last_serial, "")
        self.assertFalse(conf.device.game_package_confirmed)
        self.assertEqual(conf.device.adb_path, original["adb_path"])
        self.assertEqual(conf.device.installation_path, original["installation_path"])
        self.assertEqual(original["preset_id"], "windows.mumu6")
        self.assertEqual(original["last_serial"], "127.0.0.1:7555")
        self.assertEqual(config.Conf(**conf.model_dump()).device, conf.device)

    def test_retired_mumu_aliases_never_reuse_the_old_endpoint(self):
        for alias in (
            "MuMu6",
            "MuMu 6",
            "MuMu模拟器6",
            "MuMu模拟器 6",
            "Nemu",
            "NemuPlayer",
        ):
            with self.subTest(alias=alias):
                conf = config.Conf(simulator={"name": alias}, adb="127.0.0.1:7555")
                self.assertEqual(conf.device.preset_id, "manual.other")
                self.assertEqual(conf.device.last_serial, "")

    def test_alias_fixtures_are_readable_by_old_versions_after_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conf.yml"
            for name, preset, canonical in FIXTURES["simulators"]:
                with self.subTest(name=name):
                    conf = config.Conf(simulator={"name": name, "index": "vm-name"})
                    self.assertEqual(conf.device.preset_id, preset)
                    with (
                        patch.object(config, "conf_path", path),
                        patch.object(config, "conf", conf),
                    ):
                        config.save_conf()
                    old = LegacyDeviceConfig(
                        **yaml.load(path.read_text(encoding="utf-8"), Loader=CoreLoader)
                    )
                    self.assertEqual(old.simulator.name, canonical)
                    self.assertEqual(old.simulator.index, "vm-name")

    def test_all_legacy_backend_combinations_keep_their_effective_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conf.yml"
            for ipc, droidcast, custom, screenshot in FIXTURES["capture_combinations"]:
                for touch, effective_touch in FIXTURES["touch_methods"]:
                    with self.subTest(
                        ipc=ipc, droidcast=droidcast, custom=custom, touch=touch
                    ):
                        conf = config.Conf(
                            mumu12IPC=ipc,
                            droidcast={"enable": droidcast},
                            custom_screenshot={"enable": custom},
                            touch_method=touch,
                        )
                        self.assertEqual(conf.device.screenshot_backend, screenshot)
                        self.assertEqual(
                            conf.device.touch_backend,
                            "mumu_ipc" if ipc else effective_touch,
                        )
                        with (
                            patch.object(config, "conf_path", path),
                            patch.object(config, "conf", conf),
                        ):
                            config.save_conf()
                        old = LegacyDeviceConfig(
                            **yaml.load(
                                path.read_text(encoding="utf-8"), Loader=CoreLoader
                            )
                        )
                        self.assertEqual(old.mumu12IPC, screenshot == "mumu_ipc")
                        self.assertEqual(
                            old.droidcast.enable, screenshot == "droidcast"
                        )
                        self.assertEqual(
                            old.custom_screenshot.enable, screenshot == "custom"
                        )
                        self.assertEqual(
                            old.touch_method, "scrcpy" if ipc else effective_touch
                        )

    def test_load_legacy_conf_preserves_effective_backends_without_writing(self):
        original = (
            "simulator:\n  name: MuMu12\n  index: 3\n"
            "  simulator_folder: C:/MuMu\n"
            "adb: 127.0.0.1:16480\nmaa_adb_path: C:/tools/adb.exe\n"
            "mumu12IPC: true\ndroidcast:\n  enable: true\n"
            "custom_screenshot:\n  enable: true\ntouch_method: maatouch\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conf.yml"
            path.write_text(original, encoding="utf-8")
            with patch.object(config, "conf_path", path), patch.object(config, "conf"):
                config.load_conf()
                profile = config.conf.device
                self.assertEqual(profile.preset_id, "windows.mumu12")
                self.assertEqual(profile.instance_id, "3")
                self.assertEqual(profile.last_serial, "127.0.0.1:16480")
                self.assertEqual(profile.adb_path, "C:/tools/adb.exe")
                self.assertEqual(profile.screenshot_backend, "mumu_ipc")
                self.assertEqual(profile.touch_backend, "mumu_ipc")
                self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_new_profile_is_saved_with_downgrade_readable_legacy_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conf.yml"
            conf = config.Conf(
                device={
                    "preset_id": "windows.mumu12",
                    "installation_path": "C:/MuMu",
                    "manager_path": "C:/MuMu/shell/MuMuManager.exe",
                    "adb_path": "C:/adb.exe",
                    "instance_id": "4",
                    "instance_name": "日常基建",
                    "last_serial": "127.0.0.1:16512",
                    "game_package": "com.hypergryph.arknights.bilibili",
                    "screenshot_backend": "mumu_ipc",
                    "touch_backend": "mumu_ipc",
                },
                simulator={"wait_time": 60, "hotkey": "alt+x"},
                droidcast={"rotate": True},
                custom_screenshot={"command": "my-capture"},
            )
            with (
                patch.object(config, "conf_path", path),
                patch.object(config, "conf", conf),
            ):
                config.save_conf()
                written = yaml.load(path.read_text(encoding="utf-8"), Loader=CoreLoader)
                self.assertEqual(written["simulator"]["name"], "MuMu12")
                self.assertEqual(written["simulator"]["index"], "4")
                self.assertEqual(written["simulator"]["simulator_folder"], "C:/MuMu")
                self.assertEqual(written["simulator"]["wait_time"], 60)
                self.assertEqual(written["adb"], "127.0.0.1:16512")
                self.assertEqual(written["maa_adb_path"], "C:/adb.exe")
                self.assertEqual(written["package_type"], 2)
                self.assertTrue(written["mumu12IPC"])
                self.assertFalse(written["droidcast"]["enable"])
                self.assertFalse(written["custom_screenshot"]["enable"])
                self.assertEqual(written["touch_method"], "scrcpy")
                self.assertTrue(written["droidcast"]["rotate"])
                self.assertEqual(written["custom_screenshot"]["command"], "my-capture")
                config.load_conf()
                self.assertEqual(config.conf.device, conf.device)


class DeviceConfigurationRouteTests(unittest.TestCase):
    def setUp(self):
        import server

        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "conf.yml"
        self.path.write_text("adb: usb-original\ntheme: dark\n", encoding="utf-8")
        manager = MagicMock()
        manager.get_active_plan_key.return_value = ""
        for context in (
            patch.object(config, "conf_path", self.path),
            patch.object(config, "conf", config.Conf()),
            patch.object(server.app, "token", "device-fixture-token", create=True),
            patch(
                "arknights_mower.utils.config.weekly_plan_loader.get_weekly_plan_manager",
                return_value=manager,
            ),
            patch(
                "arknights_mower.utils.workshop_config.get_path",
                return_value=Path(self.directory.name) / "no-old-workshop.json",
            ),
        ):
            context.start()
            self.addCleanup(context.stop)
        config.load_conf()
        self.client = server.app.test_client()
        self.headers = {"token": "device-fixture-token"}

    def test_incompatible_capture_patch_never_changes_memory_or_disk(self):
        config.conf = config.Conf(device={"preset_id": "manual.other"})
        before = self.path.read_bytes()
        original = config.conf.model_dump()
        for backend in ("mumu_ipc", "ld_native"):
            with self.subTest(backend=backend):
                response = self.client.patch(
                    "/conf",
                    headers=self.headers,
                    json={
                        "device": {
                            "screenshot_backend": backend,
                            "touch_backend": "mumu_ipc"
                            if backend == "mumu_ipc"
                            else "scrcpy",
                        }
                    },
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json["error"], "invalid_configuration")
                self.assertEqual(config.conf.model_dump(), original)
                self.assertEqual(self.path.read_bytes(), before)

    def test_get_migrates_in_memory_and_patch_preserves_other_settings(self):
        before = self.path.read_bytes()
        response = self.client.get("/conf", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["device"]["last_serial"], "usb-original")
        self.assertEqual(self.path.read_bytes(), before)
        response = self.client.patch(
            "/conf",
            headers=self.headers,
            json={"device": {"adb_path": "C:/new/adb.exe"}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["device"]["adb_path"], "C:/new/adb.exe")
        self.assertEqual(response.json["device"]["last_serial"], "usb-original")
        self.assertEqual(response.json["theme"], "dark")
        config.load_conf()
        self.assertEqual(config.conf.device.adb_path, "C:/new/adb.exe")
        self.assertEqual(config.conf.theme, "dark")

    def test_legacy_full_save_and_partial_edits_update_the_stable_profile(self):
        self.client.patch(
            "/conf",
            headers=self.headers,
            json={"device": {"manager_path": "C:/manager.exe"}},
        )
        old_payload = self.client.get("/conf", headers=self.headers).json
        old_payload.pop("device")
        old_payload.update(
            simulator={
                "name": "ReDroid",
                "index": "arknights",
                "simulator_folder": "/docker",
            },
            adb="127.0.0.1:5558",
            maa_adb_path="/usr/bin/adb",
            mumu12IPC=False,
            droidcast={"enable": False, "rotate": True},
            custom_screenshot={"enable": True, "command": "capture-fixture"},
            touch_method="maatouch",
            package_type=2,
        )
        response = self.client.post("/conf", headers=self.headers, json=old_payload)
        self.assertEqual(response.status_code, 200)
        data = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(data["device"]["preset_id"], "linux.redroid")
        self.assertEqual(data["device"]["instance_id"], "arknights")
        self.assertEqual(data["device"]["last_serial"], "127.0.0.1:5558")
        self.assertEqual(data["device"]["adb_path"], "/usr/bin/adb")
        self.assertEqual(
            data["device"]["game_package"], "com.hypergryph.arknights.bilibili"
        )
        self.assertEqual(data["device"]["screenshot_backend"], "custom")
        self.assertEqual(data["device"]["touch_backend"], "maatouch")
        response = self.client.patch(
            "/conf", headers=self.headers, json={"droidcast": {"enable": True}}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["device"]["screenshot_backend"], "droidcast")
        self.assertFalse(response.json["custom_screenshot"]["enable"])
        self.assertTrue(response.json["droidcast"]["rotate"])
        self.assertEqual(
            response.json["custom_screenshot"]["command"], "capture-fixture"
        )

    def test_invalid_profile_never_changes_memory_or_file(self):
        for device in (
            {"screenshot_backend": "unknown"},
            {"touch_backend": "unknown"},
            {"screenshot_backend": "mumu_ipc"},
            {"touch_backend": "mumu_ipc"},
            {"preset_id": "unknown"},
            {"preset_id": ["windows.mumu12"]},
            {"candidates": ["ephemeral"]},
            None,
        ):
            with self.subTest(device=device):
                before, current = self.path.read_bytes(), config.conf.model_dump()
                response = self.client.patch(
                    "/conf", headers=self.headers, json={"device": device}
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json["error"], "invalid_configuration")
                self.assertEqual(config.conf.model_dump(), current)
                self.assertEqual(self.path.read_bytes(), before)

    def test_binding_changes_clear_old_serial_but_unrelated_edits_do_not(self):
        for edit in (
            {"preset_id": "windows.mumu12"},
            {"installation_path": "C:/new-emulator"},
            {"manager_path": "C:/new-manager.exe"},
            {"instance_id": "second-instance"},
        ):
            with self.subTest(edit=edit):
                config.conf = config.Conf(adb="old-serial")
                response = self.client.patch(
                    "/conf", headers=self.headers, json={"device": edit}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["device"]["last_serial"], "")
                self.assertEqual(response.json["adb"], "")
        config.conf.set_device_endpoint("new-serial")
        response = self.client.patch(
            "/conf", headers=self.headers, json={"theme": "light"}
        )
        self.assertEqual(response.json["device"]["last_serial"], "new-serial")
        self.assertEqual(response.json["adb"], "new-serial")

    def test_nox_binding_persists_vendor_identity_and_topology_confirmation(self):
        binding = {
            "preset_id": "windows.nox",
            "installation_path": "C:/Nox/bin",
            "manager_path": "C:/Nox/bin/NoxConsole.exe",
            "instance_id": "Nox_2",
            "instance_name": "夜神主账号",
            "instance_uuid": "582fe022-b9b5-452c-aa51-cd14731fb451",
            "topology_fingerprint": "confirmed-nox-topology",
            "last_serial": "",
        }
        response = self.client.patch(
            "/conf", headers=self.headers, json={"device": binding}
        )
        self.assertEqual(response.status_code, 200)
        config.load_conf()
        saved = self.client.get("/conf", headers=self.headers).json
        for key, value in binding.items():
            self.assertEqual(saved["device"][key], value)
        self.assertEqual(saved["simulator"]["index"], "Nox_2")
        self.assertEqual(saved["theme"], "dark")

    def test_bluestacks_binding_persists_product_config_and_instance_keyword(self):
        binding = {
            "preset_id": "windows.bluestacks5",
            "installation_path": "C:/BlueStacks_nxt",
            "manager_path": "C:/BlueStacks_nxt/HD-Player.exe",
            "config_path": "C:/ProgramData/BlueStacks_nxt/bluestacks.conf",
            "instance_id": "Pie64_2",
            "instance_name": "蓝叠主账号",
            "last_serial": "",
        }
        response = self.client.patch(
            "/conf", headers=self.headers, json={"device": binding}
        )
        self.assertEqual(response.status_code, 200)
        config.load_conf()
        saved = self.client.get("/conf", headers=self.headers).json
        for key, value in binding.items():
            self.assertEqual(saved["device"][key], value)
        self.assertEqual(saved["simulator"]["index"], "Pie64_2")
        self.assertEqual(saved["theme"], "dark")

    def test_nox_target_edits_discard_old_identity_guards_and_endpoint(self):
        for edit in (
            {"preset_id": "manual.other"},
            {"installation_path": "D:/Nox/bin"},
            {"manager_path": "D:/Nox/bin/NoxConsole.exe"},
            {"instance_id": "Nox_3"},
        ):
            with self.subTest(edit=edit):
                config.conf = config.Conf(
                    device={
                        "preset_id": "windows.nox",
                        "instance_id": "Nox_2",
                        "instance_uuid": "original-vm-uuid",
                        "topology_fingerprint": "original-topology",
                        "last_serial": "127.0.0.1:62025",
                        "game_package_confirmed": True,
                    }
                )
                response = self.client.patch(
                    "/conf", headers=self.headers, json={"device": edit}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["device"]["instance_uuid"], "")
                self.assertEqual(response.json["device"]["topology_fingerprint"], "")
                self.assertEqual(response.json["device"]["last_serial"], "")
                self.assertFalse(response.json["device"]["game_package_confirmed"])

    def test_bluestacks_source_edits_invalidate_the_previous_endpoint(self):
        original = {
            "preset_id": "windows.bluestacks5",
            "installation_path": "C:/BlueStacks_nxt",
            "manager_path": "C:/BlueStacks_nxt/HD-Player.exe",
            "config_path": "C:/ProgramData/BlueStacks_nxt/bluestacks.conf",
            "instance_id": "Pie64_2",
            "last_serial": "127.0.0.1:5555",
            "game_package_confirmed": True,
        }
        new_config = "D:/BlueStacksData/bluestacks.conf"
        for edit, expected_config in (
            ({"preset_id": "manual.other"}, ""),
            ({"installation_path": "D:/BlueStacks_nxt"}, ""),
            ({"manager_path": "D:/BlueStacks_nxt/HD-Player.exe"}, ""),
            ({"config_path": new_config}, new_config),
            ({"instance_id": "Pie64_3"}, original["config_path"]),
            (
                {"installation_path": "D:/BlueStacks_nxt", "config_path": new_config},
                new_config,
            ),
        ):
            with self.subTest(edit=edit):
                config.conf = config.Conf(device=original)
                response = self.client.patch(
                    "/conf", headers=self.headers, json={"device": edit}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json["device"]["config_path"], expected_config
                )
                self.assertEqual(response.json["device"]["last_serial"], "")
                self.assertEqual(response.json["adb"], "")
                self.assertFalse(response.json["device"]["game_package_confirmed"])
        config.conf = config.Conf(device=original)
        response = self.client.patch(
            "/conf", headers=self.headers, json={"theme": "light"}
        )
        self.assertEqual(
            response.json["device"]["config_path"], original["config_path"]
        )
        self.assertEqual(
            response.json["device"]["last_serial"], original["last_serial"]
        )

    def test_nox_reconfirmation_cannot_reuse_serial_or_package_confirmation(self):
        for edit in (
            {"instance_uuid": "recreated-vm"},
            {"topology_fingerprint": "imported-another-vm"},
        ):
            with self.subTest(edit=edit):
                config.conf = config.Conf(
                    device={
                        "preset_id": "windows.nox",
                        "instance_id": "Nox_2",
                        "instance_uuid": "original-vm",
                        "topology_fingerprint": "original-topology",
                        "last_serial": "127.0.0.1:62025",
                        "game_package_confirmed": True,
                    }
                )
                # A full stale settings form is not a fresh endpoint verification.
                payload = {**config.conf.device.model_dump(), **edit}
                response = self.client.patch(
                    "/conf", headers=self.headers, json={"device": payload}
                )
                self.assertEqual(response.status_code, 200)
                for key, value in edit.items():
                    self.assertEqual(response.json["device"][key], value)
                self.assertEqual(response.json["device"]["last_serial"], "")
                self.assertFalse(response.json["device"]["game_package_confirmed"])

    def test_active_session_rejects_vm_guard_changes_but_keeps_unrelated_edits(self):
        import arknights_mower.__main__ as main
        import server
        from arknights_mower.tests.device_application_tests import ManualAdapter
        from arknights_mower.utils.device.application import DeviceControl

        control = DeviceControl(lambda: config.conf, ManualAdapter())
        with (
            patch.object(main, "device_control", control),
            patch.object(server, "mower_thread", None),
        ):
            control.start()
            before = self.path.read_bytes()
            for edit in (
                {"instance_uuid": "changed-vm-uuid"},
                {"topology_fingerprint": "changed-topology"},
                {"config_path": "C:/ProgramData/BlueStacks_nxt/bluestacks.conf"},
            ):
                with self.subTest(edit=edit):
                    response = self.client.patch(
                        "/conf", headers=self.headers, json={"device": edit}
                    )
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.json["error"], "device_session_active")
                    self.assertEqual(self.path.read_bytes(), before)
            response = self.client.patch(
                "/conf", headers=self.headers, json={"theme": "light"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["device"]["last_serial"], "usb-original")
            control.close()

    def test_failed_write_preserves_previous_configuration_and_returns_error(self):
        before, current = self.path.read_bytes(), config.conf.model_dump()
        with patch(
            "arknights_mower.utils.config.os.replace",
            side_effect=PermissionError("locked"),
        ):
            response = self.client.patch(
                "/conf", headers=self.headers, json={"device": {"last_serial": "new"}}
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json["error"], "configuration_save_failed")
        self.assertEqual(config.conf.model_dump(), current)
        self.assertEqual(self.path.read_bytes(), before)

    def test_partial_configuration_requires_authentication(self):
        before = self.path.read_bytes()
        response = self.client.patch("/conf", json={"device": {"last_serial": "other"}})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.path.read_bytes(), before)

    def test_partial_save_replaces_selection_maps_and_keeps_sibling_settings(self):
        config.conf = config.Conf(
            rogue={
                "core_char": "假日威龙陈",
                "collectible_mode_start_list": {"old": True},
            }
        )
        for selected in ({"old": True, "new": True}, {"new": True}, {}):
            response = self.client.patch(
                "/conf",
                headers=self.headers,
                json={"rogue": {"collectible_mode_start_list": selected}},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json["rogue"]["collectible_mode_start_list"], selected
            )
            self.assertEqual(response.json["rogue"]["core_char"], "假日威龙陈")

    def test_advanced_timing_and_query_timeout_fields_persist(self):
        response = self.client.patch(
            "/conf",
            headers=self.headers,
            json={
                "device": {
                    "manager_query_timeout": 8.0,
                    "simulator_hotkey_delay": 5.5,
                    "simulator_hotkey": "alt+w",
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["device"]["manager_query_timeout"], 8.0)
        self.assertEqual(response.json["device"]["simulator_hotkey_delay"], 5.5)
        self.assertEqual(response.json["device"]["simulator_hotkey"], "alt+w")
        self.assertEqual(response.json["simulator"]["hotkey"], "alt+w")
        self.assertEqual(response.json["simulator"]["hotkey_delay"], 5.5)

    def test_clearing_the_boss_key_is_not_refilled_from_the_legacy_field(self):
        # The legacy keys keep a stale boss key from an older config file. The
        # device profile owns the field, so clearing it must stay cleared instead
        # of being copied back from that stale legacy value.
        config.conf = config.Conf(
            simulator={"hotkey": "alt+q"},
            device={"preset_id": "windows.mumu12", "simulator_hotkey": "alt+q"},
        )
        response = self.client.patch(
            "/conf", headers=self.headers, json={"device": {"simulator_hotkey": ""}}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["device"]["simulator_hotkey"], "")
        self.assertEqual(response.json["simulator"]["hotkey"], "")
        config.load_conf()
        self.assertEqual(config.conf.device.simulator_hotkey, "")

    def test_legacy_boss_key_still_migrates_into_a_new_profile(self):
        config.conf = config.Conf(simulator={"hotkey": "ctrl+alt+w"})
        self.assertEqual(config.conf.device.simulator_hotkey, "ctrl+alt+w")

    def test_legacy_boss_key_migrates_into_a_profile_block_that_predates_it(self):
        # An install that already saved a device block before the field existed
        # keeps its legacy boss key: the profile adopts it once, then owns it.
        config.conf = config.Conf(
            simulator={"hotkey": "ctrl+alt+w", "hotkey_delay": 5.0},
            device={"preset_id": "windows.mumu12", "instance_id": "0"},
        )
        self.assertEqual(config.conf.device.simulator_hotkey, "ctrl+alt+w")
        self.assertEqual(config.conf.device.simulator_hotkey_delay, 5.0)
        self.assertEqual(config.conf.simulator.hotkey, "ctrl+alt+w")
        self.assertEqual(config.conf.simulator.hotkey_delay, 5.0)
        # Once the profile holds the field, clearing it wins over the legacy copy.
        response = self.client.patch(
            "/conf", headers=self.headers, json={"device": {"simulator_hotkey": ""}}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["device"]["simulator_hotkey"], "")
        self.assertEqual(response.json["simulator"]["hotkey"], "")

    def test_an_explicit_default_delay_beats_the_legacy_value(self):
        # A profile that persisted the default 3.0 s keeps it: the legacy 1.0 s is
        # neither adopted nor left behind for the next reader.
        config.conf = config.Conf(
            simulator={"hotkey_delay": 1.0},
            device={"preset_id": "windows.mumu12", "simulator_hotkey_delay": 3.0},
        )
        self.assertEqual(config.conf.device.simulator_hotkey_delay, 3.0)
        self.assertEqual(config.conf.simulator.hotkey_delay, 3.0)


if __name__ == "__main__":
    unittest.main()
