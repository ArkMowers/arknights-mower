import time
from datetime import datetime

conf = {}
plan = {}


# 执行自动排班
def main(c, p, child_conn):
    __init_params__()
    from arknights_mower.utils.log import logger, init_fhlr
    from arknights_mower.utils import config
    global plan
    global conf
    conf = c
    plan = p
    config.LOGFILE_PATH = './log'
    config.SCREENSHOT_PATH = './screenshot'
    config.SCREENSHOT_MAXNUM = 1000
    config.ADB_DEVICE = [conf['adb']]
    config.ADB_CONNECT = [conf['adb']]
    config.ADB_CONNECT = [conf['adb']]
    config.APPNAME = 'com.hypergryph.arknights' if conf[
                                                       'package_type'] == 1 else 'com.hypergryph.arknights.bilibili'  # 服务器
    init_fhlr(child_conn)
    if conf['ling_xi'] == 1:
        agent_base_config['令']['UpperLimit'] = 11
        agent_base_config['夕']['UpperLimit'] = 11
        agent_base_config['夕']['LowerLimit'] = 13
    elif conf['ling_xi'] == 2:
        agent_base_config['夕']['UpperLimit'] = 11
        agent_base_config['令']['UpperLimit'] = 11
        agent_base_config['令']['LowerLimit'] = 13
    for key in list(filter(None, conf['rest_in_full'].replace('，', ',').split(','))):
        if key in agent_base_config.keys():
            agent_base_config[key]['RestInFull'] = True
        else:
            agent_base_config[key] = {'RestInFull': True}
    logger.info('开始运行Mower')
    simulate()


def inialize(tasks, scheduler=None):
    from arknights_mower.utils.log import logger
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
    from arknights_mower.strategy import Solver
    from arknights_mower.utils.device import Device
    from arknights_mower.utils import config
    device = Device()
    cli = Solver(device)
    if scheduler is None:
        base_scheduler = BaseSchedulerSolver(cli.device, cli.recog)
        base_scheduler.operators = {}
        plan1 = {}
        for key in plan:
            plan1[key] = plan[key]['plans']
        base_scheduler.package_name = config.APPNAME  # 服务器
        base_scheduler.global_plan = {'default': "plan_1", "plan_1": plan1}
        base_scheduler.current_base = {}
        base_scheduler.resting = []
        base_scheduler.max_resting_count = conf['max_resting_count']
        base_scheduler.drone_count_limit = conf['drone_count_limit']
        base_scheduler.tasks = tasks
        base_scheduler.enable_party = conf['enable_party'] == 1  # 是否使用线索
        # 读取心情开关，有菲亚梅塔或者希望全自动换班得设置为 true
        base_scheduler.read_mood = conf['run_mode'] == 1
        # 干员宿舍回复阈值
        # 高效组心情低于 UpperLimit  * 阈值 (向下取整)的时候才会会安排休息

        base_scheduler.scan_time = {}
        base_scheduler.last_room = ''
        base_scheduler.free_blacklist = list(filter(None, conf['free_blacklist'].replace('，', ',').split(',')))
        logger.info('宿舍黑名单：' + str(base_scheduler.free_blacklist))
        base_scheduler.resting_treshhold = 0.5
        base_scheduler.MAA = None
        base_scheduler.email_config = {
            'mail_enable': conf['mail_enable'],
            'subject': '[Mower通知]',
            'account': conf['account'],
            'pass_code': conf['pass_code'],
            'receipts': [conf['account']],
            'notify': False
        }
        maa_config['maa_path'] = conf['maa_path']
        maa_config['maa_adb_path'] = conf['maa_adb_path']
        maa_config['maa_adb'] = conf['adb']
        maa_config['weekly_plan'] = conf['maa_weekly_plan']
        base_scheduler.maa_config = maa_config
        base_scheduler.ADB_CONNECT = config.ADB_CONNECT[0]
        base_scheduler.error = False
        base_scheduler.drone_room = None if conf['drone_room'] == '' else conf['drone_room']
        base_scheduler.drone_execution_gap = 4
        base_scheduler.run_order_delay = conf['run_order_delay']
        base_scheduler.agent_base_config = agent_base_config
        return base_scheduler
    else:
        scheduler.device = cli.device
        scheduler.recog = cli.recog
        scheduler.handle_error(True)
        return scheduler


