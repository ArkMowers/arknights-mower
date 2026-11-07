"""按来源模块派生实时日志分组的离线测试。"""

import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils import log, log_groups
from arknights_mower.utils.log_groups import (
    BUSINESS_GROUP_OWNERS,
    LOG_GROUP_PREFIXES,
    group_for_pathname,
)

PACKAGE_ROOT = r"D:\repo\arknights-mower-fix"
PACKAGE = PACKAGE_ROOT + r"\arknights_mower"


def make_record(pathname, message="消息", level=logging.INFO):
    record = logging.LogRecord(
        "arknights_mower.test", level, pathname, 10, message, (), None
    )
    # Handler.emit 依赖 formatter 已写好的 asctime，这里直接构造记录。
    record.asctime = "2026-11-02 12:00:00,000"
    return record


class GroupForPathnameTest(unittest.TestCase):
    def test_known_modules_map_to_their_subsystem(self):
        cases = (
            (PACKAGE + r"\solvers\base_schedule.py", "base-scheduler"),
            (PACKAGE + r"\solvers\emergency.py", "base-scheduler"),
            (PACKAGE + r"\solvers\base_mixin.py", "base-scheduler"),
            (PACKAGE + r"\utils\scheduler_task.py", "base-scheduler"),
            (PACKAGE + r"\utils\calculated_mood.py", "base-scheduler"),
            (PACKAGE + r"\solvers\report.py", "base-scheduler"),
            (PACKAGE + r"\solvers\trust_rotation.py", "base-scheduler"),
            (PACKAGE + r"\solvers\clue_credit.py", "clue"),
            (PACKAGE + r"\solvers\clue_gift.py", "clue"),
            (PACKAGE + r"\solvers\operation.py", "local-operation"),
            (PACKAGE + r"\solvers\player_info.py", "local-operation"),
            (PACKAGE + r"\solvers\local_operation.py", "local-operation"),
            (PACKAGE + r"\solvers\mail.py", "local-operation"),
            (PACKAGE + r"\solvers\event_sign_in.py", "local-operation"),
            (PACKAGE + r"\solvers\credit.py", "local-operation"),
            (PACKAGE + r"\solvers\shop.py", "credit-shop"),
            (PACKAGE + r"\solvers\credit_fight.py", "local-operation"),
            (PACKAGE + r"\solvers\mission.py", "local-operation"),
            (PACKAGE + r"\solvers\skland.py", "local-operation"),
            (PACKAGE + r"\solvers\cultivate_depot.py", "growth-planning"),
            (PACKAGE + r"\utils\recognize.py", "recognition"),
            (PACKAGE + r"\utils\rapidocr.py", "recognition"),
            (PACKAGE + r"\utils\scene.py", "recognition"),
            (PACKAGE + r"\utils\graph.py", "recognition"),
            (PACKAGE + r"\utils\matcher.py", "recognition"),
            (PACKAGE + r"\utils\solver.py", "recognition"),
            (PACKAGE + r"\utils\run_order_network.py", "recognition"),
            (PACKAGE + r"\utils\network_adaptation.py", "recognition"),
            (PACKAGE + r"\utils\device\device.py", "device-control"),
            (PACKAGE + r"\utils\device\adb_client\session.py", "device-control"),
            (PACKAGE + r"\utils\manager_common.py", "device-control"),
            (PACKAGE + r"\utils\screenshot.py", "device-control"),
            (PACKAGE + r"\solvers\recruit.py", "recruitment"),
            (PACKAGE + r"\solvers\depotREC.py", "depot-recognition"),
            (PACKAGE + r"\utils\resource_ota.py", "resource-update"),
            (PACKAGE + r"\utils\resource_pkg.py", "resource-update"),
            (PACKAGE + r"\utils\resource_store.py", "resource-update"),
            (PACKAGE + r"\utils\resource_update_job.py", "resource-update"),
            (PACKAGE + r"\utils\resource_version.py", "resource-update"),
            (PACKAGE + r"\utils\res_version.py", "resource-update"),
            (PACKAGE + r"\utils\manual_update.py", "resource-update"),
            (PACKAGE + r"\utils\software_update.py", "software-update"),
            (PACKAGE + r"\utils\software_update_worker.py", "software-update"),
            (PACKAGE + r"\utils\update.py", "software-update"),
            (PACKAGE + r"\utils\update_notice.py", "software-update"),
            (PACKAGE + r"\utils\update_runtime.py", "software-update"),
            (PACKAGE + r"\utils\github_download.py", "software-update"),
            (PACKAGE + r"\utils\maa_update.py", "software-update"),
            (PACKAGE + r"\utils\maa_resource_update.py", "software-update"),
            (PACKAGE + r"\utils\maa_runtime.py", "maa-runtime"),
            (PACKAGE + r"\utils\maa_process.py", "maa-runtime"),
            (PACKAGE + r"\utils\maa_backup.py", "maa-runtime"),
            (PACKAGE + r"\utils\maa_check.py", "maa-runtime"),
            (PACKAGE + r"\utils\maa_callback.py", "maa-integration"),
            (PACKAGE + r"\utils\maa_report.py", "maa-integration"),
            (PACKAGE + r"\utils\maa_copilot.py", "maa-integration"),
            (PACKAGE + r"\utils\maa_sss.py", "maa-integration"),
            (PACKAGE + r"\utils\maa_stage_inventory.py", "maa-integration"),
            (PACKAGE + r"\utils\maa_inventory.py", "maa-integration"),
            (PACKAGE + r"\utils\maa_event_shop.py", "maa-integration"),
            (PACKAGE + r"\utils\web_auth.py", "web-access"),
            (PACKAGE + r"\utils\log_stream.py", "web-access"),
            (PACKAGE_ROOT + r"\server.py", "web-access"),
            (PACKAGE_ROOT + r"\webview_ui.py", "web-access"),
            (PACKAGE + r"\agent\tools\faq.py", "ai-assistant"),
        )
        for pathname, expected in cases:
            with self.subTest(pathname=pathname):
                self.assertEqual(group_for_pathname(pathname), expected)

    def test_already_relative_package_paths_match(self):
        self.assertEqual(
            group_for_pathname("solvers/base_schedule.py"), "base-scheduler"
        )
        self.assertEqual(group_for_pathname("utils/device/device.py"), "device-control")

    def test_posix_paths_match_the_same_modules(self):
        self.assertEqual(
            group_for_pathname("/srv/mower/arknights_mower/utils/graph.py"),
            "recognition",
        )
        self.assertEqual(
            group_for_pathname("/srv/mower/arknights_mower/utils/device/device.py"),
            "device-control",
        )
        self.assertEqual(group_for_pathname("/srv/mower/server.py"), "web-access")

    def test_unknown_modules_have_no_group(self):
        for pathname in (
            "",
            None,
            r"D:\repo\tools\build_assets.py",
            r"D:\repo\arknights_mower\tests\log_tests.py",
            "/tmp/script.py",
            PACKAGE + r"\__main__.py",
            "/srv/mower/arknights_mower/__main__.py",
            "__main__.py",
        ):
            with self.subTest(pathname=pathname):
                self.assertIsNone(group_for_pathname(pathname))

    def test_every_table_entry_resolves_to_its_group(self):
        for prefix, group in LOG_GROUP_PREFIXES:
            if "/" in prefix:
                pathname = PACKAGE + "\\" + prefix.replace("/", "\\")
            else:
                # 仓库根目录的入口模块按文件名匹配。
                pathname = PACKAGE_ROOT + "\\" + prefix
            with self.subTest(prefix=prefix):
                self.assertEqual(group_for_pathname(pathname), group)

    def test_match_order_checks_longest_prefix_first(self):
        lengths = [len(prefix) for prefix, _ in log_groups._ORDERED_PREFIXES]
        self.assertEqual(lengths, sorted(lengths, reverse=True))

    def test_groups_have_governing_subsystem_documents(self):
        docs = Path(__file__).resolve().parents[2] / "docs" / "subsystems"
        for group in {group for _, group in LOG_GROUP_PREFIXES}:
            with self.subTest(group=group):
                owner = BUSINESS_GROUP_OWNERS.get(group, group)
                self.assertTrue((docs / f"{owner}.md").is_file())


