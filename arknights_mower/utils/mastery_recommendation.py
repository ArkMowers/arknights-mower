import json
import os
from functools import lru_cache
from typing import Optional

from arknights_mower.utils.path import _install_dir, _internal_dir, get_path
from arknights_mower.utils.resource_pkg import (
    register_resource_reload,
    resource_pkg_path,
)
from arknights_mower.utils.skill_label import format_skill_label
from arknights_mower.utils.workshop_data import parse_roster

# 肉鸽赠送干员不支持训练室专精，即使 BOX 包含精二和技能数据。
UNTRAINABLE_CHAR_IDS = frozenset({"char_4195_radian", "char_4230_mcnist"})


def _find_skill_data():
    candidates = [
        resource_pkg_path("arknights_mower/data/skill_data.json"),
        _internal_dir / "arknights_mower" / "data" / "skill_data.json",
        _install_dir / "arknights_mower" / "data" / "skill_data.json",
        _install_dir / "data" / "skill_data.json",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


_skill_data_cache = None


def _load_skill_data():
    path = _find_skill_data()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("专精推荐资源格式错误")
        return data
    return {}


def get_skill_data():
    global _skill_data_cache
    if _skill_data_cache is None:
        _skill_data_cache = _load_skill_data()
    return _skill_data_cache


@register_resource_reload
def reload_resource_data() -> None:
    global _skill_data_cache
    new_data = _load_skill_data()
    if _skill_data_cache is None:
        _skill_data_cache = new_data
    else:
        _skill_data_cache.clear()
        _skill_data_cache.update(new_data)


def get_skill_real_name(char_id: str, skill_index: int):
    """从 skill_data.json 取干员技能的显示真名（如 飞翔瞪射）；查不到返回 None。

    skill_data.json 由 auto_get_res_new.py 生成并并入真名。
    """
    try:
        skills = (
            get_skill_data().get("characters", {}).get(char_id, {}).get("skills", [])
        )
        if 0 <= skill_index < len(skills):
            name = skills[skill_index].get("name")
            if name:
                return name
    except Exception:
        pass
    return None


@lru_cache(maxsize=2)
def _read_cultivate_characters(path, mtime_ns, size):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {char["id"]: char for char in parse_roster(data)}


def get_cultivate_characters():
    """专精和基建技能共用 BOX 缓存，同步文件变化后自动失效。"""
    path = get_path("@app/tmp/cultivate.json")
    try:
        stat = os.stat(path)
        return _read_cultivate_characters(str(path), stat.st_mtime_ns, stat.st_size)
    except Exception:
        return None


def _get_cultivate_character(char_id):
    return (get_cultivate_characters() or {}).get(char_id)


def get_current_mastery_level(char_id: str, skill_index: int) -> Optional[int]:
    """读取 skills[i].level（专精 0～3），不是基础技能等级；缺失时返回 None。"""
    char = _get_cultivate_character(char_id)
    if char is None:
        return None
    skills = char.get("skills", [])
    if not 0 <= skill_index < len(skills):
        return None
    level = skills[skill_index].get("level")
    return level if type(level) is int else None


def _mastery_requirement_error(char):
    if char.get("evolvePhase", 2) < 2:
        return (
            "尚未精二，可规划养成材料；精二且基础技能升至 7 级后，"
            "请前往「养成规划」页面手动点击「刷新」后再执行专精"
        )
    level = char.get("mainSkillLevel")
    if type(level) is not int or level < 1:
        return "无法确认基础技能等级，请前往「养成规划」页面手动点击「刷新」"
    if level < 7:
        return (
            f"基础技能仅 {level} 级，可加入养成计划；升至 7 级后，"
            "请前往「养成规划」页面手动点击「刷新」后再执行专精"
        )
    return None


def get_mastery_requirement_error(char_id):
    """校验已有 BOX 中的真实基础技能等级；未读取 BOX 的旧手动入口保持兼容。"""
    char = _get_cultivate_character(char_id)
    return _mastery_requirement_error(char) if char is not None else None


def get_mastery_recommendations():
    from arknights_mower.data import workshop_formula
    from arknights_mower.utils.growth import (
        available_modules,
        basic_skill_materials,
        basic_skill_target,
        calculate_growth_materials,
        growth_data,
        growth_resources,
        inventory_counts,
        level_goal_targets,
        load_goals,
        module_materials,
        promotion_materials,
        statistics,
        statistics_history,
    )
    from arknights_mower.utils.mastery_materials import MaterialBudget
    from arknights_mower.utils.operator_statistics import personal_statistics
    from arknights_mower.utils.workshop_material_policy import (
        protected_workshop_materials,
    )

    result = {"operators": [], "has_data": False, "error": None}
    try:
        with open(get_path("@app/tmp/cultivate.json"), encoding="utf-8") as stream:
            box = json.load(stream)["data"]
        if not box.get("characters"):
            raise ValueError("未找到干员数据")
        skills = growth_resources(get_skill_data())
        growth = growth_data(skills)
        budget = MaterialBudget(
            skills,
            inventory_counts(box, skills, local=True),
            workshop_formula,
            blocked_materials=protected_workshop_materials(),
        )
        result["goals"] = load_goals()
        result["statistics"] = statistics(box["characters"], skills)
        result["personal_statistics"] = personal_statistics(box["characters"], skills)
        result["history"] = statistics_history()
    except (OSError, ValueError, KeyError) as exc:
        result["error"] = f"请从森空岛同步干员数据：{exc}"
        return result

    for char in box["characters"]:
        cid = char["id"]
        definition = skills.get("characters", {}).get(cid, {})
        growth_def = growth.get("characters", {}).get(cid, {})
        modules = available_modules(cid, char, growth)
        if cid in UNTRAINABLE_CHAR_IDS or (
            not definition and not growth_def and not modules
        ):
            continue
        info = {**growth_def, **definition}
        prerequisite, material_error = [], None
        basic_summary = None
        supports_basic_skill7 = len(growth_def.get("basic_skills", [])) >= 6
        basic_prerequisite = None
        if supports_basic_skill7:
            required_phase, required_level = basic_skill_target(growth_def)
            basic_prerequisite = {"elite": required_phase, "level": required_level}
            try:
                basic = basic_skill_materials(char, growth_def)
                prerequisite += basic
                if basic:
                    basic_summary = calculate_growth_materials(budget, basic)
            except ValueError as exc:
                material_error = str(exc)
        if definition:
            try:
                prerequisite += promotion_materials(char, growth_def, growth)
            except ValueError as exc:
                material_error = str(exc)
        recommendations = []
        for index, skill in enumerate(definition.get("skills", [])):
            statuses = char.get("skills", [])
            current = (
                (statuses[index].get("level") or 0) if index < len(statuses) else 0
            )
            if current >= 3 or not skill.get("levels"):
                continue
            stages = []
            for level, costs in enumerate(skill["levels"][current:3], current + 1):
                materials = [
                    {
                        **mat,
                        "name": skills["items"]
                        .get(mat["id"], {})
                        .get("name", mat["id"]),
                    }
                    for mat in costs.get("materials", [])
                ]
                stages.append(
                    {
                        "from_level": level + 6,
                        "to_level": level + 7,
                        "lvl_up_time": costs.get("time", 0),
                        "needed_materials": materials,
                    }
                )
            targets = {}
            for target in range(current + 1, 4):
                selected = [s for s in stages if s["to_level"] - 7 <= target]
                materials = [m for stage in selected for m in stage["needed_materials"]]
                summary = (
                    None
                    if material_error
                    else calculate_growth_materials(budget, prerequisite + materials)
                )
                targets[str(target)] = {
                    "target_level": target,
                    "remaining_levels": target - current,
                    "total_time": sum(s["lvl_up_time"] for s in selected),
                    "chain_needed_materials": materials,
                    "material_summary": summary,
                    "skill_material_summary": calculate_growth_materials(
                        budget, materials
                    ),
                    "full_chain_achievable": bool(summary and summary["available"]),
                }
            recommendations.append(
                {
                    "skill_index": index,
                    "skill_name": format_skill_label(index, skill.get("name")),
                    "skill_icon_id": skill.get("skillId", ""),
                    "current_level": current,
                    "stages": stages,
                    "targets": targets,
                    **targets["3"],
                }
            )
        for module in modules:
            try:
                module["max_level"] = max(
                    (entry["level"] for entry in module.get("levels", [])), default=1
                )
                module["targets"] = {}
                for target_level in range(1, module["max_level"] + 1):
                    costs = module_materials(module, target_level)
                    materials = costs + (
                        promotion_materials(
                            char, growth_def, growth, (module["elite"], module["level"])
                        )
                        if costs
                        else []
                    )
                    module["targets"][str(target_level)] = {
                        "opening_summary": calculate_growth_materials(budget, costs),
                        "material_summary": calculate_growth_materials(
                            budget, materials
                        ),
                    }
                module.update(module["targets"][str(module["max_level"])])
            except ValueError as exc:
                module["material_error"] = str(exc)
        promotion = None
        phases = growth_def.get("phases", [])
        max_phase = len(phases) - 1 if phases else 0
        max_level = phases[-1]["max_level"] if phases else 0
        level_goals = []
        for goal_id, target in sorted(
            level_goal_targets(growth_def).items(), key=lambda row: row[1]
        ):
            elite, level = target
            phase_label = ("未精英", "精一", "精二")[elite]
            level_goals.append(
                {
                    "id": goal_id,
                    "elite": elite,
                    "level": level,
                    "label": f"{phase_label} {level} 级",
                    "summary": calculate_growth_materials(
                        budget, promotion_materials(char, growth_def, growth, target)
                    )
                    if (char.get("evolvePhase", 0), char.get("level", 1)) < target
                    else None,
                }
            )
        max_level_summary = None
        module_level = {6: 60, 5: 50, 4: 40}.get(info.get("rarity"), 0)
        module_level_summary = None
        if (
            max_level
            and module_level
            and (char.get("evolvePhase", 0), char.get("level", 1)) < (2, module_level)
        ):
            module_level_summary = calculate_growth_materials(
                budget, promotion_materials(char, growth_def, growth, (2, module_level))
            )
        if max_level and (char.get("evolvePhase", 0), char.get("level", 1)) < (
            max_phase,
            max_level,
        ):
            max_level_summary = calculate_growth_materials(
                budget,
                promotion_materials(char, growth_def, growth, (max_phase, max_level)),
            )
        if char.get("evolvePhase", 0) < max_phase:
            promotion = calculate_growth_materials(
                budget, promotion_materials(char, growth_def, growth, (max_phase, 1))
            )
        result["operators"].append(
            {
                "char_id": cid,
                "name": info.get("name", cid),
                "rarity": info.get("rarity", 0),
                "profession": info.get("profession", ""),
                "sub_profession": info.get("subProfessionId", ""),
                "elite": char.get("evolvePhase", 0),
                "level": char.get("level", 1),
                "main_skill_level": char.get("mainSkillLevel"),
                "skill_levels": [
                    skill.get("level") for skill in char.get("skills", [])
                ],
                "mastery_error": _mastery_requirement_error(char)
                if definition
                else None,
                "material_error": material_error,
                "potential": char.get("potentialRank", 0) + 1,
                "recommendations": recommendations,
                "modules": modules,
                "promotion_summary": promotion,
                "promotion_target": max_phase,
                "max_phase": max_phase,
                "level_goals": level_goals,
                "max_level": max_level,
                "max_level_summary": max_level_summary,
                "module_level": module_level,
                "module_level_summary": module_level_summary,
                "basic_skill_summary": basic_summary,
                "supports_basic_skill7": supports_basic_skill7,
                "basic_skill_prerequisite": basic_prerequisite,
            }
        )
    result["operators"].sort(key=lambda op: (-op["rarity"], op["name"]))
    result["has_data"] = True
    return result


def _workshop_lookahead_active(plan):
    """Only a confirmed, unexpired training countdown unlocks one-skill lookahead."""
    from datetime import datetime

    if plan.get("status") != "training" or not plan.get("expires_at"):
        return False
    try:
        deadline = datetime.fromisoformat(plan["expires_at"])
        return deadline > datetime.now(tz=deadline.tzinfo)
    except (TypeError, ValueError):
        return False


def _remaining_mastery_materials(plan, recommendation):
    """Remaining costs through the plan target, excluding an already-paid step."""
    stages = recommendation.get("stages")
    if stages is None:
        return recommendation.get("chain_needed_materials", [])
    paid_level = 0
    if plan.get("status") in ("training", "waiting_collect"):
        runtime = plan.get("support_runtime") or {}
        if isinstance(runtime, str):
            runtime = json.loads(runtime)
        paid_level = runtime.get("level") or recommendation.get("current_level", 0) + 1
    return [
        material
        for stage in stages
        if paid_level < stage["to_level"] - 7 <= plan.get("target_level", 3)
        for material in stage.get("needed_materials", [])
    ]


def _workshop_training_reserve(plan, recommendation):
    from collections import defaultdict

    reserved = defaultdict(int)
    for material in _remaining_mastery_materials(plan, recommendation):
        reserved[material["name"]] += material["count"]
    return reserved


def compute_workshop_config(
    fodder_operators=None,
    t5_operators=None,
    book_operators=None,
    *,
    plans=None,
    recommendations=None,
):
    """按计划顺序准备首个可满足技能，确认开训后缺料时只等待当前计划。"""
    if fodder_operators is None:
        fodder_operators = ["九色鹿"]
    if t5_operators is None:
        t5_operators = ["年"]
    if book_operators is None:
        book_operators = ["司霆惊蛰"]
    from collections import defaultdict

    from arknights_mower.data import workshop_formula

    # 计划直接读 DB（get_all_plans 非终态）。matery_plan.json 是全仓库无写入者
    # 的孤儿文件（@app/tmp 上的 stale key），UI/API/agent 新增计划不在里面；completed/
    # failed 计划不核算材料（不消耗；failed 已由扫描钩子 retry_failed_plans 先重置 idle）。
    from arknights_mower.utils.mastery_db import (
        get_all_plans,
        get_material_waiting_plan,
    )

    if plans is None:
        plans = get_all_plans()

    if plans:
        try:
            cultivate_path = get_path("@app/tmp/cultivate.json")
            if os.path.exists(cultivate_path):
                with open(cultivate_path, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                m3 = set()
                for char in cdata.get("data", {}).get("characters", []):
                    for idx, s in enumerate(char.get("skills", [])):
                        if s.get("level", 0) >= 3:
                            m3.add(f"{char.get('id')}_{idx}")
                plans = [
                    p for p in plans if f"{p['char_id']}_{p['skill_index']}" not in m3
                ]
        except Exception:
            pass

    # Starting/collecting a skill is not confirmation that training is underway.
    current = next(
        (
            p
            for p in plans
            if p.get("status") in {"arranging", "training", "waiting_collect"}
        ),
        None,
    )
    current = current or get_material_waiting_plan(plans)
    lookahead = current is not None and _workshop_lookahead_active(current)
    candidates = (
        [current]
        if current is not None and not lookahead
        else [p for p in plans if p.get("status", "idle") == "idle"]
    )
    if not candidates:
        return []

    skill_data_path = _find_skill_data()
    with open(skill_data_path, "r", encoding="utf-8") as f:
        skill_data = json.load(f)
    items = skill_data.get("items", {})

    from arknights_mower.utils.workshop_fodder import deer_fodder_items

    fodder_items = deer_fodder_items()

    t4_names = {
        n: e
        for n, e in workshop_formula.items()
        if e.get("tab") == "精英材料" and e.get("apCost") == 4.0
    }
    t5_names = {
        n: e
        for n, e in workshop_formula.items()
        if e.get("tab") == "精英材料" and e.get("apCost") == 8.0
    }

    rec_result = (
        recommendations
        if recommendations is not None
        else get_mastery_recommendations()
    )
    operators = rec_result.get("operators", [])

    recommendations = {
        (op["char_id"], r["skill_index"]): r
        for op in operators
        if not op.get("mastery_error")
        for r in op.get("recommendations", [])
    }
    reserved = {}
    if lookahead:
        current_rec = recommendations.get((current["char_id"], current["skill_index"]))
        if current_rec is None:
            return []  # Cannot safely spend stock without the active skill's costs.
        reserved = _workshop_training_reserve(current, current_rec)

    cultivate_path = get_path("@app/tmp/cultivate.json")
    inventory = defaultdict(int)
    if os.path.exists(cultivate_path):
        with open(cultivate_path, "r", encoding="utf-8") as f:
            cdata = json.load(f)
        for item in cdata.get("data", {}).get("items", []):
            cnt = int(item.get("count", 0))
            if cnt > 0:
                inventory[item.get("id", "")] = cnt

    id_by_name = {}
    for iid, info in items.items():
        id_by_name[info.get("name", "")] = iid

    def inv_of(name):
        return max(
            0, inventory.get(id_by_name.get(name, ""), 0) - reserved.get(name, 0)
        )

    from arknights_mower.utils.mastery_materials import MaterialBudget
    from arknights_mower.utils.workshop_material_policy import (
        protected_workshop_materials,
    )

    budget = MaterialBudget(
        skill_data,
        inventory,
        workshop_formula,
        blocked_materials=protected_workshop_materials(),
    )
    for candidate in candidates:
        selected_rec = recommendations.get(
            (candidate["char_id"], candidate["skill_index"])
        )
        if selected_rec is None:
            continue
        raw_demand = defaultdict(int)
        for mat in _remaining_mastery_materials(candidate, selected_rec):
            raw_demand[mat["name"]] += mat["count"]
        summary = budget.calculate(
            [
                {
                    "id": id_by_name.get(name, name),
                    "count": raw_demand.get(name, 0) + reserved.get(name, 0),
                }
                for name in raw_demand.keys() | reserved.keys()
            ]
        )
        if summary["craftable"]:
            break
        from arknights_mower.utils.log import logger

        logger.debug(
            f"专精计划 {candidate['char_id']} 技能{candidate['skill_index'] + 1} "
            "材料不足，本轮跳过，等待后续仓库扫描"
        )
    else:
        return []

    demand_t5_raw = {n: c for n, c in raw_demand.items() if n in t5_names}
    demand_t4_raw = {n: c for n, c in raw_demand.items() if n in t4_names}
    demand_t3_plus = {
        n: c for n, c in raw_demand.items() if n not in t4_names and n not in t5_names
    }

    t4_indirect = defaultdict(int)
    for t5_name, t5_demand in demand_t5_raw.items():
        t5_missing = max(0, t5_demand - inv_of(t5_name))
        formula = t5_names.get(t5_name, {})
        for child in formula.get("items", []):
            if child in t4_names:
                t4_indirect[child] += t5_missing

    t4_total = defaultdict(int)
    for name in set(list(demand_t4_raw.keys()) + list(t4_indirect.keys())):
        t4_total[name] = demand_t4_raw.get(name, 0) + t4_indirect.get(name, 0)

    # Low-tier specialists also need actual tasks (e.g. Foldbranch's 异铁组).
    # Prefer game recipe quantities; legacy resources may only contain composite.
    specialty_demand = defaultdict(int)
    for name, count in demand_t3_plus.items():
        formula = workshop_formula.get(name, {})
        if formula.get("tab") == "精英材料" and 0 < formula.get("apCost", 0) < 4:
            specialty_demand[name] += count
    for name, demand in t4_total.items():
        missing = max(0, demand - inv_of(name))
        parent_id = id_by_name.get(name)
        ingredients = (
            skill_data.get("workshop", {}).get("recipe_ingredients", {}).get(parent_id)
        )
        if ingredients is None:
            composite = skill_data.get("composite", {}).get(parent_id, {})
            ingredients = {
                child["id"]: child["count"] for child in composite.get("pathway", [])
            }
        for child_id, count in ingredients.items():
            child_name = items.get(child_id, {}).get("name")
            formula = workshop_formula.get(child_name, {})
            if formula.get("tab") == "精英材料" and 0 < formula.get("apCost", 0) < 4:
                specialty_demand[child_name] += missing * count
    specialist_items = [
        {"item_names": [name], "children_lower_limit": 0, "self_upper_limit": demand}
        for name, demand in sorted(specialty_demand.items())
        if demand > 0
    ]

    t4_items = []
    for name, demand in sorted(t4_total.items()):
        if demand > 0:
            t4_items.append(
                {
                    "item_names": [name],
                    "children_lower_limit": 0,
                    "self_upper_limit": demand,
                }
            )

    t5_items = []
    for name, demand in sorted(demand_t5_raw.items()):
        if demand > 0:
            t5_items.append(
                {
                    "item_names": [name],
                    "children_lower_limit": 0,
                    "self_upper_limit": demand,
                }
            )

    book_count = demand_t3_plus.get("技巧概要·卷3", 0)
    book_items = (
        [
            {
                "item_names": ["技巧概要·卷3"],
                "children_lower_limit": 0,
                "self_upper_limit": book_count,
            }
        ]
        if book_count > 0
        else []
    )

    from arknights_mower.utils.workshop_recommendation import allocate_workshop_items

    def protect_active_materials(tasks):
        # The existing executor uses batch crafting, so a start-only lower limit
        # cannot protect stock. Defer recipes consuming any reserved ingredient.
        return [
            {
                **task,
                "self_upper_limit": task["self_upper_limit"]
                + reserved.get(task["item_names"][0], 0),
            }
            for task in tasks
            if not any(
                reserved.get(child, 0) > 0
                for child in workshop_formula[task["item_names"][0]]["items"]
            )
        ]

    return allocate_workshop_items(
        [
            ("fodder_operators", fodder_operators, protect_active_materials(t4_items)),
            ("t5_operators", t5_operators, protect_active_materials(t5_items)),
            ("book_operators", book_operators, protect_active_materials(book_items)),
        ],
        fodder_items=fodder_items,
        specialist_items=protect_active_materials(specialist_items),
    )


def compute_default_workshop_config(
    fodder_operators=None, t5_operators=None, book_operators=None
):
    """默认 T4+T5+技巧概要配置，另为已解锁专属干员补入对应低阶配方。"""
    if fodder_operators is None:
        fodder_operators = ["九色鹿"]
    if t5_operators is None:
        t5_operators = ["年"]
    if book_operators is None:
        book_operators = ["司霆惊蛰"]
    from arknights_mower.data import workshop_formula

    t4_names = {
        n
        for n, e in workshop_formula.items()
        if e.get("tab") == "精英材料" and e.get("apCost") == 4.0
    }
    t5_names = {
        n
        for n, e in workshop_formula.items()
        if e.get("tab") == "精英材料" and e.get("apCost") == 8.0
    }
    from arknights_mower.utils.workshop_fodder import deer_fodder_items

    fodder_items = deer_fodder_items()
    default_t4 = [
        {"item_names": [n], "children_lower_limit": 20, "self_upper_limit": 20}
        for n in sorted(t4_names)
    ]
    default_t5 = [
        {"item_names": [n], "children_lower_limit": 20, "self_upper_limit": 20}
        for n in sorted(t5_names)
    ]
    default_book = [
        {
            "item_names": ["技巧概要·卷3"],
            "children_lower_limit": 20,
            "self_upper_limit": 20,
        }
    ]
    specialist_items = [
        {"item_names": [name], "children_lower_limit": 20, "self_upper_limit": 20}
        for name, recipe in sorted(workshop_formula.items())
        if recipe.get("tab") == "精英材料" and 0 < recipe.get("apCost", 0) < 4
    ]
    from arknights_mower.utils.workshop_recommendation import allocate_workshop_items

    return allocate_workshop_items(
        [
            ("fodder_operators", fodder_operators, default_t4),
            ("t5_operators", t5_operators, default_t5),
            ("book_operators", book_operators, default_book),
        ],
        fodder_items=fodder_items,
        specialist_items=specialist_items,
    )


def auto_schedule_mastery_tasks(*, inventory=None):
    """Return material-ready plans using supplied name counts or the scan snapshot."""
    result = {"scheduled": [], "skipped": []}

    # 计划直接读 DB（get_all_plans 非终态）——matery_plan.json 是全仓库无写入者
    # 的孤儿文件，只靠它的话新装/绕过前端新增的计划永远不在 plan_set，扫描自动开始失效。
    from arknights_mower.utils.mastery_db import (
        get_all_plans,
        get_material_waiting_plan,
    )

    plans = get_all_plans()
    waiting = get_material_waiting_plan(plans)
    if waiting is not None:
        plans = [waiting]
    plan_set = {(p["char_id"], p["skill_index"]): p for p in plans}
    if not plan_set:
        return result

    rec_result = get_mastery_recommendations()
    if not rec_result.get("has_data"):
        return result

    operators = rec_result.get("operators", [])
    from arknights_mower.utils.mastery_support_data import trainee_schedule_conflict

    if inventory is None:
        cultivate_path = get_path("@app/tmp/cultivate.json")
        counts = {}
        if os.path.exists(cultivate_path):
            try:
                with open(cultivate_path, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                for item in cdata.get("data", {}).get("items", []):
                    cnt = int(item.get("count", 0))
                    if cnt > 0:
                        counts[item.get("id", "")] = cnt
            except Exception:
                pass

        skill_data_path = _find_skill_data()
        name_to_id = {}
        if os.path.exists(skill_data_path):
            try:
                with open(skill_data_path, "r", encoding="utf-8") as f:
                    items_table = json.load(f).get("items", {})
                for iid, info in items_table.items():
                    name_to_id[info.get("name", "")] = iid
            except Exception:
                pass
        inventory = {name: counts.get(iid, 0) for name, iid in name_to_id.items()}

    for op in operators:
        if op.get("mastery_error"):
            continue
        schedule_conflict = trainee_schedule_conflict(op["name"])
        for rec in op.get("recommendations", []):
            if (op["char_id"], rec["skill_index"]) not in plan_set:
                continue
            plan = plan_set[(op["char_id"], rec["skill_index"])]
            if rec.get("current_level", 0) >= plan.get("target_level", 3):
                continue

            from collections import Counter

            needed = Counter()
            for mat in _remaining_mastery_materials(plan, rec):
                needed[mat["name"]] += mat["count"]
            all_materials_sufficient = True
            for name, count in needed.items():
                owned = inventory.get(name, 0)
                if owned < count:
                    all_materials_sufficient = False
                    break

            entry = {
                "char_id": op["char_id"],
                "name": op["name"],
                "profession": op["profession"],
                "skill_index": rec["skill_index"],
                "skill_name": rec["skill_name"],
                "achievable": all_materials_sufficient,
                "current_level": rec.get("current_level", 0),
            }
            if schedule_conflict:
                entry["achievable"] = False
                entry["reason"] = schedule_conflict
                result["skipped"].append(entry)
            elif all_materials_sufficient:
                result["scheduled"].append(entry)
            else:
                result["skipped"].append(entry)

    return result


PROF_MAP = {
    "WARRIOR": "近卫",
    "SNIPER": "狙击",
    "TANK": "重装",
    "MEDIC": "医疗",
    "SUPPORT": "辅助",
    "CASTER": "术师",
    "SPECIAL": "特种",
    "PIONEER": "先锋",
}
