"""失败不生成计时重试；原任务由新实测或相关安排更新重新准入。"""

import copy
import pickle
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.tests import mass_mood_recovery_tests as native
from arknights_mower.tests import scheduler_recovery_preservation_tests as recovery
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    add_release_dorm,
    find_next_task,
    merge_release_dorm,
    plan_metadata,
    scheduling,
)

scheduler = recovery.scheduler
native_solver = native.solver
ROOM = "room_1_1"


def test_recovery_depot_completion_does_not_schedule_unchanged_stock_retry(
    scheduler, monkeypatch
):
    from arknights_mower.solvers import record
    from arknights_mower.utils import crash_recovery

    monkeypatch.setattr(crash_recovery, "workshop_inventory_names", lambda: {"碳"})
    monkeypatch.setattr(record, "get_inventory_counts", lambda: {})
    solver = scheduler.solver
    task = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.DEPOT)
    # A queued scan from the previous version still completes only once.
    task.process_recovery_inventory = ["碳"]
    independent = SchedulerTask(
        scheduler.clock.now() + timedelta(hours=1), task_type=TaskTypes.WORKSHOP
    )
    solver.tasks, solver.task = [task, independent], task
    solver.仓库扫描 = Mock(return_value=False)
    solver.infra_main()
    solver.仓库扫描.assert_called_once()
    assert solver.tasks == [independent]
    assert not recovery.config.stop_mower.is_set()
    scheduler.io.assert_not_called()


@pytest.fixture
def failed_arrangement(scheduler):
    solver = scheduler.solver
    now = scheduler.clock.now()
    solver.op_data.plan = {ROOM: [Room("陈", "", [])]}
    solver.op_data.products = {}
    solver.op_data.facility_states = {}
    solver.op_data.run_order_rooms = {}
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


@pytest.mark.parametrize("persisted", [False, True])
def test_reopened_arrangement_yields_after_navigation(
    scheduler, failed_arrangement, persisted, monkeypatch
):
    from arknights_mower.utils import operation_timing

    solver, task, _ = failed_arrangement
    monkeypatch.setattr(operation_timing, "_work_durations", {ROOM: [300]})
    original_time = task.time
    solver.op_data.operators["陈"].time_stamp += timedelta(seconds=1)
    solver._resume_failed_tasks()
    if persisted:
        task = pickle.loads(pickle.dumps(task))
    critical = SchedulerTask(
        scheduler.clock.now() + timedelta(seconds=90),
        task_type=TaskTypes.RUN_ORDER,
    )
    solver.tasks = [task, critical]
    solver.agent_arrange.reset_mock()
    solver.agent_arrange.side_effect = None
    # 进入基建页面后才发现预算不足，仍须让路给尚未到点的跑单。
    for _ in range(3):
        solver.task = task
        solver.infra_main()
        assert solver.task is None
        assert solver.tasks == [critical, task]
        assert task.time == original_time
        assert task.plan == {ROOM: ["陈"]}
    solver.agent_arrange.assert_not_called()

    independent = SchedulerTask(
        scheduler.clock.now() - timedelta(seconds=1), task_type=TaskTypes.DEPOT
    )
    solver.tasks.append(independent)
    scheduling(solver.tasks, time_now=scheduler.clock.now(), op_data=solver.op_data)
    assert find_next_task(solver.tasks) is independent
    solver.仓库扫描 = Mock()
    solver.task = independent
    solver.infra_main()
    solver.仓库扫描.assert_called_once()
    solver.tasks.remove(critical)
    solver.task = task
    solver.infra_main()
    solver.agent_arrange.assert_called_once()
    assert all(queued is not task for queued in solver.tasks)
    assert task.time == original_time
    scheduler.io.assert_not_called()


