"""失败不生成计时重试；原任务由新实测或相关安排更新重新准入。"""

import copy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import jsonpickle
import pytest

from arknights_mower.tests import mass_mood_recovery_tests as native
from arknights_mower.tests import scheduler_recovery_preservation_tests as recovery
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
    merge_release_dorm,
    plan_metadata,
    scheduling,
)

scheduler = recovery.scheduler
native_solver = native.solver
ROOM = "room_1_1"


@pytest.fixture
def failed_arrangement(scheduler):
    solver = scheduler.solver
    now = scheduler.clock.now()
    solver.op_data.plan = {ROOM: [Room("陈", "", [])]}
    solver.op_data.products = {}
    solver.op_data.facility_states = {}
    solver.op_data.operators = {
        "陈": SimpleNamespace(current_room=ROOM, current_index=0, time_stamp=now)
    }
    for method in (
        "_prepare_shift_cycle",
        "_prepare_group_shift",
        "_switch_products_before_arrangement",
        "_defer_conflicting_product_shift_slots",
        "back_to_infrastructure",
        "_fill_empty_dorms",
        "plan_metadata",
    ):
        setattr(solver, method, Mock())
    solver._complete_group_shift = Mock(return_value=True)
    task = SchedulerTask(now, {ROOM: ["陈"]}, TaskTypes.SELF_CORRECTION)
    later = SchedulerTask(now + timedelta(hours=1), task_type=TaskTypes.SKILL_UPGRADE)
    solver.tasks = [task, later]
    solver.task = task
    solver.agent_arrange = Mock(
        side_effect=scheduler.module.RoomArrangementDeferred(
            ROOM, RuntimeError("读房失败")
        )
    )
    solver.infra_main()
    return solver, task, later


def test_failed_task_preserves_identity_time_and_remaining_plan(failed_arrangement):
    solver, task, later = failed_arrangement
    assert any(queued is task for queued in solver.tasks)
    assert task.time == later.time - timedelta(hours=1)
    assert task.plan == {ROOM: ["陈"]}
    assert task.execution_failure["reason"] == "读房失败"
    assert find_next_task(solver.tasks) is later


def test_elapsed_time_does_not_rearm_failed_work(scheduler, failed_arrangement):
    solver, task, later = failed_arrangement
    original_time = task.time
    for _ in range(8):
        scheduler.clock.current += timedelta(hours=1)
        solver._resume_failed_tasks()
        scheduling(solver.tasks, time_now=scheduler.clock.now(), op_data=solver.op_data)
        assert find_next_task(solver.tasks) is later
        assert task.time == original_time
    solver.agent_arrange.assert_called_once()


@pytest.mark.parametrize("failure_type", ["recognition", "room"])
def test_interrupted_insertion_dispatches_restoration_once(
    scheduler, monkeypatch, failure_type
):
    solver = scheduler.solver
    now = scheduler.clock.now()
    solver.op_data.all_dorms = lambda: []
    solver.op_data.operators = {
        "陈": SimpleNamespace(
            current_room=ROOM, current_index=0, time_stamp=now, is_working=lambda: True
        )
    }
    solver.back_to_infrastructure = Mock()
    monkeypatch.setattr(scheduler.module, "save_exception", Mock())
    task = SchedulerTask(now, {ROOM: ["但书"]}, TaskTypes.RUN_ORDER, meta_data=ROOM)
    solver.tasks = [task]
    solver._complete_group_shift = Mock(return_value=True)
    failure = (
        scheduler.module.RecognizeError("读房失败")
        if failure_type == "recognition"
        else scheduler.module.RoomArrangementDeferred(ROOM, RuntimeError("读房失败"))
    )

    def interrupted_insertion(*args):
        task.run_order_original_roster = {ROOM: ["陈"]}
        task.run_order_restore_pending = True
        solver._retain_run_order_restoration()
        raise failure

    solver.agent_arrange = Mock(side_effect=interrupted_insertion)
    solver.task = task
    solver.refresh_connecting = True
    solver.infra_main()
    assert task.time == now
    assert task.plan == {ROOM: ["陈"]}
    assert task.meta_data == ""
    assert find_next_task(solver.tasks) is task
    assert not hasattr(task, "execution_failure")
    assert not solver.error

    solver.agent_arrange.side_effect = failure
    solver.task = task
    solver.infra_main()
    assert task.execution_failure
    assert task.time == now
    for _ in range(8):
        scheduler.clock.current += timedelta(hours=1)
        solver._resume_failed_tasks()
        scheduling(solver.tasks, time_now=scheduler.clock.now(), op_data=solver.op_data)
        assert find_next_task(solver.tasks) is None
    assert solver.agent_arrange.call_count == 2

    solver.op_data.operators["陈"].time_stamp = scheduler.clock.now()
    solver._resume_failed_tasks()
    assert find_next_task(solver.tasks) is task
    assert task.time == now
    scheduler.io.assert_not_called()


