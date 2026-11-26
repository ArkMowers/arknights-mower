from collections import deque
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import record
from arknights_mower.tests import dorm_recovery_evidence_tests
from arknights_mower.tests.dorm_recovery_continuation_tests import (
    NEW,
    OTHER,
    PEER,
    VIP,
    start_after_release,
)
from arknights_mower.tests.dorm_recovery_tests import ROOM
from arknights_mower.utils import (
    config,
    crash_recovery,
    operation_timing,
    resting_priority,
)
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.dorm_recovery import (
    active_recovery_position,
    keep_measured_dorm_swap,
    observed_recovery_recipient,
)
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import (
    TaskTypes,
    replan_update_tasks,
    try_add_release_dorm,
)

scheduler = dorm_recovery_evidence_tests.scheduler
dorm_dispatch = dorm_recovery_evidence_tests.dorm_dispatch

TRADE = "room_1_1"


def queue_run_order(dispatch, deadline):
    dispatch.global_plan["default_plan"].plan[TRADE] = [
        Room("古米", "", ["芬", "但书"])
    ]
    assert dispatch.op_data.swap_plan([], refresh=True) is None
    dispatch.op_data.update_detail("古米", 24, TRADE, 0)
    del dispatch._sync_run_order_tasks
    dispatch.get_run_order_time = Mock(return_value=deadline)
    assert dispatch.plan_run_order(TRADE)
    (order,) = [task for task in dispatch.tasks if task.type == TaskTypes.RUN_ORDER]
    assert order.time == deadline and order.plan == {TRADE: ["但书"]}


def restore_and_dispatch(dispatch, scheduler, monkeypatch, restart_at, check_restored):
    today = scheduler.clock.now().date()
    dispatch.daily_report = dispatch.daily_skland = today
    dispatch.daily_mail = dispatch.daily_visit_friend = today
    dispatch.task_count = 0
    assert record.save_current_state()
    saved = replan_update_tasks(record.load_state(strict=True))
    dispatch.task, dispatch.tasks, dispatch.op_data = None, [], None

    scheduler.clock.current = restart_at
    # 第二轮刷新资源时退出，首轮由调度器决定派发任务或等待。
    main = scheduler.main
    with monkeypatch.context() as startup:
        startup.setattr(main, "initialize", Mock(return_value=dispatch))
        startup.setattr(main, "_recover_startup_scene", Mock(return_value=True))
        startup.setattr(main, "datetime", scheduler.clock)
        startup.setattr(
            main, "refresh_resource_at_boundary", Mock(side_effect=[None, MowerExit])
        )
        startup.setattr(main.NewsChecker, "get_major_maintenance", lambda: None)
        startup.setattr(main.NewsChecker, "get_effective_maintenance", lambda: None)
        startup.setattr(crash_recovery, "checkpoint_start", check_restored)
        main.simulate(saved)


