import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from queue import Queue

from arknights_mower.utils import log, path


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


class ScreenshotStoreStartupTest(MultiProcessLogTestBase):
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

    def test_first_submit_starts_store_and_both_threads(self):
        self.assertIsNone(log.get_screenshot_store())
        log.save_screenshot(b"jpeg bytes")
        store = log.get_screenshot_store()
        self.assertIsNotNone(store)
        self.assertEqual(
            sorted(thread.name for thread in store._threads),
            ["screenshot-cleaner", "screenshot-writer"],
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
