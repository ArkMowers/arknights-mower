"""停稳后普通卡片右缘少量裁切的选人回归。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import (
    AgentSelectionNotReady,
    BaseMixin,
    agent_card_selected,
)
from arknights_mower.utils import character_recognize as recognition
from arknights_mower.utils import config
from arknights_mower.utils.character_recognize import operator_list

pytestmark = pytest.mark.usefixtures("legacy_selection_conf")
FIXTURES = Path(__file__).parent / "fixtures/selection"


@pytest.mark.parametrize(
    "filename,name_left",
    [
        ("dorm_right_edge_20261010.png", 1725),
        ("manufacturing_right_edge_20261010.png", 1726),
    ],
)
def test_settled_live_right_edge_cards_are_unselected(filename, name_left):
    frame = cv2.cvtColor(cv2.imread(str(FIXTURES / filename)), cv2.COLOR_BGR2RGB)
    page = operator_list(frame)
    states = [agent_card_selected(frame, scope) for _, scope in page]

    assert len(page) == 12
    assert all(scope[0][0] == name_left for _, scope in page[-2:])
    assert states[-2:] == [False, False]
    assert all(state is not None for state in states)


@pytest.fixture(params=[13, 14], ids=["right-cut-8px", "right-cut-9px"])
def shifted_selected_page(request):
    frame = cv2.cvtColor(
        cv2.imread(str(FIXTURES / "right_edge_spot_20260930.jpg")), cv2.COLOR_BGR2RGB
    )
    original_page = operator_list(frame)
    assert [name for name, _ in original_page[-2:]] == ["斑点", "清流"]
    # 平移归档截图构造已选中卡片的裁切；不是实机滑动所得的新截图。
    # 保留原图确认的姓名，只平移坐标以隔离边框判定；现场截图另测真实分割。
    shift = request.param
    shifted = np.zeros_like(frame)
    shifted[:, shift:] = frame[:, : frame.shape[1] - shift]
    page = tuple(
        (
            name,
            ((left + shift, top), (min(right + shift, frame.shape[1]), bottom)),
        )
        for name, ((left, top), (right, bottom)) in original_page
    )
    return shifted, page


def test_shifted_selected_card_and_unselected_neighbor(shifted_selected_page):
    frame, page = shifted_selected_page

    assert agent_card_selected(frame, page[-2][1]) is True
    assert agent_card_selected(frame, page[-1][1]) is False


def test_shifted_selected_cards_keep_real_name_recognition(shifted_selected_page):
    frame, known_page = shifted_selected_page
    page = operator_list(frame)

    assert [name for name, _ in page] == [name for name, _ in known_page]
    assert [scope[0][0] for _, scope in page[-2:]] == [
        scope[0][0] for _, scope in known_page[-2:]
    ]
    assert [agent_card_selected(frame, scope) for _, scope in page[-2:]] == [
        True,
        False,
    ]


@pytest.mark.parametrize("low_frame_rate", [False, True])
@pytest.mark.parametrize("verify", [False, True], ids=["scan", "roster"])
def test_clipped_selected_card_uses_real_recognition_without_extra_observation(
    monkeypatch, shifted_selected_page, low_frame_rate, verify
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    frame, _ = shifted_selected_page
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    solver.wait_for_next_observation = MagicMock(
        side_effect=lambda *_: solver.recog.update()
    )
    solver.selection_observation_timing = lambda: (0, 3)
    solver.tap = MagicMock()
    targets = ["斑点"]

    if verify:
        assert solver.wait_for_arranged_agents(targets) == ["斑点"]
    else:
        selected, _ = solver.scan_agent(targets)
        assert selected == ["斑点"]
        assert targets == []
    solver.tap.assert_not_called()
    solver.recog.update.assert_called()
    assert solver.recog.update.call_count == (2 if low_frame_rate else 1)
    assert solver.wait_for_next_observation.call_count == (1 if low_frame_rate else 0)
    solver.sleep.assert_not_called()


def test_reduced_scan_keeps_its_existing_right_boundary(shifted_selected_page):
    frame, known_page = shifted_selected_page

    assert [name for name, _ in operator_list(frame, full_scan=False)] == [
        name for name, _ in known_page[:-2]
    ]


@pytest.mark.parametrize("shift,readable", [(16, True), (17, False)])
def test_open_terminal_name_keeps_small_cut_limit(shift, readable):
    frame = cv2.cvtColor(
        cv2.imread(str(FIXTURES / "right_edge_spot_20260930.jpg")), cv2.COLOR_BGR2RGB
    )
    shifted = np.zeros_like(frame)
    shifted[:, shift:] = frame[:, :-shift]
    page = operator_list(shifted)

    assert len(page) == (12 if readable else 10)
    assert ("斑点" in [name for name, _ in page]) is readable


def test_open_terminal_name_with_missing_text_stays_unknown(shifted_selected_page):
    frame, known_page = shifted_selected_page
    frame = frame.copy()
    name_left = known_page[-2][1][0][0]
    frame[488:519, name_left:] = 50
    page = operator_list(frame)

    assert len(page) == 12
    assert page[-2][0] == ""
    assert page[-1][0] == "清流"


@pytest.mark.parametrize("low_frame_rate", [False, True])
def test_open_terminal_name_with_cut_glyph_never_selects_or_verifies(
    monkeypatch, shifted_selected_page, low_frame_rate
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    frame, known_page = shifted_selected_page
    frame = frame.copy()
    name_left = known_page[-2][1][0][0]
    frame[488:519, name_left:] = 50
    # 将完整斑点字形放到画面右缘并裁去七像素；残字不能确认干员身份。
    template = recognition.OP_SELECT["斑点"]
    x, y, width, height = cv2.boundingRect(template)
    glyph = template[y : y + height, x : x + width]
    visible = width - 7
    frame[490 : 490 + height, -visible:] = glyph[:, :visible, None]
    page = operator_list(frame)
    assert len(page) == 12 and page[-2][0] == ""

    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    solver.wait_for_next_observation = MagicMock()
    solver.selection_observation_timing = lambda: (0, 3)
    solver.tap = MagicMock()
    targets = ["斑点"]

    selected, _ = solver.scan_agent(targets)

    assert selected == [] and targets == ["斑点"]
    with pytest.raises(AgentSelectionNotReady):
        solver.wait_for_arranged_agents(["斑点"])
    solver.tap.assert_not_called()


def test_dark_page_without_terminal_start_stays_empty():
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)

    assert operator_list(frame) == ()


@pytest.mark.parametrize("low_frame_rate", [False, True])
def test_scan_clipped_cards_preserves_selection_without_extra_observation(
    monkeypatch, shifted_selected_page, low_frame_rate
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    frame, page = shifted_selected_page
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    solver.tap = MagicMock()
    solver.wait_for_agent_page = MagicMock(return_value=page)
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: page)
    targets = ["清流", "斑点"]

    selected, _ = solver.scan_agent(targets)

    assert selected == ["斑点", "清流"]
    assert targets == []
    solver.tap.assert_called_once_with(
        page[-1][1], interval=0.2 if low_frame_rate else 0
    )
    if low_frame_rate:
        solver.recog.update.assert_not_called()
    else:
        solver.recog.update.assert_called_once()
    assert solver.wait_for_agent_page.call_count == (2 if low_frame_rate else 0)
    solver.sleep.assert_not_called()


@pytest.mark.parametrize("low_frame_rate", [False, True])
def test_verification_accepts_clipped_selected_card_without_extra_wait(
    monkeypatch, shifted_selected_page, low_frame_rate
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    frame, page = shifted_selected_page
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    solver.wait_for_next_observation = MagicMock()
    solver.tap = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: page)

    assert solver.wait_for_arranged_agents(["斑点"]) == ["斑点"]
    solver.recog.update.assert_called_once()
    assert solver.wait_for_next_observation.call_count == (1 if low_frame_rate else 0)
    solver.sleep.assert_not_called()
    solver.tap.assert_not_called()


@pytest.mark.parametrize("name_left", [1725, 1726, 1728])
@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("color", [(0, 180, 230), (0, 112, 145)])
def test_small_right_cut_preserves_bright_and_dim_states(name_left, selected, color):
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    if selected:
        cv2.rectangle(frame, (name_left - 22, 113), (name_left + 199, 532), color, 7)

    assert agent_card_selected(frame, ((name_left, 488), (1916, 520))) is selected


@pytest.mark.parametrize("name_left", [1729, 1800])
@pytest.mark.parametrize("selected", [False, True])
def test_larger_right_cut_remains_unknown(name_left, selected):
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    if selected:
        cv2.rectangle(
            frame, (name_left - 22, 113), (name_left + 199, 532), (0, 180, 230), 7
        )

    assert agent_card_selected(frame, ((name_left, 488), (1916, 520))) is None


def test_clipped_selected_card_with_occluded_top_remains_unknown():
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    cv2.rectangle(frame, (1704, 113), (1925, 532), (0, 180, 230), 7)
    frame[95:145] = 50

    assert agent_card_selected(frame, ((1726, 488), (1916, 520))) is None


def test_clipped_screen_edge_does_not_replace_missing_left_border():
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    frame[113:121, 1712:] = (0, 180, 230)
    frame[528:536, 1712:] = (0, 180, 230)
    frame[121:528, 1912:] = (0, 180, 230)

    assert agent_card_selected(frame, ((1726, 488), (1916, 520))) is None


@pytest.mark.parametrize("notice", [False, True])
@pytest.mark.parametrize("neighbor_mask", range(16))
@pytest.mark.parametrize("color", [(0, 180, 230), (0, 112, 145)])
def test_clipped_unselected_card_is_not_selected_by_neighbor_borders(
    notice, neighbor_mask, color
):
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    for bit, (dx, dy) in enumerate(((-216, 0), (216, 0), (0, -421), (0, 421))):
        if neighbor_mask & (1 << bit):
            cv2.rectangle(frame, (1704 + dx, 113 + dy), (1925 + dx, 532 + dy), color, 7)
    if notice:
        frame[95:145] = 50

    assert agent_card_selected(frame, ((1726, 488), (1916, 520))) is not True


def test_right_clipped_training_card_remains_unknown():
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    cv2.rectangle(frame, (1725, 113), (1925, 522), (0, 180, 230), 7)

    assert agent_card_selected(frame, ((1744, 479), (1916, 506)), train=True) is None


@pytest.mark.parametrize("low_frame_rate", [False, True])
def test_unknown_edge_scan_logs_card_and_stops_without_clicking(
    monkeypatch, shifted_selected_page, low_frame_rate
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    frame, page = shifted_selected_page
    scope = ((1800, 909), (1916, 941))
    page = (*page[:-1], ("清流", scope))
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    solver.tap = MagicMock()
    solver.wait_for_agent_page = MagicMock(return_value=page)
    solver.require_agent_selection_page = MagicMock()
    debug = MagicMock()
    monkeypatch.setattr(base_mixin.logger, "debug", debug)
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: page)

    with pytest.raises(AgentSelectionNotReady, match="干员选中边框不清晰"):
        solver.scan_agent(["清流"])

    solver.tap.assert_not_called()
    messages = [call.args[0] for call in debug.call_args_list]
    assert any(
        "清流" in message and str(scope) in message and str(frame.shape) in message
        for message in messages
    )
