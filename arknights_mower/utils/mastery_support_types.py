"""Shared types and JSON representation for mastery assistant plans."""

import json
from dataclasses import dataclass

BASE_HOURS = {1: 8, 2: 16, 3: 24}
REDUCERS = ("逻各斯", "艾丽妮")
CONTROL_TRAINERS = frozenset(("阿斯卡纶", "烛煌", "斩业星熊"))
IGNORED_NAMES = frozenset(("", "Free", "Current"))


class SupportPlanError(ValueError):
    pass


class RosterUnavailableError(SupportPlanError):
    pass


@dataclass
class TrainingInputs:
    roster: list | None = None
    metadata: dict | None = None
    schedule: tuple | None = None
    buffer: int = 10


@dataclass(frozen=True)
class StageSpec:
    level: int
    work: float
    central: int = 0
    buffer: int = 10
    manual: bool = False


def decode_json(value):
    if isinstance(value, str) and value:
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            raise SupportPlanError("协助方案数据损坏，请重新添加计划") from None
    return value


def decode_supports(plan):
    return decode_json(plan.get("support_plan"))


def editable_after(plan):
    if plan.get("status") in ("idle", "failed"):
        return 0
    runtime = decode_json(plan.get("support_runtime")) or {}
    return runtime.get("level", plan["target_level"])


def stage_for(plan, level):
    value = decode_supports(plan)
    stage = next(
        (dict(s) for s in (value or {}).get("stages", []) if s["level"] == level), None
    )
    runtime = decode_json(plan.get("support_runtime"))
    if stage and runtime and runtime.get("level") == level:
        stage.update(runtime)
    return stage


def encode_supports(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None
