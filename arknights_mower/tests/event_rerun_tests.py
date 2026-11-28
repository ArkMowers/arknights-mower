import sqlite3
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import event_rerun as runner
from arknights_mower.solvers import record
from arknights_mower.solvers.operation import OperationSolver
from arknights_mower.tests import maa_copilot_tests as copilot
from arknights_mower.utils import config, event_rerun
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.scene import Scene

client = copilot.client
files = copilot.files
ACTIVITY = {
    "activity_id": "act46sre",
    "activity": "雪山降临1101",
    "start_ts": 100,
    "end_ts": 1800,
    "chapters": {"normal": "圣巡之旅", "ex": "变革之路"},
}


def stage(code, chapter="圣巡之旅", cost=10, **fields):
    return {
        "id": code,
        "name": code,
        "stageType": "ACTIVITY",
        "zoneId": "act46sre_zone1" if chapter == "圣巡之旅" else "act46sre_zone2",
        "subTitle": chapter,
        "apCost": cost,
        "difficulty": "NORMAL",
        "endTs": {"startTs": 100, "endTs": 1800},
        **fields,
    }


def event():
    return event_rerun.select_rerun(
        [ACTIVITY],
        [
            stage("OS-10"),
            stage("OS-1"),
            stage("OS-TR-1", cost=0),
            stage("OS-2", endTs=None),
            stage("OS-3", zoneId="act46side_zone1"),
            stage("OS-EX-8", "变革之路"),
            stage("OS-EX-8 突袭", "变革之路", difficulty="FOUR_STAR"),
        ],
        105,
    )


def test_resources_offer_only_timed_ordinary_rerun_battles():
    choice = event()
    assert choice["key"] == "act46sre:100"
    assert [item["code"] for item in choice["stages"]] == ["OS-1", "OS-10"]
    assert "raid" not in choice
    assert (
        event_rerun.select_rerun(
            [dict(ACTIVITY, activity_id="act46side")], [stage("OS-1")], 105
        )
        is None
    )
    assert event_rerun.select_rerun([ACTIVITY], [], 99) is None
    assert event_rerun.select_rerun([ACTIVITY], [], 1800) is None


@pytest.fixture
def database(monkeypatch, tmp_path):
    monkeypatch.setattr(record, "get_path", lambda path: tmp_path / path[5:])
    monkeypatch.setattr(record, "_tables_created", False)
    return tmp_path / "tmp/data.db"


def test_stage_claim_survives_new_connection_and_is_scoped_to_opening(database):
    assert record.load_event_rerun_progress("act46sre:100") == {}
    assert not database.exists()
    assert record.claim_event_rerun_stage("act46sre:100", "OS-1")
    assert not record.claim_event_rerun_stage("act46sre:100", "OS-1")
    assert record.load_event_rerun_progress("act46sre:100") == {"OS-1": "attempted"}
    record.complete_event_rerun_stage("act46sre:100", "OS-1")
    assert record.load_event_rerun_progress("act46sre:100") == {"OS-1": "completed"}
    record.release_event_rerun_stage("act46sre:100", "OS-1")
    assert not record.claim_event_rerun_stage("act46sre:100", "OS-1")
    assert record.claim_event_rerun_stage("act46sre:200", "OS-1")


@pytest.fixture
def scheduler(monkeypatch, database):
    for name in ("stop_mower", "stop_maa", "maintenance_recheck"):
        monkeypatch.setattr(config, name, Event())
    monkeypatch.setattr(
        config,
        "conf",
        Conf(maa_rg_enable=0, stage_plan_enable=True, event_rerun={"enabled": True}),
    )
    monkeypatch.setattr(runner, "current_rerun", event)

    class Clock(datetime):
        current = datetime(2026, 11, 24, 12)

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(runner, "datetime", Clock)
    recog = MagicMock()
    owner = SimpleNamespace(
        device=object(),
        recog=recog,
        tasks=[],
        deadline=Clock.now() + timedelta(seconds=10),
    )
    return owner, Clock


