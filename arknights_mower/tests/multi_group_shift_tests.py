"""Shared followers obey every resting group without driving group mood."""

# ruff: noqa: E402

import sys
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config, mastery_db
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    generate_plan_by_drom,
    plan_metadata,
    try_reorder,
)

A, B, SHARED = "伊内丝", "银灰", "讯使"


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    monkeypatch.setattr(mastery_db, "is_operator_busy", lambda name: False)
    config.conf.enable_mastery = False
    config.conf.rescue_threshold = 0
    instance = object.__new__(BaseSchedulerSolver)
    instance.global_plan = {
        "default_plan": Plan(
            {
                "meeting": [Room(A, "甲", ["陈"]), Room(B, "乙", ["初雪"])],
                "contact": [
                    Room(
                        SHARED,
                        "甲",
                        ["红"],
                        group_bindings=[{"group": "乙", "replacement": ["黑角"]}],
                    )
                ],
                "dormitory_1": [
                    Room("塑心", "", []),
                    Room("冰酿", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            PlanConfig("", "", ""),
        ),
        "backup_plans": [],
    }
    assert instance.initialize_operators() is None
    instance.tasks = []
    instance.find_next_task = MagicMock(return_value=None)
    instance.enter_room = MagicMock(side_effect=AssertionError("device access"))
    instance.last_train_mood_read = datetime.now()
    instance._suppress_train_correction = lambda plan: None
    for op in instance.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    return instance


def apply(solver, plan):
    solver.op_data = solver.op_data.project_arrangements([plan])


def shift_off(solver, group):
    plan, replacements = {}, []
    admitted = solver.get_resting_plan(
        solver.op_data.groups[group], replacements, plan, 0
    )
    if admitted:
        beds = try_reorder(solver.op_data, plan)
        apply(solver, plan)
        apply(solver, beds)
    return admitted, plan


def test_binding_schema_roundtrip_and_legacy_default():
    doc = {
        "plan1": {
            "contact": {
                "plans": [
                    {
                        "agent": SHARED,
                        "group": "甲",
                        "replacement": ["红"],
                        "group_bindings": [{"group": "乙", "replacement": ["黑角"]}],
                    }
                ]
            }
        }
    }
    model = PlanModel(**doc)
    assert PlanModel(**model.model_dump()).plan1.contact.plans[0].group_bindings[
        0
    ].replacement == ["黑角"]
    legacy = PlanModel(plan1={"contact": {"plans": [{"agent": SHARED}]}})
    assert legacy.plan1.contact.plans[0].group_bindings == []


def test_group_members_and_mood_exclude_follower(solver):
    data = solver.op_data
    data.operators[A].mood = 10
    data.operators[B].mood = 20
    data.operators[SHARED].mood = 0
    assert data.shift_group_members("甲") == [A, SHARED]
    assert data.shift_group_members("乙") == [B, SHARED]
    assert data.group_min_mood("甲") == data.group_max_mood("甲") == 10
    assert data.group_min_mood("乙") == 20
    assert data.average_mood() == 30 / 48
    data.select_group_binding(SHARED, "乙")
    assert SHARED not in data.groups["甲"]
    assert data.operators[SHARED].replacement == ["黑角"]
    assert data.group_min_mood("乙") == 20


def test_different_covers_are_mutually_exclusive(solver):
    admitted, plan = shift_off(solver, "甲")
    assert admitted and plan["contact"] == ["红"]
    data = solver.op_data
    old_bed = data.get_dorm_by_name(SHARED)[1].position
    before = deepcopy(data.group_shift_state)
    admitted, plan = shift_off(solver, "乙")
    assert not admitted and plan == {}
    assert data.group_shift_state == before
    assert data.operators[B].current_room == "meeting"
    assert data.get_dorm_by_name(SHARED)[1].position == old_bed
    assert data.get_current_operator("contact", 0).name == "红"


def test_failed_admission_preserves_binding_and_beds(solver):
    data = solver.op_data
    data.operators["黑角"]._current_room = "room_3_3"
    before = deepcopy([(bed.name, bed.time) for bed in data.dorm])
    assert not solver.get_resting_plan(data.groups["乙"], [], {}, 0)
    assert data.operators[SHARED].group == "甲"
    assert data.operators[SHARED].replacement == ["红"]
    assert before == [(bed.name, bed.time) for bed in data.dorm]
    assert data.groups["甲"] == [A, SHARED]


@pytest.mark.parametrize("first,second", [(A, B), (B, A)])
def test_shared_cover_survives_first_return_and_last_return_recalls_primary(
    solver, first, second
):
    solver.op_data.operators[SHARED].group_bindings[1]["replacement"] = ["红"]
    assert shift_off(solver, "甲")[0]
    old_bed = solver.op_data.get_dorm_by_name(SHARED)[1].position
    assert shift_off(solver, "乙")[0]
    data = solver.op_data
    assert data.get_dorm_by_name(SHARED)[1].position == old_bed
    assert sum(bed.name == SHARED for bed in data.dorm) == 1
    now = datetime.now()
    tasks = generate_plan_by_drom(
        {
            now + timedelta(hours=1): ([data.get_dorm_by_name(first)[1]], False),
            now + timedelta(hours=2): ([data.get_dorm_by_name(second)[1]], False),
        },
        data,
    )
    assert len(tasks) == 2
    assert "contact" not in tasks[0].plan
    assert tasks[1].plan["contact"] == [SHARED]
    assert data.group_is_resting("甲") and data.group_is_resting("乙")
    apply(solver, tasks[0].plan)
    assert solver.op_data.get_current_operator("contact", 0).name == "红"
    assert solver.op_data.group_is_resting(data.operators[second].group)
    apply(solver, tasks[1].plan)
    assert solver.op_data.get_current_operator("contact", 0).name == SHARED
    assert not solver.op_data.group_is_resting("甲")
    assert not solver.op_data.group_is_resting("乙")


def test_follower_recovery_time_does_not_delay_group_return(solver):
    assert shift_off(solver, "甲")[0]
    now = datetime.now()
    data = solver.op_data
    data.get_dorm_by_name(A)[1].time = now + timedelta(hours=1)
    data.get_dorm_by_name(SHARED)[1].time = now + timedelta(hours=12)
    data.operators[SHARED].rest_in_full = True
    data.operators[SHARED].mood = 0
    data.operators[A].mood = 10
    data.operators[B].depletion_rate = 0
    tasks = plan_metadata(data, [])
    returns = [task for task in tasks if task.plan.get("contact") == [SHARED]]
    assert len(returns) == 1
    assert returns[0].time < now + timedelta(hours=2)


@pytest.mark.parametrize(
    "bindings, error",
    [
        ([{"group": "甲", "replacement": ["黑角"]}], "重复"),
        ([{"group": "", "replacement": ["黑角"]}], "不能为空"),
        ([{"group": "乙", "replacement": []}], "需要替班"),
        ([{"group": "无主组", "replacement": ["黑角"]}], "至少一名"),
        ([{"group": "乙", "replacement": [B]}], "不可用高效组"),
    ],
)
def test_invalid_binding_reports_actionable_error(solver, bindings, error):
    solver.global_plan["default_plan"].plan["contact"][0].group_bindings = bindings
    assert error in Operators(solver.global_plan).init_and_validate()


def test_reinitialization_preserves_active_binding(solver):
    data = solver.op_data
    data.select_group_binding(SHARED, "乙")
    assert data.init_and_validate(update=True) is None
    assert data.operators[SHARED].group == "乙"
    assert data.operators[SHARED].replacement == ["黑角"]


def test_low_follower_mood_never_triggers_shift(solver):
    data = solver.op_data
    data.operators[SHARED].mood = 0
    solver.total_agent = list(data.operators.values())
    assert solver.resting() == {}


def test_correct_secondary_cover_does_not_recall_any_group(solver):
    assert shift_off(solver, "乙")[0]
    solver.tasks = []
    for name in (B, SHARED):
        solver.op_data.operators[name].mood = 5
        solver.op_data.get_dorm_by_name(name)[1].time = datetime.now() + timedelta(
            hours=4
        )
    assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}


def test_saved_shift_adopts_its_binding_after_another_group_was_planned(solver):
    assert shift_off(solver, "乙")[0]
    data = solver.op_data
    data.select_group_binding(SHARED, "甲")
    projected = data.project_arrangements(
        [{"meeting": ["Current", "初雪"], "contact": ["黑角"]}]
    )
    assert projected.operators[SHARED].group == "乙"
    assert data.operators[SHARED].group == "甲"


def test_runtime_loader_keeps_primary_and_backup_columns(solver, monkeypatch):
    from arknights_mower.utils.operators import build_global_plan

    facility = {
        "plans": [
            {
                "agent": SHARED,
                "group": "甲",
                "replacement": ["红"],
                "group_bindings": [{"group": "乙", "replacement": ["黑角"]}],
            }
        ]
    }
    model = PlanModel(
        plan1={"contact": facility},
        backup_plans=[{"plan": {"contact": facility}, "conf": {}, "trigger": {}}],
    )
    monkeypatch.setattr(config, "plan", model)
    plans = build_global_plan()
    for plan in [plans["default_plan"], plans["backup_plans"][0]]:
        slot = plan.plan["contact"][0]
        assert slot.group_bindings == [{"group": "乙", "replacement": ["黑角"]}]
        assert plan.scheduled_names() == {SHARED, "红", "黑角"}


def test_no_bed_admission_preserves_previous_group(solver):
    data = solver.op_data
    data.dorm = []
    plan = {}
    assert not solver.get_resting_plan(data.groups["乙"], [], plan, 0)
    assert plan == {}
    assert data.operators[SHARED].group == "甲"


def test_same_cover_for_two_groups_keeps_latest_selected_binding(solver):
    data = solver.op_data
    data.operators[SHARED].group_bindings[1]["replacement"] = ["红"]
    data.select_group_binding(SHARED, "乙")
    data.commit_group_shifts({"甲": True, "乙": True})
    assert data.operators[SHARED].group == "乙"


def test_group_return_after_all_anchors_left_dorm_still_recalls_follower(solver):
    assert shift_off(solver, "甲")[0]
    data = solver.op_data
    data.config.operator_mood_limits[A] = {"lower": 0, "upper": 24}
    data.operators[A]._current_room = ""
    data.operators[A].current_index = -1
    data.operators[A].rest_mood_release_limit = 24
    data.select_group_binding(SHARED, "乙")
    tasks = plan_metadata(data, [])
    assert any(task.plan.get("contact") == [SHARED] for task in tasks)


def test_multiple_group_dorm_resident_uses_secondary_cover(solver):
    slot = solver.global_plan["default_plan"].plan["contact"].pop()
    slot.agent = "塑心"
    solver.global_plan["default_plan"].plan["dormitory_1"][0] = slot
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5 if op.name == B else 24, datetime.now()
    admitted, plan = shift_off(solver, "乙")
    assert admitted and plan["dormitory_1"][0] == "黑角"
    assert solver.op_data.get_dorm_by_name("塑心")[0] is None


def test_secondary_free_binding_registers_and_opens_potential_bed(solver):
    plans = solver.global_plan["default_plan"].plan
    slot = plans["contact"].pop()
    slot.agent = "塑心"
    slot.group_bindings[0]["replacement"] = ["Free"]
    plans["dormitory_1"][0] = slot
    data = Operators(solver.global_plan)
    assert data.init_and_validate() is None
    bed = next(bed for bed in data.dorm if bed.position == ("dormitory_1", 0))
    assert not data.is_effective_free_slot(bed, active_groups={"甲"})
    assert data.is_effective_free_slot(bed, active_groups={"乙"})
    assert data.operators["塑心"].group == "甲"


def test_multi_group_standby_follows_each_group_without_requiring_a_bed(solver):
    solver.global_plan["default_plan"].config.resting_standby = [SHARED]
    assert solver.initialize_operators() is None
    data = solver.op_data
    for op in data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5 if op.name in (A, B) else 24, datetime.now()
    data.dorm = data.dorm[:1]
    assert data.operators[SHARED].resting_priority == "standby"
    for group, anchor, cover in [("甲", A, "红"), ("乙", B, "黑角")]:
        admitted, plan = shift_off(solver, group)
        data = solver.op_data
        assert admitted and plan["contact"] == [cover]
        assert data.operators[SHARED].group == group
        assert data.operators[SHARED].current_room == ""
        assert data.is_standby(SHARED)
        assert data.get_dorm_by_name(SHARED)[0] is None
        bed = data.get_dorm_by_name(anchor)[1]
        returns = generate_plan_by_drom({datetime.now(): ([bed], False)}, data)
        assert returns[0].plan["contact"] == [SHARED]
        apply(solver, returns[0].plan)
        assert solver.op_data.operators[SHARED].current_room == "contact"


@pytest.fixture
def dorm_solver(solver):
    plans = solver.global_plan["default_plan"].plan
    slot = plans["contact"].pop()
    slot.agent = "塑心"
    plans["dormitory_1"][0] = slot
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5 if op.name in (A, B) else 24, datetime.now()
    return solver


def test_dorm_follower_switches_covers_only_after_previous_group_returns(dorm_solver):
    solver = dorm_solver
    for group, anchor, cover in [("甲", A, "红"), ("乙", B, "黑角")]:
        admitted, plan = shift_off(solver, group)
        assert admitted and plan["dormitory_1"][0] == cover
        data = solver.op_data
        assert data.operators["塑心"].group == group
        bed = data.get_dorm_by_name(anchor)[1]
        returns = generate_plan_by_drom({datetime.now(): ([bed], False)}, data)
        assert returns[0].plan["dormitory_1"][0] == "塑心"
        apply(solver, returns[0].plan)
        assert solver.op_data.get_current_operator("dormitory_1", 0).name == "塑心"


def test_dorm_follower_reuses_same_cover_without_changing_owner(dorm_solver):
    solver = dorm_solver
    solver.op_data.operators["塑心"].group_bindings[1]["replacement"] = ["红"]
    assert shift_off(solver, "甲")[0]
    assert solver.op_data.is_dorm_replacement("红")
    admitted, plan = shift_off(solver, "乙")
    assert admitted and plan["dormitory_1"][0] == "红"
    assert solver.op_data.group_is_resting("甲")
    assert solver.op_data.group_is_resting("乙")
    assert solver.op_data.get_current_operator("dormitory_1", 0).name == "红"


@pytest.fixture
def free_dorm_solver(dorm_solver):
    solver = dorm_solver
    slot = solver.global_plan["default_plan"].plan["dormitory_1"][0]
    slot.group_bindings[0]["replacement"] = ["Free"]
    assert solver.initialize_operators() is None
    data = solver.op_data
    for op in data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5 if op.name in (A, B) else 24, datetime.now()
    # Select the potential bed first so its opening and subsequent closure are exercised.
    data.dorm.sort(key=lambda bed: bed.position[1] != 0)
    return solver


def test_dorm_free_binding_opens_bed_and_return_relocates_occupant(free_dorm_solver):
    solver = free_dorm_solver
    assert shift_off(solver, "乙")[0]
    data = solver.op_data
    temporary = next(bed for bed in data.dorm if bed.position == ("dormitory_1", 0))
    assert data.is_effective_free_slot(temporary)
    assert temporary.name == B
    anchor_bed = data.get_dorm_by_name(B)[1]
    returns = generate_plan_by_drom({datetime.now(): ([anchor_bed], False)}, data)
    assert returns[0].plan["dormitory_1"][0] == "塑心"
    assert returns[0].plan["meeting"][1] == B
    assert temporary.name == B  # Planning does not evict the live occupant.
    apply(solver, returns[0].plan)
    data = solver.op_data
    temporary = next(bed for bed in data.dorm if bed.position == ("dormitory_1", 0))
    assert not data.is_effective_free_slot(temporary)
    assert data.get_dorm_by_name(B) == (None, None)
    assert data.get_current_operator("dormitory_1", 0).name == "塑心"


def test_occupied_dorm_free_binding_rejects_concrete_cover_without_mutation(
    free_dorm_solver,
):
    solver = free_dorm_solver
    assert shift_off(solver, "乙")[0]
    data = solver.op_data
    assert data.get_dorm_by_name(B)[1].position == ("dormitory_1", 0)
    before = deepcopy((data.groups, data.dorm))
    positions = {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    plan, replacements = {}, []
    assert not solver.get_resting_plan(data.groups["甲"], replacements, plan, 0)
    assert plan == {} and replacements == []
    assert data.groups == before[0]
    assert [(b.position, b.name, b.time) for b in data.dorm] == [
        (b.position, b.name, b.time) for b in before[1]
    ]
    assert positions == {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    assert data.operators["塑心"].group == "乙"
    assert data.operators["塑心"].replacement == ["Free"]


@pytest.mark.parametrize("first_cover", ["红", "Free"])
def test_dorm_secondary_group_accepts_its_working_primary_as_cover(
    dorm_solver, first_cover
):
    solver = dorm_solver
    slot = solver.global_plan["default_plan"].plan["dormitory_1"][0]
    slot.replacement = [first_cover]
    slot.group_bindings[0]["replacement"] = [B]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5 if op.name in (A, B) else 24, datetime.now()
    admitted, plan = shift_off(solver, "乙")
    assert admitted and plan["dormitory_1"][0] == B
    data = solver.op_data
    bed = data.get_dorm_by_name(B)[1]
    assert bed.position == ("dormitory_1", 0)
    assert sum(bed.name == B for bed in data.all_dorms()) == 1
    assert data.operators["塑心"].group == "乙"
    returns = generate_plan_by_drom({datetime.now(): ([bed], False)}, data)
    assert returns[0].plan["dormitory_1"][0] == "塑心"
    assert returns[0].plan["meeting"][1] == B


def test_native_recovery_projects_followers_from_inactive_binding(solver):
    from arknights_mower.utils.emergency_recovery import native_opportunity

    data = solver.op_data
    data.operators[B].mood = 0
    data.operators[A].mood = 24
    data.operators[SHARED].mood = 0
    result = native_opportunity(solver, {B, SHARED}, current_only=True)
    assert result.complete and result.opportunity is not None
    assert data.operators[SHARED].group == "甲"
    assert all(not bed.name for bed in data.dorm)


@pytest.mark.parametrize("reciprocal", [False, True])
def test_dorm_accepts_working_primary_secondary_binding(solver, reciprocal):
    plan = solver.global_plan["default_plan"].plan
    plan["dormitory_1"][0] = Room("塑心", "乙", [SHARED])
    if reciprocal:
        plan["contact"][0].group_bindings[0]["replacement"] = ["塑心"]
    assert solver.initialize_operators() is None
    data = solver.op_data
    assert data.operators[SHARED].group == "甲"
    assert data.is_same_group_dorm_replacement(data.operators["塑心"], SHARED)
    apply(solver, {room: [op.agent for op in row] for room, row in plan.items()})
    admitted, off = shift_off(solver, "乙")
    assert admitted
    assert off["dormitory_1"][0] == SHARED
    assert off["contact"] == (["塑心"] if reciprocal else ["黑角"])
    data = solver.op_data
    assert data.operators[SHARED].group == "乙"
    assert data.get_dorm_by_name(SHARED)[1].position == ("dormitory_1", 0)
    apply(solver, {room: [op.agent for op in row] for room, row in plan.items()})
    assert solver.op_data.get_dorm_by_name(SHARED) == (None, None)
    assert solver.op_data.operators["塑心"].current_room == "dormitory_1"
    assert solver.op_data.operators["塑心"].current_index == 0


def test_worker_accepts_dorm_primary_secondary_binding(solver):
    plan = solver.global_plan["default_plan"].plan
    plan["dormitory_1"][0] = Room(
        "塑心", "甲", ["夜莺"], group_bindings=[{"group": "乙", "replacement": [B]}]
    )
    plan["meeting"][1].replacement = ["塑心"]
    assert solver.initialize_operators() is None
    assert solver.op_data.operators["塑心"].group == "甲"
    apply(solver, {room: [op.agent for op in row] for room, row in plan.items()})
    admitted, off = shift_off(solver, "乙")
    assert admitted
    assert off["meeting"][1] == "塑心"
    assert off["dormitory_1"][0] == B
    assert solver.op_data.operators["塑心"].group == "乙"
    assert solver.op_data.get_dorm_by_name(B)[1].position == ("dormitory_1", 0)


@pytest.mark.parametrize("relationship", ["cross_group", "work_work"])
def test_secondary_binding_retains_primary_replacement_restrictions(
    solver, relationship
):
    plan = solver.global_plan["default_plan"].plan
    if relationship == "cross_group":
        plan["dormitory_1"][0] = Room("塑心", "丙", [SHARED])
    else:
        plan["meeting"][1].replacement = [SHARED]
    assert "替换组不可用高效组干员" in solver.initialize_operators()


@pytest.mark.parametrize("cover", ["Free", B])
def test_incompatible_secondary_binding_waits_even_when_target_has_a_bed(
    free_dorm_solver, cover
):
    s = free_dorm_solver
    plan = s.global_plan["default_plan"].plan
    plan["dormitory_1"][1] = Room("冰酿", "", [])
    plan["dormitory_1"][2] = Room("夜莺", "", [])
    plan["dormitory_1"][3] = Room("杜林", "", [])
    plan["dormitory_1"][0].group_bindings[0]["replacement"] = [cover]
    # A occupies the only regular bed; B uses its binding's dormitory position.
    assert s.initialize_operators() is None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5 if op.name in (A, B) else 24, datetime.now()
    assert shift_off(s, "甲")[0]
    s.op_data.get_dorm_by_name(A)[1].time = datetime.now() + timedelta(hours=1)
    assert s.op_data.available_free() == 0
    # The target has capacity, but conflicts with the resting group.
    live = s.op_data
    s.op_data = deepcopy(live)
    assert not s.get_resting_plan(s.op_data.groups["乙"], [], {}, 1)
    s.op_data = live
    s.tasks = []
    s.total_agent = list(live.operators.values())
    assert s.resting().get("meeting", [])[1:2] != ["初雪"]


@pytest.mark.parametrize("edit", ["inactive", "active", "remove_active"])
def test_backup_column_edit_preserves_only_valid_active_cover(solver, edit):
    s = solver
    s.op_data.operators[B].mood = 5
    s.op_data.operators[SHARED].mood = 5
    assert shift_off(s, "乙")[0]
    previous_plan = deepcopy(s.op_data.plan)
    previous_dorms = deepcopy(s.op_data.all_dorms())
    previous_layout = base_schedule.dorm_rebalance_signature(s.op_data)
    backup_room = deepcopy(previous_plan["contact"])
    if edit == "inactive":
        backup_room[0].replacement = ["砾"]
    elif edit == "active":
        backup_room[0].group_bindings[0]["replacement"] = ["砾"]
    else:
        backup_room[0].group_bindings = []
    s.op_data.backup_plans.append(
        Plan({"contact": backup_room}, PlanConfig("", "", ""))
    )
    assert s.op_data.swap_plan([True], refresh=True) is None
    if edit == "inactive":
        assert s.op_data.operators[SHARED].group == "乙"
        assert s.op_data.operators[SHARED].replacement == ["黑角"]
    correction = s._backup_transition_plan(
        previous_plan, [False], [True], previous_dorms, previous_layout
    )
    assert (
        correction
        == {
            "inactive": {},
            "active": {"contact": ["砾"]},
            "remove_active": {"contact": [SHARED]},
        }[edit]
    )


@pytest.mark.parametrize("cover, capacity", [("红", 0), (A, 1), ("Free", 1)])
def test_dorm_capacity_uses_target_binding_without_changing_active_group(
    free_dorm_solver, cover, capacity
):
    s = free_dorm_solver
    s.global_plan["default_plan"].plan["dormitory_1"][0].replacement = [cover]
    assert s.initialize_operators() is None
    s.op_data.select_group_binding("塑心", "乙")
    groups = deepcopy(s.op_data.groups)
    assert s.op_data.group_dorm_bed_count("甲") == capacity
    assert s.op_data.group_dorm_bed_count("乙") == 1
    assert s.op_data.groups == groups
    assert s.op_data.operators["塑心"].group == "乙"
    assert s.op_data.operators["塑心"].replacement == ["Free"]


def test_successful_planning_does_not_commit_group_or_binding(solver):
    data = solver.op_data
    groups, state = deepcopy(data.groups), dict(data.group_shift_state)
    plan = {}
    assert solver.get_resting_plan(data.groups["乙"], [], plan, 0)
    assert plan["contact"] == ["黑角"]
    assert data.groups == groups and data.group_shift_state == state
    assert data.operators[SHARED].group == "甲"
    projected = data.project_arrangements([plan])
    assert projected.group_is_resting("乙")
    assert not data.group_is_resting("乙")
    assert projected.group_shift_state is not data.group_shift_state


def test_all_resting_bindings_need_one_common_candidate(solver):
    plan = solver.global_plan["default_plan"].plan
    slot = plan["contact"][0]
    slot.replacement = ["红", "黑角"]
    slot.group_bindings = [
        {"group": "乙", "replacement": ["黑角", "砾"]},
        {"group": "丙", "replacement": ["红", "砾"]},
    ]
    plan["central"] = [Room("能天使", "丙", ["夜刀"])]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    assert shift_off(solver, "甲")[0]
    assert solver.op_data.get_current_operator("contact", 0).name == "红"
    assert shift_off(solver, "乙")[0]
    assert solver.op_data.get_current_operator("contact", 0).name == "黑角"
    # Every pair intersects, but the three-way intersection is empty.
    assert not shift_off(solver, "丙")[0]
    assert not solver.op_data.group_is_resting("丙")


def test_every_shared_slot_must_be_compatible(solver):
    plan = solver.global_plan["default_plan"].plan
    plan["contact"][0].group_bindings[0]["replacement"] = ["红"]
    plan["factory"] = [
        Room(
            "褐果",
            "甲",
            ["梅尔"],
            group_bindings=[{"group": "乙", "replacement": ["望"]}],
        )
    ]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    assert shift_off(solver, "甲")[0]
    before = deepcopy(solver.op_data.group_shift_state)
    assert not shift_off(solver, "乙")[0]
    assert solver.op_data.group_shift_state == before
    assert solver.op_data.get_current_operator("factory", 0).name == "梅尔"


def test_partial_arrangement_keeps_state_until_all_targets_are_confirmed(solver):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["Current", "初雪"],
            "contact": ["黑角"],
        },
    )
    solver._prepare_group_shift(task, remember_targets=True)
    data = solver.op_data
    assert not data.group_is_resting("乙")
    # The anchor's room succeeds; training/contact selection is still pending.
    observed = data.project_arrangements([{"meeting": ["Current", "初雪"]}])
    data.operators = observed.operators
    assert not solver._complete_group_shift(task)
    assert task.plan == {"contact": ["黑角"]}
    assert not data.group_is_resting("乙")
    observed = data.project_arrangements([task.plan])
    data.operators = observed.operators
    assert solver._complete_group_shift(task)
    assert data.group_is_resting("乙")
    assert data.operators[SHARED].group == "乙"


def test_pending_shift_blocks_another_execution(solver):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    first = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["陈", "Current"],
            "contact": ["红"],
        },
    )
    solver._prepare_group_shift(first, remember_targets=True)
    solver.tasks = [first]
    second = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["Current", "初雪"],
            "contact": ["黑角"],
        },
    )
    with pytest.raises(base_schedule.ProductSwitchDeferred):
        solver._prepare_group_shift(second)
    assert not solver.op_data.group_is_resting("甲")
    assert not solver.op_data.group_is_resting("乙")


