"""挂起整批换班允许相同目标的到期回班先释放床位。"""

import pickle
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import native_recovery_execution_tests as recovery
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

resting = recovery.resting
solver = recovery.solver
pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def waiting_batch(resting):
    scheduler, _ = resting
    for name in ("伊内丝", "银灰", "讯使"):
        scheduler.op_data.operators[name].mood = 24
    waiting = recovery.returning_task()
    waiting.type = TaskTypes.SELF_CORRECTION
    waiting.time = datetime.now() - timedelta(minutes=10)
    # 保存的副表已生效，但尚未进入选人或提交换班；没有可命名的阻塞组。
    waiting.backup_shift_active = True
    waiting.group_shift_expected = {}
    scheduler.tasks = [waiting]
    scheduler._suspend_group_shift(waiting, set())
    returning = recovery.returning_task()
    returning.time = datetime.now() - timedelta(minutes=2)
    scheduler.tasks = [returning]
    return scheduler, waiting, returning


@pytest.mark.parametrize("restore", [False, True])
def test_due_agreed_return_dispatches_without_consuming_waiting_batch(
    waiting_batch, monkeypatch, restore
):
    scheduler, waiting, returning = waiting_batch
    if restore:
        scheduler.tasks, scheduler.waiting_group_shifts = pickle.loads(
            pickle.dumps((scheduler.tasks, scheduler.waiting_group_shifts))
        )
        returning = scheduler.tasks[0]
        waiting = scheduler.waiting_group_shifts[0]
    original_time, original_plan = waiting.time, deepcopy(waiting.plan)
    return_time = returning.time
    recovery.prepare_dispatch(scheduler, monkeypatch)
    scheduler._prepare_group_shift(returning)
    for _ in range(3):
        scheduler._prepare_shift_cycle(returning)
        assert returning.plan.get("meeting") == ["伊内丝", "银灰"]
        assert returning.plan.get("contact") == ["讯使"]
        assert scheduler.waiting_group_shifts == [waiting]
        assert waiting.plan == original_plan and waiting.time == original_time
        assert returning.time == return_time
    scheduler.task = returning
    scheduler.infra_main()
    assert scheduler.op_data.operators["伊内丝"].current_room == "meeting"
    assert scheduler.op_data.operators["讯使"].current_room == "contact"
    scheduler.agent_arrange.assert_called_once()
    assert not any(task is returning for task in scheduler.tasks)
    assert sum(task is waiting for task in scheduler.tasks) == 1
    assert waiting.time == original_time
    assert not scheduler.waiting_group_shifts
    scheduler.task = waiting
    scheduler.infra_main()
    assert not any(task is waiting for task in scheduler.tasks)
    scheduler.plan_metadata()
    assert not any(task.type == TaskTypes.SHIFT_ON for task in scheduler.tasks)
    scheduler.enter_room.assert_not_called()


@pytest.mark.parametrize(
    "started",
    ["mood_physical_started", "derived_correction_started", "group_shift_expected"],
)
def test_started_batch_keeps_shared_return_reservations(waiting_batch, started):
    scheduler, waiting, returning = waiting_batch
    setattr(
        waiting,
        started,
        {("meeting", 0): "伊内丝"} if started == "group_shift_expected" else True,
    )
    scheduler._prepare_shift_cycle(returning)
    assert not returning.plan
    assert scheduler.waiting_group_shifts == [waiting]
    assert scheduler.op_data.operators["伊内丝"].is_resting()


def test_different_destination_does_not_release_waiting_reservation(waiting_batch):
    scheduler, waiting, returning = waiting_batch
    waiting.plan["meeting"] = ["陈", "初雪"]
    names, slots = scheduler._waiting_shift_reservations(
        returning_names={"伊内丝", "银灰", "讯使"}
    )
    assert {"陈", "初雪"} <= names
    assert not scheduler._waiting_return_can_progress(returning)
    assert scheduler.op_data.operators["伊内丝"].is_resting()
    assert slots


