from pathlib import Path

import cv2
import numpy as np
import pytest

from arknights_mower.utils import character_recognize as recognition


def test_same_pixels_reuse_name_but_changed_pixels_are_matched(monkeypatch):
    recognition._match_name_template.cache_clear()
    monkeypatch.setattr(
        recognition, "OP_SELECT", {"甲": np.zeros((2, 2), dtype=np.uint8)}
    )
    calls = []

    def match(image, template, method):
        calls.append(image.copy())
        return np.array([[0.9]], dtype=np.float32)

    monkeypatch.setattr(recognition.cv2, "matchTemplate", match)
    pixels = np.zeros((4, 4), dtype=np.uint8)
    for _ in range(2):
        assert (
            recognition._match_name_template(False, pixels.shape, pixels.tobytes())
            == "甲"
        )
    assert len(calls) == 1
    pixels[0, 0] = 255
    recognition._match_name_template(False, pixels.shape, pixels.tobytes())
    assert len(calls) == 2
    recognition._match_name_template.cache_clear()


def test_training_and_resource_reload_do_not_reuse_other_model(monkeypatch):
    recognition._match_name_template.cache_clear()
    template = np.ones((2, 2), dtype=np.uint8)
    pixels = np.ones((4, 4), dtype=np.uint8)
    monkeypatch.setattr(recognition, "OP_SELECT", {"甲": template})
    monkeypatch.setattr(recognition, "OP_TRAIN", {"乙": template})
    args = pixels.shape, pixels.tobytes()
    assert recognition._match_name_template(False, *args) == "甲"
    assert recognition._match_name_template(True, *args) == "乙"
    assert recognition._match_name_template(True, *args, right_align=True) == "乙"
    monkeypatch.setattr(
        recognition, "_load_models", lambda: ({"丙": template}, {"丁": template})
    )
    recognition.reload_resource_models()
    assert recognition._match_name_template(False, *args) == "丙"
    assert recognition._match_name_template(True, *args) == "丁"
    assert recognition._match_name_template(True, *args, right_align=True) == "丁"
    recognition._match_name_template.cache_clear()


def test_cache_keeps_original_matching_threshold(monkeypatch):
    recognition._match_name_template.cache_clear()
    monkeypatch.setattr(
        recognition, "OP_SELECT", {"甲": np.zeros((2, 2), dtype=np.uint8)}
    )
    monkeypatch.setattr(
        recognition.cv2,
        "matchTemplate",
        lambda *args: np.array([[0.5]], dtype=np.float32),
    )
    assert recognition._match_name_template(False, (4, 4), bytes(16)) == ""
    recognition._match_name_template.cache_clear()


@pytest.fixture
def field_model():
    recognition._name_field_templates.cache_clear()
    recognition._match_name_field_template.cache_clear()
    yield
    recognition._name_field_templates.cache_clear()
    recognition._match_name_field_template.cache_clear()


def test_full_name_field_cache_is_invalidated_by_resource_reload(
    monkeypatch, field_model
):
    image = cv2.imread(str(Path(__file__).parent / "fixtures/trust_name_clemensa.png"))
    image = cv2.cvtColor(image[5:50], cv2.COLOR_BGR2RGB)
    template = recognition.OP_SELECT["克莱门莎"]
    monkeypatch.setattr(recognition, "OP_SELECT", {"克莱门莎": template})
    monkeypatch.setattr(recognition, "OP_TRAIN", {})
    assert recognition.match_operator_name(image, dark_text=True) == "克莱门莎"
    monkeypatch.setattr(
        recognition, "_load_models", lambda: ({"资源更新": template}, {})
    )
    recognition.reload_resource_models()
    assert recognition.match_operator_name(image, dark_text=True) == "资源更新"


def test_ambiguous_full_name_field_remains_unknown(monkeypatch, field_model):
    image = cv2.imread(str(Path(__file__).parent / "fixtures/trust_name_clemensa.png"))
    image = cv2.cvtColor(image[5:50], cv2.COLOR_BGR2RGB)
    template = recognition.OP_SELECT["克莱门莎"]
    monkeypatch.setattr(recognition, "OP_SELECT", {"甲": template, "乙": template})
    assert recognition.match_operator_name(image, dark_text=True) == ""


@pytest.mark.parametrize(
    "overlaps",
    [(599,), (600,), (601,), (749, 700), (750, 700), (751, 700)],
)
def test_name_field_preserves_opencv_decisions_at_cutoffs(
    monkeypatch, field_model, overlaps
):
    rng = np.random.default_rng(802)
    positions = rng.permutation(42 * 200)
    sample = np.zeros((42, 200), np.uint8)
    sample.flat[positions[:1000]] = 255
    padded = np.pad(sample, 2)
    templates = {}
    scores = []
    for overlap in overlaps:
        template = np.zeros_like(sample)
        template.flat[positions[:overlap]] = 255
        template.flat[positions[1000 : 2000 - overlap]] = 255
        name = str(overlap)
        templates[name] = template
        score = float(cv2.matchTemplate(padded, template, cv2.TM_CCORR_NORMED).max())
        assert score == pytest.approx(overlap / 1000, abs=0.00001)
        scores.append((score, name))
    scores.sort(reverse=True)
    expected = scores[0][1] if scores[0][0] > 0.6 else ""
    if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.05:
        expected = ""
    monkeypatch.setattr(recognition, "OP_SELECT", templates)
    monkeypatch.setattr(recognition, "_normalize_name_field", lambda *_: padded)
    image = cv2.cvtColor(padded, cv2.COLOR_GRAY2RGB)
    assert recognition.match_operator_name(image) == expected


@pytest.mark.parametrize("intensity,crop", [(180, False), (255, True)])
def test_name_field_accepts_other_resource_template_formats(
    monkeypatch, field_model, intensity, crop
):
    image = cv2.imread(str(Path(__file__).parent / "fixtures/trust_name_clemensa.png"))
    image = cv2.cvtColor(image[5:50], cv2.COLOR_BGR2RGB)
    template = recognition.OP_SELECT["克莱门莎"].copy()
    if crop:
        template = template[:, :-1]
    template[template > 0] = intensity
    monkeypatch.setattr(recognition, "OP_SELECT", {"克莱门莎": template})
    assert recognition.match_operator_name(image, dark_text=True) == "克莱门莎"
