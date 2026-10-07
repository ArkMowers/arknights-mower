"""Unified growth ordering, training priorities and shared material budgets."""

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


def crafting_projects(plans, goals, order=(), *, box=None, skills=None):
    """Pin active training; default to skill order before other growth goals."""
    waiting = get_material_waiting_plan(plans)
    chars = {c["id"]: c for c in (box or {}).get("characters", [])}
    definitions = growth_data(skills).get("characters", {}) if skills else {}
    projects = {}
    for plan in sorted(
        plans,
        key=lambda p: (
            p.get("status") not in ("arranging", "training", "waiting_collect")
            and p is not waiting
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
        if goal["module_id"] in LEVEL_GOALS and goal["char_id"] in chars:
            target = level_goal_targets(definitions.get(goal["char_id"], {})).get(
                goal["module_id"]
            )
            if target and chars[goal["char_id"]].get("evolvePhase", 0) >= target[0]:
                continue
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
            box, skills, **group, separate_prerequisites=True, crafting_only=True
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
        state = {
            **project,
            "status": "ready",
            "reason": "",
            "materials_prepared": eligible and summary["available"],
        }
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
        elif state["materials_prepared"]:
            state["reason"] = "材料已备齐"
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


def describe_projects(projects, skills, *, planning=False):
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
                label = (
                    f"精{('零', '一', '二')[phase]} Lv.{level}"
                    if planning
                    else f"精英化至精{('零', '一', '二')[phase]} Lv.1"
                )
            elif mid == "skill7":
                label = "基础技能升至 7 级"
            else:
                module = next(
                    (m for m in definition.get("modules", []) if m["id"] == mid), {}
                )
                target = goal.get("target_level") or max(
                    (entry["level"] for entry in module.get("levels", [])), default=1
                )
                label = f"{module.get('name', mid)} · 模组 {target} 级"
        result.append(
            {
                **{
                    key: project[key]
                    for key in ("key", "char_id", "kind", "locked", "status", "reason")
                },
                "char_name": definition.get("name") or skill_def.get("name") or cid,
                "label": label,
                "profession": skill_def.get("profession")
                or definition.get("profession", ""),
                **(
                    {"plan_id": project["plan"].get("id")}
                    if project["kind"] == "skill"
                    else {"module_id": project["goal"]["module_id"]}
                ),
            }
        )
    return result


def prepared_project_reminders(
    box, skills, states, entries, goals, inventory, formulas, blocked=()
):
    """Report unfinished manual actions against reserved, finished inventory."""
    chars = {char["id"]: char for char in box.get("characters", [])}
    definitions = growth_data(skills).get("characters", {})
    reminders = []
    for state in states:
        if state["locked"] or not state["materials_prepared"]:
            continue
        cid = state["char_id"]
        char, definition = chars[cid], definitions.get(cid, {})
        current = (char.get("evolvePhase", 0), char.get("level", 1))
        actions = []
        if state["kind"] == "skill":
            plan = state["plan"]
            levels = char.get("skills", [])
            index = plan["skill_index"]
            level = (levels[index].get("level") or 0) if index < len(levels) else 0
            if level >= plan.get("target_level", 3):
                continue
            if current < (2, 1):
                actions.append("待精英化至精二 Lv.1")
            if char.get("mainSkillLevel", 0) < 7:
                actions.append("待基础技能升至 7 级")
        else:
            goal = state["goal"]
            mid = goal["module_id"]
            if mid in LEVEL_GOALS:
                phase, _ = level_goal_targets(definition)[mid]
                if current < (phase, 1):
                    actions.append(f"待精英化至精{('零', '一', '二')[phase]} Lv.1")
            elif mid == "skill7":
                if char.get("mainSkillLevel", 0) < 7:
                    if current < basic_skill_target(definition):
                        actions.append("待完成技能升级所需的精英化")
                    actions.append("待基础技能升至 7 级")
            else:
                level = next(
                    (
                        e.get("level", 0)
                        for e in char.get("equips", [])
                        if e["id"] == mid
                    ),
                    0,
                )
                module = next(
                    m for m in definition.get("modules", []) if m["id"] == mid
                )
                target = goal.get("target_level") or max(
                    (entry["level"] for entry in module.get("levels", [])), default=1
                )
                if level >= target:
                    continue
                if current < (module["elite"], module["level"]):
                    actions.append(
                        f"待达到模组开启等级 Lv.{module['level']}（升级资源另计）"
                    )
                actions.append("待开启模组" if level == 0 else "待升级模组")
        if actions:
            reminders.append({**state, "reason": "；".join(actions)})
    result = describe_projects(reminders, skills)

    # Pure leveling stays out of crafting order, but can have a manual reminder.
    reserved = Counter()
    for _, materials in entries:
        for material in materials:
            reserved[material["id"]] += material["count"]
    budget = MaterialBudget(skills, inventory, formulas, blocked_materials=blocked)
    for goal in goals:
        cid, mid = goal["char_id"], goal["module_id"]
        if mid not in LEVEL_GOALS or cid not in chars:
            continue
        char = chars[cid]
        target = level_goal_targets(definitions.get(cid, {})).get(mid)
        current = (char.get("evolvePhase", 0), char.get("level", 1))
        if not target or current[0] != target[0] or current >= target:
            continue
        total = reserved.copy()
        for _, materials in material_entries(box, skills, [], [goal]):
            for material in materials:
                total[material["id"]] += material["count"]
        summary = calculate_growth_materials(
            budget, [{"id": iid, "count": count} for iid, count in total.items()]
        )
        if summary["available"]:
            reserved = total
            result.append(
                {
                    "key": f"goal:{cid}:{mid}",
                    "char_id": cid,
                    "char_name": definitions.get(cid, {}).get("name") or cid,
                    "kind": "goal",
                    "locked": False,
                    "status": "ready",
                    "label": f"精{('零', '一', '二')[target[0]]} Lv.{target[1]}",
                    "reason": "龙门币与经验已备齐，待手动升级",
                }
            )
    return result


def validate_order(order, projects):
    if not isinstance(order, list) or any(not isinstance(key, str) for key in order):
        raise ValueError("养成顺序格式错误")
    keys = [project["key"] for project in projects]
    if len(order) != len(keys) or set(order) != set(keys):
        raise ValueError("养成项目已变化，请刷新养成计划后重试")
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
    plans, goals = get_all_plans(), load_goals()
    if not plans and not goals:
        return {
            "items": [],
            "planning_items": [],
            "prepared_items": [],
            "custom": bool(order),
        }
    box = json.loads(get_path("@app/tmp/cultivate.json").read_text("utf-8"))["data"]
    skills = growth_resources(get_skill_data())
    projects = crafting_projects(plans, goals, order, box=box, skills=skills)
    inventory = inventory_counts(box, skills, local=True)
    blocked = protected_workshop_materials()
    states, entries = prepare_project_materials(
        box,
        skills,
        projects,
        inventory,
        workshop_formula,
        blocked,
    )
    crafting_states = {state["key"]: state for state in states}
    planning_states = []
    for project in crafting_projects(plans, goals, order):
        state = crafting_states.get(project["key"])
        if state is None:
            state = {
                **project,
                "status": "manual",
                "reason": "纯等级提升，不需要合成",
            }
        planning_states.append(state)
    planning_items = describe_projects(planning_states, skills, planning=True)
    for item in planning_items:
        item["crafting_required"] = item["key"] in crafting_states
    return {
        "items": describe_projects(states, skills),
        "planning_items": planning_items,
        "prepared_items": prepared_project_reminders(
            box, skills, states, entries, goals, inventory, workshop_formula, blocked
        ),
        "custom": bool(order),
    }


def save_planning_order(order, projects):
    """Preserve the previous configuration if either durable order write fails."""
    from arknights_mower.utils import config
    from arknights_mower.utils.mastery_db import reordered_plan_priorities
    from arknights_mower.utils.workshop_config import save_conf

    previous = config.conf
    conf = previous.model_copy(deep=True)
    conf.growth_crafting_order = order
    if not order:
        save_conf(conf)
        return
    skill_keys = {row["key"] for row in projects if row["kind"] == "skill"}
    locked_keys = {row["key"] for row in projects if row["locked"]}
    try:
        with reordered_plan_priorities(
            [key for key in order if key in skill_keys], locked_keys
        ):
            save_conf(conf)
    except Exception:
        if config.conf is not previous:
            save_conf(previous)
        raise
