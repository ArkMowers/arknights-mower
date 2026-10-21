"""原班恢复的补充实读沿用正常唤醒，不因失败创建重复巡检。"""

import copy
import pickle
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from arknights_mower.solvers import record
from arknights_mower.tests.scheduler_recovery_preservation_tests import (
    scheduler as scheduler,
)
from arknights_mower.utils import config, operators
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    blocked_run_order_ids,
)

ROOM = "room_1_1"
START = datetime(2026, 10, 21, 19, 31)
ORIGINAL_TIME = datetime(2026, 10, 21, 17, 59, 55)


@pytest.fixture
def paused_restoration(scheduler, monkeypatch):
    solver, base, clock = scheduler.solver, scheduler.module, scheduler.clock
    clock.current = START
    monkeypatch.setattr(operators, "datetime", clock)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "wake_scheduler", Event())
    config.conf.enable_mastery = False
    config.conf.close_simulator_when_idle = False
    monkeypatch.setattr(base, "_training_room_scan_disabled", True)
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    monkeypatch.setattr(base, "save_exception", Mock())
    monkeypatch.setattr(record, "save_agent_action", Mock())
    monkeypatch.setattr(base, "refresh_resource_at_boundary", Mock())
    monkeypatch.setattr(base.logger, "disabled", True)

    def sleep(seconds):
        clock.current += timedelta(seconds=seconds)

    monkeypatch.setattr(base, "csleep", Mock(side_effect=sleep))
    data = Operators(
        {
            "default_plan": Plan(
                {ROOM: [Room("图耶", "", ["但书", "伺夜"])]},
                PlanConfig("", "", ""),
            ),
            "backup_plans": [],
        }
    )
    assert data.init_and_validate() is None
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    sampled = datetime(2026, 10, 21, 18, 4, 28)
    for operator in data.operators.values():
        operator._current_room, operator.current_index = "", -1
        operator.time_stamp = sampled
        operator.mood, operator.depletion_rate = 24, 0
    data.operators["图耶"].time_stamp = None
    data.operators["图耶"].mood = 12
    resident = data.operators["但书"]
    resident._current_room, resident.current_index = ROOM, 0
    resident.mood = 23.69
    data.room_observations[ROOM] = 1
    solver.op_data = data
    restore = SchedulerTask(ORIGINAL_TIME, {ROOM: ["图耶"]}, TaskTypes.RUN_ORDER)
    restore.run_order_original_roster = copy.deepcopy(restore.plan)
    restore.run_order_restore_pending = True
    order = SchedulerTask(
        datetime(2026, 10, 21, 21, 3, 1),
        {"room_2_1": ["Current", "但书", "龙舌兰"]},
        TaskTypes.RUN_ORDER,
        "room_2_1",
    )
    solver.tasks, solver.task = [restore, order], None
    solver._retain_failed_task(restore, "清空选择后旧蓝框尚未消失", [ROOM])
    solver.agent_get_mood = base.BaseSchedulerSolver.agent_get_mood.__get__(solver)
    solver.recog = SimpleNamespace(
        gray=np.zeros((1080, 1920), dtype=np.uint8),
        update=Mock(),
        reset_after_external_control=Mock(),
    )
    for name in (
        "enter_room",
        "back",
        "refresh_facility_state",
        "turn_on_room_detail",
        "wait_product_complete",
    ):
        setattr(solver, name, Mock())
    solver.find = Mock(
        side_effect=lambda name, *a, **k: True if name == "control_central" else None
    )
    solver.read_screen = Mock(return_value="但书")
    solver.read_accurate_mood = Mock(return_value=23)
    solver.sleep = Mock()
    return SimpleNamespace(
        solver=solver, restore=restore, order=order, scheduler=scheduler
    )


def patrol(case):
    assert case.solver.agent_get_mood(return_plan=True) == {}
    case.solver._resume_failed_tasks()


def assert_retained(case):
    task = case.restore
    assert task in case.solver.tasks
    assert task.execution_failure
    assert task.time == ORIGINAL_TIME
    assert task.plan == {ROOM: ["图耶"]}
    assert id(case.order) in blocked_run_order_ids(
        case.solver.tasks, case.solver.op_data
    )


