import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from logging.handlers import QueueListener
from pathlib import Path
from queue import Queue
from unittest.mock import Mock, patch

from arknights_mower.utils import config, log, path
from arknights_mower.utils.log_retention import RUNTIME_LOG_RETENTION_HOURS
from arknights_mower.utils.log_stream import LogStream


class MultiProcessLogTestBase(unittest.TestCase):
    """每次测试隔离到临时 space，避免在仓库 log/ 下留下 runtime.log，并复位多进程句柄。"""

    def setUp(self):
        if log.fhlr is not None:
            log.fhlr.close()
            log.fhlr = None
        self._reset_screenshot_store()
        self._orig_space = path.global_space
        self._tmp = tempfile.mkdtemp()
        path.global_space = self._tmp

    def tearDown(self):
        if log.mp_listener is not None:
            log.mp_listener.stop()
            log.mp_listener = None
        if log.mp_queue_handler is not None:
            log.logger.removeHandler(log.mp_queue_handler)
            log.mp_queue_handler = None
        if log.fhlr is not None:
            log.fhlr.close()
            log.fhlr = None
        self._reset_screenshot_store()
        path.global_space = self._orig_space

    @staticmethod
    def _reset_screenshot_store():
        # 与 fhlr 等模块级句柄一样复位，避免一个测试建立的存储与线程影响后续测试。
        if log._store_instance is not None:
            log._store_instance.close()
            log._store_instance = None
        log._store_closed = False


class LogFileHandlerTest(MultiProcessLogTestBase):
    def test_no_file_handler_created_on_import(self):
        # 回归：GUI 子进程（webview_window）经 title_version→resource_version import
        # log.py 时不应再新建指向 runtime.log 的文件句柄，否则 Windows 整点滚转
        # （os.rename 需独占移动文件）会因多进程同时持有该文件而失败（WinError 32）。
        self.assertIsNone(log.fhlr)

    def test_init_file_logging_creates_runtime_log_handler(self):
        log.init_file_logging()
        self.assertIsNotNone(log.fhlr)
        self.assertEqual(
            log.fhlr.baseFilename,
            str(log.get_path("@app/log").joinpath("runtime.log")),
        )
        self.assertEqual(log.fhlr.backupCount, RUNTIME_LOG_RETENTION_HOURS)
        self.assertEqual(log.fhlr.interval, 3600)

    def test_existing_error_archives_start_hourly_cleanup(self):
        errors = path.get_path("@app/screenshot") / "errors"
        errors.mkdir(parents=True)
        log.init_file_logging()
        self.assertIsNotNone(log.get_screenshot_store())
        self.assertTrue(
            any(
                thread.name == "screenshot-cleaner" and thread.is_alive()
                for thread in log.get_screenshot_store()._threads
            )
        )


