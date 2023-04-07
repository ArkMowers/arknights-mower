import time
from datetime import datetime

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.strategy import Solver
from arknights_mower.utils.device import Device
from arknights_mower.utils.log import logger, init_fhlr
from arknights_mower.utils import config


email_config= {
    # 发信账户
    'account':"xxx@qq.com",
    # 在QQ邮箱“帐户设置-账户-开启SMTP服务”中，按照指示开启服务获得授权码
    'pass_code':'xxx',
    # 收件人邮箱
    'receipts':['任何邮箱'],
    # 是否提醒，暂时没用
    'notify':False,
    # 邮件主题
    'subject': '任务数据'
}
maa_config = {
    # 请设置为存放 dll 文件及资源的路径
    "maa_path":'F:\\MAA-v4.10.5-win-x64',
    # 请设置为存放 dll 文件及资源的路径
    "maa_adb_path":"D:\\Program Files\\Nox\\bin\\adb.exe",
    # adb 地址
    "maa_adb":['127.0.0.1:62001'],
    # maa 运行的时间间隔，以小时计
    "maa_execution_gap":4,
    # 以下配置，第一个设置为true的首先生效
    # 是否启动肉鸽
    "roguelike":False,
    # 是否启动生息演算
    "reclamation_algorithm":False,
    # 是否启动保全派驻
    "stationary_security_service":False,
    "last_execution": None,
    "weekly_plan":[{"weekday":"周一","stage":['AP-5'],"medicine":0},
                   {"weekday":"周二","stage":['CE-6'],"medicine":0},
                   {"weekday":"周三","stage":['1-7'],"medicine":0},
                   {"weekday":"周四","stage":['AP-5'],"medicine":0},
                   {"weekday":"周五","stage":['1-7'],"medicine":0},
                   {"weekday":"周六","stage":['AP-5'],"medicine":0},
                   {"weekday":"周日","stage":['AP-5'],"medicine":0}]
}

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
        # 中枢
        'central': [{'agent': '焰尾', 'group': '红松骑士', 'replacement': ["凯尔希","诗怀雅"]},
                    {'agent': '琴柳', 'group': '', 'replacement': ["凯尔希","阿米娅"]},
                    {'agent': '重岳', 'group': '夕', 'replacement': ["玛恩纳", "清道夫", "凯尔希", "阿米娅", '坚雷']},
                    {'agent': '夕', 'group': '夕', 'replacement': ["玛恩纳", "清道夫", "凯尔希", "阿米娅", '坚雷']},
                    {'agent': '令', 'group': '夕', 'replacement': ["玛恩纳", "清道夫", "凯尔希", "阿米娅", '坚雷']},
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
                        {'agent': '斥罪', 'group': '', 'replacement': []},
                        {'agent': '爱丽丝', 'group': '', 'replacement': []},
                        {'agent': '桃金娘', 'group': '', 'replacement': []},
                        {'agent': 'Free', 'group': '', 'replacement': []}
                        ],
        'dormitory_4': [{'agent': '波登可', 'group': '', 'replacement': []},
                        {'agent': '夜莺', 'group': '', 'replacement': []},
                        {'agent': '菲亚梅塔', 'group': '', 'replacement': ['迷迭香', '黑键', '絮雨','至简']},
                        {'agent': 'Free', 'group': '', 'replacement': []},
                        {'agent': 'Free', 'group': '', 'replacement': []}],
        'factory':[{'agent': '年', 'replacement': ['九色鹿','芳汀'], 'group': '夕'}],
        # 会客室
        'meeting': [{'agent': '陈', 'replacement': ['星极','远山'], 'group': ''},
                    {'agent': '红', 'replacement': ['远山','星极'], 'group': ''} ],
        'room_1_1': [{'agent': '黑键', 'group': '', 'replacement': []},
                     {'agent': '乌有', 'group': '夕', 'replacement': ['但书','图耶']},
                     {'agent': '空弦', 'group': '夕', 'replacement': ['龙舌兰', '鸿雪']}
                     # {'agent': '伺夜', 'group': '图耶', 'replacement': ['但书','能天使']},
                     # {'agent': '空弦', 'group': '图耶', 'replacement': ['龙舌兰', '雪雉']}
                     ],
        'room_1_2': [{'agent': '迷迭香', 'group': '', 'replacement': []},
                     {'agent': '砾', 'group': '', 'Type': '', 'replacement': ['斑点','夜烟']},
                     {'agent': '至简', 'group': '', 'replacement': []}],
        'room_1_3': [{'agent': '承曦格雷伊', 'group': '异客', 'replacement': ['炎狱炎熔','格雷伊']}],
        'room_2_2': [{'agent': '温蒂', 'group': '异客', 'replacement': ['火神']},
                     # {'agent': '异客', 'group': '异客', 'Type': '', 'replacement': ['贝娜']},
                     {'agent': '异客', 'group': '异客', 'Type': '', 'replacement': ['贝娜']},
                     {'agent': '森蚺', 'group': '异客', 'replacement': ['泡泡']}],
        'room_3_1': [{'agent': '稀音', 'group': '稀音', 'replacement': ['贝娜']},
                     {'agent': '帕拉斯', 'group': '稀音', 'Type': '', 'replacement': ['泡泡']},
                     {'agent': '红云', 'group': '稀音', 'replacement': ['火神']}],
        'room_2_3': [{'agent': '澄闪', 'group': '', 'replacement': ['炎狱炎熔', '格雷伊']}],
        'room_2_1': [{'agent': '食铁兽', 'group': '食铁兽', 'replacement': ['泡泡']},
                     {'agent': '断罪者', 'group': '食铁兽', 'replacement': ['火神']},
                     {'agent': '槐琥', 'group': '食铁兽', 'replacement': ['贝娜']}],
        'room_3_2': [{'agent': '灰毫', 'group': '红松骑士', 'replacement': ['贝娜']},
                     {'agent': '远牙', 'group': '红松骑士', 'Type': '', 'replacement': ['泡泡']},
                     {'agent': '野鬃', 'group': '红松骑士', 'replacement': ['火神']}],
        'room_3_3': [{'agent': '雷蛇', 'group': '', 'replacement': ['炎狱炎熔','格雷伊']}]
    }
}