@pytest.mark.parametrize("change", ["observation", "occupancy", "target", "layout"])
def test_related_update_rearms_original_task_once(
    scheduler, failed_arrangement, change
):
    solver, task, _ = failed_arrangement
    original_time = task.time
    if change == "observation":
        solver.op_data.operators["陈"].time_stamp += timedelta(seconds=1)
    elif change == "occupancy":
        solver.op_data.operators["陈"].current_room = ""
    elif change == "target":
        task.plan[ROOM] = ["Current"]
    else:
        solver.op_data.plan[ROOM][0].agent = "银灰"
    solver._resume_failed_tasks()
    assert not hasattr(task, "execution_failure")
    assert task.time == original_time
    assert find_next_task(solver.tasks) is task
    solver.agent_arrange.side_effect = None
    solver.task = task
    solver.infra_main()
    assert solver.agent_arrange.call_count == 2
    assert all(queued is not task for queued in solver.tasks)


def test_other_task_dispatches_while_failed_work_is_retained(
    scheduler, failed_arrangement
):
    solver, task, _ = failed_arrangement
    depot = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.DEPOT)
    solver.tasks.append(depot)
    scan = Mock()
    solver.仓库扫描 = scan
    solver.run()
    scan.assert_called_once()
    solver.agent_arrange.assert_called_once()
    assert any(queued is task for queued in solver.tasks)
    assert all(queued is not depot for queued in solver.tasks)


def test_failure_survives_serialization_and_stale_cleanup(
    scheduler, failed_arrangement
):
    solver, task, _ = failed_arrangement
    restored = jsonpickle.decode(jsonpickle.encode(task))
    solver.tasks = [restored]
    scheduler.clock.current += timedelta(hours=1)
    solver.handle_error(True)
    solver._resume_failed_tasks()
    assert any(queued is restored for queued in solver.tasks)
    assert restored.time == task.time
    assert restored.execution_failure == task.execution_failure
    assert find_next_task([restored]) is None


@pytest.mark.parametrize("persisted", [False, True])
def test_rearmed_old_task_survives_repeated_cleanup(
    scheduler, failed_arrangement, persisted
):
    solver, task, _ = failed_arrangement
    original_time = task.time
    scheduler.clock.current += timedelta(minutes=20)
    solver.op_data.operators["陈"].time_stamp = scheduler.clock.now()
    solver._resume_failed_tasks()
    assert not hasattr(task, "execution_failure")
    if persisted:
        task = jsonpickle.decode(jsonpickle.encode(task))
        solver.tasks = [task]
    for _ in range(3):
        stale = SchedulerTask(
            original_time, {"meeting": ["Current"]}, TaskTypes.SHIFT_OFF
        )
        solver.tasks.append(stale)
        solver.handle_error(True)
        assert any(queued is task for queued in solver.tasks)
        assert all(queued is not stale for queued in solver.tasks)
        assert task.time == original_time
        assert task.plan == {ROOM: ["陈"]}
        assert find_next_task(solver.tasks) is task
    solver.agent_arrange.side_effect = None
    solver.run()
    assert solver.agent_arrange.call_count == 2
    assert all(queued is not task for queued in solver.tasks)
    scheduler.io.assert_not_called()