def test_budget_is_checked_before_each_claim_and_completion_survives_restart(
    scheduler, monkeypatch
):
    owner, clock = scheduler
    play = MagicMock()
    monkeypatch.setattr(runner, "_play_ordinary", play)
    owner.deadline -= timedelta(seconds=10)
    assert not runner.run_event_rerun(owner, lambda: owner.deadline)
    play.assert_not_called()

    owner.deadline += timedelta(seconds=10)

    def fight(owner, stage, settings, prepare, claim, complete, fail):
        assert prepare() > 0
        assert claim()
        clock.current += timedelta(minutes=5)
        complete()
        return "completed"

    play.side_effect = fight
    assert runner.run_event_rerun(owner, lambda: owner.deadline)
    assert play.call_count == 1
    assert record.load_event_rerun_progress("act46sre:100") == {"OS-1": "completed"}

    next_owner = SimpleNamespace(tasks=[], deadline=clock.now() + timedelta(minutes=5))
    assert runner.run_event_rerun(next_owner, lambda: next_owner.deadline)
    assert [call.args[1]["code"] for call in play.call_args_list] == ["OS-1", "OS-10"]
    assert not runner.run_event_rerun(next_owner, lambda: next_owner.deadline)


def test_navigation_reaching_scheduler_deadline_keeps_stage_pending(
    scheduler, monkeypatch
):
    owner, clock = scheduler

    def prepare_stage(owner, stage, settings, prepare, claim, complete, fail):
        assert prepare() > 0
        clock.current += timedelta(seconds=11)
        assert not claim()
        return "defer"

    play = MagicMock(side_effect=prepare_stage)
    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert not runner.run_event_rerun(owner, lambda: owner.deadline)
    play.assert_called_once()
    assert record.load_event_rerun_progress("act46sre:100") == {}


def test_stage_closing_time_limits_preparation_and_claim(scheduler, monkeypatch):
    owner, _ = scheduler
    opening = event()
    stage = opening["stages"][0]
    stage["end_ts"] = opening["now"] + 2
    opening["stages"] = [stage]
    monkeypatch.setattr(runner, "current_rerun", lambda: opening)
    elapsed = 0
    monkeypatch.setattr(runner, "monotonic", lambda: elapsed)

    def play(owner, stage, settings, prepare, claim, complete, fail):
        nonlocal elapsed
        assert prepare() == 2
        elapsed = 2
        with pytest.raises(InterruptedError):
            prepare()
        assert not claim()
        return "defer"

    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert runner.run_event_rerun(owner, lambda: owner.deadline) is False
    assert record.load_event_rerun_progress(opening["key"]) == {}


def test_cold_start_can_navigate_past_one_minute_and_settle_once(
    scheduler, monkeypatch
):
    owner, clock = scheduler
    owner.deadline = clock.now() + timedelta(seconds=100)
    elapsed = 0
    monkeypatch.setattr(runner, "monotonic", lambda: elapsed)
    navigator = MagicMock()

    def navigate(code):
        nonlocal elapsed
        assert code == "OS-1"
        assert io_timeout(120) == 100
        elapsed = 75
        clock.current += timedelta(seconds=elapsed)
        assert io_timeout(120) == 25
        return True

    navigator.run.side_effect = navigate
    monkeypatch.setattr(runner, "NavigationSolver", lambda *_: navigator)
    operation = MagicMock()

    def fight(**kwargs):
        assert kwargs["before_single_battle"]()
        clock.current += timedelta(seconds=30)
        kwargs["on_single_battle_settlement"]()
        return {"executed_runs": 1}

    operation.run.side_effect = fight
    monkeypatch.setattr(runner, "OperationSolver", lambda *_: operation)
    assert runner.run_event_rerun(owner, lambda: owner.deadline)
    navigator.confirm_selected_stage.assert_called_once()
    operation.run.assert_called_once()
    assert record.load_event_rerun_progress("act46sre:100") == {"OS-1": "completed"}


def test_unchanged_failed_preparation_yields_to_other_selected_stages(
    scheduler, monkeypatch
):
    owner, clock = scheduler
    order = []

    def play(owner, stage, settings, prepare, claim, complete, fail):
        order.append(stage["code"])
        if stage["code"] == "OS-1":
            fail("未能导航到目标关卡")
            return
        assert claim()
        complete()
        return "completed"

    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert runner.run_event_rerun(owner, lambda: owner.deadline)
    assert not runner.run_event_rerun(owner, lambda: owner.deadline)
    assert order == ["OS-1", "OS-10", "OS-1"]
    assert record.load_event_rerun_progress("act46sre:100") == {
        "OS-1": "failed",
        "OS-10": "completed",
    }
    assert owner.deadline == clock.now() + timedelta(seconds=10)


