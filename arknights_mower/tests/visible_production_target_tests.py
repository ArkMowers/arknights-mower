"""生产房可见目标先选人，未翻页且完整名单正确时不再复位。"""

import sys
from functools import cached_property
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin, base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.tests.agent_page_observation_tests import (  # noqa: E402
    page,
)
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig  # noqa: E402
from arknights_mower.utils.solver import BaseSolver  # noqa: E402

pytestmark = pytest.mark.usefixtures("low_frame_rate")


@pytest.fixture(autouse=True)
def empty_branch_data(monkeypatch):
    # 职业选择同样支持未提供分支的旧资源。
    monkeypatch.setattr(base_schedule, "agent_branch", {})


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


@pytest.mark.parametrize("mode", ["high", "low"])
@pytest.mark.parametrize(
    ("rank_sort", "case"),
    [
        (by, case)
        for by in ("技能", "效率")
        for case in (
            "hit",
            "late",
            "stale",
            "unreadable",
            "no_data",
            "outside",
            "restricted",
            "unknown_blue",
            "middle_page",
            "pinned",
            "tied_first",
            "broken_tie",
            "existing_sort",
            "inherited_gray",
            "inherited_filter_unreadable",
            "inherited_filter_exit",
            "reverse_refreshed",
            "reverse_unclear_border",
            "emergency_fresh_entry",
            "final_mismatch",
            "trust",
        )
    ]
    + [
        ("技能", "cross_hit"),
        ("技能", "cross_miss"),
        ("技能", "cross_no_product"),
        ("技能", "cross_straddle"),
        ("效率", "inherited_efficiency"),
    ],
)
def test_manufacturing_rank_search_recovers_by_visible_name(
    monkeypatch, mode, case, rank_sort
):
    from arknights_mower.tests.choose_agent_filter_tests import selection_solver
    from arknights_mower.utils import selection_skill_rank

    monkeypatch.setattr(config.conf, "performance_mode", mode)
    retained = ["芬"] if case == "pinned" else []
    solver, selected = selection_solver(monkeypatch, residents=retained)
    room, target = "room_3_1", "炎熔"
    direction = case == "existing_sort" or case.startswith("inherited_")
    criterion = "信赖值" if case == "trust" else rank_sort
    role = "ALL"
    branched = False
    old_reads = 0
    local_sorts, inputs = [], []
    reverse_captures = []
    pages = {
        1: page(("芬", "杜林", "斑点", "香草")),
        2: page(("史都华德", "远山", "夜烟", "杜林")),
        3: page(("炎熔", "史都华德", "夜烟", "杜林")),
        4: page(("杜林", "史都华德", "远山", "夜烟")),
        5: page(("炎熔", "远山")),
    }
    if retained:
        for index in range(2, 6):
            pages[index] = page((*retained, *(name for name, _ in pages[index])))

    class Recognizer:
        w, h = 1920, 1080
        _img = None

        @cached_property
        def frames(self):
            result = {}
            for index in pages:
                arr = np.zeros((self.h, self.w, 3), dtype=np.uint8)
                arr[488, 630] = index
                result[index] = arr
            return result

        def update(self):
            self._img = None

        @property
        def img(self):
            nonlocal old_reads
            if self._img is None:
                if role == "ALL":
                    index = 1
                elif branched:
                    index = 5
                elif not direction or old_reads:
                    old_reads = max(0, old_reads - 1)
                    index = 2
                else:
                    index = 4 if case in ("stale", "cross_miss") else 3
                if role == "CASTER" and direction and not branched:
                    reverse_captures.append(index)
                self._img = self.frames[index].view()
            return self._img

    def names(img, **_):
        return pages[int(img[488, 630, 0])]

    def sort(kind, _, ascending=False, *, refresh=True):
        nonlocal criterion, direction, old_reads
        if not refresh:
            local_sorts.append((kind, ascending))
            if case == "late" and ascending:
                old_reads = 3
            if case == "unreadable" and ascending:
                raise base_mixin.AgentSelectionNotReady("箭头仍未稳定")
        criterion, direction = kind, ascending
        solver.recog.update()

    def set_profession(label=None):
        nonlocal role, branched
        role, branched = label or "ALL", False
        solver.recog.update()
        if label == "CASTER" and direction and case.startswith("inherited_filter_"):
            if case == "inherited_filter_exit":
                raise base_mixin.AgentSelectionPageChanged("已离开选人页")
            raise base_mixin.AgentSelectionNotReady("职业高亮尚未确认")

    def select_branch(*_):
        nonlocal branched
        inputs.append("分支")
        branched = True
        solver.recog.update()
        return True

    def tap(scope, **_):
        hits = [n for n, b in names(solver.recog.img) if b == scope]
        assert hits == [target]
        if case == "late":
            stable_frames = 1 + solver.performance_profile.stable_page_matches
            assert reverse_captures == [2] * 3 + [3] * stable_frames
        if case in ("reverse_refreshed", "reverse_unclear_border"):
            assert not direction and branched
        selected.append(target)
        inputs.append(target)
        solver.recog.update()

    solver.recog = Recognizer()
    if case == "emergency_fresh_entry":
        solver.task = SimpleNamespace(
            emergency_staffing=True, type=None, plan={room: [target]}
        )
        solver.clear_agent_selection = MagicMock()
    if case == "reverse_refreshed":
        observe_moods = solver.observe_agent_moods

        def refresh_during_mood_check(*args, **kwargs):
            result = observe_moods(*args, **kwargs)
            if role == "CASTER" and direction and not branched:
                solver.recog.update()
            return result

        solver.observe_agent_moods = refresh_during_mood_check
    solver.op_data.profession_filter = {target}
    solver.scan_agent = base_mixin.BaseMixin.scan_agent.__get__(solver)
    configured_sort = "技能" if case == "inherited_efficiency" else rank_sort
    solver.get_order.return_value = (True, (configured_sort, False))
    solver.find.side_effect = lambda name: (
        ((1609, 990), (1735, 1050)) if name == "confirm_blue" else None
    )
    solver.profession_filter.side_effect = set_profession
    solver.detect_arrange_order.side_effect = lambda _: (criterion, direction)
    solver.switch_arrange_order.side_effect = sort
    solver.read_screen = MagicMock(
        return_value="未进驻" if case == "restricted" else "进驻状态"
    )
    solver.tap.side_effect = tap
    solver.sleep.side_effect = lambda *_: solver.recog.update()
    solver._profession_filter_buttons = MagicMock(
        return_value=(("confirm_blue", 1609, 990),)
    )
    planned = retained + [target]
    solver.wait_for_arranged_agents = MagicMock(return_value=planned)
    solver.reorder_selected_agents = MagicMock()
    solver.verify_agent = MagicMock(return_value=case != "final_mismatch")
    solver.tap_confirm = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list", names)
    monkeypatch.setattr(
        base_mixin,
        "agent_card_selected",
        lambda *_a, **_kw: (
            None
            if case in ("inherited_gray", "reverse_unclear_border")
            and direction
            and role == "CASTER"
            else False
        ),
    )
    monkeypatch.setattr(
        base_schedule,
        "agent_card_selected",
        lambda img, scope: (
            None
            if case == "unknown_blue"
            else any(name in retained and box == scope for name, box in names(img))
        ),
    )
    monkeypatch.setattr(
        base_schedule,
        "selection_title_matches",
        lambda _, label: label == "manufacture",
    )
    monkeypatch.setattr(
        base_schedule, "branch_filter_state", lambda *args: (False, False)
    )
    monkeypatch.setattr(base_schedule, "agent_branch", {target: "扩散术师"})
    monkeypatch.setattr(base_schedule, "select_visible_branch", select_branch)
    ranks = (
        None
        if case == "no_data"
        else {False: (14, 15), True: (1, 6 if case == "outside" else 2)}
    )

    def forecast(_, __, name, ___, **kwargs):
        if name == target:
            if case.startswith("cross_"):
                return {False: (14, 15), True: (8, 12)}
            return ranks
        if case in ("tied_first", "broken_tie"):
            same_group = name == "史都华德" or (name == "远山" and case == "tied_first")
            return {False: (1, 2) if same_group else (3, 3), True: (14, 15)}
        return {False: (8, 8) if case == "middle_page" else (1, 1), True: (15, 15)}

    predict = MagicMock(side_effect=forecast)
    rank_function = (
        "selection_skill_rank" if rank_sort == "技能" else "selection_efficiency_rank"
    )
    monkeypatch.setattr(selection_skill_rank, rank_function, predict)
    product = "exp3" if rank_sort == "效率" else None
    if case.startswith("cross_"):
        product = None if case == "cross_no_product" else "exp3"
        eff = MagicMock(
            return_value={
                False: (11, 12),
                True: (2, 5 if case == "cross_straddle" else 3),
            }
        )
        monkeypatch.setattr(selection_skill_rank, "selection_efficiency_rank", eff)

    def choose():
        return solver.choose_agent(
            planned.copy(), room, fresh_room_entry=True, selection_product=product
        )

    if case == "inherited_filter_exit":
        with pytest.raises(base_mixin.AgentSelectionPageChanged):
            choose()
        assert not local_sorts and not inputs
        return
    if case == "final_mismatch":
        with pytest.raises(Exception, match="检测到干员选择错误"):
            choose()
            solver.tap_confirm(room, {})
        solver.tap_confirm.assert_not_called()
    else:
        choose()
    assert selected == planned
    solver.verify_agent.assert_called()
    assert ("分支" in inputs) == (
        case
        in {
            "stale",
            "unreadable",
            "no_data",
            "outside",
            "restricted",
            "unknown_blue",
            "middle_page",
            "broken_tie",
            "inherited_gray",
            "inherited_filter_unreadable",
            "reverse_refreshed",
            "reverse_unclear_border",
            "emergency_fresh_entry",
            "cross_miss",
            "cross_no_product",
            "cross_straddle",
        }
    )
    if case.startswith("cross_"):
        if case == "cross_no_product":
            eff.assert_not_called()
        else:
            eff.assert_called_once_with(
                "MANUFACTURE", "CASTER", target, set(), product="exp3"
            )
        assert (
            local_sorts
            == {
                "cross_hit": [("效率", True)],
                "cross_miss": [("效率", True), ("技能", False)],
                "cross_straddle": [],
                "cross_no_product": [],
            }[case]
        )
    elif case in ("existing_sort", "inherited_efficiency"):
        assert not local_sorts
    elif case in ("inherited_gray", "inherited_filter_unreadable"):
        assert local_sorts == [(rank_sort, False)]
    elif case == "trust":
        assert local_sorts == [(rank_sort, False), (rank_sort, True)]
    elif case in ("stale", "unreadable", "reverse_refreshed", "reverse_unclear_border"):
        assert local_sorts == [(rank_sort, True), (rank_sort, False)]
    elif "分支" in inputs:
        assert not local_sorts
    else:
        assert local_sorts == [(rank_sort, True)]
    if case == "emergency_fresh_entry":
        solver.clear_agent_selection.assert_called_once_with(room)
        predict.assert_not_called()
    else:
        kwargs = {"product": product} if rank_sort == "效率" else {}
        predict.assert_any_call(
            "MANUFACTURE", "CASTER", target, set(retained), **kwargs
        )
    if case in ("no_data", "outside", "middle_page", "unknown_blue", "broken_tie"):
        solver.read_screen.assert_not_called()


