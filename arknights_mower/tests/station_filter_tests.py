"""进驻筛选只在菜单确认展开后输入，并等待目标标题。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_mixin import AgentSelectionNotReady, BaseMixin
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit


@pytest.fixture
def station_ui(monkeypatch):
    monkeypatch.setattr(config.stop_mower, "is_set", lambda: False)
    solver = object.__new__(BaseMixin)
    solver.recog = SimpleNamespace(img=None)
    solver.require_agent_selection_page = MagicMock()
    solver.selection_transition_timing = MagicMock(return_value=(0.1, 4))
    state = {"status": "全部", "opened": False, "delay": 0, "lost": None}
    pending = []

    def read(img, *, type, cord):
        if cord[0][1] == 35:
            return "进驻状态" if state["status"] == "全部" else state["status"]
        return "全部" if state["opened"] else ""

    def tap(pos, **kwargs):
        if pos == (1675, 60):
            action = "open"
        else:
            assert state["opened"], "cannot click a card through a closed menu"
            action = {137: "全部", 213: "宿舍锁定", 289: "未进驻"}[pos[1]]
        if state["lost"] != action:
            pending.append([state["delay"], action])

    def sleep(interval):
        for item in pending[:]:
            if item[0] > 0:
                item[0] -= 1
                continue
            if item[1] == "open":
                state["opened"] = True
            else:
                state.update(status=item[1], opened=False)
            pending.remove(item)

    solver.read_screen = MagicMock(side_effect=read)
    solver.tap = MagicMock(side_effect=tap)
    solver.sleep = MagicMock(side_effect=sleep)
    return solver, state


@pytest.mark.parametrize("original", ["全部", "宿舍锁定", "未进驻"])
@pytest.mark.parametrize("opened", [False, True])
@pytest.mark.parametrize("delay", [0, 2])
def test_read_set_and_restore_station_filter(station_ui, original, opened, delay):
    solver, state = station_ui
    state.update(status=original, opened=opened, delay=delay)
    assert solver.agent_station_filter() == original
    solver.tap.assert_not_called()
    assert solver.agent_station_filter("未进驻") == "未进驻"
    assert state["status"] == "未进驻" and not state["opened"]
    solver.agent_station_filter(original)
    assert state["status"] == original and not state["opened"]
    assert solver.tap.call_count <= 4


@pytest.mark.parametrize("lost", ["open", "未进驻"])
def test_unacknowledged_filter_input_is_not_repeated(station_ui, lost):
    solver, state = station_ui
    state["lost"] = lost
    with pytest.raises(AgentSelectionNotReady, match="尚未生效"):
        solver.agent_station_filter("未进驻")
    taps = [item.args[0] for item in solver.tap.call_args_list]
    assert taps == ([(1675, 60)] if lost == "open" else [(1675, 60), (1675, 289)])
    assert solver.sleep.call_count <= 8


def test_unknown_title_does_not_trigger_filter_input(station_ui):
    solver, state = station_ui
    state["status"] = "不可识别"
    with pytest.raises(AgentSelectionNotReady, match="未识别进驻筛选"):
        solver.agent_station_filter("未进驻")
    solver.tap.assert_not_called()


def test_read_only_station_filter_rechecks_unreadable_title_without_menu_ocr(
    station_ui,
):
    solver, _ = station_ui
    solver.read_screen.side_effect = ["", "未进驻"]
    assert solver.agent_station_filter() == "未进驻"
    assert [call.kwargs["cord"] for call in solver.read_screen.call_args_list] == [
        ((1600, 35), (1715, 82)),
        ((1600, 35), (1715, 82)),
    ]
    solver.sleep.assert_called_once()
    solver.tap.assert_not_called()


def test_stop_prevents_any_filter_input(station_ui, monkeypatch):
    solver, _ = station_ui
    monkeypatch.setattr(config.stop_mower, "is_set", lambda: True)
    with pytest.raises(MowerExit):
        solver.agent_station_filter("未进驻")
    solver.tap.assert_not_called()


@pytest.mark.parametrize(
    "status, known_room, hidden, expected_swipes",
    [
        ("未进驻", "room_3_2", True, 0),
        ("未进驻", "", True, 2),
        ("宿舍锁定", "dormitory_1", True, 2),
        ("全部", "room_3_2", False, 0),
    ],
)
def test_named_production_roster_keeps_existing_selections_when_station_filter_hides_target(
    station_ui, monkeypatch, status, known_room, hidden, expected_swipes
):
    from arknights_mower.solvers.base_mixin import AgentPageNotAdvanced
    from arknights_mower.tests.agent_page_observation_tests import page
    from arknights_mower.tests.choose_agent_filter_tests import selection_solver

    station, menu = station_ui
    menu.update(status=status, delay=2)
    solver, selected = selection_solver(monkeypatch, residents=["鸿雪"])
    solver.op_data.operators["能天使"] = SimpleNamespace(
        current_room=known_room, current_index=0 if known_room else -1
    )
    solver.find.side_effect = lambda name: (
        ((1724, 990), (1810, 1041)) if name == "confirm_blue" else None
    )
    solver.get_order.return_value = (False, ("技能", False))
    solver.agent_station_filter = MagicMock(wraps=station.agent_station_filter)
    position = 0
    retained_when_found = []

    def scan(remaining, **_):
        names = ["但书"] if position == 0 else ["红豆"]
        if position == 0 and (not hidden or menu["status"] == "全部"):
            names.append("能天使")
        found = [name for name in names if name in remaining]
        for name in found:
            if name == "能天使":
                retained_when_found.extend(selected)
            selected.append(name)
            remaining.remove(name)
        return found, page(tuple(names))

    def next_page(*_, **__):
        nonlocal position
        if position:
            raise AgentPageNotAdvanced("已到列表末尾")
        position = 1
        return 1, None

    def first_page(count, profession, *, return_page):
        nonlocal position
        assert count == 1 and profession == "ALL" and return_page
        position = 0
        return 0, None

    solver.scan_agent.side_effect = scan
    solver.swipe_agent_page.side_effect = next_page
    solver.swipe_left.side_effect = first_page
    targets = ["鸿雪", "但书", "能天使"]
    solver.choose_agent(targets.copy(), "room_1_2", fresh_room_entry=True)

    assert selected == targets and retained_when_found == targets[:2]
    assert solver.swipe_agent_page.call_count == expected_swipes
    assert menu["status"] == "全部" and not menu["opened"]
    if hidden:
        assert [c.args[0] for c in station.tap.call_args_list] == [
            (1675, 60),
            (1675, 137),
        ]
        assert solver.swipe_left.call_count == bool(expected_swipes)
    else:
        solver.agent_station_filter.assert_not_called()
        station.tap.assert_not_called()


@pytest.mark.parametrize(
    "status, left_selection, searches",
    [("未进驻", False, 2), ("模糊", False, 1), ("未进驻", True, 1)],
)
def test_station_recovery_is_bounded_and_does_not_tap_through_room_exit(
    station_ui, monkeypatch, status, left_selection, searches
):
    from arknights_mower.solvers.base_mixin import (
        AgentPageNotAdvanced,
        AgentSelectionPageChanged,
    )
    from arknights_mower.tests.agent_page_observation_tests import page
    from arknights_mower.tests.choose_agent_filter_tests import selection_solver

    station, menu = station_ui
    menu["status"] = status
    solver, selected = selection_solver(monkeypatch, residents=["鸿雪"])
    solver.agent_station_filter = MagicMock(wraps=station.agent_station_filter)
    solver.get_order.return_value = (False, ("技能", False))
    solver.scan_agent.side_effect = lambda *_, **__: ([], page(("古米", "砾")))
    solver.swipe_agent_page.side_effect = AgentPageNotAdvanced("已到列表末尾")
    confirm = ((1724, 990), (1810, 1041))
    solver.find.side_effect = lambda name: (
        confirm
        if name == "confirm_blue"
        or (
            left_selection
            and solver.swipe_agent_page.called
            and name == "arrange_check_in_on"
        )
        else None
    )

    with pytest.raises(
        AgentSelectionPageChanged if left_selection else AgentPageNotAdvanced
    ):
        solver.choose_agent(["鸿雪", "阿米娅"], "room_1_2", fresh_room_entry=True)

    assert selected == ["鸿雪"]
    assert solver.swipe_agent_page.call_count == searches
    if left_selection:
        solver.agent_station_filter.assert_not_called()
    assert station.tap.call_count == (2 if searches == 2 else 0)
