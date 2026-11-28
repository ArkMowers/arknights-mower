"""联网记录在实际调度入口绑定，导航和原班恢复共用任务补偿。"""

from datetime import timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.run_order_staffing_admission_tests import (
    staffed_order as staffed_order,
)
from arknights_mower.utils.network_adaptation import get_network_adaptation
from arknights_mower.utils.run_order_network import (
    finish_run_order_network,
    run_order_buffer_seconds,
    run_order_network_compensation,
    run_order_network_scope,
)


@pytest.fixture
def scheduler(staffed_order, monkeypatch):
    ui = staffed_order
    owner = SimpleNamespace()

    def initialize_parent(instance, device=None, recog=None, **kwargs):
        instance.device, instance.recog = device, recog

    monkeypatch.setattr(ui.base.SceneGraphSolver, "__init__", initialize_parent)
    monkeypatch.setattr(ui.base, "DigitReader", MagicMock())
    monkeypatch.setattr(ui.base, "TradingOrder", MagicMock())
    monkeypatch.setattr(ui.base, "workshop_inventory_changed", Event())
    ui.config.conf.run_order_network_adaptive = True
    ui.config.conf.run_order_grandet_mode.enable = True
    ui.config.conf.run_order_grandet_mode.buffer_time = 15
    ui.config.conf.run_order_delay = 3
    ui.solver = ui.base.BaseSchedulerSolver(device=MagicMock(), recog=owner)
    return ui


def task(ui, minutes, room="room_1_1"):
    return ui.task(
        ui.clock.now() + timedelta(minutes=minutes),
        {room: ["但书"]},
        ui.task_type.RUN_ORDER,
        room,
    )


def record(ui, seconds):
    return get_network_adaptation(ui.solver.recog).record(
        "CONNECTING",
        elapsed_seconds=seconds,
        base_seconds=30,
        observed_at=ui.clock.now(),
    )


def stub_dispatch_external_work(ui, monkeypatch):
    solver = ui.solver
    for name in (
        "_discard_legacy_mood_control_tasks",
        "_refresh_observed_recovery_tasks",
        "_resume_failed_tasks",
        "handle_error",
        "_emergency_filter_tasks",
        "_schedule_maintenance_backup_check",
        "_sync_run_order_tasks",
        "_resume_waiting_group_shifts",
        "_fill_empty_dorms",
        "_discard_product_switches",
        "queue_product_switches",
    ):
        monkeypatch.setattr(solver, name, MagicMock())
    monkeypatch.setattr(ui.base, "sync_replacement_checks", MagicMock())
    monkeypatch.setattr(ui.base, "scheduling", MagicMock())
    monkeypatch.setattr(ui.base, "save_log", MagicMock())
    monkeypatch.setattr(ui.config, "stop_mower", Event())
    monkeypatch.setattr(ui.config, "maintenance_recheck", Event())
    monkeypatch.setattr(solver.op_data, "correct_dorm", MagicMock())
    solver.party_time = solver.free_clue = solver.credit_fight = None
    solver.backup_plan_solver = MagicMock()
    solver._emergency_frozen = MagicMock(return_value=False)


def test_constructor_callback_binds_twenty_minute_tasks_without_a_queue_query(
    scheduler,
):
    ui = scheduler
    first, second, outside = task(ui, 2), task(ui, 20, "room_2_1"), task(ui, 20.1)
    ui.solver.tasks = [first, second, outside]

    record(ui, 40)

    assert run_order_buffer_seconds(first, ui.config.conf) == 55
    assert run_order_buffer_seconds(second, ui.config.conf) == 55
    assert not hasattr(outside, "run_order_network_timing")
    ui.solver.device.assert_not_called()


def test_queue_queries_do_not_reconsider_a_task_that_enters_the_window(scheduler):
    ui = scheduler
    later = task(ui, 21)
    ui.solver.tasks = [later]
    original = later.time
    record(ui, 30)
    ui.clock.current += timedelta(minutes=2)

    for _ in range(3):
        ui.solver.find_next_task()

    assert later.time == original
    assert not hasattr(later, "run_order_network_timing")


