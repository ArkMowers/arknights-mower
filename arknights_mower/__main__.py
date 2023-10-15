import atexit
import os
import time
from datetime import datetime
from arknights_mower.utils.log import logger
import json

from copy import deepcopy

from arknights_mower.utils.pipe import Pipe
from arknights_mower.utils.simulator import restart_simulator
from arknights_mower.utils.email import task_template
from arknights_mower.utils import path
from arknights_mower.utils.path import get_path
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils import rapidocr

conf = {}
plan = {}
operators = {}


# 执行自动排班
def main(c, p, o={}, child_conn=None):
    from arknights_mower.utils.log import init_fhlr
    from arknights_mower.utils import config
    
    global plan
    global conf
    global operators
    conf = c
    plan = p
    operators = o
    config.LOGFILE_PATH = str(get_path('@app/log'))
    config.SCREENSHOT_PATH = str(get_path('@app/screenshot'))
    config.SCREENSHOT_MAXNUM = conf["screenshot"]
    config.ADB_DEVICE = [conf["adb"]]
    config.ADB_CONNECT = [conf["adb"]]
    config.ADB_CONNECT = [conf["adb"]]
    config.APPNAME = (
        "com.hypergryph.arknights"
        if conf["package_type"] == 1
        else "com.hypergryph.arknights.bilibili"
    )  # 服务器
    config.TAP_TO_LAUNCH = conf["tap_to_launch_game"]
    init_fhlr(child_conn)
    Pipe.conn = child_conn
    logger.info("开始运行Mower")
    rapidocr.initialize_ocr()
    simulate()


# newbing说用这个来定义休息时间省事
def format_time(seconds):
    # 计算小时和分钟
    rest_hours = int(seconds / 3600)
    rest_minutes = int((seconds % 3600) / 60)
    # 根据小时是否为零来决定是否显示
    if rest_hours == 0:
        return f"{rest_minutes} 分钟"
    else:
        return f"{rest_hours} 小时 {rest_minutes} 分钟"


def hide_password(conf):
    hpconf = deepcopy(conf)
    hpconf["pass_code"] = "*" * len(conf["pass_code"])
    hpconf["sendKey"] = "*" * len(conf["sendKey"])
    return hpconf


def update_conf():
    logger.debug("运行中更新设置")

    if not Pipe or not Pipe.conn:
        logger.error("管道关闭")
        logger.info(maa_config)
        return

    logger.debug("通过管道发送更新设置请求")
    Pipe.conn.send({"type": "update_conf"})
    logger.debug("开始通过管道读取设置")
    conf = Pipe.conn.recv()
    logger.debug(f"接收设置：{hide_password(conf)}")

    return conf


def set_maa_options(base_scheduler):
    conf = update_conf()

    global maa_config
    maa_config["maa_enable"] = conf["maa_enable"]
    maa_config["maa_path"] = conf["maa_path"]
    maa_config["maa_adb_path"] = conf["maa_adb_path"]
    maa_config["maa_adb"] = conf["adb"]
    maa_config["expiring_medicine"] = conf["maa_expiring_medicine"]
    maa_config["weekly_plan"] = conf["maa_weekly_plan"]
    maa_config["roguelike"] = (
        conf["maa_rg_enable"] == 1 and conf["maa_long_task_type"] == "rogue"
    )
    maa_config["rogue_theme"] = conf["maa_rg_theme"]
    maa_config["sleep_min"] = conf["maa_rg_sleep_min"]
    maa_config["sleep_max"] = conf["maa_rg_sleep_max"]
    maa_config["maa_execution_gap"] = conf["maa_gap"]
    maa_config["buy_first"] = conf["maa_mall_buy"]
    maa_config["blacklist"] = conf["maa_mall_blacklist"]
    maa_config["conn_preset"] = conf["maa_conn_preset"]
    maa_config["touch_option"] = conf["maa_touch_option"]
    maa_config["mall_ignore_when_full"] = conf["maa_mall_ignore_blacklist_when_full"]
    maa_config["credit_fight"] = conf["maa_credit_fight"]
    maa_config["maa_depot_enable"] = conf["maa_depot_enable"]
    maa_config["rogue"] = conf["rogue"]
    maa_config["stationary_security_service"] = (
        conf["maa_rg_enable"] == 1 and conf["maa_long_task_type"] == "sss"
    )
    maa_config["sss_type"] = conf["sss"]["type"]
    maa_config["ec_type"] = conf["sss"]["ec"]
    maa_config["copilot_file_location"] = conf["sss"]["copilot"]
    maa_config["copilot_loop_times"] = conf["sss"]["loop"]
    maa_config["reclamation_algorithm"] = (
        conf["maa_rg_enable"] == 1 and conf["maa_long_task_type"] == "ra"
    )
    base_scheduler.maa_config = maa_config

    logger.debug(f"更新Maa设置：{base_scheduler.maa_config}")