def production_solver(
    monkeypatch, *, target_visible=True, final_missing=False, final_problem=None
):
    solver = object.__new__(BaseSchedulerSolver)
    selected = ["鸿雪", "黑键"]
    state = {"phase": "initial", "sorts": 0, "reorder_cards": None}
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
        if state["reorder_cards"] is not None:
            return state["reorder_cards"]
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
    solver.op_data = Operators(
        {"default_plan": Plan({}, PlanConfig("", "", "")), "backup_plans": []}
    )
    solver.op_data.get_current_room = lambda *args: ["鸿雪", "黑键"]
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
            if label == "SUPPORT" and state["phase"] == "sorted":
                state["phase"] = "left"
            elif label == "ALL" and state["phase"] == "final":
                state["phase"] = "final_reset"
        solver.recog.update()

    solver.profession_filter = MagicMock(side_effect=reset_filter)
    solver._close_profession_filter = MagicMock(side_effect=solver.recog.update)

    def sort(*args, **kwargs):
        state["reorder_cards"] = None
        state["sorts"] += 1
        state["phase"] = "sorted" if state["sorts"] == 1 else "final"
        events.append(("sort", state["sorts"]))
        solver.recog.update()

    def tap(location, **kwargs):
        if isinstance(location[0], (int, float)):
            if location[1] == 1026:
                # 清空不改变卡片位置，重新点击排序时才刷新已选置顶。
                state["reorder_cards"] = tuple(solver.recog.img)
                selected.clear()
                events.append(("clear",))
            elif state["reorder_cards"] is not None:
                index = [(672, 378), (672, 810)].index(location)
                name = state["reorder_cards"][index][0]
                selected.append(name)
                events.append(("reselect", name))
            else:
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
    monkeypatch.setattr(
        base_mixin,
        "agent_card_selected",
        lambda img, scope, **kwargs: (
            next(name for name, box in img if box == scope) in selected
        ),
    )
    monkeypatch.setattr(
        base_mixin,
        "selection_slot",
        lambda img, scope: next(
            (selected.index(n) + 1 for n, box in img if box == scope and n in selected),
            None,
        ),
    )
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
    assert solver.switch_arrange_order.call_count == 3
    assert events.count(("clear",)) == 1
    assert ("sort", 2) in events[selection + 1 :]
    solver.tap_confirm.assert_called_once()


