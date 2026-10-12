"""Token storage and operator uploads never share Skland credentials or inventories."""

import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests
import yaml
from yamlcore import CoreLoader

from arknights_mower.utils import yituliu_sync as sync
from arknights_mower.utils.config.conf import Conf

TOKEN = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def sync_case(tmp_path, monkeypatch):
    paths = {
        "@app/config/yituliu_sync.json": tmp_path / "sync.json",
        "@app/tmp/cultivate.json": tmp_path / "cultivate.json",
    }
    monkeypatch.setattr(sync, "get_path", lambda name: paths[name])
    monkeypatch.setattr(sync.config, "conf", Conf())
    monkeypatch.setattr(sync.config, "conf_path", tmp_path / "conf.yml")
    session = MagicMock()
    session.__enter__.return_value = session
    response = MagicMock(status_code=200)
    response.__enter__.return_value = response
    response.json.return_value = {
        "code": 200,
        "data": {"createdCount": 1, "updatedCount": 0, "unchangedCount": 0},
    }
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


def saved_settings():
    return sync.config.conf.yituliu_sync.model_dump(
        exclude_none=True, exclude_defaults=True
    )


def saved_conf_file():
    return yaml.load(sync.config.conf_path.read_text("utf-8"), Loader=CoreLoader)


@pytest.fixture
def plan_change(sync_case, tmp_path, monkeypatch, request):
    sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())
    import server

    monkeypatch.setattr(sync.config, "plan_path", tmp_path / "plan.json")
    monkeypatch.setattr(sync.config, "plan", sync.config.PlanModel())
    monkeypatch.setattr(server.app, "token", "local-token", raising=False)
    plan = sync.config.PlanModel(
        plan1={"central": {"plans": [{"agent": "阿米娅"}]}},
        advanced_settings={"drone_count_limit": 140},
    )
    if request.param == "restore":
        import arknights_mower.__main__ as mower_main

        monkeypatch.setattr(
            server, "mower_thread", SimpleNamespace(is_alive=lambda: True)
        )
        monkeypatch.setattr(
            mower_main,
            "base_scheduler",
            SimpleNamespace(source_plan=plan.model_dump(exclude_none=True)),
        )

    def apply():
        with server.app.test_client() as client:
            if request.param == "restore":
                response = client.post(
                    "/plan/restore-running", headers={"token": "local-token"}
                )
                assert response.status_code == 200
            else:
                response = client.post(
                    "/import",
                    headers={"token": "local-token"},
                    data={
                        "img": (BytesIO(plan.model_dump_json().encode()), "plan.json")
                    },
                )
                assert response.get_data(as_text=True) == "排班已加载"
        assert sync.config.conf.drone_count_limit == 140

    return apply


@pytest.mark.parametrize("plan_change", ["import", "restore"], indirect=True)
def test_plan_changes_preserve_pending_token_migration(sync_case, plan_change):
    paths, session, _, _, _ = sync_case
    path = paths["@app/config/yituliu_sync.json"]
    legacy = {"token": TOKEN, "last_synced_at": 123, "last_synced_count": 1}
    path.write_text(json.dumps(legacy))
    plan_change()
    assert sync.token_status()["configured"]
    sync.config.load_conf()
    assert saved_settings() == legacy
    assert not path.exists()
    session.post.assert_not_called()


@pytest.mark.parametrize("private", [None, {}, {"token": TOKEN}])
def test_advanced_settings_preserve_unrelated_values_and_explicit_state(private):
    from arknights_mower.utils.config.plan_advanced import apply_advanced_settings

    original = Conf(account="local-account", webview={"token": "local-auth"})
    if private is not None:
        original.yituliu_sync = type(original.yituliu_sync)(**private)
    # Nested runtime edits remain intact even when the parent is unset.
    original.product_switching.waiting_seconds = 5
    original_fields = original.model_fields_set.copy()
    updated = apply_advanced_settings(original, {"drone_count_limit": 140})
    assert updated.model_dump() == {**original.model_dump(), "drone_count_limit": 140}
    assert updated.model_fields_set == original_fields | {"drone_count_limit"}
    assert (
        updated.yituliu_sync.model_fields_set == original.yituliu_sync.model_fields_set
    )
    updated.webview.token = "changed-auth"
    assert original.webview.token == "local-auth"
    assert original.model_fields_set == original_fields


