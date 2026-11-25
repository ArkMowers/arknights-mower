import pickle
from datetime import timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import (
    dorm_recovery_evidence_tests,
    dorm_recovery_tests,
    room_scroll_recovery_tests,
    scheduler_recovery_preservation_tests,
)
from arknights_mower.tests.dorm_recovery_continuation_tests import (
    MANAGERS,
    NEW,
    OTHER,
    PEER,
    VIP,
    change_roommate,
    start_after_release,
)
from arknights_mower.tests.dorm_recovery_tests import ROOM, room_readings
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.dorm_candidates import retained_task_reservations
from arknights_mower.utils.dorm_recovery import (
    active_recovery_position,
    observed_recovery_recipient,
    remember_roommate_target,
)
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    replan_update_tasks,
)

solver = dorm_recovery_tests.solver
five_slot_room = room_scroll_recovery_tests.five_slot_room
scheduler = scheduler_recovery_preservation_tests.scheduler
dorm_dispatch = dorm_recovery_evidence_tests.dorm_dispatch


@pytest.mark.parametrize(
    "recipient, position, keep_seating",
    [
        pytest.param(VIP, (ROOM, 3), False, id="same-recipient"),
        pytest.param(OTHER, None, False, id="other-recipient"),
        pytest.param(None, None, True, id="unknown-recipient"),
    ],
)
def test_ordinary_room_read_after_ambiguous_shift(
    solver, five_slot_room, monkeypatch, recipient, position, keep_seating
):
    monkeypatch.setattr("arknights_mower.solvers.record.save_agent_action", Mock())
    start_after_release(solver, monkeypatch, bed=4)
    change_roommate(solver, PEER, NEW, None)
    names = [*MANAGERS, NEW, VIP, OTHER]
    assert solver.confirms == [names]
    data = solver.op_data
    target = data.operators[VIP]
    seating = target.dorm_roommate_roster
    assert [name for name, _, _ in seating] == names
    assert not target.dorm_recovery_roster
    assert active_recovery_position(data, target) is None

    reader, _, _, screen_names, _ = five_slot_room(False)
    screen_names[:] = names
    reader.op_data = data
    reader.task = SchedulerTask(task_type=TaskTypes.SHIFT_ON)
    reader.tasks = [reader.task]
    reader.detect_room.return_value = ROOM
    reader.enter_room, reader.choose_agent, reader.tap_confirm = Mock(), Mock(), Mock()
    reader.get_agent_from_room = Mock(wraps=reader.get_agent_from_room)
    samples = {r["agent"]: r for r in room_readings(data.operators, names, recipient)}
    read_name = reader.read_screen.side_effect
    resident = None

    def read(image, *, type, cord=None):
        nonlocal resident
        if type == "name":
            resident = read_name(image, type=type)
            return resident
        assert type == "time"
        return str(timedelta(seconds=samples[resident]["recovery_seconds"]))

    reader.read_screen.side_effect = read
    reader.read_accurate_mood = lambda image: samples[resident]["measured_mood"]

    rows = reader.get_agent_from_room(ROOM)

    assert [row["agent"] for row in rows] == names
    assert observed_recovery_recipient(rows, {}) == recipient
    reader.get_agent_from_room.assert_called_once_with(ROOM)
    reader.enter_room.assert_not_called()
    reader.choose_agent.assert_not_called()
    reader.tap_confirm.assert_not_called()
    assert active_recovery_position(data, target) == position
    assert target.dorm_recovery_roster == (seating if position else ())
    assert target.dorm_roommate_roster == (seating if keep_seating else ())


