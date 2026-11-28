"""宿舍保留允许换床和工作，达到恢复上限仍不得自动安排为空闲。"""

import copy
from datetime import datetime, timedelta

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests import (
    ling_xi_rest_limit_tests,
    native_replacement_coordination_tests,
)
from arknights_mower.utils import config
from arknights_mower.utils.operators import Dormitory, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.replacement_coordination import plan_replacement_handoff
from arknights_mower.utils.resting_correction import suppress_completed_dorm_returns
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    plan_mood_limit_releases,
    prioritize_new_dorm_recovery,
    try_reorder,
)

R1, R2 = "dormitory_1", "dormitory_2"
NOW = ling_xi_rest_limit_tests.NOW
ling_solver = ling_xi_rest_limit_tests.solver
coordination_solver = native_replacement_coordination_tests.solver


@pytest.fixture(params=[False, True], ids=["observed", "calculated"])
def data(request, monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=False))
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    result = Operators(
        {
            "default_plan": Plan(
                {
                    "central": [Room("歌蕾蒂娅", "", ["夕"])],
                    "room_1_2": [Room("乌尔比安", "", ["槐琥"])],
                    "recycle": [Room("岳羽由加莉", "", ["协律"])],
                    R1: [
                        Room(n, "", [])
                        for n in ["杜林", "闪灵", "爱丽丝", "桃金娘", "Free"]
                    ],
                    R2: [
                        Room(n, "", [])
                        for n in ["流明", "蜜莓", "Free", "Free", "Free"]
                    ],
                },
                PlanConfig(
                    "",
                    "",
                    "",
                    ling_xi=3,
                    free_room=True,
                    free_room_exclusions="乌尔比安",
                    ope_resting_priority="歌蕾蒂娅",
                ),
            ),
            "backup_plans": [],
        }
    )
    assert result.init_and_validate() is None
    now = datetime.now()
    for op in result.operators.values():
        op.mood, op.time_stamp, op.depletion_rate = 10, now, 0
        op._current_room, op.current_index = op.room, op.index
    for name, mood, room, index in [
        ("岳羽由加莉", 10, R1, 4),
        ("乌尔比安", 12, R2, 3),
        ("歌蕾蒂娅", 23.9, "central", 0),
        ("协律", 5, R2, 4),
    ]:
        op = result.operators[name]
        op.mood, op._current_room, op.current_index = mood, room, index
    result.dorm = [
        Dormitory((R1, 4), "岳羽由加莉"),
        Dormitory((R2, 2)),
        Dormitory((R2, 3), "乌尔比安"),
        Dormitory((R2, 4), "协律"),
    ]
    for bed in result.dorm:
        bed.time = now + timedelta(hours=2)
    if request.param:
        monkeypatch.setattr(
            Operators, "mood_calculation_enabled", property(lambda self: True)
        )
        monkeypatch.setattr(
            Operators,
            "calculated_mood",
            lambda self, name, now=None: self.operators[name].mood,
        )
        monkeypatch.setattr(
            Operators,
            "calculated_mood_deadline",
            lambda self, name, target, now=None: (
                (now or datetime.now()) + timedelta(hours=2)
            ),
        )
    return result


def projection(data, plan):
    return data.project_arrangements([plan])


def test_priority_arrival_moves_to_first_dorm_with_retained_roommate(data):
    before = [(bed.position, bed.name, bed.time) for bed in data.dorm]
    data.dorm[1].name = "歌蕾蒂娅"
    result = try_reorder(data, {})
    after = projection(data, result)
    assert after.operators["歌蕾蒂娅"].current_room == R1
    assert after.operators["乌尔比安"].current_room.startswith("dorm")
    assert after.operators["岳羽由加莉"].current_room.startswith("dorm")
    assert {b.name for b in after.dorm} == {
        "歌蕾蒂娅",
        "乌尔比安",
        "岳羽由加莉",
        "协律",
    }
    assert [(b.position, b.time) for b in data.dorm] == [(p, t) for p, _, t in before]


