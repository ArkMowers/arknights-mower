"""确认结果未知时只补一次完整实读，不重新选人或跳过原任务阶段。"""

import copy
import pickle
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import dorm_recovery_tests
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

base = dorm_recovery_tests.base_schedule
solver = dorm_recovery_tests.solver
ROOM = dorm_recovery_tests.ROOM
REASON = "干员确认联网等待超时，返回房间重试"


@pytest.fixture
def recovery(solver, monkeypatch):
    task = solver.task
    task.arrangement_retry_room = ROOM
    task.arrangement_retry_count = 1
    solver._retain_failed_task(task, REASON, [ROOM])
    solver.physical = dorm_recovery_tests.FINAL.copy()
    observe = solver.get_agent_from_room.side_effect

    def read(room, *args, **kwargs):
        if kwargs.pop("strict_observation", False):
            assert persisted[-1].confirmation_recovery_rooms[room] == "consumed"
        rows = observe(room, *args, **kwargs)
        solver._reconcile_room_observation(room, rows)
        return rows

    solver.get_agent_from_room.side_effect = read
    solver.get_agent_from_room.reset_mock()
    solver.back_to_infrastructure = Mock()
    solver._refresh_observed_recovery_tasks = Mock()
    solver._sync_run_order_tasks = Mock()
    solver.planned = solver.todo_task = solver.collect_notification = True
    solver.handle_error = Mock(return_value=True)
    monkeypatch.setattr(base, "sync_replacement_checks", Mock())
    persisted = []

    def save():
        persisted.append(pickle.loads(pickle.dumps(solver.tasks[0])))
        return True

    save_state = Mock(side_effect=save)
    monkeypatch.setattr(base, "save_current_state", save_state)
    return solver, task, save_state, persisted


@pytest.mark.parametrize(
    "kind, scheduled_at, reason",
    [
        (
            TaskTypes.RE_ORDER,
            "2026-10-27T00:05:04.085196",
            "干员确认画面仍未稳定，返回房间重试",
        ),
        (TaskTypes.SHIFT_OFF, "2026-10-27T13:43:30.264445", REASON),
    ],
)
def test_infra_main_observes_retained_confirmation_without_staffing(
    recovery, kind, scheduled_at, reason
):
    solver, task, save, persisted = recovery
    task.type, task.time = kind, datetime.fromisoformat(scheduled_at)
    task.execution_failure["reason"] = reason
    original_plan, original_time = copy.deepcopy(task.plan), task.time
    task.backup_shift_active = True
    task.dorm_recovery_restore = [ROOM]
    task.group_shift_expected = {(ROOM, 3): "银灰"}

    assert solver.infra_main() is True

    solver.get_agent_from_room.assert_called_once_with(ROOM, strict_observation=True)
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    assert not getattr(task, "execution_failure", None)
    assert task.plan == original_plan and task.time == original_time
    assert task.backup_shift_active and task.dorm_recovery_restore == [ROOM]
    assert task.group_shift_expected == {(ROOM, 3): "银灰"}
    assert any(pending is task for pending in solver.tasks)
    assert persisted[0].confirmation_recovery_rooms[ROOM] == "consumed"
    assert persisted[0].execution_failure
    assert save.call_count == 1


@pytest.mark.parametrize(
    "mode", ["unknown", "short", "exception", "no_revision", "duplicate"]
)
def test_failed_or_partial_read_never_reopens_or_repeats(recovery, mode):
    solver, task, save, _ = recovery
    original_plan, original_time = copy.deepcopy(task.plan), task.time
    failure = task.execution_failure
    task.plan[ROOM][2], task.plan[ROOM][4] = "Free", "Current"
    original_plan = copy.deepcopy(task.plan)

    def read(*args, **kwargs):
        solver.op_data.operators["银灰"].time_stamp = datetime.now() + timedelta(
            seconds=1
        )
        if mode == "exception":
            raise base.RecognizeError("房间名单未核实")
        rows = [{"agent": name} for name in solver.physical]
        if mode == "unknown":
            rows[2] = {"agent": "", "observed": False}
        if mode == "short":
            rows.pop()
        if mode == "duplicate":
            rows[2] = rows[3].copy()
            solver.op_data.room_observations[ROOM] = 1
        return rows

    solver.get_agent_from_room.side_effect = read
    assert solver._observe_failed_arrangement_confirmation() is True
    for _ in range(4):
        solver._resume_failed_tasks()
        assert solver._observe_failed_arrangement_confirmation() is False
        assert task.execution_failure is failure
    solver.get_agent_from_room.assert_called_once()
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    assert task.plan == original_plan and task.time == original_time
    assert save.call_count == 1


@pytest.mark.parametrize("outcome", [False, "exception"])
def test_permission_is_not_used_without_a_successful_save(recovery, outcome):
    solver, task, save, _ = recovery
    if outcome == "exception":
        save.side_effect = RuntimeError("保存失败")
    else:
        save.side_effect = None
        save.return_value = False
    solver._observe_failed_arrangement_confirmation()
    assert solver._observe_failed_arrangement_confirmation() is False
    solver.enter_room.assert_not_called()
    solver.get_agent_from_room.assert_not_called()
    assert save.call_count == 1
    assert task.execution_failure


def test_consumed_permission_survives_restart_and_repeated_failure(recovery):
    solver, task, save, persisted = recovery
    solver._observe_failed_arrangement_confirmation()
    restored = persisted[0]
    solver.tasks, solver.task = [restored], restored
    solver._retain_failed_task(restored, REASON, [ROOM])
    for _ in range(4):
        assert solver._observe_failed_arrangement_confirmation() is False
        solver.scene.return_value = base.Scene.LOGIN_START
        assert solver._observe_failed_arrangement_confirmation() is False
        solver.scene.return_value = base.Scene.INFRA_MAIN
    assert restored.execution_failure
    solver.get_agent_from_room.assert_called_once()
    assert save.call_count == 1