@pytest.mark.parametrize("critical_seconds", [120, 720])
@pytest.mark.parametrize("entry", ["worker", "idle"])
def test_worker_idle_preserves_reopened_priority_order(
    scheduler, failed_arrangement, monkeypatch, critical_seconds, entry
):
    from arknights_mower.utils import operation_timing

    solver, task, _ = failed_arrangement
    main = scheduler.main
    now = scheduler.clock.now()
    solver.op_data.operators["陈"].time_stamp += timedelta(seconds=1)
    solver._resume_failed_tasks()
    task.type = TaskTypes.RE_ORDER
    monkeypatch.setattr(operation_timing, "_work_durations", {ROOM: [1200]})
    critical = SchedulerTask(
        now + timedelta(seconds=critical_seconds), task_type=TaskTypes.RUN_ORDER
    )
    solver.tasks = [task, critical]
    monkeypatch.setattr(recovery.config, "conf", recovery.config.Conf())
    monkeypatch.setattr(main, "datetime", scheduler.clock)
    monkeypatch.setattr(main, "get_server_time", scheduler.clock.now)
    monkeypatch.setattr(main, "initialize", Mock(return_value=solver))
    monkeypatch.setattr(main, "refresh_resource_at_boundary", Mock())
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", Mock(return_value=None))
    monkeypatch.setattr(main, "_apply_version_update_resting_threshold", Mock())
    for daily in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, daily, now.date())
    solver.recruit_plan_solver = Mock()
    solver.mower_plan_solver = Mock()
    solver.has_maa_tasks = Mock(return_value=False)
    solver.run = Mock(side_effect=scheduler.module.MowerExit)
    solver._refresh_workshop_inventory = Mock()
    solver.handle_idle_action = Mock()
    solver._idle_sleep = Mock(side_effect=scheduler.module.MowerExit)
    solver.task_count = 0
    monkeypatch.setattr(scheduler.module.task_template, "render", Mock(return_value=""))
    monkeypatch.setattr(scheduler.module, "send_message", Mock())

    if entry == "worker":
        main.simulate(None)
    else:
        with pytest.raises(scheduler.module.MowerExit):
            solver.rest_until_next_task()

    solver.run.assert_not_called()
    solver._idle_sleep.assert_called_once_with(critical_seconds)
    assert solver.tasks == [critical, task]
    assert task.time == now
    assert task.plan == {ROOM: ["陈"]}
    scheduler.io.assert_not_called()


@pytest.mark.parametrize("persisted", [False, True])
def test_failed_restoration_keeps_shared_insertion_waiting_without_starving_work(
    scheduler, failed_arrangement, persisted
):
    solver, _, _ = failed_arrangement
    now = scheduler.clock.now()
    solver.op_data.operators = {
        "陈": SimpleNamespace(
            current_room=ROOM, current_index=0, time_stamp=now, is_working=lambda: True
        ),
        "但书": SimpleNamespace(
            current_room=ROOM, current_index=1, time_stamp=now, is_working=lambda: True
        ),
    }
    restore = SchedulerTask(
        now - timedelta(minutes=1), {ROOM: ["陈"]}, TaskTypes.RUN_ORDER
    )
    restore.run_order_original_roster = copy.deepcopy(restore.plan)
    restore.run_order_restore_pending = True
    insertion = SchedulerTask(
        now, {"room_2_1": ["但书"]}, TaskTypes.RUN_ORDER, "room_2_1"
    )
    solver.tasks = [restore, insertion]
    solver._retain_failed_task(restore, "原班恢复失败", [ROOM])
    if persisted:
        restore = pickle.loads(pickle.dumps(restore))
    solver.tasks = [restore, insertion]
    original = copy.deepcopy([vars(restore), vars(insertion)])
    solver.agent_arrange = Mock()
    for _ in range(4):
        work = SchedulerTask(now, {"room_1_2": ["银灰"]}, TaskTypes.SELF_CORRECTION)
        solver.tasks.append(work)
        solver._resume_failed_tasks()
        scheduling(solver.tasks, time_now=scheduler.clock.now(), op_data=solver.op_data)
        assert solver.find_next_task() is work
        assert work.time == now
        solver.task = work
        solver.infra_main()
        assert work not in solver.tasks
        assert solver.find_next_task() is None
        assert [vars(restore), vars(insertion)] == original
        scheduler.clock.current += timedelta(minutes=1)
    assert solver.agent_arrange.call_count == 4
    scheduler.io.assert_not_called()


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
    restored = pickle.loads(pickle.dumps(task))
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
        task = pickle.loads(pickle.dumps(task))
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
    task = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=f"{ROOM},gold",
    )
    solver.tasks = [task]
    solver.task = task
    solver.switch_base_products = Mock(
        side_effect=scheduler.module.ProductSwitchDeferred(
            "当前一份尚未完成", minutes=2
        )
    )
    solver.infra_main()
    solver.switch_base_products.assert_called_once()
    assert solver.tasks == [task]
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
        solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
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


