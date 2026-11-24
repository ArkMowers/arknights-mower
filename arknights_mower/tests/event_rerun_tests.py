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
        deadline=Clock.now() + timedelta(minutes=4, seconds=10),
    )
    return owner, Clock


def test_budget_is_checked_before_each_claim_and_completion_survives_restart(
    scheduler, monkeypatch
):
    owner, clock = scheduler
    play = MagicMock()
    monkeypatch.setattr(runner, "_play_ordinary", play)
    owner.deadline -= timedelta(seconds=11)
    assert not runner.run_event_rerun(owner, lambda: owner.deadline)
    play.assert_not_called()

    owner.deadline += timedelta(seconds=11)

    def fight(owner, stage, settings, prepare, claim, complete):
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


def test_navigation_cannot_spend_the_battle_reserve(scheduler, monkeypatch):
    owner, clock = scheduler

    def prepare_stage(owner, stage, settings, prepare, claim, complete):
        assert prepare() > 0
        clock.current += timedelta(seconds=11)
        assert not claim()
        return "defer"

    play = MagicMock(side_effect=prepare_stage)
    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert not runner.run_event_rerun(owner, lambda: owner.deadline)
    play.assert_called_once()
    assert record.load_event_rerun_progress("act46sre:100") == {}
    assert not owner.event_rerun_blocked[1]


def test_unchanged_failed_preparation_yields_to_other_selected_stages(
    scheduler, monkeypatch
):
    owner, clock = scheduler
    order = []

    def play(owner, stage, settings, prepare, claim, complete):
        order.append(stage["code"])
        if stage["code"] == "OS-1":
            return "blocked"
        assert claim()
        complete()
        return "completed"

    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert runner.run_event_rerun(owner, lambda: owner.deadline)
    assert not runner.run_event_rerun(owner, lambda: owner.deadline)
    assert order == ["OS-1", "OS-10"]
    assert record.load_event_rerun_progress("act46sre:100") == {"OS-10": "completed"}
    assert owner.deadline == clock.now() + timedelta(minutes=4, seconds=10)


@pytest.mark.parametrize("allow", [True, False])
def test_ordinary_keeps_device_io_after_deadline_during_battle(
    scheduler, monkeypatch, allow
):
    owner, clock = scheduler
    assert config.conf.event_rerun.use_sanity_potion is True
    config.conf.event_rerun.use_sanity_potion = allow
    navigator = MagicMock()
    navigator.scene.return_value = Scene.OPERATOR_BEFORE
    navigator.normalize_stage_text.side_effect = lambda text: text
    monkeypatch.setattr(runner, "NavigationSolver", lambda *_: navigator)
    monkeypatch.setattr(
        runner,
        "ActivityNavigation",
        lambda _: SimpleNamespace(read=lambda: [(None, "OS-1", 0.99)]),
    )
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

    def play(owner, stage, settings, prepare, claim, complete):
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
    solver.tap_element = MagicMock()
    assert solver.transition()
    solver.before_single_battle.assert_not_called()
    solver.tap_element.assert_not_called()


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


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("token", [None, "invalid", "copilot-test-token"])
def test_status_requires_token_before_reading(
    client, monkeypatch, database, method, token
):
    read = MagicMock(return_value=event())
    monkeypatch.setattr(event_rerun, "current_rerun", read)
    headers = {} if token is None else {"token": token}
    response = client.open(
        "/maa-long-task-status?kind=event_rerun", method=method, headers=headers
    )
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

    def delayed_claim(key, code):
        claimed = original(key, code)
        clock.current += timedelta(seconds=11)
        return claimed

    monkeypatch.setattr(record, "claim_event_rerun_stage", delayed_claim)

    def play(owner, stage, settings, prepare, claim, complete):
        assert not claim()
        return "defer"

    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert not runner.run_event_rerun(owner, lambda: owner.deadline)
    assert record.load_event_rerun_progress("act46sre:100") == {}


def test_next_opening_runs_all_ordinary_stages_with_previous_opening_complete(
    scheduler, monkeypatch
):
    owner, _ = scheduler

    def play(owner, stage, settings, prepare, claim, complete):
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
