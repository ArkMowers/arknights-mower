"""救急选人失败沿用原任务的失败保留、派发和重启恢复。"""

import copy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import jsonpickle
import pytest

from arknights_mower.solvers import base_schedule, emergency
from arknights_mower.solvers.base_mixin import AgentSelectionNotReady
from arknights_mower.tests.emergency_group_return_tests import (
    group_return as recovery_fixture,  # noqa: F401
)
from arknights_mower.tests.emergency_group_return_tests import (
    legacy_solver as legacy_solver,
)
from arknights_mower.tests.emergency_group_staffing_tests import staffing as staffing
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.scheduler_recovery_preservation_tests import (
    scheduler as scheduler,
)
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    find_next_task,
    protect_priority_tasks,
    task_view,
)


@pytest.fixture
def failed_rescue(scheduler, staffing, monkeypatch):
    solver = scheduler.solver
    solver.op_data = staffing.solver.op_data
    solver.emergency_state = staffing.state
    solver.last_execution = staffing.solver.last_execution
    scheduler.clock.current = next(iter(solver.op_data.operators.values())).time_stamp
    monkeypatch.setattr(emergency, "datetime", scheduler.clock)
    monkeypatch.setattr(base_schedule, "datetime", scheduler.clock)
    solver._emergency_save = Mock(return_value=True)
    solver._emergency_read_rooms = Mock(return_value=True)
    solver._emergency_collect = Mock()
    for method in (
        "_prepare_shift_cycle",
        "_prepare_group_shift",
        "_switch_products_before_arrangement",
        "_defer_conflicting_product_shift_slots",
        "back_to_infrastructure",
        "_fill_empty_dorms",
        "plan_metadata",
        "enter_room",
        "turn_on_room_detail",
        "_track_idle_dorm_shift",
        "_finish_idle_dorm_shift",
    ):
        setattr(solver, method, Mock())
    solver._complete_group_shift = Mock(return_value=True)
    solver._can_refresh_idle_dorm_search = Mock(return_value=False)
    solver.ensure_dorm_recovery_order = Mock(return_value=False)
    solver.get_agent_from_room = Mock(
        side_effect=lambda room, *args, **kwargs: [
            {"agent": name} for name in solver.op_data.get_current_room(room, True)
        ]
    )
    solver.record_selection_failure = Mock()
    solver.record_selection_success = Mock()
    solver.choose_agent = Mock(side_effect=AgentSelectionNotReady("旧蓝框尚未消失"))
    monkeypatch.setattr(base_schedule, "save_exception", Mock())
    monkeypatch.setattr(
        base_schedule, "defer_dorm_before_priority_task", lambda *a: False
    )
    solver._emergency_schedule_staffing()
    task = next(task for task in solver.tasks if task.emergency_staffing)
    # 已确认的首房从剩余安排删除，保留其补偿结果。
    completed_room = next(iter(task.plan))
    confirmed = {completed_room: task.plan.pop(completed_room)}
    solver.op_data = solver.op_data.project_arrangements([confirmed])
    solver._emergency_sync_compensation(confirmed)
    original = copy.deepcopy(task.plan)
    when = task.time
    solver.task = task
    solver.infra_main()
    return SimpleNamespace(
        solver=solver,
        task=task,
        original=original,
        when=when,
        completed_room=completed_room,
        clock=scheduler.clock,
        io=scheduler.io,
    )


def test_rescue_failure_keeps_original_remaining_arrangement(failed_rescue):
    case = failed_rescue
    assert any(task is case.task for task in case.solver.tasks)
    assert case.task.plan == case.original
    assert case.task.time == case.when
    assert case.task.execution_failure["rooms"] == (next(iter(case.original)),)
    assert case.completed_room not in case.task.plan
    assert case.solver.choose_agent.call_count <= 4
    case.io.assert_not_called()