def test_missing_target_switches_directly_to_its_profession(
    monkeypatch,
):
    solver, selected, events = production_solver(monkeypatch, target_visible=False)
    solver.choose_agent(["鸿雪", "但书"], "room_2_1")
    first_reset = next(i for i, event in enumerate(events) if event[0] == "filter")
    selection = next(
        i for i, event in enumerate(events) if event[:2] == ("select", "但书")
    )
    assert first_reset < selection
    assert events[first_reset][:3] == ("filter", "SUPPORT", "sorted")
    solver.swipe_noinertia.assert_not_called()
    assert events[selection][2][0][0] == 630
    assert selected == ["鸿雪", "但书"]


def test_missing_final_target_prevents_confirmation_even_after_visible_click(
    monkeypatch,
):
    solver, selected, events = production_solver(monkeypatch, final_missing=True)
    with pytest.raises(base_mixin.AgentSelectionNotReady, match="可识别干员列不足"):
        solver.choose_agent(["鸿雪", "但书"], "room_2_1")
        solver.tap_confirm("room_2_1", {})
    assert any(event[:2] == ("select", "但书") for event in events)
    assert any(event[:3] == ("filter", "ALL", "final") for event in events)
    assert selected == ["鸿雪"]
    assert events.count(("clear",)) == 1
    assert not any(event[0] == "reselect" for event in events)
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
def test_filter_search_does_not_reset_before_switching_profession(
    monkeypatch, room, targets, first_found
):
    solver = object.__new__(BaseSchedulerSolver)
    solver.recog = SimpleNamespace(w=1920, h=1080, img=None, update=MagicMock())
    solver.op_data = Operators(
        {"default_plan": Plan({}, PlanConfig("", "", "")), "backup_plans": []}
    )
    solver.op_data.get_current_room = lambda *_: []
    solver.last_room = ""
    solver.choose_error = set()
    solver.preserve_resting_crafters = MagicMock()
    solver.detect_arrange_order = MagicMock(return_value=("工作状态", False))
    solver.profession_filter = MagicMock()
    solver.get_order = MagicMock(return_value=(False, ("心情", "true")))
    solver.switch_arrange_order = MagicMock()
    solver.sleep = MagicMock()

    def initial_scan(remaining, **kwargs):
        found = first_found if solver.scan_agent.call_count == 1 else []
        for name in found:
            remaining.remove(name)
        return found, page()

    solver.scan_agent = MagicMock(side_effect=initial_scan)
    solver.swipe_left = MagicMock()
    solver.swipe_agent_page = MagicMock(side_effect=MowerExit)
    with pytest.raises(MowerExit):
        solver.choose_agent(targets, room)
    assert solver.profession_filter.call_args.args == ("SUPPORT",)
    solver.swipe_left.assert_not_called()
    solver.swipe_agent_page.assert_called_once()


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

    def stop_after_sort(*args, **kwargs):
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