def set_recruit_options(base_scheduler):
    conf = update_conf()
    global recruit_config
    recruit_config["recruit_enable"] = conf["recruit_enable"]
    recruit_config["permit_target"] = conf["recruitment_permit"]
    recruit_config["recruit_robot"] = conf["recruit_robot"]
    recruit_config["recruitment_time"] = conf["recruitment_time"]
    base_scheduler.recruit_config = recruit_config

    logger.debug(f"更新公招设置：{base_scheduler.recruit_config}")


def set_skland_options(base_scheduler):
    conf = update_conf()
    global skland_config
    skland_config["skland_enable"] = conf["skland_enable"]
    skland_config["skland_info"] = conf["skland_info"]
    base_scheduler.skland_config = skland_config

    logger.debug(f"更新森空岛设置：{base_scheduler.skland_config}")


def get_logic_exp(trigger):
    for k in ["left", "operator", "right"]:
        if not isinstance(trigger[k], str):
            trigger[k] = get_logic_exp(trigger[k])
    return LogicExpression(trigger["left"], trigger["operator"], trigger["right"])


def initialize(tasks, scheduler=None):
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
        plan_config = PlanConfig(
            plan["conf"]["rest_in_full"],
            plan["conf"]["exhaust_require"],
            plan["conf"]["resting_priority"],
            ling_xi=plan["conf"]["ling_xi"],
            workaholic=plan["conf"]["workaholic"],
            max_resting_count=plan["conf"]["max_resting_count"],
            free_blacklist=conf["free_blacklist"],
            resting_threshold=conf["resting_threshold"],
            run_order_buffer_time=conf["run_order_grandet_mode"]["buffer_time"]
            if conf["run_order_grandet_mode"]["enable"]
            else -1,
        )
        for room, obj in plan[plan["default"]].items():
            plan1[room] = [
                Room(op["agent"], op["group"], op["replacement"]) for op in obj["plans"]
            ]
        # 默认任务
        plan["default_plan"] = Plan(plan1, plan_config)
        # 备用自定义任务
        backup_plans = []

        for i in plan["backup_plans"]:
            backup_plan = {}
            for room, obj in i["plan"].items():
                backup_plan[room] = [
                    Room(op["agent"], op["group"], op["replacement"])
                    for op in obj["plans"]
                ]
            backup_config = PlanConfig(
                i["conf"]["rest_in_full"],
                i["conf"]["exhaust_require"],
                i["conf"]["resting_priority"],
                ling_xi=i["conf"]["ling_xi"],
                workaholic=i["conf"]["workaholic"],
                max_resting_count=i["conf"]["max_resting_count"],
                free_blacklist=i["conf"]["free_blacklist"],
                resting_threshold=conf["resting_threshold"],
                run_order_buffer_time=conf["run_order_grandet_mode"]["buffer_time"]
                if conf["run_order_grandet_mode"]["enable"]
                else -1,
            )
            backup_trigger = get_logic_exp(i["trigger"]) if "trigger" in i else None
            backup_task = i["task"] if "task" in i else None
            backup_plans.append(
                Plan(
                    backup_plan, backup_config, trigger=backup_trigger, task=backup_task
                )
            )
        plan["backup_plans"] = backup_plans

        logger.debug(plan)
        base_scheduler.package_name = config.APPNAME  # 服务器
        base_scheduler.global_plan = plan
        base_scheduler.drone_count_limit = conf["drone_count_limit"]
        base_scheduler.tasks = tasks
        base_scheduler.enable_party = conf["enable_party"] == 1  # 是否使用线索
        # 读取心情开关，有菲亚梅塔或者希望全自动换班得设置为 true
        base_scheduler.read_mood = conf["run_mode"] == 1
        # 干员宿舍回复阈值
        # 高效组心情低于 UpperLimit  * 阈值 (向下取整)的时候才会会安排休息
        base_scheduler.last_room = ""
        logger.info("宿舍黑名单：" + str(plan_config.free_blacklist))
        base_scheduler.MAA = None
        base_scheduler.send_message_config = {
            "email_config":{
                "mail_enable": conf["mail_enable"],
                "subject": conf["mail_subject"],
                "account": conf["account"],
                "pass_code": conf["pass_code"],
                "receipts": [conf["account"]],
                "notify": False,
            },
            "serverJang_push_config":{
                "server_push_enable": conf["server_push_enable"],
                "sendKey": conf["sendKey"],
            }
        }
        set_maa_options(base_scheduler)
        set_recruit_options(base_scheduler)
        set_skland_options(base_scheduler)

        base_scheduler.ADB_CONNECT = config.ADB_CONNECT[0]
        base_scheduler.error = False
        base_scheduler.drone_room = (
            None if conf["drone_room"] == "" else conf["drone_room"]
        )
        base_scheduler.reload_room = list(
            filter(None, conf["reload_room"].replace("，", ",").split(","))
        )
        base_scheduler.drone_execution_gap = conf["drone_interval"]
        base_scheduler.run_order_delay = conf["run_order_delay"]
        base_scheduler.exit_game_when_idle = conf["exit_game_when_idle"]
        base_scheduler.simulator = conf["simulator"]
        base_scheduler.close_simulator_when_idle = conf["close_simulator_when_idle"]

        # 关闭游戏次数计数器
        base_scheduler.task_count = 0

        return base_scheduler
    else:
        scheduler.device = cli.device
        scheduler.recog = cli.recog
        scheduler.handle_error(True)
        return scheduler


