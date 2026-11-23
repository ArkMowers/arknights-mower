"""用跑单归档的真实蓝框复现取消未生效后的原班恢复。"""

import copy
import importlib
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures/selection"
# 原图来自 2026-10-29 跑单异常归档，保留 JPEG 原始字节：
# before=14:54:38.391，cancel_missed=14:54:41.097，wrong_roster=14:54:45.909；
# original=14:52:35.881，target_page=14:54:42.653。
ORIGINAL = ["黑键", "能天使", "蕾缪安"]
INSERTED = ["黑键", "但书", "龙舌兰"]
ROOM = "room_1_1"


@pytest.fixture
def selection_modules(monkeypatch):
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", Mock())
    mixin = importlib.import_module("arknights_mower.solvers.base_mixin")
    schedule = importlib.import_module("arknights_mower.solvers.base_schedule")
    return mixin, schedule


def load_frame(stage):
    return np.array(
        Image.open(FIXTURES / f"trade_restore_{stage}_20261029.jpg").convert("RGB")
    )


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("before", INSERTED),
        ("cancel_missed", ["黑键", "龙舌兰"]),
        ("wrong_roster", ["黑键", "龙舌兰", "能天使"]),
        ("original", ORIGINAL),
    ],
)
def test_archive_selected_rosters_use_actual_name_and_blue_border_recognition(
    selection_modules, stage, expected
):
    mixin, _ = selection_modules
    frame = load_frame(stage)
    page = mixin.operator_list(frame)
    states = [(name, mixin.agent_card_selected(frame, scope)) for name, scope in page]
    assert all(state is not None for _, state in states)
    assert [name for name, state in states if state] == expected


@pytest.mark.parametrize("mode", ["xhigh", "high", "medium", "low"])
def test_wrong_roster_archive_reaches_reselection_with_real_page_recognition(
    monkeypatch, selection_modules, mode
):
    mixin, _ = selection_modules
    from arknights_mower.utils import config
    from arknights_mower.utils.recognize import Recognizer

    monkeypatch.setattr(config, "conf", config.Conf(performance_mode=mode))
    device = Mock()
    device.screencap.side_effect = AssertionError("原图回归不能读取真实设备")
    recognizer = Recognizer(
        device, (FIXTURES / "trade_restore_wrong_roster_20261029.jpg").read_bytes()
    )
    # 保持现场错选帧，实际执行姓名、蓝框和页面模板识别；仅替换取帧与等待。
    recognizer.update = Mock()
    solver = mixin.BaseMixin()
    solver.recog = recognizer
    solver.find = recognizer.find
    solver.wait_for_next_observation = Mock()

    assert recognizer.find("confirm_blue") is not None
    for template in (
        "double_confirm/main",
        "arrange_check_in_on",
        "recycle/dashboard",
        "connecting",
    ):
        assert recognizer.find(template) is None
    assert solver.wait_for_arranged_agents(ORIGINAL, ordered=False) is None
    solver.require_agent_selection_page()
    device.screencap.assert_not_called()


