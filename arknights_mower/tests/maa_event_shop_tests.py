import json
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call

import pytest
import yaml

from arknights_mower.solvers import base_schedule
from arknights_mower.solvers.event_shop import EventShopNavigation
from arknights_mower.tests import maa_copilot_tests as helpers
from arknights_mower.utils import maa_event_shop as shop
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.weekly_plan_loader import WeeklyPlanManager

files = helpers.files
scheduler = helpers.scheduler

ENTRY = {
    "activity": "测试活动",
    "activity_id": "act999side",
    "start_ts": 100,
    "end_ts": 200,
}


@pytest.fixture
def navigation(monkeypatch, tmp_path):
    path = tmp_path / "event_shop.json"
    path.write_text(json.dumps([ENTRY]))
    monkeypatch.setattr(shop, "resource_pkg_path", lambda _: path)
    monkeypatch.setattr(
        shop,
        "stage_data_full",
        [
            {"id": "ACT-1", "stageType": "ACTIVITY", "zoneNameSecond": "测试活动"},
            {"id": "ACT-2", "stageType": "ACTIVITY", "zoneNameSecond": "其他活动"},
        ],
    )
    return path


def test_automatic_plan_selection_and_legacy_settings(navigation, manager):
    assert shop.select_shop(manager, 100) == ENTRY
    assert shop.select_shop(manager, 200) is None
    legacy = Conf(
        maa_event_shop={
            "activity": "测试活动",
            "custom_entry": True,
            "x": 1,
            "y": 2,
            "confirm_text": "旧设置",
        }
    ).maa_event_shop
    assert "custom_entry" not in legacy.model_dump()
    assert "activity" not in legacy.model_dump()
    assert shop.select_shop(manager, 150) == ENTRY
    navigation.unlink()
    assert shop.activity_shops(150) == []


@pytest.mark.parametrize(
    "update", [{"end_ts": 99}, {"start_ts": "100"}, {"activity_id": "minigame"}]
)
def test_invalid_resource_is_rejected(navigation, update):
    navigation.write_text(json.dumps([{**ENTRY, **update}]))
    with pytest.raises(ValueError):
        shop.activity_shops(150)


@pytest.fixture
def manager(monkeypatch, tmp_path):
    from arknights_mower.utils.config import weekly_plan_loader

    manager = object.__new__(WeeklyPlanManager)
    path = tmp_path / "weekly.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "plans": {
                    name: [{"weekday": "周一", "stage": [stage]}]
                    for name, stage in [
                        ("活动", "ACT-1"),
                        ("常规", "1-7"),
                        ("其他", "CE-6"),
                    ]
                },
                "activity_fallbacks": {"活动": "常规", "常规": "其他"},
                "activity_fallback_switch_times": {"活动": 180},
            },
            allow_unicode=True,
        )
    )
    state = {"active_weekly_plan": "活动"}
    monkeypatch.setattr(manager, "WEEKLY_PLANS_FILE", path)
    monkeypatch.setattr(manager, "_read_state", lambda: dict(state))
    monkeypatch.setattr(manager, "_write_state", state.update)
    monkeypatch.setattr(manager, "_current_server_timestamp", lambda: 150)
    monkeypatch.setattr(weekly_plan_loader, "get_weekly_plan_manager", lambda: manager)
    return manager


def setup_shop(scheduler):
    conf = base_schedule.config.conf
    conf.maa_rg_enable = 0
    conf.maa_event_shop = Conf(
        maa_event_shop={
            "enable": True,
            "activity": "测试活动",
            "switch_source": "活动",
            "blacklist": ["家具"],
        }
    ).maa_event_shop
    scheduler.device = MagicMock()


def emit(solver, message, taskid=1, chain="Custom", node=None, **extra):
    solver.on_maa_callback(
        message,
        json.dumps(
            {
                "taskchain": chain,
                "taskid": taskid,
                "subtask": "ProcessTask",
                "details": {"task": node},
                **extra,
            }
        ).encode(),
        None,
    )


