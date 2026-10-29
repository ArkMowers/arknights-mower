"""联网观测只在结束时绑定任务，执行与原班恢复沿用任务快照。"""

import copy
import io
import pickle
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from arknights_mower.tests.run_order_staffing_admission_tests import (
    staffed_order as staffed_order,
)
from arknights_mower.utils import config, run_order_network
from arknights_mower.utils.network_adaptation import get_network_adaptation
from arknights_mower.utils.run_order_network import (
    begin_run_order_network,
    bind_run_order_network,
    clear_run_order_network,
    finish_run_order_network,
    reconcile_run_order_network,
    run_order_buffer_seconds,
    run_order_entry_seconds,
    run_order_network_allowance,
    run_order_network_compensation,
    run_order_network_scope,
    with_run_order_network,
)
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    blocked_run_order_ids,
    run_order_end_time,
    scheduling,
)

NOW = datetime(2026, 10, 28, 19, 50)
ROOM = "room_1_1"


class WithoutNetworkModules(pickle.Unpickler):
    def find_class(self, module, name):
        if module in {
            "arknights_mower.utils.network_adaptation",
            "arknights_mower.utils.run_order_network",
        }:
            raise AssertionError(f"Saved tasks require unavailable module: {module}")
        return super().find_class(module, name)


def order(at, room=ROOM):
    return SchedulerTask(at, {room: ["但书"]}, TaskTypes.RUN_ORDER, room)


@pytest.fixture
def planned():
    conf = config.Conf()
    conf.run_order_network_adaptive = True
    conf.run_order_delay = 3
    conf.run_order_grandet_mode.enable = True
    conf.run_order_grandet_mode.buffer_time = 15
    return conf, SimpleNamespace(), order(NOW + timedelta(minutes=2))


def observe(owner, seconds=30, *, now=NOW, timed_out=True):
    return get_network_adaptation(owner).record(
        "CONNECTING",
        elapsed_seconds=seconds,
        base_seconds=30,
        observed_at=now,
        timed_out=timed_out,
    )


def test_mood_limit_release_clears_adapted_order_window_without_time_drift(
    planned, monkeypatch, offline_maintenance
):
    now = (
        datetime(2026, 10, 28, 12, tzinfo=timezone(timedelta(hours=8)))
        .astimezone()
        .replace(tzinfo=None)
    )
    conf, owner, task = planned
    conf.run_order_delay = 5
    conf.run_order_grandet_mode.buffer_time = 90
    monkeypatch.setattr(config, "conf", conf)
    task.time = now + timedelta(minutes=10)
    observe(owner, 90, now=now)
    bind_run_order_network([task], owner, conf, now)
    assert run_order_entry_seconds(task, conf) == 480
    order_start = task.time
    deadline = order_start + timedelta(seconds=510)
    release = SchedulerTask(
        deadline,
        {"dormitory_2": ["Current", "Current", "Free", "Current", "Current"]},
        TaskTypes.RELEASE_DORM,
        "令",
        strict_mood_limit=True,
        mood_limit=12,
    )
    tasks = [task, release]

    scheduling(tasks, execution_time=0.75, time_now=now)

    assert release.time + timedelta(seconds=90) < order_start
    assert release.mood_limit_deadline == deadline
    assert task.time == order_start
    assert tasks[0] is release
    reserved_start = release.time
    for seconds in (1, 2, 3):
        scheduling(
            tasks, execution_time=0.75, time_now=now + timedelta(seconds=seconds)
        )
        assert tasks == [release, task]
        assert release.time == reserved_start
        assert release.mood_limit_deadline == deadline
        assert task.time == order_start


