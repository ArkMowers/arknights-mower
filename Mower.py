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
        'recipients':['任何邮箱'],
        # 是否启用邮件提醒
        'mail_enable':False,
        # 邮件主题
        'subject': '任务数据',
        'custom_smtp_server':{
            "enable":False
        }
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
    "last_execution": None,
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
    "eat_stone": False
}
recruit_config = {
    "recruit_enable": True,
    "permit_target": 30,
    "recruit_robot": False,
    "recruitment_time": None,
    "recruit_execution_gap": 2,
    "recruit_auto_5": True,
    "recruit_auto_only5": False,
    "recruit_email_enable": True,
    "last_execution": None,
}
# 模拟器相关设置
simulator = {
    "name": "MuMu12",
    # 多开编号，在模拟器助手最左侧的数字
    "index": 0,
    # 用于执行模拟器命令
    "simulator_folder": "D:\\Program Files\\Netease\\MuMuPlayer-12.0\\shell\\"
}

# --->>下面是配置信息

# Free (宿舍填充)干员安排黑名单 用英文逗号分开
free_blacklist = "艾丽妮,但书,龙舌兰"

# 干员宿舍回复阈值
resting_threshold = 0.5

# 跑单如果all in 贸易站则 不需要修改设置
# 如果需要无人机加速其他房间则可以修改成房间名字如 'room_1_1'
drone_room = 'room_1_2'

# 设置成0，则不启动葛朗台跑单 设置成数字，单位为秒推荐10s
run_order_buffer_time = 10
# 无人机执行间隔时间 （小时）
drone_execution_gap = 4

# 无人机阈值
drone_count_limit = 105
# 跑单延时 单位（分钟）
run_order_delay = 3.5

reload_room = []

# 基地数据json文件保存名
state_file_name = 'state.json'

# 邮件时差调整
timezone_offset = 0

# 重要！！！ 请将排班表的文本文件复制并且替换成plan 参数
plan = {}
plan1 = {}
plan_config = PlanConfig(
    plan["conf"]["rest_in_full"],
    plan["conf"]["exhaust_require"],
    plan["conf"]["resting_priority"],
    ling_xi=plan["conf"]["ling_xi"],
    workaholic=plan["conf"]["workaholic"],
    max_resting_count=plan["conf"]["max_resting_count"],
    free_blacklist=free_blacklist,
    resting_threshold=resting_threshold,
    run_order_buffer_time=run_order_buffer_time,
    refresh_trading_config=plan["conf"]["refresh_trading"]
)
for room, obj in plan[plan["default"]].items():
    plan1[room] = [
        Room(op["agent"], op["group"], op["replacement"]) for op in obj["plans"]
    ]
# 默认任务
plan["default_plan"] = Plan(plan1, plan_config)
# 备用自定义任务
plan["backup_plans"] = plan["backup_plans"]

logger.debug(plan)

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
        base_scheduler.last_room = ''
        base_scheduler.MAA = None
        base_scheduler.send_message_config = send_message_config
        base_scheduler.ADB_CONNECT = config.ADB_CONNECT[0]
        base_scheduler.maa_config = maa_config
        base_scheduler.recruit_config = recruit_config
        base_scheduler.error = False
        base_scheduler.drone_count_limit = drone_count_limit  # 无人机高于于该值时才使用
        base_scheduler.drone_room = drone_room
        base_scheduler.drone_execution_gap = drone_execution_gap
        base_scheduler.run_order_delay = run_order_delay  # 跑单提前10分钟运行
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
    try:
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
    except Exception:
        return None



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
    base_scheduler.op_data.first_init = False
    if len(base_scheduler.op_data.backup_plans) > 0:
        conditions = base_scheduler.op_data.generate_conditions(len(base_scheduler.op_data.backup_plans))
        for con in conditions:
            validation_msg = base_scheduler.op_data.swap_plan_new(con, True)
            if validation_msg is not None:
                logger.error(f"替换排班验证错误：{validation_msg}, 附表条件为 {con}")
                return
        base_scheduler.op_data.swap_plan_new([False] * len(base_scheduler.op_data.backup_plans), True)
    while True:
        try:
            if len(base_scheduler.tasks) > 0:
                (base_scheduler.tasks.sort(key=lambda x: x.time, reverse=False))
                sleep_time = (base_scheduler.tasks[0].time - datetime.now()).total_seconds()
                logger.info('||'.join([str(t) for t in base_scheduler.tasks]))
                body = task_template.render(
                    tasks=[
                        obj.format(timezone_offset) for obj in base_scheduler.tasks
                    ],
                    base_scheduler=base_scheduler
                )
                base_scheduler.send_message(body, "", "html")
                # 如果任务间隔时间超过9分钟则启动MAA
                if sleep_time > 540:
                    if base_scheduler.recruit_config['recruit_enable'] == 1:
                        base_scheduler.recruit_plan_solver()
                    base_scheduler.maa_plan_solver()
                elif sleep_time > 0:
                    time.sleep(sleep_time)
            if len(base_scheduler.tasks) > 0 and base_scheduler.tasks[0].type.value.split('_')[0] == 'maa':
                base_scheduler.maa_plan_solver((base_scheduler.tasks[0].type.value.split('_')[1]).split(','),
                                               one_time=True)
                continue
            base_scheduler.run()
            reconnect_tries = 0
        except (ConnectionError, ConnectionAbortedError, AttributeError,RuntimeError) as e:
            reconnect_tries += 1
            if reconnect_tries < reconnect_max_tries:
                logger.warning(f'连接端口断开....正在重连....')
                connected = False
                while not connected:
                    try:
                        base_scheduler = inialize([], base_scheduler)
                        break
                    except Exception as ce:
                        logger.error(ce)
                        restart_simulator(simulator)
                        continue
                continue
            continue
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
