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


# 指定日志和截屏的保存位置，方便调试和报错
config.LOGFILE_PATH = './log'
config.SCREENSHOT_PATH = './screenshot'
config.SCREENSHOT_MAXNUM = 100
init_fhlr()


# 使用信用点购买东西的优先级
shop_priority = ['招聘许可', '赤金', '龙门币', '初级作战记录', '技巧概要·卷2', '基础作战记录', '技巧概要·卷1']


def simulate():
    cli = Solver()
    cli.base()
    cli.credit()
    cli.ope()
    cli.shop()
    cli.recruit()
    cli.mission()
    # cli.mail()


schedule.every().day.at('07:00').do(simulate)
schedule.every().day.at('19:00').do(simulate)


while True:
    schedule.run_pending()
    time.sleep(60)
