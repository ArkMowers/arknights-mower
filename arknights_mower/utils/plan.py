import copy
from enum import Enum
from typing import Optional, Self

from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.mastery_support_types import IGNORED_NAMES

DEFAULT_DORM_ROOM_ORDER = [f"dormitory_{index}" for index in range(1, 5)]


def effective_dorm_room_order(values: list[str]) -> list[str]:
    """将房间或旧具体床位顺序折叠为完整的四宿舍顺序。"""
    result = []
    for value in values:
        parts = value.rsplit("_", 1)
        room = (
            parts[0]
            if len(parts) == 2
            and parts[0] in DEFAULT_DORM_ROOM_ORDER
            and parts[1].isdigit()
            else value
        )
        if room in DEFAULT_DORM_ROOM_ORDER and room not in result:
            result.append(room)
    result.extend(room for room in DEFAULT_DORM_ROOM_ORDER if room not in result)
    return result


class PlanTriggerTiming(Enum):
    "副表触发时机"

    BEGINNING = 0
    "任务开始"
    BEFORE_WORK = 100
    "进入第一个工作站前"
    BEFORE_DORM = 200
    "入住宿舍前"
    BEFORE_PLANNING = 300
    "下班结束"
    AFTER_PLANNING = 600
    "上班结束"
    END = 999
    "任务结束"


class BaseProduct(Enum):
    "基地产物"

    LMD = 0
    "龙门币"
    PureGold = 1
    "赤金"
    Electricity = 3


def to_list(str_data: str) -> list[str]:
    lst = str_data.replace("，", ",").split(",")
    return [x.strip() for x in lst]


class PlanConfig:
    def __init__(
        self,
        rest_in_full: str,
        exhaust_require: str,
        resting_priority: str,
        ling_xi: int = 0,
        workaholic: str = "",
        free_blacklist: str = "",
        resting_threshold: float = 0.5,
        refresh_trading_config: str = "",
        free_room: bool = False,
        refresh_drained: str = "",
        ope_resting_priority: str = "",
        resting_standby: str = "",
        dorm_order: str = "",
        dorm_order_override: Optional[bool] = None,
        experimental_dorm_logic: bool = False,
        mood_limits: Optional[dict] = None,
        operator_mood_limits: Optional[dict] = None,
        resting_priority_replacement: str = "",
    ):
        """排班的设置

        Args:
            rest_in_full: 回满
            exhaust_require: 耗尽
            resting_priority: 低优先级
            ling_xi: 令夕模式
            workaholic: 0心情工作
            free_blacklist: 宿舍黑名单
            resting_threshold: 心情阈值
            refresh_trading_config: 跑单时间刷新干员
            free_room: 宿舍不养闲人模式
        """
        self.rest_in_full = to_list(rest_in_full)
        self.exhaust_require = to_list(exhaust_require)
        self.workaholic = to_list(workaholic)
        self.resting_priority = to_list(resting_priority)
        self.resting_priority_replacement = to_list(resting_priority_replacement)
        self.resting_standby = to_list(resting_standby)
        self.free_blacklist = to_list(free_blacklist)
        # 0 为均衡模式
        # 1 为感知信息模式
        # 2 为人间烟火模式
        self.ling_xi = ling_xi
        from arknights_mower.utils.config.plan import MoodLimits

        self.mood_limits = (
            MoodLimits.model_validate(mood_limits).model_dump()
            if mood_limits is not None
            else None
        )
        self.operator_mood_limits = {
            name: MoodLimits.model_validate(limits).model_dump()
            for name, limits in (operator_mood_limits or {}).items()
        }
        self.resting_threshold = resting_threshold
        self.free_room = free_room
        # 格式为 干员名字+ 括弧 +指定房间（逗号分隔）
        # 不指定房间则默认全跑单站
        # example： 阿米娅,夕,令
        #           夕(room_3_1,room_1_3),令(room_3_1)
        self.refresh_trading_config = to_list(refresh_trading_config)
        self.refresh_drained = to_list(refresh_drained)
        self.ope_resting_priority = to_list(ope_resting_priority)
        self.dorm_order = [name for name in to_list(dorm_order) if name]
        self.dorm_order_override = (
            dorm_order_override
            if dorm_order_override is not None
            else bool(
                self.dorm_order
                and effective_dorm_room_order(self.dorm_order)
                != DEFAULT_DORM_ROOM_ORDER
            )
        )
        self.experimental_dorm_logic = experimental_dorm_logic

    def is_rest_in_full(self, agent_name) -> bool:
        return agent_name in self.rest_in_full

    def custom_mood_limits(self, name):
        return self.operator_mood_limits.get(name, self.mood_limits)

    def is_exhaust_require(self, agent_name) -> bool:
        return agent_name in self.exhaust_require

    def is_workaholic(self, agent_name) -> bool:
        return agent_name in self.workaholic

    def is_resting_priority(self, agent_name) -> bool:
        return agent_name in self.resting_priority

    def is_resting_standby(self, agent_name) -> bool:
        return agent_name in self.resting_standby

    def is_free_blacklist(self, agent_name) -> bool:
        return agent_name in self.free_blacklist

    def is_refresh_drained(self, agent_name) -> bool:
        return agent_name in self.refresh_drained

    def is_refresh_trading(self, agent_name) -> list[bool, list[str]]:
        match = next(
            (e for e in self.refresh_trading_config if agent_name in e.lower()),
            None,
        )
        if match is not None:
            if match.replace(agent_name, "") != "":
                return [True, match.replace(agent_name, "").split(",")]
            else:
                return [True, []]
        else:
            return [False, []]

    def merge_config(self, target: Self) -> Self:
        n = copy.deepcopy(self)
        for p in [
            "rest_in_full",
            "exhaust_require",
            "workaholic",
            "resting_priority",
            "resting_priority_replacement",
            "resting_standby",
            "free_blacklist",
            "refresh_trading_config",
            "refresh_drained",
            "ope_resting_priority",
        ]:
            p_list = getattr(n, p)
            target_list = getattr(target, p)
            merged_list = []
            for item in p_list + target_list:
                if item not in merged_list:
                    merged_list.append(item)
            setattr(n, p, merged_list)
        # 副表未显式设置宿舍顺序时继承此前结果；只有显式设置的副表覆盖。
        if self.experimental_dorm_logic and target.dorm_order_override:
            n.dorm_order = copy.deepcopy(target.dorm_order)
            n.dorm_order_override = True
        if target.mood_limits is not None:
            n.mood_limits = copy.deepcopy(target.mood_limits)
        n.operator_mood_limits.update(copy.deepcopy(target.operator_mood_limits))
        return n


