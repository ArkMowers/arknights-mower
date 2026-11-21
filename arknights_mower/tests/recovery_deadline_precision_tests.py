"""恢复期限向可表示时间量化，严格回满与工作下限不共享心情容差。"""

import pickle
import threading
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import exhaust_replacement_tests
from arknights_mower.tests.calculated_mood_tests import model
from arknights_mower.tests.mood_calculation_projection_consumers_tests import enable
from arknights_mower.utils import calculated_mood, operators
from arknights_mower.utils.calculated_mood import CalculatedMood
from arknights_mower.utils.replacement_coordination import recall_can_sustain

FIXED = datetime(2026, 11, 8, 11, 17, 24, 685387)


@pytest.fixture(autouse=True)
def independent_model_cache(monkeypatch):
    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())


@pytest.mark.parametrize("upper", [12, 24])
@pytest.mark.parametrize("deficit", [1e-8, 1e-10])
def test_real_remaining_recovery_requires_positive_representable_time(
    monkeypatch, upper, deficit
):
    value = model({"机械师": upper - deficit})
    value.thresholds = [0, 12, 24]
    monkeypatch.setattr(CalculatedMood, "_rates", lambda self: {"机械师": -4})
    now = value.at
    before = pickle.dumps(value)
    due = value.deadline("机械师", upper, now)
    assert due is not None and now < due <= now + timedelta(microseconds=10)
    assert value.value("机械师", now) < upper
    assert value.value("机械师", due) >= upper
    assert pickle.dumps(value) == before


@pytest.mark.parametrize("rate", [0, None])
@pytest.mark.parametrize("upper", [12, 24])
def test_zero_or_unknown_recovery_cannot_turn_a_deficit_into_full(
    monkeypatch, upper, rate
):
    value = model({"机械师": upper - 1e-8})
    value.thresholds = [0, 12, 24]
    monkeypatch.setattr(CalculatedMood, "_rates", lambda self: {"机械师": rate})
    assert value.deadline("机械师", upper, value.at) is None


