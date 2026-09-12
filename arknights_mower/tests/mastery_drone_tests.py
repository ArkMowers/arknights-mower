"""Fixed mastery handoffs share run-order collision handling without being accelerated."""

import sys
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.tests.mastery_scheduling_fixtures import (  # noqa: E402
    clock as clock,  # noqa: E402
)
from arknights_mower.tests.mastery_scheduling_fixtures import (  # noqa: E402
    make_solver,
    pair,
)
from arknights_mower.utils import scheduler_task as scheduler  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


def test_cleanup_is_not_drone_target_or_deferred(clock):
    order, swap = pair()
    order.meta_data = ""  # A second pass restoring trade-room staff.
    before = order.time
    clock.now.return_value = swap.time - timedelta(minutes=1)
    assert scheduler.scheduling([order, swap]) is None
    assert order.time == before


def test_drone_adjustment_reads_actual_new_order_time(clock):
    order, swap = pair()
    at = swap.time
    solver = make_solver([order, swap])
    solver.digit_reader.get_drone.return_value = 30
    actual_start = swap.time - timedelta(minutes=11)
    solver.double_read_time.return_value = actual_start + timedelta(
        minutes=scheduler.config.conf.run_order_delay
    )
    assert solver.get_run_order_adjust_room((order, swap)) == "room_1_1"
    assert solver.get_run_order_adjust_room((swap, order)) == "room_1_1"
    assert solver.get_run_order_adjust_room((swap, swap)) is None
    assert solver.adjust_order_time((10, 20), "room_1_1") is None
    assert solver.tap.call_count == 3
    assert order.time == actual_start
    assert swap.time == at
    assert scheduler.scheduling(solver.tasks) is None


def test_drone_shortage_then_deadline_gives_swap_priority(clock):
    order, swap = pair()
    solver = make_solver([order, swap])
    before = order.time
    solver.digit_reader.get_drone.return_value = 20
    assert solver.adjust_order_time((10, 20), "room_1_1") is False
    solver.tap.assert_not_called()
    assert order.time == before
    clock.now.return_value = swap.time - timedelta(minutes=9)
    assert scheduler.scheduling(solver.tasks) is None
    assert solver.tasks[0] is swap


def test_adjustment_without_conflict_is_safe(clock):
    solver = make_solver([])
    assert solver.adjust_order_time((10, 20), "room_1_1") is None
    solver.tap.assert_not_called()


def test_navigation_delay_rechecks_before_arranging(clock):
    order, swap = pair()
    solver = make_solver([order, swap])
    solver.task = order
    solver.find = MagicMock(return_value=True)
    solver.agent_arrange = MagicMock()
    solver.skip = MagicMock()
    clock.now.return_value = swap.time - timedelta(seconds=30)
    with patch.object(base_schedule, "datetime") as now:
        now.now.return_value = clock.now.return_value
        assert solver.infra_main() is True
    solver.agent_arrange.assert_not_called()
    assert solver.task is None
    assert solver.tasks[0] is swap
    assert any(t is order for t in solver.tasks)


def test_dispatch_removes_its_own_task_after_queue_reordering(clock):
    order, swap = pair()
    clock.now.return_value = swap.time
    solver = make_solver([swap, order])
    solver.task = swap
    solver.find = MagicMock(return_value=True)
    new_task = SchedulerTask(swap.time, task_type=TaskTypes.NOT_SPECIFIC)

    def execute(_):
        solver.tasks.insert(0, new_task)

    with (
        patch.object(base_schedule, "datetime", scheduler.datetime),
        patch("arknights_mower.solvers.mastery.run_swap_support", side_effect=execute),
    ):
        solver.infra_main()
    assert any(t is new_task for t in solver.tasks)
    assert any(t is order for t in solver.tasks)
    assert all(t is not swap for t in solver.tasks)


def test_drone_exception_preserves_both_tasks(clock):
    order, swap = pair()
    solver = make_solver([order, swap])
    solver.digit_reader.get_drone.return_value = 30
    solver.tap.side_effect = RuntimeError("加速面板异常")
    before = order.time, swap.time
    with pytest.raises(RuntimeError, match="加速面板异常"):
        solver.adjust_order_time((10, 20), "room_1_1")
    assert (order.time, swap.time) == before
    assert any(t is order for t in solver.tasks)
    assert any(t is swap for t in solver.tasks)


def test_acceleration_stops_when_swap_window_arrives(clock):
    order, swap = pair()
    solver = make_solver([order, swap])
    solver.digit_reader.get_drone.return_value = 30

    def read_remaining(*args, **kwargs):
        clock.now.return_value = swap.time - timedelta(minutes=9)
        return swap.time + timedelta(minutes=scheduler.config.conf.run_order_delay)

    solver.double_read_time.side_effect = read_remaining
    assert solver.adjust_order_time((10, 20), "room_1_1") is None
    assert solver.tap.call_count == 3
    assert solver.tasks[0] is swap
