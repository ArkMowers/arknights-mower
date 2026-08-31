import os
from datetime import datetime

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.solvers.reclamation_algorithm import ReclamationAlgorithm
from arknights_mower.solvers.secret_front import SecretFront
from arknights_mower.utils import config, path, rapidocr
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.csv_utils import EmptyDataError, read_csv_rows
from arknights_mower.utils.datetime import get_server_time
from arknights_mower.utils.depot import 创建csv, 创建json
from arknights_mower.utils.device.adb_client.session import Session
from arknights_mower.utils.device.scrcpy import Scrcpy
from arknights_mower.utils.email import send_message
from arknights_mower.utils.log import logger
from arknights_mower.utils.maa_check import is_maa_connectivity_check_enabled
from arknights_mower.utils.news_checker import NewsChecker
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.path import get_path
from arknights_mower.utils.simulator import restart_simulator

base_scheduler = None


def _read_depot_scan_timestamp(path):
    try:
        _, rows = read_csv_rows(path)
        return int(rows[-1][0])
    except (EmptyDataError, IndexError, ValueError):
        return None


# 执行自动排班
def main(saved_state, restart_after_mood_read=False):
    logger.info("开始运行Mower")
    rapidocr.initialize_ocr()
    data = None
    if saved_state != {}:
        data = saved_state
    result = simulate(data, restart_after_mood_read)
    if result == "restart_after_mood_read":
        from arknights_mower.solvers.record import load_state

        logger.info("正在按载入心情数据模式重启Mower")
        saved_state = load_state() or {}
        saved_state["tasks"] = []
        simulate(saved_state)


def initialize(
    tasks: list, scheduler: BaseSchedulerSolver | None = None
) -> BaseSchedulerSolver:
    if scheduler:
        scheduler.handle_error(True)
        return scheduler

    base_scheduler = BaseSchedulerSolver()
    from arknights_mower.utils.operators import build_global_plan

    plan = build_global_plan()

    logger.debug(plan)
    base_scheduler.global_plan = plan
    base_scheduler.tasks = tasks
    base_scheduler.enable_party = config.conf.enable_party == 1  # 是否使用线索
    base_scheduler.leifeng_mode = config.conf.leifeng_mode == 1  # 是否有额外线索就送出
    # 干员宿舍回复阈值
    # 高效组心情低于 UpperLimit  * 阈值 (向下取整)的时候才会会安排休息
    base_scheduler.last_room = ""
    # logger.info("宿舍黑名单：" + str(plan_config.free_blacklist))
    # 估计没用了
    base_scheduler.MAA = None
    base_scheduler.error = False
    base_scheduler.drone_room = (
        None if config.conf.drone_room == "" else config.conf.drone_room
    )
    base_scheduler.reload_room = list(
        filter(None, config.conf.reload_room.replace("，", ",").split(","))
    )

    # 关闭游戏次数计数器
    base_scheduler.task_count = 0

    return base_scheduler


