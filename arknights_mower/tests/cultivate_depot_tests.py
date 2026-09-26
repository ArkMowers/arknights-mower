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
        module.config,
        "conf",
        SimpleNamespace(skland_info=[SimpleNamespace(cultivate_select=True)]),
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
    payload["data"]["items"][0]["count"] = "290"
    with patch.object(module, "request_with_retry") as get:
        get.return_value.json.return_value = payload
        assert syncer.start() is True
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
