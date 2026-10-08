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
    defer_dorm_before_priority_task,
    logger,
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


@pytest.mark.parametrize("dispatch", [scheduling, protect_priority_tasks])
@pytest.mark.parametrize(
    "plan", [{"room_1_1": ["A"]}, {"room_1_1": ["A"], "dormitory_1": ["B"]}]
)
def test_future_work_waits_for_run_order_window(dispatch, plan, monkeypatch):
    work = task(TaskTypes.SHIFT_ON, 1190, copy.deepcopy(plan))
    order = task(TaskTypes.RUN_ORDER, 1200)
    tasks = [work, order]
    info = []
    monkeypatch.setattr(logger, "info", lambda *args: info.append(args))

    for seconds in (0, 300, 599):
        dispatch(tasks, time_now=NOW + timedelta(seconds=seconds))
        assert tasks == [work, order]
        assert work.time == NOW + timedelta(seconds=1190)
        assert work.plan == plan
    assert not info

    dispatch(tasks, time_now=NOW + timedelta(seconds=600))
    assert tasks == [order, work]
    assert work.time == order.time + timedelta(seconds=1)
    assert work.plan == plan
    assert not info


@pytest.mark.parametrize("dispatch", [scheduling, protect_priority_tasks])
def test_distant_mastery_still_protects_future_work(dispatch):
    work = task(TaskTypes.SHIFT_ON, 1190, {"room_1_1": ["A"]})
    swap = task(TaskTypes.SWAP_SUPPORT, 1200)
    tasks = [work, swap]
    dispatch(tasks, time_now=NOW)
    assert tasks == [swap, work]
    assert work.time == swap.time + timedelta(seconds=1)


@pytest.mark.parametrize("dispatch", [scheduling, protect_priority_tasks])
def test_dorm_forecast_rebuilding_does_not_repeat_info_or_defer_work(
    dispatch, monkeypatch
):
    info, debug = [], []
    monkeypatch.setattr(logger, "info", lambda *args: info.append(args))
    monkeypatch.setattr(logger, "debug", lambda *args: debug.append(args))
    # 实例中的 9.1 秒来自未来清退与跑单间隔扣去一分钟，并非当前剩余时间。
    original_time = datetime(2026, 10, 9, 1, 37, 6, 136646)
    order_time = datetime(2026, 10, 9, 1, 38, 15, 262450)
    for now in (
        datetime(2026, 10, 9, 0, 23, 43),
        datetime(2026, 10, 9, 0, 24, 7),
        datetime(2026, 10, 9, 0, 24, 35),
    ):
        dorm = SchedulerTask(
            original_time,
            {"dormitory_3": ["Current", "Current", "Free", "Current", "Current"]},
            TaskTypes.RELEASE_DORM,
            meta_data="幽灵鲨",
        )
        work = SchedulerTask(original_time + timedelta(seconds=1), {"room_1_2": ["A"]})
        order = SchedulerTask(order_time, task_type=TaskTypes.RUN_ORDER)
        tasks = [dorm, work, order]
        for _ in range(2):
            dispatch(tasks, time_now=now)
            assert tasks == [work, order, dorm]
            assert dorm.time == order_time + timedelta(seconds=1)
            assert work.time == original_time + timedelta(seconds=1)
    assert not info
    forecasts = [args for args in debug if args[0].startswith("宿舍提前规划")]
    assert len(forecasts) == 3
    assert all(args[1:3] == ("dormitory_3", "幽灵鲨") for args in forecasts)
    assert all(args[3] == original_time and args[5] == order_time for args in forecasts)


@pytest.mark.parametrize("seconds", [0, 1])
def test_due_deferral_logs_info_and_future_deferral_logs_debug(seconds, monkeypatch):
    info, debug = [], []
    monkeypatch.setattr(logger, "info", lambda *args: info.append(args))
    monkeypatch.setattr(logger, "debug", lambda *args: debug.append(args))
    work = task(TaskTypes.SHIFT_ON, seconds, {"room_1_1": ["A"]})
    order = task(TaskTypes.RUN_ORDER, 60)
    tasks = [work, order]
    scheduling(tasks, time_now=NOW)
    assert tasks == [order, work]
    messages = [
        args for args in (info if seconds == 0 else debug) if "预计耗时" in args[0]
    ]
    assert len(messages) == 1
    assert messages[0][1:4] == ("上班", "room_1_1", NOW + timedelta(seconds=seconds))
    assert messages[0][-1] == order.time
    assert not any("预计耗时" in args[0] for args in (debug if seconds == 0 else info))


def test_future_workshop_batch_waits_for_run_order_window():
    jobs = [task(TaskTypes.WORKSHOP, 1190, meta_data=f"A{i}") for i in range(3)]
    order = task(TaskTypes.RUN_ORDER, 1200)
    tasks = jobs + [order]
    scheduling(tasks, time_now=NOW)
    assert tasks == jobs + [order]
    assert [job.time for job in jobs] == [NOW + timedelta(seconds=1190)] * 3
    scheduling(tasks, time_now=NOW + timedelta(minutes=10))
    assert tasks == [order] + jobs
    assert [job.time for job in jobs] == [
        order.time + timedelta(seconds=i) for i in range(1, 4)
    ]


def test_runtime_dorm_recheck_keeps_info(monkeypatch):
    info = []
    monkeypatch.setattr(logger, "info", lambda *args: info.append(args))
    dorm = task(TaskTypes.RELEASE_DORM, plan={"dormitory_3": ["Current", "Free"]})
    order = task(TaskTypes.RUN_ORDER, 100)
    assert defer_dorm_before_priority_task(
        dorm, [dorm, order], "dormitory_3", time_now=NOW
    )
    assert dorm.time == order.time + timedelta(seconds=1)
    assert len(info) == 1
    assert "dormitory_3" in info[0][0] and "跑单" in info[0][0]
