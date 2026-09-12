"""职业筛选复位列表，保留稳定观察与最终校验，不发送反向拖动。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from arknights_mower.solvers.base_mixin import AgentSelectionNotReady, BaseMixin
from arknights_mower.tests.agent_page_observation_tests import observe, page, solver_for
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.solver import BaseSolver


@pytest.mark.parametrize("count", [0, 1, 3, 100])
@pytest.mark.parametrize("profession", [None, "ALL", "MEDIC", "SPECIAL"])
@pytest.mark.parametrize("train", [False, True])
def test_reset_switches_away_and_restores_filter_at_every_count(
    count, profession, train
):
    solver = BaseMixin()
    solver.find = MagicMock(return_value=None)
    solver.profession_filter = MagicMock()
    solver.wait_for_agent_page = MagicMock(return_value=page())
    solver.swipe_noinertia = MagicMock()
    assert solver.swipe_left(count, profession, train=train) == 0
    restored = profession or "ALL"
    temporary = "PIONEER" if restored == "ALL" else "ALL"
    assert solver.profession_filter.call_args_list == [call(temporary), call(restored)]
    solver.wait_for_agent_page.assert_called_once_with(
        full_scan=restored == "ALL", train=train
    )
    solver.swipe_noinertia.assert_not_called()


@pytest.mark.parametrize("count", [0, 100])
@pytest.mark.parametrize("result", [(), page(offset=160)])
def test_reset_rejects_empty_or_clipped_page_without_drag_fallback(count, result):
    solver = BaseMixin()
    solver.find = MagicMock(return_value=None)
    solver.profession_filter = MagicMock()
    solver.wait_for_agent_page = MagicMock(return_value=result)
    solver.tap = MagicMock()
    solver.swipe_noinertia = MagicMock()
    with pytest.raises(AgentSelectionNotReady, match="筛选复位"):
        solver.swipe_left(count, "ALL")
    solver.tap.assert_not_called()
    solver.swipe_noinertia.assert_not_called()


def test_training_layout_keeps_its_own_first_column_rule():
    solver = BaseMixin()
    solver.find = MagicMock(return_value=None)
    solver.profession_filter = MagicMock()
    solver.wait_for_agent_page = MagicMock(return_value=page(offset=160))
    solver.swipe_noinertia = MagicMock()
    assert solver.swipe_left(0, "MEDIC", train=True) == 0
    solver.wait_for_agent_page.assert_called_once_with(full_scan=False, train=True)
    solver.swipe_noinertia.assert_not_called()


@pytest.mark.parametrize("stop_at", [0, 1])
def test_stop_in_filter_transition_prevents_further_input(stop_at):
    solver = BaseMixin()
    solver.find = MagicMock(return_value=None)
    solver.profession_filter = MagicMock(side_effect=[None] * stop_at + [MowerExit])
    solver.wait_for_agent_page = MagicMock()
    solver.swipe_noinertia = MagicMock()
    with pytest.raises(MowerExit):
        solver.swipe_left(100, "MEDIC")
    assert solver.profession_filter.call_count == stop_at + 1
    solver.wait_for_agent_page.assert_not_called()
    solver.swipe_noinertia.assert_not_called()


def configure_real_filter(
    solver, monkeypatch, initial="ALL", *, opened=True, train=False
):
    """真实 profession_filter/tap，UI 仅模拟侧栏颜色与输入响应。"""
    active = {"label": initial, "offset": 160, "changes": [], "opened": opened}
    positions = {
        (1918, 135 + index * 110): label
        for index, label in enumerate(solver.profession_labels)
    }

    def device_tap(position):
        if position == (1860, 60):
            active["opened"] = not active["opened"]
            return
        if position not in positions:
            assert position == (724, 504)  # 复位后首张完整卡片中心。
            return
        label = positions[position]
        if label != active["label"]:
            active["changes"].append(label)
            active["offset"] = 0
        active["label"] = label

    solver.device = SimpleNamespace(tap=MagicMock(side_effect=device_tap))
    solver.tap = BaseSolver.tap.__get__(solver)
    solver.get_pos = BaseSolver.get_pos

    def find_button(name):
        if name != ("confirm_train" if train else "confirm_blue"):
            return None
        x = (
            (1554 if active["opened"] else 1669)
            if train
            else (1609 if active["opened"] else 1724)
        )
        return ((x, 50), (x + 40, 90))

    solver.find = MagicMock(side_effect=find_button)
    solver.get_color = MagicMock(
        side_effect=lambda location: (
            0,
            0,
            255 if positions[location] == active["label"] else 0,
        )
    )
    monkeypatch.setattr(config, "stop_mower", MagicMock(is_set=lambda: False))
    return active


@pytest.mark.parametrize("profession", ["ALL", "MEDIC"])
@pytest.mark.parametrize("opened", [False, True])
@pytest.mark.parametrize("train", [False, True])
def test_real_filter_restores_panel_and_invalidates_pre_reset_observation(
    monkeypatch, profession, opened, train
):
    old, new = page(offset=160), page()
    solver = solver_for(monkeypatch, [old] * 2 + [new] * 3)
    old_observation = observe(solver, full_scan=profession == "ALL", train=train)
    old_image = solver.recog._img
    active = configure_real_filter(
        solver, monkeypatch, profession, opened=opened, train=train
    )
    count, observed = solver.swipe_left(0, profession, train=train, return_page=True)
    assert count == 0 and active["offset"] == 0
    assert active["changes"] == (
        ["PIONEER", "ALL"] if profession == "ALL" else ["ALL", "MEDIC"]
    )
    assert active["label"] == profession
    assert active["opened"] is opened
    panel_taps = [
        item for item in solver.device.tap.call_args_list if item.args[0] == (1860, 60)
    ]
    assert len(panel_taps) == (0 if opened else 2)
    assert solver.recog._img is not old_image
    assert (
        old_observation.consume(
            solver.recog, full_scan=profession == "ALL", train=train
        )
        is None
    )
    assert observed.page == new
    captures = solver.recog.captures
    assert solver.scan_agent(
        ["砾"], full_scan=profession == "ALL", train=train, observation=observed
    )[0] == ["砾"]
    assert solver.recog.captures == captures + 1
    solver.swipe_noinertia.assert_not_called()


def test_real_tap_obeys_stop_before_filter_input(monkeypatch):
    solver = solver_for(monkeypatch, [page()] * 2)
    configure_real_filter(solver, monkeypatch)
    monkeypatch.setattr(config, "stop_mower", MagicMock(is_set=lambda: True))
    with pytest.raises(MowerExit):
        solver.swipe_left(0, "ALL")
    solver.device.tap.assert_not_called()
    solver.swipe_noinertia.assert_not_called()


def test_filter_failure_propagates_without_reverse_gesture(monkeypatch):
    solver = solver_for(monkeypatch, [page()] * 2)
    configure_real_filter(solver, monkeypatch)
    solver.get_color.return_value = (0, 0, 0)
    solver.get_color.side_effect = None
    with pytest.raises(Exception, match="打开职业筛选失败"):
        solver.swipe_left(0, "ALL")
    solver.swipe_noinertia.assert_not_called()


@pytest.mark.parametrize("opened", [False, True])
@pytest.mark.parametrize("train", [False, True])
def test_close_default_filter_still_selects_all_then_closes(monkeypatch, opened, train):
    solver = solver_for(monkeypatch, [page()] * 2)
    active = configure_real_filter(
        solver, monkeypatch, "MEDIC", opened=opened, train=train
    )
    solver.profession_filter()
    assert active["label"] == "ALL"
    assert active["opened"] is False
    solver.swipe_noinertia.assert_not_called()


def test_stop_before_restoring_closed_panel_prevents_close_input(monkeypatch):
    solver = solver_for(monkeypatch, [page()] * 2)
    active = configure_real_filter(solver, monkeypatch, opened=False)
    stopped = {"value": False}
    monkeypatch.setattr(
        config, "stop_mower", MagicMock(is_set=lambda: stopped["value"])
    )
    tap = solver.device.tap.side_effect

    def stop_after_restore(position):
        tap(position)
        if active["changes"] == ["PIONEER", "ALL"]:
            stopped["value"] = True

    solver.device.tap.side_effect = stop_after_restore
    solver.wait_for_agent_page = MagicMock()
    with pytest.raises(MowerExit):
        solver.swipe_left(0, "ALL")
    # 只发送打开侧栏的第一次操作，停止后的关闭输入不发出。
    panel_taps = [
        item for item in solver.device.tap.call_args_list if item.args[0] == (1860, 60)
    ]
    assert len(panel_taps) == 1
    solver.wait_for_agent_page.assert_not_called()
    solver.swipe_noinertia.assert_not_called()


@pytest.mark.parametrize(
    "buttons", [(None, None), (((1650, 0),), None), (((1724, 0),), ((1554, 0),))]
)
def test_unknown_or_conflicting_panel_state_is_not_guessed(buttons):
    solver = BaseMixin()
    solver.find = MagicMock(side_effect=buttons)
    solver.profession_filter = MagicMock()
    solver._close_profession_filter = MagicMock()
    solver.wait_for_agent_page = MagicMock(return_value=page())
    solver.swipe_noinertia = MagicMock()
    assert solver.swipe_left(0, "ALL") == 0
    solver._close_profession_filter.assert_not_called()
    solver.swipe_noinertia.assert_not_called()