@pytest.mark.parametrize("reader", ["ordinary", "patrol", "emergency"])
def test_complete_empty_room_read_reopens_failure_once(empty_room_solver, reader):
    solver, task = empty_room_solver
    if reader == "ordinary":
        observed = solver.get_agent_from_room(ROOM, force_mood=True)
        assert observed == [{"agent": "", "mood": -1}]
    elif reader == "patrol":
        solver._read_room_mood(ROOM, force_mood=True)
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
    solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
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


@pytest.mark.parametrize("cached_resident", [False, True])
@pytest.mark.parametrize("reader", ["ordinary", "patrol", "emergency"])
def test_unrecognized_slot_is_not_a_successful_empty_observation(
    empty_room_solver, cached_resident, reader
):
    import numpy as np

    solver, task = empty_room_solver
    resident = solver.op_data.operators[native.PRIMARY[0]]
    if cached_resident:
        resident._current_room, resident.current_index = ROOM, 0
        solver._retain_failed_task(task, "读房失败", [ROOM])
    original = (resident.current_room, resident.current_index, resident.time_stamp)
    solver.find.return_value = False
    solver.read_screen = Mock(return_value="")
    solver.sleep = Mock()
    solver.recog = SimpleNamespace(
        gray=np.zeros((1080, 1920), dtype=np.uint8), update=Mock()
    )
    if reader == "ordinary":
        observed = solver.get_agent_from_room(ROOM, force_mood=True)
        assert observed[0]["observed"] is False
    elif reader == "patrol":
        solver._read_room_mood(ROOM, force_mood=True)
    else:
        assert solver._emergency_read_rooms([ROOM])
    assert solver.read_screen.call_count == 3
    assert ROOM not in solver.op_data.room_observations
    assert (
        resident.current_room,
        resident.current_index,
        resident.time_stamp,
    ) == original
    solver._resume_failed_tasks()
    assert task.execution_failure
    assert find_next_task(solver.tasks) is None
    solver.find.return_value = True
    if reader == "ordinary":
        solver.get_agent_from_room(ROOM, force_mood=True)
    elif reader == "patrol":
        solver._read_room_mood(ROOM, force_mood=True)
    else:
        assert solver._emergency_read_rooms([ROOM])
    solver._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert find_next_task(solver.tasks) is task


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


