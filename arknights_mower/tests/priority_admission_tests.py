"""Trade orders and enabled mastery handoffs share admission guarantees."""

import copy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import order_admission_tests as room_fixtures
from arknights_mower.utils import config, operation_timing
from arknights_mower.utils.scheduler_task import (
    NewsChecker,
    SchedulerTask,
    TaskTypes,
    protect_priority_tasks,
    scheduling,
)

NOW = datetime(2026, 10, 8, 12)
CRITICAL_TYPES = [TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT]


@pytest.fixture(autouse=True)
def offline_admission(monkeypatch):
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config.conf.run_order_grandet_mode, "enable", False)
    monkeypatch.setattr(NewsChecker, "get_update_time", lambda: (None, None))
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(operation_timing, "_work_durations", {})
    monkeypatch.setattr(operation_timing, "_dorm_durations", {})


def task(kind, seconds=0, plan=None, **kwargs):
    return SchedulerTask(NOW + timedelta(seconds=seconds), plan or {}, kind, **kwargs)


@pytest.mark.parametrize("kind", CRITICAL_TYPES)
@pytest.mark.parametrize("dispatch", [scheduling, protect_priority_tasks])
def test_observed_slow_work_yields_at_both_dispatch_entries(kind, dispatch):
    operation_timing._work_durations["room_1_1"] = [180]
    work = task(TaskTypes.SHIFT_ON, plan={"room_1_1": ["A"]})
    critical = task(kind, 180)
    tasks = [work, critical]
    dispatch(tasks, time_now=NOW)
    assert tasks == [critical, work]
    assert work.time == critical.time + timedelta(seconds=1)
    assert critical.time == NOW + timedelta(seconds=180)


@pytest.mark.parametrize("kind", CRITICAL_TYPES)
def test_independent_rooms_split_and_keep_actual_occupancy(kind):
    data = room_fixtures.TestSchedulingRoomPlans().make_op_data(
        {"room_1_1": ["A"], "room_1_2": ["B"]}, targets=("C", "D")
    )
    work = task(TaskTypes.SHIFT_ON, plan={"room_1_1": ["C"], "room_1_2": ["D"]})
    critical = task(kind, 85)
    tasks = [work, critical]
    for _ in range(3):
        protect_priority_tasks(tasks, time_now=NOW, op_data=data)
        assert len(tasks) == 3
        assert tasks[:2] == [work, critical]
        assert work.plan == {"room_1_1": ["C"]}
        assert tasks[2].plan == {"room_1_2": ["D"]}
        assert tasks[2].time == critical.time + timedelta(seconds=1)
        assert data.get_current_room("room_1_1") == ["A"]
    tasks[2].plan["room_1_2"][0] = "B"
    assert work.plan == {"room_1_1": ["C"]}


@pytest.mark.parametrize("kind", CRITICAL_TYPES)
@pytest.mark.parametrize("binding", ["move", "group", "phase", "unknown"])
def test_dependent_or_unobserved_rooms_remain_atomic(kind, binding):
    data = room_fixtures.TestSchedulingRoomPlans().make_op_data(
        {"room_1_1": ["A"], "room_1_2": ["B"]}, targets=("C", "D")
    )
    work = task(TaskTypes.SHIFT_ON, plan={"room_1_1": ["C"], "room_1_2": ["D"]})
    if binding == "move":
        work.plan = {"room_1_1": ["B"], "room_1_2": ["A"]}
    elif binding == "group":
        data.operators["C"].group_bindings = [{"group": "shared"}]
        data.operators["D"].group = "shared"
    elif binding == "phase":
        work.return_window = {"deadline": NOW + timedelta(hours=1)}
    else:
        data.operators["A"].current_room = ""
    original = copy.deepcopy(work.plan)
    critical = task(kind, 85)
    tasks = [work, critical]
    scheduling(tasks, time_now=NOW, op_data=data)
    assert tasks == [critical, work]
    assert work.plan == original


