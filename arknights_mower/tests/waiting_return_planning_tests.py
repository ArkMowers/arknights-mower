"""挂起回班参与普通规划去重，并保留原任务的恢复责任。"""

from datetime import datetime, timedelta

import pytest

from arknights_mower.tests.multi_group_shift_tests import A, B, apply, shift_off
from arknights_mower.tests.multi_group_shift_tests import solver as solver
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def waiting_return(solver):
    s = solver
    s.op_data.operators["讯使"].group_bindings[1]["replacement"] = ["红"]
    assert shift_off(s, "甲")[0]
    assert shift_off(s, "乙")[0]
    for bed in s.op_data.all_dorms():
        if bed.name:
            bed.time = datetime.now() - timedelta(minutes=1)
    for name in (A, B):
        s.op_data.operators[name].rest_in_full = True
    pending = SchedulerTask(
        time=datetime.now() - timedelta(minutes=2),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": ["Current", B]},
    )
    s.tasks = [pending]
    s._suspend_group_shift(pending, {"甲"})
    return s, pending


def test_unchanged_replanning_preserves_one_waiting_return(waiting_return):
    s, pending = waiting_return
    original_time = pending.time
    for _ in range(20):
        s.plan_metadata()
        assert s.waiting_group_shifts == [pending]
        assert s.waiting_group_shifts[0] is pending
        assert pending.time == original_time
        assert all(B not in row for task in s.tasks for row in task.plan.values())
    assert any(A in row for task in s.tasks for row in task.plan.values())


def test_group_confirmation_releases_original_waiting_return_once(waiting_return):
    s, pending = waiting_return
    original_time = pending.time
    s.plan_metadata()
    prerequisite = next(
        task for task in s.tasks if any(A in row for row in task.plan.values())
    )
    s.task = prerequisite
    s._prepare_group_shift(prerequisite, remember_targets=True)
    apply(s, prerequisite.plan)
    assert s._complete_group_shift(prerequisite)
    assert not s.waiting_group_shifts
    assert sum(task is pending for task in s.tasks) == 1
    assert pending.time == original_time
    s._resume_waiting_group_shifts()
    assert sum(task is pending for task in s.tasks) == 1


def test_related_room_observation_restores_failed_predecessor(waiting_return):
    s, pending = waiting_return
    predecessor = SchedulerTask(
        time=pending.time - timedelta(minutes=1),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": [A, "Current"]},
    )
    s.tasks = [predecessor]
    s.task = predecessor
    s._prepare_group_shift(predecessor, remember_targets=True)
    pending.group_shift_predecessors = (predecessor,)
    s._retain_failed_task(predecessor, "换班确认未完成", ["meeting"])
    original_time = predecessor.time
    failure = predecessor.execution_failure
    s._resume_failed_tasks()
    s.op_data.room_observations["contact"] = 1
    s._resume_failed_tasks()
    assert predecessor.execution_failure is failure
    s._resume_waiting_group_shifts()
    assert s.waiting_group_shifts == [pending]
    s.op_data.room_observations["meeting"] = 1
    s._resume_failed_tasks()
    assert not getattr(predecessor, "execution_failure", None)
    assert predecessor.execution_retained
    assert predecessor.time == original_time
    apply(s, predecessor.plan)
    assert s._complete_group_shift(predecessor)
    assert not s.waiting_group_shifts
    assert sum(task is pending for task in s.tasks) == 1


def test_waiting_standby_return_is_not_added_to_another_group(solver):
    s = solver
    slots = s.global_plan["default_plan"].plan
    slots["meeting"][1] = Room(B, "", ["初雪"])
    slots["contact"][0].group_bindings = []
    s.global_plan["default_plan"].config.resting_standby = [B]
    assert s.initialize_operators() is None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5, datetime.now()
    assert shift_off(s, "甲")[0]
    for bed in s.op_data.all_dorms():
        if bed.name:
            bed.time = datetime.now() + timedelta(hours=1)
    s.op_data.operators[B]._current_room = ""
    s.op_data.operators[B].current_index = -1
    cover = s.op_data.operators["初雪"]
    cover._current_room, cover.current_index = "meeting", 1
    assert s.op_data.is_standby(B)
    pending = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": ["Current", B]},
    )
    s.tasks = [pending]
    s._suspend_group_shift(pending, {"甲"})
    s.plan_metadata()
    assert s.waiting_group_shifts == [pending]
    assert any(A in row for task in s.tasks for row in task.plan.values())
    assert all(B not in row for task in s.tasks for row in task.plan.values())
