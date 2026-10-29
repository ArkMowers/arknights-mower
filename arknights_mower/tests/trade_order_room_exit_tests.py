"""换人返回后的新帧须确认地图，再继续同房跑单。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.tests.mass_mood_recovery_tests import COVERS
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver

# 先加载共享离线夹具，隔离调度模块导入时的外部服务依赖。
# isort: split
from arknights_mower.solvers import base_mixin, base_schedule
from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.tests.automatic_rescue_tests import offline as offline
from arknights_mower.tests.run_order_restoration_tests import (
    ORIGINAL,
    ROOM,
    prepare_order,
)
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.recognize import RecognizeError, Scene


@pytest.mark.parametrize("adjusted,buffer", [(False, 0), (True, 1)])
@pytest.mark.parametrize("already_inserted", [False, True])
def test_run_order_waits_for_returned_map_before_real_drone_navigation(
    solver, monkeypatch, adjusted, buffer, already_inserted
):
    original = ["但书", COVERS[1]] if already_inserted else ORIGINAL
    task, _ = prepare_order(
        solver, monkeypatch, original, buffer=buffer, adjusted=adjusted
    )
    solver._selection_profile_snapshot = SimpleNamespace(
        mode="xhigh",
        low_frame_rate=False,
        transition_timeout=2,
        screenshot_interval=100,
    )
    state = {
        "page": "room",
        "exit_reads": 0,
        "clock": 0.0,
        "navigation": False,
        "fresh": True,
    }
    events = []
    exit_observations = []
    rectangle = np.array([[400, 500], [400, 750], [800, 750], [800, 500]])
    selection_find = solver.find.side_effect
    selection_enter = solver.enter_room

    def update():
        state["fresh"] = True

    def observe():
        if state["fresh"] and state["page"] in ("return_pending", "fading"):
            state["exit_reads"] += 1
            state["page"] = ("return_pending", "fading", "map")[
                min(state["exit_reads"] - 1, 2)
            ]
            exit_observations.append(state["page"])
        state["fresh"] = False
        return state["page"]

    def sleep(interval=1):
        state["clock"] += interval
        solver.recog.update()

    def scene():
        return Scene.INFRA_MAIN if observe() == "map" else Scene.INFRA_DETAILS

    def back(*args, **kwargs):
        events.append(("back", state["page"]))
        state.update(page="return_pending", exit_reads=0, fresh=True)

    def find(name, *args, **kwargs):
        if not state["navigation"]:
            return selection_find(name, *args, **kwargs)
        observe()
        if name == "control_central" and state["page"] == "map":
            return ((1100, 100), (1400, 300))
        if name == "bill_accelerate" and state["page"] == "order":
            return ((400, 700), (650, 770))
        return None

    def tap(position, *args, **kwargs):
        if not state["navigation"]:
            return
        if isinstance(position, np.ndarray):
            assert state["page"] == "map"
            events.append(("enter", state["page"]))
            state["page"] = "room"
        elif position == (96, 1026):
            events.append(("order", state["page"]))
            if state["page"] == "room":
                state["page"] = "order"
            elif state["page"] in ("return_pending", "fading"):
                state["page"] = "map"

    def accelerate(*args, **kwargs):
        assert state["page"] == "order"
        events.append(("accelerate", state["page"]))
        return ((1500, 700), (1800, 900))

    def drone(*args, **kwargs):
        state["navigation"] = True
        solver.enter_room = BaseMixin.enter_room.__get__(solver)
        try:
            return base_schedule.BaseSchedulerSolver.drone(solver, *args, **kwargs)
        finally:
            solver.enter_room = selection_enter
            state["navigation"] = False

    solver.recog.update.side_effect = update
    solver.sleep.side_effect = sleep
    solver.scene.side_effect = scene
    solver.back.side_effect = back
    solver.find.side_effect = find
    solver.tap.side_effect = tap
    solver.detect_room = MagicMock(
        side_effect=lambda: "" if state["page"] == "map" else ROOM
    )
    solver._handle_room_entry_reward = MagicMock(return_value=False)
    solver._tap_drone_accelerate = MagicMock(side_effect=accelerate)
    solver.scene_graph_navigation = MagicMock(
        side_effect=lambda target: state.update(page="map")
    )
    solver.drone.side_effect = drone
    monkeypatch.setattr(base_schedule, "monotonic", lambda: state["clock"])
    monkeypatch.setattr(
        base_mixin.segment, "base", MagicMock(return_value={ROOM: rectangle})
    )

    solver.agent_arrange(task.plan)

    first_acceleration = next(i for i, e in enumerate(events) if e[0] == "accelerate")
    expected_entry = (
        [("back", "room"), ("enter", "map")]
        if not buffer and not already_inserted
        else []
    )
    assert events[: first_acceleration + 1] == expected_entry + [
        ("order", "room"),
        ("accelerate", "order"),
    ]
    if expected_entry:
        assert exit_observations[:3] == ["return_pending", "fading", "map"]
    solver.accept_order.assert_called_once()
    if not buffer and not already_inserted:
        assert task.plan == {ROOM: ORIGINAL}
        assert task.meta_data == ""
        assert task.run_order_restore_pending
        assert solver.tasks == [task]


def test_room_exit_confirmation_keeps_one_back_and_the_original_task_on_timeout(
    solver, monkeypatch
):
    task, _ = prepare_order(solver, monkeypatch, buffer=0)
    original_time = task.time
    solver._selection_profile_snapshot = SimpleNamespace(
        mode="xhigh",
        low_frame_rate=False,
        transition_timeout=0.25,
        screenshot_interval=100,
    )
    clock = {"now": 0.0}
    solver.scene.return_value = Scene.INFRA_DETAILS
    solver.sleep.side_effect = lambda interval=1: clock.update(
        now=clock["now"] + interval
    )
    monkeypatch.setattr(base_schedule, "monotonic", lambda: clock["now"])

    with pytest.raises(RecognizeError, match="返回基建全局视角"):
        solver.agent_arrange(task.plan)

    solver.back.assert_called_once_with(0.5)
    solver.drone.assert_not_called()
    assert task.time == original_time
    assert task.plan == {ROOM: ORIGINAL}
    assert task.run_order_original_roster == {ROOM: ORIGINAL}
    assert task.run_order_restore_pending
    assert solver.tasks == [task]
    assert clock["now"] == pytest.approx(0.25)


@pytest.mark.parametrize(
    "first_scene", [Scene.INFRA_DETAILS, Scene.UNKNOWN, Scene.CONNECTING]
)
def test_room_exit_refreshes_again_without_another_back(solver, first_scene):
    solver._selection_profile_snapshot = SimpleNamespace(
        transition_timeout=1, screenshot_interval=100
    )
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.scene = MagicMock(side_effect=[first_scene, Scene.INFRA_MAIN])
    solver.sleep = MagicMock()
    solver.back = MagicMock()

    solver._wait_for_room_exit()

    assert solver.recog.update.call_count == 2
    solver.sleep.assert_called_once_with(0.1)
    solver.back.assert_not_called()


def test_confirmed_room_exit_needs_no_extra_sleep(solver):
    solver._selection_profile_snapshot = SimpleNamespace(
        transition_timeout=1, screenshot_interval=100
    )
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.scene = MagicMock(return_value=Scene.INFRA_MAIN)
    solver.sleep = MagicMock()

    solver._wait_for_room_exit()

    solver.recog.update.assert_called_once_with()
    solver.sleep.assert_not_called()


@pytest.mark.parametrize("cancel_at", ["capture", "sleep"])
def test_room_exit_cancellation_preserves_original_roster(
    solver, monkeypatch, cancel_at
):
    task, _ = prepare_order(solver, monkeypatch, buffer=0)
    original_time = task.time
    solver._selection_profile_snapshot = SimpleNamespace(
        mode="xhigh",
        low_frame_rate=False,
        transition_timeout=1,
        screenshot_interval=100,
    )
    solver.scene.return_value = Scene.INFRA_DETAILS
    cancellation = MowerExit()

    def cancel(*args, **kwargs):
        if solver.back.call_count:
            raise cancellation

    operation = solver.recog.update if cancel_at == "capture" else solver.sleep
    operation.side_effect = cancel

    with pytest.raises(MowerExit) as raised:
        solver.agent_arrange(task.plan)

    assert raised.value is cancellation
    solver.back.assert_called_once_with(0.5)
    solver.drone.assert_not_called()
    assert task.time == original_time
    assert task.plan == {ROOM: ORIGINAL}
    assert task.run_order_original_roster == {ROOM: ORIGINAL}
    assert solver.tasks == [task]
