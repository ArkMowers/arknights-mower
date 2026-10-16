import csv
import importlib
import json
import socket
import subprocess
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from arknights_mower.tests import scheduler_recovery_preservation_tests

scheduler = scheduler_recovery_preservation_tests.scheduler


@pytest.fixture(autouse=True)
def offline_io(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("external I/O is forbidden"))
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    yield forbidden
    forbidden.assert_not_called()


@pytest.fixture
def scan(monkeypatch, tmp_path):
    module = importlib.import_module("arknights_mower.solvers.depotREC")
    base = importlib.import_module("arknights_mower.utils.solver")
    scene = module.Scene

    class Clock(datetime):
        current = datetime(2026, 10, 16, 19, 0, 20)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(base, "csleep", Mock())
    if hasattr(module, "time"):
        monkeypatch.setattr(module, "time", SimpleNamespace(sleep=Mock()))

    path = tmp_path / "depotresult.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Timestamp", "Data", "json"])
        writer.writerow([1792144700, json.dumps({"合成玉": 2830}), "{}"])
    original = path.read_bytes()
    state = SimpleNamespace(
        scene=scene.INDEX,
        entry_scene=scene.DEPOT,
        tab_scenes={},
        tab=0,
        entries=0,
        unstable_at=None,
        empty_tabs=set(),
        quantities={"consume": ("应急理智顶液", 3), "normal": ("龙门币", 100000000)},
    )
    solver = object.__new__(module.depotREC)
    solver.仓库输出 = path
    solver.结果字典 = {}
    solver.knn模型_CONSUME = "consume"
    solver.knn模型_NORMAL = "normal"
    solver.recog = SimpleNamespace(
        update=Mock(),
        img=np.zeros((1080, 1920, 3), dtype=np.uint8),
        gray=np.zeros((1080, 1920), dtype=np.uint8),
    )
    solver.device = SimpleNamespace(exit=Mock(), launch=Mock())
    solver.check_current_focus = Mock()

    def back_to_index():
        state.entries += 1
        if state.entries > 1:
            pytest.fail("A failed depot scan repeated navigation in the same run")
        state.scene = scene.INDEX

    solver.back_to_index = Mock(side_effect=back_to_index)
    solver.tap_index_element = Mock(
        side_effect=lambda _: setattr(state, "scene", state.entry_scene)
    )
    solver.scene = Mock(side_effect=lambda: state.scene)

    def tap(*args, **kwargs):
        state.tab += 1
        state.scene = state.tab_scenes.get(state.tab, scene.DEPOT)

    solver.tap = Mock(side_effect=tap)

    def find(name, *args, **kwargs):
        if name == "connecting":
            return state.unstable_at == state.tab
        if name == "depot_empty":
            return state.tab in state.empty_tabs
        return False

    solver.find = Mock(side_effect=find)
    solver.sleep = Mock(
        side_effect=lambda seconds: setattr(
            Clock, "current", Clock.current + timedelta(seconds=seconds)
        )
    )
    solver.切图主程序 = Mock(return_value=[(None, None, "one item")])

    def match_item(item, gray, model):
        Clock.current += timedelta(seconds=2)
        return state.quantities[model]

    solver.匹配物品一次 = Mock(side_effect=match_item)
    merge, cleanup = Mock(), Mock()
    monkeypatch.setattr(module.depot, "读取仓库", merge)
    monkeypatch.setattr(module.depot, "清理历史", cleanup)
    return SimpleNamespace(
        solver=solver,
        state=state,
        module=module,
        base=base,
        clock=Clock,
        path=path,
        original=original,
        merge=merge,
        cleanup=cleanup,
    )


def assert_preserved(scan):
    assert scan.path.read_bytes() == scan.original
    with scan.path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert int(rows[-1][0]) == 1792144700
    scan.merge.assert_not_called()
    scan.cleanup.assert_not_called()


def test_game_restart_on_entry_aborts_without_scanning_or_persistence(
    scan, monkeypatch
):
    scan.state.entry_scene = scan.module.Scene.CONNECTING
    monkeypatch.setattr(scan.base.config.conf.waiting_scene, "CONNECTING", (1, 1))
    scan.solver.device.exit.side_effect = lambda: setattr(
        scan.state, "scene", scan.module.Scene.LOGIN_START
    )

    result = scan.solver.run()

    assert_preserved(scan)
    assert result is False
    assert scan.state.scene == scan.module.Scene.LOGIN_START
    scan.solver.device.exit.assert_called_once_with()
    scan.solver.tap.assert_not_called()
    scan.solver.匹配物品一次.assert_not_called()


def test_target_scene_wait_stops_when_waiting_solver_restarts_game(scan):
    scan.state.scene = scan.module.Scene.CONNECTING
    scan.solver.waiting_solver = Mock(
        side_effect=lambda: (
            setattr(scan.state, "scene", scan.module.Scene.DEPOT) or False
        )
    )

    result = scan.solver.wait_for_scene_stable(scan.module.Scene.DEPOT)

    assert result is False
    scan.solver.waiting_solver.assert_called_once_with()
    scan.solver.scene.assert_called_once_with()


