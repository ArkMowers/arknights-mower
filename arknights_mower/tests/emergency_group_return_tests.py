"""智能救急以完整分组的实测目标授权回到原工作岗位。"""

import copy
import pickle
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
    monkeypatch.setattr(operation_timing, "_dorm_durations", {})
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
        side_effect=AssertionError("智能救急分组回岗不能切换副表")
    )
    solver.agent_get_mood = MagicMock(
        side_effect=AssertionError("智能救急分组回岗不能触发普通纠错")
    )
    solver.run_order_solver = MagicMock()
    return SimpleNamespace(
        solver=solver, state=state, plans=plans, saves=saves, place=place
    )


def assert_original_group_positions(solver, names=PRIMARY[:2]):
    for name in names:
        op = solver.op_data.operators[name]
        assert (op.current_room, op.current_index) == (op.room, op.index)


def assert_other_group_still_recovering(solver):
    for index, name in enumerate(PRIMARY[2:], 2):
        op = solver.op_data.operators[name]
        assert op.is_resting()
        assert solver.op_data.get_current_room(op.room, True) == [COVERS[index]]


def test_measured_group_returns_together_while_other_group_keeps_temporary_workers(
    group_return,
):
    episode, solver = group_return, group_return.solver

    assert solver._emergency_return_groups()

    assert_original_group_positions(solver)
    assert_other_group_still_recovering(solver)
    assert solver.emergency_state is episode.state
    assert episode.state["phase"] == "recovering"
    assert solver.op_data.get_current_room("dormitory_1", True)[:2] == ["塑心", "冰酿"]
    assert len(episode.plans) == 1
    destinations = {
        name for row in episode.plans[0].values() for name in row if name in PRIMARY
    }
    assert destinations == set(PRIMARY[:2])
    assert episode.saves
    solver.backup_plan_solver.assert_not_called()
    solver.agent_get_mood.assert_not_called()
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize(
    "unready", ["below_target", "prediction", "missing_measurement"]
)
def test_one_member_without_measured_individual_target_keeps_whole_group_resting(
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

    assert not solver._emergency_return_groups()

    assert all(solver.op_data.operators[name].is_resting() for name in PRIMARY)
    solver.agent_arrange.assert_not_called()


def test_measured_ready_group_requires_actual_native_rotation(group_return):
    solver = group_return.solver
    for name in COVERS[:2]:
        solver.op_data.operators[name].mood = 0

    assert not solver._emergency_return_groups()

    solver.agent_arrange.assert_not_called()
    assert all(solver.op_data.operators[name].is_resting() for name in PRIMARY[:2])


def test_return_revalidates_already_working_group_before_returning_another(
    group_return,
):
    solver = group_return.solver
    assert solver._emergency_return_groups()
    solver.agent_arrange.reset_mock()
    solver.emergency_state.pop("staffing_rescore", None)
    for name in PRIMARY[2:]:
        op = solver.op_data.operators[name]
        solver.op_data.update_detail(name, 20, op.current_room, op.current_index, True)
    for name in COVERS[:2]:
        solver.op_data.operators[name].mood = 0

    assert not solver._emergency_return_groups()

    solver.agent_arrange.assert_not_called()
    assert_original_group_positions(solver)
    assert_other_group_still_recovering(solver)


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA])
def test_active_specialized_compensation_prevents_group_return(group_return, kind):
    solver = group_return.solver
    room = solver.op_data.operators[PRIMARY[0]].room
    task = SchedulerTask(time=NOW, task_type=kind, task_plan={room: [COVERS[0]]})
    task.emergency_original_roster = {room: [COVERS[0]]}
    solver.tasks.append(task)

    assert not solver._emergency_return_groups()

    assert task in solver.tasks
    solver.agent_arrange.assert_not_called()


def test_strict_release_window_prevents_group_arrangement(group_return):
    solver = group_return.solver
    release = SchedulerTask(
        time=NOW + timedelta(seconds=30),
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_2": ["Current", "Current", "Free", "Current", "Current"]},
    )
    release.strict_mood_limit = True
    solver.tasks.append(release)

    assert not solver._emergency_return_groups()

    solver.agent_arrange.assert_not_called()
    assert release in solver.tasks


def test_group_return_does_not_recall_personal_limit_released_dorm_manager(
    group_return,
):
    solver = group_return.solver
    manager = solver.op_data.operators["塑心"]
    solver.op_data.config.operator_mood_limits[manager.name] = {
        "upper_limit": 12,
        "lower_limit": 0,
    }
    solver.op_data.set_mood_limit(manager.name, 12, 0)
    solver.op_data.update_detail(manager.name, 12, "", -1, True)
    manager.rest_mood_release_limit = 12
    assert solver.op_data.rest_mood_complete(manager.name)

    assert solver._emergency_return_groups()

    assert_original_group_positions(solver)
    assert solver.op_data.operators["塑心"].current_room == ""
    assert all(
        "塑心" not in row for plan in group_return.plans for row in plan.values()
    )


