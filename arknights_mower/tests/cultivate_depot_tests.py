import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.usefixtures("income_db")

# Importing the real sign-in helper performs network work; all sync tests are local.
sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())
from arknights_mower.solvers import cultivate_depot as module  # noqa: E402


@pytest.fixture
def syncer(tmp_path, monkeypatch):
    from arknights_mower.utils import growth

    monkeypatch.setattr(
        growth, "get_path", lambda name: tmp_path / name.rsplit("/", 1)[-1]
    )
    monkeypatch.setattr(module, "get_path", lambda _: tmp_path / "cultivate.json")
    monkeypatch.setattr(
        module.config.conf,
        "skland_info",
        [SimpleNamespace(account="test-account", cultivate_select=True)],
    )
    monkeypatch.setattr(module, "log", lambda _: "login")
    monkeypatch.setattr(module, "get_cred_by_token", lambda _: {})
    monkeypatch.setattr(module.cultivate, "save_param", lambda *args: None)
    monkeypatch.setattr(module, "get_sign_header", lambda *args: {})
    monkeypatch.setattr(
        module,
        "get_binding_list",
        lambda _: [{"gameId": 1, "isOfficial": True, "uid": "test"}],
    )
    return module.cultivate()


def test_no_account_or_matching_binding_does_not_report_success(syncer, monkeypatch):
    monkeypatch.setattr(module, "get_binding_list", lambda _: [])
    assert syncer.start() is False
    monkeypatch.setattr(module.config.conf, "skland_info", [])
    assert syncer.start() is False
    assert not syncer.record_path.exists()


def test_success_means_fresh_character_data_was_written(syncer):
    data = {
        "code": 0,
        "data": {"characters": [{"id": "char_2027_wang", "evolvePhase": 2}]},
    }
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = data
        assert syncer.start() is True
    assert json.loads(syncer.record_path.read_text()) == data


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        {"code": 10001, "message": "登录已失效"},
        {"code": 0, "data": {}},
        {"code": 0, "data": None},
        {"code": 0, "data": []},
        {"code": 0, "data": {"characters": []}},
        {"code": 0, "data": {"characters": [None]}},
        {"code": 0, "data": {"characters": [{"id": ""}]}},
    ],
)
def test_invalid_remote_response_keeps_previous_roster(syncer, response):
    syncer.record_path.write_text('{"previous": true}')
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = response
        with pytest.raises(ValueError):
            syncer.start()
    assert syncer.record_path.read_text() == '{"previous": true}'


def test_sync_endpoint_rejects_empty_box_without_overwriting_saved_data(syncer):
    import server

    syncer.record_path.write_text('{"previous": true}')
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = {"code": 0, "data": {"characters": []}}
        response = server.app.test_client().get("/cultivate-fetch")
    assert response.status_code == 200
    assert response.json["success"] is False
    assert "同步干员数据" in response.json["message"]
    assert syncer.record_path.read_text() == '{"previous": true}'


@pytest.mark.parametrize("updated", [False, True])
def test_sync_endpoint_reports_actual_update_result(updated):
    import server

    with patch.object(module.cultivate, "start", return_value=updated):
        response = server.app.test_client().get("/cultivate-fetch")
    assert response.status_code == 200
    assert response.json["success"] is updated, response.json


@pytest.fixture
def stock_db(tmp_path, monkeypatch):
    from arknights_mower.solvers import record

    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(
        record,
        "get_path",
        lambda name: tmp_path / "data.db" if name.endswith(".db") else tmp_path,
    )
    return record


