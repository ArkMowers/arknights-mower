from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class MoodLimits(BaseModel):
    lower: float = Field(default=0, ge=0, lt=24, allow_inf_nan=False)
    upper: float = Field(default=24, gt=0, le=24, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_range(self):
        if self.lower >= self.upper:
            raise ValueError("心情下限必须小于上限")
        return self


class PlanConf(BaseModel):
    ling_xi: int = 1
    "令夕模式，1感知 2烟火 3均衡"
    mood_limits: Optional[MoodLimits] = None
    "全体干员自定义心情上下限；空值沿用自动规则"
    operator_mood_limits: dict[str, MoodLimits] = Field(default_factory=dict)
    "指定干员上下限，优先于全体设置"
    exhaust_require: str = ""
    "耗尽"
    rest_in_full: str = ""
    "回满"
    resting_priority: str = ""
    "低优先级"
    resting_priority_replacement: str = ""
    "测试宿舍逻辑：宿舍高优先级替班，仅提升替班身份"
    resting_standby: str = ""
    "宿舍休息候补干员"
    workaholic: str = ""
    "0心情工作（主力宿舍黑名单）"
    refresh_trading: str = ""
    "跑单时间刷新干员"
    refresh_drained: str = ""
    "用尽时间刷新干员"
    ope_resting_priority: str = ""
    "休息排序优先级"
    dorm_order: str = ""
    "测试宿舍逻辑下当前排班的宿舍房间优先级"


class BackupPlanConf(PlanConf):
    free_blacklist: str = ""
    "（非主力）宿舍黑名单"
    dorm_order_override: Optional[bool] = None
    "是否由该副表显式覆盖此前生效的宿舍房间优先级"


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
    gaming_1: Optional[Facility] = None
    "活动室1"
    gaming_2: Optional[Facility] = None
    "活动室2"
    gaming_3: Optional[Facility] = None
    "活动室3"
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
    gaming_1: Optional[list[str]] = None
    "活动室1"
    gaming_2: Optional[list[str]] = None
    "活动室2"
    gaming_3: Optional[list[str]] = None
    "训练室3"
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
    # 空值表示始终跟随切入时机，兼容旧排班且允许之后修改切入时机。
    exit_trigger_timing: Optional[str] = None
    name: str = "plan"


class PlanModel(BaseModel):
    default: str = "plan1"
    plan1: Plan1 = Plan1()
    conf: PlanConf = PlanConf()
    backup_plans: list[BackupPlan] = []
    # 全局运行设置随排班导出；旧排班没有此字段时保留本机现有设置。
    advanced_settings: Optional[dict[str, Any]] = None


def parse_plan_document(data) -> PlanModel:
    """Reject unrelated JSON instead of silently constructing an empty plan."""
    if not isinstance(data, dict) or not isinstance(data.get("plan1"), dict):
        raise ValueError("排班文件必须包含 plan1 主排班")
    if data.get("default", "plan1") != "plan1":
        raise ValueError("不支持的主排班名称")
    return PlanModel(**data)


def migrate_legacy_dorm_order(
    plan: PlanModel, data: dict, legacy_dorm_order: str
) -> bool:
    """迁移全局旧床位顺序，并折叠为每张排班独立的房间顺序。

    主表缺少独立字段时继承旧全局值；副表只迁移显式的非默认顺序。
    历史版本自动写入副表的 1→2→3→4 视为未覆盖，避免后续副表把
    前一张副表的自定义顺序冲回默认值。
    """
    rooms = [f"dormitory_{index}" for index in range(1, 5)]

    def room_order(value: str) -> str:
        result = []
        for item in (value or "").split(","):
            parts = item.rsplit("_", 1)
            room = (
                parts[0]
                if len(parts) == 2 and parts[0] in rooms and parts[1].isdigit()
                else item
            )
            if room in rooms and room not in result:
                result.append(room)
        result.extend(room for room in rooms if room not in result)
        return ",".join(result)

    changed = False
    main_conf = data.get("conf")
    if not isinstance(main_conf, dict) or "dorm_order" not in main_conf:
        plan.conf.dorm_order = legacy_dorm_order
        changed = True
    normalized = room_order(plan.conf.dorm_order)
    if plan.conf.dorm_order != normalized:
        plan.conf.dorm_order = normalized
        changed = True
    raw_backups = data.get("backup_plans")
    if not isinstance(raw_backups, list):
        raw_backups = []
    for index, backup in enumerate(plan.backup_plans):
        raw_conf = raw_backups[index].get("conf") if index < len(raw_backups) else None
        raw_conf = raw_conf if isinstance(raw_conf, dict) else {}
        raw_order = str(raw_conf.get("dorm_order", "") or "")
        normalized = room_order(raw_order) if raw_order else ""
        explicit = raw_conf.get("dorm_order_override")
        if explicit is None:
            explicit = bool(normalized and normalized != ",".join(rooms))
        explicit = bool(explicit)
        desired_order = normalized if explicit else ""
        if backup.conf.dorm_order != desired_order:
            backup.conf.dorm_order = desired_order
            changed = True
        if backup.conf.dorm_order_override != explicit:
            backup.conf.dorm_order_override = explicit
            changed = True
    return changed