def interrupt_dorm_fill(
    dispatch, scheduler, monkeypatch, task_type, recipient, *, with_order
):
    start_after_release(dispatch, monkeypatch, bed=4)
    monkeypatch.setattr(scheduler.module, "try_add_release_dorm", try_add_release_dorm)
    monkeypatch.setattr(resting_priority, "agent_list", [])
    monkeypatch.setattr(config.conf, "run_order_delay", 5)
    for single_recovery in (False, True):
        monkeypatch.setitem(
            operation_timing._dorm_durations, (ROOM, single_recovery), deque(maxlen=8)
        )
    del dispatch._fill_empty_dorms, dispatch.plan_metadata, dispatch.backup_plan_solver
    dispatch._scan_card_moods = Mock(return_value=None)
    dispatch.task, dispatch.tasks = None, []
    scheduler.clock.current = datetime.now()

    if task_type == TaskTypes.FILL_DORM:
        bed_index, full_resident = 4, OTHER
        dispatch.physical[bed_index] = ""
    else:
        bed_index, full_resident = 2, PEER
    dispatch.op_data.operators[full_resident].mood = 24
    rows = dispatch.get_agent_from_room(ROOM, read_dorm_evidence=True)
    swap = ["Current", "Current", VIP, PEER, "Current"]
    assert keep_measured_dorm_swap(dispatch.op_data, ROOM, swap, rows)
    try_add_release_dorm({}, None, dispatch.op_data, dispatch.tasks)
    (original,) = dispatch.tasks
    scheduled = original.time
    order_at = scheduled + timedelta(minutes=14)
    if with_order:
        queue_run_order(dispatch, order_at)
    assert original.type == task_type
    assert original.dorm_fill_plan[ROOM][bed_index] == NEW
    final = dispatch.physical.copy()
    final[bed_index] = NEW
    submit = dispatch.tap_confirm.side_effect
    read_room = dispatch.get_agent_from_room.side_effect

    def deliver(room, plan):
        submit(room, plan)
        if dispatch.physical == final:
            dispatch.game_recipient = recipient if len(dispatch.confirms) == 1 else VIP

    def interrupt_after_room_cache(*args, **kwargs):
        rows = read_room(*args, **kwargs)
        if dispatch.confirms:
            raise MowerExit
        return rows

    dispatch.tap_confirm.side_effect = deliver
    dispatch.get_agent_from_room.side_effect = interrupt_after_room_cache
    scheduler.clock.current += timedelta(seconds=2)
    with pytest.raises(MowerExit):
        dispatch.run()
    assert dispatch.confirms == [final]
    assert original.dorm_roommate_targets == {ROOM: (tuple(final), VIP)}
    assert not original.retains_execution and not getattr(
        original, "dorm_recovery_restore", ()
    )
    assert dispatch.op_data.get_current_room(ROOM, True) == final
    assert original.time == scheduled
    dispatch.get_agent_from_room.side_effect = read_room
    dispatch.choose_agent.reset_mock()
    dispatch.tap_confirm.reset_mock()
    return original, final, order_at


@pytest.mark.usefixtures("income_db")
@pytest.mark.parametrize("order_window", [False, True], ids=["no-order", "order-in-7m"])
@pytest.mark.parametrize("correct", [True, False], ids=["already-correct", "repair"])
@pytest.mark.parametrize(
    "task_type,other_recipient",
    [
        (TaskTypes.FILL_DORM, PEER),
        (TaskTypes.NOT_SPECIFIC, OTHER),
    ],
    ids=["vacancy", "takeover"],
)
def test_update_reads_committed_dorm_fill_before_replanning(
    scheduler,
    dorm_dispatch,
    monkeypatch,
    task_type,
    other_recipient,
    correct,
    order_window,
):
    dispatch, _, _ = dorm_dispatch
    recipient = VIP if correct else other_recipient
    original, final, order_at = interrupt_dorm_fill(
        dispatch, scheduler, monkeypatch, task_type, recipient, with_order=order_window
    )
    scheduled = original.time
    read_room = dispatch.get_agent_from_room.side_effect
    restored = restored_order = None

    def check_restored(solver):
        nonlocal restored, restored_order
        (restored,) = [
            t for t in solver.tasks if t.type == task_type and ROOM in t.plan
        ]
        assert restored.time == scheduled and restored.plan == {ROOM: final}
        assert restored.dorm_roommate_targets == original.dorm_roommate_targets
        assert solver.op_data.get_current_room(ROOM, True) == final
        if order_window:
            (restored_order,) = [
                t for t in solver.tasks if t.type == TaskTypes.RUN_ORDER
            ]
            assert restored_order.time == order_at
            assert restored_order.time - scheduler.clock.now() == timedelta(minutes=7)

    reads = []

    def observe(*args, **kwargs):
        rows = read_room(*args, **kwargs)
        reads.append(
            (
                dispatch.task,
                observed_recovery_recipient(rows, {}),
                dispatch.choose_agent.call_count,
                dispatch.tap_confirm.call_count,
            )
        )
        return rows

    dispatch.get_agent_from_room.side_effect = observe
    restart_at = (
        order_at - timedelta(minutes=7) if order_window else scheduler.clock.now()
    )
    restore_and_dispatch(dispatch, scheduler, monkeypatch, restart_at, check_restored)
    assert reads and all(owner is restored for owner, *_ in reads)
    assert reads[0][1:] == (recipient, 0, 0)
    assert reads[-1][1] == VIP
    assert (
        dispatch.choose_agent.call_count
        == dispatch.tap_confirm.call_count
        == (0 if correct else 2)
    )
    if correct:
        assert len(reads) == 1
    else:
        assert dispatch.confirms[1] != final
    assert dispatch.physical == final
    vip = dispatch.op_data.operators[VIP]
    assert active_recovery_position(dispatch.op_data, vip) == (ROOM, 3)
    assert restored.time == scheduled and not restored.plan
    assert not getattr(restored, "dorm_roommate_targets", {})
    assert all(t is not restored for t in dispatch.tasks)
    if order_window:
        (queued_order,) = [t for t in dispatch.tasks if t.type == TaskTypes.RUN_ORDER]
        assert queued_order is restored_order
        assert queued_order.time == order_at and queued_order.plan == {TRADE: ["但书"]}

        scheduler.clock.current = order_at
        dispatch.enter_room.reset_mock()
        dispatch.enter_room.side_effect = MowerExit
        with pytest.raises(MowerExit):
            dispatch.run()
        dispatch.enter_room.assert_called_once_with(TRADE)
        assert (
            dispatch.task is restored_order
            and dispatch.task.time == scheduler.clock.now()
        )
    scheduler.io.assert_not_called()


