"""救急交接释放未开始的普通等待预约，保留原请求和已开始的责任。"""

import copy
import pickle
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.automatic_rescue_tests import make_episode
from arknights_mower.tests.automatic_rescue_tests import offline as offline
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def waiting_handoff(solver):
    state = make_episode(solver)
    data = solver.op_data
    for name, group in zip(PRIMARY, ["恢复组", "恢复组", "交接组", "独立组"]):
        op = data.operators[name]
        op.group = group
        data.global_plan["default_plan"].plan[op.room][op.index].group = group
    data.groups.update(
        {"恢复组": PRIMARY[:2], "交接组": PRIMARY[2:3], "独立组": PRIMARY[3:]}
    )
    data.operators[PRIMARY[0]].mood = 8
    data.operators[PRIMARY[1]].mood = 18
    solver.op_data = data.project_arrangements([state["rescue_plan"]])
    solver.op_data.group_shift_state["交接组"] = True
    waiting = SchedulerTask(
        time=NOW - timedelta(days=2),
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "room_1_1": [COVERS[0]],
            "dormitory_1": ["Current", "Current", PRIMARY[0], "Current", "Current"],
        },
    )
    waiting.group_shift_waiting = {"交接组"}
    waiting.group_shift_predecessors = ()
    solver.waiting_group_shifts = [waiting]
    return solver, state, waiting


@pytest.mark.parametrize(
    "kind", [TaskTypes.SHIFT_OFF, TaskTypes.RE_ORDER, TaskTypes.SELF_CORRECTION]
)
@pytest.mark.parametrize("restored", [False, True])
def test_frozen_waiting_request_does_not_block_feasible_handoff(
    waiting_handoff, kind, restored
):
    solver, state, waiting = waiting_handoff
    waiting.type = kind
    if restored:
        solver.emergency_state, solver.waiting_group_shifts = pickle.loads(
            pickle.dumps((state, solver.waiting_group_shifts))
        )
        waiting = solver.waiting_group_shifts[0]
    before = pickle.dumps(waiting)
    locations = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }

    for _ in range(3):
        assert solver._emergency_ready()
        plan = solver._emergency_resting_handoff({})
        assert plan is not None
        assert solver._emergency_handoff_feasible(plan)
        projected = solver.op_data.project_arrangements([plan])
        assert all(projected.operators[name].is_resting() for name in PRIMARY[:2])
        assert projected.get_current_operator("room_1_1", 0).name == COVERS[0]
        assert all(projected.operators[name].is_working() for name in PRIMARY[2:])

    assert pickle.dumps(waiting) == before
    assert solver.waiting_group_shifts[0] is waiting
    assert locations == {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_retained", True),
        ("mood_physical_started", True),
        ("derived_correction_started", True),
        ("group_shift_expected", {("room_1_1", 0): COVERS[0]}),
        ("product_shift_locked", True),
        ("product_switched_before_arrangement", True),
        ("backup_shift_active", True),
        ("backup_retention_started", True),
        ("dorm_recovery_restore", [PRIMARY[0]]),
        ("fia_return_target", PRIMARY[0]),
        ("strict_mood_limit", True),
    ],
)
def test_started_or_retained_waiting_work_still_protects_handoff(
    waiting_handoff, field, value
):
    solver, _, waiting = waiting_handoff
    setattr(waiting, field, copy.deepcopy(value))
    before = pickle.dumps(waiting)

    assert not solver._emergency_ready()
    assert solver._emergency_resting_handoff({}) is None
    assert pickle.dumps(waiting) == before


@pytest.mark.parametrize("normal_projection", [False, True])
def test_waiting_reservations_remain_effective_without_active_rescue(
    waiting_handoff, normal_projection
):
    solver, _, waiting = waiting_handoff
    solver.emergency_state = {"targets": {}} if normal_projection else None
    solver._emergency_handoff = normal_projection

    names, slots = solver._waiting_shift_reservations()

    assert PRIMARY[0] in names
    assert ("dormitory_1", 2) in slots
    assert solver.waiting_group_shifts[0] is waiting


