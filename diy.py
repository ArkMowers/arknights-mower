import time
import schedule
import numpy as np
from datetime import datetime
from py_linq import Enumerable

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.strategy import Solver
from arknights_mower.utils.log import logger, init_fhlr
from arknights_mower.utils import config

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

email_address = "xxx@qq.com"
mail_pass = "从QQ邮箱帐户设置—>生成授权码"
to = ['任何邮箱']
email_notification = False

# 指定无人机加速第三层第三个房间的制造或贸易订单
drone_room = 'room_3_3'

# 指定关卡序列的作战计划
ope_lists = [['AP-5', 1], ['1-7', -1]]

# 使用信用点购买东西的优先级（从高到低）
shop_priority = ['招聘许可', '赤金', '龙门币', '初级作战记录', '技巧概要·卷2', '基础作战记录', '技巧概要·卷1']

# 公招选取标签时优先选择的干员的优先级（从高到低）
recruit_priority = ['因陀罗', '火神']
# 自定义基建排班
# 这里自定义了一套排班策略，实现的是两班倒，分为四个阶段
# 阶段 1 和 2 为第一班，阶段 3 和 4 为第二班
# 第一班的干员在阶段 3 和 4 分两批休息，第二班同理
# 每个阶段耗时 6 小时
plan = {
    # 阶段 1
    "default": "plan_1",
    "plan_1": {
        # 办公室
        'central': [{'agent': '焰尾', 'group': '红松骑士', 'replacement': ['战车']},
                    {'agent': '琴柳', 'group': '絮雨', 'replacement': ['霜华']},
                    {'agent': '凯尔希', 'replacement': ['灰烬']},
                    {'agent': '夕', 'group': '夕', 'replacement': ['闪击']},
                    {'agent': '令', 'group': '夕', 'replacement': ['闪击']},
                    ],
        'contact': [{'agent': '絮雨', 'group': '絮雨', 'replacement': ['艾雅法拉']}],
        # 宿舍
        'dormitory_4': [{'agent': '波登可', 'time': ''},
                        {'agent': '夜莺', 'time': ''},
                        {'agent': '菲亚梅塔', 'replacement': ['迷迭香', '黑键', '絮雨']},
                        {'agent': 'Free', 'time': ''},
                        {'agent': 'Free', 'time': ''}],
        'dormitory_1': [{'agent': '流明', 'time': ''},
                        {'agent': '蜜莓', 'time': ''},
                        {'agent': 'Free', 'time': ''},
                        {'agent': 'Free', 'time': ''},
                        {'agent': 'Free', 'time': ''}
                        ],
        'dormitory_2': [{'agent': '闪灵', 'time': ''},
                        {'agent': '杜林', 'time': ''},
                        {'agent': '褐果', 'time': ''},
                        {'agent': 'Free', 'time': ''},
                        {'agent': 'Free', 'time': ''}
                        ],
        'dormitory_3': [{'agent': '车尔尼', 'time': ''},
                        {'agent': '安比尔', 'time': ''},
                        {'agent': '爱丽丝', 'time': ''},
                        {'agent': '桃金娘', 'time': ''},
                        {'agent': 'Free', 'time': ''}
                        ],
        # 会客室
        'meeting': [{'agent': '陈', 'replacement': ['星极']},
                    {'agent': '红', 'replacement': ['远山']}, ],
        'room_1_1': [{'agent': '能天使', 'group': '', 'replacement': ['雪雉']},
                     {'agent': '空弦', 'group': '', 'replacement': ['龙舌兰']},
                     {'agent': '黑键', 'replacement': ['但书']}],
        'room_1_2': [{'agent': '稀音', 'group': '稀音', 'replacement': ['']},
                     {'agent': '红云', 'group': '稀音', 'Type': '', 'replacement': ['']},
                     {'agent': '帕拉斯', 'group': '稀音', 'time': '', 'replacement': ['']}],
        'room_1_3': [{'agent': '晨曦格雷伊', 'group': '异客', 'time': '', 'replacement': ['雷蛇']}],
        'room_2_1': [{'agent': '灰毫', 'group': '红松骑士', 'replacement': ['']},
                     {'agent': '远牙', 'group': '红松骑士', 'Type': '', 'replacement': ['']},
                     {'agent': '野鬃', 'group': '红松骑士', 'time': '', 'replacement': ['']}],
        'room_2_2': [{'agent': '迷迭香', 'group': '', 'replacement': ['']},
                     {'agent': '砾', 'group': '', 'Type': '', 'replacement': ['斑点']},
                     {'agent': '至简', 'group': '', 'time': '', 'replacement': ['夜烟']}],
        'room_2_3': [{'agent': '雷蛇', 'group': '', 'time': '', 'replacement': ['炎狱炎熔']}],
        'room_3_1': [{'agent': '异客', 'group': '异客', 'replacement': ['']},
                     {'agent': '森蚺', 'group': '异客', 'Type': '', 'replacement': ['']},
                     {'agent': '温蒂', 'group': '异客', 'time': '', 'replacement': ['']}],
        'room_3_2': [{'agent': '食铁兽', 'group': '', 'replacement': ['']},
                     {'agent': '断罪者', 'group': '', 'Type': '', 'replacement': ['']},
                     {'agent': '白雪', 'group': '', 'time': '', 'replacement': ['']}],
        'room_3_3': [{'agent': '澄闪', 'group': '', 'time': '', 'replacement': ['炎狱炎熔']}]
    }
}


