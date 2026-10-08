"""Group recall admission preserves unfinished recovery priority."""

import sys
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.data import agent_list  # noqa: E402
from arknights_mower.solvers import (  # noqa: E402
    base_schedule,
    record,
)
from arknights_mower.tests import group_resting_capacity_tests  # noqa: E402
from arknights_mower.tests.group_resting_capacity_tests import (  # noqa: E402
    DEEP,
    OTHER_COVERS,
    OTHERS,
    apply_plan,
    shift_off,
)
from arknights_mower.tests.resting_preemption_tests import (  # noqa: E402
    fill_remaining_beds,
    try_admit_newcomer,
)
from arknights_mower.utils import (  # noqa: E402
    config,
    mastery_db,
    operators,
    scheduler_task,
)
from arknights_mower.utils.emergency_recovery import (  # noqa: E402
    emergency_dorm_plan,
    primary_names,
)
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    plan_metadata,
    try_reorder,
)

solver = group_resting_capacity_tests.solver


@pytest.fixture(autouse=True)
def no_observation_database(monkeypatch, offline_maintenance):
    monkeypatch.setattr(record, "save_agent_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)


@pytest.fixture
def planning_clock(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 10, 8, 11, 9, 23)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    for module in (
        base_schedule,
        operators,
        scheduler_task,
        group_resting_capacity_tests,
    ):
        monkeypatch.setattr(module, "datetime", Clock)
    return Clock


def required_resting_group(solver, *, priority=True):
    data = solver.op_data
    for name in DEEP:
        data.operators[name].resting_priority = "low"
    data.operators[DEEP[0]].resting_priority = "high"
    data.config.ope_resting_priority = [DEEP[0]] if priority else []
    shift_off(solver)
    return data


def dispatch_without_device(solver, plan, *, task=None):
    solver.task = task or SchedulerTask(
        task_plan=plan, task_type=TaskTypes.NOT_SPECIFIC
    )
    if task is None:
        solver.tasks.append(solver.task)
    solver._emergency_frozen = lambda: False
    solver._track_idle_dorm_shift = lambda _: None
    solver._finish_idle_dorm_shift = lambda: None
    solver.agent_arrange_room = MagicMock(return_value=False)
    solver.agent_arrange(plan)


@pytest.mark.parametrize("observation", ["unfinished", "unknown", "predicted"])
def test_automatic_named_takeover_rechecks_recovery_before_dispatch(
    planning_clock, solver, observation
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    resident = data.get_current_operator("dormitory_2", 2)
    assert resident.name in DEEP[1:]
    _, bed = data.get_dorm_by_name(resident.name)
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.resting_priority_replacement = [incoming]
    solver.tasks = plan_metadata(data, [])
    returns = [(task, task.time, deepcopy(task.plan)) for task in solver.tasks]
    room, index = bed.position
    before = [(bed.name, bed.time) for bed in data.dorm]

    for _ in range(2):
        data.update_detail(resident.name, 24, *bed.position, update_time=True)
        scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
        task = next(
            task for task in solver.tasks if task.type == TaskTypes.NOT_SPECIFIC
        )
        assert incoming in {name for row in task.plan.values() for name in row}
        assert task.dorm_fill_plan[room][index] == incoming
        assert task.plan[room][index] == OTHERS[1]
        data.update_detail(resident.name, 20, *bed.position, update_time=True)
        if observation == "unknown":
            resident.time_stamp = None
        elif observation == "predicted":
            resident.mood, resident.mood_is_prediction = 24, True

        dispatch_without_device(solver, task.plan, task=task)

        assert not set(DEEP).intersection(
            name
            for room, row in task.plan.items()
            if not room.startswith("dorm")
            for name in row
        )
        assert [(bed.name, bed.time) for bed in data.dorm] == before
        assert all(
            task in solver.tasks and task.time == time and task.plan == original
            for task, time, original in returns
        )
        projected = data.project_arrangements([task.plan])
        assert all(projected.operators[name].is_resting() for name in DEEP)
        assert not projected.operators[incoming].is_resting()
        solver.tasks.remove(task)
        planning_clock.current += timedelta(minutes=3)


@pytest.mark.parametrize("departure", ["completed", "standby"])
def test_automatic_named_takeover_keeps_legal_departure_with_priority_anchor(
    planning_clock, solver, departure
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    resident = data.operators[DEEP[1]]
    if departure == "completed":
        resident.mood, resident.time_stamp = 24, planning_clock.now()
    else:
        resident.resting_priority = "standby"
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.resting_priority_replacement = [incoming]
    solver.tasks = plan_metadata(data, [])
    returns = [(task, task.time, deepcopy(task.plan)) for task in solver.tasks]
    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
    task = next(task for task in solver.tasks if task.type == TaskTypes.NOT_SPECIFIC)

    dispatch_without_device(solver, task.plan, task=task)

    assert not set(DEEP).intersection(
        name
        for room, row in task.plan.items()
        if not room.startswith("dorm")
        for name in row
    )
    assert all(
        task in solver.tasks and task.time == time and task.plan == original
        for task, time, original in returns
    )
    projected = data.project_arrangements([task.plan])
    assert projected.operators[DEEP[0]].is_resting()
    assert projected.operators[incoming].is_resting()
    assert not projected.operators[resident.name].is_resting()


def test_automatic_named_strictly_higher_takeover_preserves_group_recall(solver):
    data = required_resting_group(solver, priority=False)
    fill_remaining_beds(solver, OTHERS[1:])
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.ope_resting_priority = [incoming]
    solver.tasks = plan_metadata(data, [])
    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
    task = next(task for task in solver.tasks if task.type == TaskTypes.NOT_SPECIFIC)

    dispatch_without_device(solver, task.plan, task=task)

    projected = data.project_arrangements([task.plan])
    assert all(projected.operators[name].is_working() for name in DEEP)
    assert projected.operators[incoming].is_resting()
    assert not any(bed.name in DEEP for bed in data.dorm)
    assert not any(
        name in DEEP
        for queued in solver.tasks
        if queued.type == TaskTypes.SHIFT_ON
        for row in queued.plan.values()
        for name in row
    )


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT])
def test_automatic_group_preemption_rechecks_expanded_task_before_critical_dispatch(
    planning_clock, solver, kind
):
    data = required_resting_group(solver, priority=False)
    fill_remaining_beds(solver, OTHERS[1:])
    incoming = OTHER_COVERS[0]
    data.config.ope_resting_priority = [incoming]
    data.config.free_blacklist = [
        name for name in agent_list if name not in data.operators
    ]
    for op in data.operators.values():
        if not op.current_room:
            op.mood, op.time_stamp = 24, planning_clock.now()
    data.operators[incoming].mood = 5
    resident = data.operators[DEEP[1]]
    _, vacancy = data.get_dorm_by_name(resident.name)
    position = vacancy.position
    resident._current_room, resident.current_index = "", -1
    vacancy.reset()
    config.conf.enable_mastery = kind == TaskTypes.SWAP_SUPPORT
    critical = SchedulerTask(
        time=planning_clock.now() + timedelta(seconds=170),
        task_type=kind,
        task_plan={"room_1_1": ["Current"] * len(data.plan["room_1_1"])},
    )
    critical_time = critical.time
    solver.tasks = plan_metadata(data, []) + [critical]
    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
    task = next(task for task in solver.tasks if task.type == TaskTypes.FILL_DORM)
    scheduler_task.protect_priority_tasks(solver.tasks, op_data=data)
    assert task.time == planning_clock.now()
    apply_plan(
        solver,
        {
            position[0]: ["Current"] * position[1]
            + [resident.name]
            + ["Current"] * (len(data.plan[position[0]]) - position[1] - 1)
        },
    )
    scheduler_task.protect_priority_tasks(solver.tasks, op_data=data)
    assert task.time == planning_clock.now()
    before = [(bed.name, bed.time) for bed in data.dorm]
    returns = [
        (queued, queued.time, deepcopy(queued.plan))
        for queued in solver.tasks
        if queued.type == TaskTypes.SHIFT_ON
    ]
    assert returns

    dispatch_without_device(solver, task.plan, task=task)

    assert task.type == TaskTypes.NOT_SPECIFIC
    assert any(not room.startswith("dorm") for room in task.plan)
    assert task.time > critical_time == critical.time
    assert solver.tasks[0] is critical
    solver.agent_arrange_room.assert_not_called()
    assert [(bed.name, bed.time) for bed in data.dorm] == before
    assert all(
        queued in solver.tasks and queued.time == time and queued.plan == plan
        for queued, time, plan in returns
    )


def test_automatic_group_recall_keeps_beds_and_returns_until_legal_dispatch(
    planning_clock, solver
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    anchor = data.operators[DEEP[0]]
    _, anchor_bed = data.get_dorm_by_name(anchor.name)
    data.update_detail(anchor.name, 24, *anchor_bed.position, update_time=True)
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.ope_resting_priority.append(incoming)
    reserved = {}
    for bed in data.dorm:
        if bed.name not in DEEP or bed is anchor_bed:
            room, index = bed.position
            reserved.setdefault(room, ["Current"] * len(data.plan[room]))[index] = (
                "Free"
            )
    solver.tasks = plan_metadata(data, [])
    returns = [
        (task, task.time, deepcopy(task.plan))
        for task in solver.tasks
        if task.type == TaskTypes.SHIFT_ON
    ]
    assert any(anchor.name in plan.get(anchor.room, []) for _, _, plan in returns)
    solver.tasks.append(
        SchedulerTask(
            time=planning_clock.now() + timedelta(hours=1),
            task_plan=reserved,
            task_type=TaskTypes.RE_ORDER,
        )
    )
    before = [(bed.name, bed.time) for bed in data.dorm]

    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
    task = next(task for task in solver.tasks if task.type == TaskTypes.NOT_SPECIFIC)

    assert set(DEEP) <= {name for row in task.plan.values() for name in row}
    assert [(bed.name, bed.time) for bed in data.dorm] == before
    assert all(
        queued in solver.tasks and queued.time == time and queued.plan == plan
        for queued, time, plan in returns
    )
    data.update_detail(anchor.name, 20, *anchor_bed.position, update_time=True)

    dispatch_without_device(solver, task.plan, task=task)

    assert not task.plan
    assert [(bed.name, bed.time) for bed in data.dorm] == before
    assert all(
        queued in solver.tasks and queued.time == time and queued.plan == plan
        for queued, time, plan in returns
    )
    projected = data.project_arrangements([task.plan])
    assert all(projected.operators[name].is_resting() for name in DEEP)
    assert not projected.operators[incoming].is_resting()


def test_automatic_actual_resident_departure_does_not_recall_stale_cached_group(
    planning_clock, solver
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    resident = data.operators[DEEP[1]]
    _, bed = data.get_dorm_by_name(resident.name)
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.resting_priority_replacement = [incoming]
    data.update_detail(resident.name, 24, *bed.position, update_time=True)
    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
    task = next(task for task in solver.tasks if task.type == TaskTypes.NOT_SPECIFIC)
    resident._current_room, resident.current_index = "", -1
    resident.mood = 20
    actual = data.operators[OTHERS[0]]
    actual._current_room, actual.current_index = bed.position
    actual.mood, actual.time_stamp = 24, planning_clock.now()
    assert bed.name == resident.name

    dispatch_without_device(solver, task.plan, task=task)

    assert not set(DEEP).intersection(
        name
        for room, row in task.plan.items()
        if not room.startswith("dorm")
        for name in row
    )
    projected = data.project_arrangements([task.plan])
    assert projected.operators[DEEP[0]].is_resting()
    assert projected.operators[resident.name].current_room == ""
    assert projected.operators[actual.name].is_working()
    assert projected.operators[incoming].is_resting()


def test_rejected_automatic_named_takeover_keeps_recovery_for_next_legal_bed(
    planning_clock, solver
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    resident = data.operators[DEEP[1]]
    _, bed = data.get_dorm_by_name(resident.name)
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.resting_priority_replacement = [incoming]
    data.update_detail(resident.name, 24, *bed.position, update_time=True)
    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
    first = next(task for task in solver.tasks if task.type == TaskTypes.NOT_SPECIFIC)
    data.update_detail(resident.name, 20, *bed.position, update_time=True)
    before = [(bed.name, bed.time) for bed in data.dorm]

    dispatch_without_device(solver, first.plan, task=first)

    assert [(bed.name, bed.time) for bed in data.dorm] == before
    solver.tasks.remove(first)
    alternative = data.operators[OTHERS[1]]
    _, alternative_bed = data.get_dorm_by_name(alternative.name)
    data.update_detail(
        alternative.name, 24, *alternative_bed.position, update_time=True
    )
    planning_clock.current += timedelta(minutes=3)
    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
    second = next(task for task in solver.tasks if task.type == TaskTypes.NOT_SPECIFIC)

    dispatch_without_device(solver, second.plan, task=second)

    projected = data.project_arrangements([second.plan])
    assert all(projected.operators[name].is_resting() for name in DEEP)
    assert projected.operators[incoming].is_resting()
    assert not projected.operators[alternative.name].is_resting()


def test_automatic_named_takeover_rechecks_actual_resident_with_stale_bed_name(
    planning_clock, solver
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    resident, anchor = (data.operators[name] for name in (DEEP[1], DEEP[0]))
    _, bed = data.get_dorm_by_name(resident.name)
    _, anchor_bed = data.get_dorm_by_name(anchor.name)
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.resting_priority_replacement = [incoming]
    data.update_detail(resident.name, 24, *bed.position, update_time=True)
    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
    task = next(task for task in solver.tasks if task.type == TaskTypes.NOT_SPECIFIC)
    data.update_detail(resident.name, 20, *anchor_bed.position, update_time=True)
    data.update_detail(anchor.name, 0, *bed.position, update_time=True)
    bed.name = resident.name
    before = [(bed.name, bed.time) for bed in data.dorm]

    dispatch_without_device(solver, task.plan, task=task)

    assert not task.plan
    assert [(bed.name, bed.time) for bed in data.dorm] == before
    projected = data.project_arrangements([task.plan])
    assert all(projected.operators[name].is_resting() for name in DEEP)
    assert projected.operators[anchor.name].mood == 0
    assert not projected.operators[incoming].is_resting()


@pytest.mark.parametrize("reservation", ["none", "slot", "applicant"])
def test_automatic_named_takeover_uses_current_legal_bed_and_reservations(
    planning_clock, solver, reservation
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    resident = data.operators[DEEP[1]]
    _, bed = data.get_dorm_by_name(resident.name)
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.resting_priority_replacement = [incoming]
    data.update_detail(resident.name, 24, *bed.position, update_time=True)
    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
    task = next(task for task in solver.tasks if task.type == TaskTypes.NOT_SPECIFIC)
    original_time = task.time
    data.update_detail(resident.name, 20, *bed.position, update_time=True)
    alternative = data.operators[OTHERS[1]]
    _, alternative_bed = data.get_dorm_by_name(alternative.name)
    data.update_detail(
        alternative.name, 24, *alternative_bed.position, update_time=True
    )
    if reservation == "slot":
        room, index = alternative_bed.position
        reserved = {room: ["Current"] * len(data.plan[room])}
        reserved[room][index] = "Free"
        solver.tasks.append(SchedulerTask(task_plan=reserved))
    elif reservation == "applicant":
        solver.tasks.append(SchedulerTask(task_plan={"central": [incoming]}))
    before = [(bed.name, bed.time) for bed in data.dorm]
    planning_clock.current += timedelta(minutes=3)

    dispatch_without_device(solver, task.plan, task=task)

    assert solver.task is task and task.time == original_time
    assert [
        (bed.name, bed.time)
        for bed, previous in zip(data.dorm, before)
        if previous[0] in DEEP
    ] == [previous for previous in before if previous[0] in DEEP]
    projected = data.project_arrangements([task.plan])
    assert all(projected.operators[name].is_resting() for name in DEEP)
    if reservation == "none":
        assert projected.operators[incoming].is_resting()
        assert not projected.operators[alternative.name].is_resting()
    elif reservation == "slot":
        assert not task.plan
        assert not projected.operators[incoming].is_resting()
        assert projected.operators[alternative.name].is_resting()
    else:
        assert not projected.operators[incoming].is_resting()
        assert solver.tasks[-1].plan == {"central": [incoming]}


@pytest.mark.parametrize("initial_type", [TaskTypes.NOT_SPECIFIC, TaskTypes.FILL_DORM])
def test_automatic_dorm_task_changes_admission_type_without_replacing_task(
    planning_clock, solver, initial_type
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    resident = data.operators[DEEP[1]]
    _, bed = data.get_dorm_by_name(resident.name)
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.resting_priority_replacement = [incoming]
    priority_task = SchedulerTask(
        time=planning_clock.now() + timedelta(minutes=9),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_1": ["Current"] * len(data.plan["room_1_1"])},
    )
    solver.tasks.append(priority_task)
    if initial_type == TaskTypes.FILL_DORM:
        resident.current_room, resident.current_index = "", -1
        bed.reset()
    else:
        data.update_detail(resident.name, 24, *bed.position, update_time=True)
    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
    task = next(task for task in solver.tasks if task.type == initial_type)
    original_time = task.time
    if initial_type == TaskTypes.FILL_DORM:
        assert task.simple_dorm_fill
        solver.tasks.remove(priority_task)
        data.update_detail(resident.name, 24, *bed.position, update_time=True)
        expected_type = TaskTypes.NOT_SPECIFIC
    else:
        alternative = data.operators[OTHERS[1]]
        _, alternative_bed = data.get_dorm_by_name(alternative.name)
        alternative.current_room, alternative.current_index = "", -1
        alternative_bed.reset()
        expected_type = TaskTypes.FILL_DORM
    planning_clock.current += timedelta(minutes=3)

    dispatch_without_device(solver, task.plan, task=task)

    assert solver.task is task and task.time == original_time
    assert task.type == expected_type
    assert bool(getattr(task, "simple_dorm_fill", False)) == (
        expected_type == TaskTypes.FILL_DORM
    )
    projected = data.project_arrangements([task.plan])
    assert projected.operators[DEEP[0]].is_resting()
    assert projected.operators[incoming].is_resting()
    assert projected.operators[resident.name].is_resting() == (
        expected_type == TaskTypes.FILL_DORM
    )


def test_automatic_known_full_filler_retains_full_occupancy_protection(
    planning_clock, solver
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    data.config.free_blacklist = [
        name for name in agent_list if name not in data.operators
    ]
    for op in data.operators.values():
        if not op.current_room:
            op.mood, op.time_stamp = 24, planning_clock.now()
    resident = data.operators[DEEP[1]]
    _, bed = data.get_dorm_by_name(resident.name)
    resident.current_room, resident.current_index = "", -1
    bed.reset()
    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
    task = next(task for task in solver.tasks if task.type == TaskTypes.FILL_DORM)
    first = OTHER_COVERS[0]
    assert first in {name for row in task.plan.values() for name in row}
    data.update_detail(first, 24, "factory", 0, update_time=True)

    dispatch_without_device(solver, task.plan, task=task)

    projected = data.project_arrangements([task.plan])
    chosen = OTHER_COVERS[1]
    assert projected.operators[first].current_room == "factory"
    assert projected.operators[chosen].is_resting()
    assert projected.skip_idle_dorm_release(chosen), (
        projected.operators[chosen].dorm_mood_fallback,
        projected.operators[chosen].current_room,
        task.plan,
    )
    assert projected.operators[DEEP[0]].is_resting()


@pytest.mark.parametrize(
    "continuation", ["arrangement_retry_room", "dorm_recovery_restore"]
)
def test_automatic_dorm_continuation_preserves_confirmed_arrangement(
    planning_clock, solver, monkeypatch, continuation
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    resident = data.operators[DEEP[1]]
    _, bed = data.get_dorm_by_name(resident.name)
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.resting_priority_replacement = [incoming]
    data.update_detail(resident.name, 24, *bed.position, update_time=True)
    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
    task = next(task for task in solver.tasks if task.type == TaskTypes.NOT_SPECIFIC)
    room = bed.position[0]
    setattr(
        task,
        continuation,
        room if continuation == "arrangement_retry_room" else [room],
    )
    original = deepcopy(task.plan)
    monkeypatch.setattr(
        base_schedule,
        "try_add_release_dorm",
        MagicMock(side_effect=AssertionError("continuation restarts bed admission")),
    )

    dispatch_without_device(solver, task.plan, task=task)

    assert task.plan == original
    projected = data.project_arrangements([task.plan])
    assert projected.operators[incoming].is_resting()
    assert projected.operators[DEEP[0]].is_resting()
    assert not projected.operators[resident.name].is_resting()


@pytest.mark.parametrize("observation", ["unfinished", "unknown", "predicted"])
@pytest.mark.parametrize("entry", ["fill", "dispatch_free"])
def test_expired_countdown_does_not_allow_group_preemption(
    planning_clock, solver, observation, entry
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    resident = data.operators[DEEP[1]]
    _, bed = data.get_dorm_by_name(resident.name)
    bed.time = planning_clock.now() - timedelta(minutes=1)
    data.update_detail(resident.name, 20, *bed.position, update_time=True)
    if observation == "unknown":
        resident.time_stamp = None
    elif observation == "predicted":
        resident.mood, resident.mood_is_prediction = 24, True
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.resting_priority_replacement = [incoming]
    before = [(bed.name, bed.time) for bed in data.dorm]

    if entry == "fill":
        scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
        assert solver.tasks == []
    else:
        room, index = bed.position
        plan = {room: ["Current"] * len(data.plan[room])}
        plan[room][index] = "Free"
        dispatch_without_device(solver, plan)
        assert plan[room][index] == resident.name
        projected = data.project_arrangements([plan])
        assert all(projected.operators[name].is_resting() for name in DEEP)
    assert [(bed.name, bed.time) for bed in data.dorm] == before


@pytest.mark.parametrize("anchor_row", ["current", "omitted", "short"])
def test_dispatch_named_anchor_departure_compensates_whole_group(
    planning_clock, solver, anchor_row
):
    data = required_resting_group(solver)
    for name in DEEP[1:]:
        data.operators[name].mood = 24
    anchor = data.operators[DEEP[0]]
    _, anchor_bed = data.get_dorm_by_name(anchor.name)
    yielding_bed = next(
        bed
        for bed in data.dorm
        if bed.name in DEEP[1:] and bed.position[0] != anchor_bed.position[0]
    )
    room, index = yielding_bed.position
    plan = {room: ["Current"] * len(data.plan[room])}
    plan[room][index] = OTHER_COVERS[0]
    anchor_room, anchor_index = anchor_bed.position
    if anchor_row == "current":
        plan.setdefault(anchor_room, ["Current"] * len(data.plan[anchor_room]))
    elif anchor_row == "short":
        plan[anchor_room] = ["Current"] * anchor_index
    plan[anchor.room] = [anchor.name]
    solver.tasks = plan_metadata(data, [])

    dispatch_without_device(solver, plan)

    assert set(DEEP) <= {name for row in plan.values() for name in row}
    assert not any(bed.name in DEEP for bed in data.dorm)
    assert not any(
        name in DEEP
        for task in solver.tasks
        if task.type == TaskTypes.SHIFT_ON
        for row in task.plan.values()
        for name in row
    )
    projected = data.project_arrangements([plan])
    assert all(projected.operators[name].is_working() for name in DEEP)
    assert projected.operators[OTHER_COVERS[0]].is_resting()


@pytest.mark.parametrize("cached_anchor", [False, True])
def test_emergency_standby_yields_with_protected_anchor_context(
    planning_clock, solver, cached_anchor
):
    data = required_resting_group(solver)
    data.rescue_mode = True
    for name in DEEP[2:]:
        data.operators[name].mood = 24
    anchor, yielding = (data.operators[name] for name in DEEP[:2])
    yielding.resting_priority = "standby"
    _, anchor_bed = data.get_dorm_by_name(anchor.name)
    _, yielding_bed = data.get_dorm_by_name(yielding.name)
    if not cached_anchor:
        anchor_bed.name = ""
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.resting_priority_replacement = [incoming]
    reserved = {}
    for bed in data.dorm:
        if bed not in (anchor_bed, yielding_bed):
            room, index = bed.position
            reserved.setdefault(room, ["Current"] * len(data.plan[room]))[index] = (
                "Free"
            )
    tasks = [SchedulerTask(task_plan=reserved)]
    state = {
        "targets": {name: 16 for name in primary_names(data)},
        "ready_members": [
            name for name in primary_names(data) if data.operators[name].mood >= 16
        ],
    }
    before = [(bed.name, bed.time) for bed in data.dorm]

    plan = emergency_dorm_plan(data, state, tasks)

    room, index = yielding_bed.position
    assert plan[room][index] == incoming
    projected = data.project_arrangements([plan])
    assert projected.operators[anchor.name].is_resting()
    assert not projected.operators[yielding.name].is_resting()
    assert [(bed.name, bed.time) for bed in data.dorm] == before


@pytest.mark.parametrize("entry", ["fill", "dispatch_free"])
def test_rejected_completed_member_keeps_candidate_for_legal_alternative(
    planning_clock, solver, entry
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    _, anchor_bed = data.get_dorm_by_name(DEEP[0])
    room, index = anchor_bed.position
    row = ["Current"] * len(data.plan[room])
    row[index] = OTHERS[3]
    apply_plan(solver, {room: row})
    _, yielding_bed = data.get_dorm_by_name(DEEP[1])
    _, alternative_bed = data.get_dorm_by_name(OTHERS[1])
    for name in [*DEEP[1:], OTHERS[1]]:
        data.operators[name].mood = 24
    incoming = OTHER_COVERS[0]
    data.operators[incoming].mood = 5
    data.config.resting_priority_replacement = [incoming]
    before = (yielding_bed.name, yielding_bed.time)

    if entry == "fill":
        scheduler_task.try_add_release_dorm({}, None, data, solver.tasks)
        assert len(solver.tasks) == 1
        plan = solver.tasks[0].plan
    else:
        plan = {}
        for bed in (yielding_bed, alternative_bed):
            room, index = bed.position
            plan.setdefault(room, ["Current"] * len(data.plan[room]))[index] = "Free"
        dispatch_without_device(solver, plan)

    room, index = alternative_bed.position
    assert plan[room][index] == incoming
    assert not set(DEEP).intersection(
        name
        for room, row in plan.items()
        if not room.startswith("dorm")
        for name in row
    )
    assert (yielding_bed.name, yielding_bed.time) == before
    projected = data.project_arrangements([plan])
    assert projected.operators[DEEP[0]].current_room == ""
    assert projected.operators[DEEP[1]].is_resting()
    assert projected.operators[incoming].is_resting()


@pytest.mark.parametrize("priority", [False, True])
@pytest.mark.parametrize("observation", ["unfinished", "unknown", "predicted"])
def test_low_member_bed_does_not_bypass_unfinished_group_priority(
    planning_clock, solver, priority, observation
):
    data = required_resting_group(solver, priority=priority)
    fill_remaining_beds(solver, OTHERS[1:])
    anchor = data.operators[DEEP[0]]
    if observation == "unknown":
        anchor.mood, anchor.time_stamp = 24, None
    elif observation == "predicted":
        anchor.mood, anchor.mood_is_prediction = 24, True
    before = [(bed.name, bed.time) for bed in data.dorm]
    solver.tasks = plan_metadata(data, [])
    tasks = deepcopy(solver.tasks)

    for _ in range(2):
        if observation == "unfinished":
            anchor.mood = 0
            anchor.time_stamp = planning_clock.now()
        _, plan = try_admit_newcomer(solver)

        assert plan == {}
        assert [(bed.name, bed.time) for bed in data.dorm] == before
        assert [(task.type, task.time, task.plan) for task in solver.tasks] == [
            (task.type, task.time, task.plan) for task in tasks
        ]
        planning_clock.current += timedelta(minutes=3)


@pytest.mark.parametrize("completed_priority_member", [False, True])
def test_strictly_higher_arrival_can_recall_required_lower_group(
    solver, completed_priority_member
):
    data = required_resting_group(solver, priority=completed_priority_member)
    fill_remaining_beds(solver, OTHERS[1:])
    if completed_priority_member:
        anchor = data.operators[DEEP[0]]
        anchor.mood, anchor.time_stamp = 24, datetime.now()
    data.config.ope_resting_priority.append(OTHERS[0])

    newcomer, plan = try_admit_newcomer(solver)

    assert plan[newcomer.room][newcomer.index] == newcomer.replacement[0]
    assert set(DEEP) <= {name for row in plan.values() for name in row}
    beds = try_reorder(data, plan)
    apply_plan(solver, plan)
    apply_plan(solver, beds)
    assert all(data.operators[name].is_working() for name in DEEP)
    assert newcomer.is_resting()
    assert not any(bed.name in DEEP for bed in data.dorm)


def test_completed_low_member_yields_without_interrupting_priority_anchor(solver):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    completed = data.operators[DEEP[1]]
    completed.mood, completed.time_stamp = 24, datetime.now()
    solver.tasks = plan_metadata(data, [])
    returns = [(task, task.time, deepcopy(task.plan)) for task in solver.tasks]

    newcomer, plan = try_admit_newcomer(solver)

    assert plan[newcomer.room][newcomer.index] == newcomer.replacement[0]
    assert not set(DEEP).intersection(name for row in plan.values() for name in row)
    assert all(
        task in solver.tasks and task.time == time and task.plan == original
        for task, time, original in returns
    )
    beds = try_reorder(data, plan)
    apply_plan(solver, plan)
    apply_plan(solver, beds)
    assert data.operators[DEEP[0]].is_resting()
    assert completed.current_room == ""


def test_failed_complete_admission_does_not_commit_partial_bed_reservations(solver):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[2:])
    before = [(bed.name, bed.time) for bed in data.dorm]
    pending = {"central": ["Current"]}

    assert data.assign_dorm_group(OTHERS[:2], plan=pending) is None

    assert [(bed.name, bed.time) for bed in data.dorm] == before
    assert pending == {"central": ["Current"]}


def test_off_bed_priority_member_is_included_in_group_recall_admission(solver):
    data = required_resting_group(solver)
    anchor = data.operators[DEEP[0]]
    _, bed = data.get_dorm_by_name(anchor.name)
    bed.reset()
    anchor.current_room, anchor.current_index = "", -1
    fill_remaining_beds(solver, OTHERS[1:])
    before = [(bed.name, bed.time) for bed in data.dorm]

    _, plan = try_admit_newcomer(solver)

    assert plan == {}
    assert [(bed.name, bed.time) for bed in data.dorm] == before


@pytest.mark.parametrize("departure", ["completed", "standby"])
def test_final_admission_checks_anchor_departure_in_pending_plan(solver, departure):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    yielding = data.operators[DEEP[1]]
    if departure == "completed":
        yielding.mood, yielding.time_stamp = 24, datetime.now()
    else:
        yielding.resting_priority = "standby"
    pending = {}
    for name in DEEP:
        if name == yielding.name:
            continue
        _, bed = data.get_dorm_by_name(name)
        room, position = bed.position
        pending.setdefault(room, ["Current"] * 5)[position] = "Free"
    original = deepcopy(pending)
    before = [(bed.name, bed.time) for bed in data.dorm]

    assert data.assign_dorm_group([OTHERS[0]], plan=pending) is None

    assert [(bed.name, bed.time) for bed in data.dorm] == before
    assert pending == original


@pytest.mark.parametrize("departure", ["completed", "standby"])
def test_final_anchor_departure_skips_illegal_bed_and_uses_legal_alternative(
    solver, departure
):
    data = required_resting_group(solver)
    fill_remaining_beds(solver, OTHERS[1:])
    yielding = data.operators[DEEP[1]]
    if departure == "completed":
        yielding.mood, yielding.time_stamp = 24, datetime.now()
    else:
        yielding.resting_priority = "standby"
    pending = {}
    for name in DEEP:
        if name == yielding.name:
            continue
        _, bed = data.get_dorm_by_name(name)
        room, position = bed.position
        pending.setdefault(room, ["Current"] * 5)[position] = "Free"
    alternative = data.operators[OTHERS[1]]
    alternative.resting_priority = "low"
    _, alternative_bed = data.get_dorm_by_name(alternative.name)
    _, yielding_bed = data.get_dorm_by_name(yielding.name)
    yielding_state = (yielding_bed.name, yielding_bed.time)

    assigned = data.assign_dorm_group([OTHERS[0]], plan=pending)

    assert assigned == [alternative_bed]
    assert alternative_bed.name == OTHERS[0]
    assert (yielding_bed.name, yielding_bed.time) == yielding_state
