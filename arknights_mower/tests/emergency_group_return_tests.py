"""智能救急按个人实测目标释放床位，退出时统一恢复工作岗位。"""

import copy
import pickle
from collections import defaultdict, deque
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import emergency, record
from arknights_mower.tests.automatic_rescue_tests import make_episode
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import (
    solver as legacy_solver,  # noqa: F401
)
from arknights_mower.utils import emergency_recovery, operation_timing
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def group_return(legacy_solver, monkeypatch):  # noqa: F811
    solver = legacy_solver

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(record, "save_agent_action", MagicMock())
    monkeypatch.setattr(emergency, "datetime", Clock)
    monkeypatch.setattr(emergency_recovery, "datetime", Clock)
    monkeypatch.setattr(
        operation_timing, "_dorm_durations", defaultdict(lambda: deque(maxlen=8))
    )
    monkeypatch.setattr(emergency, "emergency_mood_history", lambda name: [])
    monkeypatch.setattr(emergency, "try_workshop_tasks", MagicMock())
    data = Operators(
        {
            "default_plan": Plan(
                {
                    **{
                        f"room_1_{index + 1}" if index < 3 else "room_2_1": [
                            Room(
                                name,
                                "先恢复" if index < 2 else "后恢复",
                                [COVERS[index]],
                            )
                        ]
                        for index, name in enumerate(PRIMARY)
                    },
                    "dormitory_1": [
                        Room("塑心", "先恢复", ["黑角"]),
                        Room("冰酿", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                    "dormitory_2": [
                        Room("闪灵", "", []),
                        Room("白面鸮", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig("", "", "", resting_priority_replacement=",".join(COVERS)),
            ),
            "backup_plans": [],
        }
    )
    assert data.init_and_validate() is None
    for op in data.operators.values():
        op.mood, op.time_stamp, op.depletion_rate = 24, NOW, 0
        op._current_room, op.current_index = op.room, op.index
    solver.op_data = data
    state = make_episode(solver)
    state["targets"][PRIMARY[1]] = 18
    roster = {
        data.operators[name].room: [COVERS[index]] for index, name in enumerate(PRIMARY)
    }
    roster.update(
        {
            "dormitory_1": ["塑心", "冰酿", *PRIMARY[:2], ""],
            "dormitory_2": ["闪灵", "白面鸮", *PRIMARY[2:], ""],
        }
    )
    data = data.project_arrangements([roster])
    solver.op_data = data
    for index, name in enumerate(PRIMARY):
        op = data.operators[name]
        data.update_detail(
            name,
            state["targets"][name] if index < 2 else 8,
            op.current_room,
            op.current_index,
            True,
        )
    state["temporary_roster"] = {
        room: data.get_current_room(room, True)
        for room in data.plan
        if not room.startswith("dorm")
    }
    plans, saves = [], []

    def place(plan, **kwargs):
        plans.append(copy.deepcopy(plan))
        solver.op_data = solver.op_data.project_arrangements([plan])
        plan.clear()
        return True

    def save():
        saves.append(
            {
                "state": copy.deepcopy(solver.emergency_state),
                "rooms": {
                    room: solver.op_data.get_current_room(room, True)
                    for room in solver.op_data.plan
                },
            }
        )

    solver.agent_arrange = MagicMock(side_effect=place)
    solver._emergency_save = MagicMock(side_effect=save)
    solver.backup_plan_solver = MagicMock(
        side_effect=AssertionError("智能救急恢复中不能切换副表")
    )
    solver.agent_get_mood = MagicMock(
        side_effect=AssertionError("智能救急离宿待命不能触发普通纠错")
    )
    solver.run_order_solver = MagicMock()
    return SimpleNamespace(
        solver=solver, state=state, plans=plans, saves=saves, place=place
    )


def assert_temporary_workers_unchanged(solver):
    for index, name in enumerate(PRIMARY):
        room = solver.op_data.operators[name].room
        assert solver.op_data.get_current_room(room, True) == [COVERS[index]]


def assert_waiting(solver, names):
    for name in names:
        op = solver.op_data.operators[name]
        assert (op.current_room, op.current_index) == ("", -1)
        assert not op.is_working()
        assert not op.is_resting()


def test_individual_measured_target_releases_without_waiting_for_bound_partner(
    group_return,
):
    episode, solver = group_return, group_return.solver
    second = solver.op_data.operators[PRIMARY[1]]
    second.mood = episode.state["targets"][second.name] - 0.1

    assert solver._emergency_release_ready()

    assert_waiting(solver, PRIMARY[:1])
    assert solver.op_data.operators[PRIMARY[1]].is_resting()
    assert set(episode.state["ready_members"]) == set(PRIMARY[:1])
    assert set(episode.state["targets"]) == set(PRIMARY)
    assert_temporary_workers_unchanged(solver)
    assert len(episode.plans) == 1
    assert all(room.startswith("dorm") for room in episode.plans[0])
    assert not episode.state.get("staffing_rescore")
    solver.backup_plan_solver.assert_not_called()
    solver.agent_get_mood.assert_not_called()
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize(
    "unready", ["below_target", "prediction", "missing_measurement"]
)
def test_unconfirmed_individual_stays_resting_while_ready_partner_leaves(
    group_return, unready
):
    solver = group_return.solver
    op = solver.op_data.operators[PRIMARY[1]]
    if unready == "below_target":
        op.mood = group_return.state["targets"][op.name] - 0.1
    elif unready == "prediction":
        op.mood_is_prediction = True
    else:
        op.time_stamp = None

    assert solver._emergency_release_ready()

    assert_waiting(solver, PRIMARY[:1])
    assert solver.op_data.operators[PRIMARY[1]].is_resting()
    assert PRIMARY[1] not in solver.emergency_state["ready_members"]
    assert_temporary_workers_unchanged(solver)


def test_ready_residents_leave_in_one_dorm_arrangement_without_return_or_rescore(
    group_return,
):
    episode, solver = group_return, group_return.solver

    assert solver._emergency_release_ready()

    assert_waiting(solver, PRIMARY[:2])
    assert set(episode.state["ready_members"]) == set(PRIMARY[:2])
    assert len(episode.plans) == 1
    assert set(episode.plans[0]) == {"dormitory_1"}
    assert solver.op_data.get_current_room("dormitory_1", True)[2:4] == ["", ""]
    assert solver.emergency_state is episode.state
    assert episode.state["phase"] == "recovering"
    assert not episode.state.get("staffing_rescore")
    assert_temporary_workers_unchanged(solver)
    assert all(solver.op_data.operators[name].is_resting() for name in PRIMARY[2:])
    solver.run_order_solver.assert_not_called()


def test_leaving_dorm_does_not_require_native_rotation_of_working_replacements(
    group_return,
):
    solver = group_return.solver
    for name in COVERS:
        solver.op_data.operators[name].mood = 0

    assert solver._emergency_release_ready()

    assert_waiting(solver, PRIMARY[:2])
    assert_temporary_workers_unchanged(solver)
    assert solver._emergency_frozen()


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA])
def test_active_specialized_compensation_defers_resident_release(group_return, kind):
    solver = group_return.solver
    room = solver.op_data.operators[PRIMARY[0]].room
    task = SchedulerTask(time=NOW, task_type=kind, task_plan={room: [COVERS[0]]})
    task.emergency_original_roster = {room: [COVERS[0]]}
    solver.tasks.append(task)

    assert not solver._emergency_release_ready()

    assert task in solver.tasks
    solver.agent_arrange.assert_not_called()


def test_strict_release_window_defers_ready_resident_arrangement(group_return):
    solver = group_return.solver
    release = SchedulerTask(
        time=NOW + timedelta(seconds=30),
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_2": ["Current", "Current", "Free", "Current", "Current"]},
    )
    release.strict_mood_limit = True
    solver.tasks.append(release)

    assert not solver._emergency_release_ready()

    solver.agent_arrange.assert_not_called()
    assert release in solver.tasks


def test_partial_release_retains_unfinished_obligations_after_state_reload(
    group_return,
):
    episode, solver = group_return, group_return.solver

    def partial(plan, **kwargs):
        solver.op_data = solver.op_data.project_arrangements(
            [{"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]}]
        )
        return False

    solver.agent_arrange.side_effect = partial
    assert solver._emergency_release_ready()
    assert_waiting(solver, PRIMARY[:1])
    assert solver.op_data.operators[PRIMARY[1]].is_resting()
    assert set(episode.state["release_members"]) == set(PRIMARY[1:2])
    assert set(episode.state["ready_members"]) == set(PRIMARY[:1])
    assert set(episode.state["release_members"]) | set(
        episode.state["ready_members"]
    ) == set(PRIMARY[:2])
    assert episode.saves[0]["state"]["release_plan"]
    assert not episode.state.get("staffing_rescore")
    solver.emergency_state = pickle.loads(pickle.dumps(episode.state))
    solver.op_data = pickle.loads(pickle.dumps(solver.op_data))
    solver.agent_arrange.side_effect = episode.place

    assert solver._emergency_release_ready()

    assert_waiting(solver, PRIMARY[:2])
    assert set(solver.emergency_state["ready_members"]) == set(PRIMARY[:2])
    assert "release_plan" not in solver.emergency_state
    assert "release_members" not in solver.emergency_state
    assert_temporary_workers_unchanged(solver)
    solver.backup_plan_solver.assert_not_called()


def test_release_success_return_value_without_actual_departure_keeps_pending_plan(
    group_return,
):
    solver = group_return.solver
    solver.agent_arrange.side_effect = lambda plan, **kwargs: True

    assert solver._emergency_release_ready()

    assert solver.emergency_state["release_plan"]
    assert set(solver.emergency_state["release_members"]) == set(PRIMARY[:2])
    assert not set(solver.emergency_state.get("ready_members", ())).intersection(
        PRIMARY[:2]
    )
    assert all(solver.op_data.operators[name].is_resting() for name in PRIMARY[:2])
    assert not solver.emergency_state.get("staffing_rescore")
    assert_temporary_workers_unchanged(solver)


def test_release_actual_departure_confirms_even_when_arrangement_returns_false(
    group_return,
):
    solver = group_return.solver

    def observed_complete(plan, **kwargs):
        group_return.place(plan, **kwargs)
        return False

    solver.agent_arrange.side_effect = observed_complete

    assert solver._emergency_release_ready()

    assert_waiting(solver, PRIMARY[:2])
    assert set(solver.emergency_state["ready_members"]) == set(PRIMARY[:2])
    assert not solver.emergency_state.get("release_plan")
    assert_temporary_workers_unchanged(solver)


def test_ready_state_reconciles_resting_actual_position_before_skipping_release(
    group_return,
):
    solver = group_return.solver
    solver.emergency_state["ready_members"] = list(PRIMARY[:2])
    assert all(solver.op_data.operators[name].is_resting() for name in PRIMARY[:2])

    assert solver._emergency_release_ready()

    assert_waiting(solver, PRIMARY[:2])
    assert_temporary_workers_unchanged(solver)


def test_already_waiting_ready_residents_do_not_repeat_arrangement(group_return):
    solver = group_return.solver
    assert solver._emergency_release_ready()
    solver.agent_arrange.reset_mock()

    assert not solver._emergency_release_ready()

    solver.agent_arrange.assert_not_called()
    assert_waiting(solver, PRIMARY[:2])
    assert_temporary_workers_unchanged(solver)


def test_partial_release_rechecks_pending_individual_measurement(group_return):
    solver = group_return.solver

    def partial(plan, **kwargs):
        solver.op_data = solver.op_data.project_arrangements(
            [{"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]}]
        )
        return False

    solver.agent_arrange.side_effect = partial
    assert solver._emergency_release_ready()
    solver.agent_arrange.reset_mock()
    solver.op_data.operators[PRIMARY[1]].mood_is_prediction = True

    assert not solver._emergency_release_ready()

    assert set(solver.emergency_state["release_members"]) == set(PRIMARY[1:2])
    assert set(solver.emergency_state["ready_members"]) == set(PRIMARY[:1])
    solver.agent_arrange.assert_not_called()
    assert_temporary_workers_unchanged(solver)


def test_release_cancels_only_completed_individuals_from_pending_dorm_filling(
    group_return,
):
    solver = group_return.solver
    solver.op_data.operators[PRIMARY[1]].mood = 8
    fill = SchedulerTask(
        task_type=TaskTypes.FILL_DORM,
        task_plan={
            "dormitory_1": ["Current", "Current", PRIMARY[0], PRIMARY[1], "Current"],
            "dormitory_2": ["Current", "Current", PRIMARY[2], PRIMARY[3], "Current"],
        },
    )
    fill.emergency_dorm = True
    solver.tasks.append(fill)

    assert solver._emergency_release_ready()

    assert fill in solver.tasks
    assert fill.plan["dormitory_1"][2:4] == ["Current", PRIMARY[1]]
    assert fill.plan["dormitory_2"][2:4] == PRIMARY[2:]
    assert solver._emergency_frozen()
    solver.backup_plan_solver.assert_not_called()


def test_ready_residents_do_not_reenter_dorm_or_temporary_work_before_exit(
    group_return,
):
    solver = group_return.solver
    assert solver._emergency_release_ready()

    plan = emergency_recovery.emergency_dorm_plan(
        solver.op_data, solver.emergency_state, solver.tasks
    )
    selected = {name for row in plan.values() for name in row}

    assert not selected.intersection(PRIMARY[:2])
    assert_waiting(solver, PRIMARY[:2])
    assert_temporary_workers_unchanged(solver)


def test_waiting_residents_remain_reserved_for_processing_and_ordinary_dorms(
    group_return,
):
    from arknights_mower.utils.dorm_candidates import dorm_task_reservations

    solver = group_return.solver
    assert solver._emergency_release_ready()
    solver.plan_metadata = MagicMock()

    solver._emergency_tick()

    reserved, _ = dorm_task_reservations(solver.op_data, solver.tasks)
    assert set(PRIMARY[:2]).issubset(reserved)
    assert solver._emergency_frozen()
    assert_temporary_workers_unchanged(solver)


def test_cached_ready_member_below_stored_target_cannot_authorize_final_exit(
    group_return,
):
    solver = group_return.solver
    assert solver._emergency_release_ready()
    for name in PRIMARY[2:]:
        op = solver.op_data.operators[name]
        solver.op_data.update_detail(name, 24, op.current_room, op.current_index, True)
    op = solver.op_data.operators[PRIMARY[0]]
    solver.op_data.update_detail(op.name, 15.9, "", -1, True)

    assert not solver._emergency_ready()
    assert_temporary_workers_unchanged(solver)


def test_final_exit_restores_all_working_primaries_together(group_return):
    solver = group_return.solver
    assert solver._emergency_release_ready()
    for name in PRIMARY[2:]:
        op = solver.op_data.operators[name]
        solver.op_data.update_detail(name, 24, op.current_room, op.current_index, True)
    assert solver._emergency_release_ready()
    assert_waiting(solver, PRIMARY)
    assert_temporary_workers_unchanged(solver)
    assert solver._emergency_ready()
    original = {solver.op_data.operators[name].room: [name] for name in PRIMARY}
    original_rooms = set(original)
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.agent_get_mood = MagicMock(side_effect=[original, {}])
    solver._emergency_handoff_feasible = MagicMock(return_value=True)
    solver._emergency_read_rooms = MagicMock(return_value=True)

    assert solver._emergency_restore()

    assert solver.emergency_state is None
    assert solver.backup_plan_solver.call_count == 1
    for name in PRIMARY:
        op = solver.op_data.operators[name]
        assert (op.current_room, op.current_index) == (op.room, op.index)
    assert set(group_return.plans[-1]) == original_rooms


def test_insufficient_beds_admit_one_member_without_waiting_for_bound_group(
    group_return,
):
    solver = group_return.solver
    empty = {
        "dormitory_1": ["Current", "Current", "Free", "Free", "Free"],
        "dormitory_2": ["Current", "Current", "Free", "Free", "Free"],
    }
    solver.op_data = solver.op_data.project_arrangements([empty])
    solver.op_data.dorm = solver.op_data.dorm[:1]
    for name in PRIMARY[:2]:
        solver.op_data.update_detail(name, 8, "", -1, True)
    solver.emergency_state["targets"] = {
        name: solver.emergency_state["targets"][name] for name in PRIMARY[:2]
    }

    plan = emergency_recovery.emergency_dorm_plan(
        solver.op_data, solver.emergency_state, members=PRIMARY[:2]
    )

    admitted = {name for row in plan.values() for name in row}.intersection(PRIMARY)
    assert len(admitted) == 1
    projected = solver.op_data.project_arrangements([plan])
    assert sum(projected.operators[name].is_resting() for name in PRIMARY[:2]) == 1
    assert_temporary_workers_unchanged(solver)
