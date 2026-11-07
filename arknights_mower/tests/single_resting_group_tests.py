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
    assert s.get_resting_plan([A, SHARED], [], plan, 0, request_names=[A])
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


def test_mixed_zero_mood_group_preserves_unique_shared_primary_recovery(single):
    from arknights_mower.tests.multi_group_shift_tests import B
    from arknights_mower.utils.resting_correction import prefer_resting_replacements

    s = single
    primary = s.global_plan["default_plan"]
    primary.plan["meeting"][1].group = "乙"
    primary.config.workaholic = [B]
    assert s.initialize_operators() is None
    Operators.current_room_changed_callback = None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    apply(
        s,
        {
            "meeting": ["Current", "初雪"],
            "contact": ["黑角"],
            "dormitory_1": ["Current", "Current", SHARED, "Current", "Current"],
        },
    )
    data = s.op_data
    data.operators[SHARED].mood = 1
    bed = data.get_dorm_by_name(SHARED)[1]
    bed.time = datetime.now() + timedelta(hours=4)
    before = (bed.position, bed.time, data.group_shift_state.copy())
    fix = {"meeting": ["Current", B]}
    prefer_resting_replacements(data, fix, lambda _: False)
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan=fix)
    s._prepare_group_shift(task)
    assert SHARED not in {name for row in task.plan.values() for name in row}
    assert SHARED not in {name for row in fix.values() for name in row}
    assert s.agent_get_mood(read_rooms=False, return_plan=True) == {}
    assert not data.is_workaholic_group("乙")
    assert (bed.position, bed.time, data.group_shift_state) == before


def test_ordinary_recall_uses_only_the_requested_normal_group_mood(single):
    from arknights_mower.tests.multi_group_shift_tests import B
    from arknights_mower.utils import config
    from arknights_mower.utils.replacement_coordination import (
        ordinary_recall_mood_admissible,
    )

    data = single.op_data
    data.runtime_conf = config.Conf(rescue_threshold=0.75)
    data.config.resting_threshold = 0.65
    data.operators[A].mood = 15
    data.operators[SHARED].mood = 10
    assert data.shift_request_groups([A]) == ["甲"]
    assert not ordinary_recall_mood_admissible(
        data, {B}, [A, SHARED], request_names=[A]
    )
    data.operators[A].mood = 7
    assert ordinary_recall_mood_admissible(data, {B}, [A, SHARED], request_names=[A])


def test_unique_normal_departure_waits_for_working_cover_handoff(single):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    s = single
    first = {}
    assert s.get_resting_plan([A], [], first, 0)
    beds = try_reorder(s.op_data, first)
    apply(s, first)
    apply(s, beds)
    s.op_data.operators[SHARED].mood = 0
    original = SchedulerTask(
        time=datetime.now() - timedelta(minutes=5),
        task_type=TaskTypes.EXHAUST_OFF,
        meta_data=SHARED,
    )
    s.tasks, s.task = [original], original
    at = original.time
    for _ in range(2):
        plan = {}
        assert not s.get_resting_plan([SHARED], [], plan, 1)
        assert plan == {}
        assert s.tasks == [original] and original.time == at
        assert not s.op_data.group_is_resting("乙")
    apply(s, {"meeting": [A, "Current"], "contact": [SHARED]})
    plan = {}
    assert s.get_resting_plan([SHARED], [], plan, 0)
    assert plan["contact"] == ["黑角"]
    assert s.op_data.arrangement_group_transitions(plan) == {"乙": True}
    assert s.tasks == [original] and original.time == at


