"""Fixed mastery handoffs share run-order collision handling without being accelerated."""

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.solvers import mastery_support_state as state  # noqa: E402
from arknights_mower.solvers import mastery_support_swap as swap_runtime  # noqa: E402
from arknights_mower.tests.mastery_support_fixtures import stat  # noqa: E402
from arknights_mower.utils import scheduler_task as scheduler  # noqa: E402
from arknights_mower.utils.mastery_optimizer import stage_route  # noqa: E402
from arknights_mower.utils.mastery_support_types import StageSpec  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


@pytest.fixture
def clock():
    now = datetime(2026, 9, 8, 18, 20)
    with (
        patch.object(scheduler.config.conf, "enable_mastery", True),
        patch.object(scheduler.config.conf.run_order_grandet_mode, "enable", False),
        patch.object(
            scheduler.NewsChecker, "get_update_time", return_value=(None, None)
        ),
        patch.object(scheduler, "datetime") as mock_clock,
    ):
        mock_clock.now.return_value = now
        yield mock_clock


def pair():
    at = datetime(2026, 9, 8, 18, 50)
    return (
        SchedulerTask(
            at - timedelta(minutes=1),
            {"room_1_1": ["但书"]},
            TaskTypes.RUN_ORDER,
            "room_1_1",
        ),
        SchedulerTask(
            at, task_type=TaskTypes.SWAP_SUPPORT, meta_data="学员 换入逻各斯"
        ),
    )


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


def test_cleanup_is_not_drone_target_or_deferred(clock):
    order, swap = pair()
    order.meta_data = ""  # A second pass restoring trade-room staff.
    before = order.time
    clock.now.return_value = swap.time - timedelta(minutes=1)
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


def make_solver(tasks):
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.tasks = tasks
    solver.recog = SimpleNamespace(gray=None, w=1920, h=1080)
    solver.digit_reader = MagicMock()
    solver.tap = MagicMock()
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver._wait_drone_interface = MagicMock()
    solver.double_read_time = MagicMock()
    return solver


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


@pytest.mark.parametrize("central", [0, 5])
def test_conservative_swap_timing_matches_legacy_and_optimizer(central):
    now = datetime(2026, 9, 8, 17, 42)
    route = stage_route(
        stat("缄默德克萨斯", 80), stat("逻各斯", 0, True), StageSpec(2, 8, central, 10)
    )
    route["working_operator"] = route["operator"]
    plan = {
        "id": 1,
        "target_level": 3,
        "support_plan": {"stages": [route]},
        "support_runtime": route,
    }
    end = now + timedelta(hours=8 / (1.85 + central / 100))
    expected = end - timedelta(minutes=310 * (1.05 + central / 100) / 1.85)
    with (
        patch.object(state, "datetime") as mock_now,
        patch.object(state, "enqueue_support_swap"),
    ):
        mock_now.now.return_value = now
        at = state.schedule_support_swap(MagicMock(), plan, end, 2)
    assert at == expected
    assert abs((at - now).total_seconds() - route["switch_after"] * 3600) < 1
    # Duration uses actual nominal rates, even though the handoff is conservative.
    expected_hours = route["switch_after"] + (
        8 - route["switch_after"] * (1.85 + central / 100)
    ) / (1.05 + central / 100)
    assert route["hours"] == pytest.approx(expected_hours)
    speed = swap_runtime._current_rate({"教官": {2: stat("教官", 80)}}, "教官", 2)
    assert speed == pytest.approx(1.85)
    remaining = (end - at).total_seconds()
    selected, delay = swap_runtime.select_swap_support(
        remaining * speed, speed, [stat("逻各斯", 0, True)], (central, 10)
    )
    assert selected["name"] == "逻各斯"
    assert delay == pytest.approx(0, abs=1e-5)


def test_dispatch_removes_its_own_task_after_queue_reordering(clock):
    order, swap = pair()
    clock.now.return_value = swap.time
    solver = make_solver([swap, order])
    solver.task = swap
    solver.find = MagicMock(return_value=True)
    new_task = SchedulerTask(swap.time, task_type=TaskTypes.NOT_SPECIFIC)

    def execute(_):
        solver.tasks.insert(0, new_task)

    with patch("arknights_mower.solvers.mastery.run_swap_support", side_effect=execute):
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
