from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock

import numpy as np
import pytest
from PIL import Image

from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.utils import rapidocr, station_filter


@pytest.fixture(scope="module")
def saved_regions():
    path = Path(__file__).parent / "fixtures/selection/station_filter_b102_20261125.png"
    with Image.open(path) as image:
        return np.vsplit(np.asarray(image), 6)


def frame_with(region):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[35:163, 1600:1745] = region
    return frame


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (0, ("全部", False)),
        (1, ("宿舍锁定", False)),
        (2, ("未进驻", False)),
        (3, ("全部", True)),
        (4, ("宿舍锁定", True)),
        (5, ("未进驻", True)),
    ],
)
def test_b102_saved_filter_and_arrow_without_ocr(saved_regions, index, expected):
    frame = frame_with(saved_regions[index])
    ocr = Mock(side_effect=AssertionError("清晰筛选状态不应调用 OCR"))
    assert station_filter.read_station_filter(frame, ocr, menu=True) == expected
    assert station_filter.read_station_filter(frame, ocr, menu=False) == (
        expected[0],
        False,
    )
    ocr.assert_not_called()


@pytest.mark.parametrize(
    "damage", ["title", "arrow", "arrow_down_with_menu", "arrow_up_without_menu"]
)
def test_unreadable_or_disagreeing_features_use_ocr_on_the_same_frame(
    saved_regions, damage
):
    frame = frame_with(saved_regions[4])
    if damage == "title":
        frame[35:82, 1600:1711] = 0
    elif damage == "arrow":
        frame[35:82, 1711:1745] = 0
    elif damage == "arrow_down_with_menu":
        frame[35:82, 1711:1745] = saved_regions[1][:47, 111:145]
    else:
        frame[115:163, 1645:1710] = saved_regions[1][80:128, 45:110]
    ocr = Mock(side_effect=["未进驻", "全部"])
    assert station_filter.read_station_filter(frame, ocr, menu=True) == ("未进驻", True)
    assert [call.kwargs for call in ocr.call_args_list] == [
        {"type": "text", "cord": ((1600, 35), (1715, 82))},
        {"type": "text", "cord": ((1645, 115), (1710, 163))},
    ]
    assert all(call.args[0] is frame for call in ocr.call_args_list)


@pytest.mark.parametrize(
    ("raw_title", "menu", "expected"),
    [
        ("进驻状态", False, ("全部", False)),
        ("全部", False, ("全部", False)),
        ("宿舍锁定", False, ("宿舍锁定", False)),
        ("残字", True, (None, False)),
        (25, True, (None, False)),
    ],
)
def test_unknown_title_and_title_only_keep_one_ocr_read(
    saved_regions, raw_title, menu, expected
):
    frame = frame_with(saved_regions[3])
    frame[35:82, 1711:1745] = 0
    ocr = Mock(return_value=raw_title)
    assert station_filter.read_station_filter(frame, ocr, menu=menu) == expected
    ocr.assert_called_once_with(frame, type="text", cord=((1600, 35), (1715, 82)))


def test_missing_atlas_uses_original_closed_menu_observation(
    tmp_path, monkeypatch, saved_regions
):
    monkeypatch.setattr(station_filter, "_ATLAS", tmp_path / "missing.png")
    station_filter._templates.cache_clear()
    try:
        frame = frame_with(saved_regions[0])
        ocr = Mock(side_effect=["进驻状态", 25])
        assert station_filter.read_station_filter(frame, ocr) == ("全部", False)
        assert ocr.call_count == 2
    finally:
        station_filter._templates.cache_clear()


@pytest.fixture(scope="module")
def station_frames(saved_regions):
    return tuple(frame_with(region) for region in saved_regions)


def filter_solver():
    solver = object.__new__(BaseMixin)
    solver.find = Mock(return_value=None)
    solver.selection_transition_timing = Mock(return_value=(0.1, 3))
    solver.sleep = Mock(side_effect=AssertionError("画面已经就绪"))
    solver.tap = Mock(side_effect=AssertionError("不应输入"))
    return solver


@pytest.mark.parametrize(
    ("start", "original", "target", "taps"),
    [
        (0, "全部", "全部", []),
        (1, "宿舍锁定", "未进驻", [60, 289]),
        (2, "未进驻", "全部", [60, 137]),
        (3, "全部", "全部", [137]),
        (4, "宿舍锁定", "未进驻", [289]),
        (5, "未进驻", "宿舍锁定", [213]),
    ],
)
def test_filter_entry_reads_switches_and_closes(
    station_frames, start, original, target, taps
):
    solver = filter_solver()
    solver.recog = SimpleNamespace(img=station_frames[start])
    solver.read_screen = Mock(side_effect=AssertionError("完整字模不需要 OCR"))
    current = start

    def tap(pos, *, interval):
        nonlocal current
        x, y = pos
        assert x == 1675 and interval == 0.1
        if y == 60:
            assert current < 3
            current += 3
        else:
            assert current >= 3
            current = (137, 213, 289).index(y)
        solver.recog.img = station_frames[current]

    solver.tap.side_effect = tap
    assert solver.agent_station_filter() == original
    solver.tap.assert_not_called()
    assert solver.agent_station_filter(target) == target
    assert [call.args[0][1] for call in solver.tap.call_args_list] == taps
    assert current == ("全部", "宿舍锁定", "未进驻").index(target)
    solver.read_screen.assert_not_called()
    solver.sleep.assert_not_called()


