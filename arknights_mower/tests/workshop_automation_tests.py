"""Real scan/API lifecycle: one durable manual backup, safe automatic restore."""

import json
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.workshop_plan_fixtures import next_skill as next_skill
from arknights_mower.utils import config, mastery_db
from arknights_mower.utils import mastery_recommendation as rec
from arknights_mower.utils import workshop_automation as auto
from arknights_mower.utils import workshop_config as state
from arknights_mower.utils.config.conf import RIICPart

_real_save_conf = config.save_conf


def manual_setting():
    return RIICPart.WorkShopSetting(
        operator="空爆",
        items=[
            {
                "item_names": ["碳素组"],
                "children_lower_limit": 18,
                "self_upper_limit": 32,
            }
        ],
    )


@pytest.fixture
def scan(next_skill, monkeypatch):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    monkeypatch.setattr(mastery_db, "retry_failed_plans", lambda: 0)
    monkeypatch.setattr(rec, "auto_schedule_mastery_tasks", lambda: {"scheduled": []})
    config.conf.workshop_settings = [manual_setting()]
    solver = object.__new__(BaseSchedulerSolver)
    solver._dispatch_scan_start_tasks = MagicMock()
    return solver._auto_schedule_mastery_after_scan


@pytest.mark.parametrize("enabled", [True, False])
def test_real_scan_retains_manual_carbon_without_plans(next_skill, scan, enabled):
    next_skill.plans.clear()
    config.conf.enable_mastery = enabled
    scan()
    assert config.conf.workshop_settings == [manual_setting()]
    assert not config.conf.workshop_auto_active


def test_disabled_mastery_does_not_take_over_even_with_plans(next_skill, scan):
    config.conf.enable_mastery = False
    scan()
    assert config.conf.workshop_settings == [manual_setting()]
    assert not config.conf.workshop_auto_active


def test_repeated_button_scan_and_restart_never_replace_original_backup(
    next_skill, scan
):
    import server

    scan()
    assert config.conf.workshop_manual_backup == [manual_setting()]
    first_generation = config.conf.workshop_generation
    config.conf = config.Conf.model_validate_json(config.conf.model_dump_json())
    for _ in range(3):
        response = server.app.test_client().post(
            "/workshop-auto-config", json={"book_operators": ["赫拉格"]}
        )
        assert response.status_code == 200
        assert response.json["automatic"]
        scan()
        assert config.conf.workshop_manual_backup == [manual_setting()]
    assert config.conf.workshop_generation == first_generation
    next_skill.plans.clear()
    scan()
    assert config.conf.workshop_settings == [manual_setting()]
    assert not config.conf.workshop_auto_active
    assert config.conf.workshop_generation > first_generation


def test_temporarily_empty_lookahead_keeps_backup_until_queue_is_finished(
    next_skill, scan
):
    scan()
    next_skill.plans[:] = [next_skill.plans[1]]
    next_skill.plans[0].update(status="training", expires_at="2999-01-01 00:00:00")
    scan()
    assert config.conf.workshop_settings == []
    assert config.conf.workshop_manual_backup == [manual_setting()]
    next_skill.plans.clear()
    auto.restore_if_no_plans()
    assert config.conf.workshop_settings == [manual_setting()]


@pytest.mark.parametrize("book_count,restored", [(7, False), (11, False), (12, True)])
def test_restore_only_when_whole_queue_materials_are_ready(
    next_skill, scan, book_count, restored
):
    scan()
    next_skill.cultivate.write_text(
        json.dumps(
            {"data": {"characters": [], "items": [{"id": "3303", "count": book_count}]}}
        )
    )
    scan()
    assert (not config.conf.workshop_auto_active) == restored
    if restored:
        assert config.conf.workshop_settings == [manual_setting()]


