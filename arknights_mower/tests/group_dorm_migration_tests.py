"""普通宿舍迁移保留仍在接替固定宿管的同组工作主班。"""

from copy import deepcopy

import pytest

from arknights_mower.solvers import record
from arknights_mower.tests import dorm_group_tests as native
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import rebalance_plan_swap_dorms

solver = native.solver
pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture(autouse=True)
def isolated_agent_history(monkeypatch):
    monkeypatch.setattr(record, "save_agent_action", lambda *args, **kwargs: None)


@pytest.fixture
def covered_group_bed(isolated_agent_history, solver):
    solver.global_plan["default_plan"].plan["dormitory_1"][0].replacement = ["伊内丝"]
    assert solver.initialize_operators() is None
    solver.op_data.add(Operator("泥岩", ""))
    native.apply_plan(
        solver,
        {
            "meeting": ["陈", "初雪"],
            "contact": ["红"],
            "dormitory_1": ["伊内丝", "冰酿", "银灰", "讯使", "泥岩"],
        },
    )
    data = solver.op_data
    for name in ("伊内丝", "银灰", "讯使", "泥岩"):
        data.operators[name].mood = 12
    bed = data.get_group_dorm("dormitory_1", 0)
    assert bed.name == "伊内丝"
    assert data.is_recovery_dorm(bed, "伊内丝")
    return data, bed


@pytest.mark.parametrize("reorder", [False, True])
def test_migration_preserves_effective_fixed_cover_and_recovery_time(
    covered_group_bed, reorder
):
    data, fixed = covered_group_bed
    previous = deepcopy(data.all_dorms())
    recovered_at = fixed.time
    positions = {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    plan = rebalance_plan_swap_dorms(data, previous, reorder=reorder)
    assert plan.get("dormitory_1", ["Current"] * 5)[0] == "Current"
    assert not any("伊内丝" in row for row in plan.values())
    assert (fixed.name, fixed.time) == ("伊内丝", recovered_at)
    assert all(bed.name != "伊内丝" for bed in data.dorm)
    assert {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    } == positions
    projected = data.project_arrangements([plan])
    assert projected.get_current_operator(*fixed.position).name == "伊内丝"


def test_invalidated_fixed_cover_is_migrated_to_a_dynamic_bed(covered_group_bed):
    data, fixed = covered_group_bed
    previous = deepcopy(data.all_dorms())
    data.plan["dormitory_1"][0].replacement = ["银灰"]
    data.operators["塑心"].replacement = ["银灰"]
    assert not data.is_recovery_dorm(fixed, "伊内丝")
    plan = rebalance_plan_swap_dorms(data, previous)
    assert plan["dormitory_1"][0] == "塑心"
    destination = next(bed for bed in data.dorm if bed.name == "伊内丝")
    assert destination.position != fixed.position
    assert plan[destination.position[0]][destination.position[1]] == "伊内丝"
    projected = data.project_arrangements([plan])
    assert projected.get_current_operator(*fixed.position).name == "塑心"
    assert projected.get_current_operator(*destination.position).name == "伊内丝"


def test_confirmed_group_return_can_restore_the_fixed_manager(covered_group_bed):
    data, fixed = covered_group_bed
    previous = deepcopy(data.all_dorms())
    return_plan = {
        "meeting": ["伊内丝", "银灰"],
        "contact": ["讯使"],
        "dormitory_1": ["塑心", "Current", "Current", "Current", "Current"],
    }
    projected = data.project_arrangements([return_plan])
    current = projected.get_current_operator(*fixed.position)
    assert current.name == "塑心"
    assert not projected.is_recovery_dorm(
        projected.get_group_dorm(*fixed.position), current.name
    )
    plan = rebalance_plan_swap_dorms(
        projected,
        previous,
        reserved_names={name for row in return_plan.values() for name in row},
    )
    assert not any("伊内丝" in row for row in plan.values())
    final = projected.project_arrangements([plan])
    assert final.get_current_operator(*fixed.position).name == "塑心"
    assert final.get_current_operator("meeting", 0).name == "伊内丝"


def test_explicit_cover_departure_does_not_reserve_its_old_fixed_bed(covered_group_bed):
    data, fixed = covered_group_bed
    previous = deepcopy(data.all_dorms())
    projected = data.project_arrangements([{"meeting": ["伊内丝", "Current"]}])
    assert projected.get_current_operator(*fixed.position) is None
    plan = rebalance_plan_swap_dorms(projected, previous, reserved_names={"伊内丝"})
    assert not any("伊内丝" in row for row in plan.values())
    final = projected.project_arrangements([plan])
    assert final.get_current_operator("meeting", 0).name == "伊内丝"
