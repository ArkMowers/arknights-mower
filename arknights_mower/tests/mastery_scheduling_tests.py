"""Order completion budgets advance conflicting mastery handoffs."""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.tests.mastery_scheduling_fixtures import (  # noqa: E402
    clock as clock,  # noqa: E402
)
from arknights_mower.tests.mastery_scheduling_fixtures import pair  # noqa: E402
from arknights_mower.utils import scheduler_task as scheduler  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


@pytest.mark.parametrize(
    "offset,collision",
    [
        (-7, False),
        (-6.5, False),
        (-6, True),
        (-1, True),
        (0, True),
        (2, True),
        (3, False),
        (9, False),
    ],
)
def test_swap_collision_includes_orders_on_both_sides(clock, offset, collision):
    order, swap = pair()
    order.time = swap.time + timedelta(minutes=offset)
    at, before = swap.time, order.time
    tasks = [order, swap]
    assert scheduler.scheduling(tasks) is None
    assert (swap.time != at) == collision
    assert order.time == before
    if collision:
        assert swap.time == order.time - timedelta(minutes=3, seconds=1)
        assert swap.advance_support_swap is True


def test_remote_backlog_cannot_delay_swap(clock):
    order, swap = pair()
    shifts = [
        SchedulerTask(
            swap.time - timedelta(minutes=2),
            {"room_1_1": ["主力"], "dormitory_1": ["替班"]},
            TaskTypes.SHIFT_OFF,
        )
        for _ in range(20)
    ]
    tasks = [order, *shifts, swap]
    order_time = order.time
    clock.now.return_value = swap.time - timedelta(seconds=73)
    assert scheduler.scheduling(tasks) is None
    assert tasks[0] is swap
    assert all(t.time > swap.time for t in shifts)
    assert order.time == order_time
    # An advanced due handoff stays ahead of its overdue order after restart.
    clock.now.return_value = swap.time + timedelta(minutes=15)
    scheduler.scheduling(tasks)
    assert tasks[0] is swap


def test_small_ordinary_task_can_finish_before_swap(clock):
    _, swap = pair()
    clock.now.return_value = swap.time - timedelta(minutes=6)
    ordinary = SchedulerTask(clock.now.return_value, task_type=TaskTypes.RELEASE_DORM)
    tasks = [swap, ordinary]
    scheduler.scheduling(tasks)
    assert tasks[0] is ordinary
    assert ordinary.time == clock.now.return_value


def test_cumulative_work_and_adjusted_tasks_yield(clock):
    _, swap = pair()
    clock.now.return_value = swap.time - timedelta(minutes=4)
    tasks = [
        SchedulerTask(
            clock.now.return_value, task_type=TaskTypes.FIAMMETTA, adjusted=True
        )
        for _ in range(2)
    ]
    tasks.append(swap)
    scheduler.scheduling(tasks)
    assert tasks[0] is swap


def test_disabled_mastery_does_not_protect_stale_swap(clock):
    order, swap = pair()
    clock.now.return_value = swap.time - timedelta(minutes=1)
    before = order.time
    with patch.object(scheduler.config.conf, "enable_mastery", False):
        assert scheduler.scheduling([order, swap]) is None
    assert order.time == before


def test_multiple_swaps_advance_without_changing_order_time(clock):
    order, first = pair()
    second = SchedulerTask(
        first.time + timedelta(minutes=2), task_type=TaskTypes.SWAP_SUPPORT
    )
    order_time = order.time
    assert scheduler.scheduling([second, order, first]) is None
    assert first.time < order_time and second.time < order_time
    assert order.time == order_time
    times = first.time, second.time
    assert scheduler.scheduling([first, second, order]) is None
    assert (first.time, second.time) == times


def test_protection_covers_custom_order_entry_delay(clock):
    order, swap = pair()
    at = swap.time
    order.time = at - timedelta(minutes=15)
    before = order.time
    clock.now.return_value = at - timedelta(hours=1)
    with patch.object(scheduler.config.conf, "run_order_delay", 15):
        assert scheduler.scheduling([order, swap]) is None
    assert swap.time == before - timedelta(minutes=3, seconds=1)
    assert order.time == before


def test_long_shift_yields_even_outside_fixed_window(clock):
    _, swap = pair()
    clock.now.return_value = swap.time - timedelta(minutes=11)
    shift = SchedulerTask(
        clock.now.return_value,
        {f"room_{i}": ["主力"] for i in range(8)},
        TaskTypes.SHIFT_OFF,
    )
    tasks = [shift, swap]
    scheduler.scheduling(tasks)
    assert tasks[0] is swap
    assert shift.time > swap.time


def test_accumulated_long_work_cannot_cross_distant_swap(clock):
    _, swap = pair()
    clock.now.return_value = swap.time - timedelta(minutes=14)
    shifts = [
        SchedulerTask(
            clock.now.return_value,
            {f"room_{i}": ["主力"] for i in range(5)},
            TaskTypes.SHIFT_OFF,
        )
        for _ in range(2)
    ]
    tasks = [*shifts, swap]
    scheduler.scheduling(tasks)
    assert tasks[0] is shifts[0]
    assert shifts[1].time > swap.time


