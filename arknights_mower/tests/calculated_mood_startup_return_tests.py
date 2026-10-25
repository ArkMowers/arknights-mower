"""启动实读完成后先重建普通回班，再从现有队列重新选择任务。"""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, emergency, record
from arknights_mower.tests.calculated_mood_tests import NOW, enable
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def startup(solver, monkeypatch):
    data = enable(solver, monkeypatch)
    monkeypatch.setattr(emergency, "datetime", base_schedule.datetime)
    monkeypatch.setattr(emergency, "save_current_state", lambda: True)
    monkeypatch.setattr(record, "save_agent_action", MagicMock())
    monkeypatch.setattr(base_schedule, "_training_room_scan_disabled", True)
    for name in ("冰酿", "闪灵"):
        data.operators[name].current_room = ""
        data.operators[name].current_index = -1
    op = data.operators["伊内丝"]
    data.update_detail(op.name, 20, "dormitory_1", 2, True)
    solver._emergency_startup_pending = True
    solver.defer_backup_plan_until_mood_read = True
    solver._initial_staffing_pending = False
    solver.emergency_state = None
    solver._startup_run_order_check_pending = False
    solver.find = MagicMock(return_value=(1, 1))
    solver.back_to_infrastructure = MagicMock()
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.back = MagicMock()
    solver.skip = MagicMock()
    solver._read_initial_card_mood = MagicMock()
    solver._prepare_group_shift = MagicMock(side_effect=MowerExit)
    reads = []

    def read_room(room, **kwargs):
        reads.append(room)
        if room == "dormitory_1":
            data.update_detail(op.name, 20, room, 2, True)
            solver._recovery_plan_dirty = True

    solver._read_room_mood = MagicMock(side_effect=read_room)
    old = SchedulerTask(
        time=NOW - timedelta(minutes=1),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={op.room: [op.name]},
    )
    solver.task = old
    solver.tasks = [old]
    return solver, op, old, reads


def test_startup_read_replaces_due_ordinary_return_before_any_arrangement(startup):
    solver, op, old, reads = startup
    assert solver.infra_main() is True
    assert "dormitory_1" in reads
    assert not solver._emergency_startup_pending
    assert not solver.defer_backup_plan_until_mood_read
    assert all(task is not old for task in solver.tasks)
    assert solver.task is None
    solver._prepare_group_shift.assert_not_called()
    replacement = next(
        task
        for task in solver.tasks
        if task.type == TaskTypes.SHIFT_ON and op.name in task.plan.get(op.room, [])
    )
    # 无宿管技能的五级宿舍每小时恢复 4；普通回班沿用八分钟提前量。
    assert replacement.time == NOW + timedelta(minutes=52)
    assert replacement.time > NOW
    assert solver.find_next_task() is not old


@pytest.mark.parametrize("protection", ["started", "retained", "explicit", "group"])
def test_startup_read_preserves_protected_arrangements_and_special_tasks(
    startup, protection
):
    solver, op, old, reads = startup
    if protection == "started":
        old.mood_physical_started = True
        old.execution_retained = True
    elif protection == "retained":
        old.execution_retained = True
    elif protection == "explicit":
        old.type = TaskTypes.SELF_CORRECTION
        old.backup_explicit_slots = {(op.room, op.index)}
    else:
        old.group_shift_expected = {"恢复组": True}
    special = SchedulerTask(
        time=NOW + timedelta(hours=3),
        task_type=TaskTypes.SKILL_UPGRADE,
    )
    solver.tasks.append(special)
    original_time, original_plan = old.time, dict(old.plan)
    with pytest.raises(MowerExit):
        solver.infra_main()
    assert "dormitory_1" in reads
    assert any(task is old for task in solver.tasks)
    assert any(task is special for task in solver.tasks)
    assert old.time == original_time and old.plan == original_plan
    solver._prepare_group_shift.assert_called_once_with(old)


def test_unfinished_startup_read_retains_dirty_state_and_original_return(startup):
    solver, op, old, reads = startup
    solver._recovery_plan_dirty = True
    solver._emergency_operation_fits = MagicMock(return_value=False)
    original_time = old.time
    assert solver.infra_main() is True
    assert solver._emergency_startup_pending
    assert solver.defer_backup_plan_until_mood_read
    assert solver._recovery_plan_dirty
    assert any(task is old for task in solver.tasks)
    assert old.time == original_time
    assert not reads
    solver._prepare_group_shift.assert_not_called()


def test_startup_read_keeps_failed_return_object_and_original_time(startup):
    solver, op, old, reads = startup
    solver._retain_failed_task(old, "等待原有安排", [op.room])
    original_time, original_plan = old.time, dict(old.plan)
    solver.planned = solver.todo_task = solver.collect_notification = True
    solver.handle_error = MagicMock(return_value=True)
    assert solver.infra_main() is True
    assert "dormitory_1" in reads
    assert any(task is old for task in solver.tasks)
    assert old.time == original_time and old.plan == original_plan
    assert old.retains_execution
    solver._prepare_group_shift.assert_not_called()


def test_normal_observation_refresh_uses_same_identity_check_before_arrangement(
    startup,
):
    solver, op, old, reads = startup
    solver._emergency_startup_pending = False
    solver.defer_backup_plan_until_mood_read = False
    solver._recovery_plan_dirty = True
    assert solver.infra_main() is True
    assert all(task is not old for task in solver.tasks)
    assert solver.task is None
    assert not reads
    solver._prepare_group_shift.assert_not_called()
