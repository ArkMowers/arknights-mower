import base64
import json
import os
import threading
from functools import lru_cache
from hashlib import sha256
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from arknights_mower.utils import config, network_settings, yituliu_sync
from arknights_mower.utils import credential_backup as backups
from arknights_mower.utils import credential_store as store
from arknights_mower.utils import path as paths

PASSWORD = "synthetic backup password"
AAD = b"Arknights Mower credential backup v1 / scrypt-131072-8-1 / AES-256-GCM"
SALT = b"test backup salt"
GROUPS = {
    "main": {
        "MOWER_MAIL_ACCOUNT": "synthetic@example.test",
        "MOWER_MAIL_PASSWORD": "synthetic-mail-password",
        "MOWER_MAIL_RECIPIENTS": ["recipient@example.test"],
        "MOWER_AI_KEY": "synthetic-ai-secret",
        "MOWER_SKLAND_ACCOUNTS": [
            {
                "account": "synthetic-user",
                "password": "synthetic-skland-password",
                "cultivate_select": True,
                "sign_in_official": False,
            }
        ],
    },
    "network": {"MOWER_GITHUB_TOKEN": "github_synthetic_token"},
    "yituliu": {"MOWER_YITULIU_TOKEN": "synthetic-yituliu-token"},
    "ai": {"MOWER_AI_FALLBACK_KEY": "synthetic-fallback-key"},
}


@lru_cache(maxsize=1)
def _package_key():
    return Scrypt(salt=SALT, length=32, n=2**17, r=8, p=1).derive(PASSWORD.encode())


def _package(groups=None, *, payload=None):
    if payload is None:
        payload = json.dumps(
            {"version": 1, "groups": GROUPS if groups is None else groups}
        ).encode()
    nonce = os.urandom(12)
    return json.dumps(
        {
            "format": "mower-credential-backup",
            "version": 1,
            "kdf": "scrypt-131072-8-1",
            "salt": base64.b64encode(SALT).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(
                AESGCM(_package_key()).encrypt(nonce, payload, AAD)
            ).decode(),
        }
    ).encode()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    def select(name="current"):
        root = tmp_path / name
        root.mkdir()
        key = root / "private.key"
        key.write_bytes(base64.b64encode(os.urandom(96)))
        key.chmod(0o600)
        monkeypatch.setenv("MOWER_CREDENTIAL_KEY_FILE", str(key))
        monkeypatch.setattr(paths, "_data_dir", root)
        monkeypatch.setattr(paths, "global_space", "instances/active")
        conf = root / "instances/active/config/conf.yml"
        conf.parent.mkdir(parents=True)
        conf.write_text("theme: dark\n", encoding="utf-8")
        monkeypatch.setattr(config, "conf_path", conf)
        monkeypatch.setattr(config, "app_state_path", conf.with_name("state.json"))
        return SimpleNamespace(
            root=root,
            key=key,
            conf=conf,
            metadata=conf.with_name("yituliu_sync.json"),
            files={
                "main": conf.parent.parent / "mower.secrets.json",
                "network": root / "network.secrets.json",
                "yituliu": conf.parent.parent / "yituliu.secrets.json",
                "ai": root / "ai.secrets.json",
            },
        )

    return select


def _write_groups(workspace, groups=GROUPS):
    for group, values in groups.items():
        store.write_credentials(workspace.files[group], values)


def _snapshot(workspace):
    return {
        group: path.read_bytes() if path.exists() else None
        for group, path in workspace.files.items()
    }


