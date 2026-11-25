from unittest.mock import MagicMock, call

import numpy as np
import pytest

from arknights_mower.solvers import navigation
from arknights_mower.utils.device.io_budget import device_io_budget


@pytest.fixture
def navigator():
    solver = object.__new__(navigation.NavigationSolver)
    solver.name = "OS-1"
    solver.recog = MagicMock()
    solver.sleep = MagicMock()
    solver.find = MagicMock()
    solver.back = MagicMock()
    solver.find_target_stage_after_entry = MagicMock(return_value=True)
    return solver


@pytest.mark.parametrize(
    "text,score,right_edge,expected",
    [
        ("OPERATIONOS-1", 0.85, 270, "OS-1"),
        ("OS-EX-8", 0.97, 265, "OS-EX-8"),
        ("OS-10", 0.98, 265, "OS-10"),
        ("OS-1", 0.98, 330, None),
        ("OS-1", 0.6, 265, None),
        ("OPERATION", 0.99, 110, None),
    ],
)
def test_detail_reads_only_a_complete_code_from_the_panel_header(
    navigator, monkeypatch, text, score, right_edge, expected
):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[108:166, 1267:1598] = 1
    navigator.recog.img = frame

    def ocr(title, **kwargs):
        assert title.shape == (58, 331, 3)
        assert title.all()
        return [([(0, 0), (right_edge, 58)], text, score)], None

    monkeypatch.setattr(navigation.rapidocr, "engine", ocr)
    navigator.find.side_effect = [None] * 4 + [True]
    assert navigator._read_stage_detail_code() == expected
    assert navigator.find.call_args_list == [call("ope_start")] * 5
    assert navigator.sleep.call_args_list == [call(0.4)] * 4


@pytest.mark.parametrize(
    "first,second,expected",
    [
        ("OS-1", None, True),
        (None, None, False),
        ("OS-2", "OS-1", True),
        ("OS-2", "OS-2", False),
        ("OS-10", None, False),
    ],
)
def test_wrong_detail_reselects_once_and_requires_exact_target(
    navigator, first, second, expected
):
    navigator._read_stage_detail_code = MagicMock(side_effect=[first, second])
    navigator.find.return_value = None

    assert navigator.confirm_selected_stage() is expected
    if first in (None, "OS-1"):
        navigator.back.assert_not_called()
        navigator.find_target_stage_after_entry.assert_not_called()
    else:
        navigator.back.assert_called_once_with()
        navigator.find_target_stage_after_entry.assert_called_once_with("OS-1")
        assert navigator._read_stage_detail_code.call_count == 2


def test_unclosed_detail_does_not_search_map_labels(navigator):
    navigator._read_stage_detail_code = MagicMock(return_value="OS-2")
    navigator.find.return_value = True

    assert not navigator.confirm_selected_stage()
    navigator.find_target_stage_after_entry.assert_not_called()


def test_expired_budget_cannot_reselect_the_stage(navigator):
    navigator._read_stage_detail_code = MagicMock(return_value="OS-2")
    with (
        pytest.raises(TimeoutError),
        device_io_budget(MagicMock(side_effect=[1.0, TimeoutError()])),
    ):
        navigator.confirm_selected_stage()
    navigator.back.assert_not_called()
