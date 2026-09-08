"""Screenshot-gated execution of per-plan assistant routes."""

import json
from datetime import datetime, timedelta

from arknights_mower.utils.mastery_support import (
    BASE_HOURS,
    REDUCERS,
    SupportPlanError,
    candidates,
    check_schedule_name,
    decode_json,
    decode_supports,
    rate,
    schedule_context,
    stage_for,
    stage_route,
)


def context(solver):
    active = getattr(getattr(solver, "op_data", None), "plan", None)
    return schedule_context(active=active if isinstance(active, dict) else None)


def persist(plan, runtime):
    from arknights_mower.utils.mastery_db import save_support_plan

    if not save_support_plan(plan["id"], runtime, runtime=True):
        raise SupportPlanError("协助执行状态保存失败")
    plan["support_runtime"] = json.dumps(runtime, ensure_ascii=False)


def warning(plan, level, message):
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    if should_notify("support_swap", f"{plan['id']}:{level}"):
        send_message(
            f"{plan.get('char_name', '')} 专{level}：{message}", level="WARNING"
        )


def prepare(solver, plan, level):
    """Validate the stage and carried halving without changing occupants."""
    saved = decode_supports(plan)
    if not saved:
        return
    route = next((s for s in saved["stages"] if s["level"] == level), None)
    if route is None:
        raise SupportPlanError("专精阶段与协助方案不一致，请重新添加计划")
    options, central = candidates(
        plan["char_id"],
        context=context(solver),
        include_dynamic=route.get("manual", False),
    )
    first = options.get(route["operator"], {}).get(level)
    if first is None:
        raise SupportPlanError("计划协助者已不可用或已加入非训练室排班，请修改协助方案")
    swap = options.get(route.get("swap_target"), {}).get(level)
    previous = decode_json(plan.get("support_runtime"))
    from arknights_mower.solvers.mastery_reader import _read_slots_checked

    support, trainee, _, reliable = _read_slots_checked(solver)
    if not reliable:
        raise SupportPlanError("无法确认当前训练室协助者，请重试")
    check_schedule_name(support, context(solver)[0])
    from arknights_mower.utils import config

    follows = config.conf.assistant_follows_schedule
    if follows:
        first = options.get(support, {}).get(level)
        if first is None:
            raise SupportPlanError("协助位跟随排班时，需要先安排可用协助者")
        swap = None
    carry = None
    if (
        reliable
        and trainee == plan.get("char_name")
        and previous
        and previous.get("level") == level - 1
        and previous.get("working_operator") == support
        and previous.get("working_halves")
        and previous.get("working_since")
    ):
        elapsed = (
            datetime.now() - datetime.fromisoformat(previous["working_since"])
        ).total_seconds()
        # Completion can have been waiting for collection: only count actual training time.
        until = previous.get("working_until")
        if until:
            elapsed = min(
                elapsed,
                (
                    datetime.fromisoformat(until)
                    - datetime.fromisoformat(previous["working_since"])
                ).total_seconds(),
            )
        if elapsed > 5 * 3600:
            carry = support
    work = BASE_HOURS[level] * (0.5 if carry else 1)
    manual = route.get("manual", False)
    selected = stage_route(
        first,
        swap,
        level,
        work,
        central,
        route.get("mastery_swap_buffer", 10),
        manual=manual,
    )
    if selected is None:
        selected = stage_route(
            first, None, level, work, central, route.get("mastery_swap_buffer", 10)
        )
    selected.update(
        manual=manual,
        activate_with=carry,
        half_inherited=bool(carry),
        working_operator=None,
        first_halves=first["halves"],
        swap_halves=swap["halves"] if swap else False,
    )
    persist(plan, selected)


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
    persist(plan, route)


def refresh_end(plan, level, end):
    route = stage_for(plan, level)
    if (
        route
        and route.get("working_operator")
        and route.get("working_until") != end.isoformat()
    ):
        route["working_until"] = end.isoformat()
        persist(plan, route)