def test_run_dispatches_rearmed_old_task_before_expiry_cleanup(
    scheduler, failed_arrangement
):
    solver, task, _ = failed_arrangement
    original_time = task.time
    scheduler.clock.current += timedelta(minutes=20)
    solver.op_data.operators["陈"].time_stamp = scheduler.clock.now()
    solver.agent_arrange.side_effect = None
    solver.run()
    assert solver.agent_arrange.call_count == 2
    assert task.time == original_time
    assert all(queued is not task for queued in solver.tasks)
    scheduler.io.assert_not_called()


def test_only_failed_task_keeps_normal_planning_without_replaying(
    scheduler, failed_arrangement
):
    solver, task, _ = failed_arrangement
    solver.tasks = [task]
    solver.run()
    solver.agent_arrange.assert_called_once()
    solver.agent_get_mood.assert_called_once()
    assert any(queued is task for queued in solver.tasks)
    assert task.execution_failure
    assert find_next_task(solver.tasks) is not task


def test_unrelated_observation_does_not_rearm_failure(scheduler, failed_arrangement):
    solver, task, _ = failed_arrangement
    solver.op_data.operators["银灰"] = SimpleNamespace(
        current_room="meeting", current_index=0, time_stamp=scheduler.clock.now()
    )
    solver._resume_failed_tasks()
    assert task.execution_failure


def test_worker_idle_uses_next_dispatchable_task(
    scheduler, failed_arrangement, monkeypatch
):
    solver, task, later = failed_arrangement
    later.time = scheduler.clock.now() + timedelta(minutes=6)
    main = scheduler.main
    monkeypatch.setattr(main, "datetime", scheduler.clock)
    monkeypatch.setattr(main, "initialize", Mock(return_value=solver))
    monkeypatch.setattr(main, "refresh_resource_at_boundary", Mock())
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", Mock(return_value=None))
    monkeypatch.setattr(main, "_apply_version_update_resting_threshold", Mock())
    solver.rest_until_next_task = Mock(side_effect=scheduler.module.MowerExit)
    solver.run = Mock(side_effect=scheduler.module.MowerExit)
    main.simulate(None)
    solver.rest_until_next_task.assert_called_once()
    solver.run.assert_not_called()
    assert task.execution_failure
    assert task.time < later.time


def test_confirmed_production_wait_retains_its_existing_timer(scheduler, monkeypatch):
    monkeypatch.setattr(recovery.config.conf.product_switching, "enable", True)
    solver = scheduler.solver
    task = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.SWITCH_PRODUCT)
    solver.tasks = [task]
    solver.task = task
    solver.switch_base_products = Mock(
        side_effect=scheduler.module.ProductSwitchDeferred(
            "当前一份尚未完成", minutes=2
        )
    )
    solver.infra_main()
    assert task.time == scheduler.clock.now() + timedelta(minutes=2)
    assert not hasattr(task, "execution_failure")
    assert find_next_task(solver.tasks) is task


def test_trade_lock_retains_only_failed_target(scheduler, monkeypatch):
    monkeypatch.setattr(recovery.config.conf.product_switching, "enable", True)
    solver = scheduler.solver
    solver.op_data.products = {}
    solver.op_data.facility_states = {}
    failed = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=f"{ROOM},orundum",
    )
    other = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data="room_1_2,gold",
    )
    solver.tasks, solver.task = [failed, other], failed
    solver.switch_base_products = Mock(
        side_effect=scheduler.module.ProductSwitchFailed("实际贸易站未达到3级", [ROOM])
    )
    solver.infra_main()
    assert failed.execution_failure
    assert not hasattr(other, "execution_failure")
    assert find_next_task(solver.tasks) is other
    assert failed.time == other.time == scheduler.clock.now()


