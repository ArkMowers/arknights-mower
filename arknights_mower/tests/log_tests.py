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
        self.assertIn("运行失败", put.call_args.args[0])

    def test_visual_error_is_archived_and_linked_in_live_log(self):
        store = Mock()
        store.mark_error.return_value = "123"
        with (
            patch.object(log, "get_screenshot_store", return_value=store),
            patch.object(config.log_queue, "put") as put,
        ):
            log.whlr.emit(self.record("solvers/base_schedule.py"))
        store.mark_error.assert_called_once()
        self.assertIn("记录编号 123", put.call_args.args[0])

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
        self.assertIn("记录编号 456", put.call_args.args[0])


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
        message = queue.get_nowait()
        queue.task_done()
        return message

    def test_archive_notice_survives_merged_line_truncation(self):
        record = self._record(
            "solvers/base_schedule.py", "长" * (2 * log.LIVE_LOG_MESSAGE_LIMIT)
        )
        message = self._emit(record)
        self.assertLessEqual(len(message), log.LIVE_LOG_MESSAGE_LIMIT)
        self.assertTrue(message.startswith("2026-10-17 12:00:00 ERROR "))
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
        self.assertEqual(
            message,
            "2026-10-17 12:00:00 WARNING 运行失败（已保存前后截图，记录编号 123）",
        )


class RuntimeLogRetentionTest(MultiProcessLogTestBase):
    def test_runtime_log_keeps_full_message_while_live_line_is_truncated(self):
        log.init_file_logging()
        full = "完整内容" * (log.LIVE_LOG_MESSAGE_LIMIT // 4 + 10)
        log.logger.info(full)
        log.fhlr.flush()
        runtime_log = path.get_path("@app/log") / "runtime.log"
        self.assertIn(full, runtime_log.read_text(encoding="utf-8"))


class LatestLogQueueTest(MultiProcessLogTestBase):
    """非阻塞淘汰语义、可读 dropped 状态与限频告警。"""

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
            # 第一次告警：自上次告警以来 1 条，累计 1 条。
            self.assertEqual(warning.call_args.args[1:], (1, 1))
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
            # 第二次告警：自上次告警以来 101 条，累计 102 条。
            self.assertEqual(warning.call_args.args[1:], (102, 101))
        self.assertEqual(queue.dropped, 102)
        self.assertEqual(queue.dropped_since_warning, 0)
