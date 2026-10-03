"""整组替班选择失败后保留未完成义务，以实测候选重新完整匹配。"""

import copy
import pickle
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, emergency
from arknights_mower.solvers.base_mixin import AgentSelectionNotReady
from arknights_mower.tests.emergency_group_return_tests import (
    group_return as recovery_fixture,  # noqa: F401
)
from arknights_mower.tests.emergency_group_return_tests import (
    legacy_solver as legacy_solver,
)
from arknights_mower.tests.emergency_group_staffing_tests import (
    staffing as staffing,  # noqa: F401
)
from arknights_mower.tests.emergency_group_staffing_tests import staffing_task
from arknights_mower.tests.mass_mood_recovery_tests import NOW, PRIMARY
from arknights_mower.utils.emergency_staffing import StaffingCandidate
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


def reject_room(solver, task, room, monkeypatch):
    solver.task = task
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    solver.find = MagicMock(return_value=True)
    solver.choose_agent = MagicMock(
        side_effect=AgentSelectionNotReady("心情不足或无法读取")
    )
    solver.back_to_infrastructure = MagicMock()
    solver._emergency_read_rooms = MagicMock()
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    assert solver.agent_arrange_room({}, room, task.plan) is False
    assert not task.plan
    solver.tasks.remove(task)
    solver.task = None


def prepare_pending(staffing, monkeypatch, *, partial=False):
    solver = staffing.solver
    assert solver._emergency_schedule_staffing()
    task = staffing_task(solver)
    rooms = [solver.op_data.operators[name].room for name in PRIMARY[:2]]
    original = copy.deepcopy(staffing.state["staffing_plan"])
    if partial:
        dorm = ["Current"] * 5
        dorm[2] = PRIMARY[0]
        completed = {rooms[0]: task.plan[rooms[0]], "dormitory_1": dorm}
        solver.op_data = solver.op_data.project_arrangements([completed])
        task.plan.pop(rooms[0])
        staffing.state["staffing_plan"].pop(rooms[0])
    failed_room = rooms[1] if partial else rooms[0]
    rejected = task.plan[failed_room][0]
    reject_room(solver, task, failed_room, monkeypatch)
    return rooms, original, rejected


def replacement_candidates(rejected, *, missing=False):
    candidates = [StaffingCandidate("赫默", 24, ()), StaffingCandidate("火神", 24, ())]
    if not missing:
        candidates.append(StaffingCandidate(rejected, 0, ()))
    return candidates


def test_rejection_stops_remaining_task_and_marks_persisted_group_for_rescore(
    staffing, monkeypatch
):
    rooms, original, _ = prepare_pending(staffing, monkeypatch)
    assert staffing.state["staffing_plan"] == original
    assert staffing.solver.task is None
    assert staffing.state["staffing_rescore"]
    assert staffing.state["next_read"] == NOW
    assert set(staffing.state["staffing_members"]) == set(PRIMARY[:2])
    assert not any(
        getattr(task, "emergency_staffing", False) for task in staffing.solver.tasks
    )


@pytest.mark.parametrize("missing", [False, True])
def test_replan_replaces_low_mood_or_missing_candidate_before_group_leaves(
    staffing, monkeypatch, missing
):
    solver = staffing.solver
    rooms, original, rejected = prepare_pending(staffing, monkeypatch)
    solver._emergency_scan_workers = MagicMock(
        return_value=replacement_candidates(rejected, missing=missing)
    )

    assert solver._emergency_schedule_staffing()

    task = staffing_task(solver)
    assert rejected not in {name for room in rooms for name in task.plan[room]}
    assert task.plan["dormitory_1"] == original["dormitory_1"]
    assert solver._emergency_scan_workers.call_count == 2
    assert all(
        not call.kwargs["fixed"]
        for call in solver._emergency_scan_workers.call_args_list
    )
    assert set(task.emergency_staffing_members) == {"塑心", *PRIMARY[:2]}
    assert not staffing.state.get("staffing_rescore")
    projected = solver.op_data.project_arrangements([task.plan])
    assert all(projected.operators[name].is_resting() for name in PRIMARY[:2])


@pytest.mark.parametrize("restart", [False, True])
def test_partial_group_replan_and_restart_keep_unfinished_dorm_obligation(
    staffing, monkeypatch, restart
):
    solver = staffing.solver
    rooms, original, rejected = prepare_pending(staffing, monkeypatch, partial=True)
    if restart:
        solver.emergency_state = pickle.loads(pickle.dumps(staffing.state))
    solver._emergency_scan_workers = MagicMock(
        return_value=replacement_candidates(rejected)
    )

    assert solver.op_data.operators[PRIMARY[0]].is_resting()
    assert solver.op_data.operators[PRIMARY[1]].is_working()
    assert solver._emergency_schedule_staffing()

    task = staffing_task(solver)
    assert task.plan[rooms[1]][0] != rejected
    assert task.plan["dormitory_1"] == original["dormitory_1"]
    assert set(task.emergency_staffing_members) == {"塑心", *PRIMARY[:2]}
    projected = solver.op_data.project_arrangements([task.plan])
    assert all(projected.operators[name].is_resting() for name in PRIMARY[:2])


