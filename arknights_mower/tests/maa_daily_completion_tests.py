import json
import sys
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower import __main__ as mower  # noqa: E402
from arknights_mower.solvers import base_schedule, record  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402


@pytest.fixture
def scheduler(monkeypatch, tmp_path):
    instance = object.__new__(base_schedule.BaseSchedulerSolver)
    instance.MAA = MagicMock()
    instance.MAA.append_task.side_effect = range(1, 100)
    instance.stages = []
    instance.credit_fight = None
    instance.maa_callback = None
    instance.maa_daily_completed = {}
    instance.maa_daily_tasks = {}
    instance.daily_visit_friend = date.min
    instance.daily_report = instance.daily_skland = instance.daily_mail = date.min
    instance.task_count = 0
    instance.emergency_state = None
    instance.tasks = []
    instance.op_data = SimpleNamespace(
        mood_calculation_enabled=False,
        backup_plans=[],
        all_dorms=lambda: [],
        operators={},
        party_time=None,
        validate_backup_plans=MagicMock(return_value={"success": True}),
        restore_group_shift_state=MagicMock(),
        restore_dorm_state=MagicMock(),
    )
    instance._state_restore_complete = True
    monkeypatch.setattr(mower, "base_scheduler", instance)
    monkeypatch.setattr(record, "get_path", lambda value: tmp_path / value[5:])
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            maa_recruit=True,
            maa_orundum=True,
            maa_mining=True,
            maa_specialaccess=True,
            maa_signinevent=True,
        ),
    )
    return instance


def callback(scheduler, msg, **details):
    scheduler.on_maa_callback(msg, json.dumps(details).encode(), None)


def append(scheduler, kind, **kwargs):
    scheduler.append_maa_task(kind, **kwargs)
    return scheduler.MAA.append_task.call_args.args[1]


def test_daily_activity_rewards_skip_completed_options_and_keep_new_rewards(scheduler):
    params = append(scheduler, "Award")
    assert all(
        params[key]
        for key in ("recruit", "orundum", "mining", "specialaccess", "signinevent")
    )
    callback(scheduler, 10002, taskchain="Award", taskid=1)
    params = append(scheduler, "Award")
    assert params == {
        "award": True,
        "mail": False,
        "recruit": False,
        "orundum": False,
        "mining": False,
        "specialaccess": False,
        "signinevent": False,
    }


@pytest.mark.parametrize("event", [10000, 10004, 20000])
def test_failed_stopped_or_unfinished_award_does_not_complete(scheduler, event):
    append(scheduler, "Award")
    callback(scheduler, event, taskchain="Award", taskid=1)
    if event == 20000:
        callback(scheduler, 10002, taskchain="Award", taskid=1)
    assert append(scheduler, "Award")["recruit"] is True
    assert scheduler.maa_daily_completed == {}


def test_only_submitted_enabled_options_complete(scheduler):
    base_schedule.config.conf.maa_mining = False
    append(scheduler, "Award")
    base_schedule.config.conf.maa_mining = True
    callback(scheduler, 10002, taskchain="Award", taskid=1)
    params = append(scheduler, "Award")
    assert params["mining"] is True
    assert params["recruit"] is False
    assert params["award"] is True
    base_schedule.config.conf.maa_mail = True
    assert append(scheduler, "Award")["mail"] is True


@pytest.mark.parametrize("node", ["VisitLimited", "VisitNextBlack"])
def test_mall_records_each_confirmed_action_without_hiding_unfinished_work(
    scheduler, node
):
    assert append(scheduler, "Mall")["credit_fight"] is True
    callback(
        scheduler,
        20002,
        taskchain="Mall",
        taskid=1,
        subtask="ProcessTask",
        details={"task": node},
    )
    params = append(scheduler, "Mall")
    assert params["visit_friends"] is False
    assert params["credit_fight"] is True
    assert params["shopping"] is True
    callback(
        scheduler,
        20002,
        taskchain="Mall",
        taskid=1,
        subtask="ProcessTask",
        details={"task": "StageDrops-Stars-3"},
    )
    assert append(scheduler, "Mall")["credit_fight"] is False


