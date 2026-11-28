from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.agent_page_observation_tests import page
from arknights_mower.tests.choose_agent_filter_tests import selection_solver
from arknights_mower.utils import config


@pytest.mark.parametrize("mode", ["high", "low"])
@pytest.mark.parametrize(
    "case",
    [
        "hit",
        "miss",
        "other_facility",
        "other_arrow",
        "other_station",
        "changed_blue",
        "unclear",
        "other_tail",
        "middle_of_first",
        "middle_of_second",
        "no_overlap",
        "double_swipe",
        "unknown_station",
        "out_of_reach",
        "reset",
        "stale_after",
    ],
)
def test_one_observed_skill_swipe_precedes_branch(monkeypatch, mode, case):
    monkeypatch.setattr(config.conf, "performance_mode", mode)
    solver, selected = selection_solver(monkeypatch, residents=[])
    first = (
        "结城理",
        "弑君者",
        "食铁兽",
        "引星棘刺",
        "砾",
        "杏仁",
        "钼铅",
        "裁度",
        "槐琥",
        "多萝西",
    )
    second = (
        "槐琥",
        "多萝西",
        "温蒂",
        "贝娜",
        "阿斯卡纶",
        "缄默德克萨斯",
        "麒麟R夜刀",
        "艾拉",
        "新约能天使",
        "琳琅诗怀雅",
    )
    target = {
        "out_of_reach": "琳琅诗怀雅",
        "middle_of_first": "贝娜",
        "middle_of_second": "艾拉",
    }.get(case, "阿斯卡纶")
    role, stage, position, branch = "ALL", 1, 0, False
    actions = []
    images = [np.zeros((1080, 1920, 3), dtype=np.uint8) for _ in range(2)]
    images[1][40:67, 1610:1692] = 255
    solver.recog._img = images[0]
    solver.recog.img = images[0]
    solver._profession_search_pages = {}
    solver.op_data.profession_filter = {"推进之王"}
    solver.get_order.side_effect = lambda *_: (
        False,
        ("技能", case == "other_arrow" and stage == 2),
    )
    solver.detect_arrange_order.side_effect = lambda *_: (
        "技能",
        case == "other_arrow" and stage == 2,
    )
    solver._profession_filter_buttons = MagicMock(
        return_value=(("confirm_blue", 1609, 990),)
    )
    solver.read_screen = MagicMock(
        return_value=None if case == "unknown_station" else "进驻状态"
    )
    solver.verify_agent = MagicMock(return_value=True)
    solver.find.side_effect = lambda resource: (
        ((1609, 990), (1710, 1050)) if resource == "confirm_blue" else None
    )
    monkeypatch.setattr(base_schedule, "agent_branch", {target: "伏击客"})
    monkeypatch.setattr(
        base_schedule, "branch_filter_state", lambda *_: (False, branch)
    )
    monkeypatch.setattr(
        base_schedule,
        "selection_title_matches",
        lambda _, title: (
            title
            == ("trade" if stage == 2 and case == "other_facility" else "manufacture")
        ),
    )
    monkeypatch.setattr(
        base_schedule,
        "agent_card_selected",
        lambda _, scope: (
            (None if case == "unclear" else True)
            if stage == 2
            and case in ("changed_blue", "unclear")
            and scope == page(first)[0][1]
            else False
        ),
    )
    monkeypatch.setattr(solver, "_ranked_first_page_order", lambda *_a, **_kw: None)

    def show():
        img = images[int(stage == 2 and case == "other_station")]
        solver.recog._img = solver.recog.img = img
        if role == "ALL":
            return page(("夜烟", "杜林", "芬"))
        if branch:
            return page((target, "伊桑", "狮蝎"))
        if not position:
            if stage == 2 and case == "middle_of_first":
                return page(("伊桑", "狮蝎", "歌蕾蒂娅", *first[:7]))
            if stage == 2 and case == "middle_of_second":
                return page((*first[:7], *second[2:5]))
            return (
                page((*first[:-3], *reversed(first[-3:])))
                if stage == 2 and case == "other_tail"
                else page(first)
            )
        if stage == 2 and case == "stale_after":
            return page(first)
        if stage == 2 and case == "miss":
            return page(tuple(n for n in second if n != target))
        if stage == 1 and case == "no_overlap":
            return page(("歌蕾蒂娅", "绮良", *second[2:]))
        return page(second)

    def set_profession(label=None):
        nonlocal role, position, branch
        role, position, branch = label or "ALL", 0, False
        show()

    def narrow(*_):
        nonlocal branch
        actions.append("分支")
        branch = stage == 2
        return branch

    def swipe(*_a, **_kw):
        nonlocal position
        position = 1
        actions.append("滑动")
        moved = 2 if stage == 1 and case == "double_swipe" else 1
        visible = show()
        return moved, solver.observe_agent_page(
            visible if mode == "low" else (), full_scan=False
        )

    def scan(remaining, **_):
        visible = show()
        found = [n for n, _ in visible if n in remaining]
        for n in found:
            actions.append(n)
            selected.append(n)
            remaining.remove(n)
        if mode == "low" and found:
            solver.recog._img = None
        return found, visible

    solver.current_search_page = MagicMock(return_value=None)
    solver.profession_filter.side_effect = set_profession
    solver.scan_agent.side_effect = scan
    solver.swipe_agent_page.side_effect = swipe
    monkeypatch.setattr(base_schedule, "select_visible_branch", narrow)
    solver.choose_agent([target], "room_3_1", fresh_room_entry=True)
    assert actions == ["分支", "滑动", target]
    selected.clear()
    actions.clear()
    if case == "reset":
        solver._profession_search_pages = {}
    stage = 2
    set_profession()
    solver.choose_agent([target], "room_1_2", fresh_room_entry=True)
    if case == "hit":
        assert actions == ["滑动", target]
    elif case in ("miss", "stale_after"):
        assert actions == ["滑动", "分支", target]
    else:
        assert actions == ["分支", target]
    assert selected == [target]
    assert solver.verify_agent.call_count == 2
    assert solver.read_screen.call_count <= 1


