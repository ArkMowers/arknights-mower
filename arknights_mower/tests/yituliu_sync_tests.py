"""Token storage and operator uploads never share Skland credentials or inventories."""

import copy
import json
import stat
import sys
from unittest.mock import MagicMock

import pytest
import requests

from arknights_mower.utils import yituliu_sync as sync

TOKEN = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def sync_case(tmp_path, monkeypatch):
    paths = {
        "@app/config/yituliu_sync.json": tmp_path / "sync.json",
        "@app/tmp/cultivate.json": tmp_path / "cultivate.json",
    }
    monkeypatch.setattr(sync, "get_path", lambda name: paths[name])
    session = MagicMock()
    session.__enter__.return_value = session
    response = MagicMock(status_code=200)
    response.__enter__.return_value = response
    response.json.return_value = {"code": 200, "data": {"affectedRows": 1}}
    session.post.return_value = response
    monkeypatch.setattr(sync.requests, "Session", lambda: session)
    snapshot = {
        "_mower_player": {
            "uid": "12345678",
            "nickName": "测试",
            "channelName": "官服",
            "channelMasterId": "1",
            "cred": "must-not-upload",
        },
        "data": {
            "characters": [
                {
                    "id": "char_test",
                    "level": 90,
                    "evolvePhase": 2,
                    "potentialRank": 5,
                    "mainSkillLevel": 7,
                    "skills": [{"id": "s1", "level": 1}, {"id": "s2", "level": 3}],
                    "equips": [
                        {"id": "uniequip_001_test", "level": 1},
                        {"id": "module_x", "level": 2},
                    ],
                    "secret": "must-not-upload",
                }
            ],
            "items": [{"id": "private-stock", "count": 999}],
        },
        "token": "must-not-upload",
    }
    definitions = {
        "char_test": {"rarity": 6, "modules": [{"id": "module_x", "type": "DRE-X"}]}
    }
    paths["@app/tmp/cultivate.json"].write_text(json.dumps(snapshot))
    from arknights_mower.utils import mastery_recommendation

    monkeypatch.setattr(
        mastery_recommendation,
        "get_skill_data",
        lambda: {"growth": {"characters": definitions}},
    )
    return paths, session, response, snapshot, definitions


def test_save_status_and_clear_are_local_and_never_echo_token(sync_case):
    paths, session, _, _, _ = sync_case
    assert sync.token_status()["configured"] is False
    result = sync.save_token(TOKEN)
    assert result["configured"] is True and TOKEN not in json.dumps(result)
    assert stat.S_IMODE(paths["@app/config/yituliu_sync.json"].stat().st_mode) == 0o600
    assert sync.token_status() == result
    session.post.assert_not_called()
    assert sync.clear_token()["configured"] is False
    assert not paths["@app/config/yituliu_sync.json"].exists()
    session.post.assert_not_called()


@pytest.mark.parametrize(
    "token", [None, {}, "short", "valid-looking-token\nAuthorization: bad"]
)
def test_invalid_tokens_cannot_be_stored_or_sent(sync_case, token):
    paths, session, _, _, _ = sync_case
    with pytest.raises(ValueError):
        sync.save_token(token)
    assert not paths["@app/config/yituliu_sync.json"].exists()
    session.post.assert_not_called()


def test_payload_matches_documented_fields_and_potential_index(sync_case):
    _, _, _, snapshot, definitions = sync_case
    original = copy.deepcopy(snapshot)
    body = sync.build_upload_payload(snapshot, definitions)
    assert set(body) == {
        "uid",
        "nickName",
        "channelName",
        "channelMasterId",
        "operatorDataList",
    }
    assert body["operatorDataList"] == [
        {
            "charId": "char_test",
            "own": True,
            "level": 90,
            "elite": 2,
            "potential": 6,
            "rarity": 6,
            "mainSkill": 7,
            "skill1": 1,
            "skill2": 3,
            "skill3": 0,
            "modX": 2,
            "modY": 0,
            "modD": 0,
            "modA": 0,
            "modB": 0,
        }
    ]
    assert "must-not-upload" not in json.dumps(body)
    assert "private-stock" not in json.dumps(body)
    assert snapshot == original


