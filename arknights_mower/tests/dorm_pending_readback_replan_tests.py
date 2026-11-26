from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import dorm_recovery_evidence_tests
from arknights_mower.tests.dorm_recovery_continuation_tests import (
    MANAGERS,
    NEW,
    OTHER,
    PEER,
    VIP,
    start_after_release,
)
from arknights_mower.tests.dorm_recovery_tests import ROOM
from arknights_mower.utils import resting_priority, scheduler_task
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.dorm_recovery import keep_measured_dorm_swap
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

scheduler = dorm_recovery_evidence_tests.scheduler
dorm_dispatch = dorm_recovery_evidence_tests.dorm_dispatch
pytestmark = pytest.mark.usefixtures("income_db")


@pytest.fixture
def dispatch(dorm_dispatch, scheduler, monkeypatch):
    solver, _, _ = dorm_dispatch
    start_after_release(solver, monkeypatch, bed=4)
    scheduler.clock.current = datetime.now()
    solver.task, solver.tasks = None, []
    del solver._fill_empty_dorms, solver.plan_metadata, solver.backup_plan_solver
    del solver._prepare_shift_backup
    monkeypatch.setattr(
        scheduler.module, "try_add_release_dorm", scheduler_task.try_add_release_dorm
    )
    monkeypatch.setattr(resting_priority, "agent_list", [])
    solver._scan_card_moods = Mock(return_value=None)
    return solver


def queue_arrangement(dispatch, kind, now):
    if kind == TaskTypes.FILL_DORM:
        dispatch.physical[4] = ""
        dispatch.op_data.operators[OTHER].mood = 24
        rows = dispatch.get_agent_from_room(ROOM, read_dorm_evidence=True)
        swap = ["Current", "Current", VIP, PEER, "Current"]
        assert keep_measured_dorm_swap(dispatch.op_data, ROOM, swap, rows)
        scheduler_task.try_add_release_dorm({}, None, dispatch.op_data, dispatch.tasks)
        (task,) = dispatch.tasks
        assert task.type == kind and task.dorm_fill_plan[ROOM][4] == NEW
        return task, [*MANAGERS, PEER, VIP, NEW]

    task = SchedulerTask(
        now, {ROOM: ["Current", "Current", NEW, "Current", "Current"]}, kind
    )
    dispatch.tasks.append(task)
    return task, [*MANAGERS, NEW, VIP, OTHER]


def submit_before_readback(dispatch, scheduler, monkeypatch, kind, cached):
    original, final = queue_arrangement(dispatch, kind, scheduler.clock.now())
    before = dispatch.physical.copy()
    scheduled = original.time
    scheduler.clock.current += timedelta(seconds=2)
    boundary = dispatch.get_agent_from_room if cached else dispatch.tap_confirm
    perform = boundary.side_effect

    def interrupt(*args, **kwargs):
        result = perform(*args, **kwargs)
        if dispatch.confirms:
            raise MowerExit
        return result

    with monkeypatch.context() as outage:
        outage.setattr(boundary, "side_effect", interrupt)
        with pytest.raises(MowerExit):
            dispatch.run()
    assert dispatch.confirms == [final]
    assert dispatch.op_data.get_current_room(ROOM, True) == (
        final if cached else before
    )
    assert original.dorm_roommate_targets == {ROOM: (tuple(final), VIP)}
    assert not original.retains_execution
    assert any(task is original for task in dispatch.tasks)
    return original, final, scheduled


def run_earlier_reorder(dispatch, scheduled, monkeypatch):
    worker = dispatch.op_data.operators["米格鲁"]
    worker.current_room, worker.current_index = "meeting", 0
    earlier = SchedulerTask(
        scheduled - timedelta(seconds=1), {"meeting": [worker.name]}, TaskTypes.RE_ORDER
    )
    dispatch.task = None
    dispatch.tasks.append(earlier)
    cached = dispatch.op_data.get_current_room(ROOM, True)
    read_dorm = dispatch.get_agent_from_room.side_effect
    plan_metadata = dispatch.plan_metadata
    replanned = []

    def read_room(room=ROOM, *args, **kwargs):
        if room == "meeting":
            return [{"agent": worker.name}, {"agent": ""}]
        return read_dorm(room, *args, **kwargs)

    def replan():
        replanned.append(dispatch.task)
        assert dispatch.op_data.get_current_room(ROOM, True) == cached
        return plan_metadata()

    with monkeypatch.context() as work:
        work.setattr(dispatch.get_agent_from_room, "side_effect", read_room)
        work.setattr(dispatch, "plan_metadata", replan)
        dispatch.run()
    assert len(replanned) == 1 and replanned[0] is earlier
    assert all(task is not earlier for task in dispatch.tasks)


