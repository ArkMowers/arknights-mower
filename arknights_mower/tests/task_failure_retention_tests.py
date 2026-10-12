"""失败不生成计时重试；原任务由新实测或相关安排更新重新准入。"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import jsonpickle
import pytest

from arknights_mower.tests import scheduler_recovery_preservation_tests as recovery
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
    scheduling,
)

scheduler = recovery.scheduler
ROOM = "room_1_1"


@pytest.fixture
def failed_arrangement(scheduler):
    solver = scheduler.solver
    now = scheduler.clock.now()
    solver.op_data.plan = {ROOM: [Room("陈", "", [])]}
    solver.op_data.products = {}
    solver.op_data.facility_states = {}
    solver.op_data.operators = {
        "陈": SimpleNamespace(current_room=ROOM, current_index=0, time_stamp=now)
    }
    for method in (
        "_prepare_shift_cycle",
        "_prepare_group_shift",
        "_switch_products_before_arrangement",
        "_defer_conflicting_product_shift_slots",
        "back_to_infrastructure",
        "_fill_empty_dorms",
        "plan_metadata",
    ):
        setattr(solver, method, Mock())
    solver._complete_group_shift = Mock(return_value=True)
    task = SchedulerTask(now, {ROOM: ["陈"]}, TaskTypes.SELF_CORRECTION)
    later = SchedulerTask(now + timedelta(hours=1), task_type=TaskTypes.SKILL_UPGRADE)
    solver.tasks = [task, later]
    solver.task = task
    solver.agent_arrange = Mock(
        side_effect=scheduler.module.RoomArrangementDeferred(
            ROOM, RuntimeError("读房失败")
        )
    )
    solver.infra_main()
    return solver, task, later


def test_failed_task_preserves_identity_time_and_remaining_plan(failed_arrangement):
    solver, task, later = failed_arrangement
    assert any(queued is task for queued in solver.tasks)
    assert task.time == later.time - timedelta(hours=1)
    assert task.plan == {ROOM: ["陈"]}
    assert task.execution_failure["reason"] == "读房失败"
    assert find_next_task(solver.tasks) is later


def test_elapsed_time_does_not_rearm_failed_work(scheduler, failed_arrangement):
    solver, task, later = failed_arrangement
    original_time = task.time
    for _ in range(8):
        scheduler.clock.current += timedelta(hours=1)
        solver._resume_failed_tasks()
        scheduling(solver.tasks, time_now=scheduler.clock.now(), op_data=solver.op_data)
        assert find_next_task(solver.tasks) is later
        assert task.time == original_time
    solver.agent_arrange.assert_called_once()


@pytest.mark.parametrize("change", ["observation", "occupancy", "target", "layout"])
def test_related_update_rearms_original_task_once(
    scheduler, failed_arrangement, change
):
    solver, task, _ = failed_arrangement
    original_time = task.time
    if change == "observation":
        solver.op_data.operators["陈"].time_stamp += timedelta(seconds=1)
    elif change == "occupancy":
        solver.op_data.operators["陈"].current_room = ""
    elif change == "target":
        task.plan[ROOM] = ["Current"]
    else:
        solver.op_data.plan[ROOM][0].agent = "银灰"
    solver._resume_failed_tasks()
    assert not hasattr(task, "execution_failure")
    assert task.time == original_time
    assert find_next_task(solver.tasks) is task
    solver.agent_arrange.side_effect = None
    solver.task = task
    solver.infra_main()
    assert solver.agent_arrange.call_count == 2
    assert all(queued is not task for queued in solver.tasks)


def test_other_task_dispatches_while_failed_work_is_retained(
    scheduler, failed_arrangement
):
    solver, task, _ = failed_arrangement
    depot = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(depot)
    scan = Mock()
    solver.仓库扫描 = scan
    solver.run()
    scan.assert_called_once()
    solver.agent_arrange.assert_called_once()
    assert any(queued is task for queued in solver.tasks)
    assert all(queued is not depot for queued in solver.tasks)


def test_failure_survives_serialization_and_stale_cleanup(
    scheduler, failed_arrangement
):
    solver, task, _ = failed_arrangement
    restored = jsonpickle.decode(jsonpickle.encode(task))
    solver.tasks = [restored]
    scheduler.clock.current += timedelta(hours=1)
    solver.handle_error(True)
    solver._resume_failed_tasks()
    assert any(queued is restored for queued in solver.tasks)
    assert restored.time == task.time
    assert restored.execution_failure == task.execution_failure
    assert find_next_task([restored]) is None


def test_only_failed_task_keeps_normal_planning_without_replaying(
    scheduler, failed_arrangement
):
    solver, task, _ = failed_arrangement
    solver.tasks = [task]
    solver.run()
    solver.agent_arrange.assert_called_once()
    solver.agent_get_mood.assert_called_once()
    assert any(queued is task for queued in solver.tasks)
    assert task.execution_failure
    assert find_next_task(solver.tasks) is not task


def test_unrelated_observation_does_not_rearm_failure(scheduler, failed_arrangement):
    solver, task, _ = failed_arrangement
    solver.op_data.operators["银灰"] = SimpleNamespace(
        current_room="meeting", current_index=0, time_stamp=scheduler.clock.now()
    )
    solver._resume_failed_tasks()
    assert task.execution_failure


def test_worker_idle_uses_next_dispatchable_task(
    scheduler, failed_arrangement, monkeypatch
):
    solver, task, later = failed_arrangement
    later.time = scheduler.clock.now() + timedelta(minutes=6)
    main = scheduler.main
    monkeypatch.setattr(main, "datetime", scheduler.clock)
    monkeypatch.setattr(main, "initialize", Mock(return_value=solver))
    monkeypatch.setattr(main, "refresh_resource_at_boundary", Mock())
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", Mock(return_value=None))
    monkeypatch.setattr(main, "_apply_version_update_resting_threshold", Mock())
    solver.rest_until_next_task = Mock(side_effect=scheduler.module.MowerExit)
    solver.run = Mock(side_effect=scheduler.module.MowerExit)
    main.simulate(None)
    solver.rest_until_next_task.assert_called_once()
    solver.run.assert_not_called()
    assert task.execution_failure
    assert task.time < later.time


def test_confirmed_production_wait_retains_its_existing_timer(scheduler, monkeypatch):
    monkeypatch.setattr(recovery.config.conf.product_switching, "enable", True)
    solver = scheduler.solver
    task = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.SWITCH_PRODUCT)
    solver.tasks = [task]
    solver.task = task
    solver.switch_base_products = Mock(
        side_effect=scheduler.module.ProductSwitchDeferred(
            "当前一份尚未完成", minutes=2
        )
    )
    solver.infra_main()
    assert task.time == scheduler.clock.now() + timedelta(minutes=2)
    assert not hasattr(task, "execution_failure")
    assert find_next_task(solver.tasks) is task


def test_trade_lock_retains_only_failed_target(scheduler, monkeypatch):
    monkeypatch.setattr(recovery.config.conf.product_switching, "enable", True)
    solver = scheduler.solver
    solver.op_data.products = {}
    solver.op_data.facility_states = {}
    failed = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=f"{ROOM},orundum",
    )
    other = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data="room_1_2,gold",
    )
    solver.tasks, solver.task = [failed, other], failed
    solver.switch_base_products = Mock(
        side_effect=scheduler.module.ProductSwitchFailed("实际贸易站未达到3级", [ROOM])
    )
    solver.infra_main()
    assert failed.execution_failure
    assert not hasattr(other, "execution_failure")
    assert find_next_task(solver.tasks) is other
    assert failed.time == other.time == scheduler.clock.now()
