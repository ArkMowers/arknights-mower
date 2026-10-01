"""HTTP task insertion must not dispatch the task selected before an idle wait."""

import sys
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower import __main__ as main  # noqa: E402
from arknights_mower.solvers import base_schedule, furniture  # noqa: E402
from arknights_mower.utils import config, scheduler_task  # noqa: E402
from arknights_mower.utils.furniture_task import (  # noqa: E402
    FurnitureNavigationError,
    FurnitureSafetyError,
)
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402
from arknights_mower.views import task as task_view  # noqa: E402

REAL_FURNITURE_RUN = furniture.FurnitureDismantler.run


@pytest.fixture
def scheduler(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 9, 9, 10)

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz is None else cls.current.replace(tzinfo=tz)

    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    shift = SchedulerTask(
        Clock.now() + timedelta(minutes=4),
        {"room_1_1": ["休息中的干员"]},
        TaskTypes.SHIFT_ON,
    )
    # A pending mastery recheck keeps handle_error() from inserting an idle job.
    recheck = SchedulerTask(
        Clock.now() + timedelta(hours=1), task_type=TaskTypes.SKILL_UPGRADE
    )
    solver.tasks = [shift, recheck]
    solver.op_data = SimpleNamespace(
        config=SimpleNamespace(free_room=False),
        plan={},
        operators={},
        dorm=[],
        correct_dorm=MagicMock(),
        rescue_needed=MagicMock(return_value=False),
        rescue_mode=False,
    )
    solver.recog = MagicMock()
    solver._simulator_closed_for_idle = False
    solver.party_time = solver.free_clue = solver.credit_fight = None
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver.find = MagicMock(return_value=True)
    solver.check_current_focus = MagicMock()
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.queue_product_switches = MagicMock()
    solver._sync_run_order_tasks = MagicMock()
    solver._switch_products_before_arrangement = MagicMock()
    solver._prepare_shift_cycle = MagicMock()
    solver.agent_get_mood = MagicMock(return_value=True)
    solver.agent_arrange = MagicMock(side_effect=lambda *args: solver.skip())
    solver.craft_material = MagicMock(side_effect=solver.skip)
    wake = Event()
    monkeypatch.setattr(config, "wake_scheduler", wake)
    monkeypatch.setattr(config, "maintenance_recheck", Event())
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config.conf, "enable_mastery", False)
    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    monkeypatch.setattr(furniture, "datetime", Clock)
    monkeypatch.setattr(
        scheduler_task.NewsChecker, "get_update_time", lambda: (None, None)
    )
    monkeypatch.setattr(base_schedule, "save_log", MagicMock())
    monkeypatch.setattr(base_schedule, "refresh_resource_at_boundary", lambda: None)
    monkeypatch.setattr(main, "base_scheduler", solver)
    monkeypatch.setattr(
        task_view, "mower_thread", SimpleNamespace(is_alive=lambda: True)
    )
    monkeypatch.setattr(task_view, "get_localzone", lambda: timezone.utc)
    app = Flask(__name__)
    app.register_blueprint(task_view.task_bp)
    state = SimpleNamespace(
        solver=solver, shift=shift, clock=Clock, wake=wake, on_sleep=None
    )

    def sleep(seconds):
        Clock.current += timedelta(seconds=seconds)
        if state.on_sleep:
            action, state.on_sleep = state.on_sleep, None
            action()

    def add_workshop(delay=0, task_type="加工材料", plan=None):
        at = Clock.now() + timedelta(seconds=delay)
        response = app.test_client().post(
            "/task",
            json={
                "task": {
                    "time": at.replace(tzinfo=timezone.utc).isoformat(
                        timespec="milliseconds"
                    ),
                    "plan": plan or {},
                    "task_type": task_type,
                    "meta_data": "蜜莓",
                }
            },
        )
        assert response.get_data(as_text=True) == "添加任务成功！"

    state.add_workshop = add_workshop
    from arknights_mower.solvers.furniture import FurnitureDismantler

    state.dismantle = MagicMock()
    monkeypatch.setattr(FurnitureDismantler, "run", state.dismantle)
    monkeypatch.setattr(base_schedule, "csleep", sleep)
    return state


