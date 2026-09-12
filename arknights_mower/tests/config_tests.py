import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils import config as config_module
from arknights_mower.utils.config import atomic_write, migrate_app_config_paths
from arknights_mower.utils.config.conf import Conf


@contextmanager
def _patched_conf(path, conf=None):
    """临时切到 path 与 conf 下读取/写配置，结束后还原模块级 conf。

    #258 之后 save_conf 只写用户配置过的键，测试须用固定的 path/conf 隔离环境里的
    @app/config/conf.yml，避免依赖残留内容。
    """
    original = config_module.conf
    try:
        with patch.object(config_module, "conf_path", path):
            if conf is not None:
                config_module.conf = conf
            yield
    finally:
        config_module.conf = original


class TestMaaConfig(unittest.TestCase):
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
            with patch("sys.platform", "linux"):
                which.return_value = "/usr/bin/adb"
                self.assertEqual(Conf().maa_adb_path, "/usr/bin/adb")
                with patch.dict(os.environ, {"MOWER_ADB_BIN": "/custom/adb"}):
                    self.assertEqual(Conf().maa_adb_path, "/custom/adb")
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
        conf = Conf(hot_update={"enable": False, "auto_update": True})
        self.assertTrue(conf.hot_update.enable)
        self.assertTrue(conf.hot_update.auto_update)
        restored = Conf(**conf.model_dump())
        self.assertTrue(restored.hot_update.enable)
        self.assertTrue(restored.hot_update.auto_update)


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
        # #265：四个新字段配置后如实读回并落盘
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
            self.assertTrue(conf.maa_mall_only_buy_discount)
            self.assertTrue(conf.maa_mall_reserve_max_credit)
            self.assertTrue(conf.maa_report_to_yituliu)
            self.assertEqual(conf.maa_yituliu_id, "yituliu-abc")
            config_module.save_conf()
        written = self.conf_path.read_text(encoding="utf-8")
        self.assertIn("maa_mall_only_buy_discount", written)
        self.assertIn("maa_mall_reserve_max_credit", written)
        self.assertIn("maa_report_to_yituliu", written)
        self.assertIn("maa_yituliu_id", written)
        # 未配置的默认字段仍不落盘
        self.assertNotIn("maa_eat_stone", written)

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

    def test_legacy_key_migrates_to_new_key_when_configured(self):
        self._write_conf("exipring_medicine_on_weekend: true\n")
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            self.assertTrue(config_module.conf.expiring_medicine_on_weekend)
            self.assertIn(
                "expiring_medicine_on_weekend",
                config_module.conf.model_fields_set,
            )
            config_module.save_conf()
        written = self.conf_path.read_text(encoding="utf-8")
        self.assertIn("expiring_medicine_on_weekend", written)
        self.assertNotIn("exipring_medicine_on_weekend", written)

    def test_legacy_key_not_migrated_when_absent(self):
        self._write_conf("maa_eat_stone: false\n")
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            # 没配过旧键：新键用运行时默认值，且不被标记为已设置（因此不落盘）
            self.assertFalse(config_module.conf.expiring_medicine_on_weekend)
            self.assertNotIn(
                "expiring_medicine_on_weekend",
                config_module.conf.model_fields_set,
            )

    def test_new_key_takes_precedence_when_legacy_and_new_both_present(self):
        self._write_conf(
            "exipring_medicine_on_weekend: true\nexpiring_medicine_on_weekend: false\n"
        )
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            # 新旧键同时出现时以新键为准，不覆盖已配置的取反值
            self.assertFalse(config_module.conf.expiring_medicine_on_weekend)

    def test_migrated_value_survives_round_trip(self):
        self._write_conf("exipring_medicine_on_weekend: true\n")
        with _patched_conf(self.conf_path):
            config_module.load_conf()
            config_module.save_conf()
            config_module.load_conf()
            self.assertTrue(config_module.conf.expiring_medicine_on_weekend)

    def test_conf_post_with_legacy_key_reconciles_at_validation_layer(self):
        # 兼容：/conf POST 提交旧键名（旧前端整包）时，Conf 校验层统一迁移，不把新键重置成默认。
        # 旧迁移只在 load_conf（读文件）执行，/conf 提交会绕过——此测锁定那条路径。
        with _patched_conf(self.conf_path):
            # 模拟旧前端整包提交：请求体带旧键名、不带新键名
            config_module.conf = config_module.Conf(
                **{"exipring_medicine_on_weekend": True}
            )
            self.assertTrue(config_module.conf.expiring_medicine_on_weekend)
            self.assertIn(
                "expiring_medicine_on_weekend",
                config_module.conf.model_fields_set,
            )
            config_module.save_conf()
        written = self.conf_path.read_text(encoding="utf-8")
        self.assertIn("expiring_medicine_on_weekend", written)
        self.assertNotIn("exipring_medicine_on_weekend", written)

    def test_visit_friend_defaults_enable_true_and_mode_maa_when_unset(self):
        with _patched_conf(self.conf_path, Conf()):
            # 未配置 → 默认开启且交 MAA（visit_friend_mode=maa），且都不被标记为已设置
            self.assertTrue(config_module.conf.visit_friend_enable)
            self.assertEqual(config_module.conf.visit_friend_mode, "maa")
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
        self.assertIn("visit_friend_mode", written)

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
        self.assertIn("visit_friend_mode", written)
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
            # 没配过旧键：新键用运行时默认（enable=true、mode=maa），且不被标记为已设置
            self.assertTrue(config_module.conf.visit_friend_enable)
            self.assertEqual(config_module.conf.visit_friend_mode, "maa")
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


if __name__ == "__main__":
    unittest.main()
