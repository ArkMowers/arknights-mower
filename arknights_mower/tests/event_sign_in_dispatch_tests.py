import sqlite3
import sys
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call

import pytest

from arknights_mower import utils

with pytest.MonkeyPatch.context() as import_patch:
    if "arknights_mower.utils.skland" not in sys.modules:
        import_patch.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
        import_patch.setattr(
            utils, "skland", sys.modules["arknights_mower.utils.skland"], raising=False
        )

    from arknights_mower import __main__ as main
    from arknights_mower.solvers import base_schedule, record
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask  # noqa: E402


@pytest.fixture
def dispatch(monkeypatch):
    now = SimpleNamespace(value=datetime(2026, 10, 25, 12))
    monkeypatch.setattr(base_schedule, "get_server_time", lambda: now.value)
    monkeypatch.setattr(main, "get_server_time", lambda: now.value)
    monkeypatch.setattr(config, "conf", Conf(event_sign_in_enable=True))
    scheduler = object.__new__(BaseSchedulerSolver)
    scheduler.device = Mock()
    scheduler.recog = Mock()
    scheduler.daily_event_sign_in = date(2026, 10, 24)
    scheduler.daily_event_sign_in_attempt = None
    runner = Mock()
    runner.run.return_value = True
    factory = Mock(return_value=runner)
    monkeypatch.setitem(
        sys.modules,
        "arknights_mower.solvers.event_sign_in",
        SimpleNamespace(EventSignInSolver=factory),
    )
    saved = Mock()
    monkeypatch.setattr(base_schedule, "save_current_state", saved)
    return scheduler, runner, factory, saved, now


def test_old_config_keeps_event_sign_in_disabled():
    conf = Conf(check_mail_enable=True)
    assert conf.event_sign_in_enable is False
    assert "event_sign_in_enable" not in conf.model_dump(exclude_unset=True)


@pytest.mark.parametrize("enabled", [False, True])
def test_event_sign_in_choice_survives_config_update_and_reload(enabled):
    conf = Conf().updated({"event_sign_in_enable": enabled})
    restored = Conf.model_validate_json(conf.model_dump_json(exclude_unset=True))
    assert restored.event_sign_in_enable is enabled
    assert (
        restored.updated({"check_mail_enable": False}).event_sign_in_enable is enabled
    )


def test_success_is_recorded_once_for_its_starting_game_day(dispatch):
    scheduler, runner, factory, saved, now = dispatch
    now.value = datetime(2026, 10, 25, 23, 59, 59)

    def cross_refresh():
        now.value += timedelta(seconds=2)
        return True

    runner.run.side_effect = cross_refresh
    assert scheduler.event_sign_in_plan_solver() is True
    assert scheduler.daily_event_sign_in == date(2026, 10, 25)
    assert scheduler.daily_event_sign_in_attempt == date(2026, 10, 25)
    factory.assert_called_once_with(scheduler.device, scheduler.recog)
    saved.assert_called_once_with()
    now.value = datetime(2026, 10, 25, 22)
    assert scheduler.event_sign_in_plan_solver() is False
    runner.run.assert_called_once_with()


def test_failed_attempt_remains_due_for_later_normal_dispatch(dispatch):
    scheduler, runner, _, saved, now = dispatch
    runner.run.return_value = False
    original_date = scheduler.daily_event_sign_in
    assert scheduler.event_sign_in_plan_solver() is False
    for hour in (13, 18, 23):
        now.value = datetime(2026, 10, 25, hour)
        assert scheduler.event_sign_in_plan_solver() is False
    assert runner.run.call_count == 4
    assert saved.call_count == 4
    assert scheduler.daily_event_sign_in == original_date
    assert scheduler.daily_event_sign_in_attempt == date(2026, 10, 25)

    now.value = datetime(2026, 10, 26, 5)
    runner.run.return_value = True
    assert scheduler.event_sign_in_plan_solver() is True
    assert runner.run.call_count == 5
    assert scheduler.daily_event_sign_in == date(2026, 10, 26)


def test_successful_game_day_is_skipped_without_an_attempt_record(dispatch):
    scheduler, runner, factory, saved, now = dispatch
    scheduler.daily_event_sign_in = now.value.date()
    scheduler.daily_event_sign_in_attempt = None

    assert scheduler.event_sign_in_plan_solver() is False

    runner.run.assert_not_called()
    factory.assert_not_called()
    saved.assert_not_called()


