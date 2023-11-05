import time
from datetime import datetime
import atexit
import json
import os
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.strategy import Solver
from arknights_mower.utils.device import Device
from arknights_mower.utils.email import task_template
from arknights_mower.utils.log import logger, init_fhlr
from arknights_mower.utils import config, rapidocr
from arknights_mower.utils.simulator import restart_simulator
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.logic_expression import LogicExpression
# 下面不能删除
from arknights_mower.utils.operators import Operators, Operator, Dormitory
from arknights_mower.utils.scheduler_task import SchedulerTask,TaskTypes

send_message_config= {
    # QQ邮箱通知配置
    "email_config":{
        # 发信账户
        'account':"xxx@qq.com",
        # 在QQ邮箱“帐户设置-账户-开启SMTP服务”中，按照指示开启服务获得授权码
        'pass_code':'xxx',
        # 收件人邮箱
        'receipts':['任何邮箱'],
        # 是否启用邮件提醒
        'mail_enable':False,
        # 邮件主题
        'subject': '任务数据'
    },
    # Server酱通知配置
    "serverJang_push_config":{
        # 是否启用Server酱提示
        "server_push_enable": False,
        # Key值
        "sendKey":'xxx'
    }
}
maa_config = {
    "maa_enable": True,
    # 请设置为存放 dll 文件及资源的路径
    "maa_path": 'F:\\MAA-v4.20.0-win-x64',
    # 请设置为存放 dll 文件及资源的路径
    "maa_adb_path": "F:\\MAA-v4.20.0-win-x64\\adb\\platform-tools\\adb.exe",
    # adb 地址
    "maa_adb": ['127.0.0.1:16384'],
    # maa 运行的时间间隔，以小时计
    "maa_execution_gap": 4,
    # 以下配置，第一个设置为true的首先生效
    # 是否启动肉鸽
    "roguelike": False,
    # 是否启动生息演算
    "reclamation_algorithm": False,
    # 是否启动保全派驻
    "stationary_security_service": False,
    # 保全派驻类别 1-2
    "sss_type": 2,
    # 导能单元类别 1-3
    "ec_type": 1,
    "copilot_file_location": "C:\\Users\\frank\\Desktop\\MAACopilot_保全派驻-阿尔斯特甜品制作平台-澄闪铃兰双核.json",
    "copilot_loop_times": 10,
    "last_execution": datetime.now(),
    # " last_execution": datetime(2023,8,16,9,0),
    "blacklist": "家具,碳,加急许可",
    "rogue_theme": "Sami",
    "buy_first": "招聘许可",
    "recruitment_permit": 30,
    "credit_fight": True,
    "recruitment_time": None,
    'mall_ignore_when_full': True,
    "touch_option": "maatouch",
    "conn_preset": "General",
    "rogue": {
        "squad": "指挥分队",
        "roles": "取长补短",
        "use_support": False,
        "core_char": "",
        "use_nonfriend_support": False,
        "mode": 0,
        "investment_enabled": True,
        "stop_when_investment_full": False,
        "refresh_trader_with_dice": True
    },
    "sleep_min": "",
    "sleep_max": "",
    "expiring_medicine": True,
    "weekly_plan": [{"weekday": "周一", "stage": ['PR-A-2'], "medicine": 0},
                    {"weekday": "周二", "stage": ['Annihilation', 'PR-B-2'], "medicine": 0},
                    {"weekday": "周三", "stage": ['Annihilation', 'PR-D-2'], "medicine": 0},
                    {"weekday": "周四", "stage": ['AP-5'], "medicine": 0},
                    {"weekday": "周五", "stage": ['Annihilation', '1-7'], "medicine": 0},
                    {"weekday": "周六", "stage": ['AP-5'], "medicine": 0},
                    {"weekday": "周日", "stage": ['AP-5'], "medicine": 0}],
}

# 模拟器相关设置
simulator = {
    "name": "MuMu12",
    # 多开编号，在模拟器助手最左侧的数字
    "index": 0,
    # 用于执行模拟器命令
    "simulator_folder": "D:\\Program Files\\Netease\\MuMuPlayer-12.0\\shell\\"
}

# Free (宿舍填充)干员安排黑名单
free_blacklist = ["艾丽妮", "但书", "龙舌兰"]