def test_callback_binds_all_twenty_minute_runs_including_temporarily_blocked(planned):
    conf, owner, first = planned
    restoration = order(NOW)
    restoration.run_order_original_roster = {"room_2_1": ["图耶"]}
    restoration.run_order_restore_pending = True
    restoration.prepare_run_order_restoration()
    second = order(NOW + timedelta(minutes=8))
    boundary = order(NOW + timedelta(minutes=20))
    outside = order(NOW + timedelta(minutes=20, microseconds=1))
    tasks = [restoration, first, second, boundary, outside]
    assert id(second) in blocked_run_order_ids(tasks)
    callback = Mock(
        side_effect=lambda event: bind_run_order_network(
            tasks, owner, conf, event.observed_at
        )
    )
    adaptation = get_network_adaptation(owner)
    adaptation.set_observation_callback(callback)

    event = observe(owner)

    callback.assert_called_once_with(event)
    for task in (first, second, boundary):
        assert task.run_order_network_timing.event is event
        assert run_order_buffer_seconds(task, conf) == 45
    assert not hasattr(restoration, "run_order_network_timing")
    assert not hasattr(outside, "run_order_network_timing")


@pytest.mark.parametrize(
    "offset,eligible",
    [
        (timedelta(microseconds=-1), False),
        (timedelta(0), True),
        (timedelta(minutes=20), True),
        (timedelta(minutes=20, microseconds=1), False),
    ],
)
def test_binding_window_uses_original_start_between_now_and_twenty_minutes(
    planned, offset, eligible
):
    conf, owner, task = planned
    task.time = NOW + offset
    original = task.time
    observe(owner)

    bind_run_order_network([task], owner, conf, NOW)

    assert hasattr(task, "run_order_network_timing") is eligible
    assert task.time == original


@pytest.mark.parametrize("retained", [False, True])
def test_new_observation_does_not_replace_binding_after_its_original_start(
    planned, retained
):
    conf, owner, task = planned
    conf.run_order_delay = 1
    original = task.time
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    timing, applied = task.run_order_network_timing, task.time
    assert applied < original
    task.execution_retained = retained
    later = original + timedelta(microseconds=1)
    observe(owner, 60, now=later)

    bind_run_order_network([task], owner, conf, later)

    assert task.run_order_network_timing is timing
    assert task.time == applied
    assert run_order_buffer_seconds(task, conf) == 45


def test_rebinding_checks_original_future_start_even_when_applied_start_is_past(
    planned,
):
    conf, owner, task = planned
    original = NOW + timedelta(minutes=1)
    task.time = original
    observe(owner, 90)
    bind_run_order_network([task], owner, conf, NOW)
    applied = task.time
    assert applied < NOW < original
    later = NOW + timedelta(seconds=1)
    newer = observe(owner, 120, now=later)

    bind_run_order_network([task], owner, conf, later)

    assert task.run_order_network_timing.event is newer
    assert task.run_order_network_timing.base_time == original
    assert task.time == applied


def test_retained_past_failure_does_not_acquire_new_binding(planned):
    conf, owner, task = planned
    task.time = NOW - timedelta(minutes=1)
    task.execution_retained = True
    original = task.time
    observe(owner)

    bind_run_order_network([task], owner, conf, NOW)

    assert task.time == original
    assert not hasattr(task, "run_order_network_timing")


@pytest.mark.parametrize(
    "base_buffer,duration,expected",
    [
        (15, 9, 24),
        (50, 9, 50),
        (50, 25, 50),
        (50, 25.01, 75.01),
        (15, 7.5, 15),
        (15, 7.51, 22.51),
    ],
)
def test_binding_requires_strictly_more_than_half_the_original_buffer(
    planned, base_buffer, duration, expected
):
    conf, owner, task = planned
    conf.run_order_grandet_mode.buffer_time = base_buffer
    event = observe(owner, duration)
    bind_run_order_network([task], owner, conf, NOW)
    begin_run_order_network(task, owner, conf, NOW)

    assert run_order_buffer_seconds(task, conf) == pytest.approx(expected)
    assert conf.run_order_grandet_mode.buffer_time == base_buffer
    assert get_network_adaptation(owner).observations == (event,)
    assert hasattr(task, "run_order_network_timing") is (expected != base_buffer)


