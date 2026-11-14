"""房间头像不能因通用特征误匹配而被当作已确认空槽。"""

from pathlib import Path
from unittest.mock import Mock

import cv2
import pytest

from arknights_mower.utils.recognize import Recognizer

FIXTURES = Path(__file__).parent / "fixtures" / "selection"
OCCUPIED = "room_crownslayer_20261103.jpg"


def recognizer(filename):
    result = object.__new__(Recognizer)
    result._gray = cv2.imread(str(FIXTURES / filename), cv2.IMREAD_GRAYSCALE)
    assert result._gray is not None
    result._matcher = Mock()
    # 事故中的头像特征被分类器接受；保持这种外部误匹配，验证空槽判断。
    result._matcher.match.return_value = ((1348, 662), (1424, 754))
    return result


@pytest.mark.parametrize("top", [135, 344, 553])
def test_recorded_occupied_slots_reject_feature_false_positive(top):
    result = recognizer(OCCUPIED)

    assert (
        result.find("infra_no_operator", scope=((1288, top), (1869, top + 191))) is None
    )


@pytest.mark.parametrize(
    "filename,top",
    [
        ("room_empty_top_20261020.jpg", 741),
        ("room_empty_bottom_20261020.jpg", 553),
        ("room_empty_bottom_20261020.jpg", 741),
        ("room_empty_bottom_again_20261020.jpg", 741),
    ],
)
def test_recorded_empty_slots_keep_positive_confirmation(filename, top):
    result = recognizer(filename)

    match = result.find("infra_no_operator", scope=((1288, top), (1869, top + 191)))

    assert match is not None
    assert 1288 <= match[0][0] < match[1][0] <= 1869
    assert top <= match[0][1] < match[1][1] <= top + 191


def test_room_read_preserves_recorded_crownslayer_occupancy(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", Mock())
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    room = "room_1_1"
    expected = ["斥罪", "琴柳", "弑君者"]
    solver = object.__new__(BaseSchedulerSolver)
    solver.task = None
    solver.tasks = []
    solver.op_data = Mock()
    solver.op_data.plan = {room: [None] * 3}
    solver.op_data.mood_calculation_enabled = False
    solver.op_data.room_observations = {}
    solver.op_data.operators = {}
    for index, name in enumerate(expected):
        operator = Mock(
            current_room=room, current_index=index, mood=24, depletion_rate=0
        )
        operator.need_to_refresh.return_value = False
        operator.current_mood.return_value = 24
        solver.op_data.operators[name] = operator
    solver.op_data.update_detail.return_value = None
    solver.recog = recognizer(OCCUPIED)
    solver.find = solver.recog.find
    solver._can_refresh_idle_dorm_search = Mock(return_value=False)
    solver.refresh_facility_state = Mock()
    solver.turn_on_room_detail = Mock()
    solver.wait_product_complete = Mock()
    solver.sleep = Mock()

    result = solver.get_agent_from_room(room)

    assert [row["agent"] for row in result] == expected
    assert solver.op_data.update_detail.call_count == 3
    assert [
        operator.current_room for operator in solver.op_data.operators.values()
    ] == [room, room, room]
    assert solver.op_data.room_observations == {room: 1}
    solver.sleep.assert_not_called()
