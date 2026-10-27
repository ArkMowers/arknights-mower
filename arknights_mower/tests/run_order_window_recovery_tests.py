"""倒计时判定漏单后重新规划，旧版等待不阻塞新订单或原班恢复。"""

import pickle
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests.emergency_compensation_tests import selection_harness
from arknights_mower.tests.run_order_planning_wakeup_tests import replay as replay
from arknights_mower.utils import config
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


@pytest.mark.parametrize("remaining", [0, -1, 660, 900, 7155.5])
def test_pre_swap_miss_retires_stale_order_and_plans_next_order(window, remaining):
    solver, clock, order = window
    solver.get_order_remaining_time.return_value = remaining
    original_time = order.time

    solver.infra_main()

    base.send_message.assert_called_once_with("检测到漏单！", level="WARNING")
    assert order not in solver.tasks
    assert order.time == original_time
    assert solver.op_data.operators["鸿雪"].time_stamp is None
    assert solver.op_data.get_current_room(ROOM, True) == ["鸿雪"]
    assert not getattr(order, "run_order_restore_pending", False)
    solver.choose_agent.assert_not_called()
    solver.accept_order.assert_not_called()
    solver.drone.assert_not_called()
    refresh = solver.find_next_task()
    assert refresh.type == TaskTypes.REFRESH_TIME and refresh.meta_data == ROOM
    assert refresh.time == clock.now()
    for _ in range(3):
        solver._resume_failed_tasks()
        solver._queue_missing_run_order_reads()
    assert solver.tasks == [refresh]
    solver.get_order_remaining_time.assert_called_once()

    next_time = clock.now() + timedelta(hours=1)
    solver.get_run_order_time.return_value = next_time
    solver.task = refresh
    solver.infra_main()
    assert refresh not in solver.tasks
    next_order = solver.find_next_task()
    assert next_order is not order
    assert next_order.type == TaskTypes.RUN_ORDER
    assert next_order.time == next_time
    assert next_order.plan == {ROOM: ["但书"]}
    assert not getattr(next_order, "execution_failure", None)


@pytest.mark.parametrize("remaining", [0, -1, 60, 900])
def test_post_swap_miss_notifies_and_restores_without_completed_order_evidence(
    window, remaining
):
    solver, _, order = window
    solver.get_order_remaining_time.side_effect = [30, remaining]

    solver.infra_main()

    base.send_message.assert_called_once_with("检测到漏单！", level="WARNING")
    assert solver.op_data.get_current_room(ROOM, True) == ["鸿雪"]
    assert order not in solver.tasks
    assert not getattr(order, "run_order_restore_pending", False)
    assert [c.args[0] for c in solver.choose_agent.call_args_list] == [
        ["但书"],
        ["鸿雪"],
    ]
    solver.accept_order.assert_called_once()
    solver.drone.assert_not_called()


@pytest.mark.parametrize("remaining", [1, 30, 659.5])
def test_in_window_order_keeps_normal_insertion_and_restoration(window, remaining):
    solver, _, order = window
    solver.get_order_remaining_time.side_effect = [remaining, 5]

    solver.infra_main()

    base.send_message.assert_not_called()
    assert order not in solver.tasks
    assert solver.op_data.get_current_room(ROOM, True) == ["鸿雪"]
    solver.accept_order.assert_called_once()
    assert [c.args[0] for c in solver.choose_agent.call_args_list] == [
        ["但书"],
        ["鸿雪"],
    ]


