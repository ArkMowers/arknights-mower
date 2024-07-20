from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .enum import (
    MaaRGEnum,
    RogueModeEnum,
    RogueRoleEnum,
    SATargetEnum,
    SquadEnum,
    WeekdayStrEnum,
)
from .util import empty_str_to_none, from_old_str_to_list, from_str_to_path


class MaaWeeklyPlanConfig(BaseModel):
    """
    旧 MAA 周计划
    """

    medicine: int = 0
    "理智药数量"

    stage: list[str] = []
    "关卡列表"

    weekday: Optional[WeekdayStrEnum] = None
    """
    周计划时间

    传入一个字符串，将会自动转换为对应的枚举类型。
    例如：
        - 周一
        - 周二
        - 周三
        - 周四
        - 周五
        - 周六
        - 周日
    """


class MaaWeeklyPlan1Stage(BaseModel):
    stage: list[str]
    "关卡列表"
    周一: int = 1
    "是否在周一进行"
    周二: int = 1
    "是否在周二进行"
    周三: int = 1
    "是否在周三进行"
    周四: int = 1
    "是否在周四进行"
    周五: int = 1
    "是否在周五进行"
    周六: int = 1
    "是否在周六进行"
    周日: int = 1
    "是否在周日进行"


class RogueConfig(BaseModel):
    squad: Optional[SquadEnum] = None
    """
    分队列表

    传入一个字符串，将会自动转换为对应的枚举类型。
    例如：
        - 研究分队
        - 指挥分队
        - 集群分队
        - 后勤分队
        - 矛头分队
        - 突击战术分队
        - 堡垒战术分队
        - ...
    """

    roles: Optional[RogueRoleEnum] = None
    """
    肉鸽职业

    传入一个字符串，将会自动转换为对应的枚举类型。
    例如：
        - 先手必胜
        - 稳扎稳打
        - 取长补短
        - 随心所欲
    """

    core_char: str = ""
    "核心干员"

    use_support: bool = False
    "是否使用助战干员"

    use_nonfriend_support: bool = False
    "是否使用非好友助战干员"

    mode: RogueModeEnum = RogueModeEnum.刷源石锭
    """
    肉鸽策略

    0: 刷等级
    1: 刷源石锭
    """

    investment_enabled: bool = True
    "是否投资源石锭"

    stop_when_investment_full: bool = True
    "是否投资源石锭满时停止"

    refresh_trader_with_dice: bool = False
    "是否刷新商店（指路鳞）"

    _empty_str_to_none = field_validator("roles", "squad", mode="before")(
        empty_str_to_none
    )


class SSSConfig(BaseModel):
    type: Literal[1, 2] = 1
    """
    关卡

    1 为左上
    2 为右下
    """

    ec: Literal[1, 2, 3] = 1
    """
    导能单元

    从左到右分别为 1, 2, 3
    """

    loop: int = 1
    "循环次数"

    copilot: Optional[Path] = None

    _to_path = field_validator("copilot", mode="before")(from_str_to_path)


class RAConfig(BaseModel):
    """
    生息演算配置
    """

    timeout: int = 30
    "生息演算超时时间"


class SAConfig(BaseModel):
    """
    隐秘前线配置
    """

    target: SATargetEnum = SATargetEnum.结局A


class MaaConfig(BaseModel):
    """
    Arknights Mower Maa 配置
    """

    maa_adb_path: Optional[Path] = None
    """
    Maa ADB 路径

    传入一个字符串，将会自动转换为对应的 Path 类型。
    """

    maa_enable: bool = False
    "是否启用 Maa"

    maa_rg_enable: bool = False
    "是否启用 Maa 大型任务"

    maa_long_task_type: MaaRGEnum = MaaRGEnum.集成战略

    maa_path: Optional[Path] = None
    """Maa 路径
    
    应该填入 Maa 的文件夹路径
    传入一个字符串，将会自动转换为对应的 Path 类型。
    """

    maa_expiring_medicine: bool = False
    "是否自动使用 60 小时内过期的理智药"

    maa_eat_stone: bool = False
    "是否自动磕源石"

    maa_weekly_plan: list[MaaWeeklyPlanConfig] = []
    "MAA 周计划 (旧)"

    maa_weekly_plan1: list[MaaWeeklyPlan1Stage] = []
    "MAA 周计划 (新)"

    maa_gap: float = 4
    """
    Maa 日常任务间隔
    
    单位为小时，可以为小数
    """

    maa_mall_blacklist: list[str] = []
    """
    信用商城黑名单

    一个字符串列表。为了兼容老配置，也可以传入一个字符串自动序列化。
    """

    maa_mall_buy: list[str] = []
    """
    信用商城购买列表

    一个字符串列表。为了兼容老配置，也可以传入一个字符串自动序列化。
    """

    maa_mall_ignore_blacklist_when_full: bool = False
    "信用点满时忽略黑名单"

    maa_rg_sleep_max: str = "0:00"
    """
    大型任务休眠最大时间

    填入一个字符串，格式为 "HH:MM"，例如 "01:23"
    TODO: 是否改为 TimeDelta
    """
    maa_rg_sleep_min: str = "0:00"
    """
    大型任务休眠最小时间

    填入一个字符串，格式为 "HH:MM"，例如 "01:23"
    TODO: 是否改为 TimeDelta
    """

    rogue: RogueConfig = Field(default_factory=RogueConfig)

    sss: SSSConfig = Field(default_factory=SSSConfig)

    reclamation_algorithm: RAConfig = Field(default_factory=RAConfig)

    _maa_old_to_new = field_validator(
        "maa_mall_blacklist", "maa_mall_buy", mode="before"
    )(from_old_str_to_list)
    _maa_to_path = field_validator("maa_adb_path", "maa_path", mode="before")(
        from_str_to_path
    )
