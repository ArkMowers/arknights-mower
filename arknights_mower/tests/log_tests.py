import tempfile
import unittest

from arknights_mower.utils import log, path


class LogFileHandlerTest(unittest.TestCase):
    def setUp(self):
        # 隔离到临时 space，避免在仓库 log/ 下留下 runtime.log
        if log.fhlr is not None:
            log.fhlr.close()
            log.fhlr = None
        self._orig_space = path.global_space
        self._tmp = tempfile.mkdtemp()
        path.global_space = self._tmp

    def tearDown(self):
        if log.fhlr is not None:
            log.fhlr.close()
            log.fhlr = None
        path.global_space = self._orig_space

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
