"""空绑组提供个人轮休，具名绑组优先选择共享岗位替班。"""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests.multi_group_shift_tests import (
    SHARED,
    A,
    apply,
    shift_off,
)
from arknights_mower.tests.multi_group_shift_tests import (
    solver as solver,
)
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.resting_priority import RestingTier, resting_tier
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    generate_plan_by_drom,
    plan_metadata,
)


@pytest.fixture
def individual(solver):
    slot = solver.global_plan["default_plan"].plan["contact"][0]
    slot.group_bindings.append({"group": "", "replacement": ["砾"]})
    assert solver.initialize_operators() is None
    Operators.current_room_changed_callback = None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    solver.total_agent = list(solver.op_data.operators.values())
    return solver


def test_low_personal_mood_uses_empty_binding(individual):
    s = individual
    s.op_data.operators[SHARED].mood = 0
    plan = s.resting()
    assert plan["contact"] == ["砾"]
    assert "meeting" not in plan
    assert any(bed.name == SHARED for bed in s.op_data.dorm)
    assert not s.op_data.group_is_resting("甲")


def test_group_departure_preserves_existing_personal_rest(individual):
    s = individual
    apply(
        s,
        {
            "contact": ["砾"],
            "dormitory_1": ["Current", "Current", SHARED, "Current", "Current"],
        },
    )
    bed = s.op_data.get_dorm_by_name(SHARED)[1]
    bed.time = datetime.now() + timedelta(hours=4)
    before = deepcopy(bed)
    plan = {}
    assert s.get_resting_plan([A], [], plan, 1)
    after = s.op_data.get_dorm_by_name(SHARED)[1]
    assert (after.position, after.time) == (before.position, before.time)
    assert plan["contact"] == ["红"]
    assert not any(SHARED in names for names in plan.values())
    apply(s, plan)
    assert s.op_data.get_current_operator("contact", 0).name == "红"
    assert s.op_data.operators[SHARED].group == ""


def test_last_group_return_preserves_personal_rest(individual):
    s = individual
    assert shift_off(s, "甲")[0]
    data = s.op_data
    now = datetime.now()
    data.get_dorm_by_name(A)[1].time = now + timedelta(hours=1)
    data.get_dorm_by_name(SHARED)[1].time = now + timedelta(hours=4)
    tasks = generate_plan_by_drom(
        {now + timedelta(hours=1): ([data.get_dorm_by_name(A)[1]], False)}, data
    )
    assert tasks[0].plan["meeting"][0] == A
    assert tasks[0].plan["contact"] == ["砾"]
    apply(s, tasks[0].plan)
    assert s.op_data.operators[SHARED].is_resting()
    assert not s.op_data.group_is_resting("甲")
    # 同宿舍成员离开后，使用重新观测的恢复时间生成个人回班。
    s.op_data.get_dorm_by_name(SHARED)[1].time = now + timedelta(hours=4)
    tasks = plan_metadata(s.op_data, [])
    assert any(task.plan.get("contact") == [SHARED] for task in tasks)


def test_personal_return_cannot_override_resting_group(individual):
    s = individual
    assert shift_off(s, "甲")[0]
    data = s.op_data
    bed = data.get_dorm_by_name(SHARED)[1]
    bed.time = datetime.now() + timedelta(hours=1)
    tasks = generate_plan_by_drom({bed.time: ([bed], False)}, data)
    assert all(task.plan.get("contact") != [SHARED] for task in tasks)
    assert data.group_is_resting("甲")


def test_duplicate_empty_binding_rejected(individual):
    slot = individual.global_plan["default_plan"].plan["contact"][0]
    slot.group_bindings.append({"group": "", "replacement": ["黑角"]})
    assert "重复" in Operators(individual.global_plan).init_and_validate()


def test_empty_first_column_and_reinitialization(individual):
    s = individual
    slot = s.global_plan["default_plan"].plan["contact"][0]
    slot.group, slot.replacement = "", ["砾"]
    slot.group_bindings[-1] = {"group": "甲", "replacement": ["红"]}
    assert s.initialize_operators() is None
    assert s.op_data.init_and_validate(update=True) is None
    assert s.op_data.operators[SHARED].group == ""
    assert s.op_data.operators[SHARED].replacement == ["砾"]


