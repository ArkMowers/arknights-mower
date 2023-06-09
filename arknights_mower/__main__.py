import atexit
import os
import time
from datetime import datetime
from arknights_mower.utils.log import logger
import json

from arknights_mower.utils.pipe import Pipe

conf = {}
plan = {}
operators = {}


# 执行自动排班
def main(c, p, o={}, child_conn=None):
    __init_params__()
    from arknights_mower.utils.log import init_fhlr
    from arknights_mower.utils import config
    global plan
    global conf
    global operators
    conf = c
    plan = p
    operators = o
    config.LOGFILE_PATH = './log'
    config.SCREENSHOT_PATH = './screenshot'
    config.SCREENSHOT_MAXNUM = 50
    config.ADB_DEVICE = [conf['adb']]
    config.ADB_CONNECT = [conf['adb']]
    config.ADB_CONNECT = [conf['adb']]
    config.APPNAME = 'com.hypergryph.arknights' if conf[
                                                       'package_type'] == 1 else 'com.hypergryph.arknights.bilibili'  # 服务器
    init_fhlr(child_conn)
    Pipe.conn = child_conn
    if plan['conf']['ling_xi'] == 1:
        agent_base_config['令']['UpperLimit'] = 12
        agent_base_config['夕']['LowerLimit'] = 12
        agent_base_config['琴柳']['LowerLimit'] = 12
        agent_base_config['重岳']['LowerLimit'] = 12
    elif plan['conf']['ling_xi'] == 2:
        agent_base_config['夕']['UpperLimit'] = 12
        agent_base_config['令']['LowerLimit'] = 12
        agent_base_config['琴柳']['LowerLimit'] = 12
        agent_base_config['重岳']['LowerLimit'] = 12
    for key in list(filter(None, plan['conf']['rest_in_full'].replace('，', ',').split(','))):
        if key in agent_base_config.keys():
            agent_base_config[key]['RestInFull'] = True
        else:
            agent_base_config[key] = {'RestInFull': True}
    for key in list(filter(None, plan['conf']['exhaust_require'].replace('，', ',').split(','))):
        if key in agent_base_config.keys():
            agent_base_config[key]['ExhaustRequire'] = True
        else:
            agent_base_config[key] = {'ExhaustRequire': True}
    for key in list(filter(None, plan['conf']['workaholic'].replace('，', ',').split(','))):
        if key in agent_base_config.keys():
            agent_base_config[key]['Workaholic'] = True
        else:
            agent_base_config[key] = {'Workaholic': True}
    for key in list(filter(None, plan['conf']['resting_priority'].replace('，', ',').split(','))):
        if key in agent_base_config.keys():
            agent_base_config[key]['RestingPriority'] = 'low'
        else:
            agent_base_config[key] = {'RestingPriority': 'low'}
    logger.info('开始运行Mower')
    logger.debug(agent_base_config)
    simulate()


