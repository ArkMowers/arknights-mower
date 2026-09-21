import copy
import os
from datetime import datetime, timedelta
from threading import Lock, Timer

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.solvers.reclamation_algorithm import ReclamationAlgorithm
from arknights_mower.solvers.secret_front import SecretFront
from arknights_mower.utils import config, path, rapidocr
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.csv_utils import EmptyDataError, read_csv_rows
from arknights_mower.utils.datetime import get_server_time
from arknights_mower.utils.depot import 创建csv, 创建json
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.log import logger
from arknights_mower.utils.news_checker import MaintenanceInfo, NewsChecker
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.path import get_path
from arknights_mower.utils.resource_pkg import (
    refresh_resource_at_boundary,
    resource_task_session,
)
from arknights_mower.utils.simulator import restart_simulator

base_scheduler = None
_maintenance_timer = None
_maintenance_timer_key = None
_maintenance_timer_lock = Lock()
_notified_maintenance_ids = set()
_flash_probe_ids = set()


def _stop_for_major_update(info: MaintenanceInfo):
    """Stop the automation thread and tell the user to update the game client."""
    from arknights_mower.solvers.record import save_current_state
    from arknights_mower.utils.email import send_message

    message = (
        "检测到明日方舟大版本更新，Mower 已停止运行。\n"
        "本次维护需要更新游戏客户端，请完成更新后再启动 Mower。\n"
        f"维护时间：{info.start:%Y-%m-%d %H:%M} - {info.end:%Y-%m-%d %H:%M}\n"
        f"官方公告：{info.url}"
    )
    with _maintenance_timer_lock:
        notify = info.announcement_id not in _notified_maintenance_ids
        _notified_maintenance_ids.add(info.announcement_id)
    logger.warning(message)
    try:
        # A client update always needs human intervention, so it must also pass
        # configurations that only deliver ERROR-level notifications.
        if notify:
            send_message(message, subject="明日方舟客户端需要更新", level="ERROR")
    except Exception:
        logger.exception("发送明日方舟客户端更新提醒失败")
    finally:
        try:
            save_current_state()
        finally:
            config.stop_mower.set()


def _cancel_maintenance_timer():
    global _maintenance_timer, _maintenance_timer_key
    with _maintenance_timer_lock:
        if _maintenance_timer is not None:
            _maintenance_timer.cancel()
        _maintenance_timer = None
        _maintenance_timer_key = None


def _arm_maintenance_timer(info: MaintenanceInfo, now=None):
    """Wake for threshold activation, then react exactly when maintenance starts."""
    global _maintenance_timer, _maintenance_timer_key
    now = now or datetime.now()
    threshold_at = info.start - timedelta(
        hours=config.conf.version_update_threshold_advance_hours
    )
    threshold_pending = info.update_type == "major" and now < threshold_at
    target = threshold_at if threshold_pending else info.start
    action = "threshold" if threshold_pending else "maintenance"
    delay = (target - now).total_seconds()
    if delay <= 0:
        return
    key = (info.announcement_id, target, action)
    with _maintenance_timer_lock:
        if _maintenance_timer_key == key and _maintenance_timer is not None:
            return
        if _maintenance_timer is not None:
            _maintenance_timer.cancel()

        def begin_maintenance():
            global _maintenance_timer, _maintenance_timer_key
            if action == "threshold":
                with _maintenance_timer_lock:
                    _maintenance_timer = None
                    _maintenance_timer_key = None
                config.wake_scheduler.set()
            elif info.update_type == "major":
                _stop_for_major_update(info)
            else:
                config.wake_scheduler.set()

        timer = Timer(delay, begin_maintenance)
        timer.daemon = True
        timer.start()
        _maintenance_timer = timer
        _maintenance_timer_key = key
        action_name = "启用版本维护心情阈值" if threshold_pending else "响应服务器维护"
        logger.info(f"已安排在 {target:%Y-%m-%d %H:%M} {action_name}")


