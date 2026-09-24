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


@pytest.mark.parametrize("state", ["running", "complete"])
def test_orchid_panel_ocr_and_template_in_both_training_states(monkeypatch, state):
    from pathlib import Path
    from types import MethodType

    from rapidocr_onnxruntime import RapidOCR

    from arknights_mower.solvers.base_mixin import BaseMixin
    from arknights_mower.utils import rapidocr
    from arknights_mower.utils.image import loadimg
    from arknights_mower.utils.mastery_panel_template import recognize_skill
    from arknights_mower.utils.mastery_recommendation import get_skill_data

    card = loadimg(
        str(Path(__file__).with_name("fixtures") / f"mastery_card_orchid_{state}.png")
    )
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    image[925:1020, 220:780] = card
    monkeypatch.setattr(rapidocr, "engine", RapidOCR(text_score=0.3))
    solver = MagicMock()
    solver.read_screen = MethodType(BaseMixin.read_screen, solver)

    panel = reader._read_panel_text(solver, image)
    match = recognize_skill(card[5:47, 15:535], "焰狐龙梓兰", get_skill_data())

    assert (panel.operator_name, panel.skill_name) == ("焰狐龙梓兰", "飞翔瞪射")
    assert match is not None and match[:2] == (1, "飞翔瞪射")
    assert match[2] >= 0.80 and match[3] >= 0.80 and match[4] >= 0.15
    assert reader._plan_matches_room(
        {"char_name": "焰狐龙梓兰", "skill_index": 1, "skill_name": "二技能·飞翔瞪射"},
        reader.RoomState("training", panel),
    )


def test_template_recovers_carnelian_skill_dropped_by_ocr():
    from pathlib import Path

    import cv2

    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    fixture = Path(__file__).with_name("fixtures") / "mastery_panel_carnelian.png"
    image[930:972, 235:755] = cv2.imread(str(fixture))
    solver = MagicMock()
    solver.read_screen.return_value = "[卡涅利安]沙缚锁"

    panel = reader._read_panel_text(solver, image)

    assert (panel.operator_name, panel.skill_name) == ("卡涅利安", "沙缚镣锁")
    assert reader._plan_matches_room(
        {"char_name": "卡涅利安", "skill_index": 1, "skill_name": "二技能·沙缚镣锁"},
        reader.RoomState("training", panel),
    )


def test_ocr_template_conflict_stays_unknown():
    from pathlib import Path

    import cv2

    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    fixture = Path(__file__).with_name("fixtures") / "mastery_panel_carnelian.png"
    image[930:972, 235:755] = cv2.imread(str(fixture))
    solver = MagicMock()
    solver.read_screen.return_value = "[卡涅利安]沙暴守卫"

    panel = reader._read_panel_text(solver, image)

    assert panel.operator_name == "卡涅利安"
    assert panel.skill_name == ""


def test_unconfirmed_skill_does_not_become_mismatch():
    solver = solver_with_text("[卡涅利安]沙缚锁")

    panel = reader._read_panel_text(solver)

    assert panel.operator_name == "卡涅利安"
    assert panel.skill_name == ""
    plan = {"char_name": "卡涅利安", "skill_index": 1, "skill_name": "二技能·沙缚镣锁"}
    room = reader.RoomState("training", panel)
    assert reader._plan_matches_room(plan, room)
    assert not reader._can_adopt_expiry(plan, room)


@pytest.mark.parametrize(
    ("char_id", "skill_name", "index"),
    [
        ("char_002_amiya", "精神爆发", 1),
        ("char_1001_amiya2", "影霄·绝影", 1),
        ("char_1037_amiya3", "哀恸共情", 0),
    ],
)
def test_amiya_ocr_keeps_known_skill_without_optional_model(
    monkeypatch, char_id, skill_name, index
):
    from arknights_mower.utils.skill_label import resolve_panel_skill

    monkeypatch.setattr(reader, "recognize_skill", lambda *_: None)
    solver = solver_with_text(f"[阿米娅]{skill_name}")
    panel = reader._read_panel_text(solver)

    assert (panel.operator_name, panel.skill_name) == ("阿米娅", skill_name)
    assert resolve_panel_skill("阿米娅", skill_name) == index
    plan = {
        "char_id": char_id,
        "char_name": "阿米娅",
        "skill_index": index,
        "skill_name": skill_name,
    }
    assert reader._plan_matches_room(plan, reader.RoomState("training", panel))


def test_amiya_same_skill_index_does_not_mix_forms():
    room = reader.RoomState("training", reader.RoomPanel("阿米娅", "影霄·绝影"))
    caster_plan = {
        "char_id": "char_002_amiya",
        "char_name": "阿米娅",
        "skill_index": 1,
        "skill_name": "精神爆发",
    }
    assert not reader._plan_matches_room(caster_plan, room)
    assert not reader._can_recover_plan(caster_plan, room)


def test_amiya_ocr_template_conflict_with_same_skill_index_stays_unknown():
    from pathlib import Path

    from PIL import ImageFont

    from arknights_mower.utils.mastery_panel_model import FONT_SIZE, render_template

    font = ImageFont.truetype(
        str(Path(__file__).parents[1] / "fonts/SourceHanSansCN-Medium-mastery.ttf"),
        FONT_SIZE,
    )
    rendered = render_template("[阿米娅]影霄·绝影", font)
    solver = solver_with_text("[阿米娅]精神爆发")
    solver.recog.img[:] = 0
    solver.recog.img[930 : 930 + rendered.shape[0], 235 : 235 + rendered.shape[1]] = (
        rendered[:, :, None]
    )

    panel = reader._read_panel_text(solver)

    assert panel.operator_name == "阿米娅"
    assert panel.skill_name == ""
