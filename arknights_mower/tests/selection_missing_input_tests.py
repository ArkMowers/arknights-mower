"""卡片名字正确，但实际选择缺人或多人的回归。"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.tests.agent_page_observation_tests import page  # noqa: E402
from arknights_mower.tests.visible_production_target_tests import (  # noqa: E402
    LivePageRecognizer,
)
from arknights_mower.utils import config  # noqa: E402


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("dropped_input", ["select", "deselect", None])
def test_matching_names_still_rebuild_actual_selection(
    monkeypatch, enabled, dropped_input
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    solver = object.__new__(BaseSchedulerSolver)
    targets = ["鸿雪", "但书"]
    current = (
        ["鸿雪", "但书", "黑键"] if dropped_input == "deselect" else ["鸿雪", "黑键"]
    )
    selected = current.copy()
    cards = current + [n for n in targets + ["杜林"] if n not in current]
    events = []
    dropped = False
    solver.recog = LivePageRecognizer(lambda: page(cards), events)
    solver.op_data = SimpleNamespace(
        operators={},
        profession_filter=set(),
        get_current_room=lambda *_: current.copy(),
    )
    solver.last_room = ""
    solver.choose_error = set()
    solver.preserve_resting_crafters = MagicMock()
    solver.profession_filter = MagicMock(side_effect=lambda *_: solver.recog.update())
    solver.detect_arrange_order = MagicMock(return_value=("技能", False))
    solver.get_order = MagicMock(return_value=(False, ("技能", False)))
    solver.find = MagicMock(return_value=None)
    solver.sleep = MagicMock(side_effect=lambda *a, **kw: solver.recog.update())
    positions = [(672, 378), (672, 810), (864, 378)]

    def sort(*a, **kw):
        # 但书即使未选中，也恰好位于已选鸿雪之后；名字前缀始终与目标相同。
        cards[:] = selected + [
            n for n in ["但书", "黑键", "鸿雪", "杜林"] if n not in selected
        ]
        events.append(("sort", tuple(selected)))
        solver.recog.update()

    def tap(location, **kw):
        nonlocal dropped
        if isinstance(location[0], (int, float)):
            if location[1] == 1026:
                selected.clear()
                events.append(("clear",))
                solver.recog.update()
                return
            name = cards[positions.index(location)]
            drop = dropped_input == "deselect" and name == "黑键"
        else:
            name = next(n for n, scope in solver.recog.img if scope == location)
            drop = dropped_input == "select" and name == "但书"
        if drop and not dropped:
            dropped = True
            events.append(("drop", name))
        elif name in selected:
            selected.remove(name)
        else:
            selected.append(name)
        # 清空与逐个点击不重排卡片；点击排序按钮时才将已选卡片置顶。
        solver.recog.update()

    solver.tap = MagicMock(side_effect=tap)
    solver.switch_arrange_order = MagicMock(side_effect=sort)
    solver.swipe_noinertia = MagicMock(side_effect=AssertionError("无需翻页"))
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kw: tuple(img))
    solver.choose_agent(targets.copy(), "room_2_1")
    assert dropped is (dropped_input is not None)
    assert selected == targets
    assert events.count(("clear",)) == 1
    sorts = [e for e in events if e[0] == "sort"]
    assert len(sorts) == 2 and sorts[-1] == ("sort", tuple(targets))
    solver.profession_filter.assert_called_once_with()
