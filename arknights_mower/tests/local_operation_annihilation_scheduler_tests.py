"""A full weekly reward or locked Proxy Command ends only the Annihilation stage."""

import sys
from datetime import datetime, timedelta
from functools import partial
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.utils import maa_stage_inventory  # noqa: E402


def operation_result(flag, **kwargs):
    skipped = kwargs["stage_id"] == "Annihilation"
    ap = kwargs["simulated_current_ap"]
    # Annihilation: the weekly-full and locked branches return before any battle.
    result = {
        "executed_runs": 0 if skipped else 1,
        "sanity_drain": False,
        "annihilation_reward_full": False,
        "annihilation_agency_locked": False,
        "next_threshold_time": None,
        "stopped_by_deadline": False,
        "stopped_by_inventory": False,
        "inventory_unconfirmed": False,
        "last_batch_duration_seconds": None,
        "simulated_current_ap": ap if skipped else ap - 25,
        "remaining_runs": kwargs["target_total_runs"] if skipped else 0,
    }
    result[flag] = skipped
    return result


@pytest.fixture(params=["annihilation_reward_full", "annihilation_agency_locked"])
def local(monkeypatch, request):
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.device = MagicMock()
    solver.recog = MagicMock()
    solver.tasks = [
        SimpleNamespace(time=datetime.now() + timedelta(hours=2), meta_data="")
    ]
    solver.local_operation_followup_time = None
    solver.last_execution = {"maa": None}
    solver.back_to_index = MagicMock()
    solver.maybe_switch_expired_activity_plan = MagicMock()
    solver.check_current_focus = MagicMock()
    solver.mower_stage_ap_cost = MagicMock(return_value=25)
    solver.report_annihilation_agency_locked = MagicMock()
    monkeypatch.setattr(base_schedule, "get_server_weekday", lambda: 0)
    for name in (
        "scheduling",
        "send_message",
        "save_exception",
        "MissionSolver",
        "cultivateDepotSolver",
    ):
        monkeypatch.setattr(base_schedule, name, MagicMock())
    monkeypatch.setattr(
        maa_stage_inventory, "load_inventory_snapshot", lambda: ({}, None)
    )
    player = MagicMock()
    player.return_value.get_first_available_snapshot.return_value = SimpleNamespace(
        current_ap=120
    )
    monkeypatch.setattr(base_schedule, "PlayerInfoClient", player)
    navigation = MagicMock()
    navigation.return_value.run.return_value = True
    monkeypatch.setattr(base_schedule, "NavigationSolver", navigation)
    operation = MagicMock()
    operation.return_value.run.side_effect = partial(operation_result, request.param)
    monkeypatch.setattr(base_schedule, "OperationSolver", operation)

    def plan(*stages):
        conf = SimpleNamespace(
            maa_gap=4,
            maa_stage_inventory_enable=True,
            maa_stage_limit_rules=[],
            maa_stage_ratio_rules=[],
            maa_weekly_plan=[SimpleNamespace(stage=list(stages), sanity_threshold=100)],
        )
        monkeypatch.setattr(base_schedule.config, "conf", conf)

    return SimpleNamespace(
        solver=solver,
        plan=plan,
        locked=request.param == "annihilation_agency_locked",
        reports=solver.report_annihilation_agency_locked,
        navigated=lambda: [
            c.args[0] for c in navigation.return_value.run.call_args_list
        ],
    )


def next_dispatch(solver):
    # The follow-up or the dispatch interval has elapsed since the last local run.
    solver.tasks = [
        t for t in solver.tasks if t.meta_data != base_schedule.FOLLOWUP_TASK_META
    ]
    solver.local_operation_followup_time = None
    solver.last_execution["maa"] -= timedelta(hours=4, minutes=1)


def test_skipped_annihilation_ends_only_that_stage_in_the_dispatch(local):
    local.plan("Annihilation", "1-7")

    local.solver.mower_plan_solver()

    assert local.navigated() == ["Annihilation", "1-7"]
    assert local.solver.last_execution["maa"] is not None
    assert local.reports.call_count == int(local.locked)
    local.solver.device.exit.assert_not_called()

    next_dispatch(local.solver)
    local.solver.mower_plan_solver()

    # Nothing is remembered: the next dispatch checks Annihilation again.
    assert local.navigated() == ["Annihilation", "1-7"] * 2
    assert local.reports.call_count == 2 * int(local.locked)


