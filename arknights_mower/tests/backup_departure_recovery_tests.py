"""副表已指定替班时，离岗成员的恢复安排与工作岗位一起提交。"""

import copy

import pytest

from arknights_mower.tests import shift_cycle_projection_state_tests as fixtures
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

pytestmark = pytest.mark.usefixtures("offline_maintenance")
positions = fixtures.positions


@pytest.fixture
def solver(monkeypatch):
    return fixtures.solver.__wrapped__(monkeypatch)


def dorm_names(plan):
    return {
        name for room, row in plan.items() if room.startswith("dorm") for name in row
    }


def test_explicit_departure_admits_displaced_primary_before_execution(solver):
    data = solver.op_data
    data.operators["夕"]._current_room = ""
    data.operators["夕"].current_index = -1
    data.operators["夕"].mood = 24
    data.operators["歌蕾蒂娅"]._current_room = "central"
    data.operators["歌蕾蒂娅"].current_index = 0
    data.commit_group_shifts({"深海": False})
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan={})
    solver.task, solver.tasks = task, [task]
    before = positions(data), copy.deepcopy(data.group_shift_state)
    solver._prepare_shift_backup(task)
    assert task.plan["central"] == ["夕"]
    assert "歌蕾蒂娅" in dorm_names(task.plan)
    assert "旅骨" not in dorm_names(task.plan)
    assert (positions(data), data.group_shift_state) == before
    solver.enter_room.assert_not_called()


def test_idle_departed_primary_enters_dorm_instead_of_correction_recall(solver):
    solver.op_data.operators["夕"].mood = 0
    solver.op_data.operators["旅骨"].mood = 24
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert plan.get("central", ["Current"]) == ["Current"]
    assert "歌蕾蒂娅" in dorm_names(plan)
    assert "旅骨" not in dorm_names(plan)
    after = solver.op_data.project_arrangements([plan])
    solver.op_data = after
    correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert correction.get("central", ["Current"]) == ["Current"]


def test_unconfirmed_idle_primary_still_uses_startup_correction(solver):
    solver.op_data.commit_group_shifts({"深海": False})
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert plan["central"] == ["歌蕾蒂娅"]


def test_known_idle_primary_with_exhausted_cover_can_complete_rest_plan(solver):
    solver.op_data.operators["夕"].mood = 0
    plan, admissions = {}, {}
    assert solver._get_resting_plan(
        ["歌蕾蒂娅"], [], plan, 0, dorm_admissions=admissions
    )
    assert plan["central"] == ["夕"]
    assert "歌蕾蒂娅" in admissions.values()


def test_exhausted_new_cover_still_rejected(solver):
    cover = solver.op_data.operators["夕"]
    cover._current_room, cover.current_index = "", -1
    cover.mood = 0
    # Multiple choices make the configured low-mood admission rule applicable.
    solver.op_data.operators["歌蕾蒂娅"].replacement.append("虎狼丸")
    plan = {}
    assert not solver._get_resting_plan(["歌蕾蒂娅"], [], plan, 0)
    assert plan == {}


def test_full_cycle_preserves_departure_and_does_not_recall_mixed_group(solver):
    solver.op_data.operators["旅骨"].mood = 24
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={"meeting": ["跃跃"]})
    solver.task, solver.tasks = task, [task]
    before = positions(solver.op_data), copy.deepcopy(solver.op_data.group_shift_state)
    solver._prepare_shift_cycle(task)
    assert "歌蕾蒂娅" in dorm_names(task.plan)
    assert task.plan.get("central", ["Current"]) == ["Current"]
    assert "旅骨" not in dorm_names(task.plan)
    assert (positions(solver.op_data), solver.op_data.group_shift_state) == before
    solver.op_data = solver.op_data.project_arrangements([task.plan])
    solver.task, solver.tasks = None, []
    correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert correction.get("central", ["Current"]) == ["Current"]


def test_insufficient_beds_keeps_original_task_and_actual_state(solver):
    from arknights_mower.solvers.base_schedule import GroupShiftBlocked

    data = solver.op_data
    data.operators["夕"]._current_room = ""
    data.operators["夕"].current_index = -1
    data.operators["夕"].mood = 24
    data.operators["歌蕾蒂娅"]._current_room = "central"
    data.operators["歌蕾蒂娅"].current_index = 0
    data.commit_group_shifts({"深海": False})
    for name, index in [("旅骨", 2), ("跃跃", 3), ("令", 4)]:
        op = data.operators[name]
        op._current_room, op.current_index = "dormitory_1", index
        op.mood = 5
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan={})
    solver.task, solver.tasks = task, [task]
    before = positions(data), copy.deepcopy(data.group_shift_state), task.time
    for _ in range(2):
        with pytest.raises(GroupShiftBlocked):
            solver._prepare_shift_backup(task)
        assert task.plan == {}
        assert solver.tasks == [task]
        assert (positions(data), data.group_shift_state, task.time) == before


