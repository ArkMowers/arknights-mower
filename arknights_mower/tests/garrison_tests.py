"""个人极速模拟的实测画面、进度与对局保留检查。"""

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from arknights_mower.solvers import record
from arknights_mower.solvers.garrison import model, runner, solver
from arknights_mower.solvers.garrison.vision import (
    Frame,
    Text,
    classify,
)
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

FIXTURES = Path(__file__).parent / "fixtures" / "garrison"


def frame(name):
    texts = [Text(**t) for t in json.loads((FIXTURES / f"{name}.json").read_text())]
    screen, quick = classify(texts)
    return Frame(np.zeros((1080, 1920, 3), np.uint8), texts, screen, quick)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("lobby", "lobby"),
        ("mode", "mode"),
        ("info", "info"),
        ("info-popup", "info"),
        ("prep", "prep"),
        ("leave", "unknown"),
        ("leave-prep", "leave"),
        ("left", "lobby"),
        ("terminal-tab", "terminal-garrison"),
        ("post-info", "squad"),
    ],
)
def test_observed_screens(name, expected):
    assert frame(name).screen == expected


def test_three_and_six_win_targets_and_explicit_recheck():
    conf = Conf(maa_long_task_type="garrison", maa_rg_enable=1)
    p = model.prepare_progress(conf, {})
    for strategy in model.catalogue()["strategies"]:
        model.record_wins(p, strategy["id"], 3)
    assert model.status(conf, p)["completed"]
    conf.garrison.target_wins = 6
    assert not model.status(conf, p)["completed"]
    p["match"] = {"stage": "act3autochess_m01", "round": 4}
    conf.garrison.run_id = "recheck"
    fresh = model.prepare_progress(conf, p)
    assert fresh["wins"] == {}
    assert fresh["match"] == p["match"]


def test_device_binding_changes_but_capture_settings_do_not_change_identity():
    conf = Conf()
    original = model.identity_key(conf)
    conf.device.recovery_timeout += 10
    assert model.identity_key(conf) == original
    conf.device.instance_id = "different"
    assert model.identity_key(conf) != original


def test_progress_round_trip_and_unknown_win_rejected(income_db):
    p = {"wins": {}, "match": {"stage": "act3autochess_m01", "round": 4}}
    record.save_garrison_progress(p)
    assert record.load_garrison_progress() == p
    with pytest.raises(model.GarrisonError):
        model.record_wins(p, model.catalogue()["strategies"][0]["id"], None)
    assert p["wins"] == {}


def test_saved_match_does_not_start_another_match():
    device = Mock()
    s = solver.GarrisonSolver(device, Mock(), {"match": {"round": 3}}, Mock())
    with pytest.raises(model.GarrisonError):
        s.start_or_resume(frame("lobby"))
    device.tap.assert_not_called()


def test_resume_clicks_reconnect_and_preserves_progress():
    p = {"match": {"round": 3, "stage": "act3autochess_m01"}}
    s = solver.GarrisonSolver(Mock(), Mock(), p, Mock())
    s.click = Mock()
    s.wait = Mock(return_value=frame("prep"))
    before = copy.deepcopy(p)
    s.start_or_resume(frame("left"))
    s.click.assert_called_once_with(frame("left").find("断线重连").center)
    assert p == before


def test_failure_blocks_unchanged_dispatch_and_retains_other_work(
    income_db, monkeypatch
):
    conf = Conf(maa_long_task_type="garrison", maa_rg_enable=1)
    monkeypatch.setattr(runner.config, "conf", conf)
    order = SchedulerTask(
        datetime.now() + timedelta(hours=1), task_type=TaskTypes.RUN_ORDER
    )
    scheduler = SimpleNamespace(
        device=Mock(), recog=Mock(), tasks=[order], task=None, op_data=None
    )
    original = (id(order), order.time, order.plan)
    run = Mock(side_effect=model.GarrisonError("未识别棋子"))
    monkeypatch.setattr(runner.GarrisonSolver, "run", run)
    monkeypatch.setattr(runner.GarrisonSolver, "leave_match", Mock())
    assert runner.run_garrison(scheduler)
    assert not runner.run_garrison(scheduler)
    assert run.call_count == 1
    assert (id(order), order.time, order.plan) == original
    assert scheduler.tasks == [order]
    conf.garrison.run_id = "retry"
    assert runner.run_garrison(scheduler)
    assert run.call_count == 2