def test_export_has_only_saved_current_business_credentials_and_random_encryption(
    workspace, monkeypatch
):
    local = workspace()
    _write_groups(local)
    store.write_credentials(
        local.files["main"],
        {
            **GROUPS["main"],
            "MOWER_WEBVIEW_TOKEN": "access-token-stays-local",
            "unknown_future_field": "not-in-allowlist",
        },
    )
    profile = local.conf.parent / "profiles" / "saved.secrets.json"
    store.write_credentials(profile, {"MOWER_MAIL_PASSWORD": "profile-secret"})
    monkeypatch.setenv("MOWER_AI_CUSTOM_KEY", "environment-default-stays-local")
    before = _snapshot(local)

    raw = backups.export_credential_backup(PASSWORD)
    second = backups.export_credential_backup(PASSWORD)
    assert raw != second
    envelope = json.loads(raw)
    assert set(envelope) == {"format", "version", "kdf", "salt", "nonce", "ciphertext"}
    key = Scrypt(
        salt=base64.b64decode(envelope["salt"]), length=32, n=2**17, r=8, p=1
    ).derive(PASSWORD.encode())
    payload = json.loads(
        AESGCM(key).decrypt(
            base64.b64decode(envelope["nonce"]),
            base64.b64decode(envelope["ciphertext"]),
            AAD,
        )
    )
    assert payload == {"version": 1, "groups": GROUPS}
    assert b"synthetic-mail-password" not in raw
    assert local.key.read_bytes() not in raw
    assert _snapshot(local) == before


def test_safe_preview_never_opens_local_storage(monkeypatch):
    def forbidden():
        pytest.fail("preview must not inspect local files or configuration")

    monkeypatch.setattr(backups, "_locked_targets", forbidden)
    preview = backups.inspect_credential_backup(_package(), PASSWORD)
    assert preview == {
        "version": 1,
        "groups": [
            {"id": "main", "label": "当前实例业务凭据", "count": 5, "clear_count": 0},
            {
                "id": "yituliu",
                "label": "当前实例一图流 Token",
                "count": 1,
                "clear_count": 0,
            },
            {
                "id": "network",
                "label": "共享 GitHub Token",
                "count": 1,
                "clear_count": 0,
            },
            {"id": "ai", "label": "共享 AI 备用密钥", "count": 1, "clear_count": 0},
        ],
        "field_count": 8,
        "clear_count": 0,
        "preserves_access_token": True,
        "includes_saved_profiles": False,
    }
    assert "synthetic" not in json.dumps(preview)


def test_cross_machine_import_uses_destination_key_and_preserves_configuration(
    workspace,
):
    source = workspace("source")
    _write_groups(source)
    source_raw = _snapshot(source)
    raw = backups.export_credential_backup(PASSWORD)
    target = workspace("destination")
    store.write_credentials(
        target.files["main"],
        {
            "MOWER_WEBVIEW_TOKEN": "destination-access-token",
            "MOWER_MAA_PENGUIN_ID": "retained-id",
        },
    )
    plan = target.conf.with_name("plan.json")
    plan.write_bytes(b'{"synthetic": true}')
    network = target.root / "config/network.json"
    network.parent.mkdir()
    network.write_bytes(b'{"http_proxy":"http://localhost:7890"}')
    originals = {path: path.read_bytes() for path in (target.conf, plan, network)}
    key_before = target.key.read_bytes()
    activated = []

    def activate():
        activated.append(
            {
                group: store.read_credentials(path)
                for group, path in target.files.items()
            }
        )

    result = backups.import_credential_backup(raw, PASSWORD, activate=activate)
    assert result["updated_groups"] == 4
    assert result["preserves_access_token"] is True
    assert activated[0]["main"] == {
        **GROUPS["main"],
        "MOWER_WEBVIEW_TOKEN": "destination-access-token",
        "MOWER_MAA_PENGUIN_ID": "retained-id",
    }
    for group in ("network", "yituliu", "ai"):
        assert store.read_credentials(target.files[group]) == GROUPS[group]
    assert all(path.read_bytes() == before for path, before in originals.items())
    assert target.key.read_bytes() == key_before
    assert _snapshot(source) == source_raw
    assert (
        json.loads(target.files["main"].read_bytes())["key_id"]
        != json.loads(source_raw["main"])["key_id"]
    )