def inialize(tasks, scheduler=None):
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
        for key in plan[plan['default']]:
            plan1[key] = plan[plan['default']][key]['plans']
        plan[plan['default']] = plan1
        logger.debug(plan)
        base_scheduler.package_name = config.APPNAME  # 服务器
        base_scheduler.global_plan = plan
        base_scheduler.current_plan = plan1
        base_scheduler.current_base = {}
        base_scheduler.resting = []
        base_scheduler.max_resting_count = plan['conf']['max_resting_count']
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
        maa_config['roguelike'] = conf['maa_rg_enable'] == 1
        maa_config['sleep_min'] = conf['maa_rg_sleep_min']
        maa_config['sleep_max'] = conf['maa_rg_sleep_max']
        maa_config['maa_execution_gap'] = conf['maa_gap']
        maa_config['buy_first'] = conf['maa_mall_buy']
        maa_config['blacklist'] = conf['maa_mall_blacklist']
        maa_config['recruitment_time'] = conf['maa_recruitment_time']
        maa_config['recruit_only_4'] = conf['maa_recruit_only_4']
        base_scheduler.maa_config = maa_config
        base_scheduler.ADB_CONNECT = config.ADB_CONNECT[0]
        base_scheduler.error = False
        base_scheduler.drone_room = None if conf['drone_room'] == '' else conf['drone_room']
        base_scheduler.reload_room = list(filter(None, conf['reload_room'].replace('，', ',').split(',')))
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
    '''
    具体调用方法可见各个函数的参数说明
    '''
    tasks = []
    reconnect_max_tries = 10
    reconnect_tries = 0
    global base_scheduler
    base_scheduler = inialize(tasks)
    validation_msg = base_scheduler.initialize_operators()
    if validation_msg is not None:
        logger.error(validation_msg)
        return
    if operators != {}:
        for k,v in operators.items():
            if k in base_scheduler.op_data.operators and not base_scheduler.op_data.operators[k].room.startswith("dorm"):
                # 只复制心情数据
                base_scheduler.op_data.operators[k].mood = v.mood
                base_scheduler.op_data.operators[k].time_stamp = v.time_stamp
                base_scheduler.op_data.operators[k].depletion_rate = v.depletion_rate
                base_scheduler.op_data.operators[k].current_room = v.current_room
                base_scheduler.op_data.operators[k].current_index = v.current_index
    while True:
        try:
            if len(base_scheduler.tasks) > 0:
                (base_scheduler.tasks.sort(key=lambda x: x.time, reverse=False))
                sleep_time = (base_scheduler.tasks[0].time - datetime.now()).total_seconds()
                logger.debug(base_scheduler.tasks)
                remaining_time = (base_scheduler.tasks[0].time - datetime.now()).total_seconds()
                if sleep_time > 540 and conf['maa_enable'] == 1:
                    subject = f"下次任务在{base_scheduler.tasks[0].time.strftime('%H:%M:%S')}"
                    context = f"下一次任务:{base_scheduler.tasks[0].plan}"
                    logger.info(context)
                    logger.info(subject)
                    base_scheduler.send_email(context, subject)
                    base_scheduler.maa_plan_solver()
                elif sleep_time > 0:
                    subject = f"开始休息 {'%.2f' % (remaining_time / 60)} 分钟，到{base_scheduler.tasks[0].time.strftime('%H:%M:%S')}"
                    context = f"下一次任务:{base_scheduler.tasks[0].plan}"
                    logger.info(context)
                    logger.info(subject)
                    base_scheduler.send_email(context, subject)
                    time.sleep(sleep_time)
            if len(base_scheduler.tasks) > 0 and base_scheduler.tasks[0].type.split('_')[0] == 'maa':
                logger.info(f"开始执行 MAA {base_scheduler.tasks[0].type.split('_')[1]} 任务")
                base_scheduler.maa_plan_solver((base_scheduler.tasks[0].type.split('_')[1]).split(','), one_time=True)
                continue
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


def save_state(op_data,file='state.json'):
    if not os.path.exists('tmp'):
        os.makedirs('tmp')
    with open('tmp/' + file, 'w') as f:
        if op_data is not None :
            json.dump(vars(op_data), f, default=str)


def load_state(file='state.json'):

    if not os.path.exists('tmp/' + file):
        return None
    with open('tmp/' + file, 'r') as f:
        state = json.load(f)
    operators = {k: eval(v) for k, v in state['operators'].items()}
    for k,v in operators.items():
        if not v.time_stamp == 'None':
            v.time_stamp = datetime.strptime(v.time_stamp, '%Y-%m-%d %H:%M:%S.%f')
        else:
            v.time_stamp = None
    logger.info("基建配置已加载！")
    return operators


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
        "空弦": {"ArrangeOrder": [2, "true"]},
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
        "红云": {"ArrangeOrder": [2, "true"]},
        "承曦格雷伊": {"ArrangeOrder": [2, "true"]},
        "乌有": {"ArrangeOrder": [2, "true"]},
        "图耶": {"ArrangeOrder": [2, "true"]},
        "鸿雪": {"ArrangeOrder": [2, "true"]},
        "孑": {"ArrangeOrder": [2, "true"]},
        "清道夫": {"ArrangeOrder": [2, "true"]},
        "临光": {"ArrangeOrder": [2, "true"]},
        "杜宾": {"ArrangeOrder": [2, "true"]},
        "焰尾": {"RestInFull": True},
        "重岳": {"ArrangeOrder": [2, "true"]},
        "琴柳": {},
        "坚雷": {"ArrangeOrder": [2, "true"]},
        "年": {"RestingPriority": "low"},
        "伊内丝": {"ExhaustRequire": True, "ArrangeOrder": [2, "true"], "RestInFull": True},
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