@pytest.mark.parametrize(
    "result",
    [
        "success",
        "short-success",
        "underfunded",
        "error",
        "stop",
        "missing",
        "unmatched",
        "subtask-error",
    ],
)
def test_real_daily_dispatch_switches_only_on_confirmed_finite_completion(
    scheduler, navigation, manager, monkeypatch, result
):
    setup_shop(scheduler)
    navigate = MagicMock(return_value=True)
    monkeypatch.setattr(EventShopNavigation, "run", navigate)

    def running():
        # StartUp and Award precede the separately navigated Custom task.
        if scheduler.MAA.append_task.call_args.args[0] == "Custom":
            taskid = scheduler.MAA.append_task.call_count
            node = (
                "SS@Store@Underfunded"
                if result == "underfunded"
                else "CheckUnlimited"
                if result == "short-success"
                else "SS@Store@CheckUnlimited"
            )
            if result != "missing":
                emit(
                    scheduler,
                    20002,
                    taskid,
                    "Mall" if result == "unmatched" else "Custom",
                    node,
                    first=["SS@Store@PurchaseSelected"],
                )
            if result == "subtask-error":
                emit(scheduler, 20000, taskid)
            emit(scheduler, {"error": 10000, "stop": 10004}.get(result, 10002), taskid)
        return False

    scheduler.MAA.running.side_effect = running
    scheduler.maa_plan_solver()
    assert scheduler.MAA.append_task.call_args.args == (
        "Custom",
        {
            "task_names": ["SS@Store@Begin"],
            "params": {"event_shop": {"blacklist": ["家具"]}},
        },
    )
    switched = result in ("success", "short-success")
    assert manager.get_active_plan_key() == ("常规" if switched else "活动")
    if switched:
        assert base_schedule.config.conf.maa_weekly_plan[0].stage == ["1-7"]
    assert scheduler.last_execution["maa"] is not None
    assert scheduler.release_maa.called

    manager.set_active_plan("活动")
    scheduler.MAA.running.side_effect = None
    scheduler.run_maa_event_shop(lambda: datetime.now() + timedelta(hours=2))
    assert navigate.call_count == (1 if switched else 2)


@pytest.mark.parametrize(
    "result",
    [
        "plugin-exhausted",
        "process-exhausted",
        "nine-swipes",
        "wrong-task",
        "unrelated-swipe",
        "underfunded",
        "underfunded-after-plugin",
        "purchase-after-swipes",
        "plugin-incomplete",
        "process-without-limit",
        "subtask-error",
        "chain-error",
        "chain-stopped",
    ],
)
def test_shop_scan_exhaustion_controls_later_dispatch_without_switching_plan(
    scheduler, navigation, manager, monkeypatch, result
):
    setup_shop(scheduler)
    navigate = MagicMock(return_value=True)
    monkeypatch.setattr(EventShopNavigation, "run", navigate)
    monkeypatch.setattr(scheduler, "_maa_refresh_deadline", lambda: None)
    process_only = result.startswith("process-")
    if process_only:
        base_schedule.config.conf.maa_event_shop.blacklist = []

    def running():
        emit(scheduler, 20001, subtask="EventShopTask")
        if process_only:
            emit(scheduler, 20002, subtask="EventShopTask")
        first = ["SS@Store@Begin" if process_only else "SS@Store@Swipe"]
        if result == "unrelated-swipe":
            first = ["SomeOtherTask"]
        for index in range(9 if result == "nine-swipes" else 10):
            emit(
                scheduler,
                20002,
                taskid=2 if result == "wrong-task" else 1,
                first=first,
                details={
                    "task": "Swipe",
                    "action": "Swipe",
                    "exec_times": index + 1 if process_only else 1,
                    "max_times": 10,
                },
            )
        if result in ("underfunded", "purchase-after-swipes"):
            purchase = ["SS@Store@PurchaseSelected"]
            node = "UnderfundedOCR" if result == "underfunded" else "PurchasedConfirm"
            emit(scheduler, 20001, node=node, first=purchase)
            emit(scheduler, 20002, node=node, first=purchase)
        if result == "subtask-error":
            emit(scheduler, 20000, subtask="EventShopTask")
        if not process_only and result != "plugin-incomplete":
            emit(scheduler, 20002, subtask="EventShopTask")
        if result == "underfunded-after-plugin":
            emit(scheduler, 20002, node="Underfunded", first=["SS@Store@Begin"])
        if result == "process-exhausted":
            emit(
                scheduler,
                20003,
                first=["SS@Store@Begin"],
                what="ExceededLimit",
                details={"task": "Swipe", "exec_times": 10, "max_times": 10},
            )
        emit(
            scheduler, {"chain-error": 10000, "chain-stopped": 10004}.get(result, 10002)
        )
        return False

    def deadline():
        return datetime.now() + timedelta(hours=2)

    scheduler.MAA.running.side_effect = running
    scheduler.run_maa_event_shop(deadline)
    assert manager.get_active_plan_key() == "活动"

    scheduler.MAA.running.side_effect = None
    scheduler.run_maa_event_shop(deadline)
    expected_runs = 1 if result in ("plugin-exhausted", "process-exhausted") else 2
    assert navigate.call_count == expected_runs
    assert scheduler.MAA.append_task.call_count == expected_runs


