from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.utils.recognize import Recognizer

FIXTURES = Path(__file__).parent / "fixtures" / "selection"
CENTRAL = ["薇薇安娜", "焰尾", "森蚺", "重岳", "歌蕾蒂娅"]


class RoomClock(datetime):
    @classmethod
    def now(cls):
        return SAMPLED + timedelta(seconds=5)


SAMPLED = RoomClock(2026, 11, 24, 12)


def recorded_panel(name):
    crop = cv2.imread(str(FIXTURES / f"room_{name}_20261124.webp"))
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[135 : 135 + crop.shape[0], 1288:1869] = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return frame


@pytest.fixture
def reader(monkeypatch):
    from arknights_mower.solvers import base_schedule

    monkeypatch.setattr(base_schedule, "datetime", RoomClock)

    def make(room, names, frame):
        s = object.__new__(base_schedule.BaseSchedulerSolver)
        s.task, s.tasks = None, []
        s.op_data = Mock()
        s.op_data.plan = {room: [None] * len(names)}
        s.op_data.operators = {
            name: Mock(current_room=room, current_index=i)
            for i, name in enumerate(names)
            if name
        }
        s.op_data.room_observations = {}
        s.op_data.mood_calculation_enabled = False
        s.op_data.update_detail.return_value = None
        s._can_refresh_idle_dorm_search = Mock(return_value=False)
        s.turn_on_room_detail = s.wait_product_complete = s.refresh_facility_state = (
            Mock()
        )
        s.recog = object.__new__(Recognizer)

        def show(image, sampled=SAMPLED):
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            s.recog._install_frame((None, image, gray), sampled)

        show(frame)
        s.find = s.recog.find
        s.read_time = Mock(return_value=None)
        s.read_screen = Mock(wraps=s.read_screen)
        return s, show

    return make


def test_power_depletion_skips_countdown_but_keeps_occupant_and_deadline(reader):
    s, _ = reader("room_2_3", ["Lancet-2"], recorded_panel("power"))
    (row,) = s.get_agent_from_room("room_2_3", force_mood=True)
    s.read_time.assert_not_called()
    assert (row["agent"], row["mood"], row["time"]) == ("Lancet-2", 0, SAMPLED)
    assert s.op_data.operators["Lancet-2"].exhaust_time == SAMPLED
    assert s.op_data.update_detail.call_args.kwargs["mood_event"] == "exhausted"


@pytest.mark.parametrize("remaining", [None, 90])
def test_portrait_label_without_status_text_keeps_countdown_fallback(reader, remaining):
    frame = recorded_panel("power")
    frame[267:309, 1470:1620] = 136  # 保留头像上的同一行文字。
    s, _ = reader("room_2_3", ["Lancet-2"], frame)
    s.read_time.return_value = remaining
    (row,) = s.get_agent_from_room("room_2_3", force_mood=True)
    s.read_time.assert_called_once_with(((1650, 270), (1780, 305)), None)
    if remaining is None:
        assert row["time"] == RoomClock.now()
        assert s.op_data.update_detail.call_args.kwargs["mood_event"] == "exhausted"
    else:
        assert row["time"] == SAMPLED + timedelta(seconds=remaining)
        assert "mood_event" not in s.op_data.update_detail.call_args.kwargs


def test_central_uses_saved_lower_slots_without_reopening_them(reader):
    bottom, top = recorded_panel("central_bottom"), recorded_panel("central_top")
    s, show = reader("central", CENTRAL, bottom)

    def scroll(*, bottom, room):
        if bottom is None:
            return True
        assert not bottom, "已确认的下端岗位不应重新滚动或截图"
        show(top, SAMPLED + timedelta(seconds=1))
        return False

    s.scroll_room_operators = Mock(side_effect=scroll)
    s.read_time.side_effect = AssertionError("已确认注意力涣散，不应重新读取倒计时")
    rows = s.get_agent_from_room("central", force_mood=True)
    assert [r["agent"] for r in rows] == CENTRAL
    assert [r["mood"] for r in rows] == [0] * 5
    assert [r["time"] for r in rows] == [SAMPLED + timedelta(seconds=1)] * 3 + [
        SAMPLED
    ] * 2
    assert all(c.kwargs["type"] == "name" for c in s.read_screen.call_args_list)
    s.read_time.assert_not_called()
    assert s.scroll_room_operators.call_count == 2


def test_recycle_confirms_both_empty_slots_without_ocr(reader):
    s, _ = reader("recycle", ["", ""], recorded_panel("recycle_empty"))
    s.op_data.recycle_capacity = 2
    rows = s.get_agent_from_room("recycle", force_mood=True)
    assert rows == [{"agent": "", "mood": -1}] * 2
    assert s.op_data.recycle_capacity == 2
    assert s.op_data.room_observations == {"recycle": 1}
    s.read_screen.assert_not_called()
    s.read_time.assert_not_called()
