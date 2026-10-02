"""The bundled panel model must match current skill data and stay conservative."""

import json
import lzma
import pickle
from copy import deepcopy
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import ImageFont

from arknights_mower.utils.mastery_panel_model import (
    FONT_SIZE,
    PIXEL_THRESHOLD,
    build_model,
    render_template,
    skill_roster_digest,
)
from arknights_mower.utils.mastery_panel_template import recognize_skill

ROOT = Path(__file__).parents[1]
DATA = ROOT / "data/skill_data.json"
MODEL = ROOT / "models/mastery_panel.model"


class _BuiltinOnlyUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        raise AssertionError(f"模型依赖外部 Python 类：{module}.{name}")


def test_incompatible_old_model_falls_back_to_ocr(monkeypatch):
    from arknights_mower.utils import mastery_panel_template as template

    def missing_numpy_module(_stream):
        raise ModuleNotFoundError("No module named 'numpy._core.numeric'")

    template.reload_mastery_panel_model()
    try:
        with monkeypatch.context() as patcher:
            patcher.setattr(template.pickle, "load", missing_numpy_module)
            assert template._load_model() is None
    finally:
        template.reload_mastery_panel_model()


def test_bundled_model_covers_current_named_skills():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    with lzma.open(MODEL, "rb") as stream:
        model = _BuiltinOnlyUnpickler(stream).load()
    assert model["schema"] == 2
    assert model["roster_sha256"] == skill_roster_digest(data)
    assert model["font_size"] == FONT_SIZE
    assert model["pixel_threshold"] == PIXEL_THRESHOLD
    expected = sum(
        bool(skill.get("name"))
        for char in data["characters"].values()
        if char.get("rarity") in (4, 5, 6)
        for skill in char.get("skills", [])
    )
    assert sum(len(entry["skills"]) for entry in model["entries"].values()) == expected
    for entry in model["entries"].values():
        for height, width, pixels in [
            entry["name_template"],
            *(template for _, _, template in entry["skills"]),
        ]:
            assert len(pixels) == height * width


def test_real_panels_match_only_their_own_skill():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    fixtures = ROOT / "tests/fixtures"
    for filename, operator, expected_index in (
        ("mastery_panel_carnelian.png", "卡涅利安", 1),
        ("mastery_panel_hairin.png", "八幡海铃", 0),
    ):
        image = cv2.imread(str(fixtures / filename))
        match = recognize_skill(image, operator, data)
        assert match is not None
        assert match[0] == expected_index
        assert match[2] >= 0.80 and match[3] >= 0.80 and match[4] >= 0.15
        assert recognize_skill(image, "泡泡", data) is None


def test_real_gamma_panel_matches_game_middle_dot_spacing():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    image = cv2.imread(str(ROOT / "tests/fixtures/mastery_panel_elysium_gamma.png"))
    match = recognize_skill(image, "极境", data)

    assert match is not None
    assert match[:2] == (0, "支援号令·γ型")
    assert match.name_score >= 0.80
    assert match.skill_score >= 0.85
    assert match.margin >= 0.15
    assert recognize_skill(image, "泡泡", data) is None


def test_other_skill_does_not_match_gamma():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    font = ImageFont.truetype(
        str(ROOT / "fonts/SourceHanSansCN-Medium-mastery.ttf"), FONT_SIZE
    )
    rendered = render_template("[极境]聆听", font)
    image = np.zeros((42, 520), dtype=np.uint8)
    image[4 : 4 + rendered.shape[0], 5 : 5 + rendered.shape[1]] = rendered

    match = recognize_skill(image, "极境", data)
    assert match is not None and match[:2] == (1, "聆听")


def test_amiya_forms_are_collected_and_recognized():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    expected = {
        "char_002_amiya": ["战术咏唱·γ型", "精神爆发", "奇美拉"],
        "char_1001_amiya2": ["影霄·奔夜", "影霄·绝影"],
        "char_1037_amiya3": ["哀恸共情", "慈悲愿景"],
    }
    font = ImageFont.truetype(
        str(ROOT / "fonts/SourceHanSansCN-Medium-mastery.ttf"), FONT_SIZE
    )
    for cid, names in expected.items():
        assert [skill["name"] for skill in data["characters"][cid]["skills"]] == names
        for index, name in enumerate(names):
            rendered = render_template(f"[阿米娅]{name}", font)
            image = np.zeros((42, 520), dtype=np.uint8)
            image[: rendered.shape[0], : rendered.shape[1]] = rendered
            match = recognize_skill(image, "阿米娅", data)
            assert match is not None and match[:2] == (index, name)


