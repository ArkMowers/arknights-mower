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


def completed_mood_limit_release(data, operator):
    """已确认的个人上限离宿完成本轮恢复，实际心情仍保留读数。"""
    return (
        not operator.current_room
        and not getattr(operator, "mood_is_prediction", False)
        and getattr(operator, "rest_mood_release_limit", None) == operator.upper_limit
        and data.rest_mood_complete(operator.name)
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
    """额外等待仅限制组内时间差等待，明确回满要求始终生效。"""
    now = now or datetime.now()
    workers = group_recovery_workers(data, group)
    gap_workers = [op for op in workers if not op.multi_group]
    latches = getattr(data, "group_recovery_full_members", None)
    if latches is None:
        latches = data.group_recovery_full_members = {}
    anchors = getattr(data, "group_recovery_return_time", None)
    if anchors is None:
        anchors = data.group_recovery_return_time = {}

    def completed_at(op):
        if observed_full_mood(op) or completed_mood_limit_release(data, op):
            return now
        _, bed = data.get_dorm_by_name(op.name)
        return bed.time if bed is not None else None

    if group in config.conf.group_mood_gap_exclusions:
        latches.pop(group, None)
        anchors.pop(group, None)
    elif group in latches:
        latches[group] = [op.name for op in gap_workers]
    elif config.conf.group_rest_in_full_on_mood_gap:
        times = [at for op in gap_workers if (at := completed_at(op)) is not None]
        limit = timedelta(minutes=config.conf.group_mood_gap_threshold_minutes)
        if len(times) > 1 and max(times) - min(times) > limit:
            latches[group] = [op.name for op in gap_workers]
    gap_names = latches.get(group, [])
    if gap_names and group not in anchors:
        residents = [op for op in gap_workers if op.is_resting()]
        high = [op for op in residents if op.resting_priority == "high"]
        times = [
            at
            for op in high or residents or gap_workers
            if (at := completed_at(op)) is not None
        ]
        if times:
            anchors[group] = max(now, min(times) - timedelta(minutes=8))
    max_wait = config.conf.group_mood_gap_max_extra_wait_hours
    cap = (
        anchors[group] + timedelta(hours=max_wait)
        if gap_names and max_wait > 0 and group in anchors
        else None
    )
    explicit = [op.name for op in workers if op.rest_in_full]
    required = list(
        dict.fromkeys(explicit + (gap_names if cap is None or now < cap else []))
    )
    explicit_times = [completed_at(data.operators[name]) for name in explicit]
    if any(at is None for at in explicit_times):
        return required, None
    deadlines = list(explicit_times)
    if gap_names:
        times = [completed_at(data.operators[name]) for name in gap_names]
        if any(at is None for at in times):
            if cap is None:
                return required, None
            deadlines.append(cap)
        else:
            latest = max(times)
            deadlines.append(min(latest, cap) if cap is not None else latest)
    return required, max(now, *deadlines) if deadlines else None