@pytest.mark.parametrize("elapsed_seconds", [0, 259])
def test_reported_ten_minute_window_keeps_order(clock, elapsed_seconds):
    now = datetime(2026, 10, 2, 20, 2, 10)
    order, swap = pair()
    swap.time = datetime(2026, 10, 2, 20, 12, 4)
    order.time = now - timedelta(seconds=elapsed_seconds)
    before = order.time
    tasks = [swap, order]
    clock.now.return_value = now
    with patch.object(scheduler.config.conf, "run_order_delay", 5):
        assert scheduler.scheduling(tasks) is None
    assert order.time == before
    assert tasks[0] is order


def test_elapsed_countdown_only_reserves_remaining_order_time(clock):
    order, swap = pair()
    now = swap.time - timedelta(minutes=3)
    clock.now.return_value = now
    order.time = now - timedelta(minutes=4, seconds=19)
    before = order.time
    with patch.object(scheduler.config.conf, "run_order_delay", 5):
        assert scheduler.scheduling([order, swap]) is None
    assert order.time == before


@pytest.mark.parametrize(
    "remaining_seconds,deferred", [(29, False), (30, False), (31, True)]
)
def test_order_completion_allowance_boundary(clock, remaining_seconds, deferred):
    order, swap = pair()
    now = swap.time - timedelta(minutes=2)
    clock.now.return_value = now
    order.time = now + timedelta(seconds=remaining_seconds) - timedelta(minutes=5)
    before = order.time
    tasks = [order, swap]
    with patch.object(scheduler.config.conf, "run_order_delay", 5):
        assert scheduler.scheduling(tasks) is None
    assert order.time == before
    assert bool(getattr(swap, "advance_support_swap", False)) == deferred
    assert tasks[0] is (swap if deferred else order)


def test_late_conflict_advances_handoff_and_preserves_due_order(clock):
    order, swap = pair()
    clock.now.return_value = swap.time - timedelta(seconds=30)
    before = order.time
    tasks = [order, swap]
    with patch.object(scheduler.config.conf, "run_order_delay", 15):
        scheduler.scheduling(tasks)
        assert swap.time == clock.now.return_value
        assert tasks[0] is swap
        assert order.time == before
        scheduler.scheduling(tasks)
        assert swap.time == clock.now.return_value
        assert tasks[0] is swap
        assert order.time == before
    tasks.remove(swap)
    scheduler.scheduling(tasks)
    assert tasks[0] is order and order.time == before


@pytest.mark.parametrize("late_seconds", [0, 30, 900])
def test_due_handoff_keeps_order_time_and_dispatches_first(clock, late_seconds):
    order, swap = pair()
    at, before = swap.time, order.time
    clock.now.return_value = at + timedelta(seconds=late_seconds)
    tasks = [order, swap]
    scheduler.scheduling(tasks)
    assert order.time == before and swap.time == at
    assert tasks[0] is swap
    scheduler.scheduling(tasks)
    assert order.time == before and swap.time == at
    tasks.remove(swap)
    scheduler.scheduling(tasks)
    assert tasks[0] is order and order.time == before


def test_long_handoff_reserves_its_room_operation_budget(clock):
    order, swap = pair()
    before = order.time
    swap.plan = {f"room_{i}": ["Current"] for i in range(6)}
    scheduler.scheduling([order, swap], execution_time=1)
    assert swap.time == before - timedelta(minutes=6, seconds=1)
    assert order.time == before


def test_multiple_due_handoffs_stay_before_overdue_order(clock):
    order, first = pair()
    second = SchedulerTask(
        first.time + timedelta(minutes=2), task_type=TaskTypes.SWAP_SUPPORT
    )
    before = order.time
    clock.now.return_value = first.time - timedelta(seconds=30)
    tasks = [order, first, second]
    scheduler.scheduling(tasks)
    assert tasks[:2] == [first, second]
    assert order.time == before
    times = first.time, second.time
    scheduler.scheduling(tasks)
    assert (first.time, second.time) == times
    tasks.remove(first)
    scheduler.scheduling(tasks)
    assert tasks[0] is second and order.time == before


def test_advance_stays_before_earliest_conflicting_order(clock):
    order, swap = pair()
    earlier = SchedulerTask(
        order.time - timedelta(minutes=1),
        task_type=TaskTypes.RUN_ORDER,
        meta_data="room_1_2",
    )
    times = order.time, earlier.time
    scheduler.scheduling([swap, order, earlier])
    assert swap.time == earlier.time - timedelta(minutes=3, seconds=1)
    assert (order.time, earlier.time) == times


def test_disabled_mastery_does_not_prioritize_advanced_swap(clock):
    order, swap = pair()
    clock.now.return_value = swap.time - timedelta(seconds=30)
    tasks = [order, swap]
    scheduler.scheduling(tasks)
    before = order.time, swap.time
    with patch.object(scheduler.config.conf, "enable_mastery", False):
        scheduler.scheduling(tasks)
    assert (order.time, swap.time) == before
    assert tasks[0] is order