def test_real_deadline_preempts_before_input(monkeypatch):
    s = solver.GarrisonSolver(
        Mock(),
        Mock(),
        {},
        Mock(),
        deadline=lambda: datetime.now() + timedelta(seconds=20),
    )
    with pytest.raises(solver.GarrisonYield):
        s.click((10, 10))
    s.device.tap.assert_not_called()


@pytest.mark.parametrize(
    ("texts", "wins"),
    [
        (["已通过模拟", "3次"], 3),
        (["已通过模拟⑥次"], 6),
        (["已通过模拟"], None),
        ([], 0),
    ],
)
def test_counts_require_open_strategy_panel(texts, wins):
    from arknights_mower.solvers.garrison.upstream import strategy_panel

    items = [(1500, 250, t) for t in texts]
    assert strategy_panel(items) is None
    assert strategy_panel(items + [(1500, 460, "初始生命值")]) == wins


def test_settlement_yields_before_starting_another_match():
    s = solver.GarrisonSolver(
        Mock(),
        Mock(),
        {"match": {"phase": "active"}},
        Mock(),
        deadline=lambda: datetime.now() + timedelta(minutes=10, seconds=29),
    )
    s._quick_confirmed = True
    result = Frame(None, [Text("返回主页", 100, 200, 50, 50)], "result", False)
    s.wait = Mock(return_value=frame("lobby"))
    s.sleep = Mock()
    s.play(Mock(), result)
    assert s.progress == {"match": None, "attempts": 1}
    s.device.tap.assert_called_once_with((125, 225))


def test_pinned_resources_reject_mismatch_before_execution(tmp_path, monkeypatch):
    from io import BytesIO

    from arknights_mower.solvers.garrison import upstream

    monkeypatch.setattr(upstream, "get_path", lambda *a, **kw: tmp_path)
    path = tmp_path / "garrison_farm.py"
    path.write_bytes(b"invalid local source")
    monkeypatch.setattr(
        upstream, "urlopen", lambda *a, **kw: BytesIO(b"invalid download")
    )
    with pytest.raises(model.GarrisonError, match="校验失败"):
        upstream.read_resource(path.name, lambda: 3)
    assert path.read_bytes() == b"invalid local source"


def test_interruption_releases_held_touch_before_closing_game(monkeypatch):
    events = []
    s = solver.GarrisonSolver(Mock(), Mock(), {}, Mock(), vision=Mock())
    session = Mock()
    session.release.side_effect = lambda: events.append("release")
    s.device.exit_after_task_stop.side_effect = lambda: events.append("exit")
    s.recog.reset_after_external_control.side_effect = lambda: events.append("reset")
    monkeypatch.setattr(solver, "FarmSession", lambda owner: session)
    s.enter = Mock(return_value=frame("prep"))
    s.play = Mock(side_effect=solver.GarrisonYield())
    s.run()
    assert events == ["release", "exit", "reset"]


def test_terminal_shows_active_simulation_before_reconnect():
    texts = [Text("模拟中", 1100, 600, 60, 40), Text("卫成协议", 240, 460, 120, 50)]
    assert classify(texts)[0] == "terminal-garrison"


def test_lobby_waits_for_reconnect_button_during_transition():
    s = solver.GarrisonSolver(Mock(), Mock(), {"match": {"phase": "starting"}}, Mock())
    loading = frame("left")
    loading.texts = [t for t in loading.texts if t.text != "断线重连"]
    ready = frame("left")
    settled = frame("prep")
    s.wait = Mock(side_effect=[ready, settled])
    s.click = Mock()
    assert s.start_or_resume(loading) is settled
    s.click.assert_called_once_with(ready.find("断线重连").center)


