"""Credential transfer requires authorization before parsing or touching storage."""

from io import BytesIO
from unittest.mock import Mock

import pytest
from flask import Flask

from arknights_mower.views import credential_backup as routes


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.token = "synthetic-session-token"
    app.register_blueprint(routes.credential_backup_bp)
    app.config["CONFIG_PROFILES_BUSY"] = lambda: False
    app.config["CREDENTIALS_ACTIVATED"] = lambda: None
    monkeypatch.setattr(routes.profiles, "current_generation", lambda: "current")
    return app.test_client()


def headers(**extra):
    return {
        "token": "synthetic-session-token",
        "X-Mower-Settings": "1",
        "X-Mower-Config-Generation": "current",
        **extra,
    }


@pytest.mark.parametrize("path", ["export", "preview", "import"])
@pytest.mark.parametrize("auth", [{}, {"token": "wrong"}])
def test_unauthorized_never_reads_inputs_or_storage(client, monkeypatch, path, auth):
    called = Mock(side_effect=AssertionError("unauthorized work"))
    for name in (
        "export_credential_backup",
        "inspect_credential_backup",
        "import_credential_backup",
    ):
        monkeypatch.setattr(routes.backups, name, called)
    monkeypatch.setattr(routes, "_upload", called)
    response = client.post(f"/credential-backup/{path}", data=b"invalid", headers=auth)
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "no-store"
    called.assert_not_called()


@pytest.mark.parametrize("path", ["export", "preview", "import"])
def test_settings_header_required(client, path):
    response = client.post(
        f"/credential-backup/{path}", headers={"token": "synthetic-session-token"}
    )
    assert response.status_code == 403


def test_export_uses_post_password_body_no_cache(client, monkeypatch):
    export = Mock(return_value=b"encrypted-backup")
    monkeypatch.setattr(routes.backups, "export_credential_backup", export)
    response = client.post(
        "/credential-backup/export",
        json={"password": "synthetic-passphrase"},
        headers=headers(),
    )
    assert response.status_code == 200
    assert response.data == b"encrypted-backup"
    assert "attachment" in response.headers["Content-Disposition"]
    assert ".mower-credentials" in response.headers["Content-Disposition"]
    assert response.headers["Cache-Control"] == "no-store"
    export.assert_called_once_with("synthetic-passphrase")


def upload(**extra):
    return {
        "backup": (BytesIO(b"encrypted"), "backup.mower-credentials"),
        "password": "synthetic-passphrase",
        **extra,
    }


def test_preview_and_confirmed_import_have_distinct_effects(client, monkeypatch):
    preview = Mock(
        return_value={"groups": [{"id": "main", "label": "当前档案", "count": 1}]}
    )
    imported = Mock(return_value={"field_count": 1})
    monkeypatch.setattr(routes.backups, "inspect_credential_backup", preview)
    monkeypatch.setattr(routes.backups, "import_credential_backup", imported)
    response = client.post(
        "/credential-backup/preview", data=upload(), headers=headers()
    )
    assert response.status_code == 200
    assert response.json["groups"][0]["count"] == 1
    imported.assert_not_called()
    response = client.post(
        "/credential-backup/import", data=upload(), headers=headers()
    )
    assert response.status_code == 400
    imported.assert_not_called()
    response = client.post(
        "/credential-backup/import", data=upload(confirmed="1"), headers=headers()
    )
    assert response.status_code == 200
    assert response.json["ok"] is True
    assert "排班和其他配置保持不变" in response.json["message"]
    imported.assert_called_once_with(
        b"encrypted",
        "synthetic-passphrase",
        activate=client.application.config["CREDENTIALS_ACTIVATED"],
    )


@pytest.mark.parametrize("condition", ["busy", "stale", "missing_generation"])
def test_import_admission_preserves_storage(client, monkeypatch, condition):
    imported = Mock()
    monkeypatch.setattr(routes.backups, "import_credential_backup", imported)
    auth = headers()
    if condition == "busy":
        client.application.config["CONFIG_PROFILES_BUSY"] = lambda: True
    elif condition == "stale":
        auth["X-Mower-Config-Generation"] = "old"
    else:
        auth.pop("X-Mower-Config-Generation")
    response = client.post(
        "/credential-backup/import", data=upload(confirmed="1"), headers=auth
    )
    assert response.status_code == 409
    imported.assert_not_called()


def test_oversized_upload_rejected_before_parsing(client, monkeypatch):
    monkeypatch.setattr(routes.backups, "MAX_BACKUP_BYTES", 1)
    response = client.post(
        "/credential-backup/preview", data=b"x" * 65538, headers=headers()
    )
    assert response.status_code == 413
    assert "4 MiB" in response.json["message"]


def test_storage_errors_do_not_return_paths_or_secrets(client, monkeypatch):
    def fail(password):
        raise OSError("secret value in filename")

    monkeypatch.setattr(routes.backups, "export_credential_backup", fail)
    response = client.post(
        "/credential-backup/export",
        json={"password": "synthetic-passphrase"},
        headers=headers(),
    )
    assert response.status_code == 500
    assert "secret value" not in response.get_data(as_text=True)


def test_multipart_file_above_parser_buffer_size_is_accepted(client, monkeypatch):
    raw = b"synthetic ciphertext" * 8192
    inspect = Mock(return_value={"groups": []})
    monkeypatch.setattr(routes.backups, "inspect_credential_backup", inspect)
    response = client.post(
        "/credential-backup/preview",
        data={
            "backup": (BytesIO(raw), "backup.mower-credentials"),
            "password": "synthetic-passphrase",
        },
        headers=headers(),
    )
    assert response.status_code == 200
    inspect.assert_called_once_with(raw, "synthetic-passphrase")


def test_real_server_preserves_manager_import_permission(monkeypatch):
    import server
    from arknights_mower.utils import config

    monkeypatch.setenv("MOWER_MANAGED", "1")
    monkeypatch.setattr(server.app, "token", "synthetic-session-token", raising=False)
    monkeypatch.setattr(
        config, "conf", config.conf.model_copy(update={"extra_settings_visible": False})
    )
    imported = Mock(side_effect=AssertionError("manager-disallowed import"))
    monkeypatch.setattr(routes.backups, "import_credential_backup", imported)
    response = server.app.test_client().post(
        "/credential-backup/import", headers=headers()
    )
    assert response.status_code == 403
    assert response.json["error"] == "manager_owned_setting"
    imported.assert_not_called()


def test_incomplete_rollback_is_uncertain_failure(client, monkeypatch):
    def fail(*args, **kwargs):
        raise routes.backups.CredentialBackupRecoveryError("无法完整回滚")

    monkeypatch.setattr(routes.backups, "import_credential_backup", fail)
    response = client.post(
        "/credential-backup/import", data=upload(confirmed="1"), headers=headers()
    )
    assert response.status_code == 500
    assert response.headers["Cache-Control"] == "no-store"
    assert "无法完整回滚" in response.json["message"]