@pytest.mark.parametrize(
    "filtered_page, targets, roles",
    [
        (["但书", "波登可"], ["但书", "伺夜", "波登可"], ["SUPPORT", "PIONEER"]),
        ([], ["但书"], ["SUPPORT", "ALL"]),
        ([], ["阿米娅"], []),
        ([], ["杜宾"], []),
    ],
)
def test_production_search_groups_professions_and_recovers_in_all(
    monkeypatch, filtered_page, targets, roles
):
    from arknights_mower.tests.choose_agent_filter_tests import selection_solver

    solver, selected = selection_solver(monkeypatch, residents=[])
    solver.get_order = MagicMock(return_value=(False, ("技能", False)))
    solver.detect_arrange_order = MagicMock(return_value=("技能", False))
    solver.op_data.profession_filter = set() if targets == ["杜宾"] else {"推进之王"}
    actual_filter = "ALL"
    current_page = 0
    entered = []
    pages = {
        "ALL": [
            ["杜林", "芬"],
            ["孑", "流明"],
            ["罗比菈塔", "夜莺"],
            ["黑键", "冰酿"],
            ["红豆", "空弦"],
            targets,
        ],
        "SUPPORT": [filtered_page],
        "PIONEER": [["伺夜"]],
    }
    scans = []

    def switch(profession=None):
        nonlocal actual_filter, current_page
        actual_filter = profession or "ALL"
        current_page = 0
        if profession:
            entered.append(profession)

    def scan(remaining, **_):
        names = pages[actual_filter][current_page]
        found = [name for name in names if name in remaining]
        scans.append((actual_filter, current_page, found.copy()))
        for name in found:
            selected.append(name)
            remaining.remove(name)
        return found, page(tuple(names) or ("杜林", "芬"))

    def swipe(*_, **kwargs):
        nonlocal current_page
        if current_page + 1 == len(pages[actual_filter]):
            raise base_mixin.AgentPageNotAdvanced("列表已到末尾")
        current_page += 1
        return (1, None)

    solver.profession_filter.side_effect = switch
    solver.scan_agent.side_effect = scan
    solver.swipe_agent_page.side_effect = swipe
    solver._close_profession_filter = MagicMock()
    solver.choose_agent(targets.copy(), "room_2_1", fresh_room_entry=True)

    assert selected == targets
    if roles == ["SUPPORT", "ALL"]:
        solver._close_profession_filter.assert_called_once_with()
    else:
        solver._close_profession_filter.assert_not_called()
    assert entered == roles + (["ALL"] if roles and roles[-1] != "ALL" else [])
    if filtered_page:
        assert ("SUPPORT", 0, ["但书", "波登可"]) in scans
        solver.swipe_agent_page.assert_not_called()
    else:
        assert ("ALL", 5, targets) in scans
        assert solver.swipe_agent_page.call_count == (6 if roles else 5)


