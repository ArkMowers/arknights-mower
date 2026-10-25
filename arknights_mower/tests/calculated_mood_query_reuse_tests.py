"""同刻查询和分段目标到达复用已知速率，保留观测及技能边界。"""

import pickle
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from arknights_mower.utils import calculated_mood
from arknights_mower.utils.resting_priority import has_resting_mood, resting_mood

NOW = datetime(2026, 10, 25, 3)


def model(monkeypatch):
    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    calls = []

    def rates(payload):
        calls.append(dict(payload["moods"]))
        return {
            "rates": {
                "worker": 1 if payload["moods"]["provider"] > 0 else 2,
                "provider": 1,
            },
            "thresholds": [0, 12, 24],
            "automaticTargets": {},
        }

    monkeypatch.setattr(calculated_mood, "shared_rates", rates)
    value = calculated_mood.CalculatedMood()
    value.at = NOW
    value.moods = {"worker": 24, "provider": 4}
    return value, calls


def test_current_value_reuses_valid_rates_without_copy_or_mutation(monkeypatch):
    value, calls = model(monkeypatch)
    value._rates()
    before = pickle.dumps(value)
    monkeypatch.setattr(
        calculated_mood.CalculatedMood,
        "__deepcopy__",
        lambda *args: pytest.fail("同刻已知速率不应复制模型"),
    )
    assert value.value("worker", NOW) == 24
    assert len(calls) == 1
    assert pickle.dumps(value) == before


def test_target_deadline_stops_before_calculating_post_target_rates(monkeypatch):
    value, calls = model(monkeypatch)
    before = pickle.dumps(value)
    # 前四小时消耗 4，提供技能者耗尽后以每小时 2 到达目标 12。
    assert value.deadline("worker", 12, NOW) == NOW + timedelta(hours=8)
    assert len(calls) == 2
    assert pickle.dumps(value) == before
    # 后续目标仍须跨过 12 的边界，不把较早目标当作最终轨迹。
    assert value.deadline("worker", 0, NOW) == NOW + timedelta(hours=14)
    assert len(calls) == 3
    assert value.deadline("worker", 0, NOW, max_hours=13) is None
    assert value.deadline("worker", -1, NOW) is None


def test_unknown_name_does_not_construct_a_forecast(monkeypatch):
    value, calls = model(monkeypatch)
    assert value.value("unknown", NOW + timedelta(hours=2)) is None
    assert value.deadline("unknown", 0, NOW) is None
    assert calls == []


def test_recovery_helpers_read_the_projection_clock_without_advancing_live_time(
    monkeypatch,
):
    value, _ = model(monkeypatch)
    value.enabled = True
    value._rates()
    op = SimpleNamespace(
        name="worker",
        current_room="dormitory_1",
        _mood_model=value,
        _mood_conf=SimpleNamespace(test_mood_calculation=True),
        _projection_now=NOW,
    )

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW + timedelta(hours=20)

    monkeypatch.setattr(calculated_mood, "datetime", Clock)
    before = pickle.dumps(value)
    assert has_resting_mood(op)
    assert resting_mood(op) == 24
    assert pickle.dumps(value) == before
