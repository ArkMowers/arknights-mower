"""实测生产倒计时驱动窗口复核，保留原跑单并允许独立任务继续。"""

import pickle
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests.emergency_compensation_tests import selection_harness
from arknights_mower.tests.run_order_planning_wakeup_tests import replay as replay
from arknights_mower.utils import config, scheduler_task
from arknights_mower.utils.dorm_candidates import retained_task_reservations
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

pytestmark = pytest.mark.usefixtures("offline_maintenance")
ROOM = "room_1_1"


@pytest.fixture
def window(replay, monkeypatch):
    solver, clock = replay
    place = selection_harness(solver, monkeypatch, primary="鸿雪", add_slot=False)
    place(["鸿雪"])
    config.conf.run_order_delay = 1
    config.conf.run_order_grandet_mode.enable = True
    config.conf.run_order_grandet_mode.buffer_time = 1
    solver.drone_room = "room_9_9"
    solver.accept_order = MagicMock()
    solver.record_selection_failure = MagicMock()
    solver.plan_metadata = MagicMock()
    solver.find = MagicMock(
        side_effect=lambda name, *a, **k: None if name == "bill_accelerate" else True
    )
    task = SchedulerTask(clock.now(), {ROOM: ["但书"]}, TaskTypes.RUN_ORDER, ROOM)
    solver.tasks, solver.task = [task], task
    return solver, clock, task


