from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PlanTriggerTiming(Enum):
    BEGINNING = 0
    BEFORE_PLANNING = 300
    AFTER_PLANNING = 600
    END = 999


class BaseProduct(Enum):
    LMD = 0
    PURE_GOLD = 1
    ELECTRICITY = 3


@dataclass
class PlanConfig:
    rest_in_full: list[str] = field(default_factory=list)
    exhaust_require: list[str] = field(default_factory=list)
    resting_priority: list[str] = field(default_factory=list)
    ling_xi: int = 0
    workaholic: list[str] = field(default_factory=list)
    free_blacklist: list[str] = field(default_factory=list)
    resting_threshold: float = 0.5
    refresh_trading_config: list[str] = field(default_factory=list)
    refresh_drained: list[str] = field(default_factory=list)
    free_room: bool = False
    ope_resting_priority: list[str] = field(default_factory=list)

    def is_rest_in_full(self, agent_name: str) -> bool:
        return agent_name in self.rest_in_full

    def is_exhaust_require(self, agent_name: str) -> bool:
        return agent_name in self.exhaust_require

    def is_workaholic(self, agent_name: str) -> bool:
        return agent_name in self.workaholic

    def is_resting_priority(self, agent_name: str) -> bool:
        return agent_name in self.resting_priority

    def is_free_blacklist(self, agent_name: str) -> bool:
        return agent_name in self.free_blacklist

    def is_refresh_drained(self, agent_name: str) -> bool:
        return agent_name in self.refresh_drained


@dataclass
class Room:
    agent: str
    group: str = ""
    replacement: list[str] = field(default_factory=list)
    facility: str = ""
    product: BaseProduct | str = ""


@dataclass
class Plan:
    plan: dict[str, list[Room]]
    config: PlanConfig
    trigger: Optional[str] = None
    task: Optional[dict[str, list[str]]] = None
    trigger_timing: PlanTriggerTiming = PlanTriggerTiming.AFTER_PLANNING
    name: str = ""

    @staticmethod
    def set_timing_enum(value: Optional[str]) -> PlanTriggerTiming:
        try:
            return PlanTriggerTiming[value.upper()]
        except Exception:
            return PlanTriggerTiming.AFTER_PLANNING