def test_stale_skill_data_and_blank_frame_never_confirm():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    stale = deepcopy(data)
    stale["characters"]["char_426_billro"]["skills"][1]["name"] = "更新后的技能名"
    fixture = ROOT / "tests/fixtures/mastery_panel_carnelian.png"
    image = cv2.imread(str(fixture))
    assert recognize_skill(image, "卡涅利安", stale) is None
    assert recognize_skill(np.zeros_like(image), "卡涅利安", data) is None


def test_font_subset_rejects_new_characters(tmp_path):
    data = json.loads(DATA.read_text(encoding="utf-8"))
    changed = deepcopy(data)
    changed["characters"]["char_426_billro"]["skills"][1]["name"] += "𠀀"
    font = ROOT / "fonts/SourceHanSansCN-Medium-mastery.ttf"
    charset = ROOT / "fonts/mastery-charset.txt"
    with pytest.raises(ValueError, match="字体子集缺字"):
        build_model(changed, font, tmp_path / "unused.model", charset)
    assert not (tmp_path / "unused.model").exists()


def test_full_name_templates_recognize_real_panels():
    from arknights_mower.utils.mastery_panel_template import recognize_operator

    data = json.loads(DATA.read_text(encoding="utf-8"))
    for filename, expected in (
        ("mastery_panel_carnelian.png", "卡涅利安"),
        ("mastery_panel_hairin.png", "八幡海铃"),
        ("mastery_panel_elysium_gamma.png", "极境"),
        ("mastery_panel_ptilopsis_enkephalin.png", "白面鸮"),
    ):
        image = cv2.imread(str(ROOT / "tests/fixtures" / filename))
        assert recognize_operator(image, data) == expected


def test_name_templates_cover_the_bundled_roster():
    from arknights_mower.utils.mastery_panel_template import recognize_operator

    data = json.loads(DATA.read_text(encoding="utf-8"))
    font = ImageFont.truetype(
        str(ROOT / "fonts/SourceHanSansCN-Medium-mastery.ttf"), FONT_SIZE
    )
    names = {
        char["name"]
        for char in data["characters"].values()
        if char.get("rarity") in (4, 5, 6)
        and any(skill.get("name") for skill in char.get("skills", []))
    }
    for name in sorted(names):
        rendered = render_template(f"[{name}]", font)
        image = np.zeros((42, 520), dtype=np.uint8)
        image[4 : 4 + rendered.shape[0], 5 : 5 + rendered.shape[1]] = rendered
        assert recognize_operator(image, data) == name, name


def test_name_templates_reject_unavailable_stale_and_blank_evidence(monkeypatch):
    from arknights_mower.utils import mastery_panel_template as template

    data = json.loads(DATA.read_text(encoding="utf-8"))
    image = cv2.imread(
        str(ROOT / "tests/fixtures/mastery_panel_ptilopsis_enkephalin.png")
    )
    assert template.recognize_operator(np.zeros_like(image), data) is None
    stale = deepcopy(data)
    stale["characters"]["char_128_plosis"]["skills"][0]["name"] += "更新"
    assert template.recognize_operator(image, stale) is None
    monkeypatch.setattr(template, "_load_model", lambda: None)
    assert template.recognize_operator(image, data) is None


@pytest.mark.parametrize("scores", [(0.69, 0.50), (0.90, 0.85)])
def test_name_templates_reject_low_scores_and_close_competitors(monkeypatch, scores):
    from arknights_mower.utils import mastery_panel_template as template

    data = {
        "characters": {
            "one": {"name": "白面鸮", "rarity": 5},
            "two": {"name": "白金", "rarity": 5},
        }
    }
    model = {
        "roster_sha256": skill_roster_digest(data),
        "entries": {
            cid: {
                "name": char["name"],
                "prefix_width": 100,
                "name_template": np.zeros((2, 2), dtype=np.uint8),
            }
            for cid, char in data["characters"].items()
        },
    }
    monkeypatch.setattr(template, "_load_model", lambda: model)
    values = iter(scores)
    monkeypatch.setattr(template, "_name_score", lambda *_: next(values))
    assert (
        template.recognize_operator(np.zeros((42, 520), dtype=np.uint8), data) is None
    )
