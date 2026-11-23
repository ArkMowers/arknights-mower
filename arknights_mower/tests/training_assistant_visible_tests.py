"""训练室协助位在当前名单中核对具名目标。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config
from arknights_mower.utils.recognize import Recognizer

FIXTURES = Path(__file__).parent / "fixtures/selection"


@pytest.fixture
def assistant(monkeypatch):
    monkeypatch.setattr(config.conf, "performance_mode", "high")
    solver = object.__new__(BaseSchedulerSolver)
    device = solver.device = MagicMock()
    device.check_current_focus.return_value = False
    solver.recog = Recognizer(
        device, (FIXTURES / "training_visible_wang_20261123.jpg").read_bytes()
    )
    selected = Recognizer(
        None, (FIXTURES / "training_selected_wang_20261123.jpg").read_bytes()
    )
    device.screencap.return_value = (selected.screencap, selected.img, selected.gray)
    solver.op_data = SimpleNamespace(
        get_current_room=MagicMock(return_value=["", ""]),
        profession_filter=set(),
    )
    solver.task = None
    solver.last_room = ""
    solver.prepare_dorm_selection = MagicMock(return_value=[])
    solver._check_group_shift_targets = MagicMock(
        wraps=solver._check_group_shift_targets
    )
    solver.observe_agent_moods = MagicMock(wraps=solver.observe_agent_moods)
    return solver


def test_visible_assistant_from_real_room_entry_taps_wang_then_verifies(assistant):
    solver = assistant
    solver.profession_filter = MagicMock(
        side_effect=AssertionError("目标在首卡，仍然重置职业")
    )
    solver.choose_agent(["望"], "train")
    solver.device.tap.assert_called_once_with((725, 504))
    solver.device.screencap.assert_called_once_with()
    assert solver.last_room == "train"
    assert solver._check_group_shift_targets.call_count == 2
    assert solver.observe_agent_moods.call_count == 1


def test_assistant_with_a_visible_blue_frame_is_verified_without_a_second_tap(
    assistant,
):
    solver = assistant
    solver.recog.set_frame(solver.device.screencap.return_value)
    solver.profession_filter = MagicMock(
        side_effect=AssertionError("已有具名蓝框，仍重置职业")
    )
    solver.choose_agent(["望"], "train")
    solver.device.tap.assert_not_called()
    solver.device.screencap.assert_called_once_with()


def test_assistant_recovers_the_profession_when_the_tap_did_not_select(
    assistant, monkeypatch
):
    solver = assistant
    solver.device.screencap.return_value = (
        solver.recog.screencap,
        solver.recog.img,
        solver.recog.gray,
    )
    monkeypatch.setattr("arknights_mower.utils.solver.csleep", lambda _: None)

    class FilterReset(Exception):
        pass

    solver.profession_filter = MagicMock(side_effect=FilterReset)
    with pytest.raises(FilterReset):
        solver.choose_agent(["望"], "train")
    solver.device.tap.assert_called_once_with((725, 504))
    assert solver.device.screencap.call_count >= 1
    solver.profession_filter.assert_called_once_with()


@pytest.mark.parametrize("case", ["other_occupant", "missing", "retry", "emergency"])
def test_assistant_keeps_normal_profession_recovery(assistant, case):
    solver = assistant
    if case == "other_occupant":
        solver.op_data.get_current_room.return_value = ["斥罪", "余"]
    if case == "emergency":
        solver.task = SimpleNamespace(emergency_staffing=True)

    class FilterReset(Exception):
        pass

    solver.profession_filter = MagicMock(side_effect=FilterReset)
    with pytest.raises(FilterReset):
        solver.choose_agent(
            ["泥岩" if case == "missing" else "望"],
            "train",
            fast_mode=case != "retry",
            choose_error=int(case == "retry"),
        )
    solver.profession_filter.assert_called_once_with()
    solver.device.tap.assert_not_called()
