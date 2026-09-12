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

    skill_data.json 由 auto_get_res_new.py 生成并并入真名（#63）。
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
    return {char["id"]: char for char in data.get("data", {}).get("characters", [])}


def _get_cultivate_character(char_id):
    # 批量添加计划时共用 BOX 快照；同步文件变化后自动失效。
    path = get_path("@app/tmp/cultivate.json")
    try:
        stat = os.stat(path)
        return _read_cultivate_characters(
            str(path), stat.st_mtime_ns, stat.st_size
        ).get(char_id)
    except Exception:
        return None


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
    level = char.get("mainSkillLevel")
    if type(level) is not int or level < 1:
        return "无法确认基础技能等级，请先同步干员数据"
    if level < 7:
        return f"基础技能仅 {level} 级，需手动升至 7 级并同步干员数据后再添加专精计划"
    return None


def get_mastery_requirement_error(char_id):
    """校验已有 BOX 中的真实基础技能等级；未读取 BOX 的旧手动入口保持兼容。"""
    char = _get_cultivate_character(char_id)
    return _mastery_requirement_error(char) if char is not None else None


def _decompose_to_t3(materials, composite, item_table, inventory):
    """将 T4/T5 材料拆解为 T3 级别材料，并与仓库库存对比"""
    raw = {}

    def _expand(mat_id, count):
        comp = composite.get(mat_id)
        if not comp:
            rarity = (item_table.get(mat_id, {}) or {}).get("rarity", 0)
            if rarity == 3:
                raw[mat_id] = raw.get(mat_id, 0) + count
            return
        rarity = comp.get("rarity", 0)
        if rarity <= 3:
            raw[mat_id] = raw.get(mat_id, 0) + count
            return
        for p in comp.get("pathway", []):
            _expand(p["id"], count * p["count"])

    for mat in materials:
        _expand(mat["id"], mat["count"])

    result = []
    for mid, cnt in sorted(raw.items(), key=lambda x: -x[1]):
        owned = inventory.get(mid, 0)
        shortage = max(0, cnt - owned)
        if shortage > 0:
            result.append(
                {
                    "id": mid,
                    "name": (item_table.get(mid, {}) or {}).get("name", mid),
                    "count": shortage,
                    "total": cnt,
                    "owned": owned,
                }
            )
    return result


