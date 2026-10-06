"""初始化原生周转预演与实测心情恢复目标。"""

import copy
import hashlib
import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil, isfinite

from arknights_mower.utils.resting_priority import (
    RestingTier,
    crafting_rest_order,
    has_resting_mood,
    resting_key,
    resting_tier,
)
from arknights_mower.utils.scheduler_task import TaskTypes

WORK_EVENTS = {"crafting", "fiammetta_before", "fiammetta_after", "fiammetta_charge"}
ORDINARY_SHIFTS = {
    TaskTypes.SHIFT_OFF,
    TaskTypes.SHIFT_ON,
    TaskTypes.EXHAUST_OFF,
    TaskTypes.SELF_CORRECTION,
    TaskTypes.RE_ORDER,
    TaskTypes.SWITCH_PRODUCT,
}


def mood_context(data, room):
    """实际驻员及产物构成采样环境；床位索引由采样独立记录。"""
    roster = sorted(
        (op.current_index, op.name)
        for op in data.operators.values()
        if op.current_room == room
    )
    product = getattr(data, "facility_states", {}).get(room, {}).get("product")
    payload = json.dumps(
        [room, roster, product], ensure_ascii=False, sort_keys=True, default=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def percentile(values, fraction):
    values = sorted(values)
    return values[max(0, ceil(len(values) * fraction) - 1)]


def history_rate(rows, room, context, index=None, *, recovering=False):
    """每条记录包含心情、时间、前后房间、事件、环境和床位。"""
    slopes = []
    previous = None
    for row in rows:
        mood, stamp, before, current, event, key, slot = row
        try:
            stamp = datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            previous = None
            continue
        valid = (
            key == context
            and current == room
            and before == current
            and event not in WORK_EVENTS
            and event in (None, "")
            and isinstance(mood, (int, float))
            and isfinite(mood)
            and 0 < mood < 24
            and (index is None or slot == index)
        )
        if valid and previous is not None:
            old_mood, old_stamp = previous
            hours = (stamp - old_stamp).total_seconds() / 3600
            if 1 / 6 <= hours <= 12:
                slope = (mood - old_mood) / hours
                slope = slope if recovering else -slope
                if slope > 0 and isfinite(slope):
                    slopes.append(slope)
        previous = (mood, stamp) if valid else None
    if len(slopes) < 3:
        return None
    return percentile(slopes, 0.25 if recovering else 0.75)


def history_cycle(rows, room, context):
    """同一工作环境的实测轮休或充能周期；不足三轮时不制造周期。"""
    cycles, start = [], None
    for mood, stamp, before, current, event, key, slot in rows:
        try:
            stamp = datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            start = None
            continue
        if event == "crafting":
            start = None
            continue
        if start is not None and (
            before == room
            and current.startswith("dorm")
            or event in ("fiammetta_before", "fiammetta_charge")
        ):
            hours = (stamp - start).total_seconds() / 3600
            if 1 / 6 <= hours <= 12:
                cycles.append(hours)
            start = None
        if current == room and key == context:
            if before != room or event == "fiammetta_after":
                start = stamp
        elif current == room and key != context:
            start = None
    return percentile(cycles, 0.75) if len(cycles) >= 3 else None


def recovery_target(data, name, rate=None, opportunity=None, now=None):
    """无适用历史时使用正常下班线；超上限目标保持不可行。"""
    op = data.operators[name]
    if op.rest_in_full:
        return op.upper_limit, "rest_in_full"
    if data._can_standby(op):
        return min(op.upper_limit, data.rescue_mood_threshold(op)), "standby"
    normal = data.resting_mood_threshold(op)
    if rate is None or opportunity is None:
        return min(op.upper_limit, normal), "fallback"
    now = now or datetime.now()
    hours = max(0, (opportunity - now).total_seconds() / 3600)
    floor = op.lower_limit if op.exhaust_require else normal
    return floor + rate * hours + max(1, rate / 4), "history"


@dataclass(frozen=True)
class NativeProjection:
    opportunity: datetime | None
    complete: bool
    reason: str = ""


def primary_names(data):
    from arknights_mower.utils.operators import TRADE_ORDER_AGENTS

    return [
        op.name
        for op in data.operators.values()
        if op.is_high()
        and op.name not in TRADE_ORDER_AGENTS
        and op.room in data.plan
        and not op.room.startswith("dorm")
        and op.room not in ("factory", "train")
        and resting_tier(data, op.name) != RestingTier.EXCLUDED
    ]


def exhaust_rest_due(data, op, tasks, now):
    """用尽组仅在已休息、个人下限或既有用尽任务到期时参与当前轮休。"""
    members = data.groups.get(op.group, [op.name])
    exhausted = [
        data.operators[name] for name in members if data.operators[name].exhaust_require
    ]
    if not exhausted or op.is_resting():
        return True
    if any(
        has_resting_mood(member) and member.current_mood(now) <= member.lower_limit
        for member in exhausted
    ):
        return True
    return any(
        task.type == TaskTypes.EXHAUST_OFF
        and task.time <= now
        and set(task.meta_data.split(",")) & set(members)
        for task in tasks
    )


def native_opportunity(solver, required, now=None, *, budget=128, current_only=False):
    """在副本上搜索轮休；当前模式只检查可立即执行的安排，不预测速率。"""
    now = now or datetime.now()
    initial = copy.deepcopy(
        solver.op_data, {id(solver.op_data.eval_model): solver.op_data.eval_model}
    )
    required = set(required)
    pending = [
        task
        for task in solver.tasks
        if task.type
        in (
            TaskTypes.SHIFT_OFF,
            TaskTypes.SHIFT_ON,
            TaskTypes.RELEASE_DORM,
            TaskTypes.SELF_CORRECTION,
            TaskTypes.RE_ORDER,
            TaskTypes.NOT_SPECIFIC,
        )
        and task.plan
        and not getattr(task, "arrangement_retry_room", None)
    ]
    fia = initial.operators.get("菲亚梅塔")
    charges = [
        task
        for task in solver.tasks
        if task.type == TaskTypes.FIAMMETTA
        and task.plan
        and (not current_only or not getattr(task, "arrangement_retry_room", None))
        and task.meta_data in required
        and fia is not None
        and fia.current_room == fia.room
        and has_resting_mood(fia)
        and task.meta_data in fia.replacement
        and any(
            "菲亚梅塔" in names and task.meta_data in names
            for names in task.plan.values()
        )
    ]
    queue = deque([(initial, now, frozenset(), frozenset())])
    visited = set()
    uncertain = False
    while queue and budget:
        budget -= 1
        data, when, used, served = queue.popleft()
        served = served | {
            name
            for name in required
            if name in data.operators and data.operators[name].is_resting()
        }
        remaining = {
            name for name in required if name in data.operators and name not in served
        }
        if not remaining:
            return NativeProjection(when, True)
        key = (
            tuple(
                sorted(
                    (n, o.current_room, o.current_index)
                    for n, o in data.operators.items()
                )
            ),
            when,
            used,
            served,
        )
        if key in visited:
            continue
        visited.add(key)
        trial = copy.copy(solver)
        trial.op_data = data
        trial.tasks = copy.deepcopy(solver.tasks)
        trial.task = None
        trial._emergency_handoff = True
        groups = {}
        for name in primary_names(data):
            op = data.operators[name]
            if (
                op.multi_group
                or op.is_resting()
                or (current_only and not exhaust_rest_due(data, op, trial.tasks, when))
            ):
                continue
            if name in remaining or (
                has_resting_mood(op)
                and op.current_mood() <= data.resting_mood_threshold(op)
            ):
                groups[op.group or name] = (
                    data.shift_group_members(op.group) if op.group else [name]
                )
        for members in groups.values():
            candidate = copy.copy(trial)
            candidate.op_data = copy.deepcopy(
                data, {id(data.eval_model): data.eval_model}
            )
            candidate.tasks = copy.deepcopy(trial.tasks)
            plan = {}
            try:
                candidate.get_resting_plan(
                    list(members),
                    [],
                    plan,
                    candidate.op_data.active_high_resting_count(),
                )
                if (
                    not plan
                    and current_only
                    and any(data.operators[name].exhaust_require for name in members)
                ):
                    support = candidate._plan_exhaust_support(list(members))
                    if support:
                        coordinated = data.project_arrangements([support])
                        queue.append((coordinated, when, used, served))
            except Exception:
                uncertain = True
                continue
            if plan:
                # 原生规划把床位预约放在 dorm 中，执行计划另行补全这些位置。
                for bed in candidate.op_data.dorm:
                    if bed.name in members:
                        room, index = bed.position
                        plan.setdefault(room, ["Current"] * len(data.plan[room]))[
                            index
                        ] = bed.name
                projected = candidate.op_data.project_arrangements([plan])
                admitted = {
                    name
                    for name in members
                    if name in required and not projected.operators[name].is_working()
                }
                queue.append((projected, when, used, served | admitted))
        events = []
        for i, task in enumerate(pending):
            event_id = ("task", i)
            if event_id not in used:
                events.append((max(when, task.time), event_id, task.plan))
        for i, task in enumerate(charges):
            event_id = ("charge", i)
            current_fia = data.operators.get("菲亚梅塔")
            if current_only and (
                current_fia is None
                or not has_resting_mood(current_fia)
                or current_fia.mood_is_prediction
                or current_fia.mood < current_fia.upper_limit
                or (current_fia.current_room, current_fia.current_index)
                != (current_fia.room, current_fia.index)
            ):
                continue
            if event_id not in used:
                events.append((max(when, task.time), event_id, {}))
        for bed in data.dorm:
            if current_only:
                continue
            op = data.operators.get(bed.name)
            event_id = ("bed", bed.name, bed.position)
            if op is None or op.multi_group or event_id in used:
                continue
            if bed.time is None:
                if op.is_high():
                    uncertain = True
                continue
            members = data.shift_group_members(op.group) if op.group else [op.name]
            plan = {}
            for member in members:
                worker = data.operators[member]
                if worker.room in data.plan:
                    plan.setdefault(
                        worker.room, ["Current"] * len(data.plan[worker.room])
                    )[worker.index] = member
            events.append((max(when, bed.time), event_id, plan))
        for time, event_id, plan in events:
            if current_only and time > now:
                continue
            if time - now > timedelta(hours=12):
                uncertain = True
                continue
            projected = copy.deepcopy(data, {id(data.eval_model): data.eval_model})
            if current_only and event_id[0] == "task":
                event_task = copy.deepcopy(pending[event_id[1]])
                if event_task.type == TaskTypes.RELEASE_DORM:
                    for name in event_task.release_dorm_targets():
                        resident = projected.operators.get(name)
                        if not event_task.strict_mood_limit and (
                            not has_resting_mood(resident)
                            or resident.mood_is_prediction
                            or resident.mood < resident.upper_limit
                        ):
                            event_task.remove_release_dorm_operator(name)
                    if not event_task.plan:
                        continue
                    checker = copy.copy(trial)
                    checker.op_data = projected
                    checker.tasks = copy.deepcopy(trial.tasks)
                    try:
                        checker.prepare_release_dorm(event_task)
                    except Exception:
                        uncertain = True
                        continue
                    if not event_task.plan:
                        continue
                    plan = event_task.plan
            timely = True
            for name in remaining:
                op = projected.operators[name]
                if time > when and op.is_working():
                    if not has_resting_mood(op) or op.depletion_rate <= 0:
                        uncertain = True
                        timely = False
                        break
                    mood = (
                        op.current_mood()
                        - op.depletion_rate * (time - when).total_seconds() / 3600
                    )
                    if mood <= op.lower_limit:
                        timely = False
                        break
                    op.mood, op.time_stamp = mood, datetime.now()
            if not timely:
                continue
            for names in plan.values():
                for name in names:
                    if (
                        not current_only
                        and name in projected.operators
                        and projected.operators[name].is_resting()
                    ):
                        op = projected.operators[name]
                        op.mood, op.time_stamp = op.upper_limit, datetime.now()
            charged = set()
            if event_id[0] == "charge":
                name = charges[event_id[1]].meta_data
                projected.operators[name].mood = projected.operators[name].upper_limit
                projected.operators[name].time_stamp = datetime.now()
                charged.add(name)
                if current_only:
                    projected.operators["菲亚梅塔"].mood = 0
            queue.append(
                (
                    projected.project_arrangements([plan]),
                    time,
                    used | {event_id},
                    served | charged,
                )
            )
    return NativeProjection(
        None,
        not (queue or uncertain),
        "budget_or_unknown" if queue or uncertain else "blocked",
    )


def emergency_dorm_plan(
    data, state, tasks=(), *, members=None, reallocate=False, recovery_order=None
):
    """救急优先连续安排同组恢复；余床沿用共享候选和预约。"""
    from arknights_mower.utils.dorm_candidates import (
        dorm_candidate_mood,
        dorm_candidates,
        dorm_task_reservations,
    )

    reserved, slots = dorm_task_reservations(data, tasks)
    reserved.update(
        name
        for task in tasks
        if getattr(task, "strict_mood_limit", False)
        for name in task.release_dorm_targets()
    )
    ready = set(state.get("ready_members", ()))
    targets = state["targets"]
    requested = targets if members is None else members
    need = {
        name
        for name in requested
        if name in targets
        and name not in reserved | ready
        and (op := data.operators.get(name)) is not None
        and not op.room.startswith("dorm")
        and (
            not has_resting_mood(op) or op.mood_is_prediction or op.mood < targets[name]
        )
        and not data.rest_mood_complete(name)
        and not op.is_working()
        and resting_tier(data, name) != RestingTier.EXCLUDED
    }
    residents = {bed.name for bed in data.all_dorms() if bed.name}
    ordinary = set()
    waiting_primary = any(
        name not in ready
        and (op := data.operators.get(name)) is not None
        and op.is_working()
        and not op.room.startswith("dorm")
        and not data._can_standby(op)
        and not data.rest_mood_complete(name)
        and resting_tier(data, name) != RestingTier.EXCLUDED
        and (not has_resting_mood(op) or op.mood_is_prediction or op.mood < target)
        for name, target in targets.items()
    )
    if members is None and not waiting_primary:
        candidates = dorm_candidates(
            data, reserved | set(targets) | ready, current_residents=residents
        )
        ordinary = {
            name
            for name in [*candidates.recovering, *candidates.unknown]
            if name in data.operators
            and (mood := dorm_candidate_mood(data, name)) is not None
            and mood < 24
        }
    protected = {
        name
        for name, target in targets.items()
        if name not in ready
        and (op := data.operators.get(name)) is not None
        and op.is_resting()
        and (not has_resting_mood(op) or op.mood_is_prediction or op.mood < target)
    }
    beds = [
        bed
        for bed in data.all_dorms()
        if bed.position not in slots
        and bed.name not in reserved | (set() if reallocate else protected)
    ]
    plan = {}
    if reallocate:
        # 独立空床预演让旧住客与新恢复者共用排序，不修改实测床位。
        beds = [copy.copy(bed) for bed in beds]
        for bed in beds:
            room, index = bed.position
            plan.setdefault(room, ["Current"] * len(data.plan[room]))[index] = ""
            bed.name, bed.time = "", None
    probe = data.project_arrangements([plan]) if reallocate else copy.copy(data)
    probe.dorm = beds
    groups = {}
    recovery_order = recovery_order or {}
    for name in sorted(
        need,
        key=lambda name: (
            resting_tier(data, name),
            recovery_order.get(name, (2, float("inf"))),
            resting_key(data, name),
            name,
        ),
    ):
        group = (resting_tier(data, name), data.operators[name].group or name)
        groups.setdefault(group, []).append(name)
    ordered = [name for members in groups.values() for name in members]
    ordinary.discard("菲亚梅塔")
    ordered.extend(
        crafting_rest_order(
            data, sorted(ordinary, key=lambda name: (resting_key(data, name), name))
        )
    )
    for name in ordered:
        op = data.operators[name]
        if (name in residents and not reallocate) or op.is_working():
            continue
        active_groups = {op.group} if op.group else set()
        index = probe._find_dorm_slot(
            name,
            set(),
            active_groups=active_groups,
            plan=plan,
            isolation=not reallocate,
        )
        if index is None:
            continue
        bed = beds.pop(index)
        room, position = bed.position
        plan.setdefault(room, ["Current"] * len(data.plan[room]))[position] = name
    from arknights_mower.utils.scheduler_task import plan_dorm_isolation

    return plan_dorm_isolation(data, plan, slots)
