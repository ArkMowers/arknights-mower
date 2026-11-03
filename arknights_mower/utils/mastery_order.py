"""Order mastery plans by operator, separating shared assistants where possible."""

from .mastery_support_types import IGNORED_NAMES, decode_json


def mastery_groups(plans, levels):
    """Group trainable skills only when at least one already has mastery."""
    groups = {}
    for plan in plans:
        key = (plan["char_id"], plan["skill_index"])
        if plan.get("status") == "failed" or levels.get(key, 0) >= plan.get(
            "target_level", 3
        ):
            continue
        groups.setdefault(plan["char_id"], []).append(plan)
    return {
        cid: group
        for cid, group in groups.items()
        if len({p["skill_index"] for p in group}) > 1
        and any(levels.get((cid, p["skill_index"]), 0) >= 1 for p in group)
    }


def consecutive_mastery_plans(plans, levels):
    groups = mastery_groups(plans, levels)
    ordered, seen = [], set()
    active = [
        p
        for p in plans
        if p.get("status") in ("arranging", "training", "waiting_collect")
    ]
    for plan in active + plans:
        if plan["id"] in seen:
            continue
        group = groups.get(plan["char_id"], [plan])
        group = sorted(
            group,
            key=lambda p: (
                p.get("status") not in ("arranging", "training", "waiting_collect"),
                levels.get((p["char_id"], p["skill_index"]), 0),
            ),
        )
        for member in group:
            if member["id"] not in seen:
                ordered.append(member)
                seen.add(member["id"])
    return ordered


def _next_skill_plan(plan, plans=None):
    if plans is None:
        from .mastery_db import get_all_plans

        plans = get_all_plans()
    next_plan = next(
        (p for p in plans if p["id"] != plan["id"] and p.get("status") == "idle"), None
    )
    if not next_plan or next_plan["char_id"] != plan.get("char_id"):
        return None
    if next_plan["skill_index"] == plan.get("skill_index"):
        return None
    return next_plan


def basic_mastery_successor(plan, level, *, plans=None, levels=None):
    """A same-operator seven-to-one successor does not need reducer attendance."""
    if level != 3:
        return False
    next_plan = _next_skill_plan(plan, plans)
    if next_plan is None:
        return False
    if levels is None:
        from .mastery_recommendation import get_current_mastery_level

        current = get_current_mastery_level(
            next_plan["char_id"], next_plan["skill_index"]
        )
    else:
        current = levels.get((next_plan["char_id"], next_plan["skill_index"]))
    return current == 0


def halving_successor(plan, level, *, plans=None, levels=None):
    """Return the next same-trainee training that can consume halving."""
    if not isinstance(level, int) or level < 1:
        return None
    if level < plan["target_level"]:
        return plan
    next_plan = _next_skill_plan(plan, plans)
    if next_plan is None:
        return None
    if levels is None:
        from .mastery_recommendation import get_current_mastery_level

        current = get_current_mastery_level(
            next_plan["char_id"], next_plan["skill_index"]
        )
    else:
        current = levels.get((next_plan["char_id"], next_plan["skill_index"]))
    return (
        next_plan
        if current is not None and 1 <= current < next_plan["target_level"]
        else None
    )


def mastery_assistants(plan):
    """Read remaining assistant occupants from the saved and executing stages."""
    support = decode_json(plan.get("support_plan")) or {}
    runtime = decode_json(plan.get("support_runtime")) or {}
    if "carry_from_skill" in runtime:
        runtime = {}
    current = runtime.get("level", 1)
    target = plan.get("target_level", 3)
    stages = {
        stage["level"]: stage
        for stage in support.get("stages", [])
        if current <= stage["level"] <= target
    }
    if runtime and current <= target:
        stages[current] = {**stages.get(current, {}), **runtime}
    return frozenset(
        name
        for stage in stages.values()
        for field in ("operator", "swap_target", "working_operator")
        if (name := stage.get(field)) and name not in IGNORED_NAMES
    )


def interleave_mastery_plans(plans: list[dict]) -> list[dict]:
    active_groups: dict[str, list[dict]] = {}
    idle_groups: dict[str, list[dict]] = {}
    failed: list[dict] = []
    for plan in plans:
        status = plan["status"]
        if status == "failed":
            failed.append(plan)
            continue
        groups = idle_groups if status == "idle" else active_groups
        groups.setdefault(plan["char_id"], []).append(plan)

    def assistants(group):
        return frozenset().union(*(mastery_assistants(plan) for plan in group))

    ordered: list[dict] = []
    previous = frozenset()
    for char_id, group in active_groups.items():
        group = group + idle_groups.pop(char_id, [])
        ordered.extend(group)
        previous = assistants(group)

    queues: dict[frozenset, list[list[dict]]] = {}
    for group in idle_groups.values():
        queues.setdefault(assistants(group), []).append(group)

    while queues:
        # Prefer fewer shared assistants, then the largest remaining queue.
        # Insertion order preserves the first appearance when both counts tie.
        names = min(queues, key=lambda key: (len(key & previous), -len(queues[key])))
        ordered.extend(queues[names].pop(0))
        if not queues[names]:
            del queues[names]
        previous = names
    return ordered + failed
