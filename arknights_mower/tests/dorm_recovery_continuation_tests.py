"""普通换班更换室友时，复核原床单回的归属。"""

import pickle
from datetime import datetime
from unittest.mock import Mock

import pytest

from arknights_mower.tests import dorm_recovery_tests
from arknights_mower.tests.dorm_recovery_tests import ROOM
from arknights_mower.utils import config
from arknights_mower.utils.dorm_recovery import (
    active_recovery_position,
    keep_measured_dorm_swap,
    observed_recovery_recipient,
    reconcile_recovery_marker,
)
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.resting_priority import RestingTier, resting_key
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    prioritize_new_dorm_recovery,
)

solver = dorm_recovery_tests.solver
MANAGERS = ["隐德来希", "蜜莓"]
VIP, PEER, OTHER, NEW = "结城理", "星源", "行铃", "八幡海铃"


def start_after_release(
    solver, monkeypatch, bed, *, calculated=False, priority=VIP, second_main=None
):
    monkeypatch.setattr(config.conf, "test_mood_calculation", calculated)
    monkeypatch.setattr(
        dorm_recovery_tests.base_schedule, "try_add_release_dorm", Mock()
    )
    solver._initial_mood_read_pending = Mock(return_value=False)
    solver._prepare_shift_backup = Mock()
    solver.resting = Mock(return_value={})
    solver.agent_get_mood = Mock(return_value={})
    meeting = [Room(VIP, "", ["米格鲁"])]
    moods = {VIP: 8, PEER: 15, OTHER: 9, NEW: 12}
    if second_main is not None:
        name, mood = second_main
        meeting.append(Room(name, "", ["斑点"]))
        moods[name] = mood
    solver.global_plan["default_plan"] = Plan(
        {
            "meeting": meeting,
            ROOM: [Room(n, "", []) for n in [*MANAGERS, "Free", "Free", "Free"]],
        },
        PlanConfig("", "", "", ope_resting_priority=priority),
    )
    assert solver.initialize_operators() is None
    data = solver.op_data
    for name in (PEER, OTHER, NEW, "黑角", "巡林者"):
        if name in data.operators:
            continue
        data.add(Operator(name, ""))
    for op in data.operators.values():
        op.mood, op.time_stamp = moods.get(op.name, 24), datetime.now()
        if calculated:
            data.mood_model.observe(op.name, op.mood)

    occupants = [PEER, VIP, OTHER] if bed == 4 else [OTHER, PEER, VIP]
    solver.physical = MANAGERS + occupants
    solver.game_recipient = VIP
    read_room = solver.get_agent_from_room.side_effect

    def observe(room=ROOM, read_time_index=None, **kwargs):
        rows = read_room(room, read_time_index, **kwargs)
        data = solver.op_data
        for slot in data.dorm:
            slot.name = solver.physical[slot.position[1]]
        evidence = kwargs.get("read_dorm_evidence") or kwargs.get(
            "record_dorm_evidence"
        )
        for index, row in enumerate(rows):
            if solver.game_recipient is None or not (
                evidence or index in (read_time_index or ())
            ):
                row.pop("recovery_seconds", None)
        reconcile_recovery_marker(data, room, rows)
        return rows

    solver.get_agent_from_room.side_effect = observe
    rows = solver.get_agent_from_room(read_dorm_evidence=True)
    proposed = ["Current"] * 5
    proposed[2], proposed[bed - 1] = VIP, occupants[0]
    assert keep_measured_dorm_swap(data, ROOM, proposed, rows)
    assert active_recovery_position(data, data.operators[VIP]) == (ROOM, bed - 1)


def prepare_roommate_shift(solver, old, new, *after_confirm):
    """每次提交后按用例给出读数，最后一份读数持续到下一班。"""
    intent = ["Current"] * 5
    intent[solver.physical.index(old)] = new
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan={ROOM: intent})
    solver.task, solver.tasks = task, [task]
    solver.confirms.clear()
    readings = iter(after_confirm)

    def confirm(room, plan):
        solver.physical = solver.selected + [""] * (5 - len(solver.selected))
        solver.game_recipient = next(readings, after_confirm[-1])
        solver.confirms.append(solver.physical.copy())

    solver.tap_confirm.side_effect = confirm
    solver._prepare_shift_cycle(task)
    return task


def change_roommate(solver, old, new, *after_confirm):
    before = solver.physical.copy()
    task = prepare_roommate_shift(solver, old, new, *after_confirm)
    planned = [
        current if name == "Current" else name
        for current, name in zip(before, task.plan[ROOM], strict=True)
    ]
    assert solver.agent_arrange(task.plan) is not False
    assert not task.plan
    return planned


