"""初始充能预约不阻挡独立到期任务，已到期充能保留原有排序。"""

import pickle
from datetime import datetime, timedelta
from types import MethodType
from unittest.mock import MagicMock, call

import pytest

from arknights_mower.solvers import base_schedule, emergency
from arknights_mower.tests.dorm_group_tests import solver as solver
from arknights_mower.utils import scheduler_task
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

pytestmark = pytest.mark.usefixtures("offline_maintenance")
NOW = datetime(2026, 11, 2, 20, 28, 28)


@pytest.fixture
def dispatch(solver, monkeypatch):
    class Clock(datetime):
        current = NOW

        @classmethod
        def now(cls, tz=None):
            return cls.current

    for module in (base_schedule, emergency, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    solver.find_next_task = MethodType(
        base_schedule.BaseSchedulerSolver.find_next_task, solver
    )
    solver.find = MagicMock(return_value=True)
    solver._initial_fia_checked = True
    solver._initial_mood_refresh_rooms = set()
    solver.planned = solver.todo_task = solver.collect_notification = True
    solver._refresh_deferred_product_reservations = MagicMock()
    solver.plan_run_order = MagicMock()
    solver._run_clue_flow = MagicMock(return_value=True)
    solver.plan_fia = MagicMock()
    solver.agent_arrange = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    return solver, Clock


@pytest.mark.parametrize("startup_pending", [False, True])
@pytest.mark.parametrize("restored", [False, True])
def test_future_initial_charge_allows_refresh_and_independent_work(
    dispatch, startup_pending, restored
):
    running, clock = dispatch
    charge = SchedulerTask(
        NOW + timedelta(minutes=2), task_type=TaskTypes.FIAMMETTA, initial_fia=True
    )
    refreshes = [
        SchedulerTask(
            NOW - timedelta(seconds=3 - index),
            task_type=TaskTypes.REFRESH_TIME,
            meta_data=f"room_1_{index + 1}",
        )
        for index in range(3)
    ]
    clue = SchedulerTask(NOW - timedelta(microseconds=1), task_type=TaskTypes.CLUE)
    running.tasks = [*refreshes, clue, charge]
    if restored:
        running.tasks = pickle.loads(pickle.dumps(running.tasks))
        *refreshes, clue, charge = running.tasks
    running._emergency_startup_pending = startup_pending
    charge_time = charge.time
    refresh_times = [task.time for task in refreshes]
    for refresh in refreshes:
        scheduler_task.protect_priority_tasks(running.tasks, op_data=running.op_data)
        running.task = running.find_next_task()
        assert running.task is refresh
        running.infra_main()
        assert all(task is not refresh for task in running.tasks)
        assert charge in running.tasks and charge.time == charge_time
    assert [task.time for task in refreshes] == refresh_times
    assert running.plan_run_order.call_args_list == [
        call("room_1_1"),
        call("room_1_2"),
        call("room_1_3"),
    ]
    running.task = running.find_next_task()
    assert running.task is clue
    running.infra_main()
    running._run_clue_flow.assert_called_once()
    running.plan_fia.assert_not_called()
    assert clue not in running.tasks
    clock.current = charge_time
    running.task = running.find_next_task()
    assert running.task is charge
    running.infra_main()
    running.plan_fia.assert_called_once()
    assert charge.time == charge_time
    assert charge not in running.tasks


@pytest.mark.parametrize("startup_pending", [False, True])
def test_failed_initial_restoration_does_not_block_independent_refresh(
    dispatch, startup_pending
):
    running, _ = dispatch
    charge = SchedulerTask(
        NOW - timedelta(minutes=1),
        task_type=TaskTypes.FIAMMETTA,
        task_plan={"dormitory_1": ["塑心", "冰酿", "泥岩", "能天使", "年"]},
        initial_fia=True,
    )
    running.tasks = [charge]
    running._retain_failed_task(charge, "等待宿舍新观测", ["dormitory_1"])
    failure, original_time = charge.execution_failure, charge.time
    running._emergency_startup_pending = startup_pending
    for index in range(3):
        refresh = SchedulerTask(
            NOW - timedelta(seconds=1),
            task_type=TaskTypes.REFRESH_TIME,
            meta_data=f"room_1_{index + 1}",
        )
        if startup_pending:
            refresh.startup_observation_pending = True
        running.tasks.append(refresh)
        running._resume_failed_tasks()
        scheduler_task.protect_priority_tasks(running.tasks, op_data=running.op_data)
        running.task = running.find_next_task()
        assert running.task is refresh
        running.infra_main()
        assert refresh not in running.tasks
        assert charge in running.tasks
        assert charge.execution_failure is failure and charge.time == original_time
    running.agent_arrange.assert_not_called()
    resident = running.op_data.operators["泥岩"]
    resident.time_stamp = NOW + timedelta(seconds=1)
    running._resume_failed_tasks()
    assert not getattr(charge, "execution_failure", None)
    assert charge.time == original_time
    running.task = running.find_next_task()
    assert running.task is charge
    running.infra_main()
    running.agent_arrange.assert_called_once_with(charge.plan, False)
    assert charge not in running.tasks


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT])
def test_due_priority_work_still_precedes_ready_initial_charge(
    dispatch, monkeypatch, kind
):
    from arknights_mower.solvers import mastery
    from arknights_mower.utils import config, workshop_automation

    running, _ = dispatch
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    actions = MagicMock()
    monkeypatch.setattr(mastery, "run_mastery_task", actions)
    monkeypatch.setattr(mastery, "run_swap_support", actions)
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", MagicMock())
    charge = SchedulerTask(NOW, task_type=TaskTypes.FIAMMETTA, initial_fia=True)
    priority = SchedulerTask(
        NOW - timedelta(seconds=1),
        task_type=kind,
        task_plan={"meeting": ["伊内丝", "银灰"]}
        if kind == TaskTypes.RUN_ORDER
        else {},
    )
    running.tasks = [charge, priority]
    scheduler_task.protect_priority_tasks(running.tasks, op_data=running.op_data)
    running.task = running.find_next_task()
    assert running.task is priority
    running.infra_main()
    assert priority not in running.tasks
    assert charge in running.tasks
    running.plan_fia.assert_not_called()
    if kind == TaskTypes.RUN_ORDER:
        running.agent_arrange.assert_called_once_with(priority.plan, False)
    else:
        actions.assert_called_once_with(running)