def test_partial_return_failure_remains_reserved_and_can_resume_after_state_reload(
    group_return,
):
    solver = group_return.solver
    state = group_return.state
    first_room = solver.op_data.operators[PRIMARY[0]].room

    def partial(plan, **kwargs):
        solver.op_data = solver.op_data.project_arrangements(
            [{first_room: plan[first_room]}]
        )
        del plan[first_room]
        return False

    solver.agent_arrange.side_effect = partial
    assert solver._emergency_return_groups()
    assert solver.emergency_state is state
    assert state["phase"] == "recovering"
    assert_original_group_positions(solver, PRIMARY[:1])
    assert solver.op_data.operators[PRIMARY[1]].is_resting()
    assert group_return.saves
    solver.emergency_state = pickle.loads(pickle.dumps(state))
    solver.op_data = pickle.loads(pickle.dumps(solver.op_data))
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    solver.agent_arrange.side_effect = group_return.place

    assert solver._emergency_return_groups()

    assert_original_group_positions(solver)
    assert_other_group_still_recovering(solver)
    assert solver.emergency_state is not None
    solver.backup_plan_solver.assert_not_called()


def test_returning_same_group_twice_does_not_repeat_arrangement(group_return):
    solver = group_return.solver
    assert solver._emergency_return_groups()
    solver.agent_arrange.reset_mock()

    assert not solver._emergency_return_groups()

    solver.agent_arrange.assert_not_called()
    assert_original_group_positions(solver)
    assert_other_group_still_recovering(solver)


def test_partial_group_return_rechecks_pending_member_measured_target(group_return):
    solver = group_return.solver
    room = solver.op_data.operators[PRIMARY[0]].room

    def partial(plan, **kwargs):
        solver.op_data = solver.op_data.project_arrangements([{room: plan[room]}])
        return False

    solver.agent_arrange.side_effect = partial
    assert solver._emergency_return_groups()
    solver.agent_arrange.reset_mock()
    op = solver.op_data.operators[PRIMARY[1]]
    op.mood_is_prediction = True

    assert not solver._emergency_return_groups()
    assert set(solver.emergency_state["group_return_members"]) == {*PRIMARY[:2], "塑心"}
    solver.agent_arrange.assert_not_called()
    solver.backup_plan_solver.assert_not_called()


def test_group_return_removes_only_its_obsolete_dorm_filling(group_return):
    solver = group_return.solver
    fill = SchedulerTask(
        task_type=TaskTypes.FILL_DORM,
        task_plan={
            "dormitory_1": ["Current", "Current", PRIMARY[0], PRIMARY[1], "Current"],
            "dormitory_2": ["Current", "Current", PRIMARY[2], PRIMARY[3], "Current"],
        },
    )
    fill.emergency_dorm = True
    solver.tasks.append(fill)

    assert solver._emergency_return_groups()

    assert fill in solver.tasks
    assert "dormitory_1" not in fill.plan
    assert fill.plan["dormitory_2"][2:4] == PRIMARY[2:]
    assert solver._emergency_frozen()
    solver.backup_plan_solver.assert_not_called()


def test_returned_group_does_not_need_old_target_again_to_exit(group_return):
    solver = group_return.solver
    assert solver._emergency_return_groups()
    for name in PRIMARY:
        op = solver.op_data.operators[name]
        solver.op_data.update_detail(name, 16, op.current_room, op.current_index, True)

    assert solver._emergency_ready()
    assert solver._emergency_frozen()


def test_automatic_cover_allows_return_when_configured_cover_is_exhausted(group_return):
    solver = group_return.solver
    state = solver.emergency_state
    for name, cover, auto in zip(PRIMARY[:2], COVERS[:2], ["阿米娅", "米格鲁"]):
        from arknights_mower.utils.operators import Operator

        solver.op_data.add(Operator(auto, ""))
        solver.op_data.update_detail(auto, 24, "", -1, True)
        solver.op_data.operators[cover].mood = 0
        state.setdefault("automatic_replacements", {})[name] = auto

    assert solver._emergency_return_groups()
    assert_original_group_positions(solver)
    assert_other_group_still_recovering(solver)


def test_group_return_restores_bound_dorm_member_displaced_by_normal_group_shift(
    group_return,
):
    solver = group_return.solver
    manager = solver.op_data.operators["塑心"]
    solver.op_data.update_detail(manager.name, 24, "", -1, True)

    assert solver._emergency_return_groups()

    assert_original_group_positions(solver)
    manager = solver.op_data.operators["塑心"]
    assert (manager.current_room, manager.current_index) == (
        manager.room,
        manager.index,
    )
    assert_other_group_still_recovering(solver)
    solver.backup_plan_solver.assert_not_called()
