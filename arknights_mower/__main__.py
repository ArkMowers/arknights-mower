import json
import os
from copy import deepcopy
from datetime import datetime, timedelta

import requests
from evalidate import Expr

from arknights_mower.solvers.reclamation_algorithm import ReclamationAlgorithm
from arknights_mower.solvers.secret_front import SecretFront
from arknights_mower.utils import config, path, rapidocr
from arknights_mower.utils.depot import 创建csv
from arknights_mower.utils.device.adb_client.session import Session
from arknights_mower.utils.device.scrcpy import Scrcpy
from arknights_mower.utils.email import task_template
from arknights_mower.utils.log import init_fhlr, logger
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.path import get_path
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.simulator import restart_simulator
from arknights_mower.utils.solver import MowerExit

global base_scheduler
base_scheduler = None


# 执行自动排班
def main():
    global conf
    global plan
    global operators
    global base_scheduler
    conf = deepcopy(config.conf)
    plan = deepcopy(config.plan)
    operators = deepcopy(config.operators)

    config.LOGFILE_PATH = str(get_path("@app/log"))
    config.SCREENSHOT_PATH = str(get_path("@app/screenshot"))
    config.SCREENSHOT_MAXNUM = conf["screenshot"]
    config.ADB_DEVICE = [conf["adb"]]
    config.ADB_CONNECT = [conf["adb"]]
    config.APPNAME = (
        "com.hypergryph.arknights"
        if conf["package_type"] == 1
        else "com.hypergryph.arknights.bilibili"
    )  # 服务器
    config.TAP_TO_LAUNCH = conf["tap_to_launch_game"]
    config.fix_mumu12_adb_disconnect = conf["fix_mumu12_adb_disconnect"]
    config.grandet_back_to_index = conf["run_order_grandet_mode"]["back_to_index"]
    config.ADB_CONTROL_CLIENT = conf["touch_method"]
    config.get_scene = conf["get_scene"]
    if hasattr(config, "droidcast"):
        config.droidcast.update(conf["droidcast"])
    else:
        config.droidcast = conf["droidcast"]
        config.droidcast["session"] = requests.Session()
        config.droidcast["port"] = 0
        config.droidcast["process"] = None
    config.ADB_BINARY = [conf["maa_adb_path"]]

    if config.wh is None:
        init_fhlr()
    logger.info("开始运行Mower")
    rapidocr.initialize_ocr()
    simulate()


# newbing说用这个来定义休息时间省事
def format_time(seconds):
    if seconds < 0:  # 权宜之计 配合刷生息演算
        return f"{0} 分钟"  # 权宜之计 配合刷生息演算
    # 计算小时和分钟
    rest_hours = int(seconds / 3600)
    rest_minutes = int((seconds % 3600) / 60)
    # 根据小时是否为零来决定是否显示
    if rest_hours == 0:
        return f"{rest_minutes} 分钟"
    elif rest_minutes == 0:
        return f"{rest_hours} 小时"
    else:
        return f"{rest_hours} 小时 {rest_minutes} 分钟"


def get_logic_exp(trigger):
    for k in ["left", "operator", "right"]:
        if not isinstance(trigger[k], str):
            trigger[k] = get_logic_exp(trigger[k])
    return LogicExpression(trigger["left"], trigger["operator"], trigger["right"])


