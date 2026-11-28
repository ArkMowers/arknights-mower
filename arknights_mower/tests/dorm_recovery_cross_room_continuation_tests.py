"""跨房回班时分别核对原宿舍的实读、空床与实际确认。"""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import (
    dorm_recovery_tests,
    scheduler_recovery_preservation_tests,
)
from arknights_mower.tests.dorm_recovery_tests import ROOM, room_readings
from arknights_mower.utils import resting_priority
from arknights_mower.utils.dorm_recovery import (
    active_recovery_position,
    keep_measured_dorm_swap,
    observed_recovery_recipient,
    reconcile_recovery_marker,
)
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes, try_reorder

scheduler = scheduler_recovery_preservation_tests.scheduler
MANAGERS = ["隐德来希", "蜜莓"]
VIP, RETURNING, OTHER, INCOMING = "结城理", "星源", "行铃", "八幡海铃"
OFFICE = "contact"
SECOND = "dormitory_2"
FIXED = ["絮雨", "国度", "伊芙利特", "玫兰莎"]


@pytest.fixture
def dorm(scheduler, monkeypatch, request):
    s = scheduler.solver
    monkeypatch.delattr(s, "initialize_operators")
    dorm_recovery_tests.prepare_dorm_solver(s, monkeypatch)
    scheduler.clock.current = datetime.now()
    s._initial_mood_read_pending = Mock(return_value=False)
    s.switch_arrange_order = Mock()
    s.swipe_left = Mock()
    s.scan_agent = Mock(return_value=([], []))
    s.resting = Mock(return_value={})
    s.agent_get_mood = Mock(return_value={})
    # 离开办公室和会客室的替班均不进宿舍，补位者由用例单独登记。
    monkeypatch.setattr(resting_priority, "agent_list", [])
    provider_returns = getattr(request, "param", None) == "provider"
    office_primary = MANAGERS[1] if provider_returns else RETURNING
    dorm_slots = [
        MANAGERS[0],
        "Free" if provider_returns else MANAGERS[1],
        *["Free"] * 3,
    ]
    s.global_plan["default_plan"] = Plan(
        {
            "meeting": [Room(VIP, "", ["米格鲁"])],
            OFFICE: [Room(office_primary, "", ["芬"])],
            ROOM: [Room(n, "", []) for n in dorm_slots],
        },
        PlanConfig("", "", "", ope_resting_priority=VIP, free_blacklist="芬,米格鲁"),
    )
    if getattr(request, "param", None) == SECOND:
        plan = s.global_plan["default_plan"]
        plan.plan[SECOND] = [Room(n, "", []) for n in [*FIXED, "Free"]]
        plan.config.ope_resting_priority = [VIP, INCOMING, "能天使"]
    assert s.initialize_operators() is None
    data = s.op_data
    data.add(Operator(OTHER, ""))
    if provider_returns:
        data.add(Operator(RETURNING, ""))
    s.rooms = {OFFICE: ["芬"], "meeting": ["米格鲁", ""]}
    s.confirmations = []

    def read(room, read_time_index=None, **kwargs):
        names = s.rooms[room]
        for index, name in enumerate(names):
            if name:
                data.update_detail(name, data.operators[name].mood, room, index)
        rows = room_readings(data.operators, names, s.game_recipient)
        s._reconcile_room_observation(
            room, rows, expected_agents=kwargs.get("expected_agents")
        )
        if room == ROOM:
            evidence = kwargs.get("read_dorm_evidence") or kwargs.get(
                "record_dorm_evidence"
            )
            for i, row in enumerate(rows):
                if not evidence and i not in (read_time_index or ()):
                    row.pop("recovery_seconds", None)
            reconcile_recovery_marker(data, room, rows)
        return rows

    def confirm(room, plan):
        selected = [n for n in s.selected if n]
        assert all(n in data.operators for n in selected), selected
        # 别房确认只留下原槽的缺口。本房确认才按勾选顺序紧排。
        for other, row in s.rooms.items():
            if other != room:
                s.rooms[other] = ["" if n in selected else n for n in row]
        s.rooms[room] = selected + [""] * (len(s.rooms[room]) - len(selected))
        s.confirmations.append((room, tuple(s.rooms[room])))

    s.get_agent_from_room.side_effect = read
    s.tap_confirm.side_effect = confirm
    yield s
    scheduler.io.assert_not_called()