@pytest.mark.parametrize("group", ["甲", "乙"])
def test_correction_retains_named_group_cover_and_personal_bed(individual, group):
    s = individual
    assert shift_off(s, group)[0]
    data = s.op_data
    for bed in data.dorm:
        if bed.name:
            bed.time = datetime.now() + timedelta(hours=4)
            data.operators[bed.name].mood = 10
    assert s.agent_get_mood(read_rooms=False, return_plan=True) == {}


def test_personal_rest_does_not_intersect_named_binding_candidates(individual):
    s = individual
    shared = s.op_data.operators[SHARED]
    shared.mood = 0
    s.op_data.operators[A].mood = 1
    plan = s.resting()
    assert plan["contact"] == ["红"]
    assert plan["meeting"][0] == "陈"
    assert sum(bed.name == SHARED for bed in s.op_data.dorm) == 1


@pytest.mark.parametrize("reuse_personal_cover", [False, True])
def test_named_departure_reuses_same_round_personal_bed(
    individual, reuse_personal_cover
):
    s = individual
    if reuse_personal_cover:
        s.op_data.operators[A].replacement = ["砾"]
    s.op_data.operators[SHARED].mood = s.op_data.operators[A].mood = 0
    plan, replacements, admissions = {}, [], {}
    assert s.get_resting_plan(
        [SHARED], replacements, plan, 0, dorm_admissions=admissions
    )
    first_bed = next(bed.position for bed in s.op_data.dorm if bed.name == SHARED)
    assert plan["contact"] == ["砾"]
    assert s.get_resting_plan([A], replacements, plan, 1, dorm_admissions=admissions)
    assert plan["contact"] == ["红"]
    assert plan["meeting"][0] == ("砾" if reuse_personal_cover else "陈")
    assert sum(bed.name == SHARED for bed in s.op_data.dorm) == 1
    assert (
        next(bed.position for bed in s.op_data.dorm if bed.name == SHARED) == first_bed
    )
    assert admissions[first_bed] == SHARED


def test_standby_can_lose_bed_without_recalling_bound_group(individual):
    s = individual
    data = s.op_data
    data.config.resting_standby = [SHARED]
    shared = data.operators[SHARED]
    shared.resting_priority = "standby"
    shared.mood = 10
    data.operators["银灰"].mood = 10
    assert shift_off(s, "甲")[0]
    data = s.op_data
    bed = data.get_dorm_by_name(SHARED)[1]
    assert resting_tier(data, SHARED) == RestingTier.STANDBY
    assert data._slot_takable(bed, requester="银灰")
    plan = {bed.position[0]: ["Current"] * 5}
    plan[bed.position[0]][bed.position[1]] = "银灰"
    returns = [
        SchedulerTask(
            task_type=TaskTypes.SHIFT_ON, task_plan={"meeting": [A, "Current"]}
        )
    ]
    state = deepcopy(data.group_shift_state)
    assert set(plan) == {bed.position[0]}
    apply(s, plan)
    assert s.op_data.operators[SHARED].current_room == ""
    assert s.op_data.get_current_operator("contact", 0).name == "红"
    assert s.op_data.group_shift_state == state
    assert len(returns) == 1


@pytest.mark.parametrize("already_resting", [False, True])
def test_only_bed_goes_to_named_anchor_before_individual_standby(
    individual, already_resting
):
    s = individual
    data = s.op_data
    data.config.resting_standby = [SHARED]
    data.operators[SHARED].resting_priority = "standby"
    data.operators[SHARED].mood = data.operators[A].mood = 10
    data.dorm = data.dorm[:1]
    if already_resting:
        apply(
            s,
            {
                "contact": ["砾"],
                "dormitory_1": ["Current", "Current", SHARED, "Current", "Current"],
            },
        )
    admitted, plan = shift_off(s, "甲")
    assert admitted
    assert plan["contact"] == ["红"]
    assert s.op_data.get_dorm_by_name(A)[1] is not None
    assert s.op_data.get_dorm_by_name(SHARED)[1] is None
    assert s.op_data.operators[SHARED].current_room == ""
    assert s.op_data.group_is_resting("甲")


def test_prepared_group_return_keeps_personal_rest(individual):
    s = individual
    assert shift_off(s, "甲")[0]
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": [A, "Current"], "contact": [SHARED]},
    )
    s.tasks = [task]
    s._prepare_group_shift(task)
    assert task.plan["contact"] == ["砾"]
    assert not any(SHARED in row for row in task.plan.values())
    assert s.op_data.operators[SHARED].is_resting()


