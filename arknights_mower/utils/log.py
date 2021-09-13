import time
import logging
import colorlog
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from . import config

BASIC_FORMAT = '%(asctime)s - %(levelname)s - %(lineno)d - %(funcName)s - %(message)s'
COLOR_FORMAT = '%(log_color)s%(asctime)s - %(levelname)s - %(lineno)d - %(funcName)s - %(message)s'
DATE_FORMAT = None
basic_formatter = logging.Formatter(BASIC_FORMAT, DATE_FORMAT)
color_formatter = colorlog.ColoredFormatter(COLOR_FORMAT, DATE_FORMAT)

chlr = logging.StreamHandler()
chlr.setFormatter(color_formatter)
chlr.setLevel('DEBUG')

logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')
logger.addHandler(chlr)


def init_fhlr():
    if config.LOGFILE_PATH is None:
        return
    folder = Path(config.LOGFILE_PATH)
    folder.mkdir(exist_ok=True)
    fhlr = TimedRotatingFileHandler(folder.joinpath('runtime.log'), when='D', interval=1, backupCount=7)
    fhlr.setFormatter(basic_formatter)
    fhlr.setLevel('DEBUG')
    logger.addHandler(fhlr)


def save_screenshot(img):
    if config.SCREENSHOT_PATH is None:
        return
    folder = Path(config.SCREENSHOT_PATH)
    folder.mkdir(exist_ok=True)
    filename = time.strftime(f'%Y%m%d%H%M%S.png', time.localtime())
    with folder.joinpath(filename).open('wb') as f:
        f.write(img)
    logger.debug(f'save screenshot: {filename}')