def test_only_skipped_annihilation_waits_for_maa_gap_without_followup(local):
    local.plan("Annihilation")

    local.solver.mower_plan_solver()

    assert local.navigated() == ["Annihilation"]
    assert local.solver.local_operation_followup_time is None
    assert local.solver.last_execution["maa"] is not None

    # Unchanged state before the interval elapses: no renavigation.
    local.solver.mower_plan_solver()
    assert local.navigated() == ["Annihilation"]

    next_dispatch(local.solver)
    local.solver.mower_plan_solver()

    assert local.navigated() == ["Annihilation", "Annihilation"]
    local.solver.device.exit.assert_not_called()


def test_locked_proxy_command_mails_once_per_game_day(monkeypatch):
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.annihilation_lock_mail_day = None
    solver.device = object()
    mail = MagicMock()
    log = MagicMock()
    monkeypatch.setattr(base_schedule, "send_message", mail)
    monkeypatch.setattr(base_schedule, "logger", log)
    day = datetime(2026, 11, 2, 9)
    monkeypatch.setattr(base_schedule, "get_server_time", lambda: day)

    solver.report_annihilation_agency_locked()
    solver.report_annihilation_agency_locked()

    mail.assert_called_once()
    body, subject = mail.call_args.args
    assert subject == "剿灭代理指挥未解锁"
    assert "不使用助战干员" in body
    assert mail.call_args.kwargs == {
        "level": "ERROR",
        "archive_screenshots": True,
        "screenshot_source": solver.device,
    }
    # The repeat on the same game day only logs, without another archive.
    log.error.assert_called_once()
    assert log.error.call_args.kwargs == {"extra": {"archive_screenshots": False}}

    next_day = day + timedelta(days=1)
    monkeypatch.setattr(base_schedule, "get_server_time", lambda: next_day)
    solver.report_annihilation_agency_locked()

    assert mail.call_count == 2


@pytest.mark.parametrize("attach_screenshot", [False, True])
def test_locked_proxy_mail_uses_current_device_screenshot_only_once(
    monkeypatch, attach_screenshot
):
    from arknights_mower.utils import email

    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.annihilation_lock_mail_day = None
    solver.device = object()
    conf = SimpleNamespace(
        mail_enable=True,
        notification_level="INFO",
        mail_subject="",
        mail_attach_error_screenshot=attach_screenshot,
    )
    screenshot = object()
    read_screenshot = MagicMock(return_value=(screenshot, "2026-11-07 12:00:00"))
    transport, thread, save = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(email.config, "conf", conf)
    monkeypatch.setattr(email, "logger", MagicMock())
    monkeypatch.setattr(email, "_notification_screenshot", read_screenshot)
    monkeypatch.setattr(email, "Email", transport)
    monkeypatch.setattr(email, "Thread", thread)
    monkeypatch.setattr(base_schedule, "send_message", email.send_message)
    monkeypatch.setattr(base_schedule, "logger", MagicMock())
    monkeypatch.setattr(base_schedule, "save_current_state", save)
    monkeypatch.setattr(
        base_schedule, "get_server_time", lambda: datetime(2026, 11, 7, 12)
    )

    solver.report_annihilation_agency_locked()
    solver.report_annihilation_agency_locked()

    transport.assert_called_once()
    thread.assert_called_once()
    thread.return_value.start.assert_called_once_with()
    save.assert_called_once_with()
    if attach_screenshot:
        read_screenshot.assert_called_once()
        assert read_screenshot.call_args.args[1:] == (conf, solver.device)
        assert transport.call_args.kwargs["inline_image"] is screenshot
        assert "cid:mower-screenshot" in transport.call_args.args[0]
    else:
        read_screenshot.assert_not_called()
        assert "inline_image" not in transport.call_args.kwargs
