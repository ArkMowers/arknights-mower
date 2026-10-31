"""共享替班召回判断与初始化驻员准入。"""

from datetime import timedelta

from arknights_mower.utils.dorm_candidates import (
    dorm_candidate_mood,
    scheduling_mood_observation,
)
from arknights_mower.utils.group_recovery import (
    completed_mood_limit_release,
    observed_recovery_deadline,
    recovery_mood_complete,
)
from arknights_mower.utils.operation_timing import estimate_dorm_minutes


def recovery_ready_for_arrangement(data, name, *, sampled_after, now):
    """有效心情已满或实读期限落在操作提前量内，不改写实际心情。"""
    op = data.operators.get(name)
    if recovery_mood_complete(data, op, now):
        return True
    if getattr(data, "mood_calculation_enabled", False):
        due = data.calculated_mood_deadline(name, op.upper_limit, now) if op else None
        return bool(
            op
            and op.is_resting()
            and due is not None
            and now
            < due
            <= now + timedelta(minutes=estimate_dorm_minutes(op.current_room, 1.5))
        )
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


def initial_idle_staffing_members(data, task, *, now=None):
    """查询仍可首次上岗的初始化主班，续行只沿用已保存的首次准入。"""
    if not getattr(task, "initial_staffing", False):
        return set()
    started = getattr(task, "derived_correction_started", False)
    expected = getattr(task, "group_shift_expected", {})
    admitted = getattr(task, "initial_staffing_idle_members", ())
    returns = getattr(task, "initial_staffing_returns", ())
    return {
        name
        for room, row in task.plan.items()
        if not room.startswith("dorm")
        for index, name in enumerate(row)
        if (op := data.operators.get(name)) is not None
        and (op.room, op.index) == (room, index)
        and not op.rest_in_full
        and (not started and not expected or name in admitted)
        and name not in returns
        and not op.current_room
        and not data.group_is_resting(op.group)
        and (mood := dorm_candidate_mood(data, name, now)) is not None
        and mood > op.lower_limit
    }
