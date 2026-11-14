"""专精开训复用有界选人页观测，不确认驻员。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import mastery_support_runtime
from arknights_mower.tests.initial_dorm_mood_tests import op_data as op_data
from arknights_mower.tests.initial_dorm_mood_tests import solver as solver
from arknights_mower.utils.mastery_mood import SupportMoodWait
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


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
