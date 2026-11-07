"""回收站拒绝部分奖励读数，并保留有界的 OCR 候选证据。"""

from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.tests.recycling_collection_tests import (
    multiple_reward_frame,
    recycling,
    reward_frame,
)
from arknights_mower.utils.rapidocr import _LocalOCREngine


@pytest.fixture(scope="module")
def local_ocr():
    return _LocalOCREngine()


@pytest.fixture(autouse=True)
def recognition_engine(monkeypatch, local_ocr):
    monkeypatch.setattr(recycling.rapidocr, "engine", local_ocr)


def background_text_frame(centers=(960,)):
    image = multiple_reward_frame(centers)
    # 合成可识别的牌外文字，不声称它就是现场未保存的第二个标签。
    cv2.putText(
        image,
        "HELLO",
        (160, 680),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return image


@pytest.mark.parametrize("centers", [(960,), (780, 1140)])
def test_real_ocr_extra_text_without_an_icon_does_not_veto_the_batch(centers):
    image = background_text_frame(centers)
    before = image.copy()
    raw_labels = recycling._ocr(image[640:705])
    texts = [text for _box, text, confidence in raw_labels if confidence >= 0.90]
    assert texts.count("HELLO") == 1
    assert texts.count("装置") == len(centers)

    assert recycling.read_recycling_materials(image) == {"装置": len(centers)}

    assert np.array_equal(image, before)


def test_archived_orirock_frame_remains_a_positive_example():
    path = Path(__file__).parent / "fixtures/recycling/reward_orirock_20261030.jpg"
    image = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)

    assert recycling.read_recycling_materials(image) == {"固源岩": 1}


def test_missing_circle_cannot_hide_a_second_real_name_plate(monkeypatch):
    image = background_text_frame((780, 1140))
    circles = recycling.cv2.HoughCircles
    observed = circles(
        cv2.cvtColor(image[280:850], cv2.COLOR_RGB2GRAY),
        cv2.HOUGH_GRADIENT,
        1.2,
        160,
        param1=100,
        param2=50,
        minRadius=85,
        maxRadius=105,
    )
    assert observed is not None and observed.shape[1] == 2

    def miss_one_in_the_full_row(gray, *args, **kwargs):
        if gray.shape == (570, 1920):
            return observed[:, :1]
        return circles(gray, *args, **kwargs)

    monkeypatch.setattr(recycling.cv2, "HoughCircles", miss_one_in_the_full_row)

    assert recycling.read_recycling_materials(image) is None


def test_extra_circle_without_a_real_name_plate_is_not_a_reward(monkeypatch):
    image = reward_frame()
    circles = np.array([[[960, 250, 95], [400, 250, 95]]], dtype=np.float32)
    monkeypatch.setattr(
        recycling.cv2, "HoughCircles", lambda *_args, **_kwargs: circles
    )

    assert recycling.read_recycling_materials(image) is None


def missing_right_geometry_frame(monkeypatch):
    image = multiple_reward_frame((780, 1140))
    right_plate = image[640:705, 1000:1280]
    bright_text = cv2.cvtColor(right_plate, cv2.COLOR_RGB2GRAY) > 180
    right_plate[~bright_text] = 0
    circles = recycling.cv2.HoughCircles
    observed = circles(
        cv2.cvtColor(image[280:850], cv2.COLOR_RGB2GRAY),
        cv2.HOUGH_GRADIENT,
        1.2,
        160,
        param1=100,
        param2=50,
        minRadius=85,
        maxRadius=105,
    )
    assert observed is not None and observed.shape[1] == 2
    left_circle = observed[:, [int(np.argmin(observed[0, :, 0]))]]

    def miss_one_in_the_full_row(gray, *args, **kwargs):
        if gray.shape == (570, 1920):
            return left_circle
        return circles(gray, *args, **kwargs)

    monkeypatch.setattr(recycling.cv2, "HoughCircles", miss_one_in_the_full_row)
    return image


def test_missing_plate_edges_and_circle_never_erase_a_readable_second_reward(
    monkeypatch,
):
    image = missing_right_geometry_frame(monkeypatch)
    labels = recycling._ocr(image[640:705])
    assert [text for _box, text, confidence in labels if confidence >= 0.90] == [
        "装置",
        "装置",
    ]

    assert recycling.read_recycling_materials(image) is None


@pytest.mark.parametrize("text,confidence", [("未知材料", 0.99), ("装置", 0.5)])
def test_unknown_second_reward_cannot_be_discarded_with_its_missing_geometry(
    monkeypatch, text, confidence
):
    image = missing_right_geometry_frame(monkeypatch)
    actual_ocr = recycling._ocr

    def faulty_name(crop, *, use_det=True):
        results = actual_ocr(crop, use_det=use_det)
        if not use_det:
            return results
        return [
            (box, text, confidence)
            if min(point[0] for point in box) > 1000
            else (box, original, score)
            for box, original, score in results
        ]

    monkeypatch.setattr(recycling, "_ocr", faulty_name)
    labels = recycling._ocr(image[640:705])
    assert len(labels) == 2
    assert any(
        candidate == text and score == confidence for _box, candidate, score in labels
    )

    assert recycling.read_recycling_materials(image) is None


def test_uncertain_icon_preserves_conflicting_name_candidates(monkeypatch):
    box = [[925, 12], [997, 12], [997, 48], [925, 48]]
    ocr = Mock(return_value=[(box, "装置", 0.99), (box, "糖", 0.98)])
    monkeypatch.setattr(recycling, "_ocr", ocr)
    monkeypatch.setattr(
        recycling.cv2,
        "HoughCircles",
        lambda *_args, **_kwargs: np.array([[[960, 250, 95]]]),
    )
    log = Mock()
    monkeypatch.setattr(recycling, "logger", log)

    image = reward_frame()
    image[415:570] = 0
    assert recycling.read_recycling_materials(image) is None

    ocr.assert_called_once()
    details = log.debug.call_args.args[2]
    assert details["candidates"] == [
        {"text": "装置", "confidence": 0.99, "box": box},
        {"text": "糖", "confidence": 0.98, "box": box},
    ]


def test_rejected_ocr_candidates_have_bounded_text_and_coordinates(monkeypatch):
    box = np.arange(12, dtype=np.float32).reshape(6, 2)
    labels = [(box, str(index) + "字" * 120, np.float32(0.95)) for index in range(65)]
    monkeypatch.setattr(recycling, "_ocr", Mock(return_value=labels))
    monkeypatch.setattr(
        recycling.cv2,
        "HoughCircles",
        lambda *_args, **_kwargs: np.array([[[960, 250, 95]]]),
    )
    log = Mock()
    monkeypatch.setattr(recycling, "logger", log)

    image = reward_frame()
    image[415:570] = 0
    assert recycling.read_recycling_materials(image) is None

    details = log.debug.call_args.args[2]
    candidates = details["candidates"]
    assert len(candidates) == 8
    for index, candidate in enumerate(candidates):
        assert candidate["text"] == str(index) + "字" * 79
        assert type(candidate["confidence"]) is float
        assert candidate["confidence"] == pytest.approx(0.95)
        assert candidate["box"] == [[0, 1], [2, 3], [4, 5], [6, 7]]
