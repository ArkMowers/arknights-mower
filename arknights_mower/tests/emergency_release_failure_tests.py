"""救急失败停止房间遍历，实测失效的已离宿主班可重新入宿。"""

import pickle
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.solvers.base_mixin import AgentSelectionNotReady
from arknights_mower.tests.emergency_group_return_tests import (
    group_return as group_return,
)
from arknights_mower.tests.emergency_group_return_tests import (
    group_return as recovery_fixture,  # noqa: F401
)
from arknights_mower.tests.emergency_group_return_tests import (
    legacy_solver as legacy_solver,
)
from arknights_mower.tests.emergency_group_staffing_tests import staffing as staffing
from arknights_mower.tests.emergency_group_staffing_tests import staffing_task
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.emergency_recovery import (
    emergency_dorm_plan,
    recovery_target,
)
from arknights_mower.utils.scheduler_task import SchedulerTask


def test_multiroom_staffing_failure_must_stop_outer_arrangement(staffing, monkeypatch):
    solver = staffing.solver
    assert solver._emergency_schedule_staffing()
    task = staffing_task(solver)
    solver.task = task
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    solver._track_idle_dorm_shift = MagicMock()
    solver._finish_idle_dorm_shift = MagicMock()
    solver.find = MagicMock(return_value=True)
    solver.choose_agent = MagicMock(
        side_effect=AgentSelectionNotReady("candidate unavailable")
    )
    solver.back_to_infrastructure = MagicMock()
    solver.back = MagicMock()
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver._emergency_read_rooms = MagicMock()
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    monkeypatch.setattr(
        base_schedule, "defer_dorm_before_priority_task", lambda *args: False
    )
    assert (
        base_schedule.BaseSchedulerSolver.agent_arrange(
            solver, task.plan, get_time=True
        )
        is False
    )
    assert solver.enter_room.call_count == 1


def test_uncertain_departure_retains_reachable_recovery_obligation(group_return):
    solver = group_return.solver
    state = solver.emergency_state
    name = PRIMARY[0]
    solver.op_data.operators[PRIMARY[1]].mood = 8
    solver._emergency_operation_fits = MagicMock(return_value=False)
    solver._emergency_release_ready()
    solver.emergency_state = pickle.loads(pickle.dumps(state))
    solver.op_data = pickle.loads(pickle.dumps(solver.op_data))
    state = solver.emergency_state
    room = solver.op_data.operators[name].current_room
    actual = solver.op_data.get_current_room(room, True)
    actual[solver.op_data.operators[name].current_index] = ""

    def read_actual(target_room, *args, **kwargs):
        observed = [{"agent": member} for member in actual]
        solver._reconcile_room_observation(target_room, observed)
        return observed

    solver.enter_room = MagicMock()
    solver.back = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver.get_agent_from_room = MagicMock(side_effect=read_actual)
    assert solver._emergency_read_rooms([room])
    assert not solver.op_data.operators[name].current_room
    assert solver.op_data.operators[name].time_stamp is None
    assert name in state["release_members"]
    solver._emergency_sync_reservations()
    solver.tasks = []
    solver._emergency_operation_fits.return_value = True
    solver._emergency_release_ready()
    assert "release_plan" not in state
    assert "release_members" not in state
    assert name not in state.get("ready_members", ())
    assert name not in solver.op_data.emergency_reserved_agents
    assert not solver._emergency_ready()
    control_plan = emergency_dorm_plan(solver.op_data, state, [])
    assert name in {member for row in control_plan.values() for member in row}
    recovery_plan = emergency_dorm_plan(solver.op_data, state, solver.tasks)
    assert name in {member for row in recovery_plan.values() for member in row}


