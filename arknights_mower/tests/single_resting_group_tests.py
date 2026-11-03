"""工作换位之外的唯一正常下班组使用共享主班心情。"""

from datetime import datetime, timedelta

import pytest

from arknights_mower.tests.multi_group_shift_tests import (
    SHARED,
    A,
    apply,
)
from arknights_mower.tests.multi_group_shift_tests import (
    solver as solver,
)
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.scheduler_task import plan_metadata, try_reorder


@pytest.fixture
def single(solver):
    s = solver
    plan = s.global_plan["default_plan"].plan
    plan["meeting"][0].replacement = [SHARED]
    plan["meeting"][1].group = ""
    assert s.initialize_operators() is None
    Operators.current_room_changed_callback = None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    s.total_agent = list(s.op_data.operators.values())
    return s


def test_unique_named_rest_group_validates_and_owns_mood(single):
    data = single.op_data
    op = data.operators[SHARED]
    op.mood = 7
    assert op.multi_group
    assert op.group == "乙"
    assert data.groups["乙"] == [SHARED]
    assert data.group_min_mood("乙") == data.group_max_mood("乙") == 7
    assert data.group_min_mood("甲") == 24
    data.select_group_binding(SHARED, "甲")
    assert op.group == "乙"
    assert data.group_min_mood("乙") == 7
    assert data.init_and_validate(update=True) is None
    assert data.operators[SHARED].group == "乙"


def test_unique_rest_group_drives_ordinary_departure_and_return(single):
    s = single
    s.op_data.operators[SHARED].mood = 0
    plan = s.resting()
    assert plan["contact"] == ["黑角"]
    assert s.op_data.arrangement_group_transitions(plan) == {"乙": True}
    beds = try_reorder(s.op_data, plan)
    apply(s, plan)
    apply(s, beds)
    data = s.op_data
    bed = data.get_dorm_by_name(SHARED)[1]
    assert bed is not None
    bed.time = datetime.now() + timedelta(hours=2)
    tasks = plan_metadata(data, [])
    returning = next(task for task in tasks if task.plan.get("contact") == [SHARED])
    assert data.arrangement_group_transitions(returning.plan) == {"乙": False}
    apply(s, returning.plan)
    assert not s.op_data.group_is_resting("乙")
    assert s.op_data.operators[SHARED].current_room == "contact"


@pytest.mark.parametrize("same_cover", [False, True])
def test_working_swap_does_not_start_normal_rest_group(single, same_cover):
    s = single
    if same_cover:
        s.op_data.operators[SHARED].group_bindings[0]["replacement"] = ["黑角"]
    s.op_data.operators[A].mood = 0
    plan = s.resting()
    assert plan["meeting"][0] == SHARED
    assert plan["contact"] == (["黑角"] if same_cover else ["红"])
    assert s.op_data.arrangement_group_transitions(plan) == {"甲": True}
    apply(s, plan)
    assert not s.op_data.group_is_resting("乙")
    assert s.op_data.operators[SHARED].current_room == "meeting"
    assert s.op_data.get_dorm_by_name(SHARED)[1] is None
    returned = {"meeting": [A, "Current"], "contact": [SHARED]}
    assert s.op_data.arrangement_group_transitions(returned) == {"甲": False}


def test_empty_binding_counts_as_an_additional_normal_rest_group(single):
    s = single
    slot = s.global_plan["default_plan"].plan["contact"][0]
    slot.group_bindings.append({"group": "", "replacement": ["砾"]})
    assert "乙 缺少决定上下班" in s.initialize_operators()


def test_empty_binding_can_be_the_only_normal_rest_group(single):
    s = single
    slot = s.global_plan["default_plan"].plan["contact"][0]
    slot.group_bindings[0]["group"] = ""
    assert s.initialize_operators() is None
    data = s.op_data
    assert data.operators[SHARED].group == ""
    assert not data.is_group_shift_anchor(data.operators[SHARED])
    for op in data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    s.total_agent = list(data.operators.values())
    data.operators[SHARED].mood = 0
    plan = s.resting()
    assert plan["contact"] == ["黑角"]
    assert data.arrangement_group_transitions(plan) == {}


def test_multiple_normal_rest_groups_remain_followers(solver):
    data = solver.op_data
    assert not data.is_group_shift_anchor(data.operators[SHARED])
    data.operators[SHARED].mood = 0
    assert data.group_min_mood("甲") == data.group_min_mood("乙") == 24


def test_no_normal_rest_binding_is_rejected(single):
    s = single
    plan = s.global_plan["default_plan"].plan
    plan["meeting"][1].group = "乙"
    plan["meeting"][1].replacement = [SHARED]
    assert "正常下班组" in s.initialize_operators()