def test_normal_wakeup_observes_restoration_despite_recent_resident_mood(
    paused_restoration,
):
    case, solver = paused_restoration, paused_restoration.solver
    original = copy.deepcopy(vars(case.restore))
    assert solver.op_data.operators["图耶"].need_to_refresh()
    assert not solver.op_data.operators["但书"].need_to_refresh()
    patrol(case)
    solver.enter_room.assert_not_called()
    assert_retained(case)

    solver._idle_sleep(60)
    solver._resume_failed_tasks()
    assert_retained(case)
    assert vars(case.restore) == original
    patrol(case)

    solver.enter_room.assert_called_once_with(ROOM)
    assert solver.op_data.room_observations[ROOM] == 2
    assert not getattr(case.restore, "execution_failure", None)
    assert solver.find_next_task() is case.restore
    assert case.restore.time == ORIGINAL_TIME
    assert case.restore.plan == {ROOM: ["图耶"]}
    assert id(case.order) in blocked_run_order_ids(solver.tasks, solver.op_data)
    case.scheduler.io.assert_not_called()


def test_repeated_run_after_restoration_failure_does_not_create_observations(
    paused_restoration, monkeypatch
):
    case, solver = paused_restoration, paused_restoration.solver
    solver._initial_mood_refresh_rooms = {ROOM}
    patrol(case)
    solver._retain_failed_task(case.restore, "原班恢复再次失败", [ROOM])
    solver.enter_room.reset_mock()
    solver._fill_empty_dorms = Mock()
    monkeypatch.setattr(
        case.scheduler.module.SceneGraphSolver,
        "run",
        lambda self: self.agent_get_mood(return_plan=True),
    )
    for _ in range(4):
        solver.run()
        assert_retained(case)
    solver.enter_room.assert_not_called()
    assert solver.op_data.room_observations[ROOM] == 2
    case.scheduler.io.assert_not_called()


def test_observation_for_previous_failure_does_not_apply_to_new_failure(
    paused_restoration,
):
    case, solver = paused_restoration, paused_restoration.solver
    old_failure = case.restore.execution_failure
    solver._idle_sleep(60)
    solver._retain_failed_task(case.restore, "新的恢复失败", [ROOM])
    assert case.restore.execution_failure is not old_failure
    patrol(case)
    solver.enter_room.assert_not_called()
    assert_retained(case)


@pytest.mark.parametrize("unreliable", ["unresolved", "exception"])
def test_failed_observation_uses_this_wakeups_read_without_repeated_dispatch(
    paused_restoration, unreliable
):
    case, solver = paused_restoration, paused_restoration.solver
    solver._idle_sleep(60)
    if unreliable == "unresolved":
        solver.read_screen.return_value = ""
        patrol(case)
    else:
        solver.read_screen.side_effect = RuntimeError("读取房间失败")
        with pytest.raises(RuntimeError, match="读取房间失败"):
            patrol(case)
    read_count = solver.read_screen.call_count
    assert read_count > 0
    assert solver.op_data.room_observations[ROOM] == 1
    assert_retained(case)
    solver.read_screen.side_effect = None
    solver.read_screen.return_value = "但书"
    for _ in range(4):
        patrol(case)
        assert_retained(case)
    assert solver.read_screen.call_count == read_count
    solver._idle_sleep(60)
    patrol(case)
    assert solver.op_data.room_observations[ROOM] == 2
    assert not getattr(case.restore, "execution_failure", None)


@pytest.mark.parametrize("seconds,allow_wakeup", [(0, True), (60, False)])
def test_nonordinary_wait_does_not_supply_restoration_observations(
    paused_restoration, seconds, allow_wakeup
):
    case, solver = paused_restoration, paused_restoration.solver
    solver._idle_sleep(seconds, allow_wakeup=allow_wakeup)
    patrol(case)
    solver.enter_room.assert_not_called()
    assert_retained(case)