def test_unconfirmed_target_is_reported_and_retried_after_restart(
    scheduler, monkeypatch
):
    owner, _ = scheduler
    navigator = MagicMock()
    navigator.confirm_selected_stage.return_value = False
    monkeypatch.setattr(runner, "NavigationSolver", lambda *_: navigator)
    operation = MagicMock()
    monkeypatch.setattr(runner, "OperationSolver", operation)

    assert not runner.run_event_rerun(owner, lambda: owner.deadline)
    operation.assert_not_called()
    reasons = {}
    assert record.event_rerun_status("act46sre:100", failure_reasons=reasons) == {
        "OS-1": "failed",
        "OS-10": "failed",
    }
    assert reasons == dict.fromkeys(["OS-1", "OS-10"], "未能在详情页确认目标关卡")
    restarted = SimpleNamespace(device=object(), recog=MagicMock())
    assert runner.run_event_rerun(restarted, lambda: owner.deadline) is False
    assert [call.args[0] for call in navigator.run.call_args_list] == [
        "OS-1",
        "OS-10",
    ] * 2
    assert record.load_event_rerun_progress("act46sre:200") == {}


@pytest.mark.parametrize("allow", [True, False])
def test_ordinary_keeps_device_io_after_deadline_during_battle(
    scheduler, monkeypatch, allow
):
    owner, clock = scheduler
    assert config.conf.event_rerun.use_sanity_potion is True
    config.conf.event_rerun.use_sanity_potion = allow
    navigator = MagicMock()
    monkeypatch.setattr(runner, "NavigationSolver", lambda *_: navigator)
    navigator.confirm_selected_stage.return_value = True
    operation = MagicMock()

    def run(**kwargs):
        assert kwargs["use_sanity_potion"] is allow
        assert io_timeout(60) <= 10
        assert kwargs["before_single_battle"]()
        clock.current += timedelta(minutes=5)
        assert io_timeout(60) == 60
        kwargs["on_single_battle_settlement"]()
        return {"executed_runs": 1}

    operation.run.side_effect = run
    monkeypatch.setattr(runner, "OperationSolver", lambda *_: operation)
    assert runner.run_event_rerun(owner, lambda: owner.deadline)
    assert operation.run.call_count == 1
    assert record.load_event_rerun_progress("act46sre:100") == {"OS-1": "completed"}


def test_unconfirmed_attempt_stays_claimed_after_new_scheduler(scheduler, monkeypatch):
    owner, clock = scheduler

    def play(owner, stage, settings, prepare, claim, complete, fail):
        assert claim()
        return "defer"

    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert runner.run_event_rerun(owner, lambda: owner.deadline)
    later = SimpleNamespace(tasks=[], deadline=owner.deadline)
    assert runner.run_event_rerun(later, lambda: later.deadline)
    assert not runner.run_event_rerun(later, lambda: later.deadline)
    assert record.load_event_rerun_progress("act46sre:100") == {
        "OS-1": "attempted",
        "OS-10": "attempted",
    }


def test_single_proxy_guard_disallows_unconfirmed_multipliers():
    solver = object.__new__(OperationSolver)
    solver.scene = lambda: Scene.OPERATOR_BEFORE
    solver.find = MagicMock(return_value=None)
    solver.recog = SimpleNamespace(gray=np.full((1080, 1920), 255, dtype=np.uint8))
    solver.before_single_battle = MagicMock(return_value=True)
    solver.single_battle_started = False
    solver.auto_repeat = False
    solver.stage_id = "OS-1"
    solver.number = MagicMock(return_value=2)
    solver.on_single_battle_failure = MagicMock()
    solver.tap_element = MagicMock()
    assert solver.transition()
    solver.before_single_battle.assert_not_called()
    solver.on_single_battle_failure.assert_called_once_with("未能确认代理次数为一次")
    solver.tap_element.assert_not_called()


