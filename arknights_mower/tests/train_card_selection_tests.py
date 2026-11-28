"""训练室选人页已有待确认选择时，不能再次点击同一张卡。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import (
    AgentSelectionNotReady,
    AgentSelectionPageChanged,
    BaseMixin,
    agent_card_selected,
    train_card_selected,
)
from arknights_mower.utils import config

pytestmark = pytest.mark.usefixtures("legacy_selection_conf")

SCOPE = ((584, 479), (759, 506))
NORMAL_SCOPE = ((631, 488), (820, 520))


def card_frame(selected):
    img = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    if selected:
        cv2.rectangle(img, (565, 113), (766, 522), (0, 180, 230), 7)
    return img


def normal_card_frame(selected):
    img = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    if selected:
        cv2.rectangle(img, (609, 113), (830, 532), (0, 180, 230), 7)
    return img


@pytest.mark.parametrize("low_frame_rate", [False, True])
@pytest.mark.parametrize("already_selected", [False, True])
def test_train_scan_only_clicks_unselected_card(
    monkeypatch, low_frame_rate, already_selected
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    frame = card_frame(already_selected)
    page = (("予愿安洁莉娜", SCOPE),)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    solver.tap = MagicMock()
    solver.wait_for_agent_page = MagicMock(return_value=page)
    monkeypatch.setattr(base_mixin, "operator_list_train", lambda img: page)

    targets = ["予愿安洁莉娜"]
    selected, _ = solver.scan_agent(targets, train=True, respect_train_selection=True)

    assert train_card_selected(frame, SCOPE) is already_selected
    assert selected == ["予愿安洁莉娜"]
    assert targets == []
    assert solver.tap.call_count == (0 if already_selected else 1)


def test_train_verification_reads_blue_frame_instead_of_first_card(monkeypatch):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", False)
    frame = card_frame(False)
    cv2.rectangle(frame, (565, 529), (766, 938), (0, 180, 230), 7)
    page = (
        ("结城理", SCOPE),
        ("予愿安洁莉娜", ((584, 895), (759, 922))),
    )
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list_train", lambda img: page)

    assert solver.wait_for_arranged_agents(["予愿安洁莉娜"], train=True) == [
        "予愿安洁莉娜"
    ]


@pytest.mark.parametrize(
    "expected,verified",
    [
        (["褐果", "凯尔希"], ["褐果", "凯尔希"]),
        (["褐果"], None),
    ],
)
def test_train_verification_accounts_for_multiple_blue_frames(
    monkeypatch, expected, verified
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", False)
    frame = card_frame(True)
    cv2.rectangle(frame, (565, 529), (766, 938), (0, 180, 230), 7)
    page = (
        ("褐果", SCOPE),
        ("凯尔希", ((584, 895), (759, 922))),
    )
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list_train", lambda img: page)

    if verified is None:
        with pytest.raises(AgentSelectionNotReady):
            solver.wait_for_arranged_agents(expected, train=True)
    else:
        assert solver.wait_for_arranged_agents(expected, train=True) == verified


@pytest.mark.parametrize("low_frame_rate", [False, True])
@pytest.mark.parametrize("already_selected", [False, True])
def test_normal_scan_checks_blue_frame_without_another_capture(
    monkeypatch, low_frame_rate, already_selected
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    frame = normal_card_frame(already_selected)
    page = (("褐果", NORMAL_SCOPE),)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    solver.tap = MagicMock()
    solver.wait_for_agent_page = MagicMock(return_value=page)
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: page)

    targets = ["褐果"]
    selected, _ = solver.scan_agent(targets)

    assert agent_card_selected(frame, NORMAL_SCOPE) is already_selected
    assert selected == ["褐果"]
    assert targets == []
    assert solver.tap.call_count == (0 if already_selected else 1)
    assert solver.recog.update.call_count == (0 if low_frame_rate else 1)


@pytest.mark.parametrize(
    "expected,verified", [(["褐果", "凯尔希"], True), (["褐果"], False)]
)
def test_normal_pre_reorder_verification_uses_all_blue_frames(
    monkeypatch, expected, verified
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", False)
    frame = normal_card_frame(True)
    cv2.rectangle(frame, (609, 534), (830, 953), (0, 180, 230), 7)
    page = (
        ("褐果", NORMAL_SCOPE),
        ("凯尔希", ((631, 909), (820, 941))),
    )
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: page)

    if verified:
        assert solver.wait_for_arranged_agents(expected) == expected
    else:
        with pytest.raises(AgentSelectionNotReady):
            solver.wait_for_arranged_agents(expected)


def test_unselected_card_below_blue_frame_is_not_ambiguous():
    frame = normal_card_frame(True)
    lower_scope = ((631, 909), (820, 941))
    assert agent_card_selected(frame, NORMAL_SCOPE) is True
    assert agent_card_selected(frame, lower_scope) is False


def test_notice_over_selected_card_does_not_interrupt_verification(monkeypatch):
    frame = normal_card_frame(True)
    frame[95:145] = 50
    page = (("但书", NORMAL_SCOPE),)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: page)

    assert agent_card_selected(frame, NORMAL_SCOPE) is True
    assert solver.wait_for_arranged_agents(["但书"]) == ["但书"]


def test_notice_over_selected_training_card_uses_remaining_border():
    frame = card_frame(True)
    frame[95:145] = 50

    assert train_card_selected(frame, SCOPE) is True


def test_neighboring_blue_frames_do_not_select_occluded_card(monkeypatch):
    frame = normal_card_frame(False)
    for top_left, bottom_right in (
        ((393, 113), (614, 532)),
        ((825, 113), (1046, 532)),
        ((609, 534), (830, 953)),
    ):
        cv2.rectangle(frame, top_left, bottom_right, (0, 180, 230), 7)
    frame[95:145] = 50

    assert agent_card_selected(frame, NORMAL_SCOPE) is not True
    page = (("但书", NORMAL_SCOPE),)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: page)
    with pytest.raises(AgentSelectionNotReady):
        solver.wait_for_arranged_agents(["但书"])


@pytest.mark.parametrize("low_frame_rate", [False, True])
@pytest.mark.parametrize(
    "target,filename,drop_first",
    [
        ("泥岩", "training_visible_mudrock", False),
        ("泥岩", "training_visible_mudrock", True),
        ("余", "training_selected_yu", False),
    ],
)
def test_visible_trainee_uses_card_then_verifies_on_new_frame(
    monkeypatch, target, filename, drop_first, low_frame_rate
):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
    from arknights_mower.utils.recognize import Recognizer

    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    monkeypatch.setattr("arknights_mower.utils.solver.csleep", lambda _: None)
    path = Path(__file__).parent / "fixtures/selection" / f"{filename}_20261123.jpg"
    solver = object.__new__(BaseSchedulerSolver)
    device = solver.device = MagicMock()
    device.check_current_focus.return_value = False
    recog = solver.recog = Recognizer(device, screencap=path.read_bytes())
    frame = recog.img.copy()
    page = base_mixin.operator_list_train(frame)
    scope = dict(page)[target]
    assert train_card_selected(frame, scope) is (target == "余")
    device.screencap.side_effect = lambda: (
        None,
        frame.copy(),
        cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY),
    )
    solver.op_data = SimpleNamespace(profession_filter=set())
    solver.profession_filter = MagicMock()

    def tap(point):
        assert point == solver.get_pos(scope)
        if drop_first and device.tap.call_count == 1:
            return
        (x, y), (right, bottom) = scope
        # 原录像选择了余，此处只模拟点击泥岩后游戏画出的蓝框。
        cv2.rectangle(
            frame, (x - 19, y - 366), (right + 7, bottom + 16), (0, 180, 230), 7
        )

    device.tap.side_effect = tap
    solver.choose_train_ope(target)

    if drop_first:
        solver.profession_filter.assert_called_once_with("TANK")
    else:
        solver.profession_filter.assert_not_called()
    assert device.tap.call_count == int(target == "泥岩") + int(drop_first)
    assert device.screencap.call_count >= (2 if low_frame_rate else 1)
    assert solver.last_room == "train"


def test_trainee_hidden_by_open_sidebar_cannot_be_selected_in_place():
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
    from arknights_mower.utils.recognize import Recognizer

    fixtures = Path(__file__).parent / "fixtures/selection"
    solver = object.__new__(BaseSchedulerSolver)
    solver.recog = Recognizer(
        None, (fixtures / "training_tank_yu_open_20261123.jpg").read_bytes()
    )
    solver.tap = MagicMock()

    assert not solver._select_visible_trainee("临光", sidebar_open=True)
    solver.tap.assert_not_called()


def test_selected_trainee_with_late_confirmation_returns_to_room(monkeypatch):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
    from arknights_mower.utils.recognize import Recognizer

    monkeypatch.setattr(config.conf, "low_frame_rate_mode", False)
    fixtures = Path(__file__).parent / "fixtures/selection"
    device = MagicMock()
    device.check_current_focus.return_value = False
    solver = object.__new__(BaseSchedulerSolver)
    solver.device = device
    solver.recog = Recognizer(
        device, (fixtures / "training_selected_yu_20261123.jpg").read_bytes()
    )
    prompt = Recognizer(
        device, (fixtures / "staffing_secondary_confirm_20261024.jpg").read_bytes()
    )
    device.screencap.return_value = (prompt.screencap, prompt.img, prompt.gray)
    solver.profession_filter = MagicMock()

    with pytest.raises(AgentSelectionPageChanged, match="二次确认"):
        solver.choose_train_ope("余")

    device.tap.assert_not_called()
    solver.profession_filter.assert_not_called()


@pytest.mark.parametrize("low_frame_rate", [False, True])
def test_trainee_visible_before_open_profession_sidebar_is_selected_in_place(
    monkeypatch, low_frame_rate
):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
    from arknights_mower.utils.recognize import Recognizer

    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    monkeypatch.setattr("arknights_mower.utils.solver.csleep", lambda _: None)
    fixtures = Path(__file__).parent / "fixtures/selection"
    solver = object.__new__(BaseSchedulerSolver)
    device = solver.device = MagicMock()
    device.check_current_focus.return_value = False

    def capture(name):
        return Recognizer(device, (fixtures / f"{name}_20261123.jpg").read_bytes())

    solver.recog = capture("training_visible_mudrock")
    ready = capture("training_tank_yu_open")
    selected = capture("training_tank_yu_selected_open")
    solver.op_data = SimpleNamespace(profession_filter=set())
    solver._close_profession_filter = MagicMock(side_effect=AssertionError("不应收栏"))
    solver.profession_filter = MagicMock(
        side_effect=lambda _: setattr(solver, "recog", ready)
    )

    ready_frame = ready.screencap, ready.img.copy(), ready.gray.copy()
    selected_frame = selected.screencap, selected.img.copy(), selected.gray.copy()
    device.screencap.side_effect = lambda: (
        selected_frame if device.tap.called else ready_frame
    )
    solver.choose_train_ope("余")

    solver.profession_filter.assert_called_once_with("TANK")
    solver._close_profession_filter.assert_not_called()
    device.tap.assert_called_once_with((1105, 908))
    assert device.screencap.call_count >= (2 if low_frame_rate else 1)
    assert solver.last_room == "train"
