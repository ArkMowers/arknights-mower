"""个人极速模拟的实测画面、进度与对局保留检查。"""

import copy
import json
from dataclasses import replace
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
    image = np.zeros((1080, 1920, 3), np.uint8)
    if name in {"lobby", "left"}:
        label = next(t for t in texts if t.text == "个人模拟")
        image[label.y : label.y + label.height, label.x : label.x + label.width] = 205
        image[label.y : label.y + label.height : 5, label.x : label.x + label.width] = (
            24
        )
    return Frame(image, texts, screen, quick)


def replay_unchanged_lobby(monkeypatch, worker, lobby):
    elapsed = 0

    def advance(seconds):
        nonlocal elapsed
        elapsed += seconds

    monkeypatch.setattr(solver.time, "monotonic", lambda: elapsed)
    worker.capture = Mock(return_value=lobby)
    worker.sleep = advance


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


@pytest.mark.parametrize(
    "saved",
    [{"round": 3}, {"phase": "active", "round": 3}, {"phase": "starting", "round": 3}],
)
def test_saved_match_does_not_start_another_match(saved, monkeypatch):
    device = Mock()
    s = solver.GarrisonSolver(device, Mock(), {"match": saved}, Mock())
    lobby = frame("lobby")
    replay_unchanged_lobby(monkeypatch, s, lobby)
    with pytest.raises(model.GarrisonError):
        s.start_or_resume(lobby)
    assert s.capture.call_count > 1
    device.tap.assert_not_called()


@pytest.mark.parametrize("phase", ["active", "starting"])
def test_saved_phase_uses_personal_lobby_and_preserves_counts(phase):
    p = {"match": {"phase": phase}, "wins": {"band_amiya": 3}, "matches_played": 2}
    initial = copy.deepcopy(p)
    lobby, mode, info = frame("lobby"), frame("mode"), frame("info")
    s = solver.GarrisonSolver(Mock(), Mock(), p, Mock(), vision=Mock())
    s.vision.frame.side_effect = ([lobby] if phase == "active" else []) + [mode, info]
    s.remaining = Mock(return_value=720)
    s.click = Mock()
    assert s.start_or_resume(lobby) is info
    assert [c.args[0] for c in s.click.call_args_list] == [
        lobby.find("^极速模拟$").center,
        mode.find("^开始模拟$").center,
    ]
    assert p == {**initial, "match": {"phase": "active"}}


def test_reconnect_takes_priority_on_active_lobby_recheck():
    lobby, reconnect, prep = frame("lobby"), frame("left"), frame("prep")
    worker = solver.GarrisonSolver(
        Mock(), Mock(), {"match": {"phase": "active"}}, Mock()
    )
    worker.capture = Mock(side_effect=[reconnect, prep])
    worker.click = Mock()
    assert worker.start_or_resume(lobby) is prep
    worker.click.assert_called_once_with(reconnect.find("断线重连").center)
    worker.save.assert_not_called()


@pytest.mark.parametrize(
    "observation", ["missing_quick", "missing_solo", "abandon", "ambiguous_selection"]
)
def test_uncertain_personal_lobby_preserves_unconfirmed_start(observation, monkeypatch):
    lobby = frame("lobby")
    if observation == "missing_quick":
        lobby.texts.remove(lobby.find("^极速模拟$"))
    elif observation == "missing_solo":
        lobby.texts.remove(lobby.find("^独立模拟$"))
    elif observation == "abandon":
        lobby.texts.append(Text("放弃模拟", 1120, 989, 84, 40))
    else:
        lobby.image[:] = 30
    p = {"match": {"phase": "starting"}}
    s = solver.GarrisonSolver(Mock(), Mock(), p, Mock())
    replay_unchanged_lobby(monkeypatch, s, lobby)
    with pytest.raises(model.GarrisonError):
        s.start_or_resume(lobby)
    assert p == {"match": {"phase": "starting"}}
    s.device.tap.assert_not_called()
    s.save.assert_not_called()


@pytest.mark.parametrize(
    "match", [{"round": 3, "stage": "act3autochess_m01"}, {"phase": "starting"}]
)
def test_resume_clicks_reconnect_and_preserves_progress(match):
    p = {"match": match}
    s = solver.GarrisonSolver(Mock(), Mock(), p, Mock())
    s.click = Mock()
    s.wait = Mock(return_value=frame("prep"))
    before = copy.deepcopy(p)
    s.start_or_resume(frame("left"))
    s.click.assert_called_once_with(frame("left").find("断线重连").center)
    assert p == before


@pytest.mark.parametrize(("entry", "target"), [("left", "prep"), ("mode", "info")])
def test_slow_match_entry_waits_for_the_first_playable_frame(
    monkeypatch, entry, target
):
    lobby = frame(entry)
    ready = frame(target)
    loading = Frame(None, [], "unknown", False)
    worker = solver.GarrisonSolver(Mock(), Mock(), {}, Mock())
    replay_unchanged_lobby(monkeypatch, worker, loading)
    worker.capture.side_effect = lambda: (
        ready if solver.time.monotonic() >= 42 else loading
    )
    assert worker.start_or_resume(lobby) is ready
    worker.device.tap.assert_called_once()
    assert 42 <= solver.time.monotonic() < 43


@pytest.mark.parametrize(
    ("budget", "error"), [(12, solver.GarrisonYield), (70, model.GarrisonError)]
)
def test_reconnect_loading_ends_at_deadline_or_timeout(monkeypatch, budget, error):
    progress = {"match": {"round": 3}}
    worker = solver.GarrisonSolver(Mock(), Mock(), progress, Mock())
    loading = Frame(None, [], "unknown", False)
    replay_unchanged_lobby(monkeypatch, worker, loading)
    worker._end = budget
    with pytest.raises(error):
        worker.start_or_resume(frame("left"))
    assert min(budget, 60) <= solver.time.monotonic() < min(budget, 60) + 1
    assert progress == {"match": {"round": 3}}
    worker.device.tap.assert_called_once()


