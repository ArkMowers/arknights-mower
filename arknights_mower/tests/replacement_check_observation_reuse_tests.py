"""替班检查复用正常观测，不为缺少消耗速率重复进房。"""

import pickle
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

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
from arknights_mower.utils.replacement_check import (
    invalidate_replacement_checks,
    run_replacement_check,
    sync_replacement_checks,
)
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
)


@pytest.mark.parametrize("room", ["central", "recycle"])
def test_recent_full_mood_without_rate_yields_without_reading(
    dispatch_solver, clock, room
):
    solver = dispatch_solver
    cover = solver.op_data.operators["薇薇安娜"]
    if room == "recycle":
        solver.op_data.plan[room] = solver.op_data.plan.pop("central")
        solver.op_data.operators["歌蕾蒂娅"].room = room
        cover.current_room = room
    cover.depletion_rate = 0
    clock.current += timedelta(minutes=3)
    sync_replacement_checks(solver)
    check = solver.tasks[0]
    original_time = check.time
    solver.task = check
    solver.infra_main()

    assert check.time == original_time and check.execution_failure["dependency"]
    solver.enter_room.assert_not_called()
    solver.get_agent_from_room.assert_not_called()
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    check = solver.tasks[0]
    independent = SchedulerTask(time=clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(independent)
    for _ in range(3):
        clock.current += timedelta(minutes=5)
        sync_replacement_checks(solver)
        solver._resume_failed_tasks()
        assert find_next_task(solver.tasks) is independent
        assert check.time == original_time and check.execution_failure
    solver.仓库扫描 = MagicMock()
    solver.task = independent
    solver.infra_main()
    solver.仓库扫描.assert_called_once()

    # 后续正常实读达到下限后，原检查恢复并安排换人。
    solver.op_data.update_detail(cover.name, 0, room, 0, True)
    solver.reading.update(mood=0, time=None)
    solver.task = check
    solver.infra_main()
    assert check.time == original_time and check not in solver.tasks
    assert any(task.plan == {room: ["赫默"]} for task in solver.tasks)


def test_recent_rate_supplies_absolute_deadline_without_reading(
    replacement_solver, clock
):
    solver = replacement_solver
    clock.current += timedelta(minutes=3)
    sync_replacement_checks(solver)
    check = solver.tasks[0]

    assert run_replacement_check(solver, check) is False

    assert check.time == clock.now() + timedelta(hours=3, minutes=57)
    solver.get_agent_from_room.assert_not_called()
    for _ in range(3):
        clock.current += timedelta(minutes=5)
        sync_replacement_checks(solver)
    assert check.time == clock.now() + timedelta(hours=3, minutes=42)


def test_new_measured_rate_replans_without_another_room_read(replacement_solver, clock):
    solver = replacement_solver
    sync_replacement_checks(solver)
    check = solver.tasks[0]
    assert run_replacement_check(solver, check) is False
    clock.current += timedelta(minutes=30)
    solver.op_data.update_detail("薇薇安娜", 12, "central", 0, True)
    sync_replacement_checks(solver)

    assert run_replacement_check(solver, check) is False

    assert check.time == clock.now() + timedelta(minutes=30)
    solver.get_agent_from_room.assert_not_called()


def test_first_room_read_supplies_peer_check_without_second_read(
    replacement_solver, clock
):
    solver = replacement_solver
    covers, _ = _prepare_same_room_reader(solver, clock, 2)
    for cover in covers:
        cover.time_stamp -= timedelta(hours=3)
    sync_replacement_checks(solver)
    first, second = solver.tasks

    assert run_replacement_check(solver, first) is False
    assert run_replacement_check(solver, second) is False

    assert solver.op_data.room_observations["central"] == 1
    solver.enter_room.assert_called_once()
    assert solver.read_accurate_mood.call_count == 2


@pytest.mark.parametrize("change", ["stale", "prediction", "unknown", "due"])
def test_insufficient_cache_still_reads_before_deciding(
    replacement_solver, clock, change
):
    solver = replacement_solver
    cover = solver.op_data.operators["薇薇安娜"]
    if change == "stale":
        cover.time_stamp -= timedelta(hours=3)
    elif change == "prediction":
        cover.mood_is_prediction = True
    elif change == "unknown":
        cover.time_stamp = None
    else:
        cover.mood, cover.depletion_rate = 1, 2
        cover.time_stamp -= timedelta(minutes=31)
    sync_replacement_checks(solver)

    assert run_replacement_check(solver, solver.tasks[0]) is False

    solver.get_agent_from_room.assert_called_once()


def test_environment_invalidation_requires_new_observation(replacement_solver, clock):
    solver = replacement_solver
    sync_replacement_checks(solver)
    check = solver.tasks[0]
    assert run_replacement_check(solver, check) is False
    clock.current += timedelta(minutes=10)
    invalidate_replacement_checks(solver)
    sync_replacement_checks(solver)

    assert run_replacement_check(solver, check) is False

    solver.get_agent_from_room.assert_called_once()
    assert check.time > clock.now()


def test_normal_observation_after_invalidation_satisfies_required_read(
    replacement_solver, clock
):
    solver = replacement_solver
    sync_replacement_checks(solver)
    check = solver.tasks[0]
    assert run_replacement_check(solver, check) is False
    clock.current += timedelta(minutes=10)
    invalidate_replacement_checks(solver)
    clock.current += timedelta(seconds=1)
    solver.op_data.update_detail("薇薇安娜", 23, "central", 0, True)
    sync_replacement_checks(solver)

    assert run_replacement_check(solver, check) is False

    solver.get_agent_from_room.assert_not_called()
    assert check.time == clock.now() + timedelta(hours=3, minutes=50)


@pytest.mark.parametrize("legacy", [False, True])
def test_saved_optional_countdown_still_reads_at_deadline(
    replacement_solver, clock, legacy
):
    solver = replacement_solver
    cover = solver.op_data.operators["薇薇安娜"]
    cover.lower_limit, cover.depletion_rate, cover.time_stamp = 6, 0, None
    solver.reading.update(mood=12, time=clock.now() + timedelta(hours=1))
    sync_replacement_checks(solver)
    check = solver.tasks[0]
    assert run_replacement_check(solver, check) is False
    assert check.time == clock.now() + timedelta(minutes=30)
    if legacy:
        del check.replacement_check_deadline
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    check = solver.tasks[0]
    clock.current = check.time
    solver.reading.update(mood=6, time=None)

    assert run_replacement_check(solver, check) is True

    assert solver.get_agent_from_room.call_count == 2
    assert solver.tasks[-1].plan == {"central": ["赫默"]}


@pytest.mark.parametrize("dependency", [False, True])
def test_idle_summary_preserves_failure_classification_and_task_name(
    dispatch_solver, clock, monkeypatch, dependency
):
    solver = dispatch_solver
    sync_replacement_checks(solver)
    check = solver.tasks[0]
    solver._retain_failed_task(
        check, "任务保留原因", ["central"], dependency=dependency
    )
    original_time = check.time
    solver.tasks.append(SchedulerTask(clock.now() + timedelta(hours=1)))
    solver._refresh_workshop_inventory = MagicMock()
    solver._refresh_observed_recovery_tasks = MagicMock()
    solver._schedule_maintenance_backup_check = MagicMock()
    solver._queue_missing_run_order_reads = MagicMock()
    solver.handle_idle_action = MagicMock()
    warnings = MagicMock()
    monkeypatch.setattr(base.logger, "warning", warnings)
    # 验证真实休眠入口在输出摘要之后，不实际等待。
    solver.handle_idle_action.side_effect = RuntimeError("idle boundary")

    with pytest.raises(RuntimeError, match="idle boundary"):
        solver.rest_until_next_task()

    if dependency:
        warnings.assert_not_called()
    else:
        warnings.assert_called_once_with(
            "未完成任务暂停派发：原时间=%s，任务=%s，原因=%s",
            original_time,
            "替班心情检查：薇薇安娜",
            "任务保留原因",
        )
    assert check.time == original_time and check in solver.tasks
    assert check.display_name == "替班心情检查：薇薇安娜"


def test_saved_timing_dependency_keeps_identity_and_normal_classification(
    replacement_solver, clock
):
    solver = replacement_solver
    cover = solver.op_data.operators["薇薇安娜"]
    cover.depletion_rate = 0
    sync_replacement_checks(solver)
    check = solver.tasks[0]
    assert run_replacement_check(solver, check) is False
    original_time = check.time
    check.execution_failure.pop("dependency")
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
    check = solver.tasks[0]

    sync_replacement_checks(solver)

    assert solver.tasks == [check] and check.time == original_time
    assert check.execution_failure["dependency"]
    solver._resume_failed_tasks()
    assert check.execution_failure
    solver.get_agent_from_room.assert_not_called()