@pytest.mark.parametrize("activity_id", ["act999side", "act1000side"])
def test_completed_shop_is_skipped_after_restart_but_next_activity_runs(
    scheduler, navigation, manager, monkeypatch, activity_id
):
    setup_shop(scheduler)
    base_schedule.config.conf.maa_event_shop.switch_source = ""
    navigate = MagicMock(return_value=True)
    monkeypatch.setattr(EventShopNavigation, "run", navigate)
    monkeypatch.setattr(scheduler, "_maa_refresh_deadline", lambda: None)

    def running():
        emit(scheduler, 20002, node="SS@Store@CheckUnlimited")
        emit(scheduler, 10002)
        return False

    def deadline():
        return datetime.now() + timedelta(hours=2)

    scheduler.MAA.running.side_effect = running
    scheduler.run_maa_event_shop(deadline)
    assert manager.get_active_plan_key() == "活动"
    navigate.assert_called_once_with(ENTRY)

    restarted = object.__new__(base_schedule.BaseSchedulerSolver)
    restarted._maa_refresh_deadline = lambda: deadline()
    restarted._defer_maa_event_shop_for_refresh = MagicMock()
    assert restarted.run_maa_event_shop(deadline, manual=True) is None
    restarted._defer_maa_event_shop_for_refresh.assert_not_called()
    navigate.assert_called_once()

    next_activity = {
        **ENTRY,
        "activity_id": activity_id,
        "start_ts": 140 if activity_id == ENTRY["activity_id"] else ENTRY["start_ts"],
        "end_ts": 240,
    }
    navigation.write_text(json.dumps([next_activity]))
    scheduler.MAA.running.side_effect = None
    scheduler.run_maa_event_shop(deadline)
    assert navigate.call_args_list == [call(ENTRY), call(next_activity)]
    assert scheduler.MAA.append_task.call_count == 2


@pytest.mark.parametrize(
    "change", ["time", "manual", "round-trip", "target", "settings", "disable"]
)
def test_stale_completion_cannot_override_later_choices(
    scheduler, navigation, manager, monkeypatch, change
):
    setup_shop(scheduler)
    monkeypatch.setattr(EventShopNavigation, "run", lambda *a: True)

    def running():
        taskid = scheduler.MAA.append_task.call_count
        emit(scheduler, 20002, taskid, node="SS@Store@CheckUnlimited")
        if change == "time":
            manager.maybe_switch_expired_activity_plan(stages=[], now=181)
        elif change in ("manual", "round-trip"):
            manager.set_active_plan("其他")
            if change == "round-trip":
                manager.set_active_plan("活动")
        elif change == "target":
            manager.set_activity_fallback("活动", "其他")
        elif change == "settings":
            base_schedule.config.conf.maa_event_shop.blacklist.append("技巧概要")
        else:
            base_schedule.config.conf.maa_event_shop.enable = False
        emit(scheduler, 10002, taskid)
        return False

    scheduler.MAA.running.side_effect = running
    scheduler.run_maa_event_shop(lambda: datetime.now() + timedelta(hours=2))
    assert manager.get_active_plan_key() == {"time": "常规", "manual": "其他"}.get(
        change, "活动"
    )


