import logging
import shutil
import sys
import time
import traceback
from datetime import datetime, timedelta
from logging.handlers import QueueHandler, QueueListener, TimedRotatingFileHandler
from pathlib import Path
from queue import Queue
from threading import Thread

import colorlog

from arknights_mower.utils import config
from arknights_mower.utils.path import get_path

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

last_screenshot = None
filter = PackagePathFilter()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# d(ebug)hlr: 终端输出
dhlr = logging.StreamHandler(stream=sys.stdout)
dhlr.setFormatter(color_formatter)
dhlr.setLevel(logging.DEBUG)
dhlr.addFilter(filter)

# f(ile)hlr: 文件记录
folder = Path(get_path("@app/log"))
folder.mkdir(exist_ok=True, parents=True)
fhlr = TimedRotatingFileHandler(
    folder.joinpath("runtime.log"), encoding="utf8", backupCount=168
)
fhlr.setFormatter(basic_formatter)
fhlr.setLevel("DEBUG")
fhlr.addFilter(filter)


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
listener = QueueListener(log_queue, dhlr, fhlr, whlr, respect_handler_level=True)
listener.start()

screenshot_folder = get_path("@app/screenshot")
screenshot_folder.mkdir(exist_ok=True, parents=True)
screenshot_queue = Queue()
cleanup_time = datetime.now()


def screenshot_cleanup():
    logger.info("清理过期截图")
    start_time_ns = time.time_ns() - config.conf.screenshot * 3600 * 10**9
    for i in screenshot_folder.iterdir():
        if i.is_dir():
            if i.name == "run_order":
                # 处理run_order文件夹，只保留最后100张图片
                images = sorted(
                    [f for f in i.iterdir() if f.is_file() and f.stem.isnumeric()],
                    key=lambda x: int(x.stem),
                )
                if len(images) > 100:
                    for img in images[:-100]:  # 保留最后100张，删除其余的
                        img.unlink()
                continue
            shutil.rmtree(i)
        elif not i.stem.isnumeric():
            i.unlink()
        elif int(i.stem) < start_time_ns:
            i.unlink()
    global cleanup_time
    cleanup_time = datetime.now()


def screenshot_worker():
    screenshot_cleanup()
    global last_screenshot
    while True:
        now = datetime.now()
        if now - cleanup_time > timedelta(hours=1):
            screenshot_cleanup()
        img, filename, upate_last = screenshot_queue.get()
        with screenshot_folder.joinpath(filename).open("wb") as f:
            f.write(img)
            if upate_last:
                last_screenshot = filename

Thread(target=screenshot_worker, daemon=True).start()


def save_screenshot(img: bytes, sub_folder=None) -> None:
    filename = f"{time.time_ns()}.jpg"
    logger.debug(filename)
    if sub_folder:
        sub_folder_path = Path(screenshot_folder) / sub_folder
        sub_folder_path.mkdir(parents=True, exist_ok=True)
        filename = f"{sub_folder}/{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
    screenshot_queue.put((img, filename,not sub_folder))


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