def test_fresh_sync_repairs_stock_but_cached_reads_keep_later_crafting(
    syncer, stock_db, monkeypatch, tmp_path
):
    import csv

    from arknights_mower.data import key_mapping
    from arknights_mower.utils import depot

    monkeypatch.setattr(
        depot, "get_path", lambda name: tmp_path / name.rsplit("/", 1)[-1]
    )
    payload = {
        "code": 0,
        "data": {
            "characters": [{"id": "char_2027_wang", "evolvePhase": 2}],
            "items": [{"id": key_mapping["固源岩组"][0], "count": "280"}],
        },
    }
    # Model a stock count corrupted by the former partial-scan bug.
    stock_db.save_inventory_counts({"固源岩组": 0, "提纯源岩": 3, "碳": 100})
    stock_db.apply_workshop_inventory({"固源岩组": 0})
    monkeypatch.setattr(module, "time", lambda: 10_000_000_000)
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = payload
        assert syncer.start() is True
    assert stock_db.get_inventory_counts()["固源岩组"] == 280
    assert stock_db.get_inventory_counts()["提纯源岩"] == 0
    assert stock_db.get_inventory_counts()["碳"] == 100
    with patch.object(stock_db, "datetime") as clock:
        clock.now.return_value.timestamp.return_value = 10_000_000_001
        stock_db.apply_workshop_inventory({"固源岩组": -4, "提纯源岩": 1})
    with (tmp_path / "depotresult.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Data", "json"])
        writer.writerow([10_000_000_002, json.dumps({"碳": 90}), "{}"])
    for _ in range(2):
        depot.读取仓库()
        assert stock_db.get_inventory_counts()["固源岩组"] == 276
        assert stock_db.get_inventory_counts()["提纯源岩"] == 1
        assert stock_db.get_inventory_counts()["碳"] == 90
    monkeypatch.setattr(module, "time", lambda: 10_000_000_003)
    # A newer HTTP request alone cannot prove a changed cloud count includes
    # local consumption (the extra rocks can be delayed loot).
    payload["data"]["items"][0]["count"] = "290"
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = payload
        assert syncer.start() is True
    assert stock_db.get_inventory_counts()["固源岩组"] == 276
    stock_db.save_inventory_counts(
        {"固源岩组": 290}, scanned_counts={"固源岩组": 290}, scanned_at=10_000_000_004
    )
    assert stock_db.get_inventory_counts()["固源岩组"] == 290


def test_craft_during_sync_is_not_overwritten(syncer, stock_db, monkeypatch):
    from arknights_mower.data import key_mapping

    stock_db.save_inventory_counts({"固源岩组": 280})
    monkeypatch.setattr(module, "time", lambda: 100)

    def respond(*args, **kwargs):
        if "/cultivate/player" in str(args[1]):
            with patch.object(stock_db, "datetime") as clock:
                clock.now.return_value.timestamp.return_value = 101
                stock_db.apply_workshop_inventory({"固源岩组": -4})
        return SimpleNamespace(
            json=lambda: {
                "code": 0,
                "data": {
                    "characters": [{"id": "char_2027_wang", "evolvePhase": 2}],
                    "items": [{"id": key_mapping["固源岩组"][0], "count": "280"}],
                },
            }
        )

    monkeypatch.setattr(module, "request_with_retry", respond)
    assert syncer.start() is True
    assert stock_db.get_inventory_counts()["固源岩组"] == 276


@pytest.mark.parametrize("items", [{}, [None], [{"id": "30013", "count": "bad"}]])
def test_invalid_stock_does_not_replace_cache_or_database(syncer, stock_db, items):
    stock_db.save_inventory_counts({"固源岩组": 276})
    syncer.record_path.write_text('{"previous": true}')
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = {
            "code": 0,
            "data": {"characters": [{"id": "char_2027_wang"}], "items": items},
        }
        with pytest.raises(ValueError):
            syncer.start()
    assert stock_db.get_inventory_counts() == {"固源岩组": 276}
    assert json.loads(syncer.record_path.read_text()) == {"previous": True}