def test_priority_work_defers_observation_without_consuming_it(paused_restoration):
    case, solver = paused_restoration, paused_restoration.solver
    solver._idle_sleep(60)
    critical = SchedulerTask(
        case.scheduler.clock.now() + timedelta(seconds=30),
        task_type=TaskTypes.SKILL_UPGRADE,
    )
    solver.tasks.insert(0, critical)
    solver.task = None
    solver.planned = False
    solver.infra_main()
    solver.enter_room.assert_not_called()
    assert_retained(case)
    solver.tasks.remove(critical)
    patrol(case)
    solver.enter_room.assert_called_once_with(ROOM)
    assert not getattr(case.restore, "execution_failure", None)


def test_cancelled_wait_does_not_supply_an_observation(paused_restoration, monkeypatch):
    case, solver = paused_restoration, paused_restoration.solver
    monkeypatch.setattr(
        case.scheduler.module,
        "csleep",
        Mock(side_effect=case.scheduler.module.MowerExit),
    )
    with pytest.raises(case.scheduler.module.MowerExit):
        solver._idle_sleep(60)
    patrol(case)
    solver.enter_room.assert_not_called()
    assert_retained(case)


@pytest.mark.parametrize("failure_stage", ["restart", "reconnect", "reset"])
@pytest.mark.parametrize("new_failure", [False, True])
def test_device_recovery_preserves_only_the_failure_captured_before_waiting(
    paused_restoration, monkeypatch, failure_stage, new_failure
):
    case, solver = paused_restoration, paused_restoration.solver
    main = case.scheduler.main
    if failure_stage == "reset":
        solver.recog.reset_after_external_control.side_effect = ConnectionError(
            "画面复位失败"
        )
    else:
        config.conf.close_simulator_when_idle = True
        solver._simulator_closed_for_idle = True
        solver._sync_idle_device = Mock()
        monkeypatch.setattr(
            case.scheduler.module,
            "restart_simulator",
            Mock(return_value=failure_stage != "restart"),
        )
        if failure_stage == "reconnect":
            solver.device.reconnect.side_effect = ConnectionError("连接失败")
    with pytest.raises(ConnectionError):
        solver._idle_sleep(60)
    assert solver._idle_observation_pending
    if new_failure:
        solver._retain_failed_task(case.restore, "等待期间产生的新失败", [ROOM])
    monkeypatch.setattr(
        main,
        "device_control",
        SimpleNamespace(
            shutdown_requested=False,
            recover=Mock(return_value=SimpleNamespace(unwrap=lambda: Mock())),
        ),
    )
    monkeypatch.setattr(main, "csleep", Mock())
    monkeypatch.setattr(main, "wait_for_recovery", lambda action, **kwargs: action())
    solver.recog.reset_after_external_control.side_effect = [
        ConnectionError("恢复后的画面仍未复位"),
        None,
    ]
    with pytest.raises(ConnectionError):
        main._resume_device_dispatch(solver, ConnectionError())
    patrol(case)
    assert_retained(case)
    solver.enter_room.assert_not_called()

    main._resume_device_dispatch(solver, ConnectionError())
    assert not solver._idle_observation_pending
    patrol(case)
    if new_failure:
        solver.enter_room.assert_not_called()
        assert_retained(case)
    else:
        solver.enter_room.assert_called_once_with(ROOM)
        assert solver.op_data.room_observations[ROOM] == 2
        assert not getattr(case.restore, "execution_failure", None)
        assert solver.find_next_task() is case.restore
    case.scheduler.io.assert_not_called()


def test_independent_work_dispatches_while_shared_insertion_stays_blocked(
    paused_restoration,
):
    case, solver = paused_restoration, paused_restoration.solver
    independent = SchedulerTask(START, task_type=TaskTypes.DEPOT)
    solver.tasks.append(independent)
    solver.仓库扫描 = Mock()
    assert solver.find_next_task() is independent
    solver.task = independent
    solver.infra_main()
    solver.仓库扫描.assert_called_once_with()
    assert independent not in solver.tasks
    assert_retained(case)
    solver._idle_sleep(60)
    patrol(case)
    assert solver.find_next_task() is case.restore
    assert id(case.order) in blocked_run_order_ids(solver.tasks, solver.op_data)


