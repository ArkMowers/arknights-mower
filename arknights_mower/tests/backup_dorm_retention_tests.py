"""副表按最终宿舍保留名单安置无主岗位的空闲干员，并释放退出者。"""

import copy
import pickle
from datetime import datetime, timedelta
from types import MethodType

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver, GroupShiftBlocked
from arknights_mower.tests import dorm_order_transition_tests
from arknights_mower.tests.choose_agent_filter_tests import selection_solver
from arknights_mower.utils import resting_priority
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Plan, PlanConfig
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
)

solver = dorm_order_transition_tests.solver


def retain(solver, name="夕"):
    solver.op_data.backup_plans[0].config.free_room_exclusions = [name]


def final_data(solver):
    projected = solver.op_data.project_arrangements([])
    for task in solver.tasks:
        if conditions := getattr(task, "backup_shift_conditions", None):
            assert projected.swap_plan(conditions, refresh=True) is None
        projected._apply_projected_arrangements([task.plan])
    return projected


def transition(solver, path):
    if path == "cached":
        solver.backup_plan_solver()
        return
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    task.product_shift_locked = path == "product"
    solver.tasks, solver.task = [task], task
    solver._prepare_shift_cycle(task)
    before = copy.deepcopy(task.plan)
    solver._prepare_shift_cycle(task)
    assert task.plan == before


@pytest.mark.parametrize("path", ["cached", "shift", "product"])
def test_backup_admits_a_retention_only_idle_operator_without_inventing_mood(
    solver, path
):
    retain(solver)
    assert "夕" not in solver.op_data.operators
    transition(solver, path)
    final = final_data(solver)
    assert final.operators["夕"].is_resting()
    assert final.get_dorm_by_name("夕")[1].position in {
        bed.position for bed in final.dorm if final.is_effective_free_slot(bed)
    }
    assert final.operators["夕"].time_stamp is None
    if path == "cached":
        assert solver.op_data.operators["夕"].current_room == ""
        assert solver.op_data.operators["夕"].time_stamp is None
    else:
        assert "夕" not in solver.op_data.operators


@pytest.mark.parametrize("mood", [5, 24])
@pytest.mark.parametrize("path", ["cached", "shift", "product"])
def test_backup_release_on_retention_exit_does_not_require_full_mood(
    solver, mood, path
):
    retain(solver)
    solver.backup_plan_solver()
    solver.op_data = final_data(solver)
    solver.tasks = []
    op = solver.op_data.operators["夕"]
    op.mood, op.time_stamp = mood, datetime.now()
    solver.op_data.backup_plans[0].trigger = LogicExpression("False", "==", "True")
    transition(solver, path)
    assert final_data(solver).operators["夕"].current_room == ""


def test_another_active_backup_keeps_its_retained_resident(solver):
    retain(solver)
    solver.backup_plan_solver()
    solver.op_data = final_data(solver)
    solver.tasks = []
    other = Plan(
        {},
        PlanConfig("", "", "", free_room_exclusions="夕"),
        trigger=LogicExpression("True", "==", "True"),
    )
    solver.op_data.backup_plans.append(other)
    solver.op_data.plan_condition.append(False)
    solver.op_data.backup_plans[0].trigger = LogicExpression("False", "==", "True")
    solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [False, True]
    assert final_data(solver).operators["夕"].is_resting()


def test_retention_does_not_recall_an_existing_working_replacement(solver):
    retain(solver, "克洛丝")
    solver.backup_plan_solver()
    assert final_data(solver).operators["克洛丝"].current_room == "central"


