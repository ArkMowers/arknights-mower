"""有界的普通轮休时间比较；预测建议不取得真实资源。"""

import copy
import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum
from time import perf_counter

from arknights_mower.utils.log import logger

POLICY_VERSION = 1
MAX_CANDIDATES = 16
MAX_EVENTS = 64


def _plain(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(item) for item in value), key=str)
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump())
    if hasattr(value, "__dict__"):
        return {
            key: _plain(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return value


def input_signature(solver, external=None):
    """时间推进和模型查询不改变输入版本；观测和真实任务变化会失效。"""
    data = solver.op_data
    model = data.mood_model
    conf = data.runtime_conf
    if conf is None:
        from arknights_mower.utils import config

        conf = config.conf
    facts = [
        POLICY_VERSION,
        external,
        model.rules_hash,
        model.observed,
        model.barriers,
        model.stages,
        model.rooms,
        model.single_targets,
        model.versions,
        [
            (
                n,
                o.mood,
                o.time_stamp,
                o.current_room,
                o.current_index,
                o.lower_limit,
                o.upper_limit,
                o.group,
                o.replacement,
                o.rest_in_full,
                o.workaholic,
                o.multi_group,
                o.independent_rest,
            )
            for n, o in data.operators.items()
        ],
        vars(data.config),
        data.plan,
        data.products,
        data.backup_plans,
        data.plan_condition,
        data.group_shift_state,
        data.group_recovery_full_members,
        data.group_recovery_return_time,
        data.exhaust_agent,
        data.exhaust_group,
        getattr(solver, "waiting_group_shifts", []),
        [(b.position, b.name, b.time) for b in data.all_dorms()],
        conf.model_dump() if hasattr(conf, "model_dump") else vars(conf),
        [
            (
                t.type.value,
                t.time,
                t.plan,
                t.meta_data,
                getattr(t, "run_order_restore_pending", False),
                getattr(t, "replacement_check", None),
                t is getattr(solver, "task", None),
                getattr(t, "execution_failure", None),
                getattr(t, "execution_retained", False),
            )
            for t in solver.tasks
            if not getattr(t, "mood_control_event", None)
            and not getattr(t, "mood_control_evidence", None)
        ],
    ]
    return hashlib.sha256(
        json.dumps(_plain(facts), default=str, sort_keys=True).encode()
    ).hexdigest()


def build_snapshot(solver, now):
    from arknights_mower.utils.resting_priority import RestingTier, resting_tier

    data = solver.op_data
    protected = solver._protected_facility_names()
    groups = []
    seen = set()
    for op in data.operators.values():
        if (
            not op.is_high()
            or not op.is_working()
            or (op.current_room, op.current_index) != (op.room, op.index)
            or op.room.startswith("dorm")
            or op.room in ("factory", "train")
            or op.name in protected
            or op.workaholic
            or op.multi_group
            and not op.independent_rest
            or op.group
            and not data.is_group_shift_anchor(op)
            or data.is_standby(op.name)
            or resting_tier(data, op.name, now) == RestingTier.EXCLUDED
        ):
            continue
        identity = op.group or op.name
        if identity in seen:
            continue
        seen.add(identity)
        members = list(data.groups[op.group]) if op.group else [op.name]
        workers = [
            data.operators[n]
            for n in members
            if not data.operators[n].room.startswith("dorm")
            and not data.operators[n].workaholic
            and (
                not data.operators[n].multi_group or data.operators[n].independent_rest
            )
        ]
        floors = [
            data.calculated_mood_deadline(w.name, w.lower_limit, now) for w in workers
        ]
        softs = [
            data.calculated_mood_deadline(w.name, data.resting_mood_threshold(w), now)
            for w in workers
        ]
        if not workers:
            continue
        if any(t is None for t in [*floors, *softs]):
            return None
        hard = any(
            w.name in data.exhaust_agent or w.group in data.exhaust_group
            for w in workers
        )
        groups.append(
            dict(
                id=identity,
                members=members,
                lowerAt=min(floors).timestamp(),
                softAt=min(floors if hard else softs).timestamp(),
                exhaust=hard,
            )
        )
    if not groups:
        return None
    # 同一观察终点覆盖后继下限及完整恢复；超出范围的候选不能取得提前资格。
    horizon = min(
        now.timestamp() + 240 * 3600, max(g["lowerAt"] for g in groups) + 24 * 3600
    )
    return dict(now=now.timestamp(), horizon=horizon, groups=groups)


def dynamic_rollout(solver, snapshot, early=None, start=None, *, max_events=MAX_EVENTS):
    from arknights_mower.utils import config
    from arknights_mower.utils.operation_timing import (
        estimate_dorm_minutes,
        estimate_work_minutes,
    )
    from arknights_mower.utils.scheduler_task import (
        SchedulerTask,
        TaskTypes,
        estimate_task_duration,
        plan_metadata,
    )

    now = datetime.fromtimestamp(snapshot["now"])
    end = datetime.fromtimestamp(snapshot["horizon"])
    trial = copy.copy(solver)
    trial.op_data = copy.deepcopy(
        solver.op_data, {id(solver.op_data.eval_model): solver.op_data.eval_model}
    )
    trial.op_data.runtime_conf = copy.deepcopy(
        solver.op_data.runtime_conf or config.conf
    )
    trial.op_data._projection_now = now
    trial.op_data._apply_projected_arrangements([], now=now)
    data = trial.op_data
    data._mood_frozen_inputs = True
    data._projection_inventory = snapshot.get("inventory", {})
    data._projection_maintenance = snapshot.get("maintenance")
    trial.tasks = copy.deepcopy(
        [
            t
            for t in solver.tasks
            if not getattr(t, "mood_control_event", None)
            and not getattr(t, "mood_control_evidence", None)
        ]
    )
    trial.waiting_group_shifts = copy.deepcopy(
        getattr(solver, "waiting_group_shifts", [])
    )
    trial.task = None
    trial._coordination_projection = True
    trial._mood_control_projection = True
    trial._mood_control_allowed = set(
        next((g["members"] for g in snapshot["groups"] if g["id"] == early), [])
    )
    groups = snapshot["groups"]
    roles = {
        n: (data.operators[n].room, data.operators[n].index, data.operators[n].group)
        for group in groups
        for n in group["members"]
    }
    memberships = {
        data.operators[n].group: tuple(data.groups[data.operators[n].group])
        for n in roles
        if data.operators[n].group
    }
    safe_types = {
        TaskTypes.CLUE,
        TaskTypes.CLUE_PARTY,
        TaskTypes.MAA_MALL,
        TaskTypes.RECRUIT,
        TaskTypes.SKLAND,
        TaskTypes.REFRESH_TIME,
        TaskTypes.DEPOT,
        TaskTypes.FURNITURE,
    }
    service_release = None

    def unknown_effect(task):
        return task.type not in (TaskTypes.SHIFT_ON, TaskTypes.RELEASE_DORM) and not (
            task.type in safe_types | {TaskTypes.NOT_SPECIFIC, TaskTypes.EXHAUST_OFF}
            and not task.plan
        )

    ordered = sorted(range(len(groups)), key=lambda i: (groups[i]["lowerAt"], i))
    requests = {
        i: datetime.fromtimestamp(
            start if groups[i]["id"] == early else groups[i]["softAt"]
        )
        for i in ordered
    }
    departing, returned, returns, plans = {}, set(), [], {}
    handoffs = set()
    events, score, count = [], [0.0, 0.0, 0, 0.0], 0
    clock = now
    slots = {
        (op.room, op.index)
        for op in data.operators.values()
        if op.is_high() and not op.room.startswith("dorm") and not op.workaholic
    }

    def take_node():
        nonlocal count, exhausted
        if exhausted:
            return False
        count += 1
        if count > max_events:
            exhausted = True
            return False
        return True

    def advance(at):
        nonlocal clock
        at = min(at, end)
        while clock < at:
            if not take_node():
                return
            _, rates, boundary_hours = data.mood_model._deadline_node(data.mood_model)
            for name, op in data.operators.items():
                rate = rates.get(name) or 0
                if rate:
                    for boundary in (op.lower_limit, op.upper_limit):
                        distance = (
                            data.mood_model.moods.get(name, 0) - boundary
                        ) / rate
                        if distance > 1e-9:
                            boundary_hours = min(boundary_hours, distance)
            until = (
                min(at, clock + timedelta(hours=boundary_hours))
                if boundary_hours < 240
                else at
            )
            if until <= clock:
                until = at
            for i, group in enumerate(groups):
                if i in handoffs:
                    continue
                floor_times = [
                    data.calculated_mood_deadline(
                        n, data.operators[n].lower_limit, clock
                    )
                    for n in group["members"]
                    if not data.operators[n].room.startswith("dorm")
                    and not data.operators[n].workaholic
                    and (
                        not data.operators[n].multi_group
                        or data.operators[n].independent_rest
                    )
                ]
                known = [due for due in floor_times if due is not None]
                if known and min(known) < until:
                    score[0] += (until - max(clock, min(known))).total_seconds()
            for room, index in slots:
                occupant = data.get_current_operator(room, index)
                if occupant is None:
                    score[1] += (until - clock).total_seconds()
                elif not occupant.workaholic:
                    zero = data.calculated_mood_deadline(occupant.name, 0, clock)
                    if zero is not None and zero < until:
                        score[1] += (until - max(clock, zero)).total_seconds()
            data.mood_model.advance(until)
            data._projection_now = until
            for op in data.operators.values():
                op._projection_now = until
            clock = until

    def execute(task, group, phase):
        nonlocal service_release
        if exhausted:
            return False
        begin = clock
        trial.task = task
        # 副表函数只在独占投影上收敛；它不执行设备操作。
        from arknights_mower.solvers.base_schedule import (
            GroupShiftBlocked,
            ProductSwitchDeferred,
            _backup_timing_runtime,
            _BackupCalculationTiming,
        )

        previous_timing = getattr(_backup_timing_runtime, "current", None)
        if previous_timing is None:
            _backup_timing_runtime.current = _BackupCalculationTiming()
        try:
            trial._prepare_shift_backup(task)
        except (ProductSwitchDeferred, GroupShiftBlocked, ValueError):
            return False
        finally:
            if previous_timing is None:
                _backup_timing_runtime.current = None
        conditions = getattr(task, "backup_shift_conditions", None)
        if conditions is not None:
            if list(conditions) != data.plan_condition:
                if not take_node():
                    return False
            if data.swap_plan(
                conditions,
                refresh=True,
                backup_group=getattr(task, "backup_group", None),
            ):
                return False
            if any(
                name not in data.operators
                or (
                    data.operators[name].room,
                    data.operators[name].index,
                    data.operators[name].group,
                )
                != role
                for name, role in roles.items()
            ):
                return False
            if any(
                tuple(data.groups.get(group, ())) != members
                for group, members in memberships.items()
            ):
                return False
        duration = estimate_task_duration(task, op_data=data)
        if begin + duration > end:
            return False
        if any(
            unknown_effect(pending) and begin + duration > pending.time
            for pending in trial.tasks
        ):
            return False
        overlaps = [
            pending.time + estimate_task_duration(pending, op_data=data)
            for pending in trial.tasks
            if pending.type in safe_types
            and not pending.plan
            and not pending.retains_execution
            and pending.time < begin + duration
            and begin < pending.time + estimate_task_duration(pending, op_data=data)
        ]
        if overlaps:
            service_release = max(overlaps)
            return False
        resources = [
            "operator:" + n
            for row in task.plan.values()
            for n in row
            if n in data.operators
        ]
        events.append(
            dict(
                time=begin.timestamp(),
                type=phase + "-start",
                group=group,
                resources=resources,
            )
        )
        # 各房间操作完成前仍按旧阵容推进。总预算与既有安排耗时一致。
        duration = estimate_task_duration(task, op_data=data)
        weights = {
            r: (
                estimate_dorm_minutes(r, 0.75)
                if r.startswith("dorm")
                else estimate_work_minutes(r)
            )
            for r in task.plan
        }
        total = sum(weights.values()) or 1
        for room, row in task.plan.items():
            if not take_node():
                return False
            advance(clock + duration * (weights[room] / total))
            if exhausted:
                return False
            data._apply_projected_arrangements([{room: row}], now=clock)
        data.commit_group_shifts(data.arrangement_group_transitions(task.plan))
        events.append(
            dict(
                time=clock.timestamp(),
                type=phase + "-complete",
                group=group,
                resources=resources,
            )
        )
        score[2] += 1
        trial.task = None
        return True

    exhausted = False
    unresolved = False

    def changes_positions(task):
        return any(
            name != "Current"
            and (
                data.get_current_operator(room, index).name
                if data.get_current_operator(room, index) is not None
                else "Free"
            )
            != name
            for room, row in task.plan.items()
            for index, name in enumerate(row)
        )

    while clock < end:
        service_release = None
        # 阵容、技能和副表变化后复用同一时刻的恢复与期限求解。
        if returns:
            metadata = plan_metadata(data, copy.deepcopy(trial.tasks), now=clock)
            for identity in dict.fromkeys(t._mood_rollout_group for t in returns):
                members = next(g["members"] for g in groups if g["id"] == identity)
                refreshed = [
                    t
                    for t in metadata
                    if t.type == TaskTypes.SHIFT_ON
                    and any(n in members for row in t.plan.values() for n in row)
                    and changes_positions(t)
                ]
                if refreshed:
                    returns[:] = [
                        t for t in returns if t._mood_rollout_group != identity
                    ]
                    for task in refreshed:
                        task._mood_rollout_group = identity
                        returns.append(task)
        for i in ordered:
            if i in departing or groups[i]["id"] == early:
                continue
            members = [
                data.operators[n]
                for n in groups[i]["members"]
                if not data.operators[n].room.startswith("dorm")
                and not data.operators[n].workaholic
            ]

            def target(op):
                return (
                    op.lower_limit
                    if groups[i]["exhaust"]
                    else data.resting_mood_threshold(op)
                )

            deadlines = [
                data.calculated_mood_deadline(op.name, target(op), clock)
                for op in members
            ]
            if deadlines and all(d is not None for d in deadlines):
                requests[i] = min(deadlines)
        due_returns = [t for t in returns if t.time <= clock]
        if due_returns:
            task = min(due_returns, key=lambda t: t.time)
            identity = task._mood_rollout_group
            if not execute(task, identity, "return"):
                exhausted = exhausted or count >= max_events
                if service_release is not None and not exhausted:
                    advance(service_release)
                    continue
                unresolved = True
                break
            returns.remove(task)
            members = next(g["members"] for g in groups if g["id"] == identity)
            if not any(t._mood_rollout_group == identity for t in returns) and all(
                (data.operators[n].current_room, data.operators[n].current_index)
                == (data.operators[n].room, data.operators[n].index)
                for n in members
            ):
                returned.add(identity)
            continue
        acted = False
        eligible = sorted(
            (i for i in ordered if i not in departing and requests[i] <= clock),
            key=lambda i: (
                groups[i]["lowerAt"] > clock.timestamp(),
                groups[i]["lowerAt"],
                i,
            ),
        )
        # 既有任务保留资源与执行窗口，不把跑单、加工等预测为已完成。
        critical = [t for t in trial.tasks if unknown_effect(t) and t.time <= clock]
        if critical:
            unresolved = True
            break
        for i in [] if critical else eligible:
            group = groups[i]
            plan, covers = {}, []
            beds = [(b, b.name, b.time) for b in data.all_dorms()]
            trial.get_resting_plan(
                list(group["members"]), covers, plan, data.active_high_resting_count()
            )
            for bed, name, time in beds:
                if bed.name in group["members"] and bed.name != name:
                    room, index = bed.position
                    plan.setdefault(room, ["Current"] * len(data.plan[room]))[index] = (
                        bed.name
                    )
                bed.name, bed.time = name, time
            if not plan:
                continue
            task = SchedulerTask(
                time=clock, task_type=TaskTypes.SHIFT_OFF, task_plan=plan
            )
            task.ordinary_coordination = not group["exhaust"]
            task.coordination_request_names = group["members"]
            if group["id"] == early:
                task.mood_control_evidence = {"group": early}
            begin = clock
            handoffs.add(i)
            if not execute(task, group["id"], "departure"):
                handoffs.discard(i)
                exhausted = exhausted or count >= max_events
                break
            departing[i] = begin
            plans.setdefault(group["id"], copy.deepcopy(task.plan))
            score[3] += max(0, group["softAt"] - begin.timestamp())
            derived = plan_metadata(data, copy.deepcopy(trial.tasks), now=clock)
            candidates = [
                t
                for t in derived
                if t.type == TaskTypes.SHIFT_ON
                and any(n in group["members"] for row in t.plan.values() for n in row)
                and changes_positions(t)
            ]
            if not candidates:
                break
            for returned_task in candidates:
                returned_task._mood_rollout_group = group["id"]
                returns.append(returned_task)
            acted = True
            break
        if exhausted:
            break
        if acted:
            continue
        future = [t.time for t in returns if t.time > clock]
        future.extend(
            at for i, at in requests.items() if i not in departing and at > clock
        )
        # 实际已有回班和离宿是合法依赖；到期后才在投影释放。
        future.extend(
            t.time
            for t in trial.tasks
            if t.type in (TaskTypes.SHIFT_ON, TaskTypes.RELEASE_DORM) and t.time > clock
        )
        future.extend(
            t.time for t in trial.tasks if unknown_effect(t) and t.time > clock
        )
        if service_release is not None and service_release > clock:
            future.append(service_release)
        if not future or min(future) >= end:
            break
        advance(min(future))
        for pending in list(trial.tasks):
            if (
                pending.type in (TaskTypes.SHIFT_ON, TaskTypes.RELEASE_DORM)
                and pending.time <= clock
            ):
                if not execute(pending, "existing", "return"):
                    exhausted = exhausted or count >= max_events
                    unresolved = True
                    break
                trial.tasks.remove(pending)
        if unresolved:
            break
    unresolved |= any(unknown_effect(t) and t.time <= end for t in trial.tasks)
    if not unresolved:
        advance(end)
    return dict(
        score=score,
        events=events,
        plans=plans,
        dependencies={g["id"]: g["members"] for g in groups},
        complete=not unresolved
        and not exhausted
        and clock == end
        and len(returned) == len(groups),
        exhausted=exhausted,
        nodeCount=count,
    )


def _plan(solver, now=None):
    now = now or datetime.now()
    from arknights_mower.utils.calculated_mood import sync_model

    sync_model(solver.op_data, now)
    external = {}
    if solver.op_data.backup_plans:
        from arknights_mower.solvers.record import get_inventory_counts
        from arknights_mower.utils.news_checker import NewsChecker

        external["inventory"] = get_inventory_counts(
            [
                "赤金",
                "源石碎片",
                "固源岩",
                "装置",
                "龙门币",
                "基础作战记录",
                "初级作战记录",
                "中级作战记录",
                "高级作战记录",
            ]
        )
        external["maintenance"] = copy.deepcopy(NewsChecker.get_maintenance())
    signature = input_signature(solver, external)
    started = perf_counter()
    blocked = any(
        t.retains_execution
        or getattr(t, "mood_physical_started", False)
        or getattr(t, "backup_shift_active", False)
        or getattr(t, "group_shift_expected", {})
        for t in solver.tasks
        if not (
            t is getattr(solver, "task", None)
            and getattr(t, "mood_control_evidence", None)
            and not getattr(t, "mood_physical_started", False)
            and not t.retains_execution
        )
    )
    signature += ":started" if blocked else ":ready"
    cached = getattr(solver, "_mood_control_cache", None)
    if cached is not None and cached["signature"] == signature:
        cached["reused"] = True
        return cached
    snapshot = None if blocked else build_snapshot(solver, now)
    if snapshot is not None:
        snapshot.update(external)
    if snapshot is None:
        result = dict(
            decision=None,
            status="insufficient",
            events=[],
            nextWake=None,
            candidates=0,
            enumeratedCandidates=0,
            processedNodes=0,
            eventCount=0,
            budgetExhausted=False,
            plans={},
            dependencies={},
        )
    else:
        groups = snapshot["groups"]
        boundaries = sorted(
            {
                snapshot["now"],
                *(g["softAt"] for g in groups),
                *(g["lowerAt"] for g in groups),
                *(t.time.timestamp() for t in solver.tasks if t.time >= now),
            }
        )
        candidates = [(None, snapshot["now"])]
        truncated = False
        for group in sorted(groups, key=lambda g: g["lowerAt"]):
            if group["exhaust"]:
                continue
            for at in boundaries:
                if at < group["softAt"]:
                    if len(candidates) < MAX_CANDIDATES:
                        candidates.append((group["id"], at))
                    else:
                        truncated = True
        baseline = dynamic_rollout(solver, snapshot, max_events=MAX_EVENTS)
        selected, decision = baseline, None
        budget, events = baseline["exhausted"], len(baseline["events"])
        max_nodes = baseline["nodeCount"]
        evaluated, processed = 1, min(MAX_EVENTS, max_nodes)
        for identity, at in [] if budget or truncated else candidates[1:]:
            candidate = dynamic_rollout(
                solver, snapshot, identity, at, max_events=MAX_EVENTS
            )
            events += len(candidate["events"])
            evaluated += 1
            processed += min(MAX_EVENTS, candidate["nodeCount"])
            max_nodes = max(max_nodes, candidate["nodeCount"])
            budget |= candidate["exhausted"]
            if budget:
                break
            if (
                candidate["complete"]
                and tuple(candidate["score"][:2]) < tuple(baseline["score"][:2])
                and tuple(candidate["score"]) < tuple(selected["score"])
            ):
                selected, decision = candidate, identity
        if budget or truncated:
            selected, decision = baseline, None
        result = dict(
            selected,
            decision=decision,
            status="budget-exhausted"
            if budget or truncated
            else "feasible"
            if selected["complete"]
            else "insufficient",
            nextWake=next(
                (e["time"] for e in selected["events"] if e["time"] > snapshot["now"]),
                None,
            ),
            candidates=evaluated,
            enumeratedCandidates=len(candidates),
            processedNodes=processed,
            eventCount=events,
            budgetExhausted=budget or truncated,
            maxCandidateNodes=max_nodes,
        )
    result.update(
        signature=signature,
        snapshot=snapshot,
        reused=False,
        elapsed=perf_counter() - started,
    )
    solver._mood_control_cache = result
    return result


def plan(solver, now=None):
    """记录整个规划批次；模型时间只作为总时间的组成部分。"""
    from arknights_mower.utils.calculated_mood import _runtime

    started = perf_counter()
    existing = getattr(_runtime, "timing", None)
    timing = existing or {"elapsed": 0.0, "calls": 0, "measuring": False}
    before = timing["elapsed"]
    if existing is None:
        _runtime.timing = timing
    try:
        result = _plan(solver, now)
    finally:
        if existing is None:
            _runtime.timing = None
    result["modelSeconds"] = timing["elapsed"] - before
    result["elapsed"] = perf_counter() - started
    logger.info(
        "心情调控规划：总计 %.3f 秒，其中模型 %.3f 秒，已评估候选 %d/%d，已处理节点 %d，轨迹事件 %d，复用 %s，预算耗尽 %s，%s",
        result["elapsed"],
        result["modelSeconds"],
        result["candidates"],
        result["enumeratedCandidates"],
        result["processedNodes"],
        result["eventCount"],
        result["reused"],
        result["budgetExhausted"],
        result["status"],
    )
    return result


def reconcile(solver, now=None):
    """唯一内存唤醒只预约时间，实际安排仍由普通任务取得预约。"""
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    now = now or datetime.now()
    solver.tasks[:] = [
        t for t in solver.tasks if not getattr(t, "mood_control_event", None)
    ]
    if not solver.op_data.mood_calculation_enabled or solver._emergency_frozen():
        solver._mood_control_cache = None
        return None
    if any(
        t.retains_execution
        or getattr(t, "mood_physical_started", False)
        or getattr(t, "backup_shift_active", False)
        or getattr(t, "group_shift_expected", {})
        for t in solver.tasks
    ):
        return None
    if any(getattr(t, "mood_control_evidence", None) for t in solver.tasks):
        return None
    if any(t.type == TaskTypes.SHIFT_OFF and t.plan for t in solver.tasks):
        return None
    result = plan(solver, now)
    decision = result["decision"]
    consumed = {
        token
        for token in getattr(solver, "_mood_control_consumed_events", set())
        if token[0] == result["signature"]
    }
    previous = getattr(solver, "_mood_control_consumed", None)
    if previous is not None:
        consumed.add(previous)
    solver._mood_control_consumed_events = consumed
    event = next(
        (
            e
            for e in result["events"]
            if e["type"] == "departure-start"
            and (result["signature"], e["group"], e["time"]) not in consumed
        ),
        None,
    )
    if event is None:
        return result
    token = (result["signature"], event["group"], event["time"])
    when = datetime.fromtimestamp(event["time"])
    if when > now:
        wake = SchedulerTask(time=when, task_type=TaskTypes.NOT_SPECIFIC, task_plan={})
        wake.mood_control_event = dict(
            signature=result["signature"], group=event["group"], at=event["time"]
        )
        solver.tasks.append(wake)
    elif decision and event["group"] == decision:
        task = SchedulerTask(
            time=when,
            task_type=TaskTypes.SHIFT_OFF,
            task_plan=copy.deepcopy(result["plans"][decision]),
        )
        task.ordinary_coordination = True
        task.coordination_request_names = list(result["dependencies"][decision])
        task.mood_control_evidence = dict(
            signature=result["signature"],
            group=decision,
            at=event["time"],
            reason="连续工作预测改善",
        )
        solver.tasks.append(task)
        solver._mood_control_consumed = token
        consumed.add(token)
    return result


def admits(solver, names, task=None):
    """实读改变后重新证明提前理由；标记本身不豁免硬限制。"""
    task = task or getattr(solver, "task", None)
    evidence = getattr(task, "mood_control_evidence", None)
    if (
        not evidence
        or not solver.op_data.mood_calculation_enabled
        or solver._emergency_frozen()
    ):
        return False
    data = solver.op_data
    if any(
        n in data.exhaust_agent or data.operators[n].group in data.exhaust_group
        for n in names
    ):
        return False
    if getattr(solver, "_mood_control_projection", False):
        return set(names) <= set(getattr(solver, "_mood_control_allowed", ()))
    result = plan(solver)
    decision = result["decision"]
    due = next(
        (
            event["time"]
            for event in result["events"]
            if event["type"] == "departure-start" and event["group"] == decision
        ),
        None,
    )
    return bool(
        decision
        and due is not None
        and due <= datetime.now().timestamp()
        and set(names) <= set(result["dependencies"].get(decision, ()))
    )


def consume_event(solver, task, now=None):
    """预测时刻到达后直接运行内存轮休规划，不进入默认心情巡检。"""
    now = now or datetime.now()
    event = task.mood_control_event
    solver.tasks[:] = [queued for queued in solver.tasks if queued is not task]
    if solver._emergency_frozen():
        reconcile(solver, now)
        return
    reconcile(solver, now)
    token = (event["signature"], event["group"], event["at"])
    if token not in getattr(solver, "_mood_control_consumed_events", set()):
        solver._mood_control_consumed = token
        consumed = getattr(solver, "_mood_control_consumed_events", set())
        consumed.add(token)
        solver._mood_control_consumed_events = consumed
        reconcile(solver, now)
    from arknights_mower.utils.scheduler_task import TaskTypes

    if not any(t.type == TaskTypes.SHIFT_OFF for t in solver.tasks):
        solver._plan_primary_recovery(scan_moods=False)
