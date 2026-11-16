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


def test_stop_prevents_any_filter_input(station_ui, monkeypatch):
    solver, _ = station_ui
    monkeypatch.setattr(config.stop_mower, "is_set", lambda: True)
    with pytest.raises(MowerExit):
        solver.agent_station_filter("未进驻")
    solver.tap.assert_not_called()
