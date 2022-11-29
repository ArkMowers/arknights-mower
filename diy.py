import time
import schedule
from datetime import datetime

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.strategy import Solver
from arknights_mower.utils.device import Device
from arknights_mower.utils.log import logger, init_fhlr
from arknights_mower.utils import config


email_config= {
    'account':"xxx@qq.com",
    'pass_code':'从QQ邮箱帐户设置—>生成授权码',
    'receipts':['任何邮箱'],
    'notify':False
}

# 指定无人机加速第三层第三个房间的制造或贸易订单
drone_room = 'room_3_3'

# 指定关卡序列的作战计划
ope_lists = [['AP-5', 1], ['1-7', -1]]

# 使用信用点购买东西的优先级（从高到低）
shop_priority = ['招聘许可', '赤金', '龙门币', '初级作战记录', '技巧概要·卷2', '基础作战记录', '技巧概要·卷1']

# 公招选取标签时优先选择的干员的优先级（从高到低）
recruit_priority = ['因陀罗', '火神']

# Free (宿舍填充)干员安排黑名单
free_blacklist= []

# 干员宿舍回复阈值
    # 高效组心情低于 UpperLimit  * 阈值 (向下取整)的时候才会会安排休息
    # UpperLimit：默认24，特殊技能干员如夕，令可能会有所不同(设置在 agent-base.json 文件可以自行更改)
resting_treshhold = 0.5

# 全自动基建排班计划：
# 这里定义了一套全自动基建的排班计划 plan_1
# agent 为常驻高效组的干员名

# group 为干员编队，你希望任何编队的人一起上下班则给他们编一样的名字
    # 编队最大数不支持超过4个干员 否则可能会在计算自动排班的时候报错
# replacement 为替换组干员备选
    # 暖机干员的自动换班
        # 目前只支持一个暖机干员休息
        # ！！ 会吧其他正在休息的暖机干员赶出宿舍
    # 请尽量安排多的替换干员，且尽量不同干员的替换人员不冲突
    # 龙舌兰和但书默认为插拔干员 必须放在 replacement的第一位
    # 请把你所安排的替换组 写入replacement 否则程序可能报错
    # 替换组会按照从左到右的优先级选择可以编排的干员
    # 宿舍常驻干员不会被替换所以不需要设置替换组
        # 宿舍空余位置请编写为Free，请至少安排一个群补和一个单补 以达到最大恢复效率
        # 宿管必须安排靠左，后面为填充干员
        # 宿舍恢复速率务必1-4从高到低排列
    # 如果有菲亚梅塔则需要安排replacement 建议干员至少为三
        # 菲亚梅塔会从replacment里找最低心情的进行充能
plan = {
    # 阶段 1
    "default": "plan_1",
    "plan_1": {
        # 办公室
        'central': [{'agent': '焰尾', 'group': '红松骑士', 'replacement': ["玛恩纳", "清道夫", "临光", "杜宾", '坚雷','布丁']},
                    {'agent': '琴柳', 'group': '', 'replacement': ["玛恩纳", "清道夫", "临光", "杜宾", '坚雷']},
                    {'agent': '凯尔希', 'replacement': ["玛恩纳", "清道夫", "临光", "杜宾", '坚雷'], 'group': ''},
                    {'agent': '夕', 'group': '夕', 'replacement': ["玛恩纳", "清道夫", "临光", "杜宾", '坚雷']},
                    {'agent': '令', 'group': '夕', 'replacement': ["玛恩纳", "清道夫", "临光", "杜宾", '坚雷']},
                    ],
        'contact': [{'agent': '絮雨', 'group': '絮雨', 'replacement': []}],
        # 宿舍
        'dormitory_1': [{'agent': '流明', 'group': '', 'replacement': []},
                        {'agent': '闪灵', 'group': '', 'replacement': []},
                        {'agent': 'Free', 'group': '', 'replacement': []},
                        {'agent': 'Free', 'group': '', 'replacement': []},
                        {'agent': 'Free', 'group': '', 'replacement': []}
                        ],
        'dormitory_2': [{'agent': '杜林', 'group': '', 'replacement': []},
                        {'agent': '蜜莓', 'group': '', 'replacement': []},
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
        'meeting': [{'agent': '陈', 'replacement': ['星极','远山'], 'group': ''},
                    {'agent': '红', 'replacement': ['远山','星极'], 'group': ''}, ],
        'room_1_1': [{'agent': '黑键', 'group': '', 'replacement': []},
                     {'agent': '图耶', 'group': '图耶', 'replacement': ['但书','空弦','雪雉','能天使']},
                     {'agent': '鸿雪', 'group': '图耶', 'replacement': ['龙舌兰', '空弦','能天使', '雪雉']}
                     ],
        'room_1_2': [{'agent': '迷迭香', 'group': '', 'replacement': []},
                     {'agent': '砾', 'group': '', 'Type': '', 'replacement': ['夜烟', '斑点']},
                     {'agent': '至简', 'group': '', 'replacement': ['夜烟', '斑点']}],
        'room_1_3': [{'agent': '承曦格雷伊', 'group': '异客', 'replacement': ['炎狱炎熔','格雷伊']}],
        'room_2_2': [{'agent': '温蒂', 'group': '异客', 'replacement': ['调香师','水月','香草']},
                     {'agent': '异客', 'group': '异客', 'Type': '', 'replacement': ['调香师','水月','香草']},
                     {'agent': '森蚺', 'group': '异客', 'replacement': ['调香师','水月','香草']}],
        'room_3_1': [{'agent': '稀音', 'group': '稀音', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3']},
                     {'agent': '帕拉斯', 'group': '稀音', 'Type': '', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3']},
                     {'agent': '红云', 'group': '稀音', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3']}],
        'room_2_3': [{'agent': '澄闪', 'group': '', 'replacement': ['炎狱炎熔', '格雷伊']}],
        'room_2_1': [{'agent': '食铁兽', 'group': '', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3']},
                     {'agent': '断罪者', 'group': '', 'Type': '', 'replacement':['霜叶', '红豆', '白雪', 'Castle-3']},
                     {'agent': '槐琥', 'group': '', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3']}],
        'room_3_2': [{'agent': '灰毫', 'group': '红松骑士', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3']},
                     {'agent': '远牙', 'group': '红松骑士', 'Type': '', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3']},
                     {'agent': '野鬃', 'group': '红松骑士', 'replacement': ['霜叶', '红豆', '白雪', 'Castle-3']}],
        'room_3_3': [{'agent': '雷蛇', 'group': '', 'replacement': ['炎狱炎熔','格雷伊']}]
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

def inialize(tasks=[]):
    device = Device()
    cli = Solver(device)
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
    base_scheduler.last_room = ''
    base_scheduler.free_blacklist = free_blacklist
    base_scheduler.resting_treshhold=resting_treshhold
    base_scheduler.MAA = None
    base_scheduler.email_config = email_config
    return base_scheduler
def simulate():
    '''
    具体调用方法可见各个函数的参数说明
    '''
    global ope_list
    # 第一次执行任务
    # tasks = [{"plan": {'room_1_1': ['能天使','但书','龙舌兰']}, "time": datetime.now()}]
    tasks=[]
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
                logger.info(base_scheduler.tasks)
                base_scheduler.send_email(base_scheduler.tasks)
                # 如果任务间隔时间超过9分钟则启动MAA
                if sleep_time > 540:
                    base_scheduler.maa_plan_solver()
                elif  sleep_time > 0 : time.sleep(sleep_time)
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


# debuglog()
savelog()
simulate()