def schedule(solver, plan, end, level):
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
    current_rate = rate(route["efficiency"], route["central_bonus"])
    tail_rate = rate(route["swap_efficiency"], route["central_bonus"])
    target_seconds = (300 + route["mastery_swap_buffer"]) * 60
    now = datetime.now()
    left = (end - now).total_seconds()
    if route.get("swap_halves", True) and left * current_rate / tail_rate < 301 * 60:
        return None
    at = now + timedelta(
        seconds=max(0, left - target_seconds * tail_rate / current_rate)
    )
    enqueue(solver, plan, at, route["swap_target"])
    return at


def enqueue(solver, plan, at, name):
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


def pick_reducer(work_seconds, current_rate, stats, central, buffer):
    """Return (candidate, delay_seconds). A slower alternate may need a later handoff."""
    minimum = (300 + max(1, buffer)) * 60
    for candidate in stats:
        dest_rate = rate(candidate["efficiency"], central)
        available_seconds = work_seconds / dest_rate
        if available_seconds <= 0 or (
            candidate["halves"] and available_seconds < 301 * 60
        ):
            continue
        tail = min(available_seconds, minimum)
        delay = max(0, (work_seconds - tail * dest_rate) / current_rate)
        return candidate, delay
    return None, 0


def confirmed_panel(solver, plan, level):
    from arknights_mower.solvers.mastery_reader import (
        RoomState,
        _close_room_detail,
        _plan_matches_room,
        read_main_panel,
    )
    from arknights_mower.utils.scene import Scene

    if solver.train_scene() == Scene.INFRA_DETAILS:
        _close_room_detail(solver)
    if solver.train_scene() != Scene.TRAIN_MAIN:
        raise SupportPlanError("未返回训练室主页面，停止换人")
    panel = read_main_panel(solver)
    if (
        not panel
        or panel.countdown_state != "active"
        or panel.mastery_tier != level
        or not panel.operator_name
        or not panel.skill_name
        or not _plan_matches_room(plan, RoomState("training", panel))
    ):
        raise SupportPlanError("训练室状态变化或读取失败，停止换人")
    return panel


def place(solver, plan, level, name):
    from arknights_mower.solvers.mastery_reader import _read_slots_checked

    check_schedule_name(name, context(solver)[0])
    confirmed_panel(solver, plan, level)
    solver.choose_train([name, "Current"])
    actual, trainee, _, reliable = _read_slots_checked(solver)
    if not reliable or actual != name or trainee != plan.get("char_name"):
        raise SupportPlanError("换人后无法确认协助者与训练位，停止自动换人")
    panel = confirmed_panel(solver, plan, level)
    record_work(plan, level, name, panel.countdown)
    return panel


def recover(solver, plan, room):
    """Reuse the room visit; no roster scan or optimizer in the scheduler loop."""
    from arknights_mower.solvers.mastery_reader import (
        _find_swap_task,
        _read_slots_checked,
    )

    level = room.panel.mastery_tier
    route = stage_for(plan, level)
    if not route or plan.get("swap_frozen"):
        return False
    support, _, _, reliable = _read_slots_checked(solver)
    if not reliable:
        return False
    if support == route.get("working_operator"):
        refresh_end(plan, level, room.panel.countdown)
    if support == route.get("swap_target"):
        return False
    if support != route["operator"]:
        if (
            support in REDUCERS
            and (room.panel.countdown - datetime.now()).total_seconds()
            < (300 + route["mastery_swap_buffer"]) * 60
        ):
            return False
        enqueue(solver, plan, datetime.now(), route["operator"])
        return True
    if _find_swap_task(solver, str(plan["id"])) is not None:
        return True
    if not route.get("working_operator"):
        # Observed now; do not invent a historical start time or a halving credit.
        route["working_operator"] = support
        persist(plan, route)
    return schedule(solver, plan, room.panel.countdown, level) is not None