def test_later_requests_with_lagging_cloud_keep_each_operators_completed_batches(
    syncer, stock_db, monkeypatch
):
    from arknights_mower.data import key_mapping, workshop_formula
    from arknights_mower.utils.config.conf import WorkShopItem
    from arknights_mower.utils.workshop_limits import batch_delta, batch_limit

    targets = {"固化纤维板": 3, "酮阵列": 3, "异铁块": 1}
    initial = {name: 2 for name in targets}
    for name in targets:
        for child in workshop_formula[name]["items"]:
            initial[child] = 100
    stock_db.save_inventory_counts(initial)
    payload = {
        "code": 0,
        "data": {
            "characters": [{"id": "char_2027_wang", "evolvePhase": 2}],
            "items": [
                {"id": key_mapping[name][0], "count": count}
                for name, count in initial.items()
            ],
        },
    }
    now = 10_000_000_000
    monkeypatch.setattr(module, "time", lambda: now)
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = payload
        for name, needed in targets.items():
            # Each new operator's request is later, but the cloud items are old.
            now += 10
            assert syncer.start()
            setting = WorkShopItem(
                item_names=[name],
                self_upper_limit=initial[name] + needed,
                children_lower_limit=0,
            )
            assert (
                batch_limit(
                    name,
                    workshop_formula[name],
                    setting,
                    stock_db.get_inventory_counts(),
                )
                == needed
            )
            with patch.object(stock_db, "datetime") as clock:
                clock.now.return_value.timestamp.return_value = now + 1
                stock_db.apply_workshop_inventory(
                    batch_delta(name, workshop_formula[name], needed)
                )
            now += 2
            assert syncer.start()
            assert (
                batch_limit(
                    name,
                    workshop_formula[name],
                    setting,
                    stock_db.get_inventory_counts(),
                )
                == 0
            )
        for _ in range(2):
            now += 10
            assert syncer.start()
            for name, needed in targets.items():
                assert stock_db.get_inventory_counts()[name] == initial[name] + needed
        # Cloud convergence clears the pending fence, so later real spending can sync.
        actual = stock_db.get_inventory_counts()
        payload["data"]["items"] = [
            {"id": key_mapping[name][0], "count": count}
            for name, count in actual.items()
        ]
        now += 10
        assert syncer.start()
        assert stock_db.get_inventory_counts() == actual
        for item in payload["data"]["items"]:
            if item["id"] == key_mapping["固化纤维板"][0]:
                item["count"] = 0
        now += 10
        assert syncer.start()
        assert stock_db.get_inventory_counts()["固化纤维板"] == 0


@pytest.mark.parametrize(
    "baseline,changes,lagging,expected",
    [(0, (6, -3), 6, 3), (10, (-6, 3), 4, 7)],
)
def test_bidirectional_crafting_rejects_intermediate_cloud_snapshot(
    stock_db, baseline, changes, lagging, expected
):
    name = "固源岩组"
    stock_db.save_inventory_counts({name: baseline})
    for delta in changes:
        stock_db.apply_workshop_inventory({name: delta})
    for timestamp in (10_000_000_000, 10_000_000_001):
        stock_db.save_inventory_counts(
            {name: lagging},
            scanned_counts={},
            cloud_counts={name: lagging},
            cloud_at=timestamp,
        )
        assert stock_db.get_inventory_counts()[name] == expected
    stock_db.save_inventory_counts(
        {name: expected},
        scanned_counts={},
        cloud_counts={name: expected},
        cloud_at=10_000_000_002,
    )
    with stock_db._conn() as conn:
        assert not list(conn.execute("SELECT * FROM workshop_inventory_pending"))
    stock_db.save_inventory_counts(
        {name: expected + 2},
        scanned_counts={},
        cloud_counts={name: expected + 2},
        cloud_at=10_000_000_003,
    )
    assert stock_db.get_inventory_counts()[name] == expected + 2


@pytest.mark.parametrize("directions", [1, 2, 3])
def test_warehouse_task_forces_cloud_baseline_and_clears_old_protection(
    syncer, stock_db, monkeypatch, tmp_path, directions
):
    from arknights_mower.solvers import base_schedule
    from arknights_mower.utils import depot

    name = "技巧概要·卷3"
    stock_db.save_inventory_counts({name: 70, "碳": 99})
    with stock_db._conn() as conn:
        conn.execute(
            "INSERT INTO workshop_inventory_pending VALUES (?, ?, ?)",
            (name, 60, directions),
        )
        conn.execute(
            "INSERT INTO workshop_inventory_updates VALUES (?, ?)", (name, 100)
        )
        conn.commit()
    monkeypatch.setattr(module, "time", lambda: 200)
    payload = {
        "code": 0,
        "data": {
            "characters": [{"id": "char_2027_wang", "evolvePhase": 2}],
            "items": [{"id": "3303", "count": "7"}],
        },
    }
    monkeypatch.setattr(base_schedule, "cultivateDepotSolver", lambda: syncer)
    scan = MagicMock()
    monkeypatch.setattr(base_schedule, "DepotSolver", scan)
    solver = SimpleNamespace(
        device=object(), recog=object(), _auto_schedule_mastery_after_scan=MagicMock()
    )
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = payload
        assert base_schedule.BaseSchedulerSolver.仓库扫描(solver)
    assert stock_db.get_inventory_counts()[name] == 7
    assert stock_db.get_inventory_counts()["碳"] == 99
    scan.return_value.run.assert_called_once()
    solver._auto_schedule_mastery_after_scan.assert_called_once()
    with stock_db._conn() as conn:
        assert (
            conn.execute(
                "SELECT * FROM workshop_inventory_pending WHERE item_name = ?", (name,)
            ).fetchall()
            == []
        )

    monkeypatch.setattr(
        depot, "get_path", lambda name: tmp_path / name.rsplit("/", 1)[-1]
    )
    for _ in range(2):
        report = depot.读取仓库()
        assert report[0]["I技能书"][name]["number"] == 7
        assert stock_db.get_inventory_counts()[name] == 7


