"""Early handoffs avoid drone use and retain dispatch and drone cleanup."""

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


def test_handoff_conflict_advances_without_drone_use(clock):
    order, swap = pair()
    before = order.time
    solver = make_solver([order, swap])
    solver.digit_reader.get_drone.return_value = 20
    assert solver.adjust_order_time((10, 20), "room_1_1") is None
    solver.tap.assert_not_called()
    solver.digit_reader.get_drone.assert_not_called()
    assert swap.time < before
    assert order.time == before


def test_adjustment_without_conflict_is_safe(clock):
    solver = make_solver([])
    assert solver.adjust_order_time((10, 20), "room_1_1") is None
    solver.tap.assert_not_called()


@pytest.mark.parametrize("product_switching_enabled", [False, True])
def test_navigation_delay_rechecks_before_arranging(
    clock, monkeypatch, product_switching_enabled
):
    monkeypatch.setattr(
        scheduler.config.conf.product_switching, "enable", product_switching_enabled
    )
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
    solver._refresh_deferred_product_reservations = MagicMock()
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


@pytest.mark.parametrize("depleted", [False, True])
def test_order_collision_summarizes_confirmed_acceleration(clock, caplog, depleted):
    order, swap = pair()
    # Two order runs retain their existing Drone Acceleration collision handling.
    other = SchedulerTask(
        order.time + timedelta(minutes=1),
        task_type=TaskTypes.RUN_ORDER,
        meta_data="room_1_2",
    )
    swap.time += timedelta(hours=1)
    at = swap.time
    solver = make_solver([order, other, swap])
    solver.op_data.facility_states = {"room_1_1": {"facility": "trade"}}
    solver.digit_reader.get_drone.side_effect = [31, 20 if depleted else 30]
    interim = order.time - timedelta(minutes=1)
    actual = order.time - timedelta(minutes=6)
    solver.double_read_time.side_effect = [
        interim + timedelta(minutes=5),
        actual + timedelta(minutes=5),
    ]
    with patch.object(scheduler.config.conf.run_order_grandet_mode, "enable", True):
        outcome = solver.adjust_order_time((10, 20), "room_1_1")

    confirmed = 1 if depleted else 2
    latest = interim if depleted else actual
    assert outcome is (False if depleted else None)
    assert solver.tap.call_count == 3 * confirmed
    assert order.time == latest and swap.time == at
    visible = [
        record.getMessage() for record in caplog.records if record.levelname == "INFO"
    ]
    assert visible == [
        "贸易站 B101：跑单时间过于接近，开始使用无人机加速",
        f"贸易站 B101：无人机加速后已重读订单 {confirmed} 次，最新跑单开始时间为 {latest:%H:%M:%S}",
    ]
    if depleted:
        assert "贸易站 B101：当前有 20 架无人机，需保留 20 架，停止加速" in caplog.text


def test_drone_exception_preserves_order_collision_tasks(clock):
    order, swap = pair()
    other = SchedulerTask(
        order.time + timedelta(minutes=1),
        task_type=TaskTypes.RUN_ORDER,
        meta_data="room_1_2",
    )
    swap.time += timedelta(hours=1)
    solver = make_solver([order, other, swap])
    solver.digit_reader.get_drone.return_value = 30
    solver.tap.side_effect = RuntimeError("加速面板异常")
    before = order.time, other.time, swap.time
    with patch.object(scheduler.config.conf.run_order_grandet_mode, "enable", True):
        with pytest.raises(RuntimeError, match="加速面板异常"):
            solver.adjust_order_time((10, 20), "room_1_1")
    assert (order.time, other.time, swap.time) == before
    assert len(solver.tasks) == 3


def test_acceleration_stops_after_runtime_handoff_advancement(clock):
    order, swap = pair()
    other = SchedulerTask(
        order.time + timedelta(minutes=1),
        task_type=TaskTypes.RUN_ORDER,
        meta_data="room_1_2",
    )
    swap.time += timedelta(hours=1)
    solver = make_solver([order, other, swap])
    solver.digit_reader.get_drone.return_value = 30

    def read_remaining(*args, **kwargs):
        swap.time = other.time + timedelta(minutes=2)
        clock.now.return_value = other.time - timedelta(seconds=30)
        return other.time + timedelta(minutes=5)

    solver.double_read_time.side_effect = read_remaining
    with patch.object(scheduler.config.conf.run_order_grandet_mode, "enable", True):
        assert solver.adjust_order_time((10, 20), "room_1_1") is None
    assert solver.tap.call_count == 3
    assert solver.tasks[0] is swap
    assert swap.advance_support_swap is True


def test_dispatch_rechecks_all_orders_after_handoff_advancement(clock):
    first, swap = pair()
    now = first.time
    second = SchedulerTask(
        now + timedelta(minutes=6),
        task_type=TaskTypes.RUN_ORDER,
        meta_data="room_1_2",
    )
    swap.time = now + timedelta(minutes=7)
    solver = make_solver([first, second, swap])
    solver.task = first
    solver.find = MagicMock(return_value=True)
    solver.agent_arrange = MagicMock(return_value=False)
    solver._refresh_deferred_product_reservations = MagicMock()
    solver.skip = MagicMock()
    clock.now.return_value = now
    with patch.object(base_schedule, "datetime", scheduler.datetime):
        assert solver.infra_main() is True
    solver.agent_arrange.assert_not_called()
    assert solver.task is None
    assert solver.tasks[0] is swap
    assert swap.time == now
    assert first.time == now
    assert second.time == now + timedelta(minutes=6)
