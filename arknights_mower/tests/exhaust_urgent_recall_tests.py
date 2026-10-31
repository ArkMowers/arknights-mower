"""用尽急救允许整组让出替班，普通回班保护仍独立生效。"""

from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.exhaust_replacement_tests import solver as solver
from arknights_mower.utils.scheduler_task import TaskTypes


@pytest.mark.parametrize("ordinary", [False, True])
def test_exhausted_worker_recalls_cover_owner_without_ordinary_wait(solver, ordinary):
    data = solver.op_data
    data.operators["苍苔"].replacement = ["槐琥"]
    data.plan["room_2_2"][0].replacement = ["槐琥"]
    data.group_recovery_full_members = {"感知": ["苍苔", "絮雨"]}
    solver.task.ordinary_coordination = ordinary
    solver.check_fia = MagicMock(return_value=([], None))
    solver.skip = MagicMock()
    original = solver.task
    solver.overtake_room()
    support = [task for task in solver.tasks if getattr(task, "exhaust_support", False)]
    if ordinary:
        assert support == []
    else:
        assert len(support) == 1
        assert support[0].plan == {"room_2_2": ["苍苔"], "contact": ["絮雨"]}
        assert original in solver.tasks
        assert original.execution_failure
        assert original.type == TaskTypes.EXHAUST_OFF
        solver.task = support[0]
        assert solver._coordination_support_valid(support[0].plan, ["机械师"])
    assert data.operators["苍苔"].is_resting()
    assert data.operators["槐琥"].current_room == "room_2_2"


def test_exhausted_worker_still_respects_explicit_full_recovery(solver):
    data = solver.op_data
    data.operators["苍苔"].replacement = ["槐琥"]
    data.plan["room_2_2"][0].replacement = ["槐琥"]
    data.operators["絮雨"].rest_in_full = True
    solver.check_fia = MagicMock(return_value=([], None))
    assert solver._plan_exhaust_support(["机械师"], urgent=True) is None


def test_failed_support_is_reused_without_rebuilding_request(solver):
    solver.check_fia = MagicMock(return_value=([], None))
    solver.skip = MagicMock()
    original = solver.task
    solver.overtake_room()
    support = next(
        task for task in solver.tasks if getattr(task, "exhaust_support", False)
    )
    solver._retain_failed_task(support, "副表改变交接条件", list(support.plan))
    original_time, support_time = original.time, support.time
    for _ in range(5):
        solver.task = original
        solver.overtake_room()
    assert [
        task for task in solver.tasks if getattr(task, "exhaust_support", False)
    ] == [support]
    assert support.execution_failure
    assert original in solver.tasks
    assert (original.time, support.time) == (original_time, support_time)


def test_support_rechecks_replacements_in_final_backup_without_mutating_actual(solver):
    from arknights_mower.utils.plan import Plan, PlanConfig, Room
    from arknights_mower.utils.scheduler_task import SchedulerTask

    solver.task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    solver.task.exhaust_support = True
    plan = {"room_2_2": ["引星棘刺"]}
    assert solver._coordination_support_valid(plan, ["机械师"])
    solver.op_data.backup_plans = [
        Plan({"room_3_3": [Room("机械师", "", [])]}, PlanConfig("", "", ""))
    ]
    solver.op_data.global_plan["backup_plans"] = solver.op_data.backup_plans
    solver.op_data.plan_condition = [False]
    solver.task.backup_shift_conditions = [True]
    assert not solver._coordination_support_valid(plan, ["机械师"])
    assert solver.op_data.plan_condition == [False]
    assert solver.op_data.operators["机械师"].replacement == ["槐琥"]
    assert solver.op_data.operators["槐琥"].current_room == "room_2_2"


def shared_recall_solver(solver, *, third_group=False, empty_binding=False):
    from datetime import datetime, timedelta

    from arknights_mower.utils.plan import Room

    plan = solver.global_plan["default_plan"].plan
    plan["room_3_3"][0].group = "深海"
    plan["room_2_2"][0].replacement = ["槐琥"]
    plan["dormitory_1"][1] = Room(
        "撷英调香师",
        "感知",
        ["桃金娘"],
        group_bindings=[
            {"group": "深海", "replacement": ["桃金娘"]},
            *([{"group": "其他", "replacement": ["桃金娘"]}] if third_group else []),
            *([{"group": "", "replacement": ["桃金娘"]}] if empty_binding else []),
        ],
    )
    if third_group:
        plan["meeting"][0].group = "其他"
    assert solver.initialize_operators() is None
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "room_3_3": ["机械师"],
                "room_2_2": ["槐琥"],
                "contact": ["斥罪"],
                "meeting": ["陈" if third_group else "能天使"],
                "dormitory_1": [
                    "冰酿",
                    "桃金娘",
                    "苍苔",
                    "絮雨",
                    "能天使" if third_group else "Free",
                ],
            }
        ]
    )
    now = datetime.now()
    for op in solver.op_data.operators.values():
        op.mood, op.time_stamp = 12, now
    solver.op_data.operators["机械师"].mood = 0
    for bed in solver.op_data.dorm:
        if bed.name:
            bed.time = now + timedelta(hours=4)
    solver.check_fia = MagicMock(return_value=([], None))
    solver.skip = MagicMock()
    return solver