def test_high_need_restored_manager_flags_and_real_order_planning(staffing):
    from arknights_mower.utils.dorm_recovery import recovery_order_plan

    solver = staffing.solver
    solver._open_emergency_beds()
    assert all(
        not operator.single_recovery_manager
        for operator in solver.op_data.operators.values()
        if operator.room.startswith("dorm")
        and solver.op_data.plan[operator.room][operator.index].agent == "Free"
    )
    room = "dormitory_1"
    assert (
        recovery_order_plan(
            solver.op_data, room, [*PRIMARY[:2], "Current", "Current", "Current"]
        )
        is None
    )


def test_multiroom_release_failure_must_stop_outer_arrangement(
    group_return, monkeypatch
):
    solver = group_return.solver
    for name in PRIMARY:
        solver.op_data.operators[name].mood = solver.emergency_state["targets"][name]
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver.prepare_dorm_selection = MagicMock(return_value=[])
    solver.refresh_current_room = MagicMock()
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    solver._track_idle_dorm_shift = MagicMock()
    solver._finish_idle_dorm_shift = MagicMock()
    solver.find = MagicMock(return_value=True)
    solver.choose_agent = MagicMock(
        side_effect=AgentSelectionNotReady("candidate unavailable")
    )
    solver.back_to_infrastructure = MagicMock()
    solver.back = MagicMock()
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver._emergency_read_rooms = MagicMock()
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    monkeypatch.setattr(
        base_schedule, "defer_dorm_before_priority_task", lambda *args: False
    )
    solver.agent_arrange = base_schedule.BaseSchedulerSolver.agent_arrange.__get__(
        solver
    )
    solver._emergency_release_ready()
    assert solver.enter_room.call_count == 1
    assert solver.task is None


@pytest.mark.parametrize("recalculate", [True, False])
def test_pending_admission_does_not_reinsert_newly_ready_idle_primary(
    group_return, monkeypatch, recalculate
):
    solver = group_return.solver
    # 本用例验证清退与补床；正常交接另有独立契约用例。
    solver._emergency_ready = MagicMock(return_value=False)
    state = solver.emergency_state
    name = PRIMARY[0]
    operator = solver.op_data.operators[name]
    operator.current_room, operator.current_index = "", -1
    for bed in solver.op_data.all_dorms():
        if bed.name == name:
            bed.reset()
    operator.mood, operator.time_stamp, operator.mood_is_prediction = 17, NOW, False
    state["targets"][name], state["target_sources"][name] = recovery_target(
        solver.op_data, name, rate=2, opportunity=NOW + timedelta(hours=4), now=NOW
    )
    assert state["target_sources"][name] == "history"
    solver._open_emergency_beds()
    solver._emergency_plan_beds(state)
    fill = next(task for task in solver.tasks if getattr(task, "emergency_dorm", False))
    assert any(name in row for row in fill.plan.values())
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    fill = next(task for task in solver.tasks if getattr(task, "emergency_dorm", False))
    state["next_read"] = NOW
    state["observed_at"] = NOW
    if not recalculate:
        solver._emergency_update_targets = MagicMock()
    solver._emergency_tick()
    if recalculate:
        assert state["targets"][name] < operator.mood
        assert name in state["ready_members"]
        assert fill not in solver.tasks
        assert not fill.plan
        assert all(
            name not in row
            for task in solver.tasks
            if getattr(task, "emergency_dorm", False)
            for row in task.plan.values()
        )
        return
    else:
        assert state["targets"][name] > operator.mood
        assert name not in state.get("ready_members", ())
    assert fill in solver.tasks
    solver.task = fill
    for room, row in fill.plan.items():
        base_schedule.BaseSchedulerSolver.prepare_dorm_selection(solver, row, room)
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver.refresh_current_room = MagicMock()
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    solver._track_idle_dorm_shift = MagicMock()
    solver._finish_idle_dorm_shift = MagicMock()
    solver.find = MagicMock(return_value=True)
    solver.choose_agent = MagicMock(side_effect=MowerExit("offline selection boundary"))
    solver.back_to_infrastructure = MagicMock()
    solver.back = MagicMock()
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    monkeypatch.setattr(
        base_schedule, "defer_dorm_before_priority_task", lambda *args: False
    )
    with pytest.raises(MowerExit, match="offline selection boundary"):
        base_schedule.BaseSchedulerSolver.agent_arrange(
            solver, fill.plan, get_time=True
        )
    selected = solver.choose_agent.call_args.args[0]
    assert name in selected, {
        "ready": state["ready_members"],
        "target": state["targets"][name],
        "mood": operator.mood,
        "dispatched": selected,
    }