def test_reenabling_releases_failed_attempt_without_a_timer(dispatch):
    scheduler, runner, _, saved, _ = dispatch
    runner.run.return_value = False
    scheduler.event_sign_in_plan_solver()
    config.conf.event_sign_in_enable = False
    scheduler.event_sign_in_plan_solver()
    assert scheduler.daily_event_sign_in_attempt is None
    assert saved.call_count == 2
    config.conf.event_sign_in_enable = True
    runner.run.return_value = True
    assert scheduler.event_sign_in_plan_solver() is True
    assert runner.run.call_count == 2


def test_disabled_task_does_not_touch_device_or_mark_completion(dispatch):
    scheduler, runner, factory, saved, _ = dispatch
    config.conf.event_sign_in_enable = False
    assert scheduler.event_sign_in_plan_solver() is False
    factory.assert_not_called()
    runner.run.assert_not_called()
    saved.assert_not_called()
    assert scheduler.daily_event_sign_in == date(2026, 10, 24)


@pytest.mark.parametrize(
    "error",
    [MowerExit, base_schedule.DeviceRecoveryError, base_schedule.SharedADBError],
)
def test_stop_or_device_recovery_does_not_mark_an_attempt_or_completion(
    dispatch, error
):
    scheduler, runner, _, saved, _ = dispatch
    runner.run.side_effect = error
    with pytest.raises(error):
        scheduler.event_sign_in_plan_solver()
    assert scheduler.daily_event_sign_in_attempt is None
    assert scheduler.daily_event_sign_in == date(2026, 10, 24)
    saved.assert_not_called()


def main_runtime(monkeypatch, scheduler):
    runtime = MagicMock()
    runtime.backup_group_task_issued = set()
    runtime.initialize_operators.return_value = None
    runtime.op_data.validate_backup_plans.return_value = {"success": True}
    runtime.op_data.mood_calculation_enabled = False
    runtime.op_data.mood_model = None
    runtime.op_data.operators = {}
    runtime.op_data.backup_plans = []
    runtime.op_data.all_dorms.return_value = []
    runtime.op_data.facility_states = {}
    runtime.op_data.room_observations = {}
    runtime.op_data.recall_recovery_rates = {}
    runtime.op_data.group_shift_state = {}
    runtime.op_data.group_recovery_full_members = {}
    runtime.op_data.group_recovery_return_time = {}
    runtime.op_data.urgent_recovery_supporters = {}
    runtime.op_data.idle_dorm_search_exhausted = False
    runtime.op_data.idle_dorm_search_stopped_at = None
    runtime.op_data.party_time = None
    runtime.waiting_group_shifts = []
    runtime._initial_mood_refresh_rooms = set()
    runtime._state_restore_complete = True
    runtime.defer_backup_plan_until_mood_read = False
    runtime.emergency_state = None
    runtime.tasks = []
    runtime.task_count = 0
    runtime.daily_visit_friend = runtime.daily_report = date.min
    runtime.daily_skland = runtime.daily_mail = date.min
    runtime.daily_visit_friend_attempt = None
    runtime.maa_copilot_progress = {}
    runtime.maa_daily_completed = {}
    runtime.daily_event_sign_in = scheduler.daily_event_sign_in
    runtime.daily_event_sign_in_attempt = scheduler.daily_event_sign_in_attempt
    runtime.find_next_task.return_value = None
    runtime.has_maa_tasks.return_value = False
    runtime.mail_plan_solver.return_value = True
    runtime.event_sign_in_plan_solver = (
        BaseSchedulerSolver.event_sign_in_plan_solver.__get__(runtime)
    )
    monkeypatch.setattr(main, "initialize", Mock(return_value=runtime))
    monkeypatch.setattr(main, "base_scheduler", runtime)
    monkeypatch.setattr(main, "refresh_resource_at_boundary", Mock())
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(
        "arknights_mower.solvers.trust_rotation.run_trust_rotation", Mock()
    )
    monkeypatch.setattr("arknights_mower.utils.crash_recovery.checkpoint_start", Mock())
    config.conf.maa_depot_enable = False
    config.conf.stage_plan_enable = False
    config.conf.recruit_enable = True
    return runtime


