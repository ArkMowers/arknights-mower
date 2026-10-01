"""救急和普通分床使用相同层级，旧住客和候补不能跨级保床。"""

from copy import deepcopy
from datetime import timedelta

import pytest

from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.resting_priority import RestingTier, resting_tier
from arknights_mower.utils.scheduler_task import TaskTypes, try_add_release_dorm


def set_role(data, tier, incoming=False):
    if tier in (RestingTier.PRIORITY_REPLACEMENT, RestingTier.REPLACEMENT):
        name = COVERS[int(incoming)]
        if tier == RestingTier.PRIORITY_REPLACEMENT:
            data.config.resting_priority_replacement.append(name)
    elif tier == RestingTier.IDLE:
        name = "陨星" if incoming else "红"
        data.add(Operator(name, ""))
    else:
        name = PRIMARY[int(incoming)]
        op = data.operators[name]
        op.resting_priority = {
            RestingTier.PRIORITY: "high",
            RestingTier.MAIN: "high",
            RestingTier.LOW_MAIN: "low",
            RestingTier.STANDBY: "standby",
        }[tier]
        if tier == RestingTier.PRIORITY:
            data.config.ope_resting_priority.append(name)
        if tier == RestingTier.STANDBY:
            data.config.resting_standby.append(name)
    op = data.operators[name]
    op.mood, op.time_stamp, op.depletion_rate = 5, NOW, 0
    return name


@pytest.mark.parametrize("rescue", [False, True])
@pytest.mark.parametrize("resident_tier", list(RestingTier)[:-1])
@pytest.mark.parametrize("incoming_tier", list(RestingTier)[:-1])
def test_takeover_uses_strict_tier_in_both_modes(
    solver, rescue, resident_tier, incoming_tier
):
    data = solver.op_data
    data.config.ope_resting_priority = []
    data.config.resting_priority_replacement = []
    data.config.resting_standby = []
    resident = set_role(data, resident_tier)
    incoming = set_role(data, incoming_tier, incoming=True)
    data.rescue_mode = rescue
    bed = data.dorm[0]
    bed.name, bed.time = resident, NOW + timedelta(hours=2)
    op = data.operators[resident]
    op._current_room, op.current_index = bed.position
    assert resting_tier(data, resident) == resident_tier
    assert resting_tier(data, incoming) == incoming_tier
    before = deepcopy(vars(bed))
    assert data._slot_takable(bed, requester=incoming) is (
        incoming_tier < resident_tier
    )
    assert vars(bed) == before


@pytest.mark.parametrize("temporary", [False, True])
def test_legacy_idle_resident_has_no_formal_rescue_protection(solver, temporary):
    data = solver.op_data
    name = set_role(data, RestingTier.IDLE)
    op = data.operators[name]
    op.temporary_dorm_fill = temporary
    bed = data.dorm[0]
    bed.name = name
    op._current_room, op.current_index = bed.position
    data.rescue_mode = True
    assert not data.is_rescue_recovering(name, NOW)
    assert data._slot_takable(bed, requester=PRIMARY[0])


def test_rescue_does_not_disable_configured_standby(solver):
    data = solver.op_data
    data.config.resting_standby = [PRIMARY[1]]
    data.rescue_mode = True
    data.shadow_copy = deepcopy(data.operators)
    data.operators.pop(PRIMARY[1])
    data.add(Operator(PRIMARY[1], "room_1_2", index=0, operator_type="high"))
    candidate = data.operators[PRIMARY[1]]
    assert candidate.rest_in_full
    assert candidate.resting_priority == "standby"
    candidate.standby_low_priority = True
    assert data._can_standby(candidate)
    assert resting_tier(data, candidate.name) == RestingTier.LOW_MAIN


def test_idle_replacement_entry_can_take_lower_rescue_priority(solver):
    data = solver.op_data
    data.config.free_room = True
    data.config.resting_priority_replacement = [COVERS[0]]
    resident = data.operators[PRIMARY[0]]
    resident.resting_priority = "standby"
    data.config.resting_standby = [resident.name]
    resident.mood, resident.time_stamp = 20, NOW
    bed = data.dorm[0]
    bed.name, bed.time = resident.name, NOW + timedelta(hours=2)
    resident._current_room, resident.current_index = bed.position
    data.rescue_mode = True
    candidate = data.operators[COVERS[0]]
    candidate.mood, candidate.time_stamp = 5, NOW
    for other in data.dorm[1:]:
        other.name = PRIMARY[2 + data.dorm.index(other) - 1]
        op = data.operators[other.name]
        op._current_room, op.current_index = other.position
        op.mood, op.time_stamp = 5, NOW
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    assert tasks[0].type == TaskTypes.NOT_SPECIFIC
    assert tasks[0].plan[bed.position[0]][bed.position[1]] == candidate.name
