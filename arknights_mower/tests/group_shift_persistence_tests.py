"""确认冲突停止后，真实运行快照保留尚未完成的换班并可重新载入。"""

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
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


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
        try:
            solver._check_group_shift_targets(
                task.plan["dormitory_1"], "dormitory_1", reason="执行边界准入与床位整理"
            )
        except base_schedule.MowerExit:
            return

    monkeypatch.setattr(mower, "_main", stopped_loop)
    mower.main({})
    assert config.stop_mower.is_set() and mower.base_scheduler is None
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


@pytest.mark.parametrize("failure", [False, RuntimeError("snapshot unavailable")])
def test_save_failure_still_stops_and_reports_non_durable_task(
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
    monkeypatch.setattr(base_schedule.logger, "error", error)
    with pytest.raises(base_schedule.GroupShiftTargetConflict) as caught:
        solver._check_group_shift_targets(["Free"], "dormitory_1", reason="最终选人")
    assert config.stop_mower.is_set()
    assert task.plan == {"dormitory_1": ["银灰"]}
    assert "保存失败" in str(caught.value)
    assert "仅保留在内存" in str(caught.value)
    assert "已保存" not in str(caught.value)
    save.assert_called_once()
    error.assert_called_once()