@pytest.mark.parametrize("path", ["cached", "shift"])
def test_reserved_beds_defer_atomically_without_delaying_independent_work(solver, path):
    retain(solver)
    due = datetime.now() + timedelta(hours=2)
    reservation = SchedulerTask(
        due,
        {
            room: ["Current", "Current", "Free", "Free", "Free"]
            for room in ["dormitory_1", "dormitory_2"]
        },
        TaskTypes.RE_ORDER,
    )
    independent = SchedulerTask(datetime.now(), task_type=TaskTypes.SKILL_UPGRADE)
    task = SchedulerTask(
        datetime.now() - timedelta(minutes=1), task_type=TaskTypes.SHIFT_OFF
    )
    solver.tasks = (
        [reservation, independent]
        if path == "cached"
        else [task, reservation, independent]
    )
    solver.task = task if path == "shift" else None
    observed = [(bed.position, bed.name, bed.time) for bed in solver.op_data.dorm]
    before = copy.deepcopy(task.__dict__)
    if path == "shift":
        with pytest.raises(GroupShiftBlocked) as error:
            solver._prepare_shift_cycle(task)
        assert task.__dict__ == before
        solver._suspend_group_shift(
            task,
            error.value.groups,
            predecessors=error.value.predecessors,
            recovery_names=error.value.recovery_names,
        )
    for _ in range(3):
        if path == "cached":
            assert not solver.backup_plan_solver()
        else:
            solver._resume_waiting_group_shifts()
            assert task in solver.waiting_group_shifts
            assert task not in solver.tasks
            assert task.plan == before["plan"]
            assert task.time == before["time"]
        assert solver.op_data.plan_condition == [False]
        assert [
            (bed.position, bed.name, bed.time) for bed in solver.op_data.dorm
        ] == observed
        assert reservation.time == due
        assert (
            find_next_task(
                sorted(solver.tasks, key=lambda queued: queued.time),
                op_data=solver.op_data,
            )
            is independent
        )
    solver.tasks.remove(reservation)
    if path == "cached":
        solver.backup_plan_solver()
    else:
        solver._resume_waiting_group_shifts()
        assert task in solver.tasks
        assert not solver.waiting_group_shifts
    assert final_data(solver).operators["夕"].is_resting()


def test_invalid_retention_name_is_rejected_before_operator_registration(solver):
    retain(solver, "不是干员")
    assert (
        solver.op_data.swap_plan([True], refresh=True)
        == "宿舍保留中的干员名无效：不是干员"
    )


def executable_selection(solver, monkeypatch, task, room):
    actual = [name for name in solver.op_data.get_current_room(room, True) if name]
    instance, selected = selection_solver(monkeypatch, residents=actual)
    instance.op_data, instance.task, instance.tasks = solver.op_data, task, [task]
    for name in ("get_free_list", "preserve_resting_crafters"):
        setattr(
            instance, name, MethodType(getattr(BaseSchedulerSolver, name), instance)
        )
    monkeypatch.setattr(
        resting_priority, "agent_list", list(instance.op_data.operators)
    )
    return instance, selected


@pytest.mark.parametrize("mood", [None, 24])
def test_retention_only_member_is_selected_at_unknown_or_full_mood(
    solver, monkeypatch, mood
):
    retain(solver)
    solver.backup_plan_solver()
    op = solver.op_data.operators["夕"]
    if mood is not None:
        op.mood, op.time_stamp = mood, datetime.now()
    task = next(task for task in solver.tasks if "夕" in sum(task.plan.values(), []))
    room = next(room for room, names in task.plan.items() if "夕" in names)
    instance, selected = executable_selection(solver, monkeypatch, task, room)
    row = [
        instance.op_data.get_current_room(room, True)[index]
        if name == "Current"
        else name
        for index, name in enumerate(task.plan[room])
    ]
    instance.choose_agent(row, room, fast_mode=False)
    assert "夕" in selected
    assert op.time_stamp is None if mood is None else op.time_stamp is not None


