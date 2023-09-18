import logging
import os
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorlog
from . import config

BASIC_FORMAT = '%(asctime)s - %(levelname)s - %(relativepath)s:%(lineno)d - %(funcName)s - %(message)s'
COLOR_FORMAT = '%(log_color)s%(asctime)s - %(levelname)s - %(relativepath)s:%(lineno)d - %(funcName)s - %(message)s'
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


class MaxFilter(object):
    def __init__(self, max_level: int) -> None:
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno <= self.max_level:
            return True


class Handler(logging.StreamHandler):
    def __init__(self, pipe):
        logging.StreamHandler.__init__(self)
        self.pipe = pipe

    def emit(self, record):
        record = f'{record.message}'
        self.pipe.send({'type':'log','data':record})


chlr = logging.StreamHandler(stream=sys.stdout)
chlr.setFormatter(color_formatter)
chlr.setLevel('INFO')
chlr.addFilter(MaxFilter(logging.INFO))
chlr.addFilter(PackagePathFilter())

ehlr = logging.StreamHandler(stream=sys.stderr)
ehlr.setFormatter(color_formatter)
ehlr.setLevel('WARNING')
ehlr.addFilter(PackagePathFilter())

logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')
logger.addHandler(chlr)
logger.addHandler(ehlr)


def init_fhlr(pipe=None) -> None:
    """ initialize log file """
    if config.LOGFILE_PATH is None:
        return
    folder = Path(config.LOGFILE_PATH)
    folder.mkdir(exist_ok=True, parents=True)
    fhlr = RotatingFileHandler(
        folder.joinpath('runtime.log'),
        encoding='utf8',
        maxBytes=10 * 1024 * 1024,
        backupCount=config.LOGFILE_AMOUNT,
    )
    fhlr.setFormatter(basic_formatter)
    fhlr.setLevel('DEBUG')
    fhlr.addFilter(PackagePathFilter())
    logger.addHandler(fhlr)
    if pipe is not None:
        wh = Handler(pipe)
        wh.setLevel(logging.INFO)
        logger.addHandler(wh)


def set_debug_mode() -> None:
    """ set debud mode on """
    if config.DEBUG_MODE:
        logger.info(f'Start debug mode, log is stored in {config.LOGFILE_PATH}')
        init_fhlr()


def save_screenshot(img: bytes, subdir: str = '') -> None:
    """ save screenshot """
    if config.SCREENSHOT_PATH is None:
        return
    folder = Path(config.SCREENSHOT_PATH).joinpath(subdir)
    folder.mkdir(exist_ok=True, parents=True)
    if subdir != '-1' and len(list(folder.iterdir())) > config.SCREENSHOT_MAXNUM:
        screenshots = list(folder.iterdir())
        screenshots = sorted(screenshots, key=lambda x: x.name)
        for x in screenshots[: -config.SCREENSHOT_MAXNUM]:
            logger.debug(f'remove screenshot: {x.name}')
            x.unlink()
    filename = time.strftime('%Y%m%d%H%M%S.png', time.localtime())
    with folder.joinpath(filename).open('wb') as f:
        f.write(img)
    logger.debug(f'save screenshot: {filename}')


class log_sync(threading.Thread):
    """ recv output from subprocess """

    def __init__(self, process: str, pipe: int) -> None:
        self.process = process
        self.pipe = os.fdopen(pipe)
        super().__init__(daemon=True)

    def __del__(self) -> None:
        self.pipe.close()

    def run(self) -> None:
        while True:
            line = self.pipe.readline().strip()
            logger.debug(f'{self.process}: {line}')