def test_queued_return_rechecks_groups_that_rest_later(solver):
    solver.op_data.operators[SHARED].group_bindings[1]["replacement"] = ["红"]
    assert shift_off(solver, "甲")[0]
    data = solver.op_data
    task = generate_plan_by_drom(
        {datetime.now(): ([data.get_dorm_by_name(A)[1]], False)}, data
    )[0]
    assert task.plan["contact"] == [SHARED]
    assert shift_off(solver, "乙")[0]
    solver._prepare_group_shift(task)
    assert "contact" not in task.plan
    assert task.group_shift_transitions == {"甲": False}
    assert solver.op_data.group_is_resting("甲")
    assert solver.op_data.group_is_resting("乙")


def test_saved_state_survives_released_anchors_and_backup_refresh(solver, monkeypatch):
    import pickle

    from arknights_mower import __main__ as main
    from arknights_mower.solvers.record import current_state

    assert shift_off(solver, "乙")[0]
    data = solver.op_data
    data.operators[B]._current_room, data.operators[B].current_index = "", -1
    for attr in (
        "daily_visit_friend",
        "daily_report",
        "daily_skland",
        "daily_mail",
        "task_count",
    ):
        setattr(solver, attr, None)
    monkeypatch.setattr(main, "base_scheduler", solver)
    saved = pickle.loads(pickle.dumps(current_state()))
    data.group_shift_state = {}
    data.restore_group_shift_state(saved["group_shift_state"])
    assert data.group_is_resting("乙")
    assert not data.group_is_resting("甲")
    assert data.swap_plan([], refresh=True) is None
    assert data.group_is_resting("乙")
    assert data.operators[SHARED].group == "乙"