@pytest.mark.parametrize(
    "cached", [False, True], ids=["before-room-cache", "after-room-cache"]
)
@pytest.mark.parametrize(
    "kind",
    [TaskTypes.FILL_DORM, TaskTypes.SHIFT_OFF, TaskTypes.SHIFT_ON],
    ids=["fill", "shift-off", "shift-on"],
)
def test_other_due_task_preserves_submitted_dorm_readback(
    dispatch, scheduler, monkeypatch, kind, cached
):
    original, final, scheduled = submit_before_readback(
        dispatch, scheduler, monkeypatch, kind, cached
    )
    run_earlier_reorder(dispatch, scheduled, monkeypatch)
    assert any(task is original for task in dispatch.tasks)
    assert original.plan == {ROOM: final}
    assert original.dorm_roommate_targets == {ROOM: (tuple(final), VIP)}
    assert original.time == scheduled

    read_dorm = dispatch.get_agent_from_room.side_effect
    reads = []
    dispatch.choose_agent.reset_mock()
    dispatch.tap_confirm.reset_mock()

    def observe(room=ROOM, *args, **kwargs):
        if room == ROOM:
            reads.append(
                (
                    dispatch.task,
                    dispatch.choose_agent.call_count,
                    dispatch.tap_confirm.call_count,
                )
            )
        return read_dorm(room, *args, **kwargs)

    monkeypatch.setattr(dispatch.get_agent_from_room, "side_effect", observe)
    dispatch.run()
    assert reads and reads[0][0] is original and reads[0][1:] == (0, 0)
    assert all(task is not original for task in dispatch.tasks)
    assert dispatch.physical == final
    scheduler.io.assert_not_called()


def test_unsubmitted_fill_expires_when_its_bed_is_taken(
    dispatch, scheduler, monkeypatch
):
    original, _ = queue_arrangement(
        dispatch, TaskTypes.FILL_DORM, scheduler.clock.now()
    )
    dispatch.physical[4] = OTHER
    dispatch.get_agent_from_room(ROOM, read_dorm_evidence=True)
    run_earlier_reorder(dispatch, original.time, monkeypatch)
    assert all(task is not original for task in dispatch.tasks)
    assert dispatch.physical[4] == OTHER and not dispatch.confirms
    scheduler.io.assert_not_called()


@pytest.mark.parametrize(
    "submitted", [False, True], ids=["ordinary", "pending-readback"]
)
def test_joint_deferral_merges_only_unsubmitted_dorm_arrangements(
    dispatch, scheduler, monkeypatch, submitted
):
    if submitted:
        owner, final, scheduled = submit_before_readback(
            dispatch, scheduler, monkeypatch, TaskTypes.SHIFT_OFF, cached=True
        )
    else:
        scheduled = scheduler.clock.now()
        final = [*MANAGERS, NEW, VIP, OTHER]
        owner = SchedulerTask(scheduled, {ROOM: final.copy()}, TaskTypes.SHIFT_OFF)
    other = SchedulerTask(
        scheduled + timedelta(microseconds=1),
        {ROOM: ["Current"] * 4 + [PEER]},
        TaskTypes.RE_ORDER,
    )
    order = SchedulerTask(
        scheduler.clock.now() + timedelta(seconds=10), task_type=TaskTypes.RUN_ORDER
    )
    tasks = [owner, other, order]
    merge = Mock(wraps=scheduler_task._merge_deferred_dorm_schedules)
    monkeypatch.setattr(scheduler_task, "_merge_deferred_dorm_schedules", merge)
    scheduler_task.scheduling(
        tasks, time_now=scheduler.clock.now(), op_data=dispatch.op_data
    )
    assert tasks[0] is order and tasks[1] is owner
    if submitted:
        assert owner.time == scheduled
        merge.assert_not_called()
        assert len(tasks) == 3 and tasks[2] is other
        assert other.time > order.time
        assert other.plan == {ROOM: ["Current"] * 4 + [PEER]}
        assert owner.plan == {ROOM: final}
        assert owner.dorm_roommate_targets == {ROOM: (tuple(final), VIP)}
    else:
        assert owner.time > order.time
        merge.assert_called_once()
        assert len(tasks) == 2 and owner.plan == {ROOM: [*final[:-1], PEER]}
    scheduler.io.assert_not_called()
