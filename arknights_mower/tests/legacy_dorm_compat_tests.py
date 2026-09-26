"""#1131 的稳定宿舍补床／让床修复，不改变测试宿舍路径。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import group_resting_capacity_tests, ling_xi_rest_limit_tests
from arknights_mower.tests.group_resting_capacity_tests import (
    COVERS,
    DEEP,
    OTHERS,
    apply_plan,
)
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    try_add_release_dorm,
)

base_solver = group_resting_capacity_tests.solver
release_solver = ling_xi_rest_limit_tests.solver


@pytest.fixture(params=[False, True], ids=["legacy", "experimental"])
def solver(base_solver, request):
    data = base_solver.op_data
    config.conf.experimental_dorm_logic = request.param
    data.config.experimental_dorm_logic = request.param
    data.config.free_room = True
    base_solver.task = None
    anchor, standby = (data.operators[name] for name in DEEP[:2])
    first, second = data.dorm[:2]
    plan = {}
    for op, bed, cover in [(anchor, first, COVERS[0]), (standby, second, COVERS[1])]:
        plan.setdefault(op.room, ["Current"] * len(data.plan[op.room]))[op.index] = (
            cover
        )
        room, index = bed.position
        plan.setdefault(room, ["Current"] * len(data.plan[room]))[index] = op.name
    apply_plan(base_solver, plan)
    standby.mood = data.rescue_mood_threshold(standby) + 1
    return base_solver


def vacate_standby(solver):
    data = solver.op_data
    name = DEEP[1]
    _, bed = data.get_dorm_by_name(name)
    room, index = bed.position
    plan = {room: ["Current"] * len(data.plan[room])}
    plan[room][index] = "Free"
    apply_plan(solver, plan)
    assert data.is_standby(name)
    return bed


def test_free_pool_admits_only_legacy_waiting_standby_and_keeps_exclusions(solver):
    data = solver.op_data
    vacate_standby(solver)
    assert (DEEP[1] in solver.get_free_list([])) is (not data.experimental_dorm_logic)
    assert DEEP[1] not in solver.get_free_list([DEEP[1]])
    solver.task = SchedulerTask(task_plan={"meeting": [DEEP[1], "Current"]})
    assert DEEP[1] not in solver.get_free_list([])


def test_free_pool_does_not_treat_uncovered_idle_main_as_waiting_standby(solver):
    data = solver.op_data
    vacate_standby(solver)
    data.operators[COVERS[1]].current_room = ""
    assert not data.is_standby(DEEP[1])
    assert DEEP[1] not in solver.get_free_list([])


def test_waiting_standby_fills_empty_bed_in_both_modes(solver):
    bed = vacate_standby(solver)
    tasks = []
    try_add_release_dorm({}, None, solver.op_data, tasks)
    room, index = bed.position
    assert any(DEEP[1] in names for t in tasks for names in t.plan.values())
    if not solver.op_data.experimental_dorm_logic:
        assert any(
            t.plan.get(room, [])[index] == DEEP[1] for t in tasks if room in t.plan
        )


def test_finished_standby_can_be_replaced_in_both_modes(solver):
    data = solver.op_data
    standby = data.operators[DEEP[1]]
    standby.mood = standby.upper_limit
    _, bed = data.get_dorm_by_name(standby.name)
    bed.time = datetime.now() - timedelta(minutes=1)
    room, index = bed.position
    # 空床已有补位预约，本用例单独验证回满候补仍可清退。
    # 没有预约的真空床在测试模式下应先生成优先补位，不能夹带普通清退。
    reserved = {}
    for other in data.dorm:
        if not other.name:
            target_room, target_index = other.position
            reserved.setdefault(target_room, ["Current"] * len(data.plan[target_room]))[
                target_index
            ] = "Free"
    tasks = [SchedulerTask(task_plan=reserved)] if reserved else []
    try_add_release_dorm({}, None, data, tasks)
    assert any(
        t.plan.get(room, [])[index] not in ("Current", standby.name)
        for t in tasks
        if room in t.plan
    )


def test_main_preempts_standby_and_experimental_also_allows_low_main(solver):
    data = solver.op_data
    _, bed = data.get_dorm_by_name(DEEP[1])
    newcomer = data.operators[OTHERS[0]]
    assert data._slot_takable(bed, True, newcomer.name)
    newcomer.resting_priority = "low"
    assert data._slot_takable(bed, True, newcomer.name) is data.experimental_dorm_logic


@pytest.mark.parametrize(
    "protection", ["rescue", "unknown", "exhaust", "full", "promoted"]
)
def test_standby_recovery_protection_prevents_preemption(solver, protection):
    data = solver.op_data
    standby = data.operators[DEEP[1]]
    if protection == "rescue":
        standby.mood = data.rescue_mood_threshold(standby) - 1
    elif protection == "unknown":
        standby.time_stamp = None
    elif protection == "exhaust":
        standby.exhaust_require = True
    elif protection == "full":
        standby.rest_in_full = True
    else:
        standby.standby_low_priority = True
    _, bed = data.get_dorm_by_name(standby.name)
    assert not data._slot_takable(bed, True, OTHERS[0])
    assert data.active_high_resting_count() == 2


def test_only_legacy_yieldable_standby_is_excluded_from_resting_capacity(solver):
    assert solver.op_data.active_high_resting_count() == (
        2 if solver.op_data.experimental_dorm_logic else 1
    )


@pytest.mark.parametrize("metadata", ["", "missing", "stale"])
def test_missing_release_identity_is_recovered_only_for_legacy_empty_metadata(
    release_solver, metadata
):
    solver = release_solver
    data = solver.op_data
    occupant = data.operators["絮雨"]
    room, index = occupant.current_room, occupant.current_index
    plan = {room: ["Current"] * len(data.plan[room])}
    plan[room][index] = "Free"
    named = data.plan["central"][0].agent if metadata == "stale" else metadata
    task = SchedulerTask(
        task_plan=plan.copy(), task_type=TaskTypes.RELEASE_DORM, meta_data=named
    )
    solver.task, solver.tasks = task, [task]
    solver.agent_arrange = MagicMock()
    solver.infra_main()
    permitted = not data.experimental_dorm_logic and metadata == ""
    solver.agent_arrange.assert_called_once_with(plan if permitted else {}, permitted)
    if permitted:
        assert task.meta_data == occupant.name
