"""Finished BOX targets cannot leave stale automatic workshop jobs running."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import config, mastery_db, scheduler_task, workshop_data
from arknights_mower.utils import workshop_automation as auto
from arknights_mower.utils.config.conf import RIICPart


@pytest.fixture
def finished_queue(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", MagicMock())
    monkeypatch.setattr(mastery_db, "_tables_created", set())
    monkeypatch.setattr(
        mastery_db,
        "get_path",
        lambda name: tmp_path / "data.db" if name.endswith("data.db") else tmp_path,
    )
    manual = RIICPart.WorkShopSetting(operator="赫拉格", items=[])
    config.conf.workshop_manual_backup = [manual]
    config.conf.workshop_preset_migrated = True
    config.conf.enable_mastery = True
    config.conf.workshop_auto_active = True
    config.conf.workshop_generation = 10
    config.conf.workshop_settings = [
        RIICPart.WorkShopSetting(operator="蜜莓", source="mastery")
    ]
    ids = [
        mastery_db.insert_plan(
            "char_test", 1, 3, char_name="测试干员", skill_name="二技能·测试"
        )
        for _ in range(2)
    ]
    assert all(plan_id > 0 for plan_id in ids)
    roster = [{"id": "char_test", "skills": [{"level": 0}, {"level": 3}]}]
    monkeypatch.setattr(workshop_data, "owned_roster", lambda: roster)
    task = scheduler_task.SchedulerTask(
        task_type=scheduler_task.TaskTypes.WORKSHOP, meta_data="蜜莓"
    )
    auto.stamp_workshop_task(task)
    return SimpleNamespace(ids=ids, roster=roster, task=task, manual=manual)


@pytest.mark.parametrize("entry", ["restore", "snapshot", "schedule"])
def test_completed_duplicate_idle_plans_restore_manual_and_invalidate_old_workshop_task(
    finished_queue, monkeypatch, entry
):
    q = finished_queue
    snapshot = auto.WorkshopSnapshot(config.conf.workshop_settings, 10)
    if entry == "restore":
        auto.restore_if_no_plans()
    elif entry == "snapshot":
        assert auto.workshop_task_snapshot(q.task) is None
    else:
        monkeypatch.setattr(scheduler_task, "get_inventory_counts", lambda: {})
        tasks = []
        scheduler_task.try_workshop_tasks(SimpleNamespace(operators={}), tasks)
        assert tasks == []
    assert mastery_db.get_all_plans() == []
    assert all(mastery_db.get_plan_by_id(i)["status"] == "completed" for i in q.ids)
    assert config.conf.workshop_settings == [q.manual]
    assert config.conf.workshop_manual_backup == [q.manual]
    assert not config.conf.workshop_auto_active
    assert not snapshot.is_current()
    assert not auto.workshop_task_current(q.task)
    generation = config.conf.workshop_generation
    auto.restore_if_no_plans()
    assert config.conf.workshop_generation == generation


@pytest.mark.parametrize("level", [None, 0, 2, True, "3", 4])
def test_missing_invalid_or_unfinished_levels_do_not_complete_plans(
    finished_queue, level
):
    finished_queue.roster[0]["skills"][1]["level"] = level
    auto.restore_if_no_plans()
    assert len(mastery_db.get_all_plans()) == 2
    assert config.conf.workshop_auto_active
    assert auto.workshop_task_current(finished_queue.task)


def test_unavailable_box_keeps_pending_plans_and_backup(finished_queue, monkeypatch):
    def unavailable():
        raise workshop_data.WorkshopRecommendationError("缺少 BOX")

    monkeypatch.setattr(workshop_data, "owned_roster", unavailable)
    auto.restore_if_no_plans()
    assert len(mastery_db.get_all_plans()) == 2
    assert config.conf.workshop_manual_backup == [finished_queue.manual]
    assert config.conf.workshop_auto_active


@pytest.mark.parametrize(
    "status", ["arranging", "training", "waiting_collect", "failed"]
)
def test_box_completion_does_not_overwrite_live_or_failed_plans(finished_queue, status):
    for plan_id in finished_queue.ids:
        mastery_db.update_plan_status(plan_id, status)
    assert mastery_db.complete_satisfied_idle_plans({("char_test", 1): 3}) == 0
    assert all(
        mastery_db.get_plan_by_id(i)["status"] == status for i in finished_queue.ids
    )


def test_finishing_one_skill_recalculates_remaining_automatic_work(
    finished_queue, monkeypatch
):
    other = mastery_db.insert_plan(
        "char_other", 0, 3, char_name="另一个干员", skill_name="一技能·测试"
    )
    recalculate = MagicMock()
    monkeypatch.setattr(auto, "update_workshop_config", recalculate)
    auto.restore_if_no_plans()
    assert [p["id"] for p in mastery_db.get_all_plans()] == [other]
    assert config.conf.workshop_manual_backup == [finished_queue.manual]
    assert config.conf.workshop_auto_active
    recalculate.assert_called_once_with()
