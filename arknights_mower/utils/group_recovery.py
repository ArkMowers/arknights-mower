"""工作主班的回满要求与本轮延迟回班期限。"""

from datetime import datetime, timedelta

from arknights_mower.utils import config


def recovery_mood_complete(data, operator, now=None):
    """按所选心情来源判断回满，不改写恢复记录。"""
    from arknights_mower.utils.dorm_candidates import dorm_candidate_mood

    if operator is None:
        return False
    mood = (
        data.calculated_mood(operator.name, now)
        if getattr(data, "mood_calculation_enabled", False)
        else dorm_candidate_mood(data, operator.name, now)
    )
    return mood is not None and mood >= operator.upper_limit


def observed_recovery_deadline(data, name, now=None):
    """按模型或宿舍实读倒计时规划恢复，不将固定岗位开放为 Free。"""
    op = data.operators[name]
    if getattr(data, "mood_calculation_enabled", False):
        return data.calculated_mood_deadline(name, op.upper_limit, now)
    _, bed = data.get_dorm_by_name(name)
    if bed is not None:
        return bed.time
    observation = getattr(op, "dorm_recovery_observation", None)
    if (
        observation is not None
        and observation[:2] == ((op.current_room, op.current_index), op.time_stamp)
        and not getattr(op, "mood_is_prediction", False)
    ):
        due = observation[2]
        if op.mood < 24:
            due = op.time_stamp + (due - op.time_stamp) * (
                (op.upper_limit - op.mood) / (24 - op.mood)
            )
        return due
    return None


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
    now = now or getattr(data, "_projection_now", None) or datetime.now()
    conf = getattr(data, "runtime_conf", None) or config.conf
    workers = group_recovery_workers(data, group)
    gap_workers = [op for op in workers if not op.multi_group]
    latches = getattr(data, "group_recovery_full_members", None)
    if latches is None:
        latches = data.group_recovery_full_members = {}
    anchors = getattr(data, "group_recovery_return_time", None)
    if anchors is None:
        anchors = data.group_recovery_return_time = {}

    def completed_at(op):
        if recovery_mood_complete(data, op, now) or completed_mood_limit_release(
            data, op
        ):
            return now
        return observed_recovery_deadline(data, op.name, now)

    if group in conf.group_mood_gap_exclusions:
        latches.pop(group, None)
        anchors.pop(group, None)
    elif group in latches:
        latches[group] = [
            op.name
            for op in gap_workers
            if op.is_resting() or op.name in latches[group]
        ]
    elif conf.group_rest_in_full_on_mood_gap:
        times = [at for op in gap_workers if (at := completed_at(op)) is not None]
        threshold = conf.group_mood_gap_threshold_minutes
        if threshold is None:
            threshold = 90 if data.power_plant_count == 2 else 60
        limit = timedelta(minutes=threshold)
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
    max_wait = conf.group_mood_gap_max_extra_wait_hours
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
    # 缺少个别读数时沿用可用期限，不把补读变成整组回班的前置条件。
    deadlines = [at for at in explicit_times if at is not None]
    if gap_names:
        times = [completed_at(data.operators[name]) for name in gap_names]
        known = [at for at in times if at is not None]
        if len(known) != len(times) and cap is not None:
            deadlines.append(cap)
        elif known:
            latest = max(known)
            deadlines.append(min(latest, cap) if cap is not None else latest)
    return required, max(now, *deadlines) if deadlines else None
