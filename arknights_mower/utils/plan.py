import copy
from enum import Enum
from typing import Optional, Self

from arknights_mower.utils.logic_expression import LogicExpression


class PlanTriggerTiming(Enum):
    "副表触发时机"

    BEGINNING = 0
    "任务开始"
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
        max_resting_count: int = 4,
        free_blacklist: str = "",
        resting_threshold: float = 0.5,
        refresh_trading_config: str = "",
        free_room: bool = False,
        refresh_drained: str = "",
    ):
        """排班的设置

        Args:
            rest_in_full: 回满
            exhaust_require: 耗尽
            resting_priority: 低优先级
            ling_xi: 令夕模式
            workaholic: 0心情工作
            max_resting_count: 最大组人数
            free_blacklist: 宿舍黑名单
            resting_threshold: 心情阈值
            refresh_trading_config: 跑单时间刷新干员
            free_room: 宿舍不养闲人模式
        """
        self.rest_in_full = to_list(rest_in_full)
        self.exhaust_require = to_list(exhaust_require)
        self.workaholic = to_list(workaholic)
        self.resting_priority = to_list(resting_priority)
        self.max_resting_count = max_resting_count
        self.free_blacklist = to_list(free_blacklist)
        # 0 为均衡模式
        # 1 为感知信息模式
        # 2 为人间烟火模式
        self.ling_xi = ling_xi
        self.resting_threshold = resting_threshold
        self.free_room = free_room
        # 格式为 干员名字+ 括弧 +指定房间（逗号分隔）
        # 不指定房间则默认全跑单站
        # example： 阿米娅,夕,令
        #           夕(room_3_1,room_1_3),令(room_3_1)
        self.refresh_trading_config = to_list(refresh_trading_config)
        self.refresh_drained = to_list(refresh_drained)

    def is_rest_in_full(self, agent_name) -> bool:
        return agent_name in self.rest_in_full

    def is_exhaust_require(self, agent_name) -> bool:
        return agent_name in self.exhaust_require

    def is_workaholic(self, agent_name) -> bool:
        return agent_name in self.workaholic

    def is_resting_priority(self, agent_name) -> bool:
        return agent_name in self.resting_priority

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
            "free_blacklist",
            "refresh_trading_config",
            "refresh_drained",
        ]:
            p_dict = set(getattr(n, p))
            target_p = set(getattr(target, p))
            setattr(n, p, list(p_dict.union(target_p)))
        return n


class Room:
    def __init__(
        self,
        agent: str,
        group: str,
        replacement: list[str],
        facility: str,
        product: str,
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


class Plan:
    def __init__(
        self,
        plan: dict[str, Room],
        config: PlanConfig,
        trigger: Optional[LogicExpression] = None,
        task: Optional[dict[str, list[str]]] = None,
        trigger_timing: Optional[str] = None,
    ):
        """
        Args:
            plan: 基建计划 or 触发备用plan 的排班表，只需要填和默认不一样的部分
            config: 基建计划相关配置，必须填写全部配置
            trigger: 触发备用plan 的条件（必填）就是每次最多只有一个备用plan触发
            task: 触发备用plan 的时间生成的任务（选填）
            trigger_timing: 触发时机
        """
        self.plan = plan
        self.config = config
        self.trigger = trigger
        self.task = task
        self.trigger_timing = self.set_timing_enum(trigger_timing)

    @staticmethod
    def set_timing_enum(value: str) -> PlanTriggerTiming:
        "将字符串转换为副表触发时机"
        try:
            return PlanTriggerTiming[value.upper()]
        except Exception:
            return PlanTriggerTiming.AFTER_PLANNING