def simulate():
    """
    具体调用方法可见各个函数的参数说明
    """
    logger.info(f"正在使用全局配置空间: {path.global_space}")
    tasks = []
    reconnect_max_tries = 10
    reconnect_tries = 0
    global base_scheduler
    success = False
    while not success:
        try:
            base_scheduler = initialize(tasks)
            success = True
        except Exception as E:
            reconnect_tries += 1
            if reconnect_tries < 3:
                logger.exception(E)
                restart_simulator(conf["simulator"])
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
    if operators != {}:
        for k, v in operators.items():
            if (
                k in base_scheduler.op_data.operators
                and not base_scheduler.op_data.operators[k].room.startswith("dorm")
            ):
                # 只复制心情数据
                base_scheduler.op_data.operators[k].mood = v.mood
                base_scheduler.op_data.operators[k].time_stamp = v.time_stamp
                base_scheduler.op_data.operators[k].depletion_rate = v.depletion_rate
                base_scheduler.op_data.operators[k].current_room = v.current_room
                base_scheduler.op_data.operators[k].current_index = v.current_index
    timezone_offset = 0
    while True:
        try:
            if len(base_scheduler.tasks) > 0:
                (base_scheduler.tasks.sort(key=lambda x: x.time, reverse=False))
                sleep_time = (
                    base_scheduler.tasks[0].time - datetime.now()
                ).total_seconds()
                logger.info("||".join([str(t) for t in base_scheduler.tasks]))
                remaining_time = (
                    base_scheduler.tasks[0].time - datetime.now()
                ).total_seconds()

                set_maa_options(base_scheduler)
                set_recruit_options(base_scheduler)
                set_skland_options(base_scheduler)

                if sleep_time > 540 and base_scheduler.maa_config["maa_enable"] == 1:
                    subject = (
                        f"下次任务在{base_scheduler.tasks[0].time.strftime('%H:%M:%S')}"
                    )
                    context = f"下一次任务:{base_scheduler.tasks[0].plan}"
                    logger.info(context)
                    logger.info(subject)
                    body = task_template.render(
                        tasks=[
                            obj.format(timezone_offset) for obj in base_scheduler.tasks
                        ]
                    )
                    base_scheduler.send_message(body, subject, "html")
                    base_scheduler.maa_plan_solver()
                elif sleep_time > 0:
                    subject = f"休息 {format_time(remaining_time)}，到{base_scheduler.tasks[0].time.strftime('%H:%M:%S')}开始工作"
                    context = f"下一次任务:{base_scheduler.tasks[0].plan}"
                    logger.info(context)
                    logger.info(subject)
                    base_scheduler.task_count += 1
                    logger.info(f"第{base_scheduler.task_count}次任务结束")
                    if sleep_time > 300:
                        if conf["close_simulator_when_idle"]:
                            restart_simulator(conf["simulator"], start=False)
                        elif conf["exit_game_when_idle"]:
                            base_scheduler.device.exit(base_scheduler.package_name)
                    body = task_template.render(
                        tasks=[
                            obj.format(timezone_offset) for obj in base_scheduler.tasks
                        ]
                    )
                    base_scheduler.send_message(body, subject, "html")
                    time.sleep(sleep_time)
                    if conf["exit_game_when_idle"]:
                        restart_simulator(conf["simulator"], stop=False)
            if (
                len(base_scheduler.tasks) > 0
                and base_scheduler.tasks[0].type.value.split("_")[0] == "maa"
            ):
                logger.info(
                    f"开始执行 MAA {base_scheduler.tasks[0].type.value.split('_')[1]} 任务"
                )
                base_scheduler.maa_plan_solver(
                    [base_scheduler.tasks[0].type.value.split("_")[1]], one_time=True
                )
                continue
            base_scheduler.run()
            reconnect_tries = 0
        except ConnectionError or ConnectionAbortedError or AttributeError as e:
            reconnect_tries += 1
            if reconnect_tries < reconnect_max_tries:
                logger.warning(f"出现错误.尝试重启Mower")
                connected = False
                while not connected:
                    try:
                        base_scheduler = initialize([], base_scheduler)
                        break
                    except (
                        RuntimeError or ConnectionError or ConnectionAbortedError
                    ) as ce:
                        logger.error(ce)
                        restart_simulator(conf["simulator"])
                        continue
                continue
            else:
                raise e
        except RuntimeError as re:
            logger.exception(f"程序出错-尝试重启模拟器->{re}")
            restart_simulator(conf["simulator"])
        except Exception as E:
            logger.exception(f"程序出错--->{E}")


def save_state(op_data, file="state.json"):
    tmp_dir = get_path('@app/tmp')
    if not tmp_dir.exists():
        tmp_dir.mkdir()
    state_file = tmp_dir / file
    with open(state_file, "w") as f:
        if op_data is not None:
            json.dump(vars(op_data), f, default=str)


def load_state(file="state.json"):
    state_file = get_path('@app/tmp') / file
    if not state_file.exists():
        return None
    with open(state_file, 'r') as f:
        state = json.load(f)
    operators = {k: eval(v) for k, v in state["operators"].items()}
    for k, v in operators.items():
        if not v.time_stamp == "None":
            v.time_stamp = datetime.strptime(v.time_stamp, "%Y-%m-%d %H:%M:%S.%f")
        else:
            v.time_stamp = None
    logger.info("基建配置已加载！")
    return operators


maa_config = {}
recruit_config = {}
skland_config = {}
