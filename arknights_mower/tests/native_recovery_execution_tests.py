"""回班按已有期限执行，正常观测只更新尚未开始的安排。"""

import pickle
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import native_group_recovery_sync_tests
from arknights_mower.tests.dorm_group_tests import apply_plan
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

resting = native_group_recovery_sync_tests.resting
solver = native_group_recovery_sync_tests.solver
pytestmark = pytest.mark.usefixtures("offline_maintenance")


def returning_task():
    return SchedulerTask(
        task_plan={"meeting": ["伊内丝", "银灰"], "contact": ["讯使"]},
        task_type=TaskTypes.SHIFT_ON,
    )


def prepare_dispatch(scheduler, monkeypatch):
    monkeypatch.setattr(scheduler, "find", Mock(return_value=True))
    monkeypatch.setattr(scheduler, "skip", Mock())
    monkeypatch.setattr(scheduler, "_scan_card_moods", Mock(side_effect=AssertionError))

    def arrange(plan, *args, **kwargs):
        previous = {
            bed.position: (bed.name, bed.time) for bed in scheduler.op_data.all_dorms()
        }
        apply_plan(scheduler, plan)
        for bed in scheduler.op_data.all_dorms():
            name, due = previous[bed.position]
            if (
                bed.name == name
                and plan.get(bed.position[0], ["Current"] * 5)[bed.position[1]]
                == "Current"
            ):
                bed.time = due
        return True

    monkeypatch.setattr(scheduler, "agent_arrange", Mock(side_effect=arrange))


@pytest.mark.parametrize("unknown", ["idle", "countdown", "predicted"])
def test_due_return_dispatches_without_mandatory_mood_reads(
    resting, monkeypatch, unknown
):
    scheduler, _ = resting
    data = scheduler.op_data
    data.operators["讯使"].rest_in_full = True
    task = returning_task()
    task.time = datetime.now() - timedelta(minutes=20)
    at = task.time
    if unknown == "idle":
        op = data.operators["讯使"]
        data.get_dorm_by_name(op.name)[1].reset()
        op.current_room, op.current_index, op.time_stamp = "", -1, None
    elif unknown == "countdown":
        data.get_dorm_by_name("讯使")[1].time = None
    else:
        data.operators["讯使"].mood_is_prediction = True
    scheduler.tasks, scheduler.task = [task], task
    prepare_dispatch(scheduler, monkeypatch)

    scheduler.infra_main()

    scheduler.agent_arrange.assert_called_once()
    scheduler.enter_room.assert_not_called()
    scheduler._scan_card_moods.assert_not_called()
    assert task.time == at
    assert all(t is not task for t in scheduler.tasks)
    assert not getattr(scheduler, "waiting_group_shifts", [])
    assert not getattr(task, "execution_failure", None)
    assert data.operators["讯使"].current_room == "contact"


@pytest.mark.parametrize("state", ["failure", "waiting"])
def test_legacy_recovery_gate_restores_original_task_once(resting, state):
    scheduler, _ = resting
    task = returning_task()
    task.time = datetime.now() - timedelta(minutes=20)
    at, plan = task.time, deepcopy(task.plan)
    if state == "failure":
        task.execution_failure = {
            "reason": "需要回满的主班心情尚未满足要求，且缺少有效恢复期限"
        }
        scheduler.tasks = [task]
    else:
        task.recovery_waiting_observations = {"讯使": datetime.now()}
        task.group_shift_waiting, task.group_shift_predecessors = set(), ()
        scheduler.waiting_group_shifts = [task]
        scheduler.tasks = []
    observation = SchedulerTask(task_type=TaskTypes.REFRESH_TIME)
    observation.recovery_observation_rooms = {"dormitory_1"}
    observation.recovery_observation_targets = {"讯使": "dormitory_1"}
    scheduler.tasks.append(observation)
    scheduler.tasks, scheduler.waiting_group_shifts = pickle.loads(
        pickle.dumps((scheduler.tasks, getattr(scheduler, "waiting_group_shifts", [])))
    )
    restored = (
        scheduler.tasks[0] if state == "failure" else scheduler.waiting_group_shifts[0]
    )

    for _ in range(3):
        scheduler._resume_failed_tasks()
        scheduler._resume_waiting_group_shifts()
        scheduler.plan_metadata()

    assert sum(t is restored for t in scheduler.tasks) == 1
    assert restored.time == at and restored.plan == plan
    assert not getattr(restored, "execution_failure", None)
    assert not hasattr(restored, "recovery_waiting_observations")
    assert not scheduler.waiting_group_shifts
    assert all(not hasattr(t, "recovery_observation_rooms") for t in scheduler.tasks)
    scheduler.enter_room.assert_not_called()