@pytest.mark.parametrize("confirm_x,limited", [(1609, True), (1724, False)])
def test_visible_entry_target_preserves_sort_and_sidebar(
    monkeypatch, confirm_x, limited
):
    from arknights_mower.tests.choose_agent_filter_tests import selection_solver

    solver, selected = selection_solver(monkeypatch, residents=[])
    solver.find.side_effect = lambda name: (
        ((confirm_x, 1000), (confirm_x + 50, 1050)) if name == "confirm_blue" else None
    )
    solver._close_profession_filter = MagicMock()

    def scan(remaining, *, full_scan, exclude_sidebar, **_):
        assert full_scan is not limited
        assert exclude_sidebar is limited
        selected.append(remaining.pop())
        return selected.copy(), page(tuple(selected))

    solver.scan_agent.side_effect = scan
    solver.choose_agent(["但书"], "room_2_1", fresh_room_entry=True)

    assert selected == ["但书"]
    solver.scan_agent.assert_called_once()
    solver.detect_arrange_order.assert_called_once_with("room_2_1")
    solver._close_profession_filter.assert_not_called()
    solver.profession_filter.assert_not_called()


@pytest.mark.parametrize(
    "confirm_x,all_active,fresh,keep_open",
    [
        (1609, True, True, True),
        (1609, False, True, False),
        (1724, True, True, False),
        (1609, True, False, False),
    ],
)
def test_right_facility_reuses_observed_all_sidebar(
    monkeypatch, confirm_x, all_active, fresh, keep_open
):
    from arknights_mower.tests.choose_agent_filter_tests import selection_solver

    solver, _ = selection_solver(monkeypatch, residents=[])
    solver.find.side_effect = lambda name: (
        ((confirm_x, 1000), (confirm_x + 50, 1050)) if name == "confirm_blue" else None
    )
    solver._profession_highlighted = MagicMock(return_value=all_active)
    solver.scan_agent.side_effect = MowerExit
    with pytest.raises(MowerExit):
        solver.choose_agent(["温蒂"], "meeting", fresh_room_entry=fresh)
    assert solver.scan_agent.call_args.kwargs["exclude_sidebar"] is keep_open
    if keep_open:
        solver.profession_filter.assert_not_called()
    else:
        solver.profession_filter.assert_called_once_with()


@pytest.mark.parametrize("mode", ["low", "high"])
def test_direct_scan_never_taps_name_under_open_sidebar(monkeypatch, mode):
    from arknights_mower.tests.agent_page_search_tests import reader

    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", mode)
    cards = page(("杜林", "芬")) + (
        ("但书", ((1600, 488), (1790, 520))),
        ("伺夜", ((1601, 909), (1791, 941))),
    )
    solver = reader(monkeypatch, [cards] * 8)
    remaining = ["但书", "伺夜"]
    selected, _ = solver.scan_agent(remaining, full_scan=False, exclude_sidebar=True)

    assert selected == ["但书"]
    assert remaining == ["伺夜"]
    assert [call.args[0] for call in solver.tap.call_args_list] == [cards[2][1]]