@pytest.mark.parametrize(
    "checkpoint, recipient, extra_confirms",
    [
        pytest.param("planned", VIP, 1, id="planned-before-entry"),
        pytest.param("submitted", VIP, 0, id="already-delivered"),
        pytest.param("submitted", None, 0, id="unknown-recipient"),
        pytest.param("read", OTHER, 2, id="room-already-cached"),
        pytest.param("stale", None, 0, id="overdue-room-read"),
        pytest.param("initial", None, 0, id="before-initial-mood-read"),
        pytest.param("initial", OTHER, 2, id="wrong-before-initial-mood-read"),
    ],
)
def test_update_resumes_roommate_shift_from_actual_room(
    dorm_dispatch, scheduler, monkeypatch, checkpoint, recipient, extra_confirms
):
    dispatch, _, scan = dorm_dispatch
    start_after_release(dispatch, monkeypatch, bed=4)
    before = dispatch.physical.copy()
    final = [*MANAGERS, NEW, VIP, OTHER]
    scheduled = scheduler.clock.now() - timedelta(seconds=1)
    task = SchedulerTask(
        time=scheduled,
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={ROOM: ["Current", "Current", NEW, "Current", "Current"]},
    )
    dispatch.task, dispatch.tasks = task, [task]
    cached = pickle.dumps(dispatch.op_data)
    submit = dispatch.tap_confirm.side_effect
    if checkpoint == "planned":
        remember_roommate_target(task, ROOM, final, VIP)
        assert not dispatch.confirms
    else:
        read_room = dispatch.get_agent_from_room.side_effect

        def interrupt_after_delivery(room, plan):
            submit(room, plan)
            dispatch.game_recipient = None
            if checkpoint != "read":
                raise MowerExit

        def interrupt_after_read(*args, **kwargs):
            rows = read_room(*args, **kwargs)
            if dispatch.confirms:
                raise MowerExit
            return rows

        dispatch.tap_confirm.side_effect = interrupt_after_delivery
        dispatch.get_agent_from_room.side_effect = interrupt_after_read
        with pytest.raises(MowerExit):
            dispatch.agent_arrange(task.plan)
        assert dispatch.confirms == [final]
        if checkpoint == "read":
            cached = pickle.dumps(dispatch.op_data)
        dispatch.get_agent_from_room.side_effect = read_room
    assert task.dorm_roommate_targets == {ROOM: (tuple(final), VIP)}
    initial_plan = {ROOM: task.plan[ROOM].copy()}
    scan.time = scheduled - timedelta(seconds=1)
    restored, independent = pickle.loads(pickle.dumps([task, scan]))
    ordinary = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    prepared = replan_update_tasks({"tasks": [ordinary, restored, independent]})
    assert any(t is restored for t in prepared["tasks"])
    assert all(t is not ordinary for t in prepared["tasks"])
    assert not restored.retains_execution

    dispatch.tasks = prepared["tasks"]
    dispatch.task = None
    dispatch.op_data = pickle.loads(cached)
    assert dispatch.op_data.get_current_room(ROOM, True) == (
        final if checkpoint == "read" else before
    )
    dispatch.game_recipient = recipient
    dispatch.tap_confirm.side_effect = submit
    dispatch.tap_confirm.reset_mock()
    dispatch.choose_agent.reset_mock()
    dispatch.get_agent_from_room.reset_mock()
    dispatch.run()
    dispatch.仓库扫描.assert_called_once_with()
    dispatch.get_agent_from_room.assert_not_called()
    assert any(t is restored for t in dispatch.tasks)
    assert all(t is not independent for t in dispatch.tasks)
    assert restored.plan == initial_plan and restored.time == scheduled

    if checkpoint == "stale":
        scheduler.clock.current += timedelta(minutes=16)
    if checkpoint == "initial":
        dispatch.defer_backup_plan_until_mood_read = True
        del dispatch._initial_mood_read_pending
        dispatch._read_agent_mood = Mock(return_value=False)
    reads = []
    read_room = dispatch.get_agent_from_room.side_effect

    def observe(*args, **kwargs):
        rows = read_room(*args, **kwargs)
        assert dispatch.task is restored
        reads.append(
            (
                [row["agent"] for row in rows],
                observed_recovery_recipient(rows, {}),
                dispatch.choose_agent.call_count,
                dispatch.tap_confirm.call_count,
            )
        )
        return rows

    dispatch.get_agent_from_room.side_effect = observe
    dispatch.run()
    assert reads and reads[0] == (
        before if checkpoint == "planned" else final,
        recipient,
        0,
        0,
    )
    assert dispatch.tap_confirm.call_count == extra_confirms
    assert dispatch.choose_agent.call_count == extra_confirms
    if extra_confirms == 0:
        assert len(reads) == 1
    if extra_confirms == 2:
        assert dispatch.confirms[-2] != final
    assert dispatch.physical == final
    assert restored.time == scheduled and not restored.plan
    assert not getattr(restored, "dorm_roommate_targets", {})
    assert all(t is not restored for t in dispatch.tasks)
    target = dispatch.op_data.operators[VIP]
    if recipient is None:
        assert active_recovery_position(dispatch.op_data, target) is None
        assert [n for n, _, _ in target.dorm_roommate_roster] == final
        assert all(ROOM not in t.plan for t in dispatch.tasks)
        dispatch.run()
        dispatch.tap_confirm.assert_not_called()
        dispatch.choose_agent.assert_not_called()
    else:
        assert active_recovery_position(dispatch.op_data, target) == (ROOM, 3)
    scheduler.io.assert_not_called()


def test_another_due_shift_leaves_the_named_dorm_read_on_its_owner(
    dorm_dispatch, scheduler, monkeypatch
):
    dispatch, _, _ = dorm_dispatch
    start_after_release(dispatch, monkeypatch, bed=4)
    roster = [*MANAGERS, NEW, VIP, OTHER]
    now = scheduler.clock.now()
    original = SchedulerTask(now, {ROOM: roster.copy()}, TaskTypes.SHIFT_OFF)
    remember_roommate_target(original, ROOM, roster, VIP)
    dispatch.tasks = replan_update_tasks({"tasks": [original]})["tasks"]
    earlier = SchedulerTask(
        now - timedelta(seconds=1), {"meeting": ["米格鲁"]}, TaskTypes.SHIFT_ON
    )
    dispatch.tasks.append(earlier)
    dispatch.task = earlier
    dispatch._prepare_shift_cycle(earlier)
    assert any(t is original for t in dispatch.tasks)
    assert ROOM not in earlier.plan
    assert original.plan == {ROOM: roster} and original.time == now
    assert not original.retains_execution


def test_planned_dorm_read_keeps_other_work_slots_available(solver):
    roster = dorm_recovery_tests.FINAL.copy()
    task = SchedulerTask(
        task_plan={ROOM: roster, "meeting": ["黑角"]}, task_type=TaskTypes.SHIFT_OFF
    )
    remember_roommate_target(task, ROOM, roster, "银灰")
    updated = replan_update_tasks({"tasks": [task]})["tasks"]
    assert updated[0] is task
    names, slots = retained_task_reservations(solver.op_data, updated)
    assert "黑角" not in names and ("meeting", 0) not in slots

    del task.plan[ROOM]
    assert all(t is not task for t in replan_update_tasks({"tasks": updated})["tasks"])
    task.execution_retained = True
    names, slots = retained_task_reservations(solver.op_data, [task])
    assert "黑角" in names and ("meeting", 0) in slots
