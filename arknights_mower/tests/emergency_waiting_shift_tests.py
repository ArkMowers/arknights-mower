"""救急作废旧状态派生的普通换班，交接后按实际状态重建排班。"""

import copy
import pickle
from datetime import timedelta
from unittest.mock import MagicMock

import jsonpickle
import pytest

from arknights_mower.tests.automatic_rescue_tests import make_episode, setup_startup
from arknights_mower.tests.automatic_rescue_tests import offline as offline
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

pytestmark = pytest.mark.usefixtures("offline_maintenance")


def restore_queues(solver):
    solver.emergency_state, solver.tasks, solver.waiting_group_shifts = (
        jsonpickle.decode(
            jsonpickle.encode(
                (solver.emergency_state, solver.tasks, solver.waiting_group_shifts)
            )
        )
    )


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
    solver.tasks.append(waiting)
    solver._suspend_group_shift(waiting, {"交接组"})
    return solver, state, waiting


@pytest.mark.parametrize(
    "kind", [TaskTypes.SHIFT_OFF, TaskTypes.RE_ORDER, TaskTypes.SELF_CORRECTION]
)
@pytest.mark.parametrize("restored", [False, True])
def test_obsolete_waiting_request_is_removed_before_feasible_handoff(
    waiting_handoff, kind, restored
):
    solver, state, waiting = waiting_handoff
    waiting.type = kind
    if restored:
        restore_queues(solver)
        waiting = solver.waiting_group_shifts[0]
    before = pickle.dumps(waiting)
    locations = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }

    solver.plan_metadata()
    assert not solver.waiting_group_shifts
    assert all(task is not waiting for task in solver.tasks)

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
    assert not solver.waiting_group_shifts
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

    solver._emergency_filter_tasks()
    assert solver.waiting_group_shifts == [waiting]
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

    solver._emergency_filter_tasks()
    names, slots = solver._waiting_shift_reservations()

    assert PRIMARY[0] in names
    assert ("dormitory_1", 2) in slots
    assert solver.waiting_group_shifts[0] is waiting


@pytest.mark.parametrize("restored", [False, True])
@pytest.mark.parametrize("interrupted", [False, True])
@pytest.mark.parametrize("recovery_hours", [2, 5])
def test_tick_rebuilds_schedule_after_handoff_without_reviving_old_requests(
    waiting_handoff, restored, interrupted, recovery_hours
):
    solver, state, waiting = waiting_handoff
    if restored:
        restore_queues(solver)
        state, waiting = solver.emergency_state, solver.waiting_group_shifts[0]
    original_time = waiting.time
    obsolete_departure = SchedulerTask(
        time=original_time,
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "room_1_3": [COVERS[2]],
            "dormitory_1": ["Current", "Current", "Current", "Current", PRIMARY[2]],
        },
    )
    solver.tasks.append(obsolete_departure)
    state["next_read"] = NOW
    state["observed_at"] = NOW
    independent = SchedulerTask(time=NOW, task_type=TaskTypes.CLUE)
    solver.tasks.append(independent)

    def read_rooms(*args, **kwargs):
        for bed in solver.op_data.all_dorms():
            if bed.name in PRIMARY[:2]:
                bed.time = NOW + timedelta(hours=recovery_hours)
        return True

    solver._emergency_read_rooms = MagicMock(side_effect=read_rooms)
    solver._suppress_train_correction = MagicMock()
    snapshots = []

    def save():
        snapshots.append(
            jsonpickle.encode(
                (solver.emergency_state, solver.tasks, solver.waiting_group_shifts)
            )
        )

    def arrange(plan, **kwargs):
        assert solver._emergency_handoff
        assert not solver.waiting_group_shifts
        assert all(task is not waiting for task in solver.tasks)
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
            restore_queues(solver)
            state = solver.emergency_state
            independent = next(
                task for task in solver.tasks if task.type == TaskTypes.CLUE
            )
        pending = copy.deepcopy(state["handoff_plan"])
        next_read = state["next_read"]
        solver.waiting_group_shifts.append(copy.deepcopy(waiting))
        for _ in range(3):
            solver._emergency_tick()
            assert state["handoff_plan"] == pending
            assert state["next_read"] == next_read
            assert not solver.waiting_group_shifts
            assert all(task.time != original_time for task in solver.tasks)
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
    assert all(task is not waiting for task in solver.tasks)
    assert all(task.time != original_time for task in solver.tasks)
    assert (independent in solver.tasks) is not interrupted
    assert all(solver.op_data.operators[name].is_resting() for name in PRIMARY[:2])
    assert all(solver.op_data.operators[name].is_working() for name in PRIMARY[2:])
    assert not solver.op_data.group_is_resting("交接组")
    returns = [task for task in solver.tasks if task.type == TaskTypes.SHIFT_ON]
    assert len(returns) == 1
    assert returns[0].time == NOW + timedelta(hours=recovery_hours, minutes=-8)
    assert returns[0].plan["room_1_1"] == [PRIMARY[0]]
    assert returns[0].plan["room_1_2"] == [PRIMARY[1]]
    planning = [
        task
        for task in solver.tasks
        if task.type == TaskTypes.NOT_SPECIFIC and not task.plan
    ]
    assert len(planning) == 1 and planning[0].time == NOW
    assert solver._plan_primary_recovery(scan_moods=False)
    assert not any(task.type == TaskTypes.SHIFT_OFF for task in solver.tasks)
    assert all(
        PRIMARY[2] not in row for task in solver.tasks for row in task.plan.values()
    )
    assert any(jsonpickle.decode(snapshot)[0] is not None for snapshot in snapshots)
    assert jsonpickle.decode(snapshots[-1])[0] is None
    _, saved_tasks, saved_waiting = jsonpickle.decode(snapshots[-1])
    assert not saved_waiting
    assert all(task.time != original_time for task in saved_tasks)
    assert solver.agent_arrange.call_count == (2 if interrupted else 1)
    assert solver._emergency_read_rooms.call_count == (2 if interrupted else 1)