@pytest.mark.parametrize("mail_enabled", [False, True])
@pytest.mark.parametrize("completed", [False, True])
def test_main_dispatches_event_after_mail_and_continues_other_work(
    monkeypatch, dispatch, mail_enabled, completed
):
    scheduler, runner, _, _, _ = dispatch
    runtime = main_runtime(monkeypatch, scheduler)
    config.conf.check_mail_enable = mail_enabled
    runner.run.return_value = completed
    actions = Mock()
    actions.attach_mock(runtime.mail_plan_solver, "mail")
    actions.attach_mock(runner.run, "event")
    actions.attach_mock(runtime.recruit_plan_solver, "recruit")

    def schedule():
        runtime.tasks = [SchedulerTask(time=datetime.now() + timedelta(minutes=20))]

    runtime.run.side_effect = schedule
    runtime.rest_until_next_task.side_effect = [None, MowerExit]
    main.simulate(None)
    assert actions.mock_calls == (
        ([call.mail()] if mail_enabled else [])
        + [call.event(), call.recruit()]
        + ([] if completed else [call.event()])
        + [call.recruit()]
    )
    assert runtime.daily_event_sign_in == (
        date(2026, 10, 25) if completed else date(2026, 10, 24)
    )
    assert runtime.daily_event_sign_in_attempt == date(2026, 10, 25)


@pytest.mark.parametrize("legacy", [False, True])
def test_event_daily_state_round_trips_and_old_snapshots_remain_due(
    monkeypatch, dispatch, tmp_path, legacy
):
    scheduler, _, _, _, _ = dispatch
    runtime = main_runtime(monkeypatch, scheduler)
    runtime.daily_event_sign_in_attempt = date(2026, 10, 25)
    database = tmp_path / "event-state.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE saved_state (time TEXT, state BLOB)")
    monkeypatch.setattr(record, "_conn", lambda: sqlite3.connect(database))
    assert record.save_current_state()
    saved = record.load_state(strict=True)
    assert saved["daily_event_sign_in"] == date(2026, 10, 24)
    assert saved["daily_event_sign_in_attempt"] == date(2026, 10, 25)
    if legacy:
        saved.pop("daily_event_sign_in")
        saved.pop("daily_event_sign_in_attempt")
    runtime.daily_event_sign_in = date.min
    runtime.daily_event_sign_in_attempt = None

    class ReachedScheduling(BaseException):
        pass

    monkeypatch.setattr(
        main, "refresh_resource_at_boundary", Mock(side_effect=ReachedScheduling)
    )
    with pytest.raises(ReachedScheduling):
        main.simulate(saved)
    assert runtime.daily_event_sign_in == date(2026, 10, 24)
    assert runtime.daily_event_sign_in_attempt == (
        None if legacy else date(2026, 10, 25)
    )


@pytest.mark.parametrize("completed", [False, True])
def test_restored_daily_result_only_skips_a_successful_game_day(
    monkeypatch, dispatch, tmp_path, completed
):
    scheduler, runner, _, _, now = dispatch
    runtime = main_runtime(monkeypatch, scheduler)
    runtime.daily_event_sign_in = (
        now.value.date() if completed else now.value.date() - timedelta(days=1)
    )
    runtime.daily_event_sign_in_attempt = now.value.date()
    runtime.tasks = [SchedulerTask(time=datetime.now() + timedelta(minutes=20))]
    database = tmp_path / "restored-event-state.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE saved_state (time TEXT, state BLOB)")
    monkeypatch.setattr(record, "_conn", lambda: sqlite3.connect(database))
    assert record.save_current_state()
    saved = record.load_state(strict=True)
    runtime.daily_event_sign_in = date.min
    runtime.daily_event_sign_in_attempt = None
    runtime.rest_until_next_task.side_effect = MowerExit

    main.simulate(saved)

    assert runner.run.call_count == (0 if completed else 1)
    assert runtime.daily_event_sign_in == now.value.date()
    assert runtime.daily_event_sign_in_attempt == now.value.date()
    runtime.recruit_plan_solver.assert_called_once_with()


def test_next_normal_dispatch_recovers_without_repeating_a_success(
    monkeypatch, dispatch
):
    scheduler, runner, _, _, now = dispatch
    runtime = main_runtime(monkeypatch, scheduler)
    runner.run.side_effect = [False, True]
    runtime.has_maa_tasks.return_value = True
    actions = Mock()
    actions.attach_mock(runner.run, "event")
    actions.attach_mock(runtime.recruit_plan_solver, "recruit")
    actions.attach_mock(runtime.maa_plan_solver, "maa")

    def schedule():
        runtime.tasks = [SchedulerTask(time=datetime.now() + timedelta(minutes=20))]

    runtime.run.side_effect = schedule
    runtime.rest_until_next_task.side_effect = [None, None, MowerExit]

    main.simulate(None)

    assert actions.mock_calls == [
        call.event(),
        call.recruit(),
        call.maa(),
        call.event(),
        call.recruit(),
        call.maa(),
        call.recruit(),
        call.maa(),
    ]
    assert runtime.daily_event_sign_in == now.value.date()
    assert runtime.daily_event_sign_in_attempt == now.value.date()