class Room:
    def __init__(
        self,
        agent: str,
        group: str,
        replacement: list[str],
        facility: str = "",
        product: str = "",
    ):
        """房间

        Args:
            agent: 主力干员
            group: 组
            replacement: 替换组
        """
        self.agent = agent
        self.group = group
        self.replacement = replacement
        self.facility = facility
        if self.facility == "发电站":
            self.product = BaseProduct.Electricity
        else:
            self.product = product

    def __repr__(self):
        return (
            f"Room(agent='{self.agent}', group='{self.group}', replacement={self.replacement}, "
            f"facility='{self.facility}', product='{self.product}')"
        )


class Plan:
    def __init__(
        self,
        plan: dict[str, Room],
        config: PlanConfig,
        trigger: Optional[LogicExpression] = None,
        task: Optional[dict[str, list[str]]] = None,
        trigger_timing: Optional[str] = None,
        exit_trigger_timing: Optional[str] = None,
        name: Optional[str] = "",
        products: Optional[dict[str, str]] = None,
    ):
        """
        Args:
            plan: 基建计划 or 触发备用plan 的排班表，只需要填和默认不一样的部分
            config: 基建计划相关配置，必须填写全部配置
            trigger: 触发备用plan 的条件（必填）就是每次最多只有一个备用plan触发
            task: 触发备用plan 的时间生成的任务（选填）
            trigger_timing: 触发时机
            exit_trigger_timing: 退出时机；未填写时与触发时机一致
        """
        self.plan = plan
        self.config = config
        self.trigger = trigger
        self.task = task
        self.trigger_timing = self.set_timing_enum(trigger_timing)
        self._exit_trigger_timing = (
            self.set_timing_enum(exit_trigger_timing) if exit_trigger_timing else None
        )
        self.name = name
        self.products = products or {}

    def scheduled_names(self, include_tasks: bool = False) -> set[str]:
        """Return assigned operators, including replacements and optional tasks."""
        names = {
            name
            for room in self.plan.values()
            for slot in room
            for name in (slot.agent, *slot.replacement)
        }
        if include_tasks:
            names.update(name for task in (self.task or {}).values() for name in task)
        return names - IGNORED_NAMES

    def primary_names(self) -> set[str]:
        """Return primary assignments used to compare backup plans."""
        return {
            slot.agent
            for room in self.plan.values()
            for slot in room
            if slot.agent not in IGNORED_NAMES
        }

    @property
    def exit_trigger_timing(self) -> PlanTriggerTiming:
        """未单独配置时动态跟随切入时机。"""
        return self._exit_trigger_timing or self.trigger_timing

    @exit_trigger_timing.setter
    def exit_trigger_timing(self, value: Optional[str | PlanTriggerTiming]):
        if value is None:
            self._exit_trigger_timing = None
        elif isinstance(value, PlanTriggerTiming):
            self._exit_trigger_timing = value
        else:
            self._exit_trigger_timing = self.set_timing_enum(value)

    @staticmethod
    def set_timing_enum(value: str) -> PlanTriggerTiming:
        "将字符串转换为副表触发时机"
        try:
            return PlanTriggerTiming[value.upper()]
        except Exception:
            return PlanTriggerTiming.AFTER_PLANNING