@pytest.mark.parametrize("failure_kind", ["room", "recognition"])
@pytest.mark.parametrize("persisted", [False, True])
def test_failed_order_before_roster_capture_is_not_regenerated(
    scheduler, failure_kind, persisted
):
    solver = scheduler.solver
    now = scheduler.clock.now()
    solver.op_data.run_order_rooms = {ROOM, "room_1_2"}
    solver.op_data.run_order_replacements = Mock(return_value=[["但书"]])
    solver._emergency_run_order_available = Mock(return_value=True)
    solver.get_run_order_time = Mock(return_value=now + timedelta(minutes=10))
    task = SchedulerTask(now, {ROOM: ["但书"]}, TaskTypes.RUN_ORDER, meta_data=ROOM)
    solver.tasks, solver.task = [task], task
    solver.refresh_connecting = True
    solver.back_to_infrastructure = Mock()
    failure = (
        scheduler.module.RoomArrangementDeferred(ROOM, RuntimeError("插拔前读房失败"))
        if failure_kind == "room"
        else scheduler.module.RecognizeError("插拔前读房失败")
    )
    solver.agent_arrange = Mock(side_effect=failure)
    solver.infra_main()
    assert task.execution_failure
    assert not getattr(task, "run_order_original_roster", None)
    if persisted:
        solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
        task = solver.tasks[0]
    original = copy.deepcopy((task.time, task.plan, task.meta_data))
    for _ in range(4):
        solver.plan_run_order(ROOM)
        solver._resume_failed_tasks()
        scheduling(solver.tasks, time_now=now, op_data=solver.op_data)
        assert solver.tasks == [task]
        assert (task.time, task.plan, task.meta_data) == original
        assert find_next_task(solver.tasks) is None
    solver.get_run_order_time.assert_not_called()
    solver.plan_run_order("room_1_2")
    other = next(t for t in solver.tasks if t is not task)
    assert find_next_task(solver.tasks) is other
    solver.get_run_order_time.assert_called_once_with("room_1_2")
    solver.op_data.room_observations = {ROOM: 1}
    solver._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    solver.plan_run_order(ROOM)
    assert sum(t is task for t in solver.tasks) == 1
    assert len(solver.tasks) == 2
    solver.agent_arrange.side_effect = None
    solver.task = task
    solver.infra_main()
    assert task not in solver.tasks
    assert other in solver.tasks
    assert solver.agent_arrange.call_count == 2
    solver.plan_run_order(ROOM)
    assert len(solver.tasks) == 2
    assert sum(t.meta_data == ROOM for t in solver.tasks) == 1
    assert solver.get_run_order_time.call_count == 2


@pytest.mark.parametrize("compare_type", ["<", "=", ">"])
def test_existing_task_query_and_dispatch_use_distinct_failure_filters(
    scheduler, failed_arrangement, compare_type
):
    solver, task, later = failed_arrangement
    compare_time = (
        task.time
        + {"<": timedelta(seconds=1), "=": timedelta(), ">": -timedelta(seconds=1)}[
            compare_type
        ]
    )
    kwargs = {
        "compare_time": compare_time,
        "compare_type": compare_type,
        "task_type": task.type,
        "meta_data": task.meta_data,
    }
    assert solver.find_next_task(**kwargs) is None
    assert solver.find_next_task(**kwargs, scope=TaskScope.PENDING) is task
    assert find_next_task(solver.tasks, **kwargs, scope=TaskScope.PENDING) is task
    assert find_next_task(solver.tasks) is later


@pytest.mark.parametrize("reopened", [False, True])
def test_idle_release_generation_reuses_retained_task(native_solver, reopened):
    solver = native_solver
    name = native.COVERS[0]
    solver.op_data = solver.op_data.project_arrangements(
        [{"dormitory_1": ["冰酿", "闪灵", name, "", ""]}]
    )
    data = solver.op_data
    data.config.free_room = True
    _, bed = data.get_dorm_by_name(name)
    bed.time = native.NOW + timedelta(hours=1)
    add_release_dorm(solver.tasks, data, name)
    task = solver.tasks[0]
    solver._retain_failed_task(task, "清退读房失败", task.plan)
    if reopened:
        data.operators[name].time_stamp += timedelta(seconds=1)
        solver._resume_failed_tasks()
    original = copy.deepcopy((task.time, task.plan, task.meta_data))
    for _ in range(4):
        add_release_dorm(solver.tasks, data, name)
        assert solver.tasks == [task]
        assert (task.time, task.plan, task.meta_data) == original


