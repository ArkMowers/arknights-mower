"""召回估算只复用实测速率，并隔离普通恢复与单回恢复记录。"""

from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from arknights_mower.tests import native_group_recovery_sync_tests as native
from arknights_mower.utils.dorm_recovery import recovery_managers
from arknights_mower.utils.operators import Dormitory, Operator, Operators
from arknights_mower.utils.recall_estimates import (
    estimated_recall_rates,
    observe_recovery_rate,
)

solver = native.solver
resting = native.resting


@pytest.fixture(autouse=True)
def no_action_database(monkeypatch):
    from arknights_mower.solvers import record

    monkeypatch.setattr(record, "save_agent_action", lambda *args, **kwargs: None)


def test_observed_work_rate_survives_rest_and_return(solver):
    data = solver.op_data
    op = data.operators["伊内丝"]
    op.mood, op.time_stamp = 20, datetime.now() - timedelta(hours=2)
    data.update_detail(op.name, 16, "meeting", 0, True)
    observed_rate = op.recall_work_rate[0]
    assert observed_rate == pytest.approx(2, abs=0.001)
    data.update_detail(op.name, 16, "dormitory_1", 2, False)
    data.update_detail(op.name, 20, "meeting", 0, True)
    assert op.depletion_rate == 0
    work, _ = estimated_recall_rates(data, data.project_arrangements([]))
    assert work[op.name] == observed_rate
    data.shadow_copy = data.operators.copy()
    replacement = Operator(op.name, "meeting", 0)
    data.add(replacement)
    assert data.operators[op.name].recall_work_rate == op.recall_work_rate


@pytest.mark.parametrize(
    "invalid",
    ["prediction", "future", "short", "nan", "flat", "preserve", "moved"],
)
def test_invalid_work_observation_does_not_create_estimate(solver, invalid):
    data = solver.op_data
    op = data.operators["伊内丝"]
    op.mood, op.time_stamp = 20, datetime.now() - timedelta(hours=2)
    op.depletion_rate = 0
    if invalid == "prediction":
        op.mood_is_prediction = True
    elif invalid == "future":
        op.time_stamp = datetime.now() + timedelta(hours=2)
    elif invalid == "short":
        op.time_stamp = datetime.now() - timedelta(minutes=10)
    data.update_detail(
        op.name,
        float("nan") if invalid == "nan" else 20 if invalid == "flat" else 16,
        "central" if invalid == "moved" else "meeting",
        0,
        True,
        preserve_depletion_rate=invalid == "preserve",
    )
    work, _ = estimated_recall_rates(data, data)
    assert op.name not in work


@pytest.mark.parametrize("rate", [0, -1, float("nan"), float("inf"), 2])
def test_legacy_work_reading_warms_only_positive_rate(solver, rate):
    data = solver.op_data
    op = data.operators["伊内丝"]
    op.depletion_rate = rate
    work, _ = estimated_recall_rates(data, data)
    assert (op.name in work) == (rate == 2)


@pytest.fixture
def sampled_dorm(resting):
    instance, now = resting
    data = instance.op_data
    data.operators["冰酿"].current_room = ""
    data.add(Operator("琴柳", "", current_room="dormitory_1", current_index=1))
    names = [data.get_current_operator("dormitory_1", i).name for i in range(5)]
    for name in ("伊内丝", "银灰", "讯使"):
        op = data.operators[name]
        op.mood, op.time_stamp = 12, now
        data.get_dorm_by_name(name)[1].time = now + timedelta(hours=6)
    single = data.operators["伊内丝"]
    single.dorm_recovery_room = single.current_room
    single.dorm_recovery_index = single.current_index
    single.dorm_recovery_fixed = recovery_managers(data, "dormitory_1", names)
    data.get_dorm_by_name(single.name)[1].time = now + timedelta(hours=3)
    return data, now


def test_current_beds_warm_distinct_roles_without_mutating_observations(sampled_dorm):
    data, now = sampled_dorm
    before = deepcopy(data)
    _, recovery = estimated_recall_rates(data, data.project_arrangements([]), now)
    assert recovery["伊内丝"] == 4
    assert recovery["银灰"] == recovery["讯使"] == 2
    assert data.recall_recovery_rates == {}
    for name, op in data.operators.items():
        previous = before.operators[name]
        assert (op.mood, op.time_stamp, op.current_room, op.current_index) == (
            previous.mood,
            previous.time_stamp,
            previous.current_room,
            previous.current_index,
        )
    assert [(bed.name, bed.time) for bed in data.all_dorms()] == [
        (bed.name, bed.time) for bed in before.all_dorms()
    ]