@pytest.mark.parametrize(
    "entry,duration,expected_buffer,expected_entry,advance",
    [
        (180, 30, 45, 180, 0),
        (180, 74.99, 89.99, 180, 0),
        (180, 75, 90, 270, 90),
        (180, 90, 105, 285, 105),
        (60, 30, 45, 105, 45),
    ],
)
def test_entry_advances_by_full_new_buffer_only_at_half_original_entry(
    planned, entry, duration, expected_buffer, expected_entry, advance
):
    conf, owner, task = planned
    conf.run_order_delay = entry / 60
    original = task.time
    completion = original + timedelta(seconds=entry)
    observe(owner, duration)

    for _ in range(3):
        bind_run_order_network([task], owner, conf, NOW)
        assert task.time == original - timedelta(seconds=advance)
        assert run_order_buffer_seconds(task, conf) == expected_buffer
        assert run_order_entry_seconds(task, conf) == expected_entry
        assert task.time + timedelta(seconds=expected_entry) == completion
    assert conf.run_order_delay == entry / 60
    assert conf.run_order_grandet_mode.buffer_time == 15
    assert run_order_end_time(task, task.time, conf=conf) >= completion + timedelta(
        seconds=45
    )


@pytest.mark.parametrize("duration", [90, 120, 180])
def test_run_order_caps_extra_buffer_at_ninety_seconds(planned, duration):
    conf, owner, task = planned
    conf.run_order_delay = 1
    original = task.time
    observe(owner, duration)
    bind_run_order_network([task], owner, conf, NOW)
    timing = begin_run_order_network(task, owner, conf, NOW)

    assert timing.event.duration_seconds == duration
    assert run_order_buffer_seconds(task, conf) == 105
    assert run_order_entry_seconds(task, conf) == 165
    assert task.time == original - timedelta(seconds=105)


def test_bound_twentieth_minute_task_starts_after_source_history_expires(
    planned, monkeypatch
):
    conf, owner, task = planned
    task.time = NOW + timedelta(minutes=20)
    event = observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    later = NOW + timedelta(minutes=20)
    adaptation = get_network_adaptation(owner)
    assert adaptation.peek_run_order(later, base_seconds=15) is None
    monkeypatch.setattr(
        adaptation,
        "peek_run_order",
        Mock(side_effect=AssertionError("execution must not rescan")),
    )

    timing = begin_run_order_network(task, owner, conf, later)

    assert timing.started
    assert timing.event is event
    assert run_order_buffer_seconds(task, conf) == 45
    adaptation.peek_run_order.assert_not_called()


def test_begin_without_binding_does_not_search_or_retroactively_bind_current_run(
    planned,
):
    conf, owner, first = planned
    second = order(NOW + timedelta(minutes=6))
    adaptation = get_network_adaptation(owner)
    adaptation.set_observation_callback(
        lambda event: bind_run_order_network(
            [first, second], owner, conf, event.observed_at
        )
    )

    assert begin_run_order_network(first, owner, conf, NOW) is None
    event = observe(owner)

    assert first.run_order_network_started is True
    assert not hasattr(first, "run_order_network_timing")
    assert second.run_order_network_timing.event is event


def test_finishing_first_run_keeps_shared_record_and_second_binding(planned):
    conf, owner, first = planned
    second = order(NOW + timedelta(minutes=6))
    event = observe(owner)
    bind_run_order_network([first, second], owner, conf, NOW)
    assert (
        get_network_adaptation(owner).take_wait("CONNECTING", NOW, base_seconds=30)
        is event
    )
    begin_run_order_network(first, owner, conf, NOW)

    finish_run_order_network(first)
    second_timing = begin_run_order_network(
        second, owner, conf, NOW + timedelta(minutes=6)
    )

    assert not hasattr(first, "run_order_network_timing")
    assert not hasattr(first, "run_order_network_started")
    assert second_timing.started and second_timing.event is event
    assert get_network_adaptation(owner).peek_run_order(NOW, base_seconds=15) is event
    assert (
        get_network_adaptation(owner).take_wait("LOADING", NOW, base_seconds=30) is None
    )