def test_replan_shortage_retains_group_state_without_replaying_bad_candidate(
    staffing, monkeypatch
):
    solver = staffing.solver
    _, original, rejected = prepare_pending(staffing, monkeypatch)
    solver._emergency_scan_workers = MagicMock(
        return_value=[StaffingCandidate(rejected, 0, ())]
    )

    assert not solver._emergency_schedule_staffing()
    assert not solver._emergency_schedule_staffing()

    assert staffing.state["staffing_plan"] == original
    assert staffing.state["staffing_rescore"]
    assert set(staffing.state["staffing_members"]) == set(PRIMARY[:2])
    assert not any(getattr(task, "emergency_staffing", False) for task in solver.tasks)
    assert solver._emergency_scan_workers.call_count == 2


def test_tick_reconciles_partial_progress_and_repairs_instead_of_requeueing(
    staffing, monkeypatch
):
    solver = staffing.solver
    rooms, _, rejected = prepare_pending(staffing, monkeypatch, partial=True)
    solver._emergency_scan_workers = MagicMock(
        return_value=replacement_candidates(rejected)
    )
    solver.plan_metadata = MagicMock()
    solver._emergency_collect = MagicMock()
    solver._emergency_update_targets = MagicMock()
    solver._emergency_release_ready = MagicMock()
    solver._emergency_ready = MagicMock(return_value=False)
    solver._emergency_plan_beds = MagicMock()
    monkeypatch.setattr(emergency, "try_workshop_tasks", MagicMock())

    solver._emergency_tick()

    task = staffing_task(solver)
    assert task.plan[rooms[1]][0] != rejected
    assert solver._emergency_scan_workers.call_count == 2
    assert set(task.emergency_staffing_members) == {"塑心", *PRIMARY[:2]}


def test_dorm_only_unfinished_plan_still_requeues_after_successful_rescore(staffing):
    solver = staffing.solver
    state = staffing.state
    state["staffing_plan"] = {
        "dormitory_1": ["Current", "Current", PRIMARY[0], "Current", "Current"]
    }
    state["staffing_members"] = [PRIMARY[0]]
    state["staffing_rescore"] = True
    solver._emergency_scan_workers.reset_mock()

    assert solver._emergency_schedule_staffing()

    assert staffing_task(solver).plan == state["staffing_plan"]
    assert not state.get("staffing_rescore")
    solver._emergency_scan_workers.assert_not_called()


@pytest.mark.parametrize("existing", [False, True])
def test_episode_reserves_pending_members_without_polling_task(
    staffing, monkeypatch, existing
):
    solver = staffing.solver
    state = staffing.state
    state["phase"] = "recovering"
    state["next_read"] = NOW + timedelta(minutes=5)
    state["staffing_members"] = ["塑心", *PRIMARY[:2]]
    state["release_members"] = list(PRIMARY[2:3])
    state["ready_members"] = list(PRIMARY[3:])
    solver.plan_metadata = MagicMock()
    solver.tasks = (
        [SchedulerTask(time=NOW, meta_data=emergency.RESUME_META)] if existing else []
    )
    observed = []

    def workshop(data, tasks):
        observed.append(set(data.emergency_reserved_agents))

    monkeypatch.setattr(emergency, "try_workshop_tasks", workshop)
    solver._emergency_update_targets = MagicMock()
    solver._emergency_release_ready = MagicMock()
    solver._emergency_ready = MagicMock(return_value=False)
    solver._emergency_schedule_staffing = MagicMock(return_value=True)
    solver._emergency_plan_beds = MagicMock()
    for name in state["ready_members"]:
        op = solver.op_data.operators[name]
        op._current_room, op.current_index = "", -1
        op.mood, op.time_stamp = 24, NOW
    completed = SchedulerTask(task_type=TaskTypes.WORKSHOP)
    solver._emergency_tick(completed_task=completed)
    assert observed == [{"塑心", *PRIMARY}]
    state.pop("staffing_members")
    state.pop("release_members")
    state.pop("ready_members")
    solver._emergency_tick(completed_task=completed)
    assert observed[-1] == set()
    assert solver.op_data.emergency_reserved_agents == set()


def test_release_failure_preserves_personal_obligation_without_staffing_rescore(
    recovery_fixture,  # noqa: F811
    monkeypatch,
):
    solver = recovery_fixture.solver
    state = recovery_fixture.state
    room = "dormitory_1"
    plan = {room: ["Current", "Current", "", "Current", "Current"]}
    state["release_plan"] = copy.deepcopy(plan)
    state["release_members"] = [PRIMARY[0]]
    task = SchedulerTask(task_plan=copy.deepcopy(plan))
    task.emergency_staffing = True
    task.emergency_recovery_release = True
    task.emergency_staffing_members = [PRIMARY[0]]
    solver.tasks.append(task)
    solver.refresh_current_room = MagicMock()
    solver.prepare_dorm_selection = MagicMock(return_value=None)

    reject_room(solver, task, room, monkeypatch)

    assert state["release_plan"] == plan
    assert state["release_members"] == [PRIMARY[0]]
    assert not state.get("staffing_rescore")
    assert not state.get("staffing_plan")
    assert solver.op_data.operators[PRIMARY[0]].is_resting()


def test_direct_release_task_reserves_only_ready_individuals(recovery_fixture):  # noqa: F811
    solver = recovery_fixture.solver
    observed = []

    def arrange(plan, **kwargs):
        observed.append(
            (
                list(solver.task.emergency_staffing_members),
                solver.task.emergency_recovery_release,
            )
        )
        assert all(room.startswith("dorm") for room in plan)
        recovery_fixture.place(plan, **kwargs)

    solver.agent_arrange = arrange
    assert solver._emergency_release_ready()
    assert len(observed) == 1
    assert set(observed[0][0]) == set(PRIMARY[:2])
    assert observed[0][1]