@pytest.mark.parametrize("role", ["ordinary", "low", "standby", "workaholic"])
@pytest.mark.parametrize("same_cover", [False, True])
def test_working_swap_request_ignores_covered_primary_recovery_role(
    single, role, same_cover
):
    s = single
    plans = s.global_plan["default_plan"].plan
    from arknights_mower.tests.multi_group_shift_tests import B
    from arknights_mower.utils.plan import Room
    from arknights_mower.utils.replacement_coordination import (
        ordinary_recall_mood_admissible,
        plan_replacement_handoff,
        replacements,
    )

    plans["meeting"][1].group = "甲"
    plans["room_1_1"] = [
        Room(
            "芬",
            "乙",
            ["香草"],
            group_bindings=[{"group": "丙", "replacement": ["翎羽"]}],
        )
    ]
    plans["recycle"] = [Room("清道夫", "丙", ["红豆"])]
    if role == "standby":
        s.global_plan["default_plan"].config.resting_standby = [A]
    elif role == "workaholic":
        s.global_plan["default_plan"].config.workaholic = [A]
    elif role == "low":
        s.global_plan["default_plan"].config.resting_priority = [A]
    if same_cover:
        plans["contact"][0].replacement = ["黑角"]
    assert s.initialize_operators() is None
    Operators.current_room_changed_callback = None
    s._refresh_deferred_product_reservations = lambda: None
    s.check_fia = lambda: (None, None)
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    s.total_agent = list(s.op_data.operators.values())
    s.op_data.operators[B].mood = 0
    data = s.op_data
    members = data.shift_group_members("甲")
    assert data.shift_request_groups([B]) == ["甲"]
    assert replacements(data, data.operators[SHARED], request_names=[B]) == (
        ["黑角"] if same_cover else ["红"]
    )
    assert (
        plan_replacement_handoff(data, members, lambda _: False, request_names=[B])
        == {}
    )
    data.operators[B].mood, data.operators[SHARED].mood = 24, 0
    assert not ordinary_recall_mood_admissible(data, set(), members, request_names=[B])
    data.operators[B].mood, data.operators[SHARED].mood = 0, 24
    plan = s.resting()
    assert plan["meeting"] == [SHARED, "初雪"]
    assert plan["contact"] == (["黑角"] if same_cover else ["红"])
    assert "room_1_1" not in plan and "recycle" not in plan
    assert not data.group_is_resting("甲") and not data.group_is_resting("乙")
    apply(s, plan)
    assert s.op_data.operators[SHARED].current_room == "meeting"
    assert s.op_data.operators["芬"].current_room == "room_1_1"
    assert s.op_data.group_is_resting("甲") and not s.op_data.group_is_resting("乙")


def test_nested_working_swaps_use_requested_binding_instead_of_effective_group(single):
    from arknights_mower.tests.multi_group_shift_tests import B
    from arknights_mower.utils.replacement_coordination import replacements

    s = single
    plans = s.global_plan["default_plan"].plan
    plans["meeting"][0].replacement = [B]
    plans["meeting"][1].group = "甲"
    plans["meeting"][1].replacement = [SHARED]
    plans["meeting"][1].group_bindings = [{"group": "丙", "replacement": ["初雪"]}]
    assert s.initialize_operators() is None
    Operators.current_room_changed_callback = None
    s._refresh_deferred_product_reservations = lambda: None
    s.check_fia = lambda: (None, None)
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    s.total_agent = list(s.op_data.operators.values())
    data = s.op_data
    data.operators[A].mood = 0
    assert data.operators[B].group == "丙"
    assert data.operators[SHARED].group == "乙"
    assert data.shift_request_groups([A]) == ["甲"]
    assert replacements(data, data.operators[SHARED], request_names=[A]) == ["红"]
    plan = s.resting()
    assert plan["meeting"] == [B, SHARED]
    assert plan["contact"] == ["红"]
    apply(s, plan)
    assert s.op_data.group_is_resting("甲")
    assert not s.op_data.group_is_resting("乙")
    assert not s.op_data.group_is_resting("丙")


def test_independent_source_survives_an_unrequested_intermediate_binding(single):
    from arknights_mower.tests.multi_group_shift_tests import B
    from arknights_mower.utils.plan import Room
    from arknights_mower.utils.replacement_coordination import plan_replacement_handoff
    from arknights_mower.utils.retained_recovery import completed_ordinary_rest_request
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    s = single
    plans = s.global_plan["default_plan"].plan
    plans["contact"][0].group_bindings = [{"group": "乙", "replacement": [B]}]
    plans["meeting"][1] = Room(
        B, "乙", ["初雪"], group_bindings=[{"group": "丙", "replacement": ["黑角"]}]
    )
    plans["room_1_1"] = [
        Room(
            "芬",
            "丙",
            ["香草"],
            group_bindings=[{"group": "丁", "replacement": ["翎羽"]}],
        )
    ]
    plans["recycle"] = [Room("清道夫", "丁", ["红豆"])]
    assert s.initialize_operators() is None
    Operators.current_room_changed_callback = None
    s._refresh_deferred_product_reservations = lambda: None
    s.check_fia = lambda: (None, None)
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    data = s.op_data
    sources = [A, B]
    members = [*data.shift_group_members("甲"), B]
    assert data.operators[SHARED].group == "乙"
    assert data.operators[B].group == "丙"
    assert data.shift_request_groups(sources) == ["甲", "丙"]
    assert (
        plan_replacement_handoff(
            data, members + ["芬"], lambda _: False, request_names=sources
        )
        == {}
    )

    plan = s._coordination_admission_plan(data, members, request_names=sources)
    assert plan is not None
    assert plan["meeting"] == [SHARED, "黑角"]
    assert plan["contact"] == ["红"]
    assert plan["room_1_1"] == ["香草"]
    assert "recycle" not in plan
    assert not data.group_is_resting("甲") and not data.group_is_resting("丙")

    apply(s, plan)
    assert s.op_data.group_is_resting("甲") and s.op_data.group_is_resting("丙")
    assert not s.op_data.group_is_resting("乙") and not s.op_data.group_is_resting("丁")
    assert s.op_data.operators[SHARED].current_room == "meeting"
    assert s.op_data.operators["芬"].is_resting()
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    task.ordinary_coordination = True
    task.coordination_request_names = sources
    task.execution_failure = {"reason": "等待床位"}
    assert completed_ordinary_rest_request(s.op_data, task)


