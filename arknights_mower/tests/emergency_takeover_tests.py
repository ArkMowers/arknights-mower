"""救急接管直接执行完整驻员，不消费普通调度的暂缓条件。"""

import copy
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.emergency_group_return_tests import (
    group_return as recovery_fixture,  # noqa: F401
)
from arknights_mower.tests.emergency_group_staffing_tests import staffing as staffing
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import (
    solver as legacy_solver,  # noqa: F401
)
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes, scheduling


def takeover(solver):
    return next(
        task for task in solver.tasks if getattr(task, "emergency_takeover", False)
    )


@pytest.mark.parametrize(
    "blocker", ["unknown", "training", "reserved", "compensation", "release"]
)
def test_takeover_dispatches_full_roster_despite_other_responsibilities(
    staffing, blocker
):
    solver, state = staffing.solver, staffing.state
    worker = solver.op_data.operators[COVERS[0]]
    if blocker == "unknown":
        worker.time_stamp = None
        solver.op_data.dorm_mood_estimates.clear()
    elif blocker == "training":
        worker._current_room, worker.current_index = "train", 0
    elif blocker == "reserved":
        solver.tasks.append(
            SchedulerTask(
                task_plan={"factory": [worker.name]}, task_type=TaskTypes.WORKSHOP
            )
        )
    elif blocker == "compensation":
        task = SchedulerTask(task_plan={worker.room or "room_1_1": [PRIMARY[0]]})
        task.emergency_original_roster = copy.deepcopy(task.plan)
        solver.tasks.append(task)
    else:
        solver.tasks.append(
            SchedulerTask(
                time=NOW + timedelta(seconds=10),
                task_plan={
                    "dormitory_1": ["Current", "Current", "Free", "Current", "Current"]
                },
                task_type=TaskTypes.RELEASE_DORM,
                strict_mood_limit=True,
            )
        )
    assert solver._emergency_schedule_staffing()
    task = takeover(solver)
    assert task.plan == state["rescue_plan"]
    assert staffing.saves[-1]["state"]["staffing_plan"] == task.plan


def test_takeover_precedes_observation_and_recovery_exit(staffing):
    solver = staffing.solver
    solver._emergency_observe_recovery = MagicMock(return_value=False)
    solver._emergency_ready = MagicMock(return_value=True)
    solver._emergency_restore = MagicMock(return_value=True)
    solver._emergency_tick()
    assert takeover(solver).plan == staffing.state["rescue_plan"]
    solver._emergency_observe_recovery.assert_not_called()
    solver._emergency_restore.assert_not_called()


@pytest.mark.parametrize(
    "kind",
    [
        TaskTypes.RUN_ORDER,
        TaskTypes.SWAP_SUPPORT,
        TaskTypes.FIAMMETTA,
        TaskTypes.RELEASE_DORM,
    ],
)
def test_due_takeover_precedes_ordinary_task_priority(staffing, kind):
    solver = staffing.solver
    urgent = SchedulerTask(
        time=NOW - timedelta(minutes=1),
        task_type=kind,
        task_plan={"dormitory_1": ["Free"]},
    )
    urgent.strict_mood_limit = kind == TaskTypes.RELEASE_DORM
    solver.tasks.append(urgent)
    assert solver._emergency_schedule_staffing()
    task = takeover(solver)
    task.time = NOW
    scheduling(solver.tasks, time_now=NOW, op_data=solver.op_data)
    assert solver.tasks[0] is task
    assert urgent in solver.tasks


def test_takeover_rebases_queued_run_order_restoration(staffing):
    solver, state = staffing.solver, staffing.state
    room = next(iter(state["rescue_plan"]))
    restore = SchedulerTask(
        task_type=TaskTypes.RUN_ORDER, task_plan={room: [PRIMARY[0]]}
    )
    restore.run_order_original_roster = copy.deepcopy(restore.plan)
    restore.run_order_restore_pending = True
    solver.tasks.append(restore)
    assert solver._emergency_schedule_staffing()
    assert takeover(solver).plan[room] == state["rescue_plan"][room]
    restore.prepare_run_order_restoration()
    assert restore.plan == {room: state["rescue_plan"][room]}


def test_takeover_dispatches_while_initial_charging_is_queued(staffing):
    solver, state = staffing.solver, staffing.state
    fia = SchedulerTask(time=NOW, task_type=TaskTypes.FIAMMETTA, initial_fia=True)
    solver.tasks.append(fia)
    assert solver._emergency_schedule_staffing()
    task = takeover(solver)
    solver.task = task
    solver.find = MagicMock(return_value=True)
    solver.skip = MagicMock()
    solver._product_switching_enabled = MagicMock(return_value=True)
    solver._emergency_tick = MagicMock()
    solver.agent_arrange.side_effect = lambda plan, get_time=False: staffing.place(
        plan, get_time=get_time
    )
    solver.refresh_connecting = True
    expected = copy.deepcopy(task.plan)
    solver.infra_main()
    solver.agent_arrange.assert_called_once()
    assert staffing.plans == [expected]
    assert task not in solver.tasks
    assert fia in solver.tasks
    assert all(
        solver.op_data.get_current_room(room, True) == row
        for room, row in state["rescue_plan"].items()
    )


def test_unsaved_takeover_is_not_dispatched(staffing):
    solver = staffing.solver
    solver._emergency_save.side_effect = RuntimeError("save failed")
    with pytest.raises(RuntimeError, match="save failed"):
        solver._emergency_schedule_staffing()
    assert not any(getattr(task, "emergency_takeover", False) for task in solver.tasks)


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("follow", [False, True])
def test_live_training_protection_does_not_filter_takeover(
    monkeypatch, enabled, follow
):
    from arknights_mower.solvers import mastery_reader
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
    from arknights_mower.tests import base_scheduler_tests
    from arknights_mower.utils import config

    monkeypatch.setattr(config.conf, "enable_mastery", enabled)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", follow)
    monkeypatch.setattr(BaseSchedulerSolver, "__init__", lambda _: None)
    plan = {"train": ["褐果", "桃金娘"]}
    solver = base_scheduler_tests.TestTrainGateReadThenJudge._make_solver(plan)
    solver.task = SchedulerTask(task_plan=plan)
    solver.task.emergency_staffing = solver.task.emergency_takeover = True
    solver._can_refresh_idle_dorm_search = lambda: False
    solver.op_data.get_current_room = MagicMock(return_value=["夜莺", "号角"])
    solver.choose_train = MagicMock()
    solver.record_selection_success = MagicMock()
    solver.get_agent_from_room = MagicMock(
        return_value=[{"agent": "褐果"}, {"agent": "桃金娘"}]
    )
    read = MagicMock(return_value=mastery_reader.RoomState("training", protected=True))
    monkeypatch.setattr(mastery_reader, "read_room_state", read)
    solver.agent_arrange_room({}, "train", plan)
    solver.choose_train.assert_called_once_with(
        ["褐果", "桃金娘"], fast_mode=True, choose_error=0
    )
    assert not getattr(solver.task, "training_skipped_slots", set())
    assert not plan