def test_old_cache_requires_refresh_without_guessing_account(sync_case):
    _, session, _, snapshot, definitions = sync_case
    del snapshot["_mower_player"]
    with pytest.raises(ValueError, match="重新同步一次森空岛"):
        sync.build_upload_payload(snapshot, definitions)
    session.post.assert_not_called()


def test_explicit_sync_sends_only_fixed_target_header_and_whitelisted_snapshot(
    sync_case,
):
    paths, session, _, snapshot, definitions = sync_case
    sync.save_token(TOKEN)
    original = paths["@app/tmp/cultivate.json"].read_text()
    result = sync.sync_cached_operators()
    assert result["success"] and result["count"] == 1
    session.post.assert_called_once_with(
        sync.UPLOAD_URL,
        headers={"Authorization": TOKEN},
        json=sync.build_upload_payload(snapshot, definitions),
        timeout=(3, 15),
        allow_redirects=False,
    )
    assert session.trust_env is False
    assert TOKEN not in json.dumps(result)
    assert sync.token_status()["last_sync_error"] is None
    assert sync.token_status()["last_synced_count"] == 1
    assert stat.S_IMODE(paths["@app/config/yituliu_sync.json"].stat().st_mode) == 0o600
    assert paths["@app/tmp/cultivate.json"].read_text() == original


def test_no_token_automatic_refresh_is_a_noop(sync_case):
    _, session, _, snapshot, _ = sync_case
    assert sync.sync_after_cultivate(snapshot) is None
    session.post.assert_not_called()


def test_automatic_refresh_uses_passed_snapshot_once_without_reading_newer_cache(
    sync_case,
):
    paths, session, _, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    paths["@app/tmp/cultivate.json"].write_text("a concurrent refresh changed the file")
    assert sync.sync_after_cultivate(snapshot)["success"] is True
    session.post.assert_called_once()
    assert (
        session.post.call_args.kwargs["json"]["uid"] == snapshot["_mower_player"]["uid"]
    )


@pytest.mark.parametrize("failure", ["timeout", "remote_error", "invalid_json"])
def test_failed_upload_preserves_snapshot_and_records_sanitized_status(
    sync_case, failure, caplog
):
    paths, session, response, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    original = paths["@app/tmp/cultivate.json"].read_text()
    if failure == "timeout":
        session.post.side_effect = requests.Timeout(TOKEN)
    elif failure == "remote_error":
        response.json.return_value = {"code": 403, "msg": TOKEN}
    else:
        response.json.side_effect = ValueError(TOKEN)
    result = sync.sync_after_cultivate(snapshot)
    assert result["success"] is False and result["message"]
    assert sync.token_status()["last_sync_error"] == result["message"]
    assert (
        TOKEN not in json.dumps(result) + json.dumps(sync.token_status()) + caplog.text
    )
    assert paths["@app/tmp/cultivate.json"].read_text() == original
    session.post.assert_called_once()


def test_missing_module_metadata_rejects_partial_upload(sync_case):
    _, session, _, snapshot, definitions = sync_case
    definitions["char_test"]["modules"] = []
    sync.save_token(TOKEN)
    result = sync.sync_after_cultivate(snapshot)
    assert result["success"] is False and "模组资源缺失" in result["message"]
    session.post.assert_not_called()


def test_token_and_sync_routes_require_local_auth_and_explicit_manual_action(
    sync_case, monkeypatch
):
    sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())
    import server

    monkeypatch.setattr(server.app, "token", "local-token", raising=False)
    client = server.app.test_client()
    headers = {"token": "local-token"}
    assert client.put("/growth-sync-token", json={"token": TOKEN}).status_code == 403
    response = client.put("/growth-sync-token", json={"token": TOKEN}, headers=headers)
    assert response.status_code == 200 and TOKEN not in response.text
    assert TOKEN not in client.get("/growth-sync-token", headers=headers).text
    assert client.post("/growth-sync", json={}, headers=headers).status_code == 400
    assert client.get("/growth-sync", headers=headers).status_code in (404, 405)
    assert client.post("/growth-sync", json={"confirmed": True}, headers=headers).json[
        "success"
    ]
    assert (
        client.delete("/growth-sync-token", headers=headers).json["configured"] is False
    )