def test_legacy_state_uses_fixed_anchors_not_follower_position(solver):
    data = solver.op_data
    data.operators[SHARED]._current_room = "dormitory_1"
    data.restore_group_shift_state()
    assert not any(data.group_shift_state.values())
    data.operators[B]._current_room = "dormitory_1"
    data.restore_group_shift_state()
    assert data.group_shift_state == {"甲": False, "乙": True}
    assert data.operators[SHARED].group == "乙"


def test_perception_training_covers_survive_correction(solver):
    plan = solver.global_plan["default_plan"].plan
    plan.pop("contact")
    plan["train"] = [
        Room(
            "褐果",
            "甲",
            ["梅尔"],
            group_bindings=[{"group": "乙", "replacement": ["望"]}],
        ),
        Room(
            "桃金娘",
            "甲",
            ["赫默"],
            group_bindings=[{"group": "乙", "replacement": ["余"]}],
        ),
    ]
    plan["dormitory_1"][0] = Room(
        "塑心",
        "甲",
        ["红"],
        group_bindings=[{"group": "乙", "replacement": ["桃金娘"]}],
    )
    solver.global_plan["default_plan"].config.workaholic = ["褐果", "桃金娘"]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5, datetime.now()
    admitted, off = shift_off(solver, "乙")
    assert admitted and off["train"] == ["望", "余"]
    data = solver.op_data
    data.get_dorm_by_name(B)[1].time = datetime.now() + timedelta(hours=4)
    assert data.get_current_operator("dormitory_1", 0).name == "桃金娘"
    assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
    assert data.get_current_room("train", True) == ["望", "余"]


