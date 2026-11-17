import base64
import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import yaml

from arknights_mower.utils import config as config_module
from arknights_mower.utils import configuration_secrets, credential_store, workshop_config
from arknights_mower.utils.config import atomic_write, migrate_app_config_paths
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.configuration_secrets import (
    conf_secrets_path,
    legacy_conf_secrets_path,
)
from arknights_mower.utils.credential_store import read_credentials


@contextmanager
def _patched_conf(path, conf=None):
    """临时切到 path 与 conf 下读取/写配置，结束后还原模块级 conf。

    #258 之后 save_conf 只写用户配置过的键，测试须用固定的 path/conf 隔离环境里的
    @app/config/conf.yml，避免依赖残留内容。
    """
    original = config_module.conf
    try:
        with (
            patch.object(config_module, "conf_path", path),
            patch.object(
                config_module, "rescue_plan_path", path.parent / "rescue_plan.json"
            ),
            patch.object(config_module, "rescue_plan", config_module.PlanModel()),
        ):
            if conf is not None:
                config_module.conf = conf
            yield
    finally:
        config_module.conf = original


class TestMaaConfig(unittest.TestCase):
    def test_device_profile_uses_bundled_adb_when_path_is_omitted(self):
        from arknights_mower.utils import path

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(path, "_internal_dir", Path(root)),
        ):
            tools = Path(root) / "platform-tools"
            tools.mkdir()
            for name in ("adb", "adb.exe"):
                (tools / name).touch()
            for platform in ("darwin", "win32", "linux"):
                with patch("sys.platform", platform), self.subTest(platform=platform):
                    name = "adb.exe" if platform == "win32" else "adb"
                    expected = f"@internal/platform-tools/{name}"
                    profile = DeviceProfile(preset_id="manual.physical")
                    self.assertEqual(profile.adb_path, expected)
                    self.assertNotIn("adb_path", profile.model_fields_set)
                    for values in ({}, {"device": {"preset_id": "manual.physical"}}):
                        conf = Conf(**values)
                        self.assertEqual(conf.device.adb_path, expected)
                        self.assertEqual(conf.maa_adb_path, expected)
                        restored = Conf(**conf.model_dump())
                        self.assertEqual(restored.device.adb_path, expected)
                        self.assertEqual(restored.maa_adb_path, expected)

    def test_explicit_device_adb_path_is_preserved(self):
        with patch("sys.platform", "darwin"):
            for selected in ("/custom/adb", ""):
                with self.subTest(selected=selected):
                    conf = Conf(device={"adb_path": selected})
                    updated = conf.updated({"theme": "dark"})
                    restored = Conf(**updated.model_dump())
                    self.assertEqual(restored.device.adb_path, selected)
                    self.assertEqual(restored.maa_adb_path, selected)

    def test_bundled_device_adb_survives_save_and_reload(self):
        with (
            tempfile.TemporaryDirectory() as root,
            patch("sys.platform", "darwin"),
            patch.object(config_module, "__system__", "darwin"),
            patch.dict(os.environ, {"MOWER_ANDROID": "0"}),
        ):
            conf_path = Path(root) / "conf.yml"
            with _patched_conf(conf_path):
                config_module.load_conf()
                expected = "@internal/platform-tools/adb"
                self.assertEqual(config_module.conf.device.adb_path, expected)
                self.assertEqual(config_module.conf.device.last_serial, "")
                config_module.save_conf()
                config_module.load_conf()
                self.assertEqual(config_module.conf.device.adb_path, expected)
                self.assertEqual(config_module.conf.maa_adb_path, expected)

    def test_defaults_share_global_maa_directory_independently_of_instance(self):
        from arknights_mower.utils import path

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(path, "_data_dir", Path(root) / "data"),
            patch.object(path, "_internal_dir", Path(root) / "bundle"),
        ):
            for platform in ("darwin", "win32", "linux"):
                for space in ("one", "two", str(Path(root) / "custom-instance")):
                    with (
                        patch("sys.platform", platform),
                        patch.object(path, "global_space", space),
                    ):
                        conf = Conf()
                    self.assertEqual(conf.maa_path, "@app/MAA")
                    self.assertEqual(
                        path.resolve_config_path(conf.maa_path),
                        str(Path(root) / "data/MAA"),
                    )
                    self.assertEqual(
                        conf.maa_conn_preset,
                        "CompatMac" if platform == "darwin" else "General",
                    )

    def test_existing_maa_settings_including_explicit_empty_values_are_preserved(self):
        configured = {
            "maa_path": "/custom/maa",
            "maa_adb_path": "/custom/adb",
            "maa_conn_preset": "General",
        }
        for values in (configured, dict.fromkeys(configured, "")):
            for platform in ("darwin", "win32", "linux"):
                with (
                    patch("sys.platform", platform),
                    patch.dict(
                        os.environ,
                        {"MOWER_ADB_BIN": "/usr/bin/adb"},
                    ),
                ):
                    conf = Conf(**values)
                    restored = Conf(**conf.model_dump())
                    for key, value in values.items():
                        self.assertEqual(getattr(restored, key), value)

    def test_adb_uses_bundle_then_linux_environment_or_path_and_windows_can_be_empty(
        self,
    ):
        from arknights_mower.utils import path

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(path, "_internal_dir", Path(root)),
            patch.dict(os.environ, {"MOWER_ADB_BIN": ""}),
            patch("shutil.which", return_value=None) as which,
        ):
            for platform in ("win32", "linux"):
                with patch("sys.platform", platform):
                    self.assertEqual(Conf().maa_adb_path, "")
                    self.assertEqual(DeviceProfile().adb_path, "")
            with patch("sys.platform", "linux"):
                which.return_value = "/usr/bin/adb"
                self.assertEqual(Conf().maa_adb_path, "/usr/bin/adb")
                self.assertEqual(DeviceProfile().adb_path, "/usr/bin/adb")
                with patch.dict(os.environ, {"MOWER_ADB_BIN": "/custom/adb"}):
                    self.assertEqual(Conf().maa_adb_path, "/custom/adb")
                    self.assertEqual(DeviceProfile().adb_path, "/custom/adb")
            tools_dir = Path(root) / "platform-tools"
            tools_dir.mkdir()
            for name in ("adb", "adb.exe"):
                (tools_dir / name).write_text("bundled executable")
            for platform in ("darwin", "win32", "linux"):
                with patch("sys.platform", platform):
                    name = "adb.exe" if platform == "win32" else "adb"
                    self.assertEqual(
                        Conf().maa_adb_path, f"@internal/platform-tools/{name}"
                    )
                    self.assertEqual(
                        path.resolve_config_path(Conf().maa_adb_path),
                        str(tools_dir / name),
                    )

    def test_mirrorchyan_token_round_trip(self):
        conf = Conf(
            maa_mirrorchyan_token="fixture-token",
            maa_update_channel="beta",
            maa_auto_check_update=True,
        )
        restored = Conf(**conf.model_dump())
        self.assertEqual(restored.maa_mirrorchyan_token, "fixture-token")
        self.assertEqual(restored.maa_update_channel, "beta")
        self.assertTrue(restored.maa_auto_check_update)


