"""专精开训复用有界选人页观测，不确认驻员。"""

import pickle
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import mastery_support_runtime
from arknights_mower.tests.initial_dorm_mood_tests import op_data as op_data
from arknights_mower.tests.initial_dorm_mood_tests import solver as solver
from arknights_mower.tests.mastery_support_fixtures import database as database
from arknights_mower.utils.mastery_mood import SupportMoodWait
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    task_view,
)


@pytest.mark.parametrize("calculated", [False, True])
def test_unknown_assistant_uses_real_scan_before_admission(
    solver, monkeypatch, calculated
):
    solver.defer_backup_plan_until_mood_read = False
    solver._card_moods_scanned_this_run = True
    solver.task = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
    solver.tasks = [solver.task]
    solver.op_data.dorm_mood_estimates.clear()
    if calculated:
        solver.op_data.runtime_conf = SimpleNamespace(test_mood_calculation=True)
        monkeypatch.setattr(solver.op_data, "calculated_mood", lambda *a: None)
        solver.op_data.mood_model = Mock(moods={"红": 24})
    route = {"level": 2, "operator": "红", "efficiency": 30}
    mastery_support_runtime._require_stage_mood(solver, route, inherited=False)
    assert solver.op_data.dorm_mood_estimates["红"][0] == 24
    assert solver.enter_room.call_count == 2
    assert solver.enter_room.call_args.args == ("train",)
    solver.tap_confirm.assert_not_called()
    solver.agent_arrange_room.assert_not_called()