def test_slow_event_entry_reaches_lobby(monkeypatch):
    terminal, lobby = frame("terminal-tab"), frame("lobby")
    loading = Frame(None, [], "unknown", False)
    worker = solver.GarrisonSolver(Mock(), Mock(), {}, Mock())
    replay_unchanged_lobby(monkeypatch, worker, loading)
    worker.capture.side_effect = lambda: (
        lobby if solver.time.monotonic() >= 42 else loading
    )
    nav = solver.GarrisonNavigation(worker.device, worker.recog)
    assert nav.run(lambda: terminal, worker.click, worker.wait) is lobby
    worker.device.tap.assert_called_once_with(terminal.find("模拟开放中").center)


def test_slow_battle_replay_and_return_to_lobby(monkeypatch):
    confirm = Text("确认", 930, 700, 93, 56)
    replay = Frame(None, [confirm], "battle-timeout", True)
    result = Frame(None, [Text("返回主页", 100, 200, 50, 50)], "result", True)
    loading, lobby = Frame(None, [], "unknown", False), frame("lobby")
    worker = solver.GarrisonSolver(Mock(), Mock(), {"match": {"round": 1}}, Mock())
    worker._quick_confirmed = True
    replay_unchanged_lobby(monkeypatch, worker, loading)
    worker._end = 120

    def capture():
        elapsed = solver.time.monotonic()
        if elapsed >= 84:
            return lobby
        if elapsed >= 42 and not worker.progress.get("settlement_counted"):
            return result
        return loading

    worker.capture.side_effect = capture
    monkeypatch.setattr(solver, "save_screenshot_frame", Mock())
    worker.play(Mock(), replay)
    assert [c.args[0] for c in worker.device.tap.call_args_list] == [
        confirm.center,
        result.find("返回主页").center,
    ]
    assert worker.progress["attempts"] == 1
    assert 84 <= solver.time.monotonic() < 85


@pytest.mark.parametrize("repeat_mode", [False, True])
def test_reconnect_returns_from_difficulty_to_recheck_personal_lobby(repeat_mode):
    lobby, mode, prep = frame("left"), frame("mode"), frame("prep")
    worker = solver.GarrisonSolver(Mock(), Mock(), {"match": {"round": 3}}, Mock())
    worker.click = Mock()
    worker.capture = Mock(side_effect=[mode, lobby, mode if repeat_mode else prep])
    if repeat_mode:
        with pytest.raises(model.GarrisonError, match="再次进入难度选择页"):
            worker.start_or_resume(lobby)
    else:
        assert worker.start_or_resume(lobby) is prep
    reconnect = lobby.find("断线重连").center
    assert [call.args[0] for call in worker.click.call_args_list] == [
        reconnect,
        (65, 58),
        reconnect,
    ]
    assert worker.progress == {"match": {"round": 3}}
    worker.save.assert_not_called()


def test_reconnect_difficulty_returns_to_new_lobby_with_short_budget():
    lobby, mode, fresh = frame("left"), frame("mode"), frame("lobby")
    worker = solver.GarrisonSolver(
        Mock(), Mock(), {"match": {"phase": "active"}}, Mock()
    )
    worker.remaining = Mock(return_value=600)
    worker.click = Mock()
    worker.capture = Mock(side_effect=[mode, fresh, fresh])
    with pytest.raises(solver.GarrisonYield):
        worker.start_or_resume(lobby)
    assert [call.args[0] for call in worker.click.call_args_list] == [
        lobby.find("断线重连").center,
        (65, 58),
    ]
    worker.save.assert_not_called()


@pytest.mark.parametrize("highlight", ["joint", "both", "neither", "missing_label"])
def test_reconnect_requires_positive_personal_selection(highlight, monkeypatch):
    lobby = frame("left")
    label = lobby.find("^个人模拟$")
    x, y, w, h = label.x, label.y, label.width, label.height
    if highlight in {"joint", "neither"}:
        lobby.image[y : y + h, x : x + w] = 30
    if highlight in {"joint", "both"}:
        lobby.image[y : y + h, x + 2 * w : x + 3 * w] = 205
    if highlight == "missing_label":
        lobby.texts.remove(label)
    progress = {"match": {"round": 3}}
    s = solver.GarrisonSolver(Mock(), Mock(), progress, Mock())
    replay_unchanged_lobby(monkeypatch, s, lobby)
    with pytest.raises(model.GarrisonError, match="复核后仍未确认大厅模式或对局入口"):
        s.start_or_resume(lobby)
    s.device.tap.assert_not_called()
    s.save.assert_not_called()
    assert progress == {"match": {"round": 3}}