def test_largest_recent_event_is_shared_and_smaller_event_does_not_accumulate(planned):
    conf, owner, first = planned
    second = order(NOW + timedelta(minutes=6))
    largest = observe(owner, 30)
    observe(owner, 10, now=NOW + timedelta(seconds=1))

    bind_run_order_network([first, second], owner, conf, NOW + timedelta(seconds=2))

    for task in (first, second):
        assert task.run_order_network_timing.event is largest
        assert run_order_buffer_seconds(task, conf) == 45


def test_new_observation_can_update_pending_binding_without_moving_started_run(planned):
    conf, owner, first = planned
    conf.run_order_delay = 1
    second = order(NOW + timedelta(minutes=6))
    event = observe(owner, 30)
    bind_run_order_network([first, second], owner, conf, NOW)
    begun = begin_run_order_network(first, owner, conf, NOW)
    first_time = first.time
    original_second = second.run_order_network_timing.base_time
    later = NOW + timedelta(seconds=1)
    newer = observe(owner, 60, now=later)

    bind_run_order_network([first, second], owner, conf, later)

    assert begun.event is event
    assert first.run_order_network_timing is begun
    assert first.time == first_time
    assert second.run_order_network_timing.event is newer
    assert second.time == original_second - timedelta(seconds=75)


@pytest.mark.parametrize("conversion", ["disabled", "drone", "adjusted"])
@pytest.mark.parametrize("external_time", [False, True])
def test_unstarted_conversion_clears_binding_without_overwriting_external_deadline(
    planned, conversion, external_time
):
    conf, owner, task = planned
    conf.run_order_delay = 1
    original = task.time
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    replacement = NOW + timedelta(minutes=12)
    if external_time:
        task.time = replacement
    if conversion == "disabled":
        conf.run_order_network_adaptive = False
    elif conversion == "drone":
        conf.run_order_grandet_mode.enable = False
    else:
        task.adjusted = True

    assert begin_run_order_network(task, owner, conf, NOW) is None
    assert not hasattr(task, "run_order_network_timing")
    assert task.time == (replacement if external_time else original)


def test_external_order_reread_replaces_original_binding_deadline(planned):
    conf, owner, task = planned
    conf.run_order_delay = 1
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    new_time = NOW + timedelta(minutes=10)
    task.time = new_time
    observe(owner, 60, now=NOW + timedelta(seconds=1))

    bind_run_order_network([task], owner, conf, NOW + timedelta(seconds=1))

    assert task.run_order_network_timing.base_time == new_time
    assert task.time == new_time - timedelta(seconds=75)


@pytest.mark.parametrize("conversion", ["disabled", "drone", "adjusted"])
@pytest.mark.parametrize("external_time", [False, True])
def test_reconcile_only_clears_invalid_unstarted_bindings_before_dispatch(
    planned, conversion, external_time
):
    conf, owner, task = planned
    conf.run_order_delay = 1
    original = task.time
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    external = NOW + timedelta(minutes=12)
    if external_time:
        task.time = external
    if conversion == "disabled":
        conf.run_order_network_adaptive = False
    elif conversion == "drone":
        conf.run_order_grandet_mode.enable = False
    else:
        task.adjusted = True

    reconcile_run_order_network([task], conf)

    assert task.time == (external if external_time else original)
    assert not hasattr(task, "run_order_network_timing")
    assert not hasattr(task, "run_order_network_started")


def test_reconcile_preserves_newly_observed_external_time_without_rebinding(planned):
    conf, owner, task = planned
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    external = NOW + timedelta(minutes=12)
    task.time = external

    reconcile_run_order_network([task], conf)

    assert task.time == external
    assert not hasattr(task, "run_order_network_timing")


def test_reconcile_preserves_valid_binding_after_source_expiry_and_started_task(
    planned, monkeypatch
):
    conf, owner, task = planned
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    timing, applied = task.run_order_network_timing, task.time
    adaptation = get_network_adaptation(owner)
    assert (
        adaptation.peek_run_order(NOW + timedelta(minutes=30), base_seconds=15) is None
    )
    monkeypatch.setattr(
        adaptation, "peek_run_order", Mock(side_effect=AssertionError("no rescan"))
    )

    reconcile_run_order_network([task], conf)

    assert task.run_order_network_timing is timing
    assert task.time == applied
    begin_run_order_network(task, owner, conf, NOW + timedelta(minutes=30))
    conf.run_order_network_adaptive = False
    reconcile_run_order_network([task], conf)
    assert task.run_order_network_timing is timing
    assert timing.started
    adaptation.peek_run_order.assert_not_called()


