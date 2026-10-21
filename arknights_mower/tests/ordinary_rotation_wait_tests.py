"""普通互斥、恢复等待和旧缓存接续不伪装为用尽失败。"""

from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import exhaust_replacement_tests
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = exhaust_replacement_tests.solver
pytestmark = pytest.mark.usefixtures("offline_maintenance")


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
            t.type == TaskTypes.NOT_SPECIFIC
            and not getattr(t, "replacement_check", None)
            and t.time <= datetime.now()
            for t in solver.tasks
        )
        == 1
    )
    (check,) = [t for t in solver.tasks if getattr(t, "replacement_check", None)]
    assert check.replacement_check == {
        "owner": "苍苔",
        "cover": "引星棘刺",
        "room": "room_2_2",
        "index": 0,
    }