@pytest.mark.parametrize("during_wait", [False, True])
def test_invalid_run_order_is_removed_before_scheduling(scheduler, during_wait):
    solver = scheduler.solver
    solver.op_data.run_order_rooms = {"room_1_1": {}} if during_wait else {}
    solver.op_data.refresh_run_order_rooms = MagicMock()
    solver._sync_run_order_tasks = (
        base_schedule.BaseSchedulerSolver._sync_run_order_tasks.__get__(solver)
    )
    stale = SchedulerTask(
        scheduler.clock.now() + timedelta(minutes=2 if during_wait else -1),
        {"room_1_1": ["Current"]},
        TaskTypes.RUN_ORDER,
        meta_data="room_1_1",
    )
    solver.tasks.insert(0, stale)
    if during_wait:
        scheduler.on_sleep = solver.op_data.run_order_rooms.clear

    solver.run()

    assert all(task is not stale for task in solver.tasks)
    solver.agent_arrange.assert_called_once_with(scheduler.shift.plan, False)
    assert scheduler.clock.now() == scheduler.shift.time


def test_http_workshop_wake_reselects_task_before_dispatch(scheduler):
    scheduler.on_sleep = scheduler.add_workshop
    scheduler.solver.run()
    scheduler.solver.agent_arrange.assert_not_called()
    scheduler.solver.craft_material.assert_called_once_with()
    assert scheduler.clock.now() == scheduler.shift.time - timedelta(seconds=239)
    assert any(task is scheduler.shift for task in scheduler.solver.tasks)
    assert all(task.type != TaskTypes.WORKSHOP for task in scheduler.solver.tasks)
    assert not scheduler.wake.is_set()
    assert not scheduler.solver.sleeping
    scheduler.solver.run()
    scheduler.solver.agent_arrange.assert_called_once_with(scheduler.shift.plan, False)
    assert scheduler.clock.now() == scheduler.shift.time
    assert all(task is not scheduler.shift for task in scheduler.solver.tasks)


def primary_with_vacancies(scheduler, monkeypatch):
    from arknights_mower.utils.operators import Operator, Operators
    from arknights_mower.utils.plan import Plan, PlanConfig, Room

    solver = scheduler.solver
    scheduler.clock.current = datetime.now()
    rooms = {
        "meeting": [Room("银灰", "", ["红"])],
        "dormitory_1": [
            Room(name, "", []) for name in ["杜林", "闪灵", "Free", "Free", "Free"]
        ],
    }
    solver.op_data = Operators(
        {
            "default_plan": Plan(rooms, PlanConfig("", "", "")),
            "backup_plans": [],
        }
    )
    assert solver.op_data.init_and_validate() is None
    solver.op_data.add(Operator("陈", "", mood=5))
    for room, row in rooms.items():
        for index, slot in enumerate(row):
            if slot.agent != "Free":
                op = solver.op_data.operators[slot.agent]
                op.current_room, op.current_index = room, index
    for op in solver.op_data.operators.values():
        op.time_stamp = scheduler.clock.now()
        op.mood = 0 if op.name == "银灰" else 5 if op.name == "陈" else 24
    solver.tasks = [
        SchedulerTask(
            scheduler.clock.now() + timedelta(hours=1),
            task_type=TaskTypes.SKILL_UPGRADE,
        )
    ]
    solver.last_train_mood_read = scheduler.clock.now()
    solver._suppress_train_correction = lambda plan: None
    return solver