def test_unstarted_retained_task_keeps_failure_timestamp_when_binding(planned):
    conf, owner, task = planned
    conf.run_order_delay = 1
    task.execution_retained = True
    original = task.time
    observe(owner)

    bind_run_order_network([task], owner, conf, NOW)

    assert task.time == original
    assert task.run_order_network_timing.buffer_seconds == 45
    clear_run_order_network(task)
    assert task.time == original


def test_started_task_keeps_snapshot_after_base_values_change(planned):
    conf, owner, task = planned
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    timing = begin_run_order_network(task, owner, conf, NOW)
    conf.run_order_delay = 5
    conf.run_order_grandet_mode.buffer_time = 50

    assert begin_run_order_network(task, owner, conf, NOW) is timing
    assert run_order_buffer_seconds(task, conf) == 45
    assert run_order_entry_seconds(task, conf) == 180


@pytest.mark.parametrize("conversion", ["drone", "adjusted"])
def test_inflight_conversion_stops_inherited_allowance(
    planned, monkeypatch, conversion
):
    conf, owner, task = planned
    monkeypatch.setattr(config, "conf", conf)
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    subject = SimpleNamespace(task=task, recog=owner)

    with run_order_network_scope(subject):
        assert run_order_network_compensation(owner, conf) == 30
        if conversion == "drone":
            conf.run_order_grandet_mode.enable = False
        else:
            task.adjusted = True
        assert run_order_network_compensation(owner, conf) == 0
        assert run_order_network_allowance(task, conf) == 0
        assert not hasattr(task, "run_order_network_timing")
    assert "_run_order_network_compensation" not in owner.__dict__


def test_scope_does_not_leak_allowance_when_current_task_changes(planned, monkeypatch):
    conf, owner, task = planned
    monkeypatch.setattr(config, "conf", conf)
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    subject = SimpleNamespace(task=task, recog=owner)

    with run_order_network_scope(subject):
        subject.task = order(NOW)
        assert run_order_network_compensation(owner, conf) == 0
        subject.task = task
        assert run_order_network_compensation(owner, conf) == 30


@pytest.mark.parametrize("initial_binding", [False, True])
def test_observation_during_scope_cleanup_does_not_rebind_finished_current_run(
    planned, monkeypatch, initial_binding
):
    conf, owner, first = planned
    monkeypatch.setattr(config, "conf", conf)
    second = order(NOW + timedelta(minutes=6))
    tasks = [first, second]
    adaptation = get_network_adaptation(owner)
    adaptation.set_observation_callback(
        lambda event: bind_run_order_network(tasks, owner, conf, event.observed_at)
    )
    if initial_binding:
        observe(owner)
    subject = SimpleNamespace(task=first, recog=owner)

    with run_order_network_scope(subject):
        assert owner._run_order_network_dispatch_task is first
        with run_order_network_scope(subject):
            finish_run_order_network(first, owner)
        assert owner._run_order_network_dispatch_task is first
        event = observe(owner, 60, now=NOW + timedelta(seconds=1))
        assert not hasattr(first, "run_order_network_timing")
        assert second.run_order_network_timing.event is event
    assert "_run_order_network_dispatch_task" not in owner.__dict__


def test_nested_unbound_task_does_not_inherit_another_solvers_allowance(
    planned, monkeypatch
):
    conf, owner, task = planned
    monkeypatch.setattr(config, "conf", conf)
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    outer = SimpleNamespace(task=task, recog=owner)
    inner = SimpleNamespace(task=order(NOW), recog=owner)

    with run_order_network_scope(outer):
        assert run_order_network_compensation(owner, conf) == 30
        with run_order_network_scope(inner):
            assert run_order_network_compensation(owner, conf) == 0
        assert run_order_network_compensation(owner, conf) == 30