@pytest.mark.parametrize("kind", [TaskTypes.SHIFT_ON, TaskTypes.RELEASE_DORM])
@pytest.mark.parametrize("status", ["failed", "reopened", "persisted"])
def test_native_replanning_preserves_retained_execution(native_solver, kind, status):
    solver = native_solver
    data = solver.op_data
    data.config.free_room = True
    name = native.PRIMARY[0] if kind == TaskTypes.SHIFT_ON else native.COVERS[0]
    room = data.operators[native.PRIMARY[0]].room
    arrangement = {"dormitory_1": ["冰酿", "闪灵", name, "", ""]}
    if kind == TaskTypes.SHIFT_ON:
        arrangement[room] = [native.COVERS[0]]
    solver.op_data = data.project_arrangements([arrangement])
    data = solver.op_data
    _, bed = data.get_dorm_by_name(name)
    bed.time = native.NOW
    data.operators[name].mood = 24
    data.operators[name].time_stamp = native.NOW
    solver.tasks = plan_metadata(data, [])
    task = next(t for t in solver.tasks if t.type == kind)
    solver._retain_failed_task(task, "读房恢复耗尽", task.plan)
    if status != "failed":
        data.operators[name].time_stamp += timedelta(seconds=1)
        solver._resume_failed_tasks()
        assert not getattr(task, "execution_failure", None)
    if status == "persisted":
        solver.tasks = jsonpickle.decode(jsonpickle.encode(solver.tasks))
        task = next(t for t in solver.tasks if t.type == kind)
    original = copy.deepcopy((task.time, task.plan, task.meta_data))
    failure = copy.deepcopy(getattr(task, "execution_failure", None))
    for _ in range(4):
        solver.tasks = plan_metadata(data, solver.tasks)
        solver._resume_failed_tasks()
        scheduling(solver.tasks, time_now=native.NOW, op_data=data)
        assert sum(t is task for t in solver.tasks) == 1
        assert (task.time, task.plan, task.meta_data) == original
        assert getattr(task, "execution_failure", None) == failure
        assert not any(
            t is not task and t.type == kind and t.plan == task.plan
            for t in solver.tasks
        )
        if status == "failed":
            assert find_next_task([task]) is None
        else:
            assert find_next_task([task]) is task

    # 无关主班仍能派生回班；保留任务不使整个规划器停转。
    other = native.PRIMARY[1]
    other_room = data.operators[other].room
    solver.op_data = data.project_arrangements(
        [
            {
                "dormitory_1": ["Current", "Current", "Current", other, ""],
                other_room: [native.COVERS[1]],
            }
        ]
    )
    data = solver.op_data
    _, bed = data.get_dorm_by_name(other)
    bed.time = native.NOW
    data.operators[other].mood = 24
    data.operators[other].time_stamp = native.NOW
    solver.tasks = plan_metadata(data, solver.tasks)
    assert sum(t is task for t in solver.tasks) == 1
    assert (task.time, task.plan, task.meta_data) == original
    assert any(
        t is not task
        and t.type == TaskTypes.SHIFT_ON
        and other in {n for row in t.plan.values() for n in row}
        for t in solver.tasks
    )


