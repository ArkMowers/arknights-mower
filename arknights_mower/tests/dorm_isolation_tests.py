"""隔离在入住前演算，人数不限，原有单回位和入住者保位优先。"""

import copy
from collections import Counter
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from arknights_mower.tests import shift_backup_convergence_tests as backup
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.plan_advanced import (
    apply_advanced_settings,
    export_advanced_settings,
)
from arknights_mower.utils.emergency_recovery import emergency_dorm_plan
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    plan_dorm_isolation,
    try_add_release_dorm,
)

GUESTS = ["空爆", "黑角", "初雪", "泥岩", "能天使", "年"]
MANAGERS = [
    ("杜林", "闪灵"),
    ("爱丽丝", "桃金娘"),
    ("安赛尔", "芙蓉"),
    ("调香师", "苏苏洛"),
]
solver = backup.solver


@pytest.fixture
def data(monkeypatch):
    monkeypatch.setattr(config, "conf", Conf(enable_mastery=False))
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    rooms = {
        f"dormitory_{index}": [Room(name, "", []) for name in managers]
        + [Room("Free", "", []) for _ in range(3)]
        for index, managers in enumerate(MANAGERS, 1)
    }
    instance = Operators(
        {"default_plan": Plan(rooms, PlanConfig("", "", "")), "backup_plans": []}
    )
    assert instance.init_and_validate() is None
    for name in GUESTS:
        instance.add(Operator(name, ""))
    for op in instance.operators.values():
        op.mood, op.time_stamp = 10, datetime.now()
        if op.room:
            op._current_room, op.current_index = op.room, op.index
    return instance


def put(data, name, room, index):
    op = data.operators[name]
    op._current_room, op.current_index = room, index
    bed = next(bed for bed in data.dorm if bed.position == (room, index))
    bed.name = name


def positions(data):
    return {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }


def test_unlimited_groups_round_trip_and_advanced_import():
    groups = [GUESTS, ["杜林", "黑角"], []]
    conf = Conf(dorm_isolation=groups)
    assert Conf.model_validate_json(conf.model_dump_json()).dorm_isolation == groups
    assert (
        apply_advanced_settings(Conf(), export_advanced_settings(conf)).dorm_isolation
        == groups
    )
    assert Conf().dorm_isolation == []


@pytest.mark.parametrize("groups", [[["黑角", "黑角"]], [["Free"]], [[""]], ["黑角"]])
def test_invalid_group_data_is_rejected(groups):
    with pytest.raises(ValidationError):
        Conf(dorm_isolation=groups)


def test_group_reservations_spread_before_occupancy_changes(data):
    config.conf.dorm_isolation = [GUESTS]
    before = positions(data)
    beds = data.assign_dorm_group(GUESTS)
    assert beds is not None
    count = Counter(bed.position[0] for bed in beds)
    assert len(count) == 4
    assert max(count.values()) == 2
    assert positions(data) == before


def test_multiple_overlapping_groups_use_current_and_reserved_roommates(data):
    config.conf.dorm_isolation = [["空爆", "黑角"], ["空爆", "初雪"]]
    put(data, "黑角", "dormitory_1", 3)
    next(bed for bed in data.dorm if bed.position == ("dormitory_2", 2)).name = "初雪"
    chosen = data.assign_dorm("空爆")
    assert chosen.position[0] in {"dormitory_3", "dormitory_4"}
    assert data.operators["初雪"].current_room == ""


def test_single_free_resident_is_not_displaced_and_two_members_can_cohabit(data):
    data.dorm = [
        bed
        for bed in data.dorm
        if bed.position
        in {
            ("dormitory_1", 2),
            ("dormitory_1", 3),
            ("dormitory_2", 2),
        }
    ]
    put(data, "年", "dormitory_2", 2)
    config.conf.dorm_isolation = [["空爆", "黑角"]]
    before = positions(data)
    beds = data.assign_dorm_group(["空爆", "黑角"])
    assert [bed.position[0] for bed in beds] == ["dormitory_1"] * 2
    assert data.get_current_operator("dormitory_2", 2).name == "年"
    assert positions(data) == before