@pytest.mark.parametrize(
    "task_type", [TaskTypes.SHIFT_OFF, TaskTypes.FIAMMETTA, TaskTypes.RUN_ORDER]
)
def test_decorated_arrangement_without_recognizer_keeps_its_existing_contract(
    task_type,
):
    task = SchedulerTask(
        NOW,
        {ROOM: ["图耶"]},
        task_type,
        ROOM if task_type == TaskTypes.RUN_ORDER else "",
    )
    solver = SimpleNamespace(task=task, tasks=[task])
    calls = []

    @with_run_order_network
    def arrange(subject, plan):
        assert subject.task is task
        calls.append(plan)
        return "arranged"

    assert arrange(solver, task.plan) == "arranged"
    assert calls == [{ROOM: ["图耶"]}]
    assert not hasattr(solver, "recog")
    assert not hasattr(task, "run_order_network_timing")
    assert not hasattr(task, "run_order_network_started")


def test_nested_non_run_order_suppresses_shared_recognizer_compensation(
    planned, monkeypatch
):
    conf, owner, task = planned
    monkeypatch.setattr(config, "conf", conf)
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    outer = SimpleNamespace(task=task, recog=owner)
    shift = SchedulerTask(NOW, {ROOM: ["图耶"]}, TaskTypes.SHIFT_OFF)
    inner = SimpleNamespace(task=shift, recog=owner)

    @with_run_order_network
    def arrange(subject):
        assert run_order_network_compensation(subject.recog, conf) == 0
        assert subject.recog._run_order_network_dispatch_task is task

    with run_order_network_scope(outer):
        assert run_order_network_compensation(owner, conf) == 30
        arrange(inner)
        assert run_order_network_compensation(owner, conf) == 30
        assert owner._run_order_network_dispatch_task is task
    assert "_run_order_network_active" not in owner.__dict__


def test_nested_scope_and_failed_restoration_keep_binding_until_explicit_finish(
    planned, monkeypatch
):
    conf, owner, task = planned
    monkeypatch.setattr(config, "conf", conf)
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    subject = SimpleNamespace(task=task, recog=owner)

    @with_run_order_network
    def nested(current):
        assert run_order_network_compensation(current.recog, conf) == 30

    with pytest.raises(RuntimeError, match="restore failed"):
        with run_order_network_scope(subject):
            nested(subject)
            assert run_order_network_compensation(owner, conf) == 30
            task.run_order_original_roster = {ROOM: ["图耶"]}
            task.run_order_restore_pending = True
            task.prepare_run_order_restoration()
            raise RuntimeError("restore failed")
    assert task.run_order_network_timing.started
    assert "_run_order_network_compensation" not in owner.__dict__

    with run_order_network_scope(subject):
        assert run_order_network_compensation(owner, conf) == 30
        assert run_order_network_allowance(task, conf) == 30
        del task.run_order_restore_pending
        finish_run_order_network(task, owner)
        assert run_order_network_compensation(owner, conf) == 0
    assert not hasattr(task, "run_order_network_timing")
    assert not hasattr(task, "run_order_network_started")


def test_real_confirmation_uses_bound_buffer_without_extra_five_seconds(
    staffed_order, monkeypatch
):
    ui = staffed_order
    solver = ui.solver
    ui.config.conf.run_order_network_adaptive = True
    ui.config.conf.run_order_delay = 3
    ui.config.conf.run_order_grandet_mode.buffer_time = 15
    monkeypatch.setattr(ui.config, "screenshot_avg", 0)
    task = ui.task(ui.clock.now(), {ROOM: ["但书"]}, ui.task_type.RUN_ORDER, ROOM)
    solver.task, solver.tasks = task, [task]
    solver.op_data.run_order_rooms[ROOM] = ["但书"]
    observe(solver.recog, now=ui.clock.now())
    bind_run_order_network([task], solver.recog, ui.config.conf, ui.clock.now())
    begin_run_order_network(task, solver.recog, ui.config.conf, ui.clock.now())
    solver.find = MagicMock(return_value=None)
    solver.sleep = MagicMock()

    ui.base.BaseSchedulerSolver.tap_confirm(solver, ROOM, {ROOM: ["图耶"]})

    solver.sleep.assert_called_once_with(135.0)


