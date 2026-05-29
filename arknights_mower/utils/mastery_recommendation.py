import json
import os

from arknights_mower.utils.path import _install_dir, _internal_dir, get_path


def _find_skill_data():
    candidates = [
        _internal_dir / "arknights_mower" / "resources" / "skill_data.json",
        _install_dir / "arknights_mower" / "resources" / "skill_data.json",
        _install_dir / "resources" / "skill_data.json",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


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

        if evolve_phase < 2:
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
                    "skill_name": f"技能{i + 1}",
                    "skill_icon_id": skill_def.get("skillId", ""),
                    "current_level": current_level,
                    "target_level": 3,
                    "remaining_levels": end_stage - start_stage,
                    "total_time": total_time,
                    "full_chain_achievable": full_chain_achievable,
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
                    "main_skill_level": char.get("mainSkillLevel", 7),
                    "potential": char.get("potentialRank", 0) + 1,
                    "recommendations": recommendations,
                }
            )

    operators.sort(key=lambda o: (-o["rarity"], -len(o["recommendations"])))

    result["operators"] = operators
    result["has_data"] = True
    return result


def compute_workshop_config(t5_operator="年", book_operator="司霆惊蛰"):
    """根据当前专精计划和仓库库存，计算合成配置（与前端自动合成配置逻辑一致）"""
    from collections import defaultdict

    from arknights_mower.data import workshop_formula

    plan_path = get_path("@app/tmp/matery_plan.json")
    planned_keys = []
    if os.path.exists(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan = json.load(f)
            planned_keys = [k for k, v in plan.items() if v]
        except Exception:
            pass

    skill_data_path = _find_skill_data()
    with open(skill_data_path, "r", encoding="utf-8") as f:
        skill_data = json.load(f)
    items = skill_data.get("items", {})

    def item_rarity(name):
        for iid, info in items.items():
            if info.get("name") == name:
                return info.get("rarity", 0)
        return 0

    fodder_list = ["碳素", "碳素组", "家具零件_碳素组"]
    fodder_items = [
        {"item_names": [f], "children_lower_limit": 0, "self_upper_limit": 9999}
        for f in fodder_list
        if f in workshop_formula
    ]

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

    if not planned_keys:
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
        return [
            {"operator": "九色鹿", "enabled": True, "items": fodder_items + default_t4},
            {"operator": t5_operator, "enabled": True, "items": default_t5},
            {"operator": book_operator, "enabled": True, "items": default_book},
        ]

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

    if not planned_keys:
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
        return [
            {"operator": "九色鹿", "enabled": True, "items": fodder_items + default_t4},
            {"operator": "年", "enabled": True, "items": default_t5},
            {"operator": "司霆惊蛰", "enabled": True, "items": default_book},
        ]

    rec_result = get_mastery_recommendations()
    operators = rec_result.get("operators", [])

    plan_set = set()
    for key in planned_keys:
        parts = key.rsplit("_", 1)
        if len(parts) == 2:
            try:
                plan_set.add((parts[0], int(parts[1])))
            except ValueError:
                pass

    raw_demand = defaultdict(int)
    for op in operators:
        for rec in op.get("recommendations", []):
            if (op["char_id"], rec["skill_index"]) not in plan_set:
                continue
            for mat in rec.get("chain_needed_materials", []):
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
        return inventory.get(id_by_name.get(name, ""), 0)

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

    return [
        {"operator": "九色鹿", "enabled": True, "items": fodder_items + t4_items},
        {"operator": "年", "enabled": True, "items": t5_items},
        {"operator": "司霆惊蛰", "enabled": True, "items": book_items},
    ]


def auto_schedule_mastery_tasks():
    """仓库扫描后：检测计划内未满M3的技能，直接需求全部满足则返回待安排列表"""
    result = {"scheduled": [], "skipped": []}

    plan_path = get_path("@app/tmp/matery_plan.json")
    if not os.path.exists(plan_path):
        return result
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except Exception:
        return result
    if not plan:
        return result

    plan_set = set()
    for key in plan:
        if not plan[key]:
            continue
        parts = key.rsplit("_", 1)
        if len(parts) == 2:
            try:
                plan_set.add((parts[0], int(parts[1])))
            except ValueError:
                pass

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
        for rec in op.get("recommendations", []):
            if (op["char_id"], rec["skill_index"]) not in plan_set:
                continue
            if rec.get("current_level", 0) >= 3:
                continue

            all_materials_sufficient = True
            for mat in rec.get("chain_needed_materials", []):
                mat_id = name_to_id.get(mat["name"], "")
                owned = inventory.get(mat_id, 0)
                if owned < mat["count"]:
                    all_materials_sufficient = False
                    break

            entry = {
                "char_id": op["char_id"],
                "name": op["name"],
                "profession": op["profession"],
                "skill_index": rec["skill_index"],
                "skill_name": rec["skill_name"],
                "achievable": all_materials_sufficient,
            }
            if all_materials_sufficient:
                result["scheduled"].append(entry)
            else:
                result["skipped"].append(entry)

    return result