def debuglog():
    '''
    在屏幕上输出调试信息，方便调试和报错
    '''
    logger.handlers[0].setLevel('DEBUG')


def savelog():
    '''
    指定日志和截屏的保存位置，方便调试和报错
    调试信息和截图默认保存在代码所在的目录下
    '''
    config.LOGFILE_PATH = './log'
    config.SCREENSHOT_PATH = './screenshot'
    config.SCREENSHOT_MAXNUM = 100
    init_fhlr()

def send_email(tasks):
    try:
        msg = MIMEMultipart()
        conntent = str(tasks)
        # 把内容加进去
        msg.attach(MIMEText(conntent, 'plain', 'utf-8'))
        msg['Subject'] = "任务数据"
        msg['From'] = email_address
        s = smtplib.SMTP_SSL("smtp.qq.com", 465)
        # 登录邮箱
        s.login(email_address, mail_pass)
        # 开始发送
        s.sendmail(email_address, to, msg.as_string())
        logger.info("邮件发送成功")
    except Exception as e:
        logger.error("邮件发送失败")

def simulate():
    '''
    具体调用方法可见各个函数的参数说明
    '''
    global ope_list, tasks, cuttent_base

    cli = Solver()
    # 第一次执行任务
    # datetime(2022, 10, 3, 3, 8, 59, 342380)
    # tasks = [{"plan": {'room_1_1': ['能天使','但书','龙舌兰']}, "time": datetime.now()}]
    # tasks = [{"plan":{"room_1_1":['图耶', '鸿雪', '但书']},"time":datetime.now()},
    #          {"plan":{'dormitory_1': ['迷迭香','菲亚梅塔'],'room_2_2': ['迷迭香','槐琥','砾']},"time":datetime(2022, 10, 3, 3, 15, 55, 342380)},
    #           {"plan":{'dormitory_1': ['夜莺', '菲亚梅塔','焰尾','Free','Free']},"time":datetime(2022, 10, 3, 15, 56, 59, 342380)}]

    tasks = []
    base_scheduler = BaseSchedulerSolver(cli.device,cli.recog)
    base_scheduler.operators = {}
    base_scheduler.global_plan = plan
    base_scheduler.current_base = {}
    base_scheduler.resting=[]
    base_scheduler.dorm_count=4
    base_scheduler.tasks = tasks
    # #cli.mail()  # 邮件
    while True:
        # output = cli.base_scheduler(tasks=tasks,plan=plan)  # 基建

        base_scheduler.run()
        tasks = base_scheduler.tasks
        # current_base =out_current_base
        if email_notification:
            # 发邮件
            send_email(tasks)
        logger.info(tasks)
        if len(tasks) == 0: continue
        sleep_time = (tasks[0]["time"] - datetime.now()).total_seconds()
        if sleep_time > 0:
            logger.info("休息: " + str((tasks[0]["time"] - datetime.now()).total_seconds()) + " 秒")
            time.sleep(sleep_time)


    # cli.credit()  # 信用
    # ope_lists = cli.ope(eliminate=True, plan=ope_lists)  # 行动，返回未完成的作战计划
    # cli.shop(shop_priority)  # 商店
    # cli.recruit()  # 公招
    # cli.mission()  # 任务

def schedule_task():
    """
    定期运行任务
    """
    schedule.every().day.at('07:00').do(simulate)
    schedule.every().day.at('19:00').do(simulate)
    while True:
        schedule.run_pending()
        time.sleep(60)


# debuglog()
# savelog()
simulate()
# schedule_task()