@pytest.mark.parametrize(
    "scene, clicked, reason",
    [
        (Scene.OPERATOR_FAILED, False, "代理作战失败"),
        (Scene.OPERATOR_GIVEUP, True, "代理作战已放弃行动"),
        (Scene.OPERATOR_GIVEUP, False, None),
    ],
)
@pytest.mark.parametrize("started", [False, True])
def test_only_owned_and_confirmed_battle_losses_are_reported(
    scene, clicked, reason, started
):
    solver = object.__new__(OperationSolver)
    solver.scene = lambda: scene
    solver.on_single_battle_failure = MagicMock()
    solver.single_battle_started = started
    solver.stage_id = "OS-1"
    solver.current_batch_repeat_count = 1
    solver._finish_batch = MagicMock()
    solver.tap = MagicMock()
    solver.tap_element = MagicMock(return_value=clicked)
    assert solver.transition()
    if reason and started:
        solver.on_single_battle_failure.assert_called_once_with(reason)
    else:
        solver.on_single_battle_failure.assert_not_called()


def test_single_proxy_confirms_battle_once_and_records_before_closing_settlement():
    solver = object.__new__(OperationSolver)
    solver.scene = MagicMock(
        side_effect=[
            Scene.OPERATOR_SELECT,
            Scene.OPERATOR_SELECT,
            Scene.OPERATOR_FINISH,
        ]
    )
    solver.before_single_battle = MagicMock(return_value=True)
    solver.on_single_battle_settlement = MagicMock()
    solver.single_battle_started = False
    solver.current_batch_started_at = datetime.now()
    solver.current_batch_repeat_count = 1
    solver.stage_id = "OS-1"
    solver.sleep = MagicMock()
    solver._record_batch_drops = MagicMock()
    solver.tap = MagicMock()

    solver.transition()
    solver.transition()
    solver.before_single_battle.assert_called_once()
    assert solver.tap.call_count == 1
    assert solver.transition()
    solver.on_single_battle_settlement.assert_called_once()
    assert solver.tap.call_count == 2


@pytest.mark.parametrize(
    "url", ["/stage/event-rerun", "/maa-long-task-status?kind=event_rerun"]
)
@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("token", [None, "invalid", "copilot-test-token"])
def test_status_requires_token_before_reading(
    client, monkeypatch, database, method, token, url
):
    read = MagicMock(return_value=event())
    monkeypatch.setattr(event_rerun, "current_rerun", read)
    headers = {} if token is None else {"token": token}
    response = client.open(url, method=method, headers=headers)
    if token == "copilot-test-token":
        read.assert_called_once()
        assert response.status_code == 200
        assert not database.exists()
        if method == "GET":
            assert response.json["stage_seconds"] == 240
            assert response.json["event"]["key"] == "act46sre:100"
    else:
        assert response.status_code == 403
        read.assert_not_called()


@pytest.mark.parametrize("master, enabled", [(False, True), (True, False)])
def test_disabled_stage_plan_or_rerun_skips_resource_reads(
    scheduler, monkeypatch, master, enabled
):
    owner, _ = scheduler
    config.conf.stage_plan_enable = master
    config.conf.event_rerun.enabled = enabled
    lookup = MagicMock()
    monkeypatch.setattr(runner, "current_rerun", lookup)
    assert not runner.run_event_rerun(owner, lambda: owner.deadline)
    lookup.assert_not_called()


def test_old_long_task_windows_retire_without_enabling_all_stages():
    window = {"start": "10:00", "end": "11:00", "weekdays": [1]}
    settings = dict(
        maa_long_task_type="event_rerun",
        maa_rg_enable=1,
        event_rerun={
            "event_key": "old",
            "stages": ["OS-1"],
            "raid_enabled": True,
            "use_sanity_potion": False,
        },
    )
    assert Conf(**settings).maa_long_task_weekly_windows == []
    conf = Conf(
        **settings,
        maa_long_task_weekly_windows=[
            window,
            dict(window, task_type="event_rerun"),
            dict(window, task_type="garrison"),
        ],
    )
    assert [w.task_type for w in conf.maa_long_task_weekly_windows] == ["garrison"]
    assert conf.event_rerun.model_dump() == {
        "enabled": False,
        "use_sanity_potion": False,
    }
    conf = Conf(
        maa_long_task_type="sss",
        maa_long_task_weekly_windows=[window, dict(window, task_type="event_rerun")],
    )
    assert conf.maa_long_task_type == "sss"
    assert [w.task_type for w in conf.maa_long_task_weekly_windows] == [None]


