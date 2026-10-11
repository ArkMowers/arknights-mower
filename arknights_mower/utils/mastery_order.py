"""Order mastery plans by operator, alternating professions where possible."""


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


def halving_successor(plan, level, *, plans=None, levels=None):
    """Return the next same-trainee training that can consume halving."""
    if not isinstance(level, int) or level < 1:
        return None
    if level < plan["target_level"]:
        return plan
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


def interleave_mastery_plans(
    plans: list[dict], professions: dict[str, str]
) -> list[dict]:
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

    ordered: list[dict] = []
    previous = None
    for char_id, group in active_groups.items():
        ordered.extend(group)
        ordered.extend(idle_groups.pop(char_id, []))
        previous = professions.get(char_id) or "unknown"

    queues: dict[str, list[list[dict]]] = {}
    for char_id, group in idle_groups.items():
        profession = professions.get(char_id) or "unknown"
        queues.setdefault(profession, []).append(group)

    while queues:
        candidates = [key for key in queues if key != previous] or list(queues)
        # max keeps the first-seen profession when remaining group counts tie.
        profession = max(candidates, key=lambda key: len(queues[key]))
        ordered.extend(queues[profession].pop(0))
        if not queues[profession]:
            del queues[profession]
        previous = profession
    return ordered + failed
