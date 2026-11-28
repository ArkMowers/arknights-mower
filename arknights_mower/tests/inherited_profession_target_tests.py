import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin, base_schedule  # noqa: E402
from arknights_mower.tests.agent_page_observation_tests import page  # noqa: E402
from arknights_mower.tests.choose_agent_filter_tests import (  # noqa: E402
    selection_solver,
)
from arknights_mower.utils import config  # noqa: E402


@pytest.mark.parametrize("mode", ["high", "low"])
@pytest.mark.parametrize(
    "case",
    [
        "work",
        "mood",
        "miss",
        "late_old_list",
        "arrow_changed",
        "wrong_branch",
        "new_blue",
        "ambiguous_border",
        "partial_card",
        "retry",
        "verification_failure",
        "late_new_page",
        "two_targets",
        "second_gray",
        "second_frame_lost",
        "second_exit",
        "page_exited",
    ],
)
def test_required_profession_precedes_optional_sort(monkeypatch, mode, case):
    monkeypatch.setattr(config.conf, "performance_mode", mode)
    solver, chosen = selection_solver(monkeypatch, residents=[])
    room, role, target = "room_3_1", "ALL", "斯卡蒂"
    plan = (
        [target, "幽灵鲨"]
        if case == "two_targets" or case.startswith("second_")
        else [target]
    )
    inherited = ("心情", False) if case == "mood" else ("工作状态", False)
    desired = ("心情", True)
    sort = inherited
    events = []
    pages = {
        1: page(("芬", "远山", "红豆")),
        2: page(("重岳", "斯卡蒂", "幽灵鲨")),
        3: page(("霜叶", "断罪者", "重岳")),
        4: page(("龙舌兰", "斯卡蒂", "重岳")),
        5: page(("重岳", "龙舌兰", "斯卡蒂")),
    }
    pages[5] = (*pages[5][:-1], (target, ((1700, 488), (1880, 520))))
    if len(plan) > 1:
        pages[4] = page(("龙舌兰", "幽灵鲨", "重岳"))
    frames = {key: np.zeros((1080, 1920, 3), np.uint8) for key in pages}
    for key, frame in frames.items():
        frame[488, 630] = key

    class Recognizer:
        w, h = 1920, 1080
        _img = None

        def update(self):
            self._img = None

        @property
        def img(self):
            if self._img is None:
                if role == "ALL":
                    key = 1
                elif sort == desired:
                    key = 4
                else:
                    key = {"miss": 3, "late_old_list": 1, "partial_card": 5}.get(
                        case, 2
                    )
                    if case == "late_new_page" and events.count(("capture", 2)):
                        key = 3
                self._img = frames[key].view()
                events.append(("capture", key))
            return self._img

    solver.recog = Recognizer()

    def names(img, **kwargs):
        return pages[int(img[488, 630, 0])]

    def set_role(new=None):
        nonlocal role
        role = new or "ALL"
        events.append(("role", role))
        solver.recog.update()
        solver.recog.img

    def change_sort(criterion, _, ascending=False, *, refresh=True):
        nonlocal sort
        sort = (criterion, ascending)
        events.append(("sort", sort))
        solver.recog.update()

    def actual_order(_):
        if case == "arrow_changed" and role == "WARRIOR" and sort == inherited:
            return ("工作状态", True)
        return sort

    def border(img, scope, **_):
        if (
            case == "second_gray"
            and chosen
            and sort == inherited
            and scope == pages[2][2][1]
        ):
            return None
        if int(img[488, 630, 0]) == 2 and scope == pages[2][0][1]:
            if case == "new_blue":
                return True
            if case == "ambiguous_border":
                return None
        return False

    def tap(scope, **_):
        (name,) = [name for name, box in names(solver.recog.img) if box == scope]
        assert name in plan and name not in chosen
        chosen.append(name)
        events.append(("tap", sort))
        solver.recog.update()

    def scan(*args, **kwargs):
        if chosen and sort == inherited:
            if case == "second_frame_lost":
                raise base_mixin.AgentCardObservationNotReady("暂时没有识别到第二名")
            if case == "second_exit":
                raise base_mixin.AgentSelectionPageChanged("已离开选人页")
        return base_mixin.BaseMixin.scan_agent(solver, *args, **kwargs)

    solver.scan_agent = scan
    solver.op_data.profession_filter = set(plan)
    solver.get_order.return_value = (True, desired)
    solver.detect_arrange_order.side_effect = actual_order
    solver.switch_arrange_order.side_effect = change_sort
    solver.profession_filter.side_effect = set_role

    def find(resource):
        if resource == "confirm_blue" and solver.recog.img is not None:
            return ((1609, 990), (1735, 1050))
        if (
            resource == "double_confirm/main"
            and role == "WARRIOR"
            and case == "page_exited"
        ):
            return ((800, 600), (1100, 700))

    solver.find.side_effect = find
    solver.tap.side_effect = tap
    solver._profession_filter_buttons = MagicMock(
        return_value=(("confirm_blue", 1609, 990),)
    )
    solver.verify_agent = MagicMock(return_value=case != "verification_failure")
    solver.wait_for_arranged_agents = MagicMock(return_value=plan)
    solver.reorder_selected_agents = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list", names)
    monkeypatch.setattr(base_schedule, "agent_card_selected", border)
    monkeypatch.setattr(base_mixin, "agent_card_selected", border)
    monkeypatch.setattr(
        base_schedule,
        "branch_filter_state",
        lambda *_: (False, case == "wrong_branch" and sort == inherited),
    )
    solver.recog.img

    def choose():
        solver.choose_agent(
            plan.copy(), room, fresh_room_entry=True, choose_error=int(case == "retry")
        )

    if case == "second_exit":
        with pytest.raises(base_mixin.AgentSelectionPageChanged):
            choose()
        assert chosen == [target]
        solver.verify_agent.assert_not_called()
        return
    if case == "page_exited":
        with pytest.raises(base_mixin.AgentSelectionPageChanged):
            choose()
        assert not chosen and all(event[0] not in ("tap", "sort") for event in events)
        return
    elif case == "verification_failure":
        with pytest.raises(Exception, match="检测到干员选择错误"):
            choose()
    else:
        choose()
    assert chosen == plan
    solver.verify_agent.assert_called()
    first_tap = next(i for i, event in enumerate(events) if event[0] == "tap")
    before_tap = [event for event in events[:first_tap] if event[0] != "capture"]
    if case in (
        "work",
        "mood",
        "verification_failure",
        "two_targets",
        "second_gray",
        "second_frame_lost",
    ) or (mode == "high" and case == "late_new_page"):
        assert before_tap == [("role", "WARRIOR")]
        assert events[first_tap] == ("tap", inherited)
        if case == "two_targets":
            assert [ev for ev in events if ev[0] == "tap"] == [("tap", inherited)] * 2
        elif case.startswith("second_"):
            assert [ev for ev in events if ev[0] == "tap"] == [
                ("tap", inherited),
                ("tap", desired),
            ]
        if mode == "low":
            assert (
                events[:first_tap].count(("capture", 2))
                >= 1 + solver.performance_profile.stable_page_matches
            )
    elif case == "retry":
        assert before_tap == [("sort", desired), ("role", "WARRIOR")]
    elif case == "wrong_branch":
        assert before_tap == [
            ("role", "WARRIOR"),
            ("sort", desired),
            ("role", "WARRIOR"),
        ]
    else:
        assert before_tap == [("role", "WARRIOR"), ("sort", desired)]
        assert events[first_tap] == ("tap", desired)
    solver.swipe_agent_page.assert_not_called()
    if case not in ("verification_failure", "second_gray", "second_frame_lost"):
        solver.swipe_left.assert_not_called()
