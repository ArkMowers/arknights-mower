from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.tests.dorm_arrangement_observation_tests import (
    incident as incident,
)
from arknights_mower.utils import config
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.mark.parametrize(
    ("facility", "read_in_detail"),
    [
        pytest.param("manufacture", True, id="manufacture-detail"),
        pytest.param("trade", True, id="trade-orders"),
        pytest.param("manufacture", False, id="visible-product"),
    ],
)
def test_explicit_arrangement_selects_after_reading_current_resident(
    incident, facility, read_in_detail
):
    solver, physical, snapshots = incident
    room = "room_3_2"
    before = ["米格鲁", "芬"]
    after = ["米格鲁", "陈"]
    solver.op_data.plan[room].append(Room("芬", "", []))
    physical[room] = before.copy()
    resident = solver.op_data.operators["芬"]
    resident._current_room, resident.current_index = room, 1
    task = SchedulerTask(
        task_type=TaskTypes.NOT_SPECIFIC, task_plan={room: ["Current", "陈"]}
    )
    solver.task, solver.tasks = task, [task]
    config.conf.product_switching.enable = True

    solver.recog._img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    solver.recog.w, solver.recog.h = 1920, 1080
    solver.get_color = lambda _: np.array([255, 255, 255])
    del solver.refresh_facility_state
    del solver.turn_on_room_detail

    if facility == "manufacture":
        facility_name, product = "制造站", "gold"
        product_scene, product_marker = Scene.FACTORY_ROOMS, "manufacture_accelerate"
        solver._visible_manufacture_product = lambda: (
            None if read_in_detail else product
        )
    else:
        facility_name, product = "贸易站", "lmd"
        product_scene, product_marker = Scene.ORDER_LIST, "bill_accelerate"
    solver.detect_room_type = lambda: facility_name
    page = "map"
    panel_button = (80, 410)
    actions = []
    roster_find = solver.find
    confirm_selection = solver.tap_confirm.side_effect

    def enter_room(target):
        nonlocal page
        assert target == room and page == "map"
        page = "closed"
        actions.append("enter room")

    def find(marker, **kwargs):
        if marker == "infra_no_operator":
            assert page == "roster"
            actions.append("read slot")
            return roster_find(marker, **kwargs)
        return {
            "closed": {"arrange_check_in": panel_button},
            "roster": {
                "room_detail": panel_button,
                "arrange_check_in_on": panel_button,
            },
            "product": {product_marker: (100, 200)},
            "selection": {"confirm_blue": (1500, 950)},
        }.get(page, {}).get(marker)

    def tap(point, **kwargs):
        nonlocal page
        if point == panel_button:
            if page == "closed":
                page = "roster"
                actions.append("open panel")
            else:
                assert page == "roster"
                page = "closed"
                actions.append("close panel")
        elif point[0] < 100:
            assert page == "closed"
            page = "product"
        else:
            assert page == "roster"
            page = "selection"
            actions.append("select")

    def back(*args, **kwargs):
        nonlocal page
        page = "closed" if page == "product" else "map"

    def read_product():
        assert page == "product"
        actions.append("read product")
        return product

    def confirm(*args):
        nonlocal page
        assert page == "selection"
        confirm_selection(*args)
        page = "roster"
        actions.append("confirm")

    solver.detect_room = lambda: room if page != "map" else None
    solver.scene.side_effect = lambda: {
        "map": Scene.INFRA_MAIN,
        "product": product_scene,
        "selection": Scene.RIIC_OPERATOR_SELECT,
    }.get(page, Scene.INFRA_DETAILS)
    solver.enter_room = enter_room
    solver.find = find
    solver.tap = tap
    solver.back = back
    solver.sleep = MagicMock()
    solver.read_manufacture_product = read_product
    solver._read_trade_product_card = lambda: (read_product(), False)
    solver.tap_confirm.side_effect = confirm

    solver.agent_arrange_room({}, room, task.plan)

    detail_actions = (
        ["close panel", "read product", "open panel"] if read_in_detail else []
    )
    assert actions == [
        "enter room",
        "open panel",
        "read slot",
        "read slot",
        *detail_actions,
        "select",
        "confirm",
        "read slot",
        "read slot",
    ]
    solver.tap_confirm.assert_called_once()
    assert snapshots == [before, after]
    assert physical[room] == after
    assert solver.op_data.get_current_room(room, True) == after
    assert solver.op_data.facility_product(room) == product
    assert not task.plan