def test_unrelated_ready_task_runs_with_waiting_batch(waiting_batch, monkeypatch):
    scheduler, waiting, _ = waiting_batch
    task = SchedulerTask(task_type=TaskTypes.CLUE)
    scheduler.tasks, scheduler.task = [task], task
    recovery.prepare_dispatch(scheduler, monkeypatch)
    scheduler._run_clue_flow = Mock(return_value=True)
    scheduler.infra_main()
    scheduler._run_clue_flow.assert_called_once()
    assert scheduler.waiting_group_shifts == [waiting]
    assert not any(queued is task for queued in scheduler.tasks)


def test_product_reservation_keeps_agreed_return_protected(waiting_batch):
    scheduler, waiting, returning = waiting_batch
    waiting.product_shift_locked = True
    names, slots = scheduler._waiting_shift_reservations(
        returning_names={"伊内丝", "银灰", "讯使"}
    )
    assert {"伊内丝", "银灰", "讯使"} <= names
    assert ("dormitory_1", 2) in slots


def test_prerequisite_return_does_not_coalesce_other_due_shifts(waiting_batch):
    scheduler, waiting, returning = waiting_batch
    another = recovery.returning_task()
    another.time = returning.time - timedelta(seconds=1)
    scheduler.tasks.append(another)
    scheduler.resting = Mock(side_effect=AssertionError("前置回班不能再合并普通轮休"))
    scheduler._prepare_group_shift(returning)
    scheduler._prepare_shift_cycle(returning)
    assert returning.plan["meeting"] == ["伊内丝", "银灰"]
    assert any(task is another for task in scheduler.tasks)
    assert scheduler.waiting_group_shifts == [waiting]


def test_mixed_wait_records_its_own_unfinished_return_dependency(waiting_batch):
    scheduler, waiting, _ = waiting_batch
    assert scheduler.op_data.group_is_resting("联动")
    assert "联动" in scheduler._shared_shift_blockers(
        waiting, {"联动": False, "下班组": True}
    )
    scheduler.op_data.commit_group_shifts({"联动": False})
    assert "联动" not in scheduler._shared_shift_blockers(
        waiting, {"联动": False, "下班组": True}
    )


def test_recorded_group_dependency_allows_complete_return_prefix(
    waiting_batch, monkeypatch
):
    scheduler, waiting, returning = waiting_batch
    # 前置整组回班与整批最终的宿舍阵容不同，仍须先恢复该组共享宿管。
    waiting.plan["dormitory_1"] = ["黑角", "Current", "Current", "Current", "Current"]
    waiting.group_shift_waiting = {"联动"}
    scheduler._prepare_group_shift(returning)
    scheduler.resting = Mock(side_effect=AssertionError("前置回班不重新安排下班"))
    scheduler._prepare_shift_cycle(returning)
    assert returning.plan["meeting"] == ["伊内丝", "银灰"]
    assert returning.plan["dormitory_1"][0] == "塑心"
    assert scheduler.waiting_group_shifts == [waiting]


@pytest.mark.parametrize("retained", ["execution_failure", "execution_retained"])
def test_retained_execution_keeps_matching_targets_reserved(waiting_batch, retained):
    scheduler, waiting, returning = waiting_batch
    setattr(
        waiting,
        retained,
        {"reason": "未确认进驻"} if retained == "execution_failure" else True,
    )
    assert not scheduler._waiting_return_can_progress(returning)
    assert "联动" not in scheduler._shared_shift_blockers(
        waiting, {"联动": False, "下班组": True}
    )


def test_pure_return_does_not_wait_for_its_own_group(waiting_batch):
    scheduler, waiting, _ = waiting_batch
    assert "联动" not in scheduler._shared_shift_blockers(waiting, {"联动": False})


def test_mixed_return_wait_does_not_suppress_its_prerequisite_planning(waiting_batch):
    scheduler, waiting, _ = waiting_batch
    waiting.type = TaskTypes.SHIFT_ON
    waiting.group_shift_waiting = {"联动"}
    scheduler.tasks = []
    original_time = waiting.time
    for _ in range(3):
        scheduler.plan_metadata()
        assert scheduler.waiting_group_shifts == [waiting]
        returns = [task for task in scheduler.tasks if task.type == TaskTypes.SHIFT_ON]
        assert len(returns) == 1
        assert returns[0].plan["meeting"] == ["伊内丝", "银灰"]
        assert waiting.time == original_time
