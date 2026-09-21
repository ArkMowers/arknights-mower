"""Shared types and JSON representation for mastery assistant plans."""

import json
from dataclasses import dataclass

BASE_HOURS = {1: 8, 2: 16, 3: 24}
DEFAULT_SWAP_BUFFER_MINUTES = 10
CENTRAL_SWAP_BUFFER_MINUTES = 15
UNHALVED_M2_SWAP_BUFFER_MINUTES = 30
DEFAULT_SWAP_BUFFERS = {
    "no_central": DEFAULT_SWAP_BUFFER_MINUTES,
    "central": CENTRAL_SWAP_BUFFER_MINUTES,
    "central_unhalved_m2": UNHALVED_M2_SWAP_BUFFER_MINUTES,
}
REDUCERS = ("逻各斯", "艾丽妮")
CONTROL_TRAINERS = frozenset(("阿斯卡纶", "烛煌", "斩业星熊"))
IGNORED_NAMES = frozenset(("", "Free", "Current"))


def swap_buffer_minutes(level, configured=None, *, central=0, inherited=False):
    """A full sixteen-hour M2 needs more margin for changes in central staffing."""
    if not central:
        key = "no_central"
    else:
        key = "central_unhalved_m2" if level == 2 and not inherited else "central"
    if isinstance(configured, dict):
        return configured.get(key, DEFAULT_SWAP_BUFFERS[key])
    return DEFAULT_SWAP_BUFFERS[key] if configured is None else configured


def configured_swap_buffer(settings):
    """Old saved numeric settings remain explicit user choices."""
    return settings.get(
        "mastery_swap_buffers",
        settings.get("mastery_swap_buffer", DEFAULT_SWAP_BUFFER_MINUTES),
    )


def route_swap_buffer(route, level=None):
    return swap_buffer_minutes(
        route.get("level") if level is None else level,
        route.get(
            "configured_swap_buffer",
            route.get("mastery_swap_buffer", DEFAULT_SWAP_BUFFER_MINUTES),
        ),
        central=route.get("central_bonus", 0),
        inherited=route.get("half_inherited", False),
    )


class SupportPlanError(ValueError):
    pass


class RosterUnavailableError(SupportPlanError):
    pass


@dataclass
class TrainingInputs:
    roster: list | None = None
    metadata: dict | None = None
    schedule: tuple | None = None
    buffer: int | dict | None = None


@dataclass(frozen=True)
class StageSpec:
    level: int
    work: float
    central: int = 0
    buffer: int | dict | None = None
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
    if stage and (
        stage.get("configured_swap_buffer", False) is None
        or isinstance(stage.get("configured_swap_buffer"), dict)
    ):
        stage["mastery_swap_buffer"] = max(1, route_swap_buffer(stage, level))
    return stage


def encode_supports(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None