@pytest.mark.parametrize("remaining", [0, -1, 5502.5])
@pytest.mark.parametrize("with_observation", [False, True])
def test_saved_countdown_failure_becomes_one_normal_order_read(
    window, remaining, with_observation
):
    solver, clock, order = window
    solver._retain_failed_task(
        order, f"订单倒计时 {remaining} 秒不在跑单窗口，尚未确认漏单", [ROOM]
    )
    if with_observation:
        order.run_order_window_wait = True
        observation = SchedulerTask(
            clock.now() + timedelta(hours=2),
            task_type=TaskTypes.REFRESH_TIME,
            meta_data=ROOM,
        )
        observation.run_order_window_observation = True
        solver._retain_failed_task(
            observation, "订单生产复核未取得有效正倒计时", [ROOM]
        )
        solver.tasks.append(observation)
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    obsolete = list(solver.tasks)
    for _ in range(3):
        solver._resume_failed_tasks()
    assert all(task not in solver.tasks for task in obsolete)
    assert len(solver.tasks) == 1
    refresh = solver.find_next_task()
    assert refresh.type == TaskTypes.REFRESH_TIME and refresh.meta_data == ROOM
    assert refresh.time == clock.now()
    assert not getattr(refresh, "execution_failure", None)
    assert solver.op_data.operators["鸿雪"].time_stamp is None
    solver.choose_agent.assert_not_called()
    solver.get_order_remaining_time.assert_not_called()

    unrelated = SchedulerTask(clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(unrelated)
    solver.task = unrelated
    solver.仓库扫描 = MagicMock()
    solver.infra_main()
    solver.仓库扫描.assert_called_once()
    assert solver.tasks == [refresh]
    next_time = clock.now() + timedelta(hours=1)
    solver.get_run_order_time.return_value = next_time
    solver.task = refresh
    solver.infra_main()
    assert len(solver.tasks) == 1
    assert solver.tasks[0].type == TaskTypes.RUN_ORDER
    assert solver.tasks[0].time == next_time


def test_saved_observation_without_parent_replans_once(window):
    solver, clock, _ = window
    observation = SchedulerTask(
        clock.now() + timedelta(hours=1),
        task_type=TaskTypes.REFRESH_TIME,
        meta_data=ROOM,
    )
    observation.run_order_window_observation = True
    solver.tasks = [observation]
    for _ in range(3):
        solver._resume_failed_tasks()
    assert observation not in solver.tasks
    assert len(solver.tasks) == 1
    assert solver.find_next_task().time == clock.now()


def test_saved_started_restoration_and_unrelated_failure_keep_original_work(window):
    solver, clock, order = window
    order.run_order_restore_pending = True
    order.run_order_original_roster = {ROOM: ["鸿雪"]}
    order.run_order_window_wait = True
    solver._retain_failed_task(order, "原班选人失败", [ROOM])
    unrelated = SchedulerTask(
        clock.now(), {"contact": ["红"]}, TaskTypes.SELF_CORRECTION
    )
    solver.tasks.append(unrelated)
    solver._retain_failed_task(unrelated, "普通换班失败", ["contact"])
    observation = SchedulerTask(task_type=TaskTypes.REFRESH_TIME, meta_data=ROOM)
    observation.run_order_window_observation = True
    solver.tasks.append(observation)
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    order, unrelated, observation = solver.tasks
    original_time = order.time
    for _ in range(3):
        solver._resume_failed_tasks()
    assert solver.tasks == [order, unrelated]
    assert order.time == original_time
    assert order.run_order_original_roster == {ROOM: ["鸿雪"]}
    assert order.execution_failure["reason"] == "原班选人失败"
    assert unrelated.execution_failure["reason"] == "普通换班失败"
    solver.get_order_remaining_time.assert_not_called()


def test_retained_order_confirmation_still_uses_new_calibration(window, monkeypatch):
    solver, clock, order = window
    order.execution_retained = True
    order.time = clock.now() - timedelta(hours=1)
    solver.get_order_remaining_time.return_value = 120
    result = solver.agent_arrange_room({}, ROOM, order.plan)
    assert order.run_order_calibrated_time == clock.now() + timedelta(seconds=60)
    solver.find = MagicMock(return_value=None)
    monkeypatch.setattr(config, "screenshot_avg", 0)
    solver.sleep.reset_mock()
    base.BaseSchedulerSolver.tap_confirm(solver, ROOM, result)
    solver.sleep.assert_called_once_with(119.0)


@pytest.mark.parametrize("miss_before_swap", [False, True])
def test_two_slot_miss_never_leaves_trade_agent_as_original_roster(
    window, miss_before_swap
):
    solver, _, order = window
    solver.op_data.plan[ROOM].append(Room("Free", "", []))
    solver.op_data.operators["深巡"]._current_room = ROOM
    solver.op_data.operators["深巡"].current_index = 1
    order.plan[ROOM] = ["Current", "但书"]
    solver.get_order_remaining_time.side_effect = (
        [900] if miss_before_swap else [30, 900]
    )

    solver.infra_main()

    assert order not in solver.tasks
    assert solver.op_data.get_current_room(ROOM, True) == ["鸿雪", "深巡"]
    assert not getattr(order, "run_order_restore_pending", False)
    assert solver.find_next_task().type == TaskTypes.REFRESH_TIME
    if miss_before_swap:
        solver.choose_agent.assert_not_called()
    else:
        assert [c.args[0] for c in solver.choose_agent.call_args_list] == [
            ["鸿雪", "但书"],
            ["鸿雪", "深巡"],
        ]


def test_post_swap_miss_keeps_failed_restoration_until_actual_roster_is_restored(
    window,
):
    solver, clock, order = window
    solver.get_order_remaining_time.side_effect = [30, 900]
    choose = solver.choose_agent.side_effect

    def fail_restoration(row, room, **kwargs):
        if row == ["鸿雪"]:
            raise base.RoomArrangementDeferred(room, RuntimeError("原班确认失败"))
        return choose(row, room, **kwargs)

    solver.choose_agent.side_effect = fail_restoration
    solver.infra_main()

    assert order in solver.tasks
    assert order.run_order_restore_pending
    assert order.run_order_original_roster == {ROOM: ["鸿雪"]}
    assert solver.op_data.get_current_room(ROOM, True) == ["但书"]
    assert not any(task.type == TaskTypes.REFRESH_TIME for task in solver.tasks)
    base.send_message.assert_called_once_with("检测到漏单！", level="WARNING")

    solver.choose_agent.side_effect = choose
    original_time = order.time
    failure = order.execution_failure
    choices = solver.choose_agent.call_count
    for _ in range(3):
        clock.current += timedelta(minutes=2)
        solver._resume_failed_tasks()
        assert solver.tasks == [order]
        assert order.execution_failure is failure
        assert order.time == original_time
        assert order.plan == {ROOM: ["鸿雪"]}
        assert solver.find_next_task() is None
        assert solver.choose_agent.call_count == choices

    unrelated = SchedulerTask(clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(unrelated)
    solver.仓库扫描 = MagicMock()
    solver.task = solver.find_next_task()
    assert solver.task is unrelated
    solver.infra_main()
    solver.仓库扫描.assert_called_once()
    assert solver.tasks == [order]
    assert order.execution_failure is failure
    assert order.time == original_time
    assert solver.choose_agent.call_count == choices

    solver._reconcile_room_observation(ROOM, [{"agent": "但书"}])
    solver._resume_failed_tasks()
    assert not getattr(order, "execution_failure", None)
    assert order.time == original_time
    solver.task = solver.find_next_task()
    assert solver.task is order
    solver.infra_main()
    assert order not in solver.tasks
    assert not getattr(order, "run_order_restore_pending", False)
    assert solver.op_data.get_current_room(ROOM, True) == ["鸿雪"]
    assert solver.get_order_remaining_time.call_count == 2
    assert [c.args[0] for c in solver.choose_agent.call_args_list].count(["但书"]) == 1


def test_legacy_wait_marker_does_not_discard_unrelated_execution_failure(window):
    solver, _, order = window
    order.run_order_window_wait = True
    solver._retain_failed_task(order, "选人失败", [ROOM])
    original_time, original_plan = order.time, order.plan.copy()
    for _ in range(3):
        solver._resume_failed_tasks()
    assert solver.tasks == [order]
    assert order.time == original_time and order.plan == original_plan
    assert order.execution_failure["reason"] == "选人失败"
    assert solver.find_next_task() is None


def test_saved_emergency_countdown_failure_restores_snapshot_before_replanning(window):
    solver, _, order = window
    order.emergency_original_roster = {ROOM: ["鸿雪"]}
    solver.op_data.operators["鸿雪"]._current_room = ""
    solver.op_data.operators["但书"]._current_room = ROOM
    solver.op_data.operators["但书"].current_index = 0
    solver._retain_failed_task(order, "订单倒计时 900 秒不在跑单窗口", [ROOM])
    original_time = order.time
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    order = solver.tasks[0]
    for _ in range(3):
        solver._resume_failed_tasks()
    assert solver.tasks == [order]
    assert order.time == original_time
    assert order.run_order_restore_pending
    assert order.plan == {ROOM: ["鸿雪"]}
    assert not getattr(order, "execution_failure", None)
    solver.task = order
    solver.infra_main()
    assert order not in solver.tasks
    assert solver.op_data.get_current_room(ROOM, True) == ["鸿雪"]
    solver.get_order_remaining_time.assert_not_called()
    solver.accept_order.assert_not_called()
    assert [c.args[0] for c in solver.choose_agent.call_args_list] == [["鸿雪"]]
