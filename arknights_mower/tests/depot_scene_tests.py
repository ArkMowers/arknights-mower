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
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.recovery import DeviceRecoveryError

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
        reset_after_external_control=Mock(),
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


@pytest.fixture
def restarting_scan(scan, monkeypatch):
    scene = scan.module.Scene
    state = scan.state
    state.interruption = "entry"
    state.recovery_failure = None
    state.restarts = 0
    state.warehouse_entries = 0
    state.events = []
    monkeypatch.setattr(scan.base.config.conf.waiting_scene, "CONNECTING", (1, 1))

    def navigate_home():
        state.entries += 1
        assert state.entries <= 2, "Depot recovery must finish within two navigations"
        state.events.append(("navigate", state.entries))
        scan.module.depotREC.back_to_index(scan.solver)

    def enter_depot(name):
        assert name == "warehouse"
        state.warehouse_entries += 1
        state.tab = 0
        state.events.append(("warehouse", state.warehouse_entries))
        interrupted = state.restarts == 0 and state.interruption == "entry"
        interrupted |= (
            state.restarts > 0 and state.recovery_failure == "entry_connecting"
        )
        state.scene = scene.CONNECTING if interrupted else scene.DEPOT

    def tap(pos, *args, **kwargs):
        if state.scene == scene.LOGIN_START:
            assert pos == (665, 741)
            state.events.append(("login_start",))
            state.scene = scene.LOGIN_QUICKLY
            return
        assert state.scene == scene.DEPOT
        state.tab += 1
        assert pos == ((1063, 1298)[state.tab - 1], 70)
        state.events.append(("category", state.warehouse_entries, state.tab))
        if (
            state.restarts == 0
            and state.interruption == "second_category"
            and state.tab == 2
        ):
            state.scene = scene.CONNECTING

    def tap_element(name, *args, **kwargs):
        assert state.scene == scene.LOGIN_QUICKLY
        assert name == "login_awake"
        state.events.append(("login_awake",))
        state.scene = {
            "login_unknown": scene.UNKNOWN,
            "login_connecting": scene.CONNECTING,
        }.get(state.recovery_failure, scene.LOADING)
        return True

    def sleep(seconds=1):
        scan.clock.current += timedelta(seconds=seconds)
        if state.scene == scene.LOADING:
            state.events.append(("loaded",))
            state.scene = scene.INDEX

    def restart():
        state.restarts += 1
        state.events.append(("restart", state.restarts))
        state.scene = scene.LOGIN_START
        state.quantities = {
            "consume": ("应急理智顶液", 1),
            "normal": ("龙门币", 50),
        }

    scan.solver.back_to_index = Mock(side_effect=navigate_home)
    scan.solver.tap_index_element = Mock(side_effect=enter_depot)
    scan.solver.tap = Mock(side_effect=tap)
    scan.solver.tap_element = Mock(side_effect=tap_element)
    scan.solver.sleep = Mock(side_effect=sleep)
    scan.solver.back = Mock()
    scan.solver.device.reconnect = Mock()
    scan.solver.device.exit.side_effect = restart
    scan.merge.side_effect = lambda **_: state.events.append(("merge",))
    scan.cleanup.side_effect = lambda: state.events.append(("cleanup",))
    return scan