@pytest.mark.parametrize("same_cover", [False, True])
def test_admission_considers_groups_already_in_the_unexecuted_plan(solver, same_cover):
    data = solver.op_data
    if same_cover:
        data.operators[SHARED].group_bindings[1]["replacement"] = ["红"]
    plan, replacements = {}, []
    assert solver.get_resting_plan(data.groups["甲"], replacements, plan, 0)
    previous = deepcopy(plan)
    admitted = solver.get_resting_plan(data.groups["乙"], replacements, plan, 1)
    assert bool(admitted) is same_cover
    assert not data.group_is_resting("甲") and not data.group_is_resting("乙")
    if same_cover:
        assert plan["meeting"] == ["陈", "初雪"]
        assert sum(bed.name == SHARED for bed in data.dorm) == 1
    else:
        assert plan == previous


def test_partial_shift_intent_survives_restart_and_convergence(solver):
    import pickle

    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["Current", "初雪"],
            "contact": ["黑角"],
            "dormitory_1": ["Current", "Current", B, SHARED, "Current"],
        },
    )
    solver.task = task
    solver.tasks = [task]
    solver._prepare_group_shift(task, remember_targets=True)
    data = solver.op_data
    completed = {room: row for room, row in task.plan.items() if room != "contact"}
    observed = data.project_arrangements([completed])
    data.operators, data.dorm = observed.operators, observed.dorm
    for name in (B, SHARED):
        data.operators[name].mood = 5
        data.get_dorm_by_name(name)[1].time = datetime.now() + timedelta(hours=4)
    assert not solver._complete_group_shift(task)
    solver.task = task = pickle.loads(pickle.dumps(task))
    solver.tasks = [task]
    solver._prepare_shift_cycle(task)
    assert task.group_shift_transitions["乙"] is True
    assert not data.group_is_resting("乙")
    assert task.plan["contact"] == ["黑角"]