@pytest.mark.parametrize("bed", [4, 5])
@pytest.mark.parametrize("calculated", [False, True], ids=["measured", "calculated"])
def test_two_roommate_changes_renew_the_same_bed(solver, monkeypatch, bed, calculated):
    start_after_release(solver, monkeypatch, bed, calculated=calculated)
    data = solver.op_data
    for old, new in [(PEER, NEW), (NEW, PEER)]:
        expected = solver.physical.copy()
        expected[bed - 2] = new
        planned = change_roommate(solver, old, new, VIP)
        assert planned == expected
        assert solver.confirms == [expected]
        op = data.operators[VIP]
        assert active_recovery_position(data, op) == (ROOM, bed - 1)
        assert [name for name, _, _ in op.dorm_recovery_roster] == expected


@pytest.mark.parametrize("policy", ["explicit_order", "higher_priority"])
def test_required_order_takes_precedence_over_the_previous_bed(
    solver, monkeypatch, policy
):
    higher = policy == "higher_priority"
    start_after_release(
        solver, monkeypatch, 5, priority=f"{NEW},{VIP}" if higher else VIP
    )
    data = solver.op_data
    if not higher:
        data.config.dorm_order.append(ROOM + "_low")
    target = NEW if higher else VIP
    planned = change_roommate(solver, PEER, NEW, target)
    assert planned[2] == solver.physical[2] == target
    assert sorted(solver.physical) == sorted([*MANAGERS, OTHER, NEW, VIP])
    assert active_recovery_position(data, data.operators[target]) == (ROOM, 2)
    if higher:
        assert active_recovery_position(data, data.operators[VIP]) is None


@pytest.mark.parametrize(
    "after_confirm, expected_count, renewed",
    [
        pytest.param((None,), 1, False, id="unknown"),
        pytest.param((OTHER,), 3, False, id="still-wrong-after-repair"),
        pytest.param((OTHER, None, VIP), 3, True, id="corrected"),
    ],
)
def test_final_read_controls_renewal_and_one_repair(
    solver, monkeypatch, after_confirm, expected_count, renewed
):
    start_after_release(solver, monkeypatch, 4)
    expected = [*MANAGERS, NEW, VIP, OTHER]
    change_roommate(solver, PEER, NEW, *after_confirm)
    assert solver.confirms[0] == solver.confirms[-1] == expected
    assert len(solver.confirms) == expected_count
    if expected_count == 3:
        assert solver.confirms[1] != expected
    data = solver.op_data
    assert active_recovery_position(data, data.operators[VIP]) == (
        (ROOM, 3) if renewed else None
    )


@pytest.mark.parametrize("bed", [4, 5])
@pytest.mark.parametrize("calculated", [False, True], ids=["measured", "calculated"])
def test_unknown_twice_then_measured_in_the_same_bed(
    solver, monkeypatch, bed, calculated
):
    start_after_release(solver, monkeypatch, bed, calculated=calculated)
    data = solver.op_data
    op = data.operators[VIP]
    for old, new, recipient in [(PEER, NEW, None), (NEW, PEER, None), (PEER, NEW, VIP)]:
        expected = solver.physical.copy()
        expected[bed - 2] = new
        assert change_roommate(solver, old, new, recipient) == expected
        assert solver.confirms == [expected]
        if recipient is None:
            assert active_recovery_position(data, op) is None
            assert not op.dorm_recovery_room and not op.dorm_recovery_roster
            assert [name for name, _, _ in op.dorm_roommate_roster] == expected
        else:
            assert active_recovery_position(data, op) == (ROOM, bed - 1)
            assert [name for name, _, _ in op.dorm_recovery_roster] == expected
            assert not op.dorm_roommate_roster


@pytest.mark.parametrize(
    "on_restart, after_repair",
    [(VIP, VIP), (OTHER, VIP), (OTHER, OTHER)],
    ids=["already-correct", "corrected-once", "still-wrong"],
)
def test_restart_reads_delivered_roster_before_any_correction(
    solver, monkeypatch, on_restart, after_repair
):
    from arknights_mower.solvers.base_schedule import MowerExit

    start_after_release(solver, monkeypatch, 4)
    before = solver.physical.copy()
    final = [*MANAGERS, NEW, VIP, OTHER]
    cached = pickle.dumps(solver.op_data)
    task = prepare_roommate_shift(solver, PEER, NEW, on_restart, None, after_repair)
    submit = solver.tap_confirm.side_effect

    def disconnect(room, plan):
        submit(room, plan)
        raise MowerExit

    solver.tap_confirm.side_effect = disconnect
    with pytest.raises(MowerExit):
        solver.agent_arrange(task.plan)
    assert solver.confirms == [final] and task.plan == {ROOM: final}
    solver.op_data = pickle.loads(cached)
    solver.task = pickle.loads(pickle.dumps(task))
    solver.tasks = [solver.task]
    assert solver.op_data.get_current_room(ROOM, True) == before
    first_read = []
    solver.choose_agent.reset_mock()
    read_room = solver.get_agent_from_room.side_effect

    def observe(*args, **kwargs):
        rows = read_room(*args, **kwargs)
        if not first_read and observed_recovery_recipient(rows, {}) == on_restart:
            first_read.append(
                (
                    [row["agent"] for row in rows],
                    len(solver.confirms),
                    solver.choose_agent.call_count,
                )
            )
        return rows

    solver.get_agent_from_room.side_effect = observe
    solver.tap_confirm.side_effect = submit
    assert solver.agent_arrange(solver.task.plan) is not False
    assert first_read == [(final, 1, 0)]
    if on_restart == VIP:
        assert solver.confirms == [final]
    else:
        assert len(solver.confirms) == 3
        assert solver.confirms[1] != final and solver.confirms[-1] == final
    data = solver.op_data
    assert active_recovery_position(data, data.operators[VIP]) == (
        (ROOM, 3) if after_repair == VIP else None
    )
    assert (
        solver.physical == final
        and not solver.task.plan
        and solver.task.time == task.time
    )


