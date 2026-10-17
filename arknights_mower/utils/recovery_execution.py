"""实际换人前需要实读确认的恢复成员。"""

from datetime import timedelta

from arknights_mower.utils.group_recovery import (
    completed_mood_limit_release,
    group_recovery_deadline,
    observed_full_mood,
)
from arknights_mower.utils.operation_timing import estimate_dorm_minutes


def recovery_ready_for_arrangement(data, name, *, sampled_after, now):
    """实读已满或将在本房操作时间内回满，不改写实际心情。"""
    op = data.operators.get(name)
    if (
        op is None
        or op.time_stamp is None
        or getattr(op, "mood_is_prediction", False)
        or not 0 <= op.mood <= 24
        or sampled_after is not None
        and op.time_stamp < sampled_after
    ):
        return False
    if observed_full_mood(op) or completed_mood_limit_release(data, op):
        return True
    _, bed = data.get_dorm_by_name(name)
    return (
        op.is_resting()
        and bed is not None
        and bed.position == (op.current_room, op.current_index)
        and bed.time is not None
        and now
        < bed.time
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
    """已实读且有未来恢复期限时，返回正常等待所依据的观测。"""
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
        _, bed = data.get_dorm_by_name(name)
        if (
            bed is None
            or bed.position != (op.current_room, op.current_index)
            or bed.time is None
            or bed.time <= now
        ):
            return None
        observations[name] = op.time_stamp
    return observations
