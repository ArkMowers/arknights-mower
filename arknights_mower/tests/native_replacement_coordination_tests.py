"""本体离线回放共享替班的交接、恢复和等待释放。"""

from datetime import datetime, timedelta

from arknights_mower.tests import exhaust_replacement_tests
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.replacement_coordination import (
    plan_replacement_handoff,
    recall_can_sustain,
)
from arknights_mower.utils.scheduler_task import TaskTypes

solver = exhaust_replacement_tests.solver


def test_handoff_retains_request_then_restores_first_cover(solver):
    original = solver.task
    original.time = datetime.now() - timedelta(minutes=30)
    at = original.time
    solver.overtake_room()
    support, pending = solver.tasks
    assert pending is original
    assert pending.time == at
    assert pending.execution_failure
    solver._resume_failed_tasks()
    assert pending.execution_failure
    before = [(bed.name, bed.time) for bed in solver.op_data.dorm]
    solver.op_data = solver.op_data.project_arrangements([support.plan])
    solver.tasks.remove(support)
    assert before == [(bed.name, bed.time) for bed in solver.op_data.dorm]
    solver._resume_failed_tasks()
    assert not hasattr(pending, "execution_failure")
    assert pending.time == at
    solver.task = pending
    solver.overtake_room()
    shift = next(task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF)
    assert shift.plan["room_3_3"] == ["槐琥"]
    solver.op_data = solver.op_data.project_arrangements([shift.plan])
    solver.tasks, solver.task = [], None
    solver._plan_preferred_replacements()
    assert solver.tasks == []
    # B 完成休息返回原岗位后，X 才释放给仍在休息的 A。
    solver.op_data = solver.op_data.project_arrangements([{"room_3_3": ["机械师"]}])
    solver._plan_preferred_replacements()
    (restore,) = solver.tasks
    assert restore.preferred_replacement_restore
    assert restore.plan == {"room_2_2": ["槐琥"]}
    assert solver.op_data.operators["苍苔"].is_resting()


def test_waiting_third_group_precedes_first_cover_restoration(solver):
    solver.op_data = solver.op_data.project_arrangements([{"room_2_2": ["引星棘刺"]}])
    waiting = solver.task
    solver.tasks = [waiting]
    solver.task = None
    solver._plan_preferred_replacements()
    assert solver.tasks == [waiting]
    solver.tasks = []
    solver._plan_preferred_replacements()
    assert solver.tasks[0].plan == {"room_2_2": ["槐琥"]}


def test_multi_hop_cover_handoff_uses_complete_matching(solver):
    data = solver.op_data
    data.operators["苍苔"].replacement = ["槐琥", "引星棘刺"]
    data.plan["room_1_1"] = [Room("阿罗玛", "", ["引星棘刺", "结城理"])]
    data.add(
        Operator(
            "阿罗玛",
            "room_1_1",
            index=0,
            replacement=["引星棘刺", "结城理"],
            operator_type="high",
        )
    )
    data = data.project_arrangements([{"room_1_1": ["引星棘刺"]}])
    support = plan_replacement_handoff(data, ["机械师"], lambda _: False)
    assert support == {"room_2_2": ["引星棘刺"], "room_1_1": ["结城理"]}
    assert data.operators["槐琥"].current_room == "room_2_2"
    assert data.operators["引星棘刺"].current_room == "room_1_1"
    data.operators["阿罗玛"].replacement = ["引星棘刺"]
    assert plan_replacement_handoff(data, ["机械师"], lambda _: False) is None


def test_failed_ordinary_request_waits_for_observation_without_duplication(solver):
    solver.op_data.operators["苍苔"].replacement = ["槐琥"]
    solver.task = None
    solver._schedule_group_coordination(["机械师"])
    (request,) = solver.tasks
    at = request.time
    for _ in range(3):
        solver._resume_failed_tasks()
        solver._schedule_group_coordination(["机械师"])
    assert solver.tasks == [request]
    assert request.execution_failure
    assert request.time == at
    # 由实际岗位变化释放，而非时间流逝重试。
    solver.op_data = solver.op_data.project_arrangements([{"room_2_2": ["苍苔"]}])
    solver._resume_failed_tasks()
    assert not hasattr(request, "execution_failure")
    assert request.time == at


