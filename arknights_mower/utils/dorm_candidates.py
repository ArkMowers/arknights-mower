"""规划与选人共用的宿舍预约和心情候选快照。"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from arknights_mower.utils.resting_priority import (
    RestingTier,
    busy_resting_names,
    has_resting_mood,
    resting_key,
    resting_mood,
    resting_tier,
    unregistered_idle_candidates,
)


@dataclass
class DormCandidates:
    recovering: list[str]
    full: list[str]
    # 缺少实读且尚需筛选；绿色笑脸观测仍只属于普通补位名单。
    unknown: list[str]
    # 有效低心情卡片仍需实读，但足以触发普通满员住客替换。
    estimated_recovering: list[str]
    # 满员兜底按心情；缺少实读时用卡片预估，不以恢复缺口排序。
    filling: list[str]


def dorm_candidate_mood(op_data, name, now=None):
    """候选筛选先用实读，缺失时用短期卡片预估；计时仍只用实读。"""
    now = now or datetime.now()
    op = op_data.operators.get(name)
    if has_resting_mood(op, now):
        return resting_mood(op, now)
    estimate = getattr(op_data, "dorm_mood_estimates", {}).get(name)
    if estimate is not None and timedelta() <= now - estimate[1] < timedelta(hours=1):
        return estimate[0]
    return None


def dorm_task_reservations(op_data, tasks, excluded=()):
    """规划与执行采用相同预约；待命候补的回班任务不阻止其临时恢复。"""
    names = set(excluded) - {"", "Current", "Free"}
    slots = set()
    for task in tasks:
        if task is None:
            continue
        names.update(getattr(task, "emergency_staffing_members", ()))
        names.update(
            name
            for row in getattr(task, "emergency_original_roster", {}).values()
            for name in row
            if name not in ("", "Current", "Free")
        )
        returning = getattr(getattr(task, "type", None), "name", "") == "SHIFT_ON"
        for room, row in task.plan.items():
            for index, name in enumerate(row):
                if room.startswith("dorm") and name != "Current":
                    slots.add((room, index))
                if name in ("", "Current", "Free"):
                    continue
                if not (
                    returning and name in op_data.operators and op_data.is_standby(name)
                ):
                    names.add(name)
    return names, slots


def vacant_dorm_slots(op_data, reserved_slots=()):
    """只认当前已经开放、实际缓存无人且尚未预约的动态床位。"""
    return {
        bed.position
        for bed in op_data.dorm
        if not bed.name
        and bed.position not in reserved_slots
        and op_data.is_effective_free_slot(bed)
        and op_data.get_current_operator(*bed.position) is None
    }


def dorm_candidates(
    op_data, excluded=(), *, include_standby=True, current_residents=(), now=None
):
    now = now or datetime.now()
    excluded = set(excluded) | busy_resting_names() | {op_data.get_train_support()}
    recovering, full, unknown = [], [], []
    for name, op in op_data.operators.items():
        if (
            name in excluded
            or op.is_high()
            and not (include_standby and op_data.is_standby(name))
            or op.current_room
            and not (name in current_residents and op.current_room.startswith("dorm"))
            or op_data.rest_mood_complete(name)
            or resting_tier(op_data, name) == RestingTier.EXCLUDED
        ):
            continue
        if not has_resting_mood(op, now):
            if not op.is_high() and not op_data.has_rest_mood_limit(name):
                unknown.append(name)
            continue
        if (
            not op_data.idle_rest_checked(name)
            and resting_mood(op, now) < op.upper_limit
        ):
            recovering.append(name)
        elif not op.is_high() and not op_data.has_rest_mood_limit(name):
            full.append(name)
    recovering.sort(key=lambda name: resting_key(op_data, name, now))

    unknown.extend(unregistered_idle_candidates(op_data, excluded))

    def estimate_key(name):
        mood = dorm_candidate_mood(op_data, name, now)
        return 24 if mood is None else mood, resting_tier(op_data, name)

    full.sort(key=estimate_key)
    unknown.sort(key=estimate_key)
    filling = sorted([*recovering, *full, *unknown], key=estimate_key)
    # 绿色笑脸只撤销主动核验；仍可补空床，不进入实读 full 集合。
    unknown = [
        name
        for name in unknown
        if (mood := dorm_candidate_mood(op_data, name, now)) is None or mood < 24
    ]
    estimated_recovering = [
        name
        for name in unknown
        if (mood := dorm_candidate_mood(op_data, name, now)) is not None
        and mood < getattr(op_data.operators.get(name), "upper_limit", 24)
    ]
    return DormCandidates(recovering, full, unknown, estimated_recovering, filling)