class ErrorArchivePolicyTest(MultiProcessLogTestBase):
    @staticmethod
    def record(source, level=logging.ERROR, archive_screenshots=None):
        record = logging.LogRecord(
            log.logger.name,
            level,
            f"/project/arknights_mower/{source}",
            12,
            "运行失败",
            (),
            None,
        )
        record.asctime = "2026-09-26 12:00:00"
        if archive_screenshots is not None:
            record.archive_screenshots = archive_screenshots
        return record

    def test_only_visual_runtime_errors_trigger_archive(self):
        for source, expected in (
            ("solvers/base_schedule.py", True),
            ("solvers/captcha_solver.py", True),
            ("utils/device/device.py", True),
            ("utils/solver.py", True),
            ("solvers/report.py", False),
            ("utils/resource_pkg.py", False),
            ("utils/config/app_state.py", False),
            ("utils/screenshot.py", False),
        ):
            with self.subTest(source=source):
                self.assertEqual(
                    log.should_archive_record(self.record(source)), expected
                )
        self.assertFalse(
            log.should_archive_record(
                self.record("solvers/base_schedule.py", level=logging.WARNING)
            )
        )

    def test_explicit_override_handles_main_loop_and_retry_errors(self):
        self.assertFalse(log.should_archive_record(self.record("__main__.py")))
        self.assertTrue(
            log.should_archive_record(
                self.record("__main__.py", archive_screenshots=True)
            )
        )
        self.assertFalse(
            log.should_archive_record(
                self.record("solvers/captcha_solver.py", archive_screenshots=False)
            )
        )

    def test_only_explicit_visual_warnings_are_archived(self):
        source = "solvers/base_schedule.py"
        self.assertFalse(
            log.should_archive_record(self.record(source, level=logging.WARNING))
        )
        self.assertTrue(
            log.should_archive_record(
                self.record(source, level=logging.WARNING, archive_screenshots=True)
            )
        )
        self.assertFalse(
            log.should_archive_record(
                self.record(source, level=logging.INFO, archive_screenshots=True)
            )
        )

    def test_non_visual_error_still_reaches_live_log_without_archive(self):
        store = Mock()
        with (
            patch.object(log, "get_screenshot_store", return_value=store),
            patch.object(config.log_queue, "put") as put,
        ):
            log.whlr.emit(self.record("utils/resource_pkg.py"))
        store.mark_error.assert_not_called()
        put.assert_called_once()
        self.assertIn("运行失败", put.call_args.args[0]["msg"])

    def test_visual_error_is_archived_and_linked_in_live_log(self):
        store = Mock()
        store.mark_error.return_value = "123"
        with (
            patch.object(log, "get_screenshot_store", return_value=store),
            patch.object(config.log_queue, "put") as put,
        ):
            log.whlr.emit(self.record("solvers/base_schedule.py"))
        store.mark_error.assert_called_once()
        self.assertIn("记录编号 123", put.call_args.args[0]["msg"])

    def test_visual_warning_is_archived_with_severity_in_summary(self):
        store = Mock()
        store.mark_error.return_value = "456"
        record = self.record(
            "solvers/base_schedule.py",
            level=logging.WARNING,
            archive_screenshots=True,
        )
        with (
            patch.object(log, "get_screenshot_store", return_value=store),
            patch.object(config.log_queue, "put") as put,
        ):
            log.whlr.emit(record)
        self.assertEqual(store.mark_error.call_args.args[1], "警告：运行失败")
        self.assertIn("记录编号 456", put.call_args.args[0]["msg"])


class ScreenshotStoreStartupTest(MultiProcessLogTestBase):
    def test_exit_before_first_capture_rejects_late_store_creation(self):
        log.close_screenshot_store()
        log.save_screenshot(b"late frame")
        self.assertIsNone(log.get_screenshot_store())

    def test_import_builds_no_screenshot_store(self):
        # 回归：ScreenshotStore 不在导入时建立。清理线程启动时会先扫一遍历史截图，
        # 而导入本模块的进程（测试、开发服务器、各种脚本）并没有删图的意图；多份
        # 清理线程并发删除同一批文件时，Windows 会让其中一次以 WinError 5 失败并
        # 记一条清理错误。这里用子进程确认导入本身不建立存储。
        space = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, space, ignore_errors=True)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os;"
                "from arknights_mower.utils import path;"
                "path.global_space = os.environ['MOWER_TEST_SPACE'];"
                "import arknights_mower.utils.log as log;"
                "print('STORE:', log.get_screenshot_store())",
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(Path(__file__).parents[2]),
            env={**os.environ, "MOWER_TEST_SPACE": space},
        )
        self.assertIn("STORE: None", result.stdout)

    def test_first_submit_starts_store_and_background_threads(self):
        self.assertIsNone(log.get_screenshot_store())
        log.save_screenshot(b"jpeg bytes")
        store = log.get_screenshot_store()
        self.assertIsNotNone(store)
        self.assertEqual(
            sorted(thread.name for thread in store._threads),
            [
                "screenshot-archiver",
                "screenshot-cleaner",
                "screenshot-preview",
                "screenshot-writer",
            ],
        )
        self.assertEqual(store.folder, path.get_path("@app/screenshot"))


class MultiProcessLoggingTest(MultiProcessLogTestBase):
    def test_bind_mp_queue_adds_queue_handler_to_logger(self):
        q = Queue()
        log.bind_mp_queue(q)
        self.assertIsNotNone(log.mp_queue_handler)
        self.assertIn(log.mp_queue_handler, log.logger.handlers)

    def test_start_mp_listener_creates_file_handler(self):
        log.start_mp_listener(Queue())
        self.assertIsNotNone(log.mp_listener)
        self.assertIsNotNone(log.fhlr)

    def test_bind_mp_queue_forwards_record_to_queue(self):
        # 子进程侧：bind 后 emit 的记录应被 QueueHandler 送进共享队列（不对本进程写文件）
        q = Queue()
        log.bind_mp_queue(q)
        log.logger.info("forwarded-msg")
        record = q.get(timeout=2)
        self.assertEqual(record.getMessage(), "forwarded-msg")