def restoration_solver(
    monkeypatch,
    selection_modules,
    mode="high",
    miss_cancel=True,
    *,
    clear_works=True,
    full_selection_wrong=False,
    inherited_order=None,
    show_numbers=True,
):
    mixin, schedule = selection_modules
    from arknights_mower.utils import config
    from arknights_mower.utils.operators import Operators
    from arknights_mower.utils.plan import Plan, PlanConfig
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    monkeypatch.setattr(config, "conf", config.Conf(performance_mode=mode))
    images = {
        stage: load_frame(stage)
        for stage in (
            "before",
            "cancel_missed",
            "wrong_roster",
            "original",
            "target_page",
        )
    }
    pages = {stage: mixin.operator_list(frame) for stage, frame in images.items()}
    name_strips = {}
    for stage in ("before", "original"):
        for name, ((left, top), (right, bottom)) in pages[stage]:
            name_strips[name] = images[stage][top:bottom, left:right].copy()

    numbers = []
    if show_numbers:
        for _, ((left, top), _) in pages["before"][:3]:
            numbers.append(
                images["before"][top - 330 : top - 242, left + 115 : left + 189]
            )

    selected = INSERTED.copy()
    state = {
        "cleared": False,
        "missed": False,
        "page": "first",
        "cards": list(name_strips),
    }
    events = []
    solver = object.__new__(schedule.BaseSchedulerSolver)
    task = SchedulerTask(
        time=datetime(2026, 10, 29, 14, 52, 25),
        task_plan={ROOM: ORIGINAL.copy()},
        task_type=TaskTypes.RUN_ORDER,
    )
    task.run_order_restore_pending = True
    task.run_order_original_roster = copy.deepcopy(task.plan)
    solver.task = task
    solver.last_room = ROOM
    solver.choose_error = set()
    solver.op_data = Operators(
        {"default_plan": Plan({}, PlanConfig("", "", "")), "backup_plans": []}
    )
    solver.op_data.get_current_room = lambda *_: INSERTED.copy()
    solver.op_data.profession_filter = set()
    solver.prepare_dorm_selection = Mock(return_value=[])
    solver._check_group_shift_targets = Mock(return_value=False)
    solver.profession_filter = Mock()
    solver.detect_arrange_order = Mock(return_value=("技能", False))
    solver.get_order = Mock(return_value=(False, ("技能", False)))
    solver.find = Mock(return_value=False)
    solver.recog = SimpleNamespace(w=1920, h=1080)

    def synthetic_feedback():
        # 归档没有本次失败后成功清空、重新选入的画面；只为后续 UI 反馈绘制蓝框，
        # 姓名仍取自原图，继续执行真实姓名分割、匹配和蓝框识别。
        frame = np.full((1080, 1920, 3), 245, dtype=np.uint8)
        if inherited_order:
            criterion, ascending = inherited_order
            x = solver._arrange_order_x(ROOM)[criterion]
            y = 80 if ascending else 70
            frame[y : y + 3, x : x + 5] = (0, 166, 220)
        for index, name in enumerate(state["cards"][:12]):
            left = 631 + index // 2 * 216
            top = 488 + index % 2 * 421
            strip = name_strips[name]
            frame[top : top + 32, left - 1 : left + 190] = 45
            frame[top : top + strip.shape[0], left : left + strip.shape[1]] = strip
            if name in selected:
                if numbers:
                    frame[top - 330 : top - 242, left + 115 : left + 189] = numbers[
                        selected.index(name)
                    ]
                cv2.rectangle(
                    frame,
                    (left - 22, top - 375),
                    (left + 199, top + 44),
                    (0, 180, 230),
                    7,
                )
        return frame

    def refresh():
        if not state["cleared"]:
            if state["page"] == "target":
                stage = "target_page"
            elif selected == INSERTED:
                stage = "before"
            elif selected == ["黑键", "龙舌兰"]:
                stage = "cancel_missed"
            elif selected == ["黑键", "龙舌兰", "能天使"]:
                stage = "wrong_roster"
            else:
                stage = None
            if stage:
                solver.recog.img = images[stage]
                state["cards"] = [name for name, _ in pages[stage]]
                events.append(("archive", stage))
                return
        solver.recog.img = synthetic_feedback()

    def tap(point, **_):
        if not isinstance(point[0], tuple) and point[1] == 1026:
            events.append(("clear",))
            if not clear_works:
                refresh()
                return
            selected.clear()
            state["cleared"] = True
            state["page"] = "first"
            refresh()
            return
        page = mixin.operator_list(solver.recog.img)
        if isinstance(point[0], tuple):
            # 真实点击落在姓名框中心，相邻蓝框可使识别框边缘移动几个像素。
            x, y = ((start + end) // 2 for start, end in zip(*point))
            name = next(
                name
                for name, ((left, top), (right, bottom)) in page
                if left <= x <= right and top <= y <= bottom
            )
        else:
            positions = [(672, 378), (672, 810), (864, 378), (864, 810), (1056, 378)]
            name = page[positions.index(tuple(point))][0]
        if miss_cancel and not state["missed"] and name == "龙舌兰":
            state["missed"] = True
            events.append(("cancel_missed", name))
        elif name in selected:
            selected.remove(name)
            events.append(("cancel", name))
        elif full_selection_wrong and state["cleared"] and name == "蕾缪安":
            selected.append("龙舌兰")
            events.append(("wrong_selection", "龙舌兰"))
        elif len(selected) < 3:
            selected.append(name)
            events.append(("select", name))
        else:
            events.append(("capacity_full", name))
        refresh()

    def sort(criterion, *_, **kwargs):
        events.append(("sort", criterion))
        state["page"] = "first"
        state["cards"] = selected + [
            name for name in name_strips if name not in selected
        ]
        refresh()

    def next_page(*_, **__):
        state["page"] = "target"
        if state["cleared"]:
            state["cards"] = ORIGINAL + [
                name for name in name_strips if name not in ORIGINAL
            ]
        refresh()
        return 1, None

    def first_page(*_, **kwargs):
        state["page"] = "first"
        refresh()
        return (0, None) if kwargs.get("return_page") else 0

    solver.recog.update = Mock(side_effect=refresh)
    solver.sleep = Mock(side_effect=lambda *_: refresh())
    solver.wait_for_next_observation = Mock(side_effect=lambda *_: refresh())
    solver.switch_arrange_order = Mock(side_effect=sort)
    solver.tap = Mock(side_effect=tap)
    solver.swipe_left = Mock(side_effect=first_page)
    solver.swipe_agent_page = Mock(side_effect=next_page)
    refresh()
    return solver, task, selected, state, events


@pytest.mark.parametrize("mode", ["xhigh", "low"])
def test_numbered_full_production_roster_keeps_current_sort(
    monkeypatch, selection_modules, mode
):
    solver, _, selected, _, _ = restoration_solver(monkeypatch, selection_modules, mode)
    solver.choose_agent(INSERTED.copy(), ROOM, fresh_room_entry=True)
    assert selected == INSERTED
    solver.tap.assert_not_called()
    solver.switch_arrange_order.assert_not_called()
    solver.swipe_left.assert_not_called()


def test_numbered_roster_in_other_order_is_reselected(monkeypatch, selection_modules):
    solver, _, selected, _, events = restoration_solver(
        monkeypatch, selection_modules, miss_cancel=False
    )
    target = list(reversed(INSERTED))
    assert not solver.verify_agent(target, ROOM, ordered=False)
    solver.choose_agent(target.copy(), ROOM)
    assert events.count(("clear",)) == 1
    assert selected == target


def test_number_overlay_arrives_after_the_selected_border(
    monkeypatch, selection_modules
):
    solver, _, _, _, _ = restoration_solver(monkeypatch, selection_modules, "xhigh")
    settled = load_frame("before")
    delayed = settled.copy()
    _, ((x, y), _) = selection_modules[0].operator_list(settled)[2]
    delayed[y - 330 : y - 242, x + 115 : x + 189] = 0
    solver.recog.update = Mock(
        side_effect=lambda: setattr(solver.recog, "img", delayed)
    )
    solver.wait_for_next_observation = Mock(
        side_effect=lambda *_: setattr(solver.recog, "img", settled)
    )
    slots = {}
    assert (
        solver.wait_for_arranged_agents(
            INSERTED, ordered=False, visible_only=True, slot_numbers=slots
        )
        == INSERTED
    )
    assert slots == {name: i for i, name in enumerate(INSERTED, 1)}
    solver.tap.assert_not_called()
    solver.wait_for_next_observation.assert_called_once()


@pytest.mark.parametrize("swap_after", ["clear", "first_click"])
@pytest.mark.parametrize("show_numbers", [True, False])
def test_reorder_recovers_changed_layout(
    monkeypatch, selection_modules, swap_after, show_numbers
):
    solver, _, selected, state, events = restoration_solver(
        monkeypatch, selection_modules, miss_cancel=False, show_numbers=show_numbers
    )
    tap = solver.tap.side_effect
    swapped = False

    def move_cards(point, **kwargs):
        nonlocal swapped
        tap(point, **kwargs)
        if not state["cleared"] or swapped:
            return
        if len(selected) == (0 if swap_after == "clear" else 1):
            cards = state["cards"]
            cards[0], cards[1] = cards[1], cards[0]
            swapped = True
            solver.recog.update()

    solver.tap.side_effect = move_cards
    target = list(reversed(INSERTED))
    solver.choose_agent(target.copy(), ROOM)
    assert swapped
    assert selected == target
    first_clicks = [event[1] for event in events if event[0] == "select"][:3]
    if swap_after == "clear":
        assert first_clicks == target
    else:
        assert first_clicks == ["龙舌兰", "黑键", "但书"]
    assert events.count(("clear",)) == (
        1 if swap_after == "clear" and show_numbers else 2
    )


def test_partial_numbered_roster_still_clears_hidden_selections(
    monkeypatch, selection_modules
):
    solver, _, selected, _, events = restoration_solver(
        monkeypatch, selection_modules, miss_cancel=False
    )
    solver.choose_agent(INSERTED[:2], ROOM)
    assert ("clear",) in events
    assert selected == INSERTED[:2]


@pytest.mark.parametrize("mode", ["xhigh", "low"])
@pytest.mark.parametrize("stale_frames", [0, 2])
def test_one_misplaced_operator_moves_to_last_slot_without_clearing(
    monkeypatch, selection_modules, mode, stale_frames
):
    solver, _, selected, _, events = restoration_solver(
        monkeypatch,
        selection_modules,
        mode,
        miss_cancel=False,
        inherited_order=("技能", False),
    )
    target = [INSERTED[0], INSERTED[2], INSERTED[1]]
    before = solver.recog.img
    capture = solver.recog.update.side_effect
    pending = stale_frames

    def refresh(*_):
        nonlocal pending
        if len(selected) == 2 and pending:
            pending -= 1
            solver.recog.img = before
        else:
            capture()

    solver.recog.update.side_effect = refresh
    solver.wait_for_next_observation.side_effect = refresh
    solver.choose_agent(target, ROOM, fresh_room_entry=True)
    assert pending == 0
    assert selected == target
    assert [e for e in events if e[0] in ("clear", "cancel", "select", "sort")] == [
        ("cancel", "但书"),
        ("select", "但书"),
    ]


def test_two_numbered_workers_fill_observed_two_slot_facility(
    monkeypatch, selection_modules
):
    solver, _, selected, state, events = restoration_solver(
        monkeypatch, selection_modules, inherited_order=("技能", False)
    )
    target = INSERTED[:2]
    selected[:] = target
    state["cleared"] = True
    solver.op_data.get_current_room = lambda *_: target.copy()
    solver.choose_agent(target, ROOM, fresh_room_entry=True, two_slot_room=True)
    assert selected == target
    assert not any(e[0] in ("clear", "cancel", "select", "sort") for e in events)


def test_deselects_the_named_resident_when_entry_order_differs_from_cache(
    monkeypatch, selection_modules
):
    solver, _, selected, _, events = restoration_solver(
        monkeypatch,
        selection_modules,
        miss_cancel=False,
        inherited_order=("技能", False),
    )
    solver.op_data.get_current_room = lambda *_: list(reversed(INSERTED))
    solver.find.side_effect = lambda name, **_: (
        ((1724, 990), (1813, 1041)) if name == "confirm_blue" else None
    )
    target = [*INSERTED[:2], ORIGINAL[1]]
    solver.choose_agent(target, ROOM, fresh_room_entry=True)
    assert selected == target
    assert ("cancel", INSERTED[0]) not in events
    assert ("clear",) not in events


@pytest.mark.parametrize("mode", ["xhigh", "low"])
def test_dropped_final_card_input_repairs_only_the_empty_slot(
    monkeypatch, selection_modules, mode
):
    solver, _, selected, _, events = restoration_solver(
        monkeypatch,
        selection_modules,
        mode,
        miss_cancel=False,
        inherited_order=("技能", False),
    )
    target = [INSERTED[0], INSERTED[2], INSERTED[1]]
    selected[:] = target[:-1]
    solver.op_data.get_current_room = lambda *_: target[:-1]
    solver.recog.update()
    tap = solver.tap.side_effect

    def drop_first_input(point, **kwargs):
        if not any(e[0] == "dropped" for e in events):
            name = next(
                name
                for name, scope in selection_modules[0].operator_list(solver.recog.img)
                if scope == point
            )
            assert name == target[-1]
            events.append(("dropped", name))
            return
        tap(point, **kwargs)

    solver.tap.side_effect = drop_first_input
    solver.choose_agent(target, ROOM, fresh_room_entry=True)
    assert selected == target
    assert ("clear",) not in events
    assert [e for e in events if e[0] in ("dropped", "select", "cancel")] == [
        ("dropped", target[-1]),
        ("select", target[-1]),
    ]


@pytest.mark.parametrize("mode", ["xhigh", "high", "medium", "low"])
@pytest.mark.parametrize("miss_cancel", [False, True])
def test_restore_original_roster_after_real_frame_cancellation_feedback(
    monkeypatch, selection_modules, mode, miss_cancel
):
    solver, task, selected, state, events = restoration_solver(
        monkeypatch, selection_modules, mode, miss_cancel
    )

    solver.choose_agent(ORIGINAL.copy(), ROOM)

    assert selected == ORIGINAL
    assert task.plan == task.run_order_original_roster == {ROOM: ORIGINAL}
    assert task.time == datetime(2026, 10, 29, 14, 52, 25)
    assert state["missed"] is miss_cancel
    if miss_cancel:
        assert ("archive", "cancel_missed") in events
        assert ("archive", "wrong_roster") in events
        assert ("capacity_full", "蕾缪安") in events


def test_failed_full_selection_does_not_repeat_same_page_fallback(
    monkeypatch, selection_modules
):
    solver, task, selected, _, events = restoration_solver(
        monkeypatch, selection_modules, full_selection_wrong=True
    )

    with pytest.raises(Exception, match="检测到干员选择错误"):
        solver.choose_agent(ORIGINAL.copy(), ROOM)

    assert events.count(("clear",)) == 1
    assert ("wrong_selection", "龙舌兰") in events
    assert selected == ["黑键", "能天使", "龙舌兰"]
    assert task.plan == task.run_order_original_roster == {ROOM: ORIGINAL}
    assert task.time == datetime(2026, 10, 29, 14, 52, 25)


def test_failed_clear_does_not_select_more_operators(monkeypatch, selection_modules):
    mixin, _ = selection_modules
    solver, task, selected, _, events = restoration_solver(
        monkeypatch, selection_modules, clear_works=False
    )

    with pytest.raises(mixin.AgentSelectionNotReady, match="清空"):
        solver.choose_agent(ORIGINAL.copy(), ROOM)

    assert events.count(("clear",)) == 1
    clear_index = events.index(("clear",))
    assert all(event[0] == "archive" for event in events[clear_index + 1 :])
    assert selected == ["黑键", "龙舌兰", "能天使"]
    assert task.plan == task.run_order_original_roster == {ROOM: ORIGINAL}
    assert task.time == datetime(2026, 10, 29, 14, 52, 25)


@pytest.mark.parametrize("abort", ["page_exit", "cancel"])
def test_page_exit_and_cancellation_prevent_fallback_inputs(
    monkeypatch, selection_modules, abort
):
    mixin, _ = selection_modules
    from arknights_mower.utils.csleep import MowerExit

    solver, task, selected, _, events = restoration_solver(
        monkeypatch, selection_modules
    )

    def find(name, *_, **__):
        if name == "double_confirm/main":
            events.append(("abort", abort))
            if abort == "cancel":
                raise MowerExit
            return True
        return False

    solver.find.side_effect = find
    error = MowerExit if abort == "cancel" else mixin.AgentSelectionPageChanged
    with pytest.raises(error):
        solver.choose_agent(ORIGINAL.copy(), ROOM)

    assert events.count(("abort", abort)) == 1
    assert ("clear",) not in events
    assert events[-1] == ("abort", abort)
    assert selected == ["黑键", "龙舌兰", "能天使"]
    assert task.plan == task.run_order_original_roster == {ROOM: ORIGINAL}
    assert task.time == datetime(2026, 10, 29, 14, 52, 25)