class PackagePathFilterGroupAttributeTest(unittest.TestCase):
    def test_filter_writes_prefix_and_keeps_caller_group_raw(self):
        record = make_record(PACKAGE + r"\solvers\base_schedule.py")
        record.log_group = "base-scheduler"
        self.assertTrue(log.filter.filter(record))
        self.assertEqual(record.log_group, "base-scheduler")
        self.assertEqual(record.log_group_prefix, "base-scheduler ")

    def test_filter_sets_empty_prefix_without_caller_group(self):
        record = make_record(PACKAGE + r"\solvers\base_schedule.py")
        self.assertTrue(log.filter.filter(record))
        self.assertFalse(hasattr(record, "log_group"))
        self.assertEqual(record.log_group_prefix, "")


class BuildLogRecordGroupTest(unittest.TestCase):
    def test_derives_group_from_source_module(self):
        record = make_record(PACKAGE + r"\solvers\base_schedule.py")
        rec = log._build_log_record(record, "安排干员")
        self.assertEqual(rec["group"], "base-scheduler")
        self.assertFalse(rec["group"].endswith(" "))

    def test_explicit_extra_group_wins_over_derivation(self):
        record = make_record(PACKAGE + r"\solvers\base_schedule.py")
        record.log_group = "recognition"
        rec = log._build_log_record(record, "消息")
        self.assertEqual(rec["group"], "recognition")

    def test_explicit_extra_group_is_trimmed(self):
        record = make_record(PACKAGE + r"\solvers\base_schedule.py")
        record.log_group = "base-scheduler "
        rec = log._build_log_record(record, "消息")
        self.assertEqual(rec["group"], "base-scheduler")

    def test_main_entry_can_still_assign_a_specific_business(self):
        record = make_record(PACKAGE + r"\__main__.py", "排班校验未完成")
        record.log_group = "base-scheduler"
        self.assertEqual(
            log._build_log_record(record, record.getMessage())["group"],
            "base-scheduler",
        )

    def test_unknown_module_omits_group_key(self):
        record = make_record(PACKAGE + r"\tests\log_tests.py")
        rec = log._build_log_record(record, "消息")
        self.assertNotIn("group", rec)


class LiveLogGroupTest(unittest.TestCase):
    def _emit(self, record):
        queue = log.LatestLogQueue(maxsize=4, drop_warning_interval=None)
        with patch.object(log, "frontend_log_queue", queue):
            log.whlr.emit(record)
        item = queue.get_nowait()
        queue.task_done()
        return item

    def test_live_record_group_has_no_trailing_space(self):
        record = make_record(PACKAGE + r"\solvers\base_schedule.py", "派发任务")
        record.log_group = "base-scheduler"
        # 文件/终端过滤器先于 WebSocket handler 处理同一条记录。
        log.filter.filter(record)
        item = self._emit(record)
        self.assertEqual(item["group"], "base-scheduler")
        self.assertFalse(item["group"].endswith(" "))

    def test_live_record_derives_group_without_extra(self):
        item = self._emit(make_record(PACKAGE + r"\utils\device\device.py"))
        self.assertEqual(item["group"], "device-control")
        self.assertFalse(item["group"].endswith(" "))


if __name__ == "__main__":
    unittest.main()