def get_mastery_recommendations():
    result = {"operators": [], "has_data": False, "error": None}

    cultivate_path = get_path("@app/tmp/cultivate.json")
    skill_data_path = _find_skill_data()

    if not os.path.exists(cultivate_path):
        result["error"] = "请先点击「从森空岛拉取数据」获取仓库和干员数据"
        return result

    if not os.path.exists(skill_data_path):
        result["error"] = (
            f"专精数据文件未找到: {skill_data_path}\n请运行 extract_skill_data.py 生成"
        )
        return result

    try:
        with open(cultivate_path, "r", encoding="utf-8") as f:
            cultivate_data = json.load(f)
    except Exception as e:
        result["error"] = f"无法读取 cultivate.json: {str(e)}"
        return result

    chars = cultivate_data.get("data", {}).get("characters", [])
    items = cultivate_data.get("data", {}).get("items", [])

    if not chars:
        result["error"] = "未找到干员数据，请先点击「从森空岛拉取数据」"
        return result

    try:
        with open(skill_data_path, "r", encoding="utf-8") as f:
            skill_data = json.load(f)
    except Exception as e:
        result["error"] = f"无法读取 skill_data.json: {str(e)}"
        return result

    char_table = skill_data.get("characters", {})
    item_table = skill_data.get("items", {})
    composite = skill_data.get("composite", {})

    inventory = {}
    for item in items:
        item_id = item.get("id", "")
        count = int(item.get("count", 0))
        if count > 0:
            inventory[item_id] = count

    from arknights_mower.data import workshop_formula
    from arknights_mower.utils.mastery_materials import MaterialBudget
    from arknights_mower.utils.workshop_material_policy import (
        protected_workshop_materials,
    )

    material_budget = MaterialBudget(
        skill_data,
        inventory,
        workshop_formula,
        blocked_materials=protected_workshop_materials(),
    )
    operators = []
    skill_name_cache = {}

    def get_item_name(item_id):
        if item_id in skill_name_cache:
            return skill_name_cache[item_id]
        item_info = item_table.get(item_id, {})
        name = item_info.get("name", item_id)
        skill_name_cache[item_id] = name
        return name

    for char in chars:
        char_id = char.get("id", "")
        evolve_phase = char.get("evolvePhase", 0)

        if evolve_phase < 2 or char_id in UNTRAINABLE_CHAR_IDS:
            continue

        char_info = char_table.get(char_id)
        if not char_info:
            continue

        skills_data = char.get("skills", [])
        if not skills_data:
            continue

        char_skills = char_info.get("skills", [])
        recommendations = []

        for i, skill_status in enumerate(skills_data):
            if i >= len(char_skills):
                continue

            current_level = skill_status.get("level", 0)
            if current_level is None:
                current_level = 0

            if current_level >= 3:
                continue

            skill_def = char_skills[i]
            skill_levels = skill_def.get("levels", [])

            start_stage = current_level
            end_stage = 3

            stages = []
            total_time = 0
            full_chain_achievable = True
            chain_total_needed = {}

            remaining_inventory = dict(inventory)

            for stage in range(start_stage, end_stage):
                if stage >= len(skill_levels):
                    break

                level_data = skill_levels[stage]
                level_materials = level_data.get("materials", [])
                lvl_up_time = level_data.get("time", 0)
                total_time += lvl_up_time

                stage_needed = []
                stage_missing = []
                stage_achievable = True

                for mat in level_materials:
                    mat_id = mat.get("id", "")
                    mat_count = mat.get("count", 0)
                    mat_name = get_item_name(mat_id)
                    owned = remaining_inventory.get(mat_id, 0)
                    shortage = max(0, mat_count - owned)

                    stage_needed.append(
                        {"id": mat_id, "name": mat_name, "count": mat_count}
                    )

                    if shortage > 0:
                        stage_missing.append(
                            {"id": mat_id, "name": mat_name, "count": shortage}
                        )
                        stage_achievable = False
                        full_chain_achievable = False

                    remaining_inventory[mat_id] = max(0, owned - mat_count)

                    chain_total_needed[mat_id] = (
                        chain_total_needed.get(mat_id, 0) + mat_count
                    )

                stages.append(
                    {
                        "from_level": stage + 7,
                        "to_level": stage + 8,
                        "lvl_up_time": lvl_up_time,
                        "achievable": stage_achievable,
                        "needed_materials": stage_needed,
                        "missing_materials": stage_missing,
                    }
                )

            if not stages:
                continue

            chain_needed_list = [
                {"id": mid, "name": get_item_name(mid), "count": cnt}
                for mid, cnt in chain_total_needed.items()
            ]
            chain_missing_list = [
                {
                    "id": mid,
                    "name": get_item_name(mid),
                    "count": max(0, chain_total_needed[mid] - inventory.get(mid, 0)),
                }
                for mid in chain_total_needed
                if chain_total_needed[mid] > inventory.get(mid, 0)
            ]

            chain_missing_t3 = _decompose_to_t3(
                chain_missing_list, composite, item_table, inventory
            )

            recommendations.append(
                {
                    "skill_index": i,
                    "skill_name": format_skill_label(i, skill_def.get("name")),
                    "skill_icon_id": skill_def.get("skillId", ""),
                    "current_level": current_level,
                    "target_level": 3,
                    "remaining_levels": end_stage - start_stage,
                    "total_time": total_time,
                    "full_chain_achievable": full_chain_achievable,
                    "material_summary": material_budget.calculate(chain_needed_list),
                    "chain_needed_materials": chain_needed_list,
                    "chain_missing_materials": chain_missing_list,
                    "chain_missing_t3": chain_missing_t3,
                    "stages": stages,
                }
            )

        if recommendations:
            operators.append(
                {
                    "char_id": char_id,
                    "name": char_info.get("name", char_id),
                    "rarity": char_info.get("rarity", 0),
                    "profession": char_info.get("profession", ""),
                    "sub_profession": "",
                    "elite": evolve_phase,
                    "level": char.get("level", 1),
                    "main_skill_level": char.get("mainSkillLevel"),
                    "mastery_error": _mastery_requirement_error(char),
                    "potential": char.get("potentialRank", 0) + 1,
                    "recommendations": recommendations,
                }
            )

    operators.sort(key=lambda o: (-o["rarity"], -len(o["recommendations"])))

    result["operators"] = operators
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
    """准备队首技能，确认正在训练后可提前一个技能；按钮与仓库扫描共用。"""
    if fodder_operators is None:
        fodder_operators = ["九色鹿"]
    if t5_operators is None:
        t5_operators = ["年"]
    if book_operators is None:
        book_operators = ["司霆惊蛰"]
    from collections import defaultdict

    from arknights_mower.data import workshop_formula

    # #83：计划直接读 DB（get_all_plans 非终态）。matery_plan.json 是全仓库无写入者
    # 的孤儿文件（@app/tmp 上的 stale key），UI/API/agent 新增计划不在里面；completed/
    # failed 计划不核算材料（不消耗；failed 已由扫描钩子 retry_failed_plans 先重置 idle）。
    from arknights_mower.utils.mastery_db import get_all_plans

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
    lookahead = current is not None and _workshop_lookahead_active(current)
    selected = (
        next((p for p in plans if p.get("status", "idle") == "idle"), None)
        if lookahead
        else current or next(iter(plans), None)
    )
    if selected is None:
        return []

    skill_data_path = _find_skill_data()
    with open(skill_data_path, "r", encoding="utf-8") as f:
        skill_data = json.load(f)
    items = skill_data.get("items", {})

    def item_rarity(name):
        for iid, info in items.items():
            if info.get("name") == name:
                return info.get("rarity", 0)
        return 0

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

    plan_key = selected["char_id"], selected["skill_index"]
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

    raw_demand = defaultdict(int)
    selected_rec = recommendations.get(plan_key)
    if selected_rec is None:
        return []
    for mat in _remaining_mastery_materials(selected, selected_rec):
        raw_demand[mat["name"]] += mat["count"]

    demand_t5_raw = {n: c for n, c in raw_demand.items() if n in t5_names}
    demand_t4_raw = {n: c for n, c in raw_demand.items() if n in t4_names}
    demand_t3_plus = {
        n: c for n, c in raw_demand.items() if n not in t4_names and n not in t5_names
    }

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
    summary = budget.calculate(
        [
            {
                "id": id_by_name.get(name, name),
                "count": raw_demand.get(name, 0) + reserved.get(name, 0),
            }
            for name in raw_demand.keys() | reserved.keys()
        ]
    )
    if not summary["craftable"]:
        from arknights_mower.utils.log import logger

        logger.info(
            f"专精计划 {selected['char_id']} 技能{selected['skill_index'] + 1} "
            "材料仍不足，暂不合成，等待后续仓库扫描"
        )
        return []

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