@pytest.mark.parametrize("reopened", [False, True])
def test_charging_planner_reuses_retained_task(scheduler, reopened):
    solver = scheduler.solver
    task = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.FIAMMETTA)
    if reopened:
        task.execution_retained = True
    else:
        task.execution_failure = {"reason": "充能读房失败"}
    solver.tasks = [task]
    solver.op_data.run_order_rooms = {}
    solver.op_data.operators = {
        "菲亚梅塔": SimpleNamespace(current_room="dormitory_1", current_index=2)
    }
    solver.check_fia = Mock(return_value=({"dormitory_1": ["菲亚梅塔"]}, "dormitory_1"))
    solver._emergency_frozen = Mock(return_value=True)
    solver._emergency_filter_tasks = Mock()
    solver.enter_room = Mock(side_effect=AssertionError("重复充能读房"))
    for _ in range(4):
        solver.run_order_solver()
        assert solver.tasks == [task]
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("reading", ["empty", "unresolved", "unrelated"])
def test_prediction_invalidation_is_not_successful_failure_evidence(
    empty_room_solver, reading
):
    import numpy as np

    solver, task = empty_room_solver
    target = solver.op_data.operators[native.PRIMARY[0]]
    target.mood_is_prediction = True
    target.rest_mood_release_limit = target.upper_limit
    solver.emergency_state = {"phase": "staffing", "targets": {target.name: 16}}
    task.plan[ROOM] = [target.name]
    solver._retain_failed_task(task, "读取失败", [ROOM])
    # 兼容旧快照中误存的预测时间。
    task.execution_failure["snapshot"]["observations"][target.name] = (
        "",
        -1,
        target.time_stamp,
    )
    if reading == "unresolved":
        solver.find.return_value = False
        solver.read_screen = Mock(return_value="")
        solver.sleep = Mock()
        solver.recog = SimpleNamespace(
            gray=np.zeros((1080, 1920), dtype=np.uint8), update=Mock()
        )
        room = ROOM
    else:
        room = "room_1_2"
    assert solver._emergency_read_rooms([] if reading == "empty" else [room])
    assert target.time_stamp is None
    assert target.rest_mood_release_limit is None
    solver._resume_failed_tasks()
    assert task.execution_failure
    assert find_next_task(solver.tasks) is None


@pytest.mark.parametrize("reader", ["ordinary", "patrol", "emergency"])
def test_unresolved_dorm_roster_preserves_beds_and_release_task(native_solver, reader):
    import numpy as np

    solver = native_solver
    room, name = "dormitory_1", native.COVERS[0]
    solver.op_data = solver.op_data.project_arrangements(
        [{room: ["冰酿", "闪灵", name, "", ""]}]
    )
    data = solver.op_data
    data.config.free_room = True
    _, bed = data.get_dorm_by_name(name)
    bed.time = native.NOW + timedelta(hours=1)
    add_release_dorm(solver.tasks, data, name)
    task = solver.tasks[0]
    solver._retain_failed_task(task, "清退读房失败", [room])
    positions = {
        op.name: (op.current_room, op.current_index, op.time_stamp)
        for op in data.operators.values()
    }
    beds = [(b.name, b.time, b.position) for b in data.all_dorms()]
    for method in (
        "refresh_facility_state",
        "turn_on_room_detail",
        "wait_product_complete",
        "enter_room",
        "back",
        "back_to_infrastructure",
        "scroll_room_operators",
        "sleep",
    ):
        setattr(solver, method, Mock())
    solver.emergency_state = None
    solver.find = Mock(return_value=False)
    solver.read_screen = Mock(return_value="")
    solver.recog = SimpleNamespace(
        gray=np.zeros((1080, 1920), dtype=np.uint8), update=Mock()
    )
    if reader == "ordinary":
        solver.get_agent_from_room(room, force_mood=True)
    elif reader == "patrol":
        solver._read_room_mood(room, force_mood=True)
    else:
        assert solver._emergency_read_rooms([room])
    assert positions == {
        op.name: (op.current_room, op.current_index, op.time_stamp)
        for op in data.operators.values()
    }
    assert beds == [(b.name, b.time, b.position) for b in data.all_dorms()]
    assert task.release_dorm_targets() == {name: bed.position}
    solver._resume_failed_tasks()
    assert task.execution_failure
    assert find_next_task(solver.tasks) is None
    assert solver.tasks == [task]


