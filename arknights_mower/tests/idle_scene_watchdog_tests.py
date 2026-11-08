"""Scheduler idle intervals do not count toward active scene timeouts."""

import os
import sys
from datetime import datetime, timedelta
from threading import Event, RLock
from types import SimpleNamespace
from unittest.mock import MagicMock, call
from weakref import ref

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower import __main__ as main  # noqa: E402
from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.solvers import record  # noqa: E402
from arknights_mower.tests.device_session_tests import (  # noqa: E402
    ADB,
    Clock,
    Preflight,
    Simulator,
)
from arknights_mower.utils import config, recognize, scheduler_task  # noqa: E402
from arknights_mower.utils import solver as solver_module  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.device import recovery  # noqa: E402
from arknights_mower.utils.device.application import DeviceControl  # noqa: E402
from arknights_mower.utils.device.device import Device  # noqa: E402
from arknights_mower.utils.device.session import DeviceSession  # noqa: E402
from arknights_mower.utils.news_checker import MaintenanceInfo  # noqa: E402
from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.recognize import Recognizer, Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402
from arknights_mower.utils.screenshot import ScreenshotStore  # noqa: E402


@pytest.fixture
def idle_scheduler(monkeypatch, offline_maintenance):
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
    monkeypatch.setattr(record, "workshop_inventory_changed", Event())
    monkeypatch.setattr(base, "refresh_resource_at_boundary", MagicMock())
    release_ocr = MagicMock()
    monkeypatch.setattr(base.rapidocr, "release_idle_local_model", release_ocr)
    solver = object.__new__(base.BaseSchedulerSolver)
    solver._simulator_closed_for_idle = False
    solver._idle_observation_pending = False
    solver.device = MagicMock()
    solver.device.session_control = None
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
    return SimpleNamespace(solver=solver, clock=Clock, release_ocr=release_ocr)


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
        mood_calculation_enabled=False,
        config=SimpleNamespace(free_room=False),
        plan={},
        operators={},
        dorm=[],
        correct_dorm=MagicMock(),
        rescue_mode=False,
    )
    solver.op_data.arrangement_group_transitions = (
        Operators.arrangement_group_transitions.__get__(solver.op_data)
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


@pytest.mark.parametrize("stop_succeeds", [True, False])
def test_idle_lifecycle_uses_replacement_device_for_next_focus_check(
    production_idle_scheduler, monkeypatch, stop_succeeds
):
    solver, clock = production_idle_scheduler.solver, production_idle_scheduler.clock
    config.conf.close_simulator_when_idle = True
    config.conf.device.preset_id = "windows.mumu12"
    config.conf.device.instance_id = "1"
    config.conf.device.last_serial = "USB-A"
    adb, simulator = ADB(), Simulator()
    adb.rows, adb.boot = [("USB-A", "device")], "1"
    simulator.state, simulator.serial = "running", "USB-A"
    handles, clients, events = [], [], []

    def open_verified(configuration, result):
        device = object.__new__(Device)
        device.owner_pid = os.getpid()
        device._resource_lock = RLock()
        device._interrupted = Event()
        device._close_error = None
        device._profile = configuration.device
        device.device_id = result.serial
        device.control = SimpleNamespace(
            input_alive=lambda: True,
            close=lambda: events.append("close_input"),
        )
        device.client = SimpleNamespace(
            run=MagicMock(
                return_value=f"mCurrentFocus=Window{{id u0 {device.game_package}/Main}}".encode()
            ),
            close=lambda: events.append("close_client"),
        )
        handles.append(device)
        clients.append(device.client)
        events.append("open")
        return device

    def stop(profile, timeout):
        assert events[-2:] == ["close_input", "close_client"]
        events.append("stop")
        if stop_succeeds:
            simulator.state = "stopped"
            adb.rows = []
        return stop_succeeds

    def started():
        simulator.state = "running"
        adb.rows = [("USB-A", "device")]

    simulator.stop = stop
    simulator.on_start = started
    control = DeviceControl(
        lambda: config.conf,
        SimpleNamespace(open_verified=open_verified),
        preflight=Preflight(),
        session=DeviceSession(adb, simulator, clock=Clock()),
    )
    monkeypatch.setattr(main, "device_control", control)
    monkeypatch.setattr(
        "arknights_mower.utils.device.application.is_android_runtime", lambda: False
    )
    solver.device = solver.recog.device = control.start().unwrap()
    pending = [(task, task.time) for task in solver.tasks]
    before = config.conf.model_dump()
    try:
        for cycle in range(2):
            solver.tasks[0].time = clock.now() + timedelta(seconds=600)
            expected_time = solver.tasks[0].time
            solver.rest_until_next_task()

            assert solver.device is solver.recog.device is handles[-1]
            assert len(handles) == cycle + 2
            assert handles[-2].client is None
            clients[-2].run.assert_not_called()
            clients[-1].run.assert_called_once_with(
                "dumpsys window | grep mCurrentFocus"
            )
            assert not solver.sleeping
            assert not solver._simulator_closed_for_idle
            assert not solver._idle_observation_pending
            assert solver.recog.last_scene is None
            assert solver.recog._img is None
            assert solver.tasks[0] is pending[0][0]
            assert solver.tasks[0].time == expected_time
            assert solver.tasks[1] is pending[1][0]
            assert solver.tasks[1].time == pending[1][1]
            assert config.conf.model_dump() == before
            clients[-1].run.reset_mock()
    finally:
        control.close().unwrap()


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


def test_long_idle_releases_frame_once_and_keeps_preview_on_wakeup(
    idle_scheduler, monkeypatch, tmp_path
):
    solver, clock = idle_scheduler.solver, idle_scheduler.clock
    started = clock.now()
    frames = ref(solver.recog._img), ref(solver.recog._gray)
    store = ScreenshotStore(tmp_path, lambda: 0, logger=MagicMock())
    try:
        store.submit(b"latest encoded screenshot")
        latest = store.latest()
        waits = []

        def sleep(seconds):
            waits.append(seconds)
            assert solver.sleeping
            assert all(frame() is None for frame in frames)
            assert solver.recog._screencap is None
            assert solver.recog._matcher is None
            assert solver.recog.scene == solver.recog.last_scene == Scene.INFRA_MAIN
            assert solver.recog.last_scene_time == started
            assert solver.recog.loading_time == 6
            assert store.latest() is latest
            solver.device.screencap.assert_not_called()
            clock.current += timedelta(seconds=seconds)
            if len(waits) == 2:
                config.wake_scheduler.set()

        monkeypatch.setattr(base, "csleep", sleep)
        solver._idle_sleep(301)

        assert waits == [1, 1]
        assert not solver.sleeping
        assert not config.wake_scheduler.is_set()
        idle_scheduler.release_ocr.assert_called_once_with()
        assert store.latest() is latest
        assert solver.recog.last_scene_time == started + timedelta(seconds=2)
        assert solver.recog.last_scene is None
        assert solver.recog.loading_time == 0
        solver.device.screencap.assert_not_called()
        assert solver.scene() == Scene.INFRA_MAIN
        solver.device.screencap.assert_called_once_with()
    finally:
        store.close(timeout=0)


def test_idle_at_long_wait_boundary_retains_frame_until_wakeup(
    idle_scheduler, monkeypatch
):
    solver, clock = idle_scheduler.solver, idle_scheduler.clock
    frame = ref(solver.recog._img)

    def sleep(seconds):
        assert frame() is solver.recog._img
        assert frame() is not None
        clock.current += timedelta(seconds=seconds)
        config.wake_scheduler.set()

    monkeypatch.setattr(base, "csleep", sleep)
    solver._idle_sleep(300)

    idle_scheduler.release_ocr.assert_not_called()
    assert frame() is None


@pytest.mark.parametrize("interruption", ["wakeup", "cancel", "stop"])
def test_immediate_idle_interruption_skips_memory_release(
    idle_scheduler, monkeypatch, interruption
):
    solver = idle_scheduler.solver
    release_frame = MagicMock(wraps=solver.recog.release_frame)
    monkeypatch.setattr(solver.recog, "release_frame", release_frame)
    sleep = MagicMock(side_effect=MowerExit)
    monkeypatch.setattr(base, "csleep", sleep)

    if interruption == "wakeup":
        config.wake_scheduler.set()
        solver._idle_sleep(600)
    elif interruption == "cancel":
        solver._idle_sleep(600, allow_wakeup=False, cancelled=lambda: True)
    else:
        config.stop_mower.set()
        with pytest.raises(MowerExit):
            solver._idle_sleep(600)

    idle_scheduler.release_ocr.assert_not_called()
    assert not solver.sleeping
    solver.device.screencap.assert_not_called()
    if interruption == "stop":
        release_frame.assert_not_called()
        sleep.assert_called_once_with(1)
    else:
        # Only the existing successful-resume reset clears the frame.
        release_frame.assert_called_once_with()
        sleep.assert_not_called()


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


@pytest.mark.parametrize("entry", ["task_wait", "round_end"])
@pytest.mark.parametrize("signal_at_deadline", [False, True])
def test_maintenance_recheck_does_not_resume_closed_simulator(
    production_idle_scheduler, monkeypatch, entry, signal_at_deadline
):
    solver, clock = production_idle_scheduler.solver, production_idle_scheduler.clock
    started = clock.now()
    duration = 600 if entry == "round_end" else 2
    cached_frame = ref(solver.recog._img)
    tasks = list(solver.tasks)
    original_times = [task.time for task in tasks]
    config.conf.close_simulator_when_idle = True
    restart = MagicMock(return_value=True)
    monkeypatch.setattr(base, "restart_simulator", restart)

    def sleep(seconds):
        clock.current += timedelta(seconds=seconds)
        if not signal_at_deadline or clock.now() >= started + timedelta(
            seconds=duration
        ):
            config.maintenance_recheck.set()
            config.wake_scheduler.set()

    monkeypatch.setattr(base, "csleep", sleep)
    if entry == "round_end":
        solver.rest_until_next_task()
    else:
        solver.handle_idle_action(600)
        solver._idle_sleep(duration)

    restart.assert_called_once_with(start=False)
    assert solver._simulator_closed_for_idle
    assert solver._idle_observation_pending
    assert not solver.sleeping
    assert config.maintenance_recheck.is_set()
    assert not config.wake_scheduler.is_set()
    if entry == "round_end":
        assert cached_frame() is solver.recog._img is None
    else:
        assert cached_frame() is solver.recog._img is not None
    assert solver.recog.last_scene == Scene.INFRA_MAIN
    assert solver.recog.last_scene_time == started
    assert solver.recog.loading_time == 6
    assert solver.tasks == tasks
    assert [task.time for task in tasks] == original_times
    solver.device.reconnect.assert_not_called()
    solver.device.check_current_focus.assert_not_called()
    solver.device.screencap.assert_not_called()


def test_maintenance_timer_defers_device_start_until_real_entry_time(
    production_idle_scheduler, monkeypatch
):
    solver, clock = production_idle_scheduler.solver, production_idle_scheduler.clock
    started = clock.now()
    monkeypatch.setattr(main, "datetime", clock)
    info = MaintenanceInfo(
        started + timedelta(minutes=1),
        started + timedelta(minutes=61),
        "hot",
        "服务器停机维护公告",
        "",
        "offline-maintenance-wake",
    )
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", lambda: info)
    config.conf.close_simulator_when_idle = True
    restart = MagicMock(return_value=True)
    monkeypatch.setattr(base, "restart_simulator", restart)
    timer_class = MagicMock()
    monkeypatch.setattr(main, "Timer", timer_class)
    tasks = list(solver.tasks)
    times = [task.time for task in tasks]
    cached_frame = ref(solver.recog._img)
    fired = False
    failures, checkpoint = [object()], object()
    monkeypatch.setattr(solver, "_run_order_restoration_failures", lambda: failures)
    monkeypatch.setattr(
        solver, "_emergency_continuation_checkpoint", lambda: checkpoint
    )
    restore = MagicMock()
    emergency = MagicMock()
    monkeypatch.setattr(solver, "_request_run_order_restoration_observations", restore)
    monkeypatch.setattr(
        solver, "_request_emergency_continuation_observation", emergency
    )

    def sleep(seconds):
        nonlocal fired
        clock.current += timedelta(seconds=seconds)
        if not fired and clock.now() >= info.start:
            fired = True
            timer_class.call_args.args[1]()

    monkeypatch.setattr(base, "csleep", sleep)
    try:
        main._arm_maintenance_timer(info, now=started)
        solver.rest_until_next_task()
        assert clock.now() == info.start
        restart.assert_called_once_with(start=False)
        assert solver._simulator_closed_for_idle
        assert cached_frame() is solver.recog._img is None
        assert solver.recog.last_scene == Scene.INFRA_MAIN
        assert solver.recog.last_scene_time == started
        assert solver.recog.loading_time == 6
        solver.device.check_current_focus.assert_not_called()
        solver.device.reconnect.assert_not_called()
        restore.assert_not_called()
        emergency.assert_not_called()

        assert main._handle_maintenance(info, solver, now=clock.now()) is False

        assert clock.now() == started + timedelta(minutes=31)
        assert restart.call_args_list == [
            call(start=False),
            call(stop=False, start=True),
        ]
        assert not solver._simulator_closed_for_idle
        assert not solver._idle_observation_pending
        assert solver.recog._img is None
        assert solver.recog.last_scene_time == clock.now()
        assert solver.recog.loading_time == 0
        assert solver.tasks == tasks
        assert [task.time for task in tasks] == times
        solver.device.reconnect.assert_called_once_with()
        solver.device.screencap.assert_not_called()
        restore.assert_called_once_with(failures)
        emergency.assert_called_once_with(checkpoint)
    finally:
        main._cancel_maintenance_timer()


def test_main_resumes_deferred_idle_after_confirming_entry_is_permitted(
    production_idle_scheduler, monkeypatch
):
    solver, clock = production_idle_scheduler.solver, production_idle_scheduler.clock
    monkeypatch.setattr(main, "datetime", clock)
    info = MaintenanceInfo(
        clock.now() - timedelta(minutes=31),
        clock.now() + timedelta(minutes=29),
        "hot",
        "服务器停机维护公告",
        "",
        "permitted-early-entry",
    )
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", lambda: info)
    monkeypatch.setattr(main, "base_scheduler", None)
    monkeypatch.setattr(main, "initialize", lambda *args, **kwargs: solver)
    monkeypatch.setattr(main, "refresh_resource_at_boundary", MagicMock())
    monkeypatch.setattr(main, "_apply_version_update_resting_threshold", MagicMock())
    monkeypatch.setattr(
        "arknights_mower.utils.crash_recovery.checkpoint_start", MagicMock()
    )
    config.conf.automatic_rescue_enable = False
    config.conf.enable_mastery = False
    config.conf.close_simulator_when_idle = True
    config.maintenance_recheck.set()
    config.wake_scheduler.set()
    solver._simulator_closed_for_idle = True
    solver._idle_observation_pending = True
    solver.emergency_state = None
    solver.tasks[0].time = clock.now() - timedelta(seconds=1)
    solver.initialize_operators = MagicMock(return_value=None)
    solver.op_data.validate_backup_plans = MagicMock(return_value={"success": True})
    restart = MagicMock(return_value=True)
    monkeypatch.setattr(base, "restart_simulator", restart)

    def dispatch():
        assert not solver._simulator_closed_for_idle
        assert not solver._idle_observation_pending
        assert not config.wake_scheduler.is_set()
        assert not config.maintenance_recheck.is_set()
        assert solver.recog._img is None
        raise MowerExit

    solver.run = MagicMock(side_effect=dispatch)
    main.simulate(None)
    solver.run.assert_called_once_with()
    restart.assert_called_once_with(stop=False, start=True)
    solver.device.reconnect.assert_called_once_with()
    solver.device.screencap.assert_not_called()


def test_pending_maintenance_skips_round_end_device_access(
    production_idle_scheduler, monkeypatch
):
    solver = production_idle_scheduler.solver
    solver._simulator_closed_for_idle = True
    config.maintenance_recheck.set()
    refresh = MagicMock()
    monkeypatch.setattr(solver, "_refresh_workshop_inventory", refresh)
    restart = MagicMock()
    monkeypatch.setattr(base, "restart_simulator", restart)
    solver.rest_until_next_task()
    refresh.assert_not_called()
    restart.assert_not_called()
    solver.device.check_current_focus.assert_not_called()


def test_closed_simulator_skips_repeated_idle_actions(idle_scheduler, monkeypatch):
    solver = idle_scheduler.solver
    solver._simulator_closed_for_idle = True
    config.conf.close_simulator_when_idle = False
    config.conf.return_home_when_idle = True
    restart = MagicMock()
    monkeypatch.setattr(base, "restart_simulator", restart)
    solver.handle_idle_action(1800)
    restart.assert_not_called()
    solver.device.return_home.assert_not_called()
    solver.device.exit.assert_not_called()
    assert solver._simulator_closed_for_idle


@pytest.mark.parametrize("entry", ["rest", "maintenance"])
@pytest.mark.parametrize("failure", ["start", "reconnect"])
def test_failed_idle_resume_restarts_observation_after_main_recovery(
    production_idle_scheduler, monkeypatch, entry, failure
):
    scheduler = production_idle_scheduler
    solver, clock = scheduler.solver, scheduler.clock
    started = clock.now()
    old_frame = ref(solver.recog._img)
    config.conf.close_simulator_when_idle = True
    restart = MagicMock(side_effect=[True, failure != "start", True])
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
    assert old_frame() is solver.recog._img is None
    assert solver.recog.scene == Scene.INFRA_MAIN
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
    recovered_closed = solver._simulator_closed_for_idle
    assert solver.recog.scene == Scene.UNDEFINED
    solver.run()
    solver.device.exit.assert_not_called()
    solver.device.screencap.assert_called_once_with()
    assert solver.recog._img is solver.device.screencap.return_value[1]
    assert solver.recog.last_scene_time == clock.now()
    assert solver.recog.loading_time == 0
    assert restart.call_count == 2
    assert_active_watchdog(solver, clock)
    solver.handle_idle_action(600)
    assert restart.call_args_list == [
        call(start=False),
        call(stop=False, start=True),
        call(start=False),
    ]
    assert not recovered_closed
    assert solver._simulator_closed_for_idle


def test_recovered_device_can_close_even_if_observation_reset_fails(
    production_idle_scheduler, monkeypatch
):
    solver = production_idle_scheduler.solver
    config.conf.close_simulator_when_idle = True
    solver._simulator_closed_for_idle = True
    solver._idle_observation_pending = True
    monkeypatch.setattr(
        solver.recog,
        "reset_after_external_control",
        MagicMock(side_effect=RuntimeError("observation reset failed")),
    )
    with pytest.raises(RuntimeError, match="observation reset failed"):
        main._resume_device_dispatch(solver, ConnectionError("offline"))
    recovered_closed = solver._simulator_closed_for_idle
    assert solver._idle_observation_pending
    restart = MagicMock(return_value=True)
    monkeypatch.setattr(base, "restart_simulator", restart)
    solver.handle_idle_action(600)
    restart.assert_called_once_with(start=False)
    assert not recovered_closed
    assert solver._simulator_closed_for_idle


def test_cancelled_device_recovery_preserves_closed_idle_marker(
    production_idle_scheduler, monkeypatch
):
    solver = production_idle_scheduler.solver
    solver._simulator_closed_for_idle = True
    solver._idle_observation_pending = True
    frame = solver.recog._img
    production_idle_scheduler.control.recover.return_value.unwrap.side_effect = (
        MowerExit
    )
    with pytest.raises(MowerExit):
        main._resume_device_dispatch(solver, ConnectionError("offline"))
    assert solver._simulator_closed_for_idle
    assert solver._idle_observation_pending
    assert solver.recog._img is frame
    restart = MagicMock()
    monkeypatch.setattr(base, "restart_simulator", restart)
    solver.handle_idle_action(600)
    restart.assert_not_called()


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
    old_frame = ref(solver.recog._img)
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
            assert old_frame() is solver.recog._img is None
            assert solver.recog.last_scene == Scene.INFRA_MAIN
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
        assert old_frame() is solver.recog._img is None
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
