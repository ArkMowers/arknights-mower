"""Owned-operator growth goals, shared prerequisite costs and observed statistics."""

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from threading import RLock
from time import time

from arknights_mower.utils.config import atomic_write
from arknights_mower.utils.path import get_path

_lock = RLock()
METRICS = ("max_level", "module_level", "elite2", "modules", "masteries")
LEVEL_GOALS = frozenset(
    {"elite1", "level_max", "elite2", "elite2_module", "elite2_max"}
)


@lru_cache(maxsize=1)
def _bundled_growth():
    return json.loads(
        (Path(__file__).parents[1] / "data/skill_data.json").read_text("utf-8")
    ).get("growth", {})


def growth_data(skills):
    # Existing resource packs can predate growth costs; keep the bundled catalog.
    return skills.get("growth") or _bundled_growth()


def growth_resources(skills):
    return {
        **skills,
        "items": {
            **skills.get("items", {}),
            "4001": {"name": "龙门币", "rarity": 1},
            "4006": {"name": "采购凭证", "rarity": 1},
            "growth_exp": {"name": "作战记录经验", "rarity": 1},
        },
    }


def inventory_counts(box, skills, *, local=False):
    stock = {item["id"]: int(item.get("count", 0)) for item in box.get("items", [])}
    if local:
        from arknights_mower.solvers.record import get_inventory_counts

        counts = get_inventory_counts()
        for iid, info in skills.get("items", {}).items():
            if info["name"] in counts:
                stock[iid] = counts[info["name"]]
    stock["growth_exp"] = sum(
        stock.get(iid, 0) * amount
        for iid, amount in (
            ("2001", 200),
            ("2002", 400),
            ("2003", 1000),
            ("2004", 2000),
        )
    )
    return stock


def expand_chip_costs(materials, inventory):
    """Show manual dual-chip production and catalyst exchange beside final costs."""
    demand = Counter()
    for material in materials:
        demand[material["id"]] += material["count"]
    for prefix in range(321, 329):
        dual, group = f"{prefix}3", f"{prefix}2"
        missing = max(0, demand[dual] - inventory.get(dual, 0))
        if missing:
            demand[group] += 2 * missing
            demand["32001"] += missing
    if demand["32001"]:
        demand["4006"] += 90 * max(0, demand["32001"] - inventory.get("32001", 0))
    return [{"id": iid, "count": count} for iid, count in demand.items() if count > 0]


def calculate_growth_materials(budget, materials):
    from arknights_mower.utils.growth_workshop import calculate_crafting_materials

    summary = calculate_crafting_materials(
        budget, expand_chip_costs(materials, budget.inventory)
    )
    rows = {row["id"]: row for row in summary["materials"]}
    catalyst = rows.get("32001")
    vouchers = rows.get("4006")
    if catalyst and catalyst["owned"] < catalyst["required"]:
        catalyst["craftable"] = bool(
            vouchers and vouchers["owned"] >= vouchers["required"]
        )
    for prefix in range(321, 329):
        dual = rows.get(f"{prefix}3")
        group = rows.get(f"{prefix}2")
        if dual and dual["owned"] < dual["required"]:
            # Expanded totals reserve shared catalysts, vouchers and chip groups
            # once. Preview readiness never creates inventory or workshop recipes.
            dual["craftable"] = bool(
                group
                and group["owned"] >= group["required"]
                and catalyst
                and catalyst["craftable"]
            )
    summary["missing"] = [
        row
        for row in summary["missing"]
        if not (row["id"] in rows and rows[row["id"]]["craftable"])
    ]
    summary["craftable"] = not summary["missing"]
    summary["manual_chips"] = any(
        row["id"].startswith("32") for row in summary["materials"]
    )
    return summary


def promotion_materials(char, definition, data, target=(2, 1)):
    phase, level = char.get("evolvePhase", 0), char.get("level", 1)
    target_phase, target_level = target
    if (phase, level) >= target:
        return []
    phases = definition.get("phases", [])
    if len(phases) <= target_phase:
        raise ValueError("缺少干员精英化材料数据，请更新资源")
    materials = []
    gold, experience = 0, 0
    for current in range(phase, target_phase + 1):
        start = level if current == phase else 1
        end = target_level if current == target_phase else phases[current]["max_level"]
        experience += sum(data["experience"][current][start - 1 : end - 1])
        gold += sum(data["level_gold"][current][start - 1 : end - 1])
        if current < target_phase:
            materials.extend(phases[current + 1]["materials"])
            gold += data["promotion_gold"][definition["rarity"] - 1][current]
    if gold:
        materials.append({"id": "4001", "count": gold})
    if experience:
        materials.append({"id": "growth_exp", "count": experience})
    return materials


