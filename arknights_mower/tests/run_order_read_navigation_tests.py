import copy
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.run_order_staffing_admission_tests import staffed_order


@pytest.fixture
def order_navigation(monkeypatch):
    return staffed_order.__wrapped__(monkeypatch)


@pytest.mark.parametrize("next_room", ["room_2_2", "dormitory_1"])
def test_failed_inline_order_read_restores_navigation_before_next_room(
    order_navigation, monkeypatch, next_room
):
    from arknights_mower.solvers import base_mixin

    ui = order_navigation
    solver = ui.solver
    page = solver._page
    scene = ui.base.Scene
    marker = ((100, 100), (200, 200))
    refresh = ui.task(
        task_type=ui.task_type.REFRESH_TIME,
        meta_data="room_1_1",
    )
    arrangement = ui.task(
        task_type=ui.task_type.SELF_CORRECTION,
        task_plan={next_room: ["Current"]},
    )
    solver.tasks = [arrangement, refresh]
    solver.task = arrangement
    ui.states["room_1_1"] = "active"
    solver.read_time.side_effect = ui.base.RecognizeError("订单数字未确认")

    def return_to_base(*args, **kwargs):
        page.update(room=None, open=False)

    solver.back_to_infrastructure = MagicMock(side_effect=return_to_base)
    solver.back_to_index = MagicMock(side_effect=return_to_base)

    solver._read_arrangement_order_times("room_1_1")

    assert refresh.execution_failure
    assert arrangement.plan == {next_room: ["Current"]}
    assert arrangement in solver.tasks and refresh in solver.tasks

    def find(resource, *args, **kwargs):
        if resource == "control_central" and page["room"] is None:
            return marker
        return None

    def current_scene():
        if page["open"]:
            return scene.ORDER_LIST
        return scene.INFRA_MAIN if page["room"] is None else scene.INFRA_DETAILS

    def enter_target(*args, **kwargs):
        page.update(room=next_room, open=False)

    monkeypatch.setattr(
        base_mixin.segment,
        "base",
        lambda *args, **kwargs: {next_room: marker},
    )
    solver.find = MagicMock(side_effect=find)
    solver.scene = MagicMock(side_effect=current_scene)
    solver.detect_room = MagicMock(side_effect=lambda: page["room"])
    solver.adjust_room = MagicMock(return_value=marker)
    solver.tap = MagicMock(side_effect=enter_target)
    solver.sleep.reset_mock()
    entered_at = ui.clock.now()

    base_mixin.BaseMixin.enter_room(solver, next_room)

    assert page == {"room": next_room, "open": False}
    assert ui.clock.now() == entered_at
    solver.back_to_index.assert_not_called()
    solver.sleep.assert_not_called()


@pytest.mark.parametrize(
    "error_name", ["DeviceRecoveryError", "SharedADBError", "MowerExit"]
)
def test_failed_inline_read_propagates_navigation_recovery_failure(
    order_navigation, error_name
):
    ui = order_navigation
    solver = ui.solver
    refresh = ui.task(
        task_type=ui.task_type.REFRESH_TIME,
        meta_data="room_1_1",
    )
    arrangement = ui.task(
        task_type=ui.task_type.SELF_CORRECTION,
        task_plan={"dormitory_1": ["Current"]},
    )
    solver.tasks = [arrangement, refresh]
    solver.task = arrangement
    ui.states["room_1_1"] = "active"
    solver.read_time.side_effect = ui.base.RecognizeError("订单数字未确认")
    failure = getattr(ui.base, error_name)("导航恢复中断")
    solver.back_to_infrastructure = MagicMock(side_effect=failure)

    with pytest.raises(type(failure)) as caught:
        solver._read_arrangement_order_times("room_1_1")

    assert caught.value is failure
    assert refresh.execution_failure["reason"] == "订单数字未确认"
    assert solver.tasks == [arrangement, refresh]
    assert arrangement.plan == {"dormitory_1": ["Current"]}
    solver.back_to_infrastructure.assert_called_once_with()


def test_restoration_with_old_room_metadata_does_not_interrupt_order_refreshes(
    order_navigation,
):
    from arknights_mower.utils.plan import Room

    ui = order_navigation
    solver = ui.solver
    solver.op_data.plan["room_3_3"] = [Room("孑", "", ["佩佩"])]
    solver.op_data.products["room_3_3"] = "lmd"
    solver.op_data.refresh_run_order_rooms()
    ui.states.update({"room_2_2": "active", "room_3_3": "active"})
    ui.deadlines["room_3_3"] = ui.clock.now() + timedelta(hours=4)
    arrangement = ui.task(
        task_type=ui.task_type.SELF_CORRECTION,
        task_plan={"dormitory_1": ["Current"]},
    )
    restoration = ui.task(
        task_type=ui.task_type.RUN_ORDER,
        task_plan={"room_1_1": ["鸿雪"]},
        meta_data="room_1_1",
    )
    restoration.run_order_original_roster = {"room_1_1": ["鸿雪"]}
    restoration.run_order_restore_pending = True
    original_restoration = copy.deepcopy(vars(restoration))
    refreshes = [
        ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data=room)
        for room in ("room_2_2", "room_3_3")
    ]
    solver.task = arrangement
    solver.tasks = [arrangement, restoration, *refreshes]

    solver._read_arrangement_order_times("room_2_2")

    assert [event[1] for event in ui.events if event[0] == "read"] == [
        "room_2_2",
        "room_3_3",
    ]
    assert all(refresh not in solver.tasks for refresh in refreshes)
    orders = {
        task.meta_data: task
        for task in solver.tasks
        if task.type == ui.task_type.RUN_ORDER
    }
    assert set(orders) == {"room_1_1", "room_2_2", "room_3_3"}
    assert orders["room_1_1"] is restoration
    assert vars(restoration) == original_restoration
    for room in ("room_2_2", "room_3_3"):
        assert orders[room].time == ui.deadlines[room] - timedelta(minutes=3)
    assert arrangement.plan == {"dormitory_1": ["Current"]}
    solver.choose_agent.assert_not_called()
