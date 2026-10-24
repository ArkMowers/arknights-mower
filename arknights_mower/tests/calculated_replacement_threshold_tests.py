"""实时替班仅在计算达到个人下限后确认，失败保留原任务。"""

import pickle
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.tests.mood_calculation_consumers_tests import (
    calculated as calculated,
)
from arknights_mower.tests.mood_calculation_consumers_tests import (
    model_values,
)
from arknights_mower.tests.replacement_check_dispatch_tests import (
    dispatch_solver as dispatch_solver,
)
from arknights_mower.tests.replacement_check_tests import (
    _prepare_same_room_reader,
    base,
)
from arknights_mower.tests.replacement_check_tests import (
    clock as clock,
)
from arknights_mower.tests.replacement_check_tests import (
    replacement_solver as replacement_solver,
)
from arknights_mower.utils import calculated_mood, replacement_check
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
    scheduling,
)


@pytest.fixture(autouse=True)
def model_clock(clock, monkeypatch):
    monkeypatch.setattr(calculated_mood, "datetime", clock)


def dispatch(solver, task):
    solver.task = task
    solver.infra_main()


def test_sync_schedules_only_real_deadline_and_reuses_unchanged_inputs(
    dispatch_solver, clock, calculated, monkeypatch
):
    solver = dispatch_solver
    deadline = clock.now() + timedelta(hours=3)
    model_values(solver.op_data, {"薇薇安娜": 12}, {"薇薇安娜": deadline})
    mood = Mock(wraps=solver.op_data.calculated_mood)
    timing = Mock(wraps=solver.op_data.calculated_mood_deadline)
    monkeypatch.setattr(solver.op_data, "calculated_mood", mood)
    monkeypatch.setattr(solver.op_data, "calculated_mood_deadline", timing)
    replacement_check.sync_replacement_checks(solver)
    check = solver.tasks[0]
    assert check.time == check.replacement_check_deadline == deadline
    assert check.display_name == "替班下限确认：薇薇安娜"
    independent = SchedulerTask(clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(independent)
    for _ in range(3):
        clock.current += timedelta(minutes=1)
        replacement_check.sync_replacement_checks(solver)
        solver._resume_failed_tasks()
        scheduling(solver.tasks, time_now=clock.now(), op_data=solver.op_data)
        assert find_next_task(solver.tasks) is independent
        assert check.time == deadline
    assert mood.call_count == timing.call_count == 1
    solver.仓库扫描 = Mock()
    dispatch(solver, independent)
    solver.仓库扫描.assert_called_once()
    assert solver.tasks == [check]
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("lower", [0, 6])
def test_due_dispatch_confirms_personal_floor_before_matching(
    dispatch_solver, clock, calculated, lower
):
    solver = dispatch_solver
    cover = solver.op_data.operators["薇薇安娜"]
    cover.lower_limit = lower
    deadline = clock.now() + timedelta(hours=2)
    model_values(
        solver.op_data,
        {"薇薇安娜": 12, "赫默": 20, "歌蕾蒂娅": 2},
        {"薇薇安娜": deadline},
    )
    replacement_check.sync_replacement_checks(solver)
    check = solver.tasks[0]
    clock.current = deadline
    solver.op_data.test_moods[cover.name] = lower
    solver.reading.update(mood=lower)
    dispatch(solver, check)
    solver.get_agent_from_room.assert_called_once_with(
        "central", force_mood=True, strict_observation=True
    )
    assert check not in solver.tasks
    assert solver.tasks[0].plan == {"central": ["赫默"]}
    assert cover.mood == lower
    assert solver.op_data.operators["歌蕾蒂娅"].current_room == "dormitory_1"


def test_higher_actual_reading_replans_from_calibration_without_polling(
    dispatch_solver, clock, calculated
):
    solver = dispatch_solver
    deadline = clock.now() + timedelta(hours=2)
    model_values(solver.op_data, {"薇薇安娜": 12}, {"薇薇安娜": deadline})
    replacement_check.sync_replacement_checks(solver)
    check = solver.tasks[0]
    clock.current = deadline
    solver.op_data.test_moods["薇薇安娜"] = 0
    next_deadline = deadline + timedelta(hours=1)
    solver.op_data.test_deadlines["薇薇安娜"] = next_deadline
    solver.reading.update(mood=3)
    original_read = solver.get_agent_from_room.side_effect

    def calibrated_read(*args, **kwargs):
        result = original_read(*args, **kwargs)
        solver.op_data.test_moods["薇薇安娜"] = result[0]["mood"]
        return result

    solver.get_agent_from_room.side_effect = calibrated_read
    dispatch(solver, check)
    assert solver.tasks == [check]
    assert check.time == next_deadline
    assert check.replacement_check_deadline == next_deadline
    assert not check.retains_execution
    for _ in range(3):
        clock.current += timedelta(minutes=5)
        replacement_check.sync_replacement_checks(solver)
        assert find_next_task(solver.tasks).time == next_deadline
    solver.get_agent_from_room.assert_called_once()


@pytest.mark.parametrize("change", ["invalidate", "product", "normal_read"])
def test_environment_events_replan_without_forcing_room_or_immediate_dispatch(
    dispatch_solver, clock, calculated, change
):
    solver = dispatch_solver
    initial = clock.now() + timedelta(hours=2)
    model_values(solver.op_data, {"薇薇安娜": 12}, {"薇薇安娜": initial})
    replacement_check.sync_replacement_checks(solver)
    check = solver.tasks[0]
    clock.current += timedelta(minutes=5)
    expected = clock.now() + timedelta(hours=3)
    solver.op_data.test_deadlines["薇薇安娜"] = expected
    if change == "invalidate":
        replacement_check.invalidate_replacement_checks(solver)
    elif change == "product":
        solver.op_data.products["central"] = "changed"
    else:
        solver.op_data.update_detail("薇薇安娜", 11, "central", 0, True)
    assert check.time == initial
    replacement_check.sync_replacement_checks(solver)
    assert solver.tasks == [check] and check.time == expected
    assert not hasattr(check, "replacement_check_read_after")
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("mood", [None, 12])
def test_unknown_deadline_retains_without_dispatch_and_resumes_original(
    dispatch_solver, clock, calculated, mood
):
    solver = dispatch_solver
    model_values(solver.op_data, {"薇薇安娜": mood})
    replacement_check.sync_replacement_checks(solver)
    check = solver.tasks[0]
    original_time = check.time
    assert check.execution_failure["dependency"]
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    check = solver.tasks[0]
    independent = SchedulerTask(clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(independent)
    for _ in range(3):
        clock.current += timedelta(hours=1)
        replacement_check.sync_replacement_checks(solver)
        solver._resume_failed_tasks()
        assert find_next_task(solver.tasks) is independent
        assert check.time == original_time and check.execution_failure
    expected = clock.now() + timedelta(hours=2)
    solver.op_data.test_moods["薇薇安娜"] = 12
    solver.op_data.test_deadlines["薇薇安娜"] = expected
    solver.op_data.update_detail("薇薇安娜", 12, "central", 0, True)
    replacement_check.sync_replacement_checks(solver)
    solver._resume_failed_tasks()
    assert not getattr(check, "execution_failure", None)
    assert check.retains_execution and check.time == original_time
    dispatch(solver, check)
    assert check not in solver.tasks and check.time == original_time
    successor = next(task for task in solver.tasks if task is not independent)
    assert successor.time == expected
    solver.enter_room.assert_not_called()


def test_failed_floor_read_yields_without_repeated_dispatch(
    dispatch_solver, clock, calculated
):
    solver = dispatch_solver
    model_values(solver.op_data, {"薇薇安娜": 0})
    replacement_check.sync_replacement_checks(solver)
    check = solver.tasks[0]
    original_time = check.time
    solver.get_agent_from_room.side_effect = base.RecognizeError("心情未确认")
    dispatch(solver, check)
    failure = check.execution_failure
    independent = SchedulerTask(clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(independent)
    for _ in range(3):
        clock.current += timedelta(minutes=5)
        replacement_check.sync_replacement_checks(solver)
        solver._resume_failed_tasks()
        assert find_next_task(solver.tasks) is independent
        assert check.execution_failure is failure and check.time == original_time
    solver.get_agent_from_room.assert_called_once()


def test_same_room_floor_confirmation_supplies_both_checks(
    replacement_solver, clock, calculated
):
    solver = replacement_solver
    covers, _ = _prepare_same_room_reader(solver, clock, 2)
    model_values(solver.op_data, {op.name: 0 for op in covers} | {"赫默": 20})
    solver.read_accurate_mood.side_effect = None
    solver.read_accurate_mood.return_value = 0
    replacement_check.sync_replacement_checks(solver)
    first, second = solver.tasks
    assert replacement_check.run_replacement_check(solver, first) is True
    # 第一份纠错预约唯一候补，第二份保留，但不再进房确认同一份实读。
    assert replacement_check.run_replacement_check(solver, second) is False
    assert second.execution_failure
    solver.enter_room.assert_called_once()
    assert solver.read_accurate_mood.call_count == 2


@pytest.mark.parametrize("release", [None, "before", "during"])
def test_peer_same_value_read_preserves_failure_but_keeps_external_release(
    replacement_solver, clock, calculated, release
):
    solver = replacement_solver
    covers, _ = _prepare_same_room_reader(solver, clock, 2)
    model_values(solver.op_data, {op.name: 0 for op in covers} | {"赫默": 20})
    spare = solver.op_data.operators["赫默"]
    spare.current_room, spare.current_index = "meeting", 0
    solver.read_accurate_mood.side_effect = None
    solver.read_accurate_mood.return_value = 0
    replacement_check.sync_replacement_checks(solver)
    first, second = solver.tasks
    assert replacement_check.run_replacement_check(solver, first) is False
    failure, original_time = first.execution_failure, first.time
    clock.current += timedelta(seconds=5)
    if release == "before":
        solver.op_data.update_detail(spare.name, 20, "", -1, True)
    elif release == "during":
        solver.refresh_facility_state.side_effect = lambda _: (
            solver.op_data.update_detail(spare.name, 20, "", -1, True)
        )
    # 第二份期限晚于前次实读，确实再次调用正常实读，检验同值采样的失败保护。
    second.replacement_check_deadline = clock.now()
    assert replacement_check.run_replacement_check(solver, second) is bool(release)
    if not release:
        assert failure["snapshot"] == solver._task_failure_snapshot(
            first, failure["rooms"]
        )
    solver._resume_failed_tasks()
    if release:
        assert not getattr(first, "execution_failure", None)
        assert first.retains_execution
    else:
        assert first.execution_failure is failure
        for _ in range(3):
            clock.current += timedelta(minutes=1)
            replacement_check.sync_replacement_checks(solver)
            solver._resume_failed_tasks()
            assert first.execution_failure is failure
    assert first.time == original_time
    assert solver.enter_room.call_count == 2


def test_initialization_blocks_replacement_deadline_creation(
    dispatch_solver, calculated
):
    solver = dispatch_solver
    solver._initial_mood_read_pending = lambda: True
    model_values(solver.op_data, {"薇薇安娜": 0})
    replacement_check.sync_replacement_checks(solver)
    assert solver.tasks == []
    solver.enter_room.assert_not_called()


def test_real_model_due_read_calibrates_and_schedules_new_personal_deadline(
    dispatch_solver, clock
):
    solver = dispatch_solver
    data = solver.op_data
    data.runtime_conf = SimpleNamespace(test_mood_calculation=True)
    cover = data.operators["薇薇安娜"]
    cover.lower_limit = 6
    # 真实模型以房间实读校准；模型下限到期后，游戏读回仍高于个人下限。
    data.update_detail(cover.name, 7, "central", 0, True)
    replacement_check.sync_replacement_checks(solver)
    check = solver.tasks[0]
    assert check.time > clock.now()
    first_deadline = check.time
    clock.current = first_deadline + timedelta(seconds=1)
    assert data.calculated_mood(cover.name, clock.now()) <= cover.lower_limit
    solver.reading.update(mood=8)
    dispatch(solver, check)
    assert solver.tasks == [check]
    assert check.time > clock.now()
    assert check.time == data.calculated_mood_deadline(
        cover.name, cover.lower_limit, clock.now()
    )
    assert cover.mood == 8
    assert data.calculated_mood(cover.name, clock.now()) == 8
    solver.get_agent_from_room.assert_called_once()


def test_normal_operation_floor_read_completes_confirmation_without_extra_room(
    dispatch_solver, clock, calculated
):
    solver = dispatch_solver
    model_values(
        solver.op_data,
        {"薇薇安娜": 12, "赫默": 20},
        {"薇薇安娜": clock.now() + timedelta(hours=2)},
    )
    replacement_check.sync_replacement_checks(solver)
    check = solver.tasks[0]
    clock.current += timedelta(minutes=30)
    solver.op_data.update_detail("薇薇安娜", 0, "central", 0, True)
    solver.op_data.test_moods["薇薇安娜"] = 0
    observed_at = clock.now()
    clock.current += timedelta(seconds=1)
    replacement_check.sync_replacement_checks(solver)
    assert check.time == observed_at
    dispatch(solver, check)
    assert solver.tasks[0].plan == {"central": ["赫默"]}
    solver.enter_room.assert_not_called()


def test_legacy_retained_label_does_not_release_unchanged_failure(
    dispatch_solver, clock, calculated
):
    solver = dispatch_solver
    model_values(solver.op_data)
    replacement_check.sync_replacement_checks(solver)
    check = solver.tasks[0]
    check.meta_data = "替班心情检查：薇薇安娜"
    check.execution_failure["snapshot"]["meta_data"] = check.meta_data
    failure, original_time = check.execution_failure, check.time
    clock.current += timedelta(hours=1)
    replacement_check.sync_replacement_checks(solver)
    solver._resume_failed_tasks()
    assert check.execution_failure is failure and check.time == original_time
    solver.enter_room.assert_not_called()


def test_existing_immediate_task_acquires_deadline_without_dispatch(
    dispatch_solver, clock, calculated
):
    solver = dispatch_solver
    expected = clock.now() + timedelta(hours=2)
    model_values(solver.op_data, {"薇薇安娜": 12}, {"薇薇安娜": expected})
    replacement_check.sync_replacement_checks(solver)
    check = solver.tasks[0]
    check.time = clock.now()
    check.replacement_check_deadline = None
    check.meta_data = "替班心情检查：薇薇安娜"
    replacement_check.sync_replacement_checks(solver)
    assert solver.tasks == [check]
    assert check.time == expected
    assert check.display_name == "替班下限确认：薇薇安娜"
    solver.enter_room.assert_not_called()