@pytest.mark.parametrize("kind", CRITICAL_TYPES)
@pytest.mark.parametrize(
    "plan,seconds,admitted",
    [
        ({"room_1_1": ["A"]}, 69, False),
        ({"room_1_1": ["A"]}, 70, True),
        ({"room_1_1": ["A"]}, 71, True),
        ({"dormitory_1": ["A"]}, 160, False),
        ({"dormitory_1": ["A"]}, 161, True),
        (
            {"room_1_1": ["A"], "dormitory_1": ["B"], "dormitory_2": ["C"]},
            295,
            False,
        ),
        (
            {"room_1_1": ["A"], "dormitory_1": ["B"], "dormitory_2": ["C"]},
            296,
            True,
        ),
    ],
)
def test_work_and_mixed_dorm_budget_boundaries(kind, plan, seconds, admitted):
    work = task(TaskTypes.SHIFT_ON, plan=copy.deepcopy(plan))
    critical = task(kind, seconds)
    tasks = [work, critical]
    scheduling(tasks, time_now=NOW)
    assert (tasks[0] is work) == admitted
    assert work.time == (NOW if admitted else critical.time + timedelta(seconds=1))
    assert work.plan == plan


@pytest.mark.parametrize("kind", CRITICAL_TYPES)
@pytest.mark.parametrize("seconds,admitted", [(169, False), (170, True)])
def test_future_waiting_counts_before_work(kind, seconds, admitted):
    work = task(TaskTypes.SHIFT_ON, 100, {"room_1_1": ["A"]})
    critical = task(kind, seconds)
    tasks = [work, critical]
    scheduling(tasks, time_now=NOW)
    assert (tasks[0] is work) == admitted


@pytest.mark.parametrize("kind", CRITICAL_TYPES)
def test_cumulative_work_retains_only_the_executable_prefix(kind):
    work = [task(TaskTypes.SHIFT_ON, plan={f"room_1_{i}": [f"A{i}"]}) for i in range(3)]
    critical = task(kind, 179)
    tasks = work + [critical]
    for _ in range(3):
        scheduling(tasks, time_now=NOW)
        assert tasks == [work[0], work[1], critical, work[2]]
        assert [t.time for t in work[:2]] == [NOW, NOW]
        assert work[2].time == critical.time + timedelta(seconds=1)


@pytest.mark.parametrize("kind", CRITICAL_TYPES)
@pytest.mark.parametrize("seconds,admitted", [(150, False), (194, False), (195, True)])
def test_workshop_batch_is_admitted_or_deferred_in_full(kind, seconds, admitted):
    jobs = [task(TaskTypes.WORKSHOP, meta_data=f"A{i}") for i in range(3)]
    critical = task(kind, seconds)
    tasks = jobs + [critical]
    for _ in range(3):
        scheduling(tasks, time_now=NOW)
        assert tasks == (jobs + [critical] if admitted else [critical] + jobs)
        assert [job.meta_data for job in jobs] == [f"A{i}" for i in range(3)]
        assert [job.time for job in jobs] == (
            [NOW] * 3
            if admitted
            else [critical.time + timedelta(seconds=i) for i in range(1, 4)]
        )


@pytest.mark.parametrize("kind", CRITICAL_TYPES)
def test_workshop_batch_includes_waiting_intervening_dorm_and_keeps_work_prefix(kind):
    prefix = task(TaskTypes.SHIFT_ON, plan={"room_1_1": ["A"]})
    first = task(TaskTypes.WORKSHOP)
    dorm = task(TaskTypes.RE_ORDER, 100, {"dormitory_1": ["B"]})
    last = task(TaskTypes.WORKSHOP, 100)
    critical = task(kind, 270)
    tasks = [prefix, first, dorm, last, critical]
    scheduling(tasks, time_now=NOW)
    assert tasks == [prefix, critical, first, dorm, last]
    assert prefix.time == NOW
    assert [t.time for t in [first, dorm, last]] == [
        critical.time + timedelta(seconds=i) for i in range(1, 4)
    ]