@pytest.mark.parametrize("legacy_object", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_legacy_preset_is_the_first_backup_and_is_imported_only_once(
    next_skill, legacy_object, empty
):
    saved = [] if empty else [manual_setting().model_dump()]
    data = {"settings": saved, "t5_operators": ["年"]} if legacy_object else saved
    state.get_path("").write_text(json.dumps(data))
    # This may already be an old unmarked automatic config; never save it over
    # the explicitly saved legacy preset.
    config.conf.workshop_settings = [RIICPart.WorkShopSetting(operator="赫拉格")]
    auto.update_workshop_config()
    assert [s.model_dump() for s in config.conf.workshop_manual_backup] == saved
    next_skill.plans.clear()
    auto.update_workshop_config()
    assert [s.model_dump() for s in config.conf.workshop_settings] == saved
    config.conf.workshop_settings = [RIICPart.WorkShopSetting(operator="年")]
    auto.update_workshop_config()
    assert config.conf.workshop_settings[0].operator == "年"


def test_empty_original_config_is_a_valid_snapshot(next_skill):
    auto.update_workshop_config()
    assert config.conf.workshop_manual_backup == []
    auto.update_workshop_config()
    assert config.conf.workshop_manual_backup == []
    next_skill.plans.clear()
    auto.update_workshop_config()
    assert config.conf.workshop_settings == []
    assert not config.conf.workshop_auto_active


def test_missing_recommendation_is_not_completion(next_skill, scan, monkeypatch):
    scan()
    monkeypatch.setattr(rec, "get_mastery_recommendations", lambda: {"has_data": False})
    scan()
    assert config.conf.workshop_manual_backup == [manual_setting()]


def test_failed_save_leaves_both_manual_config_and_backup_untouched(
    next_skill, monkeypatch
):
    config.conf.workshop_settings = [manual_setting()]
    previous = config.conf
    monkeypatch.setattr(
        config, "save_conf", MagicMock(side_effect=OSError("disk full"))
    )
    with pytest.raises(OSError):
        auto.update_workshop_config()
    assert config.conf is previous
    assert config.conf.workshop_settings == [manual_setting()]
    assert not config.conf.workshop_auto_active


def test_stale_autosaves_cannot_reset_backup_or_resurrect_generated_config(
    next_skill, scan
):
    import server

    client = server.app.test_client()
    old_manual = config.conf.model_dump()
    scan()
    assert client.post("/conf", json=old_manual).status_code == 200
    assert config.conf.workshop_manual_backup == [manual_setting()]
    assert config.conf.workshop_settings[0].source == "mastery"
    old_auto = config.conf.model_dump()
    old_auto["workshop_settings_generation"] = config.conf.workshop_generation
    next_skill.plans.clear()
    scan()
    assert client.post("/conf", json=old_auto).status_code == 200
    assert not config.conf.workshop_auto_active
    assert config.conf.workshop_settings == [manual_setting()]


def test_disabling_mastery_restores_in_the_same_config_save(next_skill, scan):
    import server

    scan()
    req = config.conf.model_dump()
    req.update(enable_mastery=False, workshop_manual_backup=[])
    assert server.app.test_client().post("/conf", json=req).status_code == 200
    assert not config.conf.workshop_auto_active
    assert config.conf.workshop_settings == [manual_setting()]


def test_legacy_save_api_cannot_overwrite_automatic_backup(next_skill):
    import server

    assert server.app.test_client().post("/workshop-preset", json=[]).status_code == 405


def test_queued_automatic_task_is_invalid_after_restore(next_skill, scan):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    scan()
    task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="赫拉格")
    auto.stamp_workshop_task(task)
    assert auto.workshop_task_current(task)
    next_skill.plans.clear()
    scan()
    solver = object.__new__(BaseSchedulerSolver)
    solver.task = task
    solver.enter_room = MagicMock()
    solver.craft_material()
    solver.enter_room.assert_not_called()


def test_backup_and_source_survive_real_config_file_reload(
    next_skill, tmp_path, monkeypatch
):
    monkeypatch.setattr(config, "conf_path", tmp_path / "conf.yml")
    monkeypatch.setattr(config, "save_conf", _real_save_conf)
    config.conf.workshop_settings = [manual_setting()]
    auto.update_workshop_config()
    config.conf = config.Conf()
    config.load_conf()
    assert config.conf.workshop_manual_backup == [manual_setting()]
    assert config.conf.workshop_settings[0].source == "mastery"
    next_skill.plans.clear()
    auto.update_workshop_config()
    config.load_conf()
    assert config.conf.workshop_settings == [manual_setting()]
    assert not config.conf.workshop_auto_active


def test_corrupt_legacy_backup_does_not_overwrite_either_file_or_settings(next_skill):
    config.conf.workshop_settings = [manual_setting()]
    path = state.get_path("")
    path.write_text("not-json")
    result = auto.update_workshop_config()
    assert result["workshop_preset_warning"]
    assert path.read_text() == "not-json"
    assert config.conf.workshop_settings == [manual_setting()]
    assert not config.conf.workshop_auto_active