def test_saved_failure_without_permission_field_gets_one_read(recovery):
    solver, task, _, _ = recovery
    task.__dict__.pop("confirmation_recovery_rooms", None)
    solver.tasks = [pickle.loads(pickle.dumps(task))]
    solver.task = solver.tasks[0]
    assert solver._observe_failed_arrangement_confirmation() is True
    assert solver.tasks[0].confirmation_recovery_rooms[ROOM] == "consumed"
    assert not getattr(solver.tasks[0], "execution_failure", None)


@pytest.mark.parametrize(
    "kind",
    [
        TaskTypes.RUN_ORDER,
        TaskTypes.FIAMMETTA,
        TaskTypes.SWAP_SUPPORT,
        TaskTypes.SKILL_UPGRADE,
    ],
)
def test_specialized_compensation_keeps_its_existing_recovery(recovery, kind):
    solver, task, save, _ = recovery
    task.type = kind
    assert solver._observe_failed_arrangement_confirmation() is False
    solver.get_agent_from_room.assert_not_called()
    save.assert_not_called()
    assert task.execution_failure


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA])
def test_due_priority_work_precedes_the_observation(recovery, kind):
    solver, task, save, _ = recovery
    priority = SchedulerTask(time=datetime.now(), task_type=kind)
    solver.tasks.append(priority)
    solver.task = priority
    assert solver._observe_failed_arrangement_confirmation() is False
    assert task.execution_failure
    solver.get_agent_from_room.assert_not_called()
    save.assert_not_called()
    solver.tasks.remove(priority)
    solver.task = task
    assert solver._observe_failed_arrangement_confirmation() is True
    solver.get_agent_from_room.assert_called_once()


def test_waiting_for_login_does_not_consume_the_observation(recovery):
    solver, task, save, _ = recovery
    solver.scene.return_value = base.Scene.LOGIN_START
    assert solver._observe_failed_arrangement_confirmation() is False
    save.assert_not_called()
    solver.scene.return_value = base.Scene.INFRA_MAIN
    assert solver._observe_failed_arrangement_confirmation() is True
    solver.get_agent_from_room.assert_called_once()


def test_existing_related_observation_is_not_swallowed_by_recovery(recovery):
    solver, task, save, _ = recovery
    solver.op_data.room_observations[ROOM] = 1
    solver._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert solver._observe_failed_arrangement_confirmation() is False
    solver.get_agent_from_room.assert_not_called()
    save.assert_not_called()


@pytest.mark.parametrize("near_order_window", [False, True])
def test_two_close_orders_only_delay_observation_inside_their_window(
    recovery, monkeypatch, near_order_window
):
    solver, task, save, _ = recovery

    class Clock(datetime):
        @classmethod
        def now(cls):
            return (
                datetime(2026, 10, 27, 14, 49)
                if near_order_window
                else datetime(2026, 10, 27, 13, 51, 37)
            )

    monkeypatch.setattr(base, "datetime", Clock)
    orders = [
        SchedulerTask(
            time=datetime(2026, 10, 27, 14, 50, 6),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_2_1",
        ),
        SchedulerTask(
            time=datetime(2026, 10, 27, 14, 54, 10),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_1_1",
        ),
    ]
    solver.tasks.extend(orders)
    original_time, original_plan = task.time, copy.deepcopy(task.plan)
    assert solver._observe_failed_arrangement_confirmation() is not near_order_window
    if near_order_window:
        for _ in range(3):
            assert solver._observe_failed_arrangement_confirmation() is False
        solver.get_agent_from_room.assert_not_called()
        save.assert_not_called()
        assert task.execution_failure
        # 已完成的跑单退出队列后，同一原任务取得尚未消费的实读机会。
        solver.tasks[:] = [pending for pending in solver.tasks if pending not in orders]
        assert solver._observe_failed_arrangement_confirmation() is True
    solver.get_agent_from_room.assert_called_once_with(ROOM, strict_observation=True)
    assert save.call_count == 1
    assert task.time == original_time and task.plan == original_plan


def test_complete_observation_preserves_and_then_executes_single_recovery(recovery):
    solver, task, _, _ = recovery
    task.dorm_recovery_restore = [ROOM]
    original_plan = copy.deepcopy(task.plan)
    assert solver._observe_failed_arrangement_confirmation() is True
    assert task.plan == original_plan and task.dorm_recovery_restore == [ROOM]
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()

    solver.agent_arrange_room({}, ROOM, task.plan)

    assert solver.confirms == [
        ["杜林", "琴柳", "黑角", "银灰", ""],
        dorm_recovery_tests.FINAL,
    ]
    assert not task.plan and task.dorm_recovery_restore == []
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM


def test_cancelled_observation_stays_consumed_without_more_navigation(recovery):
    solver, task, save, _ = recovery
    solver.get_agent_from_room.side_effect = base.MowerExit
    with pytest.raises(base.MowerExit):
        solver._observe_failed_arrangement_confirmation()
    assert task.execution_failure
    assert task.confirmation_recovery_rooms[ROOM] == "consumed"
    solver.back_to_infrastructure.assert_not_called()
    assert save.call_count == 1
    assert solver._observe_failed_arrangement_confirmation() is False


def test_other_room_failures_use_the_existing_observation_policy(recovery):
    solver, task, save, _ = recovery
    task.execution_failure["reason"] = "房间姓名未识别"
    assert solver._observe_failed_arrangement_confirmation() is False
    save.assert_not_called()
    solver.get_agent_from_room.assert_not_called()