def wait_for_production(window, remaining=5502.5):
    solver, clock, order = window
    solver.get_order_remaining_time.return_value = remaining
    assert solver.agent_arrange(order.plan) is False
    observation = next(
        task for task in solver.tasks if task.type == TaskTypes.REFRESH_TIME
    )
    assert observation.time == clock.now() + timedelta(seconds=remaining - 60)
    return observation


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("slots", [1, 2])
def test_production_wait_retains_order_and_dispatches_independent_work(
    window, restart, slots
):
    solver, clock, order = window
    if slots == 2:
        solver.op_data.plan[ROOM].append(Room("Free", "", []))
        solver.op_data.operators["深巡"]._current_room = ROOM
        solver.op_data.operators["深巡"].current_index = 1
        order.plan[ROOM] = ["鸿雪", "但书"]
    original_time = order.time
    original_plan = order.plan.copy()
    observation = wait_for_production(window)
    if restart:
        solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
        order, observation = solver.tasks
    for _ in range(3):
        clock.current += timedelta(seconds=10)
        solver._resume_failed_tasks()
        scheduler_task.scheduling(
            solver.tasks, time_now=clock.now(), op_data=solver.op_data
        )
        assert solver.find_next_task() is observation
        assert order.time == original_time and order.plan == original_plan
        assert retained_task_reservations(solver.op_data, [order]) == (set(), set())
    solver.get_order_remaining_time.assert_called_once()
    solver.choose_agent.assert_not_called()
    solver.drone.assert_not_called()
    depot = SchedulerTask(clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(depot)
    solver.仓库扫描 = MagicMock()
    solver.task = depot
    solver.infra_main()
    solver.仓库扫描.assert_called_once()
    assert depot not in solver.tasks
    assert order in solver.tasks and observation in solver.tasks
    assert order.time == original_time

    clock.current = observation.time
    solver.get_order_remaining_time.return_value = 60
    solver.task = observation
    solver.infra_main()
    assert observation not in solver.tasks
    assert solver.find_next_task() is order
    assert not hasattr(order, "execution_failure")
    solver.task = order
    solver.agent_arrange(order.plan)
    original = ["鸿雪"] if slots == 1 else ["鸿雪", "深巡"]
    target = ["但书"] if slots == 1 else ["鸿雪", "但书"]
    assert solver.op_data.get_current_room(ROOM, True) == original
    assert order.plan == {} and order.time == original_time
    solver.accept_order.assert_called_once()
    solver.drone.assert_not_called()
    assert [c.args[0] for c in solver.choose_agent.call_args_list] == [
        target,
        original,
    ]


def test_new_production_deadline_reuses_observation_without_polling(window):
    solver, clock, order = window
    observation = wait_for_production(window)
    clock.current = observation.time
    solver.get_order_remaining_time.return_value = 7155.5
    expected = clock.now() + timedelta(seconds=7095.5)
    solver.task = observation
    solver.infra_main()
    assert observation.time == expected
    assert solver.tasks.count(observation) == 1
    assert order.execution_failure
    for _ in range(3):
        solver._resume_failed_tasks()
        assert solver.find_next_task() is observation
    assert solver.get_order_remaining_time.call_count == 2
    solver.choose_agent.assert_not_called()


@pytest.mark.parametrize("remaining", [0, -1])
def test_invalid_production_read_retains_failure_without_another_timer(
    window, remaining
):
    solver, clock, order = window
    observation = wait_for_production(window)
    clock.current = observation.time
    solver.get_order_remaining_time.return_value = remaining
    solver.task = observation
    solver.infra_main()
    for _ in range(3):
        solver._resume_failed_tasks()
        assert solver.find_next_task() is None
    assert observation.execution_failure
    assert order.execution_failure
    assert len(solver.tasks) == 2
    assert solver.get_order_remaining_time.call_count == 2
    solver.choose_agent.assert_not_called()


def test_legacy_window_failure_observes_once_then_uses_measured_production(window):
    solver, clock, order = window
    original_time = order.time
    solver._retain_failed_task(
        order,
        "订单倒计时 5502.5 秒不在跑单窗口，尚未确认漏单，等待相关实测或安排更新",
        [ROOM],
    )
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    order = solver.tasks[0]
    for _ in range(3):
        solver._resume_failed_tasks()
    observation = solver.find_next_task()
    assert observation.type == TaskTypes.REFRESH_TIME
    assert observation.time == clock.now()
    solver.get_order_remaining_time.return_value = 3283.5
    solver.task = observation
    solver.infra_main()
    assert observation.time == clock.now() + timedelta(seconds=3223.5)
    assert len(solver.tasks) == 2
    assert any(task is order for task in solver.tasks)
    assert order.time == original_time
    solver.choose_agent.assert_not_called()


def test_losing_order_eligibility_releases_unstarted_production_wait(window):
    solver, _, order = window
    wait_for_production(window)
    solver.op_data.plan[ROOM][0].replacement = []
    solver._sync_run_order_tasks()
    assert order not in solver.tasks
    assert not any(
        getattr(t, "run_order_window_observation", False) for t in solver.tasks
    )


def test_production_observation_propagates_cancellation_without_navigation(window):
    solver, _, _ = window
    observation = wait_for_production(window)
    solver.back_to_infrastructure.reset_mock()
    solver.get_order_remaining_time.side_effect = base.MowerExit()
    with pytest.raises(base.MowerExit):
        solver._observe_run_order_window(observation)
    solver.back_to_infrastructure.assert_not_called()


def test_retained_order_confirmation_uses_calibrated_time_not_original_time(
    window, monkeypatch
):
    solver, clock, order = window
    observation = wait_for_production(window)
    clock.current = observation.time
    solver.get_order_remaining_time.return_value = 120
    solver.task = observation
    solver.infra_main()
    solver.task = order
    result = solver.agent_arrange_room({}, ROOM, order.plan)
    assert order.run_order_calibrated_time == clock.now() + timedelta(seconds=60)
    assert order.time < clock.now() - timedelta(hours=1)
    solver.find = MagicMock(return_value=None)
    monkeypatch.setattr(config, "screenshot_avg", 0)
    solver.sleep.reset_mock()
    base.BaseSchedulerSolver.tap_confirm(solver, ROOM, result)
    solver.sleep.assert_called_once_with(119.0)


@pytest.mark.parametrize("remaining", [660, 900, 7155.5])
def test_positive_outside_window_uses_measured_deadline(window, remaining):
    solver, _, order = window
    wait_for_production(window, remaining)
    assert len(solver.tasks) == 2
    assert order.execution_failure
    solver.choose_agent.assert_not_called()
    solver.drone.assert_not_called()


@pytest.mark.parametrize("remaining", [0, -1])
def test_legacy_invalid_read_does_not_create_production_observation(window, remaining):
    solver, _, order = window
    solver._retain_failed_task(order, f"订单倒计时 {remaining} 秒不在跑单窗口", [ROOM])
    for _ in range(3):
        solver._resume_failed_tasks()
    assert solver.tasks == [order]
    assert solver.find_next_task() is None


def test_new_valid_countdown_rearms_failed_observation(window):
    solver, clock, order = window
    observation = wait_for_production(window)
    clock.current = observation.time
    solver.get_order_remaining_time.return_value = 0
    solver.task = observation
    solver.infra_main()
    assert observation.execution_failure
    solver.op_data.operators["鸿雪"].time_stamp = clock.now()
    solver._resume_failed_tasks()
    solver.task = order
    solver.get_order_remaining_time.return_value = 900
    assert solver.agent_arrange(order.plan) is False
    assert solver.find_next_task() is observation
    assert observation.time == clock.now() + timedelta(seconds=840)
    assert not getattr(observation, "execution_failure", None)
    assert len(solver.tasks) == 2


def test_return_navigation_does_not_extend_measured_production_deadline(window):
    solver, clock, _ = window
    observation = wait_for_production(window)
    clock.current = observation.time
    measured_at = clock.now()
    solver.get_order_remaining_time.return_value = 900

    def navigate():
        clock.current += timedelta(seconds=5)

    solver.back_to_infrastructure.side_effect = navigate
    solver.task = observation
    solver.infra_main()
    assert observation.time == measured_at + timedelta(seconds=840)


def test_staffing_dependency_cancels_obsolete_production_observation(window):
    solver, _, order = window
    observation = wait_for_production(window)
    solver.op_data.operators["鸿雪"]._current_room = ""
    solver._resume_failed_tasks()
    solver.task = order
    assert solver.agent_arrange(order.plan) is False
    solver._sync_run_order_tasks()
    assert observation not in solver.tasks
    assert order.run_order_staffing_wait
    assert not getattr(order, "run_order_window_wait", False)
    solver.choose_agent.assert_not_called()


def test_due_long_work_yields_to_measured_order_observation(window):
    solver, clock, order = window
    observation = wait_for_production(window)
    clock.current = observation.time - timedelta(minutes=2)
    ordinary = SchedulerTask(
        clock.now(),
        {f"room_{i}_1": ["Current"] for i in range(1, 4)},
        TaskTypes.SELF_CORRECTION,
    )
    solver.tasks.append(ordinary)
    scheduler_task.scheduling(solver.tasks, execution_time=1, time_now=clock.now())
    assert ordinary.time > observation.time
    assert solver.find_next_task() is observation
    assert order.time < clock.now()
    assert order.execution_failure


def test_future_work_outside_order_horizon_keeps_its_time(window):
    solver, clock, _ = window
    observation = wait_for_production(window)
    original = clock.now() + timedelta(minutes=1)
    ordinary = SchedulerTask(
        original,
        {f"room_{i}_1": ["Current"] for i in range(1, 4)},
        TaskTypes.SELF_CORRECTION,
    )
    solver.tasks.append(ordinary)
    scheduler_task.scheduling(solver.tasks, execution_time=40, time_now=clock.now())
    assert ordinary.time == original
    assert solver.find_next_task() is ordinary
    assert observation.time > clock.now() + timedelta(minutes=10)


def test_room_dispatch_yields_before_measured_production_observation(window):
    solver, clock, _ = window
    observation = wait_for_production(window)
    clock.current = observation.time - timedelta(seconds=30)
    ordinary = SchedulerTask(
        clock.now(), {"contact": ["红"]}, TaskTypes.SELF_CORRECTION
    )
    original_time = ordinary.time
    solver.tasks.append(ordinary)
    solver.task = ordinary
    assert solver._defer_arrangement_for_priority_task("contact", ordinary.plan)
    assert solver.find_next_task() is observation
    assert ordinary.time == original_time
    assert ordinary.plan == {"contact": ["红"]}


def test_mastery_handoff_retains_protection_before_production_observation(window):
    solver, clock, _ = window
    observation = wait_for_production(window)
    clock.current = observation.time - timedelta(minutes=3)
    config.conf.enable_mastery = True
    handoff = SchedulerTask(
        observation.time + timedelta(seconds=20),
        {"train": ["Current", "Current"]},
        TaskTypes.SWAP_SUPPORT,
    )
    solver.tasks.append(handoff)
    deadline = observation.time
    scheduler_task.scheduling(solver.tasks, time_now=clock.now())
    assert handoff.time < deadline
    assert observation.time == deadline
    assert solver.find_next_task() is handoff


def test_strict_mood_release_finishes_before_production_observation(window):
    solver, clock, _ = window
    observation = wait_for_production(window)
    clock.current = observation.time - timedelta(minutes=5)
    release = SchedulerTask(
        observation.time - timedelta(seconds=10),
        {"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]},
        TaskTypes.RELEASE_DORM,
        "黑键",
        strict_mood_limit=True,
    )
    solver.tasks.append(release)
    deadline = observation.time
    scheduler_task.scheduling(
        solver.tasks, time_now=clock.now(), op_data=solver.op_data
    )
    assert release.time + timedelta(minutes=1.5) < deadline
    assert observation.time == deadline