def test_explicit_clear_and_omitted_fields_have_different_results(workspace):
    local = workspace()
    _write_groups(local)
    original_network = local.files["network"].read_bytes()
    raw = _package({"main": {"MOWER_MAIL_PASSWORD": "", "MOWER_MAIL_RECIPIENTS": []}})
    result = backups.import_credential_backup(raw, PASSWORD)
    saved = store.read_credentials(local.files["main"])
    assert saved["MOWER_MAIL_PASSWORD"] == ""
    assert saved["MOWER_MAIL_RECIPIENTS"] == []
    assert saved["MOWER_AI_KEY"] == GROUPS["main"]["MOWER_AI_KEY"]
    assert local.files["network"].read_bytes() == original_network
    assert result["clear_count"] == 2


@pytest.mark.parametrize("password", [None, "short", "x" * 1025, "密" * 342])
def test_invalid_password_rejected_before_reading_files(password, monkeypatch):
    monkeypatch.setattr(
        backups, "_locked_targets", lambda: pytest.fail("read local files")
    )
    with pytest.raises(backups.CredentialBackupError, match="12 个字符"):
        backups.export_credential_backup(password)


def test_unicode_password_counts_characters_and_encoded_bytes(workspace):
    local = workspace()
    _write_groups(local, {"main": {"MOWER_AI_KEY": "synthetic"}})
    password = "备份口令必须保存好不能丢失"
    raw = backups.export_credential_backup(password)
    assert backups.inspect_credential_backup(raw, password)["field_count"] == 1


@pytest.mark.parametrize("mutation", ["wrong-password", "ciphertext", "salt", "nonce"])
def test_authentication_failure_does_not_touch_destination(mutation, workspace):
    local = workspace()
    _write_groups(local)
    before = _snapshot(local)
    envelope = json.loads(_package())
    password = PASSWORD
    if mutation == "wrong-password":
        password = "incorrect synthetic password"
    else:
        raw = bytearray(base64.b64decode(envelope[mutation]))
        raw[0] ^= 1
        envelope[mutation] = base64.b64encode(raw).decode()
    with pytest.raises(backups.CredentialBackupError, match="口令错误或.*已损坏"):
        backups.import_credential_backup(json.dumps(envelope).encode(), password)
    assert _snapshot(local) == before


@pytest.mark.parametrize(
    "change",
    [
        {"version": 2},
        {"version": True},
        {"kdf": "scrypt-999999-8-1"},
        {"n": 2**40},
        {"salt": "AA=="},
    ],
)
def test_untrusted_format_cannot_select_kdf_cost(change, monkeypatch):
    envelope = json.loads(_package())
    envelope.update(change)
    monkeypatch.setattr(
        backups, "_derive", lambda *args: pytest.fail("untrusted KDF parameters")
    )
    with pytest.raises(backups.CredentialBackupError):
        backups.inspect_credential_backup(json.dumps(envelope).encode(), PASSWORD)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not JSON",
        b"{}",
        b"x" * (backups.MAX_BACKUP_BYTES + 1),
        b'{"version":1,"version":1}',
    ],
    ids=["empty", "not-json", "empty-object", "oversize", "duplicate-version"],
)
def test_invalid_outer_file_is_rejected_before_kdf(raw, monkeypatch):
    monkeypatch.setattr(
        backups, "_derive", lambda *args: pytest.fail("invalid file reached KDF")
    )
    with pytest.raises(backups.CredentialBackupError):
        backups.inspect_credential_backup(raw, PASSWORD)