@pytest.mark.parametrize("kind", CRITICAL_TYPES)
@pytest.mark.parametrize("seconds,admitted", [(274, False), (275, True)])
def test_workshop_batch_counts_future_start_waiting(kind, seconds, admitted):
    jobs = [task(TaskTypes.WORKSHOP), task(TaskTypes.WORKSHOP, 200)]
    critical = task(kind, seconds)
    tasks = jobs + [critical]
    scheduling(tasks, time_now=NOW)
    assert tasks == (jobs + [critical] if admitted else [critical] + jobs)
    assert jobs[0].time == (NOW if admitted else critical.time + timedelta(seconds=1))


@pytest.mark.parametrize("kind", CRITICAL_TYPES)
def test_deferred_workshop_backlog_is_rechecked_at_later_critical_task(kind):
    jobs = [task(TaskTypes.WORKSHOP, meta_data=f"A{i}") for i in range(3)]
    first, second = task(kind, 90), task(kind, 120)
    tasks = jobs + [first, second]
    for _ in range(3):
        scheduling(tasks, time_now=NOW)
        assert tasks == [first, second] + jobs
        assert [job.time for job in jobs] == [
            second.time + timedelta(seconds=i) for i in range(1, 4)
        ]


@pytest.mark.parametrize("previous_kind", CRITICAL_TYPES)
@pytest.mark.parametrize("kind", CRITICAL_TYPES)
def test_prior_critical_operation_consumes_time_before_later_critical_task(
    previous_kind, kind
):
    previous = task(previous_kind)
    work = task(TaskTypes.SHIFT_ON, 1, {"room_1_1": ["A"]})
    critical = task(kind, 120)
    tasks = [previous, work, critical]
    scheduling(tasks, time_now=NOW)
    assert tasks == [previous, critical, work]
    assert work.time == critical.time + timedelta(seconds=1)


@pytest.mark.parametrize(
    "kind,seconds", [(TaskTypes.RUN_ORDER, 140), (TaskTypes.SWAP_SUPPORT, 110)]
)
def test_prior_critical_task_invalidates_occupancy_projection(kind, seconds):
    data = room_fixtures.TestSchedulingRoomPlans().make_op_data({"room_1_1": ["A"]})
    previous = task(kind)
    work = task(TaskTypes.SHIFT_ON, 1, {"room_1_1": ["A"]})
    critical = task(TaskTypes.SWAP_SUPPORT, seconds)
    tasks = [previous, work, critical]
    scheduling(tasks, time_now=NOW, op_data=data)
    assert tasks == [previous, critical, work]
    assert data.get_current_room("room_1_1") == ["A"]


def test_observed_slow_training_room_reserves_the_handoff_operation():
    operation_timing._work_durations["train"] = [180]
    swap = task(TaskTypes.SWAP_SUPPORT, plan={"train": ["A"]})
    work = task(TaskTypes.SHIFT_ON, 1, {"room_1_1": ["B"]})
    critical = task(TaskTypes.RUN_ORDER, 250)
    tasks = [swap, work, critical]
    scheduling(tasks, time_now=NOW)
    assert tasks == [swap, critical, work]
    assert swap.time == NOW


def test_disabled_mastery_does_not_add_a_deadline():
    config.conf.enable_mastery = False
    operation_timing._work_durations["room_1_1"] = [180]
    work = task(TaskTypes.SHIFT_ON, plan={"room_1_1": ["A"]})
    stale = task(TaskTypes.SWAP_SUPPORT, 180)
    tasks = [work, stale]
    scheduling(tasks, time_now=NOW)
    assert tasks == [work, stale]
    assert work.time == NOW


@pytest.mark.parametrize("kind", CRITICAL_TYPES)
def test_strict_release_and_fill_phase_are_preserved(kind):
    release = task(TaskTypes.RELEASE_DORM, plan={"dormitory_1": ["Free"]})
    release.strict_mood_limit = True
    fill = task(TaskTypes.FILL_DORM, plan={"dormitory_2": ["A"]})
    fill.dorm_fill_plan = copy.deepcopy(fill.plan)
    critical = task(kind, 120)
    tasks = [release, fill, critical]
    scheduling(tasks, time_now=NOW)
    assert any(t is release for t in tasks)
    assert release.time <= NOW
    assert any(t is fill for t in tasks)
    assert fill.time > critical.time
    assert fill.plan == fill.dorm_fill_plan == {"dormitory_2": ["A"]}