def test_legacy_gate_does_not_release_real_group_dependency(resting):
    scheduler, _ = resting
    task = returning_task()
    task.recovery_waiting_observations = {"讯使": datetime.now()}
    task.group_shift_waiting, task.group_shift_predecessors = {"联动"}, ()
    scheduler.waiting_group_shifts = [task]
    scheduler._resume_waiting_group_shifts()
    assert scheduler.waiting_group_shifts == [task]
    assert all(pending is not task for pending in scheduler.tasks)
    assert not hasattr(task, "recovery_waiting_observations")


def observe_dorm(scheduler):
    scheduler.task = None
    names = scheduler.op_data.get_current_room("dormitory_1", True)
    scheduler._reconcile_room_observation(
        "dormitory_1", [{"agent": name} for name in names]
    )


def test_normal_room_observation_updates_pending_return_before_dispatch(resting):
    scheduler, now = resting
    data = scheduler.op_data
    data.operators["讯使"].rest_in_full = True
    scheduler.plan_metadata()
    original = next(t for t in scheduler.tasks if t.type == TaskTypes.SHIFT_ON)
    assert original.time == now + timedelta(hours=5)
    unrelated = SchedulerTask(time=now + timedelta(hours=8), task_type=TaskTypes.CLUE)
    scheduler.tasks.append(unrelated)
    bed = data.get_dorm_by_name("讯使")[1]
    bed.time = now + timedelta(hours=6)
    observe_dorm(scheduler)
    assert scheduler._recovery_plan_dirty

    scheduler._refresh_observed_recovery_tasks()

    returns = [t for t in scheduler.tasks if t.type == TaskTypes.SHIFT_ON]
    assert len(returns) == 1 and returns[0].time == bed.time
    assert any(t is unrelated for t in scheduler.tasks)
    assert not scheduler._recovery_plan_dirty
    before = list(scheduler.tasks)
    for _ in range(3):
        scheduler._refresh_observed_recovery_tasks()
    assert scheduler.tasks == before
    scheduler.enter_room.assert_not_called()


@pytest.mark.parametrize("handoff", ["group_shift_expected", "backup_shift_active"])
def test_observation_waits_for_started_handoff_before_replanning(resting, handoff):
    scheduler, now = resting
    task = returning_task()
    setattr(
        task,
        handoff,
        {("contact", 0): "讯使"} if handoff == "group_shift_expected" else True,
    )
    scheduler.tasks = [task]
    plan, at = deepcopy(task.plan), task.time
    observe_dorm(scheduler)
    scheduler._refresh_observed_recovery_tasks()
    assert scheduler._recovery_plan_dirty
    assert scheduler.tasks == [task]
    assert task.plan == plan and task.time == at
    delattr(task, handoff)
    scheduler.tasks.remove(task)
    scheduler._refresh_observed_recovery_tasks()
    assert not scheduler._recovery_plan_dirty
    assert any(t.type == TaskTypes.SHIFT_ON for t in scheduler.tasks)


@pytest.mark.parametrize("backup_active", [False, True])
def test_failed_unrelated_handoff_allows_observed_return_update(resting, backup_active):
    scheduler, now = resting
    data = scheduler.op_data
    data.operators["讯使"].rest_in_full = True
    scheduler.plan_metadata()
    original = next(t for t in scheduler.tasks if t.type == TaskTypes.SHIFT_ON)
    assert original.time == now + timedelta(hours=5)
    data.operators["芬"] = Operator(
        "芬", "room_1_1", index=0, mood=24, operator_type="high"
    )
    data.plan["room_1_1"] = [Room("芬", "", ["年"])]
    failure = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={"room_1_1": ["芬"]}
    )
    failure.group_shift_expected = {("room_1_1", 0): "芬"}
    failure.backup_shift_active = backup_active
    scheduler.tasks.append(failure)
    scheduler._retain_failed_task(failure, "换班实测驻员与目标不一致", ["room_1_1"])
    before_plan, before_time = deepcopy(failure.plan), failure.time
    bed = data.get_dorm_by_name("讯使")[1]
    bed.time = now + timedelta(hours=6)
    observe_dorm(scheduler)

    for _ in range(3):
        scheduler._resume_failed_tasks()
        scheduler._refresh_observed_recovery_tasks()
        returns = [t for t in scheduler.tasks if t.type == TaskTypes.SHIFT_ON]
        assert len(returns) == 1 and returns[0].time == bed.time
        assert sum(t is failure for t in scheduler.tasks) == 1
        assert failure.execution_failure
        assert failure.plan == before_plan and failure.time == before_time
        assert not scheduler._recovery_plan_dirty
    scheduler.enter_room.assert_not_called()


