"""Crafters borrow spare recovery slots; ordinary replacements above 22 cannot evict."""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.config.conf import RIICPart  # noqa: E402
from arknights_mower.utils.operators import Operator  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402


@pytest.fixture
def dorm_solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.fodder_operators = []
    config.conf.t5_operators = []
    config.conf.book_operators = []
    config.conf.workshop_manual_backup = None
    config.conf.workshop_settings = [RIICPart.WorkShopSetting(operator="空爆")]
    config.conf.enable_mastery = False
    solver = object.__new__(BaseSchedulerSolver)
    solver.global_plan = {
        "default_plan": Plan(
            {
                "dormitory_1": [
                    Room(name, "", [])
                    for name in ["塑心", "冰酿", "Free", "Free", "Free"]
                ]
            },
            PlanConfig("", "", ""),
        ),
        "backup_plans": [],
    }
    solver.initialize_operators()
    solver.tasks = []
    solver.plan_metadata = MagicMock()
    for name in ["空爆", "红", "陈", "银灰", "伊内丝", "年"]:
        solver.op_data.add(Operator(name, "", mood=5))
    for name, index in [("银灰", 2), ("伊内丝", 4)]:
        op = solver.op_data.operators[name]
        op.operator_type = "high"
        op.resting_priority = "high"
        occupy(solver, name, index)
    return solver


def occupy(solver, name, index):
    op = solver.op_data.operators[name]
    op.current_room = "dormitory_1"
    op.current_index = index
    slot = next(d for d in solver.op_data.dorm if d.position[1] == index)
    slot.name = name
    slot.time = datetime.now() + timedelta(hours=4)
    return slot


@pytest.mark.parametrize(
    "mood,allowed", [(0, True), (22, True), (22.01, False), (23, False), (24, False)]
)
def test_replacement_can_take_crafter_bed_only_at_most_22(dorm_solver, mood, allowed):
    occupy(dorm_solver, "空爆", 3)
    dorm_solver.op_data.operators["红"].mood = mood
    result = dorm_solver.op_data.assign_dorm("红")
    assert (result is not None) == allowed
    assert next(d for d in dorm_solver.op_data.dorm if d.position[1] == 3).name == (
        "红" if allowed else "空爆"
    )


def test_regular_low_priority_main_operator_can_also_take_crafter_bed(dorm_solver):
    occupy(dorm_solver, "空爆", 3)
    op = dorm_solver.op_data.operators["红"]
    op.operator_type = "high"
    op.resting_priority = "low"
    assert dorm_solver.op_data.assign_dorm("红").name == "红"


def test_crafters_never_displace_resting_ordinary_replacements(dorm_solver):
    occupy(dorm_solver, "红", 3)
    assert dorm_solver.op_data.assign_dorm("空爆") is None


def test_crafters_do_not_evict_each_other(dorm_solver):
    config.conf.t5_operators = ["年"]
    occupy(dorm_solver, "空爆", 3)
    assert dorm_solver.op_data.assign_dorm("年") is None


def test_resting_allocates_last_free_slot_to_regular_replacement_first(dorm_solver):
    crafter = dorm_solver.op_data.operators["空爆"]
    replacement = dorm_solver.op_data.operators["红"]
    crafter.mood = 0
    replacement.mood = 5
    dorm_solver.total_agent = [crafter, replacement]
    dorm_solver.resting()
    assert next(d for d in dorm_solver.op_data.dorm if d.position[1] == 3).name == "红"


def test_crafter_uses_spare_slot_when_replacement_does_not_need_rest(dorm_solver):
    crafter = dorm_solver.op_data.operators["空爆"]
    replacement = dorm_solver.op_data.operators["红"]
    crafter.mood = 0
    replacement.mood = 23
    dorm_solver.total_agent = [crafter, replacement]
    dorm_solver.resting()
    assert (
        next(d for d in dorm_solver.op_data.dorm if d.position[1] == 3).name == "空爆"
    )