def simulate():
    from arknights_mower.utils.log import logger
    '''
    具体调用方法可见各个函数的参数说明
    '''
    tasks = []
    reconnect_max_tries = 10
    reconnect_tries = 0
    base_scheduler = inialize(tasks)
    while True:
        try:
            if len(base_scheduler.tasks) > 0:
                (base_scheduler.tasks.sort(key=lambda x: x["time"], reverse=False))
                sleep_time = (base_scheduler.tasks[0]["time"] - datetime.now()).total_seconds()
                logger.debug(base_scheduler.tasks)
                remaining_time = (base_scheduler.tasks[0]["time"] - datetime.now()).total_seconds()
                if sleep_time > 540 and conf['maa_enable'] == 1:
                    subject = f"下次任务在{base_scheduler.tasks[0]['time'].strftime('%H:%M:%S')}"
                    context = f"下一次任务:{base_scheduler.tasks[0]['plan']}"
                    logger.info(context)
                    logger.info(subject)
                    base_scheduler.send_email(context, subject)
                    base_scheduler.maa_plan_solver()
                elif sleep_time > 0:
                    subject = f"开始休息 {'%.2f' % (remaining_time / 60)} 分钟，到{base_scheduler.tasks[0]['time'].strftime('%H:%M:%S')}"
                    context = f"下一次任务:{base_scheduler.tasks[0]['plan']}"
                    logger.info(context)
                    logger.info(subject)
                    base_scheduler.send_email(context, subject)
                    time.sleep(sleep_time)
            base_scheduler.run()
            reconnect_tries = 0
        except ConnectionError as e:
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
                        time.sleep(5)
                        continue
                continue
            else:
                raise Exception(e)
        except Exception as E:
            logger.exception(f"程序出错--->{E}")


agent_base_config = {}
maa_config = {}


def __init_params__():
    global agent_base_config
    global maa_config
    agent_base_config = {
        "Default": {"UpperLimit": 24, "LowerLimit": 0, "ExhaustRequire": False, "ArrangeOrder": [2, "false"],
                    "RestInFull": False},
        "令": {"ArrangeOrder": [2, "true"]},
        "夕": {"ArrangeOrder": [2, "true"]},
        "稀音": {"ExhaustRequire": True, "ArrangeOrder": [2, "true"], "RestInFull": True},
        "巫恋": {"ArrangeOrder": [2, "true"]},
        "柏喙": {"ExhaustRequire": True, "ArrangeOrder": [2, "true"]},
        "龙舌兰": {"ArrangeOrder": [2, "true"]},
        "空弦": {"ArrangeOrder": [2, "true"], "RestingPriority": "low"},
        "伺夜": {"ArrangeOrder": [2, "true"]},
        "绮良": {"ArrangeOrder": [2, "true"]},
        "但书": {"ArrangeOrder": [2, "true"]},
        "泡泡": {"ArrangeOrder": [2, "true"]},
        "火神": {"ArrangeOrder": [2, "true"]},
        "黑键": {"ArrangeOrder": [2, "true"]},
        "波登可": {"ArrangeOrder": [2, "false"]},
        "夜莺": {"ArrangeOrder": [2, "false"]},
        "菲亚梅塔": {"ArrangeOrder": [2, "false"]},
        "流明": {"ArrangeOrder": [2, "false"]},
        "蜜莓": {"ArrangeOrder": [2, "false"]},
        "闪灵": {"ArrangeOrder": [2, "false"]},
        "杜林": {"ArrangeOrder": [2, "false"]},
        "褐果": {"ArrangeOrder": [2, "false"]},
        "车尔尼": {"ArrangeOrder": [2, "false"]},
        "安比尔": {"ArrangeOrder": [2, "false"]},
        "爱丽丝": {"ArrangeOrder": [2, "false"]},
        "桃金娘": {"ArrangeOrder": [2, "false"]},
        "帕拉斯": {"RestingPriority": "low"},
        "红云": {"RestingPriority": "low", "ArrangeOrder": [2, "true"]},
        "承曦格雷伊": {"ArrangeOrder": [2, "true"]},
        "乌有": {"ArrangeOrder": [2, "true"], "RestingPriority": "low"},
        "图耶": {"ArrangeOrder": [2, "true"]},
        "鸿雪": {"ArrangeOrder": [2, "true"]},
        "孑": {"ArrangeOrder": [2, "true"]},
        "清道夫": {"ArrangeOrder": [2, "true"]},
        "临光": {"ArrangeOrder": [2, "true"]},
        "杜宾": {"ArrangeOrder": [2, "true"]},
        "焰尾": {"RestInFull": True},
        "重岳": {"ArrangeOrder": [2, "true"]},
        "坚雷": {"ArrangeOrder": [2, "true"]},
        "年": {"RestingPriority": "low"}
    }
    maa_config = {
        # maa 运行的时间间隔，以小时计
        "maa_execution_gap": 4,
        # 以下配置，第一个设置为true的首先生效
        # 是否启动肉鸽
        "roguelike": False,
        # 是否启动生息演算
        "reclamation_algorithm": False,
        # 是否启动保全派驻
        "stationary_security_service": False,
        "last_execution": None
    }
