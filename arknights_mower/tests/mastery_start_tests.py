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


@pytest.mark.parametrize("token", ["", "wrong"])
def test_endpoint_requires_token(start_context, token):
    c = start_context
    c.client.application.token = "private"
    assert (
        c.client.post(
            "/mastery-plan/start", json=c.payload, headers={"token": token}
        ).status_code
        == 403
    )
    c.add.assert_not_called()


@pytest.mark.parametrize("bad", [True, 0, 4, "2"])
def test_invalid_target_rejected(start_context, bad):
    c = start_context
    c.payload["target_level"] = bad
    assert c.client.post("/mastery-plan/start", json=c.payload).status_code == 400
    c.add.assert_not_called()


@pytest.fixture
def dialog_context(monkeypatch, tmp_path):
    from arknights_mower.utils import mastery_db, mastery_support, mastery_support_data

    scheduler = SimpleNamespace(tasks=[], task=None)
    main = SimpleNamespace(base_scheduler=scheduler)
    monkeypatch.setitem(sys.modules, "arknights_mower.__main__", main)
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config.conf, "growth_crafting_order", [])
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config, "wake_scheduler", Event())
    monkeypatch.setattr(mastery_db, "_tables_created", set())
    monkeypatch.setattr(
        mastery_db,
        "get_path",
        lambda path: tmp_path / "data.db" if path.endswith("data.db") else tmp_path,
    )
    monkeypatch.setattr(
        mastery,
        "get_skill_data",
        lambda: {
            "characters": {
                "char_test": {
                    "name": "测试",
                    "skills": [{"name": "技能"}],
                    "profession": "WARRIOR",
                }
            }
        },
    )
    monkeypatch.setattr(
        mastery_recommendation, "get_mastery_requirement_error", lambda _: None
    )
    monkeypatch.setattr(
        mastery_recommendation, "get_current_mastery_level", lambda *a: 1
    )
    monkeypatch.setattr(
        mastery_support_data, "trainee_schedule_conflict", lambda _: None
    )
    monkeypatch.setattr(
        mastery_support, "plan_supports", lambda *a, **kw: {"version": 1, "stages": []}
    )
    summary = {"available": True}
    monkeypatch.setattr(
        mastery_recommendation,
        "get_mastery_recommendations",
        lambda: {
            "has_data": True,
            "operators": [
                {
                    "char_id": "char_test",
                    "name": "测试",
                    "recommendations": [
                        {
                            "skill_index": 0,
                            "skill_name": "技能",
                            "current_level": 1,
                            "targets": {"2": {"skill_material_summary": summary}},
                        }
                    ],
                }
            ],
        },
    )
    automatic = MagicMock()
    monkeypatch.setattr(mastery, "_dispatch_new_plans_immediately", automatic)
    monkeypatch.setattr(mastery, "refresh_workshop_after_plan_change", MagicMock())
    app = Flask(__name__)
    app.token = "private"
    app.register_blueprint(mastery.mastery_bp)
    return SimpleNamespace(
        client=app.test_client(),
        scheduler=scheduler,
        main=main,
        summary=summary,
        automatic=automatic,
        payload={
            "create_task": True,
            "items": [
                {
                    "name": "测试",
                    "skill_index": 0,
                    "target_level": 2,
                    "support_mode": "auto",
                }
            ],
        },
    )


def submit_dialog(context, token="private"):
    return context.client.post(
        "/mastery-plan", json=context.payload, headers={"token": token}
    )


@pytest.mark.parametrize("mode", ["auto", "route"])
def test_dialog_persists_plan_and_generates_one_linked_task(dialog_context, mode):
    from arknights_mower.utils.mastery_db import get_all_plans

    c = dialog_context
    c.payload["items"][0]["support_mode"] = mode
    result = submit_dialog(c).get_json()["results"][0]
    assert result["status"] == "added"
    assert result["task"]["status"] == "inserted"
    plans = get_all_plans()
    assert len(plans) == 1
    assert plans[0]["target_level"] == 2
    assert bool(plans[0]["support_plan"]) == (mode == "auto")
    assert len(c.scheduler.tasks) == 1
    task = c.scheduler.tasks[0]
    assert task.type == TaskTypes.SKILL_UPGRADE
    assert task.plan_key == str(plans[0]["id"])
    assert task.step_level == 2
    assert config.wake_scheduler.is_set()
    assert submit_dialog(c).get_json()["results"][0]["task"]["status"] == "queued"
    assert len(get_all_plans()) == len(c.scheduler.tasks) == 1
    c.automatic.assert_not_called()


@pytest.mark.parametrize(
    "blocked", ["materials", "disabled", "stopped", "absent", "occupied"]
)
def test_dialog_retains_saved_plan_and_reports_why_no_task_was_created(
    dialog_context, blocked
):
    from arknights_mower.utils.mastery_db import get_all_plans

    c = dialog_context
    if blocked == "materials":
        c.summary["available"] = False
    elif blocked == "disabled":
        config.conf.enable_mastery = False
    elif blocked == "stopped":
        config.stop_mower.set()
    elif blocked == "absent":
        c.main.base_scheduler = None
    else:
        task = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
        task.plan_key = "another"
        c.scheduler.tasks.append(task)
    before = list(c.scheduler.tasks)
    result = submit_dialog(c).get_json()["results"][0]
    assert result["status"] == "added"
    assert result["task"]["status"] == (
        "insufficient" if blocked == "materials" else "blocked"
    )
    assert result["task"]["reason"]
    assert len(get_all_plans()) == 1
    assert c.scheduler.tasks == before
    assert not config.wake_scheduler.is_set()
    c.automatic.assert_not_called()


@pytest.mark.parametrize("token", ["", "wrong"])
def test_dialog_requires_token_before_saving_or_dispatching(dialog_context, token):
    from arknights_mower.utils.mastery_db import get_all_plans

    c = dialog_context
    assert submit_dialog(c, token).status_code == 403
    assert get_all_plans() == []
    assert c.scheduler.tasks == []
    assert not config.wake_scheduler.is_set()


def test_dialog_existing_target_is_not_silently_changed(dialog_context):
    from arknights_mower.utils.mastery_db import get_all_plans

    c = dialog_context
    c.summary["available"] = False
    assert submit_dialog(c).get_json()["results"][0]["status"] == "added"
    c.payload["items"][0]["target_level"] = 3
    result = submit_dialog(c).get_json()["results"][0]
    assert result["status"] == "existing"
    assert result["task"]["status"] == "blocked"
    assert "目标已变化" in result["task"]["reason"]
    assert get_all_plans()[0]["target_level"] == 2
    assert c.scheduler.tasks == []


def test_dialog_reports_active_training_without_an_extra_task(dialog_context):
    from arknights_mower.utils.mastery_db import get_all_plans, update_plan_status

    c = dialog_context
    result = submit_dialog(c).get_json()["results"][0]
    update_plan_status(result["id"], "training")
    c.scheduler.tasks.clear()
    result = submit_dialog(c).get_json()["results"][0]
    assert result["task"]["status"] == "active"
    assert len(get_all_plans()) == 1
    assert c.scheduler.tasks == []


@pytest.mark.parametrize("target", [True, 0, 4, "2", None])
def test_dialog_invalid_target_never_saves_or_dispatches(dialog_context, target):
    from arknights_mower.utils.mastery_db import get_all_plans

    c = dialog_context
    c.payload["items"][0]["target_level"] = target
    result = submit_dialog(c).get_json()["results"][0]
    assert result["status"] == "error"
    assert get_all_plans() == []
    assert c.scheduler.tasks == []