def test_explicit_relocation_does_not_admit_working_primary(solver):
    data = solver.op_data
    data.backup_plans[0].task = {"central": ["夕"], "meeting": ["歌蕾蒂娅"]}
    data.operators["夕"]._current_room, data.operators["夕"].current_index = "", -1
    data.operators["歌蕾蒂娅"]._current_room = "central"
    data.operators["歌蕾蒂娅"].current_index = 0
    data.commit_group_shifts({"深海": False})
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan={})
    solver.task, solver.tasks = task, [task]
    solver._prepare_shift_backup(task)
    assert task.plan["meeting"] == ["歌蕾蒂娅"]
    assert "歌蕾蒂娅" not in dorm_names(task.plan)


def test_unknown_mood_preserves_departure_and_requests_dorm_read(solver):
    data = solver.op_data
    data.operators["歌蕾蒂娅"].time_stamp = None
    data.operators["旅骨"].mood = 24
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert plan.get("central", ["Current"]) == ["Current"]
    assert "歌蕾蒂娅" in dorm_names(plan)
    assert data.operators["歌蕾蒂娅"].time_stamp is None
    assert data.operators["歌蕾蒂娅"].current_room == ""


def test_bed_wait_survives_restart_without_polling_and_releases_after_change(solver):
    import pickle
    from unittest.mock import patch

    from arknights_mower.solvers.base_schedule import GroupShiftBlocked

    data = solver.op_data
    data.operators["夕"]._current_room, data.operators["夕"].current_index = "", -1
    data.operators["夕"].mood = 24
    (
        data.operators["歌蕾蒂娅"]._current_room,
        data.operators["歌蕾蒂娅"].current_index,
    ) = "central", 0
    data.commit_group_shifts({"深海": False})
    for name, index in [("旅骨", 2), ("跃跃", 3), ("令", 4)]:
        op = data.operators[name]
        op._current_room, op.current_index = "dormitory_1", index
        op.mood = 5
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan={})
    solver.task, solver.tasks = task, [task]
    with pytest.raises(GroupShiftBlocked) as blocked:
        solver._prepare_shift_backup(task)
    solver._suspend_group_shift(task, (), recovery_names=blocked.value.recovery_names)
    original_time = task.time
    solver.waiting_group_shifts = pickle.loads(
        pickle.dumps(solver.waiting_group_shifts)
    )
    waiting = solver.waiting_group_shifts[0]
    solver.task = None
    with patch.object(
        solver, "_prepare_shift_backup", wraps=solver._prepare_shift_backup
    ) as prepare:
        for _ in range(3):
            solver._resume_waiting_group_shifts()
        prepare.assert_not_called()
        assert waiting.time == original_time
        op = data.operators["跃跃"]
        op._current_room, op.current_index = "", -1
        op.mood = 24
        solver._resume_waiting_group_shifts()
        prepare.assert_called_once_with(waiting)
    assert solver.tasks == [waiting]
    assert not solver.waiting_group_shifts
    assert waiting.time == original_time
    assert "歌蕾蒂娅" in dorm_names(waiting.plan)


def test_cancelled_bed_reservation_releases_original_departure(solver):
    from arknights_mower.solvers.base_schedule import GroupShiftBlocked

    data = solver.op_data
    data.operators["夕"]._current_room, data.operators["夕"].current_index = "", -1
    data.operators["夕"].mood = 24
    (
        data.operators["歌蕾蒂娅"]._current_room,
        data.operators["歌蕾蒂娅"].current_index,
    ) = "central", 0
    data.commit_group_shifts({"深海": False})
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan={})
    reservation = SchedulerTask(
        task_type=TaskTypes.RE_ORDER,
        task_plan={
            "dormitory_1": ["Current", "Current", "Free", "Free", "Free"],
        },
    )
    solver.task, solver.tasks = task, [task, reservation]
    with pytest.raises(GroupShiftBlocked) as blocked:
        solver._prepare_shift_backup(task)
    solver._suspend_group_shift(task, (), recovery_names=blocked.value.recovery_names)
    original_time = task.time
    solver.task = None
    solver._resume_waiting_group_shifts()
    assert solver.tasks == [reservation]
    solver.tasks.remove(reservation)
    solver._resume_waiting_group_shifts()
    assert solver.tasks == [task]
    assert not solver.waiting_group_shifts
    assert task.time == original_time
    assert "歌蕾蒂娅" in dorm_names(task.plan)