def test_isolation_does_not_prefer_takeover_over_a_same_group_vacancy(data):
    data.dorm = [
        bed
        for bed in data.dorm
        if bed.position
        in {
            ("dormitory_1", 2),
            ("dormitory_1", 3),
            ("dormitory_2", 2),
        }
    ]
    put(data, "黑角", "dormitory_1", 2)
    put(data, "年", "dormitory_2", 2)
    data.config.ope_resting_priority = ["空爆"]
    config.conf.dorm_isolation = [["空爆", "黑角"]]
    assert data.assign_dorm("空爆").position == ("dormitory_1", 3)
    assert data.get_current_operator("dormitory_2", 2).name == "年"


def test_post_priority_projection_spreads_only_new_secondary_beds(data):
    config.conf.dorm_isolation = [["空爆", "黑角"]]
    put(data, "空爆", "dormitory_1", 2)
    plan = {"dormitory_1": ["Current", "Current", "Current", "黑角", "Current"]}
    before = (
        positions(data),
        copy.deepcopy([(bed.name, bed.time) for bed in data.dorm]),
        copy.deepcopy(plan),
    )
    result = plan_dorm_isolation(data, plan)
    projected = data.project_arrangements([result])
    assert projected.operators["黑角"].current_room != "dormitory_1"
    assert projected.operators["黑角"].current_index > 2
    assert projected.operators["空爆"].current_index == 2
    assert (
        positions(data),
        [(bed.name, bed.time) for bed in data.dorm],
        plan,
    ) == before
    assert plan_dorm_isolation(data, result) == result
    assert plan_dorm_isolation(projected, result) == result


def test_projection_never_changes_single_target_to_satisfy_isolation(data):
    config.conf.dorm_isolation = [["空爆", "黑角"]]
    put(data, "空爆", "dormitory_1", 3)
    plan = {"dormitory_1": ["Current", "Current", "黑角", "Current", "Current"]}
    assert plan_dorm_isolation(data, plan) == plan


def test_reserved_secondary_beds_remain_unavailable(data):
    config.conf.dorm_isolation = [["空爆", "黑角"]]
    put(data, "空爆", "dormitory_1", 2)
    plan = {"dormitory_1": ["Current", "Current", "Current", "黑角", "Current"]}
    reserved = {bed.position for bed in data.dorm if bed.position[0] != "dormitory_1"}
    assert plan_dorm_isolation(data, plan, reserved) == plan


def test_vacancy_planning_keeps_capacity_after_selecting_a_later_room(data):
    data.dorm = [
        bed
        for bed in data.dorm
        if bed.position
        in {
            ("dormitory_1", 2),
            ("dormitory_1", 3),
            ("dormitory_2", 2),
        }
    ]
    config.conf.dorm_isolation = [GUESTS[:3]]
    for name in GUESTS[3:]:
        data.operators[name].mood = 24
    tasks = []
    before = positions(data)
    try_add_release_dorm({}, None, data, tasks)
    projected = data.project_arrangements([tasks[0].plan])
    assert all(projected.operators[name].is_resting() for name in GUESTS[:3])
    assert len({projected.operators[name].current_room for name in GUESTS[:3]}) == 2
    assert positions(data) == before


def test_emergency_admission_spreads_on_projection_without_live_updates(data):
    config.conf.dorm_isolation = [GUESTS]
    before = positions(data), [(bed.name, bed.time) for bed in data.dorm]
    plan = emergency_dorm_plan(
        data, {"targets": {name: 16 for name in GUESTS}}, members=GUESTS
    )
    projected = data.project_arrangements([plan])
    assert len({projected.operators[name].current_room for name in GUESTS}) == 4
    assert (positions(data), [(bed.name, bed.time) for bed in data.dorm]) == before