def test_same_free_bed_stays_open_until_last_group_returns(free_dorm_solver):
    solver = free_dorm_solver
    data = solver.op_data
    resident = data.operators["塑心"]
    resident.group_bindings[0]["replacement"] = ["Free"]
    resident.replacement = ["Free"]
    assert shift_off(solver, "甲")[0]
    assert shift_off(solver, "乙")[0]
    data = solver.op_data
    tasks = generate_plan_by_drom(
        {
            datetime.now(): ([data.get_dorm_by_name(A)[1]], False),
            datetime.now() + timedelta(hours=1): ([data.get_dorm_by_name(B)[1]], False),
        },
        data,
    )
    assert tasks[0].plan.get("dormitory_1", ["Current"])[0] != "塑心"
    assert tasks[1].plan["dormitory_1"][0] == "塑心"
    apply(solver, tasks[0].plan)
    bed = next(b for b in solver.op_data.dorm if b.position == ("dormitory_1", 0))
    assert solver.op_data.is_effective_free_slot(bed)
    apply(solver, tasks[1].plan)
    assert solver.op_data.get_current_operator("dormitory_1", 0).name == "塑心"


def test_convergence_does_not_consume_incompatible_queued_shift(solver):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    for op in solver.op_data.operators.values():
        op.mood = 5
    first = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["陈", "Current"],
            "contact": ["红"],
            "dormitory_1": ["Current", "Current", A, SHARED, "Current"],
        },
    )
    second = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["Current", "初雪"],
            "contact": ["黑角"],
            "dormitory_1": ["Current", "Current", "Current", SHARED, B],
        },
    )
    solver.task, solver.tasks = first, [first, second]
    solver._prepare_shift_cycle(first)
    assert second in solver.tasks
    assert first.plan["contact"] == ["红"]
    assert first.group_shift_transitions == {"甲": True}