def test_closing_sidebar_searches_last_full_column_before_broadening(monkeypatch):
    from arknights_mower.tests.choose_agent_filter_tests import selection_solver

    solver, selected = selection_solver(monkeypatch, residents=[])
    solver.op_data.profession_filter = {"推进之王"}
    solver.get_order.return_value = False, ("技能", False)
    solver.detect_arrange_order.return_value = "技能", False
    solver._close_profession_filter = MagicMock()
    solver.swipe_agent_page.side_effect = base_mixin.AgentPageNotAdvanced(
        "列表已到末尾"
    )

    def scan(remaining, *, full_scan, exclude_sidebar, **_):
        if solver._close_profession_filter.called:
            assert full_scan and not exclude_sidebar
            selected.append(remaining.pop())
            return selected.copy(), page(selected)
        return [], page(("杜林", "芬"))

    solver.scan_agent.side_effect = scan
    solver.choose_agent(["多萝西"], "room_3_1", fresh_room_entry=True)
    assert selected == ["多萝西"]
    solver._close_profession_filter.assert_called_once()


@pytest.mark.parametrize(
    "room,branch_result",
    [
        ("room_2_1", "found"),
        ("room_2_1", "empty"),
        ("room_2_1", "unreadable"),
        ("room_2_1", "unstable"),
        ("room_2_1", "retry"),
        ("central", "empty"),
        ("meeting", "found"),
        ("factory", "all"),
        ("contact", "unreadable"),
        ("recycle", "unstable"),
        ("train", "unstable"),
        ("factory", "closed_unreadable"),
        ("contact", "swipe_unreadable"),
        ("dormitory_1", "found"),
        ("dormitory_1", "resting"),
        ("dormitory_2", "all"),
        ("dormitory_3", "retry"),
        ("dormitory_4", "disabled"),
    ],
)
def test_branch_selection_preserves_order_and_recovers_to_profession(
    monkeypatch, room, branch_result
):
    from arknights_mower.tests.choose_agent_filter_tests import selection_solver

    solver, selected = selection_solver(monkeypatch, residents=[])
    solver.op_data.profession_filter = (
        set() if branch_result == "disabled" else {"推进之王"}
    )
    solver.get_order = MagicMock(return_value=(False, ("技能", False)))
    solver.detect_arrange_order = MagicMock(return_value=("技能", False))
    solver._close_profession_filter = MagicMock()
    confirm = "confirm_train" if room == "train" else "confirm_blue"
    solver.find.side_effect = lambda name: (
        ((1609, 970), (1720, 1050)) if name == confirm else None
    )
    solver._profession_highlighted = MagicMock(return_value=True)
    branches = {"但书": "凝滞师", "真理": "凝滞师", "初雪": "削弱者"}
    monkeypatch.setattr(base_schedule, "agent_branch", branches)
    multiple = room == "room_2_1" and branch_result == "found"
    wanted = ["但书", "初雪", "真理"] if multiple else ["但书"]
    active_filter = "ALL"
    current_page = 0
    pages = {
        "ALL": [["杜林", "芬"], ["但书"]],
        "SUPPORT": [["梅尔", "地灵"], ["铃兰" if branch_result == "all" else "但书"]],
        "凝滞师": [["但书"], ["真理"]] if branch_result == "found" else [["铃兰"]],
        "削弱者": [["初雪"]],
    }
    events = []
    if branch_result == "resting":
        monkeypatch.setattr(config.conf, "performance_mode", "high")
        solver.op_data.operators["真理"] = SimpleNamespace(
            mood=10, upper_limit=24, room="dormitory_1", is_resting=lambda: True
        )
        wanted.append("真理")
        pages["凝滞师"] = [["但书"], ["真理"]]
        pages["SUPPORT"][1] = ["真理"]

        def jump_to_end(*args, **kwargs):
            nonlocal current_page
            assert active_filter == "SUPPORT"
            events.append(("tail", active_filter))
            current_page = 1

        solver.swipe_noinertia.side_effect = jump_to_end

    def filter_profession(profession=None):
        nonlocal active_filter, current_page
        events.append(("profession", profession))
        active_filter = profession or "ALL"
        current_page = 0

    def filter_branch(owner, profession, branch):
        nonlocal active_filter, current_page
        assert owner is solver and profession == "SUPPORT"
        assert active_filter == "SUPPORT" and current_page == 0
        events.append(("branch", branch))
        active_filter = branch
        current_page = 0
        return branch_result != "unreadable"

    def scan(remaining, **options):
        if active_filter == "凝滞师" and (
            branch_result == "unstable"
            or (branch_result == "closed_unreadable" and not options["exclude_sidebar"])
        ):
            raise base_mixin.AgentCardObservationNotReady("卡片未稳定")
        names = pages[active_filter][current_page]
        found = [name for name in names if name in remaining]
        for name in found:
            events.append(("selected", name))
            remaining.remove(name)
            selected.append(name)
        return found, page(tuple(names))

    def swipe(*_, **kwargs):
        nonlocal current_page
        if branch_result == "swipe_unreadable" and active_filter == "凝滞师":
            raise base_mixin.AgentCardObservationNotReady("单槽设施翻页后的卡片未稳定")
        if current_page + 1 == len(pages[active_filter]):
            raise base_mixin.AgentPageNotAdvanced("列表已到末尾")
        current_page += 1
        return 1, None

    solver.scan_agent.side_effect = scan
    solver.swipe_agent_page.side_effect = swipe
    solver.profession_filter.side_effect = filter_profession
    monkeypatch.setattr(base_schedule, "select_visible_branch", filter_branch)

    solver.choose_agent(
        wanted.copy(),
        room,
        fresh_room_entry=True,
        choose_error=int(branch_result == "retry"),
    )

    assert selected == wanted
    if branch_result in ("retry", "disabled"):
        assert not any(kind == "branch" for kind, _ in events)
        return
    assert events.count(("branch", "凝滞师")) == 1
    if multiple:
        assert events.index(("selected", "真理")) < events.index(("branch", "削弱者"))
        assert events.count(("branch", "削弱者")) == 1
    elif branch_result == "resting":
        assert events.index(("selected", "但书")) < events.index(("tail", "SUPPORT"))
        assert events.index(("tail", "SUPPORT")) < events.index(("selected", "真理"))
    elif branch_result != "found":
        attempt = events.index(("branch", "凝滞师"))
        assert events[attempt + 1 : attempt + 3] == [
            ("profession", "ALL"),
            ("profession", "SUPPORT"),
        ]
        assert events.index(("selected", "但书")) > attempt + 2
        if branch_result == "all":
            assert events[attempt + 3 : attempt + 5] == [
                ("profession", "ALL"),
                ("selected", "但书"),
            ]


