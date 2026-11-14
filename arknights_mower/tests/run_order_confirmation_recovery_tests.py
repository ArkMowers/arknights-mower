"""跑单原班确认失败后，在正常长休眠前补读一次实际驻员。"""

import copy
import pickle
from datetime import datetime
from unittest.mock import Mock

import pytest

from arknights_mower.tests.run_order_restoration_observation_tests import (
    ROOM,
)
from arknights_mower.tests.run_order_restoration_observation_tests import (
    paused_restoration as paused_restoration,
)
from arknights_mower.tests.scheduler_recovery_preservation_tests import (
    scheduler as scheduler,
)
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    blocked_run_order_ids,
)

REASON = "干员确认点击未生效，返回房间重试"
ORIGINAL_TIME = datetime(2026, 10, 30, 0, 3, 57, 770149)


@pytest.fixture
def confirmation_restoration(paused_restoration, monkeypatch):
    case = paused_restoration
    solver, task = case.solver, case.restore
    case.scheduler.clock.current = datetime(2026, 10, 30, 0, 7, 34)
    task.time = ORIGINAL_TIME
    case.order.time = datetime(2026, 10, 30, 1, 40, 40)
    solver.op_data.operators["但书"].time_stamp = datetime(2026, 10, 30, 0, 7, 16)
    solver._retain_failed_task(task, REASON, [ROOM])
    solver.handle_error()
    case.patrol = next(t for t in solver.tasks if t.type == TaskTypes.NOT_SPECIFIC)
    assert case.patrol.time == datetime(2026, 10, 30, 2, 37, 34)
    solver.planned = solver.todo_task = solver.collect_notification = True
    solver.back_to_infrastructure = Mock()
    solver._refresh_observed_recovery_tasks = Mock()
    solver._refresh_workshop_inventory = Mock()
    solver._schedule_maintenance_backup_check = Mock()
    solver._idle_sleep = Mock()
    solver.choose_agent = Mock(side_effect=AssertionError("实读不应执行选人"))
    solver.tap_confirm = Mock(side_effect=AssertionError("实读不应重复确认"))
    solver.accept_order = Mock(side_effect=AssertionError("原班恢复不应重新接单"))
    solver.drone = Mock(side_effect=AssertionError("原班恢复不应加速"))
    solver.get_order_remaining_time = Mock(
        side_effect=AssertionError("原班恢复不应读取订单倒计时")
    )
    monkeypatch.setattr(case.scheduler.module, "sync_replacement_checks", Mock())
    case.persisted = []

    def save():
        case.persisted.append(pickle.loads(pickle.dumps(solver.tasks)))
        return True

    case.save = Mock(side_effect=save)
    monkeypatch.setattr(case.scheduler.module, "save_current_state", case.save)
    read = solver.get_agent_from_room

    def observe(room, *args, **kwargs):
        if kwargs.get("strict_observation"):
            saved = next(
                t
                for t in case.persisted[-1]
                if getattr(t, "run_order_restore_pending", False)
            )
            assert saved.confirmation_recovery_rooms[room] == "consumed"
        return read(room, *args, **kwargs)

    solver.get_agent_from_room = Mock(side_effect=observe)
    return case


def test_confirmation_read_reopens_original_task_before_long_idle(
    confirmation_restoration,
):
    case = confirmation_restoration
    solver, task = case.solver, case.restore
    original_plan = copy.deepcopy(task.plan)
    assert solver.find_next_task() is case.patrol

    assert solver.infra_main() is True

    solver.get_agent_from_room.assert_called_once_with(ROOM, strict_observation=True)
    assert not getattr(task, "execution_failure", None)
    assert solver.find_next_task() is task
    solver.rest_until_next_task()
    solver._idle_sleep.assert_not_called()
    assert task.plan == original_plan and task.time == ORIGINAL_TIME
    assert task.run_order_original_roster == original_plan
    assert task.run_order_restore_pending and task.meta_data == ""
    assert id(case.order) in blocked_run_order_ids(solver.tasks, solver.op_data)
    assert case.save.call_count == 1
    case.scheduler.io.assert_not_called()


def test_confirmed_original_roster_finishes_before_shared_next_order(
    confirmation_restoration,
):
    case = confirmation_restoration
    solver, task = case.solver, case.restore
    solver.read_screen.return_value = "图耶"
    assert solver.infra_main() is True
    assert not getattr(task, "execution_failure", None)
    assert id(case.order) in blocked_run_order_ids(solver.tasks, solver.op_data)

    solver.task = solver.find_next_task()
    assert solver.task is task
    solver.infra_main()

    assert all(pending is not task for pending in solver.tasks)
    assert task.time == ORIGINAL_TIME
    assert not hasattr(task, "run_order_restore_pending")
    assert not hasattr(task, "run_order_original_roster")
    assert id(case.order) not in blocked_run_order_ids(solver.tasks, solver.op_data)
    assert solver.find_next_task(task_type=TaskTypes.RUN_ORDER) is case.order
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    solver.accept_order.assert_not_called()
    solver.drone.assert_not_called()
    solver.get_order_remaining_time.assert_not_called()
    case.scheduler.io.assert_not_called()