def _apply_version_update_resting_threshold(info, scheduler, now=None):
    """Hot-apply the effective threshold to active and future plan switches."""
    if scheduler is None:
        return False
    now = now or datetime.now()
    advance = timedelta(hours=config.conf.version_update_threshold_advance_hours)
    active = (
        info is not None
        and info.update_type == "major"
        and info.start - advance <= now < info.start
    )
    desired = (
        config.conf.version_update_resting_threshold
        if active
        else config.conf.resting_threshold
    )
    targets = []
    global_plan = getattr(scheduler, "global_plan", None)
    if isinstance(global_plan, dict):
        default_plan = global_plan.get("default_plan")
        if default_plan is not None:
            targets.append(default_plan.config)
        targets.extend(plan.config for plan in global_plan.get("backup_plans", []))
    op_data = getattr(scheduler, "op_data", None)
    if op_data is not None and getattr(op_data, "config", None) is not None:
        targets.append(op_data.config)
    changed = False
    for target in targets:
        if target.resting_threshold != desired:
            target.resting_threshold = desired
            changed = True
    if changed:
        label = "版本维护" if active else "日常"
        logger.info(f"已即时应用{label}心情阈值：{desired:.0%}")
    return changed


def _has_recent_task(scheduler, reference_time, window_minutes=10):
    if scheduler is None:
        return False
    deadline = reference_time + timedelta(minutes=window_minutes)
    tasks = getattr(scheduler, "tasks", None)
    try:
        iterator = iter(tasks)
    except TypeError:
        return False
    for task in iterator:
        task_time = getattr(task, "time", None)
        if isinstance(task_time, datetime) and task_time <= deadline:
            return True
    return False


def _handle_maintenance(info: MaintenanceInfo, scheduler, now=None):
    now = now or datetime.now()
    if not info.active_at(now):
        return False
    if info.update_type == "major":
        _stop_for_major_update(info)
        return True

    flash_probe_at = min(info.end, info.start + timedelta(minutes=5))
    if info.is_flash_update and info.announcement_id not in _flash_probe_ids:
        probe_reference = max(now, flash_probe_at)
        if _has_recent_task(scheduler, probe_reference):
            _flash_probe_ids.add(info.announcement_id)
            if now >= flash_probe_at:
                logger.info("闪断更新已进行 5 分钟且有近期任务，尝试进入游戏一次")
                return False
            resume_at = flash_probe_at
        else:
            resume_at = info.end
    else:
        resume_at = info.resume_at
    remaining_time = (resume_at - now).total_seconds()
    logger.info("==============================================")
    logger.info("ザ・ワールド！時よ止まれ！！（The World!~ 时间暂停！）——DIO")
    logger.info("WRYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY!")
    logger.info("服务器维护/热更新中，DIO大人已为你暂停一切行动。")
    logger.info("==============================================")
    if scheduler is None:
        try:
            csleep(remaining_time)
        except MowerExit:
            return True
        logger.info("时间开始流动了……DIO大人贴心为你重启时间！")
        return False
    scheduler.handle_idle_action(remaining_time)
    # 服务器维护期间 mower 完全空闲，同样走休眠收口点，让 /status 显示休眠
    scheduler._idle_sleep(remaining_time, allow_wakeup=False)
    logger.info("时间开始流动了……DIO大人贴心为你重启时间！")
    return False


def _wait_before_early_login_retry(now=None):
    """Retry early entry every five minutes until the announced maintenance end."""
    now = now or datetime.now()
    info = NewsChecker.get_maintenance()
    if (
        info is not None
        and info.is_flash_update
        and info.announcement_id in _flash_probe_ids
        and now < info.end
    ):
        delay = (info.end - now).total_seconds()
        logger.warning("闪断更新第 5 分钟试探未成功，等待公告结束后恢复")
        try:
            csleep(delay)
        except MowerExit:
            pass
        return True
    if (
        info is None
        or not info.allows_early_login
        or not (info.resume_at <= now < info.end)
    ):
        return False
    delay = min(300, (info.end - now).total_seconds())
    logger.warning(f"停机维护可能尚未提前开服，{delay / 60:g} 分钟后再次尝试进入游戏")
    try:
        csleep(delay)
    except MowerExit:
        pass
    return True


