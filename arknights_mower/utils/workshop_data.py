"""Validate cached/synchronized BOX data and read unlocked workshop skills."""

import json
from functools import lru_cache


class WorkshopRecommendationError(ValueError):
    pass


def parse_roster(payload):
    """Reject unusable BOX payloads before caching or replacing the previous file."""
    if not isinstance(payload, dict) or payload.get("code", 0) != 0:
        raise ValueError("森空岛返回的干员数据无效")
    data = payload.get("data")
    roster = data.get("characters") if isinstance(data, dict) else None
    if not isinstance(roster, list) or not roster:
        raise ValueError("干员数据为空或无效，请重新同步干员数据")
    if not all(_valid_character(char) for char in roster):
        raise ValueError("干员数据格式不完整，请重新同步干员数据")
    return roster


def _valid_character(char):
    if not isinstance(char, dict) or not isinstance(char.get("id"), str):
        return False
    progress = (char.get("evolvePhase", 0), char.get("level", 1))
    return bool(char["id"].strip()) and all(
        type(value) is int and value >= 0 for value in progress
    )


@lru_cache(maxsize=2)
def _read_roster(path, mtime, size):
    with open(path, encoding="utf-8") as f:
        return parse_roster(json.load(f))


def owned_roster():
    from arknights_mower.utils.path import get_path

    path = get_path("@app/tmp/cultivate.json")
    try:
        stat = path.stat()
        return _read_roster(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError):
        raise WorkshopRecommendationError(
            "请先同步干员数据，再使用加工站一键设置"
        ) from None


def operator_metadata(metadata=None):
    if metadata is not None:
        return metadata
    from arknights_mower.utils.mastery_recommendation import get_skill_data

    data = get_skill_data().get("workshop", {})
    if data.get("version") != 1 or not isinstance(data.get("operators"), dict):
        raise WorkshopRecommendationError("当前资源缺少加工站技能规则，请更新资源包")
    return data["operators"]


def fully_unlocked_operators(metadata=None):
    """Read each operator's final skill upgrades without consulting the user's BOX."""
    result = {}
    for meta in operator_metadata(metadata).values():
        elite, level = max(
            ((v["elite"], v["level"]) for group in meta["groups"] for v in group),
            default=(0, 1),
        )
        result[meta["name"]] = unlocked(meta, {"evolvePhase": elite, "level": level})
    return result


def unlocked(meta, char):
    progress = (char.get("evolvePhase", 0), char.get("level", 1))
    effects = []
    for group in meta.get("groups", []):
        versions = [v for v in group if (v["elite"], v["level"]) <= progress]
        if versions:
            effects.extend(
                max(versions, key=lambda v: (v["elite"], v["level"]))["effects"]
            )
    return effects


def scheduled_operators(plan=None):
    """Block primary/replacement staff in every plan, except dorms and workshop."""
    if plan is None:
        from arknights_mower.utils import config

        plan = getattr(config, "plan", {})
    if hasattr(plan, "model_dump"):
        plan = plan.model_dump(exclude_none=True)
    base = plan.get(plan.get("default", "plan1"), {})
    blocked = {}
    for table in [base, *(p.get("plan", {}) for p in plan.get("backup_plans", []))]:
        for room, facility in table.items():
            if room == "factory" or room.startswith("dormitory_") or not facility:
                continue
            for slot in facility.get("plans", []):
                for name in [slot.get("agent", ""), *slot.get("replacement", [])]:
                    if name and name not in {"Free", "Current"}:
                        blocked.setdefault(name, set()).add(room)
    return {name: sorted(rooms) for name, rooms in blocked.items()}
