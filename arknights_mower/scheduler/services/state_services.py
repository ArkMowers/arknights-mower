from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from arknights_mower.scheduler.constants import DORM_ROOM_PREFIX, FacilityType
from arknights_mower.scheduler.domain.operators import Operator, OperatorType
from arknights_mower.scheduler.services.operator_service import need_to_refresh

if TYPE_CHECKING:
    from arknights_mower.scheduler.state import SchedulerState


def operator_not_valid(operator: Operator) -> bool:
    """`SchedulerState.not_valid` 的无状态实现（跨对象逻辑，落 service）。"""
    if operator.room == FacilityType.TRAIN.value:
        return False
    if operator.operator_type == OperatorType.HIGH:
        if operator.workaholic:
            return (
                operator.current_room != operator.room
                or operator.index != operator.current_index
            )
        if not operator.room.startswith(
            DORM_ROOM_PREFIX
        ) and operator.current_room.startswith(DORM_ROOM_PREFIX):
            if operator.mood == -1 or operator.mood == 24:
                return True
            else:
                return False
        return (
            need_to_refresh(operator, 2.5)
            or operator.current_room != operator.room
            or operator.index != operator.current_index
        )
    return False


def predict_operator_exhaust(operator: Operator) -> datetime:
    """`SchedulerState.predict_exhaust` 的无状态实现。"""
    if (
        operator.workaholic
        or operator.exhaust_require
        or operator.room in [FacilityType.FACTORY.value, FacilityType.TRAIN.value]
    ):
        return datetime.now() + timedelta(hours=24)
    remaining_mood = operator.mood - operator.lower_limit
    depletion_rate = operator.depletion_rate
    if operator.time_stamp and depletion_rate > 0:
        predict = operator.time_stamp + timedelta(
            hours=((remaining_mood / depletion_rate) - 0.5)
        )
        if operator.exhaust_time is not None:
            return min(predict, operator.exhaust_time)
        else:
            return predict
    elif remaining_mood <= 0:
        return datetime.now()
    return datetime.now() + timedelta(hours=24)


def count_available_free(state: SchedulerState, free_type: str = "high") -> int:
    """`SchedulerState.available_free` 的无状态实现。"""
    dorm_count = sum(1 for key in state.plan if key.startswith("dorm"))
    total = len(state.dormitories)
    count_high = 0
    count_low = 0
    for dorm in state.dormitories.values():
        if dorm.name == "" or (
            dorm.name in state.operators and not state.operators[dorm.name].is_high()
        ):
            continue
        if dorm.name in state.operators:
            op = state.operators[dorm.name]
            if op.is_high_priority():
                count_high += 1
            else:
                count_low += 1
    available_high = max(0, dorm_count - count_high)
    available_low = total - count_low - max(count_high, dorm_count)
    return available_high if free_type == "high" else available_low