@pytest.mark.parametrize("restored", [False, True])
@pytest.mark.parametrize("interrupted", [False, True])
def test_tick_finishes_handoff_and_reprepares_original_waiting_request(
    waiting_handoff, restored, interrupted
):
    solver, state, waiting = waiting_handoff
    if restored:
        solver.emergency_state, solver.tasks, solver.waiting_group_shifts = (
            pickle.loads(
                pickle.dumps((state, solver.tasks, solver.waiting_group_shifts))
            )
        )
        state, waiting = solver.emergency_state, solver.waiting_group_shifts[0]
    original_time = waiting.time
    state["next_read"] = NOW
    state["observed_at"] = NOW
    independent = SchedulerTask(time=NOW, task_type=TaskTypes.CLUE)
    solver.tasks.append(independent)
    solver._emergency_read_rooms = MagicMock(return_value=True)
    solver._suppress_train_correction = MagicMock()
    snapshots = []

    def save():
        snapshots.append(
            pickle.dumps((solver.emergency_state, solver.waiting_group_shifts))
        )

    def arrange(plan, **kwargs):
        assert solver._emergency_handoff
        assert solver.waiting_group_shifts[0] is waiting
        if interrupted and solver.agent_arrange.call_count == 1:
            room = "room_1_3"
            solver.op_data = solver.op_data.project_arrangements([{room: plan[room]}])
            del plan[room]
            return False
        solver.op_data = solver.op_data.project_arrangements([plan])
        plan.clear()
        return True

    solver._emergency_save = MagicMock(side_effect=save)
    solver.agent_arrange = MagicMock(side_effect=arrange)

    solver._emergency_tick()

    if interrupted:
        assert state["phase"] == "returning"
        assert state["handoff_plan"] and "room_1_3" not in state["handoff_plan"]
        if restored:
            solver.emergency_state, solver.tasks, solver.waiting_group_shifts = (
                pickle.loads(
                    pickle.dumps(
                        (
                            solver.emergency_state,
                            solver.tasks,
                            solver.waiting_group_shifts,
                        )
                    )
                )
            )
            state, waiting = solver.emergency_state, solver.waiting_group_shifts[0]
            independent = next(
                task for task in solver.tasks if task.type == TaskTypes.CLUE
            )
        pending = copy.deepcopy(state["handoff_plan"])
        next_read = state["next_read"]
        for _ in range(3):
            solver._emergency_tick()
            assert state["handoff_plan"] == pending
            assert state["next_read"] == next_read
            assert solver.waiting_group_shifts[0] is waiting
            assert waiting.time == original_time
        solver.agent_arrange.assert_called_once()

        solver.task = independent
        solver.find = MagicMock(return_value=(1, 1))
        solver.planned = solver.todo_task = solver.collect_notification = True
        solver.handle_error = MagicMock(return_value=True)
        solver._run_clue_flow = MagicMock()
        solver.skip = MagicMock()
        solver.infra_main()
        solver._run_clue_flow.assert_called_once()
        assert independent not in solver.tasks
        solver.agent_arrange.assert_called_once()
        solver.task = None

        solver.op_data.room_observations["room_1_1"] = (
            solver.op_data.room_observations.get("room_1_1", 0) + 1
        )
        solver._emergency_tick()

    assert solver.emergency_state is None
    assert not solver.waiting_group_shifts
    assert any(task is waiting for task in solver.tasks)
    assert waiting.time == original_time
    assert (independent in solver.tasks) is not interrupted
    assert all(solver.op_data.operators[name].is_resting() for name in PRIMARY[:2])
    assert all(solver.op_data.operators[name].is_working() for name in PRIMARY[2:])
    assert not solver.op_data.group_is_resting("交接组")
    assert any(pickle.loads(snapshot)[0] is not None for snapshot in snapshots)
    assert pickle.loads(snapshots[-1])[0] is None
    assert solver.agent_arrange.call_count == (2 if interrupted else 1)
    assert solver._emergency_read_rooms.call_count == (2 if interrupted else 1)


@pytest.mark.parametrize("invalid", ["unknown", "exhausted_cover", "insufficient_beds"])
def test_releasing_frozen_requests_does_not_bypass_normal_handoff_admission(
    waiting_handoff, invalid
):
    solver, _, waiting = waiting_handoff
    data = solver.op_data
    if invalid == "unknown":
        data.operators[PRIMARY[0]].time_stamp = None
    elif invalid == "exhausted_cover":
        data.operators[COVERS[0]].mood = 0
    else:
        for name in PRIMARY:
            data.operators[name].mood = 8
    before = pickle.dumps(waiting)

    assert not solver._emergency_ready()
    assert pickle.dumps(waiting) == before


@pytest.mark.parametrize(
    "kind",
    [
        TaskTypes.SWITCH_PRODUCT,
        TaskTypes.RUN_ORDER,
        TaskTypes.FIAMMETTA,
        TaskTypes.SWAP_SUPPORT,
    ],
)
def test_specialized_waiting_work_keeps_its_reservations(waiting_handoff, kind):
    solver, _, waiting = waiting_handoff
    waiting.type = kind
    before = pickle.dumps(waiting)

    assert not solver._emergency_ready()
    assert pickle.dumps(waiting) == before
