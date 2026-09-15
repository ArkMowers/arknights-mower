"""The editable manual table survives scans, takeovers and concurrent saves."""

import json
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.workshop_automation_tests import manual_setting
from arknights_mower.tests.workshop_plan_fixtures import next_skill as next_skill
from arknights_mower.utils import config
from arknights_mower.utils import workshop_automation as auto
from arknights_mower.utils import workshop_config as state


def payload():
    data = state.read_user_config()
    data["workshop_manual_settings_revision"] = data["workshop_manual_revision"]
    return data


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("saved", [[], [{"operator": "年", "items": []}]])
def test_legacy_form_is_visible_without_changing_runtime_before_takeover(
    next_skill, enabled, saved
):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    next_skill.plans.clear()
    config.conf.enable_mastery = enabled
    config.conf.workshop_settings = [manual_setting()]
    state.get_path("").write_text(json.dumps(saved))
    data = payload()
    assert [s["operator"] for s in data["workshop_manual_settings"]] == [
        s["operator"] for s in saved
    ]
    solver = object.__new__(BaseSchedulerSolver)
    solver._dispatch_scan_start_tasks = MagicMock()
    for _ in range(2):
        solver._auto_schedule_mastery_after_scan()
        state.save_user_config(data)  # An unrelated autosave is not a manual edit.
        assert config.conf.workshop_settings == [manual_setting()]
        assert not config.conf.workshop_auto_active


@pytest.mark.parametrize("cleared", [False, True])
def test_form_open_before_takeover_edits_backup_and_restores_latest_edit(
    next_skill, cleared
):
    import server

    config.conf.workshop_settings = [manual_setting()]
    req = payload()
    auto.update_workshop_config()
    running = config.conf.workshop_settings
    generation = config.conf.workshop_generation
    edited = [] if cleared else [{"operator": "年", "items": [], "enabled": False}]
    req["workshop_manual_settings"] = edited
    # These backend-owned fields cannot be overwritten by a browser.
    req.update(
        workshop_settings=[], workshop_manual_backup=[], workshop_auto_active=False
    )
    response = server.app.test_client().post("/conf", json=req)
    assert response.status_code == 200
    assert not response.json["workshop_manual_conflict"]
    assert config.conf.workshop_settings == running
    assert config.conf.workshop_generation == generation
    assert config.conf.workshop_auto_active
    expected = state.settings(edited, "manual")
    assert config.conf.workshop_manual_backup == expected
    auto.update_workshop_config()
    assert config.conf.workshop_manual_backup == expected
    next_skill.plans.clear()
    auto.restore_if_no_plans()
    assert config.conf.workshop_settings == expected
    assert config.conf.workshop_manual_backup == expected
    assert not config.conf.workshop_auto_active


def test_edit_when_idle_updates_runtime_and_cannot_be_replaced_by_old_tab(next_skill):
    first, old = payload(), payload()
    first["workshop_manual_settings"] = [manual_setting().model_dump()]
    response = state.save_user_config(first)
    assert not response["workshop_manual_conflict"]
    assert config.conf.workshop_settings == [manual_setting()]
    old["workshop_manual_settings"] = [{"operator": "年"}]
    old["drone_interval"] = 9
    response = state.save_user_config(old)
    assert response["workshop_manual_conflict"]
    assert config.conf.workshop_manual_backup == [manual_setting()]
    assert config.conf.workshop_settings == [manual_setting()]
    assert config.conf.drone_interval == 9


def test_edit_during_restore_uses_manual_revision_not_runtime_generation(next_skill):
    config.conf.workshop_settings = [manual_setting()]
    auto.update_workshop_config()
    req = payload()
    next_skill.plans.clear()
    auto.restore_if_no_plans()
    req["workshop_manual_settings"] = []
    state.save_user_config(req)
    assert config.conf.workshop_settings == []
    assert config.conf.workshop_manual_backup == []
    assert not config.conf.workshop_auto_active


def test_old_active_backup_migrates_and_can_still_restore():
    old = config.Conf().model_dump()
    old.pop("workshop_auto_active")
    old["workshop_manual_backup"] = []
    conf = config.Conf(**old)
    assert conf.workshop_auto_active
    assert state.restore_manual_settings(conf)
    assert not conf.workshop_auto_active


def test_initialized_form_remains_inactive_after_config_reload(
    next_skill, tmp_path, monkeypatch
):
    from arknights_mower.tests.workshop_automation_tests import _real_save_conf

    monkeypatch.setattr(config, "conf_path", tmp_path / "conf.yml")
    monkeypatch.setattr(config, "save_conf", _real_save_conf)
    config.conf.workshop_settings = [manual_setting()]
    state.get_path("").write_text("[]")
    state.read_user_config()
    config.load_conf()
    assert not config.conf.workshop_auto_active
    assert config.conf.workshop_manual_backup == []
    assert config.conf.workshop_settings == [manual_setting()]


def test_edited_backup_is_persisted_across_restart(next_skill, tmp_path, monkeypatch):
    from arknights_mower.tests.workshop_automation_tests import _real_save_conf

    monkeypatch.setattr(config, "conf_path", tmp_path / "conf.yml")
    monkeypatch.setattr(config, "save_conf", _real_save_conf)
    auto.update_workshop_config()
    req = payload()
    req["workshop_manual_settings"] = [manual_setting().model_dump()]
    state.save_user_config(req)
    config.load_conf()
    assert config.conf.workshop_auto_active
    assert config.conf.workshop_manual_backup == [manual_setting()]
    next_skill.plans.clear()
    auto.restore_if_no_plans()
    config.load_conf()
    assert not config.conf.workshop_auto_active
    assert config.conf.workshop_manual_backup == config.conf.workshop_settings