@pytest.mark.parametrize("failure", ["wrong_scene", "unstable"])
def test_entry_must_confirm_depot_and_stable_frame_before_selecting_tabs(scan, failure):
    if failure == "wrong_scene":
        scan.state.entry_scene = scan.module.Scene.LOGIN_START
    else:
        scan.state.unstable_at = 0

    result = scan.solver.run()

    assert_preserved(scan)
    assert result is False
    scan.solver.tap.assert_not_called()
    scan.solver.匹配物品一次.assert_not_called()


@pytest.mark.parametrize("failed_tab", [1, 2])
@pytest.mark.parametrize("failure", ["wrong_scene", "unstable"])
def test_tab_failure_never_commits_a_partial_inventory(scan, failed_tab, failure):
    if failure == "wrong_scene":
        scan.state.tab_scenes[failed_tab] = scan.module.Scene.LOGIN_START
    else:
        scan.state.unstable_at = failed_tab

    result = scan.solver.run()

    assert_preserved(scan)
    assert result is False
    assert scan.solver.tap.call_count == failed_tab
    assert scan.solver.匹配物品一次.call_count == failed_tab - 1


@pytest.mark.parametrize("lost_after", [0, 2])
def test_pixel_stability_cannot_replace_final_depot_scene_confirmation(
    scan, lost_after
):
    def refresh_frame():
        if scan.state.tab == lost_after:
            scan.state.scene = scan.module.Scene.LOGIN_START

    scan.solver.recog.update.side_effect = refresh_frame

    result = scan.solver.run()

    assert_preserved(scan)
    assert result is False
    assert scan.solver.tap.call_count == lost_after
    assert scan.solver.匹配物品一次.call_count == max(0, lost_after - 1)


def test_success_commits_both_categories_once_with_actual_completion_time(scan):
    started_at = int(scan.clock.now().timestamp())

    result = scan.solver.run()

    with scan.path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == 3
    assert json.loads(rows[-1][1]) == {"应急理智顶液": 3, "龙门币": 100000000}
    completed_at = int(scan.clock.now().timestamp())
    assert completed_at > started_at
    assert int(rows[-1][0]) == completed_at
    scan.merge.assert_called_once_with(记录快照时刻=completed_at)
    scan.cleanup.assert_called_once_with()
    assert result is True


def test_explicitly_empty_category_is_accepted_without_recognizing_items(scan):
    scan.state.empty_tabs = {1}

    result = scan.solver.run()

    with scan.path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == 3
    assert json.loads(rows[-1][1]) == {"龙门币": 100000000}
    scan.solver.匹配物品一次.assert_called_once_with(None, None, "normal")
    assert result is True


def test_both_explicitly_empty_categories_are_valid_observations(scan):
    scan.state.empty_tabs = {1, 2}

    result = scan.solver.run()

    with scan.path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == 3
    assert json.loads(rows[-1][1]) == {}
    scan.solver.匹配物品一次.assert_not_called()
    scan.merge.assert_called_once_with(记录快照时刻=int(scan.clock.now().timestamp()))
    assert result is True


def test_reusing_solver_does_not_accumulate_the_previous_scan(scan):
    assert scan.solver.run() is True
    scan.state.tab = scan.state.entries = 0
    scan.state.quantities = {"consume": ("应急理智顶液", 1), "normal": ("龙门币", 50)}

    result = scan.solver.run()

    with scan.path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == 4
    assert json.loads(rows[-1][1]) == {"应急理智顶液": 1, "龙门币": 50}
    assert result is True
    assert scan.merge.call_count == scan.cleanup.call_count == 2


def test_nonempty_categories_with_no_confirmed_quantity_do_not_write_empty_success(
    scan,
):
    scan.state.quantities = {
        "consume": ("应急理智顶液", None),
        "normal": ("龙门币", None),
    }

    result = scan.solver.run()

    assert_preserved(scan)
    assert result is False


def test_category_recognition_uses_the_frame_that_passed_depot_confirmation(scan):
    confirmed_frame = scan.solver.recog.img
    scan.solver.recog.update.side_effect = lambda: setattr(
        scan.solver.recog, "img", np.ones_like(confirmed_frame)
    )

    scan.solver.分类扫描("consume")

    cropped = scan.solver.切图主程序.call_args.args[0]
    assert np.shares_memory(cropped, confirmed_frame)


@pytest.mark.parametrize("scan_result", [False, True])
def test_scheduler_admits_mastery_only_after_successful_depot_scan(
    scheduler, monkeypatch, scan_result
):
    module, solver = scheduler.module, scheduler.solver
    inventory_sync = Mock()
    inventory_sync.start.return_value = True
    depot_solver = Mock()
    depot_solver.run.return_value = scan_result
    monkeypatch.setattr(
        module, "cultivateDepotSolver", Mock(return_value=inventory_sync)
    )
    monkeypatch.setattr(module, "DepotSolver", Mock(return_value=depot_solver))
    solver._auto_schedule_mastery_after_scan = Mock()

    result = solver.仓库扫描()

    assert result is scan_result
    inventory_sync.start.assert_called_once_with(force_inventory=True)
    depot_solver.run.assert_called_once_with()
    if scan_result:
        solver._auto_schedule_mastery_after_scan.assert_called_once_with()
    else:
        solver._auto_schedule_mastery_after_scan.assert_not_called()