def test_daily_then_shop_restores_theme_only_in_daily_queue(
    scheduler, navigation, manager, monkeypatch
):
    setup_shop(scheduler)
    conf = base_schedule.config.conf
    conf.maa_restore_theme_enable = True
    conf.maa_restore_theme = "夜间"
    scheduler.MAA.get_version.return_value = "v6.17.3"
    monkeypatch.setattr(
        scheduler,
        "append_maa_theme_task",
        base_schedule.BaseSchedulerSolver.append_maa_theme_task.__get__(scheduler),
    )
    monkeypatch.setattr(EventShopNavigation, "run", MagicMock(return_value=True))
    order = MagicMock()
    order.attach_mock(scheduler.MAA.append_task, "append")
    order.attach_mock(scheduler.MAA.start, "start")
    scheduler.MAA.start.return_value = True
    scheduler.maa_plan_solver()
    assert [entry.args[0] for entry in scheduler.MAA.append_task.call_args_list] == [
        "StartUp",
        "Award",
        "SwitchTheme",
        "Custom",
    ]
    assert order.mock_calls[2:4] == [
        call.append("SwitchTheme", {"themes": ["夜间"]}),
        call.start(),
    ]
    assert order.mock_calls[-1] == call.start()
    assert scheduler.MAA.start.call_count == 2


@pytest.mark.parametrize("ready,expired", [(False, False), (True, True)])
def test_unconfirmed_or_expired_shop_never_submits_custom(
    scheduler, navigation, manager, monkeypatch, ready, expired
):
    setup_shop(scheduler)
    monkeypatch.setattr(EventShopNavigation, "run", lambda *a: ready)
    if expired:
        monkeypatch.setattr(manager, "_current_server_timestamp", lambda: 200)
    scheduler.run_maa_event_shop(lambda: datetime.now() + timedelta(hours=2))
    scheduler.MAA.append_task.assert_not_called()


def test_mower_stop_during_shop_stops_maa_and_closes_game_without_wait(
    scheduler, navigation, manager, monkeypatch
):
    setup_shop(scheduler)
    monkeypatch.setattr(EventShopNavigation, "run", lambda *a: True)

    def running():
        if scheduler.MAA.append_task.call_args.args[0] == "Custom":
            base_schedule.config.stop_mower.set()
            return True
        return False

    scheduler.MAA.running.side_effect = running
    scheduler.sleep = MagicMock()
    with pytest.raises(base_schedule.MowerExit):
        scheduler.maa_plan_solver()
    scheduler.device.exit_after_task_stop.assert_called_once()
    scheduler.sleep.assert_not_called()
    assert manager.get_active_plan_key() == "活动"


