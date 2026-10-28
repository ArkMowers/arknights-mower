"""手动队列任务复用现有执行器，并在真实任务依赖解除后继续剩余项目。"""

import copy
import hashlib
from datetime import datetime, timedelta

from arknights_mower.utils import config
from arknights_mower.utils.datetime import get_server_time
from arknights_mower.utils.scheduler_task import (
    TaskScope,
    TaskTypes,
    find_next_task,
    task_view,
)

LONG_TASKS = {
    TaskTypes.ROGUELIKE: "rogue",
    TaskTypes.SSS: "sss",
    TaskTypes.RECLAMATION: "rcl",
    TaskTypes.RA: "ra",
    TaskTypes.SECRET_FRONT: "sf",
}


def deferrable_dorm_task(task):
    return getattr(task, "type", None) == TaskTypes.FILL_DORM or (
        getattr(task, "type", None) == TaskTypes.RELEASE_DORM
        and not getattr(task, "strict_mood_limit", False)
        and not getattr(task, "emergency_recovery_release", False)
    )


def long_task_deadline(scheduler, limit):
    current = getattr(scheduler, "task", None)
    if getattr(current, "type", None) not in LONG_TASKS:
        current = None
    pending = next(
        (
            task
            for task in task_view(
                scheduler.tasks,
                TaskScope.DISPATCH,
                getattr(scheduler, "op_data", None),
            )
            if task is not current and not deferrable_dorm_task(task)
        ),
        None,
    )
    return min(pending.time, limit) if pending else limit


def run_long_task_if_dorm_pending(scheduler):
    pending = scheduler.find_next_task()
    if pending is None or not deferrable_dorm_task(pending):
        return False
    conf = config.conf
    if not any(
        getattr(conf, flag, False)
        for flag in ("RG", "COPILOT", "PARADOX", "SSS", "RCL", "RA", "SF")
    ):
        return False
    now = datetime.now()
    try:
        start = datetime.strptime(conf.maa_rg_sleep_min, "%H:%M").time()
        end = datetime.strptime(conf.maa_rg_sleep_max, "%H:%M").time()
        sleeping = (
            now.time() > start or now.time() < end
            if end < start
            else start < now.time() < end
        )
    except ValueError:
        sleeping = False
    if sleeping or long_task_deadline(
        scheduler, now + timedelta(hours=24)
    ) - now < timedelta(minutes=9):
        return False
    scheduler.maa_plan_solver([])
    return True


def manual_task_deadline(scheduler):
    if not hasattr(scheduler.task, "manual_deadline"):
        scheduler.task.manual_deadline = datetime.now() + timedelta(hours=24)
    if scheduler.task.type in LONG_TASKS:
        return long_task_deadline(scheduler, scheduler.task.manual_deadline)
    pending = find_next_task(
        [task for task in scheduler.tasks if task is not scheduler.task],
        compare_time=datetime.max,
        op_data=getattr(scheduler, "op_data", None),
    )
    return (
        min(pending.time, scheduler.task.manual_deadline)
        if pending
        else scheduler.task.manual_deadline
    )


def manual_task_snapshot(scheduler, task):
    """只有原先阻塞本任务的依赖变化才能释放等待；时间流逝不算变化。"""
    dependencies = getattr(task, "manual_dependencies", ())
    return copy.deepcopy(
        {
            "observations": {},
            "room_observations": {},
            "reservations": ([], []),
            "correction_groups": {},
            "dependencies": sorted(
                [
                    (pending.type, pending.time, pending.plan)
                    for pending in scheduler.tasks
                    if pending is not task
                    and (pending.type, pending.time) in dependencies
                ],
                key=lambda item: (item[1], item[0].value),
            ),
            "settings": hashlib.sha256(
                config.conf.model_dump_json().encode()
            ).hexdigest(),
        }
    )


def _wait_for_tasks(scheduler, task):
    task.manual_dependencies = [
        (pending.type, pending.time)
        for pending in scheduler.tasks
        if pending is not task and pending.time <= datetime.now() + timedelta(minutes=5)
    ]
    task.__dict__.pop("manual_deadline", None)
    scheduler._retain_failed_task(
        task, "为其他排队任务预留执行时间", [], dependency=True
    )
    return False


