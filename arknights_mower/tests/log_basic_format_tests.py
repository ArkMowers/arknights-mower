"""阶段三：验证 BASIC_FORMAT 的 log_group_prefix 前缀，diagnostics.py 时间线读取器仍正确解析。"""

import logging
import tempfile
import unittest
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from arknights_mower.utils import log
from arknights_mower.utils.diagnostics import timeline


class BasicFormatGroupPrefixTest(unittest.TestCase):
    """验证文件日志格式携带 group 前缀，WebSocket 推送不受影响。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._log_folder = Path(self._tmp) / "log"
        self._log_folder.mkdir()
        self._screenshot_folder = Path(self._tmp) / "screenshot"
        self._screenshot_folder.mkdir()

        # 建立独立的 logger 和 file handler，不影响全局 log.fhlr
        self._logger = logging.getLogger(f"test.{id(self)}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        self._fhlr = TimedRotatingFileHandler(
            self._log_folder / "runtime.log",
            when="h",
            interval=1,
            encoding="utf8",
        )
        self._fhlr.setFormatter(log.basic_formatter)
        self._fhlr.addFilter(log.filter)
        self._logger.addHandler(self._fhlr)

    def tearDown(self):
        self._logger.removeHandler(self._fhlr)
        self._fhlr.close()

    def test_format_includes_group_prefix_when_present(self):
        """有 log_group 时，文件日志在时间戳后、文件名前携带 group 前缀和空格。"""
        self._logger.info("测试消息", extra={"log_group": "base_schedule"})
        self._fhlr.flush()

        lines = (self._log_folder / "runtime.log").read_text(encoding="utf-8").strip()
        # 格式：asctime base_schedule relativepath:lineno levelname funcName: message
        self.assertIn(" base_schedule ", lines)
        self.assertIn(" INFO ", lines)
        self.assertIn("测试消息", lines)

        # 确认 group 在时间戳之后，且只出现一次前缀。
        parts = lines.split(" ", 3)  # 日期 时间 group ...
        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[2], "base_schedule")
        self.assertEqual(lines.count("base_schedule"), 1)

    def test_filter_keeps_caller_group_and_writes_separate_prefix(self):
        """过滤器只写 log_group_prefix，调用方原始 log_group 不带前缀空格。"""
        record = self._logger.makeRecord(
            self._logger.name,
            logging.INFO,
            "arknights_mower/solvers/base_schedule.py",
            10,
            "测试消息",
            (),
            None,
        )
        record.log_group = "base_scheduler"
        self.assertTrue(log.filter.filter(record))
        self.assertEqual(record.log_group, "base_scheduler")
        self.assertEqual(record.log_group_prefix, "base_scheduler ")
        formatted = log.basic_formatter.format(record)
        self.assertIn(" base_scheduler ", formatted)

    def test_format_omits_group_when_absent(self):
        """没有 log_group 时，文件日志不产生额外空格，直接接文件名。"""
        self._logger.info("测试消息")
        self._fhlr.flush()

        lines = (self._log_folder / "runtime.log").read_text(encoding="utf-8").strip()
        # 格式：asctime relativepath:lineno levelname funcName: message
        # 时间戳后直接是文件路径，中间只有一个空格
        parts = lines.split(" ", 3)  # 日期 时间 路径:行号 ...
        self.assertEqual(len(parts), 4)
        # 第三部分应该是路径:行号，不是 group
        self.assertIn(".py:", parts[2])


class DiagnosticsTimelineCompatibilityTest(unittest.TestCase):
    """验证 diagnostics.py 时间线读取器在新格式下仍正确解析。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._log_folder = Path(self._tmp) / "log"
        self._log_folder.mkdir()
        self._screenshot_folder = Path(self._tmp) / "screenshot"
        self._screenshot_folder.mkdir()

        # 建立独立的 logger 和 file handler
        self._logger = logging.getLogger(f"test.{id(self)}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        self._fhlr = TimedRotatingFileHandler(
            self._log_folder / "runtime.log",
            when="h",
            interval=1,
            encoding="utf8",
        )
        self._fhlr.setFormatter(log.basic_formatter)
        self._fhlr.addFilter(log.filter)
        self._logger.addHandler(self._fhlr)

    def tearDown(self):
        self._logger.removeHandler(self._fhlr)
        self._fhlr.close()

    def test_timeline_parses_records_with_group_prefix(self):
        """时间线读取器正确解析带 group 前缀的记录。"""
        now = datetime.now()
        self._logger.info("带 group 的消息", extra={"log_group": "base_schedule"})
        self._logger.info("不带 group 的消息")
        self._logger.warning("另一条带 group 的消息", extra={"log_group": "device"})
        self._fhlr.flush()

        rows = timeline(self._log_folder, self._screenshot_folder, now, limit=10)

        self.assertEqual(len(rows), 3)
        self.assertIn("带 group 的消息", rows[0]["message"])
        self.assertIn("不带 group 的消息", rows[1]["message"])
        self.assertIn("另一条带 group 的消息", rows[2]["message"])

        # 验证时间提取正确
        for row in rows:
            self.assertIsNotNone(row["time"])
            self.assertEqual(len(row["time"]), 19)  # YYYY-MM-DD HH:MM:SS

    def test_timeline_extracts_time_correctly_regardless_of_group(self):
        """时间线读取器从前 19 个字符提取时间，不受 group 前缀影响。"""
        now = datetime.now()
        expected_time = now.strftime("%Y-%m-%d %H:%M:%S")

        # 手动构造一条带 group 的日志行写入文件
        log_line = (
            f"{expected_time},123 base_schedule "
            f"solver.py:456 INFO test_func: 测试时间提取\n"
        )
        (self._log_folder / "runtime.log").write_text(log_line, encoding="utf-8")

        rows = timeline(self._log_folder, self._screenshot_folder, now, limit=10)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["time"], expected_time)
        self.assertIn("测试时间提取", rows[0]["message"])

    def test_timeline_handles_mixed_format_logs(self):
        """时间线读取器处理混合格式的日志（有 group 和无 group）。"""
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M:%S")

        # 混合写入两种格式
        mixed_logs = (
            f"{time_str},100 base_schedule solver.py:10 INFO func1: 消息一\n"
            f"{time_str},200 device.py:20 INFO func2: 消息二\n"
            f"{time_str},300 device capture.py:30 DEBUG func3: 消息三\n"
        )
        (self._log_folder / "runtime.log").write_text(mixed_logs, encoding="utf-8")

        rows = timeline(self._log_folder, self._screenshot_folder, now, limit=10)

        self.assertEqual(len(rows), 3)
        messages = [row["message"] for row in rows]
        self.assertTrue(any("消息一" in msg for msg in messages))
        self.assertTrue(any("消息二" in msg for msg in messages))
        self.assertTrue(any("消息三" in msg for msg in messages))


if __name__ == "__main__":
    unittest.main()
