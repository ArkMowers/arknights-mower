"""工作主班的回满要求与本轮延迟回班期限。"""

from datetime import datetime, timedelta

from arknights_mower.utils import config


def observed_full_mood(operator):
    """只有实际采样能确认恢复完成，倒计时推算不构成实读。"""
    return (
        operator is not None
        and operator.time_stamp is not None
        and not getattr(operator, "mood_is_prediction", False)
        and 0 <= operator.mood <= 24
        and operator.mood >= operator.upper_limit
    )


def group_recovery_workers(data, group):
    """仅工作主班参与组内恢复，候补、宿管和零心情工作者不增加等待。"""
    return [
        op
        for name in data.shift_group_members(group)
        for op in [data.operators[name]]
        if op.is_high()
        and not op.room.startswith("dorm")
        and not op.independent_rest
        and not op.workaholic
        and not data._can_standby(op)
        and (op.is_resting() or not op.current_room)
    ]


def group_recovery_deadline(data, group, *, now=None):
    """合并明确回满与已触发的组内等待；未知恢复期限不能允许提前回班。"""
    now = now or datetime.now()
    workers = group_recovery_workers(data, group)
    gap_workers = [op for op in workers if not op.multi_group]
    latches = getattr(data, "group_recovery_full_members", None)
    if latches is None:
        latches = data.group_recovery_full_members = {}

    def completed_at(op):
        if observed_full_mood(op):
            return now
        _, bed = data.get_dorm_by_name(op.name)
        return bed.time if bed is not None else None

    if group in latches:
        latches[group] = [op.name for op in gap_workers]
    elif config.conf.group_rest_in_full_on_mood_gap:
        times = [at for op in gap_workers if (at := completed_at(op)) is not None]
        limit = timedelta(minutes=config.conf.group_mood_gap_threshold_minutes)
        if len(times) > 1 and max(times) - min(times) > limit:
            latches[group] = [op.name for op in gap_workers]
    required = list(
        dict.fromkeys(
            [op.name for op in workers if op.rest_in_full] + latches.get(group, [])
        )
    )
    times = [completed_at(data.operators[name]) for name in required]
    deadline = (
        max(now, *times) if times and all(at is not None for at in times) else None
    )
    return required, deadline