@pytest.mark.parametrize("reopened", [False, True])
@pytest.mark.parametrize("serialized", [False, True])
@pytest.mark.parametrize("low_mood", [False, True])
@pytest.mark.parametrize(
    "kind",
    [TaskTypes.SELF_CORRECTION, TaskTypes.SHIFT_ON, TaskTypes.FILL_DORM],
)
def test_unrelated_shift_cycle_preserves_retained_execution(
    native_solver, kind, reopened, serialized, low_mood
):
    solver = native_solver
    solver.op_data.first_init = False
    if low_mood:
        solver.op_data.operators[native.PRIMARY[0]].mood = 1
    failed = SchedulerTask(
        native.NOW - timedelta(minutes=5), {ROOM: [native.PRIMARY[0]]}, kind
    )
    if kind == TaskTypes.FILL_DORM:
        failed.plan = {
            "dormitory_1": [
                "Current",
                "Current",
                "Current",
                "Current",
                native.COVERS[0],
            ]
        }
    else:
        solver.op_data.operators[native.PRIMARY[0]]._current_room = ""
        solver.op_data.operators[native.PRIMARY[0]].current_index = -1
    independent = native.PRIMARY[1]
    other_room = solver.op_data.operators[independent].room
    solver.op_data.operators[independent]._current_room = ""
    solver.op_data.operators[independent].current_index = -1
    solver.tasks = [failed]
    solver._retain_failed_task(failed, "换人失败", failed.plan)
    if reopened:
        failed.execution_failure = None
        failed.execution_retained = True
    if serialized:
        failed = pickle.loads(pickle.dumps(failed))
        solver.tasks = [failed]
    original = copy.deepcopy((failed.time, failed.plan, failed.meta_data))
    for _ in range(3):
        active = SchedulerTask(
            native.NOW, {other_room: [independent]}, TaskTypes.SELF_CORRECTION
        )
        solver.tasks.append(active)
        solver.task = active
        solver._prepare_shift_cycle(active)
        assert sum(t is failed for t in solver.tasks) == 1
        assert (failed.time, failed.plan, failed.meta_data) == original
        assert active.plan[other_room] == [independent]
        if kind == TaskTypes.FILL_DORM:
            assert active.plan.get("dormitory_1", ["Current"] * 5)[4] == "Current"
            assert native.PRIMARY[0] not in {
                name for row in active.plan.values() for name in row
            }
        else:
            assert ROOM not in active.plan
        solver.tasks.remove(active)
    if not reopened:
        solver._resume_failed_tasks()
        assert find_next_task(solver.tasks) is None
        relevant_room = next(iter(failed.plan))
        solver.op_data.room_observations[relevant_room] = 1
        solver._resume_failed_tasks()
    assert find_next_task(solver.tasks) is failed


def test_shift_cycle_retention_keeps_ordinary_due_coalescing(native_solver):
    solver = native_solver
    solver.op_data.first_init = False
    for name in native.PRIMARY[:2]:
        solver.op_data.operators[name]._current_room = ""
        solver.op_data.operators[name].current_index = -1
    first = SchedulerTask(
        native.NOW, {ROOM: [native.PRIMARY[0]]}, TaskTypes.SELF_CORRECTION
    )
    other = SchedulerTask(
        native.NOW, {"room_1_2": [native.PRIMARY[1]]}, TaskTypes.SHIFT_ON
    )
    solver.tasks, solver.task = [first, other], first
    solver._prepare_shift_cycle(first)
    assert solver.tasks == [first]
    assert first.plan[ROOM] == [native.PRIMARY[0]]
    assert first.plan["room_1_2"] == [native.PRIMARY[1]]


