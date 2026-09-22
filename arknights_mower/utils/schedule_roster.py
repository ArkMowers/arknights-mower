"""Check scheduled operators against the locally cached Skland roster."""

import json

from arknights_mower.utils.path import get_path

IGNORED_NAMES = frozenset({"", "Current", "Free"})


def validate_owned_operators(global_plan) -> str | None:
    """Return a precheck error only when a Skland roster cache exists."""
    path = get_path("@app/tmp/cultivate.json")
    if not path.exists():
        return None

    try:
        with path.open(encoding="utf-8") as file:
            payload = json.load(file)
        data = payload.get("data") if isinstance(payload, dict) else None
        characters = data.get("characters") if isinstance(data, dict) else None
        if (
            not isinstance(characters, list)
            or not characters
            or not all(
                isinstance(char, dict)
                and isinstance(char.get("id"), str)
                and char["id"]
                for char in characters
            )
        ):
            raise ValueError("invalid character roster")
    except (OSError, ValueError):
        return "森空岛干员数据缓存无效，请重新同步干员数据后验证排班"

    from arknights_mower.utils.mastery_recommendation import get_skill_data

    resources = get_skill_data()
    name_to_ids: dict[str, set[str]] = {}
    for section in ("characters", "training", "workshop"):
        entries = resources.get(section, {})
        if section != "characters":
            entries = entries.get("operators", {})
        for char_id, info in entries.items():
            name = info.get("name")
            if name:
                name_to_ids.setdefault(name, set()).add(char_id)

    scheduled = set()
    plans = [global_plan["default_plan"], *global_plan["backup_plans"]]
    for plan in plans:
        for room in plan.plan.values():
            for slot in room:
                scheduled.add(slot.agent)
                scheduled.update(slot.replacement)
    for plan in global_plan["backup_plans"]:
        for names in (plan.task or {}).values():
            scheduled.update(names)

    owned_ids = {char["id"] for char in characters}
    missing = sorted(
        name
        for name in scheduled - IGNORED_NAMES
        if name in name_to_ids and name_to_ids[name].isdisjoint(owned_ids)
    )
    if missing:
        return f"森空岛缓存中未持有以下排班干员：{'、'.join(missing)}"
    return None
