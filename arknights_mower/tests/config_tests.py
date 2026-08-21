import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils import config as config_module
from arknights_mower.utils.config import atomic_write, migrate_app_config_paths


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

    def test_migration_failure_keeps_old_file_and_does_not_crash(self):
        # Windows 上 os.replace 失败（锁住/TOCTOU）→ 跳过保留旧文件，不拖垮 import
        old = self.dir / "conf.yml"
        new = self.dir / "config" / "conf.yml"
        old.write_text("legacy", encoding="utf-8")

        def boom(*args, **kwargs):
            raise PermissionError("locked")

        with (
            patch.object(config_module, "_CONFIG_PATH_PAIRS", [(old, new)]),
            patch("arknights_mower.utils.config.os.replace", boom),
        ):
            migrate_app_config_paths()
        self.assertTrue(old.exists())
        self.assertFalse(new.exists())


class TestPersistFunctionsWriteThrough(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_save_conf_writes_atomic(self):
        target = self.dir / "conf.yml"
        with patch.object(config_module, "conf_path", target):
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


if __name__ == "__main__":
    unittest.main()
