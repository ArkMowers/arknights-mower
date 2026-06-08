from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from arknights_mower.scheduler.constants import DORM_ROOM_PREFIX


class OperatorType(Enum):
    HIGH = "high"
    LOW = "low"


class RestPriority(Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class Operator:
    name: str

    room: str = ""
    index: int = -1
    group: str = ""
    replacement: list[str] = field(default_factory=list)
    operator_type: OperatorType = OperatorType.LOW
    resting_priority: RestPriority = RestPriority.NORMAL
    exhaust_require: bool = False
    rest_in_full: bool = False
    workaholic: bool = False
    arrange_order: list[str] = field(default_factory=lambda: ["技能", "false"])

    current_room: str = ""
    current_index: int = -1

    mood: float = 24.0
    upper_limit: float = 24.0
    lower_limit: float = 0.0
    depletion_rate: float = 0.0
    time_stamp: Optional[datetime] = None
    exhaust_time: Optional[datetime] = None
    refresh_drained: bool = False
    refresh_order_room: list = field(default_factory=lambda: [False, []])

    def is_high(self) -> bool:
        return self.operator_type == OperatorType.HIGH

    def is_resting(self) -> bool:
        return self.current_room.startswith(DORM_ROOM_PREFIX)

    def is_working(self) -> bool:
        from arknights_mower.data import base_room_list

        return self.current_room in base_room_list and not self.is_resting()

    def is_high_priority(self) -> bool:
        return self.resting_priority == RestPriority.HIGH

    def current_mood(self, time: Optional[datetime] = None) -> float:
        if time is None:
            time = datetime.now()
        if self.time_stamp is not None:
            predicted = (
                self.mood
                - self.depletion_rate * (time - self.time_stamp).total_seconds() / 3600
            )
            if 0 <= predicted <= 24:
                return predicted
        return self.mood

@dataclass
class Dormitory:
    position: tuple[str, int]
    name: str = ""
    time: Optional[datetime] = None

    def reset(self) -> None:
        self.name = ""
        self.time = None
