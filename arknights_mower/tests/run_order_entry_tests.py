import copy
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.run_order_restoration_tests import (
    ORIGINAL,
    ROOM,
    prepare_order,
)
from arknights_mower.tests.run_order_restoration_tests import offline as offline
from arknights_mower.tests.run_order_restoration_tests import solver as solver
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.scheduler_task import TaskTypes


def entry_screen(solver, monkeypatch, frames, *, restoration=False, button=None):
    task, place = prepare_order(solver, monkeypatch)
    if restoration:
        place(task.plan[ROOM])
        task.plan = {ROOM: ORIGINAL.copy()}
        task.meta_data = ""
        task.run_order_original_roster = copy.deepcopy(task.plan)
        task.run_order_restore_pending = True
    state = {
        "scene": Scene.INFRA_MAIN,
        "entered": False,
        "selection_started": False,
        "clock": 0.0,
        "frames": deque(frames),
    }
    initial = frames[0]
    original_choose = solver.choose_agent.side_effect
    original_confirm = solver.tap_confirm.side_effect

    def enter(room):
        state["entered"] = False
        state["scene"] = Scene.INFRA_MAIN
        state["frames"] = deque(frames)

    def find(name, *args, **kwargs):
        if name == "confirm_blue":
            if not state["entered"]:
                state["entered"] = True
                state["scene"] = initial
            return button if button is not None else ((1609, 990), (1740, 1030))
        return None if name == "bill_accelerate" else True

    def sleep(interval=1):
        state["clock"] += interval
        assert state["clock"] <= 100, "未知场景观察没有按已有期限结束"
        if not restoration and not state["selection_started"]:
            assert not getattr(task, "run_order_restore_pending", False)
        if len(state["frames"]) > 1:
            state["frames"].popleft()
            state["scene"] = state["frames"][0]

    def choose(*args, **kwargs):
        assert state["scene"] not in (
            Scene.UNKNOWN,
            Scene.UNDEFINED,
            Scene.CONNECTING,
        ), "尚未取得正常选人画面就开始点击干员"
        state["selection_started"] = True
        return original_choose(*args, **kwargs)

    def confirm(*args, **kwargs):
        original_confirm(*args, **kwargs)
        state["scene"] = Scene.INFRA_MAIN

    def back(*args, **kwargs):
        state["scene"] = Scene.INFRA_MAIN

    solver.enter_room.side_effect = enter
    solver.find.side_effect = find
    solver.scene.side_effect = lambda: state["scene"]
    solver.sleep.side_effect = sleep
    solver.choose_agent.side_effect = choose
    solver.tap_confirm.side_effect = confirm
    solver.back.side_effect = back
    solver.waiting_solver = MagicMock()
    monkeypatch.setattr(base_schedule, "monotonic", lambda: state["clock"])
    return task, state


@pytest.mark.parametrize("restoration", [False, True])
@pytest.mark.parametrize(
    "scene", [Scene.INFRA_ARRANGE_ORDER, Scene.RIIC_OPERATOR_SELECT]
)
@pytest.mark.parametrize("x", [1609, 1724, 1400])
def test_ready_page_keeps_original_button_matching_and_adds_no_wait(
    solver, monkeypatch, restoration, scene, x
):
    task, _ = entry_screen(
        solver,
        monkeypatch,
        [scene],
        restoration=restoration,
        button=((x, 900), (x + 100, 950)),
    )

    solver.agent_arrange_room({}, ROOM, task.plan)

    solver.choose_agent.assert_called_once()
    solver.tap_confirm.assert_called_once()
    solver.sleep.assert_not_called()
    solver.recog.update.assert_not_called()
    solver.waiting_solver.assert_not_called()
    assert ROOM not in task.plan
    for call in solver.find.call_args_list:
        if call.args[0] == "confirm_blue":
            assert call.args == ("confirm_blue",)
            assert not call.kwargs


