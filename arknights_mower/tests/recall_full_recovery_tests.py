"""普通救急召回必须支撑连接主班回满，既有事件不缩短恢复期限。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import exhaust_replacement_tests
from arknights_mower.tests.mood_calculation_projection_consumers_tests import enable
from arknights_mower.utils import (
    recall_estimates,
    replacement_coordination,
)
from arknights_mower.utils.replacement_coordination import recall_can_sustain
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = exhaust_replacement_tests.solver
NOW = datetime(2026, 10, 25, 12)


@pytest.fixture(params=[False, True], ids=["observed", "calculated"])
def recall(solver, monkeypatch, request):
    data = solver.op_data
    data._projection_now = NOW
    data.exhaust_agent = []
    data.operators["机械师"].exhaust_require = False
    data.operators["苍苔"].replacement = ["槐琥"]
    data.plan["room_2_2"][0].replacement = ["槐琥"]
    data.operators["能天使"].replacement = ["陈", "结城理"]
    data.plan["meeting"][0].replacement = ["陈", "结城理"]
    data.operators["能天使"]._current_room = ""
    data.operators["能天使"].current_index = -1
    data.operators["陈"]._current_room = "meeting"
    data.operators["陈"].current_index = 0
    for op in data.operators.values():
        op.mood, op.time_stamp, op.depletion_rate = 12, NOW, 0
    data.operators["机械师"].mood = 7
    data.operators["苍苔"].mood = data.operators["絮雨"].mood = 1
    for bed in data.all_dorms():
        if bed.name:
            bed.time = NOW + timedelta(hours=4)
    solver.task = None
    solver.check_fia = Mock(return_value=([], None))
    rates = ({name: 1 for name in data.operators}, {name: 4 for name in data.operators})
    monkeypatch.setattr(
        recall_estimates, "estimated_recall_rates", lambda *a, **k: rates
    )
    if request.param:
        enable(data, NOW, monkeypatch)
    return solver, rates, request.param


def event(kind="order", *, at=None):
    task = SchedulerTask(time=at or NOW + timedelta(minutes=10))
    if kind == "order":
        task.type, task.meta_data = TaskTypes.RUN_ORDER, "room_3_3"
    elif kind == "replacement":
        task.meta_data = "替班心情检查：陈"
        task.replacement_check = {
            "owner": "能天使",
            "cover": "陈",
            "room": "meeting",
            "index": 0,
        }
    return task


def set_recalled_mood(solver, mood, *, calculated):
    for name in ("苍苔", "絮雨"):
        solver.op_data.operators[name].mood = mood
        if calculated:
            solver.op_data.mood_model.observe(name, mood, NOW)


def admitted_recall(solver):
    supported = solver.op_data.project_arrangements(
        [{"room_2_2": ["苍苔"], "contact": ["絮雨"]}]
    )
    return solver._coordination_admission(supported, ["机械师"])


@pytest.mark.parametrize("kind", ["order", "replacement", "patrol"])
@pytest.mark.parametrize("mood,allowed", [(1, False), (12, True)])
def test_existing_event_cannot_replace_full_recovery_endurance(
    recall, kind, mood, allowed
):
    solver, _, calculated = recall
    set_recalled_mood(solver, mood, calculated=calculated)
    wake = event(kind)
    solver.tasks = [wake]
    before = deepcopy(vars(wake))
    support = solver._plan_exhaust_support(["机械师"])
    assert bool(support) is allowed
    if allowed:
        assert support["room_2_2"] == ["苍苔"]
    assert (
        solver._coordination_support_valid(
            {"room_2_2": ["苍苔"], "contact": ["絮雨"]}, ["机械师"]
        )
        is allowed
    )
    assert solver.tasks == [wake] and vars(wake) == before
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("wall_offset", [-1, 1])
def test_full_recovery_planning_uses_projection_time(recall, monkeypatch, wall_offset):
    solver, _, calculated = recall
    set_recalled_mood(solver, 12, calculated=calculated)
    clock = Mock(wraps=datetime)
    clock.now.return_value = NOW + timedelta(hours=wall_offset)
    monkeypatch.setattr(replacement_coordination, "datetime", clock)
    solver.tasks = [event()]
    support = solver._plan_exhaust_support(["机械师"])
    assert support and solver._coordination_support_valid(support, ["机械师"])
    clock.now.assert_not_called()


@pytest.mark.parametrize("recall", [False], indirect=True)
def test_existing_check_cannot_replace_missing_recovery_evidence(recall):
    solver, rates, _ = recall
    set_recalled_mood(solver, 12, calculated=False)
    solver.tasks = [event("replacement")]
    assert solver._plan_exhaust_support(["机械师"])
    rates[1].clear()
    assert solver._plan_exhaust_support(["机械师"]) is None


@pytest.mark.parametrize("recall", [True], indirect=True)
def test_calculated_recall_checks_new_residents_upper_deadline(recall, monkeypatch):
    solver, _, _ = recall
    set_recalled_mood(solver, 12, calculated=True)
    admitted = admitted_recall(solver)
    cls = type(solver.op_data)
    original = cls.calculated_mood_deadline
    calls = []
    work_horizons = []

    def deadline(data, name, target, *args, **kwargs):
        calls.append((name, target))
        if target == data.operators[name].lower_limit:
            work_horizons.append(kwargs["max_hours"])
        return original(data, name, target, *args, **kwargs)

    monkeypatch.setattr(cls, "calculated_mood_deadline", deadline)
    assert recall_can_sustain(
        solver.op_data, admitted, ["苍苔", "絮雨"], ["机械师"], now=NOW
    )
    assert ("机械师", admitted.operators["机械师"].upper_limit) in calls
    assert work_horizons and min(work_horizons) > 1
    assert work_horizons == pytest.approx([work_horizons[0]] * len(work_horizons))


def test_full_recovery_guards_recalled_explicit_completion(recall):
    solver, _, calculated = recall
    set_recalled_mood(solver, 12, calculated=calculated)
    solver.tasks = [event()]
    assert solver._plan_exhaust_support(["机械师"])
    solver.op_data.operators["絮雨"].rest_in_full = True
    assert solver._plan_exhaust_support(["机械师"]) is None
    solver.op_data.operators["絮雨"].rest_in_full = False
    solver.op_data.group_recovery_full_members["感知"] = ["苍苔", "絮雨"]
    assert solver._plan_exhaust_support(["机械师"]) is None


def test_exhausted_handoff_keeps_independent_endurance_exemption(recall):
    solver, _, _ = recall
    assert solver._plan_exhaust_support(["机械师"]) is None
    assert solver._plan_exhaust_support(["机械师"], urgent=True)
    solver.op_data.operators["絮雨"].rest_in_full = True
    assert solver._plan_exhaust_support(["机械师"], urgent=True) is None


@pytest.mark.parametrize("kind", ["order", "replacement", "patrol"])
def test_unknown_recovery_cannot_borrow_existing_event(recall, kind):
    solver, _, calculated = recall
    solver.tasks = [event(kind)]
    set_recalled_mood(solver, 12, calculated=calculated)
    if calculated:
        solver.op_data.mood_model.moods.pop("机械师")
    else:
        solver.op_data.operators["机械师"].time_stamp = None
    assert solver._plan_exhaust_support(["机械师"]) is None


@pytest.mark.parametrize("reserve,allowed", [(-0.01, False), (0, False), (0.01, True)])
@pytest.mark.parametrize("recall", [False], indirect=True)
def test_working_mood_stays_strictly_above_floor_until_full_recovery(
    recall, reserve, allowed
):
    solver, rates, _ = recall
    set_recalled_mood(solver, 12, calculated=False)
    admitted = admitted_recall(solver)
    # 机械师从 7 恢复到 24 需要 17/4 小时；絮雨在终点仍须高于自己的下限。
    horizon = (24 - 7) / 4
    admitted.operators["絮雨"].lower_limit = 2
    rates[0]["絮雨"] = (12 - 2 - reserve) / horizon
    assert (
        recall_can_sustain(
            solver.op_data, admitted, ["苍苔", "絮雨"], ["机械师"], rates=rates, now=NOW
        )
        is allowed
    )
