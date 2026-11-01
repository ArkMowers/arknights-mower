"""原始入住信息截图不能作为选人卡片读取或触发选人输入。"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import (
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
@pytest.mark.parametrize("operation", ["verify", "page", "scan"])
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