@pytest.mark.parametrize("reopened", [False, True])
def test_release_merging_never_consumes_retained_execution(scheduler, reopened):
    now = scheduler.clock.now()
    retained = SchedulerTask(
        now,
        {"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]},
        TaskTypes.RELEASE_DORM,
        meta_data="陈",
    )
    if reopened:
        retained.execution_retained = True
    else:
        retained.execution_failure = {"reason": "读房失败"}
    other = SchedulerTask(
        now + timedelta(minutes=1),
        {"dormitory_1": ["Current", "Current", "Current", "Free", "Current"]},
        TaskTypes.RELEASE_DORM,
        meta_data="银灰",
    )
    tasks = [retained, other]
    original = copy.deepcopy((retained.time, retained.plan, retained.meta_data))
    for _ in range(3):
        merge_release_dorm(tasks, 5)
        assert len(tasks) == 2
        assert any(t is retained for t in tasks)
        assert any(t is other for t in tasks)
        assert (retained.time, retained.plan, retained.meta_data) == original


@pytest.fixture
def empty_room_solver(native_solver):
    solver = native_solver
    for op in solver.op_data.operators.values():
        if op.current_room == ROOM:
            op._current_room, op.current_index = "", -1
    for method in (
        "enter_room",
        "back",
        "back_to_infrastructure",
        "refresh_facility_state",
        "turn_on_room_detail",
        "wait_product_complete",
    ):
        setattr(solver, method, Mock())
    solver.find = Mock(return_value=True)  # 每个实际槽位均识别为空。
    solver.emergency_state = None
    task = SchedulerTask(native.NOW, {ROOM: [native.COVERS[0]]})
    task.emergency_staffing = True
    solver.tasks = [task]
    solver._retain_failed_task(task, "读房恢复耗尽", [ROOM])
    return solver, task


@pytest.mark.parametrize("reader", ["ordinary", "emergency"])
def test_complete_empty_room_read_reopens_failure_once(empty_room_solver, reader):
    solver, task = empty_room_solver
    if reader == "ordinary":
        observed = solver.get_agent_from_room(ROOM, force_mood=True)
        assert observed == [{"agent": "", "mood": -1}]
    else:
        assert solver._emergency_read_rooms([ROOM])
    assert solver.op_data.room_observations[ROOM] == 1
    solver._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert find_next_task(solver.tasks) is task
    assert task.time == native.NOW
    solver._retain_failed_task(task, "再次失败", [ROOM])
    for _ in range(4):
        solver._resume_failed_tasks()
        assert find_next_task(solver.tasks) is None
    assert len(solver.tasks) == 1
    assert solver.op_data.room_observations[ROOM] == 1


def test_failed_empty_room_read_does_not_reopen_failure(empty_room_solver):
    solver, task = empty_room_solver
    solver.find.side_effect = RuntimeError("页面识别失败")
    with pytest.raises(RuntimeError, match="页面识别失败"):
        solver._emergency_read_rooms([ROOM])
    assert ROOM not in solver.op_data.room_observations
    solver._resume_failed_tasks()
    assert task.execution_failure
    assert find_next_task(solver.tasks) is None


def test_unrelated_empty_room_read_does_not_reopen_failure(empty_room_solver):
    solver, task = empty_room_solver
    other_room = "room_1_2"
    solver.get_agent_from_room(other_room, force_mood=True)
    assert solver.op_data.room_observations == {other_room: 1}
    solver._resume_failed_tasks()
    assert task.execution_failure
    assert find_next_task(solver.tasks) is None


def test_legacy_failure_without_room_revision_stays_retained(empty_room_solver):
    solver, task = empty_room_solver
    del task.execution_failure["snapshot"]["room_observations"]
    solver.tasks = jsonpickle.decode(jsonpickle.encode(solver.tasks))
    task = solver.tasks[0]
    solver._resume_failed_tasks()
    assert task.execution_failure
    assert find_next_task(solver.tasks) is None
    solver.get_agent_from_room(ROOM, force_mood=True)
    solver._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)


@pytest.mark.parametrize("release_kind", ["strict", "emergency"])
@pytest.mark.parametrize("reopened", [False, True])
def test_specialized_release_replanning_preserves_execution(
    native_solver, release_kind, reopened
):
    solver = native_solver
    name = native.COVERS[0]
    solver.op_data = solver.op_data.project_arrangements(
        [{"dormitory_1": ["冰酿", "闪灵", name, "", ""]}]
    )
    data = solver.op_data
    op = data.operators[name]
    op.mood, op.time_stamp = 12, native.NOW
    _, bed = data.get_dorm_by_name(name)
    bed.time = native.NOW + timedelta(hours=1)
    if release_kind == "strict":
        data.config.operator_mood_limits = {name: {"lower": 0, "upper": 12}}
        data.init_mood_limit()
        solver.tasks = plan_metadata(data, [])
        task = next(t for t in solver.tasks if t.strict_mood_limit)
    else:
        solver.emergency_state = {"phase": "recovering", "targets": {name: 12}}
        solver._emergency_replan_releases()
        task = next(t for t in solver.tasks if t.emergency_recovery_release)
    solver._retain_failed_task(task, "读房恢复耗尽", task.plan)
    if reopened:
        op.time_stamp += timedelta(seconds=1)
        solver._resume_failed_tasks()
    original = copy.deepcopy((task.time, task.plan, task.meta_data))
    for _ in range(4):
        if release_kind == "strict":
            solver.tasks = plan_metadata(data, solver.tasks)
        else:
            solver._emergency_replan_releases()
        assert sum(t is task for t in solver.tasks) == 1
        assert not any(
            t is not task and name in t.release_dorm_targets() for t in solver.tasks
        )
        assert (task.time, task.plan, task.meta_data) == original
    if release_kind == "strict":
        # 部分换班分支同样保留失败清退，不能重新生成可派发副本。
        partial = SchedulerTask(native.NOW, {"room_1_2": ["Current"]})
        partial.backup_shift_active = True
        solver.tasks.append(partial)
        solver.tasks = plan_metadata(data, solver.tasks)
        assert sum(t is task for t in solver.tasks) == 1
        assert (task.time, task.plan, task.meta_data) == original


