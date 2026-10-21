"""更新偏好脱离缓存，保留安装与数据根目录共享范围。"""

import json

import pytest

from arknights_mower.utils import path
from arknights_mower.utils import software_update as update


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(path, "_data_dir", tmp_path / "data")
    monkeypatch.setattr(
        update.runtime, "installation_root", lambda: tmp_path / "install"
    )
    return tmp_path


def test_legacy_update_settings_move_to_shared_config_and_save_there(storage):
    legacy = update.runtime.state_dir() / "settings.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"channel": "dev", "source_branch": "saved"}))
    assert update.get_settings()["source_branch"] == "saved"
    destination = update.settings_path()
    assert destination.parent == storage / "data/config/software-update"
    assert not legacy.exists()
    update.save_settings({"auto_check": True})
    assert json.loads(destination.read_text())["auto_check"] is True
    assert not legacy.exists()


def test_canonical_update_settings_win_over_legacy(storage):
    update.runtime.write_json(update.settings_path(), {"channel": "beta"})
    legacy = update.runtime.state_dir() / "settings.json"
    update.runtime.write_json(legacy, {"channel": "dev"})
    assert update.get_settings()["channel"] == "beta"
    assert json.loads(legacy.read_text())["channel"] == "dev"


def test_update_settings_share_instances_but_isolate_installations_and_data(
    storage, monkeypatch
):
    monkeypatch.setattr(path, "global_space", "first")
    update.save_settings({"channel": "dev"})
    original = update.settings_path()
    monkeypatch.setattr(path, "global_space", "second")
    assert update.settings_path() == original
    assert update.get_settings()["channel"] == "dev"
    monkeypatch.setattr(
        update.runtime, "installation_root", lambda: storage / "another-install"
    )
    assert update.settings_path() != original
    monkeypatch.setattr(path, "_data_dir", storage / "another-data")
    assert (
        update.settings_path().parent == storage / "another-data/config/software-update"
    )


def test_failed_update_settings_migration_preserves_old_file(storage, monkeypatch):
    legacy = update.runtime.state_dir() / "settings.json"
    update.runtime.write_json(legacy, {"channel": "dev"})
    original = legacy.read_bytes()

    def fail(*args):
        raise OSError("readonly")

    monkeypatch.setattr(update.os, "replace", fail)
    with pytest.raises(OSError, match="readonly"):
        update.get_settings()
    assert legacy.read_bytes() == original
    assert not update.settings_path().exists()
