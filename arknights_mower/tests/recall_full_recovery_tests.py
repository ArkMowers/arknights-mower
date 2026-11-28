"""普通救急召回支撑实际完整回班，既有事件不能替代恢复交接。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import exhaust_replacement_tests
from arknights_mower.tests.mood_calculation_projection_consumers_tests import enable
from arknights_mower.utils import (
    config,
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


@pytest.mark.parametrize("mood, allowed", [(1, False), (12, True)])
@pytest.mark.parametrize("wait_cap", [0, 0.5])
def test_ordinary_rescue_bypasses_automatic_group_wait_only_with_endurance(
    recall, mood, allowed, wait_cap, monkeypatch
):
    solver, _, calculated = recall
    data = solver.op_data
    set_recalled_mood(solver, mood, calculated=calculated)
    data.group_recovery_full_members["感知"] = ["苍苔", "絮雨"]
    conf = getattr(data, "runtime_conf", None) or config.conf
    monkeypatch.setattr(conf, "group_mood_gap_max_extra_wait_hours", wait_cap)
    solver.tasks = [event()]
    positions = {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    task_time = solver.tasks[0].time
    support = solver._plan_exhaust_support(["机械师"])
    assert (support is not None) is allowed
    assert {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    } == positions
    assert solver.tasks[0].time == task_time
    assert {"苍苔", "絮雨"}.issubset(data.group_recovery_full_members["感知"])
    if allowed:
        data.operators["絮雨"].rest_in_full = True
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


def test_calculated_rescue_dispatch_bypasses_auto_wait_but_preserves_explicit_full(
    recall, monkeypatch
):
    from arknights_mower.solvers import base_schedule

    solver, _, calculated = recall
    if not calculated:
        pytest.skip("仅计算心情路径有提交前心情复核")
    clock = Mock(wraps=datetime)
    clock.now.return_value = NOW
    monkeypatch.setattr(base_schedule, "datetime", clock)
    set_recalled_mood(solver, 12, calculated=True)
    data = solver.op_data
    data.group_recovery_full_members["感知"] = ["苍苔", "絮雨"]
    plan = solver._plan_exhaust_support(["机械师"])
    assert plan
    task = SchedulerTask(task_plan=plan, task_type=TaskTypes.SELF_CORRECTION)
    task.exhaust_support = task.ordinary_coordination = True
    task.coordination_request_names = ["机械师"]
    solver.task = task
    assert solver._coordination_support_valid(plan, ["机械师"])
    solver._validate_calculated_arrangement()
    data.operators["絮雨"].rest_in_full = True
    with pytest.raises(base_schedule.MoodArrangementChanged):
        solver._validate_calculated_arrangement()
    data.operators["絮雨"].rest_in_full = False
    task.exhaust_support = False
    with pytest.raises(base_schedule.MoodArrangementChanged):
        solver._validate_calculated_arrangement()


@pytest.mark.parametrize("recall", [False], indirect=True)
def test_ordinary_recall_uses_actual_return_advance(recall):
    solver, rates, _ = recall
    set_recalled_mood(solver, 12, calculated=False)
    solver.op_data.operators["机械师"].rest_in_full = False
    # 本轮主班回满要 4.25 小时，实际普通回班提前八分钟。
    # 召回者可支撑 4.2 小时，应允许这次完整交接。
    rates[0]["苍苔"] = rates[0]["絮雨"] = 12 / 4.2
    plan = solver._plan_exhaust_support(["机械师"])
    assert plan
    assert solver._coordination_support_valid(plan, ["机械师"])


def test_unrelated_resident_cannot_extend_request_recovery(recall, monkeypatch):
    solver, rates, calculated = recall
    set_recalled_mood(solver, 12, calculated=calculated)
    data = solver.op_data
    data.operators["能天使"].mood = 1
    if calculated:
        data.mood_model.observe("能天使", 1, NOW)
    solver.op_data = data.project_arrangements(
        [{"dormitory_1": ["冰酿", "闪灵", "苍苔", "絮雨", "能天使"]}]
    )
    rates[1].pop("能天使")
    cls = type(data)
    deadline = cls.calculated_mood_deadline

    def requested_deadline(forecast, name, target, *args, **kwargs):
        assert not (name == "能天使" and target == forecast.operators[name].upper_limit)
        return deadline(forecast, name, target, *args, **kwargs)

    if calculated:
        monkeypatch.setattr(cls, "calculated_mood_deadline", requested_deadline)
    before = [(bed.name, bed.time) for bed in solver.op_data.all_dorms()]
    plan = solver._plan_exhaust_support(["机械师"])
    assert plan
    assert solver._coordination_support_valid(plan, ["机械师"])
    assert [(bed.name, bed.time) for bed in solver.op_data.all_dorms()] == before


@pytest.mark.parametrize("recall", [False], indirect=True)
@pytest.mark.parametrize("reserve", ["name", "slot"])
def test_normal_return_deadline_respects_reservations(recall, reserve):
    solver, rates, _ = recall
    set_recalled_mood(solver, 12, calculated=False)
    kwargs = (
        {"reserved_names": {"机械师"}}
        if reserve == "name"
        else {"reserved_slots": {("room_3_3", 0)}}
    )
    assert not recall_can_sustain(
        solver.op_data,
        admitted_recall(solver),
        ["苍苔", "絮雨"],
        ["机械师"],
        rates=rates,
        now=NOW,
        **kwargs,
    )


@pytest.mark.parametrize("priority", ["low", "standby"])
def test_slow_nonpriority_peer_does_not_add_recovery_endpoint(
    recall, monkeypatch, priority
):
    solver, rates, calculated = recall
    set_recalled_mood(solver, 12, calculated=calculated)
    original = solver.op_data
    admitted = admitted_recall(solver)
    for data in (original, admitted):
        data.groups["请求"] = ["机械师", "能天使"]
        for name in data.groups["请求"]:
            data.operators[name].group = "请求"
        data.operators["机械师"].rest_in_full = False
        data.operators["能天使"].resting_priority = priority
        conf = data.runtime_conf or config.conf
        monkeypatch.setattr(conf, "group_rest_in_full_on_mood_gap", False)
    admitted = admitted.project_arrangements(
        [{"dormitory_1": ["冰酿", "闪灵", "机械师", "Free", "能天使"]}]
    )
    admitted.group_shift_state["请求"] = True
    if priority == "standby":
        rates[1].pop("能天使")
    else:
        rates[1]["能天使"] = 0.1
    cls = type(original)
    deadline = cls.calculated_mood_deadline

    def requested_deadline(data, name, target, *args, **kwargs):
        assert not (name == "能天使" and target == data.operators[name].upper_limit)
        return deadline(data, name, target, *args, **kwargs)

    if calculated:
        monkeypatch.setattr(cls, "calculated_mood_deadline", requested_deadline)
    assert recall_can_sustain(
        original,
        admitted,
        ["苍苔", "絮雨"],
        ["机械师", "能天使"],
        rates=rates,
        now=NOW,
        request_names=["机械师"],
    )


def test_multiple_request_units_apply_each_real_return_before_next(recall, monkeypatch):
    solver, rates, calculated = recall
    set_recalled_mood(solver, 12, calculated=calculated)
    admitted = admitted_recall(solver).project_arrangements(
        [{"dormitory_1": ["冰酿", "闪灵", "机械师", "Free", "能天使"]}]
    )
    # 能天使先回班释放陈；陈只需支撑该次交接，无须等机械师后续回班。
    rates[0]["陈"] = 12 / 3.5
    plan_return = replacement_coordination.ordinary_recall_return_task
    snapshots = []

    def record(data, *args, **kwargs):
        snapshots.append(
            (
                kwargs["now"],
                data.operators["能天使"].is_working(),
                data.operators["陈"].current_room,
            )
        )
        return plan_return(data, *args, **kwargs)

    monkeypatch.setattr(replacement_coordination, "ordinary_recall_return_task", record)
    assert recall_can_sustain(
        solver.op_data,
        admitted,
        ["苍苔", "絮雨"],
        ["机械师", "能天使"],
        rates=rates,
        now=NOW,
    )
    assert len(snapshots) == 2
    assert snapshots[0] == (NOW, False, "meeting")
    assert snapshots[1][0] > NOW and snapshots[1][1:] == (True, "")
    assert admitted.operators["能天使"].is_resting()
    assert admitted.operators["陈"].current_room == "meeting"


def test_independent_rest_request_keeps_its_own_return_endpoint(recall):
    solver, rates, _ = recall
    set_recalled_mood(solver, 12, calculated=recall[2])
    admitted = admitted_recall(solver)
    for data in (solver.op_data, admitted):
        op = data.operators["机械师"]
        op.group_bindings = [
            {"group": "", "replacement": ["槐琥"]},
            {"group": "感知", "replacement": ["槐琥"]},
        ]
        # 空绑组提供个人轮休，具名绑组保留工作替班身份。
        op.group = ""
        op.shift_group = None
    assert admitted.operators["机械师"].independent_rest
    assert recall_can_sustain(
        solver.op_data,
        admitted,
        ["苍苔", "絮雨"],
        ["机械师"],
        rates=rates,
        now=NOW,
        request_names=["机械师"],
    )


def test_immediate_group_return_cannot_put_unrecovered_peer_at_floor(
    recall, monkeypatch
):
    solver, rates, calculated = recall
    set_recalled_mood(solver, 12, calculated=calculated)
    original = solver.op_data
    for name, mood in (("机械师", 0), ("能天使", 24)):
        original.operators[name].mood = mood
        if calculated:
            original.mood_model.observe(name, mood, NOW)
    admitted = admitted_recall(solver)
    for data in (original, admitted):
        data.groups["请求"] = ["机械师", "能天使"]
        for name in data.groups["请求"]:
            data.operators[name].group = "请求"
        data.operators["机械师"].rest_in_full = False
        data.operators["机械师"].resting_priority = "low"
        data.operators["能天使"].resting_priority = "high"
        conf = data.runtime_conf or config.conf
        monkeypatch.setattr(conf, "group_rest_in_full_on_mood_gap", False)
    admitted = admitted.project_arrangements(
        [{"dormitory_1": ["冰酿", "闪灵", "机械师", "Free", "能天使"]}]
    )
    admitted.group_shift_state["请求"] = True
    assert not recall_can_sustain(
        original,
        admitted,
        ["苍苔", "絮雨"],
        ["机械师", "能天使"],
        rates=rates,
        now=NOW,
        request_names=["机械师"],
    )


@pytest.mark.parametrize(
    "gate,allowed",
    [
        ("ordinary", True),
        ("explicit", False),
        ("gap", False),
        ("capped-gap", True),
        ("known-full", True),
    ],
)
def test_return_endpoint_obeys_recovery_gate_and_known_zero_rate(
    recall, monkeypatch, gate, allowed
):
    solver, rates, calculated = recall
    set_recalled_mood(solver, 12, calculated=calculated)
    original = solver.op_data
    admitted = admitted_recall(solver)
    for data in (original, admitted):
        data.groups["请求"] = ["机械师", "能天使"]
        for name in data.groups["请求"]:
            data.operators[name].group = "请求"
        data.operators["机械师"].rest_in_full = False
        data.operators["能天使"].resting_priority = "low"
        data.operators["能天使"].rest_in_full = gate in ("explicit", "known-full")
        conf = data.runtime_conf or config.conf
        monkeypatch.setattr(conf, "group_rest_in_full_on_mood_gap", False)
        if gate in ("gap", "capped-gap"):
            data.group_recovery_full_members["请求"] = ["机械师", "能天使"]
            monkeypatch.setattr(
                conf,
                "group_mood_gap_max_extra_wait_hours",
                0.5 if gate == "capped-gap" else 0,
            )
    admitted = admitted.project_arrangements(
        [{"dormitory_1": ["冰酿", "闪灵", "机械师", "Free", "能天使"]}]
    )
    admitted.group_shift_state["请求"] = True
    rates[1]["能天使"] = 4 if gate == "known-full" else 0
    if calculated and gate != "known-full":
        cls = type(original)
        deadline, mood = cls.calculated_mood_deadline, cls.calculated_mood

        def no_peer_deadline(data, name, target, *args, **kwargs):
            if name == "能天使" and target == data.operators[name].upper_limit:
                return None
            return deadline(data, name, target, *args, **kwargs)

        def constant_peer_mood(data, name, *args, **kwargs):
            return 12 if name == "能天使" else mood(data, name, *args, **kwargs)

        monkeypatch.setattr(cls, "calculated_mood_deadline", no_peer_deadline)
        monkeypatch.setattr(cls, "calculated_mood", constant_peer_mood)
    assert (
        recall_can_sustain(
            original,
            admitted,
            ["苍苔", "絮雨"],
            ["机械师", "能天使"],
            rates=rates,
            now=NOW,
            request_names=["机械师"],
        )
        is allowed
    )
