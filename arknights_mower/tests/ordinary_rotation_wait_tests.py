"""普通互斥、恢复等待和旧缓存接续不伪装为用尽失败。"""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import (
    exhaust_replacement_tests,
    native_recovery_execution_tests,
)
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = exhaust_replacement_tests.solver
recovery_solver = native_recovery_execution_tests.solver
pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def recovery_resting(recovery_solver):
    return native_recovery_execution_tests.native_group_recovery_sync_tests.resting.__wrapped__(
        recovery_solver
    )


def test_ordinary_handoff_enqueues_only_concrete_work(solver, caplog):
    solver.task = None
    before = [(b.name, b.time) for b in solver.op_data.dorm]
    for _ in range(3):
        solver._schedule_group_coordination(["机械师"])
    (support,) = solver.tasks
    assert support.type == TaskTypes.SELF_CORRECTION
    assert support.plan == {"room_2_2": ["引星棘刺"]}
    assert not getattr(support, "execution_failure", None)
    assert before == [(b.name, b.time) for b in solver.op_data.dorm]
    assert not [r for r in caplog.records if r.levelno >= 30]


def test_legacy_ordinary_placeholder_is_removed_without_losing_real_tasks(solver):
    ordinary = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="机械师")
    ordinary.ordinary_coordination = True
    ordinary.execution_failure = {"reason": "旧普通互斥"}
    exhausted = solver.task
    real = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"room_3_3": ["槐琥"]}
    )
    real.ordinary_coordination = True
    at = exhausted.time
    solver.tasks = [ordinary, exhausted, real]
    solver._resume_failed_tasks()
    assert all(t is not ordinary for t in solver.tasks)
    assert exhausted in solver.tasks and real in solver.tasks
    assert exhausted.time == at
    wake = [t for t in solver.tasks if t.type == TaskTypes.NOT_SPECIFIC]
    assert len(wake) == 1
    solver._resume_failed_tasks()
    assert len(solver.tasks) == 3


def test_known_recovery_wait_preserves_task_without_error_and_resumes_once(
    recovery_resting, monkeypatch, caplog
):
    scheduler, _ = recovery_resting
    op = scheduler.op_data.operators["讯使"]
    op.rest_in_full = True
    task = native_recovery_execution_tests.returning_task()
    scheduler.tasks = [task]
    before, at = deepcopy(task.plan), task.time

    def read(rooms):
        op.mood, op.time_stamp = 22.5, datetime.now()

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert not scheduler._verify_required_recovery(task)
    assert not [r for r in caplog.records if r.levelno >= 30]
    assert task not in scheduler.tasks
    assert scheduler.waiting_group_shifts == [task]
    for _ in range(3):
        scheduler._resume_waiting_group_shifts()
    assert scheduler.waiting_group_shifts == [task]
    assert task.plan == before and task.time == at
    op.mood, op.time_stamp = 24, datetime.now()
    scheduler._resume_waiting_group_shifts()
    scheduler._resume_waiting_group_shifts()
    assert sum(t is task for t in scheduler.tasks) == 1
    assert not scheduler.waiting_group_shifts


def test_legacy_recovery_failure_becomes_observed_wait(recovery_resting, monkeypatch):
    scheduler, _ = recovery_resting
    op = scheduler.op_data.operators["讯使"]
    op.rest_in_full = True
    task = native_recovery_execution_tests.returning_task()
    task.execution_failure = {"reason": "需要回满的主班尚未实读确认恢复完成"}
    task.execution_retained = True
    scheduler.tasks = [task]
    scheduler._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert scheduler.waiting_group_shifts == [task]
    assert task not in scheduler.tasks


def test_repeated_metadata_does_not_duplicate_waiting_return(
    recovery_resting, monkeypatch
):
    scheduler, _ = recovery_resting
    op = scheduler.op_data.operators["讯使"]
    op.rest_in_full = True
    task = native_recovery_execution_tests.returning_task()
    scheduler.tasks = [task]

    def read(rooms):
        op.mood, op.time_stamp = 22.5, datetime.now()

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert not scheduler._verify_required_recovery(task)
    for _ in range(3):
        scheduler.plan_metadata()
    returns = [t for t in scheduler.tasks if t.type == TaskTypes.SHIFT_ON]
    assert returns == []
    assert scheduler.waiting_group_shifts == [task]


