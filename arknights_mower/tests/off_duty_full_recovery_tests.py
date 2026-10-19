"""离岗回满主班先安排替班与入宿，独立纠错不等待恢复期限。"""

import pickle
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.dorm_group_tests import apply_plan
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils import dorm_candidates, resting_correction
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


@pytest.fixture
def recovery(solver, monkeypatch):
    data = solver.op_data
    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(resting_correction, "datetime", Clock)
    monkeypatch.setattr(dorm_candidates, "datetime", Clock)
    op = data.operators[PRIMARY[0]]
    op.rest_in_full = op.exhaust_require = True
    data.config.rest_in_full = [op.name]
    data.config.exhaust_require = [op.name]
    data.global_plan["default_plan"].config.rest_in_full = [op.name]
    data.global_plan["default_plan"].config.exhaust_require = [op.name]
    data.exhaust_agent = [op.name]
    op._current_room, op.current_index = "", -1
    op.mood, op.time_stamp = 18, NOW
    solver.global_plan = data.global_plan
    solver.find = MagicMock(return_value=True)
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver.skip = MagicMock()
    solver._read_recovery_rooms = MagicMock(
        side_effect=AssertionError("上岗前无需读取恢复期限")
    )
    solver._scan_card_moods = MagicMock(side_effect=AssertionError("已有有效心情"))
    solver.agent_arrange = MagicMock(
        side_effect=lambda plan, *a, **kw: (
            apply_plan(solver, plan),
            plan.clear(),
            True,
        )[2]
    )
    return solver, op


@pytest.mark.parametrize("initial", [False, True])
@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("exhaust", [False, True])
@pytest.mark.parametrize("card_only", [False, True])
def test_correction_sends_idle_full_recovery_primary_to_dorm(
    recovery, initial, restart, exhaust, card_only
):
    solver, op = recovery
    op.exhaust_require = exhaust
    solver.op_data.config.exhaust_require = [op.name] if exhaust else []
    solver.global_plan["default_plan"].config.exhaust_require = (
        [op.name] if exhaust else []
    )
    if card_only:
        op.mood, op.time_stamp = 24, None
        solver.op_data.dorm_mood_estimates[op.name] = (
            18,
            base_schedule.datetime.fromtimestamp(NOW.timestamp()),
        )
        assert dorm_candidates.dorm_candidate_mood(solver.op_data, op.name) == 18
    independent = solver.op_data.operators[PRIMARY[1]]
    independent._current_room, independent.current_index = "", -1
    task = SchedulerTask(
        time=NOW - timedelta(minutes=20),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={op.room: [op.name], "room_1_2": [PRIMARY[1]]},
    )
    task.derived_correction, task.initial_staffing = True, initial
    solver.tasks, solver.task = [task], task
    original_time = task.time
    if restart:
        solver._retain_failed_task(
            task, "需要回满的主班心情尚未满足要求，且缺少有效恢复期限", []
        )
        task.backup_shift_intent = {room: row.copy() for room, row in task.plan.items()}
        task.backup_shift_conditions = []
        task = pickle.loads(pickle.dumps(task))
        solver.tasks = [task]
        solver._resume_failed_tasks()
        assert not getattr(task, "execution_failure", None)
        solver.task = task
    solver.infra_main()
    assert solver.op_data.operators[op.name].is_resting()
    assert solver.op_data.get_current_room(op.room, True) == [COVERS[0]]
    assert solver.op_data.operators[PRIMARY[1]].current_room == "room_1_2"
    assert task.time == original_time
    assert task not in solver.tasks
    solver._read_recovery_rooms.assert_not_called()


def test_generated_correction_keeps_off_duty_primary_resting(recovery):
    solver, op = recovery
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert op.name not in plan.get(op.room, [])
    assert any(op.name in row for room, row in plan.items() if room.startswith("dorm"))
    assert plan[op.room] == [COVERS[0]]
    assert not op.current_room


@pytest.mark.parametrize("initial", [False, True])
def test_new_card_observation_replaces_idle_primary_before_arrangement(
    recovery, initial
):
    solver, op = recovery
    op.mood, op.time_stamp = 24, None

    def observe(**kwargs):
        solver.op_data.dorm_mood_estimates[op.name] = (
            18,
            Clock.fromtimestamp(NOW.timestamp()),
        )

    solver._scan_card_moods.side_effect = observe
    task = SchedulerTask(
        time=NOW,
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={op.room: [op.name]},
    )
    task.derived_correction, task.initial_staffing = True, initial
    solver.tasks, solver.task = [task], task
    solver.infra_main()
    assert solver.op_data.operators[op.name].is_resting()
    assert solver.op_data.get_current_room(op.room, True) == [COVERS[0]]
    solver._scan_card_moods.assert_called_once()
    solver._read_recovery_rooms.assert_not_called()