def test_drone_reread_replaces_binding_even_when_new_time_equals_old_applied_time(
    staffed_order, monkeypatch
):
    ui = staffed_order
    ui.config.conf.run_order_network_adaptive = True
    ui.config.conf.run_order_delay = 1
    ui.config.conf.run_order_grandet_mode.buffer_time = 15
    task = ui.task(
        ui.clock.now() + timedelta(seconds=300),
        {ROOM: ["但书"]},
        ui.task_type.RUN_ORDER,
        ROOM,
    )
    ui.solver.task, ui.solver.tasks = task, [task]
    observe(ui.solver.recog, 90, now=ui.clock.now())
    bind_run_order_network([task], ui.solver.recog, ui.config.conf, ui.clock.now())
    old_applied = task.time
    new_completion = old_applied + timedelta(seconds=60)
    monkeypatch.setattr(ui.base, "scheduling", MagicMock(side_effect=[[task], None]))
    ui.solver.get_run_order_adjust_room = MagicMock(return_value=ROOM)
    ui.solver.digit_reader = SimpleNamespace(get_drone=MagicMock(return_value=100))
    ui.solver.recog.gray = object()
    ui.solver._wait_drone_interface = MagicMock()
    ui.solver.double_read_time = MagicMock(return_value=new_completion)
    ui.solver.tap = MagicMock()

    ui.solver.adjust_order_time((500, 700), ROOM)

    assert task.time == old_applied
    assert not hasattr(task, "run_order_network_timing")
    observe(ui.solver.recog, 90, now=ui.clock.now() + timedelta(seconds=1))
    bind_run_order_network(
        [task], ui.solver.recog, ui.config.conf, ui.clock.now() + timedelta(seconds=1)
    )
    assert task.run_order_network_timing.base_time == old_applied
    assert task.time == new_completion - timedelta(seconds=165)


def test_real_insertion_uses_bound_window_and_restores_original_roster(
    staffed_order, monkeypatch
):
    ui = staffed_order
    solver = ui.solver
    monkeypatch.setattr(run_order_network, "datetime", ui.clock)
    ui.config.conf.run_order_network_adaptive = True
    ui.config.conf.run_order_delay = 1
    ui.config.conf.run_order_grandet_mode.buffer_time = 15
    ui.occupants[ROOM] = ["图耶"]
    ui.states[ROOM] = "active"
    solver.get_agent_from_room(ROOM)
    task = ui.task(ui.clock.now(), {ROOM: ["但书"]}, ui.task_type.RUN_ORDER, ROOM)
    solver.task, solver.tasks = task, [task]
    observe(solver.recog, now=ui.clock.now())
    bind_run_order_network([task], solver.recog, ui.config.conf, ui.clock.now())
    solver.get_order_remaining_time.side_effect = [90, 110]

    assert solver.agent_arrange(task.plan) is not False

    ui.base.send_message.assert_not_called()
    assert ui.occupants[ROOM] == ["图耶"]
    assert not hasattr(task, "run_order_restore_pending")
    assert "_run_order_network_compensation" not in solver.recog.__dict__