def test_confirmed_partial_roster_keeps_existing_failure_recovery_rules(
    paused_restoration,
):
    case, solver = paused_restoration, paused_restoration.solver
    data = solver.op_data
    original = ["图耶", "黑键", "鸿雪"]
    data.plan[ROOM] = [
        Room("图耶", "", ["但书", "伺夜"]),
        Room("黑键", "", []),
        Room("鸿雪", "", []),
    ]
    data.global_plan["default_plan"].plan[ROOM] = copy.deepcopy(data.plan[ROOM])
    for index, name in enumerate(original[1:], 1):
        data.add(
            Operator(
                name,
                ROOM,
                index=index,
                current_room=ROOM,
                current_index=index,
                mood=18,
                operator_type="high",
                time_stamp=START - timedelta(hours=1),
            )
        )
    case.restore.plan = {ROOM: original.copy()}
    case.restore.run_order_original_roster = copy.deepcopy(case.restore.plan)
    solver._retain_failed_task(case.restore, "原班恢复失败", [ROOM])
    solver._idle_sleep(60)
    solver.read_screen.side_effect = ["图耶", "黑键", "", "", ""]
    patrol(case)
    assert data.room_observations[ROOM] == 1
    assert data.operators["图耶"].current_room == ROOM
    assert data.operators["但书"].current_room == ""
    assert data.operators["鸿雪"].current_room == ROOM
    assert data.operators["鸿雪"].current_index == 2
    assert not getattr(case.restore, "execution_failure", None)
    assert solver.find_next_task() is case.restore
    assert case.restore.time == ORIGINAL_TIME
    assert case.restore.plan == {ROOM: original}


def test_saved_restoration_gets_one_observation_when_worker_starts(
    paused_restoration, monkeypatch
):
    case, solver = paused_restoration, paused_restoration.solver
    main = case.scheduler.main
    saved = pickle.loads(
        pickle.dumps(
            {
                "tasks": solver.tasks,
                "operators": solver.op_data.operators,
                "dorm": [],
                "room_observations": solver.op_data.room_observations,
                "party_time": None,
                "daily_visit_friend": START.date(),
                "daily_report": START.date(),
                "daily_skland": START.date(),
                "daily_mail": START.date(),
                "task_count": 0,
            }
        )
    )
    solver.tasks = []
    monkeypatch.setattr(main, "initialize", Mock(return_value=solver))
    monkeypatch.setattr(main, "datetime", case.scheduler.clock)
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", Mock(return_value=None))
    monkeypatch.setattr(main, "refresh_resource_at_boundary", Mock())
    monkeypatch.setattr(main, "_apply_version_update_resting_threshold", Mock())
    monkeypatch.setattr(
        solver.op_data, "validate_backup_plans", Mock(return_value={"success": True})
    )
    from arknights_mower.utils import crash_recovery

    monkeypatch.setattr(crash_recovery, "checkpoint_start", Mock())
    visited = []
    restored_tasks = []

    def inspect_and_stop():
        restored_tasks.append(
            next(task for task in solver.tasks if task.run_order_restore_pending)
        )
        solver.agent_get_mood(return_plan=True)
        solver._resume_failed_tasks()
        visited.append(solver.op_data.room_observations[ROOM])
        raise case.scheduler.module.MowerExit

    solver.run = Mock(side_effect=inspect_and_stop)
    main.simulate(saved)
    assert visited == [2]
    restore = restored_tasks[0]
    assert any(task is restore for task in solver.tasks)
    assert not getattr(restore, "execution_failure", None)
    assert restore.time == ORIGINAL_TIME
    assert restore.plan == {ROOM: ["图耶"]}
    assert solver.find_next_task(scope=TaskScope.PENDING) is restore
    solver._retain_failed_task(restore, "原班恢复再次失败", [ROOM])
    read_count = solver.read_screen.call_count
    for _ in range(4):
        solver.agent_get_mood(return_plan=True)
        solver._resume_failed_tasks()
    assert restore.execution_failure
    assert solver.read_screen.call_count == read_count
    case.scheduler.io.assert_not_called()