class LiveLogTruncationTest(MultiProcessLogTestBase):
    """实时日志先并入归档说明，再对合并整行做最终截断。"""

    @staticmethod
    def _record(source, message, level=logging.ERROR, archive_screenshots=None):
        record = logging.LogRecord(
            log.logger.name,
            level,
            f"/project/arknights_mower/{source}",
            12,
            message,
            (),
            None,
        )
        record.asctime = "2026-10-17 12:00:00"
        if archive_screenshots is not None:
            record.archive_screenshots = archive_screenshots
        return record

    def _emit(self, record):
        queue = log.LatestLogQueue(maxsize=4, drop_warning_interval=None)
        store = Mock()
        store.mark_error.return_value = "123"
        with (
            patch.object(log, "get_screenshot_store", return_value=store),
            patch.object(log, "frontend_log_queue", queue),
        ):
            log.whlr.emit(record)
        item = queue.get_nowait()
        queue.task_done()
        # 返回结构化记录的 msg 字段，与旧测试对文本行的断言保持相同的比较对象。
        return item["msg"]

    def test_archive_notice_survives_merged_line_truncation(self):
        record = self._record(
            "solvers/base_schedule.py", "长" * (2 * log.LIVE_LOG_MESSAGE_LIMIT)
        )
        message = self._emit(record)
        # msg 只含消息正文；asctime 与 levelname 在结构化记录的 t/level 字段。
        self.assertLessEqual(len(message), log.LIVE_LOG_MESSAGE_LIMIT)
        # 截断标记与归档编号都必须留在行尾；编号被尾部切掉时这条断言失败。
        self.assertTrue(
            message.endswith(
                log.LIVE_LOG_TRUNCATION_SUFFIX + "（已保存前后截图，记录编号 123）"
            )
        )
        self.assertEqual(message.count(log.LIVE_LOG_TRUNCATION_SUFFIX), 1)

    def test_archive_notice_survives_prepare_then_final_truncation(self):
        handler = log.LiveQueueHandler(
            log.LatestLogQueue(maxsize=4, drop_warning_interval=None)
        )
        prepared = handler.prepare(
            self._record(
                "solvers/base_schedule.py", "长" * (2 * log.LIVE_LOG_MESSAGE_LIMIT)
            )
        )
        # 入队前那条消息已被 prepare 截到上限，最终整行仍要多留归档编号。
        self.assertEqual(len(prepared.message), log.LIVE_LOG_MESSAGE_LIMIT)
        message = self._emit(prepared)
        self.assertLessEqual(len(message), log.LIVE_LOG_MESSAGE_LIMIT)
        self.assertTrue(
            message.endswith(
                log.LIVE_LOG_TRUNCATION_SUFFIX + "（已保存前后截图，记录编号 123）"
            )
        )
        self.assertEqual(message.count(log.LIVE_LOG_TRUNCATION_SUFFIX), 1)

    def test_short_archived_warning_keeps_notice_at_line_end(self):
        record = self._record(
            "solvers/base_schedule.py",
            "运行失败",
            level=logging.WARNING,
            archive_screenshots=True,
        )
        message = self._emit(record)
        # msg 只含消息正文与归档说明；asctime 和 level 在结构化记录的 t/level 字段。
        self.assertEqual(
            message,
            "运行失败（已保存前后截图，记录编号 123）",
        )