@pytest.mark.parametrize("plan_change", ["import", "restore"], indirect=True)
@pytest.mark.parametrize("change", ["clear", "replace"])
def test_plan_changes_serialize_token_routes(
    sync_case, plan_change, monkeypatch, change
):
    import server

    sync.save_token(TOKEN)
    attempted = Event()
    acquired = []
    original_lock = sync._lock
    apply_settings = server.apply_advanced_settings

    class ObservedLock:
        def __enter__(self):
            immediate = original_lock.acquire(blocking=False)
            acquired.append(immediate)
            attempted.set()
            if not immediate:
                original_lock.acquire()

        def __exit__(self, *_):
            original_lock.release()

    def change_token():
        with server.app.test_client() as client:
            response = client.open(
                "/growth-sync-token",
                method="DELETE" if change == "clear" else "PUT",
                headers={"token": "local-token"},
                json={"token": "replacement-access-token"},
            )
            assert response.status_code == 200
            assert response.json["configured"] == (change == "replace")

    monkeypatch.setattr(sync, "_lock", ObservedLock())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = None

        def pause_after_copy(conf, settings):
            nonlocal future
            candidate = apply_settings(conf, settings)
            future = pool.submit(change_token)
            assert attempted.wait(5)
            assert acquired[0] is False
            return candidate

        monkeypatch.setattr(server, "apply_advanced_settings", pause_after_copy)
        plan_change()
        future.result(timeout=5)
    sync.config.load_conf()
    assert saved_settings().get("token", "") == (
        "replacement-access-token" if change == "replace" else ""
    )
    assert sync.config.conf.drone_count_limit == 140


def test_save_status_and_clear_are_local_and_never_echo_token(sync_case):
    paths, session, _, _, _ = sync_case
    assert sync.token_status()["configured"] is False
    result = sync.save_token(TOKEN)
    assert result["configured"] is True and TOKEN not in json.dumps(result)
    assert saved_conf_file()["yituliu_sync"]["token"] == TOKEN
    assert not paths["@app/config/yituliu_sync.json"].exists()
    assert sync.token_status() == result
    session.post.assert_not_called()
    assert sync.clear_token()["configured"] is False
    assert saved_conf_file()["yituliu_sync"] == {}
    assert not paths["@app/config/yituliu_sync.json"].exists()
    session.post.assert_not_called()


@pytest.mark.parametrize("action", ["status", "save"])
def test_failed_legacy_migration_preserves_source_until_durable_retry(
    sync_case, monkeypatch, action
):
    paths, _, _, _, _ = sync_case
    path = paths["@app/config/yituliu_sync.json"]
    legacy = {"token": TOKEN, "last_synced_at": 123, "last_synced_count": 1}
    path.write_text(json.dumps(legacy))
    previous = sync.config.conf
    previous_fields = previous.model_fields_set.copy()
    read = sync.token_status if action == "status" else lambda: sync.save_token(TOKEN)
    with monkeypatch.context() as patch:
        patch.setattr(sync.config, "atomic_write", MagicMock(side_effect=OSError()))
        for _ in range(2):
            with pytest.raises(OSError):
                read()
            assert sync.config.conf is previous
            assert previous.model_fields_set == previous_fields
            assert json.loads(path.read_text()) == legacy
            assert not sync.config.conf_path.exists()
    assert read()["last_synced_at"] == 123
    assert not path.exists()
    sync.config.load_conf()
    assert saved_settings() == legacy


@pytest.mark.parametrize("existing_token", [False, True])
@pytest.mark.parametrize("failure", [OSError, RuntimeError])
def test_failed_token_save_restores_model_and_same_token_retry_writes(
    sync_case, monkeypatch, existing_token, failure
):
    if existing_token:
        sync.save_token("previous-access-token")
    previous = sync.config.conf
    previous_fields = previous.model_fields_set.copy()
    previous_file = (
        sync.config.conf_path.read_bytes() if sync.config.conf_path.exists() else None
    )
    with monkeypatch.context() as patch:
        patch.setattr(sync.config, "atomic_write", MagicMock(side_effect=failure()))
        with pytest.raises(failure):
            sync.save_token(TOKEN)
        assert sync.config.conf is previous
        assert previous.model_fields_set == previous_fields
        if previous_file is None:
            assert not sync.config.conf_path.exists()
        else:
            assert sync.config.conf_path.read_bytes() == previous_file
    assert sync.save_token(TOKEN)["configured"]
    sync.config.load_conf()
    assert saved_settings()["token"] == TOKEN


