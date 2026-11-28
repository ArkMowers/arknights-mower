"""重复心情查询保持技能边界和模型隔离。"""

import copy
import pickle
import threading
from datetime import timedelta

import pytest

from arknights_mower.tests.calculated_mood_tests import NOW, central_model
from arknights_mower.utils import calculated_mood


def test_repeated_rates_follow_in_place_mood_changes(monkeypatch):
    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    value = central_model()
    assert value._rates()["桃金娘"] == pytest.approx(0.7)
    assert value._rates()["桃金娘"] == pytest.approx(0.7)
    value.moods["阿米娅"] = 0
    assert value._rates()["桃金娘"] == pytest.approx(0.75)
    value.moods["阿米娅"] = 1
    assert value._rates()["桃金娘"] == pytest.approx(0.7)


def test_equal_moods_in_different_rooms_keep_independent_rates(monkeypatch):
    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    working = central_model()
    resting = copy.deepcopy(working)
    resting.rooms.pop("room_1_1")
    resting.rooms["dormitory_1"] = {"roster": ["桃金娘"], "level": 5}
    assert working._rates()["桃金娘"] == pytest.approx(0.7)
    assert resting._rates()["桃金娘"] == pytest.approx(-4.15)
    assert working._rates()["桃金娘"] == pytest.approx(0.7)


def test_repeated_forecasts_preserve_serialized_source_and_copy_isolation(monkeypatch):
    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    value = central_model()
    before = pickle.dumps(value)
    future = NOW + timedelta(hours=1)
    assert value.value("桃金娘", future) == pytest.approx(23.3)
    projected = copy.deepcopy(value)
    projected.moods["阿米娅"] = 0
    assert projected.value("桃金娘", future) == pytest.approx(23.25)
    assert value.value("桃金娘", future) == pytest.approx(23.3)
    assert pickle.dumps(value) == before


def test_band_reuse_tracks_threshold_replacement_and_in_place_changes(monkeypatch):
    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    value = central_model()
    value.thresholds = [0, 24]
    original = value._signature(value.moods)
    value.thresholds.insert(1, 1)
    boundary = value._signature(value.moods)
    assert boundary != original
    value.thresholds = [0, 24]
    assert value._signature(value.moods) == original