def test_unconfirmed_single_never_supplies_ordinary_rate(sampled_dorm):
    data, now = sampled_dorm
    data.operators["伊内丝"].clear_dorm_recovery()
    _, recovery = estimated_recall_rates(data, data.project_arrangements([]), now)
    assert recovery == {}
    data.recall_recovery_rates[("dormitory_1", "ordinary")] = (2, now)
    _, recovery = estimated_recall_rates(data, data.project_arrangements([]), now)
    assert recovery["伊内丝"] == 2
    assert recovery["银灰"] == 2


def test_current_ordinary_samples_use_slowest_observed_rate(sampled_dorm):
    data, now = sampled_dorm
    data.get_dorm_by_name("讯使")[1].time = now + timedelta(hours=4)
    observe_recovery_rate(data, data.get_dorm_by_name("讯使")[1], now=now)
    assert data.recall_recovery_rates[("dormitory_1", "ordinary")][0] == 2
    assert estimated_recall_rates(data, data, now)[1]["讯使"] == 2


def test_single_history_never_fills_ordinary_or_other_dorm(sampled_dorm):
    data, now = sampled_dorm
    bed = data.get_dorm_by_name("伊内丝")[1]
    observe_recovery_rate(data, bed, now=now)
    for entry in data.all_dorms():
        entry.time = None
    _, recovery = estimated_recall_rates(data, data, now)
    assert recovery["伊内丝"] == 4
    assert "银灰" not in recovery
    data.recall_recovery_rates = {("dormitory_2", "ordinary"): (2, now)}
    assert estimated_recall_rates(data, data, now)[1] == {}


@pytest.mark.parametrize("invalid", ["prediction", "future", "past", "full", "nan"])
def test_invalid_recovery_sample_is_ignored(sampled_dorm, invalid):
    data, now = sampled_dorm
    op = data.operators["银灰"]
    bed = data.get_dorm_by_name(op.name)[1]
    if invalid == "prediction":
        op.mood_is_prediction = True
    elif invalid == "future":
        op.time_stamp = now + timedelta(hours=1)
    elif invalid == "past":
        bed.time = now - timedelta(hours=1)
    elif invalid == "full":
        op.mood = op.upper_limit
    elif invalid == "nan":
        op.mood = float("nan")
    observe_recovery_rate(data, bed, now=now)
    assert data.recall_recovery_rates == {}


def test_real_deadline_reader_uses_personal_limit_and_projection_isolation(
    sampled_dorm,
):
    data, now = sampled_dorm
    op = data.operators["银灰"]
    op.upper_limit = 20
    bed = data.get_dorm_by_name(op.name)[1]
    bed.time = None
    data.refresh_dorm_time(
        op.current_room,
        op.current_index,
        {"agent": op.name, "time": now + timedelta(hours=6)},
    )
    assert bed.time == now + timedelta(hours=4)
    assert data.recall_recovery_rates[("dormitory_1", "ordinary")][0] == 2
    projected = data.project_arrangements([])
    projected.recall_recovery_rates[("dormitory_1", "ordinary")] = (3, now)
    assert data.recall_recovery_rates[("dormitory_1", "ordinary")][0] == 2


def test_recovery_history_is_bounded(sampled_dorm):
    data, now = sampled_dorm
    data.recall_recovery_rates = {
        (f"dormitory_{i}", "ordinary"): (2, now - timedelta(hours=i))
        for i in range(2, 10)
    }
    observe_recovery_rate(data, data.get_dorm_by_name("银灰")[1], now=now)
    assert len(data.recall_recovery_rates) == 8
    assert ("dormitory_9", "ordinary") not in data.recall_recovery_rates
    assert ("dormitory_1", "ordinary") in data.recall_recovery_rates


def test_lightweight_room_reader_keeps_deadline_without_sampling():
    now = datetime.now()
    bed = Dormitory(("dormitory_1", 0))
    op = SimpleNamespace(mood=12, upper_limit=20, time_stamp=now)
    reader = SimpleNamespace(
        dorm=[bed],
        operators={"银灰": op},
        true_exhaust_room=set(),
        is_dynamic_dorm_position=lambda *args, **kwargs: True,
    )
    Operators.refresh_dorm_time(
        reader,
        "dormitory_1",
        0,
        {"agent": "银灰", "time": now + timedelta(hours=6)},
    )
    assert bed.time == now + timedelta(hours=4)
    assert not hasattr(reader, "recall_recovery_rates")