def auto_schedule_mastery_tasks():
    """仓库扫描后：检测计划内未满M3的技能，直接需求全部满足则返回待安排列表"""
    result = {"scheduled": [], "skipped": []}

    # #83：计划直接读 DB（get_all_plans 非终态）——matery_plan.json 是全仓库无写入者
    # 的孤儿文件，只靠它的话新装/绕过前端新增的计划永远不在 plan_set，扫描自动开始失效。
    from arknights_mower.utils.mastery_db import get_all_plans

    plan_set = {(p["char_id"], p["skill_index"]): p for p in get_all_plans()}
    if not plan_set:
        return result

    rec_result = get_mastery_recommendations()
    if not rec_result.get("has_data"):
        return result

    operators = rec_result.get("operators", [])

    cultivate_path = get_path("@app/tmp/cultivate.json")
    inventory = {}
    if os.path.exists(cultivate_path):
        try:
            with open(cultivate_path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            for item in cdata.get("data", {}).get("items", []):
                cnt = int(item.get("count", 0))
                if cnt > 0:
                    inventory[item.get("id", "")] = cnt
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

    for op in operators:
        if op.get("mastery_error"):
            continue
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
                mat_id = name_to_id.get(name, "")
                owned = inventory.get(mat_id, 0)
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
            if all_materials_sufficient:
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
