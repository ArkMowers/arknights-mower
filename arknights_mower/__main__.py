import copy
import os
from datetime import datetime, timedelta
from threading import Lock, Timer

from arknights_mower.data import base_room_list
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.solvers.reclamation_algorithm import ReclamationAlgorithm
from arknights_mower.solvers.secret_front import SecretFront
from arknights_mower.utils import config, path, rapidocr
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.csv_utils import EmptyDataError, read_csv_rows
from arknights_mower.utils.datetime import get_server_time
from arknights_mower.utils.depot import 创建csv, 创建json
from arknights_mower.utils.device.application import (
    RECOVERABLE_DEVICE_ERRORS,
    create_device_control,
)
from arknights_mower.utils.device.recovery import wait_for_recovery
from arknights_mower.utils.device.touch_backend import TouchFailure
from arknights_mower.utils.log import logger
from arknights_mower.utils.news_checker import MaintenanceInfo, NewsChecker
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.path import get_path
from arknights_mower.utils.resource_pkg import (
    refresh_resource_at_boundary,
    resource_task_session,
)
from arknights_mower.utils.scheduler_task import protect_priority_tasks

base_scheduler = None
device_control = create_device_control()
_maintenance_timer = None
_maintenance_timer_key = None
_maintenance_timer_lock = Lock()
_notified_maintenance_ids = set()
_flash_probe_ids = set()


def _close_device_session():
    if device_control.shutdown_requested:
        # Application shutdown joins this worker before restoring preparation.
        return device_control.status()
    result = device_control.close()
    if not result.ok:
        logger.error(f"关闭设备会话失败：{result.error.message}")
    return result


_ADB_CONNECTION_FAILURES = {
    "Can't start adb server",
    "ADB server is not working",
    "Device connection failure",
}


def _is_adb_connection_failure(error: Exception) -> bool:
    return isinstance(error, ConnectionError) or (
        isinstance(error, RuntimeError) and str(error) in _ADB_CONNECTION_FAILURES
    )


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
                config.maintenance_recheck.set()
                config.wake_scheduler.set()
            elif info.update_type == "major":
                _stop_for_major_update(info)
            else:
                config.maintenance_recheck.set()
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
def main(saved_state, *, preparation_serial=None):
    global base_scheduler
    config.maintenance_recheck.clear()
    try:
        with (
            device_control.run(preparation_serial=preparation_serial),
            resource_task_session(),
        ):
            return _main(saved_state)
    finally:
        _close_device_session()
        _cancel_maintenance_timer()
        base_scheduler = None


def _main(saved_state):
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
    simulate(data)


def initialize(
    tasks: list,
    scheduler: BaseSchedulerSolver | None = None,
    *,
    connection_retries: int = 3,
) -> BaseSchedulerSolver:
    if scheduler:
        scheduler.handle_error(True)
        return scheduler

    if not device_control.run_active:
        _close_device_session().unwrap()
    try:
        device = device_control.start(connection_retries=connection_retries).unwrap()
        return _initialize_scheduler(tasks, device)
    except BaseException:
        _close_device_session()
        raise


def _initialize_scheduler(tasks, device):
    base_scheduler = BaseSchedulerSolver(device=device)
    from arknights_mower.utils.operators import build_global_plan

    plan, source_plan = build_global_plan(include_source=True)

    logger.debug(plan)
    base_scheduler.global_plan = plan
    base_scheduler.source_plan = source_plan
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
    # 关闭游戏次数计数器
    base_scheduler.task_count = 0

    return base_scheduler


def _resume_device_dispatch(scheduler=None, failure=None):
    def resume():
        if device_control.shutdown_requested or config.stop_mower.is_set():
            raise MowerExit
        device = device_control.recover().unwrap()
        if scheduler is not None:
            scheduler.device = device
            scheduler.recog.device = device
            if getattr(scheduler, "_idle_observation_pending", False):
                scheduler.recog.reset_after_external_control()
                scheduler._idle_observation_pending = False
            else:
                scheduler.recog.update()
        return device

    csleep(30)
    device = wait_for_recovery(resume, retry_errors=RECOVERABLE_DEVICE_ERRORS)
    if isinstance(failure, TouchFailure) and failure.delivery_unknown:
        logger.warning("输入结果待核实：保留当前任务，暂停设备调度，不重复提交副作用")
        while not config.stop_mower.is_set():
            device_control.pause_dispatch(failure)
            csleep(30)
            if device_control.shutdown_requested:
                raise MowerExit
            if scheduler is not None:
                wait_for_recovery(resume, retry_errors=RECOVERABLE_DEVICE_ERRORS)
        raise MowerExit
    return device


