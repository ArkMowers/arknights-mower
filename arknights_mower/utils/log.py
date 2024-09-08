import logging
import shutil
import sys
import time
import traceback
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorlog

from arknights_mower.utils import config
from arknights_mower.utils.path import get_path

BASIC_FORMAT = "%(asctime)s %(relativepath)s:%(lineno)d %(levelname)s %(message)s"
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
logger.setLevel("DEBUG")

dhlr = logging.StreamHandler(stream=sys.stdout)
dhlr.setFormatter(color_formatter)
dhlr.setLevel("DEBUG")
dhlr.addFilter(filter)
logger.addHandler(dhlr)

folder = Path(get_path("@app/log"))
folder.mkdir(exist_ok=True, parents=True)
fhlr = RotatingFileHandler(
    folder.joinpath("runtime.log"),
    encoding="utf8",
    maxBytes=10 * 1024 * 1024,
    backupCount=20,
)
fhlr.setFormatter(basic_formatter)
fhlr.setLevel("DEBUG")
fhlr.addFilter(filter)
logger.addHandler(fhlr)


class Handler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord):
        msg = f"{record.asctime} {record.levelname} {record.message}"
        if record.exc_info:
            msg += "\n" + "".join(traceback.format_exception(*record.exc_info))
        config.log_queue.put(msg)


whlr = Handler()
whlr.setLevel(logging.INFO)
logger.addHandler(whlr)


def save_screenshot(img: bytes) -> None:
    folder = get_path("@app/screenshot")
    folder.mkdir(exist_ok=True, parents=True)
    time_ns = time.time_ns()
    start_time_ns = time_ns - config.conf.screenshot * 3600 * 10 ** 9
    checking_thread = threading.Thread(target=check_old_screenshot,
                                       kwargs={"start_time_ns": start_time_ns,
                                               "folder": folder})
    checking_thread.start()
    filename = f"{time_ns}.jpg"
    with folder.joinpath(filename).open("wb") as f:
        f.write(img)
    logger.debug(f"save screenshot: {filename}")


def check_old_screenshot(start_time_ns, folder):
    for i in folder.iterdir():
        if i.is_dir():
            shutil.rmtree(i)
        elif not i.stem.isnumeric():
            i.unlink()
        elif int(i.stem) < start_time_ns:
            i.unlink()