def test_expired_budget_during_database_claim_keeps_stage_pending(
    scheduler, monkeypatch
):
    owner, clock = scheduler
    original = record.claim_event_rerun_stage

    def delayed_claim(key, code, previous):
        claimed = original(key, code, previous)
        clock.current += timedelta(seconds=11)
        return claimed

    monkeypatch.setattr(record, "claim_event_rerun_stage", delayed_claim)

    def play(owner, stage, settings, prepare, claim, complete, fail):
        assert not claim()
        return "defer"

    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert not runner.run_event_rerun(owner, lambda: owner.deadline)
    assert record.load_event_rerun_progress("act46sre:100") == {}


def test_next_opening_runs_all_ordinary_stages_with_previous_opening_complete(
    scheduler, monkeypatch
):
    owner, _ = scheduler

    def play(owner, stage, settings, prepare, claim, complete, fail):
        assert claim()
        complete()
        return "completed"

    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert runner.run_event_rerun(owner, lambda: owner.deadline)
    monkeypatch.setattr(runner, "current_rerun", lambda: None)
    assert runner.run_event_rerun(owner, lambda: owner.deadline) is None
    monkeypatch.setattr(
        runner, "current_rerun", lambda: dict(event(), key="act46sre:200")
    )
    assert runner.run_event_rerun(owner, lambda: owner.deadline)
    for key in ("act46sre:100", "act46sre:200"):
        assert record.load_event_rerun_progress(key) == {
            "OS-1": "completed",
            "OS-10": "completed",
        }


RERUN_URL = "/stage/event-rerun"
STAGE_CHANGE = {
    "event_key": "act46sre:100",
    "stage": "OS-1",
    "expected": "pending",
    "completed": True,
}


@pytest.mark.parametrize("token", [None, "invalid"])
def test_progress_edit_auth_before_reads_or_writes(
    client, database, monkeypatch, token
):
    read = MagicMock()
    monkeypatch.setattr(event_rerun, "current_rerun", read)
    headers = {"token": token} if token else {}
    assert (
        client.patch(RERUN_URL, json=STAGE_CHANGE, headers=headers).status_code == 403
    )
    read.assert_not_called()
    assert not database.exists()


@pytest.mark.parametrize(
    "url,fields,status",
    [
        ("/maa-long-task-status?kind=event_rerun", {}, 405),
        (RERUN_URL, {"completed": 1}, 400),
        (RERUN_URL, {"event_key": "act46sre:99"}, 409),
        (RERUN_URL, {"stage": "OS-EX-8"}, 400),
        (RERUN_URL, {"expected": "running"}, 400),
    ],
)
def test_invalid_stage_edits_leave_progress_untouched(
    client, database, monkeypatch, url, fields, status
):
    monkeypatch.setattr(event_rerun, "current_rerun", event)
    response = client.patch(
        url, json={**STAGE_CHANGE, **fields}, headers={"token": "copilot-test-token"}
    )
    assert response.status_code == status
    assert not database.exists()


def test_read_legacy_three_column_progress_and_keep_legacy_writes(
    client, database, monkeypatch
):
    monkeypatch.setattr(event_rerun, "current_rerun", event)
    key = event()["key"]
    database.parent.mkdir(exist_ok=True)
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE event_rerun_progress (event_key TEXT, stage TEXT, status TEXT, PRIMARY KEY(event_key, stage))"
        )
        conn.execute(
            "INSERT INTO event_rerun_progress VALUES (?, 'OS-1', 'completed')", (key,)
        )
    headers = {"token": "copilot-test-token"}
    state = client.get(RERUN_URL, headers=headers).json
    assert state["progress"] == {"OS-1": "completed"}
    assert state["failure_reasons"] == {}
    record.fail_event_rerun_stage(key, "OS-10", "未能导航到目标关卡", attempted=False)
    with sqlite3.connect(database) as conn:
        conn.execute(
            "INSERT INTO event_rerun_progress VALUES (?, 'OS-2', 'attempted')", (key,)
        )
    state = client.get(RERUN_URL, headers=headers).json
    assert state["progress"] == {"OS-1": "completed", "OS-10": "failed"}
    assert state["failure_reasons"] == {"OS-10": "未能导航到目标关卡"}


