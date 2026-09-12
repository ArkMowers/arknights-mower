"""生产房可见目标先选人，未翻页且完整名单正确时不再复位。"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.tests.agent_page_observation_tests import (  # noqa: E402
    page,
)
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.solver import BaseSolver  # noqa: E402

pytestmark = pytest.mark.usefixtures("low_frame_rate")


class LivePageRecognizer:
    w, h = 1920, 1080

    def __init__(self, provider, events):
        self.provider = provider
        self.events = events
        self._img = None
        self.captures = 0

    def update(self):
        self._img = None

    @property
    def img(self):
        if self._img is None:
            self._img = list(self.provider())
            self.captures += 1
            self.events.append(("capture", self.captures))
        return self._img


def production_solver(
    monkeypatch, *, target_visible=True, final_missing=False, final_problem=None
):
    solver = object.__new__(BaseSchedulerSolver)
    selected = ["鸿雪", "黑键"]
    state = {"phase": "initial", "sorts": 0}
    events = []
    initial = page(("鸿雪", "黑键", "杜林", "芬"))
    after_sort = page(
        (
            "鸿雪",
            "暗索",
            "桃金娘",
            "史都华德",
            "龙舌兰",
            "渡桥",
            "明椒",
            "折光",
            "卡夫卡",
            "柏喙",
            "但书",
            "嘉辛塔",
        )
    )
    missing = page(("鸿雪", "暗索", "桃金娘", "史都华德"))

    def provider():
        if state["phase"] == "initial":
            return initial
        if state["phase"] == "sorted":
            return after_sort if target_visible else missing
        if state["phase"] == "left":
            return page(("鸿雪", "但书", "暗索", "芬"))
        if state["phase"] == "final":
            if final_problem == "clipped":
                return page(tuple(selected), offset=160)
            if final_problem == "middle":
                return page(("杜林", "芬"))
        return page(("鸿雪", "暗索") if final_missing else tuple(selected))

    solver.recog = LivePageRecognizer(provider, events)
    solver.op_data = SimpleNamespace(
        operators={},
        profession_filter=set(),
        get_current_room=lambda *args: ["鸿雪", "黑键"],
    )
    solver.last_room = ""
    solver.choose_error = set()
    solver.preserve_resting_crafters = MagicMock()
    solver.detect_arrange_order = MagicMock(return_value=("工作状态", False))
    solver.get_order = MagicMock(return_value=(True, ("技能", "true")))
    solver.find = MagicMock(side_effect=lambda *_: bool(solver.recog.img) and False)
    solver.sleep = MagicMock(side_effect=lambda *args, **kwargs: solver.recog.update())

    def reset_filter(label=None):
        if label:
            events.append(("filter", label, state["phase"], solver.recog.captures))
            if label == "ALL" and state["phase"] == "sorted":
                state["phase"] = "left"
            elif label == "ALL" and state["phase"] == "final":
                state["phase"] = "final_reset"
        solver.recog.update()

    solver.profession_filter = MagicMock(side_effect=reset_filter)

    def sort(*args):
        state["sorts"] += 1
        state["phase"] = "sorted" if state["sorts"] == 1 else "final"
        events.append(("sort", state["sorts"]))
        solver.recog.update()

    def tap(location, **kwargs):
        if isinstance(location[0], (int, float)):
            # 快速模式撤下原第二位黑键；目标安排仍保留Current解析后的鸿雪。
            assert location == (672.0, 810.0)
            selected.remove("黑键")
            events.append(("remove", "黑键"))
        else:
            name = next(name for name, scope in solver.recog.img if scope == location)
            assert name not in selected
            selected.append(name)
            events.append(("select", name, location))
        solver.recog.update()

    solver.switch_arrange_order = MagicMock(side_effect=sort)
    solver.tap = MagicMock(side_effect=tap)
    solver.swipe_noinertia = MagicMock(side_effect=AssertionError("不应反向拖动"))
    solver.tap_confirm = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: tuple(img))
    return solver, selected, events


def test_visible_target_and_correct_final_roster_do_not_reset_filter(
    monkeypatch,
):
    solver, selected, events = production_solver(monkeypatch)
    solver.choose_agent(["鸿雪", "但书"], "room_2_1")
    solver.tap_confirm("room_2_1", {})
    selection = next(
        i for i, event in enumerate(events) if event[:2] == ("select", "但书")
    )
    assert not any(event[0] == "filter" for event in events)
    assert events[selection][2][0][0] == 1705  # 第六列，无需先复位到左端。
    solver.swipe_noinertia.assert_not_called()
    assert selected == ["鸿雪", "但书"]
    assert solver.switch_arrange_order.call_count == 2
    assert ("sort", 2) in events[selection + 1 :]
    solver.tap_confirm.assert_called_once()


def test_missing_target_resets_filter_then_searches_left(
    monkeypatch,
):
    solver, selected, events = production_solver(monkeypatch, target_visible=False)
    solver.choose_agent(["鸿雪", "但书"], "room_2_1")
    first_reset = next(i for i, event in enumerate(events) if event[0] == "filter")
    selection = next(
        i for i, event in enumerate(events) if event[:2] == ("select", "但书")
    )
    assert first_reset < selection
    assert events[first_reset][:3] == ("filter", "PIONEER", "sorted")
    solver.swipe_noinertia.assert_not_called()
    assert events[selection][2][0][0] == 630
    assert selected == ["鸿雪", "但书"]


def test_missing_final_target_prevents_confirmation_even_after_visible_click(
    monkeypatch,
):
    solver, _, events = production_solver(monkeypatch, final_missing=True)
    with pytest.raises(Exception, match="检测到干员选择错误"):
        solver.choose_agent(["鸿雪", "但书"], "room_2_1")
        solver.tap_confirm("room_2_1", {})
    assert any(event[:2] == ("select", "但书") for event in events)
    assert any(event[:3] == ("filter", "ALL", "final") for event in events)
    solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize(
    "room,targets,first_found",
    [
        ("dormitory_1", ["但书"], []),
        ("central", ["但书"], []),
        ("meeting", ["但书"], []),
        ("train", ["但书"], []),
        ("room_2_1", ["但书", "Free"], []),
        ("room_2_1", ["但书", "伺夜"], []),
        ("room_2_1", ["伺夜", "但书"], ["伺夜"]),
    ],
)
def test_other_scopes_and_initial_multiple_targets_reset_before_searching(
    monkeypatch, room, targets, first_found
):
    solver = object.__new__(BaseSchedulerSolver)
    solver.recog = SimpleNamespace(w=1920, h=1080, img=None, update=MagicMock())
    solver.op_data = SimpleNamespace(
        operators={}, profession_filter=set(), get_current_room=lambda *_: []
    )
    solver.last_room = ""
    solver.choose_error = set()
    solver.preserve_resting_crafters = MagicMock()
    solver.detect_arrange_order = MagicMock(return_value=("工作状态", False))
    solver.profession_filter = MagicMock()
    solver.get_order = MagicMock(return_value=(False, ("心情", "true")))
    solver.switch_arrange_order = MagicMock()
    solver.sleep = MagicMock()

    def initial_scan(remaining, **kwargs):
        for name in first_found:
            remaining.remove(name)
        return first_found, page()

    solver.scan_agent = MagicMock(side_effect=initial_scan)
    solver.swipe_left = MagicMock(side_effect=MowerExit)
    with pytest.raises(MowerExit):
        solver.choose_agent(targets, room)
    solver.scan_agent.assert_called_once()
    solver.swipe_left.assert_called_once_with(0, "ALL", return_page=True)


def test_stop_after_sort_prevents_visible_target_device_tap(monkeypatch):
    solver, _, events = production_solver(monkeypatch)
    solver.op_data.get_current_room = lambda *_: ["鸿雪"]
    solver.device = MagicMock()
    solver.tap = BaseSolver.tap.__get__(solver)
    stopped = {"value": False}
    monkeypatch.setattr(
        config, "stop_mower", MagicMock(is_set=lambda: stopped["value"])
    )
    sort = solver.switch_arrange_order.side_effect

    def stop_after_sort(*args):
        sort(*args)
        stopped["value"] = True

    solver.switch_arrange_order.side_effect = stop_after_sort
    with pytest.raises(MowerExit):
        solver.choose_agent(["鸿雪", "但书"], "room_2_1")
    assert ("sort", 1) in events
    solver.device.tap.assert_not_called()
    solver.swipe_noinertia.assert_not_called()
    solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize("problem", ["clipped", "middle"])
def test_zero_swipes_still_reset_when_final_page_cannot_confirm_roster(
    monkeypatch, problem
):
    solver, selected, events = production_solver(monkeypatch, final_problem=problem)
    solver.choose_agent(["鸿雪", "但书"], "room_2_1")
    assert selected == ["鸿雪", "但书"]
    assert any(event[:3] == ("filter", "PIONEER", "final") for event in events)
    assert any(event[:3] == ("filter", "ALL", "final") for event in events)
    solver.swipe_noinertia.assert_not_called()


def test_stop_during_current_roster_verification_does_not_reset(monkeypatch):
    solver, _, events = production_solver(monkeypatch)
    solver.wait_for_arranged_agents = MagicMock(side_effect=MowerExit)
    with pytest.raises(MowerExit):
        solver.choose_agent(["鸿雪", "但书"], "room_2_1")
    assert not any(event[0] == "filter" for event in events)
    solver.tap_confirm.assert_not_called()
