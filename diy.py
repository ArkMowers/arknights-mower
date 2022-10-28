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

# 全自动基建排班计划：
# 这里定义了一套全自动基建的排班计划 plan_1
# agent 为常驻高效组的干员名
    # 宿舍空余位置请编写为Free，请至少安排一个群补和一个单补 以达到最大恢复效率
# group 为干员编队，你希望任何编队的人一起上下班则给他们编一样的名字
    # 建议编队最大数不超过4个干员 否则可能会在计算自动排班的时候报错
# replacement 为替换组干员备选
    # 龙舌兰和但书默认为插拔干员 必须放在 replacement的第一位
    # 请把你所安排的替换组 写入replacement 否则程序可能报错
    # 替换组会按照从左到右的优先级选择可以编排的干员
    # 宿舍常驻干员不会被替换所以不需要设置替换组
    # 如果有菲亚梅塔则需要安排replacement 建议干员至少为三
        # 菲亚梅塔会从replacment里找最低心情的进行充能
plan = {
    # 阶段 1
    "default": "plan_1",
    "plan_1": {
        # 办公室
        'central': [{'agent': '焰尾', 'group': '红松骑士', 'replacement': ["玛恩纳", "清道夫", "临光", "杜宾", '坚雷']},
                    {'agent': '琴柳', 'group': '絮雨', 'replacement': ["玛恩纳", "清道夫", "临光", "杜宾", '坚雷']},
                    {'agent': '凯尔希', 'replacement': ["玛恩纳", "清道夫", "临光", "杜宾", '坚雷'], 'group': ''},
                    {'agent': '夕', 'group': '夕', 'replacement': ["玛恩纳", "清道夫", "临光", "杜宾", '坚雷']},
                    {'agent': '令', 'group': '夕', 'replacement': ["玛恩纳", "清道夫", "临光", "杜宾", '坚雷']},
                    ],
        'contact': [{'agent': '絮雨', 'group': '絮雨', 'replacement': ['艾雅法拉']}],
        # 宿舍
        'dormitory_1': [{'agent': '流明', 'group': '', 'replacement': []},
                        {'agent': '蜜莓', 'group': '', 'replacement': []},
                        {'agent': 'Free', 'group': '', 'replacement': []},
                        {'agent': 'Free', 'group': '', 'replacement': []},
                        {'agent': 'Free', 'group': '', 'replacement': []}
                        ],
        'dormitory_2': [{'agent': '闪灵', 'group': '', 'replacement': []},
                        {'agent': '杜林', 'group': '', 'replacement': []},
                        {'agent': '褐果', 'group': '', 'replacement': []},
                        {'agent': 'Free', 'group': '', 'replacement': []},
                        {'agent': 'Free', 'group': '', 'replacement': []}
                        ],
        'dormitory_3': [{'agent': '车尔尼', 'group': '', 'replacement': []},
                        {'agent': '安比尔', 'group': '', 'replacement': []},
                        {'agent': '爱丽丝', 'group': '', 'replacement': []},
                        {'agent': '桃金娘', 'group': '', 'replacement': []},
                        {'agent': 'Free', 'group': '', 'replacement': []}
                        ],
        'dormitory_4': [{'agent': '波登可', 'group': '', 'replacement': []},
                        {'agent': '夜莺', 'group': '', 'replacement': []},
                        {'agent': '菲亚梅塔', 'group': '', 'replacement': ['迷迭香', '黑键', '絮雨']},
                        {'agent': 'Free', 'group': '', 'replacement': []},
                        {'agent': 'Free', 'group': '', 'replacement': []}],
        # 会客室
        'meeting': [{'agent': '陈', 'replacement': ['星极'], 'group': ''},
                    {'agent': '红', 'replacement': ['远山'], 'group': ''}, ],
        'room_1_1': [{'agent': '能天使', 'group': '', 'replacement': ['能天使', '雪雉']},
                     {'agent': '空弦', 'group': '', 'replacement': ['龙舌兰', '能天使', '雪雉']},
                     {'agent': '黑键', 'group': '', 'replacement': ['但书']}],
        'room_1_2': [{'agent': '迷迭香', 'group': '', 'replacement': ['']},
                     {'agent': '砾', 'group': '', 'Type': '', 'replacement': ['夜烟', '斑点']},
                     {'agent': '至简', 'group': '', 'replacement': ['夜烟', '斑点']}],
        'room_1_3': [{'agent': '承曦格雷伊', 'group': '异客', 'replacement': ['炎狱炎熔', '雷蛇', '澄闪']}],
        'room_2_1': [{'agent': '异客', 'group': '异客', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3', '火神','泡泡']},
                     {'agent': '森蚺', 'group': '异客', 'Type': '', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3', '火神','泡泡']},
                     {'agent': '温蒂', 'group': '异客', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3', '火神','泡泡']}],
        'room_2_2': [{'agent': '稀音', 'group': '稀音', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3', '火神','泡泡']},
                     {'agent': '红云', 'group': '稀音', 'Type': '', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3', '火神','泡泡']},
                     {'agent': '帕拉斯', 'group': '稀音', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3', '火神','泡泡']}],
        'room_2_3': [{'agent': '澄闪', 'group': '', 'replacement': ['炎狱炎熔', '雷蛇']}],
        'room_3_1': [{'agent': '食铁兽', 'group': '', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3', '火神','泡泡']},
                     {'agent': '断罪者', 'group': '', 'Type': '', 'replacement': ['炎狱炎熔', '雷蛇', '澄闪']},
                     {'agent': '槐琥', 'group': '', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3', '火神','泡泡']}],
        'room_3_2': [{'agent': '灰毫', 'group': '红松骑士', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3', '火神','泡泡']},
                     {'agent': '远牙', 'group': '红松骑士', 'Type': '', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3', '火神','泡泡']},
                     {'agent': '野鬃', 'group': '红松骑士', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3', '火神','泡泡']}],
        'room_3_3': [{'agent': '雷蛇', 'group': '', 'replacement': ['炎狱炎熔', '澄闪','Lancet-2']}]
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
    config.ADB_DEVICE = ['127.0.0.1:62001']
    config.ADB_CONNECT = ['127.0.0.1:62001']
    config.PASSWORD = '你的密码'
    init_fhlr()

def send_email(tasks):
    try:
        msg = MIMEMultipart()
        conntent = str(tasks)
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

def inialize(tasks=[]):
    cli = Solver()
    base_scheduler = BaseSchedulerSolver(cli.device,cli.recog)
    base_scheduler.operators = {}
    base_scheduler.global_plan = plan
    base_scheduler.current_base = {}
    base_scheduler.resting=[]
    base_scheduler.dorm_count=4
    base_scheduler.tasks = tasks
    # 读取心情开关，有菲亚梅塔或者希望全自动换班得设置为 true
    base_scheduler.read_mood = True
    base_scheduler.scan_time = {}
    # base_scheduler.current_base={'central': [{'mood': 12, 'agent': '凯尔希'}, {'mood': 12, 'agent': '琴柳'}, {'mood': 7, 'agent': '焰尾'}, {'mood': 7, 'agent': '令'}, {'mood': 20, 'agent': '夕'}], 'meeting': [{'mood': 13, 'agent': '红'}, {'mood': 15, 'agent': '陈'}], 'room_1_1': [{'mood': 19, 'agent': '能天使'}, {'mood': 19, 'agent': '黑键'}, {'mood': 8, 'agent': '空弦'}], 'room_1_2': [{'mood': 8, 'agent': '迷迭香'}, {'mood': 12, 'agent': '砾'}, {'mood': 23, 'agent': '槐琥'}], 'room_1_3': [{'mood': 12, 'agent': '雷蛇'}], 'dormitory_1': [{'mood': 24, 'agent': '流明'}, {'mood': 24, 'agent': '蜜莓'}, {'mood': 12, 'agent': '承曦格雷伊'}, {'mood': 24, 'agent': '夜烟'}, {'mood': 24, 'agent': '霜叶'}], 'room_2_1': [{'mood': 10, 'agent': '帕拉斯'}, {'mood': 0, 'agent': '稀音'}, {'mood': 10, 'agent': '红云'}], 'room_2_2': [{'mood': 8, 'agent': '远牙'}, {'mood': 8, 'agent': '野鬃'}, {'mood': 9, 'agent': '灰毫'}], 'room_2_3': [{'mood': 12, 'agent': '澄闪'}], 'dormitory_2': [{'mood': 24, 'agent': '闪灵'}, {'mood': 24, 'agent': '杜林'}, {'mood': 24, 'agent': 'Castle-3'}, {'mood': 24, 'agent': 'Lancet-2'}, {'mood': 13, 'agent': '温蒂'}], 'contact': [{'mood': 12, 'agent': '絮雨'}], 'room_3_1': [{'mood': 22, 'agent': '食铁兽'}, {'mood': 20, 'agent': '断罪者'}, {'mood': 18, 'agent': '至简'}], 'room_3_2': [{'mood': 23, 'agent': '白雪'}, {'mood': 21, 'agent': '泡泡'}, {'mood': 21, 'agent': '火神'}], 'room_3_3': [{'mood': 23, 'agent': '炎狱炎熔'}], 'dormitory_3': [{'mood': 24, 'agent': '车尔尼'}, {'mood': 24, 'agent': '安比尔'}, {'mood': 24, 'agent': '爱丽丝'}, {'mood': 24, 'agent': '星极'}, {'mood': 13, 'agent': '森蚺'}], 'dormitory_4': [{'mood': 22, 'agent': '菲亚梅塔'}, {'mood': 24, 'agent': '夜莺'}, {'mood': 24, 'agent': '波登可'}, {'mood': 24, 'agent': '玛恩纳'}, {'mood': 13, 'agent': '异客'}]}
    return base_scheduler
def simulate():
    '''
    具体调用方法可见各个函数的参数说明
    '''
    global ope_list

    # 第一次执行任务
    # datetime(2022, 10, 3, 3, 8, 59, 342380)
    # tasks = [{"plan": {'room_1_1': ['能天使','但书','龙舌兰']}, "time": datetime.now()}]
    tasks =  [#{'time': datetime(2022, 10, 20, 18, 25, 51, 268286), 'plan': {'room_1_1': ['能天使', '龙舌兰', '但书']}},
               #{'time': datetime(2022, 10, 20, 19, 00, 31, 511427), 'plan':{'dormitory_4': ['迷迭香', '菲亚梅塔']} },
             #  {'time': datetime(2022, 10, 21, 1, 33, 31, 118454), 'plan': {'central': ['焰尾','布丁','森蚺','夕','令'],'dormitory_1': ['流明','蜜莓','红','澄闪', '凯尔希']
             #,'dormitory_2': ['凛冬', '爱丽丝', '车尔尼', '星极', '香草']}},
             # ,'dormitory_2': ['闪灵', '杜林', '陈', '炎狱炎熔', '香草'], 'meeting':['星极','远山'],'dormitory_4': ['迷迭香', '菲亚梅塔']}}
            #{'time': datetime(2022, 10, 20, 0, 3, 31, 118454), 'plan': {'room_1_1': ['能天使', '龙舌兰', '但书']}},
             # {'time': datetime(2022, 10, 20, 3, 3, 20, 147573), 'plan': {'dormitory_4': ['絮雨', '菲亚梅塔']}},
#        {'time': datetime(2022, 10, 20, 23, 25, 5, 383340), 'plan': {'room_1_1': ['能天使', '龙舌兰', '但书']}},
            #{'time': datetime(2022, 10, 21, 1, 32, 20, 147573), 'plan': {'room_2_2': ['灰毫', '远牙', '野鬃'],'central': ['焰尾', '琴柳', '凯尔希','夕', '令'],
          #   'dormitory_1': ['流明', '蜜莓','正义骑士号','空','阿米娅'], 'dormitory_4': ['波登可', '夜莺', '菲亚梅塔','布丁','斑点'], 'dormitory_3': ['车尔尼', '安比尔', '爱丽丝', '凛冬','Lancet-2'] }},
         {'time': datetime(2022, 10, 21, 2, 34, 20, 147573), 'plan': {'room_3_1': ['食铁兽', '至简', '断罪者'], 'dormitory_2': ['闪灵','杜林','四月','香草','白雪']}}
              ]
    tasks= []
    reconnect_max_tries = 10
    reconnect_tries = 0
    base_scheduler = inialize(tasks)

    # #cli.mail()  # 邮件
    while True:
        # output = cli.base_scheduler(tasks=tasks,plan=plan)  # 基建
        try:
            if len(base_scheduler.tasks) > 0:
                (base_scheduler.tasks.sort(key=lambda x: x["time"], reverse=False))
                sleep_time = (tasks[0]["time"] - datetime.now()).total_seconds()
                if email_notification:
                    # 发邮件
                    send_email(base_scheduler.tasks)
                logger.info(base_scheduler.tasks)
                if sleep_time > 0:
                    logger.info("休息: " + str((tasks[0]["time"] - datetime.now()).total_seconds()) + " 秒")
                    time.sleep(sleep_time)
            base_scheduler.run()
            reconnect_tries = 0
        except ConnectionError as e:
            reconnect_tries +=1
            if reconnect_tries < reconnect_max_tries:
                logger.warning(f'连接端口断开....正在重连....')
                base_scheduler = inialize(base_scheduler.tasks)
                continue
            else:
                raise Exception(e)
        except Exception as E:
            logger.error(f"程序出错--->{E}")
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
savelog()
simulate()
# schedule_task()