@pytest.mark.parametrize(
    "groups",
    [
        {},
        {"../config/conf.yml": {"MOWER_AI_KEY": "secret"}},
        {"main": {"MOWER_WEBVIEW_TOKEN": "attacker-token"}},
        {"main": {"MOWER_MAIL_PASSWORD": 3}},
        {"main": {"MOWER_MAIL_RECIPIENTS": "not-a-list"}},
        {"main": {"MOWER_MAIL_RECIPIENTS": [2]}},
        {"main": {"MOWER_SKLAND_ACCOUNTS": "not-a-list"}},
        {"main": {"MOWER_SKLAND_ACCOUNTS": ["not-an-account"]}},
        {"main": {"MOWER_SKLAND_ACCOUNTS": [{"password": []}]}},
        {"main": {"MOWER_SKLAND_ACCOUNTS": [{"sign_in_official": "true"}]}},
        {"main": {"MOWER_SKLAND_ACCOUNTS": [{"sign_in_official": 1}]}},
        {"main": {"MOWER_SKLAND_ACCOUNTS": [{"unknown_field": "secret"}]}},
        {"network": {"MOWER_GITHUB_TOKEN": "github token invalid"}},
        {"yituliu": {"MOWER_YITULIU_TOKEN": "invalid"}},
    ],
)
def test_authenticated_invalid_schema_is_rejected_before_opening_targets(
    groups, monkeypatch
):
    monkeypatch.setattr(
        backups, "_locked_targets", lambda: pytest.fail("invalid schema opened files")
    )
    with pytest.raises(backups.CredentialBackupError, match="口令错误或.*已损坏"):
        backups.import_credential_backup(_package(groups), PASSWORD)


def test_duplicate_inner_field_is_rejected(monkeypatch):
    monkeypatch.setattr(
        backups, "_locked_targets", lambda: pytest.fail("duplicate fields opened files")
    )
    payload = b'{"version":1,"groups":{"main":{"MOWER_AI_KEY":"first","MOWER_AI_KEY":"second"}}}'
    with pytest.raises(backups.CredentialBackupError):
        backups.import_credential_backup(_package(payload=payload), PASSWORD)


def test_kdf_unavailable_message_is_not_replaced_by_password_error(monkeypatch):
    def fail(*args):
        raise backups.CredentialBackupError("凭据备份正在处理，请稍后重试")

    monkeypatch.setattr(backups, "_derive", fail)
    with pytest.raises(backups.CredentialBackupError, match="正在处理"):
        backups.inspect_credential_backup(_package(), PASSWORD)


def test_all_destination_files_are_checked_before_first_write(workspace, monkeypatch):
    local = workspace()
    _write_groups(local)
    local.files["ai"].write_bytes(b"corrupt-existing-ciphertext")
    before = _snapshot(local)
    monkeypatch.setattr(
        store,
        "write_credentials",
        lambda *args: pytest.fail("wrote before all targets were validated"),
    )
    with pytest.raises(store.CredentialStoreError):
        backups.import_credential_backup(_package(), PASSWORD)
    assert _snapshot(local) == before


def test_missing_destination_private_key_does_not_replace_any_credentials(workspace):
    local = workspace()
    _write_groups(local)
    before = _snapshot(local)
    local.key.unlink()
    with pytest.raises(store.CredentialStoreError):
        backups.import_credential_backup(_package(), PASSWORD)
    assert _snapshot(local) == before
    assert not local.key.exists()


@pytest.mark.parametrize("failure", ["second-write", "activate"])
def test_failure_restores_exact_ciphertext_and_removes_new_files(
    failure, workspace, monkeypatch
):
    local = workspace()
    store.write_credentials(
        local.files["main"],
        {"MOWER_AI_KEY": "old-value", "MOWER_WEBVIEW_TOKEN": "retained-token"},
    )
    before = _snapshot(local)
    write = store.write_credentials
    attempts = []
    activated = []

    def save(path, values):
        attempts.append(path)
        if failure == "second-write" and len(attempts) == 2:
            raise OSError("synthetic private error must stay hidden")
        write(path, values)

    def activate():
        activated.append(True)
        raise ValueError("synthetic private error must stay hidden")

    monkeypatch.setattr(store, "write_credentials", save)
    with pytest.raises(backups.CredentialBackupError, match="已恢复原文件") as caught:
        backups.import_credential_backup(_package(), PASSWORD, activate=activate)
    assert "synthetic" not in str(caught.value)
    assert _snapshot(local) == before
    assert bool(activated) == (failure == "activate")