def test_roommate_change_outside_the_task_invalidates_unknown_seating(
    solver, monkeypatch
):
    start_after_release(solver, monkeypatch, 4)
    change_roommate(solver, PEER, NEW, None)
    op = solver.op_data.operators[VIP]
    assert [name for name, _, _ in op.dorm_roommate_roster] == solver.physical
    solver.physical[4] = PEER
    solver.get_agent_from_room(read_dorm_evidence=True)
    assert not op.dorm_roommate_roster
    assert active_recovery_position(solver.op_data, op) is None
    planned = change_roommate(solver, NEW, OTHER, None)
    assert planned[2] == solver.physical[2] == VIP
    assert active_recovery_position(solver.op_data, op) is None


def test_wrong_read_on_entry_orders_before_confirming_the_new_roommates(
    solver, monkeypatch
):
    start_after_release(solver, monkeypatch, 4)
    solver.game_recipient = OTHER
    final = [*MANAGERS, NEW, VIP, OTHER]
    assert change_roommate(solver, PEER, NEW, OTHER) == final
    temporary, restored = solver.confirms
    assert temporary != final and temporary[3] == VIP
    assert restored == final
    assert (
        active_recovery_position(solver.op_data, solver.op_data.operators[VIP]) is None
    )


def ordinary_roommate_allocation(data, before):
    """清除副本上的原床记录，取得同一换人意图的普通分床结果。"""
    intent = [NEW if name == PEER else "Current" for name in before]
    unmarked = data.project_arrangements([])
    unmarked.operators[VIP].clear_dorm_recovery_target()
    allocation = prioritize_new_dorm_recovery(unmarked, {ROOM: intent})
    return unmarked.project_arrangements([allocation]).get_current_room(ROOM, True)


@pytest.mark.parametrize("bed", [4, 5])
@pytest.mark.parametrize("calculated", [False, True], ids=["measured", "calculated"])
@pytest.mark.parametrize(
    "incoming_mood, winner", [(18, VIP), (3, NEW)], ids=["resident", "newcomer"]
)
def test_same_tier_primaries_follow_the_allocated_recipient(
    solver, monkeypatch, bed, calculated, incoming_mood, winner
):
    start_after_release(
        solver,
        monkeypatch,
        bed,
        calculated=calculated,
        priority="",
        second_main=(NEW, incoming_mood),
    )
    data = solver.op_data
    ranks = {name: resting_key(data, name) for name in (VIP, NEW)}
    assert ranks[VIP][:2] == ranks[NEW][:2] == (RestingTier.MAIN, 0)
    other = NEW if winner == VIP else VIP
    assert ranks[winner][2] < ranks[other][2]

    before = solver.physical.copy()
    allocated = ordinary_roommate_allocation(data, before)
    assert allocated[2] == winner

    planned = change_roommate(solver, PEER, NEW, winner)
    if winner == VIP:
        expected = [NEW if name == PEER else name for name in before]
        assert solver.confirms == [expected]
    else:
        expected = allocated
        assert active_recovery_position(data, data.operators[VIP]) is None
    assert planned == solver.physical == expected
    op = data.operators[winner]
    assert active_recovery_position(data, op) == (ROOM, expected.index(winner))
    assert [name for name, _, _ in op.dorm_recovery_roster] == expected


def test_same_tier_front_bed_resident_keeps_the_recovery_position(solver, monkeypatch):
    start_after_release(solver, monkeypatch, 5, priority="", second_main=(OTHER, 18))
    data = solver.op_data
    before = solver.physical.copy()
    assert before == [*MANAGERS, OTHER, PEER, VIP]
    back, front = (resting_key(data, name) for name in (VIP, OTHER))
    assert back[:2] == front[:2] == (RestingTier.MAIN, 0)
    assert back[2] < front[2]
    expected = [*MANAGERS, OTHER, NEW, VIP]
    assert ordinary_roommate_allocation(data, before) == expected

    assert change_roommate(solver, PEER, NEW, OTHER) == expected
    assert solver.confirms[-1] == solver.physical == expected
    assert all(roster[2] == OTHER for roster in solver.confirms)
    assert active_recovery_position(data, data.operators[VIP]) is None
    kept = data.operators[OTHER]
    assert active_recovery_position(data, kept) == (ROOM, 2)
    assert [name for name, _, _ in kept.dorm_recovery_roster] == expected
