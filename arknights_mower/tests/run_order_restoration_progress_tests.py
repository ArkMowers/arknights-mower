"""跑单中断立即恢复原班，恢复失败保留原时间并释放派发。"""

import copy
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_schedule import RoomArrangementDeferred
from arknights_mower.tests.automatic_rescue_tests import offline as offline
from arknights_mower.tests.mass_mood_recovery_tests import NOW
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.tests.run_order_restoration_tests import (
    ORIGINAL,
    ROOM,
    assert_pending_restoration,
    prepare_order,
)
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    task_view,
)


def test_insertion_server_wait_restores_without_invented_deadline(solver, monkeypatch):
    task, _ = prepare_order(solver, monkeypatch, adjusted=False)
    solver.waiting_scene = [solver.scene()]
    calibrated_times = []
    solver.waiting_solver = MagicMock(
        side_effect=lambda: calibrated_times.append(task.time) or False
    )

    assert solver.agent_arrange(task.plan) is False

    assert_pending_restoration(task)
    assert task.time == calibrated_times[0]
    assert not getattr(task, "execution_failure", None)
    assert task in task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data)


@pytest.mark.parametrize("inline", [False, True])
@pytest.mark.parametrize("raises", [False, True])
def test_unfinished_restoration_waits_for_new_observation(
    solver, monkeypatch, inline, raises
):
    task, place = prepare_order(solver, monkeypatch)
    if not inline:
        task.run_order_original_roster = {ROOM: ORIGINAL.copy()}
        task.run_order_restore_pending = True
        task.prepare_run_order_restoration()
        place(["但书", ORIGINAL[1]])
    arrange = solver.agent_arrange_room

    def interrupt_restore(new_plan, room, plan, **kwargs):
        if plan[room] == ORIGINAL:
            if raises:
                raise RoomArrangementDeferred(room, "原班选人核验失败")
            return False
        return arrange(new_plan, room, plan, **kwargs)

    monkeypatch.setattr(solver, "agent_arrange_room", interrupt_restore)
    independent = SchedulerTask(NOW, task_type=TaskTypes.CLUE)
    solver.tasks.append(independent)

    if raises:
        with pytest.raises(RoomArrangementDeferred, match="原班选人核验失败"):
            solver.agent_arrange(task.plan)
    else:
        assert solver.agent_arrange(task.plan) is False

    assert_pending_restoration(task)
    assert task.time == NOW
    assert task.execution_failure
    failure = copy.deepcopy(task.execution_failure)
    for _ in range(3):
        solver._resume_failed_tasks()
        assert task.execution_failure == failure
        assert task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data) == [
            independent
        ]
    solver.op_data.room_observations[ROOM] = 1
    solver._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    monkeypatch.setattr(solver, "agent_arrange_room", arrange)
    solver.agent_arrange(task.plan)
    assert task.time == NOW
    assert not getattr(task, "run_order_restore_pending", False)
    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL


def test_rescue_compensation_wait_preserves_deadline_and_yields(solver, monkeypatch):
    task, _ = prepare_order(solver, monkeypatch)
    task.emergency_original_roster = {ROOM: ORIGINAL.copy()}
    task.meta_data = ""
    task.plan = copy.deepcopy(task.emergency_original_roster)
    monkeypatch.setattr(solver, "_emergency_frozen", lambda: True)
    monkeypatch.setattr(solver, "_emergency_compensation_available", lambda plan: False)
    independent = SchedulerTask(NOW + timedelta(seconds=5), task_type=TaskTypes.CLUE)
    solver.tasks.append(independent)

    assert solver.agent_arrange(task.plan) is False

    assert task.time == NOW
    assert task.execution_failure["dependency"]
    for _ in range(3):
        solver._resume_failed_tasks()
        assert task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data) == [
            independent
        ]
    solver.choose_agent.assert_not_called()