def test_pickled_task_snapshots_load_without_network_modules_and_preserve_plain_tasks(
    planned,
):
    conf, owner, task = planned
    conf.run_order_delay = 1
    original = task.time
    observe(owner, 90)
    bind_run_order_network([task], owner, conf, NOW)
    get_network_adaptation(owner).set_observation_callback(lambda event: None)
    plain = order(NOW + timedelta(minutes=8), "room_2_1")

    payload = pickle.dumps({"tasks": [task, plain]}, protocol=pickle.HIGHEST_PROTOCOL)
    restored, plain_restored = WithoutNetworkModules(io.BytesIO(payload)).load()[
        "tasks"
    ]

    assert type(restored.run_order_network_timing) is dict
    assert type(restored.run_order_network_timing["event"]) is dict
    assert restored.time == task.time == original - timedelta(seconds=105)
    assert restored.plan == task.plan
    assert restored.meta_data == task.meta_data
    assert vars(plain_restored) == vars(plain)
    assert not hasattr(plain_restored, "run_order_network_timing")
    assert run_order_entry_seconds(restored, conf) == 165
    assert run_order_buffer_seconds(restored, conf) == 105
    second_payload = pickle.dumps({"tasks": [restored]})
    second = WithoutNetworkModules(io.BytesIO(second_payload)).load()["tasks"][0]
    assert type(second.run_order_network_timing) is dict
    assert second.time == restored.time


def test_deepcopied_binding_hydrates_independently_and_preserves_original_deadline(
    planned,
):
    conf, owner, task = planned
    conf.run_order_delay = 1
    original = task.time
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    timing = task.run_order_network_timing

    projected = copy.deepcopy(task)

    assert type(projected.run_order_network_timing) is dict
    assert projected.time == task.time == original - timedelta(seconds=45)
    assert run_order_entry_seconds(projected, conf) == 105
    assert run_order_buffer_seconds(projected, conf) == 45
    assert projected.run_order_network_timing is not timing
    assert projected.run_order_network_timing.event is not timing.event
    projected.plan[ROOM][0] = "龙舌兰"
    assert task.plan[ROOM] == ["但书"]
    projected.adjusted = True
    reconcile_run_order_network([projected], conf)
    assert projected.time == original
    assert not hasattr(projected, "run_order_network_timing")
    assert task.time == original - timedelta(seconds=45)
    assert task.run_order_network_timing is timing
    assert timing.started is False


def test_pickled_restoration_restarts_with_expired_source_without_losing_roster(
    planned, monkeypatch
):
    conf, owner, task = planned
    monkeypatch.setattr(config, "conf", conf)
    observe(owner)
    bind_run_order_network([task], owner, conf, NOW)
    begin_run_order_network(task, owner, conf, NOW)
    task.run_order_original_roster = {ROOM: ["图耶"]}
    task.run_order_restore_pending = True
    task.prepare_run_order_restoration()
    original_time = task.time
    payload = pickle.dumps({"tasks": [task]})
    restored = WithoutNetworkModules(io.BytesIO(payload)).load()["tasks"][0]
    later = NOW + timedelta(minutes=30)
    assert get_network_adaptation(owner).peek_run_order(later, base_seconds=15) is None
    resumed_owner = SimpleNamespace()
    resumed_adaptation = get_network_adaptation(resumed_owner)
    listener = Mock()
    resumed_adaptation.set_observation_callback(listener)

    timing = begin_run_order_network(restored, resumed_owner, conf, later)

    assert timing.started
    assert timing.event.observed_at == NOW
    assert restored.time == original_time
    assert restored.run_order_original_roster == {ROOM: ["图耶"]}
    assert restored.plan == {ROOM: ["图耶"]}
    assert restored.meta_data == ""
    assert resumed_adaptation.observations == ()
    solver = SimpleNamespace(task=restored, recog=resumed_owner)
    with pytest.raises(RuntimeError, match="restore interrupted"):
        with run_order_network_scope(solver):
            assert run_order_network_compensation(resumed_owner, conf) == 30
            assert run_order_network_allowance(restored, conf) == 30
            raise RuntimeError("restore interrupted")
    assert restored.run_order_restore_pending is True
    assert restored.time == original_time
    with run_order_network_scope(solver):
        assert run_order_network_compensation(resumed_owner, conf) == 30
        del restored.run_order_original_roster
        del restored.run_order_restore_pending
        finish_run_order_network(restored, resumed_owner)
        assert run_order_network_compensation(resumed_owner, conf) == 0
    assert not hasattr(restored, "run_order_network_timing")
    assert restored.time == original_time
    listener.assert_not_called()