def test_forced_warehouse_sync_keeps_changes_confirmed_during_the_request(
    syncer, stock_db, monkeypatch
):
    name = "技巧概要·卷3"
    stock_db.save_inventory_counts({name: 70})
    monkeypatch.setattr(module, "time", lambda: 200)
    payload = {
        "code": 0,
        "data": {
            "characters": [{"id": "char_2027_wang", "evolvePhase": 2}],
            "items": [{"id": "3303", "count": "7"}],
        },
    }

    def response(*args, **kwargs):
        if "/cultivate/player" in args[1]:
            with patch.object(stock_db, "datetime") as clock:
                clock.now.return_value.timestamp.return_value = 201
                stock_db.apply_workshop_inventory({name: -8})
        return SimpleNamespace(json=lambda: payload)

    monkeypatch.setattr(module, "request_with_retry", response)
    assert syncer.start(force_inventory=True)
    assert stock_db.get_inventory_counts()[name] == 62
    with stock_db._conn() as conn:
        assert conn.execute(
            "SELECT directions FROM workshop_inventory_pending WHERE item_name = ?",
            (name,),
        ).fetchone() == (2,)


@pytest.mark.parametrize("failure", ["no_binding", "missing_items", "http_error"])
def test_failed_warehouse_sync_never_scans_or_dispatches_using_cached_stock(
    syncer, stock_db, monkeypatch, failure
):
    from arknights_mower.solvers import base_schedule

    stock_db.save_inventory_counts({"技巧概要·卷3": 70})
    monkeypatch.setattr(base_schedule, "cultivateDepotSolver", lambda: syncer)
    scan = MagicMock()
    monkeypatch.setattr(base_schedule, "DepotSolver", scan)
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    solver = SimpleNamespace(_auto_schedule_mastery_after_scan=MagicMock())
    if failure == "no_binding":
        monkeypatch.setattr(module, "get_binding_list", lambda _: [])
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = {
            "code": 0,
            "data": {"characters": [{"id": "char_2027_wang", "evolvePhase": 2}]},
        }
        if failure == "http_error":
            get.side_effect = RuntimeError("sync failed")
        assert base_schedule.BaseSchedulerSolver.仓库扫描(solver) is False
    assert stock_db.get_inventory_counts()["技巧概要·卷3"] == 70
    scan.assert_not_called()
    solver._auto_schedule_mastery_after_scan.assert_not_called()


@pytest.fixture(autouse=True)
def isolate_optional_yituliu_sync(tmp_path, monkeypatch):
    from arknights_mower.utils import yituliu_sync

    monkeypatch.setattr(
        yituliu_sync, "get_path", lambda path: tmp_path / path.rsplit("/", 1)[-1]
    )


