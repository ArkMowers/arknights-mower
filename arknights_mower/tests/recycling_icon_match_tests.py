from pathlib import Path

import cv2
import numpy as np
import pytest

from arknights_mower.tests.recycling_collection_tests import (
    multiple_reward_frame,
    recycling,
    reward_frame,
)
from arknights_mower.tests.recycling_ocr_evidence_tests import (
    background_text_frame,
)
from arknights_mower.tests.recycling_ocr_evidence_tests import (
    local_ocr as local_ocr,
)
from arknights_mower.tests.recycling_ocr_evidence_tests import (
    recognition_engine as recognition_engine,
)


def name_box(left=925, right=997):
    return [[left, 12], [right, 12], [right, 48], [left, 48]]


def test_real_background_text_does_not_override_the_reward_icon():
    image = background_text_frame()
    labels = recycling._ocr(image[640:705])
    assert any(text == "HELLO" and score > 0.90 for _box, text, score in labels)

    assert recycling.read_recycling_materials(image) == {"装置": 1}


@pytest.mark.parametrize(
    "labels",
    [
        [(name_box(925, 960), "装", 0.99), (name_box(961, 997), "置", 0.99)],
        [(name_box(), "装置", 0.99), (name_box(), "装置", 0.99)],
        [(name_box(), "装置", 0.99), (name_box(), "糖", 0.99)],
        [(name_box(), "未知材料", 0.99)],
        [(name_box(), "装置", 0.10)],
        [],
    ],
    ids=["split", "duplicate", "conflicting", "unknown", "low-confidence", "empty"],
)
def test_name_detection_does_not_choose_or_veto_an_icon(monkeypatch, labels):
    actual_ocr = recycling._ocr

    def read(crop, *, use_det=True):
        if use_det:
            return labels
        assert crop.ndim == 2, "Only reward quantities need recognition-only OCR"
        return actual_ocr(crop, use_det=False)

    monkeypatch.setattr(recycling, "_ocr", read)

    assert recycling.read_recycling_materials(reward_frame()) == {"装置": 1}


def test_shifted_archived_card_keeps_its_real_quantity():
    path = Path(__file__).parent / "fixtures/recycling/reward_orirock_20261030.jpg"
    original = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    image = np.zeros_like(original)
    image[430:720, 820:1100] = original[415:705, 820:1100]

    assert recycling.read_recycling_materials(image) == {"固源岩": 1}


def controlled_icon_scores(monkeypatch, scores, *, detected_name=None):
    names = list(scores)
    monkeypatch.setattr(
        recycling,
        "recycling_model",
        lambda: {"ordinary": [{"name": name} for name in names], "extra": []},
    )
    templates = {
        name: np.full((132, 220, 3), index + 1, np.uint8)
        for index, name in enumerate(names)
    }
    monkeypatch.setattr(
        recycling,
        "_material_icon",
        lambda _directory, name: (
            (templates[name], np.full((132, 220), 255, np.uint8))
            if name in templates
            else None
        ),
    )

    def match(_region, template, _method, *, mask):
        name = names[int(template[0, 0, 0]) - 1]
        result = np.zeros((29, 61), dtype=np.float64)
        if np.isfinite(scores[name]):
            result[5, 30] = scores[name]
        else:
            result.fill(scores[name])
        return result

    monkeypatch.setattr(recycling.cv2, "matchTemplate", match)
    if detected_name is not None:
        actual_ocr = recycling._ocr

        def read(crop, *, use_det=True):
            results = actual_ocr(crop, use_det=use_det)
            if use_det:
                return [(box, detected_name, score) for box, _text, score in results]
            return results

        monkeypatch.setattr(recycling, "_ocr", read)


def test_highest_of_several_qualified_templates_chooses_one_material(monkeypatch):
    controlled_icon_scores(
        monkeypatch, {"糖": 0.907, "固源岩": 0.904, "装置": 0.991}, detected_name="糖"
    )

    assert recycling.read_recycling_materials(reward_frame()) == {"装置": 1}


@pytest.mark.parametrize("score,expected", [(0.90, None), (0.9001, {"装置": 1})])
def test_icon_threshold_is_strictly_above_point_nine(monkeypatch, score, expected):
    controlled_icon_scores(monkeypatch, {"装置": score})

    assert recycling.read_recycling_materials(reward_frame()) == expected


@pytest.mark.parametrize("score", [float("nan"), float("inf")])
def test_nonfinite_icon_candidate_does_not_beat_a_finite_match(monkeypatch, score):
    controlled_icon_scores(monkeypatch, {"糖": score, "装置": 0.991})

    assert recycling.read_recycling_materials(reward_frame()) == {"装置": 1}


def test_all_nonfinite_or_below_threshold_icons_remain_unknown(monkeypatch):
    controlled_icon_scores(
        monkeypatch, {"糖": float("nan"), "固源岩": float("inf"), "装置": 0.80}
    )

    assert recycling.read_recycling_materials(reward_frame()) is None


