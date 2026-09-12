"""Persist one manual snapshot for an automatic mastery crafting session."""

import json
from collections import Counter
from dataclasses import dataclass

from arknights_mower.utils import config
from arknights_mower.utils.config.conf import RIICPart
from arknights_mower.utils.log import logger
from arknights_mower.utils.workshop_config import (
    initialize_manual_settings,
    restore_manual_settings,
    save_conf,
    workshop_lock,
    workshop_state,
)
from arknights_mower.utils.workshop_config import (
    settings as make_settings,
)


def _materials_ready(plans, recommendations):
    """Confirm the whole queue's remaining costs, without spending shared stock twice.

    Missing BOX/costs are unknown, never evidence that crafting has finished.
    This runs only after a depot scan or an explicit auto-config request.
    """
    from arknights_mower.utils import mastery_recommendation as rec

    if not recommendations.get("has_data"):
        return None
    path = rec.get_path("@app/tmp/cultivate.json")
    data = json.loads(path.read_text(encoding="utf-8"))["data"]
    names = rec.get_skill_data().get("items", {})
    inventory = Counter(
        {
            names.get(item["id"], {}).get("name", item["id"]): int(item["count"])
            for item in data["items"]
        }
    )
    levels = {
        (char["id"], index): skill.get("level", 0)
        for char in data["characters"]
        for index, skill in enumerate(char.get("skills", []))
    }
    skills = {
        (op["char_id"], skill["skill_index"]): skill
        for op in recommendations.get("operators", [])
        for skill in op.get("recommendations", [])
    }
    demand = Counter()
    for plan in plans:
        key = plan["char_id"], plan["skill_index"]
        if levels.get(key, 0) >= plan["target_level"]:
            continue
        skill = skills.get(key)
        if skill is None:
            return None
        stages = skill.get("stages")
        if stages:
            if rec._workshop_lookahead_active(plan):
                stages = stages[1:]  # This training step has already been paid.
            materials = [
                mat
                for stage in stages
                if stage["to_level"] - 7 <= plan["target_level"]
                for mat in stage.get("needed_materials", [])
            ]
        else:
            materials = skill.get("chain_needed_materials")
            if materials is None:
                return None
        for material in materials:
            demand[material["name"]] += material["count"]
    return all(inventory[name] >= count for name, count in demand.items())


def update_workshop_config(**operators):
    """Take over once, retain the backup while waiting, restore on completion."""
    from arknights_mower.utils import mastery_recommendation as rec
    from arknights_mower.utils.mastery_db import get_all_plans

    with workshop_lock:
        conf = config.conf.model_copy(deep=True)
        warning = initialize_manual_settings(conf)
        if warning:
            return {
                **workshop_state(conf, warning),
                "restored": False,
                "t3_summary": [],
            }
        plans = get_all_plans() if conf.enable_mastery else []
        ready = not plans
        settings = None
        if plans:
            recommendations = rec.get_mastery_recommendations()
            ready = _materials_ready(plans, recommendations)
            if ready is False:
                settings = rec.compute_workshop_config(
                    **{
                        key: operators.get(key, getattr(conf, key))
                        for key in (
                            "fodder_operators",
                            "t5_operators",
                            "book_operators",
                        )
                    },
                    plans=plans,
                    recommendations=recommendations,
                )
        restored = False
        if ready:
            restored = restore_manual_settings(conf)
        elif settings is not None:
            if settings and not conf.workshop_auto_active:
                conf.workshop_auto_active = True
                conf.workshop_generation += 1
            if conf.workshop_auto_active:
                generated = make_settings(settings, "mastery")
                if generated != conf.workshop_settings:
                    conf.workshop_settings = generated
                    conf.workshop_generation += 1
        save_conf(conf)
        return {**workshop_state(conf), "restored": restored, "t3_summary": []}


def restore_if_no_plans():
    from arknights_mower.utils.mastery_db import (
        complete_satisfied_idle_plans,
        get_all_plans,
    )
    from arknights_mower.utils.workshop_data import (
        WorkshopRecommendationError,
        owned_roster,
    )

    with workshop_lock:
        if not config.conf.workshop_auto_active:
            return
        plans = get_all_plans()
        waiting = {
            (p["char_id"], p["skill_index"]) for p in plans if p.get("status") == "idle"
        }
        if waiting:
            try:
                roster = owned_roster()
            except WorkshopRecommendationError:
                roster = []
            levels = {
                (char["id"], index): skill.get("level")
                for char in roster
                if isinstance(char.get("skills"), list)
                for index, skill in enumerate(char["skills"])
                if (char["id"], index) in waiting and isinstance(skill, dict)
            }
            if completed := complete_satisfied_idle_plans(levels):
                logger.info(
                    f"同步数据确认{completed}条待开始专精计划已达目标，标记完成"
                )
                plans = get_all_plans()
                if plans:
                    update_workshop_config()
        if plans:
            return
        conf = config.conf.model_copy(deep=True)
        restore_manual_settings(conf)
        save_conf(conf)
        logger.info("专精备料已结束，恢复手动合成配置并作废旧加工任务")


def stamp_workshop_task(task):
    if config.conf.workshop_auto_active:
        task.workshop_generation = config.conf.workshop_generation


def workshop_task_current(task):
    generation = getattr(task, "workshop_generation", None)
    return generation is None or (
        config.conf.workshop_auto_active
        and generation == config.conf.workshop_generation
    )


@dataclass(frozen=True)
class WorkshopSnapshot:
    settings: list[RIICPart.WorkShopSetting]
    generation: int

    def is_current(self):
        return self.generation == config.conf.workshop_generation


def workshop_task_snapshot(task):
    with workshop_lock:
        restore_if_no_plans()
        if not workshop_task_current(task):
            return None
        # Bind at acquisition, including RELEASE_DORM and direct/unmarked calls.
        # A stale queued WORKSHOP task must still fail before acquiring a new epoch.
        return WorkshopSnapshot(
            [entry.model_copy(deep=True) for entry in config.conf.workshop_settings],
            config.conf.workshop_generation,
        )