@pytest.mark.parametrize("reader", ["ordinary", "patrol", "emergency"])
@pytest.mark.parametrize("room", [ROOM, "dormitory_1"])
@pytest.mark.parametrize("observed_name", ["陈", ""])
def test_partial_roster_clears_confirmed_slot_and_preserves_unknown_slot(
    empty_room_solver, room, observed_name, reader
):
    import numpy as np

    solver, task = empty_room_solver
    data = solver.op_data
    known_index, unknown_index = (0, 1) if room == ROOM else (2, 3)
    if room == ROOM:
        data.plan[room].append(Room("银灰", "", []))
    old, unknown, incoming = (data.operators[name] for name in ("伊内丝", "银灰", "陈"))
    old._current_room, old.current_index = room, known_index
    unknown._current_room, unknown.current_index = room, unknown_index
    incoming._current_room, incoming.current_index = "", -1
    unknown_state = (unknown.current_room, unknown.current_index, unknown.time_stamp)
    if room.startswith("dorm"):
        old_bed = next(bed for bed in data.dorm if bed.position == (room, known_index))
        unknown_bed = next(
            bed for bed in data.dorm if bed.position == (room, unknown_index)
        )
        old_bed.name, unknown_bed.name = old.name, unknown.name
        unknown_bed.time = native.NOW + timedelta(hours=1)
    task.plan = {room: ["Current"] * len(data.plan[room])}
    task.strict_mood_limit = True
    task.meta_data = old.name
    solver.task = task
    solver._retain_failed_task(task, "名单识别未决", [room])
    solver.find = Mock(return_value=False)
    reads = [
        name
        for index in range(len(data.plan[room]))
        for name in (
            [observed_name] if index == known_index and observed_name else ["", "", ""]
        )
    ]
    solver.read_screen = Mock(side_effect=reads)
    # A positively identified empty slot needs no name reads.
    if not observed_name:
        slot_calls = 0

        def find_empty(*args, **kwargs):
            nonlocal slot_calls
            if args[0] != "infra_no_operator":
                return False
            slot_calls += 1
            return slot_calls == known_index * 3 + 1

        solver.find.side_effect = find_empty
        reads = [
            ""
            for index in range(len(data.plan[room]))
            if index != known_index
            for _ in range(3)
        ]
        solver.read_screen.side_effect = reads
    solver.read_accurate_mood = Mock(return_value=12)
    solver.read_operator_time = Mock(return_value=native.NOW + timedelta(hours=2))
    solver.sleep = Mock()
    solver.scroll_room_operators = Mock()
    solver.recog = SimpleNamespace(
        gray=np.zeros((1080, 1920), dtype=np.uint8), update=Mock()
    )
    if reader == "ordinary":
        result = solver.get_agent_from_room(room, force_mood=True)
        assert result[known_index]["agent"] == observed_name
        assert result[unknown_index]["observed"] is False
    elif reader == "patrol":
        solver._read_room_mood(room, force_mood=True)
    else:
        assert solver._emergency_read_rooms([room])
    assert [
        op.name
        for op in data.operators.values()
        if (op.current_room, op.current_index) == (room, known_index)
    ] == ([observed_name] if observed_name else [])
    assert (old.current_room, old.current_index) == ("", -1)
    assert (
        unknown.current_room,
        unknown.current_index,
        unknown.time_stamp,
    ) == unknown_state
    assert room not in data.room_observations
    if room.startswith("dorm"):
        assert old_bed.name == observed_name
        assert unknown_bed.name == unknown.name
        assert unknown_bed.time == native.NOW + timedelta(hours=1)
        assert old.rest_mood_release_limit == old.upper_limit


@pytest.mark.parametrize("reopened", [False, True])
@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.REFRESH_TIME])
def test_product_switch_refresh_keeps_retained_orders_and_deduplicates(
    native_solver, reopened, kind
):
    solver = native_solver
    other = "room_1_2"
    solver.op_data.run_order_rooms = {ROOM: {}, other: {}}
    task = SchedulerTask(native.NOW, {ROOM: ["但书"]}, kind, meta_data=ROOM)
    solver.tasks = [task]
    solver._retain_failed_task(task, "倒计时读取失败", task.plan)
    if reopened:
        solver.op_data.room_observations[ROOM] = 1
        solver._resume_failed_tasks()
    original = copy.deepcopy(vars(task))
    for _ in range(3):
        solver._refresh_orders_after_product_switch()
        assert any(queued is task for queued in solver.tasks)
        assert vars(task) == original
        assert [
            (queued.type, queued.meta_data)
            for queued in solver.tasks
            if queued is not task
        ] == [(TaskTypes.REFRESH_TIME, other)]


