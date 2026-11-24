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
from arknights_mower.utils.maa_backup import VerifiedAsst
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


def test_resources_offer_timed_ordinary_battles_and_ex8_raid():
    choice = event()
    assert choice["key"] == "act46sre:100"
    assert [item["code"] for item in choice["stages"]] == ["OS-1", "OS-10"]
    assert choice["raid"]["code"] == "OS-EX-8 突袭"
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
        Conf(
            maa_rg_enable=1,
            maa_long_task_type="garrison",
            maa_long_task_weekly_windows=[
                {
                    "start": "11:00",
                    "end": "13:00",
                    "weekdays": [1],
                    "task_type": "event_rerun",
                }
            ],
            event_rerun={
                "event_key": "act46sre:100",
                "stages": ["OS-10", "OS-1", "OS-1"],
            },
        ),
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
    monkeypatch.setattr(
        runner, "long_task_deadline", lambda owner, cutoff: owner.deadline
    )
    return owner, Clock


def test_budget_is_checked_before_each_claim_and_completion_survives_restart(
    scheduler, monkeypatch
):
    owner, clock = scheduler
    play = MagicMock()
    monkeypatch.setattr(runner, "_play_ordinary", play)
    owner.deadline -= timedelta(seconds=11)
    assert not runner.run_event_rerun(owner)
    play.assert_not_called()

    owner.deadline += timedelta(seconds=11)

    def fight(owner, stage, prepare, claim, complete):
        assert prepare() > 0
        assert claim()
        clock.current += timedelta(minutes=5)
        complete()
        return "completed"

    play.side_effect = fight
    assert runner.run_event_rerun(owner)
    assert play.call_count == 1
    assert record.load_event_rerun_progress("act46sre:100") == {"OS-1": "completed"}

    next_owner = SimpleNamespace(tasks=[], deadline=clock.now() + timedelta(minutes=5))
    assert runner.run_event_rerun(next_owner)
    assert [call.args[1]["code"] for call in play.call_args_list] == ["OS-1", "OS-10"]
    assert not runner.run_event_rerun(next_owner)


def test_navigation_cannot_spend_the_battle_reserve(scheduler, monkeypatch):
    owner, clock = scheduler

    def prepare_stage(owner, stage, prepare, claim, complete):
        assert prepare() > 0
        clock.current += timedelta(seconds=11)
        assert not claim()
        return "defer"

    play = MagicMock(side_effect=prepare_stage)
    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert not runner.run_event_rerun(owner)
    play.assert_called_once()
    assert record.load_event_rerun_progress("act46sre:100") == {}
    assert not owner.event_rerun_blocked[1]


def test_unchanged_failed_preparation_yields_to_other_selected_stages(
    scheduler, monkeypatch
):
    owner, clock = scheduler
    order = []

    def play(owner, stage, prepare, claim, complete):
        order.append(stage["code"])
        if stage["code"] == "OS-1":
            return "blocked"
        assert claim()
        complete()
        return "completed"

    monkeypatch.setattr(runner, "_play_ordinary", play)
    assert runner.run_event_rerun(owner)
    assert not runner.run_event_rerun(owner)
    assert order == ["OS-1", "OS-10"]
    assert record.load_event_rerun_progress("act46sre:100") == {"OS-10": "completed"}
    assert owner.deadline == clock.now() + timedelta(minutes=4, seconds=10)


def test_ordinary_keeps_device_io_after_deadline_during_battle(scheduler, monkeypatch):
    owner, clock = scheduler
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
        assert io_timeout(60) <= 10
        assert kwargs["before_single_battle"]()
        clock.current += timedelta(minutes=5)
        assert io_timeout(60) == 60
        kwargs["on_single_battle_settlement"]()
        return {"executed_runs": 1}

    operation.run.side_effect = run
    monkeypatch.setattr(runner, "OperationSolver", lambda *_: operation)
    assert runner.run_event_rerun(owner)
    assert operation.run.call_count == 1
    assert record.load_event_rerun_progress("act46sre:100") == {"OS-1": "completed"}


def test_raid_auto_formation_stays_running_past_task_deadline(
    scheduler, monkeypatch, files
):
    owner, clock = scheduler
    config.conf.event_rerun.stages = []
    config.conf.event_rerun.raid_enabled = True
    config.conf.event_rerun.script_id = copilot.upload(
        {**copilot.SCRIPT, "stage_name": "act46side_ex08"}
    )["id"]
    navigator = MagicMock()
    navigator.run.side_effect = lambda _: owner.MAA is maa
    monkeypatch.setattr(runner, "NavigationSolver", lambda *_: navigator)
    owner.scene_graph_navigation = MagicMock()
    owner.scene = lambda: Scene.OPERATOR_CHOOSE_LEVEL
    owner._maa_refresh_deadline = lambda: None
    owner.release_maa = MagicMock()
    maa = MagicMock()
    maa.append_task.return_value = 7
    checked = []

    def init(on_task_event):
        owner.MAA = maa

        def running():
            checked.append(clock.now())
            if len(checked) == 1:
                clock.current += timedelta(minutes=5)
                return True
            other_task = {"taskid": 8, "taskchain": "Copilot"}
            on_task_event(10002, other_task)
            assert record.load_event_rerun_progress("act46sre:100") == {
                "OS-EX-8 突袭": "attempted"
            }
            on_task_event(10002, {**other_task, "taskid": 7})
            return False

        maa.running.side_effect = running

    owner.initialize_maa = init
    monkeypatch.setattr(runner, "csleep", lambda _: None)
    assert runner.run_event_rerun(owner)
    task, params = maa.append_task.call_args.args
    assert task == "Copilot" and params["formation"]
    assert len(params["copilot_list"]) == 1
    assert params["copilot_list"][0]["is_raid"]
    assert params["copilot_list"][0]["nav_name_override"] == "OS-EX-8"
    assert checked[1] > owner.deadline
    maa.start.assert_called_once()
    maa.stop.assert_not_called()
    assert record.load_event_rerun_progress("act46sre:100") == {
        "OS-EX-8 突袭": "completed"
    }
    assert not runner.run_event_rerun(owner)