@pytest.mark.parametrize("resume", ["next_order", "manual_recheck", "next_period"])
def test_failure_yields_until_a_new_window_and_retains_other_work(
    income_db, monkeypatch, resume
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
    assert (
        model.status(conf, record.load_garrison_progress())["message"] == "未识别棋子"
    )
    if resume == "next_order":
        scheduler.tasks = [
            SchedulerTask(
                order.time + timedelta(hours=1), task_type=TaskTypes.RUN_ORDER
            )
        ]
    elif resume == "next_period":
        monkeypatch.setattr(
            runner,
            "long_task_schedule",
            lambda *_: ("garrison", order.time, order.time),
        )
    else:
        conf.garrison.run_id = "retry"
    assert runner.run_garrison(scheduler)
    assert run.call_count == 2


@pytest.mark.parametrize("stop_worker", [True, False])
def test_stop_and_legacy_failed_match_resume_without_reset(
    income_db, monkeypatch, stop_worker
):
    conf = Conf(maa_rg_enable=1, maa_long_task_type="garrison")
    monkeypatch.setattr(runner.config, "conf", conf)
    progress = model.prepare_progress(conf, {})
    progress.update(
        failed=True,
        theme_restore_blocked=True,
        error="旧错误",
        match={"phase": "active"},
        wins={"example": 2},
        matches_played=4,
        original_theme="乌萨斯齐心团",
    )
    record.save_garrison_progress(progress)
    order = SchedulerTask(
        datetime.now() + timedelta(hours=1), task_type=TaskTypes.RUN_ORDER
    )
    scheduler = SimpleNamespace(
        device=Mock(), recog=Mock(), tasks=[order], task=None, op_data=None
    )

    def interrupt(owner):
        if stop_worker:
            raise solver.MowerExit
        runner.config.stop_maa.set()

    monkeypatch.setattr(runner.GarrisonSolver, "run", interrupt)
    try:
        if stop_worker:
            with pytest.raises(solver.MowerExit):
                runner.run_garrison(scheduler)
        else:
            assert runner.run_garrison(scheduler)
        assert not runner.run_garrison(scheduler)
        if stop_worker:
            scheduler = SimpleNamespace(
                device=Mock(), recog=Mock(), tasks=[order], task=None, op_data=None
            )
        else:
            scheduler.tasks.clear()
        resumed = Mock()
        monkeypatch.setattr(runner.GarrisonSolver, "run", resumed)
        assert runner.run_garrison(scheduler)
        resumed.assert_called_once()
        saved = record.load_garrison_progress()
        assert "original_theme" not in saved
        for field in ("match", "wins", "matches_played"):
            assert saved[field] == progress[field]
        assert not saved.get("failed") and not saved.get("theme_restore_blocked")
        assert not saved["error"]
    finally:
        runner.config.stop_maa.clear()


@pytest.mark.parametrize("interrupted", [False, True])
def test_squad_intro_can_outlast_unknown_screen_timeout(monkeypatch, interrupted):
    now = 0
    monkeypatch.setattr(solver.time, "monotonic", lambda: now)
    s = solver.GarrisonSolver(
        Mock(), Mock(), {"match": {"phase": "starting"}}, Mock(), match_limit=1
    )
    s._quick_confirmed = True
    outcome = Frame(None, [Text("返回主页", 0, 0, 20, 20)], "result", False)

    def capture():
        if interrupted and now >= 7:
            raise solver.GarrisonYield
        if now < 23:
            return Frame(None, [], "unknown", False)
        return frame("prep") if now == 23 else outcome

    def advance(seconds):
        nonlocal now
        now += 1

    s.capture = capture
    s.sleep = advance
    s.click = Mock()
    game = Mock()
    game.prep_phase.side_effect = lambda *_: advance(1)
    game.Board.return_value.prep_done = False
    monkeypatch.setattr(solver, "save_screenshot_frame", Mock())
    if interrupted:
        with pytest.raises(solver.GarrisonYield):
            s.play(game, frame("post-info"))
        s.click.assert_not_called()
        assert s.progress["match"] == {"phase": "starting"}
    else:
        s.play(game, frame("post-info"))
        game.prep_phase.assert_called_once()
        s.click.assert_called_once_with(outcome.find("返回主页").center)
    game.pick_squad.assert_called_once()


@pytest.mark.parametrize("outcome", ["settles", "deadline", "timeout"])
def test_battle_loading_waits_for_confirmed_settlement(monkeypatch, outcome):
    loading = Frame(None, [], "unknown", False)
    battle = Frame(None, [], "battle", True)
    result = Frame(None, [Text("返回主页", 0, 0, 80, 40)], "result", False)
    worker = solver.GarrisonSolver(
        Mock(), Mock(), {"match": {"phase": "active"}}, Mock(), match_limit=1
    )
    worker._quick_confirmed = True
    replay_unchanged_lobby(monkeypatch, worker, loading)
    worker._end = 10 if outcome == "deadline" else 100
    worker.capture.side_effect = lambda: (
        result if outcome == "settles" and solver.time.monotonic() >= 24 else loading
    )
    archived = Mock()
    monkeypatch.setattr(solver, "save_screenshot_frame", archived)
    if outcome == "settles":
        worker.play(Mock(), battle)
        archived.assert_called_once_with(result.image, "garrison_result")
        worker.device.tap.assert_called_once_with(result.find("返回主页").center)
        assert worker.progress["matches_played"] == 1
    else:
        with pytest.raises(
            solver.GarrisonYield if outcome == "deadline" else model.GarrisonError
        ):
            worker.play(Mock(), battle)
        assert worker.progress == {"match": {"phase": "active"}}
        archived.assert_not_called()
        worker.device.tap.assert_not_called()


def test_real_deadline_preempts_before_input(monkeypatch):
    now = datetime.now()
    clock = Mock()
    clock.now.return_value = now
    monkeypatch.setattr(solver, "datetime", clock)
    s = solver.GarrisonSolver(
        Mock(),
        Mock(),
        {},
        Mock(),
        deadline=lambda: now + timedelta(minutes=12),
    )
    assert s.remaining() == 720
    clock.now.return_value = now + timedelta(minutes=12)
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


def test_settlement_yields_before_starting_another_match(monkeypatch):
    monkeypatch.setattr(solver, "save_screenshot_frame", Mock())
    s = solver.GarrisonSolver(
        Mock(),
        Mock(),
        {"match": {"phase": "active"}},
        Mock(),
        deadline=lambda: datetime.now() + timedelta(minutes=11, seconds=59),
    )
    s._quick_confirmed = True
    result = Frame(None, [Text("返回主页", 100, 200, 50, 50)], "result", False)
    s.wait = Mock(return_value=frame("lobby"))
    s.sleep = Mock()
    s.play(Mock(), result)
    assert s.progress == {"match": None, "attempts": 1, "settlement_counted": True}
    s.device.tap.assert_called_once_with((125, 225))


def test_packaged_garrison_files_initialize_gameplay():
    from arknights_mower.solvers.garrison import upstream

    session = upstream.FarmSession(Mock(target_wins=3))
    assert session.game.TARGET == 3
    assert session.game.LAYOUT["safe"]
    assert callable(session.game.set_profile)


@pytest.mark.parametrize("missing", ["garrison_farm.py", "tiles.json"])
def test_missing_bundled_file_reports_incomplete_installation(
    tmp_path, monkeypatch, missing
):
    from arknights_mower.solvers.garrison import upstream

    for name in ("garrison_farm.py", "tiles.json"):
        if name != missing:
            (tmp_path / name).write_bytes((upstream.BUNDLED_DIR / name).read_bytes())
    monkeypatch.setattr(upstream, "BUNDLED_DIR", tmp_path)
    with pytest.raises(model.GarrisonError, match=missing):
        upstream.FarmSession(Mock(target_wins=3))
    assert not (tmp_path / missing).exists()


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
    game.has_color_badge.return_value = game.has_badge.return_value = False
    game.grid_shift.return_value = 0
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


@pytest.mark.parametrize(
    ("target", "match_limit", "expected", "scrolled"),
    [
        (3, None, (700, 610), True),
        (6, None, (900, 400), False),
        (3, 0, (700, 400), False),
    ],
)
def test_marked_cards_do_not_cost_panel_reads(
    monkeypatch, target, match_limit, expected, scrolled
):
    worker = solver.GarrisonSolver(
        Mock(),
        Mock(),
        {"wins": {}},
        Mock(),
        target_wins=target,
        match_limit=match_limit,
    )
    current = Frame(None, [Text("确认选择", 1650, 920, 50, 40)], "strategy", True)
    replay_unchanged_lobby(monkeypatch, worker, current)
    worker.click = Mock()
    worker.wait = Mock(return_value=frame("prep"))
    game = Mock(
        GRID_X=[700, 900, 1100, 1310],
        GRID_Y=[400, 580, 790, 1000],
        GRID_TOP=250,
        GRID_BOTTOM=1050,
    )
    game.has_color_badge.side_effect = lambda page, x, y: y != 610 and x == 700
    game.has_badge.side_effect = lambda page, x, y: y != 610 and x != 700
    game.grid_shift.side_effect = [0, None, 210]
    game.detect_rows.side_effect = [[], [610]]
    game.ocr.return_value = [(1550, 480, "初始生命值"), (1610, 560, "阿米娅")]

    assert worker.choose_strategy(game).screen == "prep"
    game.tap.assert_called_once_with(*expected, 0.7)
    assert game.ocr.call_count == 1
    assert game.scroll_grid.call_count == int(scrolled)
    game.swipe.assert_not_called()


@pytest.mark.parametrize("first_card_wins", [0, 3])
def test_badge_fallback_reads_panels_after_row_centers_shift(
    monkeypatch, first_card_wins
):
    strategies = model.catalogue()["strategies"]
    progress = {"wins": {s["id"]: 3 for s in strategies}}
    missing = strategies[0]
    del progress["wins"][missing["id"]]
    worker = solver.GarrisonSolver(Mock(), Mock(), progress, Mock())
    replay_unchanged_lobby(
        monkeypatch,
        worker,
        Frame(None, [Text("确认选择", 1650, 920, 50, 40)], "strategy", True),
    )
    worker.click = Mock()
    worker.wait = Mock(return_value=frame("prep"))
    game = Mock(GRID_X=[680], GRID_Y=[370], GRID_TOP=250, GRID_BOTTOM=1050)
    game.has_color_badge.return_value = False
    game.has_badge.side_effect = lambda page, x, y: y in (370, 610)
    page = 0

    def scroll():
        nonlocal page
        page = 1

    def back(*args, **kwargs):
        nonlocal page
        page = 0

    game.shot.side_effect = lambda: page
    game.scroll_grid.side_effect = scroll
    game.swipe.side_effect = back
    game.grid_shift.side_effect = lambda before, after: (after - before) * 210
    game.detect_rows.side_effect = lambda image: [610 if image else 390]
    game.ocr.side_effect = lambda *args: [
        (1550, 220, f"已通过模拟{3 if page else first_card_wins}次"),
        (1550, 480, "初始生命值"),
        (1610, 560, strategies[page]["name"]),
    ]
    result = worker.choose_strategy(game)
    if first_card_wins:
        assert result is None
        worker.click.assert_called_once_with((1500, 580))
    else:
        assert result.screen == "prep"
        assert worker.click.call_args.args == ((1675, 940),)
    assert [call.args[:2] for call in game.tap.call_args_list] == [
        (680, 610),
        (680, 390),
    ]
    assert progress["wins"][missing["id"]] == first_card_wins
    assert game.has_badge.call_count == 2


@pytest.mark.parametrize(
    ("known", "banner", "expected", "partial"),
    [
        (3, "", 3, False),
        (0, "已通过模拟3次", 3, False),
        (0, "已通过模拟3次", 3, True),
        (0, "", 0, False),
    ],
)
def test_strategy_uses_first_readable_count_and_preserves_wins(
    known, banner, expected, partial
):
    p = {"wins": {"band_amiya": known}}
    worker = solver.GarrisonSolver(Mock(), Mock(), p, Mock())
    worker.sleep = Mock()
    panel = [(1550, 480, "初始生命值"), (1610, 560, "阿米娅")]
    final = panel + ([(1540, 215, banner)] if banner else [])
    game = Mock()
    readings = [panel + [(1540, 215, "已通过模拟")], []] if partial else []
    game.ocr.side_effect = [*readings, final]
    action = worker.read_strategy_action(
        game, {"阿米娅": "band_amiya", "其他策略": "other"}
    )
    assert game.shot.call_count == len(readings) + 1
    assert action == ("skip" if expected >= 3 else "play")
    assert p["wins"]["band_amiya"] == expected


@pytest.mark.parametrize("deadline", [1, 30])
def test_unreadable_strategy_releases_card_or_device(monkeypatch, deadline):
    worker = solver.GarrisonSolver(Mock(), Mock(), {"wins": {"band_amiya": 3}}, Mock())
    replay_unchanged_lobby(monkeypatch, worker, frame("lobby"))
    worker._end = deadline
    game = Mock()
    game.ocr.return_value = [(1550, 480, "初始生命值"), (1550, 225, "已通过模拟")]
    if deadline == 1:
        with pytest.raises(solver.GarrisonYield):
            worker.read_strategy_action(game, {})
    else:
        assert worker.read_strategy_action(game, {}) is None
    assert game.shot.call_count > 1
    assert worker.progress["wins"] == {"band_amiya": 3}
    worker.device.tap.assert_not_called()
    worker.save.assert_not_called()


@pytest.mark.parametrize("screen", ["choice", "confirm-ready"])
def test_reconnect_recognizes_quick_simulation_prompt(screen):
    worker = solver.GarrisonSolver(
        Mock(), Mock(), {"match": {"phase": "active"}}, Mock(), vision=Mock()
    )
    worker.click = Mock()
    prompt = Frame(None, [], screen, False)
    worker.vision.frame.return_value = prompt
    assert worker.start_or_resume(frame("left")) is prompt
    assert not worker.can_dispatch_frame(prompt)
    worker.vision.frame.return_value = replace(prompt, quick=True)
    assert worker.can_dispatch_frame(worker.capture())


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
    game.has_color_badge.return_value = game.has_badge.return_value = False
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
    [(719, False, False), (720, False, True), (540, True, True), (539, True, False)],
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


@pytest.mark.parametrize("progress", [{}, {"match": {"phase": "starting"}}])
def test_match_budget_rechecked_after_navigation_before_saving_new_match(progress):
    before = copy.deepcopy(progress)
    s = solver.GarrisonSolver(Mock(), Mock(), progress, Mock())
    s.remaining = Mock(side_effect=[720, 719])
    s.text_click = Mock()
    s.wait = Mock(return_value=frame("mode"))
    with pytest.raises(solver.GarrisonYield):
        s.start_or_resume(frame("lobby"))
    assert [call.args[1] for call in s.text_click.call_args_list] == ["^极速模拟$"]
    s.save.assert_not_called()
    assert s.progress == before


def test_start_waits_for_mode_and_button_before_saving(monkeypatch):
    mode = frame("mode")
    start = mode.find("^开始模拟$")
    missing_mode = replace(mode, quick=False)
    missing_button = replace(mode, texts=[t for t in mode.texts if t != start])
    info = frame("info")
    events = []
    worker = solver.GarrisonSolver(
        Mock(), Mock(), {}, lambda progress: events.append(dict(progress))
    )
    replay_unchanged_lobby(monkeypatch, worker, missing_mode)
    worker.capture.side_effect = [missing_button, mode, info]
    worker.device.tap.side_effect = events.append

    assert worker.start_or_resume(missing_mode) is info

    assert worker.capture.call_count == 3
    assert events == [{"match": {"phase": "starting"}}, start.center]


def test_observed_quick_match_is_saved_for_reconnect():
    s = solver.GarrisonSolver(Mock(), Mock(), {"match": None}, Mock(), vision=Mock())
    s.vision.frame.side_effect = [frame("mode"), frame("prep"), frame("prep")]
    s.capture()
    s.save.assert_not_called()
    s.capture()
    s.capture()
    assert s.progress["match"] == {"phase": "active"}
    s.save.assert_called_once()


@pytest.mark.parametrize("outcome", ["模拟完成", "模拟失败", "模拟中断"])
def test_match_limit_counts_each_settlement_once_after_restart(
    outcome, income_db, monkeypatch
):
    conf = Conf(
        maa_long_task_type="garrison",
        maa_rg_enable=1,
        garrison={"mode": "matches", "match_limit": 2},
    )
    monkeypatch.setattr(runner.config, "conf", conf)
    progress = model.prepare_progress(conf, {})
    progress.update(matches_played=1, match={"phase": "active"})
    result = Frame(
        None,
        [Text(outcome, 10, 20, 50, 50), Text("返回主页", 100, 200, 50, 50)],
        "result",
        False,
    )
    screenshot = Mock()
    monkeypatch.setattr(solver, "save_screenshot_frame", screenshot)
    for replay in range(2):
        s = solver.GarrisonSolver(
            Mock(), Mock(), progress, record.save_garrison_progress, match_limit=2
        )
        s.click = Mock()
        if not replay:
            s.click.side_effect = solver.GarrisonYield()
            with pytest.raises(solver.GarrisonYield):
                s.play(Mock(), result)
        else:
            s.play(Mock(), result)
        progress = record.load_garrison_progress()
        assert progress["matches_played"] == 2
        assert progress["match"] is None
    screenshot.assert_called_once_with(result.image, "garrison_result")
    assert (
        runner.eligible_progress(
            conf, 3600, SimpleNamespace(tasks=[], op_data=None), None
        )
        is None
    )
    conf.garrison.match_limit = 3
    assert (
        runner.eligible_progress(
            conf, 3600, SimpleNamespace(tasks=[], op_data=None), None
        )["matches_played"]
        == 2
    )
    conf.garrison.run_id = "next"
    assert model.status(conf, progress)["count"] == 0


def test_two_match_target_starts_second_match_and_stops_at_its_result(monkeypatch):
    screenshots = Mock()
    monkeypatch.setattr(solver, "save_screenshot_frame", screenshots)
    progress = {"match": {"phase": "active"}, "wins": {}}
    s = solver.GarrisonSolver(
        Mock(), Mock(), progress, Mock(), match_limit=2, vision=Mock()
    )
    s._theme_checked = True
    result = Frame(
        None,
        [Text("模拟中断", 10, 20, 50, 50), Text("返回主页", 100, 200, 50, 50)],
        "result",
        False,
    )
    lobby, mode = frame("lobby"), frame("mode")
    s.vision.frame.side_effect = [
        lobby,
        mode,
        frame("info"),
        frame("post-info"),
        result,
    ]
    s.click = Mock()
    s.play(Mock(), result)
    taps = [call.args[0] for call in s.click.call_args_list]
    assert taps.count(result.find("返回主页").center) == 2
    assert taps.count(mode.find("^开始模拟$").center) == 1
    assert progress["matches_played"] == screenshots.call_count == 2
    assert progress["match"] is None


def test_unlimited_matches_can_use_completed_strategy_and_continue_past_200(
    monkeypatch,
):
    monkeypatch.setattr(solver, "save_screenshot_frame", Mock())
    conf = Conf(garrison={"mode": "matches", "match_limit": 0})
    progress = model.prepare_progress(conf, {})
    progress.update(matches_played=200, attempts=200, match={"phase": "active"})
    s = solver.GarrisonSolver(Mock(), Mock(), progress, Mock(), match_limit=0)
    game = Mock()
    game.ocr.return_value = [(0, 220, "已通过模拟⑥次"), (0, 480, "初始生命值")]
    assert s.read_strategy_action(game, {}) == "play"
    result = Frame(None, [Text("返回主页", 100, 200, 50, 50)], "result", False)
    s._quick_confirmed = True
    s.click = Mock()
    s.wait = Mock(return_value=frame("lobby"))
    s._theme_checked = True
    s.start_or_resume = Mock(side_effect=solver.GarrisonYield())
    with pytest.raises(solver.GarrisonYield):
        s.play(Mock(), result)
    s.start_or_resume.assert_called_once()
    detail = model.status(conf, progress)
    assert (detail["count"], detail["total"], detail["completed"]) == (201, 0, False)


@pytest.mark.parametrize("screen", ["info", "choice"])
def test_rechecks_missing_gameplay_control_before_tapping(monkeypatch, screen):
    progress = {"match": {"phase": "active"}}
    worker = solver.GarrisonSolver(Mock(), Mock(), progress, Mock(), match_limit=1)
    worker._quick_confirmed = True
    initial, ready = (
        (frame("info"), frame("info"))
        if screen == "info"
        else (Frame(None, [], "choice", False), Frame(None, [], "choice", False))
    )
    result = Frame(None, [Text("返回主页", 100, 200, 50, 50)], "result", False)
    if screen == "info":
        target = ready.find("[准淮]备就绪|^确认$").center
        initial.texts = [t for t in initial.texts if t.center != target]
        after_click = [frame("prep"), result]
    else:
        initial.texts = [Text("精准", 405, 450, 80, 40, 0.5)]
        ready.texts = [Text("精准", 405, 450, 80, 40)]
        target = (475, 540)
        after_click = [result]
    other = Frame(None, ready.texts, "detail", False)
    replay_unchanged_lobby(monkeypatch, worker, initial)
    worker.capture.side_effect = [initial, other, ready, *after_click]
    monkeypatch.setattr(solver, "save_screenshot_frame", Mock())
    game = Mock()
    game.Board.return_value.prep_done = False

    worker.play(game, initial)

    assert [call.args[0] for call in worker.device.tap.call_args_list] == [
        target,
        result.find("返回主页").center,
    ]
    assert worker.capture.call_count == 3 + len(after_click)
    assert progress["matches_played"] == 1


def test_missing_quick_mode_evidence_defers_gameplay_input(monkeypatch):
    info, prep = frame("info"), frame("prep")
    partial = replace(info, quick=False)
    unknown = Frame(None, [], "unknown", False)
    result = Frame(None, [Text("返回主页", 100, 200, 50, 50)], "result", False)
    worker = solver.GarrisonSolver(
        Mock(),
        Mock(),
        {"match": {"phase": "active"}},
        Mock(),
        match_limit=1,
        vision=Mock(),
    )
    worker.sleep = Mock()
    frames = iter([unknown, partial, info, prep, result])

    def recognize(_):
        observed = next(frames)
        if observed is info:
            worker.device.tap.assert_not_called()
        return observed

    worker.vision.frame.side_effect = recognize
    game = Mock()
    game.Board.return_value.prep_done = False
    monkeypatch.setattr(solver, "save_screenshot_frame", Mock())

    worker.play(game, partial)

    assert worker.vision.frame.call_count == 5
    assert worker.device.tap.call_args_list[0].args == (
        info.find("[准淮]备就绪|^确认$").center,
    )
    assert worker.progress["matches_played"] == 1


@pytest.mark.parametrize("deadline", [0.5, 20])
def test_unreadable_info_keeps_match_when_observation_ends(monkeypatch, deadline):
    progress = {"match": {"phase": "active"}, "wins": {"band_amiya": 3}}
    worker = solver.GarrisonSolver(Mock(), Mock(), progress, Mock())
    worker._quick_confirmed = True
    initial = Frame(None, [Text("确认本局信息", 800, 100, 200, 50)], "info", True)
    replay_unchanged_lobby(monkeypatch, worker, initial)
    worker._end = deadline
    error = solver.GarrisonYield if deadline < 8 else model.GarrisonError

    with pytest.raises(error):
        worker.play(Mock(), initial)

    assert worker.capture.call_count > 1
    worker.device.tap.assert_not_called()
    worker.save.assert_not_called()
    assert progress == {"match": {"phase": "active"}, "wins": {"band_amiya": 3}}


def test_timeout_replay_requires_exact_message_and_button_and_limits_repeat(
    monkeypatch,
):
    message = Text("出现超时异常，战斗将重新进行", 685, 456, 550, 49)
    confirm = Text("确认", 930, 700, 93, 56)
    observed = frame("prep")
    observed.texts = [message, confirm]
    observed.screen, observed.quick = classify(observed.texts)
    assert observed.screen == "battle-timeout"
    assert (
        classify([Text("出现超时异常，本次战斗将结束", 685, 456, 550, 49), confirm])[0]
        != observed.screen
    )
    s = solver.GarrisonSolver(Mock(), Mock(), {"match": {"round": 5}}, Mock())
    s._quick_confirmed = True
    s.click = Mock()
    s.sleep = Mock()
    s.capture = Mock(return_value=observed)
    playing = frame("prep")
    playing.screen = "battle"
    s.wait = Mock(return_value=playing)
    game = SimpleNamespace(Board=lambda: SimpleNamespace(round_done=-1))
    with pytest.raises(model.GarrisonError, match="同一回合"):
        s.play(game, observed)
    s.click.assert_called_once_with(confirm.center)
    assert s.wait.call_args.args[0](playing)
    assert not s.wait.call_args.args[0](observed)
    s.save.assert_not_called()

    observed.texts = [message, Text("确认", 150, 100, 60, 40)]
    s.click.reset_mock()
    del s.wait
    replay_unchanged_lobby(monkeypatch, s, observed)
    with pytest.raises(model.GarrisonError, match="未识别到按钮"):
        s.play(game, observed)
    s.click.assert_not_called()


@pytest.mark.parametrize("saved", [False, True])
def test_switches_team_lobby_before_choosing_quick_or_resuming(saved):
    # 取自联合模拟大厅截图的按钮文字及中心位置。
    team = frame("lobby")
    team.image[:] = 30
    team.texts = [
        Text("个人模拟", 1458, 830, 100, 38),
        Text("联合模拟", 1719, 830, 100, 38),
        Text("同盟模拟", 1295, 987, 100, 38),
        Text("搜寻队友", 1725, 987, 100, 38),
    ]
    after_switch = frame("left" if saved else "lobby")
    frames = iter(
        [after_switch, frame("prep")]
        if saved
        else [after_switch, frame("mode"), frame("info")]
    )
    worker = solver.GarrisonSolver(
        Mock(), Mock(), {"match": {"round": 5} if saved else None}, Mock()
    )

    def wait(predicate, timeout):
        next_frame = next(frames)
        assert predicate(next_frame)
        return next_frame

    worker.wait = wait
    worker.click = Mock()
    worker.start_or_resume(team)
    points = [call.args[0] for call in worker.click.call_args_list]
    assert points[:2] == [
        team.find("个人模拟").center,
        after_switch.find("断线重连" if saved else "极速模拟").center,
    ]
    assert team.find("搜寻队友").center not in points


def theme_panel(name, applied=True):
    texts = [
        Text("效果预览", 1250, 980, 115, 38),
        Text("已设置" if applied else "设置主题", 1510, 980, 160, 38),
        Text(name, 45, 950, 305, 40),
        Text("卫戍协议终端", 1670, 238, 180, 38),
        Text("乌萨斯齐心团", 1670, 428, 180, 38),
        Text("全能的”可露希尔", 1640, 613, 220, 42),
    ]
    screen, quick = classify(texts)
    return Frame(None, texts, screen, quick)


@pytest.mark.parametrize("appears", [True, False])
def test_waits_for_theme_icon_in_the_lobby(monkeypatch, appears):
    from arknights_mower.solvers.garrison import theme

    lobby = frame("left")
    lobby.texts.remove(lobby.find("^更换主题$"))
    worker = solver.GarrisonSolver(
        Mock(), Mock(), {"match": {"phase": "active"}}, Mock()
    )
    replay_unchanged_lobby(monkeypatch, worker, lobby)
    worker.click = Mock()
    worker.recog.template_match.return_value = (0.2, None)
    if appears:
        panel = theme_panel(theme.DEFAULT_THEME)
        worker.capture.side_effect = [lobby, panel, lobby, panel]
        worker.recog.template_match.side_effect = [
            (0.2, None),
            (0.3, None),
            (0.99, None),
        ]
        assert theme.open_equipped(worker, lobby) is panel
        worker.click.assert_called_once_with((523, 960))
    else:
        with pytest.raises(model.GarrisonError, match="更换主题按钮"):
            theme.open_equipped(worker, lobby)
        assert worker.capture.call_count > 1
        worker.click.assert_not_called()
    assert worker.progress == {"match": {"phase": "active"}}


def test_theme_icon_wait_yields_at_the_task_deadline(monkeypatch):
    from arknights_mower.solvers.garrison import theme
    from arknights_mower.utils.image import loadres
    from arknights_mower.utils.recognize import Recognizer

    lobby = frame("left")
    gray = np.zeros(lobby.image.shape[:2], np.uint8)
    # 入场动画中，扳手尚未升到可以点击的位置。
    icon = loadres("garrison/change_theme", gray=True)
    gray[1010 : 1010 + icon.shape[0], 495 : 495 + icon.shape[1]] = icon
    recog = SimpleNamespace(gray=gray)
    recog.template_match = Recognizer.template_match.__get__(recog)
    worker = solver.GarrisonSolver(
        Mock(), recog, {"match": {"phase": "active"}}, Mock()
    )
    replay_unchanged_lobby(monkeypatch, worker, lobby)
    worker._end = 0.5
    with pytest.raises(solver.GarrisonYield):
        theme.open_equipped(worker, lobby)
    assert worker.capture.call_count > 1
    worker.device.tap.assert_not_called()
    worker.save.assert_not_called()
    assert worker.progress == {"match": {"phase": "active"}}

    gray[932 : 932 + icon.shape[0], 495 : 495 + icon.shape[1]] = icon
    worker._end = 12
    panel = theme_panel(theme.DEFAULT_THEME)
    worker.capture.return_value = panel
    assert theme.open_equipped(worker, lobby) is panel
    worker.device.tap.assert_called_once_with((523, 960))


def test_waits_for_personal_highlight_before_clicking_reconnect():
    ready = frame("left")
    fading = frame("left")
    fading.image[:] = 30
    worker = solver.GarrisonSolver(
        Mock(), Mock(), {"match": {"phase": "active"}}, Mock()
    )
    playing = frame("prep")
    worker.capture = Mock(side_effect=[fading, ready, playing])
    worker.sleep = Mock()
    worker.click = Mock()
    assert worker.start_or_resume(fading) is playing
    worker.click.assert_called_once_with(ready.find("断线重连").center)


@pytest.mark.parametrize(
    "original", ["卫戍协议终端", "乌萨斯齐心团", "“全能的”可露希尔"]
)
def test_theme_switch_requires_observed_equipped_label(original):
    from arknights_mower.solvers.garrison import theme

    lobby = frame("left")
    default = theme.DEFAULT_THEME
    before = theme_panel(original)
    if original == "“全能的”可露希尔":
        before.texts = [t for t in before.texts if t.text != original]
        before.texts.extend(
            [Text("可露希尔", 241, 950, 170, 48), Text("“全能的”", 58, 940, 180, 66)]
        )
    changed = original != default
    frames = [before]
    if changed:
        frames += [theme_panel(default, False), theme_panel(default)]
    frames.append(lobby)
    events = []
    s = solver.GarrisonSolver(
        Mock(), Mock(), {}, lambda p: events.append(("saved", dict(p)))
    )
    s.recog.template_match.return_value = (0.99, ((495, 932), (551, 990)))
    s.click = lambda point: events.append(("tap", point))

    def wait(check, timeout=8):
        f = frames.pop(0)
        assert check(f)
        return f

    s.wait = wait
    assert s.prepare_theme(lobby) is lobby
    assert not frames
    assert s.progress == {}
    if changed:
        assert events.count(("tap", (1590, 999))) == 1
        assert events[-1] == ("tap", (65, 58))
    else:
        assert events == [("tap", (523, 960)), ("tap", (65, 58))]


@pytest.mark.parametrize(
    "part",
    [
        Text("可露希尔", 241, 950, 170, 48, 0.5),
        Text("可露希尔", 450, 950, 170, 48),
        Text("可露希尔", 241, 984, 170, 48),
        Text("可露希", 241, 950, 170, 48),
    ],
)
def test_equipped_theme_requires_complete_title_on_one_line(part):
    from arknights_mower.solvers.garrison import theme

    panel = theme_panel(theme.DEFAULT_THEME)
    panel.texts = [t for t in panel.texts if not (t.x < 930 and t.y >= 927)]
    panel.texts.extend([Text("“全能的”", 58, 940, 180, 66), part])
    assert theme.equipped(panel) is None


def test_theme_rechecks_equipped_title_and_missing_card(monkeypatch):
    from arknights_mower.solvers.garrison import theme

    name = "乌萨斯齐心团"
    panel = theme_panel(theme.DEFAULT_THEME)
    partial = replace(panel, texts=[t for t in panel.texts if t.x > 930])
    no_card = replace(panel, texts=[t for t in panel.texts if t.text != name])
    preview, applied = theme_panel(name, False), theme_panel(name)
    worker = solver.GarrisonSolver(Mock(), Mock(), {}, Mock())
    replay_unchanged_lobby(monkeypatch, worker, partial)
    worker.capture.side_effect = [partial, panel, no_card, panel, preview, applied]

    assert theme.open_equipped(worker, partial) is panel
    worker.device.tap.assert_not_called()
    theme.apply(worker, no_card, name)

    assert [call.args[0] for call in worker.device.tap.call_args_list] == [
        panel.find(name).center,
        preview.find("设置主题").center,
    ]


def test_completed_goal_skips_device_with_legacy_theme_record(income_db):
    conf = Conf(garrison={"mode": "matches", "match_limit": 1})
    progress = model.prepare_progress(conf, {})
    progress.update(matches_played=1, original_theme="乌萨斯齐心团")
    record.save_garrison_progress(progress)
    assert model.status(conf, progress)["completed"]
    assert (
        runner.eligible_progress(
            conf, 1000, SimpleNamespace(tasks=[], op_data=None), None
        )
        is None
    )
    worker = solver.GarrisonSolver(Mock(), Mock(), progress, Mock(), match_limit=1)
    worker.run()
    assert not worker.device.mock_calls
    assert not worker.recog.mock_calls


@pytest.mark.parametrize(
    "old, expected", [("maa_medals", "medals"), ("maa_score", "matches")]
)
def test_preview_settings_retain_target_and_match_limit_without_maa(old, expected):
    settings = Conf(garrison={"mode": old, "target_wins": 6, "match_limit": 4}).garrison
    assert (settings.mode, settings.target_wins, settings.match_limit) == (
        expected,
        6,
        4,
    )


def test_deployment_cost_marks_battle_without_round_text_and_preserves_dialog():
    from arknights_mower.solvers.garrison.vision import Vision
    from arknights_mower.utils.image import loadres

    image = np.zeros((1080, 1920, 3), np.uint8)
    inspect = Vision(Mock())
    quick = Text("极速模拟", 238, 25, 74, 37)
    inspect.texts = Mock(return_value=[quick, Text("6/30", 690, 32, 128, 35)])
    assert inspect.frame(image).screen == "unknown"
    icon = loadres("garrison/deployment_cost", gray=True)
    image[910 : 910 + icon.shape[0], 1748 : 1748 + icon.shape[1]] = icon[:, :, None]
    assert inspect.frame(image).screen == "battle"
    inspect.texts = Mock(
        return_value=[Text("出现超时异常，战斗将重新进行", 685, 456, 550, 49)]
    )
    assert inspect.frame(image).screen == "battle-timeout"
