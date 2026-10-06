"""Multiple group followers use the latest admitted shift without driving mood."""

# ruff: noqa: E402

import sys
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config
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


def test_each_group_uses_its_cover_without_reserving_follower_twice(solver):
    admitted, plan = shift_off(solver, "甲")
    assert admitted and plan["contact"] == ["红"]
    assert solver.op_data.operators[B].current_room == "meeting"
    assert solver.op_data.operators[SHARED].is_resting()
    old_bed = solver.op_data.get_dorm_by_name(SHARED)[1].position
    admitted, plan = shift_off(solver, "乙")
    assert admitted and plan["contact"] == ["黑角"]
    assert solver.op_data.operators[SHARED].group == "乙"
    assert solver.op_data.get_dorm_by_name(SHARED)[1].position == old_bed
    assert sum(bed.name == SHARED for bed in solver.op_data.dorm) == 1
    assert solver.op_data.operators["红"].current_room == ""


def test_failed_admission_preserves_binding_and_beds(solver):
    data = solver.op_data
    data.operators["黑角"]._current_room = "room_3_3"
    before = deepcopy([(bed.name, bed.time) for bed in data.dorm])
    assert not solver.get_resting_plan(data.groups["乙"], [], {}, 0)
    assert data.operators[SHARED].group == "甲"
    assert data.operators[SHARED].replacement == ["红"]
    assert before == [(bed.name, bed.time) for bed in data.dorm]
    assert data.groups["甲"] == [A, SHARED]


def test_return_from_any_binding_overrides_current_group_only_on_projection(solver):
    assert shift_off(solver, "甲")[0]
    assert shift_off(solver, "乙")[0]
    data = solver.op_data
    bed = data.get_dorm_by_name(A)[1]
    tasks = generate_plan_by_drom(
        {datetime.now() + timedelta(hours=1): ([bed], False)}, data
    )
    assert len(tasks) == 1
    assert tasks[0].plan["contact"] == [SHARED]
    assert data.operators[SHARED].group == "乙"
    projected = data.project_arrangements([tasks[0].plan])
    assert projected.operators[SHARED].group == "甲"
    assert data.operators[SHARED].group == "乙"
    assert SHARED in data.groups["乙"]
    assert SHARED in projected.groups["甲"]


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
    data.select_arrangement_bindings({"meeting": ["陈", "初雪"], "contact": ["红"]})
    assert data.operators[SHARED].group == "乙"


def test_group_return_after_all_anchors_left_dorm_still_recalls_follower(solver):
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


def test_dorm_follower_switches_covers_and_returns_with_either_group(dorm_solver):
    solver = dorm_solver
    for group, cover in [("甲", "红"), ("乙", "黑角")]:
        admitted, plan = shift_off(solver, group)
        assert admitted and plan["dormitory_1"][0] == cover
        assert solver.op_data.operators["塑心"].group == group
        assert solver.op_data.get_dorm_by_name("塑心")[0] is None
        assert solver.op_data.get_current_operator("dormitory_1", 0).name == cover
    data = solver.op_data
    assert {bed.name for bed in data.dorm if bed.name} == {A, B}
    bed = data.get_dorm_by_name(A)[1]
    returns = generate_plan_by_drom({datetime.now(): ([bed], False)}, data)
    assert returns[0].plan["dormitory_1"][0] == "塑心"
    assert data.operators["塑心"].group == "乙"
    apply(solver, returns[0].plan)
    assert solver.op_data.operators["塑心"].group == "甲"
    assert solver.op_data.get_current_operator("dormitory_1", 0).name == "塑心"
    assert solver.op_data.operators[B].is_resting()
    assert solver.op_data.operators["黑角"].current_room == ""


def test_dorm_follower_reuses_same_cover_when_latest_group_changes(dorm_solver):
    solver = dorm_solver
    solver.op_data.operators["塑心"].group_bindings[1]["replacement"] = ["红"]
    assert shift_off(solver, "甲")[0]
    assert solver.op_data.is_dorm_replacement("红")
    admitted, plan = shift_off(solver, "乙")
    assert admitted and plan["dormitory_1"][0] == "红"
    assert solver.op_data.operators["塑心"].group == "乙"
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
    assert shift_off(solver, "甲")[0]
    assert shift_off(solver, "乙")[0]
    data = solver.op_data
    temporary = next(bed for bed in data.dorm if bed.position == ("dormitory_1", 0))
    assert data.is_effective_free_slot(temporary)
    assert temporary.name == B
    anchor_bed = data.get_dorm_by_name(A)[1]
    returns = generate_plan_by_drom({datetime.now(): ([anchor_bed], False)}, data)
    assert returns[0].plan["dormitory_1"][0] == "塑心"
    assert B in returns[0].plan["dormitory_1"][2:]
    assert temporary.name == B  # Planning does not evict the live occupant.
    apply(solver, returns[0].plan)
    data = solver.op_data
    temporary = next(bed for bed in data.dorm if bed.position == ("dormitory_1", 0))
    assert not data.is_effective_free_slot(temporary)
    assert data.get_dorm_by_name(B)[1].position != temporary.position
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
