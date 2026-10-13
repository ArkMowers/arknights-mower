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

_refresh_error = None


def refresh_workshop_after_inventory_change():
    """Consume committed changes at a scheduler boundary, preserving concurrent writes."""
    from arknights_mower.solvers.record import (
        battle_inventory_active,
        workshop_inventory_changed,
    )

    global _refresh_error
    with workshop_lock:
        if not workshop_inventory_changed.is_set():
            return _refresh_error is None
        if battle_inventory_active.is_set() or config.stop_mower.is_set():
            return False
        workshop_inventory_changed.clear()
        if not (config.conf.enable_mastery or config.conf.workshop_auto_active):
            _refresh_error = None
            return True
        try:
            update_workshop_config()
            _refresh_error = None
            return True
        except Exception:
            _refresh_error = "合成缺口重算失败，等待下次调度重试"
            workshop_inventory_changed.set()
            logger.exception(_refresh_error)
            conf = config.conf.model_copy(deep=True)
            if conf.workshop_auto_active and conf.workshop_settings:
                conf.workshop_settings = []
                conf.workshop_generation += 1
                try:
                    save_conf(conf)
                except Exception:
                    logger.exception("暂停加工配置保存失败，本次运行继续阻止加工")
            return False


def calculate_workshop_plan(conf, *, local_stock=None, **operators):
    """Read one local growth projection for configuration and status consumers."""
    from arknights_mower.data import workshop_formula
    from arknights_mower.utils import mastery_recommendation as rec
    from arknights_mower.utils.growth import (
        _lock,
        growth_resources,
        inventory_counts,
        load_goals,
    )
    from arknights_mower.utils.growth_workshop import (
        GrowthWorkshopPlan,
        growth_workshop_config,
    )
    from arknights_mower.utils.mastery_db import get_all_plans
    from arknights_mower.utils.workshop_material_policy import (
        protected_workshop_materials,
    )

    with _lock:
        plans, goals = get_all_plans(), load_goals()
        if not plans and not goals:
            return GrowthWorkshopPlan()
        path = rec.get_path("@app/tmp/cultivate.json")
        if not path.exists():
            raise ValueError("尚无干员与材料数据，请读取仓库")
        box = json.loads(path.read_text(encoding="utf-8"))["data"]
        skills = growth_resources(rec.get_skill_data())
        return growth_workshop_config(
            box,
            skills,
            plans,
            goals,
            inventory_counts(box, skills, local=True, local_counts=local_stock),
            workshop_formula,
            {
                key: operators.get(key, getattr(conf, key))
                for key in ("fodder_operators", "t5_operators", "book_operators")
            },
            protected_workshop_materials(),
            order=conf.growth_crafting_order,
        )


def update_workshop_config(*, explicit=False, **operators):
    """Take over once, retain the backup while waiting, restore on completion."""
    global _refresh_error
    with workshop_lock:
        conf = config.conf.model_copy(deep=True)
        warning = initialize_manual_settings(conf)
        if warning:
            return {
                **workshop_state(conf, warning),
                "restored": False,
                "t3_summary": [],
            }
        enabled = conf.enable_mastery or explicit or conf.workshop_auto_active
        result = calculate_workshop_plan(conf, **operators) if enabled else None
        settings = result.settings if result else []
        focus = result.focus if result else None
        ready = focus is None
        restored = False
        if ready:
            restored = restore_manual_settings(conf)
        else:
            if settings and not conf.workshop_auto_active:
                conf.workshop_auto_active = True
                conf.workshop_generation += 1
            if conf.workshop_auto_active:
                generated = make_settings(settings, "mastery")
                if generated != conf.workshop_settings:
                    conf.workshop_settings = generated
                    conf.workshop_generation += 1
        save_conf(conf)
        _refresh_error = None
        return {
            **workshop_state(conf),
            "restored": restored,
            "t3_summary": [],
            "focus_char_id": focus["char_id"] if focus else None,
            "pending": focus is not None,
        }


def refresh_workshop_after_plan_change():
    """Invalidate old quotas immediately when an active growth plan is edited."""
    from arknights_mower.solvers.record import workshop_inventory_changed

    with workshop_lock:
        if not config.conf.workshop_auto_active:
            return
        workshop_inventory_changed.set()
        refresh_workshop_after_inventory_change()


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
        if not refresh_workshop_after_inventory_change():
            return None
        restore_if_no_plans()
        if not workshop_task_current(task):
            return None
        # Bind at acquisition, including RELEASE_DORM and direct/unmarked calls.
        # A stale queued WORKSHOP task must still fail before acquiring a new epoch.
        return WorkshopSnapshot(
            [entry.model_copy(deep=True) for entry in config.conf.workshop_settings],
            config.conf.workshop_generation,
        )
