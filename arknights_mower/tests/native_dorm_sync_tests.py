"""实机排班沿用演算的单回资格和宿舍事件分床规则。"""

import pytest

from arknights_mower.tests import (
    dorm_admission_priority_tests,
    dorm_recovery_tests,
    dorm_release_tests,
)
from arknights_mower.tests.resting_priority_tests import set_tier
from arknights_mower.utils.dorm_recovery import (
    active_recovery_position,
    recovery_order_plan,
)
from arknights_mower.utils.operators import Dormitory
from arknights_mower.utils.plan import Room
from arknights_mower.utils.resting_priority import RestingTier
from arknights_mower.utils.scheduler_task import prioritize_new_dorm_recovery

ROOM = "dormitory_1"
SECOND = "dormitory_2"
residents = dorm_admission_priority_tests.residents
solver = dorm_recovery_tests.solver
op_data = dorm_release_tests.op_data


@pytest.mark.parametrize("single_free", [False, True])
def test_skill_worker_never_receives_proactive_confirmation(solver, single_free):
    worker = set_tier(solver.op_data, "闪灵", RestingTier.MAIN, 5)
    worker.single_recovery_manager = False
    solver.op_data.plan[ROOM] = [
        Room(name, "", []) for name in ["琴柳", "Free", "杜林", "黑角", "芬"]
    ]
    names = ["琴柳", "闪灵", "杜林", "黑角", "芬"]
    if not single_free:
        solver.op_data.plan[ROOM][2] = Room("Free", "", [])
        names[2] = "银灰"
    assert recovery_order_plan(solver.op_data, ROOM, names) is None
    assert not solver.ensure_dorm_recovery_order(ROOM, names)
    assert solver.confirms == []


@pytest.mark.parametrize("ordinary_first", [False, True])
def test_skill_worker_admission_uses_compatible_configured_order(
    residents, ordinary_first
):
    data = residents
    data.operators["银灰"].current_room = "meeting"
    data.dorm[0].reset()
    data.plan[SECOND] = [Room("Free", "", [])]
    data.dorm.append(Dormitory((SECOND, 0)))
    data.config.dorm_order = [
        ROOM,
        *([f"{ROOM}_low"] if ordinary_first else []),
        SECOND,
    ]
    worker = set_tier(data, "安赛尔", RestingTier.MAIN, 1)
    assert not worker.single_recovery_manager
    assigned = data.assign_dorm_group([worker.name])
    assert assigned is not None
    assert assigned[0].position == ((ROOM, 4) if ordinary_first else (SECOND, 0))


def test_skill_worker_reordering_avoids_multi_free_first_bed(residents):
    data = residents
    data.operators["银灰"].current_room = "meeting"
    data.dorm[0].reset()
    set_tier(data, "安赛尔", RestingTier.MAIN, 1)
    set_tier(data, "红", RestingTier.MAIN, 10)
    plan = {ROOM: ["Current"] * 3 + ["安赛尔", "红"]}
    result = prioritize_new_dorm_recovery(data, plan)
    projected = data.project_arrangements([result])
    assert projected.get_current_operator(ROOM, 3).name == "红"
    assert projected.get_current_operator(ROOM, 4).name == "安赛尔"
    assert plan[ROOM][3:] == ["安赛尔", "红"]


@pytest.mark.parametrize("name", ["安赛尔", "菲亚梅塔"])
def test_old_skill_target_marker_is_not_a_valid_recovery_position(residents, name):
    op = set_tier(residents, name, RestingTier.MAIN, 5)
    op.current_room, op.current_index = ROOM, 4
    op.dorm_recovery_room, op.dorm_recovery_index = ROOM, 4
    assert active_recovery_position(op) is None


def test_skill_routing_keeps_higher_tier_resident(residents):
    data = residents
    data.operators["银灰"].current_room = "meeting"
    data.dorm[0].reset()
    set_tier(data, "安赛尔", RestingTier.MAIN, 1)
    set_tier(data, "红", RestingTier.PRIORITY, 10)
    plan = {ROOM: ["Current"] * 3 + ["安赛尔", "红"]}
    result = prioritize_new_dorm_recovery(data, plan)
    projected = data.project_arrangements([result])
    assert projected.get_current_operator(ROOM, 3).name == "红"
    assert projected.get_current_operator(ROOM, 4).name == "安赛尔"


def test_skill_routing_falls_back_when_only_multi_free_first_bed_is_available(
    residents,
):
    data = residents
    data.operators["银灰"].current_room = "meeting"
    data.dorm[0].reset()
    set_tier(data, "安赛尔", RestingTier.MAIN, 1)
    protected = set_tier(data, "红", RestingTier.PRIORITY, 5)
    protected.current_room, protected.current_index = ROOM, 4
    data.dorm[1].name = "红"
    assigned = data.assign_dorm_group(["安赛尔"])
    assert assigned is not None and assigned[0].position == (ROOM, 3)
    assert data.dorm[1].name == "红"


def test_unrelated_arrival_does_not_reorder_unchanged_targets(residents):
    data = residents
    data.plan[SECOND] = [Room("Free", "", []), Room("Free", "", [])]
    target = set_tier(data, "陈", RestingTier.MAIN, 20)
    target.current_room, target.current_index = SECOND, 0
    data.dorm.extend([Dormitory((SECOND, 0), "陈"), Dormitory((SECOND, 1))])
    set_tier(data, "红", RestingTier.LOW_MAIN, 1)
    plan = {SECOND: ["Current", "红"]}
    result = prioritize_new_dorm_recovery(data, plan)
    projected = data.project_arrangements([result])
    assert projected.get_current_operator(ROOM, 3).name == "银灰"
    assert projected.get_current_operator(SECOND, 0).name == "陈"


@pytest.mark.parametrize("protected", [False, True])
def test_target_change_reallocates_equal_tiers_by_deficit(residents, protected):
    data = residents
    data.operators["银灰"].mood = 1
    data.plan[SECOND] = [Room("Free", "", []), Room("Free", "", [])]
    other = set_tier(data, "陈", RestingTier.MAIN, 20)
    other.current_room, other.current_index = SECOND, 0
    data.dorm.extend([Dormitory((SECOND, 0), "陈"), Dormitory((SECOND, 1))])
    set_tier(data, "红", RestingTier.PRIORITY, 20)
    plan = {ROOM: ["Current"] * 4 + ["红"]}
    reserved = {(SECOND, 0)} if protected else set()
    result = prioritize_new_dorm_recovery(data, plan, reserved)
    projected = data.project_arrangements([result])
    assert projected.get_current_operator(ROOM, 3).name == "红"
    assert projected.get_current_operator(SECOND, 0).name == (
        "陈" if protected else "银灰"
    )
    assert projected.get_current_operator(ROOM, 4).name == (
        "银灰" if protected else "陈"
    )
    assert data.operators["银灰"].current_index == 3
    assert data.operators["陈"].current_index == 0