@pytest.mark.parametrize("mode", ["high", "low"])
def test_single_profession_page_in_previous_room_does_not_precede_branch(
    monkeypatch, mode
):
    from arknights_mower.tests.choose_agent_filter_tests import selection_solver

    solver, selected = selection_solver(monkeypatch, residents=[])
    monkeypatch.setattr(config.conf, "performance_mode", mode)
    monkeypatch.setattr(base_schedule, "agent_branch", {"多萝西": "陷阱师"})
    solver.op_data.profession_filter = {"推进之王"}
    solver.get_order.return_value = False, ("技能", False)
    solver.detect_arrange_order.return_value = "技能", False
    solver._profession_search_pages = {}
    saved = [
        "引星棘刺",
        "结城理",
        "弑君者",
        "食铁兽",
        "砾",
        "杏仁",
        "钼铅",
        "裁度",
        "槐琥",
        "多萝西",
    ]
    current = [
        "结城理",
        "娜斯提",
        "弑君者",
        "食铁兽",
        "引星棘刺",
        "砾",
        "杏仁",
        "钼铅",
        "裁度",
        "槐琥",
    ]
    pages = {"ALL": ["酒神", "红豆"], "SPECIAL": saved}
    route = []
    view = "ALL"

    def change(label=None):
        nonlocal view
        view = label or "ALL"

    def scan(remaining, **kwargs):
        names = pages[view]
        found = [name for name in names if name in remaining]
        for name in found:
            selected.append(name)
            remaining.remove(name)
        return found, page(names)

    def narrow(*args):
        route.append("陷阱师")
        pages["SPECIAL"] = ["多萝西"]
        return True

    solver.profession_filter.side_effect = change
    solver.scan_agent.side_effect = scan
    solver.swipe_agent_page.side_effect = AssertionError("只读过一页，不能提前翻页")
    monkeypatch.setattr(base_schedule, "select_visible_branch", narrow)
    solver.choose_agent(["砾"], "room_2_2")
    assert selected == ["砾"]
    selected.clear()
    pages["SPECIAL"] = current
    solver.choose_agent(["多萝西"], "room_3_1")
    assert selected == ["多萝西"]
    assert route == ["陷阱师"]


