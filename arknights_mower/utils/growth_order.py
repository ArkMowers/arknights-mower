"""Order crafting projects without changing the training queue or shared costs."""

import json
from collections import Counter

from arknights_mower.utils.growth import (
    LEVEL_GOALS,
    basic_skill_target,
    calculate_growth_materials,
    growth_data,
    level_goal_targets,
    material_entries,
)
from arknights_mower.utils.mastery_db import get_material_waiting_plan
from arknights_mower.utils.mastery_materials import MaterialBudget
from arknights_mower.utils.path import get_path


def crafting_projects(plans, goals, order=()):
    """Pin active training; default to skill order before other growth goals."""
    waiting = get_material_waiting_plan(plans)
    projects = {}
    for plan in sorted(
        plans,
        key=lambda p: (
            p.get("status") not in ("arranging", "training", "waiting_collect")
        ),
    ):
        key = f"skill:{plan['char_id']}:{plan['skill_index']}"
        projects.setdefault(
            key,
            {
                "key": key,
                "char_id": plan["char_id"],
                "kind": "skill",
                "plan": plan,
                "locked": plan.get("status")
                in ("arranging", "training", "waiting_collect")
                or plan is waiting,
            },
        )
    for goal in goals:
        key = f"goal:{goal['char_id']}:{goal['module_id']}"
        projects[key] = {
            "key": key,
            "char_id": goal["char_id"],
            "kind": "goal",
            "goal": goal,
            "locked": False,
        }
    rank = {key: index for index, key in enumerate(order)}
    return sorted(
        projects.values(),
        key=lambda p: (not p["locked"], rank.get(p["key"], len(rank))),
    )


def prepare_project_materials(box, skills, projects, inventory, formulas, blocked=()):
    """Skip shortages without reserving them; keep confirmed training protected."""
    budget = MaterialBudget(skills, inventory, formulas, blocked_materials=blocked)
    groups, accounted, prerequisite_costs, entries = {}, {}, {}, []
    reserved = Counter()
    active_shortage = False
    states = []
    for project in projects:
        cid = project["char_id"]
        previous = groups.get(cid, {"plans": [], "goals": []})
        group = {key: list(values) for key, values in previous.items()}
        if project["kind"] == "skill":
            group["plans"].append(project["plan"])
        else:
            group["goals"].append(project["goal"])
        cumulative, prerequisites = Counter(), Counter()
        for _, before, materials in material_entries(
            box, skills, **group, separate_prerequisites=True
        ):
            for material in before:
                prerequisites[material["id"]] += material["count"]
            for material in before + materials:
                cumulative[material["id"]] += material["count"]
        extra = cumulative - accounted.get(cid, Counter())
        total = reserved + extra
        summary = calculate_growth_materials(
            budget, [{"id": iid, "count": n} for iid, n in total.items()]
        )
        eligible = summary["craftable"] and not active_shortage
        state = {**project, "status": "ready", "reason": ""}
        if project["locked"]:
            state["status"] = "active"
            if not eligible:
                active_shortage = True
                state["reason"] = "当前训练材料不足，暂停后续备料"
        elif active_shortage:
            state.update(status="waiting", reason="等待当前训练材料补齐")
        elif not eligible:
            state.update(status="waiting", reason="材料不足，本轮跳过")
        elif not prerequisites_ready(box, skills, project):
            state.update(status="preparing", reason="仅准备材料，前置未完成")
        states.append(state)
        if not eligible:
            continue
        groups[cid] = group
        accounted[cid] = cumulative
        reserved = total
        before = prerequisites - prerequisite_costs.get(cid, Counter())
        prerequisite_costs[cid] = prerequisites
        for costs in (before, extra - before):
            if costs:
                entries.append(
                    (
                        project["key"],
                        [{"id": iid, "count": n} for iid, n in costs.items()],
                    )
                )
    return states, entries


def prerequisites_ready(box, skills, project):
    cid = project["char_id"]
    char = next((c for c in box.get("characters", []) if c["id"] == cid), {})
    current = (char.get("evolvePhase", 0), char.get("level", 1))
    if project["kind"] == "skill":
        return current >= (2, 1) and char.get("mainSkillLevel", 0) >= 7
    mid = project["goal"]["module_id"]
    if mid in LEVEL_GOALS:
        return True
    definition = growth_data(skills).get("characters", {}).get(cid, {})
    if mid == "skill7":
        return current >= basic_skill_target(definition)
    module = next(m for m in definition.get("modules", []) if m["id"] == mid)
    return current >= (module["elite"], module["level"])


def describe_projects(projects, skills):
    definitions = growth_data(skills).get("characters", {})
    result = []
    for project in projects:
        cid = project["char_id"]
        definition = definitions.get(cid, {})
        skill_def = skills.get("characters", {}).get(cid, {})
        if project["kind"] == "skill":
            plan = project["plan"]
            label = (
                f"{plan.get('skill_name') or str(plan['skill_index'] + 1) + '技能'}"
                f" · 专{('一', '二', '三')[plan.get('target_level', 3) - 1]}"
            )
        else:
            goal = project["goal"]
            mid = goal["module_id"]
            if mid in LEVEL_GOALS:
                phase, level = level_goal_targets(definition)[mid]
                label = f"精{('零', '一', '二')[phase]} Lv.{level}"
            elif mid == "skill7":
                label = "基础技能升至 7 级"
            else:
                module = next(
                    (m for m in definition.get("modules", []) if m["id"] == mid), {}
                )
                label = (
                    f"{module.get('name', mid)} · 模组 {goal.get('target_level', 1)} 级"
                )
        result.append(
            {
                **{
                    key: project[key]
                    for key in ("key", "char_id", "kind", "locked", "status", "reason")
                },
                "char_name": definition.get("name") or skill_def.get("name") or cid,
                "label": label,
            }
        )
    return result


def validate_order(order, projects):
    if not isinstance(order, list) or any(not isinstance(key, str) for key in order):
        raise ValueError("合成顺序格式错误")
    keys = [project["key"] for project in projects]
    if len(order) != len(keys) or set(order) != set(keys):
        raise ValueError("养成项目已变化，请刷新合成顺序后重试")
    locked = [project["key"] for project in projects if project["locked"]]
    if order[: len(locked)] != locked:
        raise ValueError("正在训练或等待继续的计划固定在最前，不能调整")
    return list(order)


def crafting_order_state():
    from arknights_mower.data import workshop_formula
    from arknights_mower.utils import config
    from arknights_mower.utils.growth import (
        growth_resources,
        inventory_counts,
        load_goals,
    )
    from arknights_mower.utils.mastery_db import get_all_plans
    from arknights_mower.utils.mastery_recommendation import get_skill_data
    from arknights_mower.utils.workshop_material_policy import (
        protected_workshop_materials,
    )

    order = config.conf.growth_crafting_order
    projects = crafting_projects(get_all_plans(), load_goals(), order)
    if not projects:
        return {"items": [], "custom": bool(order)}
    box = json.loads(get_path("@app/tmp/cultivate.json").read_text("utf-8"))["data"]
    skills = growth_resources(get_skill_data())
    states, _ = prepare_project_materials(
        box,
        skills,
        projects,
        inventory_counts(box, skills, local=True),
        workshop_formula,
        protected_workshop_materials(),
    )
    return {"items": describe_projects(states, skills), "custom": bool(order)}
