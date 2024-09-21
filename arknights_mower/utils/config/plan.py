from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PlanConf(BaseModel):
    ling_xi: int = 1
    "令夕模式，1感知 2烟火 3均衡"
    max_resting_count: int = 4
    "最大组人数"
    exhaust_require: str = ""
    "耗尽"
    rest_in_full: str = ""
    "回满"
    resting_priority: str = ""
    "低优先级"
    workaholic: str = ""
    "0心情工作（主力宿舍黑名单）"
    refresh_trading: str = ""
    "跑单时间刷新干员"
    refresh_drained: str = ""
    "用尽时间刷新干员"


class BackupPlanConf(PlanConf):
    free_blacklist: str = ""
    "（非主力）宿舍黑名单"


class Plans(BaseModel):
    agent: str
    group: str = ""
    replacement: list[str] = []


class Facility(BaseModel):
    name: str = ""
    plans: list[Plans] = []
    product: Optional[str] = None


class Plan1(BaseModel):
    central: Optional[Facility] = None
    "控制中枢"
    meeting: Optional[Facility] = None
    "会客室"
    factory: Optional[Facility] = None
    "加工站"
    contact: Optional[Facility] = None
    "办公室"
    train: Optional[Facility] = None
    "训练室"
    dormitory_1: Optional[Facility] = None
    dormitory_2: Optional[Facility] = None
    dormitory_3: Optional[Facility] = None
    dormitory_4: Optional[Facility] = None
    room_1_1: Optional[Facility] = None
    room_1_2: Optional[Facility] = None
    room_1_3: Optional[Facility] = None
    room_2_1: Optional[Facility] = None
    room_2_2: Optional[Facility] = None
    room_2_3: Optional[Facility] = None
    room_3_1: Optional[Facility] = None
    room_3_2: Optional[Facility] = None
    room_3_3: Optional[Facility] = None


class Task(BaseModel):
    central: Optional[list[str]] = None
    "控制中枢"
    meeting: Optional[list[str]] = None
    "会客室"
    factory: Optional[list[str]] = None
    "加工站"
    contact: Optional[list[str]] = None
    "办公室"
    train: Optional[list[str]] = None
    "训练室"
    dormitory_1: Optional[list[str]] = None
    dormitory_2: Optional[list[str]] = None
    dormitory_3: Optional[list[str]] = None
    dormitory_4: Optional[list[str]] = None
    room_1_1: Optional[list[str]] = None
    room_1_2: Optional[list[str]] = None
    room_1_3: Optional[list[str]] = None
    room_2_1: Optional[list[str]] = None
    room_2_2: Optional[list[str]] = None
    room_2_3: Optional[list[str]] = None
    room_3_1: Optional[list[str]] = None
    room_3_2: Optional[list[str]] = None
    room_3_3: Optional[list[str]] = None


class Trigger(BaseModel):
    left: str | Trigger = ""
    operator: str = ""
    right: str | Trigger = ""


class BackupPlan(BaseModel):
    conf: BackupPlanConf = {}
    plan: Plan1 = {}
    task: Task = {}
    trigger: Trigger = {}
    trigger_timing: str = "AFTER_PLANNING"


class PlanModel(BaseModel):
    default: str = "plan1"
    plan1: Plan1 = Plan1()
    conf: PlanConf = PlanConf()
    backup_plans: list[BackupPlan] = []
