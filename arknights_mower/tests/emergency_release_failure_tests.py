"""救急失败停止房间遍历，实测失效的已离宿主班可重新入宿。"""

import pickle
from types import SimpleNamespace
from unittest.mock import MagicMock

from arknights_mower.solvers import base_schedule, emergency
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
from arknights_mower.tests.mass_mood_recovery_tests import PRIMARY
from arknights_mower.utils.emergency_recovery import emergency_dorm_plan
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
        _, bed = solver.op_data.get_dorm_by_name(name)
        if bed is not None:
            bed.reset()
        solver.op_data.operators[name].current_room = ""
        solver.op_data.operators[name].current_index = -1
        return [{"agent": member} for member in actual]

    solver.enter_room = MagicMock()
    solver.back = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver.get_agent_from_room = MagicMock(side_effect=read_actual)
    assert solver._emergency_read_rooms([room])
    assert not solver.op_data.operators[name].current_room
    assert solver.op_data.operators[name].time_stamp is None
    assert name in state["release_members"]
    check = SchedulerTask(meta_data=emergency.CHECK_META)
    check.emergency_staffing_members = state["release_members"]
    solver.tasks = [check]
    solver._emergency_operation_fits.return_value = True
    solver._emergency_release_ready()
    assert "release_plan" not in state
    assert "release_members" not in state
    assert name not in state.get("ready_members", ())
    assert name not in check.emergency_staffing_members
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