def simulate(saved):
    """
    具体调用方法可见各个函数的参数说明
    """
    logger.info(f"正在使用全局配置空间: {path.global_space}")
    tasks = saved["tasks"] if saved else []
    connection_retries = 1
    global base_scheduler
    if config.stop_mower.is_set():
        return
    success = False
    while not success:
        try:
            if config.stop_mower.is_set():
                raise MowerExit
            base_scheduler = initialize([], connection_retries=connection_retries)
            # saved 为空表示没有可载入的运行缓存。此时干员 current_room 尚未读取，
            # 首轮任务开始前必须暂缓副表判断，避免把“未知”误判成“不在工作”。
            base_scheduler.defer_backup_plan_until_mood_read = (
                not saved
                or bool(saved.get("initial_mood_pending", False))
                or config.conf.automatic_rescue_enable
                or bool(saved and saved.get("automatic_rescue_state"))
            )
            base_scheduler._initial_mood_refresh_rooms = set(
                saved.get("initial_mood_refresh_rooms", ()) if saved else ()
            ) | set(saved.get("initial_mood_probe_layout", {}) if saved else {})
            success = True
        except RECOVERABLE_DEVICE_ERRORS as exc:
            try:
                _resume_device_dispatch(failure=exc)
            except MowerExit:
                return
            continue
        except MowerExit:
            return
        except Exception as e:
            logger.exception(e)
            if config.stop_mower.is_set():
                return
            if _wait_before_early_login_retry():
                if config.stop_mower.is_set():
                    return
                connection_retries = 3
                continue
            # Session startup owns the shared recovery budget. Initialization
            # failures (including recognition errors) must not open a new one.
            raise
    # base_scheduler.仓库扫描() #别删了 方便我找
    validation_msg = base_scheduler.initialize_operators()
    if validation_msg is not None:
        logger.error(validation_msg)
        return
    validation_msg = base_scheduler.op_data.validate_backup_plans(max_seconds=5)
    if validation_msg.get("status") == "incomplete":
        logger.warning(f"排班校验未完成: {validation_msg['message']}")
    elif not validation_msg["success"]:
        logger.error(f"排班验证失败: {validation_msg['message']}")
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
                base_scheduler.op_data.select_group_binding(k, v.group)
                base_scheduler.op_data.operators[k].mood = v.mood
                base_scheduler.op_data.operators[k].time_stamp = v.time_stamp
                base_scheduler.op_data.operators[k].depletion_rate = v.depletion_rate
                base_scheduler.op_data.operators[k].current_room = v.current_room
                base_scheduler.op_data.operators[k].current_index = v.current_index
                base_scheduler.op_data.operators[k].dorm_position_version = getattr(
                    v, "dorm_position_version", 0
                )
                base_scheduler.op_data.operators[k].dorm_recovery_room = getattr(
                    v, "dorm_recovery_room", ""
                )
                base_scheduler.op_data.operators[k].dorm_recovery_index = getattr(
                    v, "dorm_recovery_index", -1
                )
                base_scheduler.op_data.operators[k].resting_from_train = getattr(
                    v, "resting_from_train", False
                )
                for attr, default in (
                    ("mood_is_prediction", False),
                    ("rest_mood_release_limit", None),
                    ("dorm_mood_fallback", ""),
                    ("dorm_mood_peers", {}),
                    ("idle_rest_check", None),
                    ("temporary_dorm_fill", False),
                ):
                    setattr(
                        base_scheduler.op_data.operators[k],
                        attr,
                        copy.deepcopy(getattr(v, attr, default)),
                    )
                base_scheduler.op_data.operators[k].dorm_recovery_fixed = getattr(
                    v, "dorm_recovery_fixed", ()
                )
            base_scheduler.op_data.restore_group_shift_state(
                saved.get("group_shift_state")
            )
            base_scheduler.waiting_group_shifts = saved.get("waiting_group_shifts", [])
            base_scheduler.op_data.restore_dorm_state(saved["dorm"])
            base_scheduler.op_data.facility_states = copy.deepcopy(
                saved.get("facility_states", {})
            )
            base_scheduler.emergency_state = copy.deepcopy(
                saved.get("automatic_rescue_state")
            )
            if isinstance(base_scheduler.emergency_state, dict):
                base_scheduler._emergency_validate_state()
                state = base_scheduler.emergency_state
                previous = dict(
                    zip(
                        state.get("handoff_names", state["backup_names"]),
                        state.get("handoff_conditions", state["frozen_conditions"]),
                    )
                )
                names = [backup.name for backup in base_scheduler.op_data.backup_plans]
                error = base_scheduler.op_data.swap_plan(
                    [previous.get(name, False) for name in names], refresh=True
                )
                if error:
                    raise ValueError(error)
            base_scheduler.op_data.idle_dorm_search_exhausted = saved.get(
                "idle_dorm_search_exhausted", False
            )
            base_scheduler.op_data.idle_dorm_search_stopped_at = saved.get(
                "idle_dorm_search_stopped_at"
            )
            base_scheduler.party_time = saved["party_time"]
            base_scheduler.daily_visit_friend = saved["daily_visit_friend"]
            base_scheduler.daily_report = saved["daily_report"]
            base_scheduler.daily_skland = saved["daily_skland"]
            base_scheduler.daily_mail = saved["daily_mail"]
            base_scheduler.task_count = saved["task_count"]
            from arknights_mower.utils.config.plan import migrate_backup_tasks

            base_scheduler.tasks = migrate_backup_tasks(
                tasks,
                saved.get("backup_plan_names", []),
                [backup.name for backup in base_scheduler.op_data.backup_plans],
                config.retired_backup_indices,
                retired=bool(saved.get("rescue_state"))
                or config.retired_backup_migrated
                or bool(
                    set(saved.get("backup_plan_names", []))
                    - {backup.name for backup in base_scheduler.op_data.backup_plans}
                ),
            )
            if len(base_scheduler.op_data.backup_plans) > 0:
                # 启动的时候按照条件触发副表
                base_scheduler.backup_plan_solver()
        except Exception as ex:
            logger.exception(ex)
    from arknights_mower.solvers.emergency import RESUME_META
    from arknights_mower.utils.emergency_recovery import ORDINARY_SHIFTS
    from arknights_mower.utils.scheduler_task import SchedulerTask

    if saved and saved.get("rescue_state"):
        base_scheduler.tasks[:] = [
            task
            for task in base_scheduler.tasks
            if task.type not in ORDINARY_SHIFTS
            and not getattr(task, "backup_shift_active", False)
        ]
    if (
        config.conf.automatic_rescue_enable
        or isinstance(base_scheduler.emergency_state, dict)
        or bool(saved and saved.get("initial_mood_pending"))
    ):
        base_scheduler._emergency_startup_pending = True
        base_scheduler.defer_backup_plan_until_mood_read = True
        base_scheduler.tasks[:] = [
            task for task in base_scheduler.tasks if task.meta_data != RESUME_META
        ]
        if not (saved and saved.get("initial_mood_pending")):
            base_scheduler._initial_mood_refresh_rooms = {
                room for room in base_scheduler.op_data.plan if room in base_room_list
            }
        base_scheduler.tasks.insert(0, SchedulerTask(time=datetime.now()))
    while True:
        try:
            config.maintenance_recheck.clear()
            refresh_resource_at_boundary()
            maintenance = NewsChecker.get_maintenance()
            _apply_version_update_resting_threshold(maintenance, base_scheduler)
            if maintenance is not None:
                _arm_maintenance_timer(maintenance)
                if _handle_maintenance(maintenance, base_scheduler):
                    return
            if len(base_scheduler.tasks) > 0:
                # 维护避让先于日常任务和等待预算，包含从存档恢复的专精换人。
                protect_priority_tasks(
                    base_scheduler.tasks,
                    op_data=getattr(base_scheduler, "op_data", None),
                )
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

                        scheduling(
                            base_scheduler.tasks,
                            op_data=base_scheduler.op_data,
                        )
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
                    # A maintenance timer may have ended this sleep. Recheck the
                    # announcement before dispatching another scheduler task.
                    continue

            base_scheduler.run()
        except RECOVERABLE_DEVICE_ERRORS as exc:
            try:
                _resume_device_dispatch(base_scheduler, exc)
            except MowerExit:
                return
            continue
        except MowerExit:
            return
        except (ConnectionError, ConnectionAbortedError, AttributeError) as e:
            logger.exception(
                "设备连接或页面识别失败：%s",
                e,
                extra={"archive_screenshots": not _is_adb_connection_failure(e)},
            )
            if _wait_before_early_login_retry():
                if config.stop_mower.is_set():
                    return
                continue
            try:
                _resume_device_dispatch(base_scheduler, e)
            except MowerExit:
                return
            continue
        except RuntimeError as e:
            logger.exception(
                "运行时发生错误，正在尝试恢复设备连接：%s",
                e,
                extra={"archive_screenshots": not _is_adb_connection_failure(e)},
            )
            if _wait_before_early_login_retry():
                if config.stop_mower.is_set():
                    return
                continue
            try:
                _resume_device_dispatch(base_scheduler, e)
            except MowerExit:
                return
        except Exception as e:
            logger.exception(
                "任务执行失败，正在刷新画面后继续：%s",
                e,
                extra={"archive_screenshots": True},
            )
            if _wait_before_early_login_retry():
                if config.stop_mower.is_set():
                    return
                continue
            try:
                base_scheduler.recog.update()
            except RECOVERABLE_DEVICE_ERRORS as exc:
                try:
                    _resume_device_dispatch(base_scheduler, exc)
                except MowerExit:
                    return
