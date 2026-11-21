"""清空输入的延迟反馈不能导致保留旧暂选或跳过目标。"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit


@pytest.fixture
def selection_module(monkeypatch):
    import importlib

    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", Mock())
    return importlib.import_module("arknights_mower.solvers.base_mixin")


@pytest.mark.parametrize("mode", ["xhigh", "high", "medium", "low"])
@pytest.mark.parametrize("unchanged", [False, True])
def test_clear_waits_for_observed_unselected_borders(
    monkeypatch, selection_module, mode, unchanged
):
    base_mixin = selection_module
    from arknights_mower.utils.character_recognize import operator_list

    image = np.array(
        Image.open(
            Path(__file__).parent / "fixtures/selection/clear_delayed_20261020.jpg"
        )
    )
    page = operator_list(image)
    assert [name for name, scope in page[:4]] == ["隐德来希", "车尔尼", "香草", "清流"]
    # 保留现场原图的姓名识别及旧蓝框；只替换清空完成后的边框观测。
    states = [True, True, False, False, False, False, False, False]
    cursor = -1
    solver = selection_module.BaseMixin()
    solver.recog = SimpleNamespace(w=1920, h=1080, img=image)

    def update():
        nonlocal cursor
        cursor += 1

    solver.recog.update = Mock(side_effect=update)
    solver.find = Mock(return_value=False)
    solver.tap = Mock()
    solver.wait_for_next_observation = Mock(side_effect=lambda *_: update())
    original = base_mixin.agent_card_selected
    monkeypatch.setattr(config, "conf", config.Conf(performance_mode=mode))
    monkeypatch.setattr(
        base_mixin,
        "agent_card_selected",
        lambda img, scope, **_: (
            original(img, scope) if unchanged or states[cursor] else False
        ),
    )
    if unchanged:
        with pytest.raises(selection_module.AgentSelectionNotReady, match="清空"):
            solver.clear_agent_selection()
    else:
        solver.clear_agent_selection()
        assert cursor >= (3 if mode == "low" else 2)
    solver.tap.assert_called_once()


@pytest.mark.parametrize("error", ["MowerExit", "AgentSelectionPageChanged"])
def test_clear_does_not_hide_cancellation_or_page_exit(selection_module, error):
    error = (
        MowerExit
        if error == "MowerExit"
        else selection_module.AgentSelectionPageChanged
    )
    solver = selection_module.BaseMixin()
    solver.recog = SimpleNamespace(w=1920, h=1080, update=Mock(side_effect=error))
    solver.tap = Mock()
    with pytest.raises(error):
        solver.clear_agent_selection()
    solver.tap.assert_called_once()


@pytest.mark.parametrize("mode", ["xhigh", "high", "medium", "low"])
def test_normal_selection_cannot_skip_residents_from_delayed_clear(
    monkeypatch, selection_module, mode
):
    base_mixin = selection_module
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
    from arknights_mower.utils.operators import Operators
    from arknights_mower.utils.plan import Plan, PlanConfig

    targets = ["隐德来希", "车尔尼", "杰西卡"]
    selected = ["隐德来希", "车尔尼", "香草", "清流", "撷英调香师"]
    roster = selected + ["杰西卡", "杜林", "摩根"]
    cards = roster.copy()
    frames = {}
    clear_pending = 0
    events = []
    solver = object.__new__(BaseSchedulerSolver)
    solver.task = None
    solver.last_room = ""
    solver.choose_error = set()
    solver.op_data = Operators(
        {"default_plan": Plan({}, PlanConfig("", "", "")), "backup_plans": []}
    )
    solver.op_data.profession_filter = set()
    solver.prepare_dorm_selection = Mock(return_value=[])
    solver._check_group_shift_targets = Mock(return_value=False)
    solver.profession_filter = Mock()
    solver.detect_arrange_order = Mock(return_value=("技能", False))
    solver.get_order = Mock(return_value=(False, ("心情", "true")))
    solver.find = Mock(return_value=False)
    solver.recog = SimpleNamespace(w=1920, h=1080)

    def refresh():
        nonlocal clear_pending
        if clear_pending:
            clear_pending -= 1
            if not clear_pending:
                selected.clear()
                events.append("cleared")
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        page = []
        for index, name in enumerate(cards):
            left, top = 631 + index // 2 * 216, 488 + index % 2 * 421
            scope = ((left, top), (left + 189, top + 32))
            page.append((name, scope))
        frames[id(img)] = (page, set(selected))
        solver.recog.img = img

    def order(*_):
        cards[:] = selected + [name for name in roster if name not in selected]
        refresh()

    def tap(point, **_):
        nonlocal clear_pending
        if point[1] == 1026:
            events.append("clear")
            clear_pending = 3
        else:
            assert not clear_pending, "不能在旧暂选清空前选人"
            if isinstance(point[0], tuple):
                name = next(
                    name
                    for name, scope in frames[id(solver.recog.img)][0]
                    if scope == point
                )
            else:
                positions = [
                    (672, 378),
                    (672, 810),
                    (864, 378),
                    (864, 810),
                    (1056, 378),
                ]
                name = cards[positions.index(point)]
            if name in selected:
                selected.remove(name)
            else:
                selected.append(name)
            events.append(("select", name))

    solver.recog.update = Mock(side_effect=refresh)
    solver.sleep = Mock(side_effect=lambda *_: refresh())
    solver.wait_for_next_observation = Mock(side_effect=lambda *_: refresh())
    solver.switch_arrange_order = Mock(side_effect=order)
    solver.tap = Mock(side_effect=tap)
    solver.swipe_left = Mock(return_value=(0, None))
    solver.swipe_agent_page = Mock(side_effect=AssertionError("当前页已有目标"))
    monkeypatch.setattr(config, "conf", config.Conf(performance_mode=mode))
    monkeypatch.setattr(
        base_mixin, "operator_list", lambda img, **_: frames[id(img)][0]
    )
    monkeypatch.setattr(
        base_mixin,
        "agent_card_selected",
        lambda img, scope, **_: (
            next(name for name, box in frames[id(img)][0] if box == scope)
            in frames[id(img)][1]
        ),
    )
    refresh()
    solver.choose_agent(targets.copy(), "dormitory_3", fast_mode=False)
    assert selected == targets
    assert events.count("clear") == events.count("cleared") == 2
