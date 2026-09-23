"""The bundled panel model must match current skill data and stay conservative."""

import json
import lzma
import pickle
from copy import deepcopy
from pathlib import Path

import cv2
import numpy as np
import pytest

from arknights_mower.utils.mastery_panel_model import (
    FONT_SIZE,
    PIXEL_THRESHOLD,
    build_model,
    skill_roster_digest,
)
from arknights_mower.utils.mastery_panel_template import recognize_skill

ROOT = Path(__file__).parents[1]
DATA = ROOT / "data/skill_data.json"
MODEL = ROOT / "models/mastery_panel.model"


def test_bundled_model_covers_current_named_skills():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    with lzma.open(MODEL, "rb") as stream:
        model = pickle.load(stream)
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
