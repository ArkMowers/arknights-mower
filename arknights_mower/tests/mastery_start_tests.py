"""Explicit mastery insertion acknowledges only a verified DB-backed queue task."""

import sys
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.utils import config, mastery_recommendation  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402
from arknights_mower.views import mastery  # noqa: E402


@pytest.fixture
def start_context(monkeypatch):
    from arknights_mower.utils import mastery_support_data

    scheduler = SimpleNamespace(tasks=[], task=None)
    main = SimpleNamespace(base_scheduler=scheduler)
    monkeypatch.setitem(sys.modules, "arknights_mower.__main__", main)
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config, "wake_scheduler", Event())
    plan = dict(
        id=23,
        char_id="char_test",
        char_name="测试",
        skill_index=1,
        skill_name="技能",
        target_level=2,
        status="idle",
    )
    op = dict(
        char_id="char_test",
        name="测试",
        mastery_error=None,
        recommendations=[
            {
                "skill_index": 1,
                "skill_name": "技能",
                "current_level": 1,
                "targets": {"2": {"skill_material_summary": {"available": True}}},
            }
        ],
    )
    state = SimpleNamespace(
        existing=None, plans=[], op=op, plan=plan, scheduler=scheduler, main=main
    )
    monkeypatch.setattr(mastery, "get_plan_by_skill", lambda *a: state.existing)
    monkeypatch.setattr(mastery, "get_all_plans", lambda: state.plans)
    monkeypatch.setattr(mastery, "get_plan_by_id", lambda *a: state.plan)
    state.add = MagicMock(
        return_value=({"status": "added", "id": 23}, ("char_test", 1), True)
    )
    monkeypatch.setattr(mastery, "_add_or_reuse_plan", state.add)
    state.refresh = MagicMock()
    monkeypatch.setattr(mastery, "refresh_workshop_after_plan_change", state.refresh)
    monkeypatch.setattr(
        mastery_support_data, "trainee_schedule_conflict", lambda _: None
    )
    monkeypatch.setattr(
        mastery_recommendation,
        "get_mastery_recommendations",
        lambda: {"has_data": True, "operators": [state.op]},
    )
    app = Flask(__name__)
    app.register_blueprint(mastery.mastery_bp)
    state.client = app.test_client()
    state.payload = dict(char_id="char_test", skill_index=1, target_level=2)
    return state


def submit(context):
    return context.client.post("/mastery-plan/start", json=context.payload).get_json()


def test_inserts_selected_target_with_plan_key_and_wakes_scheduler(start_context):
    c = start_context
    assert submit(c)["status"] == "inserted"
    assert len(c.scheduler.tasks) == 1
    task = c.scheduler.tasks[0]
    assert task.type == TaskTypes.SKILL_UPGRADE
    assert task.plan_key == "23"
    assert task.step_level == 2
    assert c.add.call_args.args[4] == 2
    assert config.wake_scheduler.is_set()


def test_repeat_click_is_idempotent(start_context):
    c = start_context
    assert submit(c)["status"] == "inserted"
    c.existing = c.plan
    assert submit(c)["status"] == "queued"
    assert len(c.scheduler.tasks) == 1
    assert c.add.call_count == 1


def test_craftable_materials_do_not_count_as_ready(start_context):
    c = start_context
    c.op["recommendations"][0]["targets"]["2"]["skill_material_summary"] = {
        "available": False,
        "craftable": True,
    }
    assert submit(c)["status"] == "insufficient"
    c.add.assert_not_called()
    assert c.scheduler.tasks == []


@pytest.mark.parametrize("reason", ["尚未精二", "基础技能未满 7 级"])
def test_unready_operator_never_inserted(start_context, reason):
    c = start_context
    c.op["mastery_error"] = reason
    assert submit(c) == {"status": "blocked", "reason": reason}
    c.add.assert_not_called()


@pytest.mark.parametrize(
    "blocked", ["disabled", "stopped", "absent", "training", "queued"]
)
def test_execution_gates_report_failure_before_creating_plan(start_context, blocked):
    c = start_context
    if blocked == "disabled":
        config.conf.enable_mastery = False
    elif blocked == "stopped":
        config.stop_mower.set()
    elif blocked == "absent":
        c.main.base_scheduler = None
    elif blocked == "training":
        c.plans = [{**c.plan, "id": 42, "status": "training"}]
    elif blocked == "queued":
        task = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
        task.plan_key = "42"
        c.scheduler.tasks.append(task)
    assert submit(c)["status"] == "blocked"
    c.add.assert_not_called()
    assert not config.wake_scheduler.is_set()


def test_target_mismatch_does_not_silently_train_old_target(start_context):
    c = start_context
    c.existing = {**c.plan, "target_level": 3}
    assert submit(c)["status"] == "blocked"
    c.add.assert_not_called()


def test_one_completed_target_not_requeued(start_context):
    c = start_context
    c.payload["target_level"] = 1
    assert submit(c)["status"] == "blocked"
    c.add.assert_not_called()


def test_endpoint_requires_token(start_context):
    c = start_context
    c.client.application.token = "private"
    assert c.client.post("/mastery-plan/start", json=c.payload).status_code == 403
    c.add.assert_not_called()


@pytest.mark.parametrize("bad", [True, 0, 4, "2"])
def test_invalid_target_rejected(start_context, bad):
    c = start_context
    c.payload["target_level"] = bad
    assert c.client.post("/mastery-plan/start", json=c.payload).status_code == 400
    c.add.assert_not_called()