def test_each_reward_circle_contributes_one_material(monkeypatch):
    controlled_icon_scores(
        monkeypatch, {"糖": 0.907, "固源岩": 0.904, "装置": 0.991}, detected_name="糖"
    )

    assert recycling.read_recycling_materials(multiple_reward_frame((780, 1140))) == {
        "装置": 2
    }


def test_different_materials_are_selected_at_their_own_circles():
    path = Path(__file__).parent / "fixtures/recycling/reward_sugar_20261027.jpg"
    sugar = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    image = multiple_reward_frame((780, 1140))
    image[415:705, 640:920] = sugar[415:705, 820:1100]

    assert recycling.read_recycling_materials(image) == {"糖": 1, "装置": 1}


@pytest.mark.parametrize("missing", ["icon", "quantity"])
def test_a_second_reward_with_missing_evidence_keeps_the_whole_batch_unknown(
    monkeypatch, missing
):
    image = multiple_reward_frame((780, 1140))
    circles = recycling.cv2.HoughCircles(
        cv2.cvtColor(image[280:850], cv2.COLOR_RGB2GRAY),
        cv2.HOUGH_GRADIENT,
        1.2,
        160,
        param1=100,
        param2=50,
        minRadius=85,
        maxRadius=105,
    )
    assert circles is not None and circles.shape[1] == 2
    monkeypatch.setattr(
        recycling.cv2, "HoughCircles", lambda *_args, **_kwargs: circles
    )
    if missing == "icon":
        image[415:575, 1000:1280] = 0
    else:
        image[570:625, 1000:1280] = 0

    assert recycling.read_recycling_materials(image) is None


@pytest.mark.parametrize("failure", [FileNotFoundError, ValueError, None])
def test_known_ocr_name_can_supply_an_icon_when_the_pool_is_unavailable(
    monkeypatch, failure
):
    def unavailable_model():
        if failure is not None:
            raise failure("unavailable candidate snapshot")
        return {"ordinary": [], "extra": []}

    monkeypatch.setattr(recycling, "recycling_model", unavailable_model)

    assert recycling.read_recycling_materials(reward_frame()) == {"装置": 1}


def test_material_outside_the_pool_uses_its_real_template(monkeypatch):
    monkeypatch.setattr(
        recycling,
        "recycling_model",
        lambda: {"ordinary": [{"name": "装置"}], "extra": []},
    )
    path = Path(__file__).parent / "fixtures/recycling/reward_sugar_20261027.jpg"
    sugar = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)

    assert recycling.read_recycling_materials(sugar) == {"糖": 1}


def test_invalid_pool_names_do_not_break_valid_icon_candidates(monkeypatch):
    monkeypatch.setattr(
        recycling,
        "recycling_model",
        lambda: {
            "ordinary": [{"name": name} for name in [None, 42, "不明物品", "装置"]],
            "extra": [],
        },
    )

    assert recycling.read_recycling_materials(reward_frame()) == {"装置": 1}


def test_one_missing_required_template_cannot_select_the_wrong_remaining_material(
    monkeypatch,
):
    path = Path(__file__).parent / "fixtures/recycling/reward_orirock_20261030.jpg"
    image = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    model = recycling.recycling_model()
    required_names = {item["name"] for item in model["ordinary"] + model["extra"]}
    assert "固源岩" in required_names
    directory = str(recycling._icon_directory())
    actual_icon = recycling._material_icon
    assert all(actual_icon(directory, name) is not None for name in required_names)

    def missing_only_orirock(directory, name):
        if name == "固源岩":
            return None
        return actual_icon(directory, name)

    monkeypatch.setattr(recycling, "_material_icon", missing_only_orirock)

    assert recycling.read_recycling_materials(image) is None


def test_excess_duplicate_hints_do_not_veto_a_clear_icon(monkeypatch):
    actual_ocr = recycling._ocr

    def read(crop, *, use_det=True):
        if use_det:
            return [(name_box(), "装置", 0.99)] * 65
        assert crop.ndim == 2
        return actual_ocr(crop, use_det=False)

    monkeypatch.setattr(recycling, "_ocr", read)

    assert recycling.read_recycling_materials(reward_frame()) == {"装置": 1}


@pytest.mark.parametrize(
    "left,right,top",
    [(750, 800, 32), (1195, 1205, 43), (1655, 1665, 43), (1695, 1705, 43)],
)
def test_controlled_v_hint_on_archive_background_cannot_veto_the_rock(
    monkeypatch, left, right, top
):
    path = Path(__file__).parent / "fixtures/recycling/reward_orirock_20261030.jpg"
    image = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    actual_ocr = recycling._ocr

    def read(crop, *, use_det=True):
        labels = actual_ocr(crop, use_det=use_det)
        if use_det:
            return labels + [
                ([[left, top], [right, top], [right, 64], [left, 64]], "V", 0.99)
            ]
        assert crop.ndim == 2
        return labels

    monkeypatch.setattr(recycling, "_ocr", read)

    assert recycling.read_recycling_materials(image) == {"固源岩": 1}
