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