# UpperLimit、LowerLimit：心情上下限
# ExhaustRequire：是否强制工作到红脸再休息
# ArrangeOrder：指定在宿舍外寻找干员的方式
# RestInFull：是否强制休息到24心情再工作，与ExhaustRequire一起帮助暖机类技能工作更长时间
# RestingPriority：休息优先级，低优先级不会使用单回技能。

agent_base_config = {
    "Default":{"UpperLimit": 24,"LowerLimit": 0,"ExhaustRequire": False,"ArrangeOrder":[2,"false"],"RestInFull": False},
    # 卡贸易站
    "令":{"UpperLimit": 11,"LowerLimit": 13,"ArrangeOrder":[2,"true"]},
    "夕": {"UpperLimit": 11,"ArrangeOrder":[2,"true"]},
    # 卡制造站
    #"令": {"UpperLimit": 11, "LowerLimit": 13, "ArrangeOrder": [2, "true"]},
    #"夕": {"UpperLimit": 11, "ArrangeOrder": [2, "true"]},
    "稀音":{"ExhaustRequire": True,"ArrangeOrder":[2,"true"],"RestInFull": True},
    "巫恋":{"ArrangeOrder":[2,"true"]},
    "柏喙":{"ExhaustRequire": True,"ArrangeOrder":[2,"true"]},
    "龙舌兰":{"ArrangeOrder":[2,"true"]},
    "空弦":{"ArrangeOrder":[2,"true"],"RestingPriority": "low"},
    "伺夜":{"ArrangeOrder":[2,"true"]},
    "绮良":{"ArrangeOrder":[2,"true"]},
    "但书":{"ArrangeOrder":[2,"true"]},
    "泡泡":{"ArrangeOrder":[2,"true"]},
    "火神":{"ArrangeOrder":[2,"true"]},
    "黑键":{"ArrangeOrder":[2,"true"]},
    "波登可":{"ArrangeOrder":[ 2, "false" ]},
    "夜莺":{"ArrangeOrder":[ 2, "false" ]},
    "菲亚梅塔":{"ArrangeOrder":[ 2, "false" ]},
    "流明":{"ArrangeOrder":[ 2, "false" ]},
    "蜜莓":{"ArrangeOrder":[ 2, "false" ]},
    "闪灵":{"ArrangeOrder":[ 2, "false" ]},
    "杜林":{"ArrangeOrder":[ 2, "false" ]},
    "褐果":{"ArrangeOrder":[ 2, "false" ]},
    "车尔尼":{"ArrangeOrder":[ 2, "false" ]},
    "安比尔":{"ArrangeOrder":[ 2, "false" ]},
    "爱丽丝":{"ArrangeOrder":[ 2, "false" ]},
    "桃金娘":{"ArrangeOrder":[ 2, "false" ]},
    "帕拉斯": {"RestingPriority": "low"},
    "红云": {"RestingPriority": "low","ArrangeOrder":[2,"true"]},
    "承曦格雷伊": {"ArrangeOrder":[2,"true"]},
    "乌有":{"ArrangeOrder":[2,"true"],"RestingPriority": "low"},
    "图耶":{"ArrangeOrder":[2,"true"]},
    "鸿雪": {"ArrangeOrder":[2,"true"]},
    "孑":{"ArrangeOrder":[2,"true"]},
    "清道夫":{"ArrangeOrder":[2,"true"]},
    "临光":{"ArrangeOrder":[2,"true"]},
    "杜宾":{"ArrangeOrder":[2,"true"]},
    "焰尾":{"RestInFull": True},
    "重岳":{"ArrangeOrder":[2,"true"]},
    "坚雷":{"ArrangeOrder":[2,"true"]},
    "年":{"RestingPriority": "low"}
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
    config.SCREENSHOT_MAXNUM = 1000
    config.ADB_DEVICE = maa_config['maa_adb']
    config.ADB_CONNECT = maa_config['maa_adb']
    config.MAX_RETRYTIME = 10
    config.PASSWORD = '你的密码'
    config.APPNAME = 'com.hypergryph.arknights'  # 官服
    #  com.hypergryph.arknights.bilibili   # Bilibili 服
    init_fhlr()


def inialize(tasks, scheduler=None):
    device = Device()
    cli = Solver(device)
    if scheduler is None:
        base_scheduler = BaseSchedulerSolver(cli.device, cli.recog)
        base_scheduler.package_name = config.APPNAME
        base_scheduler.operators = {}
        base_scheduler.global_plan = plan
        base_scheduler.current_base = {}
        base_scheduler.resting = []
        # 同时休息最大人数
        base_scheduler.max_resting_count = 4
        base_scheduler.tasks = tasks
        # 读取心情开关，有菲亚梅塔或者希望全自动换班得设置为 true
        base_scheduler.read_mood = True
        base_scheduler.scan_time = {}
        base_scheduler.last_room = ''
        base_scheduler.free_blacklist = free_blacklist
        base_scheduler.resting_treshhold = resting_treshhold
        base_scheduler.MAA = None
        base_scheduler.email_config = email_config
        base_scheduler.ADB_CONNECT = config.ADB_CONNECT[0]
        base_scheduler.maa_config = maa_config
        base_scheduler.error = False
        base_scheduler.drone_count_limit = 92  # 无人机高于于该值时才使用
        base_scheduler.agent_base_config = agent_base_config
        return base_scheduler
    else:
        scheduler.device = cli.device
        scheduler.recog = cli.recog
        scheduler.handle_error(True)
        return scheduler

def simulate():
    '''
    具体调用方法可见各个函数的参数说明
    '''
    global ope_list
    # 第一次执行任务
    # tasks = [{"plan": {'room_1_1': ['能天使','但书','龙舌兰']}, "time": datetime.now()}]
    tasks =[]
    reconnect_max_tries = 10
    reconnect_tries = 0
    base_scheduler = inialize(tasks)

    while True:
        try:
            if len(base_scheduler.tasks) > 0:
                (base_scheduler.tasks.sort(key=lambda x: x["time"], reverse=False))
                sleep_time = (base_scheduler.tasks[0]["time"] - datetime.now()).total_seconds()
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
                connected = False
                while not connected:
                    try:
                        base_scheduler = inialize([],base_scheduler)
                        break
                    except Exception as ce:
                        logger.error(ce)
                        time.sleep(5)
                        continue
                continue
            else:
                raise Exception(e)
        except Exception as E:
            logger.exception(f"程序出错--->{E}")
    # cli.credit()  # 信用
    # ope_lists = cli.ope(eliminate=True, plan=ope_lists)  # 行动，返回未完成的作战计划
    # cli.shop(shop_priority)  # 商店
    # cli.recruit()  # 公招
    # cli.mission()  # 任务


# debuglog()
savelog()
simulate()
