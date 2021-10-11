from pathlib import Path
from arknights_mower.utils import detector
from arknights_mower.strategy import Solver
from arknights_mower.utils.log import logger, init_fhlr
from arknights_mower.utils.adb import ADBConnector
from arknights_mower.utils.recognize import Recognizer, threshole, bytes2img
from arknights_mower.utils import config
from matplotlib import pyplot as plt


def debuglog():
    logger.handlers[0].setLevel('DEBUG')


def simulate():
    config.LOGFILE_PATH = './log'
    config.SCREENSHOT_PATH = './screenshot'
    config.SCREENSHOT_MAXNUM = 50
    init_fhlr()
    cli = Solver()
    cli.base()
    cli.credit()
    cli.ope() 
    cli.shop() 
    cli.recruit() 
    cli.mission() 
    cli.mail()


debuglog()
simulate()