def test_idle_unknown_group_member_keeps_known_recovery_deadline(resting):
    scheduler, now = resting
    data = scheduler.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    scheduler.plan_metadata()
    op = data.operators["讯使"]
    op.rest_in_full = True
    data.get_dorm_by_name(op.name)[1].reset()
    op.current_room, op.current_index, op.time_stamp = "", -1, None
    observe_dorm(scheduler)
    scheduler._refresh_observed_recovery_tasks()
    returns = [t for t in scheduler.tasks if t.type == TaskTypes.SHIFT_ON]
    assert len(returns) == 1
    assert returns[0].time == now + timedelta(hours=3)
    assert returns[0].plan["contact"] == [op.name]
    assert op.time_stamp is None
    scheduler.enter_room.assert_not_called()


def test_unrelated_correction_dispatches_while_group_member_is_unknown(
    resting, monkeypatch
):
    scheduler, now = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    data.get_dorm_by_name(op.name)[1].reset()
    op.current_room, op.current_index, op.time_stamp = "", -1, None
    name, room = "芬", "room_1_1"
    data.operators[name] = Operator(name, room, index=0, mood=24, operator_type="high")
    data.plan[room] = [Room(name, "", ["年"])]
    scheduler.global_plan["default_plan"].plan[room] = data.plan[room]
    task = SchedulerTask(
        time=now, task_type=TaskTypes.SELF_CORRECTION, task_plan={room: [name]}
    )
    task.derived_correction = True
    scheduler.tasks, scheduler.task = [task], task
    deadline = data.get_dorm_by_name("伊内丝")[1].time
    prepare_dispatch(scheduler, monkeypatch)

    scheduler.infra_main()

    assert data.operators[name].current_room == room
    assert data.operators["伊内丝"].is_resting()
    assert data.get_dorm_by_name("伊内丝")[1].time == deadline
    assert not getattr(scheduler, "waiting_group_shifts", [])
    scheduler._scan_card_moods.assert_not_called()
    assert task not in scheduler.tasks


def test_overdue_initial_idle_primary_without_full_setting_dispatches(
    solver, monkeypatch
):
    from arknights_mower.tests.dorm_group_tests import apply_plan

    data = solver.op_data
    for op in data.operators.values():
        op.mood = 24
    name = "芬"
    room = "room_1_1"
    op = Operator(name, room, index=0, mood=24, operator_type="high")
    op.rest_in_full = False
    data.operators[name] = op
    data.plan[room] = [Room(name, "", ["年"])]
    solver.global_plan["default_plan"].plan[room] = data.plan[room]
    data.dorm_mood_estimates[name] = (18, datetime.now())
    task = SchedulerTask(
        time=datetime.now() - timedelta(minutes=20),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={room: [name]},
    )
    task.initial_staffing = True
    solver.tasks, solver.task = [task], task
    before = task.time
    monkeypatch.setattr(solver, "find", Mock(return_value=True))
    monkeypatch.setattr(solver, "skip", Mock())
    monkeypatch.setattr(solver, "_scan_card_moods", Mock())
    monkeypatch.setattr(
        solver,
        "agent_arrange",
        Mock(side_effect=lambda plan, *a, **kw: (apply_plan(solver, plan), True)[1]),
    )

    solver.infra_main()

    assert solver.op_data.operators[name].current_room == room
    assert task.time == before
    assert task not in solver.tasks
    solver.agent_arrange.assert_called_once()


def test_initial_explicit_return_survives_complete_cycle(solver):
    op = solver.op_data.operators["讯使"]
    for member in solver.op_data.operators.values():
        member.mood = 24
    op.rest_in_full = True
    op.current_room, op.current_index, op.time_stamp = "", -1, None
    solver.op_data.dorm_mood_estimates[op.name] = (18, datetime.now())
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={"contact": [op.name]}
    )
    task.initial_staffing = True
    due = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan=task.plan.copy())
    solver.tasks, solver.task = [task, due], task

    solver._prepare_shift_cycle(task)

    assert op.name in task.initial_staffing_returns

    task = pickle.loads(pickle.dumps(task))
    solver.tasks, solver.task = [task], task
    solver._prepare_shift_cycle(task)
    assert task.plan["contact"] == [op.name]