@pytest.mark.parametrize("invalid", ["unknown", "exhausted_cover", "insufficient_beds"])
def test_invalidating_old_requests_does_not_bypass_normal_handoff_admission(
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

    solver.plan_metadata()
    assert not solver.waiting_group_shifts
    assert not solver._emergency_ready()
    assert pickle.dumps(waiting) == before


@pytest.mark.parametrize(
    "kind",
    [
        TaskTypes.RUN_ORDER,
        TaskTypes.FIAMMETTA,
        TaskTypes.SWAP_SUPPORT,
    ],
)
def test_specialized_waiting_work_keeps_its_reservations(waiting_handoff, kind):
    solver, _, waiting = waiting_handoff
    waiting.type = kind
    waiting.emergency_original_roster = copy.deepcopy(waiting.plan)
    before = pickle.dumps(waiting)

    solver._emergency_filter_tasks()
    assert solver.waiting_group_shifts == [waiting]
    assert not solver._emergency_ready()
    assert pickle.dumps(waiting) == before


@pytest.mark.parametrize("queue", ["tasks", "waiting_group_shifts"])
@pytest.mark.parametrize("phase", ["staffing", "recovering", "returning"])
@pytest.mark.parametrize(
    "kind",
    [
        TaskTypes.SHIFT_ON,
        TaskTypes.SHIFT_OFF,
        TaskTypes.EXHAUST_OFF,
        TaskTypes.RE_ORDER,
        TaskTypes.SELF_CORRECTION,
        TaskTypes.SWITCH_PRODUCT,
    ],
)
def test_rescue_invalidates_old_ordinary_plans_in_both_queues(
    waiting_handoff, queue, phase, kind
):
    solver, state, old = waiting_handoff
    state["phase"] = phase
    old.type = kind
    old.ordinary_coordination = True
    old.coordination_request_names = [PRIMARY[0]]
    solver.waiting_group_shifts = []
    setattr(solver, queue, [old])
    restore_queues(solver)
    for _ in range(3):
        solver._emergency_filter_tasks()
        assert not solver.tasks
        assert not solver.waiting_group_shifts


@pytest.mark.parametrize("queue", ["tasks", "waiting_group_shifts"])
@pytest.mark.parametrize(
    "field",
    [
        "execution_retained",
        "mood_physical_started",
        "group_shift_expected",
        "backup_shift_active",
        "urgent_recovery_started",
        "strict_mood_limit",
        "dorm_recovery_restore",
        "emergency_staffing",
    ],
)
def test_rescue_cleanup_keeps_unfinished_responsibilities(
    waiting_handoff, queue, field
):
    solver, _, task = waiting_handoff
    setattr(task, field, True)
    solver.waiting_group_shifts = []
    setattr(solver, queue, [task])
    before = pickle.dumps(task)
    for _ in range(3):
        solver._emergency_filter_tasks()
        assert getattr(solver, queue) == [task]
        assert pickle.dumps(task) == before


@pytest.mark.parametrize("queue", ["tasks", "waiting_group_shifts"])
def test_fresh_rescue_admission_persists_without_obsolete_requests(solver, queue):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    old = SchedulerTask(
        time=NOW - timedelta(days=2),
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"room_1_1": [COVERS[0]]},
    )
    old.group_shift_waiting = set()
    solver.waiting_group_shifts = []
    setattr(solver, queue, [old])
    snapshots = []
    solver._emergency_save = MagicMock(
        side_effect=lambda: snapshots.append(
            jsonpickle.encode(
                (solver.emergency_state, solver.tasks, solver.waiting_group_shifts)
            )
        )
    )

    solver._emergency_startup()

    assert solver._emergency_active()
    assert all(task is not old for task in solver.tasks)
    assert not solver.waiting_group_shifts
    state, tasks, waiting = jsonpickle.decode(snapshots[-1])
    assert state["phase"] == "staffing"
    assert not waiting
    assert not any(task.type == TaskTypes.SHIFT_OFF for task in tasks)
    solver._emergency_schedule_staffing.assert_not_called()