def test_waiting_recovery_survives_snapshot_and_updated_deadline(
    recovery_resting, monkeypatch
):
    import pickle

    from arknights_mower import __main__ as main
    from arknights_mower.solvers.record import current_state

    scheduler, _ = recovery_resting
    op = scheduler.op_data.operators["讯使"]
    op.rest_in_full = True
    task = native_recovery_execution_tests.returning_task()
    scheduler.tasks = [task]

    def read(rooms):
        op.mood, op.time_stamp = 22.5, datetime.now()

    monkeypatch.setattr(scheduler, "_read_recovery_rooms", read)
    assert not scheduler._verify_required_recovery(task)
    for attr in (
        "daily_visit_friend",
        "daily_report",
        "daily_skland",
        "daily_mail",
        "task_count",
    ):
        setattr(scheduler, attr, None)
    monkeypatch.setattr(main, "base_scheduler", scheduler)
    snapshot = pickle.loads(pickle.dumps(current_state()))
    scheduler.tasks = snapshot["tasks"]
    scheduler.waiting_group_shifts = snapshot["waiting_group_shifts"]
    restored = scheduler.waiting_group_shifts[0]
    assert restored.time == task.time and restored.plan == task.plan
    # 原期限读房后，新的真实倒计时延后；更新等待期限而不轮询。
    scheduler.tasks = []
    op.mood, op.time_stamp = 23, datetime.now()
    deadline = datetime.now() + timedelta(minutes=20)
    scheduler.op_data.get_dorm_by_name(op.name)[1].time = deadline
    for _ in range(3):
        scheduler._resume_waiting_group_shifts()
    assert scheduler.waiting_group_shifts == [restored]
    assert len(scheduler.tasks) == 1 and scheduler.tasks[0].time == deadline
    assert not getattr(restored, "execution_failure", None)
    op.mood, op.time_stamp = 24, datetime.now()
    scheduler._resume_waiting_group_shifts()
    assert any(t is restored for t in scheduler.tasks)
    assert not scheduler.waiting_group_shifts


def test_completed_ordinary_handoff_wakes_normal_planning(solver, monkeypatch):
    from unittest.mock import Mock

    from arknights_mower.solvers import base_schedule

    solver.task = None
    solver._schedule_group_coordination(["机械师"])
    (support,) = solver.tasks
    # 普通请求仍需要心情阈值；此夹具原先为用尽测试，改为普通下班。
    solver.op_data.exhaust_agent = []
    solver.op_data.operators["机械师"].exhaust_require = False
    solver.refresh_connecting = False
    solver.find = Mock(return_value=(1, 1))
    solver.skip = Mock()
    solver.back_to_infrastructure = Mock()
    solver.task = support
    future = SchedulerTask(
        time=datetime.now() + timedelta(hours=4),
        task_type=TaskTypes.REFRESH_TIME,
        meta_data="room_3_3",
    )
    solver.tasks.append(future)
    monkeypatch.setattr(
        base_schedule, "protect_priority_tasks", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(solver, "_suppress_train_arrangement", lambda plan: None)
    monkeypatch.setattr(solver, "_suppress_train_correction", lambda plan: None)
    monkeypatch.setattr(solver, "_refresh_orders_after_product_switch", lambda: None)
    monkeypatch.setattr(solver, "_read_recovery_rooms", lambda rooms: None)

    def arrange(plan, *args, **kwargs):
        solver.op_data = solver.op_data.project_arrangements([plan])
        return True

    monkeypatch.setattr(solver, "agent_arrange", arrange)
    assert solver.infra_main()
    assert all(t is not support for t in solver.tasks)
    assert solver.op_data.operators["引星棘刺"].current_room == "room_2_2"
    assert solver.op_data.operators["苍苔"].is_resting()
    assert any(t is future for t in solver.tasks)
    assert any(
        t.type == TaskTypes.SHIFT_ON and "苍苔" in t.plan.get("room_2_2", [])
        for t in solver.tasks
    )
    assert (
        sum(
            t.type == TaskTypes.NOT_SPECIFIC and t.time <= datetime.now()
            for t in solver.tasks
        )
        == 1
    )