class TestUpdateConfig(unittest.TestCase):
    def test_auto_update_enables_check_and_round_trips(self):
        conf = Conf(resource_update={"enable": False, "auto_update": True})
        self.assertTrue(conf.resource_update.enable)
        self.assertTrue(conf.resource_update.auto_update)
        restored = Conf(**conf.model_dump())
        self.assertTrue(restored.resource_update.enable)
        self.assertTrue(restored.resource_update.auto_update)

    def test_old_update_settings_migrate_to_resource_update(self):
        conf = Conf(hot_update={"enable": False, "auto_update": True})
        self.assertTrue(conf.resource_update.enable)
        self.assertTrue(conf.resource_update.auto_update)
        self.assertNotIn("hot_update", conf.model_dump())


class TestAtomicWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.target = self.dir / "sub" / "target.json"

    def _writer(self, f):
        f.write("{}")

    def test_writes_content_and_removes_temp(self):
        atomic_write(self.target, self._writer)
        self.assertTrue(self.target.is_file())
        self.assertEqual(self.target.read_text(encoding="utf-8"), "{}")
        leftovers = [p for p in self.dir.rglob(".*.tmp") if p.is_file()]
        self.assertEqual(leftovers, [])

    def test_creates_parent_dirs(self):
        atomic_write(self.target, self._writer)
        self.assertTrue(self.target.parent.is_dir())

    def test_cleans_temp_on_writer_exception(self):
        def bad_writer(f):
            f.write("partial")
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            atomic_write(self.target, bad_writer)
        self.assertFalse(self.target.exists())
        leftovers = [p for p in self.dir.rglob(".*.tmp") if p.is_file()]
        self.assertEqual(leftovers, [])

    def test_overwrites_existing_file(self):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text("old", encoding="utf-8")
        atomic_write(self.target, self._writer)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "{}")

    def test_concurrent_writes_same_path_succeed(self):
        # web/调度线程可能并发写同一文件（如 cultivate.json）：每路径锁串行化，
        # Windows 上不应再出现 os.replace PermissionError
        target = self.dir / "shared.json"
        errors = []

        def worker(tag):
            try:
                for _ in range(20):
                    atomic_write(target, lambda f: json.dump({"tag": tag}, f))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertTrue(target.is_file())


class TestMigrateAppConfigPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.old = self.dir / "old.json"
        self.new = self.dir / "new" / "new.json"

    def _pairs(self):
        return [(self.old, self.new)]

    def test_moves_old_when_new_missing(self):
        self.old.write_text("data", encoding="utf-8")
        with patch.object(config_module, "_CONFIG_PATH_PAIRS", self._pairs()):
            migrate_app_config_paths()
        self.assertFalse(self.old.exists())
        self.assertEqual(self.new.read_text(encoding="utf-8"), "data")

    def test_keeps_both_when_both_exist(self):
        self.old.write_text("old", encoding="utf-8")
        self.new.parent.mkdir(parents=True, exist_ok=True)
        self.new.write_text("new", encoding="utf-8")
        with patch.object(config_module, "_CONFIG_PATH_PAIRS", self._pairs()):
            migrate_app_config_paths()
        self.assertEqual(self.old.read_text(encoding="utf-8"), "old")
        self.assertEqual(self.new.read_text(encoding="utf-8"), "new")

    def test_leaves_new_alone_when_only_new(self):
        self.new.parent.mkdir(parents=True, exist_ok=True)
        self.new.write_text("new", encoding="utf-8")
        with patch.object(config_module, "_CONFIG_PATH_PAIRS", self._pairs()):
            migrate_app_config_paths()
        self.assertEqual(self.new.read_text(encoding="utf-8"), "new")
        self.assertFalse(self.old.exists())

    def test_noop_when_neither_exists(self):
        with patch.object(config_module, "_CONFIG_PATH_PAIRS", self._pairs()):
            migrate_app_config_paths()
        self.assertFalse(self.old.exists())
        self.assertFalse(self.new.exists())

    def test_migrate_then_load_reads_legacy_conf(self):
        # 核心事故防护：旧 conf 存在 → migrate → load_conf 读到旧值而非默认值
        old = self.dir / "conf.yml"
        new = self.dir / "config" / "conf.yml"
        legacy = "webview:\n  port: 58001\n"
        old.write_text(legacy, encoding="utf-8")
        original_conf = config_module.conf
        try:
            with (
                patch.object(config_module, "_CONFIG_PATH_PAIRS", [(old, new)]),
                patch.object(config_module, "conf_path", new),
            ):
                migrate_app_config_paths()
                config_module.load_conf()
            self.assertEqual(config_module.conf.webview.port, 58001)
            self.assertEqual(new.read_text(encoding="utf-8"), legacy)
        finally:
            config_module.conf = original_conf

    def test_migration_failure_stops_before_defaults_can_hide_old_file(self):
        # Windows 上迁移失败时中止启动，不能随后生成默认配置遮蔽旧文件。
        old = self.dir / "conf.yml"
        new = self.dir / "config" / "conf.yml"
        old.write_text("legacy", encoding="utf-8")

        def boom(*args, **kwargs):
            raise PermissionError("locked")

        with (
            patch.object(config_module, "_CONFIG_PATH_PAIRS", [(old, new)]),
            patch("arknights_mower.utils.config.os.replace", boom),
            self.assertRaisesRegex(OSError, "已停止启动"),
        ):
            migrate_app_config_paths()
        self.assertTrue(old.exists())
        self.assertFalse(new.exists())

    def test_concurrent_migration_success_does_not_block_startup(self):
        self.old.write_text("legacy", encoding="utf-8")

        def moved_elsewhere(*args):
            self.new.write_text("legacy", encoding="utf-8")
            self.old.unlink()
            raise FileNotFoundError("already moved")

        with (
            patch.object(config_module, "_CONFIG_PATH_PAIRS", self._pairs()),
            patch("arknights_mower.utils.config.os.replace", moved_elsewhere),
        ):
            migrate_app_config_paths()
        self.assertEqual(self.new.read_text(encoding="utf-8"), "legacy")

    def test_gui_pair_converges_to_config_dir(self):
        # gui 窗口尺寸配置与其余应用配置一起收敛到 @app/config/，旧 @app/gui.yml 纳入迁移
        pairs = dict(config_module._CONFIG_PATH_PAIRS)
        self.assertEqual(pairs[config_module._LEGACY_GUI_PATH], config_module.gui_path)
        self.assertEqual(config_module.gui_path.parent.name, "config")