def test_retained_single_target_can_change_rooms(data):
    (
        data.operators["乌尔比安"]._current_room,
        data.operators["乌尔比安"].current_index,
    ) = R1, 4
    (
        data.operators["岳羽由加莉"]._current_room,
        data.operators["岳羽由加莉"].current_index,
    ) = R2, 3
    data.dorm[0].name, data.dorm[2].name = "乌尔比安", "岳羽由加莉"
    result = prioritize_new_dorm_recovery(
        data, {R2: ["Current", "Current", "歌蕾蒂娅", "Current", "Current"]}
    )
    after = projection(data, result)
    assert after.operators["歌蕾蒂娅"].current_room == R1
    assert after.operators["乌尔比安"].current_room == R2


def test_full_retained_operator_keeps_configured_priority(data):
    data.config.ope_resting_priority = ["乌尔比安"]
    data.operators["乌尔比安"].mood = 24
    data.config.operator_mood_limits = {"乌尔比安": {"upper": 24}}
    assert data.rest_mood_complete("乌尔比安")
    result = prioritize_new_dorm_recovery(
        data, {R2: ["Current", "Current", "歌蕾蒂娅", "Current", "Current"]}
    )
    assert projection(data, result).get_current_operator(R1, 4).name == "乌尔比安"


@pytest.mark.parametrize("guard", ["slot", "name", "product"])
def test_real_reservations_still_protect_retained_resident(data, guard):
    slots, names = set(), set()
    if guard == "slot":
        slots.add((R2, 3))
    elif guard == "name":
        names.add("乌尔比安")
    else:
        data.reserved_product_beds[(R2, 3)] = "乌尔比安"
    result = prioritize_new_dorm_recovery(
        data,
        {R2: ["Current", "Current", "歌蕾蒂娅", "Current", "Current"]},
        slots,
        reserved_names=names,
    )
    assert projection(data, result).get_current_operator(R2, 3).name == "乌尔比安"


def test_completed_retained_resident_has_no_limit_release_and_can_work(data):
    data.config.operator_mood_limits = {"乌尔比安": {"upper": 12}}
    data.operators["乌尔比安"].upper_limit = 12
    assert data.rest_mood_complete("乌尔比安")
    assert plan_mood_limit_releases(data) == []
    plan = {R2: ["Current", "Current", "乌尔比安", "Free", "Current"]}
    suppress_completed_dorm_returns(data, plan)
    assert plan[R2][2] == "乌尔比安"
    after = projection(data, plan)
    assert after.operators["乌尔比安"].current_index == 2
    returned = projection(after, {"room_1_2": ["乌尔比安"]})
    assert returned.operators["乌尔比安"].current_room == "room_1_2"
    assert returned.operators["乌尔比安"].upper_limit == 12


def test_merged_retained_release_cancels_only_its_member(data):
    for name in ["乌尔比安", "协律"]:
        data.config.operator_mood_limits[name] = {"upper": 12}
        data.operators[name].mood = data.operators[name].upper_limit = 12
    task = SchedulerTask(
        time=datetime.now(),
        task_plan={R2: ["Current", "Current", "Current", "Free", "Free"]},
        task_type=TaskTypes.RELEASE_DORM,
        meta_data="乌尔比安,协律",
        strict_mood_limit=True,
        mood_limit=12,
    )
    task.release_targets = {"乌尔比安": (R2, 3), "协律": (R2, 4)}
    task.execution_retained = True
    when = task.time
    execution = copy.deepcopy(task)
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data, solver.tasks = data, [execution]
    assert solver.prepare_release_dorm(execution)
    assert execution.time == when
    assert execution.release_dorm_targets() == {"协律": (R2, 4)}
    assert execution.plan[R2][3] == "Current"
    result = plan_mood_limit_releases(data, previous_tasks=[task])
    assert result == [task]
    assert task.time == when
    assert task.release_dorm_targets() == {"协律": (R2, 4)}
    assert task.plan[R2][3] == "Current"
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data, solver.tasks = data, [task]
    assert solver.prepare_release_dorm(task)
    assert task.time == when and task.release_dorm_targets() == {"协律": (R2, 4)}


