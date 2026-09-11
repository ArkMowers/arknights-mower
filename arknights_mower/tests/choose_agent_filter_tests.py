"""执行真实选人流程，模拟职业筛选后的可见卡片及点击结果。"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin, base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402

RESIDENTS = ["冰酿", "闪灵", "菲亚梅塔", "爱丽丝"]


@pytest.mark.parametrize("fast_mode", [True, False])
@pytest.mark.parametrize("preserve", [True, False])
@pytest.mark.parametrize("fill_free", [True, False])
def test_mixed_professions_reordered_after_filtered_selection(
    monkeypatch, fast_mode, preserve, fill_free
):
    agents = RESIDENTS + ["Free" if fill_free else "伊芙利特"]
    solver, selected = selection_solver(monkeypatch)

    solver.choose_agent(
        agents, "dormitory_1", fast_mode, preserve_dorm_occupants=preserve
    )

    assert selected == RESIDENTS + ["伊芙利特"]
    assert agents == selected
    if not fill_free:
        assert any(
            call.args == ("CASTER",) for call in solver.profession_filter.call_args_list
        )


def test_single_operator_still_selects_correctly(monkeypatch):
    solver, selected = selection_solver(monkeypatch, residents=[])
    solver.choose_agent(["伊芙利特"], "dormitory_1")
    assert selected == ["伊芙利特"]


def test_already_selected_mixed_roster_still_reorders(monkeypatch):
    current = ["伊芙利特"] + RESIDENTS
    solver, selected = selection_solver(monkeypatch, residents=current)
    solver.choose_agent(RESIDENTS + ["伊芙利特"], "dormitory_1")
    assert selected == RESIDENTS + ["伊芙利特"]
    solver.scan_agent.assert_not_called()


def selection_solver(monkeypatch, residents=None):
    solver = object.__new__(BaseSchedulerSolver)
    current = list(RESIDENTS if residents is None else residents)
    selected = current.copy()
    cards = current.copy()
    profession = "ALL"
    first_scan = True
    roster = RESIDENTS + ["伊芙利特", "杜林", "妮芙", "特米米", "深靛"]
    positions = [(672, 378), (672, 810), (864, 378), (864, 810), (1056, 378)]
    solver.recog = SimpleNamespace(w=1920, h=1080, img=None)
    solver.op_data = SimpleNamespace(
        operators={},
        profession_filter=set(),
        get_current_room=lambda *args: current.copy(),
    )
    solver.last_room = ""
    solver.choose_error = set()
    solver.preserve_resting_crafters = MagicMock()
    solver.get_free_list = MagicMock(return_value=["伊芙利特"])
    solver.detect_arrange_order = MagicMock(return_value=("技能", False))
    solver.get_order = MagicMock(return_value=(False, ("心情", "true")))
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    solver.swipe_noinertia = MagicMock()

    def visible(names):
        return [
            name
            for name in names
            if profession == "ALL" or base_schedule.agent_profession[name] == profession
        ]

    def set_filter(value=None):
        nonlocal profession
        profession = value or "ALL"

    def order(kind, *args):
        if kind == "技能":
            cards[:] = visible(selected + [n for n in roster if n not in selected])

    def tap(point, **kwargs):
        if point[1] == 1026:
            selected.clear()
        else:
            name = cards[positions.index(point)]
            if name in selected:
                selected.remove(name)
            else:
                selected.append(name)

    def scan(names, max_agent_count=None, **kwargs):
        nonlocal first_scan
        # 首屏找不到目标，需要走后续职业筛选分支。
        found = [] if first_scan else visible(names)
        first_scan = False
        if max_agent_count is not None:
            found = found[:max_agent_count]
        for name in found:
            selected.append(name)
            names.remove(name)
        return found, [("杜林", ((0, 0), (1, 1)))] * 2

    solver.profession_filter = MagicMock(side_effect=set_filter)
    solver.switch_arrange_order = MagicMock(side_effect=order)
    solver.tap = MagicMock(side_effect=tap)
    solver.scan_agent = MagicMock(side_effect=scan)
    monkeypatch.setattr(
        base_mixin,
        "operator_list",
        lambda *args, **kwargs: [(name, None) for name in cards],
    )
    return solver, selected
