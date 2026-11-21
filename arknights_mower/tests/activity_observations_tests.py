"""执行路径只记录展示观测，不改变原任务、时钟和执行结果。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import local_operation_scheduler_log_tests as local_checks
from arknights_mower.tests import maa_daily_completion_tests as daily_checks

local = local_checks.local
result = local_checks.result
maa_scheduler = daily_checks.scheduler
callback = daily_checks.callback


@pytest.mark.parametrize("entry", ["automatic", "manual"])
def test_mission_observation_is_a_round_check_for_both_real_entries(
    local, monkeypatch, entry
):
    from arknights_mower.solvers import base_schedule, manual_tasks, mission
    from arknights_mower.utils.scheduler_task import TaskTypes

    solver = local.solver
    seen = []

    def run():
        seen.append(solver.display_observations["mission"]["outcome"])
        if entry == "automatic":
            assert solver.display_observations["stage-plan"]["outcome"] != "running"

    def factory(*args):
        return SimpleNamespace(run=run)

    monkeypatch.setattr(base_schedule, "MissionSolver", factory)
    monkeypatch.setattr(mission, "MissionSolver", factory)
    if entry == "automatic":
        local.plan("1-7")
        solver.mower_plan_solver()
    else:
        manual_tasks._run_single(solver, TaskTypes.MISSION)
    assert seen == ["running"]
    assert solver.display_observations["mission"]["outcome"] == "checked"


@pytest.mark.parametrize(
    "cloud_ok,scan_ok", [(True, True), (False, True), (True, False)]
)
def test_depot_result_is_observed_after_actual_scan(
    maa_scheduler, monkeypatch, cloud_ok, scan_ok
):
    from arknights_mower.solvers import base_schedule

    solver = maa_scheduler
    solver.device = solver.recog = MagicMock()
    cloud = MagicMock()
    cloud.start.return_value = cloud_ok
    scan = MagicMock()
    scan.run.return_value = scan_ok
    monkeypatch.setattr(base_schedule, "cultivateDepotSolver", lambda: cloud)
    monkeypatch.setattr(base_schedule, "DepotSolver", lambda *args: scan)
    solver._auto_schedule_mastery_after_scan = MagicMock()
    assert solver.仓库扫描() is (cloud_ok and scan_ok)
    observation = solver.display_observations["depot"]
    assert observation["outcome"] == (
        "completed" if cloud_ok and scan_ok else "incomplete"
    )
    if not cloud_ok:
        scan.run.assert_not_called()


def test_display_observations_survive_real_save_restore_without_running(
    maa_scheduler, monkeypatch
):
    from arknights_mower import __main__ as mower
    from arknights_mower.solvers import base_schedule, record

    observed_at = datetime.now().astimezone()
    maa_scheduler.display_observations = {
        "stage-plan": {"at": observed_at, "runner": "maa", "outcome": "running"},
        "annihilation": {
            "at": observed_at,
            "runner": "mower",
            "outcome": "reward_full",
        },
    }
    maa_scheduler.last_execution = {"maa": None, "recruit": None, "todo": None}
    maa_scheduler.last_clue = maa_scheduler.drone_time = maa_scheduler.reload_time = (
        None
    )
    record.save_current_state()
    saved = record.load_state()
    assert saved["display_observations"] == maa_scheduler.display_observations
    maa_scheduler.display_observations = {}
    maa_scheduler.initialize_operators = MagicMock(return_value=None)
    maa_scheduler.run = MagicMock(side_effect=base_schedule.MowerExit)
    maa_scheduler._request_run_order_restoration_observations = MagicMock()
    monkeypatch.setattr(mower, "initialize", lambda *a, **kw: maa_scheduler)
    monkeypatch.setattr(mower.NewsChecker, "get_effective_maintenance", lambda: None)
    monkeypatch.setattr(mower, "refresh_resource_at_boundary", MagicMock())
    mower.simulate(saved)
    assert maa_scheduler.display_observations["stage-plan"]["outcome"] == "stopped"
    assert (
        maa_scheduler.display_observations["annihilation"]["outcome"] == "reward_full"
    )
    assert maa_scheduler.display_observations["annihilation"]["at"] == observed_at
    assert maa_scheduler.last_execution == {"maa": None, "recruit": None, "todo": None}
    assert (
        maa_scheduler.last_clue,
        maa_scheduler.drone_time,
        maa_scheduler.reload_time,
    ) == (None, None, None)


def test_locked_annihilation_notification_is_not_repeated_after_resume(
    maa_scheduler, monkeypatch
):
    from arknights_mower import __main__ as mower
    from arknights_mower.solvers import base_schedule, record

    mail = MagicMock()
    monkeypatch.setattr(base_schedule, "send_message", mail)
    game_time = datetime(2026, 11, 2, 9)
    monkeypatch.setattr(base_schedule, "get_server_time", lambda: game_time)
    maa_scheduler.annihilation_lock_mail_day = None
    maa_scheduler.report_annihilation_agency_locked()
    saved = record.load_state(strict=True)
    assert saved["annihilation_lock_mail_day"] == game_time.date()

    maa_scheduler.annihilation_lock_mail_day = None
    maa_scheduler.initialize_operators = MagicMock(return_value=None)
    maa_scheduler.run = MagicMock(side_effect=base_schedule.MowerExit)
    maa_scheduler._request_run_order_restoration_observations = MagicMock()
    monkeypatch.setattr(mower, "initialize", lambda *a, **kw: maa_scheduler)
    monkeypatch.setattr(mower.NewsChecker, "get_effective_maintenance", lambda: None)
    monkeypatch.setattr(mower, "refresh_resource_at_boundary", MagicMock())
    mower.simulate(saved)

    maa_scheduler.report_annihilation_agency_locked()
    mail.assert_called_once()


def test_maa_observations_require_accepted_fight_task_and_end_on_release(
    maa_scheduler, monkeypatch
):
    from arknights_mower.solvers import base_schedule

    monkeypatch.setattr(base_schedule, "get_server_weekday", lambda: 0)
    monkeypatch.setattr(
        maa_scheduler, "maybe_switch_expired_activity_plan", lambda: None
    )
    maa_scheduler.append_maa_task("Fight")
    assert not getattr(maa_scheduler, "display_observations", {})
    for taskid, chain in ((999, "Fight"), (1, "Award"), (True, "Fight")):
        callback(maa_scheduler, 10001, taskid=taskid, taskchain=chain)
    assert not getattr(maa_scheduler, "display_observations", {})

    callback(maa_scheduler, 10001, taskid=1, taskchain="Fight")
    assert maa_scheduler.display_observations["stage-plan"]["outcome"] == "running"
    callback(maa_scheduler, 10002, taskid=1, taskchain="Fight")
    observation = maa_scheduler.display_observations["stage-plan"]
    assert observation["outcome"] == "checked"
    assert observation["runner"] == "maa"
    assert observation["stage"] == ""
    assert "executed_runs" not in observation

    maa_scheduler.append_maa_task("Fight")
    callback(maa_scheduler, 10001, taskid=2, taskchain="Fight")
    maa_scheduler.release_maa()
    assert maa_scheduler.display_observations["stage-plan"]["outcome"] == "stopped"
    callback(maa_scheduler, 10002, taskid=2, taskchain="Fight")
    assert maa_scheduler.display_observations["stage-plan"]["outcome"] == "stopped"


def test_local_stage_observes_actual_running_and_confirmed_runs(local):
    solver = local.solver
    local.plan("1-7")
    before_tasks = list(solver.tasks)
    seen = []

    def finish(**kwargs):
        seen.append(dict(solver.display_observations["stage-plan"]))
        return result(executed_runs=6, sanity_drain=True, simulated_current_ap=0)

    local.operation.return_value.run.side_effect = finish
    outcome = solver.run_local_operation_stage(
        "1-7", datetime.now() + timedelta(hours=2), 36, 6, None, "fallback"
    )

    assert seen[0]["outcome"] == "running"
    assert seen[0]["stage"] == "1-7"
    observation = solver.display_observations["stage-plan"]
    assert observation["outcome"] == "checked"
    assert observation["runner"] == "mower"
    assert observation["executed_runs"] == 6
    assert observation["reason"] == "sanity_drain"
    assert observation["at"].utcoffset() is not None
    assert outcome == {
        "simulated_current_ap": 0,
        "executed_any": True,
        "should_break": True,
    }
    assert solver.tasks == before_tasks
    assert solver.last_execution == {"maa": None}


def test_local_threshold_check_without_battle_has_its_own_observation(local):
    local.plan("1-7", ap=5, threshold=100)
    local.solver.mower_plan_solver()
    assert local.solver.display_observations["stage-plan"]["outcome"] == "checked"
    assert local.solver.display_observations["stage-plan"]["reason"] == "plan_checked"
    local.operation.assert_not_called()


@pytest.mark.parametrize(
    "flag,outcome",
    [
        ("annihilation_reward_full", "reward_full"),
        ("annihilation_agency_locked", "agency_locked"),
    ],
)
def test_local_annihilation_records_only_confirmed_result(local, flag, outcome):
    local.plan("Annihilation")
    local.solver.report_annihilation_agency_locked = MagicMock()
    local.operation.return_value.run.return_value = result(**{flag: True})
    local.operation.return_value.run.side_effect = None
    returned = local.solver.run_local_operation_stage(
        "Annihilation",
        datetime.now() + timedelta(hours=2),
        None,
        None,
        None,
        "fallback",
    )
    assert returned["annihilation_skipped"] is True
    assert local.solver.display_observations["annihilation"]["outcome"] == outcome
    assert local.solver.display_observations["stage-plan"]["executed_runs"] == 0


def test_completed_annihilation_replaces_previous_proxy_lock(local):
    local.plan("Annihilation")
    solver = local.solver
    solver.report_annihilation_agency_locked = MagicMock()
    local.operation.return_value.run.side_effect = [
        result(annihilation_agency_locked=True),
        result(),
        result(executed_runs=1),
    ]
    deadline = datetime.now() + timedelta(hours=2)

    solver.run_local_operation_stage(
        "Annihilation", deadline, None, None, None, "fallback"
    )
    assert solver.display_observations["annihilation"]["outcome"] == "agency_locked"

    solver.run_local_operation_stage(
        "Annihilation", deadline, None, None, None, "fallback"
    )
    assert solver.display_observations["annihilation"]["outcome"] == "agency_locked"

    solver.run_local_operation_stage(
        "Annihilation", deadline, None, None, None, "fallback"
    )
    observation = solver.display_observations["annihilation"]
    assert observation["outcome"] == "completed"
    assert observation["executed_runs"] == 1


def test_maa_award_checks_mission_even_without_optional_rewards(maa_scheduler):
    from arknights_mower.solvers import base_schedule

    for key in ("recruit", "orundum", "mining", "specialaccess", "signinevent"):
        setattr(base_schedule.config.conf, f"maa_{key}", False)
    maa_scheduler.append_maa_task("Award")
    callback(maa_scheduler, 10001, taskid=1, taskchain="Award")
    assert maa_scheduler.display_observations["mission"]["outcome"] == "running"
    callback(maa_scheduler, 10002, taskid=1, taskchain="Award")
    assert maa_scheduler.display_observations["mission"]["outcome"] == "checked"
    assert "stage" not in maa_scheduler.display_observations["mission"]


def test_registered_maa_callback_cannot_apply_old_run_to_reused_task_id(
    maa_scheduler, monkeypatch
):
    import json
    import sys
    from threading import Event

    from arknights_mower.solvers import base_schedule, record
    from arknights_mower.utils import maa_backup

    callbacks = []
    inventory_active = Event()
    monkeypatch.setattr(base_schedule, "battle_inventory_active", inventory_active)
    monkeypatch.setattr(record, "battle_inventory_active", inventory_active)
    monkeypatch.setattr(base_schedule.config, "stop_maa", Event())

    def engine(asst, path, callback):
        callbacks.append(callback)
        instance = MagicMock()
        instance.connect.return_value = True
        return instance

    monkeypatch.setenv("MOWER_ANDROID", "1")
    monkeypatch.setitem(sys.modules, "mower_android.maa", SimpleNamespace(Asst=object))
    monkeypatch.setattr(maa_backup, "VerifiedAsst", engine)
    monkeypatch.setattr(maa_scheduler, "update_maa_navigation", lambda *args: None)
    maa_scheduler.initialize_maa()
    maa_scheduler.MAA.append_task.return_value = 1
    maa_scheduler.append_maa_task("Award")
    first = callbacks[0]
    maa_scheduler.release_maa()
    maa_scheduler.initialize_maa()
    maa_scheduler.MAA.append_task.return_value = 1
    maa_scheduler.append_maa_task("Award")
    current = callbacks[1]
    payload = json.dumps({"taskchain": "Award", "taskid": 1}).encode()
    current(10001, payload, None)
    first(10000, payload, None)
    assert maa_scheduler.display_observations["mission"]["outcome"] == "running"
    current(10002, payload, None)
    assert maa_scheduler.display_observations["mission"]["outcome"] == "checked"
    maa_scheduler.release_maa()


@pytest.mark.parametrize("cancelled", [True, False])
def test_local_observation_preserves_cancellation_and_error(local, cancelled):
    from arknights_mower.utils.csleep import MowerExit

    local.plan("1-7")
    failure = MowerExit() if cancelled else ValueError("original")
    local.operation.return_value.run.side_effect = failure
    with pytest.raises(type(failure)) as raised:
        local.solver.run_local_operation_stage(
            "1-7", datetime.now() + timedelta(hours=2), None, None, None, "fallback"
        )
    assert raised.value is failure
    assert local.solver.display_observations["stage-plan"]["outcome"] == (
        "stopped" if cancelled else "error"
    )
    assert local.solver.display_observations["stage-plan"]["reason"] == (
        "cancelled" if cancelled else "exception"
    )


def test_maa_subtask_failure_is_not_hidden_by_chain_end(maa_scheduler):
    maa_scheduler.append_maa_task("Award")
    callback(maa_scheduler, 10001, taskid=1, taskchain="Award")
    callback(maa_scheduler, 20000, taskid=1, taskchain="Award")
    callback(maa_scheduler, 10002, taskid=1, taskchain="Award")
    assert maa_scheduler.display_observations["mission"]["outcome"] == "incomplete"


def test_snapshot_is_immutable_when_later_observation_replaces_it(maa_scheduler):
    from arknights_mower.solvers import record
    from arknights_mower.utils.activity_observations import observe_activity

    observe_activity(maa_scheduler, "depot", "mower", "running")
    snapshot = record.current_state()
    observe_activity(maa_scheduler, "depot", "mower", "completed")
    assert snapshot["display_observations"]["depot"]["outcome"] == "running"
    assert maa_scheduler.display_observations["depot"]["outcome"] == "completed"


def test_observations_only_restore_snapshot_and_write_the_four_known_keys(
    maa_scheduler,
):
    from arknights_mower.utils.activity_observations import (
        observe_activity,
        restore_observations,
        snapshot_observations,
    )

    at = datetime.now().astimezone()
    raw = {
        **{
            f"unknown-{index}": {"at": at, "outcome": "running"}
            for index in range(1500)
        },
        "stage-plan": {"at": at, "runner": "maa", "outcome": "running"},
        "depot": {"at": at, "runner": "mower", "outcome": "completed"},
    }
    maa_scheduler.display_observations = raw
    assert set(snapshot_observations(maa_scheduler)) == {"stage-plan", "depot"}
    restore_observations(maa_scheduler, raw)
    assert set(maa_scheduler.display_observations) == {"stage-plan", "depot"}
    assert maa_scheduler.display_observations["stage-plan"]["outcome"] == "stopped"
    before = dict(maa_scheduler.display_observations)
    observe_activity(maa_scheduler, "unknown-new", "mower", "running")
    assert maa_scheduler.display_observations == before


def test_maa_tracking_bound_does_not_reject_accepted_real_tasks(maa_scheduler):
    from arknights_mower.utils.activity_observations import remember_maa_activity

    for taskid in range(1, 1025):
        remember_maa_activity(maa_scheduler, taskid, "Fight", "stage-plan", stage="1-7")
    maa_scheduler.MAA.append_task.side_effect = None
    maa_scheduler.MAA.append_task.return_value = 1025
    maa_scheduler.append_maa_task("Award")
    assert maa_scheduler.MAA.append_task.call_args.args[0] == "Award"
    assert len(maa_scheduler._maa_activity_tasks) == 1024
    callback(maa_scheduler, 10001, taskid=1025, taskchain="Award")
    assert "mission" not in getattr(maa_scheduler, "display_observations", {})
    callback(maa_scheduler, 10001, taskid=1, taskchain="Fight")
    assert maa_scheduler.display_observations["stage-plan"]["outcome"] == "running"


@pytest.mark.parametrize("value", [None, [], "broken"])
def test_malformed_legacy_observation_container_does_not_change_execution(
    maa_scheduler, value
):
    from arknights_mower.utils.activity_observations import (
        observe_activity,
        snapshot_observations,
    )

    maa_scheduler.display_observations = value
    assert snapshot_observations(maa_scheduler) == {}
    observe_activity(maa_scheduler, "depot", "mower", "completed")
    assert set(maa_scheduler.display_observations) == {"depot"}


@pytest.mark.parametrize("raw", [None, b"null", b"[]", b"broken"])
def test_non_mapping_callback_payload_does_not_add_observation_failure(
    maa_scheduler, raw
):
    maa_scheduler.on_maa_callback(10001, raw, None)
    assert getattr(maa_scheduler, "display_observations", {}) == {}