@pytest.mark.parametrize(
    ("target", "observed", "selected"), [(3, 3, False), (6, 3, True)]
)
def test_choose_strategy_from_count_even_with_unreadable_name(
    target, observed, selected
):
    s = solver.GarrisonSolver(Mock(), Mock(), {"wins": {}}, Mock(), target_wins=target)
    current = Frame(None, [Text("确认选择", 1650, 920, 50, 40)], "strategy", True)
    s.click = Mock()
    s.capture = Mock(return_value=current)
    s.wait = Mock(return_value=frame("prep"))
    game = Mock(GRID_Y=[400], GRID_X=[700], GRID_TOP=250, GRID_BOTTOM=1050)
    game.ocr.return_value = [
        (1600, 220, f"已通过模拟{observed}次"),
        (1600, 520, "初始生命值"),
    ]
    game.detect_rows.return_value = []
    if selected:
        assert s.choose_strategy(game).screen == "prep"
        assert s.click.call_args.args == ((1675, 940),)
    else:
        with pytest.raises(model.GarrisonError, match="待核对"):
            s.choose_strategy(game)
        s.click.assert_called_once_with((1500, 580))
    assert s.progress["wins"] == {}


@pytest.mark.parametrize("target", [3, 6])
def test_last_confirmed_medal_stops_scan_and_future_dispatch(
    target, income_db, monkeypatch
):
    conf = Conf(maa_long_task_type="garrison", maa_rg_enable=1)
    conf.garrison.target_wins = target
    monkeypatch.setattr(runner.config, "conf", conf)
    progress = model.prepare_progress(conf, {})
    strategies = model.catalogue()["strategies"]
    progress["wins"] = {s["id"]: target for s in strategies[:-1]}
    s = solver.GarrisonSolver(
        Mock(), Mock(), progress, record.save_garrison_progress, target_wins=target
    )
    s.click = Mock()
    s.capture = Mock(return_value=frame("prep"))
    s.capture.return_value.screen = "strategy"
    game = Mock(GRID_Y=[400], GRID_X=[700, 900], GRID_TOP=250, GRID_BOTTOM=1050)
    game.ocr.return_value = [
        (1600, 250, f"已通过模拟{target}次"),
        (1600, 500, "初始生命值"),
        (1600, 565, strategies[-1]["name"]),
    ]
    assert s.choose_strategy(game) is None
    game.tap.assert_called_once_with(700, 400, 0.7)
    game.scroll_grid.assert_not_called()
    assert model.status(conf, record.load_garrison_progress())["completed"]

    worker = Mock()
    monkeypatch.setattr(runner, "GarrisonSolver", worker)
    scheduler = SimpleNamespace(
        tasks=[], task=None, op_data=None, device=Mock(), recog=Mock()
    )
    for _ in range(2):
        assert not runner.run_garrison(scheduler)
    worker.assert_not_called()
    if target == 3:
        conf.garrison.target_wins = 6
        assert runner.run_garrison(scheduler)
        worker.return_value.run.assert_called_once()


@pytest.mark.parametrize(
    ("seconds", "saved_match", "admitted"),
    [(629, False, False), (630, False, True), (540, True, True), (539, True, False)],
)
def test_dispatch_reserves_a_full_new_match(
    seconds, saved_match, admitted, income_db, monkeypatch
):
    conf = Conf(maa_long_task_type="garrison", maa_rg_enable=1)
    monkeypatch.setattr(runner.config, "conf", conf)
    now = datetime.now()
    monkeypatch.setattr(runner, "datetime", Mock(now=lambda: now))
    progress = model.prepare_progress(conf, {})
    if saved_match:
        progress["match"] = {"phase": "active"}
    record.save_garrison_progress(progress)
    order = SchedulerTask(
        now + timedelta(seconds=seconds), task_type=TaskTypes.RUN_ORDER
    )
    scheduler = SimpleNamespace(
        tasks=[order], task=None, op_data=None, device=Mock(), recog=Mock()
    )
    worker = Mock()
    monkeypatch.setattr(runner, "GarrisonSolver", worker)
    assert runner.run_garrison(scheduler) is admitted
    assert worker.called is admitted


def test_match_budget_rechecked_after_navigation_before_saving_new_match():
    s = solver.GarrisonSolver(Mock(), Mock(), {}, Mock())
    s.remaining = Mock(side_effect=[600, 599])
    s.text_click = Mock()
    s.wait = Mock(return_value=frame("mode"))
    with pytest.raises(solver.GarrisonYield):
        s.start_or_resume(frame("lobby"))
    assert [call.args[1] for call in s.text_click.call_args_list] == ["^极速模拟$"]
    s.save.assert_not_called()
    assert "match" not in s.progress