def _daily_steps(conf):
    steps = []
    for enabled, kind in (
        (
            conf.visit_friend_enable and conf.visit_friend_mode == "mower",
            TaskTypes.VISIT_FRIEND,
        ),
        (conf.report_enable, TaskTypes.REPORT),
        (conf.skland_enable, TaskTypes.SKLAND),
        (conf.check_mail_enable, TaskTypes.MAIL),
        (conf.recruit_enable, TaskTypes.RECRUIT),
        (conf.should_run_mower_mall, TaskTypes.CREDIT_SHOP),
        (conf.should_run_mower_stage_plan, TaskTypes.STAGE_PLAN),
    ):
        if enabled:
            steps.append(kind.display_value)
    if conf.has_maa_daily_tasks:
        steps.append("maa_daily")
    steps.append(TaskTypes.MISSION.display_value)
    return steps


def run_manual_task(scheduler, task):
    """每个单项只运行一次；组合任务在设备恢复或依赖等待后保留未执行项。"""
    if not hasattr(task, "manual_steps"):
        task.manual_steps = (
            _daily_steps(config.conf)
            if task.type == TaskTypes.DAILY
            else [task.type.display_value]
        )
    while task.manual_steps:
        if config.stop_mower.is_set():
            from arknights_mower.utils.csleep import MowerExit

            raise MowerExit
        if manual_task_deadline(scheduler) - datetime.now() < timedelta(minutes=5):
            return _wait_for_tasks(scheduler, task)
        kind = task.manual_steps[0]
        if kind == "maa_daily":
            if scheduler.maa_plan_solver(manual=True) is False:
                return _wait_for_tasks(scheduler, task)
        else:
            if (
                _run_single(
                    scheduler,
                    next(item for item in TaskTypes if item.display_value == kind),
                )
                is False
            ):
                return _wait_for_tasks(scheduler, task)
        task.manual_steps.pop(0)
    return True


def _run_single(scheduler, kind):
    from arknights_mower.solvers.credit import CreditSolver
    from arknights_mower.solvers.mail import MailSolver
    from arknights_mower.solvers.mission import MissionSolver
    from arknights_mower.solvers.recruit import RecruitSolver
    from arknights_mower.solvers.report import ReportSolver
    from arknights_mower.solvers.shop import CreditShop

    conf = config.conf
    today = get_server_time().date()
    if kind == TaskTypes.RECRUIT:
        RecruitSolver(scheduler.device, scheduler.recog).run()
        scheduler.last_execution["recruit"] = datetime.now()
    elif kind == TaskTypes.SKLAND:
        if scheduler.skland_plan_solver():
            scheduler.daily_skland = today
    elif kind == TaskTypes.MAIL:
        MailSolver(scheduler.device, scheduler.recog).run()
        scheduler.daily_mail = today
    elif kind == TaskTypes.REPORT:
        if ReportSolver(scheduler.device, scheduler.recog).run():
            scheduler.daily_report = today
    elif kind == TaskTypes.VISIT_FRIEND:
        if conf.visit_friend_mode == "maa":
            return scheduler.maa_plan_solver(
                ["Mall"], manual=True, mall_action="visit_friends"
            )
        scheduler.daily_visit_friend_attempt = today
        if CreditSolver(scheduler.device, scheduler.recog).run():
            scheduler.daily_visit_friend = today
    elif kind == TaskTypes.CREDIT_SHOP:
        if conf.maa_mall_mode == "maa":
            return scheduler.maa_plan_solver(
                ["Mall"], manual=True, mall_action="shopping"
            )
        CreditShop(scheduler.device, scheduler.recog).run()
    elif kind == TaskTypes.MISSION:
        MissionSolver(scheduler.device, scheduler.recog).run()
    elif kind == TaskTypes.STAGE_PLAN:
        if conf.stage_plan_runner == "maa":
            return scheduler.maa_plan_solver(["Fight", "Award"], manual=True)
        scheduler.mower_plan_solver(manual=True)
    elif kind in LONG_TASKS:
        return scheduler.maa_plan_solver([], manual=True, long_task=LONG_TASKS[kind])
