"""Prepare ordinary Copilot formations and battle actions for MaaCore."""

import json
import os
from functools import lru_cache
from pathlib import Path

from arknights_mower.utils import config
from arknights_mower.utils.maa_storage import storage_root
from arknights_mower.utils.path import resolve_config_path

# The script protocol uses English class names; MaaCore parses its resource keys.
_ROLE_ALIASES = {
    "guard": "warrior",
    "vanguard": "pioneer",
    "defender": "tank",
    "supporter": "support",
    "specialist": "special",
}


def _normalize_role(item):
    role = item.get("role", "")
    if not isinstance(role, str):
        return None
    role = role.casefold()
    if role in _ROLE_ALIASES:
        role = item["role"] = _ROLE_ALIASES[role]
    return role


def _index_skill_limits(chars):
    limits = {}
    for char_id, char in chars.items():
        limit = _skill_limit(char_id, char["rarity"])
        role = char.get("profession", "").casefold()
        names = {
            char[key].casefold()
            for key in ("name", "name_en", "name_jp", "name_kr", "name_tw")
            if char.get(key)
        }
        if char.get("name") == "阿米娅" and char_id != "char_002_amiya" and role:
            names.add(f"阿米娅-{role}")
        for name in names:
            for key in ((name, ""), (name, role)):
                # Forms sharing a name can have different skill limits.
                if limits.setdefault(key, limit) != limit:
                    limits[key] = None
    return limits


@lru_cache(maxsize=2)
def _battle_skill_limits(path, _file_version):
    return _index_skill_limits(json.loads(path.read_text("utf-8"))["chars"])


def _skill_limit(char_id, rarity):
    if char_id == "char_002_amiya" or rarity >= 6:
        return 3
    if rarity >= 4:
        return 2
    return int(rarity >= 3)


def battle_data_path(installation):
    target = Path(installation)
    cache = target / "cache"
    if os.environ.get("MOWER_ANDROID") != "1":
        shared_cache = storage_root(target) / "cache"
        # Before its first load, MaaCore's launcher migrates the installation cache here.
        if shared_cache.is_dir():
            cache = shared_cache
    relative = Path("resource/battle_data.json")
    override = cache / relative
    return override if override.is_file() else target / relative


def _operator_limits():
    path = battle_data_path(resolve_config_path(config.conf.maa_path))
    try:
        stat = path.stat()
    except FileNotFoundError:
        from arknights_mower.utils.growth import growth_data
        from arknights_mower.utils.mastery_recommendation import get_skill_data

        return _index_skill_limits(growth_data(get_skill_data())["characters"])
    return _battle_skill_limits(path, (stat.st_mtime_ns, stat.st_size, stat.st_ino))


def _require_name(item, field):
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"作业的 {field}.name 必须是非空字符串")
    return name


def _integer(item, key, default, field):
    value = item.get(key, default)
    if type(value) is not int:
        raise ValueError(f"作业的 {field}.{key} 必须是整数")
    return value


def _normalize_oper(oper, field, limits):
    name = _require_name(oper, field)
    skill = _integer(oper, "skill", 0, field)
    if not 0 <= skill <= 3:
        raise ValueError(f"作业的 {field}.skill 必须在 0 到 3 之间")
    limit = limits.get((name.casefold(), _normalize_role(oper)))
    if limit is not None and skill > limit:
        oper["skill"] = skill = 0
    requirements = oper.get("requirements")
    if requirements is None:
        requirements = {}
    if not isinstance(requirements, dict):
        raise ValueError(f"作业的 {field}.requirements 必须是对象")
    field += ".requirements"
    level = _integer(requirements, "skill_level", 0, field)
    elite = _integer(requirements, "elite", 0, field)
    module = _integer(requirements, "module", -1, field)
    if not -1 <= level <= 10 or not -1 <= elite <= 2:
        raise ValueError(f"作业的 {field} 要求技能等级 -1 到 10、精英化等级 -1 到 2")
    skill_elite = skill - 1 if limit is not None else -1
    level_elite = 2 if level > 7 else 1 if level > 4 else -1
    minimum = max(skill_elite, level_elite, 2 if module > 0 else -1)
    if elite < minimum:
        requirements["elite"] = minimum
        oper["requirements"] = requirements


def normalize_copilot(data):
    operators = [(f"opers[{i}]", oper) for i, oper in enumerate(data.get("opers", []))]
    for i, group in enumerate(data.get("groups", [])):
        field = f"groups[{i}]"
        _require_name(group, field)
        members = group.get("opers")
        if not isinstance(members, list) or not all(
            isinstance(op, dict) for op in members
        ):
            raise ValueError(f"作业的 {field}.opers 必须是对象列表")
        operators.extend((f"{field}.opers[{j}]", op) for j, op in enumerate(members))
    if operators:
        limits = _operator_limits()
        for field, oper in operators:
            _normalize_oper(oper, field, limits)

    for i, action in enumerate(data["actions"]):
        _normalize_role(action)
        kind = action.get("type")
        if kind not in ("Skill", "Retreat", "BulletTime", "SkillUsage", "Click"):
            continue
        for key, size in (("location", 2), ("rect", 4)):
            if key == "rect" and kind != "Click":
                continue
            coords = action.get(key)
            if coords is not None and (
                not isinstance(coords, list)
                or len(coords) != size
                or any(type(value) is not int for value in coords)
            ):
                raise ValueError(f"作业的 actions[{i}].{key} 必须包含 {size} 个整数")
        if kind == "Click":
            if action.get("rect") is not None:
                if min(action["rect"][2:]) <= 0:
                    raise ValueError(f"作业的 actions[{i}].rect 宽度和高度必须大于 0")
                action.pop("location", None)
            elif action.get("location") is None:
                raise ValueError(f"作业的 actions[{i}] 点击动作需要 rect 或 location")
            else:
                action.pop("rect", None)
        elif action.get("location") is not None and action.get("name") is not None:
            del action["name"]
            action.pop("role", None)
        elif action.get("location") is None:
            action.pop("location", None)
