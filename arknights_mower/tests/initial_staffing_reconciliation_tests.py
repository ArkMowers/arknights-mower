"""清零启动实读后的驻员纠错和普通轮休任务展示。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.observed_group_return_tests import solver as solver
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

pytestmark = pytest.mark.usefixtures("offline_maintenance")


def test_reset_releases_stale_fixed_cover_before_ordinary_recovery(solver):
    data = solver.op_data
    data.group_shift_state.clear()
    solver._initial_staffing_pending = True
    solver.defer_backup_plan_until_mood_read = False
    release = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_3": ["Current", "Current", "Free", "Current", "Current"]},
        meta_data="能天使",
    )
    solver.tasks = [release]
    solver.find_next_task = lambda *a, task_type=None, **kw: next(
        (t for t in solver.tasks if task_type is None or t.type == task_type), None
    )
    assert solver._reconcile_initial_staffing()
    correction = next(t for t in solver.tasks if t.type == TaskTypes.SELF_CORRECTION)
    assert correction.plan["dormitory_2"][0] == "流明"
    assert any(t is release for t in solver.tasks)
    assert data.operators["妮芙"].current_room == "dormitory_2"
    assert not solver._initial_staffing_pending
    solver.task = correction
    solver._prepare_group_shift(correction)
    solver._prepare_shift_cycle(correction)
    solver._prepare_group_shift(correction, remember_targets=True)
    assert correction.plan["dormitory_2"][0] == "流明"
    solver.op_data = data.project_arrangements([correction.plan])
    assert solver._complete_group_shift(correction)
    assert not solver.op_data.is_dorm_replacement("妮芙")
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("blocked", ["unread", "retained_shift", "backup", "rescue"])
def test_initial_reconciliation_waits_for_actual_dependencies(solver, blocked):
    solver._initial_staffing_pending = True
    solver.defer_backup_plan_until_mood_read = blocked == "unread"
    if blocked in ("retained_shift", "backup"):
        task = SchedulerTask(
            task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["能天使"]}
        )
        if blocked == "backup":
            task.backup_shift_active = True
        else:
            task.execution_failure = {"reason": "waiting"}
        solver.tasks = [task]
    if blocked == "rescue":
        solver._emergency_active = lambda: True
    solver.agent_get_mood = MagicMock()
    assert not solver._reconcile_initial_staffing()
    assert solver._initial_staffing_pending
    solver.agent_get_mood.assert_not_called()


def test_resumed_state_does_not_run_reset_reconciliation(solver):
    solver._initial_staffing_pending = False
    solver.agent_get_mood = MagicMock()
    assert not solver._reconcile_initial_staffing()
    solver.agent_get_mood.assert_not_called()


@pytest.mark.parametrize("ordinary", [False, True])
def test_task_format_distinguishes_ordinary_coordination_without_mutation(ordinary):
    at = datetime(2026, 10, 17, 3, 57, 38)
    task = SchedulerTask(time=at, task_type=TaskTypes.EXHAUST_OFF, meta_data="令,絮雨")
    if ordinary:
        task.ordinary_coordination = True
    formatted = task.format(8)
    assert formatted.type == ("轮休协调" if ordinary else "用尽下班")
    assert formatted.time == at + timedelta(hours=8)
    assert task.type == TaskTypes.EXHAUST_OFF
    assert task.time == at


def test_startup_observation_reconciles_despite_release_and_future_return(solver):
    solver.op_data.group_shift_state.clear()
    solver._initial_staffing_pending = True
    solver._emergency_startup_pending = True
    solver.defer_backup_plan_until_mood_read = True
    release = SchedulerTask(task_type=TaskTypes.RELEASE_DORM, meta_data="能天使")
    future = SchedulerTask(
        time=datetime.now() + timedelta(hours=2),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": ["绮良"]},
    )
    solver.tasks = [release, future]
    solver._emergency_replan_releases = MagicMock()
    solver._emergency_operation_fits = lambda seconds: True
    solver._read_initial_card_mood = MagicMock()
    solver._queue_initial_fia = lambda: False
    solver.backup_plan_solver = MagicMock()
    solver._emergency_save = MagicMock()
    solver._emergency_startup()
    corrections = [t for t in solver.tasks if t.type == TaskTypes.SELF_CORRECTION]
    assert corrections, "初始化须生成恢复宿管、释放旧替班的实际任务"
    assert corrections[0].plan["dormitory_2"][0] == "流明"
    assert not solver._initial_staffing_pending
    assert not solver._emergency_startup_pending
    assert any(t is future for t in solver.tasks)
    assert any(t is release for t in solver.tasks)
    solver._read_agent_mood.assert_called_once()
    solver.enter_room.assert_not_called()


def test_task_api_exposes_ordinary_name_and_preserves_dispatch_type(
    solver, monkeypatch
):
    from types import SimpleNamespace

    from flask import Flask

    from arknights_mower import __main__ as main
    from arknights_mower.views import task as task_view

    ordinary = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF)
    ordinary.ordinary_coordination = True
    exhausted = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF)
    solver.tasks = [ordinary, exhausted]
    monkeypatch.setattr(main, "base_scheduler", solver)
    monkeypatch.setattr(
        task_view, "mower_thread", SimpleNamespace(is_alive=lambda: True)
    )
    app = Flask(__name__)
    app.register_blueprint(task_view.task_bp)
    response = app.test_client().get("/task")
    assert response.status_code == 200
    rows = response.get_json()
    assert [row["display_name"] for row in rows] == ["轮休协调", "用尽下班"]
    assert ordinary.type == exhausted.type == TaskTypes.EXHAUST_OFF


def test_reset_preserves_observed_low_mood_group_recovery(solver):
    data = solver.op_data.project_arrangements(
        [
            {
                "central": ["夕", "令"],
                "meeting": ["能天使"],
                "dormitory_2": ["妮芙", "冰酿", "森蚺", "绮良", "Free"],
            }
        ]
    )
    data.group_shift_state.clear()
    for name in ("森蚺", "绮良"):
        data.operators[name].mood = 3
        data.operators[name].time_stamp = datetime.now()
    solver.op_data = data
    solver._initial_staffing_pending = True
    solver.defer_backup_plan_until_mood_read = False
    solver._reconcile_initial_staffing()
    for task in solver.tasks:
        assert task.plan.get("central", ["Current"])[0] != "森蚺"
        assert task.plan.get("meeting", ["Current"])[0] != "绮良"
        assert task.plan.get("dormitory_2", ["Current"])[0] != "流明"
    assert data.operators["森蚺"].is_resting()
    assert data.operators["绮良"].is_resting()


def test_blocked_dependency_release_retries_once_without_changing_task(solver):
    solver._initial_staffing_pending = True
    solver.defer_backup_plan_until_mood_read = False
    solver.op_data.group_shift_state.clear()
    pending = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["能天使"]}
    )
    at = pending.time
    pending.execution_failure = {"reason": "waiting"}
    solver.tasks = [pending]
    for _ in range(3):
        assert not solver._reconcile_initial_staffing()
        assert solver.tasks == [pending]
        assert pending.time == at
    solver.tasks.clear()
    assert solver._reconcile_initial_staffing()
    correction = solver.tasks[-1]
    assert not solver._reconcile_initial_staffing()
    assert solver.tasks == [correction]