def test_unknown_recall_forecast_never_uses_old_rates(solver):
    data = solver.op_data
    admitted = data.project_arrangements(
        [
            {
                "room_2_2": ["苍苔"],
                "contact": ["絮雨"],
                "room_3_3": ["槐琥"],
                "dormitory_1": ["Current", "Current", "机械师", "Free", "Free"],
            }
        ]
    )
    for op in data.operators.values():
        op.depletion_rate = 0.5
    assert not recall_can_sustain(data, admitted, ["苍苔", "絮雨"], ["机械师"])
    # 完整可信阵容速率存在时才比较整个连通范围与共享床位的恢复周期。
    work = {name: 0.1 for name in data.operators}
    recovery = {name: 4 for name in data.operators}
    assert recall_can_sustain(
        data, admitted, ["苍苔", "絮雨"], ["机械师"], rates=(work, recovery)
    )
    work["絮雨"] = 10
    assert not recall_can_sustain(
        data, admitted, ["苍苔", "絮雨"], ["机械师"], rates=(work, recovery)
    )


def test_released_unrelated_bed_rearms_original_coordination(solver):
    data = solver.op_data
    data.operators["机械师"].replacement = ["陈"]
    solver.task.coordination_request_names = ["机械师"]
    solver.tasks = [solver.task]
    solver._retain_failed_task(solver.task, "没有空床", [])
    at = solver.task.time
    solver._resume_failed_tasks()
    assert solver.task.execution_failure
    solver.op_data = data.project_arrangements([{"contact": ["絮雨"]}])
    solver._resume_failed_tasks()
    assert not hasattr(solver.task, "execution_failure")
    assert solver.task.time == at


def test_ordinary_request_rechecks_mood_after_fiammetta_charge(solver):
    from unittest.mock import Mock

    data = solver.op_data
    data.exhaust_agent = []
    data.operators["机械师"].exhaust_require = False
    solver.task.ordinary_coordination = True
    assert solver._ordinary_coordination_needed(["机械师"])
    data.operators["机械师"].mood = 24
    data.operators["机械师"].time_stamp = datetime.now()
    solver.get_resting_plan = Mock(side_effect=AssertionError("已充满者不再下班"))
    solver.overtake_room()
    solver.get_resting_plan.assert_not_called()
    assert solver.tasks == []


def test_obsolete_support_does_not_move_returned_primary(solver):
    solver.overtake_room()
    support, request = solver.tasks
    solver.op_data = solver.op_data.project_arrangements(
        [{"room_2_2": ["苍苔"], "contact": ["絮雨"]}]
    )
    solver.task = support
    solver._refresh_coordination_support(support)
    assert support.plan == {}
    assert request in solver.tasks
    assert solver.op_data.operators["苍苔"].is_working()


def test_explicit_retained_task_keeps_its_alternate_cover(solver):
    from arknights_mower.utils.replacement_coordination import coordination_reservations
    from arknights_mower.utils.scheduler_task import SchedulerTask

    data = solver.op_data
    data.operators["苍苔"].replacement = ["槐琥", "引星棘刺"]
    reserved = SchedulerTask(task_plan={"meeting": ["引星棘刺"]})
    solver.tasks = [reserved]
    solver._retain_failed_task(reserved, "等待读房", ["meeting"])
    names, slots = coordination_reservations(data, solver.tasks, solver.task)
    assert "引星棘刺" in names
    assert ("meeting", 0) in slots
    assert solver._plan_exhaust_support(["机械师"]) is None
    assert reserved.plan == {"meeting": ["引星棘刺"]}
    assert data.operators["槐琥"].current_room == "room_2_2"


def test_ordinary_retry_support_discards_obsolete_backup_intent(solver):
    from copy import deepcopy

    data = solver.op_data
    data.exhaust_agent = []
    data.operators["机械师"].exhaust_require = False
    solver.task.ordinary_coordination = True
    solver.overtake_room()
    support, request = solver.tasks
    assert support.ordinary_coordination
    support.backup_shift_intent = deepcopy(support.plan)
    assert support.backup_shift_intent
    data.operators["机械师"].mood = 24
    data.operators["机械师"].time_stamp = datetime.now()
    solver.task = support
    solver._refresh_coordination_support(support)
    assert support.plan == {}
    assert support.backup_shift_intent == {}
    assert request in solver.tasks


def test_started_support_keeps_remaining_arrangement(solver):
    from copy import deepcopy

    solver.overtake_room()
    support, request = solver.tasks
    remaining = deepcopy(support.plan)
    support.group_shift_expected = {
        (room, index): name
        for room, names in remaining.items()
        for index, name in enumerate(names)
    }
    solver.op_data = solver.op_data.project_arrangements(
        [{"room_2_2": ["苍苔"], "contact": ["絮雨"]}]
    )
    solver.task = support
    solver._refresh_coordination_support(support)
    assert support.plan == remaining
    assert request in solver.tasks