@pytest.fixture
def recall_projection(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return FIXED

    monkeypatch.setattr(exhaust_replacement_tests, "datetime", Clock)
    monkeypatch.setattr(operators, "datetime", Clock)
    solver = exhaust_replacement_tests.solver.__wrapped__(monkeypatch)
    data = solver.op_data
    enable(data, FIXED, monkeypatch)
    return solver


@pytest.mark.parametrize("offset_us", [0, 500])
@pytest.mark.parametrize("upper", [12, 24])
def test_native_complete_recall_reaches_personal_cap_without_mutating_actual_state(
    recall_projection, monkeypatch, offset_us, upper
):
    solver = recall_projection
    data = solver.op_data
    data.operators["机械师"].upper_limit = upper
    data.config.operator_mood_limits["机械师"] = {"lower": 0, "upper": upper}
    now = FIXED + timedelta(microseconds=offset_us)

    class ProjectClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(operators, "datetime", ProjectClock)
    admitted = data.project_arrangements(
        [
            {
                "room_2_2": ["苍苔"],
                "contact": ["絮雨"],
                "room_3_3": ["槐琥"],
                "dormitory_1": ["Current", "Current", "机械师", "Free", "Free"],
            }
        ]
    )
    before = {
        name: (op.mood, op.time_stamp, op.current_room, op.current_index)
        for name, op in data.operators.items()
    }
    beds = [(bed.name, bed.time) for bed in data.all_dorms()]
    queue = deepcopy(solver.tasks)
    due = admitted.calculated_mood_deadline("机械师", upper, now)
    assert due is not None
    assert admitted.calculated_mood("机械师", due) >= upper
    assert recall_can_sustain(data, admitted, ["苍苔", "絮雨"], ["机械师"], now=now)
    assert before == {
        name: (op.mood, op.time_stamp, op.current_room, op.current_index)
        for name, op in data.operators.items()
    }
    assert beds == [(bed.name, bed.time) for bed in data.all_dorms()]
    assert [vars(task) for task in solver.tasks] == [vars(task) for task in queue]


@pytest.mark.parametrize("upper", [12, 24])
def test_recovery_deadline_does_not_authorize_a_real_deficit_before_horizon(
    monkeypatch, upper
):
    value = model({"机械师": upper - 0.001})
    value.thresholds = [0, 12, 24]
    monkeypatch.setattr(CalculatedMood, "_rates", lambda self: {"机械师": -4})
    due = value.deadline("机械师", upper, value.at)
    assert due is not None and due >= value.at + timedelta(milliseconds=900)
    assert value.value("机械师", value.at + timedelta(milliseconds=899)) < upper
    assert value.deadline("机械师", upper, value.at, max_hours=0.5 / 3600) is None


@pytest.mark.parametrize("upper", [12, 24])
def test_recovery_microsecond_rounding_respects_exact_query_horizon(monkeypatch, upper):
    value = model({"机械师": upper - 1e-10})
    value.thresholds = [0, 12, 24]
    monkeypatch.setattr(CalculatedMood, "_rates", lambda self: {"机械师": -4})
    assert value.deadline(
        "机械师", upper, value.at, max_hours=1 / 3_600_000_000
    ) == value.at + timedelta(microseconds=1)
    assert value.deadline("机械师", upper, value.at, max_hours=0) is None


@pytest.mark.parametrize("upper", [12, 24])
@pytest.mark.parametrize("coincident_floor", [False, True])
def test_recovery_and_work_deadlines_are_independent_of_query_order(
    monkeypatch, upper, coincident_floor
):
    start_mood = 0.123456789
    work_mood = (upper - start_mood) / 4.55 * 0.95 if coincident_floor else 13.000000123
    value = model({"机械师": start_mood, "陈": work_mood})
    value.at = FIXED
    value.thresholds = [0, 12, 24]
    monkeypatch.setattr(
        CalculatedMood, "_rates", lambda self: {"机械师": -4.55, "陈": 0.95}
    )
    results = []
    before = pickle.dumps(value)
    for order in (("机械师", "陈"), ("陈", "机械师")):
        monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
        dates = {
            name: value.deadline(name, upper if name == "机械师" else 0, FIXED)
            for name in order
        }
        other_upper = 12 if upper == 24 else 24
        dates[f"cap-{other_upper}"] = value.deadline("机械师", other_upper, FIXED)
        assert value.value("机械师", dates[f"cap-{other_upper}"]) >= other_upper
        assert value.value("机械师", dates["机械师"]) >= upper
        assert value.value("陈", dates["陈"]) <= 1e-7
        if coincident_floor:
            assert dates["陈"] <= dates["机械师"]
            assert value.value("陈", dates["机械师"]) == 0
        results.append(dates)
    assert results[0] == results[1]
    assert pickle.dumps(value) == before


@pytest.mark.parametrize("cover_mood", [0, 1])
def test_real_native_recall_still_rejects_working_floor_exhaustion(
    recall_projection, cover_mood
):
    data = recall_projection.op_data
    admitted = data.project_arrangements(
        [
            {
                "room_2_2": ["苍苔"],
                "contact": ["絮雨"],
                "room_3_3": ["槐琥"],
                "dormitory_1": ["Current", "Current", "机械师", "Free", "Free"],
            }
        ],
        now=FIXED,
    )
    for name in ("苍苔", "絮雨"):
        data.operators[name].mood = cover_mood
        data.mood_model.observe(name, cover_mood, FIXED)
        admitted.operators[name].mood = cover_mood
        admitted.mood_model.observe(name, cover_mood, FIXED)
    assert not recall_can_sustain(
        data, admitted, ["苍苔", "絮雨"], ["机械师"], now=FIXED
    )


@pytest.mark.parametrize("rate", [0, None])
@pytest.mark.parametrize("upper", [12, 24])
def test_known_zero_rate_keeps_full_evidence_but_unknown_rate_does_not(
    monkeypatch, upper, rate
):
    value = model({"机械师": upper})
    value.thresholds = [0, 12, 24]
    monkeypatch.setattr(CalculatedMood, "_rates", lambda self: {"机械师": rate})
    assert value.deadline("机械师", upper, value.at) == (
        value.at if rate == 0 else None
    )