def start(dorm, bed, departing_bed, *, fill=False):
    data = dorm.op_data
    row = MANAGERS + [OTHER] * 3
    row[bed - 1], row[departing_bed - 1] = VIP, RETURNING
    dorm.rooms[ROOM] = row
    if fill:
        data.add(Operator(INCOMING, ""))
    moods = {VIP: 8, RETURNING: 15, OTHER: 9, INCOMING: 12}
    for name, op in data.operators.items():
        op.mood, op.time_stamp = (
            moods.get(name, 24),
            datetime.now() - timedelta(minutes=1),
        )
    for room in (OFFICE, "meeting"):
        dorm.get_agent_from_room(room)
    dorm.game_recipient = VIP
    observed = dorm.get_agent_from_room(ROOM, read_dorm_evidence=True)
    swap = ["Current"] * 5
    swap[2], swap[bed - 1] = VIP, row[2]
    assert keep_measured_dorm_swap(data, ROOM, swap, observed)
    assert active_recovery_position(data, data.operators[VIP]) == (ROOM, bed - 1)
    dorm.get_agent_from_room.reset_mock()
    return row.copy()


@pytest.mark.parametrize("bed, departing_bed", [(4, 5), (4, 3), (5, 4), (5, 3)])
def test_office_return_without_a_replacement_leaves_the_dorm_alone(
    dorm, bed, departing_bed
):
    before = start(dorm, bed, departing_bed)
    expected = before.copy()
    expected[departing_bed - 1] = ""
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={OFFICE: [RETURNING]})
    dorm.task, dorm.tasks = task, [task]
    dorm.run()
    assert task not in dorm.tasks and dorm.rooms[OFFICE] == [RETURNING]
    assert dorm.confirmations == [(OFFICE, (RETURNING,))]
    assert dorm.rooms[ROOM] == expected
    assert ROOM not in [call.args[0] for call in dorm.enter_room.call_args_list]
    assert ROOM not in [
        call.args[0] for call in dorm.get_agent_from_room.call_args_list
    ]
    assert active_recovery_position(dorm.op_data, dorm.op_data.operators[VIP]) is None


@pytest.mark.parametrize("bed, departing_bed", [(4, 5), (4, 3), (5, 4), (5, 3)])
def test_office_return_and_a_real_admission_use_one_dorm_confirmation(
    dorm, bed, departing_bed
):
    before = start(dorm, bed, departing_bed, fill=True)
    expected = before.copy()
    expected[departing_bed - 1] = INCOMING
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={OFFICE: [RETURNING]})
    dorm.task, dorm.tasks = task, [task]
    dorm.run()
    assert task not in dorm.tasks and dorm.rooms[OFFICE] == [RETURNING]
    assert dorm.confirmations == [(OFFICE, (RETURNING,)), (ROOM, tuple(expected))]
    assert active_recovery_position(dorm.op_data, dorm.op_data.operators[VIP]) == (
        ROOM,
        bed - 1,
    )
    assert [
        n for n, _, _ in dorm.op_data.operators[VIP].dorm_recovery_roster
    ] == expected


def test_ambiguous_new_roster_does_not_renew_the_old_measurement(dorm):
    expected = start(dorm, 5, 4, fill=True)
    expected[3] = INCOMING
    confirm = dorm.tap_confirm.side_effect

    def confirm_with_ambiguous_reading(room, plan):
        confirm(room, plan)
        if room == ROOM:
            dorm.game_recipient = None

    dorm.tap_confirm.side_effect = confirm_with_ambiguous_reading
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={OFFICE: [RETURNING]})
    dorm.task, dorm.tasks = task, [task]
    dorm.run()
    assert task not in dorm.tasks
    assert dorm.confirmations == [(OFFICE, (RETURNING,)), (ROOM, tuple(expected))]
    op = dorm.op_data.operators[VIP]
    assert active_recovery_position(dorm.op_data, op) is None
    assert not op.dorm_recovery_roster


def test_reserved_vacated_bed_waits_for_its_owner(dorm):
    expected = start(dorm, 5, 4, fill=True)
    expected[3] = ""
    booking = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={ROOM: ["Current", "Current", "Current", INCOMING, "Current"]},
        time=datetime.now() + timedelta(hours=1),
    )
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={OFFICE: [RETURNING]})
    dorm.task, dorm.tasks = task, [task, booking]
    dorm.run()
    assert booking in dorm.tasks and task not in dorm.tasks
    assert booking.plan == {
        ROOM: ["Current", "Current", "Current", INCOMING, "Current"]
    }
    assert dorm.rooms[ROOM] == expected
    assert dorm.confirmations == [(OFFICE, (RETURNING,))]
    assert ROOM not in [call.args[0] for call in dorm.enter_room.call_args_list]