@pytest.mark.parametrize("action", ["off", "on"])
def test_backup_can_request_the_unique_normal_rest_group(single, action):
    from arknights_mower.utils.backup_group_tasks import (
        sync_group_tasks,
        validate_group_tasks,
    )
    from arknights_mower.utils.plan import Plan, PlanConfig
    from arknights_mower.utils.scheduler_task import TaskTypes

    s = single
    data = s.op_data
    data.backup_plans = [
        Plan(
            {},
            PlanConfig("", "", ""),
            group_tasks=[{"group": "乙", "action": action, "mode": "once"}],
        )
    ]
    data.plan_condition = [True]
    if action == "on":
        data.commit_group_shifts({"乙": True})
    validate_group_tasks(data)
    sync_group_tasks(s)
    (task,) = s.tasks
    if action == "off":
        assert task.type == TaskTypes.EXHAUST_OFF
        assert task.meta_data == SHARED
    else:
        assert task.type == TaskTypes.SHIFT_ON
        assert task.plan == {"contact": [SHARED]}


def test_unique_normal_group_keeps_exhaustion_full_recovery_and_threshold(single):
    s = single
    conf = s.global_plan["default_plan"].config
    conf.exhaust_require = conf.rest_in_full = [SHARED]
    conf.group_resting_thresholds = {"甲": 0.2, "乙": 0.8}
    assert s.initialize_operators() is None
    data = s.op_data
    assert SHARED in data.exhaust_agent
    assert data.exhaust_group == data.rest_in_full_group == {"乙"}
    assert data.resting_mood_threshold(data.operators[SHARED]) == 19


@pytest.mark.parametrize("same_cover", [False, True])
def test_expanded_swap_members_do_not_request_their_normal_rest_group(
    single, same_cover
):
    s = single
    if same_cover:
        s.op_data.operators[SHARED].group_bindings[0]["replacement"] = ["黑角"]
    plan = {}
    assert s.get_resting_plan([A, SHARED], [], plan, 0)
    assert plan["meeting"][0] == SHARED
    assert s.op_data.arrangement_group_transitions(plan) == {"甲": True}


def test_huaihu_and_dionysus_keep_their_distinct_normal_resting_groups(single):
    from arknights_mower.utils.plan import Room

    s = single
    plan = s.global_plan["default_plan"].plan
    plan["meeting"] = [Room("苍苔", "感知", ["槐琥"]), Room("清流", "自动化", ["槐琥"])]
    plan["contact"] = [
        Room(
            "槐琥",
            "红松",
            ["灰毫"],
            group_bindings=[
                {"group": "感知", "replacement": ["灰毫"]},
                {"group": "自动化", "replacement": ["食铁兽"]},
            ],
        )
    ]
    plan["room_1_1"] = [
        Room(
            "酒神",
            "红松",
            ["远牙"],
            group_bindings=[{"group": "感知", "replacement": ["远牙"]}],
        )
    ]
    assert s.initialize_operators() is None
    data = s.op_data
    assert all(
        data.operators[name].multi_group for name in data.shift_group_members("红松")
    )
    assert data.operators["槐琥"].shift_group == "红松"
    assert data.operators["酒神"].shift_group is None
    data.operators["槐琥"].mood = 9
    data.operators["酒神"].mood = 0
    assert data.group_min_mood("红松") == data.group_max_mood("红松") == 9
    assert not data.is_group_shift_anchor(data.operators["酒神"])


def test_working_swap_waits_for_real_capacity_without_opening_other_group_beds(single):
    from arknights_mower.tests.multi_group_shift_tests import B
    from arknights_mower.utils.plan import Room

    s = single
    s.global_plan["default_plan"].plan["dormitory_1"] = [
        Room("塑心", "乙", ["Free"]),
        Room("冰酿", "", []),
        Room("杜林", "", []),
        Room("夜莺", "", []),
        Room("Free", "", []),
    ]
    assert s.initialize_operators() is None
    Operators.current_room_changed_callback = None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 10, datetime.now()
    apply(
        s,
        {
            "meeting": ["Current", "初雪"],
            "dormitory_1": ["Current", "Current", "Current", "Current", B],
        },
    )
    for _ in range(2):
        plan = {}
        assert not s.get_resting_plan([A], [], plan, 1)
        assert plan == {}
        assert s.op_data.operators["塑心"].current_room == "dormitory_1"
        assert not s.op_data.group_is_resting("乙")
    apply(
        s,
        {
            "meeting": ["Current", B],
            "dormitory_1": ["Current", "Current", "Current", "Current", "Free"],
        },
    )
    plan = {}
    assert s.get_resting_plan([A], [], plan, 0)
    assert plan["meeting"][0] == SHARED
    assert s.op_data.arrangement_group_transitions(plan) == {"甲": True}
