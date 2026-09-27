"""训练室选人页已有待确认选择时，不能再次点击同一张卡。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import BaseMixin, train_card_selected
from arknights_mower.utils import config

SCOPE = ((584, 479), (759, 506))


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
