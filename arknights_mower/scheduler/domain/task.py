from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TaskTypes(Enum):
    RUN_ORDER = ("run_order", "跑单", 1)
    FIAMMETTA = ("菲亚梅塔", "肥鸭", 2)
    SHIFT_OFF = ("shifit_off", "下班", 2)
    SHIFT_ON = ("shifit_on", "上班", 2)
    EXHAUST_OFF = ("exhaust_on", "用尽下班", 2)
    SELF_CORRECTION = ("self_correction", "纠错", 2)
    CLUE_PARTY = ("Impart", "趴体", 2)
    MAA_MALL = ("maa_Mall", "MAA信用购物", 2)
    NOT_SPECIFIC = ("", "空任务", 2)
    RECRUIT = ("recruit", "公招", 2)
    SKLAND = ("skland", "森空岛签到", 2)
    RE_ORDER = ("宿舍排序", "宿舍排序", 2)
    RELEASE_DORM = ("释放宿舍空位", "释放宿舍空位", 2)
    REFRESH_TIME = ("强制刷新任务时间", "强制刷新任务时间", 2)
    SKILL_UPGRADE = ("技能专精", "技能专精", 2)
    DEPOT = ("仓库扫描", "仓库扫描", 2)
    WORKSHOP = ("加工材料", "加工材料", 2)

    def __new__(cls, value: str, display_value: str, priority: int):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.display_value = display_value
        obj.priority = priority
        return obj


def set_type_enum(value: object) -> TaskTypes:
    if value is None:
        return TaskTypes.NOT_SPECIFIC
    if isinstance(value, TaskTypes):
        return value
    if isinstance(value, str):
        for task_type in TaskTypes:
            if value.upper() == task_type.display_value.upper():
                return task_type
    return TaskTypes.NOT_SPECIFIC


@dataclass
class SchedulerTask:
    time: datetime
    type: TaskTypes = TaskTypes.NOT_SPECIFIC
    plan: dict[str, list[str]] = field(default_factory=dict)
    meta_data: str = ""
    adjusted: bool = False

    def __str__(self) -> str:
        return (
            f"SchedulerTask(time='{self.time}',task_plan={self.plan},"
            f"task_type={self.type},meta_data='{self.meta_data}',adjusted={self.adjusted})"
        )