def test_room_observation_and_failure_survive_saved_state(
    empty_room_solver, monkeypatch, tmp_path
):
    from arknights_mower import __main__ as main
    from arknights_mower.solvers import record

    solver, task = empty_room_solver
    solver.get_agent_from_room(ROOM, force_mood=True)
    solver._resume_failed_tasks()
    solver._retain_failed_task(task, "再次失败", [ROOM])
    for field in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, field, None)
    solver.task_count = 0
    monkeypatch.setattr(main, "base_scheduler", solver)
    monkeypatch.setattr(
        record,
        "get_path",
        lambda path: tmp_path if path == "@app/tmp" else tmp_path / "record.db",
    )
    monkeypatch.setattr(record, "_tables_created", False)
    assert record.save_current_state()
    saved = record.load_state()
    assert saved["room_observations"] == {ROOM: 1}
    solver.tasks = saved["tasks"]
    solver.op_data.room_observations = saved["room_observations"]
    task = solver.tasks[0]
    solver._resume_failed_tasks()
    assert task.execution_failure
    assert find_next_task(solver.tasks) is None
    solver.get_agent_from_room(ROOM, force_mood=True)
    solver._resume_failed_tasks()
    assert solver.op_data.room_observations == {ROOM: 2}
    assert not getattr(task, "execution_failure", None)
    assert find_next_task(solver.tasks) is task


def test_unrecognized_slot_is_not_a_successful_empty_observation(empty_room_solver):
    import numpy as np

    solver, task = empty_room_solver
    solver.find.return_value = False
    solver.read_screen = Mock(return_value="")
    solver.sleep = Mock()
    solver.recog = SimpleNamespace(
        gray=np.zeros((1080, 1920), dtype=np.uint8), update=Mock()
    )
    solver.get_agent_from_room(ROOM, force_mood=True)
    assert solver.read_screen.call_count == 3
    assert ROOM not in solver.op_data.room_observations
    solver._resume_failed_tasks()
    assert task.execution_failure
    assert find_next_task(solver.tasks) is None


@pytest.mark.parametrize("failed_kind", ["return", "recovery_release"])
def test_retained_work_keeps_independent_personal_limit_release(
    native_solver, failed_kind
):
    solver = native_solver
    name = native.PRIMARY[0]
    room = solver.op_data.operators[name].room
    solver.op_data = solver.op_data.project_arrangements(
        [{"dormitory_1": ["冰酿", "闪灵", name, "", ""], room: [native.COVERS[0]]}]
    )
    data = solver.op_data
    data.config.operator_mood_limits = {name: {"lower": 0, "upper": 20}}
    data.init_mood_limit()
    op = data.operators[name]
    op.mood, op.time_stamp = 10, native.NOW
    _, bed = data.get_dorm_by_name(name)
    bed.time = native.NOW + timedelta(hours=1)
    if failed_kind == "return":
        solver.tasks = plan_metadata(data, [])
        task = next(t for t in solver.tasks if t.type == TaskTypes.SHIFT_ON)
    else:
        solver.emergency_state = {"phase": "recovering", "targets": {name: 12}}
        solver._emergency_replan_releases()
        task = next(t for t in solver.tasks if t.emergency_recovery_release)
    strict = next(t for t in solver.tasks if t.strict_mood_limit)
    deadline = strict.time
    solver._retain_failed_task(task, "读房恢复耗尽", task.plan)
    for _ in range(3):
        if failed_kind == "return":
            solver.tasks = plan_metadata(data, solver.tasks)
        else:
            solver._emergency_replan_releases()
        assert any(t is task for t in solver.tasks)
        releases = [t for t in solver.tasks if t.strict_mood_limit]
        assert len(releases) == 1
        assert releases[0].time == deadline
        assert not getattr(releases[0], "execution_failure", None)
        assert find_next_task(releases) is releases[0]