def test_first_write_failure_does_not_rewrite_unchanged_files(workspace, monkeypatch):
    local = workspace()
    store.write_credentials(local.files["main"], {"MOWER_AI_KEY": "old"})
    before = _snapshot(local)

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(store, "write_credentials", fail)
    monkeypatch.setattr(
        store,
        "restore_credentials",
        lambda *args: pytest.fail("unchanged file was rewritten"),
    )
    with pytest.raises(backups.CredentialBackupError, match="已恢复原文件"):
        backups.import_credential_backup(_package(), PASSWORD)
    assert _snapshot(local) == before


def test_incomplete_rollback_has_distinct_error(workspace, monkeypatch):
    local = workspace()
    store.write_credentials(local.files["main"], {"MOWER_AI_KEY": "old"})

    def fail(*args):
        raise OSError("synthetic-private-details")

    monkeypatch.setattr(store, "restore_credentials", fail)
    with pytest.raises(backups.CredentialBackupRecoveryError, match="无法完整回滚"):
        backups.import_credential_backup(_package(), PASSWORD, activate=fail)


def test_same_credentials_are_not_reencrypted_but_activation_still_runs(
    workspace, monkeypatch
):
    local = workspace()
    _write_groups(local)
    before = _snapshot(local)
    activated = []
    monkeypatch.setattr(
        store,
        "write_credentials",
        lambda *args: pytest.fail("unchanged values were rewritten"),
    )
    result = backups.import_credential_backup(
        _package(), PASSWORD, activate=lambda: activated.append(True)
    )
    assert result["updated_groups"] == 0
    assert activated == [True]
    assert _snapshot(local) == before


@pytest.mark.parametrize("same_token", [False, True])
def test_yituliu_sync_records_are_invalidated_only_for_changed_token(
    same_token, workspace
):
    local = workspace()
    token = (
        GROUPS["yituliu"]["MOWER_YITULIU_TOKEN"] if same_token else "old-yituliu-token"
    )
    store.write_credentials(local.files["yituliu"], {"MOWER_YITULIU_TOKEN": token})
    metadata = {
        "last_synced_at": 100,
        "last_synced_count": 2,
        "last_synced_fingerprint": "old-fingerprint",
        "last_attempt_at": 101,
        "last_sync_error": "old-error",
        "future_setting": {"enabled": True},
    }
    local.metadata.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    before = local.metadata.read_bytes()
    result = backups.import_credential_backup(
        _package({"yituliu": GROUPS["yituliu"]}), PASSWORD
    )
    assert result["updated_groups"] == (0 if same_token else 1)
    if same_token:
        assert local.metadata.read_bytes() == before
    else:
        assert json.loads(local.metadata.read_bytes()) == {
            "future_setting": {"enabled": True}
        }
        status = yituliu_sync.token_status()
        assert status["configured"] is True
        assert status["last_synced_at"] is None


def test_yituliu_metadata_rolls_back_with_credentials(workspace):
    local = workspace()
    store.write_credentials(
        local.files["yituliu"], {"MOWER_YITULIU_TOKEN": "old-yituliu-token"}
    )
    local.metadata.write_bytes(
        b'{"last_synced_at": 100, "last_synced_fingerprint": "old"}'
    )
    before = _snapshot(local)
    metadata_before = local.metadata.read_bytes()

    def fail():
        assert json.loads(local.metadata.read_bytes()) == {}
        raise RuntimeError("activation failure")

    with pytest.raises(backups.CredentialBackupError, match="已恢复原文件"):
        backups.import_credential_backup(_package(), PASSWORD, activate=fail)
    assert _snapshot(local) == before
    assert local.metadata.read_bytes() == metadata_before


