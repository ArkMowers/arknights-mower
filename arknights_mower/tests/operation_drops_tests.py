"""Offline settlement crops: real icon/count evidence and rejection boundaries."""

from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.utils import operation_drops as drops


@pytest.fixture(scope="module")
def templates():
    return drops._templates(str(drops._icon_directory()))


@pytest.fixture(scope="module")
def ocr():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR(text_score=0.3)


def frame(name):
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    path = Path(__file__).parent / "fixtures/operation_drops" / f"{name}.png"
    image[500:670] = cv2.imread(str(path))
    return image


@pytest.mark.parametrize(
    "fixture,left,name,quantity",
    [
        ("go8_single", 67, "龙门币", 252),
        ("go8_single", 220, "凝胶", 1),
        ("go8_batch2", 67, "龙门币", 504),
        ("go8_batch2", 358, "凝胶", 1),
    ],
)
def test_real_settlement_slots(
    fixture, left, name, quantity, templates, ocr, monkeypatch
):
    monkeypatch.setattr(drops.rapidocr, "engine", ocr)
    image = frame(fixture)
    assert drops._read_icon(image, left, templates) == name
    assert drops._read_quantity(image, left) == quantity


def test_unknown_historical_event_token_rejects_entire_batch(ocr, monkeypatch):
    monkeypatch.setattr(drops.rapidocr, "engine", ocr)
    image = cv2.cvtColor(
        cv2.resize(frame("go8_batch2"), (1920, 1080)), cv2.COLOR_BGR2RGB
    )
    assert drops.read_operation_drops(image, "GO-8") is None


def test_batch_quantities_are_not_multiplied(monkeypatch):
    # Controlled geometry uses the real settlement separator layout; slot
    # identity/count are supplied so aggregation is independent of OCR here.
    image = cv2.cvtColor(
        cv2.resize(frame("go8_batch2"), (1920, 1080)), cv2.COLOR_BGR2RGB
    )
    monkeypatch.setattr(drops, "_templates", lambda *args: [object()])
    monkeypatch.setattr(drops.rapidocr, "engine", object())
    monkeypatch.setattr(
        drops, "_read_icon", lambda image, left, _: "龙门币" if left == 67 else "凝胶"
    )
    monkeypatch.setattr(
        drops, "_read_quantity", lambda image, left: 504 if left == 67 else 1
    )
    assert drops.read_operation_drops(image, "GO-8") == {"龙门币": 504, "凝胶": 2}


@pytest.mark.parametrize(
    "text,score", [("I", 1), ("1.2万", 1), ("12", 0.89), ("0", 1), ("12", float("nan"))]
)
def test_uncertain_or_abbreviated_quantity_is_not_estimated(text, score, monkeypatch):
    monkeypatch.setattr(
        drops.rapidocr, "engine", Mock(return_value=([(text, score)], None))
    )
    assert drops._read_quantity(frame("go8_batch2"), 67) is None


def test_clipped_quantity_is_rejected(monkeypatch):
    image = frame("go8_batch2")
    image[600:615, 82:87] = 255
    engine = Mock()
    monkeypatch.setattr(drops.rapidocr, "engine", engine)
    assert drops._read_quantity(image, 67) is None
    engine.assert_not_called()


@pytest.mark.parametrize("shape", [(720, 1280, 3), (1080, 1920), (1080, 1920, 4)])
def test_nonstandard_frame_rejected(shape):
    assert drops.read_operation_drops(np.zeros(shape, dtype=np.uint8)) is None


def test_unsupported_or_missing_separator_layout_rejected():
    image = frame("go8_batch2")
    image[636:638] = 0
    assert drops._slot_positions(image) is None
    image[636:638, 67:1279] = 255
    assert drops._slot_positions(image) is None


def test_missing_selected_resources_do_not_fall_back(monkeypatch, tmp_path):
    selected = tmp_path / "selected" / "depot"
    monkeypatch.setattr(drops, "resource_ui_path", lambda _: selected)
    assert drops._icon_directory() == selected
    assert drops._templates(str(selected)) == []


def test_complete_known_row_uses_real_icons_and_ocr(monkeypatch, ocr):
    monkeypatch.setattr(drops.rapidocr, "engine", ocr)
    image = frame("go8_single")
    # Construct a two-item row from the original known material cells. The
    # unavailable historical event currency is deliberately removed, not mocked.
    image[:, 358:] = 0
    image = cv2.cvtColor(cv2.resize(image, (1920, 1080)), cv2.COLOR_BGR2RGB)
    assert drops.read_operation_drops(image, "GO-8") == {"龙门币": 252, "凝胶": 1}


@pytest.mark.parametrize("text", ["1234", "12345"])
def test_complete_count_band_includes_leading_digits(text, monkeypatch):
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    left = 67
    # Synthetic separated glyphs retain real settlement count geometry. The
    # first digit is outside the former left+70 crop with black space after it.
    for index in range(len(text)):
        x = left + 38 + index * 10
        image[600:614, x : x + 6] = 255
    engine = Mock(return_value=([(text, 1)], None))
    monkeypatch.setattr(drops.rapidocr, "engine", engine)
    assert drops._read_quantity(image, left) == int(text)
    assert engine.call_args.args[0].shape[1] > (len(text) * 10) * 3


def test_clipped_short_rightmost_slot_rejects_row():
    image = frame("go8_single")
    image[636:638, 1200:] = 255
    assert drops._slot_positions(image) is None


@pytest.mark.parametrize("width", [8, 50, 80, 99])
def test_incomplete_additional_slot_is_not_silently_dropped(width):
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[636:638, 67:205] = 255
    image[636:638, 220 : 220 + width] = 255
    assert drops._slot_positions(image) is None


def test_nonstandard_pixel_dtype_is_rejected():
    assert drops.read_operation_drops(np.zeros((1080, 1920, 3))) is None


def test_unicode_icon_filename_and_corrupt_resource(tmp_path):
    source = Path(drops._icon_directory()) / "龙门币.webp"
    target = tmp_path / "龙门币.webp"
    target.write_bytes(source.read_bytes())
    assert drops._templates(str(tmp_path))[0][0] == "龙门币"
    drops._templates.cache_clear()
    target.write_bytes(b"broken image")
    assert drops._templates(str(tmp_path)) == []


def test_unreadable_resource_refuses_templates(monkeypatch, tmp_path):
    (tmp_path / "龙门币.webp").touch()

    def denied(*args, **kwargs):
        raise OSError("unreadable resource")

    monkeypatch.setattr(drops.np, "fromfile", denied)
    assert drops._templates(str(tmp_path)) == []
