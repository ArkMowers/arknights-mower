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
    "outcome", ["submitted", "restarted", "timeout", "cancelled", "transitioning"]
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
        if outcome == "restarted":
            state["scene"] = base.Scene.LOGIN_START
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

    def recover_navigation():
        if outcome == "restarted":
            solver.physical = dorm_recovery_tests.FINAL.copy()
            state["scene"] = base.Scene.INFRA_MAIN

    solver.back_to_infrastructure = MagicMock(side_effect=recover_navigation)
    reads_before = solver.get_agent_from_room.call_count

    if outcome in ("submitted", "restarted"):
        solver.agent_arrange_room({}, ROOM, solver.task.plan)
        assert not solver.task.plan
        assert solver.get_agent_from_room.call_count > reads_before
        assert solver.task is original_task
        assert solver.task.time == original_time
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
    assert solver.back_to_infrastructure.call_count == (
        1 if outcome in ("restarted", "timeout") else 0
    )


def test_single_recovery_submission_timeout_restarts_reads_and_restores_roster(
    solver, monkeypatch
):
    from arknights_mower.utils import solver as solver_module

    monkeypatch.setattr(base.config.conf.waiting_scene, "CONNECTING", (1, 3))
    recovery_sleep = MagicMock()
    monkeypatch.setattr(solver_module, "csleep", recovery_sleep)
    original_task = solver.task
    original_time = original_task.time
    original_plan = original_task.plan
    state = {"page": "infra"}
    temporary = ["杜林", "琴柳", "黑角", "银灰", ""]
    initial = solver.physical.copy()
    observed = []
    solver.recog.w, solver.recog.h = 1920, 1080
    solver.device = MagicMock()
    solver.sleep = MagicMock()
    solver.waiting_scene = [base.Scene.CONNECTING]
    solver.scene.side_effect = lambda: {
        "infra": base.Scene.INFRA_MAIN,
        "details": base.Scene.INFRA_DETAILS,
        "selection": base.Scene.RIIC_OPERATOR_SELECT,
        "connecting": base.Scene.CONNECTING,
        "login": base.Scene.LOGIN_START,
    }[state["page"]]
    solver.enter_room.side_effect = lambda room: state.update(page="details")
    solver.back.side_effect = lambda *args, **kwargs: state.update(page="infra")
    solver.find.side_effect = lambda name, **kwargs: (
        (100, 100)
        if (name, state["page"])
        in {
            ("connecting", "connecting"),
            ("confirm_blue", "selection"),
            ("room_detail", "details"),
        }
        else None
    )

    def tap(*args, **kwargs):
        if state["page"] == "selection":
            solver.physical = solver.selected + [""] * (5 - len(solver.selected))
            solver.confirms.append(solver.physical.copy())
            state["page"] = "connecting" if len(solver.confirms) == 1 else "details"
        else:
            state["page"] = "selection"

    def recover_navigation():
        assert state["page"] == "login"
        assert solver.task is original_task
        assert solver.task.plan is original_plan
        assert original_plan == {ROOM: dorm_recovery_tests.FINAL}
        state["page"] = "infra"

    read = solver.get_agent_from_room.side_effect

    def observe(*args, **kwargs):
        observed.append(solver.physical.copy())
        return read(*args, **kwargs)

    solver.tap = MagicMock(side_effect=tap)
    solver.check_current_focus = MagicMock(
        side_effect=lambda: state.update(page="login")
    )
    solver.back_to_infrastructure = MagicMock(side_effect=recover_navigation)
    solver.get_agent_from_room.side_effect = observe
    solver.tap_confirm = MagicMock(
        wraps=base.BaseSchedulerSolver.tap_confirm.__get__(solver)
    )
    solver.waiting_solver = MagicMock(wraps=solver.waiting_solver)

    solver.agent_arrange_room({}, ROOM, original_plan)

    assert solver.confirms == [temporary, dorm_recovery_tests.FINAL]
    assert observed[:2] == [initial, temporary]
    assert observed[-1] == dorm_recovery_tests.FINAL
    assert solver.physical == dorm_recovery_tests.FINAL
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM
    assert solver.task is original_task
    assert solver.task.time == original_time
    assert solver.task.plan is original_plan
    assert original_plan == {}
    assert any(task is original_task for task in solver.tasks)
    assert not hasattr(original_task, "execution_failure")
    assert solver.choose_agent.call_count == solver.tap_confirm.call_count == 2
    solver.waiting_solver.assert_called_once_with()
    assert solver.sleep.call_args_list == [call(1)] * 3
    solver.device.exit.assert_called_once_with()
    solver.check_current_focus.assert_called_once_with()
    solver.back_to_infrastructure.assert_called_once_with()
    recovery_sleep.assert_called_once_with(3)
