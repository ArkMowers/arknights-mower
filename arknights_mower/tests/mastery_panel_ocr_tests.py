"""Training panel OCR retry must preserve identity and skill checks."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import mastery_reader as reader


def solver_with_text(*texts):
    solver = MagicMock()
    solver.recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    solver.recog.img[936:965, 240:560] = 240
    solver.read_screen.side_effect = texts
    return solver


def test_known_operator_keeps_single_ocr_fast_path():
    solver = solver_with_text("[八幡海铃]颤栗之弦")
    panel = reader._read_panel_text(solver)
    assert panel.operator_name == "八幡海铃"
    solver.read_screen.assert_called_once()


def test_missing_character_recovered_without_using_plan_name():
    solver = solver_with_text("[幡海铃]颤栗之弦", "[八幡海铃]颤栗之弦")
    panel = reader._read_panel_text(solver)
    assert (panel.operator_name, panel.skill_name) == ("八幡海铃", "颤栗之弦")
    image = solver.read_screen.call_args.args[0]
    assert image.shape == (42, 520)
    assert set(np.unique(image)) == {0, 255}
    assert "cord" not in solver.read_screen.call_args.kwargs
    plan = {
        "char_name": "八幡海铃",
        "skill_index": 0,
        "skill_name": "一技能·颤栗之弦",
    }
    assert reader._plan_matches_room(plan, reader.RoomState("training", panel))


@pytest.mark.parametrize(
    "retry",
    ["[幡海铃]颤栗之弦", "[八幡海铃]其他技能", "[八幡海铃]", None],
)
def test_unverified_retry_does_not_replace_original_identity(retry):
    solver = solver_with_text("[幡海铃]颤栗之弦", retry)
    panel = reader._read_panel_text(solver)
    assert (panel.operator_name, panel.skill_name) == ("幡海铃", "颤栗之弦")


def test_retry_exception_preserves_original_panel():
    solver = solver_with_text("[幡海铃]颤栗之弦", RuntimeError("OCR failed"))
    assert reader._read_panel_text(solver).operator_name == "幡海铃"


def test_actual_other_operator_is_not_rewritten_to_plan():
    solver = solver_with_text("[白面鸮]脑啡肽")
    panel = reader._read_panel_text(solver)
    assert panel.operator_name == "白面鸮"
    solver.read_screen.assert_called_once()
    assert not reader._plan_matches_room(
        {"char_name": "八幡海铃", "skill_name": "一技能·颤栗之弦"},
        reader.RoomState("training", panel),
    )


def test_empty_panel_does_not_open_retry_path():
    solver = solver_with_text(None)
    assert reader._read_panel_text(solver).operator_name == ""
    solver.read_screen.assert_called_once()


def test_real_device_panel_passes_identity_check(monkeypatch):
    from pathlib import Path
    from types import MethodType

    from rapidocr_onnxruntime import RapidOCR

    from arknights_mower.solvers.base_mixin import BaseMixin
    from arknights_mower.utils import rapidocr
    from arknights_mower.utils.image import loadimg

    # Keep only the panel text from the device screenshot. Exercise the real
    # preprocessing and OCR together, without depending on the original misread.
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    path = Path(__file__).with_name("fixtures") / "mastery_panel_hairin.png"
    image[930:972, 235:755] = loadimg(str(path))
    monkeypatch.setattr(rapidocr, "engine", RapidOCR(text_score=0.3))
    solver = MagicMock()
    solver.read_screen = MethodType(BaseMixin.read_screen, solver)
    panel = reader._read_panel_text(solver, image)
    assert (panel.operator_name, panel.skill_name) == ("八幡海铃", "颤栗之弦")
    assert reader._plan_matches_room(
        {"char_name": "八幡海铃", "skill_index": 0, "skill_name": "一技能·颤栗之弦"},
        reader.RoomState("training", panel),
    )