@pytest.mark.parametrize("success", [True, False])
def test_successful_refresh_passes_exact_snapshot_to_optional_sync_once(
    syncer, monkeypatch, success
):
    from arknights_mower.utils import yituliu_sync

    player = {
        "uid": "12345678",
        "nickName": "测试",
        "channelName": "官服",
        "channelMasterId": "1",
    }
    monkeypatch.setattr(
        module,
        "get_binding_list",
        lambda _: [{**player, "gameId": 1, "isOfficial": True, "cred": "private"}],
    )
    outcome = {"success": success, "message": "同步成功" if success else "一图流不可用"}
    hook = MagicMock(return_value=outcome)
    monkeypatch.setattr(yituliu_sync, "sync_after_cultivate", hook)
    payload = {
        "code": 0,
        "data": {"characters": [{"id": "char_2027_wang", "evolvePhase": 2}]},
    }
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = payload
        assert syncer.start() is True
    hook.assert_called_once()
    sent = hook.call_args.args[0]
    assert sent["_mower_player"] == player
    assert "cred" not in sent["_mower_player"]
    assert json.loads(syncer.record_path.read_text()) == sent
    assert syncer.yituliu_sync_result == outcome


def test_fetch_response_keeps_skland_success_when_optional_upload_fails(
    syncer, monkeypatch
):
    import server

    outcome = {"success": False, "message": "一图流未确认同步成功"}

    def start(*, force_inventory):
        assert force_inventory is True
        syncer.yituliu_sync_result = outcome
        return True

    monkeypatch.setattr(syncer, "start", start)
    monkeypatch.setattr(module, "cultivate", lambda: syncer)
    result = server.app.test_client().get("/cultivate-fetch").json
    assert result["success"] is True
    assert result["yituliu_sync"] == outcome


def test_failed_skland_refresh_does_not_upload_previous_cache(syncer, monkeypatch):
    from arknights_mower.utils import yituliu_sync

    hook = MagicMock()
    monkeypatch.setattr(yituliu_sync, "sync_after_cultivate", hook)
    syncer.record_path.write_text('{"previous": true}')
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = {"code": 10001, "message": "登录已失效"}
        with pytest.raises(ValueError):
            syncer.start()
    hook.assert_not_called()
    assert json.loads(syncer.record_path.read_text()) == {"previous": True}


