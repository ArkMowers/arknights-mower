import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

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
    "start_ts": 100,
    "end_ts": 200,
    "x": 1200,
    "y": 500,
    "confirm_text": "测试兑换处",
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


def test_resource_time_coordinate_override_and_missing_old_resource(navigation):
    conf = Conf(maa_event_shop={"activity": "测试活动"}).maa_event_shop
    assert shop.select_shop(conf, 100) == ENTRY
    assert shop.select_shop(conf, 200) is None
    conf.custom_entry = True
    conf.x, conf.y, conf.confirm_text = 100, 200, "自选兑换处"
    assert shop.select_shop(conf, 150)["confirm_text"] == "自选兑换处"
    conf.confirm_text = ""
    assert shop.select_shop(conf, 150) is None
    navigation.unlink()
    assert shop.activity_shops(150) == []


@pytest.mark.parametrize(
    "update", [{"end_ts": 99}, {"x": 1920}, {"y": True}, {"confirm_text": ""}]
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


def emit(solver, message, taskid=1, chain="Custom", node=None):
    solver.on_maa_callback(
        message,
        json.dumps(
            {
                "taskchain": chain,
                "taskid": taskid,
                "subtask": "ProcessTask",
                "details": {"task": node},
            }
        ).encode(),
        None,
    )


@pytest.mark.parametrize(
    "result",
    [
        "success",
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
    monkeypatch.setattr(EventShopNavigation, "run", MagicMock(return_value=True))

    def running():
        # StartUp and Award precede the separately navigated Custom task.
        if scheduler.MAA.append_task.call_args.args[0] == "Custom":
            taskid = scheduler.MAA.append_task.call_count
            node = (
                "SS@Store@Underfunded"
                if result == "underfunded"
                else "SS@Store@CheckUnlimited"
            )
            if result != "missing":
                emit(
                    scheduler,
                    20002,
                    taskid,
                    "Mall" if result == "unmatched" else "Custom",
                    node,
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
    assert manager.get_active_plan_key() == ("常规" if result == "success" else "活动")
    if result == "success":
        assert base_schedule.config.conf.maa_weekly_plan[0].stage == ["1-7"]
    assert scheduler.last_execution["maa"] is not None
    assert scheduler.release_maa.called


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


def test_authorized_shop_route_reads_selected_resources(
    monkeypatch, navigation, manager
):
    import server

    monkeypatch.setattr(server.app, "token", "test-shop-token", raising=False)
    response = server.app.test_client().get(
        "/maa-event-shop", headers={"token": "test-shop-token"}
    )
    assert response.get_json() == {"shops": [ENTRY]}


@pytest.mark.parametrize("title,ready", [("测试兑换处", True), ("活动首页", False)])
def test_navigation_confirms_shop_title_after_entering_selected_activity(
    monkeypatch, title, ready
):
    from arknights_mower.solvers import event_shop

    solver = object.__new__(EventShopNavigation)
    solver.recog = MagicMock()
    order = []
    for name in (
        "scene_graph_navigation",
        "open_activity_overview_until_ready",
        "find_stage_image_and_enter",
        "tap",
        "wait_for_scene_stable",
    ):
        monkeypatch.setattr(
            solver,
            name,
            MagicMock(
                side_effect=lambda *a, _name=name, **k: order.append((_name, a)) or True
            ),
        )
    monkeypatch.setattr(
        event_shop.rapidocr,
        "engine",
        MagicMock(return_value=([[[], title, 0.99]], None)),
    )
    assert solver.run(ENTRY) is ready
    assert order[2] == ("find_stage_image_and_enter", ("测试活动",))
    assert order[3] == ("tap", ((1200, 500),))


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