@pytest.mark.parametrize("deferred_fill", [False, True])
def test_run_dispatches_fresh_primary_shift_before_ordinary_dorm_fill(
    scheduler, monkeypatch, deferred_fill
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    if deferred_fill:
        solver.tasks.append(
            SchedulerTask(
                scheduler.clock.now(),
                {"dormitory_1": ["Current", "Current", "陈", "Current", "Current"]},
                TaskTypes.FILL_DORM,
            )
        )

    solver.run()

    solver.agent_arrange.assert_called_once()
    plan, read_time = solver.agent_arrange.call_args.args
    assert read_time is True
    assert plan["meeting"] == ["红"]
    assert "银灰" in plan["dormitory_1"]
    assert not any(task.type == TaskTypes.FILL_DORM for task in solver.tasks)


def test_due_fill_preflight_preserves_original_task_without_new_primary(
    scheduler, monkeypatch
):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    solver.op_data.operators["银灰"].mood = 24
    fill = SchedulerTask(
        scheduler.clock.now(),
        {"dormitory_1": ["Current", "Current", "陈", "Current", "Current"]},
        TaskTypes.FILL_DORM,
    )
    fill.simple_dorm_fill = True
    solver.tasks.append(fill)
    preflight = MagicMock(wraps=solver._plan_primary_recovery)
    solver._plan_primary_recovery = preflight
    before = fill.time

    assert not solver._fill_empty_dorms()

    preflight.assert_called_once_with()
    assert any(task is fill for task in solver.tasks)
    assert fill.time == before
    assert fill.simple_dorm_fill


@pytest.mark.parametrize("protected", ["retry", "restore", "product", "partial"])
def test_due_fill_preserves_in_progress_arrangement(scheduler, monkeypatch, protected):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    fill = SchedulerTask(
        scheduler.clock.now(),
        {"dormitory_1": ["Current"] * 4 + ["陈"]},
        TaskTypes.FILL_DORM,
    )
    if protected == "retry":
        fill.arrangement_retry_room = "dormitory_1"
    elif protected == "restore":
        fill.dorm_recovery_restore = ["dormitory_1"]
    elif protected == "product":
        fill.product_shift_locked = True
    else:
        fill.dorm_fill_plan = fill.plan | {"dormitory_2": ["Current"] * 4 + ["红"]}
    solver.tasks.append(fill)
    solver._plan_primary_recovery = MagicMock()

    assert not solver._fill_empty_dorms()

    solver._plan_primary_recovery.assert_not_called()
    assert any(task is fill for task in solver.tasks)


def test_due_fill_preflight_restores_task_when_planning_raises(scheduler, monkeypatch):
    solver = primary_with_vacancies(scheduler, monkeypatch)
    fill = SchedulerTask(
        scheduler.clock.now(),
        {"dormitory_1": ["Current"] * 4 + ["陈"]},
        TaskTypes.FILL_DORM,
    )
    solver.tasks.append(fill)
    solver._plan_primary_recovery = MagicMock(
        side_effect=RuntimeError("planning failed")
    )

    with pytest.raises(RuntimeError, match="planning failed"):
        solver._fill_empty_dorms()

    assert any(task is fill for task in solver.tasks)


def test_plan_solver_runs_primary_phase_once_before_both_idle_stages(
    scheduler, monkeypatch
):
    solver = scheduler.solver
    solver.tasks = []
    order = []
    solver._plan_primary_recovery = MagicMock(
        side_effect=lambda: order.append("primary") or True
    )
    solver._fill_empty_dorms = MagicMock(
        side_effect=lambda **kwargs: order.append("fill")
    )
    monkeypatch.setattr(
        base_schedule, "try_add_release_dorm", lambda *args: order.append("replace")
    )
    monkeypatch.setattr(
        base_schedule, "try_workshop_tasks", lambda *args: order.append("workshop")
    )

    solver.plan_solver()

    assert order == ["primary", "fill", "replace", "workshop"]
    solver._plan_primary_recovery.assert_called_once_with()


def test_maintenance_sleep_ignores_regular_scheduler_wakeup(scheduler):
    started_at = scheduler.clock.now()
    scheduler.wake.set()

    scheduler.solver._idle_sleep(2, allow_wakeup=False)

    assert scheduler.clock.now() == started_at + timedelta(seconds=2)
    assert scheduler.wake.is_set()
    assert not scheduler.solver.sleeping


def test_maintenance_wake_returns_to_main_before_dispatch(scheduler):
    def start_maintenance():
        config.maintenance_recheck.set()
        scheduler.wake.set()

    scheduler.on_sleep = start_maintenance
    scheduler.solver.run()

    scheduler.solver.agent_arrange.assert_not_called()
    assert scheduler.shift in scheduler.solver.tasks
    assert scheduler.clock.now() < scheduler.shift.time
    assert config.maintenance_recheck.is_set()
    assert not scheduler.solver.sleeping


@pytest.mark.parametrize("wake_only", [False, True])
def test_original_shift_waits_until_due_without_new_work(scheduler, wake_only):
    if wake_only:
        scheduler.on_sleep = scheduler.wake.set
    scheduler.solver.run()
    scheduler.solver.agent_arrange.assert_called_once_with(scheduler.shift.plan, False)
    scheduler.solver.craft_material.assert_not_called()
    assert scheduler.clock.now() == scheduler.shift.time


def test_new_future_workshop_waits_for_its_own_deadline(scheduler):
    scheduler.on_sleep = lambda: scheduler.add_workshop(delay=9)
    scheduler.solver.run()
    scheduler.solver.agent_arrange.assert_not_called()
    scheduler.solver.craft_material.assert_called_once_with()
    assert scheduler.clock.now() == scheduler.shift.time - timedelta(seconds=230)


def test_workshop_wake_respects_pending_mastery_handoff(scheduler, monkeypatch):
    from arknights_mower.solvers import mastery

    monkeypatch.setattr(config.conf, "enable_mastery", True)
    swap = SchedulerTask(
        scheduler.clock.now() + timedelta(minutes=2), task_type=TaskTypes.SWAP_SUPPORT
    )
    scheduler.solver.tasks.append(swap)
    dispatch = MagicMock(side_effect=lambda solver: solver.skip())
    monkeypatch.setattr(mastery, "run_swap_support", dispatch)
    scheduler.on_sleep = scheduler.add_workshop
    scheduler.solver.run()
    dispatch.assert_called_once_with(scheduler.solver)
    scheduler.solver.craft_material.assert_not_called()
    scheduler.solver.agent_arrange.assert_not_called()
    assert scheduler.clock.now() == swap.time
    workshop = next(
        task for task in scheduler.solver.tasks if task.type == TaskTypes.WORKSHOP
    )
    assert workshop.time > swap.time


@pytest.mark.parametrize("change", ["remove", "postpone"])
def test_changed_task_during_wait_is_not_dispatched(scheduler, change):
    def update_queue():
        if change == "remove":
            scheduler.solver.tasks[:] = [
                task for task in scheduler.solver.tasks if task is not scheduler.shift
            ]
        else:
            scheduler.shift.time += timedelta(hours=1)
        scheduler.wake.set()

    scheduler.on_sleep = update_queue
    scheduler.solver.run()
    scheduler.solver.agent_arrange.assert_not_called()
    scheduler.solver.craft_material.assert_not_called()


@pytest.mark.parametrize("change", ["future", "remove"])
def test_dispatch_rechecks_deadline_and_membership(scheduler, change):
    solver = scheduler.solver
    solver.task = scheduler.shift
    if change == "remove":
        scheduler.shift.time = scheduler.clock.now()
        solver.tasks[:] = [task for task in solver.tasks if task is not scheduler.shift]
    assert solver.infra_main() is True
    solver.agent_arrange.assert_not_called()
    assert solver.task is None


@pytest.mark.parametrize("delay", [0, 9])
def test_furniture_wake_waits_for_its_own_deadline_and_ignores_staff(scheduler, delay):
    scheduler.on_sleep = lambda: scheduler.add_workshop(
        delay=delay, task_type="分解所有重复家具", plan={"factory": ["九色鹿"]}
    )
    scheduler.solver.run()
    scheduler.dismantle.assert_called_once_with()
    scheduler.solver.agent_arrange.assert_not_called()
    scheduler.solver.craft_material.assert_not_called()
    assert scheduler.clock.now() == scheduler.shift.time - timedelta(
        seconds=239 - delay
    )
    assert all(t.type != TaskTypes.FURNITURE for t in scheduler.solver.tasks)
    assert not scheduler.wake.is_set()


def test_furniture_http_contract_discards_operator_metadata(scheduler):
    scheduler.add_workshop(
        delay=9, task_type="分解所有重复家具", plan={"factory": ["九色鹿"]}
    )
    task = next(t for t in scheduler.solver.tasks if t.type == TaskTypes.FURNITURE)
    assert task.plan == {}
    assert task.meta_data == ""
    assert not hasattr(task, "workshop_generation")
    assert scheduler.wake.is_set()


def test_furniture_dispatch_ignores_legacy_staff_plan(scheduler):
    task = SchedulerTask(
        task_type=TaskTypes.FURNITURE, task_plan={"factory": ["九色鹿"]}
    )
    scheduler.solver.task = task
    scheduler.solver.tasks = [task]
    scheduler.solver.infra_main()
    scheduler.dismantle.assert_called_once_with()
    scheduler.solver.agent_arrange.assert_not_called()
    assert scheduler.solver.tasks == []


@pytest.mark.parametrize(
    "error",
    [
        FurnitureSafetyError("无法确认保留完整套装"),
        ValueError("保留开关识别置信度不足"),
        RuntimeError("OCR 执行失败"),
    ],
)
def test_failed_furniture_task_is_removed_before_next_dispatch(
    scheduler, monkeypatch, error
):
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    scheduler.dismantle.side_effect = error
    scheduler.on_sleep = lambda: scheduler.add_workshop(task_type="分解所有重复家具")
    scheduler.solver.run()
    assert all(t.type != TaskTypes.FURNITURE for t in scheduler.solver.tasks)
    assert any(t is scheduler.shift for t in scheduler.solver.tasks)
    scheduler.solver.run()
    scheduler.dismantle.assert_called_once_with()
    scheduler.solver.agent_arrange.assert_called_once_with(scheduler.shift.plan, False)
    assert scheduler.clock.now() == scheduler.shift.time


def test_pre_submission_navigation_failure_remains_retryable(scheduler, monkeypatch):
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    scheduler.dismantle.side_effect = [FurnitureNavigationError("未进入家具页面"), None]
    scheduler.on_sleep = lambda: scheduler.add_workshop(task_type="分解所有重复家具")
    scheduler.solver.run()
    assert any(t.type == TaskTypes.FURNITURE for t in scheduler.solver.tasks)
    scheduler.solver.run()
    assert scheduler.dismantle.call_count == 2
    assert all(t.type != TaskTypes.FURNITURE for t in scheduler.solver.tasks)


@pytest.mark.parametrize(
    "error", [base_schedule.MowerExit(), ConnectionError("导航断线")]
)
def test_furniture_preserves_stop_and_pre_submission_connection_signals(
    scheduler, monkeypatch, error
):
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    task = SchedulerTask(scheduler.clock.now(), task_type=TaskTypes.FURNITURE)
    scheduler.solver.tasks.insert(0, task)
    scheduler.solver.task = task
    scheduler.dismantle.side_effect = error
    with pytest.raises(type(error)):
        scheduler.solver.infra_main()
    assert any(t is task for t in scheduler.solver.tasks)


@pytest.mark.parametrize("other_type", [TaskTypes.SWAP_SUPPORT, TaskTypes.RUN_ORDER])
def test_furniture_budget_defers_scan_before_fixed_deadline(
    scheduler, monkeypatch, other_type
):
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    now = scheduler.clock.now()
    task = SchedulerTask(now, task_type=TaskTypes.FURNITURE)
    fixed = SchedulerTask(now + timedelta(minutes=3), task_type=other_type)
    tasks = [task, fixed]
    scheduler_task.scheduling(tasks, time_now=now)
    assert fixed.time == now + timedelta(minutes=3)
    assert task.time > fixed.time
    assert scheduler_task._ordinary_task_minutes(task, 0.75) == 31


@pytest.mark.parametrize("insert_swap", [False, True])
def test_long_furniture_scan_yields_before_shift_or_new_swap(
    scheduler, monkeypatch, insert_swap
):
    from arknights_mower.solvers import mastery

    monkeypatch.setattr(config.conf, "enable_mastery", True)
    start = scheduler.clock.now()
    solver = scheduler.solver
    task = SchedulerTask(start, task_type=TaskTypes.FURNITURE)
    solver.tasks.insert(0, task)
    solver.task = task
    swap = SchedulerTask(start + timedelta(minutes=3), task_type=TaskTypes.SWAP_SUPPORT)
    dispatch_swap = MagicMock(side_effect=lambda solver: solver.skip())
    monkeypatch.setattr(mastery, "run_swap_support", dispatch_swap)
    runner = furniture.FurnitureDismantler(solver)
    runner.open_formula = MagicMock()
    solver.factory_scene = MagicMock(return_value=furniture.Scene.FACTORY_FORMULA)
    solver.back_to_infrastructure = MagicMock()
    solver.sleep = MagicMock()
    page = 0

    def swipe(*args, **kwargs):
        nonlocal page
        page += 1
        scheduler.clock.current += timedelta(seconds=10)
        if insert_swap and page == 1:
            solver.tasks.append(swap)

    solver.swipe_noinertia = MagicMock(side_effect=swipe)
    monkeypatch.setattr(
        furniture, "monotonic", lambda: (scheduler.clock.now() - start).total_seconds()
    )
    monkeypatch.setattr(furniture, "furniture_cards", lambda img: [((0.4, 0.2), 1)])
    monkeypatch.setattr(furniture, "list_fingerprint", lambda img: page)
    monkeypatch.setattr(furniture, "same_list", lambda a, b: a == b)
    scheduler.dismantle.side_effect = lambda: REAL_FURNITURE_RUN(runner)
    solver.infra_main()
    next_task = swap if insert_swap else scheduler.shift
    assert scheduler.clock.now() == next_task.time - timedelta(minutes=1)
    assert page == (12 if insert_swap else 18)
    assert all(t is not task for t in solver.tasks)
    assert any(t is scheduler.shift for t in solver.tasks)
    solver.back_to_infrastructure.assert_called_once_with()
    solver.agent_arrange.assert_not_called()
    solver.error = False
    solver.handle_error(force=True)
    assert any(t is scheduler.shift for t in solver.tasks)
    if insert_swap:
        solver.run()
        dispatch_swap.assert_called_once_with(solver)
        assert scheduler.clock.now() == swap.time
    solver.run()
    solver.agent_arrange.assert_called_once_with(scheduler.shift.plan, False)
    assert scheduler.clock.now() == scheduler.shift.time
