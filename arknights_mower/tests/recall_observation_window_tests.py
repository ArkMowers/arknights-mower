"""既有重新判断机会限制普通召回续航，实际交接仍经过完整准入。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests import exhaust_replacement_tests
from arknights_mower.tests.mood_calculation_projection_consumers_tests import enable
from arknights_mower.utils import (
    config,
    predictive_mood_control,
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


@pytest.mark.parametrize("kind", ["order", "replacement", "patrol"])
def test_short_existing_event_admits_real_recall_without_mutating_queue(recall, kind):
    solver, _, _ = recall
    assert solver._plan_exhaust_support(["机械师"]) is None
    wake = event(kind)
    solver.tasks = [wake]
    before = deepcopy(vars(wake))
    support = solver._plan_exhaust_support(["机械师"])
    assert support and support["room_2_2"] == ["苍苔"]
    assert solver._coordination_support_valid(support, ["机械师"])
    assert solver.tasks == [wake] and vars(wake) == before
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("wall_offset", [-1, 1])
def test_recall_planning_uses_projection_time_instead_of_wall_clock(
    recall, monkeypatch, wall_offset
):
    solver, _, _ = recall
    clock = Mock(wraps=datetime)
    clock.now.return_value = NOW + timedelta(hours=wall_offset)
    monkeypatch.setattr(replacement_coordination, "datetime", clock)
    solver.tasks = [event()]
    support = solver._plan_exhaust_support(["机械师"])
    assert support and support["room_2_2"] == ["苍苔"]
    assert solver._coordination_support_valid(support, ["机械师"])
    clock.now.assert_not_called()


@pytest.mark.parametrize(
    "invalid", ["past", "due", "current", "failed", "restore", "no-room", "memory"]
)
def test_unusable_events_leave_original_full_recovery_fallback(recall, invalid):
    solver, _, _ = recall
    wake = event()
    if invalid == "past":
        wake.time = NOW - timedelta(seconds=1)
    elif invalid == "due":
        wake.time = NOW
    elif invalid == "current":
        solver.task = wake
    elif invalid == "failed":
        wake.execution_failure = {"reason": "等待新观测"}
    elif invalid == "restore":
        wake.run_order_restore_pending = True
        wake.run_order_original_roster = {}
    elif invalid == "no-room":
        wake.meta_data = ""
    else:
        wake = event("patrol")
        wake.mood_control_event = {"at": wake.time.timestamp()}
    solver.tasks = [wake]
    assert solver._plan_exhaust_support(["机械师"]) is None
    assert solver.tasks == [wake]


def test_blocked_order_cannot_shorten_recall_window(recall):
    solver, _, _ = recall
    wake = event()
    wake.plan = {"room_3_3": ["槐琥"]}
    restoration = SchedulerTask(time=NOW)
    restoration.type = TaskTypes.RUN_ORDER
    restoration.run_order_restore_pending = True
    restoration.run_order_original_roster = {"room_3_3": ["机械师"]}
    restoration.execution_failure = {"reason": "等待原班恢复"}
    solver.tasks = [wake, restoration]
    assert solver._plan_exhaust_support(["机械师"]) is None


def test_readmitted_retained_event_still_provides_existing_opportunity(recall):
    solver, _, _ = recall
    wake = event()
    wake.execution_retained = True
    solver.tasks = [wake]
    assert solver._plan_exhaust_support(["机械师"])


@pytest.mark.parametrize("recall", [False], indirect=True)
def test_short_window_needs_work_evidence_but_not_recovery_rates(recall):
    solver, rates, _ = recall
    solver.tasks = [event()]
    rates[1].clear()
    assert solver._plan_exhaust_support(["机械师"])
    rates[0].pop("絮雨")
    assert solver._plan_exhaust_support(["机械师"]) is None


def test_operation_budget_prevents_nearly_zero_recall_window(recall, monkeypatch):
    solver, _, _ = recall
    solver.tasks = [event(at=NOW + timedelta(microseconds=1))]
    monkeypatch.setattr(
        base_schedule, "estimate_task_duration", lambda *a, **k: timedelta(hours=1)
    )
    assert solver._plan_exhaust_support(["机械师"]) is None


def test_earlier_complete_recovery_can_end_before_distant_event(recall):
    solver, rates, calculated = recall
    if calculated:
        for name in ("苍苔", "絮雨"):
            solver.op_data.mood_model.observe(name, 12, NOW)
    else:
        for name in ("苍苔", "絮雨"):
            solver.op_data.operators[name].mood = 12
        rates[1].update({name: 24 for name in rates[1]})
    solver.tasks = [event(at=NOW + timedelta(days=1))]
    assert solver._plan_exhaust_support(["机械师"])


@pytest.mark.parametrize("recall", [True], indirect=True)
def test_successful_calculated_short_window_skips_upper_deadlines(recall, monkeypatch):
    solver, _, _ = recall
    supported = solver.op_data.project_arrangements(
        [{"room_2_2": ["苍苔"], "contact": ["絮雨"]}]
    )
    admitted = solver._coordination_admission(supported, ["机械师"])
    cls = type(solver.op_data)
    original = cls.calculated_mood_deadline
    calls = []

    def deadline(data, name, target, *args, **kwargs):
        calls.append((name, target))
        # 原休息组的回满等待仍需核验；本次新入宿者不再决定续航终点。
        assert name != "机械师" or target != data.operators[name].upper_limit
        if target == data.operators[name].lower_limit:
            assert kwargs["max_hours"] == pytest.approx(11 / 60)
        return original(data, name, target, *args, **kwargs)

    monkeypatch.setattr(cls, "calculated_mood_deadline", deadline)
    assert recall_can_sustain(
        solver.op_data,
        admitted,
        ["苍苔", "絮雨"],
        ["机械师"],
        now=NOW,
        until=NOW + timedelta(minutes=11),
        not_before=NOW + timedelta(minutes=3),
    )
    assert calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("meta_data", ""),
        ("run_order_restore_pending", True),
        ("replacement_check", {"cover": "槐琥"}),
    ],
)
def test_event_classification_changes_invalidate_prediction_input(recall, field, value):
    solver, _, _ = recall
    wake = event()
    solver.tasks = [wake]
    before = predictive_mood_control.input_signature(solver)
    setattr(wake, field, value)
    assert predictive_mood_control.input_signature(solver) != before


def test_explicit_recovery_guards_still_apply_to_short_window(recall):
    solver, _, _ = recall
    solver.tasks = [event()]
    solver.op_data.operators["絮雨"].rest_in_full = True
    assert solver._plan_exhaust_support(["机械师"]) is None
    solver.op_data.operators["絮雨"].rest_in_full = False
    solver.op_data.group_recovery_full_members["感知"] = ["苍苔", "絮雨"]
    assert solver._plan_exhaust_support(["机械师"]) is None


def test_current_event_selection_invalidates_prediction_input(recall):
    solver, _, _ = recall
    wake = event()
    solver.tasks = [wake]
    before = predictive_mood_control.input_signature(solver)
    solver.task = wake
    assert predictive_mood_control.input_signature(solver) != before


def test_operation_budget_counts_changes_in_incomplete_rooms(recall, monkeypatch):
    solver, _, _ = recall
    original = solver.op_data
    supported = original.project_arrangements(
        [{"room_2_2": ["苍苔"], "contact": ["絮雨"]}]
    )
    admitted = solver._coordination_admission(supported, ["机械师"])
    solver.tasks = [event("patrol", at=NOW + timedelta(seconds=1))]
    seen = []

    def duration(task, **kwargs):
        seen.append(task.plan)
        return timedelta(minutes=2)

    monkeypatch.setattr(base_schedule, "estimate_task_duration", duration)
    until, minimum = solver._coordination_recall_window(
        original, supported, admitted, now=NOW
    )
    assert "dormitory_1" in seen[0]
    assert "dormitory_1" in seen[1]
    assert minimum == NOW + timedelta(minutes=4)
    assert until == NOW + timedelta(minutes=6)


def test_run_order_wait_must_finish_before_recall_work_expires(recall, monkeypatch):
    solver, _, calculated = recall
    conf = solver.op_data.runtime_conf or config.conf
    monkeypatch.setattr(conf, "run_order_delay", 10)
    monkeypatch.setattr(conf.run_order_grandet_mode, "enable", True)
    monkeypatch.setattr(conf.run_order_grandet_mode, "buffer_time", 2)
    for name in ("苍苔", "絮雨"):
        solver.op_data.operators[name].mood = 0.25
        if calculated:
            solver.op_data.mood_model.observe(name, 0.25, NOW)
    wake = event()
    solver.tasks = [wake]
    supported = solver.op_data.project_arrangements(
        [{"room_2_2": ["苍苔"], "contact": ["絮雨"]}]
    )
    admitted = solver._coordination_admission(supported, ["机械师"])
    assert recall_can_sustain(
        solver.op_data,
        admitted,
        ["苍苔", "絮雨"],
        ["机械师"],
        now=NOW,
        until=wake.time + timedelta(minutes=2),
    )
    assert solver._plan_exhaust_support(["机械师"]) is None
    assert not solver._coordination_support_valid(
        {"room_2_2": ["苍苔"], "contact": ["絮雨"]}, ["机械师"]
    )
    assert solver.tasks == [wake]
    until, _ = solver._coordination_recall_window(
        solver.op_data, supported, admitted, now=NOW
    )
    assert until == NOW + timedelta(minutes=20, seconds=45)


@pytest.mark.parametrize("empty_meta", [False, True])
def test_recall_cannot_use_check_cancelled_by_its_own_handoff(recall, empty_meta):
    solver, _, _ = recall
    solver.op_data.operators["苍苔"].replacement = ["槐琥", "结城理"]
    wake = event("replacement")
    if empty_meta:
        wake.meta_data = ""
    wake.replacement_check = {
        "owner": "苍苔",
        "cover": "槐琥",
        "room": "room_2_2",
        "index": 0,
    }
    solver.tasks = [wake]
    supported = solver.op_data.project_arrangements(
        [{"room_2_2": ["苍苔"], "contact": ["絮雨"]}]
    )
    admitted = solver._coordination_admission(supported, ["机械师"])
    assert solver._coordination_recall_window(
        solver.op_data, supported, admitted, now=NOW
    ) == (None, None)
    assert not solver._coordination_support_valid(
        {"room_2_2": ["苍苔"], "contact": ["絮雨"]}, ["机械师"]
    )


@pytest.mark.parametrize("kind", ["patrol", "order"])
def test_ordinary_queue_before_recheck_is_part_of_recall_endurance(recall, kind):
    solver, _, calculated = recall
    for name in ("苍苔", "絮雨"):
        solver.op_data.operators[name].mood = 0.5
        if calculated:
            solver.op_data.mood_model.observe(name, 0.5, NOW)
    wake = event(kind)
    solver.tasks = [wake]
    assert solver._plan_exhaust_support(["机械师"])
    furniture = SchedulerTask(
        time=NOW + timedelta(minutes=5), task_type=TaskTypes.FURNITURE
    )
    solver.tasks.insert(0, furniture)
    before = [deepcopy(vars(task)) for task in solver.tasks]
    assert bool(solver._plan_exhaust_support(["机械师"])) == (kind == "order")
    assert [vars(task) for task in solver.tasks] == before
