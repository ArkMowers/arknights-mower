"""选中蓝框改变姓名边界及右侧阴影的离线回归。"""

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
from arknights_mower.utils import config
from arknights_mower.utils.character_recognize import operator_list

pytestmark = pytest.mark.usefixtures("legacy_selection_conf")


@pytest.fixture
def captured_page():
    path = Path(__file__).parent / "fixtures/selection/right_edge_spot_20260930.jpg"
    frame = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    return frame, operator_list(frame)


def test_captured_selected_card_and_unselected_neighbor(captured_page):
    frame, page = captured_page
    assert page[-2:] == (
        ("斑点", ((1712, 488), (1912, 520))),
        ("清流", ((1712, 909), (1912, 941))),
    )
    assert agent_card_selected(frame, page[-2][1]) is True
    assert agent_card_selected(frame, page[-1][1]) is False
    assert all(agent_card_selected(frame, scope) is False for _, scope in page[:-2])


@pytest.mark.parametrize("low_frame_rate", [False, True])
def test_captured_scan_preserves_selection_and_clicks_only_neighbor(
    monkeypatch, captured_page, low_frame_rate
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    frame, page = captured_page
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
    solver.tap.assert_called_once()
    assert solver.tap.call_args.args == (page[-1][1],)


def test_captured_roster_verification_accepts_only_selected_card(captured_page):
    frame, _ = captured_page
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()

    assert solver.wait_for_arranged_agents(["斑点"]) == ["斑点"]
    with pytest.raises(AgentSelectionNotReady):
        solver.wait_for_arranged_agents(["斑点", "清流"])


@pytest.mark.parametrize("name_width", [189, 200])
@pytest.mark.parametrize("name_left", [631, 1712])
def test_dim_border_uses_card_geometry_instead_of_name_width(name_width, name_left):
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    cv2.rectangle(
        frame, (name_left - 22, 113), (name_left + 199, 532), (0, 112, 145), 7
    )
    scope = ((name_left, 488), (name_left + name_width, 520))

    assert agent_card_selected(frame, scope) is True


def test_genuinely_clipped_card_remains_unknown():
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    cv2.rectangle(frame, (1778, 113), (1999, 532), (0, 180, 230), 7)

    assert agent_card_selected(frame, ((1800, 488), (1912, 520))) is None


@pytest.mark.parametrize("train", [False, True])
@pytest.mark.parametrize("notice", [False, True])
@pytest.mark.parametrize("neighbor_mask", range(16))
@pytest.mark.parametrize("color", [(0, 180, 230), (0, 112, 145)])
def test_neighbor_border_combinations_never_select_unselected_card(
    train, notice, neighbor_mask, color
):
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    if train:
        scope = ((584, 479), (759, 506))
        left, top, right, bottom = 565, 113, 766, 522
        step_x, step_y = 196, 416
    else:
        scope = ((631, 488), (831, 520))
        left, top, right, bottom = 609, 113, 830, 532
        step_x, step_y = 216, 421
    for bit, (dx, dy) in enumerate(
        ((-step_x, 0), (step_x, 0), (0, -step_y), (0, step_y))
    ):
        if neighbor_mask & (1 << bit):
            cv2.rectangle(
                frame, (left + dx, top + dy), (right + dx, bottom + dy), color, 7
            )
    if notice:
        frame[95:145] = 50

    assert agent_card_selected(frame, scope, train=train) is not True


@pytest.mark.parametrize("train", [False, True])
def test_blue_portrait_inside_card_does_not_count_as_selected(train):
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    scope = ((584, 479), (759, 506)) if train else ((631, 488), (831, 520))
    left = scope[0][0]
    frame[125:520, left : left + 160] = (0, 112, 145)

    assert agent_card_selected(frame, scope, train=train) is False


def test_training_dim_border_keeps_original_unselected_state():
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    cv2.rectangle(frame, (565, 113), (766, 522), (0, 112, 145), 7)

    assert agent_card_selected(frame, ((584, 479), (759, 506)), train=True) is False


@pytest.fixture(params=[False, True], ids=["archived-jpeg", "badge-color-boundary"])
def purestream_page(request):
    path = Path(__file__).parent / "fixtures/selection/purestream_badge_20261007.jpg"
    frame = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    if request.param:
        # JPEG 色差改变青色状态图标的掩膜覆盖率；明确构造阈值另一侧，
        # 不把归档 JPEG 当作现场 RGB 像素的无损复现。
        badge = cv2.cvtColor(frame[113:121, 748:818], cv2.COLOR_RGB2HSV)
        cyan = (
            (badge[:, :, 0] >= 90)
            & (badge[:, :, 0] <= 105)
            & (badge[:, :, 1] >= 100)
            & (badge[:, :, 2] >= 100)
        )
        badge[:, :, 0][cyan] = 100
        badge[:, :, 1][cyan] = np.maximum(140, badge[:, :, 1][cyan])
        badge[:, :, 2][cyan] = np.maximum(140, badge[:, :, 2][cyan])
        frame[113:121, 748:818] = cv2.cvtColor(badge, cv2.COLOR_HSV2RGB)
    return frame, operator_list(frame)


def test_badge_and_lower_neighbor_leave_only_purestream_selected(purestream_page):
    frame, page = purestream_page
    assert [name for name, _ in page[:2]] == ["温蒂", "清流"]
    states = [agent_card_selected(frame, scope) for _, scope in page]
    assert states == [False, True] + [False] * 10


@pytest.mark.parametrize("low_frame_rate", [False, True])
def test_purestream_verification_ignores_unselected_badge(
    monkeypatch, purestream_page, low_frame_rate
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    frame, _ = purestream_page
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    solver.tap = MagicMock()

    assert solver.wait_for_arranged_agents(["清流"]) == ["清流"]
    solver.tap.assert_not_called()


@pytest.mark.parametrize("low_frame_rate", [False, True])
def test_purestream_scan_preserves_existing_selection(
    monkeypatch, purestream_page, low_frame_rate
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    frame, _ = purestream_page
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    solver.tap = MagicMock()
    targets = ["清流"]

    selected, page = solver.scan_agent(targets)

    assert selected == ["清流"] and targets == []
    assert len(page) == 12
    solver.tap.assert_not_called()


@pytest.mark.parametrize("upper_width", [50, 65, 90])
def test_partial_badge_above_selected_neighbor_is_unselected(upper_width):
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    # 状态图标只占上沿的一段，下排选中框只擦到下沿靠后的像素。
    frame[113:121, 720 : 720 + upper_width] = (0, 180, 230)
    cv2.rectangle(frame, (609, 538), (830, 953), (0, 180, 230), 7)

    assert agent_card_selected(frame, ((631, 488), (820, 520))) is False
    assert agent_card_selected(frame, ((631, 909), (820, 941))) is True


def test_partial_border_with_vertical_evidence_remains_unknown():
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    frame[113:121, 720:785] = (0, 180, 230)
    frame[528:536, 720:785] = (0, 180, 230)
    frame[121:528, 609:617] = (0, 180, 230)

    assert agent_card_selected(frame, ((631, 488), (820, 520))) is None


@pytest.mark.parametrize("top", [113, 528])
def test_full_horizontal_border_without_sides_remains_unknown(top):
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    frame[top : top + 8, 617:826] = (0, 180, 230)

    assert agent_card_selected(frame, ((631, 488), (820, 520))) is None