def _read_depot_scan_timestamp(path):
    try:
        _, rows = read_csv_rows(path)
        return int(rows[-1][0])
    except (EmptyDataError, IndexError, ValueError):
        return None


# 执行自动排班
def main(saved_state, restart_after_mood_read=False):
    global base_scheduler
    try:
        with resource_task_session():
            return _main(saved_state, restart_after_mood_read)
    finally:
        _cancel_maintenance_timer()
        base_scheduler = None


def _main(saved_state, restart_after_mood_read=False):
    logger.info("开始运行Mower")
    maintenance = NewsChecker.get_maintenance()
    if maintenance is not None:
        _arm_maintenance_timer(maintenance)
        # Check before connecting to the game. A Mower started during maintenance
        # may otherwise fail device/game initialization before reaching the loop.
        if _handle_maintenance(maintenance, None):
            return
    rapidocr.initialize_ocr()
    data = None
    if saved_state != {}:
        data = saved_state
    result = simulate(data, restart_after_mood_read)
    if result == "restart_after_mood_read":
        from arknights_mower.solvers.record import load_state
        from arknights_mower.utils.scheduler_task import TaskTypes

        logger.info("正在按载入心情数据模式重启Mower")
        saved_state = load_state() or {}
        # simulate 已保存本次读取后的新状态。排班任务需要按新心情重建，但训练室
        # 刚恢复的收取/换人任务必须保留，否则近期读过的训练室可能数小时不再进入。
        saved_state["tasks"] = [
            task
            for task in saved_state.get("tasks", [])
            if task.type in (TaskTypes.SKILL_UPGRADE, TaskTypes.SWAP_SUPPORT)
        ]
        simulate(saved_state)