def test_bad_yituliu_metadata_fails_before_writing_credentials(workspace, monkeypatch):
    local = workspace()
    local.metadata.write_bytes(b"not JSON")
    monkeypatch.setattr(
        store,
        "write_credentials",
        lambda *args: pytest.fail("metadata not validated before write"),
    )
    with pytest.raises(backups.CredentialBackupError, match="同步记录无法读取"):
        backups.import_credential_backup(_package(), PASSWORD)


def test_activation_runs_inside_config_and_network_writer_locks(workspace):
    workspace()
    entered = threading.Event()
    released = threading.Event()
    errors = []

    def competing_save():
        try:
            entered.set()
            with config._CONF_WRITE_LOCK, network_settings._environment_lock:
                released.set()
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=competing_save)

    def activate():
        worker.start()
        assert entered.wait(2)
        assert not released.wait(0.05)

    try:
        backups.import_credential_backup(_package(), PASSWORD, activate=activate)
    finally:
        worker.join(timeout=3)
    assert released.is_set()
    assert not worker.is_alive()
    assert not errors


def test_empty_store_does_not_export_launch_environment_defaults(
    workspace, monkeypatch
):
    workspace()
    monkeypatch.setenv("MOWER_AI_KEY", "environment-default")
    with pytest.raises(backups.CredentialBackupError, match="没有可导出"):
        backups.export_credential_backup(PASSWORD)


def test_import_invalidates_old_page_generation_and_creates_redacted_initial_profile(
    workspace,
):
    from arknights_mower.utils import config_backup, config_profiles

    local = workspace()
    assert config_profiles.current_generation() == "0"
    result = backups.import_credential_backup(_package(), PASSWORD)
    assert config_profiles.current_generation() == result["generation"] != "0"
    with pytest.raises(config_profiles.ProfileConflict):
        config_profiles.check_generation("0", allow_legacy=False)
    registry = config_profiles._read_registry()
    profile = config_profiles._profile_path(registry["active_id"])
    with ZipFile(profile) as archive:
        assert archive.comment == config_backup.REDACTED_ARCHIVE_COMMENT
        assert archive.read("config/conf.yml") == local.conf.read_bytes()
        assert not any(name.endswith(".secrets.json") for name in archive.namelist())
    assert not profile.with_suffix(".secrets.json").exists()


def test_existing_profile_snapshot_is_unchanged_when_generation_advances(workspace):
    from arknights_mower.utils import config_profiles

    workspace()
    raw = _package()
    backups.import_credential_backup(raw, PASSWORD)
    registry = config_profiles._read_registry()
    profile = config_profiles._profile_path(registry["active_id"])
    snapshot = profile.read_bytes()
    first_generation = registry["generation"]
    result = backups.import_credential_backup(raw, PASSWORD)
    assert result["generation"] != first_generation
    assert profile.read_bytes() == snapshot
    assert config_profiles._read_registry()["active_id"] == registry["active_id"]


@pytest.mark.parametrize("existing_registry", [False, True])
def test_failed_activation_restores_generation_and_profile_snapshot(
    existing_registry, workspace
):
    from arknights_mower.utils import config_profiles

    local = workspace()
    if existing_registry:
        backups.import_credential_backup(
            _package({"main": {"MOWER_AI_KEY": "before"}}), PASSWORD
        )
    root = config_profiles._root()
    before = (
        {path.name: path.read_bytes() for path in root.iterdir()}
        if root.exists()
        else {}
    )
    credentials = _snapshot(local)
    generation = config_profiles.current_generation()

    def fail():
        assert config_profiles.current_generation() != generation
        raise ValueError("synthetic activation failure")

    with pytest.raises(backups.CredentialBackupError, match="已恢复原文件"):
        backups.import_credential_backup(_package(), PASSWORD, activate=fail)
    assert _snapshot(local) == credentials
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before
    assert config_profiles.current_generation() == generation


