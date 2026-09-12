"""中枢已耗尽干员不重读不存在的计时，恢复和正常工作计时保持不变。"""

import sys
from datetime import datetime, timedelta
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils.operators import Operators  # noqa: E402


@pytest.fixture
def room_reader():
    def make(room="central", name="歌蕾蒂娅", mood=0):
        target = SimpleNamespace(
            current_room=room,
            current_index=0,
            mood=mood,
            time_stamp=datetime.now(),
            depletion_rate=0,
            lower_limit=0,
            exhaust_time=None,
            need_to_refresh=MagicMock(return_value=True),
            current_mood=MagicMock(return_value=mood),
            is_working=MagicMock(return_value=not room.startswith("dorm")),
        )
        op_data = SimpleNamespace(
            operators={name: target},
            plan={room: [SimpleNamespace(agent="Free")]},
            true_exhaust_room={"central"},
            dorm=[],
            config=SimpleNamespace(free_room=False),
        )

        def update_detail(name, value, room, index, update_time):
            target.mood = value
            target.current_room = room
            target.current_index = index
            if update_time:
                target.time_stamp = datetime.now()

        op_data.update_detail = update_detail
        op_data.refresh_dorm_time = MethodType(Operators.refresh_dorm_time, op_data)
        solver = object.__new__(BaseSchedulerSolver)
        solver.op_data = op_data
        solver.tasks, solver.task = [], None
        solver.leifeng_mode = True
        solver.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
        solver.turn_on_room_detail = MagicMock()
        solver.detect_product_complete = MagicMock(return_value=None)
        solver.detect_room = MagicMock(return_value=room)

        def find(resource, scope=None):
            if resource == "room_detail":
                return ((1, 1), (2, 2))
            if resource == "infra_no_operator" and scope[0][1] == 344:
                return ((1, 1), (2, 2))
            return None

        solver.find = MagicMock(side_effect=find)
        solver.read_screen = MagicMock(return_value=name)
        solver.read_accurate_mood = MagicMock(return_value=mood)
        deadline = datetime.now() + timedelta(hours=1)
        solver.double_read_time = MagicMock(return_value=deadline)
        return solver, target, deadline

    return make


def test_confirmed_exhausted_central_sets_real_exhaust_time_without_timer_ocr(
    room_reader,
):
    solver, target, _ = room_reader()
    before = datetime.now()
    result = solver.get_agent_from_room("central", [0])[0]
    after = datetime.now()
    assert before <= result["time"] <= after
    assert before <= target.exhaust_time <= after
    assert result["mood"] == 0
    solver.double_read_time.assert_not_called()
    assert solver.read_screen.call_count == 2
    assert solver.read_accurate_mood.call_count == 2
    solver.recog.update.assert_called_once()


@pytest.mark.parametrize("room", ["dormitory_1", "train", "room_1_1", "contact"])
def test_zero_mood_outside_central_keeps_existing_countdown(room_reader, room):
    solver, _, deadline = room_reader(room=room)
    result = solver.get_agent_from_room(room, [0])[0]
    assert result["time"] == deadline
    solver.double_read_time.assert_called_once_with(((1650, 270), (1780, 305)))
    solver.recog.update.assert_not_called()


def test_fiammetta_keeps_countdown_even_when_in_central(room_reader):
    solver, _, deadline = room_reader(name="菲亚梅塔")
    assert solver.get_agent_from_room("central", [0])[0]["time"] == deadline
    solver.double_read_time.assert_called_once()
    solver.recog.update.assert_not_called()


def test_nonzero_central_keeps_measured_working_countdown(room_reader):
    solver, target, deadline = room_reader(mood=8)
    result = solver.get_agent_from_room("central", [0])[0]
    assert result["time"] == target.exhaust_time == deadline
    solver.double_read_time.assert_called_once()
    solver.recog.update.assert_not_called()


@pytest.mark.parametrize("change", ["room", "name", "mood", "detail", "connecting"])
def test_uncertain_second_observation_keeps_existing_countdown(room_reader, change):
    solver, _, deadline = room_reader()
    if change == "room":
        solver.detect_room.return_value = "dormitory_1"
    elif change == "name":
        solver.read_screen.side_effect = ["歌蕾蒂娅", "夕"]
    elif change == "mood":
        solver.read_accurate_mood.side_effect = [0, 3]
    elif change in ("detail", "connecting"):
        old_find = solver.find.side_effect

        def find(resource, **kwargs):
            if resource == "room_detail" and change == "detail":
                return None
            if resource == "connecting" and change == "connecting":
                return ((1, 1), (2, 2))
            return old_find(resource, **kwargs)

        solver.find.side_effect = find
    assert solver.get_agent_from_room("central", [0])[0]["time"] == deadline
    solver.double_read_time.assert_called_once()


def test_cached_zero_mood_is_not_an_exhaustion_measurement(room_reader):
    solver, target, deadline = room_reader()
    target.need_to_refresh.return_value = False
    # 只有读完缓存后才出现的时间请求，不能把估算的零心情变成已确认耗尽。
    solver.op_data.update_detail = MagicMock(return_value=0)
    assert solver.get_agent_from_room("central")[0]["time"] == deadline
    solver.read_accurate_mood.assert_not_called()
    solver.double_read_time.assert_called_once()
    solver.recog.update.assert_not_called()


@pytest.mark.parametrize("condition", ["not_working", "not_exhaust_room"])
def test_zero_mood_without_working_exhaustion_semantics_keeps_countdown(
    room_reader, condition
):
    solver, target, deadline = room_reader()
    if condition == "not_working":
        target.is_working.return_value = False
    else:
        solver.op_data.true_exhaust_room.clear()
    assert solver.get_agent_from_room("central", [0])[0]["time"] == deadline
    solver.double_read_time.assert_called_once()
    solver.recog.update.assert_not_called()