def test_concurrent_refreshes_keep_fetch_cache_and_upload_in_order(syncer, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    from arknights_mower.utils import yituliu_sync

    uploading, release, waiting = Event(), Event(), Event()
    lock = Lock()

    class ObservedLock:
        def __enter__(self):
            if lock.locked():
                waiting.set()
            lock.acquire()

        def __exit__(self, *args):
            lock.release()

    monkeypatch.setattr(module, "_refresh_lock", ObservedLock())
    phases = []

    def upload(snapshot):
        phases.append(snapshot["data"]["characters"][0]["evolvePhase"])
        if len(phases) == 1:
            uploading.set()
            assert release.wait(5)

    monkeypatch.setattr(yituliu_sync, "sync_after_cultivate", upload)
    with patch.object(module, "request_with_retry") as get:
        get.side_effect = [
            response
            for phase in (1, 2)
            for response in (
                SimpleNamespace(
                    json=lambda phase=phase: {
                        "code": 0,
                        "data": {
                            "characters": [
                                {"id": "char_2027_wang", "evolvePhase": phase}
                            ]
                        },
                    }
                ),
                SimpleNamespace(json=lambda: {"code": 0, "data": {}}),
            )
        ]
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(syncer.start)
            try:
                assert uploading.wait(5)
                second = workers.submit(module.cultivate().start)
                assert waiting.wait(5)
                assert get.call_count == 2
                assert phases == [1]
            finally:
                release.set()
            assert first.result(timeout=5) is True
            assert second.result(timeout=5) is True
    assert phases == [1, 2]
    assert (
        json.loads(syncer.record_path.read_text())["data"]["characters"][0][
            "evolvePhase"
        ]
        == 2
    )


def test_refresh_fetches_facilities_for_the_same_role_and_keeps_only_conditions(syncer):
    roster = {
        "code": 0,
        "data": {"characters": [{"id": "char_2027_wang", "evolvePhase": 2}]},
    }
    info = {
        "code": 0,
        "data": {
            "building": {
                "hire": {"level": 1},
                "powers": [{"level": 3}] * 2,
                "manufactures": [{"level": 3}] * 5,
                "dormitories": [{"level": 1}, {"level": 2}],
            },
            "status": {"name": "private"},
        },
    }
    with patch.object(module, "request_with_retry") as get:
        get.side_effect = [
            SimpleNamespace(json=lambda: roster),
            SimpleNamespace(json=lambda: info),
        ]
        assert syncer.start() is True
    saved = json.loads(syncer.record_path.read_text())
    assert saved["_mower_base_conditions"] == {
        "recruits": 0,
        "power": 2,
        "factories": 5,
        "dormLevel": 2,
    }
    assert "private" not in json.dumps(saved)
    assert get.call_args.kwargs["timeout"] == 10
    assert get.call_args.args[1].endswith("?uid=test")


def test_facility_fetch_failure_keeps_successful_roster_sync(syncer):
    roster = {
        "code": 0,
        "data": {"characters": [{"id": "char_2027_wang", "evolvePhase": 2}]},
    }
    with patch.object(module, "request_with_retry") as get:
        get.side_effect = [
            SimpleNamespace(json=lambda: roster),
            RuntimeError("private response"),
        ]
        with patch.object(module.logger, "warning") as logged:
            assert syncer.start() is True
    assert json.loads(syncer.record_path.read_text()) == roster
    assert "private response" not in str(logged.call_args)


def test_combined_roster_and_facilities_need_no_second_request(syncer):
    data = {
        "code": 0,
        "data": {
            "characters": [{"id": "char_2027_wang", "evolvePhase": 2}],
            "building": {"hire": {"level": 3}},
        },
    }
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = data
        assert syncer.start() is True
    assert get.call_count == 1
    assert json.loads(syncer.record_path.read_text())["_mower_base_conditions"] == {
        "recruits": 2
    }


def test_manual_refresh_calibrates_existing_70_to_cloud_7(
    syncer, stock_db, monkeypatch
):
    import server

    name = "技巧概要·卷3"
    stock_db.save_inventory_counts({name: 70})
    stock_db.apply_workshop_inventory({name: 1})
    monkeypatch.setattr(module, "cultivate", lambda: syncer)
    monkeypatch.setattr(server.app, "token", "", raising=False)
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = {
            "code": 0,
            "data": {
                "characters": [{"id": "char_2027_wang", "evolvePhase": 2}],
                "items": [{"id": "3303", "count": "7"}],
            },
        }
        response = server.app.test_client().get("/cultivate-fetch").json
    assert response["success"] is True
    assert stock_db.get_inventory_counts()[name] == 7


@pytest.mark.parametrize(
    "module_id,target_level", [("elite1", None), ("skill7", None), ("module", 2)]
)
def test_successful_sync_removes_only_confirmed_completed_manual_goals(
    syncer, monkeypatch, module_id, target_level
):
    from arknights_mower.utils import growth, mastery_recommendation

    goal = {"char_id": "char_test", "module_id": module_id}
    if target_level is not None:
        goal["target_level"] = target_level
    remaining = {"char_id": "char_other", "module_id": "elite2"}
    path = growth.get_path("@app/config/growth_plan.json")
    path.write_text(json.dumps([goal, remaining]))
    skills = {
        "growth": {
            "characters": {
                "char_test": {
                    "phases": [{"max_level": 50}, {"max_level": 80}, {"max_level": 90}],
                    "modules": [
                        {"id": "module", "levels": [{"level": n} for n in (1, 2, 3)]}
                    ],
                }
            }
        }
    }
    monkeypatch.setattr(mastery_recommendation, "get_skill_data", lambda: skills)
    payload = {
        "code": 0,
        "data": {
            "characters": [
                {
                    "id": "char_test",
                    "evolvePhase": 2,
                    "level": 1,
                    "mainSkillLevel": 7,
                    "equips": [{"id": "module", "level": 2}],
                }
            ]
        },
    }
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = payload
        assert syncer.start()
    assert growth.load_goals() == [remaining]
    assert json.loads(syncer.record_path.read_text()) == payload


def test_failed_sync_keeps_saved_manual_goals(syncer):
    from arknights_mower.utils import growth

    path = growth.get_path("@app/config/growth_plan.json")
    path.write_text('[{"char_id": "char_test", "module_id": "elite1"}]')
    previous = path.read_bytes()
    with patch.object(
        module, "request_with_retry", side_effect=RuntimeError("offline")
    ):
        with pytest.raises(RuntimeError, match="offline"):
            syncer.start()
    assert path.read_bytes() == previous


@pytest.fixture
def completed_manual_goal(syncer, monkeypatch):
    from arknights_mower.utils import growth

    path = growth.get_path("@app/config/growth_plan.json")
    path.write_text('[{"char_id": "char_test", "module_id": "skill7"}]')
    monkeypatch.setattr(module, "time", lambda: 200)
    return {
        "code": 0,
        "data": {
            "characters": [
                {"id": "char_test", "evolvePhase": 2, "level": 1, "mainSkillLevel": 7}
            ],
            "items": [{"id": "3303", "count": "7"}],
        },
    }


def test_completed_manual_goal_calibrates_old_stock_and_invalidates_unreported_counts(
    syncer, stock_db, completed_manual_goal
):
    from arknights_mower.utils import growth

    stock_db.save_inventory_counts({"技巧概要·卷3": 70, "龙门币": 999})
    with patch.object(stock_db, "datetime") as clock:
        clock.now.return_value.timestamp.return_value = 100
        stock_db.apply_workshop_inventory({"技巧概要·卷3": 6})
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = completed_manual_goal
        assert syncer.start()
    current = stock_db.get_inventory_counts()
    assert current["技巧概要·卷3"] == 7
    assert "龙门币" not in current
    assert growth.load_goals() == []
    stock_db.save_inventory_counts(
        {"龙门币": 999}, scanned_counts={"龙门币": 999}, scanned_at=150
    )
    assert "龙门币" not in stock_db.get_inventory_counts()


@pytest.mark.parametrize("force_inventory", [False, True])
def test_completion_without_inventory_never_keeps_old_counts_as_confirmed(
    syncer, stock_db, completed_manual_goal, force_inventory
):
    from arknights_mower.utils import growth

    del completed_manual_goal["data"]["items"]
    stock_db.save_inventory_counts({"技巧概要·卷3": 70, "龙门币": 999})
    syncer.record_path.write_text('{"previous": true}')
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = completed_manual_goal
        if force_inventory:
            with pytest.raises(ValueError, match="未返回库存"):
                syncer.start(force_inventory=True)
            assert json.loads(syncer.record_path.read_text()) == {"previous": True}
            assert growth.load_goals() == [
                {"char_id": "char_test", "module_id": "skill7"}
            ]
        else:
            assert syncer.start()
            assert growth.load_goals() == []
    assert stock_db.get_inventory_counts() == {}


def test_completion_calibration_preserves_changes_confirmed_during_request(
    syncer, stock_db, completed_manual_goal, monkeypatch
):
    stock_db.save_inventory_counts({"技巧概要·卷3": 70, "龙门币": 999})

    def respond(*args, **kwargs):
        if "/cultivate/player" in args[1]:
            with patch.object(stock_db, "datetime") as clock:
                clock.now.return_value.timestamp.return_value = 201
                stock_db.apply_workshop_inventory({"技巧概要·卷3": 6, "龙门币": -10})
        return SimpleNamespace(json=lambda: completed_manual_goal)

    monkeypatch.setattr(module, "request_with_retry", respond)
    assert syncer.start()
    current = stock_db.get_inventory_counts()
    assert current["技巧概要·卷3"] == 76
    assert current["龙门币"] == 989


def test_unknown_shared_stock_never_falls_back_to_old_cultivate_materials(
    syncer, stock_db, completed_manual_goal
):
    from arknights_mower.utils import growth

    stock_db.save_inventory_counts({"技巧概要·卷3": 70})
    syncer.record_path.write_text(
        json.dumps({"data": {"items": [{"id": "3303", "count": 70}]}})
    )
    del completed_manual_goal["data"]["items"]
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = completed_manual_goal
        with pytest.raises(ValueError, match="未返回库存"):
            syncer.start(force_inventory=True)
    cached = json.loads(syncer.record_path.read_text())["data"]
    skills = {"items": {"3303": {"name": "技巧概要·卷3"}}}
    assert "3303" not in growth.inventory_counts(cached, skills, local=True)
    assert "3303" not in growth.inventory_counts(
        cached, skills, local=True, local_counts={}
    )
