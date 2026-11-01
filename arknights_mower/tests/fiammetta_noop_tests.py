"""满心情目标不产生充能任务，已开始的换人与原班恢复继续执行。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import dorm_group_tests
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = dorm_group_tests.solver
ROOM = "dormitory_1"
TARGET = "冰酿"


@pytest.fixture
def fia_solver(solver):
    solver.op_data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔",
        ROOM,
        index=3,
        current_room=ROOM,
        current_index=3,
        mood=24,
        time_stamp=datetime.now(),
    )
    solver.check_fia = lambda: ([TARGET], ROOM)
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA)
    solver._sync_run_order_tasks = MagicMock()
    return solver


@pytest.mark.parametrize("protection", [False, True])
@pytest.mark.parametrize("threshold", [0.9, 1])
@pytest.mark.parametrize("calculated", [False, True])
def test_full_targets_complete_without_charge_or_retry(
    fia_solver, monkeypatch, protection, threshold, calculated
):
    if calculated:
        from arknights_mower.tests.mood_calculation_projection_consumers_tests import (
            enable,
        )

        enable(fia_solver.op_data, datetime.now(), monkeypatch)
    monkeypatch.setattr(config.conf, "fia_fool", protection)
    monkeypatch.setattr(config.conf, "fia_threshold", threshold)
    independent = SchedulerTask(task_type=TaskTypes.WORKSHOP)
    fia_solver.tasks = [independent]

    fia_solver.plan_fia()

    assert fia_solver.tasks == [independent]
    assert config.conf.fia_fool is protection
    fia_solver.enter_room.assert_not_called()


def test_threshold_one_skips_full_first_target(fia_solver, monkeypatch):
    monkeypatch.setattr(config.conf, "fia_fool", False)
    monkeypatch.setattr(config.conf, "fia_threshold", 1)
    fia_solver.op_data.operators["年"].mood = 23
    fia_solver.op_data.operators["年"].room = ROOM
    fia_solver.check_fia = lambda: ([TARGET, "年"], ROOM)

    fia_solver.plan_fia()

    assert fia_solver.tasks[0].plan == {ROOM: ["年", "菲亚梅塔"]}


@pytest.mark.parametrize("upper_limit", [12, 20, 24])
def test_unprotected_fallback_keeps_nonfull_target_above_threshold(
    fia_solver, monkeypatch, upper_limit
):
    monkeypatch.setattr(config.conf, "fia_fool", False)
    target = fia_solver.op_data.operators[TARGET]
    target.mood, target.upper_limit = 23, upper_limit

    fia_solver.plan_fia()

    assert len(fia_solver.tasks) == 1
    assert fia_solver.tasks[0].plan == {ROOM: [TARGET, "菲亚梅塔"]}
    assert fia_solver.tasks[0].meta_data == TARGET


def test_protected_nonfull_target_retains_existing_threshold_wait(
    fia_solver, monkeypatch
):
    monkeypatch.setattr(config.conf, "fia_fool", True)
    fia_solver.op_data.operators[TARGET].mood = 23

    fia_solver.plan_fia()

    assert len(fia_solver.tasks) == 1
    retry = fia_solver.tasks[0]
    assert retry.plan == {}
    assert retry.time == fia_solver.task.time + timedelta(hours=1.2)
    assert retry.fia_retry_after == retry.time


def test_repeated_full_state_does_not_requeue_and_observed_depletion_allows_charge(
    fia_solver, monkeypatch
):
    monkeypatch.setattr(config.conf, "fia_fool", False)
    independent = SchedulerTask(task_type=TaskTypes.WORKSHOP)
    fia_solver.tasks = [independent]
    fia_solver.find_next_task.side_effect = lambda **kwargs: next(
        (task for task in fia_solver.tasks if task.type == kwargs["task_type"]), None
    )
    for _ in range(3):
        fia_solver.run_order_solver()
        fia_solver.plan_fia()
    assert fia_solver.tasks == [independent]
    fia_solver.enter_room.assert_not_called()

    target = fia_solver.op_data.operators[TARGET]
    target.mood, target.time_stamp = 23, datetime.now()
    fia_solver.enter_room.side_effect = None
    fia_solver.back = MagicMock()
    fia_solver.get_agent_from_room = MagicMock(
        return_value=[{}, {}, {}, {"agent": "菲亚梅塔", "time": datetime.now()}]
    )

    fia_solver.run_order_solver()
    empty_charge = next(
        task for task in fia_solver.tasks if task.type == TaskTypes.FIAMMETTA
    )
    fia_solver.task = empty_charge
    fia_solver.plan_fia()

    assert independent in fia_solver.tasks
    assert any(task.plan == {ROOM: [TARGET, "菲亚梅塔"]} for task in fia_solver.tasks)
    fia_solver.get_agent_from_room.assert_called_once_with(ROOM, [3])


def test_unknown_target_keeps_room_read_before_selection(fia_solver, monkeypatch):
    monkeypatch.setattr(config.conf, "fia_fool", False)
    target = fia_solver.op_data.operators[TARGET]
    target.time_stamp = None
    fia_solver.enter_room.side_effect = None
    fia_solver.back = MagicMock()

    def observe(room, indexes):
        assert (room, indexes) == (ROOM, [1])
        target.mood, target.time_stamp = 20, datetime.now()

    fia_solver.get_agent_from_room = MagicMock(side_effect=observe)

    fia_solver.plan_fia()

    fia_solver.get_agent_from_room.assert_called_once_with(ROOM, [1])
    assert fia_solver.tasks[0].plan == {ROOM: [TARGET, "菲亚梅塔"]}


def test_unknown_target_does_not_suppress_ready_task(fia_solver):
    fia_solver.op_data.operators[TARGET].time_stamp = None
    fia_solver.enter_room.side_effect = None
    fia_solver.back = MagicMock()
    fia_solver.get_agent_from_room = MagicMock(
        return_value=[{}, {}, {}, {"agent": "菲亚梅塔", "time": datetime.now()}]
    )

    fia_solver.run_order_solver()

    assert len(fia_solver.tasks) == 1
    assert fia_solver.tasks[0].type == TaskTypes.FIAMMETTA
    fia_solver.get_agent_from_room.assert_called_once_with(ROOM, [3])


def test_calculated_full_target_can_charge_after_new_lower_observation(
    fia_solver, monkeypatch
):
    from arknights_mower.tests.mood_calculation_projection_consumers_tests import enable

    now = datetime.now()
    monkeypatch.setattr(config.conf, "fia_fool", False)
    enable(fia_solver.op_data, now, monkeypatch)
    for _ in range(3):
        fia_solver.run_order_solver()
        fia_solver.plan_fia()
    assert fia_solver.tasks == []

    fia_solver.op_data.mood_model.observe(TARGET, 23, now)
    fia_solver.run_order_solver()
    assert len(fia_solver.tasks) == 1
    fia_solver.task = fia_solver.tasks[0]
    fia_solver.plan_fia()

    assert fia_solver.tasks[-1].plan == {ROOM: [TARGET, "菲亚梅塔"]}
    fia_solver.enter_room.assert_not_called()


def test_queued_target_reaches_full_before_dispatch_and_independent_work_runs(
    fia_solver,
):
    charge = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA,
        task_plan={ROOM: [TARGET, "菲亚梅塔"]},
        meta_data=TARGET,
    )
    independent = SchedulerTask(task_type=TaskTypes.WORKSHOP)
    fia_solver.tasks, fia_solver.task = [charge, independent], charge
    fia_solver.find = MagicMock(return_value=True)
    fia_solver._refresh_deferred_product_reservations = MagicMock()
    fia_solver.agent_arrange_room = MagicMock(
        side_effect=AssertionError("full target must not be moved")
    )
    fia_solver.craft_material = MagicMock()

    fia_solver.infra_main()
    fia_solver.task = independent
    fia_solver.infra_main()

    assert fia_solver.tasks == []
    assert not getattr(charge, "execution_failure", None)
    fia_solver.agent_arrange_room.assert_not_called()
    fia_solver.craft_material.assert_called_once()


@pytest.mark.parametrize("responsibility", ["restore", "retained", "started"])
def test_full_target_does_not_cancel_restoration_or_started_arrangement(
    fia_solver, responsibility
):
    plan = {ROOM: [TARGET, "菲亚梅塔"]}
    task = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA,
        task_plan=plan,
        meta_data="" if responsibility == "restore" else TARGET,
    )
    if responsibility == "retained":
        task.execution_retained = True
    elif responsibility == "started":
        task.mood_physical_started = True
    original_time = task.time
    fia_solver.task, fia_solver.tasks = task, [task]
    fia_solver.agent_arrange_room = MagicMock(return_value={})

    fia_solver.agent_arrange(plan)

    fia_solver.agent_arrange_room.assert_called_once_with(
        {}, ROOM, plan, get_time=False
    )
    assert fia_solver.tasks == [task]
    assert task.time == original_time
    assert task.plan == plan
