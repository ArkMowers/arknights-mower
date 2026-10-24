"""确认冲突恢复原任务后，真实运行快照保留尚未完成的换班并可重新载入。"""

import copy
from contextlib import nullcontext
from datetime import datetime, timedelta
from threading import Event
from unittest.mock import MagicMock

import pytest

from arknights_mower import __main__ as mower
from arknights_mower.solvers import base_schedule, record
from arknights_mower.tests.dorm_group_tests import (
    apply_plan,
    configure_explicit_free_bed,
)
from arknights_mower.tests.dorm_group_tests import solver as solver
from arknights_mower.tests.dorm_state_restore_tests import (
    recovery_snapshot as recovery_snapshot,
)
from arknights_mower.tests.pending_dorm_context_tests import prepare_scheduler_entry
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.mark.parametrize("interleaved", [False, True])
def test_conflict_restart_retains_completed_room_recovery(
    recovery_snapshot, monkeypatch, tmp_path, interleaved
):
    solver, task, incoming, due = recovery_snapshot
    task.plan = {"dormitory_2": ["闪灵", "杜林", "Free", "Free", "Free"]}
    task.group_shift_expected["dormitory_2", 2] = "能天使"
    future = SchedulerTask(
        time=task.time + timedelta(hours=4), task_type=TaskTypes.SHIFT_ON
    )
    # 未开始的未来任务不能覆盖本次已经观测到的换班意图。
    future.group_shift_transitions = {
        group: not resting for group, resting in task.group_shift_transitions.items()
    }
    solver.tasks.append(future)
    if interleaved:
        intervening = SchedulerTask(time=task.time)
        task.time = datetime.now() + timedelta(minutes=1)
        solver.tasks.insert(0, intervening)
    for attr in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, attr, datetime.now().date())
    solver.task_count = 7
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(mower, "base_scheduler", solver)
    monkeypatch.setattr(mower.device_control, "run", lambda **kw: nullcontext())
    monkeypatch.setattr(mower, "resource_task_session", nullcontext)
    monkeypatch.setattr(mower, "_close_device_session", MagicMock())
    monkeypatch.setattr(mower, "_cancel_maintenance_timer", MagicMock())
    monkeypatch.setattr(
        record,
        "get_path",
        lambda path: tmp_path if path == "@app/tmp" else tmp_path / "record.db",
    )
    monkeypatch.setattr(record, "_tables_created", False)

    def stopped_loop(saved):
        assert solver._check_group_shift_targets(
            task.plan["dormitory_2"], "dormitory_2", reason="最终选人"
        )
        assert not config.stop_mower.is_set()

    monkeypatch.setattr(mower, "_main", stopped_loop)
    mower.main({})
    assert not config.stop_mower.is_set() and mower.base_scheduler is None
    saved = record.load_state()
    assert any(bed.name == incoming and bed.time == due for bed in saved["dorm"])
    resumed = object.__new__(base_schedule.BaseSchedulerSolver)
    resumed.__dict__.update(solver.__dict__)
    resumed.global_plan = copy.deepcopy(solver.global_plan)
    resumed.tasks, resumed.task = [], None
    resumed.emergency_state = None
    config.stop_mower.clear()
    monkeypatch.setattr(mower, "initialize", lambda *a, **kw: resumed)
    monkeypatch.setattr(mower.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(mower, "refresh_resource_at_boundary", lambda: None)
    prepare_scheduler_entry(resumed, monkeypatch)

    def resume_remaining_room():
        if resumed.run.call_count > 1:
            pytest.fail("unexpected scheduler recovery during snapshot restoration")
        try:
            base_schedule.BaseSchedulerSolver.run(resumed)
            if interleaved:
                assert not getattr(resumed.task, "group_shift_expected", {})
                resumed.tasks.remove(resumed.task)
                resumed.tasks[0].time = datetime.now() - timedelta(seconds=1)
                base_schedule.BaseSchedulerSolver.run(resumed)
            assert resumed.task.group_shift_expected
            assert "dormitory_1" not in resumed.task.plan
            data = resumed.op_data
            context = resumed._execution_group_transitions()
            assert (
                data.get_dorm_by_name(incoming, group_transitions=context)[1].time
                == due
            )
            assert data.group_shift_state == saved["group_shift_state"]
            for index, name in enumerate(resumed.task.plan["dormitory_2"]):
                if name not in ("Free", "Current", ""):
                    data.update_detail(
                        name, 5, "dormitory_2", index, group_transitions=context
                    )
            resumed.task.plan.clear()
            assert resumed._complete_group_shift(resumed.task)
            data.correct_dorm()
        except Exception as exc:
            pytest.fail(f"snapshot restoration failed: {exc}")
        raise base_schedule.MowerExit

    resumed.run = MagicMock(side_effect=resume_remaining_room)
    mower.simulate(saved)
    resumed.run.assert_called_once()
    bed = resumed.op_data.get_dorm_by_name(incoming)[1]
    assert bed is not None and (bed.name, bed.time) == (incoming, due)
    assert resumed.tasks[-1].time == future.time


def test_conflict_saves_remaining_task_before_worker_cleanup_and_resumes(
    solver, monkeypatch, tmp_path
):
    configure_explicit_free_bed(solver)
    solver.op_data.commit_group_shifts({"联动": False})
    apply_plan(solver, {"meeting": ["陈", "初雪"], "contact": ["红"]})
    task = SchedulerTask(
        time=datetime.now() - timedelta(seconds=1),
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"dormitory_1": ["Free", "冰酿", "泥岩", "能天使", "年"]},
    )
    task.group_shift_transitions = {"联动": True}
    task.group_shift_expected = {("dormitory_1", 0): "银灰"}
    follow = SchedulerTask(
        time=task.time + timedelta(hours=4), task_plan={"meeting": ["伊内丝", "银灰"]}
    )
    solver.task, solver.tasks = task, [task, follow]
    for attr in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, attr, datetime.now().date())
    solver.task_count = 7
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(mower, "base_scheduler", solver)
    monkeypatch.setattr(mower.device_control, "run", lambda **kw: nullcontext())
    monkeypatch.setattr(mower, "resource_task_session", nullcontext)
    monkeypatch.setattr(mower, "_close_device_session", MagicMock())
    monkeypatch.setattr(mower, "_cancel_maintenance_timer", MagicMock())
    monkeypatch.setattr(
        record,
        "get_path",
        lambda path: tmp_path if path == "@app/tmp" else tmp_path / "record.db",
    )
    monkeypatch.setattr(record, "_tables_created", False)
    # 已落盘旧状态中仍有兜底名单，退出必须用恢复后的目标替换它。
    assert record.save_current_state()

    def stopped_loop(saved):
        assert solver._check_group_shift_targets(
            task.plan["dormitory_1"], "dormitory_1", reason="执行边界准入与床位整理"
        )
        assert not config.stop_mower.is_set()

    monkeypatch.setattr(mower, "_main", stopped_loop)
    mower.main({})
    assert not config.stop_mower.is_set() and mower.base_scheduler is None
    mower._close_device_session.assert_called_once()
    saved = record.load_state()
    restored, restored_follow = saved["tasks"]
    assert restored is not task and restored.time == task.time
    assert restored.plan == {"dormitory_1": ["银灰", "冰酿", "泥岩", "能天使", "年"]}
    assert restored.group_shift_expected == task.group_shift_expected
    assert restored.group_shift_transitions == {"联动": True}
    assert saved["group_shift_state"] == solver.op_data.group_shift_state
    assert not saved["group_shift_state"]["联动"]
    assert restored_follow.plan == follow.plan and restored_follow.time == follow.time

    resumed = object.__new__(base_schedule.BaseSchedulerSolver)
    resumed.__dict__.update(solver.__dict__)
    resumed.global_plan = copy.deepcopy(solver.global_plan)
    resumed.tasks, resumed.task = [], None
    resumed.emergency_state = None
    config.stop_mower.clear()
    monkeypatch.setattr(mower, "initialize", lambda *a, **kw: resumed)
    monkeypatch.setattr(mower.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(mower, "refresh_resource_at_boundary", lambda: None)
    monkeypatch.setattr(record, "save_agent_action", lambda *a, **kw: None)

    def resume_remaining_room():
        assert resumed.tasks == saved["tasks"]
        assert resumed.task_count == 7
        assert resumed.op_data.get_current_room("meeting", True) == ["陈", "初雪"]
        resumed.task = resumed.tasks[0]
        assert not resumed.op_data.group_is_resting("联动")
        resumed._prepare_group_shift(resumed.task, remember_targets=True)
        row = resumed.task.plan["dormitory_1"]
        resumed.prepare_dorm_selection(row, "dormitory_1")
        assert row[0] == "银灰"
        assert "meeting" not in resumed.task.plan and "contact" not in resumed.task.plan
        apply_plan(resumed, {"dormitory_1": row})
        resumed.task.plan.clear()
        assert resumed._complete_group_shift(resumed.task)
        assert resumed.op_data.group_is_resting("联动")
        raise base_schedule.MowerExit

    resumed.run = MagicMock(side_effect=resume_remaining_room)
    mower.simulate(saved)
    resumed.run.assert_called_once()


@pytest.mark.parametrize(
    "recovery_snapshot", ["free_only", "mixed_dynamic"], indirect=True
)
@pytest.mark.parametrize("case", ["unstarted", "explicit_return", "retired"])
def test_restart_does_not_open_beds_from_ineligible_or_overridden_shifts(
    recovery_snapshot, monkeypatch, case
):
    solver, task, incoming, _ = recovery_snapshot
    if case == "unstarted":
        task.group_shift_expected = {}
    elif case == "explicit_return":
        task.plan = {"meeting": ["伊内丝", "银灰"]}
    for attr in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, attr, datetime.now().date())
    solver.task_count = 7
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(mower, "base_scheduler", solver)
    saved = copy.deepcopy(record.current_state())
    if case == "retired":
        saved["backup_plan_names"] = ["retired"]
    monkeypatch.setattr(mower, "initialize", lambda *a, **kw: solver)
    monkeypatch.setattr(mower.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(mower, "refresh_resource_at_boundary", lambda: None)
    solver.emergency_state = None
    solver.tasks, solver.task = [], None
    solver.run = MagicMock(side_effect=base_schedule.MowerExit)

    mower.simulate(saved)

    solver.run.assert_called_once()
    assert solver.op_data.group_shift_state == saved["group_shift_state"]
    assert all(not bed.name for bed in solver.op_data.all_dorms())
    assert solver.op_data.get_current_operator("dormitory_1", 0).name == incoming
    if case == "retired":
        assert solver.tasks == []


@pytest.mark.parametrize("failure", [False, RuntimeError("snapshot unavailable")])
def test_save_failure_keeps_running_and_reports_non_durable_task(
    solver, monkeypatch, failure
):
    task = SchedulerTask(task_plan={"dormitory_1": ["Free"]})
    task.group_shift_expected = {("dormitory_1", 0): "银灰"}
    solver.task, solver.tasks = task, [task]
    monkeypatch.setattr(config, "stop_mower", Event())
    save = MagicMock(return_value=failure)
    if isinstance(failure, Exception):
        save.side_effect = failure
    monkeypatch.setattr(base_schedule, "save_current_state", save)
    error = MagicMock()
    monkeypatch.setattr(base_schedule.logger, "warning", error)
    agents = ["Free"]
    before = task.time
    assert solver._check_group_shift_targets(agents, "dormitory_1", reason="最终选人")
    assert agents == ["银灰"] and task.time == before
    assert not config.stop_mower.is_set()
    assert task.plan == {"dormitory_1": ["银灰"]}
    assert "保存失败" in error.call_args.args[0]
    assert "仅保留在内存" in error.call_args.args[0]
    assert "已保存" not in error.call_args.args[0]
    save.assert_called_once()
    error.assert_called_once()