def basic_skill_materials(char, definition):
    level = char.get("mainSkillLevel")
    if type(level) is not int or not 1 <= level <= 7:
        raise ValueError("无法确认基础技能等级，请同步干员数据")
    if level == 7:
        return []
    levels = definition.get("basic_skills", [])
    if len(levels) < 6:
        raise ValueError("缺少基础技能升级材料，请更新资源")
    return [material for costs in levels[level - 1 : 6] for material in costs]


def basic_skill_target(definition):
    if len(definition.get("basic_skills", [])) < 6:
        raise ValueError("该干员不支持基础技能 7 级养成")
    # Older resource packs contain costs only; basic level 7 requires elite 1.
    requirements = definition.get("basic_skill_requirements") or [
        {"elite": 1, "level": 1}
    ]
    return max((entry["elite"], entry["level"]) for entry in requirements[:6])


def level_goal_targets(definition):
    phases = definition.get("phases", [])
    if len(phases) >= 3:
        targets = {
            "elite2": (2, 1),
            "elite2_max": (2, phases[2]["max_level"]),
        }
        module_level = {6: 60, 5: 50, 4: 40}.get(definition.get("rarity"))
        if module_level:
            targets["elite2_module"] = (2, module_level)
        return targets
    if len(phases) == 2:
        return {"elite1": (1, 1), "level_max": (1, phases[1]["max_level"])}
    if phases:
        return {"level_max": (0, phases[0]["max_level"])}
    return {}


def available_modules(char_id, char, data):
    owned = {entry["id"]: entry.get("level", 0) for entry in char.get("equips", [])}
    return [
        {**module, "current_level": owned.get(module["id"], 0)}
        for module in data.get("characters", {}).get(char_id, {}).get("modules", [])
        if module.get("release_at", 0) <= time()
    ]


def module_materials(module, target_level=None):
    levels = module.get("levels") or [{"level": 1, "materials": module["materials"]}]
    maximum = max(entry["level"] for entry in levels)
    target = maximum if target_level is None else target_level
    if type(target) is not int or not 1 <= target <= maximum:
        raise ValueError("目标模组等级无效")
    current = module.get("current_level", 0)
    return [
        material
        for entry in levels
        if current < entry["level"] <= target
        for material in entry["materials"]
    ]