@pytest.mark.parametrize("selected_group", ["感知", "其他"])
def test_urgent_recall_preserves_shared_cover_for_other_resting_group(
    solver, selected_group
):
    s = shared_recall_solver(solver, third_group=True)
    data = s.op_data
    data.select_group_binding("撷英调香师", selected_group)
    original, original_time = s.task, s.task.time
    s.overtake_room()
    support = next(task for task in s.tasks if getattr(task, "exhaust_support", False))
    assert support.plan == {"room_2_2": ["苍苔"], "contact": ["絮雨"]}
    projected = data.project_arrangements([support.plan])
    assert projected.group_is_resting("其他")
    assert projected.get_current_operator("dormitory_1", 1).name == "桃金娘"
    assert projected.operators["能天使"].is_resting()
    assert data.group_is_resting("感知")
    assert data.get_current_operator("room_2_2", 0).name == "槐琥"
    assert original in s.tasks and original.time == original_time
    s.task = support
    assert s._coordination_support_valid(support.plan, ["机械师"])


@pytest.mark.parametrize("third_group", [False, True])
def test_urgent_recall_shared_follower_overlap_does_not_block_fixed_workers(
    solver, third_group
):
    s = shared_recall_solver(solver, third_group=third_group)
    support = s._plan_exhaust_support(["机械师", "撷英调香师"], urgent=True)
    assert support is not None
    assert support["room_2_2"] == ["苍苔"]
    assert support["contact"] == ["絮雨"]
    if third_group:
        assert "dormitory_1" not in support
    else:
        assert support["dormitory_1"][1] == "撷英调香师"
    assert s.op_data.group_is_resting("感知")
    assert not s.op_data.group_is_resting("深海")


def test_urgent_recall_shared_worker_still_requires_explicit_full_recovery(solver):
    s = shared_recall_solver(solver)
    s.op_data = s.op_data.project_arrangements(
        [{"dormitory_1": ["Current"] * 4 + ["撷英调香师"]}]
    )
    s.op_data.operators["撷英调香师"].rest_in_full = True
    assert s._plan_exhaust_support(["机械师", "撷英调香师"], urgent=True) is None


def test_urgent_recall_keeps_shared_dorm_full_recovery_requirement(solver):
    s = shared_recall_solver(solver, empty_binding=True)
    s.op_data = s.op_data.project_arrangements(
        [{"dormitory_1": ["Current"] * 4 + ["撷英调香师"]}]
    )
    s.op_data.operators["撷英调香师"].rest_in_full = True
    assert s._plan_exhaust_support(["机械师"], urgent=True) is None
    assert s.op_data.get_current_operator("dormitory_1", 1).name == "桃金娘"
    assert s.op_data.operators["撷英调香师"].is_resting()


@pytest.mark.parametrize("guard", ["reserved", "busy"])
def test_urgent_recall_ignores_protection_for_unchanged_shared_manager(solver, guard):
    from arknights_mower.utils.exhaust_replacement import plan_exhaust_support

    s = shared_recall_solver(solver)
    shared = "撷英调香师"
    s.op_data.operators[shared].group_bindings = [
        {"group": "感知", "replacement": ["桃金娘"]},
        {"group": "其他", "replacement": ["桃金娘"]},
    ]
    s.op_data.group_shift_state["其他"] = False
    s.op_data = s.op_data.project_arrangements(
        [{"dormitory_1": ["Current", shared, "Current", "Current", "Current"]}]
    )
    support = plan_exhaust_support(
        s.op_data,
        ["机械师"],
        lambda data: s._coordination_admission(data, ["机械师"]) is not None,
        lambda name: guard == "busy" and name == shared,
        [shared] if guard == "reserved" else [],
        urgent=True,
    )
    assert support == {"room_2_2": ["苍苔"], "contact": ["絮雨"]}
    assert s.op_data.get_current_operator("dormitory_1", 1).name == shared


def test_urgent_recall_preserves_independent_worker_full_recovery(solver):
    from datetime import datetime, timedelta

    from arknights_mower.utils.plan import Room

    s = solver
    plan = s.global_plan["default_plan"].plan
    plan["room_2_2"][0].replacement = ["槐琥"]
    plan["meeting"][0] = Room(
        "能天使", "", ["陈"], group_bindings=[{"group": "感知", "replacement": ["陈"]}]
    )
    assert s.initialize_operators() is None
    s.op_data = s.op_data.project_arrangements(
        [
            {
                "room_3_3": ["机械师"],
                "room_2_2": ["槐琥"],
                "contact": ["斥罪"],
                "meeting": ["陈"],
                "dormitory_1": ["冰酿", "闪灵", "苍苔", "絮雨", "能天使"],
            }
        ]
    )
    now = datetime.now()
    for op in s.op_data.operators.values():
        op.mood, op.time_stamp = 12, now
    for bed in s.op_data.dorm:
        if bed.name:
            bed.time = now + timedelta(hours=4)
    s.op_data.operators["机械师"].mood = 0
    shared = s.op_data.operators["能天使"]
    shared.rest_in_full = True
    assert shared.independent_rest and shared.group == ""
    s.check_fia = MagicMock(return_value=([], None))
    support = s._plan_exhaust_support(["机械师"], urgent=True)
    assert support == {"room_2_2": ["苍苔"], "contact": ["絮雨"]}
    projected = s.op_data.project_arrangements([support])
    assert projected.get_current_operator("meeting", 0).name == "陈"
    assert projected.operators["能天使"].is_resting()


def test_urgent_recall_does_not_exempt_unrelated_shared_request(solver):
    s = shared_recall_solver(solver)
    s.op_data.operators["撷英调香师"].group_bindings = [
        {"group": "感知", "replacement": ["桃金娘"]},
        {"group": "其他", "replacement": ["桃金娘"]},
    ]
    assert s._plan_exhaust_support(["机械师", "撷英调香师"], urgent=True) is None
