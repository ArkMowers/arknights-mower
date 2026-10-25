"""按所选心情来源估算召回后的工作消耗与宿舍恢复速率。"""

from datetime import datetime, timedelta
from math import isfinite


def _positive(value):
    return isinstance(value, (int, float)) and isfinite(value) and value > 0


def _observed(op, now):
    return (
        op.time_stamp is not None
        and op.time_stamp <= now
        and not getattr(op, "mood_is_prediction", False)
        and not getattr(op, "working_mood_unconfirmed", False)
        and isinstance(op.mood, (int, float))
        and isfinite(op.mood)
        and 0 <= op.mood <= 24
    )


def observe_work_rate(op, mood, room, index, now, *, preserve=False):
    """仅同一工作岗位的两次实读下降产生工作速率；充能换位不采样。"""
    op.recall_work_rate_checked = True
    if (
        preserve
        or not op.is_working()
        or (op.current_room, op.current_index) != (room, index)
        or not _observed(op, now)
        or not isinstance(mood, (int, float))
        or not isfinite(mood)
        or not 0 <= mood < op.mood
        or now - op.time_stamp <= timedelta(minutes=29)
    ):
        return
    rate = (op.mood - mood) * 3600 / (now - op.time_stamp).total_seconds()
    if _positive(rate):
        op.recall_work_rate = (rate, now)


def _bed_role(data, op, *, projected=False):
    from arknights_mower.utils.dorm_recovery import (
        active_recovery_position,
        recovery_managers,
        recovery_target,
    )

    room = op.current_room
    if (
        not room.startswith("dorm")
        or room not in getattr(data, "plan", {})
        or not hasattr(data, "get_current_operator")
    ):
        return None
    occupants = [
        data.get_current_operator(room, index) for index in range(len(data.plan[room]))
    ]
    names = [resident.name if resident is not None else "" for resident in occupants]
    managers = recovery_managers(data, room, names, update_cache=False)
    if not managers:
        return room, "ordinary"
    confirmed = next(
        (
            resident
            for resident in occupants
            if resident is not None
            and resident.mood < resident.upper_limit
            and active_recovery_position(resident) == (room, resident.current_index)
            and getattr(resident, "dorm_recovery_fixed", ()) == managers
        ),
        None,
    )
    if confirmed is not None:
        return room, "single" if op.name == confirmed.name else "ordinary"
    if not projected:
        return None
    expected = recovery_target(data, room, names, {name for name, _, _ in managers})
    if expected is not None and op.name == expected.name:
        return room, "single"
    return room, "ordinary"


def _recovery_sample(data, bed, now):
    op = data.operators.get(bed.name)
    if (
        op is None
        or not _observed(op, now)
        or (op.current_room, op.current_index) != bed.position
        or bed.time is None
        or bed.time <= now
        or not _positive(op.upper_limit - op.mood)
    ):
        return None
    role = _bed_role(data, op)
    if role is None:
        return None
    rate = (
        (op.upper_limit - op.mood) * 3600 / (bed.time - op.time_stamp).total_seconds()
    )
    return (role, (rate, op.time_stamp)) if _positive(rate) else None


def _remember(samples, role, sample):
    samples[role] = sample
    while len(samples) > 8:
        del samples[min(samples, key=lambda key: samples[key][1])]


def _current_recovery_samples(data, now):
    samples = {}
    for bed in data.all_dorms():
        observed = _recovery_sample(data, bed, now)
        if observed is None:
            continue
        role, sample = observed
        if role not in samples or sample[0] < samples[role][0]:
            samples[role] = sample
    return samples


def observe_recovery_rate(data, bed, *, now=None):
    """保存已读个人恢复期限，按宿舍及单回类别保留最多八条记录。"""
    if not hasattr(data, "all_dorms"):
        return
    now = now or datetime.now()
    sample = _recovery_sample(data, bed, now)
    if sample is None:
        return
    if not hasattr(data, "recall_recovery_rates"):
        data.recall_recovery_rates = {}
    role, _ = sample
    sample = role, _current_recovery_samples(data, now)[role]
    _remember(data.recall_recovery_rates, *sample)


def estimated_recall_rates(original, admitted, now=None):
    """返回模型阵容速率或实测近似速率，不写回实际心情与期限。"""
    now = now or datetime.now()
    if getattr(original, "mood_calculation_enabled", False):
        work, recovery = {}, {}
        for name, projected in admitted.operators.items():
            rate = admitted.calculated_mood_rate(name, now)
            if not isinstance(rate, (int, float)) or not isfinite(rate):
                continue
            if projected.is_working() and rate >= 0:
                work[name] = rate
            elif projected.is_resting() and rate < 0:
                recovery[name] = -rate
        return work, recovery
    samples = {
        role: sample
        for role, sample in getattr(original, "recall_recovery_rates", {}).items()
        if _positive(sample[0]) and sample[1] <= now
    }
    for role, sample in _current_recovery_samples(original, now).items():
        samples[role] = sample
    work, recovery = {}, {}
    for name, projected in admitted.operators.items():
        observed = original.operators.get(name)
        if observed is None:
            continue
        if projected.is_working():
            sample = getattr(observed, "recall_work_rate", None)
            if sample is not None and _positive(sample[0]) and sample[1] <= now:
                work[name] = sample[0]
            elif (
                not getattr(observed, "recall_work_rate_checked", False)
                and observed.is_working()
                and _observed(observed, now)
                and _positive(observed.depletion_rate)
            ):
                work[name] = observed.depletion_rate
        elif projected.is_resting():
            role = _bed_role(admitted, projected, projected=True)
            if role is None:
                continue
            sample = samples.get(role)
            if sample is None and role[1] == "single":
                sample = samples.get((role[0], "ordinary"))
            if sample is not None:
                recovery[name] = sample[0]
    return work, recovery