def test_deferred_release_prunes_queued_admission_before_budget_return(group_return):
    solver = group_return.solver
    state = solver.emergency_state
    solver._open_emergency_beds()
    task = SchedulerTask(
        task_plan={
            "dormitory_2": ["Current", "Current", PRIMARY[0], PRIMARY[2], "Current"]
        }
    )
    task.emergency_dorm = True
    solver.tasks.append(task)
    solver._emergency_operation_fits = MagicMock(return_value=False)
    solver._emergency_release_ready()
    assert task.plan["dormitory_2"][2] == "Current"
    assert task.plan["dormitory_2"][3] == PRIMARY[2]
    assert PRIMARY[0] in state["release_members"]
    assert not state.get("ready_members")
    solver.agent_arrange.assert_not_called()


@pytest.mark.parametrize("failure", ["exception", "incomplete"])
def test_release_failure_retains_observation_dependency_before_distant_order(
    group_return, failure
):
    from arknights_mower.solvers.emergency import RESUME_META
    from arknights_mower.utils.scheduler_task import TaskTypes

    solver = group_return.solver
    original_task = solver.task
    distant = SchedulerTask(
        time=NOW + timedelta(hours=4), task_type=TaskTypes.RUN_ORDER
    )
    solver.tasks.append(distant)
    if failure == "exception":
        solver.agent_arrange = MagicMock(side_effect=RuntimeError("selection failed"))
        with pytest.raises(RuntimeError, match="selection failed"):
            solver._emergency_release_ready()
    else:
        solver.agent_arrange = MagicMock(return_value=False)
        solver._emergency_release_ready()
    assert solver.task is original_task
    assert solver.emergency_state["release_members"]
    retry = next(t for t in solver.tasks if t.meta_data == RESUME_META)
    assert retry.time == NOW
    assert retry.execution_failure["dependency"]
    assert distant in solver.tasks


def test_middle_bed_departure_matches_game_compaction(group_return):
    solver = group_return.solver
    survivor = solver.op_data.operators[PRIMARY[1]]
    survivor.mood = 8

    def arrange(plan, **kwargs):
        for room, row in plan.items():
            if "" in row:
                assert all(not name for name in row[row.index("") :])
        return group_return.place(plan, **kwargs)

    solver.agent_arrange = arrange
    assert solver._emergency_release_ready()
    assert solver.op_data.operators[PRIMARY[0]].current_room == ""
    assert solver.op_data.operators[PRIMARY[1]].current_index == 2
    assert "release_members" not in solver.emergency_state


def test_dorm_compaction_keeps_fiammetta_position(group_return):
    from arknights_mower.utils.dorm_recovery import compact_dorm_vacancies

    plan = {"dormitory_1": ["塑心", "", "菲亚梅塔", "银灰", ""]}
    compact_dorm_vacancies(group_return.solver.op_data, plan)
    assert plan["dormitory_1"] == ["塑心", "Free", "菲亚梅塔", "银灰", ""]