def test_unchanged_rescue_failure_yields_to_independent_work(failed_rescue):
    case, solver = failed_rescue, failed_rescue.solver
    calls = solver.choose_agent.call_count
    for _ in range(5):
        case.clock.current += timedelta(seconds=1)
        solver._resume_failed_tasks()
        solver._emergency_tick()
        assert case.task not in task_view(
            solver.tasks, TaskScope.DISPATCH, solver.op_data
        )
        assert (
            sum(
                bool(getattr(task, "emergency_staffing", False))
                for task in solver.tasks
            )
            == 1
        )
    assert solver.choose_agent.call_count == calls
    solver._emergency_read_rooms.assert_not_called()
    independent = SchedulerTask(case.clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(independent)
    solver.仓库扫描 = Mock()
    assert find_next_task(solver.tasks) is independent
    solver.task = independent
    solver.infra_main()
    solver.仓库扫描.assert_called_once()
    assert any(task is case.task for task in solver.tasks)
    assert case.task.plan == case.original


def test_saved_rescue_failure_needs_related_observation(failed_rescue):
    case, solver = failed_rescue, failed_rescue.solver
    solver.tasks = jsonpickle.decode(jsonpickle.encode(solver.tasks))
    restored = next(
        task for task in solver.tasks if getattr(task, "emergency_staffing", False)
    )
    case.clock.current += timedelta(seconds=2)
    solver._resume_failed_tasks()
    assert restored.execution_failure
    assert restored.time == case.when
    assert restored.plan == case.original
    room = next(iter(restored.plan))
    solver.op_data.room_observations = {case.completed_room: 1}
    solver._resume_failed_tasks()
    assert restored.execution_failure
    solver.op_data.room_observations[room] = 1
    solver._resume_failed_tasks()
    assert not getattr(restored, "execution_failure", None)
    assert find_next_task(solver.tasks) is restored
    assert restored.time == case.when
    assert restored.plan == case.original


@pytest.fixture
def release_failure(recovery_fixture):  # noqa: F811
    solver = recovery_fixture.solver
    state = solver.emergency_state
    # 两个到期主班分属两个宿舍，第一间确认完成后第二间读数失败。
    members = list(state["targets"])[:2]
    move = solver.op_data.get_current_room("dormitory_2", True)
    move[-1] = members[1]
    solver.op_data = solver.op_data.project_arrangements([{"dormitory_2": move}])
    state["staffing_complete"] = False
    state.pop("dorm_replan_pending", None)
    solver._emergency_save = Mock(return_value=True)

    def interrupted(plan, **kwargs):
        first = next(iter(plan))
        solver.op_data = solver.op_data.project_arrangements([{first: plan.pop(first)}])
        room = next(iter(plan))
        raise base_schedule.RoomArrangementDeferred(
            room, RuntimeError("旧蓝框尚未消失")
        )

    solver.agent_arrange = Mock(side_effect=interrupted)
    previous = solver.task
    assert solver._emergency_release_ready() is False
    assert solver.task is previous
    task = next(
        task for task in solver.tasks if getattr(task, "emergency_staffing", False)
    )
    assert list(task.plan) == ["dormitory_2"]
    return SimpleNamespace(solver=solver, task=task, members=members)


def test_retained_release_is_not_replaced_by_new_reminders(release_failure):
    solver, task = release_failure.solver, release_failure.task
    when, remaining = task.time, copy.deepcopy(task.plan)
    for _ in range(3):
        solver._emergency_replan_releases()
        assert not solver._emergency_release_ready()
        assert [
            pending
            for pending in solver.tasks
            if getattr(pending, "emergency_recovery_release", False)
        ] == [task]
        assert task.time == when
        assert task.plan == remaining
    solver.agent_arrange.assert_called_once()


@pytest.mark.parametrize("relation", ["independent", "shared_group", "shared_slot"])
@pytest.mark.parametrize("saved", [False, True])
def test_failed_release_protects_only_related_departures(
    recovery_fixture,  # noqa: F811
    relation,
    saved,
):
    solver = recovery_fixture.solver
    state = solver.emergency_state
    names = list(state["targets"])
    state["staffing_complete"] = False
    solver.op_data.operators[names[1]].mood = state["targets"][names[1]] - 1

    def fail(plan, **kwargs):
        assert set(plan) == {"dormitory_1"}
        raise base_schedule.RoomArrangementDeferred(
            "dormitory_1", RuntimeError("返回失败")
        )

    solver.agent_arrange = Mock(side_effect=fail)
    assert solver._emergency_release_ready() is False
    if saved:
        solver.tasks = jsonpickle.decode(jsonpickle.encode(solver.tasks))
    retained = next(task for task in solver.tasks if task.emergency_staffing)
    when, remaining = retained.time, copy.deepcopy(retained.plan)
    member = names[1] if relation == "shared_group" else names[2]
    if relation == "shared_slot":
        roster = solver.op_data.get_current_room("dormitory_1", True)
        roster[2] = member
        solver.op_data = solver.op_data.project_arrangements([{"dormitory_1": roster}])
    op = solver.op_data.operators[member]
    solver.op_data.update_detail(
        member, state["targets"][member], op.current_room, op.current_index, True
    )

    def complete(plan, **kwargs):
        assert set(plan) == {"dormitory_2"}
        assert state["release_plan"] == remaining | plan
        solver.op_data = solver.op_data.project_arrangements([copy.deepcopy(plan)])
        plan.clear()
        return True

    solver.agent_arrange = Mock(side_effect=complete)
    if relation == "independent":
        assert solver._emergency_release_ready()
        solver.agent_arrange.assert_called_once()
        assert not solver.op_data.operators[member].current_room
        assert member in state["ready_members"]
    else:
        assert solver._emergency_release_ready() is False
        solver.agent_arrange.assert_not_called()
        assert solver.op_data.operators[member].is_resting()
    solver.agent_arrange.reset_mock()
    for _ in range(3):
        assert solver._emergency_release_ready() is False
        assert solver.tasks == [retained]
        assert retained.time == when and retained.plan == remaining
        assert retained.execution_failure
        assert state["release_plan"] == remaining
    solver.agent_arrange.assert_not_called()


@pytest.mark.parametrize("partial", [False, True])
def test_deferred_release_survives_replanning_and_restart(recovery_fixture, partial):  # noqa: F811
    solver = recovery_fixture.solver

    def defer(plan, **kwargs):
        if partial:
            solver.op_data = solver.op_data.project_arrangements(
                [{"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]}]
            )
        return False

    solver.agent_arrange = Mock(side_effect=defer)
    solver._emergency_release_ready()
    pending = next(
        task for task in solver.tasks if getattr(task, "emergency_staffing", False)
    )
    when, remaining = pending.time, copy.deepcopy(pending.plan)
    solver._emergency_replan_releases()
    assert any(task is pending for task in solver.tasks)
    assert pending.plan == remaining
    assert pending.time == when
    solver.tasks = jsonpickle.decode(jsonpickle.encode(solver.tasks))
    restored = next(
        task for task in solver.tasks if getattr(task, "emergency_staffing", False)
    )
    solver._emergency_replan_releases()
    assert any(task is restored for task in solver.tasks)
    assert restored.plan == remaining
    assert restored.time == when
    critical = SchedulerTask(when, task_type=TaskTypes.RUN_ORDER)
    solver.tasks.append(critical)
    protect_priority_tasks(solver.tasks, time_now=when, op_data=solver.op_data)
    assert find_next_task(solver.tasks) is critical
    assert restored.plan == remaining
    assert restored.time == when


@pytest.mark.parametrize("kind", ["release", "staffing"])
@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize("shared_candidate", [False, True])
def test_failed_arrangement_allows_independent_worker_rotation(
    recovery_fixture,  # noqa: F811
    kind,
    saved,
    shared_candidate,
):
    solver = recovery_fixture.solver
    state = solver.emergency_state
    data = solver.op_data
    if kind == "release":
        data.operators[PRIMARY[1]].mood = 8
        solver.agent_arrange = Mock(
            side_effect=base_schedule.RoomArrangementDeferred(
                "dormitory_1", RuntimeError("返回失败")
            )
        )
        assert solver._emergency_release_ready() is False
    else:
        failed_room = data.operators[PRIMARY[0]].room
        data.add(Operator("芬", "", mood=24, time_stamp=NOW))
        state["rescue_plan"][failed_room] = ["芬"]
        state["staffing_plan"] = {failed_room: ["芬"]}
        state["staffing_complete"] = False
        state["takeover_complete"] = True
        failed = SchedulerTask(task_plan=copy.deepcopy(state["staffing_plan"]))
        failed.emergency_staffing = True
        failed.emergency_staffing_members = list(state["targets"])
        solver.tasks.append(failed)
        solver._retain_failed_task(failed, "选人失败", [failed_room])
    if saved:
        state, solver.tasks = jsonpickle.decode(
            jsonpickle.encode((state, solver.tasks))
        )
        solver.emergency_state = state
    retained = next(task for task in solver.tasks if task.emergency_staffing)
    when, remaining = retained.time, copy.deepcopy(retained.plan)
    temporary = copy.deepcopy(state["temporary_roster"])
    data.add(Operator("年", "", mood=24, time_stamp=NOW))
    room = data.operators[PRIMARY[2]].room
    candidate = (
        (PRIMARY[0] if kind == "release" else "芬") if shared_candidate else "年"
    )
    state["worker_replacements"] = {room: [[candidate]]}
    data.operators[COVERS[2]].mood = 0

    assert solver._emergency_schedule_staffing()

    if shared_candidate:
        assert solver.tasks == [retained]
        assert state["rescue_plan"][room] == [COVERS[2]]
        assert state["temporary_roster"] == temporary
        assert retained.time == when and retained.plan == remaining
        assert retained.execution_failure
        return
    rotation = next(
        task
        for task in solver.tasks
        if task is not retained and getattr(task, "emergency_staffing", False)
    )
    assert rotation.plan == {room: ["年"]}
    assert state["staffing_plan"] == (
        ({room: ["年"]}) if kind == "release" else remaining | {room: ["年"]}
    )
    assert state["temporary_roster"] == temporary
    for _ in range(3):
        solver._emergency_schedule_staffing()
        assert solver.tasks == [retained, rotation]
        assert retained.time == when and retained.plan == remaining
        assert retained.execution_failure

    solver.op_data = data.project_arrangements([rotation.plan])
    solver.tasks.remove(rotation)
    completed = solver._emergency_reconcile_staffing()
    assert completed == (kind == "release")
    assert state["staffing_complete"] == (kind == "release")
    assert state["staffing_plan"] == ({} if kind == "release" else remaining)
    assert solver.op_data.get_current_room(room, True) == ["年"]
    assert retained.time == when and retained.plan == remaining
    assert retained.execution_failure


@pytest.mark.parametrize("manager", ["闪灵", "菲亚梅塔"])
@pytest.mark.parametrize("boundary", ["tick", "fixed_plan"])
def test_pending_release_protects_fixed_manager_target_slot(
    recovery_fixture,  # noqa: F811
    manager,
    boundary,
):
    solver = recovery_fixture.solver
    data, state = solver.op_data, solver.emergency_state
    data.add(Operator("芬", "", mood=24, time_stamp=NOW))
    if manager not in data.operators:
        data.add(Operator(manager, "", mood=24, time_stamp=NOW))
    current = data.get_current_room("dormitory_1", True)
    data = solver.op_data = data.project_arrangements(
        [{"dormitory_1": [*current[:2], PRIMARY[1], "芬", PRIMARY[0]]}]
    )
    data.operators[PRIMARY[1]].mood = 8
    data.operators[manager]._current_room = "train"
    data.operators[manager].current_index = 1
    state["dorm_layout"] = {
        "dormitory_1": ["Free"] * 4 + [manager],
        "dormitory_2": ["Free"] * 5,
    }
    state["staffing_complete"] = False
    solver.agent_arrange = Mock(
        side_effect=base_schedule.RoomArrangementDeferred(
            "dormitory_1", RuntimeError("返回失败")
        )
    )
    assert solver._emergency_release_ready() is False
    retained = next(task for task in solver.tasks if task.emergency_staffing)
    remaining, when = copy.deepcopy(retained.plan), retained.time
    assert remaining == {"dormitory_1": ["Current"] * 4 + [""]}
    data.operators[manager]._current_room = ""
    data.operators[manager].current_index = -1
    state["staffing_complete"] = True
    solver.plan_metadata = Mock()
    solver._emergency_read_rooms = Mock(return_value=True)
    solver._emergency_collect = Mock()
    solver._emergency_update_targets = Mock()
    if boundary == "tick":
        solver._emergency_tick(completed_task=SchedulerTask(task_type=TaskTypes.DEPOT))
    else:
        data.plan["dormitory_1"][4].agent = manager
        solver._emergency_plan_beds(state)
    assert all(
        task.plan.get("dormitory_1", ["Current"] * 5)[4] == "Current"
        for task in solver.tasks
        if getattr(task, "emergency_dorm", False)
    )
    assert retained.time == when and retained.plan == remaining
    assert retained.execution_failure


@pytest.mark.parametrize("saved", [False, True])
def test_failed_release_tick_fills_independent_empty_bed(
    recovery_fixture,  # noqa: F811
    monkeypatch,
    saved,
):
    solver = recovery_fixture.solver
    state = solver.emergency_state
    names = list(state["targets"])
    solver.op_data.operators[names[1]].mood = 8
    solver.agent_arrange = Mock(
        side_effect=base_schedule.RoomArrangementDeferred(
            "dormitory_1", RuntimeError("返回失败")
        )
    )
    assert solver._emergency_release_ready() is False
    if saved:
        state, solver.tasks = jsonpickle.decode(
            jsonpickle.encode((state, solver.tasks))
        )
        solver.emergency_state = state
    retained = next(task for task in solver.tasks if task.emergency_staffing)
    when, remaining = retained.time, copy.deepcopy(retained.plan)
    roster = solver.op_data.get_current_room("dormitory_2", True)
    roster[2] = ""
    solver.op_data = solver.op_data.project_arrangements([{"dormitory_2": roster}])
    waiting = names[2]
    solver.op_data.operators[waiting].mood = 8
    clock = {"now": emergency.datetime.now()}

    class Clock(emergency.datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"]

    monkeypatch.setattr(emergency, "datetime", Clock)
    solver.plan_metadata = Mock()
    solver._emergency_read_rooms = Mock(return_value=True)
    solver._emergency_collect = Mock()
    solver._emergency_update_targets = Mock()
    solver._emergency_save = Mock(return_value=True)
    workshop = Mock()
    monkeypatch.setattr(emergency, "try_workshop_tasks", workshop)
    solver.agent_arrange.reset_mock()
    deadline = state["next_read"]

    solver._emergency_tick(completed_task=SchedulerTask(task_type=TaskTypes.DEPOT))

    fill = next(task for task in solver.tasks if getattr(task, "emergency_dorm", False))
    assert set(fill.plan) == {"dormitory_2"}
    assert waiting in fill.plan["dormitory_2"]
    assert state["release_plan"] == remaining
    assert state["next_read"] == deadline
    workshop.assert_called_once_with(solver.op_data, solver.tasks)
    solver.run_order_solver.assert_called_once()
    continuation = next(
        task for task in solver.tasks if getattr(task, "emergency_continuation", False)
    )
    continuation_time, fill_time = continuation.time, fill.time
    pending_tasks = list(solver.tasks)
    observations = solver._emergency_read_rooms.call_count
    for _ in range(3):
        clock["now"] += timedelta(minutes=1)
        solver._emergency_tick()
        assert [
            task for task in solver.tasks if getattr(task, "emergency_dorm", False)
        ] == [fill]
        assert fill.time == fill_time
        assert continuation.time == continuation_time
        assert retained.time == when and retained.plan == remaining
        assert retained.execution_failure
        assert state["next_read"] == deadline
        assert solver.tasks == pending_tasks
        assert solver._emergency_read_rooms.call_count == observations
    solver.agent_arrange.assert_not_called()

    solver.op_data = solver.op_data.project_arrangements([copy.deepcopy(fill.plan)])
    solver.tasks.remove(fill)
    solver._emergency_tick(completed_task=fill)
    assert solver.op_data.operators[waiting].current_room == "dormitory_2"
    assert retained.execution_failure and retained.plan == remaining
    assert state["release_plan"] == remaining
    assert not any(getattr(task, "emergency_dorm", False) for task in solver.tasks)
    solver.op_data.room_observations["dormitory_1"] = (
        solver.op_data.room_observations.get("dormitory_1", 0) + 1
    )
    solver._resume_failed_tasks()
    assert not getattr(retained, "execution_failure", None)
    assert retained in task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data)
    assert retained.time == when and retained.plan == remaining


@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize("shared_group", [False, True])
def test_failed_staffing_tick_fills_unreserved_primary_bed(
    recovery_fixture,  # noqa: F811
    saved,
    shared_group,
):
    solver = recovery_fixture.solver
    data, state = solver.op_data, solver.emergency_state
    for name in state["targets"]:
        data.operators[name].mood = 8
    failed_room = data.operators[PRIMARY[0]].room
    data.add(Operator("芬", "", mood=24, time_stamp=NOW))
    state["rescue_plan"][failed_room] = ["芬"]
    state["staffing_plan"] = {failed_room: ["芬"]}
    state["staffing_complete"] = False
    state["takeover_complete"] = True
    state["phase"] = "staffing"
    failed = SchedulerTask(task_plan=copy.deepcopy(state["staffing_plan"]))
    failed.emergency_staffing = True
    failed.emergency_staffing_members = list(state["targets"])
    solver.tasks.append(failed)
    solver._retain_failed_task(failed, "选人失败", [failed_room])
    if saved:
        state, solver.tasks = jsonpickle.decode(
            jsonpickle.encode((state, solver.tasks))
        )
        solver.emergency_state = state
    retained = next(task for task in solver.tasks if task.emergency_staffing)
    remaining, when = copy.deepcopy(retained.plan), retained.time
    roster = data.get_current_room("dormitory_2", True)
    roster[2] = ""
    solver.op_data = data.project_arrangements([{"dormitory_2": roster}])
    if shared_group:
        group = solver.op_data.operators[PRIMARY[2]].group
        solver.op_data.operators[COVERS[0]].group = group
        solver.op_data.groups[group].append(COVERS[0])
    solver.plan_metadata = Mock()
    solver._emergency_update_targets = Mock()
    solver._emergency_save = Mock(return_value=True)
    deadline = state["next_read"]
    solver.agent_arrange.reset_mock()

    solver._emergency_tick(completed_task=SchedulerTask(task_type=TaskTypes.DEPOT))

    if shared_group:
        assert all(
            PRIMARY[2] not in row
            for task in solver.tasks
            if getattr(task, "emergency_dorm", False)
            for row in task.plan.values()
        )
        assert retained.plan == remaining and retained.time == when
        assert retained.execution_failure
        solver.agent_arrange.assert_not_called()
        return
    fill = next(task for task in solver.tasks if getattr(task, "emergency_dorm", False))
    assert all(room.startswith("dorm") for room in fill.plan)
    assert any(PRIMARY[2] in row for row in fill.plan.values())
    assert state["staffing_plan"] == remaining
    assert retained.plan == remaining and retained.time == when
    assert retained.execution_failure
    assert state["next_read"] == deadline
    for _ in range(3):
        solver._emergency_tick()
        assert [
            task for task in solver.tasks if getattr(task, "emergency_dorm", False)
        ] == [fill]
        assert retained.plan == remaining and retained.time == when
        assert retained.execution_failure
        assert state["next_read"] == deadline
    solver.agent_arrange.assert_not_called()

    solver.op_data = solver.op_data.project_arrangements([copy.deepcopy(fill.plan)])
    solver.tasks.remove(fill)
    solver._emergency_tick(completed_task=fill)
    assert solver.op_data.operators[PRIMARY[2]].is_resting()
    assert retained.execution_failure
    solver.op_data.room_observations[failed_room] = (
        solver.op_data.room_observations.get(failed_room, 0) + 1
    )
    solver._resume_failed_tasks()
    assert retained in task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data)
    assert retained.plan == remaining and retained.time == when


def test_saved_release_reenters_real_executor_and_finishes(
    release_failure, scheduler, monkeypatch
):
    source = release_failure.solver
    solver = scheduler.solver
    solver.op_data = source.op_data
    solver.emergency_state = source.emergency_state
    solver.tasks = jsonpickle.decode(jsonpickle.encode(source.tasks))
    restored = next(
        task for task in solver.tasks if getattr(task, "emergency_staffing", False)
    )
    when = restored.time
    solver._resume_failed_tasks()
    assert restored.execution_failure
    room = next(iter(restored.plan))
    solver.op_data.room_observations = {room: 1}
    solver._resume_failed_tasks()
    assert not getattr(restored, "execution_failure", None)
    scheduler.clock.current = when + timedelta(seconds=1)
    solver.emergency_state["staffing_complete"] = True
    solver.emergency_state["next_read"] = scheduler.clock.now() + timedelta(hours=1)
    original_read_time = solver.emergency_state["next_read"]
    solver.last_execution = source.last_execution
    solver._emergency_save = Mock(return_value=True)
    solver._emergency_update_targets = Mock()
    solver._emergency_ready = Mock(return_value=False)
    solver._emergency_schedule_staffing = Mock(return_value=True)
    solver._emergency_plan_beds = Mock()
    solver._open_emergency_beds = Mock()
    solver.run_order_solver = Mock()
    monkeypatch.setattr(emergency, "try_workshop_tasks", Mock())
    for method in (
        "_prepare_shift_cycle",
        "_prepare_group_shift",
        "_switch_products_before_arrangement",
        "_defer_conflicting_product_shift_slots",
        "plan_metadata",
    ):
        setattr(solver, method, Mock())
    solver._complete_group_shift = Mock(return_value=True)

    def complete(plan, *args, **kwargs):
        solver.op_data = solver.op_data.project_arrangements([plan])
        plan.clear()
        return True

    solver.agent_arrange = Mock(side_effect=complete)
    solver.task = restored
    solver.infra_main()
    solver.agent_arrange.assert_called_once()
    assert not restored.plan
    assert all(task is not restored for task in solver.tasks)
    assert restored.time == when
    for member in release_failure.members:
        assert not solver.op_data.operators[member].current_room
        assert member in solver.emergency_state["ready_members"]
    assert "release_plan" not in solver.emergency_state
    assert "release_members" not in solver.emergency_state
    assert solver.emergency_state["next_read"] == original_read_time
    solver._emergency_plan_beds.assert_called_once_with(solver.emergency_state)


@pytest.mark.parametrize("error", ["cancel", "device", "shared_adb", "save"])
def test_release_keeps_control_errors_and_restores_current_task(
    recovery_fixture,  # noqa: F811
    error,
):
    from arknights_mower.utils.csleep import MowerExit
    from arknights_mower.utils.device.adb_client.server import SharedADBError
    from arknights_mower.utils.device.recovery import DeviceRecoveryError

    solver = recovery_fixture.solver
    previous = SchedulerTask()
    solver.task = previous
    failure = {
        "cancel": MowerExit(),
        "device": DeviceRecoveryError("offline"),
        "shared_adb": SharedADBError("offline"),
        "save": RuntimeError("save failed"),
    }[error]
    if error == "save":
        # 首次保存是现有状态，第二次保存时原任务已入队。
        solver._emergency_save = Mock(side_effect=[True, failure, failure])
    else:
        solver.agent_arrange = Mock(side_effect=failure)
    with pytest.raises(type(failure)):
        solver._emergency_release_ready()
    assert solver.task is previous
    if error != "save":
        assert not any(
            getattr(task, "execution_failure", None) for task in solver.tasks
        )