@pytest.mark.parametrize("exhaust", [False, True])
def test_full_recovery_does_not_send_working_primary_to_rest(recovery, exhaust):
    solver, op = recovery
    op.exhaust_require = exhaust
    op._current_room, op.current_index = op.room, op.index
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert not any(
        op.name in row for room, row in plan.items() if room.startswith("dorm")
    )
    assert op.is_working()


def test_missing_beds_does_not_block_independent_correction(recovery):
    solver, op = recovery
    # 三名不同主班占用全部床位，恢复中的成员不被挤出。
    for bed, name in zip(solver.op_data.dorm, PRIMARY[1:]):
        resident = solver.op_data.operators[name]
        resident._current_room, resident.current_index = bed.position
        resident.rest_in_full = True
        resident.mood = 10
        bed.name = name
        bed.time = NOW + timedelta(hours=3)
    solver.global_plan["default_plan"].config.rest_in_full = PRIMARY
    task = SchedulerTask(
        time=NOW,
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={op.room: [op.name], "room_1_2": [PRIMARY[1]]},
    )
    task.derived_correction = True
    solver.tasks, solver.task = [task], task
    solver.infra_main()
    assert not getattr(task, "execution_failure", None)
    assert not op.is_working()
    assert solver.op_data.get_current_room(op.room, True) == [COVERS[0]]
    assert solver.op_data.get_current_room("room_1_2", True) == [COVERS[1]]

    # 真实床位释放后，普通纠错即可补入宿舍，无需定时重试任务。
    data = solver.op_data
    bed = data.dorm[0]
    resident = data.operators[bed.name]
    resident._current_room, resident.current_index = "", -1
    resident.mood, resident.time_stamp = 24, NOW
    bed.reset()
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert any(op.name in row for room, row in plan.items() if room.startswith("dorm"))
    assert op.name not in plan.get(op.room, [])


def test_missing_cover_keeps_full_primary_off_duty_and_corrects_independent_room(
    recovery,
):
    solver, op = recovery
    solver.op_data.operators[COVERS[0]].mood = 0
    independent = solver.op_data.operators[PRIMARY[1]]
    independent._current_room, independent.current_index = "", -1
    task = SchedulerTask(
        time=NOW,
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={op.room: [op.name], independent.room: [independent.name]},
    )
    task.derived_correction = True
    solver.tasks, solver.task = [task], task
    solver.infra_main()
    assert not getattr(task, "execution_failure", None)
    assert not solver.op_data.operators[op.name].is_working()
    assert solver.op_data.operators[independent.name].current_room == independent.room


def test_dorm_resident_without_deadline_keeps_cover(recovery):
    solver, op = recovery
    data = solver.op_data
    bed = data.dorm[0]
    bed.name, bed.time = op.name, None
    op._current_room, op.current_index = bed.position
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert plan[op.room] == [COVERS[0]]
    assert not any(
        op.name in row for room, row in plan.items() if not room.startswith("dorm")
    )


def test_confirmed_full_resident_can_return_without_recovery_countdown(recovery):
    solver, op = recovery
    bed = solver.op_data.dorm[0]
    bed.name, bed.time = op.name, None
    op._current_room, op.current_index = bed.position
    op.mood, op.time_stamp = op.upper_limit, NOW
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={op.room: [op.name]})
    solver.tasks, solver.task = [task], task

    assert solver._verify_required_recovery(task)
    assert not getattr(task, "execution_failure", None)
    solver._read_recovery_rooms.assert_not_called()
    solver._scan_card_moods.assert_not_called()


@pytest.mark.parametrize("started", [False, True])
def test_correction_preserves_explicit_return_or_started_arrangement(recovery, started):
    solver, op = recovery
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={op.room: [op.name]}
    )
    task.derived_correction = True
    if started:
        task.derived_correction_started = True
    else:
        task.initial_staffing = True
        task.initial_staffing_returns = {op.name}
    solver.tasks = [task]
    assert not solver._prepare_correction_recovery(task)
    assert task.plan == {op.room: [op.name]}


@pytest.mark.parametrize("mood", [None, 24])
def test_unobserved_or_full_primary_is_not_sent_to_dorm(recovery, mood):
    solver, op = recovery
    op.mood, op.time_stamp = 24, NOW if mood is not None else None
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert not any(
        op.name in row for room, row in plan.items() if room.startswith("dorm")
    )
