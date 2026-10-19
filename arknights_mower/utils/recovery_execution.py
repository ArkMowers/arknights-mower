"""实际换人前的心情要求及独立恢复期限。"""

from datetime import timedelta

from arknights_mower.utils import config
from arknights_mower.utils.dorm_candidates import scheduling_mood_observation
from arknights_mower.utils.group_recovery import (
    completed_mood_limit_release,
    group_recovery_deadline,
    observed_recovery_deadline,
    recovery_mood_complete,
)
from arknights_mower.utils.operation_timing import estimate_dorm_minutes


def recovery_ready_for_arrangement(data, name, *, sampled_after, now):
    """有效心情已满或实读期限落在操作提前量内，不改写实际心情。"""
    op = data.operators.get(name)
    if recovery_mood_complete(data, op, now):
        return True
    if (
        op is None
        or op.time_stamp is None
        or getattr(op, "mood_is_prediction", False)
        or not 0 <= op.mood <= 24
        or sampled_after is not None
        and op.time_stamp < sampled_after
    ):
        return False
    observation = scheduling_mood_observation(data, name, now)
    if observation is not None and observation[1] > op.time_stamp:
        return False
    if completed_mood_limit_release(data, op):
        return True
    due = observed_recovery_deadline(data, name)
    return (
        op.is_resting()
        and due is not None
        and now
        < due
        <= now + timedelta(minutes=estimate_dorm_minutes(op.current_room, 1.5))
    )


def required_recovery_members(data, task, *, now=None):
    required = set()
    urgent = getattr(task, "exhaust_support", False) and not getattr(
        task, "ordinary_coordination", False
    )
    explicit = set(getattr(task, "backup_explicit_slots", ()))
    for room, row in task.plan.items():
        for index, name in enumerate(row):
            if (room, index) in explicit:
                continue
            op = data.operators.get(name)
            if op is None or room.startswith("dorm"):
                continue
            if not getattr(op, "rest_in_full", False) and not getattr(op, "group", ""):
                continue
            if (op.room, op.index) != (room, index) or op.is_working():
                continue
            if op.rest_in_full and not op.workaholic:
                required.add(name)
            if op.group:
                required.update(
                    member
                    for member in group_recovery_deadline(data, op.group, now=now)[0]
                    if not urgent or data.operators[member].rest_in_full
                )
    targets = (
        task.release_dorm_targets() if hasattr(task, "release_dorm_targets") else {}
    )
    for name in targets:
        op = data.operators.get(name)
        if op is None or (
            not getattr(op, "rest_in_full", False) and not getattr(op, "group", "")
        ):
            continue
        if (op.current_room, op.current_index) != targets[name] or (
            getattr(task, "strict_mood_limit", False)
            and (
                not data.has_rest_mood_limit(name)
                or getattr(task, "mood_limit", None) not in (None, op.upper_limit)
            )
        ):
            continue
        if getattr(task, "strict_mood_limit", False):
            # 个人上限离宿已预留操作时间，仍由清退入口核验床位与有效上限。
            continue
        group_required = (
            group_recovery_deadline(data, op.group, now=now)[0] if op.group else ()
        )
        if op.rest_in_full and not op.workaholic or name in group_required:
            required.add(name)
    return required


def pending_recovery_observations(data, names, *, now, sampled_after=None):
    """已有恢复期限或本轮等待上限时，返回等待所依据的实读。"""
    observations = {}
    for name in names:
        op = data.operators.get(name)
        if (
            op is None
            or op.time_stamp is None
            or sampled_after is not None
            and op.time_stamp < sampled_after
            or getattr(op, "mood_is_prediction", False)
            or not 0 <= op.mood < op.upper_limit
            or not op.is_resting()
        ):
            return None
        due = recovery_observation_deadline(data, name, now=now)
        if due is None or due <= now:
            return None
        observations[name] = op.time_stamp
    return observations


def recovery_observation_deadline(data, name, *, now):
    """下一次核验不晚于已确认的组内等待上限，不延长原任务。"""
    op = data.operators[name]
    due = observed_recovery_deadline(data, name)
    if (
        not op.rest_in_full
        and config.conf.group_mood_gap_max_extra_wait_hours > 0
        and name in getattr(data, "group_recovery_full_members", {}).get(op.group, [])
    ):
        _, group_due = group_recovery_deadline(data, op.group, now=now)
        if group_due is not None:
            due = min(due, group_due) if due is not None else group_due
    return due


def independent_recovery_plan(data, task, unfinished):
    """分离不共享干员或绑组的整房安排，已开始和副表整体安排保持原样。"""
    from arknights_mower.utils.scheduler_task import TaskTypes

    if task.type not in (
        TaskTypes.SHIFT_ON,
        TaskTypes.SELF_CORRECTION,
        TaskTypes.RE_ORDER,
    ):
        return {}
    if (
        task.meta_data
        or any(
            getattr(task, flag, False)
            for flag in (
                "derived_correction_started",
                "group_shift_expected",
                "backup_shift_active",
                "backup_explicit_slots",
                "backup_refresh_rules",
                "product_shift_locked",
                "exhaust_support",
                "ordinary_coordination",
                "preferred_replacement_restore",
                "dorm_recovery_restore",
                "emergency_staffing",
                "arrangement_retry_room",
            )
        )
        or hasattr(task, "backup_shift_intent")
        or hasattr(task, "backup_shift_conditions")
    ):
        return {}

    def resources(names):
        result = set()
        for name in names:
            op = data.operators.get(name)
            if op is None:
                continue
            result.add(("operator", name))
            groups = (
                [binding["group"] for binding in op.group_bindings]
                if op.multi_group
                else [op.group]
            )
            result.update(("group", group) for group in groups if group)
        return result

    involved = {}
    for room, row in task.plan.items():
        names = set()
        for index, name in enumerate(row):
            if name == "Current":
                continue
            names.add(name)
            occupant = data.get_current_operator(room, index)
            if occupant is not None:
                names.add(occupant.name)
            slots = data.plan.get(room, [])
            if index < len(slots):
                names.add(slots[index].agent)
        involved[room] = resources(names)
    blocked, related = set(), resources(unfinished)
    while True:
        connected = {
            room for room, names in involved.items() if names & related
        } - blocked
        if not connected:
            break
        blocked.update(connected)
        for room in connected:
            related.update(involved[room])
    if not blocked:
        return {}
    return {room: list(row) for room, row in task.plan.items() if room not in blocked}
