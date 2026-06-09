from __future__ import annotations

from datetime import datetime, timedelta

from typing import TYPE_CHECKING

from arknights_mower.scheduler.constants import DORM_ROOM_PREFIX
from arknights_mower.scheduler.domain.operators import Operator

if TYPE_CHECKING:
    from arknights_mower.scheduler.state import SchedulerState


def current_operators_in_room(
    state: SchedulerState, room: str
) -> list[str]:
    slots = state.plan.get(room, [])
    length = len(slots)
    result = [""] * length
    for op in state.operators.values():
        if op.current_room == room and 0 <= op.current_index < length:
            result[op.current_index] = op.name
    return result


def need_to_refresh(operator: Operator, h: float = 2, r: str = "") -> bool:
    if operator.name in ["歌蕾蒂娅", "见行者"]:
        h = 0.5
    if (
        operator.time_stamp is None
        or operator.time_stamp + timedelta(hours=h) < datetime.now()
        or (
            r.startswith(DORM_ROOM_PREFIX)
            and not operator.room.startswith(DORM_ROOM_PREFIX)
        )
    ):
        return True
    return False
