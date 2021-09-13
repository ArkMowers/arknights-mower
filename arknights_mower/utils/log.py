import time
import logging
import colorlog
from pathlib import Path
from logging.handlers import FileHandler
from .config import LOGFILE_PATH, SCREENSHOT_PATH, SCREENSHOT_MAXNUM

BASIC_FORMAT = '%(asctime)s - %(levelname)s - %(lineno)d - %(funcName)s - %(message)s'
COLOR_FORMAT = '%(log_color)s%(asctime)s - %(levelname)s - %(lineno)d - %(funcName)s - %(message)s'
DATE_FORMAT = None
basic_formatter = logging.Formatter(BASIC_FORMAT, DATE_FORMAT)
color_formatter = colorlog.ColoredFormatter(COLOR_FORMAT, DATE_FORMAT)

chlr = logging.StreamHandler()
chlr.setFormatter(color_formatter)
chlr.setLevel('DEBUG')

fhlr = FileHandler(LOGFILE_PATH, when='D', interval=1, backupCount=7)
fhlr.setFormatter(basic_formatter)
fhlr.setLevel('DEBUG')

logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')
logger.addHandler(chlr)
logger.addHandler(fhlr)


def save_screenshot(img=None):

    assert img is not None

    folder = Path(SCREENSHOT_PATH)
    png_lists = list(folder.iterdir())
    for x in png_lists[:1-SCREENSHOT_MAXNUM]:
        logger.debug(f'remove screenshot: {x.name}')
        x.unlink()

    filename = time.strftime(f'%Y%m%d%H%M%S.png', time.localtime())
    with folder.joinpath(filename).open('wb') as f:
        f.write(img)
    logger.debug(f'save screenshot: {filename}')