def test_manual_completion_skips_stage_and_reset_allows_another_battle(
    client, scheduler, monkeypatch
):
    owner, _ = scheduler
    monkeypatch.setattr(event_rerun, "current_rerun", event)
    headers = {"token": "copilot-test-token"}

    def change(expected, completed):
        return client.patch(
            RERUN_URL,
            json=dict(STAGE_CHANGE, expected=expected, completed=completed),
            headers=headers,
        )

    assert change("pending", True).json["progress"] == {"OS-1": "completed"}
    assert change("pending", True).status_code == 200
    assert runner.pending_rerun(owner, lambda: owner.deadline)[1]["code"] == "OS-10"
    assert change("completed", False).json["progress"] == {}
    assert runner.pending_rerun(owner, lambda: owner.deadline)[1]["code"] == "OS-1"

    with record.event_rerun_execution(STAGE_CHANGE["event_key"], "OS-1") as admitted:
        assert admitted
        assert record.claim_event_rerun_stage(STAGE_CHANGE["event_key"], "OS-1")
        assert client.get(RERUN_URL, headers=headers).json["progress"] == {
            "OS-1": "running"
        }
        for completed in (True, False):
            assert change("attempted", completed).status_code == 409
        assert (
            client.patch(
                RERUN_URL, json=dict(STAGE_CHANGE, stage="OS-10"), headers=headers
            ).status_code
            == 200
        )
    assert change("pending", True).status_code == 409
    assert change("attempted", False).json["progress"] == {"OS-10": "completed"}
    assert record.claim_event_rerun_stage(STAGE_CHANGE["event_key"], "OS-1")
    assert change("attempted", True).json["progress"]["OS-1"] == "completed"


@pytest.mark.parametrize("url", [RERUN_URL, "/maa-long-task-status?kind=event_rerun"])
def test_unreadable_progress_skips_rerun_and_returns_status_error(
    client, scheduler, database, monkeypatch, url
):
    owner, _ = scheduler
    database.parent.mkdir(exist_ok=True)
    database.write_bytes(b"unreadable progress database")
    play = MagicMock()
    monkeypatch.setattr(runner, "_play_ordinary", play)
    monkeypatch.setattr(event_rerun, "current_rerun", event)

    assert runner.run_event_rerun(owner, lambda: owner.deadline) is None
    play.assert_not_called()
    response = client.get(url, headers={"token": "copilot-test-token"})
    assert response.status_code == 503
    assert response.json == {"message": "暂时无法读取复刻关卡进度，请稍后重试"}


def test_manual_completion_before_preparation_skips_operation(scheduler, monkeypatch):
    owner, _ = scheduler
    select = runner.pending_rerun

    def mark_selected_completed(*args):
        pending = select(*args)
        if pending:
            opening, stage = pending[:2]
            assert record.set_event_rerun_completion(
                opening["key"], stage["code"], "pending", True
            )
        return pending

    monkeypatch.setattr(runner, "pending_rerun", mark_selected_completed)
    play = MagicMock()
    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert runner.run_event_rerun(owner, lambda: owner.deadline) is False
    play.assert_not_called()


