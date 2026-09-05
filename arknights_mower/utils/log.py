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

# f(ile)hlr: 文件记录
fhlr = None


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
listener = None

folder = Path(get_path("@app/log"))
folder.mkdir(exist_ok=True, parents=True)
fhlr = TimedRotatingFileHandler(
    folder.joinpath("runtime.log"), encoding="utf8", backupCount=168
)
fhlr.setFormatter(basic_formatter)
fhlr.setLevel("DEBUG")
fhlr.addFilter(filter)
queue_handler = QueueHandler(log_queue)
logger.addHandler(queue_handler)
listener = QueueListener(log_queue, dhlr, fhlr, whlr, respect_handler_level=True)
listener.start()

screenshot_folder = get_path("@app/screenshot")
screenshot_store = ScreenshotStore(
    screenshot_folder, lambda: config.conf.screenshot, logger
)
screenshot_queue = screenshot_store.queue
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