def load_goals():
    path = get_path("@app/tmp/growth_plan.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text("utf-8"))
    if not isinstance(data, list):
        raise ValueError("养成计划文件格式错误")
    return data


def set_goal(char_id, module_id, selected, box, skills, target_level=None):
    if (
        type(selected) is not bool
        or not isinstance(char_id, str)
        or not isinstance(module_id, str)
    ):
        raise ValueError("养成目标格式错误")
    char = next((c for c in box.get("characters", []) if c["id"] == char_id), None)
    if char is None:
        raise ValueError("干员不在已拥有列表，请同步干员数据")
    data = growth_data(skills)
    definition = data.get("characters", {}).get(char_id, {})
    if module_id in LEVEL_GOALS:
        if module_id not in level_goal_targets(definition):
            raise ValueError("该干员不支持此等级目标")
    elif module_id == "skill7":
        basic_skill_target(definition)
        if selected:
            basic_skill_materials(char, definition)
    elif module_id not in {m["id"] for m in available_modules(char_id, char, data)}:
        raise ValueError("该干员没有此模组")
    goal = {"char_id": char_id, "module_id": module_id}
    if module_id not in LEVEL_GOALS | {"skill7"} and selected:
        module = next(
            m for m in available_modules(char_id, char, data) if m["id"] == module_id
        )
        module_materials(module, target_level)
        goal["target_level"] = (
            target_level
            if target_level is not None
            else max((entry["level"] for entry in module.get("levels", [])), default=1)
        )
        if goal["target_level"] <= module["current_level"]:
            raise ValueError("模组已达到所选等级")
    with _lock:
        levels = LEVEL_GOALS
        goals = [
            g
            for g in load_goals()
            if not (g["char_id"] == char_id and g["module_id"] == module_id)
            and not (
                selected
                and module_id in levels
                and g["char_id"] == char_id
                and g["module_id"] in levels
            )
        ]
        if selected:
            goals.append(goal)
        atomic_write(
            get_path("@app/tmp/growth_plan.json"),
            lambda f: json.dump(goals, f, ensure_ascii=False),
        )
    return goals


def material_entries(box, skills, plans, goals=(), *, separate_prerequisites=False):
    """One prerequisite per operator; all skills and modules share that cost."""
    data = growth_data(skills)
    chars = {c["id"]: c for c in box.get("characters", [])}
    groups = {}
    for plan in plans:
        groups.setdefault(plan["char_id"], {"plans": [], "goals": []})["plans"].append(
            plan
        )
    for goal in goals:
        groups.setdefault(goal["char_id"], {"plans": [], "goals": []})["goals"].append(
            goal
        )
    entries = []
    for cid, group in groups.items():
        char = chars.get(cid)
        if char is None:
            raise ValueError("部分计划缺少干员数据，请同步干员数据")
        definition = data.get("characters", {}).get(cid, {})
        target = (char.get("evolvePhase", 0), char.get("level", 1))
        materials = []
        prerequisites = []
        has_skill = False
        for plan in group["plans"]:
            index = plan["skill_index"]
            definitions = skills.get("characters", {}).get(cid, {}).get("skills", [])
            if type(index) is not int or not 0 <= index < len(definitions):
                raise ValueError("部分计划缺少技能数据，请更新资源")
            status = char.get("skills", [])
            current = (status[index].get("level") or 0) if index < len(status) else 0
            runtime = plan.get("support_runtime") or {}
            if isinstance(runtime, str):
                runtime = json.loads(runtime)
            if plan.get("status") in ("training", "waiting_collect"):
                current = max(current, runtime.get("level") or current + 1)
            goal_level = plan.get("target_level", 3)
            if type(goal_level) is not int or goal_level not in (1, 2, 3):
                raise ValueError("目标专精等级无效")
            if current >= goal_level:
                continue
            has_skill = True
            for level in definitions[index].get("levels", [])[current:goal_level]:
                materials.extend(level.get("materials", []))
        if has_skill:
            target = max(target, (2, 1))
        needs_basic = has_skill
        modules = {m["id"]: m for m in available_modules(cid, char, data)}
        for goal in group["goals"]:
            mid = goal["module_id"]
            if mid in LEVEL_GOALS:
                goal_target = level_goal_targets(definition).get(mid)
                if goal_target is None:
                    raise ValueError("该干员不支持此等级目标")
                target = max(target, goal_target)
                continue
            if mid == "skill7":
                basic_skill_target(definition)
                needs_basic = True
                continue
            module = modules.get(mid)
            if module is None:
                raise ValueError("部分计划缺少模组数据，请更新资源")
            costs = module_materials(module, goal.get("target_level"))
            if costs:
                target = max(target, (module["elite"], module["level"]))
                materials.extend(costs)
        if needs_basic:
            basic = basic_skill_materials(char, definition)
            if basic:
                target = max(target, basic_skill_target(definition))
                prerequisites.extend(basic)
        prerequisites.extend(promotion_materials(char, definition, data, target))
        if separate_prerequisites:
            entries.append((cid, prerequisites, materials))
        else:
            entries.append((cid, materials + prerequisites))
    return entries


def statistics(chars, skills):
    from arknights_mower.utils.growth_value import consumed_statistics

    definitions = growth_data(skills).get("characters", {})
    result = {str(r): dict.fromkeys(METRICS, 0) for r in range(6, 0, -1)}
    for char in chars:
        definition = definitions.get(char["id"], {})
        rarity = definition.get("rarity")
        if rarity not in range(1, 7):
            continue
        row = result[str(rarity)]
        elite2 = char.get("evolvePhase") == 2
        row["elite2"] += elite2
        phases = definition.get("phases", [])
        row["max_level"] += bool(phases) and (
            char.get("evolvePhase") == len(phases) - 1
            and char.get("level", 0) >= phases[-1]["max_level"]
        )
        row["module_level"] += elite2 and char.get("level", 0) >= {
            6: 60,
            5: 50,
            4: 40,
        }.get(rarity, float("inf"))
        valid_modules = {m["id"] for m in definition.get("modules", [])}
        row["modules"] += len(
            {
                e["id"]
                for e in char.get("equips", [])
                if e.get("level", 0) > 0 and e["id"] in valid_modules
            }
        )
        row["masteries"] += sum(s.get("level") == 3 for s in char.get("skills", []))
    for rarity, values in consumed_statistics(
        chars, skills, growth_data(skills)
    ).items():
        result[rarity].update(values)
    return result


def save_statistics(payload, path, observed_at, skills):
    """Record actual sync observations only, never backfill invented history."""
    row = {
        "time": observed_at,
        "rarities": statistics(payload["data"]["characters"], skills),
    }
    with _lock:
        history = json.loads(path.read_text("utf-8")) if path.exists() else []
        history = [entry for entry in history if entry["time"] != observed_at]
        history.append(row)
        history.sort(key=lambda entry: entry["time"])
        atomic_write(path, lambda f: json.dump(history[-3000:], f, ensure_ascii=False))


def statistics_history():
    path = get_path("@app/tmp/growth_history.json")
    try:
        return json.loads(path.read_text("utf-8"))[-3000:] if path.exists() else []
    except (OSError, ValueError, TypeError):
        return []
