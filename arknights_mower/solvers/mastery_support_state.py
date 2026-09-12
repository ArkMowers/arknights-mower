"""Persist assistant execution records and schedule_support_swap bounded swap tasks."""

from datetime import datetime, timedelta

from arknights_mower.utils.mastery_support import (
    SupportPlanError,
    decode_json,
    encode_supports,
    rate,
    stage_for,
)


def save_runtime(plan, runtime):
    from arknights_mower.utils.mastery_db import save_support_plan

    if not save_support_plan(plan["id"], runtime, runtime=True):
        raise SupportPlanError("协助执行状态保存失败")
    plan["support_runtime"] = encode_supports(runtime)


def _notification_level(plan, level):
    """Use cached progress only for notification identity, never device actions."""
    if type(level) is int and level in (1, 2, 3):
        return level
    try:
        runtime = decode_json(plan.get("support_runtime"))
    except SupportPlanError:
        return None
    saved = runtime.get("level") if isinstance(runtime, dict) else None
    return saved if type(saved) is int and saved in (1, 2, 3) else None


def notify_support_failure(plan, level, message):
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    level = _notification_level(plan, level)
    stage = f"专{level}" if level is not None else "专精阶段未知"
    key = level if level is not None else "unknown"
    if should_notify("support_swap", f"{plan['id']}:{key}"):
        send_message(f"{plan.get('char_name', '')} {stage}：{message}", level="WARNING")


def record_work(plan, level, name, until=None):
    route = stage_for(plan, level)
    if not route:
        return
    route.update(
        working_operator=name,
        working_since=datetime.now().isoformat(),
        working_halves=route.get("first_halves", False)
        if name == route["operator"]
        else route.get("swap_halves", False),
        working_until=until.isoformat() if until else None,
    )
    save_runtime(plan, route)


def refresh_end(plan, level, end):
    route = stage_for(plan, level)
    if (
        route
        and route.get("working_operator")
        and route.get("working_until") != end.isoformat()
    ):
        route["working_until"] = end.isoformat()
        save_runtime(plan, route)


def schedule_support_swap(solver, plan, end, level):
    route = stage_for(plan, level)
    if (
        not route
        or not route.get("swap_target")
        or level >= plan["target_level"]
        or plan.get("swap_frozen")
    ):
        return None
    if route.get("working_operator") != route["operator"]:
        return None
    # Scheduled central staff may be absent: preserve the legacy conservative ratio.
    current_rate = rate(route["efficiency"])
    tail_rate = rate(route["swap_efficiency"], route["central_bonus"])
    target_seconds = (300 + route["mastery_swap_buffer"]) * 60
    now = datetime.now()
    left = (end - now).total_seconds()
    check_rate = rate(route["efficiency"], route["central_bonus"])
    if route.get("swap_halves", True) and left * check_rate / tail_rate < 301 * 60:
        return None
    at = now + timedelta(
        seconds=max(0, left - target_seconds * tail_rate / current_rate)
    )
    enqueue_support_swap(solver, plan, at, route["swap_target"])
    return at


def enqueue_support_swap(solver, plan, at, name):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    # Do not mutate/remove the task currently being dispatched (main loop owns its removal).
    for task in solver.tasks:
        if (
            task is not getattr(solver, "task", None)
            and task.type == TaskTypes.SWAP_SUPPORT
            and getattr(task, "plan_key", None) == str(plan["id"])
        ):
            task.time = at
            return
    task = SchedulerTask(
        time=at,
        task_type=TaskTypes.SWAP_SUPPORT,
        meta_data=f"{plan.get('char_name', '')} 换入{name}",
    )
    task.plan_key = str(plan["id"])
    solver.tasks.append(task)


def finish_support_swap(solver, plan, level, freeze=False):
    from arknights_mower.solvers.mastery import _schedule_collect_after_swap
    from arknights_mower.utils.mastery_db import update_plan_status

    try:
        if freeze:
            update_plan_status(plan["id"], "training", swap_frozen=1)
    finally:
        _schedule_collect_after_swap(solver, plan, tier=level)


def stop_support_swap(solver, plan, level, reason):
    try:
        notify_support_failure(plan, level, reason)
    finally:
        finish_support_swap(solver, plan, level, freeze=True)


def select_swap_support(
    work_seconds, current_rate, stats, settings, *, schedule_rate=None
):
    """Validate with nominal rates, while keeping conservative handoff timing."""
    central, buffer = settings
    schedule_rate = current_rate if schedule_rate is None else schedule_rate
    remaining = work_seconds / current_rate
    minimum = (300 + max(1, buffer)) * 60
    for candidate in stats:
        dest_rate = rate(candidate["efficiency"], central)
        available_seconds = work_seconds / dest_rate
        if available_seconds <= 0 or (
            candidate["halves"] and available_seconds < 301 * 60
        ):
            continue
        # The more permissive final check must not postpone an already-due swap.
        # A slower alternate still uses the original conservative scheduling rate.
        delay = max(0, remaining - minimum * dest_rate / schedule_rate)
        return candidate, delay
    return None, 0
