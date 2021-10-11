import time
import schedule
from arknights_mower.strategy import Solver
from arknights_mower.utils.log import logger, init_fhlr
from arknights_mower.utils import config


# 使用信用点购买东西的优先级
shop_priority = ['招聘许可', '赤金', '龙门币', '初级作战记录', '技巧概要·卷2', '基础作战记录', '技巧概要·卷1']


def debuglog():
    '''
    在屏幕上输出调试信息，方便调试和报错
    '''
    logger.handlers[0].setLevel('DEBUG')


def savelog():
    '''
    指定日志和截屏的保存位置，方便调试和报错
    '''
    config.LOGFILE_PATH = './log'
    config.SCREENSHOT_PATH = './screenshot'
    config.SCREENSHOT_MAXNUM = 100
    init_fhlr()


def simulate():
    cli = Solver()
    cli.base() # 基建
    cli.credit() # 信用
    cli.ope(eliminate=True) # 行动
    cli.shop(shop_priority) # 商店
    cli.recruit() # 公招
    cli.mission() # 任务
    # cli.mail() # 邮件 (TODO)


def schedule_task():
    """
    定期运行
    """
    schedule.every().day.at('07:00').do(simulate)
    schedule.every().day.at('19:00').do(simulate)
    while True:
        schedule.run_pending()
        time.sleep(60)


debuglog()
savelog()
simulate()
# schedule_task()
