"""网络等待只提前一次跑单，确认、窗口检查与恢复使用同一份参数。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.run_order_staffing_admission_tests import (
    staffed_order as staffed_order,
)
from arknights_mower.utils import config, run_order_network
from arknights_mower.utils.network_adaptation import get_network_adaptation
from arknights_mower.utils.news_checker import NewsChecker
from arknights_mower.utils.run_order_network import (
    begin_run_order_network,
    refresh_run_order_network,
    run_order_buffer_seconds,
    run_order_entry_seconds,
)
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    run_order_end_time,
)

NOW = datetime(2026, 10, 28, 19, 50)
ROOM = "room_1_1"


@pytest.fixture
def planned():
    conf = config.Conf()
    conf.run_order_network_adaptive = True
    conf.run_order_delay = 3
    conf.run_order_grandet_mode.enable = True
    conf.run_order_grandet_mode.buffer_time = 15
    owner = SimpleNamespace()
    task = SchedulerTask(
        NOW + timedelta(minutes=2), {ROOM: ["但书"]}, TaskTypes.RUN_ORDER, ROOM
    )
    return conf, owner, task


def observe(owner, seconds=30, *, now=NOW, timed_out=True):
    return get_network_adaptation(owner).record(
        "CONNECTING",
        elapsed_seconds=seconds,
        base_seconds=30,
        observed_at=now,
        timed_out=timed_out,
    )


def test_preview_adds_only_observed_delay_and_does_not_consume_or_drift(planned):
    conf, owner, task = planned
    event = observe(owner)
    original = task.time
    for _ in range(5):
        refresh_run_order_network([task], owner, conf, NOW)
        assert task.time == original
        assert run_order_entry_seconds(task, conf) == 180
        assert run_order_buffer_seconds(task, conf) == 45
    assert get_network_adaptation(owner).peek_run_order(NOW, base_seconds=15) == event
    assert conf.run_order_grandet_mode.buffer_time == 15
    assert conf.run_order_delay == 3


@pytest.mark.parametrize(
    "base_buffer,elapsed,expected",
    [(15, 9, 24), (50, 9, 50), (50, 25, 75), (15, 7.5, 22.5), (15, 7.49, 15)],
)
def test_real_run_order_policy_uses_half_of_saved_buffer(
    planned, base_buffer, elapsed, expected
):
    conf, owner, task = planned
    conf.run_order_grandet_mode.buffer_time = base_buffer
    original = task.time
    event = observe(owner, elapsed, timed_out=False)
    refresh_run_order_network([task], owner, conf, NOW)
    begin_run_order_network(task, owner, conf, NOW)
    assert run_order_buffer_seconds(task, conf) == expected
    assert conf.run_order_grandet_mode.buffer_time == base_buffer
    assert get_network_adaptation(owner).observations == (event,)
    if expected == base_buffer:
        assert task.time == original
        assert not hasattr(task, "run_order_network_timing")


def test_later_run_uses_original_buffer_rather_than_previous_compensation(planned):
    conf, owner, first = planned
    observe(owner, 9, timed_out=False)
    begin_run_order_network(first, owner, conf, NOW)
    assert run_order_buffer_seconds(first, conf) == 24
    second = SchedulerTask(
        first.time + timedelta(minutes=2), {ROOM: ["但书"]}, TaskTypes.RUN_ORDER, ROOM
    )
    later = NOW + timedelta(seconds=1)
    observe(owner, 8, now=later, timed_out=False)
    begin_run_order_network(second, owner, conf, later)
    assert run_order_buffer_seconds(second, conf) == 23
    assert conf.run_order_grandet_mode.buffer_time == 15


def test_earlier_entry_preserves_completion_and_priority_window(planned):
    conf, owner, task = planned
    conf.run_order_delay = 1
    completion = task.time + timedelta(seconds=60)
    observe(owner, 90)
    refresh_run_order_network([task], owner, conf, NOW)
    assert run_order_buffer_seconds(task, conf) == 105
    assert run_order_entry_seconds(task, conf) == 150
    assert task.time == completion - timedelta(seconds=150)
    assert run_order_end_time(task, task.time, conf=conf) == completion + timedelta(
        seconds=45
    )


@pytest.mark.parametrize("disable", [False, True])
def test_expired_or_disabled_preview_restores_original_time(planned, disable):
    conf, owner, task = planned
    conf.run_order_delay = 1
    observe(owner, 90)
    original = task.time
    refresh_run_order_network([task], owner, conf, NOW)
    assert task.time < original
    conf.run_order_network_adaptive = not disable
    now = NOW if disable else NOW + timedelta(minutes=15)
    refresh_run_order_network([task], owner, conf, now)
    assert task.time == original
    assert not hasattr(task, "run_order_network_timing")


def test_execution_consumes_once_independently_of_next_scene_wait(planned):
    conf, owner, task = planned
    event = observe(owner)
    assert (
        get_network_adaptation(owner).take_wait("CONNECTING", NOW, base_seconds=30)
        == event
    )
    first = begin_run_order_network(task, owner, conf, NOW)
    assert first is not None and first.started
    assert begin_run_order_network(task, owner, conf, NOW) is first
    next_task = SchedulerTask(task.time, {ROOM: ["但书"]}, TaskTypes.RUN_ORDER, ROOM)
    refresh_run_order_network([task, next_task], owner, conf, NOW)
    assert not hasattr(next_task, "run_order_network_timing")
    assert run_order_buffer_seconds(task, conf) == 45


def test_execution_logs_approved_text_once_and_preview_emits_no_log(
    planned, monkeypatch
):
    from arknights_mower.utils import log

    conf, owner, task = planned
    logger = MagicMock()
    monkeypatch.setattr(log, "logger", logger)
    observe(owner)
    for _ in range(3):
        refresh_run_order_network([task], owner, conf, NOW)
    logger.info.assert_not_called()
    begin_run_order_network(task, owner, conf, NOW)
    begin_run_order_network(task, owner, conf, NOW)
    logger.info.assert_called_once_with(
        "近15分钟内出现过网络卡顿，本次 %s 跑单的葛朗台缓冲时间由%s秒增加至%s秒。",
        ROOM,
        "15",
        "45",
    )


def test_external_deadline_change_is_not_rolled_back(planned):
    conf, owner, task = planned
    observe(owner)
    refresh_run_order_network([task], owner, conf, NOW)
    replacement_time = task.time + timedelta(minutes=10)
    task.time, task.adjusted = replacement_time, True
    refresh_run_order_network([task], owner, conf, NOW)
    assert task.time == replacement_time
    assert not hasattr(task, "run_order_network_timing")


def test_retained_preview_keeps_original_failure_time(planned):
    conf, owner, task = planned
    conf.run_order_delay = 1
    observe(owner, 90)
    refresh_run_order_network([task], owner, conf, NOW)
    retained_time = task.time
    task.execution_retained = True
    for now in (NOW, NOW + timedelta(minutes=30)):
        refresh_run_order_network([task], owner, conf, now)
        assert task.time == retained_time
    assert (
        begin_run_order_network(task, owner, conf, NOW + timedelta(minutes=30)) is None
    )
    assert task.time == retained_time


def test_retained_execution_can_use_new_evidence_without_changing_time(planned):
    conf, owner, task = planned
    task.execution_retained = True
    original = task.time
    observe(owner)
    timing = begin_run_order_network(task, owner, conf, NOW)
    assert timing.started and timing.buffer_seconds == 45
    assert task.time == original


def test_daily_refresh_uses_observed_completion_after_earlier_entry(
    planned, monkeypatch
):
    conf, owner, task = planned
    conf.run_order_delay = 1
    now = NOW.replace(hour=3, minute=50)
    reset = now.replace(hour=4, minute=0)
    task.time = reset
    observe(owner, 120, now=now)
    refresh_run_order_network([task], owner, conf, now)
    assert task.time == reset - timedelta(minutes=2)
    monkeypatch.setattr(config, "conf", conf)
    monkeypatch.setattr(
        NewsChecker,
        "get_daily_reset",
        lambda now: SimpleNamespace(start=reset, end=reset),
    )
    monkeypatch.setattr(NewsChecker, "get_update_time", lambda: (None, None))
    from arknights_mower.utils.scheduler_task import adjust_run_order_for_maintenance

    adjust_run_order_for_maintenance([task], now=now)
    assert task.adjusted
    assert task.time == reset - timedelta(minutes=5)


def test_real_dispatch_previews_before_original_start(staffed_order, monkeypatch):
    ui = staffed_order
    monkeypatch.setattr(run_order_network, "datetime", ui.clock)
    ui.config.conf.run_order_network_adaptive = True
    ui.config.conf.run_order_delay = 1
    ui.config.conf.run_order_grandet_mode.buffer_time = 15
    original = ui.clock.now() + timedelta(seconds=60)
    task = ui.task(original, {ROOM: ["但书"]}, ui.task_type.RUN_ORDER, ROOM)
    ui.solver.tasks = [task]
    observe(ui.solver.recog, 90, now=ui.clock.now())
    assert ui.solver.find_next_task() is task
    assert task.time == original - timedelta(seconds=90)
    for _ in range(3):
        assert ui.solver.find_next_task() is task
        assert task.time == original - timedelta(seconds=90)


def test_main_loop_uses_network_adjusted_appointment(staffed_order, monkeypatch):
    from arknights_mower import __main__ as mower_main

    ui = staffed_order
    monkeypatch.setattr(mower_main, "base_scheduler", ui.solver)
    ui.config.conf.run_order_network_adaptive = True
    ui.config.conf.run_order_delay = 1
    ui.config.conf.run_order_grandet_mode.buffer_time = 15
    original = ui.clock.now() + timedelta(seconds=60)
    task = ui.task(original, {ROOM: ["但书"]}, ui.task_type.RUN_ORDER, ROOM)
    ui.solver.tasks = [task]
    observe(ui.solver.recog, 90, now=ui.clock.now())
    assert mower_main._next_scheduler_task() is task
    assert task.time == original - timedelta(seconds=90)


def test_real_confirmation_uses_extra_buffer_without_extra_five_seconds(
    staffed_order, monkeypatch
):
    ui = staffed_order
    solver = ui.solver
    monkeypatch.setattr(run_order_network, "datetime", ui.clock)
    ui.config.conf.run_order_network_adaptive = True
    ui.config.conf.run_order_grandet_mode.buffer_time = 15
    monkeypatch.setattr(ui.config, "screenshot_avg", 0)
    task = ui.task(ui.clock.now(), {ROOM: ["但书"]}, ui.task_type.RUN_ORDER, ROOM)
    solver.task, solver.tasks = task, [task]
    solver.op_data.run_order_rooms[ROOM] = ["但书"]
    observe(solver.recog, now=ui.clock.now())
    begin_run_order_network(task, solver.recog, ui.config.conf, ui.clock.now())
    solver.find = MagicMock(return_value=None)
    solver.sleep = MagicMock()
    ui.base.BaseSchedulerSolver.tap_confirm(solver, ROOM, {ROOM: ["图耶"]})
    solver.sleep.assert_called_once_with(135.0)


def test_real_insertion_uses_extended_window_and_restores_roster(
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
    solver.get_order_remaining_time.side_effect = [90, 110]
    assert solver.agent_arrange(task.plan) is not False
    ui.base.send_message.assert_not_called()
    assert ui.occupants[ROOM] == ["图耶"]
    assert not hasattr(task, "run_order_restore_pending")
    assert "_run_order_network_compensation" not in solver.recog.__dict__


def test_unstarted_insertion_failure_does_not_freeze_expired_allowance(
    staffed_order, monkeypatch
):
    ui = staffed_order
    monkeypatch.setattr(run_order_network, "datetime", ui.clock)
    ui.config.conf.run_order_network_adaptive = True
    ui.config.conf.run_order_grandet_mode.buffer_time = 15
    task = ui.task(ui.clock.now(), {ROOM: ["但书"]}, ui.task_type.RUN_ORDER, ROOM)
    ui.solver.task, ui.solver.tasks = task, [task]
    observe(ui.solver.recog, now=ui.clock.now())
    assert ui.solver.agent_arrange(task.plan) is False
    retained_time = task.time
    assert task.retains_execution
    assert not hasattr(task, "run_order_network_timing")
    ui.clock.current += timedelta(hours=1)
    refresh_run_order_network([task], ui.solver.recog, ui.config.conf, ui.clock.now())
    assert task.time == retained_time
    assert run_order_buffer_seconds(task, ui.config.conf) == 15


def test_drone_reread_replaces_preview_even_if_base_time_matches_old_applied_time(
    staffed_order, monkeypatch
):
    ui = staffed_order
    ui.config.conf.run_order_network_adaptive = True
    ui.config.conf.run_order_delay = 1
    ui.config.conf.run_order_grandet_mode.buffer_time = 15
    task = ui.task(
        ui.clock.now() + timedelta(seconds=60),
        {ROOM: ["但书"]},
        ui.task_type.RUN_ORDER,
        ROOM,
    )
    ui.solver.task, ui.solver.tasks = task, [task]
    observe(ui.solver.recog, 90, now=ui.clock.now())
    refresh_run_order_network([task], ui.solver.recog, ui.config.conf, ui.clock.now())
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
    refresh_run_order_network([task], ui.solver.recog, ui.config.conf, ui.clock.now())
    assert task.time == new_completion - timedelta(seconds=150)


def test_retained_unstarted_preview_uses_new_base_buffer_without_changing_time(planned):
    conf, owner, task = planned
    conf.run_order_delay = 1
    observe(owner, 30)
    refresh_run_order_network([task], owner, conf, NOW)
    assert run_order_buffer_seconds(task, conf) == 45
    assert run_order_entry_seconds(task, conf) == 90
    retained_time = task.time
    task.execution_retained = True
    conf.run_order_grandet_mode.buffer_time = 50

    timing = begin_run_order_network(task, owner, conf, NOW)

    assert timing.started
    assert task.time == retained_time
    assert run_order_buffer_seconds(task, conf) == 80
    assert run_order_entry_seconds(task, conf) == 125
    assert conf.run_order_grandet_mode.buffer_time == 50


def test_retained_unstarted_preview_drops_fact_below_new_half_without_consuming_it(
    planned,
):
    conf, owner, task = planned
    conf.run_order_delay = 1
    event = observe(owner, 30)
    refresh_run_order_network([task], owner, conf, NOW)
    retained_time = task.time
    task.execution_retained = True
    conf.run_order_grandet_mode.buffer_time = 70

    assert begin_run_order_network(task, owner, conf, NOW) is None

    assert task.time == retained_time
    assert not hasattr(task, "run_order_network_timing")
    assert run_order_buffer_seconds(task, conf) == 70
    assert get_network_adaptation(owner).peek_run_order(NOW, base_seconds=15) == event


@pytest.mark.parametrize("new_base", [50, 70])
def test_started_retained_run_keeps_its_snapshot_when_base_buffer_changes(
    planned, new_base
):
    conf, owner, task = planned
    conf.run_order_delay = 1
    observe(owner, 30)
    started = begin_run_order_network(task, owner, conf, NOW)
    assert started.started
    assert started.buffer_seconds == 45
    assert started.entry_seconds == 90
    retained_time = task.time
    task.execution_retained = True
    conf.run_order_grandet_mode.buffer_time = new_base

    assert begin_run_order_network(task, owner, conf, NOW) is started

    assert task.time == retained_time
    assert run_order_buffer_seconds(task, conf) == 45
    assert run_order_entry_seconds(task, conf) == 90
    assert conf.run_order_grandet_mode.buffer_time == new_base
