import time
import schedule
from pathlib import Path
from arknights_mower.utils import detector
from arknights_mower.strategy import Solver
from arknights_mower.utils.log import logger, init_fhlr
from arknights_mower.utils.adb import ADBConnector
from arknights_mower.utils.recognize import Recognizer, threshole, bytes2img
from arknights_mower.utils import config
from matplotlib import pyplot as plt

config.LOGFILE_PATH = './log'
config.SCREENSHOT_PATH = './screenshot'
config.SCREENSHOT_MAXNUM = 100
init_fhlr()


def simulate():
    cli = Solver()
    cli.base()
    cli.credit()
    cli.fight()
    cli.shop()
    cli.recruit()
    cli.mission()
    # cli.mail()


schedule.every().day.at('07:00').do(simulate)
schedule.every().day.at('19:00').do(simulate)


while True:
    schedule.run_pending()
    time.sleep(60)