@pytest.mark.parametrize("original_known_low", [False, True])
def test_observation_yields_to_due_work_and_resumes_after_dependency_release(
    solver, monkeypatch, original_known_low
):
    from arknights_mower.utils import mastery_mood

    solver.defer_backup_plan_until_mood_read = False
    solver.task = SchedulerTask(
        datetime.now() - timedelta(minutes=5), task_type=TaskTypes.SKILL_UPGRADE
    )
    task = solver.task
    other = SchedulerTask(task_type=TaskTypes.RUN_ORDER)
    solver.tasks = [task, other]
    solver.op_data.dorm_mood_estimates.clear()
    route = {"level": 2, "operator": "红", "efficiency": 30}
    with pytest.raises(SupportMoodWait) as wait:
        mastery_support_runtime._require_stage_mood(solver, route, inherited=False)
    solver.enter_room.assert_not_called()
    assert task.mastery_mood_observation_pending
    task.mastery_mood_wait = {
        "plan_id": 1,
        "context": {},
        "required": wait.value.required,
    }
    if original_known_low:
        solver.op_data.dorm_mood_estimates["银灰"] = (1, datetime.now())
        task.mastery_mood_wait["required"] = {"银灰": 5}
        task.mastery_mood_wait["alternatives"] = [wait.value.required]
    task.execution_failure = {"dependency": True}
    at = task.time
    monkeypatch.setattr(mastery_mood, "support_mood_context", lambda *a: {})
    for _ in range(3):
        solver._resume_failed_tasks()
        assert task.execution_failure and task.time == at
    solver.tasks.remove(other)
    solver._resume_failed_tasks()
    assert not hasattr(task, "execution_failure")
    assert task.time == at
    mastery_support_runtime._require_stage_mood(solver, route, inherited=False)
    assert solver.enter_room.call_count == 2
    assert solver.enter_room.call_args.args == ("train",)
    assert not task.mastery_mood_observation_pending


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("original_mood", [None, 1])
@pytest.mark.parametrize("observed_mood", [None, 3, 24, "restored_original"])
def test_deferred_observation_does_not_start_with_known_zero_bonus_fallback(
    solver, database, monkeypatch, legacy, original_mood, observed_mood
):
    from arknights_mower.solvers import mastery
    from arknights_mower.utils import config
    from arknights_mower.utils import mastery_db as db

    monkeypatch.setattr(config.conf, "assistant_follows_schedule", False)
    solver.defer_backup_plan_until_mood_read = False
    solver.op_data.dorm_mood_estimates.clear()
    if original_mood is not None:
        solver.op_data.dorm_mood_estimates["银灰"] = (original_mood, datetime.now())
    solver.op_data.dorm_mood_estimates["冰酿"] = (24, datetime.now())
    route = dict(level=2, operator="银灰", efficiency=100)
    pid = db.insert_plan(
        "trainee",
        0,
        2,
        char_name="学员",
        support_plan=None if legacy else {"stages": [route]},
    )
    monkeypatch.setattr(mastery, "_get_plan_route", lambda *a: route)
    monkeypatch.setattr(
        mastery_support_runtime, "_observed_support", lambda _: ("银灰", "学员")
    )
    monkeypatch.setattr(mastery_support_runtime, "schedule_context", lambda: ({}, 0))
    monkeypatch.setattr(
        mastery_support_runtime, "basic_mastery_successor", lambda *a: False
    )
    monkeypatch.setattr(mastery_support_runtime, "halving_successor", lambda *a: None)
    options = {
        name: {
            level: dict(name=name, efficiency=bonus, halves=False)
            for level in (1, 2, 3)
        }
        for name, bonus in [("银灰", 100), ("红", 30), ("冰酿", 0)]
    }
    monkeypatch.setattr(
        mastery_support_runtime, "candidates", lambda *a, **k: (options, 0)
    )
    notify = Mock(return_value=False)
    monkeypatch.setattr(db, "should_notify", notify)
    solver._task_failure_snapshot = Mock(return_value={})
    task = SchedulerTask(
        datetime.now() - timedelta(minutes=2), task_type=TaskTypes.SKILL_UPGRADE
    )
    task.plan_key = str(pid)
    other = SchedulerTask(task_type=TaskTypes.NOT_SPECIFIC)
    solver.task, solver.tasks = task, [task, other]
    at = task.time
    prepare = (
        mastery_support_runtime.prepare_legacy_support_mood
        if legacy
        else mastery_support_runtime.prepare_plan_supports
    )

    with pytest.raises(SupportMoodWait) as wait:
        prepare(solver, db.get_plan_by_id(pid), 2)
    assert task.mastery_mood_observation_pending
    assert solver.enter_room.call_count == 0
    assert db.get_plan_by_id(pid)["support_runtime"] is None
    mastery._defer_support_mood(solver, db.get_plan_by_id(pid), wait.value)
    notify.assert_not_called()
    assert "补读暂缓" in db.get_plan_by_id(pid)["failed_reason"]
    task = pickle.loads(pickle.dumps(task))
    solver.task, solver.tasks = task, [task, other]
    for _ in range(3):
        solver._resume_failed_tasks()
        assert task.execution_failure and task.time == at
        assert task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data) == [other]
    if observed_mood == "restored_original":
        solver.op_data.dorm_mood_estimates["银灰"] = (24, datetime.now())
    else:
        solver.tasks.remove(other)
    solver._resume_failed_tasks()
    assert not hasattr(task, "execution_failure")
    assert task.time == at

    if observed_mood != "restored_original":
        solver.recog.img[0] = observed_mood
    prepare(solver, db.get_plan_by_id(pid), 2)

    if observed_mood == "restored_original":
        assert solver.tasks == [task, other]
        solver.enter_room.assert_not_called()
    else:
        assert solver.tasks == [task]
        assert solver.enter_room.call_count == 2
    assert not task.mastery_mood_observation_pending
    saved = db.get_plan_by_id(pid)["support_runtime"]
    if observed_mood in (24, "restored_original") and legacy:
        assert saved is None
    else:
        import json

        saved = json.loads(saved)
        assert saved["operator"] == (
            "银灰" if observed_mood in (24, "restored_original") else "红"
        )
    solver.tap_confirm.assert_not_called()
    solver.agent_arrange_room.assert_not_called()