@pytest.mark.parametrize("path", ["cached", "shift", "product"])
def test_retention_exit_survives_reprepare_pickle_and_other_free_selection(
    solver, monkeypatch, path
):
    retain(solver)
    solver.backup_plan_solver()
    solver.op_data = final_data(solver)
    solver.tasks = []
    solver.op_data.backup_plans[0].trigger = LogicExpression("False", "==", "True")
    op = solver.op_data.operators["夕"]
    op.mood, op.time_stamp = 5, datetime.now()
    transition(solver, path)
    task = next(
        task for task in solver.tasks if getattr(task, "backup_retention_releases", {})
    )
    solver.task = task
    solver._prepare_shift_cycle(task)
    assert "夕" in task.backup_retention_releases
    task = pickle.loads(pickle.dumps(task))
    if conditions := getattr(task, "backup_shift_conditions", None):
        assert solver.op_data.swap_plan(conditions, refresh=True) is None
    room = op.current_room
    assert "" in task.plan[room]
    instance, selected = executable_selection(solver, monkeypatch, task, room)
    row = [
        instance.op_data.get_current_room(room, True)[index]
        if name == "Current"
        else name
        for index, name in enumerate(task.plan[room])
    ]
    vacancy = next(
        index
        for index in range(len(row))
        if row[index] in ("", "Free") and index != op.current_index
    )
    row[vacancy] = "Free"
    instance.choose_agent(row, room, fast_mode=False)
    assert "夕" not in selected
    assert "夕" not in instance.get_dorm_candidates(current_resident="夕").filling
    assert op.mood == 5


def test_policy_admission_is_cancelled_before_execution_without_losing_other_work(
    solver,
):
    retain(solver)
    solver.backup_plan_solver()
    task = next(task for task in solver.tasks if "夕" in sum(task.plan.values(), []))
    task.plan["meeting"] = ["香草"]
    solver.op_data.backup_plans[0].trigger = LogicExpression("False", "==", "True")
    solver.backup_plan_solver()
    assert all(
        "夕" not in names for queued in solver.tasks for names in queued.plan.values()
    )
    assert task.plan["meeting"] == ["香草"]


def test_explicit_backup_dorm_admission_is_not_cancelled_as_retention_policy(solver):
    retain(solver)
    solver.op_data.backup_plans[0].task = {
        "dormitory_1": ["Current", "Current", "Current", "夕", "Current"]
    }
    solver.backup_plan_solver()
    task = next(task for task in solver.tasks if "夕" in sum(task.plan.values(), []))
    assert "夕" not in task.backup_retention_admissions


@pytest.mark.parametrize(
    "started_field",
    [
        "execution_retained",
        "backup_shift_active",
        "backup_retention_started",
        "group_shift_expected",
    ],
)
def test_started_retention_admission_keeps_original_arrangement(solver, started_field):
    retain(solver)
    solver.backup_plan_solver()
    task = next(task for task in solver.tasks if "夕" in sum(task.plan.values(), []))
    task.plan["meeting"] = ["香草"]
    setattr(
        task,
        started_field,
        {("dormitory_1", 3): "夕"} if started_field == "group_shift_expected" else True,
    )
    before = copy.deepcopy(task.__dict__)
    assert solver.op_data.swap_plan([False], refresh=True) is None
    pending = solver._cancel_stale_retention_admissions()
    assert any(queued is task for queued in pending)
    assert task.__dict__ == before


@pytest.mark.parametrize("path", ["cached", "shift", "product"])
def test_retention_uses_vacancy_without_moving_recovering_residents(solver, path):
    retain(solver)
    solver.op_data.backup_plans[
        0
    ].config.dorm_order = solver.op_data.config.dorm_order.copy()
    positions = {
        name: (solver.op_data.operators[name].current_room, 2)
        for name in ("芬", "香草")
    }
    vacancies = {bed.position for bed in solver.op_data.dorm if not bed.name}
    transition(solver, path)
    final = final_data(solver)
    for name, position in positions.items():
        op = final.operators[name]
        assert (op.current_room, op.current_index) == position
    op = final.operators["夕"]
    assert (op.current_room, op.current_index) in vacancies


