"""Persist one manual snapshot for an automatic mastery crafting session."""

import json
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


def update_workshop_config(*, explicit=False, **operators):
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
        from arknights_mower.data import workshop_formula
        from arknights_mower.utils.growth import (
            growth_resources,
            inventory_counts,
            load_goals,
        )
        from arknights_mower.utils.growth_workshop import growth_workshop_config
        from arknights_mower.utils.workshop_material_policy import (
            protected_workshop_materials,
        )

        enabled = conf.enable_mastery or explicit or conf.workshop_auto_active
        plans = get_all_plans() if enabled else []
        goals = load_goals() if enabled else []
        ready = not plans and not goals
        settings = None
        focus = None
        if plans or goals:
            path = rec.get_path("@app/tmp/cultivate.json")
            if path.exists():
                box = json.loads(path.read_text(encoding="utf-8"))["data"]
                skills = growth_resources(rec.get_skill_data())
                stock = inventory_counts(box, skills, local=True)
                settings, focus = growth_workshop_config(
                    box,
                    skills,
                    plans,
                    goals,
                    stock,
                    workshop_formula,
                    {
                        key: operators.get(key, getattr(conf, key))
                        for key in (
                            "fodder_operators",
                            "t5_operators",
                            "book_operators",
                        )
                    },
                    protected_workshop_materials(),
                )
                # Readiness means remaining craftable demands are covered. Gold,
                # chips and module tokens remain visible in the material overview.
                ready = focus is None
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
        return {
            **workshop_state(conf),
            "restored": restored,
            "t3_summary": [],
            "focus_char_id": focus,
            "pending": focus is not None,
        }


def refresh_workshop_after_plan_change():
    """Invalidate old quotas immediately when an active growth plan is edited."""
    with workshop_lock:
        if not config.conf.workshop_auto_active:
            return
        try:
            update_workshop_config()
        except Exception:
            logger.exception("养成计划已保存，但合成缺口重算失败，暂停旧加工配置")
            conf = config.conf.model_copy(deep=True)
            conf.workshop_settings = []
            conf.workshop_generation += 1
            save_conf(conf)


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
        from arknights_mower.utils.growth import load_goals

        if plans or load_goals():
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