def test_protected_first_order_records_a_new_wait_for_a_run_fifteen_minutes_later(
    scheduler,
):
    ui = scheduler
    first, second = task(ui, 1), task(ui, 25, "room_2_1")
    ui.solver.tasks = [first, second]
    record(ui, 30)
    ui.clock.current += timedelta(minutes=10)
    ui.solver.task = first

    with run_order_network_scope(ui.solver):
        assert run_order_network_compensation(ui.solver.recog, ui.config.conf) == 30
        record(ui, 40)
        assert first.run_order_network_timing.event.duration_seconds == 30
        finish_run_order_network(first, ui.solver.recog)

    ui.clock.current += timedelta(minutes=15)
    ui.solver.task = second
    with run_order_network_scope(ui.solver):
        assert run_order_network_compensation(ui.solver.recog, ui.config.conf) == 40
        assert run_order_buffer_seconds(second, ui.config.conf) == 55
    assert not hasattr(first, "run_order_network_timing")


@pytest.mark.parametrize("interrupted", [False, True])
def test_real_run_protects_initial_navigation_and_retains_failed_restoration(
    staffed_order, monkeypatch, interrupted
):
    ui = staffed_order
    solver = ui.solver
    ui.config.conf.run_order_network_adaptive = True
    ui.config.conf.run_order_grandet_mode.enable = True
    ui.config.conf.run_order_grandet_mode.buffer_time = 15
    solver.recog = SimpleNamespace()
    solver.tasks = [task(ui, 1)]
    solver.task = None
    solver._register_network_wait_observer()
    record(ui, 30)
    selected = solver.tasks[0]
    ui.clock.current += timedelta(minutes=1)
    stub_dispatch_external_work(ui, monkeypatch)
    observed = []

    def navigation():
        observed.append(run_order_network_compensation(solver.recog, ui.config.conf))

    def transition():
        observed.append(run_order_network_compensation(solver.recog, ui.config.conf))
        if interrupted:
            selected.run_order_restore_pending = True
            raise RuntimeError("restoration interrupted")
        solver.tasks.clear()
        return True

    solver.check_current_focus = MagicMock(side_effect=navigation)
    solver.transition = MagicMock(side_effect=transition)
    if interrupted:
        with pytest.raises(RuntimeError, match="restoration interrupted"):
            solver.run()
    else:
        assert solver.run() is True

    assert observed == [30, 30]
    assert "_run_order_network_task" not in solver.recog.__dict__
    assert hasattr(selected, "run_order_network_timing") is interrupted


@pytest.mark.parametrize("conversion", ["disabled", "drone", "adjusted"])
def test_real_run_waits_for_original_time_after_unstarted_binding_is_invalidated(
    staffed_order, monkeypatch, conversion
):
    ui = staffed_order
    solver = ui.solver
    ui.config.conf.run_order_network_adaptive = True
    ui.config.conf.run_order_grandet_mode.enable = True
    ui.config.conf.run_order_grandet_mode.buffer_time = 15
    ui.config.conf.run_order_delay = 3
    solver.recog = SimpleNamespace()
    selected = task(ui, 1)
    original = selected.time
    solver.tasks, solver.task = [selected], None
    solver._register_network_wait_observer()
    record(ui, 90)
    assert selected.time == original - timedelta(seconds=105)
    assert selected.time < ui.clock.now() < original
    if conversion == "disabled":
        ui.config.conf.run_order_network_adaptive = False
    elif conversion == "drone":
        ui.config.conf.run_order_grandet_mode.enable = False
    else:
        selected.adjusted = True
    stub_dispatch_external_work(ui, monkeypatch)
    navigation_times = []

    def sleep(seconds):
        assert not navigation_times
        assert selected.time == original
        assert not hasattr(selected, "run_order_network_timing")
        ui.clock.current += timedelta(seconds=seconds)

    def transition():
        solver.tasks.clear()
        return True

    solver._idle_sleep = MagicMock(side_effect=sleep)
    solver.check_current_focus = MagicMock(
        side_effect=lambda: navigation_times.append(ui.clock.now())
    )
    solver.transition = MagicMock(side_effect=transition)

    assert solver.run() is True

    solver._idle_sleep.assert_called_once_with(60.0)
    assert navigation_times == [original]
    assert selected.time == original
    assert not hasattr(selected, "run_order_network_timing")