def simulate(saved, restart_after_mood_read=False):
    """
    具体调用方法可见各个函数的参数说明
    """
    logger.info(f"正在使用全局配置空间: {path.global_space}")
    tasks = saved["tasks"] if saved else []
    reconnect_max_tries = 10
    reconnect_tries = 0
    global base_scheduler
    success = False
    while not success:
        try:
            base_scheduler = initialize([])
            base_scheduler.restart_after_mood_read = restart_after_mood_read
            success = True
        except MowerExit:
            return
        except Exception as e:
            logger.exception(e)
            reconnect_tries += 1
            if reconnect_tries < 3:
                restart_simulator()
                base_scheduler.device.client.check_server_alive()
                Session().connect(config.conf.adb)
                if config.conf.droidcast.enable:
                    base_scheduler.device.start_droidcast()
                if config.conf.touch_method == "scrcpy":
                    base_scheduler.device.control.scrcpy = Scrcpy(
                        base_scheduler.device.client
                    )
                continue
            else:
                raise e
    if is_maa_connectivity_check_enabled():
        try:
            base_scheduler.check_maa_connectivity("启动预检")
        except RuntimeError as e:
            message = str(e)
            logger.error(message)
            send_message(
                message,
                "Mower启动中止：Maa连接测试失败",
                level="ERROR",
            )
            return
    # base_scheduler.仓库扫描() #别删了 方便我找
    validation_msg = base_scheduler.initialize_operators()
    if validation_msg is not None:
        logger.error(validation_msg)
        return
    validation_msg = base_scheduler.op_data.validate_backup_plans()
    if not validation_msg["success"]:
        logger.error(f"备用计划验证失败: {validation_msg['message']}")
        return
    if saved:
        try:
            for k, v in saved["operators"].items():
                if k not in base_scheduler.op_data.operators:
                    base_scheduler.op_data.add(Operator(k, ""))
                    # 只复制心情数据
                base_scheduler.op_data.operators[k].mood = v.mood
                base_scheduler.op_data.operators[k].time_stamp = v.time_stamp
                base_scheduler.op_data.operators[k].depletion_rate = v.depletion_rate
                base_scheduler.op_data.operators[k].current_room = v.current_room
                base_scheduler.op_data.operators[k].current_index = v.current_index
            base_scheduler.op_data.dorm = saved["dorm"]
            base_scheduler.party_time = saved["party_time"]
            base_scheduler.daily_visit_friend = saved["daily_visit_friend"]
            base_scheduler.daily_report = saved["daily_report"]
            base_scheduler.daily_skland = saved["daily_skland"]
            base_scheduler.daily_mail = saved["daily_mail"]
            base_scheduler.task_count = saved["task_count"]
            base_scheduler.tasks = tasks
            if len(base_scheduler.op_data.backup_plans) > 0:
                # 启动的时候按照条件触发副表
                base_scheduler.backup_plan_solver()
        except Exception as ex:
            logger.exception(ex)
    while True:
        try:
            st, et = NewsChecker.get_update_time()
            if st is not None and et is not None:
                if et > datetime.now() > st:
                    remaining_time = (et - datetime.now()).total_seconds()
                    logger.info("==============================================")
                    logger.info(
                        "ザ・ワールド！時よ止まれ！！（The World!~ 时间暂停！）——DIO"
                    )
                    logger.info("WRYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY!")
                    logger.info("服务器维护中，DIO大人已为你暂停一切行动。")
                    logger.info("==============================================")
                    base_scheduler.handle_idle_action(remaining_time)
                    # 服务器维护期间 mower 完全空闲，同样走休眠收口点，让 /status 显示休眠
                    base_scheduler._idle_sleep(remaining_time)
                    logger.info("时间开始流动了……DIO大人贴心为你重启时间！")
            if len(base_scheduler.tasks) > 0:
                (base_scheduler.tasks.sort(key=lambda x: x.time, reverse=False))
                remaining_time = (
                    base_scheduler.tasks[0].time - datetime.now()
                ).total_seconds()
                if remaining_time > 540:
                    if base_scheduler.daily_visit_friend < get_server_time().date():
                        if base_scheduler.visit_friend_plan_solver():
                            base_scheduler.daily_visit_friend = get_server_time().date()

                    if base_scheduler.daily_report < get_server_time().date():
                        if base_scheduler.report_plan_solver():
                            base_scheduler.daily_report = get_server_time().date()

                    if (
                        config.conf.skland_enable
                        and base_scheduler.daily_skland < get_server_time().date()
                    ):
                        if base_scheduler.skland_plan_solver():
                            base_scheduler.daily_skland = get_server_time().date()

                    if (
                        config.conf.check_mail_enable
                        and base_scheduler.daily_mail < get_server_time().date()
                    ):
                        if base_scheduler.mail_plan_solver():
                            base_scheduler.daily_mail = get_server_time().date()

                    if config.conf.recruit_enable:
                        base_scheduler.recruit_plan_solver()

                    # 应该在maa任务之后
                    def _is_depotscan():
                        path = get_path("@app/tmp/depotresult.csv")
                        if os.path.exists(path):
                            timestamp = _read_depot_scan_timestamp(path)
                            if timestamp is not None:
                                return timestamp
                            logger.warning(f"{path} 没有有效仓库记录，重新初始化")
                            创建csv()
                            return (
                                int(datetime.now().timestamp())
                                - config.conf.maa_gap * 3600
                            )
                        else:
                            logger.info(f"{path} 不存在,新建一个存储仓库物品的csv")
                            now_time = (
                                int(datetime.now().timestamp())
                                - config.conf.maa_gap * 3600
                            )
                            创建csv()
                            创建json()
                            return now_time

                    if config.conf.maa_depot_enable:
                        dt = int(datetime.now().timestamp()) - _is_depotscan()
                        if dt >= config.conf.maa_gap * 3600:
                            base_scheduler.仓库扫描()
                        else:
                            logger.info(
                                f"仓库扫描未到时间，将在 {config.conf.maa_gap - dt // 3600}小时之内开始扫描"
                            )

                    from arknights_mower.utils.scheduler_task import (
                        TaskTypes as _TaskTypes,
                    )

                    next_upgrade = base_scheduler.find_next_task(
                        task_type=_TaskTypes.SKILL_UPGRADE
                    )
                    if next_upgrade is not None and next_upgrade.time <= datetime.now():
                        logger.info("仓库扫描后有专精任务待执行，立即运行后继续日常")
                        base_scheduler.run()
                        from arknights_mower.utils.scheduler_task import scheduling

                        scheduling(base_scheduler.tasks)
                    if config.conf.maa_enable != 1:
                        base_scheduler.mower_plan_solver()
                    elif config.conf.maa_enable == 1:
                        subject = f"下次任务在{base_scheduler.tasks[0].time.strftime('%H:%M:%S')}"
                        context = f"下一次任务:{base_scheduler.tasks[0].plan}"
                        logger.info(context)
                        logger.info(subject)
                        base_scheduler.maa_plan_solver()

                elif remaining_time > 0:
                    now_time = datetime.now().time()
                    try:
                        min_time = datetime.strptime(
                            config.conf.maa_rg_sleep_min, "%H:%M"
                        ).time()
                        max_time = datetime.strptime(
                            config.conf.maa_rg_sleep_max, "%H:%M"
                        ).time()
                        if max_time < min_time:
                            rg_sleep = now_time > min_time or now_time < max_time
                        else:
                            rg_sleep = min_time < now_time < max_time
                    except ValueError:
                        rg_sleep = False

                    if not rg_sleep:
                        if config.conf.RA:
                            base_scheduler.recog.update()
                            base_scheduler.back_to_index()
                            ra_solver = ReclamationAlgorithm(
                                base_scheduler.device, base_scheduler.recog
                            )
                            ra_solver.run(base_scheduler.tasks[0].time - datetime.now())
                            remaining_time = (
                                base_scheduler.tasks[0].time - datetime.now()
                            ).total_seconds()
                        elif config.conf.SF:
                            base_scheduler.recog.update()
                            base_scheduler.back_to_index()
                            sf_solver = SecretFront(
                                base_scheduler.device, base_scheduler.recog
                            )
                            sf_solver.run(base_scheduler.tasks[0].time - datetime.now())
                            remaining_time = (
                                base_scheduler.tasks[0].time - datetime.now()
                            ).total_seconds()

                    base_scheduler.rest_until_next_task()

            result = base_scheduler.run()
            if result == "restart_after_mood_read":
                from arknights_mower.solvers.record import save_current_state

                if save_current_state():
                    return result
                logger.warning("心情数据保存失败，继续当前Mower流程")
            reconnect_tries = 0
        except MowerExit:
            return
        except (ConnectionError, ConnectionAbortedError, AttributeError) as e:
            logger.exception(e)
            reconnect_tries += 1
            if reconnect_tries < reconnect_max_tries:
                logger.warning("出现错误.尝试重启Mower")
                # #84：内层重连循环加次数上限，最后失败抛错而非无限重启
                retry = 0
                while retry < reconnect_max_tries:
                    retry += 1
                    try:
                        base_scheduler = initialize([], base_scheduler)
                        break
                    except MowerExit:
                        raise
                    except Exception as e:
                        if retry >= reconnect_max_tries:
                            raise
                        logger.exception(e)
                        restart_simulator()
                        base_scheduler.device.client.check_server_alive()
                        Session().connect(config.conf.adb)
                        if config.conf.droidcast.enable:
                            base_scheduler.device.start_droidcast()
                        if config.conf.touch_method == "scrcpy":
                            base_scheduler.device.control.scrcpy = Scrcpy(
                                base_scheduler.device.client
                            )
                continue
            else:
                raise e
        except RuntimeError as e:
            logger.exception(f"程序出错-尝试重启模拟器->{e}")
            restart_simulator()
            base_scheduler.device.client.check_server_alive()
            Session().connect(config.conf.adb)
            if config.conf.droidcast.enable:
                base_scheduler.device.start_droidcast()
            if config.conf.touch_method == "scrcpy":
                base_scheduler.device.control.scrcpy = Scrcpy(
                    base_scheduler.device.client
                )
        except Exception as e:
            logger.exception(f"程序出错--->{e}")
            base_scheduler.recog.update()