def test_failed_clear_retains_token_and_baseline(sync_case, monkeypatch):
    _, _, _, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    sync.sync_cached_operators(snapshot)
    previous = sync.config.conf
    previous_fields = previous.model_fields_set.copy()
    previous_file = sync.config.conf_path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(sync.config, "atomic_write", MagicMock(side_effect=OSError()))
        with pytest.raises(OSError):
            sync.clear_token()
    assert sync.config.conf is previous
    assert previous.model_fields_set == previous_fields
    assert sync.config.conf_path.read_bytes() == previous_file
    assert sync.token_status()["configured"]
    assert sync.clear_token()["configured"] is False


@pytest.mark.parametrize("action", ["migrate", "save", "clear"])
def test_legacy_cleanup_failure_cannot_override_durable_settings(
    sync_case, monkeypatch, action
):
    paths, session, _, snapshot, _ = sync_case
    path = paths["@app/config/yituliu_sync.json"]
    path.write_text(json.dumps({"token": "old-access-token"}))
    unlink = type(path).unlink

    def fail_legacy_cleanup(target, *args, **kwargs):
        if target == path:
            raise PermissionError()
        return unlink(target, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(type(path), "unlink", fail_legacy_cleanup)
        if action == "migrate":
            assert sync.token_status()["configured"]
            expected = "old-access-token"
        elif action == "save":
            assert sync.save_token(TOKEN)["configured"]
            expected = TOKEN
        else:
            assert sync.clear_token()["configured"] is False
            expected = ""
        assert path.exists()
        sync.config.load_conf()
        assert saved_settings().get("token", "") == expected
        assert sync.token_status()["configured"] == bool(expected)
        if action == "clear":
            assert sync.sync_after_cultivate(snapshot) is None
    sync.token_status()
    assert not path.exists()
    session.post.assert_not_called()


def test_general_config_save_before_migration_preserves_legacy_import(
    sync_case,
):
    from arknights_mower.utils import workshop_config

    paths, _, _, _, _ = sync_case
    path = paths["@app/config/yituliu_sync.json"]
    path.write_text(json.dumps({"token": TOKEN, "last_synced_at": 123}))
    workshop_config.save_user_config({"theme": "dark"})
    assert "yituliu_sync" not in saved_conf_file()
    sync.config.load_conf()
    assert sync.token_status()["last_synced_at"] == 123
    assert saved_conf_file()["yituliu_sync"]["token"] == TOKEN
    assert not path.exists()


def test_failed_sync_record_save_does_not_skip_next_upload(sync_case, monkeypatch):
    _, session, _, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    previous = sync.config.conf
    previous_file = sync.config.conf_path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(sync.config, "atomic_write", MagicMock(side_effect=OSError()))
        result = sync.sync_cached_operators(snapshot)
    assert result["success"] and "本地同步记录未能保存" in result["message"]
    assert sync.config.conf is previous
    assert "last_synced_fingerprint" not in saved_settings()
    assert sync.config.conf_path.read_bytes() == previous_file
    assert not sync.sync_cached_operators(snapshot).get("skipped")
    assert session.post.call_count == 2
    sync.config.load_conf()
    assert sync.sync_cached_operators(snapshot)["skipped"]
    assert session.post.call_count == 2


@pytest.mark.parametrize("change", ["clear", "replace", "upload"])
def test_general_config_save_serializes_token_and_baseline_changes(
    sync_case, monkeypatch, change
):
    from arknights_mower.utils import workshop_config

    _, _, _, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    attempted = Event()
    acquired = []
    original_lock = sync._lock

    class ObservedLock:
        def __enter__(self):
            immediate = original_lock.acquire(blocking=False)
            acquired.append(immediate)
            attempted.set()
            if not immediate:
                original_lock.acquire()

        def __exit__(self, *_):
            original_lock.release()

    monkeypatch.setattr(sync, "_lock", ObservedLock())
    initialize = workshop_config.initialize_manual_settings
    actions = {
        "clear": sync.clear_token,
        "replace": lambda: sync.save_token("replacement-access-token"),
        "upload": lambda: sync.sync_cached_operators(snapshot),
    }
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = None

        def pause_after_copy(conf):
            nonlocal future
            future = pool.submit(actions[change])
            assert attempted.wait(5)
            assert acquired[0] is False
            return initialize(conf)

        monkeypatch.setattr(
            workshop_config, "initialize_manual_settings", pause_after_copy
        )
        workshop_config.save_user_config({"theme": "dark"})
        assert future.result(timeout=5)
    sync.config.load_conf()
    assert sync.config.conf.theme == "dark"
    if change == "clear":
        assert sync.token_status()["configured"] is False
        assert sync.sync_after_cultivate(snapshot) is None
    elif change == "replace":
        assert saved_settings()["token"] == "replacement-access-token"
    else:
        assert sync.sync_cached_operators(snapshot)["skipped"]


@pytest.mark.parametrize(
    "token", [None, {}, "short", "valid-looking-token\nAuthorization: bad"]
)
def test_invalid_tokens_cannot_be_stored_or_sent(sync_case, token):
    paths, session, _, _, _ = sync_case
    with pytest.raises(ValueError):
        sync.save_token(token)
    assert not sync.config.conf_path.exists()
    assert not paths["@app/config/yituliu_sync.json"].exists()
    session.post.assert_not_called()


def test_payload_matches_documented_fields_and_potential_index(sync_case):
    _, _, _, snapshot, definitions = sync_case
    original = copy.deepcopy(snapshot)
    body = sync.build_upload_payload(snapshot, definitions)
    assert set(body) == {"playerInfo", "operators"}
    assert body["playerInfo"] == {"akUid": "12345678"}
    assert body["operators"] == [
        {
            "id": "char_test",
            "level": 90,
            "evolvePhase": 2,
            "potentialRank": 5,
            "rarity": 6,
            "mainSkillLevel": 7,
            "skill1": 8,
            "skill2": 10,
            "skill3": 0,
            "equipX": 2,
            "equipY": 0,
            "equipD": 0,
            "equipA": 0,
            "equipB": 0,
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
        headers={"Authorization": f"Bearer {TOKEN}"},
        json=sync.build_upload_payload(snapshot, definitions),
        timeout=(3, 15),
        allow_redirects=False,
    )
    assert session.trust_env is False
    assert TOKEN not in json.dumps(result)
    assert sync.token_status()["last_sync_error"] is None
    assert sync.token_status()["last_synced_count"] == 1
    assert saved_conf_file()["yituliu_sync"]["last_synced_count"] == 1
    assert not paths["@app/config/yituliu_sync.json"].exists()
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
        session.post.call_args.kwargs["json"]["playerInfo"]["akUid"]
        == snapshot["_mower_player"]["uid"]
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
    _, _, _, snapshot, _ = sync_case
    syncer = SimpleNamespace(yituliu_sync_result=None)

    def refresh():
        syncer.yituliu_sync_result = sync.sync_after_cultivate(snapshot)
        return True

    syncer.start = MagicMock(side_effect=refresh)
    monkeypatch.setitem(
        sys.modules,
        "arknights_mower.solvers.cultivate_depot",
        SimpleNamespace(cultivate=lambda: syncer),
    )
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
    syncer.start.assert_called_once_with()
    assert (
        client.delete("/growth-sync-token", headers=headers).json["configured"] is False
    )


def test_general_configuration_route_boundary_does_not_expose_or_edit_token(sync_case):
    from arknights_mower.utils import workshop_config

    sync.save_token(TOKEN)
    visible = workshop_config.read_user_config()
    assert "yituliu_sync" not in visible
    workshop_config.save_user_config(
        {"theme": "dark", "yituliu_sync": {"token": "replacement-token"}}
    )
    assert sync.token_status()["configured"] is True
    assert saved_settings()["token"] == TOKEN


@pytest.mark.parametrize("automatic", [False, True])
def test_identical_confirmed_payload_skips_manual_and_automatic_network(
    sync_case, automatic
):
    paths, session, _, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    first = sync.sync_cached_operators()
    # Re-reading persisted settings exercises the baseline used after a restart.
    saved = saved_settings()
    assert len(saved["last_synced_fingerprint"]) == 64
    result = (
        sync.sync_after_cultivate(snapshot)
        if automatic
        else sync.sync_cached_operators()
    )
    assert result["success"] and result["skipped"]
    assert result["synced_at"] == first["synced_at"]
    assert result["count"] == 1
    assert "未传输" in result["message"]
    assert sync.token_status()["last_synced_at"] == first["synced_at"]
    assert "fingerprint" not in json.dumps(sync.token_status())
    session.post.assert_called_once()


def test_order_inventory_and_snapshot_timestamps_do_not_trigger_upload(sync_case):
    _, session, response, snapshot, definitions = sync_case
    response.json.return_value["data"]["createdCount"] = 2
    second = copy.deepcopy(snapshot["data"]["characters"][0])
    second["id"] = "char_second"
    definitions["char_second"] = copy.deepcopy(definitions["char_test"])
    snapshot["data"]["characters"].append(second)
    sync.save_token(TOKEN)
    sync.sync_cached_operators(snapshot)
    snapshot["data"]["characters"].reverse()
    snapshot["data"]["items"][0]["count"] += 1
    snapshot["_mower_inventory_observed_at"] = 12345
    snapshot["_mower_player"]["cred"] = "different-secret"
    assert sync.sync_cached_operators(snapshot)["skipped"]
    session.post.assert_called_once()


@pytest.mark.parametrize(
    "field",
    [
        "level",
        "elite",
        "potential",
        "basic",
        "skill",
        "module",
        "uid",
        "rarity",
    ],
)
def test_changed_upload_fields_transmit_again(sync_case, field):
    _, session, _, snapshot, definitions = sync_case
    sync.save_token(TOKEN)
    sync.sync_cached_operators(snapshot)
    char = snapshot["data"]["characters"][0]
    if field == "level":
        char["level"] = 89
    elif field == "elite":
        char["evolvePhase"] = 1
    elif field == "potential":
        char["potentialRank"] = 4
    elif field == "basic":
        char["mainSkillLevel"] = 6
    elif field == "skill":
        char["skills"][0]["level"] = 2
    elif field == "module":
        char["equips"][1]["level"] = 3
    elif field == "uid":
        snapshot["_mower_player"]["uid"] = "87654321"
    else:
        definitions["char_test"]["rarity"] = 5
    assert not sync.sync_cached_operators(snapshot).get("skipped")
    assert session.post.call_count == 2
    assert sync.sync_cached_operators(snapshot)["skipped"]
    assert session.post.call_count == 2


def test_failed_changed_upload_preserves_baseline_and_can_retry(sync_case):
    paths, session, _, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    sync.sync_cached_operators(snapshot)
    first = saved_settings()
    snapshot["data"]["characters"][0]["level"] = 89
    session.post.side_effect = requests.Timeout()
    assert not sync.sync_after_cultivate(snapshot)["success"]
    failed = saved_settings()
    assert failed["last_synced_fingerprint"] == first["last_synced_fingerprint"]
    session.post.side_effect = None
    assert not sync.sync_cached_operators(snapshot).get("skipped")
    assert session.post.call_count == 3


def test_payload_validation_happens_before_deduplication(sync_case):
    _, session, _, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    sync.sync_cached_operators(snapshot)
    snapshot["data"]["characters"][0]["level"] = True
    with pytest.raises(ValueError, match="等级无效"):
        sync.sync_cached_operators(snapshot)
    session.post.assert_called_once()


def test_same_token_preserves_baseline_and_replacement_or_clear_resets_it(sync_case):
    _, session, _, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    sync.sync_cached_operators(snapshot)
    sync.save_token("  " + TOKEN + "  ")
    assert sync.sync_cached_operators(snapshot)["skipped"]
    session.post.assert_called_once()
    replacement = "abcdef0123456789abcdef0123456789"
    sync.save_token(replacement)
    assert not sync.sync_cached_operators(snapshot).get("skipped")
    assert session.post.call_args.kwargs["headers"] == {
        "Authorization": f"Bearer {replacement}"
    }
    sync.clear_token()
    sync.save_token(replacement)
    assert not sync.sync_cached_operators(snapshot).get("skipped")
    assert session.post.call_count == 3


def test_concurrent_identical_sync_requests_upload_once(sync_case):
    from concurrent.futures import ThreadPoolExecutor

    _, session, _, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(
            workers.map(lambda _: sync.sync_cached_operators(snapshot), range(2))
        )
    assert all(result["success"] for result in results)
    assert sum(bool(result.get("skipped")) for result in results) == 1
    session.post.assert_called_once()


def test_saving_token_repairs_unreadable_settings(sync_case):
    paths, session, _, _, _ = sync_case
    paths["@app/config/yituliu_sync.json"].write_text("invalid-json")
    assert sync.save_token(TOKEN)["configured"]
    assert saved_conf_file()["yituliu_sync"]["token"] == TOKEN
    assert not paths["@app/config/yituliu_sync.json"].exists()
    session.post.assert_not_called()


def test_first_failed_upload_cannot_establish_deduplication_baseline(sync_case):
    paths, session, response, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    response.json.return_value = {"code": 403}
    assert not sync.sync_after_cultivate(snapshot)["success"]
    saved = saved_settings()
    assert "last_synced_fingerprint" not in saved
    response.json.return_value = {
        "code": 200,
        "data": {"createdCount": 1, "updatedCount": 0, "unchangedCount": 0},
    }
    assert not sync.sync_cached_operators(snapshot).get("skipped")
    assert session.post.call_count == 2


@pytest.mark.parametrize(
    "confirmation",
    [
        {"code": 200},
        {
            "code": 200.0,
            "data": {"createdCount": 1, "updatedCount": 0, "unchangedCount": 0},
        },
        {"code": 200, "data": None},
        {
            "code": 200,
            "data": {"createdCount": 0, "updatedCount": 0, "unchangedCount": 0},
        },
        {
            "code": 200,
            "data": {"createdCount": True, "updatedCount": 0, "unchangedCount": 0},
        },
        {
            "code": 200,
            "data": {"createdCount": -1, "updatedCount": 2, "unchangedCount": 0},
        },
        {
            "code": 200,
            "data": {"createdCount": "1", "updatedCount": 0, "unchangedCount": 0},
        },
    ],
)
def test_invalid_confirmation_never_advances_success_baseline(sync_case, confirmation):
    _, session, response, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    sync.sync_cached_operators(snapshot)
    first = saved_settings()
    snapshot["data"]["characters"][0]["level"] -= 1
    response.json.return_value = confirmation
    result = sync.sync_after_cultivate(snapshot)
    assert not result["success"]
    saved = saved_settings()
    assert saved["last_synced_fingerprint"] == first["last_synced_fingerprint"]
    assert saved["last_synced_at"] == first["last_synced_at"]
    assert session.post.call_count == 2


@pytest.mark.parametrize(
    "code, expected",
    [
        (80001, "失效"),
        (80008, "gama-data.write"),
        (10002, "字段"),
        (30006, "2 秒"),
        (40003, "限流服务"),
        (40004, "冲突"),
        (40001, "繁忙"),
    ],
)
def test_oauth_business_errors_are_actionable_without_retry_or_remote_echo(
    sync_case, code, expected, caplog
):
    paths, session, response, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    response.json.return_value = {
        "code": code,
        "msg": TOKEN,
        "data": {"retryAfterSeconds": 2},
    }
    result = sync.sync_after_cultivate(snapshot)
    assert not result["success"] and expected in result["message"]
    assert TOKEN not in json.dumps(result) + caplog.text
    assert "last_synced_fingerprint" not in saved_settings()
    session.post.assert_called_once()


def test_oauth_target_and_legacy_baseline_migration(sync_case):
    paths, session, _, snapshot, _ = sync_case
    assert (
        sync.UPLOAD_URL == "https://auth.yituliu.cn/oauth2/ak-accounts/operators/save"
    )
    paths["@app/config/yituliu_sync.json"].write_text(
        json.dumps(
            {
                "token": TOKEN,
                "last_synced_fingerprint": "legacy-payload-digest",
                "last_synced_at": 1,
            }
        )
    )
    assert not sync.sync_cached_operators(snapshot).get("skipped")
    assert not paths["@app/config/yituliu_sync.json"].exists()
    assert saved_conf_file()["yituliu_sync"]["token"] == TOKEN
    assert sync.sync_cached_operators(snapshot)["skipped"]
    session.post.assert_called_once()


def test_only_bound_uid_is_required_and_untransmitted_identity_does_not_upload(
    sync_case,
):
    _, session, _, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    sync.sync_cached_operators(snapshot)
    snapshot["_mower_player"] = {"uid": "12345678"}
    assert sync.sync_cached_operators(snapshot)["skipped"]
    snapshot["_mower_player"].update(nickName="changed", channelMasterId="2")
    assert sync.sync_cached_operators(snapshot)["skipped"]
    session.post.assert_called_once()


@pytest.mark.parametrize(
    "basic, mastery, expected",
    [(1, 0, 1), (6, 0, 6), (7, 0, 7), (7, 1, 8), (7, 2, 9), (7, 3, 10)],
)
def test_oauth_skill_levels_and_zero_based_potential(
    sync_case, basic, mastery, expected
):
    _, _, _, snapshot, definitions = sync_case
    char = snapshot["data"]["characters"][0]
    char.update(
        mainSkillLevel=basic, potentialRank=0, skills=[{"id": "s1", "level": mastery}]
    )
    row = sync.build_upload_payload(snapshot, definitions)["operators"][0]
    assert row["skill1"] == expected
    assert row["skill2"] == row["skill3"] == 0
    assert row["potentialRank"] == 0


@pytest.mark.parametrize("cid", ["", "a" * 65, "char test", "char_中文", "char_\n"])
def test_invalid_operator_ids_are_rejected_before_network(sync_case, cid):
    _, session, _, snapshot, definitions = sync_case
    definitions[cid] = definitions.pop("char_test")
    snapshot["data"]["characters"][0]["id"] = cid
    sync.save_token(TOKEN)
    assert not sync.sync_after_cultivate(snapshot)["success"]
    session.post.assert_not_called()


def test_manual_sync_refreshes_skland_before_single_upload_and_uses_new_roster(
    sync_case, monkeypatch
):
    _, session, _, snapshot, _ = sync_case
    sync.save_token(TOKEN)
    fresh = copy.deepcopy(snapshot)
    fresh["data"]["characters"][0]["level"] = 80
    syncer = SimpleNamespace(yituliu_sync_result=None)

    def refresh():
        session.post.assert_not_called()
        syncer.yituliu_sync_result = sync.sync_after_cultivate(fresh)
        return True

    syncer.start = MagicMock(side_effect=refresh)
    monkeypatch.setitem(
        sys.modules,
        "arknights_mower.solvers.cultivate_depot",
        SimpleNamespace(cultivate=lambda: syncer),
    )
    assert sync.refresh_and_sync_operators()["success"]
    syncer.start.assert_called_once_with()
    session.post.assert_called_once()
    assert session.post.call_args.kwargs["json"]["operators"][0]["level"] == 80


@pytest.mark.parametrize("outcome", [False, ValueError("must-not-expose-credential")])
def test_manual_refresh_failure_never_uploads_old_cache(
    sync_case, monkeypatch, outcome
):
    _, session, _, _, _ = sync_case
    sync.save_token(TOKEN)
    before = sync.token_status()
    start = (
        MagicMock(side_effect=outcome)
        if isinstance(outcome, Exception)
        else MagicMock(return_value=outcome)
    )
    syncer = SimpleNamespace(start=start, yituliu_sync_result=None)
    monkeypatch.setitem(
        sys.modules,
        "arknights_mower.solvers.cultivate_depot",
        SimpleNamespace(cultivate=lambda: syncer),
    )
    with pytest.raises(ValueError, match="未上传旧缓存") as error:
        sync.refresh_and_sync_operators()
    assert "must-not-expose" not in str(error.value)
    session.post.assert_not_called()
    assert sync.token_status() == before


def test_manual_sync_without_oauth_token_does_not_start_refresh(sync_case, monkeypatch):
    factory = MagicMock()
    monkeypatch.setitem(
        sys.modules,
        "arknights_mower.solvers.cultivate_depot",
        SimpleNamespace(cultivate=factory),
    )
    with pytest.raises(ValueError, match="先保存"):
        sync.refresh_and_sync_operators()
    factory.assert_not_called()