class TestPersistFunctionsWriteThrough(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_save_conf_writes_atomic(self):
        target = self.dir / "conf.yml"
        # 固定一份带 webview 的配置，避免依赖测试环境 @app/config/conf.yml 的遗留内容
        with _patched_conf(target, Conf(webview={"port": 58000})):
            config_module.save_conf()
        self.assertTrue(target.is_file())
        self.assertIn("webview", target.read_text(encoding="utf-8"))
        leftovers = [p for p in self.dir.rglob(".*.tmp") if p.is_file()]
        self.assertEqual(leftovers, [])

    def test_save_plan_writes_atomic(self):
        target = self.dir / "plan.json"
        with patch.object(config_module, "plan_path", target):
            config_module.save_plan()
        self.assertTrue(target.is_file())
        json_text = target.read_text(encoding="utf-8")
        self.assertTrue(json_text.lstrip().startswith("{"))
        leftovers = [p for p in self.dir.rglob(".*.tmp") if p.is_file()]
        self.assertEqual(leftovers, [])

    def test_write_app_state_writes_atomic(self):
        import arknights_mower.utils.config.app_state as app_state_module

        target = self.dir / "state.json"
        with patch.object(app_state_module, "STATE_FILE", target):
            app_state_module.write_app_state({"active_weekly_plan": "默认"})
        self.assertTrue(target.is_file())
        self.assertEqual(
            target.read_text(encoding="utf-8"), '{\n  "active_weekly_plan": "默认"\n}'
        )

    def test_write_weekly_plans_writes_atomic(self):
        from arknights_mower.utils.config.weekly_plan_loader import WeeklyPlanManager

        target = self.dir / "weekly_plans.yml"
        manager = object.__new__(WeeklyPlanManager)
        with patch.object(WeeklyPlanManager, "WEEKLY_PLANS_FILE", target):
            manager._write_weekly_plans({"plans": {"默认": []}})
        self.assertTrue(target.is_file())
        leftovers = [p for p in self.dir.rglob(".*.tmp") if p.is_file()]
        self.assertEqual(leftovers, [])


class TestConfigPersistence(unittest.TestCase):
    """#258：save_conf 只写用户配置过的键 + 旧键→新键迁移钩子。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.conf_path = self.dir / "conf.yml"

    def _write_conf(self, text):
        self.conf_path.parent.mkdir(parents=True, exist_ok=True)
        self.conf_path.write_text(text, encoding="utf-8")

    def test_save_conf_writes_only_user_configured_keys(self):
        with _patched_conf(self.conf_path, Conf(medicine_expire_days=3)):
            config_module.save_conf()
        written = self.conf_path.read_text(encoding="utf-8")
        self.assertIn("medicine_expire_days", written)
        # 未配置的默认字段不落盘
        self.assertNotIn("expiring_medicine_on_weekend", written)
        self.assertNotIn("maa_eat_stone", written)
        self.assertNotIn("ap_fallback", written)

    def test_unconfigured_conf_serializes_without_injected_defaults(self):
        with _patched_conf(self.conf_path, Conf()):
            # 未配置任何字段 → 序列化结果为空，不注入任何默认值
            dumped = config_module.conf.model_dump(exclude_unset=True)
            config_module.save_conf()
        self.assertEqual(dumped, {})
        written = self.conf_path.read_text(encoding="utf-8")
        self.assertNotIn("maa_eat_stone", written)
        self.assertNotIn("webview", written)

    def test_medicine_expire_days_defaults_to_zero_when_unset(self):
        with _patched_conf(self.conf_path, Conf()):
            # 未配置 → 运行时默认 0（不使用过期理智药），且不被标记为已设置
            self.assertEqual(config_module.conf.medicine_expire_days, 0)
            self.assertNotIn(
                "medicine_expire_days", config_module.conf.model_fields_set
            )

    def test_medicine_expire_days_round_trips_when_configured(self):
        with _patched_conf(self.conf_path, Conf(medicine_expire_days=3)):
            self.assertEqual(config_module.conf.medicine_expire_days, 3)
            self.assertIn("medicine_expire_days", config_module.conf.model_fields_set)
            config_module.save_conf()
        written = self.conf_path.read_text(encoding="utf-8")
        self.assertIn("medicine_expire_days", written)

    @patch(
        "arknights_mower.utils.config.conf.get_server_time",
        return_value=datetime(2026, 11, 24),
    )
    def test_medicine_use_all_date_round_trips_and_can_be_cleared(self, _clock):
        day = "2026-11-24"
        with _patched_conf(self.conf_path, Conf(medicine_use_all_date=day)):
            config_module.save_conf()
            config_module.load_conf()
            self.assertEqual(config_module.conf.medicine_use_all_date, day)
            config_module.conf = config_module.conf.updated(
                {"medicine_use_all_date": None}
            )
            config_module.save_conf()
            config_module.load_conf()
            self.assertIsNone(config_module.conf.medicine_use_all_date)

    def test_past_medicine_date_is_cleared_at_the_game_day_boundary(self):
        previous = datetime(2026, 11, 24, 19, 59, 59, tzinfo=timezone.utc)
        reset = datetime(2026, 11, 24, 20, tzinfo=timezone.utc)
        day = "2026-11-24"
        future = "2026-11-25"
        with patch("arknights_mower.utils.datetime.datetime") as clock:
            clock.now.side_effect = previous.astimezone
            conf = Conf(medicine_use_all_date=day, medicine_expire_days=3)
            with _patched_conf(self.conf_path, conf):
                config_module.save_conf()
                before = self.conf_path.read_bytes()
                self.assertEqual(
                    workshop_config.read_user_config()["medicine_use_all_date"], day
                )

                clock.now.side_effect = reset.astimezone
                data = workshop_config.read_user_config()
                self.assertIsNone(data["medicine_use_all_date"])
                self.assertEqual(data["medicine_expire_days"], 3)
                self.assertEqual(self.conf_path.read_bytes(), before)
                self.assertEqual(
                    conf.updated(
                        {"medicine_use_all_date": future}
                    ).medicine_use_all_date,
                    future,
                )

                config_module.load_conf()
                self.assertIsNone(config_module.conf.medicine_use_all_date)
                config_module.save_conf()
                self.assertNotIn(day.encode(), self.conf_path.read_bytes())

    def test_medicine_use_all_date_rejects_invalid_or_noncanonical_values(self):
        for value in ("", "2026-02-29", "20261124", "2026-W48-2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Conf(medicine_use_all_date=value)

    def test_mall_and_fight_new_fields_default_without_injection(self):
        # #265：Mall/Fight 新字段未配置时用运行时默认值，且不被标记为已设置（不落盘）
        with _patched_conf(self.conf_path, Conf()):
            conf = config_module.conf
            self.assertFalse(conf.maa_mall_only_buy_discount)
            self.assertFalse(conf.maa_mall_reserve_max_credit)
            self.assertFalse(conf.maa_report_to_yituliu)
            self.assertEqual(conf.maa_yituliu_id, "")
            for field in (
                "maa_mall_only_buy_discount",
                "maa_mall_reserve_max_credit",
                "maa_report_to_yituliu",
                "maa_yituliu_id",
            ):
                self.assertNotIn(field, conf.model_fields_set)

    def test_mall_and_fight_new_fields_round_trip_when_configured(self):
        # 旧购物选项退役后不再落盘，作战上报设置继续保留。
        with _patched_conf(
            self.conf_path,
            Conf(
                maa_mall_only_buy_discount=True,
                maa_mall_reserve_max_credit=True,
                maa_report_to_yituliu=True,
                maa_yituliu_id="yituliu-abc",
            ),
        ):
            conf = config_module.conf
            self.assertFalse(conf.maa_mall_only_buy_discount)
            self.assertFalse(conf.maa_mall_reserve_max_credit)
            self.assertTrue(conf.maa_report_to_yituliu)
            self.assertEqual(conf.maa_yituliu_id, "yituliu-abc")
            config_module.save_conf()
        written = self.conf_path.read_text(encoding="utf-8")
        self.assertNotIn("maa_mall_only_buy_discount", written)
        self.assertNotIn("maa_mall_reserve_max_credit", written)
        self.assertIn("maa_report_to_yituliu", written)
        self.assertNotIn("yituliu-abc", written)
        self.assertEqual(
            read_credentials(conf_secrets_path(self.conf_path))["MOWER_MAA_YITULIU_ID"],
            "yituliu-abc",
        )
        # 未配置的默认字段仍不落盘
        self.assertNotIn("maa_eat_stone", written)

    def test_legacy_credentials_and_rescue_plan_migrate_on_first_load(self):
        legacy = {
            "theme": "dark",
            "account": "sender@example.test",
            "pass_code": 'quoted " secret \\ $(example) # value\n第二行',
            "recipient": ["recipient@example.test"],
            "webview": {"token": "remote-test-secret", "port": 58009},
            "maa_mirrorchyan_token": "mirror-test-secret",
            "maa_penguin_id": "penguin-test-identifier",
            "ai_key": "deepseek-test-secret",
            "ai_custom_key": "custom-test-secret",
            "ai_base_url": "https://relay.example.test/?key=embedded-test-secret",
            "skland_info": [
                {"account": "skland-test-user", "password": "skland-test-secret"}
            ],
            "automatic_rescue_plan": {},
        }
        self.conf_path.write_text(yaml.safe_dump(legacy), encoding="utf-8")
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            self.assertEqual(config_module.conf.pass_code, legacy["pass_code"])
            self.assertEqual(config_module.conf.webview.token, "remote-test-secret")
            self.assertEqual(
                config_module.conf.skland_info[0].password, "skland-test-secret"
            )
            self.assertTrue(config_module.rescue_plan_path.is_file())
            clean = yaml.safe_load(self.conf_path.read_text(encoding="utf-8"))
            self.assertEqual(clean, {"theme": "dark", "webview": {"port": 58009}})
            env = read_credentials(conf_secrets_path(self.conf_path))
            self.assertEqual(env["MOWER_MAIL_RECIPIENTS"], ["recipient@example.test"])
            self.assertEqual(env["MOWER_AI_KEY"], "deepseek-test-secret")
            config_module.conf = config_module.conf.updated({"ai_custom_key": ""})
            config_module.save_conf()
            config_module.load_conf()
            self.assertEqual(config_module.conf.ai_custom_key, "")
            self.assertEqual(config_module.conf.webview.token, "remote-test-secret")
            self.assertEqual(config_module.conf.pass_code, legacy["pass_code"])
            self.assertEqual(config_module.conf.ai_base_url, legacy["ai_base_url"])

    def test_launch_environment_bootstraps_new_values_and_ui_can_clear_them(self):
        with (
            _patched_conf(self.conf_path),
            patch.dict(os.environ, {"MOWER_AI_KEY": "launch-secret"}),
        ):
            config_module.load_conf()
            self.assertEqual(config_module.conf.ai_key, "launch-secret")
            config_module.conf = config_module.conf.updated({"ai_key": ""})
            config_module.save_conf()
            config_module.load_conf()
            self.assertEqual(config_module.conf.ai_key, "")
            self.assertNotIn(
                "launch-secret", self.conf_path.read_text(encoding="utf-8")
            )

    def test_old_root_conf_credentials_are_available_when_legacy_conf_is_recovered(
        self,
    ):
        canonical = self.dir / "config" / "conf.yml"
        canonical.parent.mkdir()
        canonical.write_text("webview: {token: current-value}\n", encoding="utf-8")
        self._write_conf("webview: {token: legacy-value, port: 58001}\n")
        with (
            _patched_conf(canonical),
            patch.object(config_module, "_LEGACY_CONF_PATH", self.conf_path),
            patch.object(
                config_module, "_CONFIG_PATH_PAIRS", ((self.conf_path, canonical),)
            ),
        ):
            config_module.load_conf()
            config_module._migrate_unused_legacy_credentials()
            self.assertEqual(config_module.conf.webview.token, "current-value")
            self.assertEqual(
                yaml.safe_load(self.conf_path.read_text(encoding="utf-8")),
                {"webview": {"port": 58001}},
            )
            self.assertEqual(
                read_credentials(legacy_conf_secrets_path(canonical))[
                    "MOWER_WEBVIEW_TOKEN"
                ],
                "legacy-value",
            )
            canonical.unlink()
            conf_secrets_path(canonical).unlink()
            migrate_app_config_paths()
            config_module.load_conf()
            self.assertEqual(config_module.conf.webview.token, "legacy-value")

    def test_yaml_write_failure_reverts_an_explicit_token_change(self):
        with _patched_conf(self.conf_path, Conf(webview={"token": "first"})):
            config_module.save_conf()
            config_module.conf = config_module.conf.updated(
                {"webview": {"token": "second"}}
            )
            with patch.object(
                config_module, "atomic_write", side_effect=OSError("write failed")
            ):
                with self.assertRaises(OSError):
                    config_module.save_conf()
            config_module.load_conf()
            self.assertEqual(config_module.conf.webview.token, "first")

    def test_legacy_yaml_recovery_preserves_existing_active_credential_map(self):
        canonical = self.dir / "config" / "conf.yml"
        canonical.parent.mkdir()
        self._write_conf("webview: {port: 58001}\n")
        encrypted = conf_secrets_path(canonical)
        credential_store.write_credentials(encrypted, {})
        credential_store.write_credentials(
            legacy_conf_secrets_path(canonical),
            {
                "MOWER_WEBVIEW_TOKEN": "retired-token",
                "MOWER_MAIL_PASSWORD": "retired-password",
            },
        )
        original = encrypted.read_bytes()
        with (
            _patched_conf(canonical),
            patch.object(config_module, "_LEGACY_CONF_PATH", self.conf_path),
            patch.object(
                config_module, "_CONFIG_PATH_PAIRS", ((self.conf_path, canonical),)
            ),
            patch.dict(os.environ, {"MOWER_MANAGED": "1"}),
        ):
            migrate_app_config_paths()
            config_module.load_conf()
            self.assertEqual(config_module.conf.webview.token, "")
            self.assertEqual(config_module.conf.pass_code, "")
            self.assertEqual(config_module.conf.webview.port, 58001)
        self.assertEqual(encrypted.read_bytes(), original)
        self.assertEqual(read_credentials(encrypted), {})

    def test_failed_credential_readback_restores_exact_files(self):
        with _patched_conf(
            self.conf_path,
            Conf(theme="dark", pass_code="mail-original", webview={"token": "first"}),
        ):
            config_module.save_conf()
            encrypted = conf_secrets_path(self.conf_path)
            originals = {
                path: path.read_bytes() for path in (encrypted, self.conf_path)
            }
            config_module.conf = config_module.conf.updated(
                {
                    "theme": "light",
                    "pass_code": "changed",
                    "webview": {"token": "second"},
                }
            )
            atomic_bytes = credential_store._atomic_bytes
            corrupted = False

            def corrupt_once(path, raw):
                nonlocal corrupted
                if path == encrypted and not corrupted:
                    corrupted = True
                    raw = b"damaged after persistence"
                atomic_bytes(path, raw)

            with patch.object(credential_store, "_atomic_bytes", corrupt_once):
                with self.assertRaises(credential_store.CredentialStoreError):
                    config_module.save_conf()
            self.assertTrue(corrupted)
            self.assertEqual({path: path.read_bytes() for path in originals}, originals)
            config_module.load_conf()
            self.assertEqual(config_module.conf.webview.token, "first")
            self.assertEqual(config_module.conf.pass_code, "mail-original")
            self.assertEqual(config_module.conf.theme, "dark")

    def test_missing_key_load_and_save_preserve_access_token_and_files(self):
        key = self.dir / "private.key"
        key.write_bytes(base64.urlsafe_b64encode(os.urandom(96)))
        key.chmod(0o600)
        with (
            patch.dict(os.environ, {"MOWER_CREDENTIAL_KEY_FILE": str(key)}),
            _patched_conf(self.conf_path, Conf(webview={"token": "protected-token"})),
        ):
            config_module.save_conf()
            loaded = config_module.conf
            originals = {
                path: path.read_bytes()
                for path in (self.conf_path, conf_secrets_path(self.conf_path))
            }
            key.unlink()
            for operation in (config_module.load_conf, config_module.save_conf):
                with self.subTest(operation=operation.__name__):
                    with self.assertRaises(credential_store.CredentialStoreError):
                        operation()
                    self.assertIs(config_module.conf, loaded)
                    self.assertEqual(
                        config_module.conf.webview.token, "protected-token"
                    )
                    self.assertEqual(
                        {path: path.read_bytes() for path in originals}, originals
                    )
                    self.assertFalse(key.exists())

    def test_empty_encrypted_store_does_not_restore_stale_yaml_credentials(self):
        self._write_conf(
            "theme: dark\npass_code: obsolete-password\n"
            "webview: {token: obsolete-token, port: 58001}\n"
        )
        encrypted = conf_secrets_path(self.conf_path)
        credential_store.write_credentials(encrypted, {})
        with (
            _patched_conf(self.conf_path),
            patch.dict(os.environ, {"MOWER_MANAGED": "1"}),
        ):
            config_module.load_conf()
            self.assertEqual(config_module.conf.webview.token, "")
            self.assertEqual(config_module.conf.webview.port, 58001)
            self.assertEqual(config_module.conf.pass_code, "")
            self.assertEqual(config_module.conf.theme, "dark")
        self.assertEqual(read_credentials(encrypted), {})
        self.assertEqual(
            yaml.safe_load(self.conf_path.read_text(encoding="utf-8")),
            {"theme": "dark", "webview": {"port": 58001}},
        )

    def test_manager_uses_per_instance_secrets_instead_of_launch_defaults(self):
        with (
            _patched_conf(self.conf_path),
            patch.dict(
                os.environ,
                {"MOWER_MANAGED": "1", "MOWER_WEBVIEW_TOKEN": "ambient-secret"},
            ),
        ):
            config_module.load_conf()
            self.assertEqual(config_module.conf.webview.token, "")
            config_module.conf = config_module.conf.updated(
                {"webview": {"token": "instance-secret"}}
            )
            config_module.save_conf()
            config_module.load_conf()
            self.assertEqual(config_module.conf.webview.token, "instance-secret")

    def test_fallback_ai_key_migration_respects_explicit_data_directory(self):
        data = self.dir / "custom-data"
        data.mkdir()
        external = self.dir / "token.txt"
        external.write_text("installed-key", encoding="utf-8")
        local = data / "token.txt"
        local.write_text("local-key", encoding="utf-8")
        env = data / "ai.secrets.json"
        with (
            patch.dict(os.environ, {"MOWER_DATA_DIR": str(data)}),
            patch.object(
                configuration_secrets, "__rootdir__", self.dir / "arknights_mower"
            ),
            patch.object(configuration_secrets, "get_path", return_value=env),
        ):
            configuration_secrets.migrate_fallback_ai_key()
            self.assertEqual(configuration_secrets.fallback_ai_key(), "local-key")
        self.assertEqual(external.read_text(encoding="utf-8"), "installed-key")
        self.assertEqual(read_credentials(env), {"MOWER_AI_FALLBACK_KEY": "local-key"})
        self.assertFalse(local.exists())

    def test_rogue_new_fields_default_without_injection(self):
        # #264：Roguelike 通用字段未配置时用协议默认值，且不被标记为已设置（不落盘）
        with _patched_conf(self.conf_path, Conf()):
            rogue = config_module.conf.rogue
            self.assertEqual(rogue.difficulty, -1)
            self.assertFalse(rogue.stop_at_final_boss)
            self.assertFalse(rogue.stop_at_max_level)
            self.assertTrue(rogue.investment_enabled)
            self.assertFalse(rogue.stop_when_investment_full)
            self.assertFalse(rogue.investment_with_more_score)
            self.assertFalse(rogue.collectible_mode_shopping)
            self.assertEqual(rogue.collectible_mode_squad, "")
            self.assertFalse(rogue.start_with_elite_two)
            self.assertFalse(rogue.only_start_with_elite_two)
            self.assertEqual(rogue.collectible_mode_start_list, {})
            self.assertEqual(
                rogue.expected_collapsal_paradigms,
                ["目空一些", "睁眼瞎", "图像损坏", "一抹黑"],
            )
            config_module.save_conf()
        written = self.conf_path.read_text(encoding="utf-8")
        for field in (
            "difficulty",
            "stop_at_final_boss",
            "investment_enabled",
            "expected_collapsal_paradigms",
        ):
            self.assertNotIn(field, written)

    def test_rogue_new_fields_round_trip_when_configured(self):
        # #264：Roguelike 通用字段配置后如实读回并落盘（collectible_mode_squad 默认与 squad 同步）
        with _patched_conf(
            self.conf_path,
            Conf(
                rogue={
                    "difficulty": 2,
                    "stop_at_final_boss": True,
                    "stop_at_max_level": True,
                    "investment_enabled": False,
                    "stop_when_investment_full": True,
                    "investment_with_more_score": True,
                    "collectible_mode_shopping": True,
                    "collectible_mode_squad": "指挥分队",
                    "start_with_elite_two": True,
                    "only_start_with_elite_two": True,
                    "collectible_mode_start_list": {"hot_water": True},
                    "expected_collapsal_paradigms": ["目空一些", "一抹黑"],
                }
            ),
        ):
            rogue = config_module.conf.rogue
            self.assertEqual(rogue.difficulty, 2)
            self.assertTrue(rogue.stop_at_final_boss)
            self.assertTrue(rogue.stop_at_max_level)
            self.assertFalse(rogue.investment_enabled)
            self.assertTrue(rogue.stop_when_investment_full)
            self.assertTrue(rogue.investment_with_more_score)
            self.assertTrue(rogue.collectible_mode_shopping)
            self.assertEqual(rogue.collectible_mode_squad, "指挥分队")
            self.assertTrue(rogue.start_with_elite_two)
            self.assertTrue(rogue.only_start_with_elite_two)
            self.assertEqual(rogue.collectible_mode_start_list, {"hot_water": True})
            self.assertEqual(rogue.expected_collapsal_paradigms, ["目空一些", "一抹黑"])
            config_module.save_conf()
        written = self.conf_path.read_text(encoding="utf-8")
        self.assertIn("difficulty", written)
        self.assertIn("stop_at_final_boss", written)
        self.assertIn("collectible_mode_squad", written)
        self.assertIn("start_with_elite_two", written)
        self.assertIn("only_start_with_elite_two", written)
        self.assertIn("collectible_mode_start_list", written)
        self.assertIn("expected_collapsal_paradigms", written)
        self.assertIn("investment_with_more_score", written)

    def test_retired_weekend_keys_are_ignored_on_read_and_save(self):
        for key in ("exipring_medicine_on_weekend", "expiring_medicine_on_weekend"):
            for days in (0, 3):
                with self.subTest(key=key, days=days):
                    self._write_conf(f"{key}: true\nmedicine_expire_days: {days}\n")
                    with _patched_conf(self.conf_path):
                        config_module.load_conf()
                        self.assertEqual(config_module.conf.medicine_expire_days, days)
                        self.assertNotIn(key, config_module.conf.model_fields_set)
                        self.assertNotIn(key, config_module.conf.model_dump())
                        config_module.save_conf()
                        config_module.load_conf()
                        self.assertEqual(config_module.conf.medicine_expire_days, days)
                    self.assertNotIn("medicine_on_weekend", self.conf_path.read_text())

    def test_retired_weekend_keys_are_ignored_on_submission(self):
        for payload in (
            {"exipring_medicine_on_weekend": True},
            {"expiring_medicine_on_weekend": True},
            {
                "exipring_medicine_on_weekend": True,
                "expiring_medicine_on_weekend": False,
            },
        ):
            with self.subTest(payload=payload):
                conf = Conf(medicine_expire_days=3, **payload)
                updated = conf.updated({**payload, "medicine_expire_days": 2})
                self.assertEqual(updated.medicine_expire_days, 2)
                for key in payload:
                    self.assertNotIn(key, updated.model_dump())
                    self.assertNotIn(key, updated.model_fields_set)

    def test_visit_friend_defaults_enable_true_and_mode_mower_when_unset(self):
        with _patched_conf(self.conf_path, Conf()):
            # 未配置 → 默认开启且交 Mower（visit_friend_mode=mower），且都不被标记为已设置
            self.assertTrue(config_module.conf.visit_friend_enable)
            self.assertEqual(config_module.conf.visit_friend_mode, "mower")
            self.assertNotIn("visit_friend_enable", config_module.conf.model_fields_set)
            self.assertNotIn("visit_friend_mode", config_module.conf.model_fields_set)

    def test_visit_friend_round_trips_when_configured(self):
        with _patched_conf(
            self.conf_path, Conf(visit_friend_enable=False, visit_friend_mode="mower")
        ):
            self.assertFalse(config_module.conf.visit_friend_enable)
            self.assertEqual(config_module.conf.visit_friend_mode, "mower")
            self.assertIn("visit_friend_enable", config_module.conf.model_fields_set)
            config_module.save_conf()
        written = self.conf_path.read_text(encoding="utf-8")
        self.assertIn("visit_friend_enable", written)
        self.assertNotIn("visit_friend_mode", written)

    def test_legacy_visit_friend_true_migrates_to_enable_true_and_mower(self):
        # `visit_friend: true`（原语义：mower 原生访问好友）迁移为 visit_friend_enable=true，
        # 并保留 mode=mower，避免非 MAA 用户在迁移后静默失去访问好友
        self._write_conf("visit_friend: true\n")
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            self.assertTrue(config_module.conf.visit_friend_enable)
            self.assertEqual(config_module.conf.visit_friend_mode, "mower")
            self.assertIn("visit_friend_enable", config_module.conf.model_fields_set)
            config_module.save_conf()
        written = self.conf_path.read_text(encoding="utf-8")
        self.assertIn("visit_friend_enable", written)
        self.assertNotIn("visit_friend_mode", written)
        self.assertNotIn("visit_friend:", written)

    def test_legacy_visit_friend_false_migrates_to_enable_false(self):
        # `visit_friend: false`（用户显式关闭访问好友）迁移为 visit_friend_enable=false
        self._write_conf("visit_friend: false\n")
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            self.assertFalse(config_module.conf.visit_friend_enable)

    def test_legacy_visit_friend_not_migrated_when_absent(self):
        self._write_conf("maa_eat_stone: false\n")
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            # 没配过旧键：新键用运行时默认（enable=true、mode=mower），且不被标记为已设置
            self.assertTrue(config_module.conf.visit_friend_enable)
            self.assertEqual(config_module.conf.visit_friend_mode, "mower")
            self.assertNotIn("visit_friend_enable", config_module.conf.model_fields_set)

    def test_new_visit_friend_enable_takes_precedence_when_both_present(self):
        self._write_conf("visit_friend: true\nvisit_friend_enable: false\n")
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            # 新旧键同时出现时以新键为准，不覆盖已配置的值
            self.assertFalse(config_module.conf.visit_friend_enable)

    def test_migrated_visit_friend_survives_round_trip(self):
        self._write_conf("visit_friend: true\n")
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            config_module.save_conf()
            config_module.load_conf()
            self.assertTrue(config_module.conf.visit_friend_enable)
            self.assertEqual(config_module.conf.visit_friend_mode, "mower")

    def test_conf_post_with_legacy_visit_friend_reconciles(self):
        # 兼容：/conf POST 提交旧键名（旧前端整包）时，Conf 校验层统一迁移，不把新键重置成默认。
        with _patched_conf(self.conf_path):
            config_module.conf = config_module.Conf(**{"visit_friend": True})
            self.assertTrue(config_module.conf.visit_friend_enable)
            self.assertEqual(config_module.conf.visit_friend_mode, "mower")
            self.assertIn("visit_friend_enable", config_module.conf.model_fields_set)

    def test_stage_plan_and_mall_defaults(self):
        conf = config_module.Conf()
        self.assertTrue(conf.stage_plan_enable)
        self.assertEqual(conf.stage_plan_runner, "maa")
        self.assertTrue(conf.maa_mall_enable)
        self.assertEqual(conf.maa_mall_mode, "mower")

    def test_legacy_maa_enable_true_migrates(self):
        self._write_conf("maa_enable: true\n")
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            self.assertTrue(config_module.conf.stage_plan_enable)
            self.assertEqual(config_module.conf.stage_plan_runner, "maa")
            self.assertTrue(config_module.conf.maa_mall_enable)
            self.assertEqual(config_module.conf.maa_mall_mode, "mower")

    def test_legacy_maa_enable_false_migrates(self):
        self._write_conf("maa_enable: false\n")
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            self.assertFalse(config_module.conf.stage_plan_enable)
            self.assertEqual(config_module.conf.stage_plan_runner, "mower")
            self.assertFalse(config_module.conf.maa_mall_enable)
            self.assertEqual(config_module.conf.maa_mall_mode, "mower")

    def test_new_stage_plan_takes_precedence_when_both_present(self):
        self._write_conf(
            "maa_enable: false\nstage_plan_enable: true\nstage_plan_runner: mower\nmaa_mall_enable: true\nmaa_mall_mode: mower\n"
        )
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            self.assertTrue(config_module.conf.stage_plan_enable)
            self.assertEqual(config_module.conf.stage_plan_runner, "mower")
            self.assertTrue(config_module.conf.maa_mall_enable)
            self.assertEqual(config_module.conf.maa_mall_mode, "mower")

    def test_migrated_stage_plan_survives_round_trip(self):
        self._write_conf(
            "stage_plan_enable: false\nstage_plan_runner: mower\nmaa_mall_enable: true\nmaa_mall_mode: mower\n"
        )
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            config_module.save_conf()
            config_module.load_conf()
            self.assertFalse(config_module.conf.stage_plan_enable)
            self.assertEqual(config_module.conf.stage_plan_runner, "mower")
            self.assertTrue(config_module.conf.maa_mall_enable)
            self.assertEqual(config_module.conf.maa_mall_mode, "mower")


if __name__ == "__main__":
    unittest.main()