@pytest.mark.parametrize("personal_full", [False, True])
def test_personal_cap_release_preserves_early_operation_window(
    resting, monkeypatch, personal_full
):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.rest_in_full, op.upper_limit, op.mood = personal_full, 12, 11.879
    data.config.operator_mood_limits[op.name] = {"lower": 0, "upper": 12}
    data.group_recovery_full_members["联动"] = ["伊内丝", "银灰", "讯使"]
    bed = data.get_dorm_by_name(op.name)[1]
    bed.time = datetime.now() + timedelta(seconds=140)
    row = ["Current"] * 5
    row[op.current_index] = "Free"
    task = SchedulerTask(
        task_plan={op.current_room: row},
        task_type=TaskTypes.RELEASE_DORM,
        meta_data=op.name,
        strict_mood_limit=True,
        mood_limit=12,
    )
    scheduler.tasks, scheduler.task = [task], task
    arrange = Mock(return_value=True)
    monkeypatch.setattr(scheduler, "agent_arrange", arrange)
    assert scheduler.arrange_release_dorm() == (True, True)
    arrange.assert_called_once()
    assert task.plan == {} and not getattr(task, "execution_failure", None)
    assert op.mood == 11.879


def test_early_cap_release_still_rejects_changed_personal_limit(resting):
    scheduler, _ = resting
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.upper_limit = 20
    data.config.operator_mood_limits[op.name] = {"lower": 0, "upper": 20}
    row = ["Current"] * 5
    row[op.current_index] = "Free"
    task = SchedulerTask(
        task_plan={op.current_room: row},
        task_type=TaskTypes.RELEASE_DORM,
        meta_data=op.name,
        strict_mood_limit=True,
        mood_limit=12,
    )
    assert not scheduler.prepare_release_dorm(task)
    assert task.plan == {}


@pytest.mark.parametrize("explicit", [False, True])
def test_missing_new_countdowns_preserve_existing_return_time(resting, explicit):
    scheduler, now = resting
    data = scheduler.op_data
    data.operators["讯使"].rest_in_full = explicit
    scheduler.plan_metadata()
    original = next(t for t in scheduler.tasks if t.type == TaskTypes.SHIFT_ON)
    original_time = original.time
    for bed in data.all_dorms():
        bed.time = None
    observe_dorm(scheduler)
    scheduler._refresh_observed_recovery_tasks()
    returns = [t for t in scheduler.tasks if t.type == TaskTypes.SHIFT_ON]
    assert len(returns) == 1
    assert returns[0].time == original_time
    assert data.get_dorm_by_name("讯使")[1].time is None
    scheduler.enter_room.assert_not_called()


def test_observed_delay_replaces_selected_return_before_it_can_execute(
    resting, monkeypatch
):
    scheduler, now = resting
    data = scheduler.op_data
    data.operators["讯使"].rest_in_full = True
    scheduler.plan_metadata()
    original = next(t for t in scheduler.tasks if t.type == TaskTypes.SHIFT_ON)
    data.get_dorm_by_name("讯使")[1].time = now + timedelta(hours=6)
    observe_dorm(scheduler)
    scheduler.task = original
    prepare_dispatch(scheduler, monkeypatch)

    scheduler.infra_main()

    scheduler.agent_arrange.assert_not_called()
    assert scheduler.task is None
    returns = [t for t in scheduler.tasks if t.type == TaskTypes.SHIFT_ON]
    assert len(returns) == 1 and returns[0].time == now + timedelta(hours=6)
    assert not any(getattr(t, "execution_failure", None) for t in scheduler.tasks)


@pytest.mark.parametrize("confirmed", [False, True])
def test_partial_dorm_read_only_updates_tasks_from_confirmed_slots(resting, confirmed):
    scheduler, now = resting
    scheduler.task = None
    names = scheduler.op_data.get_current_room("dormitory_1", True)
    observed = [
        {"agent": name, "observed": confirmed and index == 2}
        for index, name in enumerate(names)
    ]
    scheduler._reconcile_room_observation("dormitory_1", observed)
    assert getattr(scheduler, "_recovery_plan_dirty", False) is confirmed
    assert "dormitory_1" not in getattr(scheduler.op_data, "room_observations", {})
    assert scheduler.op_data.operators["讯使"].is_resting()