def test_released_bed_wait_yields_to_confirmation_then_resumes_without_new_read(solver):
    from unittest.mock import patch

    from arknights_mower.solvers.base_schedule import GroupShiftBlocked

    data = solver.op_data
    data.operators["夕"]._current_room, data.operators["夕"].current_index = "", -1
    data.operators["夕"].mood = 24
    (
        data.operators["歌蕾蒂娅"]._current_room,
        data.operators["歌蕾蒂娅"].current_index,
    ) = "central", 0
    data.commit_group_shifts({"深海": False})
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan={})
    reservation = SchedulerTask(
        task_type=TaskTypes.RE_ORDER,
        task_plan={
            "dormitory_1": ["Current", "Current", "Free", "Free", "Free"],
        },
    )
    solver.task, solver.tasks = task, [task, reservation]
    with pytest.raises(GroupShiftBlocked) as blocked:
        solver._prepare_shift_backup(task)
    solver._suspend_group_shift(task, (), recovery_names=blocked.value.recovery_names)
    original_time = task.time
    solver.task = None
    solver.tasks.remove(reservation)
    predecessor = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={})
    predecessor.group_shift_expected = {("recycle", 0): "旅骨"}
    predecessor.group_shift_transitions = {"深海": False}
    solver.tasks.append(predecessor)
    solver._resume_waiting_group_shifts()
    assert solver.waiting_group_shifts == [task]
    assert task.group_shift_predecessors == (predecessor,)
    assert "歌蕾蒂娅" in dorm_names(task.plan)
    observation = solver._departure_recovery_signature(["歌蕾蒂娅"], current_task=task)
    predecessor.group_shift_expected = {}
    assert observation == solver._departure_recovery_signature(
        ["歌蕾蒂娅"], current_task=task
    )
    with patch.object(
        solver, "_prepare_shift_backup", wraps=solver._prepare_shift_backup
    ) as prepare:
        solver._resume_waiting_group_shifts()
        prepare.assert_not_called()
    assert not solver.waiting_group_shifts
    assert task in solver.tasks
    assert task.time == original_time


def test_partial_backup_departure_keeps_full_peers_until_scheduled_group_return(solver):
    from datetime import datetime, timedelta

    data = solver.op_data
    glady = data.operators["歌蕾蒂娅"]
    glady._current_room, glady.current_index = "dormitory_1", 2
    glady.mood = 5
    worker = data.operators["旅骨"]
    worker.mood, worker.time_stamp = 22, datetime.now()
    peer = data.operators["令"]
    peer.group = "深海"
    peer.group_bindings = [{"group": "深海", "replacement": ["重岳"]}]
    data.groups["感知"].remove("令")
    data.groups["深海"].append("令")
    data.plan["contact"][0].group = "深海"
    data.plan["contact"][0].group_bindings = copy.deepcopy(peer.group_bindings)
    peer._current_room, peer.current_index = "dormitory_1", 3
    peer.mood = 24
    cover = data.operators["重岳"]
    cover._current_room, cover.current_index = "contact", 0
    task = SchedulerTask(
        time=datetime.now() + timedelta(minutes=30),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"central": ["歌蕾蒂娅"], "contact": ["令"]},
    )
    solver.tasks = [task]
    original = task.time, copy.deepcopy(task.plan)
    before = positions(data), copy.deepcopy(data.group_shift_state)
    for _ in range(3):
        correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
        assert correction.get("contact", ["Current"]) == ["Current"]
        assert correction.get("central", ["Current"]) == ["Current"]
        assert correction.get("dormitory_1", ["Current"])[0] != "撷英调香师"
        assert solver.tasks == [task]
        assert (task.time, task.plan) == original
        assert (positions(data), data.group_shift_state) == before
    projected = data.project_arrangements([task.plan])
    assert projected.operators["歌蕾蒂娅"].current_room == "central"
    assert projected.operators["令"].current_room == "contact"