def test_individual_request_remains_required_alongside_a_named_group(single):
    from arknights_mower.tests.multi_group_shift_tests import B
    from arknights_mower.utils import config
    from arknights_mower.utils.replacement_coordination import (
        ordinary_recall_mood_admissible,
    )
    from arknights_mower.utils.retained_recovery import completed_ordinary_rest_request
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    s = single
    plans = s.global_plan["default_plan"].plan
    plans["contact"][0].group_bindings = [{"group": "", "replacement": ["黑角"]}]
    assert s.initialize_operators() is None
    Operators.current_room_changed_callback = None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    data = s.op_data
    data.runtime_conf = config.Conf(rescue_threshold=0.75)
    data.operators[SHARED].mood = 0
    sources = [SHARED, B]
    assert data.operators[SHARED].independent_rest
    assert ordinary_recall_mood_admissible(data, set(), sources, request_names=sources)

    apply(
        s, {"meeting": [A, "初雪"], "dormitory_1": ["塑心", "冰酿", B, "Free", "Free"]}
    )
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    task.ordinary_coordination = True
    task.coordination_request_names = sources
    task.execution_failure = {"reason": "等待床位"}
    assert not completed_ordinary_rest_request(s.op_data, task)
    assert not s._has_pending_exhausted_shift(sources, request_names=sources)
    apply(s, {"contact": ["黑角"], "dormitory_1": ["塑心", "冰酿", B, SHARED, "Free"]})
    assert completed_ordinary_rest_request(s.op_data, task)


def test_nested_support_rebuild_preserves_original_requester(single):
    from arknights_mower.tests.multi_group_shift_tests import B
    from arknights_mower.utils.plan import Room

    s = single
    plans = s.global_plan["default_plan"].plan
    plans["meeting"][0].replacement = [B]
    plans["meeting"][1] = Room(
        B, "甲", [SHARED], group_bindings=[{"group": "丙", "replacement": ["初雪"]}]
    )
    plans["recycle"] = [Room("清道夫", "", ["红", "香草"])]
    assert s.initialize_operators() is None
    Operators.current_room_changed_callback = None
    s._refresh_deferred_product_reservations = lambda: None
    s.check_fia = lambda: (None, None)
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    apply(
        s,
        {
            "recycle": ["红"],
            "dormitory_1": ["塑心", "冰酿", "清道夫", "Free", "Free"],
        },
    )
    s.op_data.operators[A].mood = 0
    s.op_data.operators["清道夫"].mood = 12
    s.task = None
    s._schedule_group_coordination([A])
    (support,) = s.tasks
    assert support.plan == {"recycle": ["香草"]}
    assert support.coordination_request_names == [A]
    original_time = support.time
    s.task = support
    for _ in range(2):
        s._refresh_coordination_support(support)
        assert support.plan == {"recycle": ["香草"]}
        assert support.coordination_request_names == [A]
        assert support.time == original_time
        assert s._coordination_support_valid(support.plan, [A])
    apply(s, support.plan)
    s.tasks = []
    s.task = None
    admission = s._coordination_admission_plan(s.op_data, [A])
    assert admission is not None
    assert admission["meeting"] == [B, SHARED]
    assert admission["contact"] == ["红"]
    apply(s, admission)
    assert s.op_data.group_is_resting("甲")
    assert not s.op_data.group_is_resting("乙") and not s.op_data.group_is_resting("丙")
