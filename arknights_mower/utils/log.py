import logging
import shutil
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorlog

from arknights_mower.utils import config
from arknights_mower.utils.path import get_path

BASIC_FORMAT = (
    "%(asctime)s - %(levelname)s - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s"
)
COLOR_FORMAT = "%(log_color)s%(asctime)s - %(levelname)s - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s"
DATE_FORMAT = None
basic_formatter = logging.Formatter(BASIC_FORMAT, DATE_FORMAT)
color_formatter = colorlog.ColoredFormatter(COLOR_FORMAT, DATE_FORMAT)


class PackagePathFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        pathname = record.pathname
        record.relativepath = None
        abs_sys_paths = map(os.path.abspath, sys.path)
        for path in sorted(abs_sys_paths, key=len, reverse=True):  # longer paths first
            if not path.endswith(os.sep):
                path += os.sep
            if pathname.startswith(path):
                record.relativepath = os.path.relpath(pathname, path)
                break
        return True


class Handler(logging.StreamHandler):
    def __init__(self, queue):
        logging.StreamHandler.__init__(self)
        self.queue = queue

    def emit(self, record):
        self.queue.put(record.message)


dhlr = logging.StreamHandler(stream=sys.stdout)
dhlr.setFormatter(color_formatter)
dhlr.setLevel("DEBUG")
dhlr.addFilter(PackagePathFilter())


logger = logging.getLogger(__name__)
logger.setLevel("DEBUG")
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
fhlr.addFilter(PackagePathFilter())
logger.addHandler(fhlr)
whlr = Handler(config.log_queue)
whlr.setLevel(logging.INFO)
logger.addHandler(whlr)


def save_screenshot(img: bytes) -> None:
    folder = get_path("@app/screenshot")
    folder.mkdir(exist_ok=True, parents=True)
    time_ns = time.time_ns()
    start_time_ns = time_ns - config.conf.screenshot * 3600 * 10**9
    for i in folder.iterdir():
        if i.is_dir():
            shutil.rmtree(i)
        elif not i.stem.isnumeric():
            i.unlink()
        elif int(i.stem) < start_time_ns:
            i.unlink()
    filename = f"{time_ns}.jpg"
    with folder.joinpath(filename).open("wb") as f:
        f.write(img)
    logger.debug(f"save screenshot: {filename}")
