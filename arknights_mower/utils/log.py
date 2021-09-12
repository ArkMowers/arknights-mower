import logging
import colorlog
from logging.handlers import TimedRotatingFileHandler

BASIC_FORMAT = '%(asctime)s - %(levelname)s - %(lineno)d - %(funcName)s - %(message)s'
COLOR_FORMAT = '%(log_color)s%(asctime)s - %(levelname)s - %(lineno)d - %(funcName)s - %(message)s'
DATE_FORMAT = None
basic_formatter = logging.Formatter(BASIC_FORMAT, DATE_FORMAT)
color_formatter = colorlog.ColoredFormatter(COLOR_FORMAT, DATE_FORMAT)

chlr = logging.StreamHandler()
chlr.setFormatter(color_formatter)
chlr.setLevel('DEBUG')

fhlr = TimedRotatingFileHandler(
    './logs/log.txt', when='H', interval=1, backupCount=24)
fhlr.setFormatter(basic_formatter)
fhlr.setLevel('DEBUG')

logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')
logger.addHandler(chlr)
logger.addHandler(fhlr)
