import os
from pathlib import Path

import pytest

from arknights_mower.tests.config_profiles_tests import storage as storage


@pytest.fixture
def bootstrap(storage, monkeypatch):
    from arknights_mower.utils import config
    from arknights_mower.utils.config.conf import Conf

    monkeypatch.setattr(config, "conf", Conf())
    for key, value in {
        "MOWER_TOKEN": "initial-container-token",
        "MOWER_PORT": "58000",
        "MOWER_MAA_DIR": "/MAA",
        "MOWER_ADB_BIN": "/usr/bin/adb",
        "MOWER_SIMULATOR_FOLDER": "/simulator",
    }.items():
        monkeypatch.setenv(key, value)
    script = Path(__file__).resolve().parents[2] / "docker/entrypoint.sh"
    source = (
        script.read_text(encoding="utf-8")
        .split("python - <<'PY'\n", 1)[1]
        .split("\nPY\n", 1)[0]
    )

    def run():
        exec(compile(source, str(script), "exec"), {})
        config.load_conf()
        return config.conf.webview.token

    return config, run


def test_container_bootstraps_then_preserves_token_saved_in_ui(bootstrap):
    config, run = bootstrap
    private_key = Path(os.environ["MOWER_CREDENTIAL_KEY_FILE"])
    original_key = private_key.read_bytes()
    assert run() == "initial-container-token"
    config.conf.webview = config.conf.webview.model_copy(
        update={"token": "updated-in-ui"}
    )
    config.save_conf()
    assert run() == "updated-in-ui"
    assert private_key.read_bytes() == original_key
    assert "updated-in-ui" not in config.conf_path.read_text(encoding="utf-8")


def test_container_without_supplied_token_retains_generated_value(
    bootstrap, monkeypatch
):
    config, run = bootstrap
    monkeypatch.delenv("MOWER_TOKEN")
    generated = run()
    assert len(generated) >= 32
    assert run() == generated


def test_old_empty_container_setting_cannot_launch_without_authentication(bootstrap):
    config, run = bootstrap
    config.conf.webview = config.conf.webview.model_copy(update={"token": ""})
    config.save_conf()
    generated = run()
    assert len(generated) >= 32
    assert generated != "initial-container-token"
