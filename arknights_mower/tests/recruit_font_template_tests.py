"""Replay public recruitment text templates against game screenshots."""

import json
import lzma
import pickle
from pathlib import Path

import cv2
import pytest

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests/fixtures"


def _model(name):
    with lzma.open(ROOT / "models" / name, "rb") as file:
        return pickle.load(file)


def _rank(image, templates):
    return sorted(
        (
            cv2.minMaxLoc(cv2.matchTemplate(image, template, cv2.TM_CCORR_NORMED))[1],
            name,
        )
        for name, template in templates.items()
        if image.shape[0] >= template.shape[0] and image.shape[1] >= template.shape[1]
    )[::-1]


@pytest.mark.parametrize(
    ("index", "expected"),
    tuple(enumerate(("近卫干员", "医疗干员", "爆发", "生存", "元素"))),
)
def test_recruit_tags_match_game_screenshot(index, expected):
    image = cv2.imread(str(FIXTURES / "recruit_tags_20260926.png"))
    height, width = image.shape[:2]
    row, column = divmod(index, 3)
    tag = image[
        row * (height // 2) : (row + 1) * (height // 2),
        column * (width // 3) : (column + 1) * (width // 3),
    ]
    (score, name), (runner_up, _) = _rank(tag, _model("recruit.pkl"))[:2]
    assert name == expected
    assert score > 0.93
    assert score - runner_up > 0.05


@pytest.mark.parametrize(
    ("fixture", "expected"),
    (
        ("recruit_result_beanstalk_20260926.png", "豆苗"),
        ("recruit_result_jessica_20260926.png", "杰西卡"),
    ),
)
def test_recruit_result_matches_game_screenshot(fixture, expected):
    image = cv2.imread(str(FIXTURES / fixture), cv2.IMREAD_GRAYSCALE)
    image = cv2.threshold(image, 220, 255, cv2.THRESH_BINARY)[1]
    names = {
        key: value["name"]
        for key, value in json.loads((ROOT / "data/recruit.json").read_text()).items()
    }
    (score, key), (runner_up, _) = _rank(image, _model("recruit_result.pkl"))[:2]
    assert names[key] == expected
    assert score > 0.85
    assert score - runner_up > 0.18
