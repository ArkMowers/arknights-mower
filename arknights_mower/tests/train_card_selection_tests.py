"""训练室选人页已有待确认选择时，不能再次点击同一张卡。"""

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
    train_card_selected,
)
from arknights_mower.utils import config

SCOPE = ((584, 479), (759, 506))
NORMAL_SCOPE = ((571, 488), (759, 520))


def card_frame(selected):
    img = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    if selected:
        cv2.rectangle(img, (565, 113), (766, 522), (0, 180, 230), 7)
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
    frame = card_frame(already_selected)
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
    frame = card_frame(True)
    cv2.rectangle(frame, (565, 534), (766, 943), (0, 180, 230), 7)
    page = (
        ("褐果", NORMAL_SCOPE),
        ("凯尔希", ((571, 909), (759, 941))),
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