def test_explicit_order_applies_when_filling_a_returning_roommates_bed(dorm):
    start(dorm, 5, 4, fill=True)
    dorm.op_data.config.dorm_order.append(ROOM + "_low")
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={OFFICE: [RETURNING]})
    dorm.task, dorm.tasks = task, [task]
    dorm._prepare_shift_cycle(task)
    final = dorm.op_data.project_arrangements([task.plan]).get_current_room(ROOM, True)
    assert final[2] == VIP
    assert sorted(final) == sorted([*MANAGERS, VIP, OTHER, INCOMING])
    assert ROOM not in getattr(task, "dorm_roommate_targets", {})


@pytest.mark.parametrize(
    "required_position", [False, True], ids=["fill-request", "fixed-fourth-bed"]
)
def test_explicit_fill_of_the_vacated_middle_bed_can_still_compact_the_dorm(
    dorm, required_position
):
    start(dorm, 5, 4)
    # 一份明确请求补第四床但没有候选；另一份指定结城理接第四床并腾出第五床。
    # 两者都要求进宿舍确认，确认后游戏会把中间空位挤到末尾。
    row = ["Current"] * 3 + ([VIP, ""] if required_position else ["Free", "Current"])
    fixed = {(ROOM, 3), (ROOM, 4)} if required_position else {(ROOM, 3)}
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON, task_plan={OFFICE: [RETURNING], ROOM: row}
    )
    task.backup_explicit_slots = fixed.copy()
    dorm.task, dorm.tasks = task, [task]
    dorm._prepare_shift_cycle(task)
    assert task.backup_shift_intent[ROOM] == row
    assert task.backup_explicit_slots == fixed
    assert task.plan[ROOM][3] == (VIP if required_position else "Free")
    assert ROOM not in getattr(task, "dorm_roommate_targets", {})
    assert dorm.agent_arrange(task.plan) is not False
    assert dorm.confirmations == [
        (OFFICE, (RETURNING,)),
        (ROOM, (*MANAGERS, OTHER, VIP, "")),
    ]
    assert active_recovery_position(dorm.op_data, dorm.op_data.operators[VIP]) is None


@pytest.mark.parametrize("dorm", ["provider", "recipient"], indirect=True)
def test_departing_provider_or_recipient_invalidates_the_measured_bed(dorm):
    start(dorm, 5, 4, fill=True)
    data = dorm.op_data
    provider = MANAGERS[1]
    if data.plan[OFFICE][0].agent == provider:
        destination, leaving = OFFICE, provider
    else:
        destination, leaving = "meeting", VIP
    old = data.operators[VIP].dorm_recovery_roster
    assert old and data.operators[VIP].dorm_recovery_fixed[0][0] == provider
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON, task_plan={destination: [leaving]}
    )
    dorm.task, dorm.tasks = task, [task]
    dorm._prepare_shift_cycle(task)
    assert data.operators[VIP].dorm_recovery_roster == old
    assert ROOM not in getattr(task, "dorm_roommate_targets", {})
    dorm.game_recipient = None
    assert dorm.agent_arrange(task.plan) is not False
    assert [n for n in dorm.rooms[destination] if n] == [leaving]
    assert leaving not in dorm.rooms[ROOM]
    assert INCOMING in dorm.rooms[ROOM]
    assert any(r == ROOM for r, _ in dorm.confirmations)
    assert active_recovery_position(data, data.operators[VIP]) is None
    assert not data.operators[VIP].dorm_recovery_roster


def dispatch(dorm, task_type, plan):
    task = SchedulerTask(task_type=task_type, task_plan=plan)
    dorm.task, dorm.tasks = task, [task]
    dorm.run()
    assert task not in dorm.tasks


@pytest.mark.parametrize("confirmed", [False, True], ids=["gap-in-place", "compacted"])
def test_fill_after_a_fresh_read_respects_the_observed_recipient(dorm, confirmed):
    start(dorm, 5, 4, fill=True)
    dorm.rooms[OFFICE] = [RETURNING]
    dorm.rooms[ROOM][3] = ""
    dorm.get_agent_from_room(OFFICE)
    if confirmed:
        dorm.rooms[ROOM] = [n for n in dorm.rooms[ROOM] if n] + [""]
    current = dorm.rooms[ROOM].copy()
    observed = dorm.get_agent_from_room(ROOM, read_dorm_evidence=True)
    assert observed_recovery_recipient(observed, {}) == VIP
    swap = ["Current"] * 5
    swap[2], swap[current.index(VIP)] = VIP, current[2]
    assert keep_measured_dorm_swap(dorm.op_data, ROOM, swap, observed)
    vacancy = current.index("")
    fill = ["Current"] * 5
    fill[vacancy] = current[vacancy] = INCOMING
    dispatch(dorm, TaskTypes.SHIFT_OFF, {ROOM: fill})
    assert dorm.confirmations == [(ROOM, tuple(current))]
    assert active_recovery_position(dorm.op_data, dorm.op_data.operators[VIP]) == (
        ROOM,
        current.index(VIP),
    )