def initialize(
    tasks: list,
    scheduler: BaseSchedulerSolver | None = None,
    *,
    connection_retries: int = 3,
) -> BaseSchedulerSolver:
    if scheduler:
        scheduler.handle_error(True)
        return scheduler

    base_scheduler = BaseSchedulerSolver(connection_retries=connection_retries)
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
    connection_retries = 1
    global base_scheduler
    if config.stop_mower.is_set():
        return
    if config.conf.close_simulator_when_idle:
        connection_retries = 3
        logger.info("已启用任务结束后关闭模拟器，任务开始前直接启动模拟器")
        try:
            if not restart_simulator(stop=False, start=True):
                raise ConnectionError("任务开始前启动模拟器失败")
        except MowerExit:
            return
    success = False
    while not success:
        try:
            if config.stop_mower.is_set():
                raise MowerExit
            base_scheduler = initialize([], connection_retries=connection_retries)
            base_scheduler.restart_after_mood_read = restart_after_mood_read
            # saved=None 表示没有可载入的运行缓存。此时干员 current_room 尚未读取，
            # 首轮任务开始前必须暂缓副表判断，避免把“未知”误判成“不在工作”。
            base_scheduler.defer_backup_plan_until_mood_read = saved is None
            success = True
        except MowerExit:
            return
        except DeviceRecoveryError:
            raise
        except Exception as e:
            logger.exception(e)
            if config.stop_mower.is_set():
                return
            if _wait_before_early_login_retry():
                if config.stop_mower.is_set():
                    return
                reconnect_tries = 0
                connection_retries = 3
                continue
            reconnect_tries += 1
            if reconnect_tries < 3:
                logger.warning("初始化失败，尝试重启模拟器后重新连接")
                if not restart_simulator():
                    raise ConnectionError("首次初始化重启模拟器失败") from e
                # 首次快速失败只生效一次，恢复后的初始化均先重试三次连接。
                connection_retries = 3
                # 下一次 initialize 会新建 Device，不重连上次运行残留的 scheduler。
                continue
            else:
                raise e
    # base_scheduler.仓库扫描() #别删了 方便我找
    validation_msg = base_scheduler.initialize_operators()
    if validation_msg is not None:
        logger.error(validation_msg)
        return
    validation_msg = base_scheduler.op_data.validate_backup_plans()
    if not validation_msg["success"]:
        logger.error(f"备用计划验证失败: {validation_msg['message']}")
        return
    _apply_version_update_resting_threshold(
        NewsChecker.get_maintenance(), base_scheduler
    )
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
                base_scheduler.op_data.operators[k].dorm_recovery_room = getattr(
                    v, "dorm_recovery_room", ""
                )
                base_scheduler.op_data.operators[k].dorm_recovery_fixed = getattr(
                    v, "dorm_recovery_fixed", ()
                )
            base_scheduler.op_data.restore_dorm_state(saved["dorm"])
            base_scheduler.op_data.facility_states = copy.deepcopy(
                saved.get("facility_states", {})
            )
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
            refresh_resource_at_boundary()
            maintenance = NewsChecker.get_maintenance()
            _apply_version_update_resting_threshold(maintenance, base_scheduler)
            if maintenance is not None:
                _arm_maintenance_timer(maintenance)
                if _handle_maintenance(maintenance, base_scheduler):
                    return
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

                    # 应该在MAA任务之后
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
                    if len(base_scheduler.tasks) > 0:
                        base_scheduler.tasks.sort(key=lambda x: x.time, reverse=False)
                        remaining_time = (
                            base_scheduler.tasks[0].time - datetime.now()
                        ).total_seconds()
                    else:
                        remaining_time = 0

                    if remaining_time > 0 and config.conf.should_run_mower_stage_plan:
                        base_scheduler.mower_plan_solver()

                    if len(base_scheduler.tasks) > 0:
                        base_scheduler.tasks.sort(key=lambda x: x.time, reverse=False)
                        remaining_time = (
                            base_scheduler.tasks[0].time - datetime.now()
                        ).total_seconds()
                    else:
                        remaining_time = 0

                    if remaining_time >= 540 and base_scheduler.has_maa_tasks():
                        subject = f"下次任务在{base_scheduler.tasks[0].time.strftime('%H:%M:%S')}"
                        context = f"下一次任务:{base_scheduler.tasks[0].plan}"
                        logger.info(context)
                        logger.info(subject)
                        base_scheduler.maa_plan_solver()

                if len(base_scheduler.tasks) > 0:
                    base_scheduler.tasks.sort(key=lambda x: x.time, reverse=False)
                    remaining_time = (
                        base_scheduler.tasks[0].time - datetime.now()
                    ).total_seconds()
                else:
                    remaining_time = 0

                if remaining_time > 0:
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
                logger.warning("心情数据保存失败，直接刷新副表后继续当前Mower流程")
                base_scheduler.backup_plan_solver()
            reconnect_tries = 0
        except MowerExit:
            return
        except DeviceRecoveryError:
            raise
        except (ConnectionError, ConnectionAbortedError, AttributeError) as e:
            logger.exception(e)
            if _wait_before_early_login_retry():
                if config.stop_mower.is_set():
                    return
                reconnect_tries = 0
                continue
            reconnect_tries += 1
            if reconnect_tries < reconnect_max_tries:
                logger.warning("出现错误.尝试重启Mower")
                # 内层重连循环加次数上限，最后失败抛错而非无限重启
                retry = 0
                while retry < reconnect_max_tries:
                    retry += 1
                    try:
                        base_scheduler = initialize([], base_scheduler)
                        break
                    except (MowerExit, DeviceRecoveryError):
                        raise
                    except Exception as e:
                        if retry >= reconnect_max_tries:
                            raise
                        logger.exception(e)
                        base_scheduler.device.reconnect()
                continue
            else:
                raise e
        except RuntimeError as e:
            logger.exception(f"程序出错-尝试恢复设备连接->{e}")
            if _wait_before_early_login_retry():
                if config.stop_mower.is_set():
                    return
                continue
            base_scheduler.device.reconnect()
        except Exception as e:
            logger.exception(f"程序出错--->{e}")
            if _wait_before_early_login_retry():
                if config.stop_mower.is_set():
                    return
                continue
            base_scheduler.recog.update()