def test_named_primary_exchange_remains_eligible(individual):
    s = individual
    slot = s.global_plan["default_plan"].plan["contact"][0]
    slot.replacement = [A]
    s.global_plan["default_plan"].plan["meeting"][0].replacement = [SHARED]
    assert s.initialize_operators() is None
    Operators.current_room_changed_callback = None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5, datetime.now()
    admitted, plan = shift_off(s, "甲")
    assert admitted
    assert plan["meeting"][0] == SHARED
    assert plan["contact"] == [A]


def test_personal_exhaustion_recognizes_pending_rest(individual):
    s = individual
    s.global_plan["default_plan"].config.exhaust_require = [SHARED]
    assert s.initialize_operators() is None
    assert SHARED in s.op_data.exhaust_agent
    s.tasks = [
        SchedulerTask(
            task_type=TaskTypes.SHIFT_OFF,
            task_plan={
                "contact": ["砾"],
                "dormitory_1": ["Current", "Current", SHARED, "Current", "Current"],
            },
        )
    ]
    assert s._has_pending_exhausted_shift([SHARED])


def test_named_group_does_not_restart_personal_return_window(individual, monkeypatch):
    from arknights_mower.utils import scheduler_task

    s = individual
    now = datetime.now()

    class Clock(datetime):
        @classmethod
        def now(cls):
            return now

    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    apply(
        s,
        {
            "contact": ["砾"],
            "dormitory_1": ["Current", "Current", SHARED, "Current", "Current"],
        },
    )
    data = s.op_data
    data.operators[A].mood = 0
    data.get_dorm_by_name(SHARED)[1].time = now + timedelta(hours=4)
    first = plan_metadata(data, [])
    deadline = next(task.time for task in first if task.plan.get("contact") == [SHARED])
    now += timedelta(minutes=10)
    data.commit_group_shifts({"甲": True})
    blocked = plan_metadata(data, first)
    assert not any(task.plan.get("contact") == [SHARED] for task in blocked)
    now += timedelta(minutes=5)
    data.commit_group_shifts({"甲": False})
    resumed = plan_metadata(data, blocked)
    assert (
        next(task.time for task in resumed if task.plan.get("contact") == [SHARED])
        == deadline
    )


@pytest.mark.parametrize("group_resting", [False, True])
@pytest.mark.parametrize("personal_limit", [False, True])
def test_personal_cap_departure_returns_only_without_named_dependencies(
    individual, group_resting, personal_limit
):
    s = individual
    if personal_limit:
        s.op_data.config.operator_mood_limits[SHARED] = {"lower": 0, "upper": 24}
    shared = s.op_data.operators[SHARED]
    shared._current_room, shared.current_index = "", -1
    shared.mood = 24
    shared.rest_mood_release_limit = 24
    s.op_data.commit_group_shifts({"甲": group_resting})
    tasks = plan_metadata(s.op_data, [])
    assert any(task.plan.get("contact") == [SHARED] for task in tasks) is (
        not group_resting
    )


@pytest.mark.parametrize("empty_first", [False, True])
def test_rescue_validation_accepts_one_empty_column(individual, empty_first):
    from arknights_mower.utils.config.plan import PlanModel
    from arknights_mower.utils.emergency_plan import validate_rescue_schedule

    rows = {
        room: {
            "plans": [
                {
                    "agent": slot.agent,
                    "group": slot.group,
                    "replacement": slot.replacement,
                    "group_bindings": slot.group_bindings,
                }
                for slot in slots
            ]
        }
        for room, slots in individual.global_plan["default_plan"].plan.items()
    }
    shared = rows["contact"]["plans"][0]
    if empty_first:
        shared["group"], shared["replacement"] = "", ["砾"]
        shared["group_bindings"] = [{"group": "甲", "replacement": ["红"]}]
    schedule = PlanModel(plan1=rows)
    validate_rescue_schedule(individual.op_data, schedule)
    from arknights_mower.utils.config.plan import GroupBinding

    schedule.plan1.contact.plans[0].group_bindings.append(
        GroupBinding(group="", replacement=["黑角"])
    )
    with pytest.raises(ValueError, match="空绑组最多填写一次"):
        validate_rescue_schedule(individual.op_data, schedule)
