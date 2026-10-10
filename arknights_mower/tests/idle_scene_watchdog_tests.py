"""Scheduler idle intervals do not count toward active scene timeouts."""

import sys
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower import __main__ as main  # noqa: E402
from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.utils import config, recognize, scheduler_task  # noqa: E402
from arknights_mower.utils import solver as solver_module  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.device import recovery  # noqa: E402
from arknights_mower.utils.news_checker import MaintenanceInfo  # noqa: E402
from arknights_mower.utils.recognize import Recognizer, Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


@pytest.fixture
def idle_scheduler(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 10, 8, 10, 55, 38, 643000)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(recognize, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf(run_order_delay=3))
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config, "wake_scheduler", Event())
    monkeypatch.setattr(config, "maintenance_recheck", Event())
    monkeypatch.setattr(base, "refresh_resource_at_boundary", MagicMock())
    solver = object.__new__(base.BaseSchedulerSolver)
    solver._simulator_closed_for_idle = False
    solver._idle_observation_pending = False
    solver.device = MagicMock()
    solver.device.check_current_focus.return_value = False
    solver.recog = Recognizer(solver.device)
    solver.recog.scene = solver.recog.last_scene = Scene.INFRA_MAIN
    solver.recog.last_scene_time = Clock.now()
    solver.recog.loading_time = 6
    solver.recog._screencap = b"cached capture"
    solver.recog._img = np.ones((1080, 1920, 3), dtype=np.uint8)
    solver.recog._gray = np.ones((1080, 1920), dtype=np.uint8)
    solver.recog._matcher = object()
    frame = np.full((1080, 1920, 3), 2, dtype=np.uint8)
    gray = np.full((1080, 1920), 2, dtype=np.uint8)
    solver.device.screencap.return_value = b"fresh capture", frame, gray
    template_ids = {}

    def load_template(name, gray=False):
        value = template_ids.setdefault(name, len(template_ids) + 1)
        return np.full((8, 8) if gray else (8, 8, 3), value, dtype=np.uint8)

    class FrameMatcher:
        def __init__(self, observed):
            assert observed is gray

        def match(self, template, **kwargs):
            if int(template[0, 0]) == template_ids.get("infra_overview"):
                return ((0, 0), (8, 8))
            return None

    # Stub visual scores; get_scene, find, lazy capture and frame caches stay real.
    monkeypatch.setattr(recognize, "loadres", load_template)
    monkeypatch.setattr(recognize, "cmatch", lambda *args, **kwargs: False)
    monkeypatch.setattr(recognize, "Matcher", FrameMatcher)
    monkeypatch.setattr(
        recognize.cv2,
        "matchTemplate",
        lambda *args, **kwargs: np.zeros((1, 1), dtype=np.float32),
    )

    def advance(seconds):
        Clock.current += timedelta(seconds=seconds)

    for module in (base, main, solver_module, recovery):
        monkeypatch.setattr(module, "csleep", advance)
    return SimpleNamespace(solver=solver, clock=Clock)


@pytest.fixture
def production_idle_scheduler(idle_scheduler, monkeypatch):
    solver, clock = idle_scheduler.solver, idle_scheduler.clock
    solver.tasks = [
        SchedulerTask(
            clock.now() + timedelta(seconds=600), task_type=TaskTypes.SHIFT_ON
        ),
        SchedulerTask(
            clock.now() + timedelta(hours=1), task_type=TaskTypes.SKILL_UPGRADE
        ),
    ]
    solver.op_data = SimpleNamespace(
        config=SimpleNamespace(free_room=False),
        plan={},
        operators={},
        dorm=[],
        correct_dorm=MagicMock(),
        rescue_mode=False,
    )
    solver._party_time = solver.free_clue = solver.credit_fight = None
    solver.task_count = 0
    for method in (
        "_schedule_maintenance_backup_check",
        "_sync_run_order_tasks",
        "_resume_waiting_group_shifts",
        "_fill_empty_dorms",
        "_discard_product_switches",
        "backup_plan_solver",
        "queue_product_switches",
    ):
        setattr(solver, method, MagicMock())
    solver._product_switching_enabled = MagicMock(return_value=False)
    solver.infra_main = MagicMock(return_value=True)
    monkeypatch.setattr(base, "send_message", MagicMock())
    monkeypatch.setattr(base, "task_template", MagicMock())
    monkeypatch.setattr(base, "save_log", MagicMock())
    monkeypatch.setattr(
        scheduler_task.NewsChecker, "get_update_time", lambda: (None, None)
    )
    control = SimpleNamespace(shutdown_requested=False, recover=MagicMock())
    control.recover.return_value.unwrap.return_value = solver.device
    monkeypatch.setattr(main, "device_control", control)
    idle_scheduler.control = control
    return idle_scheduler