def initialize(tasks, scheduler=None):
    if scheduler is not None:
        scheduler.handle_error(True)
        return scheduler
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    base_scheduler = BaseSchedulerSolver()
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
        refresh_trading_config=plan["conf"]["refresh_trading"],
        free_room=conf["free_room"],
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
                Room(op["agent"], op["group"], op["replacement"]) for op in obj["plans"]
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
            refresh_trading_config=i["conf"]["refresh_trading"],
            free_room=conf["free_room"],
        )
        backup_trigger = get_logic_exp(i["trigger"]) if "trigger" in i else None
        backup_task = i["task"] if "task" in i else None
        backup_trigger_timing = i["trigger_timing"] if "trigger_timing" in i else None
        backup_plans.append(
            Plan(
                backup_plan,
                backup_config,
                trigger=backup_trigger,
                task=backup_task,
                trigger_timing=backup_trigger_timing,
            )
        )
    plan["backup_plans"] = backup_plans

    logger.debug(plan)
    base_scheduler.package_name = config.APPNAME  # 服务器
    base_scheduler.global_plan = plan
    base_scheduler.drone_count_limit = conf["drone_count_limit"]
    base_scheduler.tasks = tasks
    base_scheduler.enable_party = conf["enable_party"] == 1  # 是否使用线索
    # 干员宿舍回复阈值
    # 高效组心情低于 UpperLimit  * 阈值 (向下取整)的时候才会会安排休息
    base_scheduler.last_room = ""
    # logger.info("宿舍黑名单：" + str(plan_config.free_blacklist))
    # 估计没用了
    base_scheduler.MAA = None
    base_scheduler.send_message_config = {
        "email_config": {
            "mail_enable": conf["mail_enable"],
            "subject": conf["mail_subject"],
            "encryption": conf["custom_smtp_server"][
                "encryption"
            ],  # 添加判断starttls的变量
            "account": conf["account"],
            "pass_code": conf["pass_code"],
            "recipients": conf["recipient"] or [conf["account"]],
            "custom_smtp_server": conf["custom_smtp_server"],
            "notify": False,
        },
        "serverJang_push_config": {
            "server_push_enable": conf["server_push_enable"],
            "sendKey": conf["sendKey"],
        },
    }
    base_scheduler.check_mail_enable = conf["check_mail_enable"]
    base_scheduler.report_enable = conf["report_enable"]
    base_scheduler.sign_in_enable = conf["sign_in"]["enable"]
    base_scheduler.visit_friend_enable = conf["visit_friend"]

    base_scheduler.ADB_CONNECT = config.ADB_CONNECT[0]
    base_scheduler.error = False
    base_scheduler.drone_room = None if conf["drone_room"] == "" else conf["drone_room"]
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
        except MowerExit:
            return
        except Exception as E:
            reconnect_tries += 1
            if reconnect_tries < 3:
                logger.exception(E)
                restart_simulator()
                base_scheduler.device.client.check_server_alive()
                Session().connect(config.ADB_DEVICE[0])
                if config.droidcast["enable"]:
                    base_scheduler.device.start_droidcast()
                if config.ADB_CONTROL_CLIENT == "scrcpy":
                    base_scheduler.device.control.scrcpy = Scrcpy(
                        base_scheduler.device.client
                    )
                continue
            else:
                raise E
    # base_scheduler.仓库扫描() #别删了 方便我找
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

    if len(base_scheduler.op_data.backup_plans) > 0:
        conditions = base_scheduler.op_data.generate_conditions(
            len(base_scheduler.op_data.backup_plans)
        )
        for con in conditions:
            validation_msg = base_scheduler.op_data.swap_plan(con, True)
            if validation_msg is not None:
                logger.error(f"替换排班验证错误：{validation_msg}, 附表条件为 {con}")
                return
        base_scheduler.op_data.swap_plan(
            [False] * len(base_scheduler.op_data.backup_plans), True
        )
    while True:
        try:
            if len(base_scheduler.tasks) > 0:
                (base_scheduler.tasks.sort(key=lambda x: x.time, reverse=False))
                logger.info("||".join([str(t) for t in base_scheduler.tasks]))
                remaining_time = (
                    base_scheduler.tasks[0].time - datetime.now()
                ).total_seconds()

                if remaining_time > 540:
                    # 刷新时间以鹰历为准
                    if (
                        base_scheduler.sign_in
                        < (datetime.now() - timedelta(hours=4)).date()
                    ):
                        if base_scheduler.sign_in_plan_solver():
                            base_scheduler.sign_in = (
                                datetime.now() - timedelta(hours=4)
                            ).date()

                    if (
                        base_scheduler.daily_visit_friend
                        < (datetime.now() - timedelta(hours=4)).date()
                    ):
                        if base_scheduler.visit_friend_plan_solver():
                            base_scheduler.daily_visit_friend = (
                                datetime.now() - timedelta(hours=4)
                            ).date()

                    if (
                        base_scheduler.daily_report
                        < (datetime.now() - timedelta(hours=4)).date()
                    ):
                        if base_scheduler.report_plan_solver(conf["send_report"]):
                            base_scheduler.daily_report = (
                                datetime.now() - timedelta(hours=4)
                            ).date()

                    if (
                        base_scheduler.skland_config["skland_enable"]
                        and base_scheduler.daily_skland
                        < (datetime.now() - timedelta(hours=4)).date()
                    ):
                        if base_scheduler.skland_plan_solover():
                            base_scheduler.daily_skland = (
                                datetime.now() - timedelta(hours=4)
                            ).date()

                    if (
                        base_scheduler.check_mail_enable
                        and base_scheduler.daily_mail
                        < (datetime.now() - timedelta(hours=8)).date()
                    ):
                        if base_scheduler.mail_plan_solver():
                            base_scheduler.daily_mail = (
                                datetime.now() - timedelta(hours=8)
                            ).date()

                    if base_scheduler.recruit_config["recruit_enable"] == 1:
                        base_scheduler.recruit_plan_solver()

                    # 应该在maa任务之后
                    def _is_depotscan():
                        import pandas as pd

                        path = get_path("@app/tmp/depotresult.csv")
                        if os.path.exists(path):
                            depotinfo = pd.read_csv(path)
                            仓库识别时间戳 = depotinfo.iloc[-1, 0]
                            return int(仓库识别时间戳)
                        else:
                            logger.info(f"{path} 不存在,新建一个存储仓库物品的csv")
                            now_time = (
                                int(datetime.now().timestamp())
                                - base_scheduler.maa_config["maa_execution_gap"] * 3600
                            )
                            创建csv()
                            return now_time

                    if conf["maa_depot_enable"]:
                        dt = int(datetime.now().timestamp()) - _is_depotscan()
                        if dt >= base_scheduler.maa_config["maa_execution_gap"] * 3600:
                            base_scheduler.仓库扫描()
                        else:
                            logger.info(
                                f"仓库扫描未到时间，将在 {base_scheduler.maa_config['maa_execution_gap']-dt//3600}小时之内开始扫描"
                            )
                    if base_scheduler.maa_config["maa_enable"] == 1:
                        subject = f"下次任务在{base_scheduler.tasks[0].time.strftime('%H:%M:%S')}"
                        context = f"下一次任务:{base_scheduler.tasks[0].plan}"
                        logger.info(context)
                        logger.info(subject)
                        body = task_template.render(
                            tasks=[
                                obj.format(timezone_offset)
                                for obj in base_scheduler.tasks
                            ],
                            base_scheduler=base_scheduler,
                        )
                        base_scheduler.send_message(body, subject, "html")
                        base_scheduler.maa_plan_solver()
                    else:
                        remaining_time = (
                            base_scheduler.tasks[0].time - datetime.now()
                        ).total_seconds()
                        subject = f"休息 {format_time(remaining_time)}，到{base_scheduler.tasks[0].time.strftime('%H:%M:%S')}开始工作"
                        context = f"下一次任务:{base_scheduler.tasks[0].plan if len(base_scheduler.tasks[0].plan) != 0 else '空任务' if base_scheduler.tasks[0].type == '' else base_scheduler.tasks[0].type}"
                        logger.info(context)
                        logger.info(subject)
                        base_scheduler.task_count += 1
                        logger.info(f"第{base_scheduler.task_count}次任务结束")
                        if remaining_time > 0:
                            if remaining_time > 300:
                                if base_scheduler.close_simulator_when_idle:
                                    restart_simulator(start=False)
                                elif base_scheduler.exit_game_when_idle:
                                    base_scheduler.device.exit()
                            body = task_template.render(
                                tasks=[
                                    obj.format(timezone_offset)
                                    for obj in base_scheduler.tasks
                                ],
                                base_scheduler=base_scheduler,
                            )
                            base_scheduler.send_message(body, subject, "html")
                            base_scheduler.sleeping = True
                            base_scheduler.sleep(remaining_time)
                            base_scheduler.sleeping = False
                            if base_scheduler.device.check_current_focus():
                                base_scheduler.recog.update()

                elif remaining_time > 0:
                    now_time = datetime.now().time()
                    try:
                        min_time = datetime.strptime(
                            base_scheduler.maa_config["sleep_min"], "%H:%M"
                        ).time()
                        max_time = datetime.strptime(
                            base_scheduler.maa_config["sleep_max"], "%H:%M"
                        ).time()
                        if max_time < min_time:
                            rg_sleep = now_time > min_time or now_time < max_time
                        else:
                            rg_sleep = min_time < now_time < max_time
                    except ValueError:
                        rg_sleep = False

                    if not rg_sleep:
                        if base_scheduler.maa_config["reclamation_algorithm"]:
                            base_scheduler.recog.update()
                            base_scheduler.back_to_index()
                            ra_solver = ReclamationAlgorithm(
                                base_scheduler.device, base_scheduler.recog
                            )
                            ra_solver.run(
                                base_scheduler.tasks[0].time - datetime.now(),
                                base_scheduler.maa_config["ra_timeout"],
                            )
                            remaining_time = (
                                base_scheduler.tasks[0].time - datetime.now()
                            ).total_seconds()
                        elif base_scheduler.maa_config["secret_front"]:
                            base_scheduler.recog.update()
                            base_scheduler.back_to_index()
                            sf_solver = SecretFront(
                                base_scheduler.device, base_scheduler.recog
                            )
                            sf_solver.send_message_config = base_scheduler.send_message_config
                            sf_solver.run(
                                base_scheduler.tasks[0].time - datetime.now(),
                                base_scheduler.maa_config["ra_timeout"],
                            )
                            remaining_time = (
                                base_scheduler.tasks[0].time - datetime.now()
                            ).total_seconds()

                    subject = f"休息 {format_time(remaining_time)}，到{base_scheduler.tasks[0].time.strftime('%H:%M:%S')}开始工作"
                    context = f"下一次任务:{base_scheduler.tasks[0].plan}"
                    logger.info(context)
                    logger.info(subject)
                    base_scheduler.task_count += 1
                    logger.info(f"第{base_scheduler.task_count}次任务结束")
                    if remaining_time > 300:
                        if conf["close_simulator_when_idle"]:
                            restart_simulator(start=False)
                        elif conf["exit_game_when_idle"]:
                            base_scheduler.device.exit()
                    body = task_template.render(
                        tasks=[
                            obj.format(timezone_offset) for obj in base_scheduler.tasks
                        ],
                        base_scheduler=base_scheduler,
                    )
                    base_scheduler.send_message(body, subject, "html")
                    base_scheduler.sleeping = True
                    base_scheduler.sleep(remaining_time)
                    base_scheduler.sleeping = False
                    if base_scheduler.device.check_current_focus():
                        base_scheduler.recog.update()
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
        except MowerExit:
            return
        except (ConnectionError, ConnectionAbortedError, AttributeError) as e:
            reconnect_tries += 1
            if reconnect_tries < reconnect_max_tries:
                logger.warning("出现错误.尝试重启Mower")
                connected = False
                while not connected:
                    try:
                        base_scheduler = initialize([], base_scheduler)
                        break
                    except MowerExit:
                        raise
                    except Exception as ce:
                        logger.error(ce)
                        restart_simulator()
                        base_scheduler.device.client.check_server_alive()
                        Session().connect(config.ADB_DEVICE[0])
                        if config.droidcast["enable"]:
                            base_scheduler.device.start_droidcast()
                        if config.ADB_CONTROL_CLIENT == "scrcpy":
                            base_scheduler.device.control.scrcpy = Scrcpy(
                                base_scheduler.device.client
                            )
                        continue
                continue
            else:
                raise e
        except RuntimeError as re:
            logger.exception(f"程序出错-尝试重启模拟器->{re}")
            restart_simulator()
            base_scheduler.device.client.check_server_alive()
            Session().connect(config.ADB_DEVICE[0])
            if config.droidcast["enable"]:
                base_scheduler.device.start_droidcast()
            if config.ADB_CONTROL_CLIENT == "scrcpy":
                base_scheduler.device.control.scrcpy = Scrcpy(
                    base_scheduler.device.client
                )
        except Exception as E:
            logger.exception(f"程序出错--->{E}")


def save_state(op_data, file="state.json"):
    tmp_dir = get_path("@app/tmp")
    if not tmp_dir.exists():
        tmp_dir.mkdir()
    state_file = tmp_dir / file
    with open(state_file, "w") as f:
        if op_data is not None:
            json.dump(vars(op_data), f, default=str)


def load_state(file="state.json"):
    state_file = get_path("@app/tmp") / file
    if not state_file.exists():
        return None
    with open(state_file, "r") as f:
        state = json.load(f)
    operators = {k: Expr(v).eval() for k, v in state["operators"].items()}
    for k, v in operators.items():
        if not v.time_stamp == "None":
            v.time_stamp = datetime.strptime(v.time_stamp, "%Y-%m-%d %H:%M:%S.%f")
        else:
            v.time_stamp = None
    logger.info("基建配置已加载！")
    return operators
