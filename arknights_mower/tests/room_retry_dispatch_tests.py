"""房间失败在安全边界让出队列，重试仍以实际驻员为准。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, call

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import dorm_recovery_tests
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = dorm_recovery_tests.solver
ROOM = dorm_recovery_tests.ROOM


@pytest.fixture(autouse=True)
def isolated_feedback(monkeypatch):
    for name, value in (
        ("operation_feedback_avg", None),
        ("operation_feedback_count", 0),
        ("operation_feedback_mode", None),
        ("operation_feedback_cap", None),
        ("operation_failure_streak", 0),
        ("operation_recovery_successes", 0),
    ):
        monkeypatch.setattr(base.config, name, value)


@pytest.mark.parametrize("urgent", [False, True])
def test_persistent_room_failure_has_bounded_attempts(solver, urgent):
    solver.enter_room.side_effect = RuntimeError("room names unreadable")
    original = solver.task.plan.copy()
    if urgent:
        solver.tasks.append(
            SchedulerTask(
                task_type=TaskTypes.FIAMMETTA,
                time=datetime.now() + timedelta(seconds=30),
            )
        )
    with pytest.raises(base.RoomArrangementDeferred) as error:
        solver.agent_arrange_room({}, ROOM, solver.task.plan)
    assert error.value.room == ROOM
    assert solver.enter_room.call_count == (1 if urgent else 4)
    assert solver.task.plan == original
    solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA])
def test_temporary_swap_sequences_keep_original_retry(solver, kind):
    solver.task.type = kind
    solver.enter_room.side_effect = RuntimeError("room names unreadable")
    solver.tasks.append(SchedulerTask(task_type=TaskTypes.SWAP_SUPPORT))
    with pytest.raises(RuntimeError) as error:
        solver.agent_arrange_room({}, ROOM, solver.task.plan)
    assert not isinstance(error.value, base.RoomArrangementDeferred)
    assert solver.enter_room.call_count == 4


def test_deferred_retry_reads_actual_room_without_repeating_successful_selection(
    solver,
):
    solver.task.arrangement_retry_room = ROOM
    solver.task.arrangement_retry_count = 3
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver.physical = dorm_recovery_tests.FINAL.copy()
    before = solver.get_agent_from_room.call_count
    solver.agent_arrange_room({}, ROOM, solver.task.plan)
    assert solver.get_agent_from_room.call_count > before
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    assert not solver.task.plan
    assert not hasattr(solver.task, "arrangement_retry_room")


def test_page_exit_recovery_reads_actual_occupants_without_confirming(solver):
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)

    def leave_selection(*args, **kwargs):
        solver.physical = dorm_recovery_tests.FINAL.copy()
        raise base.AgentSelectionPageChanged("页面退出，结果未知")

    solver.choose_agent.side_effect = leave_selection
    reads_before = solver.get_agent_from_room.call_count
    solver.agent_arrange_room({}, ROOM, solver.task.plan)
    solver.choose_agent.assert_called_once()
    solver.tap_confirm.assert_not_called()
    assert solver.get_agent_from_room.call_count > reads_before
    assert not solver.task.plan


def test_persistent_page_exit_retains_pending_task_and_bounded_retry(solver):
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver.choose_agent.side_effect = base.AgentSelectionPageChanged("页面退出")
    original = solver.task.plan.copy()
    with pytest.raises(base.RoomArrangementDeferred):
        solver.agent_arrange_room({}, ROOM, solver.task.plan)
    assert solver.choose_agent.call_count == 4
    solver.tap_confirm.assert_not_called()
    assert solver.task.plan == original


@pytest.mark.parametrize(
    "outcome", ["submitted", "timeout", "cancelled", "transitioning"]
)
def test_room_recovery_does_not_back_through_pending_submission(solver, outcome):
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver.waiting_scene = [base.Scene.CONNECTING, base.Scene.LOADING]
    state = {"scene": base.Scene.INFRA_MAIN}
    solver.scene.side_effect = lambda: state["scene"]
    original = {room: names.copy() for room, names in solver.task.plan.items()}
    original_time = solver.task.time
    original_task = solver.task

    def submission_pending(*args):
        state["scene"] = base.Scene.CONNECTING
        raise base.RecognizeError("干员确认结果尚未读回")

    def finish_wait():
        if outcome == "cancelled":
            raise base.MowerExit
        if outcome == "timeout":
            return False
        if outcome == "transitioning":
            state["scene"] = (
                base.Scene.LOADING
                if state["scene"] == base.Scene.CONNECTING
                else base.Scene.CONNECTING
            )
            return True
        solver.physical = dorm_recovery_tests.FINAL.copy()
        state["scene"] = base.Scene.INFRA_MAIN
        return True

    solver.tap_confirm.side_effect = submission_pending
    solver.waiting_solver = MagicMock(side_effect=finish_wait)

    if outcome == "submitted":
        solver.agent_arrange_room({}, ROOM, solver.task.plan)
        assert not solver.task.plan
        # 返回动作只用于结束已读回确认的房间流程。
        assert solver.back.call_args_list == [call(0.5)]
    else:
        expected = (
            base.MowerExit if outcome == "cancelled" else base.RoomArrangementDeferred
        )
        with pytest.raises(expected):
            solver.agent_arrange_room({}, ROOM, solver.task.plan)
        assert solver.task is original_task
        assert solver.task.plan == original
        assert solver.task.time == original_time
        assert any(task is original_task for task in solver.tasks)
        solver.back.assert_not_called()
    assert solver.waiting_solver.call_args_list == [call()] * (
        4 if outcome == "transitioning" else 1
    )
    solver.choose_agent.assert_called_once()
    solver.tap_confirm.assert_called_once()