def perform_swap(solver, plan, panel, support, reliable):
    from arknights_mower.solvers.mastery import _schedule_collect_after_swap
    from arknights_mower.solvers.mastery_reader import (
        RoomState,
        _plan_matches_room,
    )
    from arknights_mower.utils.csleep import MowerExit
    from arknights_mower.utils.mastery_db import update_plan_status

    level = panel.mastery_tier if panel else None
    if (
        not reliable
        or not panel
        or panel.countdown_state != "active"
        or not level
        or not panel.operator_name
        or not panel.skill_name
        or not _plan_matches_room(plan, RoomState("training", panel))
    ):
        return
    route = stage_for(plan, level)
    if not route:
        return
    if support == route.get("swap_target"):
        refresh_end(plan, level, panel.countdown)
        _schedule_collect_after_swap(solver, plan, tier=level)
        return
    try:
        options, central = candidates(
            plan["char_id"],
            context=context(solver),
            include_dynamic=route.get("manual", False),
        )
        current = options.get(support, {}).get(level)
        if support and current is None:
            raise SupportPlanError("当前协助者不在可用名单中，停止自动换人")
        current_rate = (
            rate(current["efficiency"], central) if current else 1 + central / 100
        )
        names = [route.get("swap_target")]
        if not route.get("manual"):
            names += [n for n in REDUCERS if n not in names]
        stats = [
            options[n][level]
            for n in names
            if n in options and (route.get("manual") or options[n][level]["halves"])
        ]
        swapping = bool(route.get("swap_target")) and level < plan["target_level"]
        correcting = support != route["operator"]
        first = options.get(route["operator"], {}).get(level)
        if not swapping and not correcting:
            _schedule_collect_after_swap(solver, plan, tier=level)
            return
        if not stats and not correcting:
            update_plan_status(plan["id"], "training", swap_frozen=1)
            _schedule_collect_after_swap(solver, plan, tier=level)
            return  # No reducers is a normal roster limitation; no alert.
        panel = confirmed_panel(solver, plan, level)
        work = max(0, (panel.countdown - datetime.now()).total_seconds()) * current_rate
        selected, delay = (
            pick_reducer(
                work, current_rate, stats, central, route["mastery_swap_buffer"]
            )
            if swapping
            else (None, 0)
        )
        # Restore the initial assistant when an empty/foreign slot is observed, unless
        # we can directly hand off to the reducer now. Never briefly remove a reducer
        # that cannot earn its five hours again.
        if correcting and (selected is None or delay > 5):
            if (
                support in REDUCERS
                and work / current_rate < (300 + route["mastery_swap_buffer"]) * 60
            ):
                _schedule_collect_after_swap(solver, plan, tier=level)
                return
            if first is None:
                raise SupportPlanError("计划协助者已不可用，无法恢复协助位")
            route.update(
                efficiency=first["efficiency"],
                first_halves=first["halves"],
                central_bonus=central,
            )
            persist(plan, route)
            panel = place(solver, plan, level, first["name"])
            if schedule(solver, plan, panel.countdown, level) is None:
                _schedule_collect_after_swap(solver, plan, tier=level)
            return
        if selected is None:
            if stats:
                warning(
                    plan,
                    level,
                    "换入减半教官后的剩余训练不足 5 小时，已保留当前协助者，本阶段不再尝试替换",
                )
            update_plan_status(plan["id"], "training", swap_frozen=1)
        else:
            route.update(
                swap_target=selected["name"],
                swap_efficiency=selected["efficiency"],
                central_bonus=central,
                swap_halves=selected["halves"],
            )
            persist(plan, route)
            if delay > 5:
                enqueue(
                    solver,
                    plan,
                    datetime.now() + timedelta(seconds=delay),
                    selected["name"],
                )
                return
            panel = place(solver, plan, level, selected["name"])
            if (
                selected["halves"]
                and (panel.countdown - datetime.now()).total_seconds() <= 5 * 3600
            ):
                warning(
                    plan, level, "换人后的实际倒计时不足 5 小时，下一阶段减半无法保证"
                )
            update_plan_status(plan["id"], "training", swap_frozen=1)
        _schedule_collect_after_swap(solver, plan, tier=level)
    except MowerExit:
        raise
    except Exception as exc:
        warning(plan, level, str(exc))
        update_plan_status(plan["id"], "training", swap_frozen=1)
        _schedule_collect_after_swap(solver, plan, tier=level)
