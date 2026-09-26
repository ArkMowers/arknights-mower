"""测试宿舍共用的空闲候选快照；规划与执行只区分是否允许主动安排候补。"""

from dataclasses import dataclass
from datetime import datetime

from arknights_mower.utils.resting_priority import (
    RestingTier,
    busy_resting_names,
    resting_key,
    resting_mood,
    resting_tier,
    unregistered_idle_candidates,
)


@dataclass
class DormCandidates:
    recovering: list[str]
    full: list[str]
    unregistered: list[str]
    # 满员兜底按真实心情，不使用恢复缺口或优先级作第一排序条件。
    filling: list[str]


def dorm_candidates(
    op_data, excluded=(), *, include_standby=False, current_residents=(), now=None
):
    now = now or datetime.now()
    excluded = set(excluded) | busy_resting_names() | {op_data.get_train_support()}
    recovering, full = [], []
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
        if (
            not op_data.idle_rest_checked(name)
            and resting_mood(op, now) < op.upper_limit
        ):
            recovering.append(name)
        elif not op.is_high() and not op_data.has_rest_mood_limit(name):
            full.append(name)
    recovering.sort(key=lambda name: resting_key(op_data, name, now))

    def fill_key(name):
        return resting_mood(op_data.operators.get(name), now), resting_tier(
            op_data, name
        )

    full.sort(key=fill_key)
    unregistered = unregistered_idle_candidates(op_data, excluded)
    filling = sorted([*recovering, *full, *unregistered], key=fill_key)
    return DormCandidates(recovering, full, unregistered, filling)