# 干员宿舍回复阈值
    # 高效组心情低于 UpperLimit  * 阈值 (向下取整)的时候才会会安排休息
    # UpperLimit：默认24，特殊技能干员如夕，令可能会有所不同(设置在 agent-base.json 文件可以自行更改)
resting_threshold = 0.5

# 跑单如果all in 贸易站则 不需要修改设置
# 如果需要无人机加速其他房间则可以修改成房间名字如 'room_1_1'
drone_room = 'room_1_2'
# 无人机执行间隔时间 （小时）
drone_execution_gap = 4

reload_room = []

# 基地数据json文件保存名
state_file_name = 'state.json'

# 邮件时差调整
timezone_offset = 0

# 全自动基建排班计划：
# 这里定义了一套全自动基建的排班计划 plan_1
# agent 为常驻高效组的干员名

# group 为干员编队，你希望任何编队的人一起上下班则给他们编一样的名字
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

agent_base_config = PlanConfig("稀音,黑键,承曦格雷伊,焰尾,伊内丝", "稀音,柏喙,伊内丝", "伺夜,帕拉斯,雷蛇,澄闪,红云,乌有,年,远牙,阿米娅,桑葚,截云",ling_xi=2, free_blacklist="艾丽妮,但书,龙舌兰")

plan_config = {"room_1_1": [Room("绮良", "", []),
                            Room("黑键", "黑键", ["龙舌兰", "伺夜"]),
                            Room("巫恋", "黑键", ["但书", "空弦"])],
               "room_2_1": [Room("砾", "砾", ["夜烟"]),
                            Room("斑点", "斑点", ["夜烟"]),
                            Room("苍苔", "", [])],
               "room_3_1": [Room("至简", "", ["夜烟", "梅尔"]),
                            Room("淬羽赫默", "多萝西", ["泡泡"]),
                            Room("多萝西", "多萝西", ["火神"])],
               "room_3_2": [Room("乌有", "乌有", ["空弦"]),
                            Room("图耶", "", ["但书"]),
                            Room("鸿雪", "", ["龙舌兰", "能天使"])],
               "room_3_3": [Room("雷蛇", "澄闪", ["炎狱炎熔", "格雷伊"])],
               "room_1_2": [Room("槐琥", "", ["梅尔"]),
                            Room("迷迭香", "黑键", ["梅尔", "夜烟"]),
                            Room("截云", "乌有", ["梅尔", "夜烟"])],
               "room_1_3": [Room("承曦格雷伊", "自动化", ["炎狱炎熔", "格雷伊"])],
               "room_2_2": [Room("温蒂", "自动化", ["泡泡"]),
                            Room("森蚺", "自动化", ["火神"]),
                            Room("清流", "自动化", ["贝娜"])],
               "room_2_3": [Room("澄闪", "澄闪", ["炎狱炎熔", "格雷伊"])],
               "central": [Room("阿米娅", "", ["诗怀雅"]),
                           Room("琴柳", "乌有", ["清道夫", "杜宾", "玛恩纳", "临光"]),
                           Room("重岳", "乌有", ["杜宾"]),
                           Room("夕", "乌有", ["玛恩纳"]),
                           Room("令", "乌有", ["临光"])],
               "dormitory_1": [Room("流明", "", []),
                               Room("闪灵", "", []),
                               Room("Free", "", []),
                               Room("Free", "", []),
                               Room("Free", "", [])],
               "dormitory_2": [Room("杜林", "", []),
                               Room("断罪者", "", []),
                               Room("褐果", "", []),
                               Room("Free", "", []),
                               Room("Free", "", [])],
               "dormitory_3": [Room("斥罪", "", []),
                               Room("蜜莓", "", []),
                               Room("桃金娘", "", []),
                               Room("爱丽丝", "", []),
                               Room("Free", "", [])],
               "dormitory_4": [Room("纯烬艾雅法拉", "", []),
                               Room("车尔尼", "", []),
                               Room("菲亚梅塔", "", ["绮良", "鸿雪", "图耶", "苍苔", "至简"]),
                               Room("Free", "", []),
                               Room("Free", "", [])],
               "meeting": [Room("伊内丝", "", ["红"]),
                           Room("见行者", "", ["陈"])],
               "contact": [Room("桑葚", "乌有", ["絮雨"])],
               "factory": [Room("年", "乌有", ["九色鹿"])],
               }
