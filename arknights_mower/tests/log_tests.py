import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from queue import Empty, Queue
from unittest.mock import Mock, patch

from arknights_mower.utils import log, path
from arknights_mower.utils.log_retention import RUNTIME_LOG_RETENTION_HOURS


class MultiProcessLogTestBase(unittest.TestCase):
    """每次测试隔离到临时 space，避免在仓库 log/ 下留下 runtime.log，并复位多进程句柄。"""

    def setUp(self):
        self._reset_file_handler()
        self._reset_screenshot_store()
        self._orig_space = path.global_space
        self._tmp = tempfile.mkdtemp()
        path.global_space = self._tmp

    def tearDown(self):
        if log.mp_listener is not None:
            log.mp_listener.stop()
            log.mp_listener = None
        if log.mp_queue_handler is not None:
            # 与 bind_mp_queue 的挂载位置一致：上行 handler 在包级 logger 上。
            logging.getLogger("arknights_mower").removeHandler(log.mp_queue_handler)
            log.mp_queue_handler = None
        self._reset_file_handler()
        self._reset_screenshot_store()
        path.global_space = self._orig_space

    @staticmethod
    def _reset_file_handler():
        # fhlr 挂在包级 logger 上，只 close() 而不摘掉，后续测试 emit 时仍会写这条已关闭的流。
        if log.fhlr is None:
            return
        for target in (log.logger, logging.getLogger("arknights_mower")):
            target.removeHandler(log.fhlr)
        log.fhlr.close()
        log.fhlr = None

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
            patch.object(log.config.log_queue, "put") as put,
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
            patch.object(log.config.log_queue, "put") as put,
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
            patch.object(log.config.log_queue, "put") as put,
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
    def test_bind_mp_queue_attaches_the_relay_to_the_package_logger(self):
        q = Queue()
        log.bind_mp_queue(q)
        self.assertIsNotNone(log.mp_queue_handler)
        package_logger = logging.getLogger("arknights_mower")
        self.assertIn(log.mp_queue_handler, package_logger.handlers)
        self.assertNotIn(log.mp_queue_handler, log.logger.handlers)
        # 子进程不调用 init_file_logging，等级必须在这里放开，否则 INFO/DEBUG 在进入
        # 任何 handler 之前就被 root 的 WARNING 滤掉。
        self.assertLessEqual(package_logger.getEffectiveLevel(), logging.DEBUG)

    def test_start_mp_listener_creates_file_handler(self):
        log.start_mp_listener(Queue())
        self.assertIsNotNone(log.mp_listener)
        self.assertIsNotNone(log.fhlr)

    def test_start_mp_listener_relays_child_records_to_both_sinks(self):
        log.start_mp_listener(Queue())
        self.assertEqual(list(log.mp_listener.handlers), [log.fhlr, log.whlr])

    def test_bind_mp_queue_forwards_record_to_queue(self):
        # 子进程侧：bind 后 emit 的记录应被 QueueHandler 送进共享队列（不对本进程写文件）
        q = Queue()
        log.bind_mp_queue(q)
        log.logger.info("forwarded-msg")
        record = q.get(timeout=2)
        self.assertEqual(record.getMessage(), "forwarded-msg")

    def test_bind_mp_queue_forwards_records_from_any_module_logger(self):
        # 共享 logger 之外的模块 logger 同样上行；第三方 logger 不在该命名空间下，不上行。
        q = Queue()
        log.bind_mp_queue(q)
        module_logger = logging.getLogger("arknights_mower.utils.device.window")
        module_logger.info("module-forwarded")
        logging.getLogger("arknights_mower.utils.log").info("shared-forwarded")
        logging.getLogger("urllib3").info("third-party-forwarded")
        forwarded = {q.get(timeout=2).getMessage(), q.get(timeout=2).getMessage()}
        self.assertEqual(forwarded, {"module-forwarded", "shared-forwarded"})
        with self.assertRaises(Empty):
            q.get(timeout=0.2)

    def test_child_record_reaches_the_frontend_sink(self):
        q = Queue()
        log.start_mp_listener(q)
        record = logging.LogRecord(
            "arknights_mower.utils.window_shell",
            logging.INFO,
            __file__,
            1,
            "child-line",
            (),
            None,
        )
        with patch.object(log.config.log_queue, "put") as put:
            q.put(record)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and not put.called:
                time.sleep(0.02)
        put.assert_called_once()
        self.assertIn("child-line", put.call_args.args[0])


class ModuleLoggerRoutingTest(MultiProcessLogTestBase):
    """包级 handler 让命名空间下任意模块的记录各写一次，第三方 logger 不写。"""

    def _runtime_log_text(self):
        """等到 flush 哨兵落盘；文件 handler 与 listener 不同线程，只能有限等待。"""

        def read():
            runtime_log = Path(log.fhlr.baseFilename)
            return (
                runtime_log.read_text(encoding="utf8") if runtime_log.exists() else ""
            )

        text = ""
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            text = read()
            if "probe-flush-line" in text:
                break
            time.sleep(0.02)
        return text

    def test_records_from_any_module_logger_land_in_runtime_log_once(self):
        log.init_file_logging()
        probe_logger = logging.getLogger("arknights_mower.utils.device.probe")
        probe_logger.debug("probe-debug-line")
        probe_logger.info("probe-info-line")
        logging.getLogger("arknights_mower.utils.log").info("probe-flush-line")
        text = self._runtime_log_text()
        for line in ("probe-debug-line", "probe-info-line", "probe-flush-line"):
            self.assertEqual(text.count(line), 1, f"{line} 应恰好写入一次")

    def test_third_party_logger_is_not_written(self):
        log.init_file_logging()
        logging.getLogger("urllib3.probe").info("probe-third-party-line")
        logging.getLogger("arknights_mower.utils.probe").info("probe-flush-line")
        text = self._runtime_log_text()
        self.assertNotIn("probe-third-party-line", text)