@pytest.mark.parametrize("token", [None, "invalid"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_shop_route_rejects_unauthenticated_resource_read(monkeypatch, token, method):
    import server

    monkeypatch.setattr(server.app, "token", "test-shop-token", raising=False)
    read = MagicMock()
    monkeypatch.setattr(shop, "activity_shops", read)
    response = server.app.test_client().open(
        "/maa-event-shop",
        method=method,
        headers={} if token is None else {"token": token},
    )
    assert response.status_code == 403
    read.assert_not_called()


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_authorized_shop_route_reads_selected_resources(
    monkeypatch, navigation, manager, method
):
    import server

    entry = {**ENTRY, "token_icon_ids": ["rerun_currency_icon"]}
    navigation.write_text(json.dumps([entry]))
    monkeypatch.setattr(server.app, "token", "test-shop-token", raising=False)
    response = server.app.test_client().open(
        "/maa-event-shop", method=method, headers={"token": "test-shop-token"}
    )
    assert response.status_code == 200
    if method == "GET":
        assert response.get_json() == {"shops": [entry]}
    else:
        assert response.data == b""


@pytest.mark.parametrize(
    "activity_id,start_ts,point,terminal_point",
    [
        ("act46sre", 1795291200, (229, 826), (336, 827)),
        ("act55side", 1793487600, (1461, 255), None),
    ],
)
@pytest.mark.parametrize("title,ready", [("关闭时间", True), ("活动首页", False)])
def test_navigation_reads_shop_page_after_clicking_fixed_entrance(
    monkeypatch, activity_id, start_ts, point, terminal_point, title, ready
):
    from arknights_mower.solvers import activity_navigation, event_shop
    from arknights_mower.utils.scene import Scene

    token_entry = MagicMock(return_value=terminal_point)
    monkeypatch.setattr(
        activity_navigation.ActivityNavigation, "token_entry", token_entry
    )
    solver = object.__new__(EventShopNavigation)
    solver.recog = MagicMock()
    monkeypatch.setattr(solver, "scene", lambda: Scene.TERMINAL_MAIN)
    monkeypatch.setattr(solver, "collect_terminal_ocr_candidates", lambda: [])
    for name in (
        "scene_graph_navigation",
        "open_activity_overview_until_ready",
        "find_stage_image_and_enter",
        "tap_and_detect_page_move",
        "wait_for_scene_stable",
        "sleep",
    ):
        monkeypatch.setattr(solver, name, MagicMock(return_value=True))
    monkeypatch.setattr(solver, "tap", MagicMock())

    def read_shop_page(*_args, **_kwargs):
        assert solver.tap.call_args == call(point)
        return [[[], title, 0.99], [[], "剩余10", 0.99]], None

    monkeypatch.setattr(event_shop.rapidocr, "engine", read_shop_page)
    entry = {**ENTRY, "activity_id": activity_id, "start_ts": start_ts}
    assert solver.run(entry) is ready
    token_entry.assert_called_once_with()
    if terminal_point is None:
        solver.find_stage_image_and_enter.assert_called_once_with(
            "测试活动", max_swipes=10
        )
        assert solver.tap.call_args_list == [
            call((490, 1014), interval=0.2),
            call(point),
        ]
    else:
        solver.tap_and_detect_page_move.assert_called_once_with(
            terminal_point, "测试活动", record_step=False
        )
        solver.tap.assert_called_once_with(point)


def test_shop_with_no_fixed_point_for_its_edition_skips_navigation(monkeypatch):
    from arknights_mower.solvers import event_shop

    solver = object.__new__(EventShopNavigation)
    navigate = MagicMock()
    initialize_ocr = MagicMock()
    monkeypatch.setattr(solver, "scene_graph_navigation", navigate)
    monkeypatch.setattr(event_shop.rapidocr, "initialize_ocr", initialize_ocr)
    monkeypatch.setattr(event_shop.rapidocr, "engine", None)

    entry = {**ENTRY, "activity_id": "act46sre", "start_ts": 1795291201}
    assert not solver.run(entry)
    navigate.assert_not_called()
    initialize_ocr.assert_not_called()


def test_stopping_shop_navigation_does_not_start_a_following_large_task(
    scheduler, navigation, manager, monkeypatch
):
    from arknights_mower.utils import maa_copilot

    setup_shop(scheduler)
    conf = base_schedule.config.conf
    script = maa_copilot.store_script(
        b'{"stage_name":"mem_test_1","actions":[]}', paradox=True
    )
    conf.maa_rg_enable = 1
    conf.maa_long_task_type = "paradox"
    conf.paradox = Conf(paradox={"scripts": [{"id": script["id"]}]}).paradox

    def stop_navigation(*args):
        base_schedule.config.stop_maa.set()
        return True

    monkeypatch.setattr(EventShopNavigation, "run", stop_navigation)
    scheduler.maa_plan_solver()
    assert [call.args[0] for call in scheduler.MAA.append_task.call_args_list] == [
        "StartUp",
        "Award",
    ]
    scheduler.initialize_maa.assert_called_once()
    assert manager.get_active_plan_key() == "活动"


@pytest.mark.parametrize("ending", ["initial-wait", "recovery-wait", "cancel"])
def test_shop_navigation_exits_recovery_when_its_task_ends(
    scheduler, navigation, manager, monkeypatch, ending
):
    from arknights_mower.solvers import event_shop
    from arknights_mower.utils import graph
    from arknights_mower.utils.device import recovery
    from arknights_mower.utils.device.io_budget import io_timeout
    from arknights_mower.utils.device.touch_backend import TouchFailure
    from arknights_mower.utils.scene import Scene

    setup_shop(scheduler)
    monkeypatch.setitem(
        event_shop.SHOP_ENTRANCE_POINTS, shop.shop_identity(ENTRY), (229, 826)
    )
    elapsed = 0.0
    sleeps = []
    monkeypatch.setattr(time, "monotonic", lambda: elapsed)
    monkeypatch.setattr(event_shop.rapidocr, "engine", MagicMock())
    monkeypatch.setattr(EventShopNavigation, "scene", lambda _: Scene.INDEX)
    monkeypatch.setattr(EventShopNavigation, "check_current_focus", MagicMock())

    def failed_touch(*args, **kwargs):
        raise TouchFailure(
            base_schedule.config.conf.device,
            "darwin",
            BrokenPipeError("touch connection lost"),
            delivery_unknown=True,
        )

    tap = MagicMock(side_effect=failed_touch)
    monkeypatch.setattr(EventShopNavigation, "tap_index_element", tap)

    def sleep(seconds):
        nonlocal elapsed
        sleeps.append(seconds)
        if len(sleeps) > 5:
            pytest.fail("shop navigation kept waiting after its task ended")
        elapsed += seconds
        if ending == "cancel":
            base_schedule.config.stop_maa.set()

    def reconnect():
        io_timeout(0)
        raise TimeoutError("local connection timeout")

    scheduler.device.reconnect.side_effect = reconnect
    monkeypatch.setattr(graph, "csleep", sleep)
    monkeypatch.setattr(recovery, "csleep", sleep)
    monkeypatch.setattr(base_schedule, "logger", MagicMock())
    budget = 20 if ending == "initial-wait" else 120
    scheduler.run_maa_event_shop(
        lambda: datetime.now() + timedelta(seconds=300 + budget)
    )

    assert elapsed == pytest.approx(30 if ending == "cancel" else budget, abs=0.1)
    assert scheduler.device.reconnect.call_count == (
        3 if ending == "recovery-wait" else 0
    )
    tap.assert_called_once()
    scheduler.initialize_maa.assert_not_called()
    scheduler.MAA.append_task.assert_not_called()
    scheduler.device.launch.assert_not_called()
    assert manager.get_active_plan_key() == "活动"
    base_schedule.logger.warning.assert_called_once_with(
        "活动商店导航超时或收到停止指令，跳过兑换",
        extra={"log_group": "maa-integration"},
    )


@pytest.mark.parametrize("stages", [["1-7"], ["ACT-2"], ["UNKNOWN"], []])
def test_shop_skips_before_navigation_without_matching_activity_in_current_weekly_plan(
    scheduler, navigation, manager, monkeypatch, stages
):
    setup_shop(scheduler)
    data = yaml.safe_load(manager.WEEKLY_PLANS_FILE.read_text())
    data["plans"]["活动"] = [{"weekday": "周一", "stage": stages}]
    manager.WEEKLY_PLANS_FILE.write_text(yaml.safe_dump(data, allow_unicode=True))
    navigate = MagicMock(return_value=True)
    monkeypatch.setattr(EventShopNavigation, "run", navigate)
    scheduler.run_maa_event_shop(lambda: datetime.now() + timedelta(hours=1))
    navigate.assert_not_called()
    scheduler.initialize_maa.assert_not_called()
    scheduler.MAA.append_task.assert_not_called()


def test_shop_rechecks_plan_after_navigation_before_purchase(
    scheduler, navigation, manager, monkeypatch
):
    setup_shop(scheduler)

    def change_plan(*args):
        manager.set_active_plan("常规")
        return True

    monkeypatch.setattr(EventShopNavigation, "run", change_plan)
    scheduler.run_maa_event_shop(lambda: datetime.now() + timedelta(hours=1))
    scheduler.initialize_maa.assert_not_called()
    scheduler.MAA.append_task.assert_not_called()


def test_matching_activity_on_another_weekday_qualifies(navigation, manager):
    data = yaml.safe_load(manager.WEEKLY_PLANS_FILE.read_text())
    data["plans"]["活动"] = [
        {"weekday": "周一", "stage": ["1-7"]},
        {"weekday": "周日", "stage": ["ACT-1"]},
    ]
    manager.WEEKLY_PLANS_FILE.write_text(yaml.safe_dump(data, allow_unicode=True))
    assert shop.weekly_plan_uses_activity(manager, "测试活动")
    assert not shop.weekly_plan_uses_activity(manager, "其他活动")


def test_no_current_ss_does_not_start_navigation_or_maa(
    navigation, manager, scheduler, monkeypatch
):
    setup_shop(scheduler)
    navigation.write_text("[]")
    navigate = MagicMock()
    monkeypatch.setattr(EventShopNavigation, "run", navigate)
    scheduler.run_maa_event_shop(lambda: datetime.now() + timedelta(hours=2))
    navigate.assert_not_called()
    scheduler.MAA.append_task.assert_not_called()


def test_current_ss_is_selected_before_weekly_plan_filtering(navigation, manager):
    newer = {
        **ENTRY,
        "activity": "新活动",
        "activity_id": "act1000side",
        "start_ts": 120,
    }
    navigation.write_text(json.dumps([ENTRY, newer]))
    assert shop.select_shop(manager, 150) is None


def test_simultaneous_current_ss_candidates_are_not_guessed(navigation, manager):
    other = {**ENTRY, "activity": "其他活动", "activity_id": "act1000side"}
    navigation.write_text(json.dumps([ENTRY, other]))
    assert shop.select_shop(manager, 150) is None


def test_legacy_shop_is_classified_only_from_matching_selected_stage_data(
    navigation, monkeypatch
):
    legacy = {key: value for key, value in ENTRY.items() if key != "activity_id"}
    navigation.write_text(json.dumps([legacy]))
    monkeypatch.setattr(
        shop,
        "stage_data_full",
        [
            {
                "id": "ACT-1",
                "stageType": "ACTIVITY",
                "zoneNameSecond": "测试活动",
                "zoneId": "act999side_zone1",
                "endTs": {"startTs": 100, "endTs": 180},
            }
        ],
    )
    item = shop.activity_shops(150)[0]
    assert item["activity_id"] == "act999side"
    assert item["end_ts"] == 180
    assert item["reward_end_ts"] == 200
    assert shop.activity_shops(190) == []
    legacy["start_ts"] = 90
    navigation.write_text(json.dumps([legacy]))
    assert shop.activity_shops(150) == []


@pytest.mark.parametrize("code", ["TL-EX-1", "TL-S-1"])
def test_unrecorded_chapter_plan_does_not_start_shop(
    navigation, manager, scheduler, monkeypatch, code
):
    from pathlib import Path

    current = json.loads(
        (Path(__file__).parents[1] / "data/event_shop.json").read_text("utf-8")
    )[0]
    current = {**current, "start_ts": 100, "end_ts": 200}
    navigation.write_text(json.dumps([current]))
    monkeypatch.setattr(
        shop,
        "stage_data_full",
        [
            {
                "id": "TL-1",
                "stageType": "ACTIVITY",
                "zoneNameSecond": current["activity"],
            }
        ],
    )
    data = yaml.safe_load(manager.WEEKLY_PLANS_FILE.read_text())
    data["plans"]["活动"] = [{"weekday": "周一", "stage": [code]}]
    manager.WEEKLY_PLANS_FILE.write_text(yaml.safe_dump(data, allow_unicode=True))
    assert shop.select_shop(manager, 150) is None
    setup_shop(scheduler)
    navigate = MagicMock(return_value=True)
    monkeypatch.setattr(EventShopNavigation, "run", navigate)
    scheduler.run_maa_event_shop(lambda: datetime.now() + timedelta(hours=1))
    navigate.assert_not_called()
    scheduler.MAA.append_task.assert_not_called()