def test_partial_generation_write_rolls_back_all_credentials(workspace, monkeypatch):
    from arknights_mower.utils import config_profiles

    local = workspace()
    before = _snapshot(local)
    save = config_profiles._write_registry

    def fail(registry):
        save(registry)
        raise OSError("synthetic index failure after replace")

    monkeypatch.setattr(config_profiles, "_write_registry", fail)
    with pytest.raises(backups.CredentialBackupError, match="已恢复原文件"):
        backups.import_credential_backup(_package(), PASSWORD)
    assert _snapshot(local) == before
    assert list(config_profiles._root().iterdir()) == []


def test_changed_yituliu_token_uploads_even_if_snapshot_was_previously_synced(
    workspace, monkeypatch
):
    from arknights_mower.utils import mastery_recommendation

    local = workspace()
    store.write_credentials(
        local.files["yituliu"], {"MOWER_YITULIU_TOKEN": "previous-yituliu-token"}
    )
    payload = {"uid": "synthetic", "operators": [{"id": "synthetic-operator"}]}
    fingerprint = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    local.metadata.write_text(
        json.dumps({"last_synced_fingerprint": fingerprint, "last_synced_at": 1}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        mastery_recommendation, "get_skill_data", lambda: {"growth": {"characters": {}}}
    )
    monkeypatch.setattr(yituliu_sync, "build_upload_payload", lambda *args: payload)
    uploaded = []

    def upload(data, token):
        uploaded.append((data, token))
        return {
            "success": True,
            "skipped": False,
            "synced_at": 2,
            "count": 1,
            "message": "synthetic success",
        }

    monkeypatch.setattr(yituliu_sync, "_upload", upload)
    before = yituliu_sync.sync_cached_operators(snapshot={})
    assert before["skipped"] is True
    assert uploaded == []
    backups.import_credential_backup(_package({"yituliu": GROUPS["yituliu"]}), PASSWORD)
    result = yituliu_sync.sync_cached_operators(snapshot={})
    assert result["skipped"] is False
    assert uploaded == [(payload, GROUPS["yituliu"]["MOWER_YITULIU_TOKEN"])]


def test_real_activation_preserves_normal_fields_and_validates_skland_models(
    workspace, monkeypatch
):
    from arknights_mower.utils.config.conf import Conf
    from arknights_mower.views.credential_backup import _activate_credentials

    local = workspace()
    current = Conf(
        theme="dark", webview={"token": "existing-access-token", "port": 12345}
    )
    monkeypatch.setattr(config, "conf", current)
    before = current.model_dump(exclude_unset=True)
    before_fields = current.model_fields_set.copy()
    device = current.device
    webview = current.webview
    conf_bytes = local.conf.read_bytes()
    store.write_credentials(
        local.files["main"], {"MOWER_WEBVIEW_TOKEN": "existing-access-token"}
    )
    imported = {
        "main": {
            "MOWER_AI_KEY": "new-ai-key",
            "MOWER_SKLAND_ACCOUNTS": GROUPS["main"]["MOWER_SKLAND_ACCOUNTS"],
        }
    }
    backups.import_credential_backup(
        _package(imported), PASSWORD, activate=_activate_credentials
    )
    assert config.conf.ai_key == "new-ai-key"
    assert config.conf.skland_info[0].account == "synthetic-user"
    assert config.conf.skland_info[0].sign_in_official is False
    assert config.conf.device is device
    assert config.conf.webview is webview
    assert config.conf.model_fields_set == before_fields | {"ai_key", "skland_info"}
    saved = config.conf.model_dump(exclude_unset=True)
    saved.pop("ai_key")
    saved.pop("skland_info")
    assert saved == before
    assert local.conf.read_bytes() == conf_bytes
