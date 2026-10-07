"""原始入住信息截图不能作为选人卡片读取或触发选人输入。"""

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
)
from arknights_mower.utils import config
from arknights_mower.utils.recognize import Recognizer

FIXTURES = Path(__file__).parent / "fixtures" / "selection"


def captured_solver(filename):
    solver = BaseMixin()
    solver.recog = Recognizer(MagicMock(), (FIXTURES / filename).read_bytes())
    solver.recog.update = MagicMock()
    solver.find = solver.recog.find
    solver.tap = MagicMock()
    solver.sleep = MagicMock()
    return solver


@pytest.mark.parametrize("mode", ["medium", "high", "xhigh"])
@pytest.mark.parametrize("train", [False, True])
@pytest.mark.parametrize(
    "filename", ["room_roster_20261007.jpg", "room_roster_transition_20261007.jpg"]
)
@pytest.mark.parametrize("operation", ["verify", "page", "scan", "clear"])
def test_room_roster_stops_after_one_anomalous_read_without_input(
    monkeypatch, mode, train, filename, operation
):
    monkeypatch.setattr(config.conf, "performance_mode", mode)
    solver = captured_solver(filename)
    read = MagicMock(wraps=base_mixin.operator_list)
    read_train = MagicMock(wraps=base_mixin.operator_list_train)
    monkeypatch.setattr(base_mixin, "operator_list", read)
    monkeypatch.setattr(base_mixin, "operator_list_train", read_train)
    with pytest.raises(AgentSelectionPageChanged, match="页面"):
        if operation == "verify":
            solver.wait_for_arranged_agents(["清流"], train=train)
        elif operation == "page":
            solver.wait_for_agent_page(train=train)
        elif operation == "scan":
            solver.scan_agent(["清流"], train=train)
        else:
            solver.wait_for_arranged_agents([], train=train, check_empty=True)
    (read_train if train else read).assert_called_once()
    solver.tap.assert_not_called()
    solver.sleep.assert_not_called()


def test_original_selection_frame_retains_real_roster_verification(monkeypatch):
    monkeypatch.setattr(config.conf, "performance_mode", "high")
    solver = captured_solver("purestream_badge_20261007.jpg")
    solver.find = MagicMock(wraps=solver.find)
    assert solver.wait_for_arranged_agents(["清流"]) == ["清流"]
    assert all(call.args == ("connecting",) for call in solver.find.call_args_list)
    solver.tap.assert_not_called()


def clear_reader(monkeypatch, frames):
    monkeypatch.setattr(config.conf, "performance_mode", "high")
    monkeypatch.setattr(config.conf, "selection_poll_interval", 0.5)
    monkeypatch.setattr(config.conf, "selection_transition_timeout", 2.5)
    solver = BaseMixin()
    sequence = iter(frames)
    solver.recog = SimpleNamespace(img=None)
    solver.recog.update = MagicMock(
        side_effect=lambda: setattr(solver.recog, "img", next(sequence))
    )
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock(side_effect=lambda *args: solver.recog.update())
    solver.tap = MagicMock()
    monkeypatch.setattr(
        base_mixin,
        "operator_list",
        lambda *args, **kwargs: [
            ("温蒂", ((631, 488), (820, 520))),
            ("清流", ((631, 909), (820, 941))),
        ],
    )
    return solver


def selection_frame(selected):
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    if selected:
        for top in (113, 534):
            cv2.rectangle(frame, (609, top), (830, top + 419), (0, 180, 230), 7)
    return frame


def test_high_clear_waits_for_blue_borders_to_disappear_without_input(monkeypatch):
    selected, cleared = selection_frame(True), selection_frame(False)
    solver = clear_reader(monkeypatch, [selected, selected, cleared])
    assert solver.wait_for_arranged_agents([], check_empty=True) == []
    assert solver.recog.update.call_count == 3
    assert all(call.args == ("connecting",) for call in solver.find.call_args_list)
    solver.tap.assert_not_called()


@pytest.mark.parametrize("missing_page", [False, True])
def test_high_clear_never_accepts_old_selection_or_missing_cards(
    monkeypatch, missing_page
):
    solver = clear_reader(monkeypatch, [selection_frame(True)] * 6)
    if missing_page:
        monkeypatch.setattr(base_mixin, "operator_list", lambda *args, **kwargs: [])
    with pytest.raises(AgentSelectionNotReady):
        solver.wait_for_arranged_agents([], check_empty=True)
    assert solver.recog.update.call_count == 6
    solver.tap.assert_not_called()