@pytest.mark.parametrize(
    "field",
    [
        "fodder_operators",
        "t5_operators",
        "book_operators",
        "workshop_settings",
        "workshop_manual_backup",
    ],
)
def test_every_crafting_selection_is_dynamic_and_below_ordinary_replacements(
    dorm_solver, field
):
    op = dorm_solver.op_data.operators["年"]
    regular = dorm_solver.op_data.operators["红"]
    op.operator_type = "high"
    op.resting_priority = "high"
    setattr(
        config.conf,
        field,
        ["年"]
        if field.endswith("operators")
        else [RIICPart.WorkShopSetting(operator="年")],
    )
    assert BaseSchedulerSolver._resting_tier(op) > BaseSchedulerSolver._resting_tier(
        regular
    )
    config.conf.workshop_low_priority_rest = False
    assert BaseSchedulerSolver._resting_tier(op) == BaseSchedulerSolver._REST_TIER_HIGH
    config.conf.workshop_low_priority_rest = True
    assert op.is_workshop()
    setattr(config.conf, field, [] if field != "workshop_manual_backup" else None)
    assert not op.is_workshop()


def test_occupied_crafter_bed_does_not_exhaust_regular_rest_capacity(dorm_solver):
    before = dorm_solver.op_data.available_free("low")
    op = dorm_solver.op_data.operators["空爆"]
    op.operator_type = "high"
    op.resting_priority = "high"
    occupy(dorm_solver, "空爆", 3)
    assert dorm_solver.op_data.available_free("low") == before
    assert dorm_solver.op_data.active_high_resting_count() == 2


@pytest.mark.parametrize("mood,expected", [(22, "红"), (22.01, "空爆"), (24, "空爆")])
def test_free_placeholder_also_preserves_crafter_above_22(dorm_solver, mood, expected):
    occupy(dorm_solver, "空爆", 3)
    for name in ["红", "陈", "年"]:
        dorm_solver.op_data.operators[name].mood = mood if name == "红" else 24
    agents = ["塑心", "冰酿", "银灰", "Free", "伊内丝"]
    dorm_solver.task = MagicMock(plan={"dormitory_1": agents})
    dorm_solver.preserve_resting_crafters(agents, "dormitory_1")
    assert agents[3] == expected


def test_one_tired_replacement_does_not_evict_two_crafters(dorm_solver):
    config.conf.t5_operators = ["年"]
    occupy(dorm_solver, "空爆", 3)
    dorm_solver.op_data.operators["伊内丝"].current_room = ""
    occupy(dorm_solver, "年", 4)
    dorm_solver.op_data.operators["红"].mood = 22
    dorm_solver.op_data.operators["陈"].mood = 23
    agents = ["塑心", "冰酿", "银灰", "Free", "Free"]
    dorm_solver.task = MagicMock(plan={"dormitory_1": agents})
    dorm_solver.preserve_resting_crafters(agents, "dormitory_1")
    assert agents[3:] == ["红", "年"]


def test_disabling_crafter_priority_restores_bed_allocation_and_ui_selection(
    dorm_solver,
):
    config.conf.workshop_low_priority_rest = False
    occupy(dorm_solver, "空爆", 3)
    # Both are ordinary low-priority replacements again: occupied beds stay protected.
    assert dorm_solver.op_data.assign_dorm("红") is None
    agents = ["塑心", "冰酿", "银灰", "Free", "伊内丝"]
    dorm_solver.task = MagicMock(plan={"dormitory_1": agents})
    dorm_solver.preserve_resting_crafters(agents, "dormitory_1")
    assert agents[3] == "Free"
    # Actual free-slot selection must also retain crafters, even with tired replacements.
    dorm_solver.op_data.operators["空爆"].current_room = ""
    assert "空爆" in dorm_solver.get_free_list(agents)
    config.conf.workshop_low_priority_rest = True
    assert "空爆" not in dorm_solver.get_free_list(agents)