def test_mall_chain_completion_does_not_claim_failed_credit_fight_or_visits(scheduler):
    append(scheduler, "Mall")
    callback(scheduler, 10002, taskchain="Mall", taskid=1)
    params = append(scheduler, "Mall")
    assert params["credit_fight"] is True
    assert params["visit_friends"] is True


def test_shopping_only_never_completes_credit_or_visits(scheduler):
    params = append(scheduler, "Mall", mall_action="shopping")
    assert params["credit_fight"] is False
    assert params["visit_friends"] is False
    callback(scheduler, 10002, taskchain="Mall", taskid=1)
    assert append(scheduler, "Mall")["credit_fight"] is True


def test_native_visit_completion_also_suppresses_maa_visit(scheduler):
    scheduler.daily_visit_friend = base_schedule.get_server_time().date()
    assert append(scheduler, "Mall")["visit_friends"] is False


def test_cross_reset_completion_belongs_to_submission_day(scheduler, monkeypatch):
    now = datetime(2026, 10, 27, 23, 59)
    monkeypatch.setattr(base_schedule, "get_server_time", lambda: now)
    append(scheduler, "Award")
    now += timedelta(minutes=2)
    callback(scheduler, 10002, taskchain="Award", taskid=1)
    assert append(scheduler, "Award")["recruit"] is True
    assert scheduler.maa_daily_completed["recruit"] == date(2026, 10, 27)


def test_completion_persists_through_real_snapshot_and_startup_restore(
    scheduler, monkeypatch
):
    append(scheduler, "Award")
    callback(scheduler, 10002, taskchain="Award", taskid=1)
    append(scheduler, "Mall")
    for node in ("VisitLimited", "StageDrops-Stars-3"):
        callback(
            scheduler,
            20002,
            taskchain="Mall",
            taskid=2,
            subtask="ProcessTask",
            details={"task": node},
        )
    saved = record.load_state()
    assert (
        saved["maa_daily_completed"]["recruit"]
        == base_schedule.get_server_time().date()
    )
    scheduler.maa_daily_completed = {}
    scheduler.daily_visit_friend = date.min
    scheduler.credit_fight = None
    scheduler.op_data.validate_backup_plans.return_value = {"success": True}
    scheduler.initialize_operators = MagicMock(return_value=None)
    scheduler.run = MagicMock(side_effect=base_schedule.MowerExit)
    scheduler._request_run_order_restoration_observations = MagicMock()
    monkeypatch.setattr(mower, "initialize", lambda *a, **kw: scheduler)
    monkeypatch.setattr(mower.NewsChecker, "get_effective_maintenance", lambda: None)
    monkeypatch.setattr(mower, "refresh_resource_at_boundary", MagicMock())
    mower.simulate(saved)
    assert scheduler.run.called
    assert append(scheduler, "Award")["recruit"] is False
    params = append(scheduler, "Mall")
    assert params["credit_fight"] is False
    assert params["visit_friends"] is False


def test_unknown_or_malformed_callbacks_cannot_complete_unsubmitted_work(scheduler):
    append(scheduler, "Award")
    for taskid in (None, True, [], 999):
        callback(scheduler, 10002, taskchain="Award", taskid=taskid)
    callback(scheduler, 10002, taskchain="Mall", taskid=1)
    assert scheduler.maa_daily_completed == {}


def test_signin_alone_admits_maa_without_other_daily_tasks(scheduler):
    conf = Conf(
        stage_plan_enable=False,
        maa_credit_fight=False,
        maa_mall_enable=False,
        visit_friend_enable=False,
        maa_signinevent=True,
    )
    base_schedule.config.conf = conf
    assert conf.has_maa_daily_tasks is True
    assert conf.has_maa_tasks is True
    assert scheduler.has_maa_daily_tasks() is True
    assert append(scheduler, "Award")["signinevent"] is True


def test_previous_week_record_does_not_suppress_today(scheduler):
    scheduler.maa_daily_completed = {
        "credit_fight": base_schedule.get_server_time().date() - timedelta(days=7)
    }
    assert append(scheduler, "Mall")["credit_fight"] is True