def assert_active_watchdog(solver, clock):
    observed_at = clock.now()
    clock.current = observed_at + timedelta(seconds=270)
    solver.recog.update()
    assert solver.scene() == Scene.INFRA_MAIN
    solver.device.exit.assert_not_called()
    clock.current += timedelta(seconds=1)
    solver.sleep(0)
    assert solver.scene() == Scene.UNDEFINED
    solver.device.exit.assert_called_once()


@pytest.mark.parametrize("resume", ["deadline", "early_wake", "maintenance"])
def test_idle_resume_restarts_observation_and_preserves_active_watchdog(
    idle_scheduler, monkeypatch, resume
):
    scheduler = idle_scheduler
    solver, clock = scheduler.solver, scheduler.clock
    started = clock.now()

    def sleep(seconds):
        clock.current += timedelta(seconds=seconds)
        if resume != "deadline" and clock.now() >= started + timedelta(seconds=275):
            config.wake_scheduler.set()

    monkeypatch.setattr(base, "csleep", sleep)
    solver._idle_sleep(298.417708, allow_wakeup=resume != "maintenance")

    assert not solver.sleeping
    assert (clock.now() - started).total_seconds() == (
        275 if resume == "early_wake" else 298.417708
    )
    assert config.wake_scheduler.is_set() == (resume == "maintenance")
    assert solver.recog.scene == Scene.UNDEFINED
    assert solver.recog.last_scene is None
    assert solver.recog.last_scene_time == clock.now()
    assert solver.recog.loading_time == 0
    for name in ("_screencap", "_img", "_gray", "_matcher"):
        assert getattr(solver.recog, name) is None

    assert solver.scene() == Scene.INFRA_MAIN
    solver.device.screencap.assert_called_once_with()
    assert solver.recog._img is solver.device.screencap.return_value[1]
    assert solver.recog._gray is solver.device.screencap.return_value[2]
    assert_active_watchdog(solver, clock)


def test_cancelled_idle_preserves_stop_and_does_not_resume_recognition(
    idle_scheduler, monkeypatch
):
    solver = idle_scheduler.solver
    cached_frame = solver.recog._img

    def stop(_):
        config.stop_mower.set()
        raise MowerExit

    monkeypatch.setattr(base, "csleep", stop)
    with pytest.raises(MowerExit):
        solver._idle_sleep(298.417708)

    assert not solver.sleeping
    assert solver.recog._img is cached_frame
    assert solver.recog.last_scene == Scene.INFRA_MAIN
    solver.device.assert_not_called()
    solver.device.exit.assert_not_called()
    solver.device.reconnect.assert_not_called()
    solver.device.screencap.assert_not_called()