@pytest.mark.parametrize("bed,roommate", [(4, 5), (5, 4)])
def test_isolated_ordinary_bed_swap_with_the_measured_target(dorm, bed, roommate):
    current = start(dorm, bed, roommate)
    dorm.task, dorm.tasks = None, []
    assert not try_reorder(dorm.op_data, {})
    dorm.plan_metadata()
    assert all(task.type != TaskTypes.RE_ORDER for task in dorm.tasks)
    swap = ["Current"] * 5
    swap[2], swap[bed - 1] = VIP, current[2]
    dispatch(dorm, TaskTypes.RE_ORDER, {ROOM: swap})
    assert dorm.confirmations == []
    dorm.enter_room.assert_not_called()
    assert dorm.rooms[ROOM] == current
    assert all(task.type != TaskTypes.RE_ORDER for task in dorm.tasks)


def test_reorder_moves_the_target_after_readback_identifies_another_recipient(dorm):
    current = start(dorm, 5, 4)
    dorm.game_recipient = OTHER
    reading = dorm.get_agent_from_room(ROOM, read_dorm_evidence=True)
    assert observed_recovery_recipient(reading, {}) == OTHER
    target = dorm.op_data.operators[VIP]
    assert active_recovery_position(dorm.op_data, target) is None

    expected = current.copy()
    expected[2], expected[4] = VIP, OTHER
    confirm = dorm.tap_confirm.side_effect

    def confirm_then_read_new_recipient(room, plan):
        confirm(room, plan)
        dorm.game_recipient = VIP

    dorm.tap_confirm.side_effect = confirm_then_read_new_recipient
    dispatch(
        dorm, TaskTypes.RE_ORDER, {ROOM: ["Current", "Current", VIP, "Current", OTHER]}
    )
    assert dorm.confirmations[-1] == (ROOM, tuple(expected))
    assert dorm.rooms[ROOM] == expected
    assert active_recovery_position(dorm.op_data, dorm.op_data.operators[VIP]) == (
        ROOM,
        2,
    )


def test_actual_office_change_leaves_the_unrelated_dorm_alone(dorm):
    current = start(dorm, 5, 4)
    dorm.op_data.add(Operator("巡林者", "", mood=24))
    dispatch(dorm, TaskTypes.SELF_CORRECTION, {OFFICE: ["巡林者"]})
    assert dorm.confirmations == [(OFFICE, ("巡林者",))]
    assert dorm.rooms[ROOM] == current
    assert [call.args[0] for call in dorm.enter_room.call_args_list] == [OFFICE]
    assert all(task.type != TaskTypes.RE_ORDER for task in dorm.tasks)


@pytest.mark.parametrize("dorm", [SECOND], indirect=True)
@pytest.mark.parametrize("bed,roommate", [(4, 5), (5, 4)])
def test_independent_roommate_change_keeps_the_other_dorm_in_place(dorm, bed, roommate):
    data = dorm.op_data
    data.add(Operator("能天使", ""))
    data.add(Operator(INCOMING, ""))
    current = start(dorm, bed, roommate)
    data.operators[INCOMING].mood = 15
    dorm.rooms[SECOND] = [*FIXED, "能天使"]
    dorm.get_agent_from_room(SECOND)
    dispatch(dorm, TaskTypes.SHIFT_OFF, {SECOND: ["Current"] * 4 + [INCOMING]})
    assert dorm.rooms[SECOND] == [*FIXED, INCOMING]
    assert dorm.confirmations == [(SECOND, (*FIXED, INCOMING))]
    assert dorm.rooms[ROOM] == current
    assert [call.args[0] for call in dorm.enter_room.call_args_list] == [SECOND]
    assert all(task.type != TaskTypes.RE_ORDER for task in dorm.tasks)


def test_independent_office_return_and_meeting_return_leave_source_beds_vacant(dorm):
    before = start(dorm, 5, 4)
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON, task_plan={OFFICE: [RETURNING], "meeting": [VIP]}
    )
    dorm.task, dorm.tasks = task, [task]
    dorm._prepare_shift_cycle(task)
    assert set(task.plan) == {OFFICE, "meeting"}
    assert dorm.agent_arrange(task.plan) is not False
    assert dict(dorm.confirmations) == {OFFICE: (RETURNING,), "meeting": (VIP, "")}
    assert len(dorm.confirmations) == 2
    assert dorm.rooms[ROOM] == before[:3] + ["", ""]
    assert ROOM not in [call.args[0] for call in dorm.enter_room.call_args_list]
    assert active_recovery_position(dorm.op_data, dorm.op_data.operators[VIP]) is None