def test_retention_release_does_not_evict_a_newly_observed_resident(
    solver, monkeypatch
):
    retain(solver)
    solver.op_data.backup_plans[
        0
    ].config.dorm_order = solver.op_data.config.dorm_order.copy()
    solver.backup_plan_solver()
    solver.op_data = final_data(solver)
    solver.tasks = []
    solver.op_data.backup_plans[0].trigger = LogicExpression("False", "==", "True")
    solver.backup_plan_solver()
    task = next(
        task for task in solver.tasks if getattr(task, "backup_retention_releases", {})
    )
    previous = solver.op_data.operators["夕"]
    room, index = previous.current_room, previous.current_index
    assert task.backup_retention_empty_slots[room, index] == "夕"
    previous._current_room, previous.current_index = "", -1
    solver.op_data.add(Operator("令", ""))
    observed = solver.op_data.operators["令"]
    observed._current_room, observed.current_index = room, index
    observed.mood, observed.time_stamp = 5, datetime.now()
    next(
        bed for bed in solver.op_data.dorm if bed.position == (room, index)
    ).name = "令"
    instance, selected = executable_selection(solver, monkeypatch, task, room)
    row = [
        instance.op_data.get_current_room(room, True)[slot]
        if name == "Current"
        else name
        for slot, name in enumerate(task.plan[room])
    ]
    instance.choose_agent(row, room, fast_mode=False)
    assert "令" in selected
    assert "夕" not in selected


@pytest.mark.parametrize("path", ["cached", "shift"])
def test_retention_admission_does_not_evict_actual_recovering_residents(solver, path):
    retain(solver)
    names = iter(["红", "陈", "阿米娅", "玫兰莎"])
    for bed in solver.op_data.dorm:
        if bed.name:
            continue
        name = next(names)
        solver.op_data.add(Operator(name, ""))
        op = solver.op_data.operators[name]
        op._current_room, op.current_index = bed.position
        op.mood, op.time_stamp, bed.name = 5, datetime.now(), name
    before = [(bed.position, bed.name) for bed in solver.op_data.dorm]
    if path == "cached":
        assert not solver.backup_plan_solver()
    else:
        task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
        solver.tasks, solver.task = [task], task
        with pytest.raises(GroupShiftBlocked):
            solver._prepare_shift_cycle(task)
        assert task.plan == {}
    assert solver.op_data.plan_condition == [False]
    assert [(bed.position, bed.name) for bed in solver.op_data.dorm] == before


@pytest.mark.parametrize("by_name", [True, False])
def test_retention_exit_respects_existing_named_and_positional_reservations(
    solver, by_name
):
    retain(solver)
    solver.backup_plan_solver()
    solver.op_data = final_data(solver)
    op = solver.op_data.operators["夕"]
    row = ["Current"] * 5
    row[op.current_index] = "夕" if by_name else "Free"
    reservation = SchedulerTask(
        datetime.now() + timedelta(hours=1),
        {op.current_room: row},
        TaskTypes.RE_ORDER,
    )
    solver.tasks = [reservation]
    solver.op_data.backup_plans[0].trigger = LogicExpression("False", "==", "True")
    assert not solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [True]
    assert solver.tasks == [reservation]
    solver.tasks = []
    solver.backup_plan_solver()
    assert final_data(solver).operators["夕"].current_room == ""


def test_final_retention_replaces_unstarted_admission_reservation_in_one_bed(solver):
    retain(solver)
    solver.op_data.backup_plans[
        0
    ].config.dorm_order = solver.op_data.config.dorm_order.copy()
    # 其余空床属于不受本次切表影响的真实预约。
    beds = [bed for bed in solver.op_data.dorm if not bed.name]
    reservation = SchedulerTask(
        datetime.now() + timedelta(hours=2), task_plan={}, task_type=TaskTypes.RE_ORDER
    )
    for bed in beds[1:]:
        room, index = bed.position
        reservation.plan.setdefault(room, ["Current"] * 5)[index] = "Free"
    solver.tasks = [reservation]
    solver.backup_plan_solver()
    old = next(task for task in solver.tasks if "夕" in sum(task.plan.values(), []))
    solver.op_data.backup_plans[0].trigger = LogicExpression("False", "==", "True")
    solver.op_data.backup_plans.append(
        Plan(
            {},
            PlanConfig("", "", "", free_room_exclusions="令"),
            trigger=LogicExpression("True", "==", "True"),
        )
    )
    solver.op_data.plan_condition.append(False)
    assert solver.backup_plan_solver()
    final = final_data(solver)
    assert final.operators["令"].is_resting()
    assert final.operators["夕"].current_room == ""
    assert old.plan == {}
    assert reservation in solver.tasks