@pytest.mark.parametrize("entry", ["rest", "maintenance"])
@pytest.mark.parametrize("failure", ["start", "reconnect"])
def test_failed_idle_resume_restarts_observation_after_main_recovery(
    production_idle_scheduler, monkeypatch, entry, failure
):
    scheduler = production_idle_scheduler
    solver, clock = scheduler.solver, scheduler.clock
    started = clock.now()
    old_frame = solver.recog._img
    config.conf.close_simulator_when_idle = True
    restart = MagicMock(side_effect=[True, failure != "start"])
    monkeypatch.setattr(base, "restart_simulator", restart)
    if failure == "reconnect":
        solver.device.reconnect.side_effect = ConnectionError("offline")

    with pytest.raises(ConnectionError):
        if entry == "rest":
            solver.rest_until_next_task()
        else:
            config.wake_scheduler.set()
            info = MaintenanceInfo(
                start=started,
                end=started + timedelta(seconds=600),
                update_type="hot",
                title="maintenance test",
                url="",
                announcement_id="offline-idle-recovery",
            )
            main._handle_maintenance(info, solver, now=started)

    assert clock.now() == started + timedelta(seconds=600)
    assert not solver.sleeping
    assert solver.recog._img is old_frame
    assert solver.recog.last_scene == Scene.INFRA_MAIN
    assert solver.recog.last_scene_time == started
    assert solver.recog.loading_time == 6
    solver.device.screencap.assert_not_called()
    solver.device.exit.assert_not_called()
    if failure == "start":
        solver.device.reconnect.assert_not_called()
    else:
        solver.device.reconnect.assert_called_once_with()

    assert (
        main._resume_device_dispatch(solver, ConnectionError("offline"))
        is solver.device
    )
    assert solver.recog.scene == Scene.UNDEFINED
    solver.run()
    solver.device.exit.assert_not_called()
    solver.device.screencap.assert_called_once_with()
    assert solver.recog._img is solver.device.screencap.return_value[1]
    assert solver.recog.last_scene_time == clock.now()
    assert solver.recog.loading_time == 0
    assert restart.call_count == 2
    assert_active_watchdog(solver, clock)


def test_active_device_recovery_preserves_scene_watchdog(production_idle_scheduler):
    solver, clock = production_idle_scheduler.solver, production_idle_scheduler.clock
    observed_at = solver.recog.last_scene_time
    clock.current += timedelta(seconds=271)

    main._resume_device_dispatch(solver, ConnectionError("active operation failed"))

    assert solver.recog.last_scene == Scene.INFRA_MAIN
    assert solver.recog.last_scene_time == observed_at
    assert solver.scene() == Scene.UNDEFINED
    solver.device.screencap.assert_called_once_with()
    solver.device.exit.assert_called_once()


@pytest.mark.parametrize("cancel_recovery", [False, True])
def test_idle_observation_resumes_only_after_successful_device_recovery(
    production_idle_scheduler, monkeypatch, cancel_recovery
):
    scheduler = production_idle_scheduler
    solver, clock = scheduler.solver, scheduler.clock
    old_frame = solver.recog._img
    config.conf.close_simulator_when_idle = True
    monkeypatch.setattr(base, "restart_simulator", MagicMock(return_value=True))
    solver.device.reconnect.side_effect = ConnectionError("offline")
    reset = MagicMock(wraps=solver.recog.reset_after_external_control)
    monkeypatch.setattr(solver.recog, "reset_after_external_control", reset)
    with pytest.raises(ConnectionError):
        solver.rest_until_next_task()

    def recover():
        if scheduler.control.recover.call_count == 1:
            reset.assert_not_called()
            assert solver.recog._img is old_frame
            if cancel_recovery:
                config.stop_mower.set()
                raise MowerExit
            raise ConnectionError("recovery still offline")
        return solver.device

    scheduler.control.recover.return_value.unwrap.side_effect = recover
    if cancel_recovery:
        with pytest.raises(MowerExit):
            main._resume_device_dispatch(solver, ConnectionError("offline"))
        reset.assert_not_called()
        assert solver.recog._img is old_frame
        assert not solver.sleeping
        solver.device.screencap.assert_not_called()
        return

    main._resume_device_dispatch(solver, ConnectionError("offline"))
    reset.assert_called_once_with()
    assert solver.scene() == Scene.INFRA_MAIN
    observed_at = clock.now()
    main._resume_device_dispatch(solver, ConnectionError("active operation failed"))
    reset.assert_called_once_with()
    assert solver.scene() == Scene.INFRA_MAIN
    assert solver.recog.last_scene_time == observed_at
    solver.device.exit.assert_not_called()