def test_filter_entry_falls_back_twice_on_one_frame(station_frames, monkeypatch):
    frame = station_frames[1].copy()
    frame[35:82, 1715:1745] = 0
    solver = filter_solver()
    solver.recog = Mock()
    capture = PropertyMock(side_effect=[frame])
    type(solver.recog).img = capture
    solver.read_screen = Mock(wraps=solver.read_screen)
    engine = Mock(side_effect=[([["宿舍锁定", 1.0]], []), (None, None)])
    monkeypatch.setattr(rapidocr, "engine", engine)

    assert solver.agent_station_filter("宿舍锁定") == "宿舍锁定"
    capture.assert_called_once()
    assert [call.kwargs["cord"] for call in solver.read_screen.call_args_list] == [
        ((1600, 35), (1715, 82)),
        ((1645, 115), (1710, 163)),
    ]
    assert all(call.args[0] is frame for call in solver.read_screen.call_args_list)
    assert engine.call_count == 2
    solver.tap.assert_not_called()


_JOINED_PAGES = (
    "食铁兽",
    "槐琥",
    "砾",
    "杏仁",
    "钼铅",
    "裁度",
    "温蒂",
    "贝娜",
    "阿斯卡纶",
    "艾拉",
)


def ranked_and_remembered(frame, read_screen, monkeypatch):
    from arknights_mower.solvers import base_schedule
    from arknights_mower.tests.agent_page_observation_tests import page
    from arknights_mower.utils import selection_skill_rank

    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.recog = SimpleNamespace(_img=frame, img=frame)
    solver.find = Mock(return_value=None)
    solver.read_screen = read_screen
    order = ("技能", False)
    solver.detect_arrange_order = Mock(return_value=order)
    solver._profession_filter_buttons = Mock(
        return_value=(("confirm_blue", 1609, 990),)
    )
    solver._profession_search_pages = {}
    monkeypatch.setattr(base_schedule, "agent_card_selected", lambda *_: False)
    monkeypatch.setattr(base_schedule, "branch_filter_state", lambda *_: (False, False))
    monkeypatch.setattr(
        base_schedule, "selection_title_matches", lambda _, name: name == "manufacture"
    )
    monkeypatch.setattr(
        selection_skill_rank,
        "selection_skill_rank",
        lambda *_: {False: (1, 1), True: (10, 10)},
    )

    left, right = page(_JOINED_PAGES[:6]), page(_JOINED_PAGES[4:])
    room, profession = "room_3_1", "SPECIAL"
    choice = solver._ranked_first_page_order(
        room,
        profession,
        "温蒂",
        set(),
        left,
        order,
        profession_page=False,
        product=None,
    )
    first = solver._skill_profession_page(room, profession, order, (), left, first=True)
    assert first is not None
    solver._remember_skill_successor(first, room, right)
    if solver._profession_search_pages:
        solver._remember_skill_successor(first, room, right)
    return choice, list(solver._profession_search_pages.values())


@pytest.mark.parametrize(
    ("index", "allowed"),
    [(0, True), (1, False), (2, False), (3, True), (4, False), (5, False)],
)
def test_selector_entries_use_the_b102_title(
    station_frames, monkeypatch, index, allowed
):
    ocr = Mock(side_effect=AssertionError("完整字模不需要 OCR"))
    result = ranked_and_remembered(station_frames[index], ocr, monkeypatch)
    expected = (("技能", False), [_JOINED_PAGES]) if allowed else (None, [])
    assert result == expected
    ocr.assert_not_called()


@pytest.mark.parametrize(
    ("raw_title", "allowed"),
    [
        ("进驻状态", True),
        ("全部", False),
        ("宿舍锁定", False),
        ("未进驻", False),
        (25, False),
    ],
)
def test_selector_entries_keep_the_original_ocr_title_guard(
    station_frames, monkeypatch, raw_title, allowed
):
    frame = station_frames[3].copy()
    frame[35:82, 1715:1745] = 0
    ocr = Mock(return_value=raw_title)
    result = ranked_and_remembered(frame, ocr, monkeypatch)
    expected = (("技能", False), [_JOINED_PAGES]) if allowed else (None, [])
    assert result == expected
    assert ocr.call_count == 2
    for call in ocr.call_args_list:
        assert call.args[0] is frame
        assert call.kwargs == {"type": "text", "cord": ((1600, 35), (1715, 82))}