@pytest.mark.usefixtures("income_db")
def test_imminent_order_runs_before_committed_dorm_readback(
    scheduler, dorm_dispatch, monkeypatch
):
    dispatch, _, _ = dorm_dispatch
    monkeypatch.setattr(config.conf.run_order_grandet_mode, "enable", False)
    original, final, order_at = interrupt_dorm_fill(
        dispatch, scheduler, monkeypatch, TaskTypes.FILL_DORM, VIP, with_order=True
    )
    scheduled = original.time
    restart_at = order_at - timedelta(seconds=30)
    restored = order = None

    def check_restored(solver):
        nonlocal restored, order
        restored = solver.find_next_task(task_type=TaskTypes.FILL_DORM)
        order = solver.find_next_task(task_type=TaskTypes.RUN_ORDER)
        assert restored.time == scheduled and restored.plan == {ROOM: final}
        assert order.time == order_at and order.plan == {TRADE: ["但书"]}

    def elapse(seconds, *, round_end):
        scheduler.clock.current += timedelta(seconds=seconds)

    dispatch.get_agent_from_room.reset_mock()
    dispatch.enter_room.reset_mock()
    dispatch._idle_sleep = Mock(side_effect=elapse)
    monkeypatch.setattr(scheduler.module, "send_message", Mock())
    restore_and_dispatch(dispatch, scheduler, monkeypatch, restart_at, check_restored)
    dispatch._idle_sleep.assert_called_once_with(30, round_end=True)
    assert dispatch.find_next_task() is order
    dispatch.enter_room.assert_not_called()
    dispatch.get_agent_from_room.assert_not_called()
    assert restored.time == scheduled
    assert restored.plan == {ROOM: final}
    assert restored.dorm_roommate_targets == {ROOM: (tuple(final), VIP)}

    entries = []
    dispatch.enter_room.side_effect = lambda room: entries.append(
        (room, dispatch.task, scheduler.clock.now())
    )
    read_room = dispatch.get_agent_from_room.side_effect
    dorm_reads = []

    def observe(room, *args, **kwargs):
        if room == TRADE:
            # 贸易站实读已是但书，调度器处理订单后自行释放跑单任务。
            return [{"agent": "但书"}]
        assert room == ROOM
        rows = read_room(room, *args, **kwargs)
        dorm_reads.append((dispatch.task, observed_recovery_recipient(rows, {})))
        return rows

    dispatch.get_agent_from_room.side_effect = observe
    dispatch.drone = Mock()
    dispatch.run()
    ((room, owner, entered_at),) = entries
    assert room == TRADE and owner is order and entered_at == order.time == order_at
    dispatch.drone.assert_called_once_with(TRADE, not_customize=True)
    assert not dorm_reads and all(t is not order for t in dispatch.tasks)
    assert any(t is restored for t in dispatch.tasks)
    assert restored.time == scheduled and restored.plan == {ROOM: final}

    dispatch.run()
    ((owner, recipient),) = dorm_reads
    assert owner is restored and recipient == VIP
    vip = dispatch.op_data.operators[VIP]
    assert active_recovery_position(dispatch.op_data, vip) == (ROOM, 3)
    assert restored.time == scheduled and not restored.plan
    assert not getattr(restored, "dorm_roommate_targets", {})
    assert all(t is not restored for t in dispatch.tasks)
    scheduler.io.assert_not_called()
