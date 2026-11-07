"""设施安排以实际完成为准，异常与提前返回不宣告完成。"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests.choose_agent_filter_tests import selection_solver
from arknights_mower.tests.dorm_recovery_tests import FINAL, ROOM
from arknights_mower.tests.dorm_recovery_tests import solver as solver
from arknights_mower.tests.raw_schedule_log_tests import capture
from arknights_mower.utils import log
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room


def events(caplog):
    return [
        record.log_event
        for record in caplog.records
        if getattr(record, "log_event", {}).get("type") == "facility-arrangement"
    ]


def test_room_summary_is_completed_only_after_real_arrangement(
    solver, caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    original = deepcopy(solver.task.plan)
    solver.agent_arrange_room({}, ROOM, solver.task.plan)
    progress = events(caplog)
    assert [event["phase"] for event in progress] == ["started", "completed"]
    assert progress[0]["id"] == progress[1]["id"]
    assert [event["anchor"] for event in progress] == [True, False]
    source = next(
        record
        for record in caplog.records
        if getattr(record, "log_event", {}).get("anchor")
    )
    assert source.getMessage() == "宿舍1"
    assert progress[0]["room"] == ROOM and progress[0]["label"] == "宿舍1"
    assert progress[0]["agents"] == original[ROOM]
    assert progress[1]["agents"] == FINAL
    for record in caplog.records:
        if getattr(record, "log_event", {}).get("type") == "facility-arrangement":
            assert record.log_parent == {
                "type": "facility-arrangement",
                "id": progress[0]["id"],
                "room": ROOM,
            }
    assert solver.physical == FINAL
    assert not solver.task.plan
    assert "_active_facility_log" not in solver.__dict__


def test_retained_recycling_resident_updates_progress_before_confirmation(
    solver, caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    room = "recycle"
    for name in ("国度", "旅骨", "行铃"):
        solver.op_data.add(Operator(name, ""))
    solver.op_data.plan[room] = [Room("国度", "", []), Room("旅骨", "", [])]
    solver.task.plan = {room: ["行铃", "Current"]}
    solver.physical = ["国度", "旅骨"]
    solver.get_agent_from_room(room)
    target = ["行铃", "旅骨"]

    def confirm(room, new_plan):
        progress = events(caplog)
        assert progress[0]["agents"] == ["行铃"]
        assert progress[-1]["agents"] == target
        assert progress[-1]["phase"] == "updated"
        assert progress[-1]["id"] == progress[0]["id"]
        assert progress[-1]["anchor"] is False
        assert solver.physical == ["国度", "旅骨"]
        solver.physical = solver.selected.copy()

    solver.tap_confirm.side_effect = confirm
    solver.agent_arrange_room({}, room, solver.task.plan)

    assert solver.physical == target
    assert not solver.task.plan
    progress = events(caplog)
    assert [event["phase"] for event in progress] == [
        "started",
        "updated",
        "completed",
    ]
    assert sum(event["anchor"] for event in progress) == 1
    update = next(
        record
        for record in caplog.records
        if getattr(record, "log_event", {}).get("phase") == "updated"
    )
    delivered = log._display_snapshots(update, update.getMessage())
    assert delivered["event"] == progress[1]
    assert delivered["parent"] == {
        "type": "facility-arrangement",
        "id": progress[0]["id"],
        "room": room,
    }


def test_resolved_free_resident_updates_progress_before_selection_reordering(
    caplog, monkeypatch, low_frame_rate
):
    capture(caplog, monkeypatch)
    solver, selected = selection_solver(monkeypatch, residents=[])
    room = "recycle"
    target = ["爱丽丝", "伊芙利特"]
    reorder = solver.reorder_selected_agents

    def reorder_after_update(agents, exists):
        progress = events(caplog)
        assert progress[0]["agents"] == ["爱丽丝"]
        assert progress[-1]["agents"] == target
        assert progress[-1]["phase"] == "updated"
        assert progress[-1]["id"] == progress[0]["id"]
        assert progress[-1]["anchor"] is False
        return reorder(agents, exists)

    solver.reorder_selected_agents = reorder_after_update

    def arrange(new_plan, room, plan, *args):
        solver._start_facility_arrangement_log(room, plan[room])
        solver.choose_agent(plan[room], room)
        assert selected == target
        solver._confirm_facility_arrangement_log(room, plan[room])
        del plan[room]
        return new_plan

    solver._arrange_room = arrange
    solver.agent_arrange_room({}, room, {room: ["爱丽丝", "Free"]})

    assert [event["phase"] for event in events(caplog)] == [
        "started",
        "updated",
        "completed",
    ]


def test_training_slot_selection_preserves_the_complete_facility_target(
    caplog, monkeypatch, low_frame_rate
):
    capture(caplog, monkeypatch)
    solver, selected = selection_solver(monkeypatch, residents=[])
    target = ["闪灵", "伊芙利特"]
    solver.clear_agent_selection = MagicMock(side_effect=lambda room: selected.clear())

    def arrange(new_plan, room, plan, *args):
        solver._start_facility_arrangement_log(room, plan[room])
        solver.choose_agent([target[1]], room, fast_mode=False, train_index=1)
        assert selected == [target[1]]
        assert events(caplog)[-1]["agents"] == target
        assert events(caplog)[-1]["positions"] == [
            {"agent": "闪灵", "index": 0},
            {"agent": "伊芙利特", "index": 1},
        ]
        solver._confirm_facility_arrangement_log(room, plan[room])
        return new_plan

    solver._arrange_room = arrange
    solver.agent_arrange_room({}, "train", {"train": target})
    assert [event["phase"] for event in events(caplog)] == ["started", "completed"]


def test_interrupted_single_recovery_keeps_the_final_facility_target(
    solver, caplog, monkeypatch, low_frame_rate
):
    capture(caplog, monkeypatch)
    original = deepcopy(solver.task.plan)
    original_time = solver.task.time
    selection, selected = selection_solver(monkeypatch, residents=solver.physical)
    selection.op_data = solver.op_data
    selection.task = solver.task

    def choose(agents, room, *args, **kwargs):
        assert kwargs["recovery_padding"] is True
        assert agents != original[room]
        selection._active_facility_log = solver._active_facility_log
        selection.choose_agent(agents, room, *args, **kwargs)
        solver.selected = selected.copy()

    solver.choose_agent.side_effect = choose
    solver.tap_confirm.side_effect = base.MowerExit

    with pytest.raises(base.MowerExit):
        solver.agent_arrange_room({}, ROOM, solver.task.plan)

    assert solver.task.plan == original
    assert solver.task.time == original_time
    assert solver.selected != original[ROOM]
    assert [event["phase"] for event in events(caplog)] == ["started", "failed"]
    assert all(event["agents"] == original[ROOM] for event in events(caplog))


@pytest.mark.parametrize(
    "evidence",
    [
        "complete",
        "partial",
        "origin-partial",
        "stale",
        "run-order",
        "fiammetta",
        "workshop",
        "skill-upgrade",
        "swap-support",
    ],
)
def test_confirmed_idle_result_uses_final_room_observation(
    solver, caplog, monkeypatch, evidence
):
    capture(caplog, monkeypatch)
    solver.physical[3] = "黑角"
    solver.get_agent_from_room()
    if evidence == "stale":
        solver.physical[3] = "陈"
    specialized = evidence not in ("complete", "partial", "origin-partial", "stale")
    if specialized:
        solver.task.type = base.TaskTypes[evidence.upper().replace("-", "_")]
    observe = solver.get_agent_from_room.side_effect

    def read_room(*args, **kwargs):
        rows = observe(*args, **kwargs)
        if (
            evidence == "partial"
            and solver.physical == FINAL
            or evidence == "origin-partial"
            and solver.physical[3] == "黑角"
        ):
            rows[3]["observed"] = False
        return rows

    solver.get_agent_from_room.side_effect = read_room
    solver._read_arrangement_order_times = MagicMock()
    solver.agent_arrange(solver.task.plan)
    assert solver.physical == FINAL
    completed = events(caplog)[-1]
    assert completed["phase"] == "completed"
    assert solver.op_data.operators["黑角"].current_room == ""
    results = [
        record
        for record in caplog.records
        if getattr(record, "log_event", {}).get("type") == "facility-idle"
    ]
    if evidence == "complete":
        (result,) = results
        assert result.log_event == {
            "type": "facility-idle",
            "id": completed["id"],
            "room": ROOM,
            "agents": ["黑角"],
        }
        assert result.log_parent == {
            "type": "facility-arrangement",
            "id": completed["id"],
            "room": ROOM,
        }
        assert result.getMessage() == "已确认 [[operator:黑角]] 转为空闲"
    else:
        assert not results
    if specialized and evidence != "fiammetta":
        assert all(
            getattr(record, "log_parent", None) is None for record in caplog.records
        )


def test_fiammetta_scopes_each_facility_attempt_and_its_details(
    solver, caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    work_room = "room_2_2"
    solver.task.type = base.TaskTypes.FIAMMETTA
    solver.task.plan = {
        ROOM: ["冰酿", "闪灵", "菲亚梅塔", "撷英调香师", "歌蕾蒂娅"],
        work_room: ["砾", "苍苔", "引星棘刺"],
    }
    solver.op_data.facility_states[work_room] = {"facility": "manufacture"}
    solver._read_arrangement_order_times = MagicMock()

    def arrange(new_plan, room, plan, *args):
        roster = plan[room]
        solver._start_facility_arrangement_log(room, roster)
        base.logger.info(
            "选人页当前选中", extra={"log_room": room, "log_agents": roster}
        )
        base.logger.info("读取设施进驻结果")
        solver._confirm_facility_arrangement_log(room, roster)
        del plan[room]
        return new_plan

    solver._arrange_room = arrange
    solver.agent_arrange(solver.task.plan)
    base.logger.info("进驻结束后的独立记录")

    attempts = {}
    for record in caplog.records:
        parent = getattr(record, "log_parent", None)
        if parent:
            assert parent["type"] == "facility-arrangement"
            attempts.setdefault(parent["id"], []).append(record)
    assert len(attempts) == 2
    assert {records[0].log_parent["room"] for records in attempts.values()} == {
        work_room,
        ROOM,
    }
    for attempt_id, records in attempts.items():
        started, selection, diagnostic, completed = records
        room = started.log_event["room"]
        parent = {"type": "facility-arrangement", "id": attempt_id, "room": room}
        assert all(record.log_parent == parent for record in records)
        assert started.log_event["phase"] == "started"
        assert completed.log_event["phase"] == "completed"
        assert started.log_event["id"] == completed.log_event["id"] == attempt_id
        assert selection.getMessage() == "选人页当前选中"
        assert selection.log_room == room
        assert diagnostic.getMessage() == "读取设施进驻结果"
    assert not any(
        getattr(record, "log_event", {}).get("type") == "facility-idle"
        for record in caplog.records
    )
    assert caplog.records[-1].getMessage() == "进驻结束后的独立记录"
    assert getattr(caplog.records[-1], "log_parent", None) is None


@pytest.mark.parametrize(
    "result", ["confirmed", "partial", "restoration", "interrupted"]
)
def test_fiammetta_charge_summary_requires_confirmed_charging_arrangement(
    solver, caplog, monkeypatch, result
):
    capture(caplog, monkeypatch)
    target = "歌蕾蒂娅"
    fia = "菲亚梅塔"
    started_summary = (
        "正在安排[[operator:菲亚梅塔]]为[[operator:歌蕾蒂娅]]充能（宿舍1）"
    )
    summary = "已在宿舍1安排[[operator:菲亚梅塔]]充能[[operator:歌蕾蒂娅]]"
    solver.op_data.add(Operator(target, ""))
    solver.op_data.add(Operator(fia, ROOM))
    solver.task.type = base.TaskTypes.FIAMMETTA
    solver.task.meta_data = target if result != "restoration" else ""
    roster = [target, fia] if result != "restoration" else [target, *FINAL[1:-1], fia]
    solver.task.plan = {ROOM: roster.copy()}
    observe = solver.get_agent_from_room.side_effect
    confirm = solver.tap_confirm.side_effect

    def read_room(room, read_time_index=None, related_operators=None, **kwargs):
        rows = observe(room, read_time_index, **kwargs)
        if related_operators:
            assert [event["phase"] for event in events(caplog)] == ["started"]
            assert related_operators == {1: target}
            if result == "partial":
                rows[0]["observed"] = False
        return rows

    def confirm_room(room, new_plan):
        (started,) = events(caplog)
        assert started["phase"] == "started"
        assert started.get("summary") == (
            None if result == "restoration" else started_summary
        )
        assert all(summary not in record.getMessage() for record in caplog.records)
        if result == "interrupted":
            raise base.MowerExit
        confirm(room, new_plan)

    solver.get_agent_from_room.side_effect = read_room
    solver.tap_confirm.side_effect = confirm_room
    if result == "interrupted":
        with pytest.raises(base.MowerExit):
            solver.agent_arrange_room({}, ROOM, solver.task.plan)
    else:
        solver.agent_arrange_room({}, ROOM, solver.task.plan)

    started, terminal = events(caplog)
    assert started["id"] == terminal["id"]
    assert terminal["phase"] == ("failed" if result == "interrupted" else "completed")
    assert terminal["agents"] == roster
    if result == "restoration":
        assert "summary" not in started
    else:
        assert started["summary"] == started_summary
        assert (
            sum(record.getMessage() == started_summary for record in caplog.records)
            == 1
        )
    if result == "confirmed":
        assert terminal["summary"] == summary
        assert sum(record.getMessage() == summary for record in caplog.records) == 1
    else:
        assert "summary" not in terminal
        assert all(summary not in record.getMessage() for record in caplog.records)
    assert all("肥鸭换入完成" not in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    ("room", "capacity", "label"),
    [("central", 5, "控制中枢"), ("room_1_1", 3, "制造站 B101")],
)
def test_work_room_idle_result_uses_observed_origin_and_attempt(
    solver, caplog, monkeypatch, room, capacity, label
):
    capture(caplog, monkeypatch)
    solver.op_data.plan[room] = deepcopy(solver.op_data.plan[ROOM][:capacity])
    solver.op_data.facility_states[room] = {"facility": "manufacture"}
    target = [*FINAL[: capacity - 1], "陈"]
    solver.task.plan = {room: target.copy()}
    solver.physical = [*target[:-1], "桃金娘"]
    solver.get_agent_from_room(room)
    # 缓存中的住员已经变化，本次读房确认真正被替换的是黑角。
    solver.physical[-1] = "黑角"
    solver.get_agent_from_room.reset_mock()
    solver._read_arrangement_order_times = MagicMock()

    def confirm(room, new_plan):
        solver.physical = solver.selected.copy()

    solver.tap_confirm.side_effect = confirm
    solver.agent_arrange(solver.task.plan)

    assert solver.physical == target
    assert solver.get_agent_from_room.call_count == 2
    started, completed = events(caplog)
    assert started["label"] == completed["label"] == label
    assert started["id"] == completed["id"]
    (result,) = [
        record
        for record in caplog.records
        if getattr(record, "log_event", {}).get("type") == "facility-idle"
    ]
    assert result.log_event == {
        "type": "facility-idle",
        "id": completed["id"],
        "room": room,
        "agents": ["黑角"],
    }
    assert result.log_parent == {
        "type": "facility-arrangement",
        "id": completed["id"],
        "room": room,
    }


def test_dorm_reordering_does_not_report_a_reselected_resident_as_idle(
    solver, caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    solver._read_arrangement_order_times = MagicMock()
    solver.agent_arrange(solver.task.plan)
    assert solver.physical == FINAL
    assert len(solver.confirms) == 2
    assert not any(
        getattr(record, "log_event", {}).get("type") == "facility-idle"
        for record in caplog.records
    )


@pytest.mark.parametrize(
    "later_result",
    [
        "complete",
        "reselected",
        "partial",
        "unresolved",
        "deferred",
        "group-unconfirmed",
    ],
)
def test_idle_result_waits_for_other_rooms_to_finish(
    solver, caplog, monkeypatch, later_result
):
    capture(caplog, monkeypatch)
    solver.physical[3] = "黑角"
    solver.get_agent_from_room()
    later = "dormitory_2"
    solver.op_data.plan[later] = deepcopy(solver.op_data.plan[ROOM])
    solver.task.plan[later] = ["桃金娘"]
    solver._read_arrangement_order_times = MagicMock()
    arrange_room = solver._arrange_room

    def idle_records():
        return [
            record.log_event
            for record in caplog.records
            if getattr(record, "log_event", {}).get("type") == "facility-idle"
        ]

    def arrange(new_plan, room, plan, *args):
        if room == ROOM:
            return arrange_room(new_plan, room, plan, *args)
        assert events(caplog)[-1]["phase"] == "completed"
        assert not idle_records()
        solver._start_facility_arrangement_log(room, plan[room])
        if later_result == "deferred":
            return False
        if later_result == "unresolved":
            targets, observed = ["Free"], None
        elif later_result == "partial":
            targets, observed = ["桃金娘"], [{"agent": "桃金娘", "observed": False}]
        else:
            name = "黑角" if later_result == "reselected" else "桃金娘"
            operator = solver.op_data.operators[name]
            operator.current_room, operator.current_index = room, 0
            targets, observed = [name], [{"agent": name}]
        solver._confirm_facility_arrangement_log(room, targets, observed)
        del plan[room]
        if later_result == "group-unconfirmed":
            solver.task.group_shift_expected = {(room, 1): "黑角"}
        return new_plan

    solver._arrange_room = arrange
    solver.agent_arrange(solver.task.plan)
    assert solver.physical == FINAL
    if later_result == "complete":
        (result,) = idle_records()
        assert result["agents"] == ["黑角"]
        assert result["room"] == ROOM
        assert result["id"] == events(caplog)[0]["id"]
    else:
        assert not idle_records()


def test_interruption_before_room_entry_does_not_create_a_progress_anchor(
    solver, caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    original = deepcopy(solver.task.plan)
    solver.enter_room = MagicMock(side_effect=base.MowerExit)
    with pytest.raises(base.MowerExit):
        solver.agent_arrange_room({}, ROOM, solver.task.plan)
    progress = events(caplog)
    assert progress == []
    assert solver.task.plan == original
    assert "_active_facility_log" not in solver.__dict__


def test_suppressed_arrangement_does_not_report_completed(solver, caplog, monkeypatch):
    capture(caplog, monkeypatch)
    solver._suppress_facility_arrangement = MagicMock(
        side_effect=lambda plan: plan.clear()
    )
    solver.agent_arrange_room({}, ROOM, solver.task.plan)
    assert events(caplog) == []


def test_actual_room_detail_is_open_before_the_facility_anchor(
    solver, caplog, monkeypatch
):
    capture(caplog, monkeypatch)

    def before_entry(*args, **kwargs):
        assert events(caplog) == []

    solver.enter_room = MagicMock(side_effect=before_entry)
    solver.turn_on_room_detail = MagicMock(side_effect=before_entry)

    solver.agent_arrange_room({}, ROOM, solver.task.plan)

    assert [event["phase"] for event in events(caplog)] == ["started", "completed"]


def test_interruption_after_the_anchor_updates_the_same_operation(
    solver, caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    solver.choose_agent = MagicMock(side_effect=base.MowerExit)
    with pytest.raises(base.MowerExit):
        solver.agent_arrange_room({}, ROOM, solver.task.plan)
    progress = events(caplog)
    assert [event["phase"] for event in progress] == ["started", "failed"]
    assert progress[0]["id"] == progress[1]["id"]
    assert [event["anchor"] for event in progress] == [True, False]


def test_nested_same_room_arrangements_keep_distinct_anchors(
    solver, caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    active = []

    def arrange(new_plan, room, plan, *args):
        solver._start_facility_arrangement_log(room, plan[room])
        operation = solver._active_facility_log
        active.append(operation)
        if len(active) == 1:
            solver.agent_arrange_room({}, room, {room: ["红"]})
            assert solver._active_facility_log is operation
        solver._confirm_facility_arrangement_log(room, plan[room])
        return new_plan

    solver._arrange_room = arrange

    solver.agent_arrange_room({}, ROOM, {ROOM: ["杜林"]})

    progress = events(caplog)
    assert [event["phase"] for event in progress] == [
        "started",
        "started",
        "completed",
        "completed",
    ]
    assert progress[0]["id"] == progress[3]["id"]
    assert progress[1]["id"] == progress[2]["id"]
    assert progress[0]["id"] != progress[1]["id"]
    assert "_active_facility_log" not in solver.__dict__


def test_facility_anchor_snapshots_the_type_observed_on_entry(caplog, monkeypatch):
    capture(caplog, monkeypatch)
    solver = object.__new__(base.BaseSchedulerSolver)
    room = "room_1_1"
    solver.op_data = SimpleNamespace(
        facility_states={room: {"facility": "manufacture"}}
    )
    solver.enter_room = MagicMock(
        side_effect=lambda current: solver.op_data.facility_states[current].update(
            facility="trade"
        )
    )
    solver.turn_on_room_detail = MagicMock()

    def arrange(new_plan, room, plan, *args):
        assert solver._active_facility_log["label"] == "制造站 B101"
        solver.enter_room(room)
        solver.turn_on_room_detail(room)
        solver._start_facility_arrangement_log(room, plan[room])
        solver._confirm_facility_arrangement_log(room, plan[room])
        return new_plan

    solver._arrange_room = arrange
    solver.agent_arrange_room({}, room, {room: ["陈"]})

    progress = events(caplog)
    assert [event["label"] for event in progress] == ["贸易站 B101", "贸易站 B101"]
    assert progress[0]["id"] == progress[1]["id"]
    assert (
        next(
            record
            for record in caplog.records
            if getattr(record, "log_event", {}).get("anchor")
        ).getMessage()
        == "贸易站 B101"
    )
