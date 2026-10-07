import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Importing the real sign-in helper performs network work; all sync tests are local.
sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())
from arknights_mower.solvers import cultivate_depot as module  # noqa: E402


@pytest.fixture
def syncer(tmp_path, monkeypatch):
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

    def start():
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
            SimpleNamespace(
                json=lambda phase=phase: {
                    "code": 0,
                    "data": {
                        "characters": [{"id": "char_2027_wang", "evolvePhase": phase}]
                    },
                }
            )
            for phase in (1, 2)
        ]
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(syncer.start)
            try:
                assert uploading.wait(5)
                second = workers.submit(module.cultivate().start)
                assert waiting.wait(5)
                assert get.call_count == 1
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
