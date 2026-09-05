import atexit
import logging
import sys
import traceback
from datetime import datetime, timedelta
from logging.handlers import QueueHandler, QueueListener, TimedRotatingFileHandler
from pathlib import Path
from queue import Queue

import colorlog

from arknights_mower.utils import config
from arknights_mower.utils.path import get_path
from arknights_mower.utils.screenshot import ScreenshotStore

BASIC_FORMAT = (
    "%(asctime)s %(relativepath)s:%(lineno)d %(levelname)s %(funcName)s: %(message)s"
)
COLOR_FORMAT = f"%(log_color)s{BASIC_FORMAT}"
DATE_FORMAT = None
basic_formatter = logging.Formatter(BASIC_FORMAT, DATE_FORMAT)
color_formatter = colorlog.ColoredFormatter(COLOR_FORMAT, DATE_FORMAT)


class PackagePathFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        relativepath = Path(record.pathname)
        try:
            relativepath = relativepath.relative_to(get_path("@install"))
        except ValueError:
            pass
        record.relativepath = relativepath
        return True


filter = PackagePathFilter()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# d(ebug)hlr: 终端输出
dhlr = logging.StreamHandler(stream=sys.stdout)
dhlr.setFormatter(color_formatter)
dhlr.setLevel(logging.DEBUG)
dhlr.addFilter(filter)


class Handler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord):
        msg = f"{record.asctime} {record.levelname} {record.message}"
        if record.exc_info:
            msg += "\n" + "".join(traceback.format_exception(*record.exc_info))
        config.log_queue.put(msg)


# w(ebsocket)hlr: WebSocket
whlr = Handler()
whlr.setLevel(logging.INFO)

log_queue = Queue()
queue_handler = QueueHandler(log_queue)
logger.addHandler(queue_handler)
listener = QueueListener(log_queue, dhlr, whlr, respect_handler_level=True)
listener.start()

# f(ile)hlr: 文件记录（整点滚转）。不在导入时建立，避免 GUI 子进程（webview_window
# 等）import 本模块时也各建一个指向同一 runtime.log 的文件句柄。Windows 的 os.rename
# 需要独占移动文件，两个进程都持有该文件时，任一进程整点滚转都会因另一进程仍占用而
# 抛 PermissionError [WinError 32]，且失败后该进程之后所有日志都会重复失败、全部丢失。
# 因此文件日志交由主进程显式 init_file_logging() 建立，子进程不调用。
fhlr = None


def init_file_logging() -> None:
    global fhlr
    if fhlr is not None:
        return
    folder = Path(get_path("@app/log"))
    folder.mkdir(exist_ok=True, parents=True)
    fhlr = TimedRotatingFileHandler(
        folder.joinpath("runtime.log"), encoding="utf8", backupCount=168
    )
    fhlr.setFormatter(basic_formatter)
    fhlr.setLevel("DEBUG")
    fhlr.addFilter(filter)
    logger.addHandler(fhlr)


# 多进程集中式日志：mower 主进程独占 runtime.log 文件句柄（init_file_logging），
# mp.Process 子进程（如 webview_window）经 title_version→resource_version import log.py 时
# 不建 fhlr，而是用 QueueHandler 把 LogRecord 经共享的 multiprocessing.Queue 上行到主进程，
# 由主进程的 start_mp_listener 消费后写入 fhlr。这样既保留子进程日志落盘，又避免多个进程
# 各自持有 runtime.log 导致 Windows 整点滚转（os.rename 需独占）抛 PermissionError
# [WinError 32]。两个通过 subprocess.Popen 拉起的 worker（进程控制 / 软件更新）与主进程
# 之间没有共享的 mp.Queue，走不进这条路，它们各自把输出写进 process.log / update.log。
mp_queue_handler = None  # 子进程侧：把本进程的 logger 记录送上共享队列
mp_listener = None  # 主进程侧：把共享队列里的记录写入 fhlr


def bind_mp_queue(queue) -> None:
    """mp.Process 子进程使用：把本进程日志上行到主进程的共享队列。

    子进程不调用 init_file_logging（不建 fhlr），只把 logger 挂到 QueueHandler(queue)，
    记录由主进程的 start_mp_listener 消费后写入 runtime.log。
    """
    global mp_queue_handler
    if mp_queue_handler is not None:
        return
    mp_queue_handler = QueueHandler(queue)
    logger.addHandler(mp_queue_handler)


def start_mp_listener(queue) -> None:
    """主进程使用：消费共享队列，把子进程上行的记录写入 runtime.log。

    QueueHandler.prepare 会把 message 连同异常栈一起格式化进 record.message，随后清空
    args / exc_info / exc_text，因此跨进程 pickle 安全，子进程的异常栈会随 message 落盘。
    须在能取得 fhlr 之后调用（内部会兜底 init_file_logging）。
    """
    global mp_listener
    if mp_listener is not None:
        return
    init_file_logging()
    mp_listener = QueueListener(queue, fhlr, respect_handler_level=True)
    mp_listener.start()


screenshot_folder = get_path("@app/screenshot")
screenshot_store = ScreenshotStore(
    screenshot_folder, lambda: config.conf.screenshot, logger
)
screenshot_cleanup = screenshot_store.cleanup
screenshot_store.start()
atexit.register(screenshot_store.close)


def save_screenshot(img: bytes, sub_folder=None) -> None:
    filename = screenshot_store.submit(img, sub_folder)
    logger.debug(filename)


def get_log_by_time(target_time, time_range=1):
    folder = Path(get_path("@app/log"))
    time_points = [
        target_time - timedelta(hours=time_range),
        target_time,
        target_time + timedelta(hours=time_range),
    ]
    valid_suffixes = [tp.strftime("%Y-%m-%d_%H") for tp in time_points]
    matching_files = []
    for file_path in folder.iterdir():
        if file_path.is_file():
            try:
                if any(suffix in file_path.name for suffix in valid_suffixes):
                    matching_files.append(file_path)
                elif (
                    file_path.name == "runtime.log"
                    and (datetime.now() - target_time).total_seconds() <= 3600
                ):
                    matching_files.append(file_path)
            except Exception as e:
                logger.exception(f"Error processing file {file_path}: {e}")
    return matching_files