@pytest.mark.parametrize("interruption", ["entry", "second_category"])
def test_game_restart_completes_login_and_rescans_both_categories_once(
    restarting_scan, scheduler, monkeypatch, interruption
):
    scan = restarting_scan
    scan.state.interruption = interruption
    inventory_sync = Mock()
    inventory_sync.start.return_value = True
    monkeypatch.setattr(
        scheduler.module, "cultivateDepotSolver", Mock(return_value=inventory_sync)
    )
    monkeypatch.setattr(scheduler.module, "DepotSolver", Mock(return_value=scan.solver))
    scheduler.solver._auto_schedule_mastery_after_scan = Mock(
        side_effect=lambda: scan.state.events.append(("mastery",))
    )

    result = scheduler.solver.仓库扫描()

    assert result is True
    with scan.path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == 3
    assert json.loads(rows[-1][1]) == {"应急理智顶液": 1, "龙门币": 50}
    completed_at = int(scan.clock.now().timestamp())
    assert int(rows[-1][0]) == completed_at
    scan.merge.assert_called_once_with(记录快照时刻=completed_at)
    scan.cleanup.assert_called_once_with()
    scheduler.solver._auto_schedule_mastery_after_scan.assert_called_once_with()
    inventory_sync.start.assert_called_once_with(force_inventory=True)
    scan.solver.device.exit.assert_called_once_with()
    assert scan.state.entries == scan.state.warehouse_entries == 2
    assert scan.state.events[scan.state.events.index(("restart", 1)) + 1 :] == [
        ("navigate", 2),
        ("login_start",),
        ("login_awake",),
        ("loaded",),
        ("warehouse", 2),
        ("category", 2, 1),
        ("category", 2, 2),
        ("merge",),
        ("cleanup",),
        ("mastery",),
    ]
    recognized_models = [
        call.args[2] for call in scan.solver.匹配物品一次.call_args_list
    ]
    assert recognized_models == (
        ["consume", "normal"]
        if interruption == "entry"
        else ["consume", "consume", "normal"]
    )


@pytest.mark.parametrize(
    "failure", ["login_unknown", "login_connecting", "entry_connecting"]
)
@pytest.mark.parametrize("interruption", ["entry", "second_category"])
def test_game_restart_recovery_failure_is_bounded_and_preserves_inventory(
    restarting_scan, failure, interruption
):
    scan = restarting_scan
    scan.state.interruption = interruption
    scan.state.recovery_failure = failure

    result = scan.solver.run()

    assert_preserved(scan)
    assert result is False
    assert scan.state.entries == 2
    assert scan.state.restarts == 1
    assert scan.state.warehouse_entries == (2 if failure == "entry_connecting" else 1)
    scan.solver.tap_element.assert_called_once_with("login_awake")
    assert scan.solver.匹配物品一次.call_count == (0 if interruption == "entry" else 1)
    assert scan.clock.now() - datetime(2026, 10, 16, 19, 0, 20) < timedelta(seconds=30)


@pytest.mark.parametrize("login_scene", ["LOGIN_START", "LOGIN_QUICKLY"])
def test_restart_login_with_ineffective_input_stops_at_navigation_deadline(
    restarting_scan, monkeypatch, login_scene
):
    scan = restarting_scan
    started_at = scan.clock.now()
    monkeypatch.setattr(scan.base.config.conf, "run_order_delay", 0.1)
    monkeypatch.setattr(
        scan.module,
        "monotonic",
        lambda: (scan.clock.now() - started_at).total_seconds(),
    )
    scan.solver.recog.get_scene = Mock(side_effect=lambda: scan.state.scene)
    scan.solver.scene = scan.module.depotREC.scene.__get__(scan.solver)
    stalled_scene = getattr(scan.module.Scene, login_scene)
    stalled_inputs = []

    def input_without_progress():
        stalled_inputs.append(scan.state.scene)
        if len(stalled_inputs) > 12:
            pytest.fail("Login navigation did not stop at its deadline")
        scan.clock.current += timedelta(seconds=1)

    tap = scan.solver.tap.side_effect
    tap_element = scan.solver.tap_element.side_effect

    def controlled_tap(pos, *args, **kwargs):
        if scan.state.scene == stalled_scene:
            input_without_progress()
            return
        return tap(pos, *args, **kwargs)

    def controlled_tap_element(name, *args, **kwargs):
        if scan.state.scene == stalled_scene:
            input_without_progress()
            return True
        return tap_element(name, *args, **kwargs)

    scan.solver.tap.side_effect = controlled_tap
    scan.solver.tap_element.side_effect = controlled_tap_element

    result = scan.solver.run()

    assert result is False
    assert_preserved(scan)
    assert 1 <= len(stalled_inputs) <= 9
    assert scan.clock.now() - started_at <= timedelta(seconds=10)
    assert scan.state.entries == 2
    assert scan.state.warehouse_entries == 1
    scan.solver.device.exit.assert_called_once_with()
    scan.solver.device.launch.assert_not_called()
    scan.solver.匹配物品一次.assert_not_called()


