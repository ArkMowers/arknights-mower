"""Confirmed crafting admits mastery without waiting for another depot scan."""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.solvers import record
from arknights_mower.utils import (
    config,
    mastery_db,
    mastery_recommendation,
    workshop_automation,
    workshop_limits,
    workshop_mood,
)
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.scheduler_task import TaskTypes


@pytest.fixture
def crafting(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=True))
    db_path = tmp_path / "data.db"
    monkeypatch.setattr(
        record,
        "get_path",
        lambda value: db_path if value.endswith("data.db") else tmp_path,
    )
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(mastery_db, "get_path", record.get_path)
    monkeypatch.setattr(mastery_db, "_tables_created", set())
    record.save_inventory_counts({"技巧概要·卷3": 0, "技巧概要·卷2": 30})
    plan_id = mastery_db.insert_plan(
        "char_fixture", 0, 3, char_name="测试干员", skill_name="测试技能"
    )
    assert plan_id > 0
    cloud = tmp_path / "cultivate.json"
    cloud.write_text(
        json.dumps(
            {
                "data": {
                    "items": [{"id": "3303", "count": 0}, {"id": "3302", "count": 30}]
                }
            }
        )
    )
    skills = tmp_path / "skill_data.json"
    skills.write_text(
        json.dumps(
            {
                "items": {
                    "3303": {"name": "技巧概要·卷3"},
                    "3302": {"name": "技巧概要·卷2"},
                }
            }
        )
    )
    monkeypatch.setattr(mastery_recommendation, "get_path", lambda _: cloud)
    monkeypatch.setattr(mastery_recommendation, "_find_skill_data", lambda: skills)
    recommendations = {
        "has_data": True,
        "operators": [
            {
                "char_id": "char_fixture",
                "name": "测试干员",
                "profession": "CASTER",
                "recommendations": [
                    {
                        "skill_index": 0,
                        "skill_name": "测试技能",
                        "current_level": 0,
                        "chain_needed_materials": [
                            {"name": "技巧概要·卷3", "count": 2}
                        ],
                    }
                ],
            }
        ],
    }
    monkeypatch.setattr(
        mastery_recommendation, "get_mastery_recommendations", lambda: recommendations
    )
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
        lambda _: None,
    )
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    monkeypatch.setattr(workshop_limits, "blocked_workshop_recipes", lambda _: set())
    monkeypatch.setattr(workshop_mood, "operator_mood_rules", lambda _: ([], True))
    monkeypatch.setattr(
        "arknights_mower.utils.workshop_recommendation.scope_workshop_items",
        lambda _, items, __: items,
    )
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.task = None
    solver.tasks = []
    solver.recog = MagicMock(w=1920, h=1080)
    solver.op_data = SimpleNamespace(operators={"赫拉格": SimpleNamespace(mood=24)})
    for method in (
        "tap",
        "back",
        "sleep",
        "enter_room",
        "back_to_infrastructure",
        "swipe_noinertia",
    ):
        setattr(solver, method, MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.item_valid = MagicMock(return_value=True)
    solver.item_list = MagicMock(
        return_value=[("技巧概要·卷3", ((10, 10), (20, 20)), True)]
    )
    errors = MagicMock()
    monkeypatch.setattr(base, "save_exception", errors)
    notify = MagicMock()
    monkeypatch.setattr(base, "send_message", notify)
    update = MagicMock()
    monkeypatch.setattr(workshop_automation, "update_workshop_config", update)

    def run(target=2, confirmed=True):
        item = WorkShopItem(
            item_names=["技巧概要·卷3"], self_upper_limit=target, children_lower_limit=0
        )
        snapshot = workshop_automation.WorkshopSnapshot(
            [RIICPart.WorkShopSetting(operator="赫拉格", items=[item])],
            config.conf.workshop_generation,
        )
        solver.factory_scene = MagicMock(
            side_effect=[
                base.Scene.FACTORY_DASHBOARD,
                base.Scene.FACTORY_DASHBOARD,
                base.Scene.FACTORY_FORMULA,
                base.Scene.FACTORY_DASHBOARD,
                *(
                    [base.Scene.FACTORY_PRODUCT_COLLECT]
                    if confirmed
                    else [base.Scene.UNKNOWN] * 11
                ),
            ]
        )
        return solver.generate_product("赫拉格", snapshot=snapshot)

    return SimpleNamespace(
        solver=solver,
        run=run,
        plan_id=plan_id,
        recommendations=recommendations,
        errors=errors,
        notify=notify,
        update=update,
    )


def upgrades(crafting):
    return [t for t in crafting.solver.tasks if t.type == TaskTypes.SKILL_UPGRADE]


def test_confirmed_output_dispatches_once_before_next_scan(crafting):
    before = datetime.now()
    crafting.run()
    tasks = upgrades(crafting)
    assert len(tasks) == 1
    assert tasks[0].plan_key == str(crafting.plan_id)
    assert tasks[0].step_level == 1
    assert before <= tasks[0].time <= datetime.now()
    assert record.get_inventory_counts()["技巧概要·卷3"] == 2
    # A later confirmed batch reuses the existing task for this idle plan.
    crafting.run(target=3)
    assert upgrades(crafting) == tasks
    assert mastery_db.get_plan_by_id(crafting.plan_id)["status"] == "idle"
    crafting.errors.assert_not_called()


def test_partial_preparation_waits_for_all_target_costs(crafting):
    crafting.run(target=1)
    assert upgrades(crafting) == []
    crafting.run(target=2)
    assert len(upgrades(crafting)) == 1


def test_disabled_mastery_keeps_confirmed_output_without_dispatch(crafting):
    config.conf.enable_mastery = False
    crafting.run()
    assert record.get_inventory_counts()["技巧概要·卷3"] == 2
    assert upgrades(crafting) == []


def test_unconfirmed_batch_never_dispatches_or_retains_predicted_output(crafting):
    assert crafting.run(confirmed=False) is False
    assert "技巧概要·卷3" not in record.get_inventory_counts()
    assert upgrades(crafting) == []
    crafting.notify.assert_called_once()


def test_dispatch_failure_does_not_invalidate_confirmed_batch(crafting):
    crafting.solver._dispatch_scan_start_tasks = MagicMock(
        side_effect=ValueError("queue")
    )
    crafting.run()
    crafting.solver._dispatch_scan_start_tasks.assert_called_once()
    assert record.get_inventory_counts()["技巧概要·卷3"] == 2
    crafting.notify.assert_not_called()
    crafting.errors.assert_not_called()


def test_consumed_or_unknown_stock_never_uses_cloud_fallback(crafting):
    cloud = mastery_recommendation.get_path("@app/tmp/cultivate.json")
    cloud.write_text(
        json.dumps(
            {
                "data": {
                    "items": [{"id": "3303", "count": 20}, {"id": "3302", "count": 30}]
                }
            }
        )
    )
    needed = crafting.recommendations["operators"][0]["recommendations"][0][
        "chain_needed_materials"
    ]
    needed.append({"name": "技巧概要·卷2", "count": 25})
    crafting.run()
    assert record.get_inventory_counts()["技巧概要·卷2"] == 24
    assert upgrades(crafting) == []
    record.invalidate_workshop_inventory(["技巧概要·卷2"])
    assert (
        mastery_recommendation.auto_schedule_mastery_tasks(
            inventory=record.get_inventory_counts()
        )["scheduled"]
        == []
    )
    assert (
        mastery_recommendation.auto_schedule_mastery_tasks(inventory={})["scheduled"]
        == []
    )


def test_restoring_manual_crafting_does_not_drop_ready_training(crafting):
    config.conf.workshop_auto_active = True

    def restore():
        config.conf.workshop_auto_active = False
        config.conf.workshop_generation += 1

    crafting.update.side_effect = restore
    crafting.run()
    assert len(upgrades(crafting)) == 1
    crafting.update.assert_called_once()
    assert not config.conf.workshop_auto_active


@pytest.mark.parametrize("blocked", ["prerequisite", "schedule"])
def test_confirmed_materials_retain_training_admission_checks(
    crafting, monkeypatch, blocked
):
    if blocked == "prerequisite":
        crafting.recommendations["operators"][0]["mastery_error"] = "尚未精二"
    else:
        monkeypatch.setattr(
            "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
            lambda _: "非训练室排班占用",
        )
    crafting.run()
    assert upgrades(crafting) == []
    assert record.get_inventory_counts()["技巧概要·卷3"] == 2
