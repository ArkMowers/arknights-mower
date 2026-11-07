"""Broken legacy workshop files cannot disable general configuration access."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.workshop_automation_tests import manual_setting
from arknights_mower.tests.workshop_plan_fixtures import next_skill as next_skill
from arknights_mower.utils import config
from arknights_mower.utils import workshop_automation as auto
from arknights_mower.utils import workshop_config as state


@pytest.fixture
def client(next_skill, monkeypatch):
    import server
    from arknights_mower.utils.config import weekly_plan_loader

    manager = MagicMock()
    manager.get_active_plan_key.return_value = ""
    monkeypatch.setattr(weekly_plan_loader, "get_weekly_plan_manager", lambda: manager)
    config.conf.workshop_settings = [manual_setting()]
    return server.app.test_client()


@pytest.mark.parametrize(
    "broken",
    [
        b'{"settings": [',
        b'{"settings": "invalid"}',
        b"[false]",
        b'[{"items": "invalid"}]',
        b"\xff\xfe",
    ],
)
@pytest.mark.parametrize("modern", [False, True])
def test_broken_preset_does_not_block_conf_get_or_unrelated_save(
    client, broken, modern
):
    path = state.get_path("")
    path.write_bytes(broken)
    response = client.get("/conf")
    assert response.status_code == 200
    data = response.json
    assert data["workshop_preset_warning"]
    assert data["workshop_manual_settings"] == [manual_setting().model_dump()]
    if modern:
        data["workshop_manual_settings_revision"] = data["workshop_manual_revision"]
    else:
        data.pop("workshop_manual_settings")
    data["drone_interval"] = 9
    assert client.post("/conf", json=data).status_code == 200
    assert config.conf.drone_interval == 9
    assert config.conf.workshop_settings == [manual_setting()]
    assert config.conf.workshop_manual_backup is None
    assert not config.conf.workshop_preset_migrated
    assert not config.conf.workshop_auto_active
    assert path.read_bytes() == broken
    assert auto.update_workshop_config()["workshop_preset_warning"]
    assert config.conf.workshop_settings == [manual_setting()]


def test_unreadable_preset_is_also_scoped_to_workshop(client, monkeypatch):
    path = state.get_path("")
    path.write_text("[]")
    read = Path.read_text

    def deny_preset(self, *args, **kwargs):
        if self == path:
            raise PermissionError("not readable")
        return read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_preset)
    data = client.get("/conf").json
    assert data["workshop_preset_warning"]
    data["drone_interval"] = 7
    assert client.post("/conf", json=data).status_code == 200
    assert config.conf.drone_interval == 7
    assert config.conf.workshop_settings == [manual_setting()]


@pytest.mark.parametrize("saved", [[], [{"operator": "年"}]])
def test_repaired_file_can_migrate_without_stale_form_overwriting_it(client, saved):
    path = state.get_path("")
    path.write_text("{")
    old = client.get("/conf").json
    old["workshop_manual_settings_revision"] = old["workshop_manual_revision"]
    path.write_text(json.dumps(saved))
    response = client.post("/conf", json=old)
    assert response.status_code == 200
    assert not response.json["workshop_preset_warning"]
    assert response.json["workshop_manual_conflict"]
    assert config.conf.workshop_manual_backup == state.settings(saved, "manual")
    assert config.conf.workshop_settings == [manual_setting()]
    assert config.conf.workshop_preset_migrated
    assert not config.conf.workshop_auto_active


@pytest.mark.parametrize("manual", [[], [{"operator": "年"}]])
def test_user_can_replace_failed_migration_by_editing_manual_form(client, manual):
    path = state.get_path("")
    path.write_text("{")
    data = client.get("/conf").json
    data["workshop_manual_settings_revision"] = data["workshop_manual_revision"]
    data["workshop_manual_settings"] = manual
    response = client.post("/conf", json=data)
    assert response.status_code == 200
    assert not response.json["workshop_preset_warning"]
    assert config.conf.workshop_manual_backup == state.settings(manual, "manual")
    assert config.conf.workshop_settings == config.conf.workshop_manual_backup
    assert config.conf.workshop_preset_migrated
    assert path.read_text() == "{"
    assert not client.get("/conf").json["workshop_preset_warning"]


def test_existing_manual_form_does_not_reimport_broken_legacy_file(client):
    path = state.get_path("")
    path.write_text("{")
    config.conf.workshop_manual_backup = []
    assert client.get("/conf").status_code == 200
    assert not client.get("/conf").json["workshop_preset_warning"]
    assert config.conf.workshop_manual_backup == []
    assert config.conf.workshop_settings == [manual_setting()]
    assert path.read_text() == "{"
