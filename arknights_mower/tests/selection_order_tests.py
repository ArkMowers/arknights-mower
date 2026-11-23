from pathlib import Path

import pytest

from arknights_mower.utils import selection_order
from arknights_mower.utils.character_recognize import operator_list
from arknights_mower.utils.image import loadimg

FIXTURES = Path(__file__).parent / "fixtures" / "selection"


def test_trust_percentages_cannot_be_read_as_operator_names():
    frame = loadimg(str(FIXTURES / "trust_percentages.webp")).copy()
    # 排序栏已经更新、卡片仍显示上一帧百分比时也要拒绝姓名。
    frame[:100] = 0
    page = operator_list(frame)
    assert len(page) == 10
    assert all(name == "" for name, _ in page)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        # 模板 1–4 取自该宿舍画面，模板 5 取自下一个横向滚动后的画面。
        (
            "clear_delayed_20261020.jpg",
            {"隐德来希": 1, "车尔尼": 2, "香草": 3, "清流": 4},
        ),
        ("dorm_right_edge_20261010.png", {"菲亚梅塔": 3, "刺玫": 4, "绮良": 5}),
        ("trade_restore_before_20261029.jpg", {"黑键": 1, "但书": 2, "龙舌兰": 3}),
        (
            "trade_restore_wrong_roster_20261029.jpg",
            {"黑键": 1, "龙舌兰": 2, "能天使": 3},
        ),
        ("trade_single_cleared_20261021.jpg", {}),
        ("workshop_single_selected_20261029.jpg", {}),
    ],
)
def test_selection_slot_reads_visible_numbers(filename, expected):
    frame = loadimg(str(FIXTURES / filename))
    page = operator_list(frame)
    assert len(page) == 12
    numbers = {
        name: selection_order.selection_slot(frame, scope) for name, scope in page
    }
    assert {
        name: slot for name, slot in numbers.items() if slot is not None
    } == expected


def test_selection_slot_tolerates_name_position_jitter_and_rejects_occlusion():
    frame = loadimg(str(FIXTURES / "trade_restore_before_20261029.jpg")).copy()
    name, ((x, y), (right, bottom)) = operator_list(frame)[2]
    assert name == "龙舌兰"
    shifted = ((x + 3, y - 2), (right + 3, bottom - 2))
    assert selection_order.selection_slot(frame, shifted) == 3
    frame[y - 323 : y - 285, x + 117 : x + 185] = 0
    assert selection_order.selection_slot(frame, shifted) is None


def test_selection_slot_without_templates_is_unknown(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(selection_order, "loadres", missing)
    monkeypatch.setattr(
        selection_order, "_slot_templates", selection_order._slot_templates.__wrapped__
    )
    frame = loadimg(str(FIXTURES / "trade_restore_before_20261029.jpg"))
    assert selection_order.selection_slot(frame, operator_list(frame)[0][1]) is None


def test_two_slot_capacity_in_room_details_rejects_three_and_missing_digits():
    from types import SimpleNamespace

    import numpy as np

    from arknights_mower.solvers.base_mixin import BaseMixin

    bands = loadimg(str(FIXTURES / "manufacturing_capacity.webp"))
    room = BaseMixin()
    for index, expected in enumerate((True, False)):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        top = index * 127 + 77
        frame[18:95, 568:958] = bands[top - 77 : top]
        frame[1006:1056, 1650:1920] = bands[top : top + 50, :270]
        room.recog = SimpleNamespace(img=frame)
        assert room.detect_room() == ("room_3_2" if expected else "room_3_1")
        assert selection_order.room_shows_two_slots(frame) is expected
        frame[1006:1056, 1840:] = 255
        assert not selection_order.room_shows_two_slots(frame)
