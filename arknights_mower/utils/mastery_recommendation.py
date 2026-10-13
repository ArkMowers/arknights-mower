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


def get_mastery_recommendations(*, include_materials=True, char_id=None):
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
    from arknights_mower.utils.growth_value import price_catalog
    from arknights_mower.utils.mastery_materials import MaterialBudget
    from arknights_mower.utils.operator_statistics import personal_statistics
    from arknights_mower.utils.workshop_material_policy import (
        protected_workshop_materials,
    )

    summarize = calculate_growth_materials if include_materials else lambda *_: None
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
        catalog = price_catalog()
        result["statistics"] = statistics(box["characters"], skills, catalog)
        result["personal_statistics"] = personal_statistics(
            box["characters"], skills, catalog
        )
        result["history"] = statistics_history()
    except (OSError, ValueError, KeyError) as exc:
        result["error"] = f"请从森空岛同步干员数据：{exc}"
        return result

    for char in box["characters"]:
        cid = char["id"]
        if char_id is not None and cid != char_id:
            continue
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
                    basic_summary = summarize(budget, basic)
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
                    else summarize(budget, prerequisite + materials)
                )
                targets[str(target)] = {
                    "target_level": target,
                    "remaining_levels": target - current,
                    "total_time": sum(s["lvl_up_time"] for s in selected),
                    "chain_needed_materials": materials,
                    "material_summary": summary,
                    "skill_material_summary": summarize(budget, materials),
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
                        "opening_summary": summarize(budget, costs),
                        "material_summary": summarize(budget, materials),
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
                    "summary": summarize(
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
            module_level_summary = summarize(
                budget, promotion_materials(char, growth_def, growth, (2, module_level))
            )
        if max_level and (char.get("evolvePhase", 0), char.get("level", 1)) < (
            max_phase,
            max_level,
        ):
            max_level_summary = summarize(
                budget,
                promotion_materials(char, growth_def, growth, (max_phase, max_level)),
            )
        if char.get("evolvePhase", 0) < max_phase:
            promotion = summarize(
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
    if not include_materials:
        for operator in result["operators"]:
            operator["recommendations"] = [
                {
                    key: rec[key]
                    for key in (
                        "skill_index",
                        "skill_name",
                        "skill_icon_id",
                        "current_level",
                    )
                }
                for rec in operator["recommendations"]
            ]
            operator["modules"] = [
                {
                    key: module[key]
                    for key in (
                        "id",
                        "name",
                        "type",
                        "current_level",
                        "max_level",
                        "elite",
                        "level",
                    )
                    if key in module
                }
                for module in operator["modules"]
            ]
    result["operators"].sort(key=lambda op: (-op["rarity"], op["name"]))
    result["has_data"] = True
    return result


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
    plan_set = {(p["char_id"], p["skill_index"]): p for p in plans}
    if not plan_set:
        return result

    rec_result = get_mastery_recommendations()
    if not rec_result.get("has_data"):
        return result

    operators = rec_result.get("operators", [])
    from .mastery_db import normalize_mastery_queue
    from .mastery_order import mastery_groups

    recommendations = {
        (op["char_id"], rec["skill_index"]): rec
        for op in operators
        if not op.get("mastery_error")
        for rec in op.get("recommendations", [])
    }
    levels = {key: rec.get("current_level", 0) for key, rec in recommendations.items()}
    plans = normalize_mastery_queue(levels)
    groups = mastery_groups(plans, levels)
    group_heads = {
        cid: next((p["id"] for p in group if p.get("status") == "idle"), None)
        for cid, group in groups.items()
    }
    waiting = get_material_waiting_plan(plans)
    if waiting is not None:
        plan_set = {(waiting["char_id"], waiting["skill_index"]): waiting}
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
    skill_data = {}
    if os.path.exists(skill_data_path):
        try:
            with open(skill_data_path, "r", encoding="utf-8") as f:
                skill_data = json.load(f)
                items_table = skill_data.get("items", {})
            for iid, info in items_table.items():
                name_to_id[info.get("name", "")] = iid
        except Exception:
            pass
    if inventory is None:
        inventory = {name: counts.get(iid, 0) for name, iid in name_to_id.items()}

    from arknights_mower.data import workshop_formula

    from .mastery_materials import MaterialBudget
    from .workshop_material_policy import protected_workshop_materials

    budget = MaterialBudget(
        skill_data,
        {name_to_id.get(name, name): count for name, count in inventory.items()},
        workshop_formula,
        blocked_materials=protected_workshop_materials(),
    )
    group_craftable = {}
    for cid, group in groups.items():
        materials = []
        for member in group:
            member_rec = recommendations.get((cid, member["skill_index"]))
            if member_rec is None:
                group_craftable[cid] = False
                break
            materials.extend(
                {"id": name_to_id.get(mat["name"], mat["name"]), "count": mat["count"]}
                for mat in _remaining_mastery_materials(member, member_rec)
            )
        else:
            group_craftable[cid] = budget.calculate(materials)["craftable"]

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
            elif not group_craftable.get(op["char_id"], True):
                entry["achievable"] = False
                entry["reason"] = "同干员相邻技能的联合材料需求尚不可合成"
                result["skipped"].append(entry)
            elif (
                plan.get("status") == "idle"
                and op["char_id"] in group_heads
                and plan["id"] != group_heads[op["char_id"]]
            ):
                entry["achievable"] = False
                entry["reason"] = "等待同干员前序技能，当前仅筹备一个技能的材料"
                result["skipped"].append(entry)
            elif all_materials_sufficient:
                result["scheduled"].append(entry)
            else:
                result["skipped"].append(entry)

    ranks = {(p["char_id"], p["skill_index"]): i for i, p in enumerate(plans)}
    result["scheduled"].sort(
        key=lambda entry: ranks.get(
            (entry["char_id"], entry["skill_index"]), len(ranks)
        )
    )
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