@pytest.mark.parametrize("mode", ["high", "low"])
def test_unknown_rescue_mood_aborts_filtered_selection(monkeypatch, mode):
    from arknights_mower.tests.choose_agent_filter_tests import selection_solver

    solver, _ = selection_solver(monkeypatch, residents=[])
    monkeypatch.setattr(base_mixin.config.conf, "performance_mode", mode)
    target = "但书"
    room = "room_2_1"
    solver.task = SimpleNamespace(emergency_staffing=True, plan={room: [target]})
    solver.op_data.plan = {room: []}
    solver.op_data.profession_filter = {"推进之王"}
    solver.prepare_dorm_selection = MagicMock(return_value=[])
    solver._check_group_shift_targets = MagicMock(return_value=False)
    solver.clear_agent_selection = MagicMock()
    solver.scan_agent = base_mixin.BaseMixin.scan_agent.__get__(solver)
    solver.get_order.return_value = (False, ("技能", False))
    solver.find.side_effect = lambda name: (
        ((1609, 970), (1720, 1050)) if name == "confirm_blue" else None
    )
    active = "ALL"

    def switch(profession=None):
        nonlocal active
        assert profession != "ALL", "救急准入拒绝后不能继续操作筛选"
        active = profession or "ALL"
        solver.recog.update()

    solver.profession_filter.side_effect = switch
    solver.recog = LivePageRecognizer(
        lambda: page((target, "地灵") if active == "SUPPORT" else ("杜林", "芬")), []
    )
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **_: tuple(img))
    monkeypatch.setattr(base_mixin, "estimate_agent_mood", lambda *_: None)
    solver.tap_confirm = MagicMock()

    with pytest.raises(
        base_mixin.AgentSelectionNotReady, match="自动救急候选 但书 心情读数未知或无效"
    ):
        solver.choose_agent([target], room)

    assert [call.args for call in solver.profession_filter.call_args_list] == [
        (),
        ("SUPPORT",),
    ]
    solver.tap.assert_not_called()
    solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize(
    "starting_order, expected_search_orders",
    [
        (("信赖值", True), [("技能", True), ("心情", True)]),
        (("心情", True), [("技能", True), ("心情", True)]),
        (("技能", True), [("心情", True)]),
    ],
)
def test_mixed_trade_staff_follow_configured_skill_and_mood_search(
    monkeypatch, starting_order, expected_search_orders
):
    from arknights_mower.tests.choose_agent_filter_tests import selection_solver
    from arknights_mower.utils.operators import Operator

    solver, selected = selection_solver(monkeypatch, residents=[])
    target = ["但书", "斯卡蒂", "龙舌兰"]
    defaults = Operators(
        {"default_plan": Plan({}, PlanConfig("", "", "")), "backup_plans": []}
    )
    for name in target:
        defaults.add(Operator(name, ""))
    solver.op_data.operators.update(defaults.operators)
    solver.op_data.profession_filter = defaults.profession_filter
    solver.get_order = BaseSchedulerSolver.get_order.__get__(solver)
    current_sort = starting_order
    current_filter = "ALL"
    search_sorts = []
    filters = []
    scans = []
    original_sort = solver.switch_arrange_order.side_effect
    original_filter = solver.profession_filter.side_effect

    def sort(criterion, room, ascending=False, *, refresh=True):
        nonlocal current_sort
        current_sort = (criterion, ascending)
        if not refresh:
            search_sorts.append(current_sort)
        original_sort(criterion, room, ascending)

    def filter_profession(profession=None):
        nonlocal current_filter
        current_filter = profession or "ALL"
        filters.append(current_filter)
        original_filter(profession)

    def scan(remaining, **kwargs):
        visible = []
        if current_filter == "ALL" and current_sort == ("技能", True):
            visible = ["但书", "龙舌兰"]
        elif current_filter == "WARRIOR" and current_sort == ("心情", True):
            visible = ["斯卡蒂"]
        found = [name for name in visible if name in remaining]
        scans.append((current_filter, current_sort, found))
        for name in found:
            remaining.remove(name)
            selected.append(name)
        return found, page(tuple(visible) or ("杜林", "芬"))

    solver.switch_arrange_order.side_effect = sort
    solver.detect_arrange_order.side_effect = lambda room: current_sort
    solver.profession_filter.side_effect = filter_profession
    solver.scan_agent.side_effect = scan
    solver.swipe_agent_page.side_effect = AssertionError("目标在对应排序或职业的首屏")

    solver.choose_agent(target.copy(), "room_2_1", fresh_room_entry=True)

    assert selected == target
    assert search_sorts == expected_search_orders
    assert ("ALL", ("技能", True), ["但书", "龙舌兰"]) in scans
    assert ("WARRIOR", ("心情", True), ["斯卡蒂"]) in scans
    assert filters == ["WARRIOR", "ALL"]
