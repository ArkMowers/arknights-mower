"""单岗位设施通过已选卡片取消暂选，不点击不存在的清空按钮。"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from arknights_mower.utils import config

ROOM = "room_1_1"


@pytest.fixture
def selection_module(monkeypatch):
    import importlib

    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", Mock())
    return importlib.import_module("arknights_mower.solvers.base_mixin")


@pytest.mark.parametrize("cleared", [False, True])
def test_captured_single_slot_selection_border(selection_module, cleared):
    from arknights_mower.utils.character_recognize import operator_list

    state = "cleared" if cleared else "selected"
    image = np.array(
        Image.open(
            Path(__file__).parent
            / f"fixtures/selection/trade_single_{state}_20261021.jpg"
        )
    )
    page = operator_list(image)
    assert page[0][0] == "但书"
    selected = [
        name
        for name, scope in page
        if selection_module.agent_card_selected(image, scope)
    ]
    assert selected == ([] if cleared else ["但书"])
    assert all(
        selection_module.agent_card_selected(image, scope) is not None
        for _, scope in page
    )


@pytest.mark.parametrize(
    "room,targets,initial,capacity,initial_profession,expected_events",
    [
        pytest.param(
            room,
            targets,
            initial,
            1,
            profession,
            events,
            id=f"{room}-{case}",
        )
        for room in (ROOM, "contact", "factory")
        for targets, initial, profession, events, case in (
            (
                ["图耶"],
                ["但书"],
                "ALL",
                [("cancel", "但书"), "cleared", ("select", "图耶")],
                "replace-selected",
            ),
            ([""], ["但书"], "ALL", [("cancel", "但书"), "cleared"], "leave-empty"),
            (
                [""],
                ["但书"],
                "MEDIC",
                [("cancel", "但书"), "cleared"],
                "clear-hidden-selected-card",
            ),
            (["图耶"], [], "ALL", [("select", "图耶")], "select-from-empty"),
            ([""], [], "ALL", [], "already-empty"),
        )
    ]
    + [
        pytest.param(
            ROOM,
            ["图耶"],
            ["但书"],
            3,
            "ALL",
            ["clear", "cleared", ("select", "图耶")],
            id="multiple-slots-clear-button",
        )
    ],
)
@pytest.mark.parametrize("mode", ["xhigh", "high", "medium", "low"])
def test_single_slot_retry_cancels_actual_card_before_selecting_target(
    monkeypatch,
    selection_module,
    mode,
    room,
    targets,
    initial,
    capacity,
    initial_profession,
    expected_events,
):
    from arknights_mower.data import agent_profession
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    monkeypatch.setattr(config, "conf", config.Conf(performance_mode=mode))
    selected = initial.copy()
    cards = ["但书", "图耶", "暗索", "史都华德"]
    frames = {}
    events = []
    clear_pending = 0
    active_profession = initial_profession
    solver = object.__new__(BaseSchedulerSolver)
    solver.task = None
    solver.last_room = ""
    solver.choose_error = set()
    solver.op_data = SimpleNamespace(
        plan={room: [SimpleNamespace(agent="图耶")] * capacity},
        operators={},
        profession_filter=set(),
        dorm_mood_estimates={},
    )
    solver.prepare_dorm_selection = Mock(return_value=[])
    solver._check_group_shift_targets = Mock(return_value=False)
    solver.detect_arrange_order = Mock(return_value=("技能", False))
    solver.get_order = Mock(return_value=(False, ("技能", False)))
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
        visible = [
            name
            for name in cards
            if active_profession == "ALL" or agent_profession[name] == active_profession
        ]
        for index, name in enumerate(visible):
            left, top = 631 + index // 2 * 216, 488 + index % 2 * 421
            scope = ((left, top), (left + 189, top + 32))
            page.append((name, scope))
        frames[id(img)] = (page, set(selected))
        solver.recog.img = img

    def sort(*_):
        cards[:] = selected + [name for name in cards if name not in selected]
        refresh()

    def filter_profession(profession=None):
        nonlocal active_profession
        active_profession = profession or "ALL"
        refresh()

    def tap(point, **_):
        nonlocal clear_pending
        if isinstance(point[0], (int, float)) and point[1] == 1026:
            assert capacity > 1, "单岗位页面没有清空按钮，不能点击 (729, 1026)"
            clear_pending = 3
            events.append("clear")
            refresh()
            return
        assert not clear_pending, "不能在原卡片取消暂选前选择目标"
        name = next(
            name for name, scope in frames[id(solver.recog.img)][0] if scope == point
        )
        if name in selected:
            clear_pending = 3
            events.append(("cancel", name))
        else:
            assert selected == []
            selected.append(name)
            events.append(("select", name))
        refresh()

    solver.recog.update = Mock(side_effect=refresh)
    solver.profession_filter = Mock(side_effect=filter_profession)
    solver.sleep = Mock(side_effect=lambda *_: refresh())
    solver.wait_for_next_observation = Mock(side_effect=lambda *_: refresh())
    solver.switch_arrange_order = Mock(side_effect=sort)
    solver.tap = Mock(side_effect=tap)
    solver.swipe_left = Mock(return_value=(0, None))
    solver.swipe_agent_page = Mock(side_effect=AssertionError("当前页已有图耶"))
    monkeypatch.setattr(
        selection_module, "operator_list", lambda img, **_: frames[id(img)][0]
    )
    monkeypatch.setattr(
        selection_module,
        "agent_card_selected",
        lambda img, scope, **_: (
            next(name for name, box in frames[id(img)][0] if box == scope)
            in frames[id(img)][1]
        ),
    )
    refresh()

    solver.choose_agent(targets.copy(), room, fast_mode=False, choose_error=1)

    assert selected == [name for name in targets if name]
    assert events == expected_events


@pytest.mark.parametrize("already_clear", [False, True])
def test_single_slot_clear_uses_captured_card_and_observes_feedback(
    monkeypatch, selection_module, already_clear
):
    from arknights_mower.utils.character_recognize import operator_list

    images = {
        state: np.array(
            Image.open(
                Path(__file__).parent
                / f"fixtures/selection/trade_single_{state}_20261021.jpg"
            )
        )
        for state in ("selected", "cleared")
    }
    monkeypatch.setattr(config, "conf", config.Conf(performance_mode="high"))
    solver = selection_module.BaseMixin()
    solver.op_data = SimpleNamespace(plan={ROOM: [object()]})
    solver.recog = SimpleNamespace(
        w=1920,
        h=1080,
        img=images["cleared" if already_clear else "selected"],
    )
    solver.find = Mock(return_value=False)
    solver.switch_arrange_order = Mock()
    pending = 0

    def update():
        nonlocal pending
        if pending:
            pending -= 1
            if not pending:
                solver.recog.img = images["cleared"]

    scope = operator_list(images["selected"])[0][1]

    def tap(point, **_):
        nonlocal pending
        assert point == scope
        pending = 3

    solver.recog.update = Mock(side_effect=update)
    solver.wait_for_next_observation = Mock(side_effect=lambda *_: update())
    solver.tap = Mock(side_effect=tap)

    solver.clear_agent_selection(ROOM)

    assert solver.tap.call_count == (0 if already_clear else 1)
    assert solver.recog.img is images["cleared"]


def test_captured_workshop_single_slot_selection_border(selection_module):
    from arknights_mower.utils.character_recognize import operator_list

    image = np.array(
        Image.open(
            Path(__file__).parent
            / "fixtures/selection/workshop_single_selected_20261029.jpg"
        )
    )
    page = operator_list(image)

    assert page[0][0] == "特克诺"
    assert "年" in [name for name, _ in page]
    assert [
        name
        for name, scope in page
        if selection_module.agent_card_selected(image, scope) is True
    ] == ["特克诺"]
    assert all(
        selection_module.agent_card_selected(image, scope) is not None
        for _, scope in page
    )


@pytest.mark.parametrize("room", ["factory", "contact"])
@pytest.mark.parametrize("plan_count", [None, 0, 1])
def test_right_side_single_slot_clear_uses_captured_card_without_static_staff(
    monkeypatch, selection_module, room, plan_count
):
    """加工站实图提供蓝框和坐标；无蓝框反馈由已有贸易站样本模拟。"""
    from arknights_mower.utils.character_recognize import operator_list

    fixture_dir = Path(__file__).parent / "fixtures/selection"
    selected_image = np.array(
        Image.open(fixture_dir / "workshop_single_selected_20261029.jpg")
    )
    cleared_image = np.array(
        Image.open(fixture_dir / "trade_single_cleared_20261021.jpg")
    )
    monkeypatch.setattr(config, "conf", config.Conf(performance_mode="high"))
    solver = selection_module.BaseMixin()
    plan = {} if plan_count is None else {room: [object()] * plan_count}
    solver.op_data = SimpleNamespace(plan=plan)
    solver.recog = SimpleNamespace(w=1920, h=1080, img=selected_image)
    solver.find = Mock(return_value=False)
    solver.switch_arrange_order = Mock()
    scope = operator_list(selected_image)[0][1]
    pending = 0
    events = []

    def update():
        nonlocal pending
        if pending:
            pending -= 1
            if not pending:
                solver.recog.img = cleared_image
                events.append("cleared")

    def tap(point, **_):
        nonlocal pending
        assert point == scope, "单岗位设施必须点击实读蓝框卡片"
        pending = 3
        events.append(("cancel", "特克诺"))

    solver.recog.update = Mock(side_effect=update)
    solver.wait_for_next_observation = Mock(side_effect=lambda *_: update())
    solver.tap = Mock(side_effect=tap)

    solver.clear_agent_selection(room)

    assert events == [("cancel", "特克诺"), "cleared"]
    assert solver.tap.call_count == 1
    assert solver.recog.img is cleared_image


def test_training_selection_keeps_legacy_clear(selection_module):
    solver = selection_module.BaseMixin()
    solver.op_data = SimpleNamespace(plan={"train": [object()]})
    solver.recog = SimpleNamespace(w=1920, h=1080)
    solver.tap = Mock()
    solver.switch_arrange_order = Mock()
    solver.wait_for_cleared_selection = Mock()

    solver.clear_agent_selection("train")

    solver.tap.assert_called_once()
    assert solver.tap.call_args.args == ((729.6, 1026.0),)
    solver.wait_for_cleared_selection.assert_called_once_with()
    solver.switch_arrange_order.assert_not_called()


@pytest.mark.parametrize("problem", ["unknown", "multiple", "exited", "name"])
def test_single_slot_clear_does_not_guess_an_unconfirmed_card(
    monkeypatch, selection_module, problem
):
    image = np.array(
        Image.open(
            Path(__file__).parent
            / "fixtures/selection/trade_single_selected_20261021.jpg"
        )
    )
    from arknights_mower.utils.character_recognize import operator_list

    page = operator_list(image)
    solver = selection_module.BaseMixin()
    solver.op_data = SimpleNamespace(plan={ROOM: [object()]})
    solver.recog = SimpleNamespace(img=image)
    solver.find = Mock(
        side_effect=lambda name: problem == "exited" and name == "arrange_check_in_on"
    )
    solver.switch_arrange_order = Mock()
    solver.wait_for_agent_page = Mock(
        return_value=(("", page[0][1]),) if problem == "name" else page
    )
    solver.tap = Mock()
    if problem in ("unknown", "multiple"):
        monkeypatch.setattr(
            selection_module,
            "agent_card_selected",
            lambda *_: None if problem == "unknown" else True,
        )

    with pytest.raises(selection_module.AgentSelectionNotReady):
        solver.clear_agent_selection(ROOM)

    solver.tap.assert_not_called()
