"""执行真实选人流程，模拟职业筛选后的可见卡片及点击结果。"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin, base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils.operators import Operators  # noqa: E402

pytestmark = pytest.mark.usefixtures("low_frame_rate")

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


def test_unexpected_dorm_residents_rebuild_selection_before_canceling_cards(
    monkeypatch,
):
    actual = ["Lancet-2", "澄闪", "玛露西尔", "菲亚梅塔", "槐琥"]
    cached = ["冰酿", "闪灵", "桃金娘", "菲亚梅塔", "槐琥"]
    expected = cached[:4] + ["歌蕾蒂娅"]
    solver, selected = selection_solver(monkeypatch, residents=actual)
    solver.op_data.get_current_room = lambda *args: cached.copy()

    solver.choose_agent(expected.copy(), "dormitory_1")

    assert selected == expected
    # 不能按旧缓存先点第五张，更不能保留 Lancet-2；首次点击须清空选择。
    assert solver.tap.call_args_list[0].args[0] == (729.6, 1026.0)


def test_dorm_fast_selection_cancels_using_observed_card_order(monkeypatch):
    actual = ["杜林"] + RESIDENTS
    solver, selected = selection_solver(monkeypatch, residents=actual)
    solver.op_data.get_current_room = lambda *args: RESIDENTS + ["杜林"]

    solver.choose_agent(RESIDENTS + ["伊芙利特"], "dormitory_1")

    assert selected == RESIDENTS + ["伊芙利特"]
    assert solver.tap.call_args_list[0].args[0] == (672.0, 378.0)


@pytest.mark.parametrize("enabled", [False, True])
def test_free_search_switches_directly_to_all_and_keeps_final_roster(
    monkeypatch, enabled
):
    monkeypatch.setattr(base_mixin.config.conf, "low_frame_rate_mode", enabled)
    solver, selected = selection_solver(monkeypatch, residents=[])
    agents = ["爱丽丝", "Free"]
    solver.choose_agent(agents, "dormitory_1")
    assert selected == agents == ["爱丽丝", "伊芙利特"]
    filters = [c.args for c in solver.profession_filter.call_args_list]
    assert ("CASTER",) in filters
    # 选完术师直接切 ALL；不能先复位回术师，再重复切一次 ALL。
    assert all(c.args[1] != "CASTER" for c in solver.swipe_left.call_args_list)


def test_already_selected_mixed_roster_still_reorders(monkeypatch):
    current = ["伊芙利特"] + RESIDENTS
    solver, selected = selection_solver(monkeypatch, residents=current)
    solver.choose_agent(RESIDENTS + ["伊芙利特"], "dormitory_1")
    assert selected == RESIDENTS + ["伊芙利特"]
    solver.scan_agent.assert_not_called()


def test_matching_card_names_still_clear_and_reselect(monkeypatch):
    solver, selected = selection_solver(monkeypatch, residents=RESIDENTS)
    solver.choose_agent(RESIDENTS.copy(), "dormitory_1")
    assert selected == RESIDENTS
    assert solver.tap.call_count == len(RESIDENTS) + 1
    solver.scan_agent.assert_not_called()
    assert solver.switch_arrange_order.call_count == 2
    solver.swipe_left.assert_not_called()


def test_fast_click_strategy_keeps_zero_interval_reorder(
    monkeypatch,
):
    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", "xhigh")
    solver, selected = selection_solver(monkeypatch, residents=RESIDENTS)
    solver.recog.img = selected_card_frame()

    solver.choose_agent(RESIDENTS.copy(), "dormitory_1")

    assert selected == RESIDENTS
    assert solver.tap.call_count == len(RESIDENTS) + 1
    assert solver.tap.call_args_list[0].kwargs["interval"] == 0.5
    assert all(call.kwargs["interval"] == 0 for call in solver.tap.call_args_list[1:])
    assert solver.switch_arrange_order.call_count == 2


def test_high_mode_checks_full_roster_after_all_reorder_clicks(monkeypatch):
    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", "high")
    solver, selected = selection_solver(
        monkeypatch, residents=list(reversed(RESIDENTS))
    )
    solver.recog.img = selected_card_frame()
    confirmations = []
    tap_counts = []

    def confirm(prefix, **kwargs):
        confirmations.append(prefix.copy())
        tap_counts.append(solver.tap.call_count)
        return list(reversed(RESIDENTS)) if len(confirmations) <= 2 else prefix

    solver.wait_for_arranged_agents = MagicMock(side_effect=confirm)
    solver.choose_agent(RESIDENTS.copy(), "dormitory_1")

    assert selected == RESIDENTS
    assert len(confirmations) == 3
    assert all(sorted(names) == sorted(RESIDENTS) for names in confirmations)
    assert tap_counts == [0, 0, len(RESIDENTS) + 1]
    assert all(
        call.kwargs.get("ordered") is False
        for call in solver.wait_for_arranged_agents.call_args_list
    )
    assert solver.tap.call_args_list[0].kwargs["interval"] == 0.3
    assert all(call.kwargs["interval"] == 0.1 for call in solver.tap.call_args_list[1:])


def test_high_mode_rejects_wrong_final_roster_after_reorder(monkeypatch):
    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", "high")
    solver, _ = selection_solver(monkeypatch, residents=list(reversed(RESIDENTS)))
    solver.recog.img = selected_card_frame()
    solver.wait_for_arranged_agents = MagicMock(
        side_effect=[list(reversed(RESIDENTS)), list(reversed(RESIDENTS))]
    )
    solver.verify_agent = MagicMock(return_value=False)
    solver.tap_confirm = MagicMock()

    with pytest.raises(Exception, match="检测到干员选择错误"):
        solver.choose_agent(RESIDENTS.copy(), "dormitory_1")

    assert solver.tap.call_count == len(RESIDENTS) + 1
    assert solver.verify_agent.call_count == 2
    solver.verify_agent.assert_called_with(
        RESIDENTS, "dormitory_1", observation=None, ordered=False
    )
    solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize("phase", ["exists", "verify"])
def test_page_change_bypasses_filter_reset_in_reorder_and_final_verification(
    monkeypatch, phase
):
    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", "high")
    solver, _ = selection_solver(monkeypatch, residents=RESIDENTS)
    solver.recog.img = selected_card_frame()
    solver.tap_confirm = MagicMock()
    observations = 0

    def observe(expected, **kwargs):
        nonlocal observations
        observations += 1
        stop = 2 if phase == "exists" else 3
        if observations == stop:
            raise base_mixin.AgentSelectionPageChanged("页面退出")
        return expected.copy()

    solver.wait_for_arranged_agents = MagicMock(side_effect=observe)
    with pytest.raises(base_mixin.AgentSelectionPageChanged):
        solver.choose_agent(RESIDENTS.copy(), "dormitory_1")
    assert solver.tap.call_count == (0 if phase == "exists" else len(RESIDENTS) + 1)
    assert solver.profession_filter.call_count == 2
    assert all(not call.args for call in solver.profession_filter.call_args_list)
    solver.swipe_left.assert_not_called()
    solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize(
    ("mode", "low_frame_rate", "poll_interval", "click_interval"),
    [
        ("high", False, 0.1, 0.1),
        ("medium", True, 0.5, 0.2),
        ("low", True, 0.75, 0.2),
    ],
)
def test_non_ultra_rebuilds_order_without_selection_number_proof(
    monkeypatch, mode, low_frame_rate, poll_interval, click_interval
):
    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", mode)
    monkeypatch.setattr(base_mixin.config.conf, "low_frame_rate_mode", low_frame_rate)
    monkeypatch.setattr(
        base_mixin.config.conf, "selection_poll_interval", poll_interval
    )
    solver, selected = selection_solver(monkeypatch, residents=RESIDENTS)
    solver.recog.img = selected_card_frame()
    solver.wait_for_arranged_agents = MagicMock(
        side_effect=lambda expected, **kwargs: [
            name for name in RESIDENTS if name in selected
        ]
    )

    solver.choose_agent(RESIDENTS.copy(), "dormitory_1")

    assert selected == RESIDENTS
    assert solver.tap.call_count == len(RESIDENTS) + 1
    assert solver.tap.call_args_list[0].kwargs["interval"] == (
        0.3 if mode == "high" else 0.5
    )
    assert all(
        call.kwargs["interval"] == click_interval
        for call in solver.tap.call_args_list[1:]
    )
    assert solver.switch_arrange_order.call_count == 2


def test_reorder_accepts_page_order_different_from_click_order(monkeypatch):
    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", "high")
    target = ["菲亚梅塔", "波登可", "砾", "苏苏洛", "绮良"]
    page_order = ["菲亚梅塔", "波登可", "砾", "绮良", "苏苏洛"]
    solver, selected = selection_solver(monkeypatch, residents=page_order)
    solver.recog.img = selected_card_frame()

    def observe(expected, *, ordered=True, **kwargs):
        actual = [name for name in page_order if name in selected]
        matches = actual == expected if ordered else sorted(actual) == sorted(expected)
        return actual if matches else None

    solver.wait_for_arranged_agents = MagicMock(side_effect=observe)
    solver.choose_agent(target.copy(), "dormitory_1")

    assert selected == target
    assert solver.tap.call_count == len(target) + 1
    assert all(
        call.kwargs.get("ordered") is False
        for call in solver.wait_for_arranged_agents.call_args_list
    )


def selected_card_frame():
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    for i in range(len(RESIDENTS)):
        right = 818 + (i // 2) * 215
        top = 113 + (i % 2) * 421
        cv2.rectangle(
            frame, (right - 210, top), (right + 10, top + 419), (0, 180, 230), 7
        )
    return frame


def test_reorder_does_not_trust_cached_selection_order(monkeypatch):
    solver, selected = selection_solver(monkeypatch, residents=RESIDENTS)
    original_order = solver.switch_arrange_order.side_effect
    first = True

    def order(kind, *args):
        nonlocal first
        if kind == "技能" and first:
            first = False
            # 游戏实际卡片顺序与进入房间时缓存的顺序不同。
            selected.reverse()
        original_order(kind, *args)

    solver.switch_arrange_order.side_effect = order
    solver.choose_agent(RESIDENTS.copy(), "dormitory_1")
    assert selected == RESIDENTS


def test_resting_operator_is_scanned_without_skipping_pages(monkeypatch):
    solver, selected = selection_solver(monkeypatch, residents=[])
    solver.op_data.operators["伊芙利特"] = SimpleNamespace(
        mood=10, upper_limit=24, room="dormitory_1", is_resting=lambda: True
    )
    solver.choose_agent(["伊芙利特"], "dormitory_1")
    assert selected == ["伊芙利特"]
    solver.swipe_noinertia.assert_not_called()
    solver.swipe_agent_page.assert_not_called()


@pytest.mark.parametrize(
    "mode,tail_wait", [("high", 0.5), ("xhigh", 1), ("medium", None), ("low", None)]
)
def test_resting_operator_tail_search_retains_wait_before_scan(
    monkeypatch, mode, tail_wait
):
    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", mode)
    solver, selected = selection_solver(monkeypatch, residents=[])
    solver.op_data.operators["伊芙利特"] = SimpleNamespace(
        mood=10, upper_limit=24, room="dormitory_1", is_resting=lambda: True
    )
    scan = solver.scan_agent.side_effect

    def scan_after_swipe(*args, **kwargs):
        if solver.swipe_noinertia.call_count:
            solver.sleep.assert_called_once_with(tail_wait)
        return scan(*args, **kwargs)

    solver.scan_agent.side_effect = scan_after_swipe
    solver.choose_agent(["伊芙利特"], "dormitory_1")

    assert selected == ["伊芙利特"]
    if tail_wait is None:
        solver.swipe_noinertia.assert_not_called()
    else:
        assert solver.swipe_noinertia.call_count == 3
        assert all(
            call.kwargs["interval"] == 0
            for call in solver.swipe_noinertia.call_args_list
        )
        solver.sleep.assert_called_once_with(tail_wait)


@pytest.mark.parametrize("mode", ["high", "xhigh"])
@pytest.mark.parametrize("target_page", [1, 2, None], ids=["middle", "tail", "absent"])
@pytest.mark.parametrize("tail_companion", [False, True])
def test_resting_operator_tail_miss_searches_from_first_page(
    monkeypatch, mode, target_page, tail_companion
):
    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", mode)
    solver, selected = selection_solver(monkeypatch, residents=[])
    solver.op_data.operators["伊芙利特"] = SimpleNamespace(
        mood=10, upper_limit=24, room="dormitory_1", is_resting=lambda: True
    )
    state = {"page": 0}
    observed_pages = []
    scan = solver.scan_agent.side_effect

    def scan_page(names, **kwargs):
        page_index = state["page"]
        observed_pages.append(page_index)
        found, _ = scan(
            [
                name
                for name in names
                if (name == "伊芙利特" and page_index == target_page)
                or (name == "特米米" and page_index == 2)
            ],
            **kwargs,
        )
        for name in found:
            names.remove(name)
        return found, [
            (["杜林", "妮芙", "特米米"][page_index], ((630, 488), (818, 520)))
        ]

    def rewind(*args, **kwargs):
        state["page"] = 0
        return (0, None) if kwargs.get("return_page") else 0

    def next_page(*args, **kwargs):
        state["page"] = min(state["page"] + 1, 2)
        return (1, None)

    solver.scan_agent.side_effect = scan_page
    solver.swipe_left.side_effect = rewind
    solver.swipe_agent_page.side_effect = next_page
    solver.swipe_noinertia.side_effect = lambda *args, **kwargs: state.update(page=2)

    expected = ["伊芙利特"] + (["特米米"] if tail_companion else [])
    agents = expected.copy()
    if target_page is None:
        with pytest.raises(base_mixin.AgentSelectionNotReady, match="末尾"):
            solver.choose_agent(agents, "dormitory_1")
        assert selected == (["特米米"] if tail_companion else [])
    else:
        solver.choose_agent(agents, "dormitory_1")
        assert selected == agents == expected

    assert solver.swipe_noinertia.call_count == 3
    solver.sleep.assert_called_once_with(0.5 if mode == "high" else 1)
    if target_page == 2:
        assert observed_pages == [0, 2]
        solver.swipe_agent_page.assert_not_called()
    else:
        assert observed_pages[:4] == [0, 2, 0, 1]
        assert any(call.args[0] > 0 for call in solver.swipe_left.call_args_list)
        assert len(observed_pages) <= 6


@pytest.mark.parametrize("targets", [[], ["伊芙利特"], ["Free"]])
def test_high_clear_wait_applies_to_empty_fixed_and_free_selection(
    monkeypatch, targets
):
    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", "high")
    solver, selected = selection_solver(monkeypatch, residents=[])

    solver.choose_agent(targets.copy(), "dormitory_1", fast_mode=False)

    assert selected == (["伊芙利特"] if targets else [])
    clears = [
        call for call in solver.tap.call_args_list if call.args[0] == (729.6, 1026.0)
    ]
    assert clears
    assert all(call.kwargs["interval"] == 0.3 for call in clears)


def selection_solver(monkeypatch, residents=None):
    solver = object.__new__(BaseSchedulerSolver)
    solver.task = None
    solver.wait_for_cleared_selection = MagicMock()
    current = list(RESIDENTS if residents is None else residents)
    selected = current.copy()
    cards = current.copy()
    profession = "ALL"
    first_scan = True
    roster = RESIDENTS + ["伊芙利特", "杜林", "妮芙", "特米米", "深靛"]
    positions = [(672, 378), (672, 810), (864, 378), (864, 810), (1056, 378)]
    solver.recog = SimpleNamespace(w=1920, h=1080, img=None, update=MagicMock())
    solver.op_data = SimpleNamespace(
        operators={},
        dorm_mood_estimates={},
        plan={},
        config=SimpleNamespace(
            free_blacklist=[],
            ope_resting_priority=[],
            resting_standby=[],
            free_room_exclusions=[],
        ),
        profession_filter=set(),
        get_current_room=lambda *args: current.copy(),
        rest_mood_complete=lambda *args, **kwargs: False,
        is_dynamic_dorm_position=lambda *args, **kwargs: False,
        is_dorm_replacement_for_slot=lambda *args, **kwargs: False,
        get_current_operator=lambda *args, **kwargs: None,
        dorm_capacity_allows=lambda *args, **kwargs: True,
    )
    solver.op_data.add = lambda op: solver.op_data.operators.setdefault(op.name, op)
    solver.op_data.arrangement_group_transitions = lambda plan, **kwargs: (
        Operators.arrangement_group_transitions(solver.op_data, plan, **kwargs)
    )
    solver.last_room = ""
    solver.choose_error = set()
    solver.preserve_resting_crafters = MagicMock()
    solver.get_free_list = MagicMock(return_value=["伊芙利特"])
    solver.detect_arrange_order = MagicMock(return_value=("技能", False))
    solver.get_order = MagicMock(return_value=(False, ("心情", "true")))
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock(side_effect=lambda *args, **kwargs: solver.recog.update())
    solver.swipe_noinertia = MagicMock()
    # 本组模拟筛选和选择结果；真实翻页与延迟帧在 agent_page_search_tests 中验证。
    solver.swipe_agent_page = MagicMock(
        side_effect=lambda *args, **kwargs: (
            (1, None) if kwargs.get("return_page") else 1
        )
    )
    solver.swipe_left = MagicMock(
        side_effect=lambda *args, **kwargs: (
            (0, None) if kwargs.get("return_page") else 0
        )
    )

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
        lambda *args, **kwargs: [
            (
                name,
                (
                    (630 + (i // 2) * 215, 488 + (i % 2) * 421),
                    (818 + (i // 2) * 215, 520 + (i % 2) * 421),
                ),
            )
            for i, name in enumerate(cards)
        ],
    )
    return solver, selected


@pytest.mark.parametrize("mode", ["xhigh", "high", "medium", "low"])
def test_unconfirmed_initial_residents_use_full_selection(monkeypatch, mode):
    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", mode)
    solver, selected = selection_solver(monkeypatch, residents=RESIDENTS)
    original = solver.wait_for_arranged_agents
    first = True

    def read(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            raise base_mixin.AgentSelectionNotReady("实读比缓存多一人")
        return original(*args, **kwargs)

    solver.wait_for_arranged_agents = MagicMock(side_effect=read)
    target = RESIDENTS[:2] + ["伊芙利特"]
    solver.choose_agent(target.copy(), "dormitory_1")
    assert selected == target
    assert solver.tap.call_args_list[0].args[0] == (729.6, 1026.0)
