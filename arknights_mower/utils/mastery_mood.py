"""Conservative assistant endurance for the current mastery stage."""

from collections import defaultdict

from .dorm_candidates import card_mood_estimate, dorm_candidate_mood
from .mastery_optimizer import stage_route
from .mastery_support_types import (
    BASE_HOURS,
    REDUCERS,
    StageSpec,
    SupportPlanError,
    swap_buffer_minutes,
)


class SupportMoodWait(SupportPlanError):
    def __init__(self, required, shortages):
        self.required = required
        self.shortages = shortages
        details = "、".join(
            f"{name}（需要 {required[name]:.2f}，"
            + ("心情未知）" if mood is None else f"当前约 {mood:.2f}）")
            for name, mood in shortages.items()
        )
        action = (
            "确认心情"
            if any(value is None for value in shortages.values())
            else "恢复心情"
        )
        super().__init__(f"等待专精协助干员{action}：{details}")


def support_mood_requirements(route, *, inherited=False):
    """Budget one stage at one mood per hour, without central speed."""
    required = defaultdict(float)
    first = {
        "name": route["operator"],
        "efficiency": route["efficiency"],
        "halves": route.get("first_halves", route["operator"] in REDUCERS),
    }
    swap = (
        {
            "name": route["swap_target"],
            "efficiency": route["swap_efficiency"],
            "halves": route.get("swap_halves", route["swap_target"] in REDUCERS),
        }
        if route.get("swap_target")
        else None
    )
    spec = StageSpec(
        route["level"],
        BASE_HOURS[route["level"]] * (0.5 if inherited else 1),
        central=0,
        buffer=swap_buffer_minutes(
            route["level"],
            route.get("configured_swap_buffer", route.get("mastery_swap_buffer")),
            central=route.get("central_bonus", 0),
            inherited=inherited,
        ),
        manual=route.get("manual", False),
    )
    projected = stage_route(first, swap, spec) or stage_route(first, None, spec)
    before_swap = projected["switch_after"]
    if before_swap is None:
        required[first["name"]] += projected["hours"]
    else:
        required[first["name"]] += before_swap
        last_hours = projected["hours"] - before_swap
        required[swap["name"]] += last_hours
    return dict(required)


def support_mood_shortages(op_data, required):
    shortages = {}
    for name, needed in required.items():
        mood = dorm_candidate_mood(op_data, name)
        if mood is None:
            mood = card_mood_estimate(op_data, name)
        if mood is None or mood + 1e-9 < needed:
            shortages[name] = mood
    return shortages


def require_support_mood(solver, route, *, inherited=False):
    required = support_mood_requirements(route, inherited=inherited)
    shortages = support_mood_shortages(solver.op_data, required)
    if shortages:
        raise SupportMoodWait(required, shortages)


def support_mood_context(plan_id, op_data):
    """Changes to the plan, successor or assistant policy require a fresh budget."""
    from . import config
    from .mastery_db import (
        get_all_plans,
        get_all_routes,
        get_plan_by_id,
        get_route_settings,
    )

    plan = get_plan_by_id(plan_id)
    return {
        "mood_scope": "current_stage_observation",
        "plan": {
            key: plan.get(key)
            for key in ("status", "target_level", "support_plan", "support_runtime")
        }
        if plan
        else None,
        "queue": [
            (p["id"], p["char_id"], p["skill_index"], p["target_level"], p["status"])
            for p in get_all_plans()
        ],
        "follow_schedule": config.conf.assistant_follows_schedule,
        "support_slot": tuple(
            sorted(
                name
                for name, op in op_data.operators.items()
                if op.current_room == "train" and op.current_index == 0
            )
        )
        if config.conf.assistant_follows_schedule
        else None,
        "routes": get_all_routes() if plan and not plan.get("support_plan") else None,
        "settings": get_route_settings()
        if plan and not plan.get("support_plan")
        else None,
    }