@pytest.mark.parametrize("reading", ["陈", "伊内丝", ""])
def test_rescue_readback_updates_compensation_only_after_confirmed_takeover(
    empty_room_solver, reading
):
    import numpy as np

    solver, takeover_task = empty_room_solver
    old = solver.op_data.operators["伊内丝"]
    old._current_room, old.current_index = ROOM, 0
    solver.task = takeover_task
    solver.emergency_state = {"phase": "staffing", "staffing_plan": {ROOM: ["陈"]}}
    restore = SchedulerTask(native.NOW, {ROOM: [old.name]}, TaskTypes.RUN_ORDER)
    restore.run_order_original_roster = copy.deepcopy(restore.plan)
    restore.emergency_original_roster = copy.deepcopy(restore.plan)
    restore.run_order_restore_pending = True
    solver.tasks.append(restore)
    original_time = restore.time
    solver.find = Mock(return_value=False)
    solver.read_screen = Mock(return_value=reading)
    solver.read_accurate_mood = Mock(return_value=12)
    solver.sleep = Mock()
    solver.recog = SimpleNamespace(
        gray=np.zeros((1080, 1920), dtype=np.uint8), update=Mock()
    )
    solver.get_agent_from_room(ROOM, force_mood=True)
    expected = {ROOM: ["陈" if reading == "陈" else old.name]}
    assert restore.plan == expected
    assert restore.run_order_original_roster == expected
    assert restore.emergency_original_roster == expected
    assert restore.time == original_time
    restored = pickle.loads(pickle.dumps(solver.tasks))
    assert restored[1].run_order_original_roster == expected


@pytest.mark.parametrize(
    "product, quantity",
    [("gold", 99), ("orirock", 54), ("orirock_device", 2)],
)
def test_unverified_manufacture_max_retains_task_until_new_observation(
    scheduler, monkeypatch, product, quantity
):
    monkeypatch.setattr(recovery.config.conf.product_switching, "enable", True)
    monkeypatch.setattr(scheduler.module, "save_exception", Mock())
    solver = scheduler.solver
    solver.op_data.products = {}
    solver.op_data.facility_states = {}
    solver.op_data.room_observations = {}
    original_time = scheduler.clock.now()
    task = SchedulerTask(
        original_time, task_type=TaskTypes.SWITCH_PRODUCT, meta_data=f"{ROOM},{product}"
    )
    solver.tasks, solver.task = [task], task
    solver.back_to_infrastructure = Mock()
    solver._open_manufacture_product_detail = Mock()
    solver.read_manufacture_product = Mock(return_value=product)
    solver._cache_facility_state = Mock()
    solver._read_manufacture_queue_count = Mock(return_value=1)
    solver._tap_product_point = Mock()
    solver.sleep = Mock()
    solver.find = Mock(return_value=False)

    solver.infra_main()

    assert task.execution_failure
    assert solver.tasks == [task]
    assert task.time == original_time
    reads = solver._read_manufacture_queue_count.call_count
    for _ in range(3):
        solver._resume_failed_tasks()
        scheduling(solver.tasks, time_now=scheduler.clock.now(), op_data=solver.op_data)
        assert find_next_task(solver.tasks) is None
    assert solver._read_manufacture_queue_count.call_count == reads
    assert find_next_task(solver.tasks) is None

    solver.op_data.room_observations[ROOM] = original_time + timedelta(seconds=1)
    solver._read_manufacture_queue_count.return_value = quantity
    solver._resume_failed_tasks()
    assert find_next_task(solver.tasks) is task
    solver.task = task
    solver.infra_main()
    assert solver.tasks == []
    assert task.time == original_time
    scheduler.io.assert_not_called()