def test_retained_ling_xi_cap_remains_complete_and_returns_with_group(ling_solver):
    solver = ling_solver
    data, name = solver.op_data, ling_xi_rest_limit_tests.limited_name(solver)
    data.config.free_room_exclusions = [name]
    op = data.operators[name]
    op.mood = 12
    assert data.rest_mood_complete(name)
    for _ in range(3):
        solver.plan_metadata()
        assert not any(t.type == TaskTypes.RELEASE_DORM for t in solver.tasks)
        assert op.is_resting()
        assert len([t for t in solver.tasks if t.type == TaskTypes.SHIFT_ON]) == 1
    solver.task = SchedulerTask()
    agents = ["冰酿", "闪灵", "絮雨", name, "Free"]
    solver.prepare_dorm_selection(agents, R1, preserve_dorm_occupants=True)
    assert agents[3] == name
    # 同组恢复完成后，真实元数据规划仍生成原岗位回班。
    data.operators["絮雨"].mood = 24
    for bed in data.dorm:
        if bed.name:
            bed.time = NOW
    solver.plan_metadata()
    returning = next(t for t in solver.tasks if t.type == TaskTypes.SHIFT_ON)
    assert returning.plan["central"] == [name]
    assert returning.plan["contact"] == ["絮雨"]
    assert returning.time <= NOW
    solver.op_data = data.project_arrangements([returning.plan])
    solver.tasks, solver.task = [], None
    solver.plan_metadata()
    assert solver.op_data.operators[name].current_room == "central"
    assert solver.tasks == []


def test_departure_recovery_rejects_no_bed_for_completed_retained_primary(data):
    op = data.operators["乌尔比安"]
    op._current_room, op.current_index = op.room, op.index
    op.mood = op.upper_limit = 12
    data.config.operator_mood_limits[op.name] = {"upper": 12}
    for bed in data.dorm:
        if bed.name == op.name:
            bed.name = ""
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data, solver.tasks = data, []
    plan = {op.room: ["槐琥"]}
    original = copy.deepcopy(plan)
    assert not solver._complete_departed_recovery(
        plan, [op.name], reserved_slots={bed.position for bed in data.dorm}
    )
    assert plan == original
    assert op.current_room == op.room


def test_retained_dorm_resident_can_take_legal_coordination_work(coordination_solver):
    data = coordination_solver.op_data
    data = data.project_arrangements(
        [{"dormitory_1": ["Current", "Current", "Current", "Current", "引星棘刺"]}]
    )
    data.config.free_room_exclusions = ["引星棘刺"]
    assert data.operators["引星棘刺"].is_resting()
    support = plan_replacement_handoff(data, ["机械师"], lambda _: False)
    assert support == {"room_2_2": ["引星棘刺"]}
    assert (
        data.project_arrangements([support]).operators["引星棘刺"].current_room
        == "room_2_2"
    )


def test_full_retained_required_or_standby_cannot_use_no_bed_fallback(data):
    op = data.operators["乌尔比安"]
    op.mood = op.upper_limit = 12
    data.config.operator_mood_limits[op.name] = {"upper": 12}
    data.config.resting_standby = [op.name]
    before = copy.deepcopy(data.dorm)
    assert (
        data.assign_dorm_group(
            [op.name], reserved_slots={bed.position for bed in data.dorm}
        )
        is None
    )
    assert [(b.position, b.name) for b in data.dorm] == [
        (b.position, b.name) for b in before
    ]
    assert op.current_room == R2