def test_complete_shift_resolves_isolation_before_submission(solver):
    config.conf.dorm_isolation = [["野鬃", "灰毫"]]
    data = solver.op_data
    data.global_plan["default_plan"].plan["dormitory_2"] = [
        Room("闪灵", "", []),
        Room("爱丽丝", "", []),
        *[Room("Free", "", []) for _ in range(3)],
    ]
    assert data.swap_plan([False], refresh=True) is None
    for name in ("闪灵", "爱丽丝"):
        op = data.operators[name]
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    task = backup.downshift(solver)
    before = positions(data), copy.deepcopy(task.plan)
    solver.enter_room = MagicMock(
        side_effect=AssertionError("projection cannot use device")
    )
    solver._prepare_shift_cycle(task)
    assert positions(data) == before[0]
    projected = data.project_arrangements([task.plan])
    assert (
        projected.operators["野鬃"].current_room
        != projected.operators["灰毫"].current_room
    )
    assert solver.tasks == [task]
    solver.enter_room.assert_not_called()
    solver._activate_shift_backup(task)
    solver.op_data = solver.op_data.project_arrangements([task.plan])
    task.backup_shift_active = False
    solver.tasks, solver.task = [], None
    next_task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    solver._prepare_shift_cycle(next_task)
    assert all(
        name in {"Current", "Free", ""}
        for row in next_task.plan.values()
        for name in row
    )
    assert plan_dorm_isolation(solver.op_data, task.plan) == task.plan


def test_emergency_reallocation_keeps_existing_residents_baseline(data):
    put(data, "空爆", "dormitory_1", 2)
    put(data, "黑角", "dormitory_1", 3)
    state = {"targets": {"空爆": 16, "黑角": 16}}
    before = positions(data), [(bed.name, bed.time) for bed in data.dorm]
    baseline = emergency_dorm_plan(
        data, state, members=state["targets"], reallocate=True
    )
    config.conf.dorm_isolation = [["空爆", "黑角", "杜林"]]
    assert (
        emergency_dorm_plan(data, state, members=state["targets"], reallocate=True)
        == baseline
    )
    assert (positions(data), [(bed.name, bed.time) for bed in data.dorm]) == before


@pytest.mark.parametrize("entry", ["shift", "idle", "projection"])
def test_explicit_low_priority_precedes_isolation(data, entry):
    data.config.dorm_order = ["dormitory_1", "dormitory_1_low", "dormitory_2"]
    config.conf.dorm_isolation = [["空爆", "黑角"]]
    put(data, "空爆", "dormitory_1", 2)
    if entry == "shift":
        assert data.assign_dorm("黑角").position == ("dormitory_1", 3)
    elif entry == "idle":
        for name in GUESTS:
            if name != "黑角":
                data.operators[name].mood = 24
        tasks = []
        try_add_release_dorm({}, None, data, tasks)
        assert tasks
        assert tasks[0].plan["dormitory_1"][3] == "黑角"
    else:
        plan = {"dormitory_1": ["Current"] * 3 + ["黑角", "Current"]}
        assert plan_dorm_isolation(data, plan) == plan


@pytest.mark.parametrize("guard", [None, "priority", "mood", "reservation", "resident"])
def test_custom_order_isolates_equal_newcomers_within_selected_beds(data, guard):
    data.config.dorm_order = ["dormitory_1", "dormitory_1_low", "dormitory_2"]
    config.conf.dorm_isolation = [["空爆", "黑角"]]
    put(data, "空爆", "dormitory_1", 2)
    plan = {
        "dormitory_1": ["Current"] * 3 + ["黑角", "Current"],
        "dormitory_2": ["Current"] * 3 + ["初雪", "Current"],
    }
    reserved = set()
    if guard == "priority":
        data.config.ope_resting_priority = ["黑角"]
    elif guard == "mood":
        data.operators["黑角"].mood = 1
    elif guard == "reservation":
        reserved.add(("dormitory_1", 3))
    elif guard == "resident":
        put(data, "黑角", "dormitory_1", 3)
    before = positions(data), copy.deepcopy(plan)
    result = plan_dorm_isolation(data, plan, reserved)
    if guard:
        assert result == plan
    else:
        assert result["dormitory_1"][3] == "初雪"
        assert result["dormitory_2"][3] == "黑角"
        assert set(result) == set(plan)
        for room in result:
            assert result[room][:3] == ["Current"] * 3
            assert result[room][4] == "Current"
    assert (positions(data), plan) == before