@pytest.mark.parametrize("mode", ["unknown", "short", "exception", "no_revision"])
def test_incomplete_confirmation_read_is_consumed_without_repeated_dispatch(
    confirmation_restoration, mode
):
    case = confirmation_restoration
    solver, task = case.solver, case.restore
    failure, original_plan = task.execution_failure, copy.deepcopy(task.plan)

    def read(*args, **kwargs):
        solver.op_data.operators["但书"].time_stamp = case.scheduler.clock.now()
        if mode == "exception":
            raise RuntimeError("实读失败")
        if mode == "short":
            return []
        return (
            [{"agent": "", "observed": False}]
            if mode == "unknown"
            else [{"agent": "但书"}]
        )

    solver.get_agent_from_room.side_effect = read
    assert solver.infra_main() is True
    for _ in range(4):
        solver._resume_failed_tasks()
        solver.infra_main()
        assert task.execution_failure is failure
        assert solver.find_next_task() is case.patrol
    solver.get_agent_from_room.assert_called_once_with(ROOM, strict_observation=True)
    assert task.confirmation_recovery_rooms[ROOM] == "consumed"
    assert task.plan == original_plan and task.time == ORIGINAL_TIME
    assert task.run_order_restore_pending
    assert id(case.order) in blocked_run_order_ids(solver.tasks, solver.op_data)
    assert case.save.call_count == 1
    case.scheduler.io.assert_not_called()


def test_consumed_confirmation_read_survives_restart_and_repeated_failure(
    confirmation_restoration,
):
    case = confirmation_restoration
    solver = case.solver
    assert solver.infra_main() is True
    solver.tasks = case.persisted[-1]
    restored = next(
        task
        for task in solver.tasks
        if getattr(task, "run_order_restore_pending", False)
    )
    solver._retain_failed_task(restored, REASON, [ROOM])
    for _ in range(4):
        solver.scene.return_value = case.scheduler.module.Scene.LOGIN_START
        assert solver._observe_failed_arrangement_confirmation() is False
        solver.scene.return_value = case.scheduler.module.Scene.INFRA_MAIN
        solver._resume_failed_tasks()
        assert solver._observe_failed_arrangement_confirmation() is False
    assert restored.execution_failure
    assert restored.time == ORIGINAL_TIME
    solver.get_agent_from_room.assert_called_once()
    assert case.save.call_count == 1
    case.scheduler.io.assert_not_called()


def test_failed_restoration_keeps_consumed_read_and_shared_order_blocked(
    confirmation_restoration,
):
    case = confirmation_restoration
    solver, task = case.solver, case.restore
    assert solver.infra_main() is True
    solver.agent_arrange = Mock(
        side_effect=case.scheduler.module.RecognizeError(REASON)
    )
    solver.task = solver.find_next_task()
    assert solver.task is task
    solver.infra_main()
    failure = task.execution_failure
    for _ in range(4):
        solver._resume_failed_tasks()
        solver.infra_main()
        assert task.execution_failure is failure
    assert task.confirmation_recovery_rooms[ROOM] == "consumed"
    assert task.time == ORIGINAL_TIME and task.plan == task.run_order_original_roster
    assert id(case.order) in blocked_run_order_ids(solver.tasks, solver.op_data)
    solver.agent_arrange.assert_called_once()
    solver.get_agent_from_room.assert_called_once_with(ROOM, strict_observation=True)
    assert case.save.call_count == 1
    case.scheduler.io.assert_not_called()


@pytest.mark.parametrize("save_result", [False, "exception"])
def test_confirmation_read_requires_successful_persistence(
    confirmation_restoration, save_result
):
    case = confirmation_restoration
    solver, task = case.solver, case.restore
    case.save.side_effect = (
        RuntimeError("保存失败") if save_result == "exception" else None
    )
    case.save.return_value = False
    assert solver.infra_main() is True
    for _ in range(4):
        assert solver._observe_failed_arrangement_confirmation() is False
    solver.get_agent_from_room.assert_not_called()
    assert task.execution_failure
    assert task.plan == task.run_order_original_roster
    assert task.time == ORIGINAL_TIME
    assert case.save.call_count == 1
    case.scheduler.io.assert_not_called()


def test_due_independent_order_precedes_confirmation_read(confirmation_restoration):
    case = confirmation_restoration
    solver, task = case.solver, case.restore
    independent = SchedulerTask(
        case.scheduler.clock.now(),
        {"room_3_1": ["伺夜"]},
        TaskTypes.RUN_ORDER,
        "room_3_1",
    )
    solver.tasks.append(independent)
    solver.agent_arrange = Mock()
    solver.task = independent
    solver.infra_main()
    solver.agent_arrange.assert_called_once()
    solver.get_agent_from_room.assert_not_called()
    case.save.assert_not_called()
    assert all(pending is not independent for pending in solver.tasks)
    assert task.execution_failure
    assert solver.infra_main() is True
    solver.get_agent_from_room.assert_called_once_with(ROOM, strict_observation=True)
    assert not getattr(task, "execution_failure", None)
    case.scheduler.io.assert_not_called()


@pytest.mark.parametrize("stage", ["insertion", "non_confirmation", "no_restoration"])
def test_only_original_roster_confirmation_failures_get_the_read(
    confirmation_restoration, stage
):
    case = confirmation_restoration
    solver, task = case.solver, case.restore
    if stage == "insertion":
        task.meta_data = ROOM
    elif stage == "non_confirmation":
        task.execution_failure["reason"] = "房间名单未识别"
    else:
        del task.run_order_restore_pending
    assert solver._observe_failed_arrangement_confirmation() is False
    solver.get_agent_from_room.assert_not_called()
    case.save.assert_not_called()
