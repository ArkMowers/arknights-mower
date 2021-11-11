import sys
import time
import logging
import colorlog
from pathlib import Path
from logging.handlers import RotatingFileHandler
from . import config

BASIC_FORMAT = '%(asctime)s - %(levelname)s - %(lineno)d - %(funcName)s - %(message)s'
COLOR_FORMAT = '%(log_color)s%(asctime)s - %(levelname)s - %(lineno)d - %(funcName)s - %(message)s'
DATE_FORMAT = None
basic_formatter = logging.Formatter(BASIC_FORMAT, DATE_FORMAT)
color_formatter = colorlog.ColoredFormatter(COLOR_FORMAT, DATE_FORMAT)


class MaxFilter:
    def __init__(self, max_level):
        self.max_level = max_level

    def filter(self, record):
        if record.levelno <= self.max_level:
            return True


chlr = logging.StreamHandler(stream=sys.stdout)
chlr.setFormatter(color_formatter)
chlr.setLevel('INFO')
chlr.addFilter(MaxFilter(logging.INFO))

ehlr = logging.StreamHandler(stream=sys.stderr)
ehlr.setFormatter(color_formatter)
ehlr.setLevel('WARNING')

logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')
logger.addHandler(chlr)
logger.addHandler(ehlr)


def init_fhlr():
    if config.LOGFILE_PATH is None:
        return
    folder = Path(config.LOGFILE_PATH)
    folder.mkdir(exist_ok=True, parents=True)
    fhlr = RotatingFileHandler(folder.joinpath('runtime.log'),
                               maxBytes=10 * 1024 * 1024, backupCount=3)
    fhlr.setFormatter(basic_formatter)
    fhlr.setLevel('DEBUG')
    logger.addHandler(fhlr)


def set_debug_mode():
    if config.DEBUG_MODE:
        logger.info(f'开启 debug 模式，运行日志被保存在 {config.LOGFILE_PATH} 中')
        init_fhlr()


def save_screenshot(img, subdir=''):
    if config.SCREENSHOT_PATH is None:
        return
    folder = Path(config.SCREENSHOT_PATH).joinpath(subdir)
    folder.mkdir(exist_ok=True, parents=True)
    if subdir != '-1' and len(list(folder.iterdir())) > config.SCREENSHOT_MAXNUM:
        for x in list(folder.iterdir())[:-config.SCREENSHOT_MAXNUM]:
            logger.debug(f'remove screenshot: {x.name}')
            x.unlink()
    filename = time.strftime('%Y%m%d%H%M%S.png', time.localtime())
    with folder.joinpath(filename).open('wb') as f:
        f.write(img)
    logger.debug(f'save screenshot: {filename}')
