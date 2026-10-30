"""本体离线回放共享替班的交接、恢复和等待释放。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, call

import pytest

from arknights_mower.tests import (
    backup_rest_schedule_tests,
    exhaust_replacement_tests,
    multi_group_individual_rest_tests,
    multi_group_shift_tests,
)
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.replacement_coordination import (
    plan_replacement_handoff,
    recall_can_sustain,
)
from arknights_mower.utils.scheduler_task import TaskTypes

solver = exhaust_replacement_tests.solver
base = exhaust_replacement_tests.base_schedule
backup_solver = backup_rest_schedule_tests.solver
shared_solver = multi_group_shift_tests.solver


def test_handoff_retains_request_then_restores_first_cover(solver, caplog):
    caplog.set_level("INFO")
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
    solver.overtake_room()
    assert solver.tasks == [support, pending]
    assert pending.time == at
    waits = [record for record in caplog.records if "等待" in record.message]
    assert len(waits) == 2
    assert all(record.levelname == "INFO" for record in waits)
    assert not [record for record in caplog.records if record.levelno >= 30]
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


def test_ordinary_mutex_creates_no_request_or_error_and_replans_after_release(
    solver, caplog
):
    solver.op_data.operators["苍苔"].replacement = ["槐琥"]
    solver.task = None
    for _ in range(3):
        solver._schedule_group_coordination(["机械师"])
        solver._resume_failed_tasks()
    assert solver.tasks == []
    assert not [record for record in caplog.records if record.levelno >= 30]
    # 实际回班释放替班后，正常规划可以取得完整下班安排。
    solver.op_data = solver.op_data.project_arrangements([{"room_2_2": ["苍苔"]}])
    plan = {}
    assert solver.get_resting_plan(["机械师"], [], plan, 0)
    assert plan["room_3_3"] == ["槐琥"]


def test_unknown_recall_forecast_requires_work_and_recovery_estimates(solver):
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


def test_backup_exhaust_rule_blocks_ordinary_request_for_the_whole_group(solver):
    from unittest.mock import Mock

    data = solver.op_data
    for name in ("机械师", "能天使"):
        data.operators[name].group = "工作组"
    data.groups["工作组"] = ["机械师", "能天使"]
    data.operators["机械师"].exhaust_require = False
    data.operators["能天使"].exhaust_require = True
    data.exhaust_agent = {"能天使"}
    data.exhaust_group = {"工作组"}
    solver.task.ordinary_coordination = True
    solver.get_resting_plan = Mock(side_effect=AssertionError("普通请求不能绕过用尽"))

    solver.overtake_room()

    solver.get_resting_plan.assert_not_called()
    assert solver.tasks == []
    assert data.operators["机械师"].is_working()
    assert data.operators["能天使"].is_working()
    data.exhaust_agent.clear()
    data.exhaust_group.clear()
    data.operators["能天使"].exhaust_require = False
    assert solver._ordinary_coordination_needed(["机械师", "能天使"])


def _queue_ordinary_departure(solver, *, grouped=False):
    data = solver.op_data
    solver.op_data = data.project_arrangements(
        [{"room_2_2": ["苍苔"], "contact": ["絮雨"]}]
    )
    data = solver.op_data
    data.exhaust_agent.clear()
    data.operators["机械师"].exhaust_require = False
    if grouped:
        for name in ("机械师", "能天使"):
            data.operators[name].group = "工作组"
        data.groups["工作组"] = ["机械师", "能天使"]
    solver.task.ordinary_coordination = True
    solver.overtake_room()
    (task,) = solver.tasks
    assert task.type == TaskTypes.SHIFT_OFF
    solver.task = task
    return task


def _prepare_dispatch(solver):
    from unittest.mock import MagicMock

    solver.find = MagicMock(return_value=True)
    solver.planned = True
    solver.todo_task = solver.collect_notification = False
    solver.agent_arrange = MagicMock(side_effect=AssertionError("不应操作设备"))


def test_ordinary_concrete_departure_rechecks_peer_exhaustion_before_dispatch(solver):
    task = _queue_ordinary_departure(solver, grouped=True)
    _prepare_dispatch(solver)
    data = solver.op_data
    data.exhaust_agent.add("能天使")
    data.exhaust_group.add("工作组")
    data.operators["能天使"].exhaust_require = True

    solver.infra_main()

    solver.agent_arrange.assert_not_called()
    assert task not in solver.tasks
    assert solver.planned is False
    assert data.operators["机械师"].is_working()
    assert data.operators["能天使"].is_working()


def test_ordinary_batch_replans_when_only_one_group_becomes_exhaustion(solver):
    _queue_ordinary_departure(solver)
    solver.tasks, solver.task = [], None
    solver.op_data.correct_dorm()
    solver.op_data.operators["能天使"].mood = 0
    solver.total_agent = list(solver.op_data.operators.values())
    solver.resting()
    (task,) = [task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF]
    assert task.plan["room_3_3"] == ["槐琥"]
    assert task.plan["meeting"] == ["陈"]
    solver.task = task
    _prepare_dispatch(solver)
    solver.op_data.exhaust_agent.add("能天使")

    solver.infra_main()

    solver.agent_arrange.assert_not_called()
    assert task not in solver.tasks
    assert solver.planned is False
    assert solver.op_data.operators["机械师"].is_working()


def test_direct_ordinary_planning_keeps_departure_origin(solver):
    _queue_ordinary_departure(solver)
    solver.task = None
    solver.tasks = []
    solver.total_agent = list(solver.op_data.operators.values())

    plan = solver.resting()

    (task,) = [task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF]
    assert plan["room_3_3"] == ["槐琥"]
    _prepare_dispatch(solver)
    solver.task = task
    solver.op_data.exhaust_agent.add("机械师")
    solver.infra_main()
    solver.agent_arrange.assert_not_called()
    assert task not in solver.tasks


def test_genuine_exhaustion_departure_keeps_device_execution(solver):
    from unittest.mock import MagicMock

    class ReachedArrangement(BaseException):
        pass

    solver.op_data = solver.op_data.project_arrangements(
        [{"room_2_2": ["苍苔"], "contact": ["絮雨"]}]
    )
    solver.overtake_room()
    (task,) = solver.tasks
    solver.task = task
    _prepare_dispatch(solver)
    solver.agent_arrange = MagicMock(side_effect=ReachedArrangement)
    with pytest.raises(ReachedArrangement):
        solver.infra_main()
    assert solver.agent_arrange.call_args.args[0]["room_3_3"] == ["槐琥"]


@pytest.mark.parametrize(
    "started_marker", ["backup_shift_active", "group_shift_expected"]
)
def test_started_ordinary_departure_keeps_remaining_arrangement(solver, started_marker):
    from unittest.mock import MagicMock

    class ReachedArrangement(BaseException):
        pass

    task = _queue_ordinary_departure(solver)
    setattr(
        task,
        started_marker,
        True if started_marker == "backup_shift_active" else {("room_3_3", 0): "槐琥"},
    )
    solver.op_data.exhaust_agent.add("机械师")
    _prepare_dispatch(solver)
    solver.agent_arrange = MagicMock(side_effect=ReachedArrangement)
    with pytest.raises(ReachedArrangement):
        solver.infra_main()
    assert solver.agent_arrange.call_args.args[0]["room_3_3"] == ["槐琥"]


@pytest.mark.usefixtures("offline_maintenance")
def test_ordinary_departure_applies_real_backup_condition_before_arrangement(
    backup_solver,
):
    from arknights_mower.solvers import base_schedule
    from arknights_mower.utils.scheduler_task import SchedulerTask

    s = backup_solver
    song = s.op_data.operators["歌蕾蒂娅"]
    song.mood, song.time_stamp = 12, base_schedule.datetime.now()
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "central": ["陈"],
            "dormitory_1": ["Current", "Current", "Current", "歌蕾蒂娅", "Current"],
        },
    )
    task.ordinary_coordination = True
    task.coordination_request_names = ["歌蕾蒂娅"]
    s.tasks, s.task = [task], task
    _prepare_dispatch(s)
    assert s.op_data.plan_condition == [False]

    s.infra_main()

    assert s.op_data.plan_condition == [True]
    assert s.op_data.operators["歌蕾蒂娅"].exhaust_require
    assert s.op_data.operators["歌蕾蒂娅"].is_working()
    s.agent_arrange.assert_not_called()
    assert task not in s.tasks
    assert s.planned is False
    assert all(
        "歌蕾蒂娅" not in names
        for queued in s.tasks
        for room, names in queued.plan.items()
        if room.startswith("dorm")
    )


def test_group_request_does_not_make_independent_follower_an_extra_trigger(
    shared_solver,
):
    from arknights_mower.tests.multi_group_shift_tests import SHARED, A
    from arknights_mower.utils.scheduler_task import SchedulerTask

    s = multi_group_individual_rest_tests.individual.__wrapped__(shared_solver)
    s.op_data.operators[A].mood = 0
    s.task = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data=A)
    s.task.ordinary_coordination = True
    s.overtake_room()
    (task,) = [task for task in s.tasks if task.type == TaskTypes.SHIFT_OFF]
    assert SHARED not in task.coordination_request_names
    assert s._prepare_ordinary_departure(task)


@pytest.mark.usefixtures("offline_maintenance")
@pytest.mark.parametrize("coalesced", [False, True])
@pytest.mark.parametrize("explicit", [False, True])
def test_projected_exhaust_backup_keeps_trigger_group_and_removes_other_departure(
    backup_solver, coalesced, explicit
):
    from arknights_mower.solvers import base_schedule
    from arknights_mower.utils.scheduler_task import SchedulerTask

    s = backup_solver
    data = s.op_data
    data.operators["黑键"].current_room = "contact"
    data.operators["黑键"].current_index = 0
    data.operators["黑键"].mood = 0
    data.operators["歌蕾蒂娅"].mood = 12
    data.operators["歌蕾蒂娅"].time_stamp = base_schedule.datetime.now()
    data.correct_dorm()
    s.total_agent = list(data.operators.values())
    s.resting()
    (task,) = [pending for pending in s.tasks if pending.type == TaskTypes.SHIFT_OFF]
    assert task.plan["contact"] == ["红"]
    assert task.plan["central"] == ["陈"]
    if coalesced:
        song_plan = {"central": task.plan.pop("central")}
        for room, row in task.plan.items():
            if not room.startswith("dorm"):
                continue
            song_plan[room] = [
                name if name == "歌蕾蒂娅" else "Current" for name in row
            ]
            task.plan[room] = [
                "Current" if name == "歌蕾蒂娅" else name for name in row
            ]
        task.coordination_request_names = ["黑键"]
        song_task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan=song_plan)
        song_task.ordinary_coordination = True
        song_task.coordination_request_names = ["歌蕾蒂娅"]
        s.tasks.append(song_task)
    s.task = task
    if explicit:
        task.backup_explicit_slots = {("central", 0), ("dormitory_1", 3)}
        task.plan["dormitory_1"][3] = "歌蕾蒂娅"

    s._prepare_group_shift(task)
    s._prepare_shift_cycle(task)
    assert ("central" in task.backup_shift_intent) == explicit
    s._prepare_shift_cycle(task)
    s._activate_shift_backup(task)

    projected = s.op_data.project_arrangements([task.plan])
    assert s.op_data.plan_condition == [True]
    assert s.op_data.operators["歌蕾蒂娅"].is_working()
    assert projected.operators["歌蕾蒂娅"].is_working() is not explicit
    assert projected.operators["歌蕾蒂娅"].is_resting() is explicit
    assert projected.operators["黑键"].is_resting()
    assert projected.operators["歌蕾蒂娅"].exhaust_require
    assert ("central" in task.plan) == explicit
    s.agent_arrange.assert_not_called()


@pytest.mark.usefixtures("offline_maintenance")
def test_projected_exhaustion_preserves_shared_follower_needed_by_trigger_group(
    shared_solver,
):
    from arknights_mower.tests.multi_group_shift_tests import SHARED, A, B
    from arknights_mower.utils.logic_expression import LogicExpression
    from arknights_mower.utils.plan import Plan, PlanConfig

    s = shared_solver
    s.global_plan["default_plan"].plan["contact"][0].group_bindings[0][
        "replacement"
    ] = ["红"]
    s.global_plan["backup_plans"] = [
        Plan(
            {},
            PlanConfig("", B, ""),
            trigger=LogicExpression(
                f"op_data.operators['{A}'].is_resting()", "==", "True"
            ),
        )
    ]
    assert s.initialize_operators() is None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 12, datetime.now()
    s.op_data.operators[A].mood = 0
    s.op_data.operators[B].mood = 1
    s.total_agent = list(s.op_data.operators.values())
    s.resting()
    (task,) = [pending for pending in s.tasks if pending.type == TaskTypes.SHIFT_OFF]
    s.task = task

    s._prepare_group_shift(task)
    s._prepare_shift_cycle(task)
    projected = s.op_data.project_arrangements([task.plan])

    assert task.backup_shift_conditions == [True]
    assert projected.operators[A].is_resting()
    assert projected.operators[B].is_working()
    assert projected.operators[SHARED].is_resting()
    assert projected.get_current_operator("contact", 0).name == "红"


@pytest.mark.usefixtures("offline_maintenance")
def test_genuine_exhaust_departure_survives_merged_duplicate_ordinary_request(
    backup_solver,
):
    from copy import deepcopy

    from arknights_mower.solvers import base_schedule
    from arknights_mower.utils.scheduler_task import SchedulerTask

    s = backup_solver
    song = s.op_data.operators["歌蕾蒂娅"]
    song.mood, song.time_stamp = 0, base_schedule.datetime.now()
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "central": ["陈"],
            "dormitory_1": ["Current", "Current", "Current", "歌蕾蒂娅", "Current"],
        },
    )
    ordinary = deepcopy(task)
    ordinary.ordinary_coordination = True
    ordinary.coordination_request_names = ["歌蕾蒂娅"]
    s.tasks, s.task = [task, ordinary], task

    s._prepare_shift_cycle(task)
    projected = s.op_data.project_arrangements([task.plan])

    assert task.backup_shift_conditions == [True]
    assert projected.operators["歌蕾蒂娅"].is_resting()
    assert task.plan["central"] == ["陈"]


def test_backup_coalescing_keeps_cover_in_dorm_when_ordinary_departure_is_cancelled(
    solver,
):
    from arknights_mower.utils.scheduler_task import SchedulerTask

    s = solver
    s.op_data = s.op_data.project_arrangements(
        [
            {
                "room_2_2": ["苍苔"],
                "contact": ["絮雨"],
                "dormitory_1": ["Current", "Current", "Free", "Free", "槐琥"],
            }
        ]
    )
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "room_3_3": ["槐琥"],
            "dormitory_1": ["Current", "Current", "机械师", "Current", "Free"],
        },
    )
    task.ordinary_coordination = True
    task.coordination_request_names = ["机械师"]
    s.tasks = [task]
    transition = {"dormitory_1": ["Current", "Current", "苍苔", "Current", "Current"]}

    merged, consumed = s._coalesce_backup_transition(transition)
    projected = s.op_data.project_arrangements([merged])

    assert consumed == [task]
    assert projected.operators["机械师"].is_working()
    assert projected.get_current_operator("dormitory_1", 4).name == "槐琥"
    assert "room_3_3" not in merged


@pytest.mark.usefixtures("offline_maintenance")
def test_failed_exhaust_preview_retains_original_ordinary_request(
    backup_solver, monkeypatch
):
    from copy import deepcopy

    from arknights_mower.solvers.base_schedule import (
        BaseSchedulerSolver,
        ProductSwitchDeferred,
    )
    from arknights_mower.utils.scheduler_task import SchedulerTask

    s = backup_solver
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "central": ["陈"],
            "dormitory_1": ["Current", "Current", "Current", "歌蕾蒂娅", "Current"],
        },
    )
    task.ordinary_coordination = True
    task.coordination_request_names = ["歌蕾蒂娅"]
    task.group_shift_transitions = {}
    s.tasks, s.task = [task], task
    original = deepcopy(task.__dict__)

    def failed_preview(solver, *args, failure_reasons=None):
        solver._backup_departure_waiting_names = set()
        return None

    monkeypatch.setattr(BaseSchedulerSolver, "_backup_transition_plan", failed_preview)

    with pytest.raises(ProductSwitchDeferred):
        s._prepare_shift_backup(task)

    assert task.__dict__ == original
    assert s.op_data.plan_condition == [False]
    assert s.op_data.operators["歌蕾蒂娅"].is_working()


def seed_observed_recall_rates(data):
    from arknights_mower.utils.dorm_recovery import recovery_managers

    for op in data.operators.values():
        op.depletion_rate = 0.5
        op.recall_work_rate = (0.5, op.time_stamp)
    room = "dormitory_1"
    names = [
        data.get_current_operator(room, index) for index in range(len(data.plan[room]))
    ]
    target = data.operators["苍苔"]
    target.dorm_recovery_room, target.dorm_recovery_index = room, 2
    target.dorm_recovery_fixed = recovery_managers(
        data, room, [op.name if op else "" for op in names]
    )


def test_native_support_can_recall_using_observed_approximate_rates(solver):
    data = solver.op_data
    data.operators["苍苔"].replacement = ["槐琥"]
    seed_observed_recall_rates(data)
    before = {
        name: (op.current_room, op.current_index, op.mood, op.time_stamp)
        for name, op in data.operators.items()
    }
    before_beds = [(bed.name, bed.time) for bed in data.all_dorms()]
    support = solver._plan_exhaust_support(["机械师"])
    assert support is not None
    assert support["room_2_2"] == ["苍苔"]
    assert support["contact"] == ["絮雨"]
    assert solver._coordination_support_valid(support, ["机械师"])
    assert before == {
        name: (op.current_room, op.current_index, op.mood, op.time_stamp)
        for name, op in data.operators.items()
    }
    assert before_beds == [(bed.name, bed.time) for bed in data.all_dorms()]


@pytest.mark.parametrize("failure", ["short-work", "full-required", "unknown-work"])
def test_approximate_recall_preserves_protection_and_sustainability(solver, failure):
    data = solver.op_data
    data.operators["苍苔"].replacement = ["槐琥"]
    seed_observed_recall_rates(data)
    if failure == "short-work":
        data.operators["絮雨"].depletion_rate = 10
        data.operators["絮雨"].recall_work_rate = (
            10,
            data.operators["絮雨"].time_stamp,
        )
    elif failure == "full-required":
        data.operators["絮雨"].rest_in_full = True
    else:
        data.operators["絮雨"].depletion_rate = 0
        del data.operators["絮雨"].recall_work_rate
    assert solver._plan_exhaust_support(["机械师"]) is None


@pytest.mark.parametrize("group_wait", [False, True])
@pytest.mark.parametrize("remaining", [60, 180])
def test_recall_requires_each_selected_member_within_operation_window(
    solver, monkeypatch, group_wait, remaining
):
    from arknights_mower.utils import operation_timing

    data = solver.op_data
    data.operators["苍苔"].replacement = ["槐琥"]
    seed_observed_recall_rates(data)
    monkeypatch.setattr(operation_timing, "_dorm_durations", {})
    for name in ["苍苔", "絮雨"]:
        op = data.operators[name]
        op.rest_in_full = not group_wait
        op.mood, op.time_stamp, op.mood_is_prediction = 23.9, datetime.now(), False
        data.get_dorm_by_name(name)[1].time = datetime.now() + timedelta(
            seconds=60 if name == "苍苔" else remaining
        )
    if group_wait:
        data.group_recovery_full_members["感知"] = ["苍苔", "絮雨"]
    support = solver._plan_exhaust_support(["机械师"])
    if remaining == 60:
        assert support is not None
        assert support["room_2_2"] == ["苍苔"]
        assert support["contact"] == ["絮雨"]
    else:
        assert support is None
    assert data.operators["苍苔"].mood == data.operators["絮雨"].mood == 23.9


def test_failed_arrangement_retains_error_logging(solver, caplog):
    original = solver.task
    at = original.time
    solver._retain_failed_task(original, "宿舍换人失败", ["dormitory_1"])
    assert original.time == at
    assert original.execution_failure["reason"] == "宿舍换人失败"
    assert any(
        record.levelname == "ERROR" and "宿舍换人失败" in record.message
        for record in caplog.records
    )


@pytest.fixture
def ordinary_recall(solver, monkeypatch):
    from unittest.mock import Mock

    from arknights_mower.utils import config, recall_estimates

    data = solver.op_data
    data.config.resting_threshold = 0.65
    config.conf.rescue_threshold = 0.5
    data.exhaust_agent = []
    data.operators["机械师"].exhaust_require = False
    data.operators["苍苔"].replacement = ["槐琥"]
    data.plan["room_2_2"][0].replacement = ["槐琥"]
    for op in data.operators.values():
        op.depletion_rate = 0
        op.time_stamp = datetime.now() - timedelta(seconds=1)
    solver.check_fia = Mock(return_value=([], None))
    solver.task = None
    rates = (
        {name: 0.1 for name in data.operators},
        {name: 4 for name in data.operators},
    )
    monkeypatch.setattr(
        recall_estimates, "estimated_recall_rates", lambda *a, **k: rates
    )
    return solver, rates


@pytest.mark.parametrize("request_mood,allowed", [(7.81, False), (7.8, True)])
def test_ordinary_recall_requires_request_at_rescue_line(
    ordinary_recall, request_mood, allowed
):
    s, _ = ordinary_recall
    s.op_data.operators["机械师"].mood = request_mood
    before = [(op.name, op.current_room) for op in s.op_data.operators.values()]
    plan = s._plan_exhaust_support(["机械师"])
    assert bool(plan) == allowed
    if allowed:
        assert plan["room_2_2"] == ["苍苔"]
    assert before == [(op.name, op.current_room) for op in s.op_data.operators.values()]


@pytest.mark.parametrize("target_mood,allowed", [(7.8, True), (7.79, True), (0, False)])
def test_ordinary_rescue_checks_low_group_endurance(
    ordinary_recall, target_mood, allowed
):
    s, _ = ordinary_recall
    s.op_data.operators["机械师"].mood = 7
    # 急救线以下也按整组续航决定，不能漏查另一名组员。
    s.op_data.operators["絮雨"].mood = target_mood
    assert bool(s._plan_exhaust_support(["机械师"])) == allowed


@pytest.mark.parametrize("request_mood", [7, 0])
def test_ordinary_rescue_and_floor_recall_keep_endurance_check(
    ordinary_recall, request_mood
):
    s, rates = ordinary_recall
    s.op_data.operators["机械师"].mood = request_mood
    s.op_data.operators["苍苔"].mood = 3
    s.op_data.operators["絮雨"].mood = 3
    assert s._plan_exhaust_support(["机械师"])
    rates[0]["絮雨"] = 2
    assert s._plan_exhaust_support(["机械师"]) is None
    # 真正用尽继续沿用独立强制召回规则。
    assert s._plan_exhaust_support(["机械师"], urgent=True)


def test_ordinary_handoff_above_rescue_does_not_recall(ordinary_recall):
    s, _ = ordinary_recall
    s.op_data.operators["机械师"].mood = 15
    s.op_data.operators["苍苔"].replacement.append("引星棘刺")
    assert s._plan_exhaust_support(["机械师"]) == {"room_2_2": ["引星棘刺"]}


def test_ordinary_recall_revalidates_changed_request_and_target(ordinary_recall):
    from arknights_mower.utils.scheduler_task import SchedulerTask

    s, _ = ordinary_recall
    s.op_data.operators["机械师"].mood = 7
    plan = s._plan_exhaust_support(["机械师"])
    assert plan
    s.task = SchedulerTask(task_plan=plan, task_type=TaskTypes.SELF_CORRECTION)
    s.task.exhaust_support = True
    s.task.ordinary_coordination = True
    assert s._coordination_support_valid(plan, ["机械师"])
    s.op_data.operators["机械师"].mood = 20
    assert not s._coordination_support_valid(plan, ["机械师"])
    s.op_data.operators["机械师"].mood = 7
    s.op_data.operators["絮雨"].mood = 0
    assert not s._coordination_support_valid(plan, ["机械师"])


@pytest.mark.parametrize("name", ["机械师", "苍苔"])
@pytest.mark.parametrize("invalid", ["missing", "prediction", "nan", "future"])
def test_ordinary_recall_rejects_unknown_observations(ordinary_recall, name, invalid):
    s, _ = ordinary_recall
    s.op_data.operators["机械师"].mood = 7
    op = s.op_data.operators[name]
    if invalid == "missing":
        op.time_stamp = None
    elif invalid == "prediction":
        op.mood_is_prediction = True
    elif invalid == "nan":
        op.mood = float("nan")
    else:
        op.time_stamp = datetime.now() + timedelta(hours=1)
    assert s._plan_exhaust_support(["机械师"]) is None


def test_failed_rescue_reassesses_at_floor_after_recovery_changes(
    ordinary_recall, caplog
):
    s, rates = ordinary_recall
    data = s.op_data
    data.operators["机械师"].mood = 7
    data.operators["苍苔"].mood = data.operators["絮雨"].mood = 3
    rates[0]["絮雨"] = 2
    for _ in range(3):
        s._schedule_group_coordination(["机械师"])
    assert s.tasks == []
    # 其他组实际恢复后，新观测允许到下限的原请求重新评估。
    data.operators["机械师"].mood = 0
    data.operators["苍苔"].mood = data.operators["絮雨"].mood = 16
    for op in data.operators.values():
        op.time_stamp = datetime.now()
    s._schedule_group_coordination(["机械师"])
    s._schedule_group_coordination(["机械师"])
    assert len(s.tasks) == 1
    assert s.tasks[0].ordinary_coordination
    assert s.tasks[0].plan["room_2_2"] == ["苍苔"]
    assert not [record for record in caplog.records if record.levelno >= 30]


@pytest.mark.parametrize("first_mood,expected", [(4, "meeting"), (12, "room_2_2")])
def test_ordinary_recall_tries_next_owner_after_complete_unsafe_admission(
    ordinary_recall, first_mood, expected
):
    s, rates = ordinary_recall
    data = s.op_data
    data.operators["机械师"].mood = 7
    data.operators["机械师"].replacement = ["槐琥", "陈"]
    data.plan["room_3_3"][0].replacement = ["槐琥", "陈"]
    for name in ("苍苔", "絮雨"):
        data.operators[name].mood = first_mood
    data.operators["能天使"].mood = 20
    s.op_data = data.project_arrangements(
        [{"meeting": ["陈"], "dormitory_1": ["冰酿", "闪灵", "苍苔", "絮雨", "能天使"]}]
    )
    for bed in s.op_data.dorm:
        if bed.name:
            bed.time = datetime.now() + timedelta(hours=4)
    rates[0].update({name: 1 for name in data.operators})
    before = [(op.name, op.current_room) for op in s.op_data.operators.values()]
    plan = s._plan_exhaust_support(["机械师"])
    assert plan
    assert expected in plan
    assert ("room_2_2" in plan) == (expected == "room_2_2")
    assert before == [(op.name, op.current_room) for op in s.op_data.operators.values()]


def test_ordinary_recall_preserves_prerequisite_until_all_covers_are_released(
    ordinary_recall,
):
    s, rates = ordinary_recall
    data = s.op_data
    for name in ("机械师", "能天使"):
        data.operators[name].group = "工作组"
        data.operators[name].mood = 7
    data.groups["工作组"] = ["机械师", "能天使"]
    data.operators["能天使"].replacement = ["斥罪"]
    data.plan["meeting"][0].replacement = ["斥罪"]
    data.groups.pop("感知")
    for name in ("苍苔", "絮雨"):
        data.operators[name].group = ""
        data.operators[name].mood = 20
    rates[0].update({name: 1 for name in data.operators})
    # 只召回苍苔时，能天使尚无替班；不能把不完整准入当作续航失败。
    after_first = data.project_arrangements([{"room_2_2": ["苍苔"]}])
    assert s._coordination_admission(after_first, ["机械师", "能天使"]) is None
    plan = s._plan_exhaust_support(["机械师", "能天使"])
    assert plan == {"room_2_2": ["苍苔"], "contact": ["絮雨"]}


@pytest.mark.usefixtures("offline_maintenance")
@pytest.mark.parametrize("enabled", [False, True])
def test_failed_training_entry_recovers_handoff_at_next_patrol(
    solver, monkeypatch, enabled
):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.current

    from arknights_mower.solvers import mastery_reader
    from arknights_mower.utils import config, operators

    Clock.current = Clock(2026, 10, 30, 0)
    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(operators, "datetime", Clock)
    monkeypatch.setattr(config.conf, "enable_mastery", enabled)
    monkeypatch.setattr(operators.Operators, "current_room_changed_callback", None)
    solver.global_plan = {
        "default_plan": Plan(
            {
                "central": [
                    Room("歌蕾蒂娅", "深海", ["夕"]),
                    Room("森蚺", "自动化", ["诗怀雅"]),
                ],
                "train": [
                    Room("褐果", "自动化", ["梅尔"]),
                    Room("桃金娘", "自动化", ["赫默"]),
                ],
                "dormitory_1": [
                    Room("冰酿", "", []),
                    Room("琴柳", "深海", ["赫默"]),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
                "dormitory_2": [
                    Room("杜林", "", []),
                    Room("闪灵", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            PlanConfig("", "", ""),
        ),
        "backup_plans": [
            Plan(
                {},
                PlanConfig("", "", ""),
                trigger=LogicExpression("False", "==", "True"),
            )
        ],
    }
    assert solver.initialize_operators() is None
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "central": ["歌蕾蒂娅", "诗怀雅"],
                "train": ["梅尔", "赫默"],
                "dormitory_1": ["冰酿", "琴柳", "森蚺", "Free", "Free"],
            }
        ]
    )
    for op in solver.op_data.operators.values():
        op.mood, op.time_stamp, op.depletion_rate = 24, Clock.now(), 0
    solver.op_data.operators["歌蕾蒂娅"].mood = 0
    solver.op_data.commit_group_shifts({"自动化": True, "深海": False})
    for bed in solver.op_data.dorm:
        if bed.name:
            bed.time = Clock.now() + timedelta(hours=4)
    for name in ("梅尔", "赫默"):
        solver.op_data.operators[name].time_stamp -= timedelta(hours=3)
    solver.tasks, solver.task = [], None
    solver.check_fia = lambda: ({}, None)
    solver.skip = lambda: None
    solver.enter_room = MagicMock(side_effect=RuntimeError("未成功进入房间 train"))
    solver.back_to_infrastructure = MagicMock()
    solver.back = MagicMock()
    solver._read_room_mood = MagicMock()
    monkeypatch.setattr(mastery_reader, "reconcile_short", MagicMock())
    solver._read_agent_mood()
    solver._read_agent_mood()
    solver.enter_room.assert_called_once_with("train", max_attempts=1)
    assert solver.tasks == []

    Clock.current += timedelta(hours=2.5)
    solver.enter_room.side_effect = None
    observed = mastery_reader.RoomState("empty", slots_read=True, slots_reliable=True)
    moods = [{"agent": name, "mood": 24} for name in ("梅尔", "赫默")]
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *args, **kwargs: (observed, moods) if enabled else observed,
    )
    solver.get_agent_from_room = MagicMock(return_value=moods)
    solver._read_agent_mood()
    assert solver.enter_room.call_args_list.count(call("train", max_attempts=1)) == 2
    assert solver.last_train_mood_read == Clock.now()

    from arknights_mower.utils.scheduler_task import SchedulerTask

    request = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="歌蕾蒂娅")
    solver.task = request
    solver.overtake_room()
    support = next(
        task for task in solver.tasks if getattr(task, "exhaust_support", False)
    )
    assert support.plan["train"] == ["褐果", "桃金娘"]
    before = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    solver.task = support
    solver._prepare_group_shift(support)
    solver._prepare_shift_cycle(support)
    assert support.plan["train"] == ["褐果", "桃金娘"]
    assert solver._coordination_support_valid(
        support.plan, support.coordination_request_names
    )
    assert before == {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    assert solver.op_data.operators["赫默"].current_room == "train"
    solver.op_data = solver.op_data.project_arrangements([support.plan])
    assert solver.op_data.operators["赫默"].current_room == ""
    solver.tasks, solver.task = [request], request
    solver.overtake_room()
    departure = next(task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF)
    assert departure.plan["dormitory_1"][1] == "赫默"
    assert any(
        "歌蕾蒂娅" in row
        for room, row in departure.plan.items()
        if room.startswith("dorm")
    )