@pytest.mark.parametrize("restoration", [False, True])
@pytest.mark.parametrize("scene", [Scene.UNKNOWN, Scene.UNDEFINED])
def test_unknown_page_waits_for_new_normal_observation_before_selection(
    solver, monkeypatch, restoration, scene
):
    task, _ = entry_screen(
        solver,
        monkeypatch,
        [scene, Scene.INFRA_ARRANGE_ORDER],
        restoration=restoration,
    )
    solver._selection_profile_snapshot = SimpleNamespace(
        mode="xhigh", low_frame_rate=False, transition_timeout=1, poll_interval=0.25
    )
    original_time = task.time

    solver.agent_arrange_room({}, ROOM, task.plan)

    solver.choose_agent.assert_called_once()
    solver.tap_confirm.assert_called_once()
    assert solver.sleep.call_count == 1
    assert task.time == original_time
    assert ROOM not in task.plan


@pytest.mark.parametrize("restoration", [False, True])
def test_connecting_page_uses_existing_wait_before_selection(
    solver, monkeypatch, restoration
):
    task, state = entry_screen(
        solver,
        monkeypatch,
        [Scene.CONNECTING],
        restoration=restoration,
    )

    def finish_wait(*, restart_on_timeout):
        assert restart_on_timeout is False
        solver.choose_agent.assert_not_called()
        if not restoration:
            assert not getattr(task, "run_order_restore_pending", False)
        state["scene"] = Scene.INFRA_ARRANGE_ORDER
        return True

    solver.waiting_solver.side_effect = finish_wait

    solver.agent_arrange_room({}, ROOM, task.plan)

    solver.waiting_solver.assert_called_once_with(restart_on_timeout=False)
    solver.choose_agent.assert_called_once()
    solver.tap_confirm.assert_called_once()


@pytest.mark.parametrize("restoration", [False, True])
@pytest.mark.parametrize("scene", [Scene.UNKNOWN, Scene.UNDEFINED, Scene.CONNECTING])
def test_unready_page_exhausts_local_recovery_without_selection_or_plan_loss(
    solver, monkeypatch, restoration, scene
):
    task, state = entry_screen(solver, monkeypatch, [scene], restoration=restoration)
    solver._selection_profile_snapshot = SimpleNamespace(
        mode="xhigh", low_frame_rate=False, transition_timeout=1, poll_interval=0.25
    )
    solver.waiting_solver.return_value = False
    original_plan = copy.deepcopy(task.plan)
    original_time = task.time

    with pytest.raises(base_schedule.AgentSelectionNotReady):
        solver.agent_arrange_room({}, ROOM, task.plan)

    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    assert task.plan == original_plan
    assert task.time == original_time
    assert any(queued is task for queued in solver.tasks)
    assert bool(getattr(task, "run_order_restore_pending", False)) is restoration
    assert solver.enter_room.call_count <= 4
    assert state["clock"] <= 4
    if scene == Scene.CONNECTING:
        assert solver.waiting_solver.call_count <= 4
        assert all(
            call.kwargs == {"restart_on_timeout": False}
            for call in solver.waiting_solver.call_args_list
        )


def test_repeated_connecting_result_cannot_repeat_network_wait_forever(
    solver, monkeypatch
):
    task, _ = entry_screen(solver, monkeypatch, [Scene.CONNECTING])
    solver.waiting_solver.return_value = True
    original_plan = copy.deepcopy(task.plan)

    with pytest.raises(base_schedule.AgentSelectionNotReady):
        solver.agent_arrange_room({}, ROOM, task.plan)

    solver.choose_agent.assert_not_called()
    assert solver.waiting_solver.call_count <= 4
    assert task.plan == original_plan
    assert not getattr(task, "run_order_restore_pending", False)


def test_unknown_scene_keeps_ordinary_arrangement_compatibility(solver, monkeypatch):
    task, state = entry_screen(solver, monkeypatch, [Scene.UNKNOWN])
    task.type = TaskTypes.SHIFT_ON
    solver.choose_agent.side_effect = None

    def confirm(room, new_plan):
        for index, name in enumerate(task.plan[room]):
            operator = solver.op_data.operators[name]
            operator._current_room, operator.current_index = room, index
        state["scene"] = Scene.INFRA_MAIN

    solver.tap_confirm.side_effect = confirm

    solver.agent_arrange_room({}, ROOM, task.plan)

    solver.choose_agent.assert_called_once()
    solver.sleep.assert_not_called()
    solver.waiting_solver.assert_not_called()
    assert ROOM not in task.plan