backup_plan1_config = {"central": [Room("阿米娅", "", ["诗怀雅"]),
                                   Room("清道夫", "", ["诗怀雅"]),
                                   Room("杜宾", "", ["泡泡"]),
                                   Room("玛恩纳", "", ["火神"]),
                                   Room("森蚺", "", ["诗怀雅"])],
                       "room_2_2": [Room("温蒂", "", ["泡泡"]),
                                    Room("掠风", "", ["贝娜"]),
                                    Room("清流", "", ["火神"])],
                       "room_1_3": [Room("炎狱炎熔", "自动化", ["承曦格雷伊"])],
                       "room_2_3": [Room("澄闪", "", ["承曦格雷伊", ])],
                       "room_3_3": [Room("雷蛇", "", ["承曦格雷伊"])],
                       }

agent_base_config0 = PlanConfig("稀音,黑键,焰尾,伊内丝", "稀音,柏喙,伊内丝", "伺夜,帕拉斯,雷蛇,澄闪,红云,乌有,年,远牙,阿米娅,桑葚,截云,掠风", ling_xi=2)

plan = {
    # 阶段 1
    "default_plan": Plan(plan_config, agent_base_config),
    # "backup_plans": [Plan(backup_plan1_config, agent_base_config0,
    #                       trigger=LogicExpression("op_data.operators['令'].current_room.startswith('dorm')", "and",
    #                                               LogicExpression(
    #                                                   "op_data.operators['温蒂'].current_mood() - op_data.operators['承曦格雷伊'].current_mood()",
    #                                                   ">", "4")),
    #                       task={'dormitory_2': ['Current', 'Current', 'Current', 'Current', '承曦格雷伊']})]
    "backup_plans":[]
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
    config.LOGFILE_PATH = './log1'
    config.SCREENSHOT_PATH = './screenshot1'
    config.SCREENSHOT_MAXNUM = 200
    config.ADB_DEVICE = maa_config['maa_adb']
    config.ADB_CONNECT = maa_config['maa_adb']
    config.MAX_RETRYTIME = 3
    config.PASSWORD = '你的密码'
    config.APPNAME = 'com.hypergryph.arknights'  # 官服
    config.TAP_TO_LAUNCH["enable"] = False
    config.TAP_TO_LAUNCH["x"], config.TAP_TO_LAUNCH["y"] = 0, 0
    #  com.hypergryph.arknights.bilibili   # Bilibili 服
    config.ADB_BINARY = ['F:\\MAA-v4.20.0-win-x64\\adb\\platform-tools\\adb.exe']
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
        base_scheduler.tasks = tasks
        # 读取心情开关，有菲亚梅塔或者希望全自动换班得设置为 true
        base_scheduler.read_mood = True
        base_scheduler.last_room = ''
        base_scheduler.free_blacklist = free_blacklist
        base_scheduler.resting_threshold = resting_threshold
        base_scheduler.MAA = None
        base_scheduler.send_message_config = send_message_config
        base_scheduler.ADB_CONNECT = config.ADB_CONNECT[0]
        base_scheduler.maa_config = maa_config
        base_scheduler.error = False
        base_scheduler.drone_count_limit = 102  # 无人机高于于该值时才使用
        base_scheduler.drone_room = drone_room
        base_scheduler.drone_execution_gap = drone_execution_gap
        base_scheduler.run_order_delay = 5  # 跑单提前10分钟运行
        base_scheduler.reload_room = reload_room
        return base_scheduler
    else:
        scheduler.device = cli.device
        scheduler.recog = cli.recog
        scheduler.handle_error(True)
        return scheduler


def save_state():
    with open(state_file_name, 'w') as f:
        if base_scheduler is not None and base_scheduler.op_data is not None:
            json.dump(vars(base_scheduler.op_data), f, default=str)


def load_state():
    if not os.path.exists(state_file_name):
        return None

    with open(state_file_name, 'r') as f:
        state = json.load(f)
    operators = {k: eval(v) for k, v in state['operators'].items()}
    for k, v in operators.items():
        if not v.time_stamp == 'None':
            v.time_stamp = datetime.strptime(v.time_stamp, '%Y-%m-%d %H:%M:%S.%f')
        else:
            v.time_stamp = None
    return operators


def simulate():
    '''
    具体调用方法可见各个函数的参数说明
    '''
    global ope_list, base_scheduler
    # 第一次执行任务
    taskstr = "SchedulerTask(time='2023-09-12 21:35:43.278494',task_plan={},task_type=TaskTypes.MAA_MALL,meta_data='')"
    tasks = [eval(t) for t in taskstr.split("||")]
    for t in tasks:
        t.time = datetime.strptime(t.time, '%Y-%m-%d %H:%M:%S.%f')
    reconnect_max_tries = 10
    reconnect_tries = 0
    success = False
    while not success:
        try:
            base_scheduler = inialize(tasks)
            success = True
        except Exception as E:
            reconnect_tries += 1
            if reconnect_tries < 3:
                restart_simulator(simulator)
                continue
            else:
                raise E
    if base_scheduler.recog.h != 1080 or base_scheduler.recog.w != 1920:
        logger.error("模拟器分辨率不为1920x1080")
        return
    validation_msg = base_scheduler.initialize_operators()
    if validation_msg is not None:
        logger.error(validation_msg)
        return
    _loaded_operators = load_state()
    if _loaded_operators is not None:
        for k, v in _loaded_operators.items():
            if k in base_scheduler.op_data.operators and not base_scheduler.op_data.operators[k].room.startswith(
                    "dorm"):
                # 只复制心情数据
                base_scheduler.op_data.operators[k].mood = v.mood
                base_scheduler.op_data.operators[k].time_stamp = v.time_stamp
                base_scheduler.op_data.operators[k].depletion_rate = v.depletion_rate
                base_scheduler.op_data.operators[k].current_room = v.current_room
                base_scheduler.op_data.operators[k].current_index = v.current_index

    if len(base_scheduler.op_data.backup_plans)>0 :
        for idx, backplan in enumerate(base_scheduler.op_data.backup_plans):
            validation_msg = base_scheduler.op_data.swap_plan(idx,True)
            if validation_msg is not None:
                logger.error(f"替换排班验证错误：{validation_msg}")
                return
            base_scheduler.op_data.swap_plan(-1,True)
    while True:
        try:
            if len(base_scheduler.tasks) > 0:
                (base_scheduler.tasks.sort(key=lambda x: x.time, reverse=False))
                sleep_time = (base_scheduler.tasks[0].time - datetime.now()).total_seconds()
                logger.info('||'.join([str(t) for t in base_scheduler.tasks]))
                base_scheduler.send_message(
                    task_template.render(tasks=[obj.format(timezone_offset) for obj in base_scheduler.tasks]), '',
                    'html')
                # 如果任务间隔时间超过9分钟则启动MAA
                if sleep_time > 540:
                    base_scheduler.maa_plan_solver()
                elif sleep_time > 0:
                    time.sleep(sleep_time)
            if len(base_scheduler.tasks) > 0 and base_scheduler.tasks[0].type.value.split('_')[0] == 'maa':
                base_scheduler.maa_plan_solver((base_scheduler.tasks[0].type.value.split('_')[1]).split(','), one_time=True)
                continue
            base_scheduler.run()
            reconnect_tries = 0
        except (ConnectionError, ConnectionAbortedError, AttributeError) as e:
            reconnect_tries += 1
            if reconnect_tries < reconnect_max_tries:
                logger.warning(f'连接端口断开....正在重连....')
                connected = False
                while not connected:
                    try:
                        base_scheduler = inialize([], base_scheduler)
                        break
                    except (ConnectionError, ConnectionAbortedError, AttributeError) as ce:
                        logger.error(ce)
                        restart_simulator(simulator)
                        continue
                continue
            else:
                raise Exception(e)
        except RuntimeError as re:
            restart_simulator(simulator)
        except Exception as E:
            logger.exception(f"程序出错--->{E}")

    # cli.credit()  # 信用
    # ope_lists = cli.ope(eliminate=True, plan=ope_lists)  # 行动，返回未完成的作战计划
    # cli.shop(shop_priority)  # 商店
    # cli.recruit()  # 公招
    # cli.mission()  # 任务


# debuglog()
atexit.register(save_state)
savelog()
rapidocr.initialize_ocr()
simulate()