@pytest.mark.parametrize("same_cover", [False, True])
def test_zero_mood_shared_primary_uses_no_bed_and_still_obeys_compatibility(
    solver, same_cover
):
    default = solver.global_plan["default_plan"]
    default.config.workaholic = [SHARED]
    default.plan["dormitory_1"][2] = Room("杜林", "", [])
    if same_cover:
        default.plan["contact"][0].group_bindings[0]["replacement"] = ["红"]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5, datetime.now()
    solver.op_data.operators[SHARED].mood = 0
    assert shift_off(solver, "甲")[0]
    assert not solver.op_data.operators[SHARED].current_room
    assert solver.op_data.get_dorm_by_name(SHARED) == (None, None)
    assert bool(shift_off(solver, "乙")[0]) is same_cover
    data = solver.op_data
    assert {bed.name for bed in data.dorm if bed.name} == (
        {A, B} if same_cover else {A}
    )
    assert data.group_min_mood("甲") == 5
    first = generate_plan_by_drom(
        {datetime.now(): ([data.get_dorm_by_name(A)[1]], False)}, data
    )[0]
    apply(solver, first.plan)
    if same_cover:
        assert solver.op_data.get_current_operator("contact", 0).name == "红"
        assert solver.op_data.get_dorm_by_name(SHARED) == (None, None)
        second = generate_plan_by_drom(
            {datetime.now(): ([solver.op_data.get_dorm_by_name(B)[1]], False)},
            solver.op_data,
        )[0]
        apply(solver, second.plan)
    assert solver.op_data.get_current_operator("contact", 0).name == SHARED