@pytest.mark.parametrize("ready_after_restart", [True, False])
def test_graph_restart_and_scene_wait_share_one_restart_budget(
    restarting_scan, ready_after_restart
):
    scan = restarting_scan
    scan.state.scene = scan.module.Scene.LOGIN_START
    scan.state.interruption = None
    scan.state.recovery_failure = None if ready_after_restart else "entry_connecting"
    tap = scan.solver.tap.side_effect

    def fail_initial_login(pos, *args, **kwargs):
        if scan.state.restarts == 0:
            raise RuntimeError("offline login input failure")
        return tap(pos, *args, **kwargs)

    scan.solver.tap.side_effect = fail_initial_login

    result = scan.solver.run()

    assert result is ready_after_restart
    scan.solver.device.reconnect.assert_called_once_with()
    scan.solver.device.exit.assert_called_once_with()
    scan.solver.device.launch.assert_called_once_with()
    assert scan.state.entries == 2
    scan.solver.tap_element.assert_called_once_with("login_awake")
    if ready_after_restart:
        with scan.path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        assert len(rows) == 3
        assert json.loads(rows[-1][1]) == {"应急理智顶液": 1, "龙门币": 50}
        assert [call.args[2] for call in scan.solver.匹配物品一次.call_args_list] == [
            "consume",
            "normal",
        ]
        scan.merge.assert_called_once_with(
            记录快照时刻=int(scan.clock.now().timestamp())
        )
        scan.cleanup.assert_called_once_with()
    else:
        assert_preserved(scan)
        scan.solver.匹配物品一次.assert_not_called()


@pytest.mark.parametrize("error_type", [MowerExit, DeviceRecoveryError, SharedADBError])
@pytest.mark.parametrize("entry_point", ["scan", "scheduler", "dispatch"])
def test_recovery_login_preserves_cancellation_and_device_errors(
    restarting_scan, scheduler, monkeypatch, error_type, entry_point
):
    scan = restarting_scan
    error = error_type("offline recovery interrupted")
    scan.solver.tap_element.side_effect = error
    inventory_sync = Mock()
    inventory_sync.start.return_value = True
    monkeypatch.setattr(
        scheduler.module, "cultivateDepotSolver", Mock(return_value=inventory_sync)
    )
    monkeypatch.setattr(scheduler.module, "DepotSolver", Mock(return_value=scan.solver))
    scheduler.solver._auto_schedule_mastery_after_scan = Mock()
    scheduled_at = scheduler.clock.now()
    task = scheduler_recovery_preservation_tests.SchedulerTask(
        scheduled_at,
        task_type=scheduler_recovery_preservation_tests.TaskTypes.DEPOT,
    )
    scheduler.solver.tasks = [task]
    scheduler.solver.task = task
    run = {
        "scan": scan.solver.run,
        "scheduler": scheduler.solver.仓库扫描,
        "dispatch": scheduler.solver.infra_main,
    }[entry_point]

    with pytest.raises(error_type) as caught:
        run()

    assert caught.value is error
    assert_preserved(scan)
    assert scan.state.entries == 2
    scan.solver.tap_element.assert_called_once_with("login_awake")
    scan.solver.device.exit.assert_called_once_with()
    scan.solver.device.launch.assert_not_called()
    scan.solver.匹配物品一次.assert_not_called()
    scheduler.solver._auto_schedule_mastery_after_scan.assert_not_called()
    assert scheduler.solver.tasks == [task]
    assert scheduler.solver.tasks[0] is scheduler.solver.task is task
    assert task.time == scheduled_at
    assert scheduler.solver.error is False


def test_waiting_timeout_without_restart_returns_failure_without_exiting(scan):
    scan.state.scene = scan.module.Scene.CONNECTING

    result = scan.base.BaseSolver.waiting_solver(scan.solver, restart_on_timeout=False)

    assert result is False
    scan.solver.device.exit.assert_not_called()
    scan.solver.device.launch.assert_not_called()
    scan.solver.check_current_focus.assert_not_called()


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
    assert scan.state.entries == 1
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
    assert scan.state.entries == 1
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