@pytest.mark.parametrize("rejected", [True, False])
def test_raid_start_failure_releases_only_confirmed_rejection(
    scheduler, monkeypatch, files, rejected
):
    owner, _ = scheduler
    settings = config.conf.event_rerun
    settings.stages = []
    settings.raid_enabled = True
    script = {**copilot.SCRIPT, "stage_name": "act46side_ex08"}
    settings.script_id = copilot.upload(script)["id"]
    monkeypatch.setattr(runner, "NavigationSolver", lambda *_: MagicMock())
    owner.scene_graph_navigation = MagicMock()
    owner.scene = lambda: Scene.OPERATOR_CHOOSE_LEVEL
    owner._maa_refresh_deadline = lambda: None
    owner.release_maa = MagicMock()
    owner.MAA = MagicMock()
    owner.MAA.append_task.return_value = 7
    owner.MAA.running.return_value = False
    owner.initialize_maa = MagicMock()

    verified = object.__new__(VerifiedAsst)
    verified._asst = MagicMock()
    verified._outcome = MagicMock()
    verified._asst.start.return_value = False
    if not rejected:
        verified._asst.start.side_effect = TimeoutError("启动响应超时")
    owner.MAA.start.side_effect = verified.start

    assert runner.run_event_rerun(owner) is not rejected
    assert not runner.run_event_rerun(owner)
    owner.MAA.start.assert_called_once()
    raid_code = "OS-EX-8 突袭"
    progress = record.load_event_rerun_progress("act46sre:100")
    if rejected:
        assert progress == {}
        owner.MAA.stop.assert_called_once()
        settings.script_id = copilot.upload({**script, "doc": {"title": "替换作业"}})[
            "id"
        ]
        verified._asst.start.return_value = True
        assert runner.run_event_rerun(owner)
        assert record.load_event_rerun_progress("act46sre:100") == {
            raid_code: "attempted"
        }
    else:
        assert progress == {raid_code: "attempted"}
        owner.MAA.stop.assert_called_once()


def test_raid_does_not_dispatch_a_script_for_another_stage(files):
    script_id = copilot.upload({**copilot.SCRIPT, "stage_name": "OS-EX-7"})["id"]
    with pytest.raises(ValueError, match="OS-EX-8"):
        runner._raid_params(event()["raid"], script_id)


def test_unconfirmed_attempt_stays_claimed_after_new_scheduler(scheduler, monkeypatch):
    owner, clock = scheduler

    def play(owner, stage, prepare, claim, complete):
        assert claim()
        return "defer"

    monkeypatch.setattr(runner, "_play_ordinary", play)
    config.conf.event_rerun.stages = ["OS-1"]
    assert runner.run_event_rerun(owner)
    assert not runner.run_event_rerun(
        SimpleNamespace(tasks=[], deadline=owner.deadline)
    )
    assert record.load_event_rerun_progress("act46sre:100") == {"OS-1": "attempted"}


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


@pytest.mark.parametrize(
    ("scenario", "expected_status"),
    [
        ("active", 409),
        ("no_current_rerun", 200),
        ("previous_opening", 200),
        ("no_raid", 200),
        ("raid_ended", 200),
        ("raid_disabled", 200),
        ("resources_unreadable", 503),
    ],
)
def test_script_deletion_protects_only_current_raid(
    client, monkeypatch, files, scenario, expected_status
):
    script_id = copilot.upload({**copilot.SCRIPT, "stage_name": "OS-EX-8"})["id"]
    settings = config.conf.event_rerun
    current = event()
    settings.event_key = current["key"]
    settings.script_id = script_id
    settings.raid_enabled = scenario != "raid_disabled"
    if scenario == "no_current_rerun":
        current = None
    elif scenario == "previous_opening":
        current["key"] = "act46sre:200"
    elif scenario == "no_raid":
        current["raid"] = None
    elif scenario == "raid_ended":
        current["raid"]["end_ts"] = current["now"]
    error = OSError("资源不可读") if scenario == "resources_unreadable" else None
    read = MagicMock(return_value=current, side_effect=error)
    monkeypatch.setattr(event_rerun, "current_rerun", read)

    response = client.delete(
        f"/maa-copilot/{script_id}", headers={"token": "copilot-test-token"}
    )

    assert response.status_code == expected_status
    assert (files / f"{script_id}.json").exists() is (expected_status != 200)
    assert read.call_count == int(settings.raid_enabled)


@pytest.mark.parametrize("token", [None, "invalid"])
def test_unauthorized_delete_does_not_inspect_rerun(client, monkeypatch, token):
    script_id = "a" * 64
    config.conf.event_rerun.raid_enabled = True
    config.conf.event_rerun.script_id = script_id
    read = MagicMock()
    monkeypatch.setattr(event_rerun, "current_rerun", read)
    headers = {} if token is None else {"token": token}

    assert (
        client.delete(f"/maa-copilot/{script_id}", headers=headers).status_code == 403
    )
    read.assert_not_called()