@pytest.mark.parametrize("restoration", [False, True])
def test_button_lost_during_transition_cannot_start_selection(
    solver, monkeypatch, restoration
):
    task, state = entry_screen(
        solver,
        monkeypatch,
        [Scene.UNKNOWN, Scene.INFRA_ARRANGE_ORDER],
        restoration=restoration,
    )
    solver._selection_profile_snapshot = SimpleNamespace(
        mode="xhigh", low_frame_rate=False, transition_timeout=1, poll_interval=0.25
    )
    find_button = solver.find.side_effect

    def disappearing_button(name, *args, **kwargs):
        if name == "confirm_blue" and state["scene"] == Scene.INFRA_ARRANGE_ORDER:
            return None
        return find_button(name, *args, **kwargs)

    solver.find.side_effect = disappearing_button
    original_plan = copy.deepcopy(task.plan)
    original_time = task.time

    with pytest.raises(base_schedule.AgentSelectionNotReady, match="确认按钮已消失"):
        solver.agent_arrange_room({}, ROOM, task.plan)

    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    assert task.plan == original_plan
    assert task.time == original_time
    assert bool(getattr(task, "run_order_restore_pending", False)) is restoration


def test_network_round_trip_keeps_original_unknown_scene_deadline(solver, monkeypatch):
    task, state = entry_screen(
        solver,
        monkeypatch,
        [Scene.UNKNOWN, Scene.CONNECTING, Scene.UNKNOWN],
    )
    solver._selection_profile_snapshot = SimpleNamespace(
        mode="xhigh", low_frame_rate=False, transition_timeout=1, poll_interval=0.25
    )
    state["entered"] = True
    state["scene"] = Scene.UNKNOWN

    def finish_wait(*, restart_on_timeout):
        state["clock"] += 0.6
        state["frames"].popleft()
        state["scene"] = state["frames"][0]
        return True

    solver.waiting_solver.side_effect = finish_wait

    with pytest.raises(base_schedule.AgentSelectionNotReady, match="场景仍未知"):
        solver._wait_for_run_order_selection_page()

    assert state["clock"] == pytest.approx(1.0)
    solver.waiting_solver.assert_called_once_with(restart_on_timeout=False)
    solver.choose_agent.assert_not_called()
    assert not getattr(task, "run_order_restore_pending", False)


def test_recurring_network_after_unknown_scene_returns_to_room_recovery(
    solver, monkeypatch
):
    task, state = entry_screen(
        solver, monkeypatch, [Scene.CONNECTING, Scene.CONNECTING]
    )
    solver._selection_profile_snapshot = SimpleNamespace(
        mode="xhigh", low_frame_rate=False, transition_timeout=1, poll_interval=0.25
    )

    def finish_wait(*, restart_on_timeout):
        state["scene"] = Scene.UNKNOWN
        return True

    solver.waiting_solver.side_effect = finish_wait
    original_plan = copy.deepcopy(task.plan)

    with pytest.raises(base_schedule.AgentSelectionNotReady, match="反复联网"):
        solver.agent_arrange_room({}, ROOM, task.plan)

    assert solver.enter_room.call_count == 4
    assert solver.waiting_solver.call_count == 4
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    assert task.plan == original_plan
    assert not getattr(task, "run_order_restore_pending", False)


@pytest.mark.parametrize("scene", [Scene.UNKNOWN, Scene.CONNECTING])
def test_entry_wait_propagates_cancellation_without_retry(solver, monkeypatch, scene):
    task, _ = entry_screen(solver, monkeypatch, [scene])
    solver._selection_profile_snapshot = SimpleNamespace(
        mode="xhigh", low_frame_rate=False, transition_timeout=1, poll_interval=0.25
    )
    cancelled = base_schedule.MowerExit()
    if scene == Scene.CONNECTING:
        solver.waiting_solver.side_effect = cancelled
    else:
        solver.sleep.side_effect = cancelled
    original_plan = copy.deepcopy(task.plan)
    original_time = task.time

    with pytest.raises(base_schedule.MowerExit) as raised:
        solver.agent_arrange_room({}, ROOM, task.plan)

    assert raised.value is cancelled
    solver.enter_room.assert_called_once()
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    solver.recog.update.assert_not_called()
    assert task.plan == original_plan
    assert task.time == original_time
    assert not getattr(task, "run_order_restore_pending", False)