def release_room_readback(solver, monkeypatch):
    """隔离选人及读屏，保留救急离宿、房间安排和驻员核对。"""
    actual = {
        room: solver.op_data.get_current_room(room, True)
        for room in solver.op_data.plan
    }
    chosen = {}
    solver.agent_arrange = base_schedule.BaseSchedulerSolver.agent_arrange.__get__(
        solver
    )
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver.prepare_dorm_selection = MagicMock(return_value=None)
    solver.find = MagicMock(return_value=True)
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver.waiting_scene = []
    solver.back = MagicMock()
    solver.record_selection_success = MagicMock()
    monkeypatch.setattr(
        base_schedule, "defer_dorm_before_priority_task", lambda *args: False
    )

    def choose(row, room, **kwargs):
        assert "Free" not in row
        chosen[room] = list(row)

    solver.choose_agent = MagicMock(side_effect=choose)
    solver.tap_confirm = MagicMock(
        side_effect=lambda room, previous: actual.update({room: chosen[room]})
    )

    def read(room, *args, **kwargs):
        for index, name in enumerate(actual[room]):
            if name:
                operator = solver.op_data.operators[name]
                solver.op_data.update_detail(name, operator.mood, room, index, True)
        observed = [{"agent": name} for name in actual[room]]
        solver._reconcile_room_observation(room, observed)
        return observed

    solver.get_agent_from_room = MagicMock(side_effect=read)


@pytest.mark.parametrize("combined_fill", [False, True])
def test_measured_release_readback_keeps_primary_reserved_without_readmission(
    group_return, monkeypatch, combined_fill
):
    solver, state = group_return.solver, group_return.state
    name, partner = PRIMARY[:2]
    solver.op_data.operators[name].depletion_rate = -2
    solver.op_data.operators[partner].mood = 8
    if combined_fill:
        waiting = solver.op_data.operators[PRIMARY[2]]
        waiting._current_room, waiting.current_index = "", -1
        for bed in solver.op_data.all_dorms():
            if bed.name == waiting.name:
                bed.reset()
    release_room_readback(solver, monkeypatch)

    assert solver._emergency_release_ready()

    operator = solver.op_data.operators[name]
    assert not operator.current_room
    assert operator.mood == state["targets"][name]
    assert operator.time_stamp == NOW
    assert not operator.mood_is_prediction
    assert operator.depletion_rate == 0
    assert name in state["ready_members"]
    assert name in solver.op_data.emergency_reserved_agents
    assert solver.op_data.operators[partner].is_resting()
    if combined_fill:
        assert solver.op_data.operators[PRIMARY[2]].is_resting()

    solver.choose_agent.reset_mock()
    for _ in range(2):
        solver._emergency_release_ready()
        solver._open_emergency_beds()
        solver._emergency_plan_beds(state)
        assert all(
            name not in row
            for task in solver.tasks
            if getattr(task, "emergency_dorm", False)
            for row in task.plan.values()
        )
    solver.choose_agent.assert_not_called()


@pytest.mark.parametrize(
    "unconfirmed",
    [
        "ordinary_read",
        "unlisted",
        "prediction",
        "unknown",
        "below_target",
        "partial",
        "mismatch",
    ],
)
def test_unconfirmed_release_readback_still_invalidates_old_measurement(
    group_return, unconfirmed
):
    solver, state = group_return.solver, group_return.state
    name = PRIMARY[0]
    operator = solver.op_data.operators[name]
    room = operator.current_room
    row = solver.op_data.get_current_room(room, True)
    row[operator.current_index] = ""
    task = SchedulerTask(task_plan={room: row.copy()})
    task.emergency_staffing = True
    task.emergency_recovery_release = unconfirmed != "ordinary_read"
    task.emergency_staffing_members = [] if unconfirmed == "unlisted" else [name]
    solver.task = task
    if unconfirmed == "prediction":
        operator.mood_is_prediction = True
    elif unconfirmed == "unknown":
        operator.time_stamp = None
    elif unconfirmed == "below_target":
        operator.mood = state["targets"][name] - 0.1
    elif unconfirmed == "mismatch":
        row[-1] = COVERS[0]
    observed = [{"agent": member} for member in row]
    if unconfirmed == "partial":
        observed[0]["observed"] = False

    solver._reconcile_room_observation(room, observed)

    assert not operator.current_room
    assert operator.time_stamp is None
    assert name not in state.get("ready_members", ())
