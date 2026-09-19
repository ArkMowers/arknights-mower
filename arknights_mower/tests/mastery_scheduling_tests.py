"""Fixed mastery handoffs share run-order collision handling without being accelerated."""

import sys
from datetime import timedelta
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
    [(-11, False), (-10, False), (-1, True), (0, True), (9, True), (11, False)],
)
def test_swap_collision_includes_orders_on_both_sides(clock, offset, collision):
    order, swap = pair()
    order.time = swap.time + timedelta(minutes=offset)
    at = swap.time
    tasks = [order, swap]
    result = scheduler.scheduling(tasks)
    assert (result is not None) == collision
    assert swap.time == at
    if result:
        assert result[0] is order and result[1] is swap


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
    clock.now.return_value = swap.time - timedelta(seconds=73)
    assert scheduler.scheduling(tasks) is None
    assert tasks[0] is swap
    assert all(t.time > swap.time for t in shifts)
    assert order.time > swap.time
    # Restart/overdue dispatch must still put the immutable deadline first.
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


def test_multiple_swaps_keep_their_times(clock):
    order, first = pair()
    second = SchedulerTask(
        first.time + timedelta(minutes=2), task_type=TaskTypes.SWAP_SUPPORT
    )
    times = first.time, second.time
    assert scheduler.scheduling([second, order, first]) == (order, first)
    assert (first.time, second.time) == times
    assert scheduler.scheduling([first, second]) is None


def test_protection_covers_custom_order_entry_delay(clock):
    order, swap = pair()
    order.time = swap.time - timedelta(minutes=15)
    clock.now.return_value = swap.time - timedelta(hours=1)
    with patch.object(scheduler.config.conf, "run_order_delay", 15):
        assert scheduler.scheduling([order, swap]) == (order, swap)
        clock.now.return_value = swap.time - timedelta(minutes=20)
        tasks = [order, swap]
        assert scheduler.scheduling(tasks) is None
        assert tasks[0] is swap


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