class RuntimeLogRetentionTest(MultiProcessLogTestBase):
    def test_runtime_log_keeps_full_message_while_live_line_is_truncated(self):
        log.init_file_logging()
        full = "完整内容" * (log.LIVE_LOG_MESSAGE_LIMIT // 4 + 10)
        log.logger.info(full)
        log.fhlr.flush()
        runtime_log = path.get_path("@app/log") / "runtime.log"
        self.assertIn(full, runtime_log.read_text(encoding="utf-8"))


class LiveRecordFieldsTest(MultiProcessLogTestBase):
    def test_record_time_survives_delivery_independently_of_formatted_timezone(self):
        for timestamp in ("2023-11-14 22:13:20,123", "2023-11-15 06:13:20,123"):
            with self.subTest(timestamp=timestamp):
                source = logging.LogRecord(
                    "test", logging.INFO, __file__, 1, "正在等待场景变化", (), None
                )
                source.created = 1_700_000_000.123
                source.asctime = timestamp
                prepared = log.LiveQueueHandler(Queue()).prepare(source)
                frontend = Queue()
                with patch.object(log, "frontend_log_queue", frontend):
                    log.whlr.emit(prepared)
                delivered = frontend.get_nowait()
                self.assertEqual(delivered["at"], 1_700_000_000_123)
                self.assertEqual(delivered["t"], timestamp)

                stream = LogStream()
                subscription = stream.subscribe()
                subscription.messages.get_nowait()
                stream.publish(delivered)
                live = json.loads(subscription.messages.get_nowait())
                history = json.loads(stream.subscribe().messages.get_nowait())
                self.assertEqual(history["records"], live["records"])
                self.assertEqual(history["records"][0]["at"], 1_700_000_000_123)
                self.assertEqual(history["data"], f"{timestamp} INFO 正在等待场景变化")

    @staticmethod
    def task_snapshot():
        return {
            "header": "休息至 19:42:00，随后执行甲组下班、乙组上班",
            "title": "甲组下班、乙组上班",
            "rooms": [
                {
                    "id": "room_2_1",
                    "label": "贸易站 B201",
                    "agents": ["Current", "但书", "龙舌兰"],
                }
            ],
            "backups": [{"name": "夜班", "active": True}],
            "targets": [],
        }

    def test_task_snapshot_is_detached_before_the_async_consumer(self):
        live_queue = log.LatestLogQueue(maxsize=4, drop_warning_interval=None)
        frontend = log.LatestLogQueue(maxsize=4, drop_warning_interval=None)
        source = logging.getLogger("arknights_mower.tests.task_snapshot")
        previous_level, previous_propagate = source.level, source.propagate
        source.propagate = False
        source.setLevel(logging.INFO)
        handler = log.LiveQueueHandler(live_queue)
        source.addHandler(handler)
        task = self.task_snapshot()
        original = self.task_snapshot()
        try:
            source.info("任务预告", extra={"log_task": task})
            task["rooms"][0]["agents"][1] = "错误的后续名单"
            task["backups"][0]["name"] = "后续改名"
            listener = QueueListener(
                live_queue, log.dhlr, log.whlr, respect_handler_level=True
            )
            with patch.object(log, "frontend_log_queue", frontend):
                listener.start()
                try:
                    record = frontend.get(timeout=2)
                finally:
                    listener.stop()
        finally:
            source.removeHandler(handler)
            source.setLevel(previous_level)
            source.propagate = previous_propagate
        self.assertEqual(record["task"], original)
        self.assertEqual(record["msg"], "任务预告")

    def test_task_snapshot_obeys_message_budget_without_clipping_positions(self):
        for value in (
            {"rooms": "长" * log.LIVE_LOG_MESSAGE_LIMIT},
            {"rooms": object()},
            {"rooms": float("nan")},
        ):
            with self.subTest(value_type=type(value["rooms"]).__name__):
                record = logging.LogRecord(
                    "test", logging.INFO, __file__, 1, "完整计划见文件", (), None
                )
                record.log_task = value
                prepared = log.LiveQueueHandler(Queue()).prepare(record)
                self.assertNotIn("log_task", prepared.__dict__.keys())
                record.asctime = "2026-11-04 18:30:02"
                delivered = log._build_log_record(record, record.getMessage())
                self.assertNotIn("task", delivered)
                self.assertEqual(delivered["msg"], "完整计划见文件")
                self.assertIs(record.log_task, value)

    def test_task_snapshot_shares_the_existing_live_message_budget(self):
        record = logging.LogRecord(
            "test",
            logging.INFO,
            __file__,
            1,
            "正文" * (log.LIVE_LOG_MESSAGE_LIMIT // 2),
            (),
            None,
        )
        record.log_task = self.task_snapshot()
        prepared = log.LiveQueueHandler(Queue()).prepare(record)
        self.assertNotIn("log_task", prepared.__dict__.keys())
        self.assertLessEqual(len(prepared.getMessage()), log.LIVE_LOG_MESSAGE_LIMIT)

    def test_extra_fields_reach_frontend_record_through_live_queue(self):
        # 与模块级管道相同：logger → LiveQueueHandler → QueueListener(dhlr, whlr)。
        live_queue = log.LatestLogQueue(maxsize=4, drop_warning_interval=None)
        frontend = log.LatestLogQueue(maxsize=4, drop_warning_interval=None)
        source = logging.getLogger("arknights_mower.tests.live_record_fields")
        source.propagate = False
        source.setLevel(logging.DEBUG)
        handler = log.LiveQueueHandler(live_queue)
        source.addHandler(handler)
        listener = QueueListener(
            live_queue, log.dhlr, log.whlr, respect_handler_level=True
        )
        listener.start()
        try:
            with patch.object(log, "frontend_log_queue", frontend):
                source.info(
                    "安排干员：但书 → B101",
                    extra={"log_room": "room_1_1", "log_agents": ["但书"]},
                )
                record = frontend.get(timeout=2)
        finally:
            listener.stop()
            source.removeHandler(handler)
        self.assertEqual(record["level"], "INFO")
        self.assertEqual(record["msg"], "安排干员：但书 → B101")
        self.assertEqual(record["room"], "room_1_1")
        self.assertEqual(record["agents"], ["但书"])
        self.assertTrue(record["t"])
        self.assertNotIn("group", record)


class LatestLogQueueTest(MultiProcessLogTestBase):
    """非阻塞淘汰语义、可读 dropped 状态与限频告警。"""

    def test_backlog_warning_identifies_display_loss_and_preserves_file_records(self):
        records = []
        capture = logging.Handler()
        capture.emit = records.append
        queue = log.LatestLogQueue(maxsize=1)
        queued = log.LiveQueueHandler(queue)
        destination = Path(self._tmp) / "runtime.log"
        output = logging.FileHandler(destination, encoding="utf-8")
        try:
            output.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            with patch.object(log.logger, "handlers", [queued, capture, output]):
                log.logger.info("第一条原始记录")
                log.logger.info("第二条原始记录")
        finally:
            output.close()
        warnings = [record for record in records if record.levelno == logging.WARNING]
        self.assertEqual(len(warnings), 1)
        warning = warnings[0]
        self.assertEqual(
            log._build_log_record(warning, warning.getMessage())["group"], "runtime-log"
        )
        self.assertEqual(
            warning.getMessage(),
            "部分日志未能及时显示，已跳过较早记录以显示最新内容。"
            "需要查看这些记录时，请打开 runtime.log。",
        )
        self.assertNotIn("消费", warning.getMessage())
        self.assertNotIn("累计", warning.getMessage())
        saved = destination.read_text(encoding="utf-8")
        self.assertIn("第一条原始记录", saved)
        self.assertIn("第二条原始记录", saved)
        self.assertIn(warning.getMessage(), saved)

    def test_debug_loss_does_not_claim_user_visible_records_are_missing(self):
        records = []
        capture = logging.Handler()
        capture.emit = records.append
        queue = log.LatestLogQueue(maxsize=1)
        queued = log.LiveQueueHandler(queue)
        with patch.object(log.logger, "handlers", [queued, capture]):
            for index in range(3):
                log.logger.debug("调试记录 %d", index)
            log.logger.info("第一条界面记录")
            self.assertEqual(queue.dropped, 3)
            self.assertFalse(
                any(record.levelno == logging.WARNING for record in records)
            )
            log.logger.info("第二条界面记录")
        warnings = [record for record in records if record.levelno == logging.WARNING]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].getMessage(), log.LIVE_LOG_DROP_WARNING_FORMAT)

    def test_notice_loss_does_not_generate_another_notice_or_delay_a_real_warning(self):
        notice = logging.LogRecord(
            log.logger.name,
            logging.WARNING,
            __file__,
            1,
            log.LIVE_LOG_DROP_WARNING_FORMAT,
            (),
            None,
        )
        notice.log_drop_notice = True
        notice.log_group = "runtime-log"
        notice.asctime = "2026-11-08 12:00:00"
        representations = (notice, log._build_log_record(notice, notice.getMessage()))
        for item in representations:
            with self.subTest(representation=type(item).__name__):
                queue = log.LatestLogQueue(maxsize=1)
                with patch.object(log.logger, "warning") as warning:
                    queue.put(item)
                    queue.put("新的界面记录")
                    warning.assert_not_called()
                    self.assertEqual(queue.dropped, 1)
                    queue.put("下一条界面记录")
                    warning.assert_called_once()

    def test_shutdown_sentinel_is_not_displaced_by_its_own_drop_warning(self):
        records = []
        capture = logging.Handler()
        capture.emit = records.append
        queue = log.LatestLogQueue(maxsize=1)
        queued = log.LiveQueueHandler(queue)
        with patch.object(log.logger, "handlers", [queued, capture]):
            log.logger.info("退出前的记录")
            listener = QueueListener(queue)
            listener.enqueue_sentinel()
        self.assertIs(queue.get_nowait(), listener._sentinel)
        queue.task_done()
        self.assertEqual(queue.dropped, 1)
        self.assertFalse(any(record.levelno == logging.WARNING for record in records))

    def test_put_has_no_ignored_block_or_timeout_arguments(self):
        queue = log.LatestLogQueue(maxsize=1, drop_warning_interval=None)
        with self.assertRaises(TypeError):
            queue.put("item", block=False)
        with self.assertRaises(TypeError):
            queue.put("item", block=True, timeout=1)
        queue.put("item")
        self.assertEqual(queue.get_nowait(), "item")
        queue.task_done()

    def test_put_nowait_remains_the_non_blocking_entry_point(self):
        queue = log.LatestLogQueue(maxsize=1, drop_warning_interval=None)
        queue.put_nowait("first")
        queue.put_nowait("second")
        self.assertEqual(queue.dropped, 1)
        self.assertEqual(queue.get_nowait(), "second")
        queue.task_done()

    def test_full_queue_evicts_oldest_without_raising_full(self):
        queue = log.LatestLogQueue(maxsize=2, drop_warning_interval=None)
        for message in ("first", "second", "third", "fourth"):
            queue.put(message)
        self.assertEqual(queue.qsize(), 2)
        self.assertEqual(queue.dropped, 2)
        self.assertEqual(queue.get_nowait(), "third")
        queue.task_done()
        self.assertEqual(queue.get_nowait(), "fourth")
        queue.task_done()

    def test_full_queue_accepts_listener_sentinel(self):
        queue = log.LatestLogQueue(maxsize=1, drop_warning_interval=None)
        queue.put_nowait("live")
        listener = QueueListener(queue)
        listener.enqueue_sentinel()
        self.assertIs(queue.get_nowait(), listener._sentinel)
        queue.task_done()
        self.assertEqual(queue.dropped, 1)

    def test_dropped_state_is_readable_and_warning_is_rate_limited(self):
        now = [1000.0]
        queue = log.LatestLogQueue(maxsize=1)
        with (
            patch.object(log, "monotonic", lambda: now[0]),
            patch.object(log.logger, "warning") as warning,
        ):
            queue.put("first")
            self.assertEqual(warning.call_count, 0)
            queue.put("second")
            self.assertEqual(warning.call_count, 1)
            self.assertEqual(
                warning.call_args.args[0], log.LIVE_LOG_DROP_WARNING_FORMAT
            )
            self.assertEqual(warning.call_args.args[1:], ())
            now[0] += log.LIVE_LOG_DROP_WARNING_INTERVAL / 2
            for index in range(100):
                queue.put(str(index))
            # 同一间隔内只允许一条告警，不随淘汰次数增加高频日志。
            self.assertEqual(warning.call_count, 1)
            self.assertEqual(queue.dropped, 101)
            self.assertEqual(queue.dropped_since_warning, 100)
            now[0] += log.LIVE_LOG_DROP_WARNING_INTERVAL
            queue.put("last")
            self.assertEqual(warning.call_count, 2)
            self.assertEqual(warning.call_args.args[1:], ())
        self.assertEqual(queue.dropped, 102)
        self.assertEqual(queue.dropped_since_warning, 0)
