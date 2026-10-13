"""Read building-skill unlocks from the shared automatic-mastery BOX snapshot."""

import json
import re
from functools import lru_cache
from pathlib import Path

from arknights_mower import __rootdir__
from arknights_mower.utils.mastery_recommendation import get_cultivate_snapshot
from arknights_mower.utils.res_version import BUILDING_SKILL_DATA
from arknights_mower.utils.resource_pkg import (
    register_resource_reload,
    resource_pkg_path,
    resource_ui_path,
)
from arknights_mower.utils.schedule_roster import _operator_ids_by_name


@lru_cache(maxsize=1)
def skill_supplement():
    path = Path(__rootdir__) / "data" / "riic" / "supplement.json"
    return json.loads(path.read_text("utf-8"))


@lru_cache(maxsize=1)
def skill_index():
    path = resource_pkg_path(BUILDING_SKILL_DATA)
    catalog = {
        a["name"]: a.get("child_skill", []) for a in json.loads(path.read_text("utf-8"))
    }
    for operator in skill_supplement():
        catalog.setdefault(operator["name"], operator["child_skill"])
    return catalog


@lru_cache(maxsize=1)
def term_index():
    relative = "pages/basement_skill/buffer.json"
    path = resource_ui_path(relative, source=True)
    if path is None:
        path = Path(__rootdir__).parent / "ui" / "src" / relative
    return {
        term["termId"]: term for term in json.loads(path.read_text("utf-8")).values()
    }


@register_resource_reload
def clear_building_skills():
    skill_index.cache_clear()
    skill_supplement.cache_clear()
    term_index.cache_clear()


def _requirement(skill):
    match = re.fullmatch(r"精([0-2])\s+(\d+)级", skill.get("phase_level", ""))
    return (int(match[1]), int(match[2])) if match else None


def _operator_skills(name, progress):
    catalog = skill_index().get(name, ())
    active = {}
    if progress is not None:
        for skill in catalog:
            requirement = _requirement(skill)
            if requirement is not None and requirement <= progress:
                key = skill["skill_key"]
                version = (*requirement, skill["skill_level"])
                if key not in active or version > active[key][0]:
                    active[key] = (version, skill)
    result = []
    for skill in catalog:
        requirement = _requirement(skill)
        if progress is None or requirement is None:
            status = "unknown"
        elif requirement > progress:
            status = "locked"
        elif active[skill["skill_key"]][1] is skill:
            status = "active"
        else:
            status = "replaced"
        result.append(
            {
                "skill_key": skill["skill_key"],
                "skill_level": skill["skill_level"],
                "status": status,
            }
        )
    return result


def parse_base_conditions(building):
    """Extract available facility conditions; absent or invalid fields stay absent."""
    if not isinstance(building, dict):
        return {}
    result = {}
    for field, aliases, maximum in (
        ("trade", ("tradings", "trading"), 5),
        ("factories", ("manufactures", "manufacture"), 5),
        ("power", ("powers", "power"), 3),
    ):
        entries = next((building[key] for key in aliases if key in building), None)
        if (
            isinstance(entries, list)
            and len(entries) <= 9
            and all(
                isinstance(entry, dict)
                and type(entry.get("level")) is int
                and 0 <= entry["level"] <= 3
                for entry in entries
            )
        ):
            count = sum(entry["level"] > 0 for entry in entries)
            if count <= maximum:
                result[field] = count
    for key, field in (("hire", "recruits"), ("meeting", "reception")):
        facility = building.get(key)
        level = facility.get("level") if isinstance(facility, dict) else None
        if type(level) is int and 1 <= level <= 3:
            result[field] = level - 1 if field == "recruits" else level
    dormitories = building.get("dormitories")
    if isinstance(dormitories, list):
        levels = [
            room["level"]
            for room in dormitories
            if isinstance(room, dict)
            and type(room.get("level")) is int
            and 1 <= room["level"] <= 5
        ]
        if levels:
            result["dormLevel"] = max(levels)
    return result


def load_skill_snapshot():
    """Reuse the mastery snapshot without fetching data or assuming missing growth."""
    unavailable = {
        "has_data": False,
        "operators": [],
        "base_conditions": {},
        "message": "请同步森空岛干员数据",
    }
    payload = get_cultivate_snapshot()
    if not payload:
        return unavailable
    roster = {entry["id"]: entry for entry in payload["data"]["characters"]}
    try:
        name_to_ids = _operator_ids_by_name()
    except (OSError, ValueError, TypeError):
        return unavailable
    operators = []
    supplemental_ids = {a["name"]: [a["id"]] for a in skill_supplement()}
    for name in skill_index():
        ids = name_to_ids.get(name) or supplemental_ids.get(name)
        owned = [roster[cid] for cid in ids or () if cid in roster]
        progress = None
        # 同名形态共用基建技能目录，任一有效形态的练度均可证明解锁。
        for character in owned:
            phase, level = character.get("evolvePhase"), character.get("level")
            if (
                type(phase) is int
                and phase in (0, 1, 2)
                and type(level) is int
                and level > 0
            ):
                progress = max(progress or (0, 0), (phase, level))
        skills = _operator_skills(name, progress)
        operators.append(
            {
                "name": name,
                "owned": bool(owned) if ids else None,
                "phase": progress[0] if progress else None,
                "level": progress[1] if progress else None,
                "active_skills": [
                    {"skill_key": s["skill_key"], "skill_level": s["skill_level"]}
                    for s in skills
                    if s["status"] == "active"
                ],
                "skills": skills,
            }
        )
    conditions = payload.get("_mower_base_conditions")
    if not isinstance(conditions, dict):
        conditions = parse_base_conditions(payload.get("data", {}).get("building"))
    return {
        "has_data": True,
        "operators": operators,
        "base_conditions": conditions,
        "message": "使用已同步的森空岛练度",
    }


def owned_operator(name, snapshot):
    if not snapshot.get("has_data"):
        return None
    return next((a["owned"] for a in snapshot["operators"] if a["name"] == name), None)


def unlocked_skills(name, facility, snapshot):
    """Return current skill versions, or None when growth cannot be confirmed."""
    if not snapshot.get("has_data"):
        return None
    operator = next((a for a in snapshot["operators"] if a["name"] == name), None)
    if operator is None or operator["owned"] is None:
        return None
    if operator["owned"] is False:
        return ()
    if operator["phase"] is None or operator["level"] is None:
        return None
    active = {(s["skill_key"], s["skill_level"]) for s in operator["active_skills"]}
    return tuple(
        s
        for s in skill_index().get(name, ())
        if s["roomType"] == facility and (s["skill_key"], s["skill_level"]) in active
    )