def test_observed_prefix_order_and_bounded_batch_history(monkeypatch):
    solver, _ = selection_solver(monkeypatch, residents=[])
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    solver.recog.img = solver.recog._img = img
    solver._profession_search_pages = {}
    solver.get_order.return_value = False, ("技能", False)
    solver.detect_arrange_order.return_value = "技能", False
    solver._profession_filter_buttons = MagicMock(
        return_value=(("confirm_blue", 1609, 990),)
    )
    solver.read_screen = MagicMock(return_value="进驻状态")
    monkeypatch.setattr(
        base_schedule,
        "selection_title_matches",
        lambda _, label: label == "manufacture",
    )
    monkeypatch.setattr(base_schedule, "branch_filter_state", lambda *_: (False, False))
    pinned = {"芬", "杜林"}
    rows = page(("芬", "杜林", "食铁兽", "槐琥", "砾", "杏仁"))
    monkeypatch.setattr(
        base_schedule,
        "agent_card_selected",
        lambda _, scope: scope in (rows[0][1], rows[1][1]),
    )

    def capture(names):
        return solver._skill_profession_page(
            "room_3_1", "SPECIAL", ("技能", False), pinned, page(names), first=True
        )

    prefix = capture([n for n, _ in rows])
    reversed_prefix = capture(("杜林", "芬", "食铁兽", "槐琥", "砾", "杏仁"))
    assert prefix and reversed_prefix and prefix[0] != reversed_prefix[0]
    assert not solver._skill_profession_page(
        "dormitory_4", "SPECIAL", ("技能", False), pinned, rows, first=True
    )
    monkeypatch.setattr(base_schedule, "agent_card_selected", lambda *_: False)
    after = page(("砾", "杏仁", "温蒂", "贝娜", "阿斯卡纶", "艾拉"))
    solver._remember_skill_successor(prefix, "room_3_1", after)
    pairs = solver._profession_search_pages
    key = (*prefix[0], prefix[1][-3:])
    assert key in pairs and (*reversed_prefix[0], reversed_prefix[1][-3:]) not in pairs
    for index in range(24):
        img[35, 1600 + index] = 255
        monkeypatch.setattr(
            base_schedule,
            "agent_card_selected",
            lambda _, scope: scope in (rows[0][1], rows[1][1]),
        )
        snapshot = capture([n for n, _ in rows])
        monkeypatch.setattr(base_schedule, "agent_card_selected", lambda *_: False)
        solver._remember_skill_successor(snapshot, "room_3_1", after)
    assert len(pairs) == 24 and key not in pairs