def test_preparation_before_potions_rejects_edits_without_durable_battle_claim(
    client, scheduler, monkeypatch
):
    owner, _ = scheduler
    monkeypatch.setattr(event_rerun, "current_rerun", event)

    def preparing(_owner, stage, settings, prepare, claim, complete, fail):
        assert settings.use_sanity_potion
        assert record.load_event_rerun_progress(STAGE_CHANGE["event_key"]) == {}
        response = client.patch(
            RERUN_URL, json=STAGE_CHANGE, headers={"token": "copilot-test-token"}
        )
        assert response.status_code == 409
        return "defer"

    monkeypatch.setattr(runner, "_play_ordinary", preparing)
    assert runner.run_event_rerun(owner, lambda: owner.deadline) is False
    assert record.event_rerun_status(STAGE_CHANGE["event_key"]) == {}
    assert (
        client.patch(
            RERUN_URL, json=STAGE_CHANGE, headers={"token": "copilot-test-token"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("completed", [False, True])
def test_persisted_failure_is_editable_only_after_execution(
    client, scheduler, monkeypatch, completed
):
    owner, _ = scheduler
    key = STAGE_CHANGE["event_key"]
    monkeypatch.setattr(event_rerun, "current_rerun", event)
    headers = {"token": "copilot-test-token"}
    change = dict(STAGE_CHANGE, expected="failed", completed=completed)

    def play(_owner, stage, settings, prepare, claim, complete, fail):
        assert claim()
        fail("代理作战失败")
        assert client.patch(RERUN_URL, json=change, headers=headers).status_code == 409
        raise RuntimeError("closing settlement failed")

    monkeypatch.setattr(runner, "_play_ordinary", play)
    # Leave only one eligible stage in this opening.
    assert record.set_event_rerun_completion(key, "OS-10", "pending", True)
    assert runner.run_event_rerun(owner, lambda: owner.deadline)
    record.complete_event_rerun_stage(key, "OS-1")
    for url in (RERUN_URL, "/maa-long-task-status?kind=event_rerun"):
        state = client.get(url, headers=headers).json
        assert state["progress"] == {"OS-1": "failed", "OS-10": "completed"}
        assert state["failure_reasons"] == {"OS-1": "代理作战失败"}
        assert state["retryable_failures"] == ["OS-1"]
    edit = client.patch(RERUN_URL, json=change, headers=headers)
    assert edit.status_code == 200
    assert edit.json["failure_reasons"] == {}
    assert edit.json["progress"].get("OS-1", "pending") == (
        "completed" if completed else "pending"
    )
    record.fail_event_rerun_stage(key, "OS-1", "代理作战失败", attempted=True)
    assert record.event_rerun_status(key).get("OS-1", "pending") == (
        "completed" if completed else "pending"
    )


@pytest.mark.parametrize(
    "outcome", ["sanity", "cancel", "deadline", "setup_error", "unknown_battle"]
)
def test_only_preparation_errors_become_failed(scheduler, monkeypatch, outcome):
    owner, clock = scheduler
    navigator = MagicMock()
    monkeypatch.setattr(runner, "NavigationSolver", lambda *_: navigator)
    operation = MagicMock()

    def fight(**kwargs):
        if outcome == "unknown_battle":
            assert kwargs["before_single_battle"]()
        if outcome in ("setup_error", "unknown_battle"):
            raise RuntimeError("screen unavailable")
        if outcome == "cancel":
            config.stop_maa.set()
        if outcome == "deadline":
            clock.current = owner.deadline
        return {"executed_runs": 0, "sanity_drain": outcome == "sanity"}

    operation.run.side_effect = fight
    monkeypatch.setattr(runner, "OperationSolver", lambda *_: operation)
    runner.run_event_rerun(owner, lambda: owner.deadline)
    status = {"setup_error": "failed", "unknown_battle": "attempted"}.get(outcome)
    expected = dict.fromkeys(["OS-1", "OS-10"], status) if status else {}
    assert record.load_event_rerun_progress(STAGE_CHANGE["event_key"]) == expected


def test_transient_failure_can_become_confirmed_lock_until_manually_reset(
    client, scheduler, monkeypatch
):
    owner, _ = scheduler
    key = event()["key"]
    headers = {"token": "copilot-test-token"}
    monkeypatch.setattr(event_rerun, "current_rerun", event)
    record.fail_event_rerun_stage(key, "OS-1", "未能导航到目标关卡", attempted=False)
    assert record.set_event_rerun_completion(key, "OS-10", "pending", True)
    monkeypatch.setattr(runner, "NavigationSolver", lambda *_: MagicMock())
    operation = object.__new__(OperationSolver)
    operation.scene = lambda: Scene.OPERATOR_BEFORE
    operation.find = lambda name: name == "ope_agency_lock"

    def fight(**kwargs):
        operation.before_single_battle = kwargs["before_single_battle"]
        operation.on_single_battle_failure = kwargs["on_single_battle_failure"]
        operation.single_battle_started = False
        assert operation.transition()
        return {"executed_runs": 0, "sanity_drain": False}

    operation.run = MagicMock(side_effect=fight)
    monkeypatch.setattr(runner, "OperationSolver", lambda *_: operation)
    assert runner.run_event_rerun(owner, lambda: owner.deadline) is False
    assert runner.run_event_rerun(owner, lambda: owner.deadline) is None
    operation.run.assert_called_once()
    state = client.get(RERUN_URL, headers=headers).json
    assert state["failure_reasons"] == {"OS-1": "目标关卡尚未解锁代理指挥"}
    assert state["retryable_failures"] == []
    response = client.patch(
        RERUN_URL,
        json={**STAGE_CHANGE, "expected": "failed", "completed": False},
        headers=headers,
    )
    assert response.status_code == 200
    assert runner.pending_rerun(owner, lambda: owner.deadline)[1]["code"] == "OS-1"


@pytest.mark.parametrize("previous", [None, "旧版记录的准备失败"])
@pytest.mark.parametrize("started", [False, True])
def test_exhausted_scene_recovery_stops_dispatch_without_poisoning_stages(
    scheduler, monkeypatch, previous, started
):
    owner, _ = scheduler
    key = event()["key"]
    if previous:
        record.fail_event_rerun_stage(key, "OS-1", previous, attempted=False)

    def play(_owner, stage, settings, prepare, claim, complete, fail):
        if started:
            assert claim()
        raise runner.SceneRecoveryExhausted

    play = MagicMock(side_effect=play)
    monkeypatch.setattr(runner, "_play_ordinary", play)
    with pytest.raises(runner.SceneRecoveryExhausted):
        runner.run_event_rerun(owner, lambda: owner.deadline)
    play.assert_called_once()
    reasons = {}
    state = record.event_rerun_status(key, failure_reasons=reasons)
    expected = {"OS-1": "failed"} if previous else {}
    assert state == ({"OS-1": "attempted"} if started else expected)
    assert reasons == ({"OS-1": previous} if previous and not started else {})


def test_retry_claim_rolled_back_to_previous_failure_if_deadline_moves(
    scheduler, monkeypatch
):
    owner, clock = scheduler
    key = event()["key"]
    previous = "上次代理作战失败"
    record.fail_event_rerun_stage(key, "OS-1", previous, attempted=False)
    original = record.claim_event_rerun_stage

    def claim_then_expire(*args):
        assert original(*args)
        clock.current = owner.deadline
        return True

    monkeypatch.setattr(record, "claim_event_rerun_stage", claim_then_expire)

    def play(_owner, stage, settings, prepare, claim, complete, fail):
        assert not claim()
        return "defer"

    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert runner.run_event_rerun(owner, lambda: owner.deadline) is False
    reasons = {}
    assert record.event_rerun_status(key, failure_reasons=reasons) == {"OS-1": "failed"}
    assert reasons == {"OS-1": previous}


def test_old_failures_classify_exact_lock_only_and_retry_claim_completes(
    client, scheduler, database, monkeypatch
):
    owner, _ = scheduler
    key = event()["key"]
    monkeypatch.setattr(event_rerun, "current_rerun", event)
    database.parent.mkdir(exist_ok=True)
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE event_rerun_progress (event_key TEXT, stage TEXT, status TEXT, PRIMARY KEY(event_key, stage))"
        )
        conn.executemany(
            "INSERT INTO event_rerun_progress VALUES (?, ?, ?)",
            [
                (key, "OS-1", "failed:目标关卡尚未解锁代理指挥"),
                (key, "OS-10", "failed"),
            ],
        )
    state = client.get(RERUN_URL, headers={"token": "copilot-test-token"}).json
    assert set(state["progress"].values()) == {"failed"}
    assert state["retryable_failures"] == ["OS-10"]

    def play(_owner, stage, settings, prepare, claim, complete, fail):
        assert stage["code"] == "OS-10"
        assert claim()
        complete()

    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert runner.run_event_rerun(owner, lambda: owner.deadline) is True
    assert record.load_event_rerun_progress(key) == {
        "OS-1": "failed",
        "OS-10": "completed",
    }


@pytest.mark.parametrize(
    "replacement", ["completed", "failed:目标关卡尚未解锁代理指挥"]
)
def test_retry_rechecks_progress_on_admission_and_on_battle_claim(
    database, replacement
):
    key, stage = "act46sre:100", "OS-1"
    record.fail_event_rerun_stage(key, stage, "未能导航到目标关卡", attempted=False)
    with record.event_rerun_execution(key, stage) as previous:
        assert previous is not None
        with record.event_rerun_execution(key, stage) as competing:
            assert competing is None
        assert not record.set_event_rerun_completion(key, stage, "failed", True)
        with sqlite3.connect(database) as conn:
            conn.execute(
                "UPDATE event_rerun_progress SET status=? WHERE event_key=? AND stage=?",
                (replacement, key, stage),
            )
        assert not record.claim_event_rerun_stage(key, stage, previous)
        record.fail_event_rerun_stage(
            key, stage, "未能确认目标关卡", attempted=False, previous=previous
        )
    with record.event_rerun_execution(key, stage) as competing:
        assert competing is None
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT status FROM event_rerun_progress").fetchone() == (
            replacement,
        )
