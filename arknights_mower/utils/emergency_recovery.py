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
    """无适用历史时使用正常下班线加一点；超上限目标保持不可行。"""
    op = data.operators[name]
    normal = data.resting_mood_threshold(op)
    if rate is None or opportunity is None:
        return min(op.upper_limit, normal + 1), "fallback"
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


def native_opportunity(
    solver, required, now=None, *, budget=128, deadlines=None, rates=None, earliest=None
):
    """在副本上搜索轮休及已知恢复事件；预算不足不证明恢复阻塞。"""
    now = now or datetime.now()
    initial = copy.deepcopy(solver.op_data)
    deadlines, rates, earliest = deadlines or {}, rates or {}, earliest or {}
    for name, rate in rates.items():
        if name in initial.operators:
            initial.operators[name].depletion_rate = rate
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
            if op.is_resting():
                continue
            if earliest.get(name, now) > when:
                continue
            if name in remaining or (
                has_resting_mood(op)
                and op.current_mood() <= data.resting_mood_threshold(op)
            ):
                groups[op.group or name] = data.groups.get(op.group, [name])
        progressed = False
        for members in groups.values():
            candidate = copy.copy(trial)
            candidate.op_data = copy.deepcopy(data)
            candidate.tasks = copy.deepcopy(trial.tasks)
            plan = {}
            try:
                candidate.get_resting_plan(
                    list(members),
                    [],
                    plan,
                    candidate.op_data.active_high_resting_count(),
                )
            except Exception:
                uncertain = True
                continue
            if plan:
                progressed = True
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
        for name in remaining:
            if earliest.get(name, now) > when:
                events.append((earliest[name], ("eligible", name), {}))
        for i, task in enumerate(pending):
            event_id = ("task", i)
            if event_id not in used:
                events.append((max(when, task.time), event_id, task.plan))
        for i, task in enumerate(charges):
            event_id = ("charge", i)
            if event_id not in used:
                events.append((max(when, task.time), event_id, {}))
        for bed in data.dorm:
            op = data.operators.get(bed.name)
            event_id = ("bed", bed.name, bed.position)
            if op is None or event_id in used:
                continue
            if bed.time is None:
                if op.is_high():
                    uncertain = True
                continue
            members = data.groups.get(op.group, [op.name])
            plan = {}
            for member in members:
                worker = data.operators[member]
                if worker.room in data.plan:
                    plan.setdefault(
                        worker.room, ["Current"] * len(data.plan[worker.room])
                    )[worker.index] = member
            events.append((max(when, bed.time), event_id, plan))
        for time, event_id, plan in events:
            if time - now > timedelta(hours=12):
                uncertain = True
                continue
            projected = copy.deepcopy(data)
            timely = True
            for name in remaining:
                op = projected.operators[name]
                if time > deadlines.get(name, datetime.max):
                    timely = False
                    break
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
                        name in projected.operators
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
            queue.append(
                (
                    projected.project_arrangements([plan]),
                    time,
                    used | {event_id},
                    served | charged,
                )
            )
        if progressed and len(queue) > budget:
            uncertain = True
    return NativeProjection(
        None,
        not (queue or uncertain),
        "budget_or_unknown" if queue or uncertain else "blocked",
    )


def emergency_dorm_plan(data, state, tasks=()):
    """共享恢复层级选择空闲主班；宿管按跨宿舍一号位、二号位恢复。"""
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
    need = []
    for name, target in state["targets"].items():
        op = data.operators.get(name)
        if (
            op is not None
            and name not in reserved
            and (not has_resting_mood(op) or op.mood < target)
            and not data.rest_mood_complete(name)
            and not op.is_working()
            and resting_tier(data, name) != RestingTier.EXCLUDED
        ):
            need.append(name)
    need.sort(key=lambda name: resting_key(data, name))
    primary_need = set(need)
    residents = {bed.name for bed in data.dorm if bed.name}
    candidates = dorm_candidates(
        data, reserved | set(state["targets"]), current_residents=residents
    )
    ordinary = [
        name
        for name in [*candidates.recovering, *candidates.unknown]
        if name in data.operators
        and (mood := dorm_candidate_mood(data, name)) is not None
        and mood < 24
    ]
    critical = {
        name for name in ordinary if resting_tier(data, name) <= RestingTier.MAIN
    }
    need = sorted(primary_need | critical, key=lambda name: resting_key(data, name))
    plan = {}
    occupied = {
        op.name: (op.current_room, op.current_index) for op in data.operators.values()
    }
    beds = [bed for bed in data.dorm if bed.position not in slots]
    managers = {
        name
        for names in state["dorm_layout"].values()
        for name in names[:2]
        if name not in ("Free", "Current", "菲亚梅塔")
    }

    def place(name):
        if any(bed.name == name for bed in beds):
            return
        target_bed = next(
            (
                bed
                for bed in sorted(
                    beds,
                    key=lambda item: (
                        bool(item.name),
                        item.name in managers,
                        -item.position[1]
                        if item.name in managers
                        else -resting_tier(data, item.name),
                    ),
                )
                if bed.name not in reserved
                and (
                    not bed.name
                    or bed.name in state["targets"]
                    and has_resting_mood(data.operators.get(bed.name))
                    and data.operators[bed.name].mood >= state["targets"][bed.name]
                    or data._slot_takable(bed, requester=name)
                    or name in primary_need
                    and bed.name in managers
                    and bed.name in data.operators
                    and bed.name not in primary_need
                )
            ),
            None,
        )
        if target_bed is None:
            return
        room, index = target_bed.position
        plan.setdefault(room, ["Current"] * len(data.plan[room]))[index] = name
        beds.remove(target_bed)

    for name in need:
        place(name)
    for index in (0, 1):
        for room, configured in state["dorm_layout"].items():
            name = configured[index] if index < len(configured) else "Free"
            if name in ("Free", "Current", "菲亚梅塔") or name in reserved:
                continue
            op = data.operators.get(name)
            if op is None or op.is_working() or name in need:
                continue
            bed = next((bed for bed in beds if bed.position == (room, index)), None)
            if bed is None or bed.name in need or bed.name in reserved:
                continue
            if occupied.get(name) == (room, index):
                beds.remove(bed)
                continue
            previous = occupied.get(name)
            if previous and previous[0].startswith("dorm"):
                plan.setdefault(previous[0], ["Current"] * len(data.plan[previous[0]]))[
                    previous[1]
                ] = "Free"
            plan.setdefault(room, ["Current"] * len(data.plan[room]))[index] = name
            beds.remove(bed)
    for name in sorted(
        set(ordinary) - critical, key=lambda name: resting_key(data, name)
    ):
        place(name)
    return plan
