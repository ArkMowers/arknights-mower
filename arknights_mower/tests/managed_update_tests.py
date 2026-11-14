import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from pydantic import ValidationError

import server
from arknights_mower.utils import config, resource_version, software_update
from arknights_mower.utils.config.conf import Conf


@pytest.mark.parametrize("choice", [False, True])
def test_launch_choice_only_restricts_managed_instances(choice):
    conf = Conf(extra_settings_visible=choice)
    assert conf.updates_enabled_for_launch(managed=False) is True
    assert conf.updates_enabled_for_launch(managed=True) is choice


def test_managed_update_default_is_disabled_without_persisting_a_choice():
    conf = Conf()
    assert conf.updates_enabled_for_launch(managed=True) is False
    assert conf.assistant_enabled_for_launch(managed=True) is False
    assert "updates_enabled" not in conf.model_dump(exclude_unset=True)
    assert "extra_settings_visible" not in conf.model_dump(exclude_unset=True)
    assert "ai_assistant_enabled" not in conf.model_dump(exclude_unset=True)


@pytest.mark.parametrize("choice", [None, 0, 1, "true", "false", [], {}])
@pytest.mark.parametrize("field", ["updates_enabled", "extra_settings_visible"])
def test_update_choice_rejects_non_boolean_values(choice, field):
    with pytest.raises(ValidationError):
        Conf(**{field: choice})


@pytest.mark.parametrize(
    "raw, expected",
    [
        ({"updates_enabled": True}, True),
        ({"updates_enabled": False}, False),
        ({"extra_settings_visible": True}, True),
        ({"extra_settings_visible": False}, False),
        ({"extra_settings_visible": False, "updates_enabled": False}, False),
        ({"extra_settings_visible": True, "updates_enabled": True}, True),
        ({"extra_settings_visible": True, "updates_enabled": False}, False),
        ({"extra_settings_visible": False, "updates_enabled": True}, True),
    ],
)
def test_legacy_permissions_converge_on_real_configuration_load_and_save(
    tmp_path, monkeypatch, raw, expected
):
    path = tmp_path / "conf.yml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.setattr(config, "conf_path", path)
    monkeypatch.setattr(config, "conf", Conf())
    monkeypatch.setattr(config, "manager_inherited_settings", frozenset())
    monkeypatch.setattr(config, "_load_rescue_plan", Mock())
    before = path.read_bytes()
    config.load_conf()
    assert config.conf.extra_settings_visible is expected
    assert config.conf.updates_enabled_for_launch(managed=True) is expected
    assert config.conf.updates_enabled_for_launch(managed=False) is True
    assert path.read_bytes() == before
    config.save_conf()
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "updates_enabled" not in saved
    assert saved.get("extra_settings_visible", False) is expected
    assert Conf(**saved).extra_settings_visible is expected


def test_update_permission_compatibility_property_is_read_only():
    conf = Conf(extra_settings_visible=True)
    assert conf.updates_enabled is True
    with pytest.raises(AttributeError):
        conf.updates_enabled = False
    assert "updates_enabled" not in conf.model_dump()


@pytest.mark.parametrize(
    "managed,choice,expected",
    [
        (False, False, True),
        (True, None, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_fresh_launch_captures_permission_once(tmp_path, managed, choice, expected):
    directory = tmp_path / "config"
    directory.mkdir()
    if choice is not None:
        (directory / "conf.yml").write_text(
            f"extra_settings_visible: {str(choice).lower()}\n", encoding="utf-8"
        )
    script = (
        "import json, os, server\n"
        "from arknights_mower.utils import config\n"
        "before = server.app.config['UPDATES_ENABLED']\n"
        "config.conf.extra_settings_visible = not before\n"
        "os.environ['MOWER_MANAGED'] = '0'\n"
        "config.load_conf()\n"
        "server.app.token = 'update-status-test'\n"
        "print(json.dumps([before, config.updates_enabled, "
        "server.app.test_client().get('/status', headers={'token': 'update-status-test'}).json['updates_enabled']]))\n"
    )
    process = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env={
            **os.environ,
            "MOWER_DATA_DIR": str(tmp_path),
            "MOWER_MANAGED": "1" if managed else "0",
        },
        capture_output=True,
        encoding="utf-8",
        timeout=60,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout.strip().splitlines()[-1]) == [expected] * 3


UPDATE_ROUTES = [
    (rule.rule, method, rule.endpoint)
    for rule in server.app.url_map.iter_rules()
    if rule.rule.startswith(
        (
            "/software-update/",
            "/maa-update/",
            "/maa-resource-update/",
            "/resource-update/",
        )
    )
    or rule.rule in {"/resource/install", "/resource/status", "/resource-version"}
    for method in sorted(rule.methods - {"HEAD", "OPTIONS"})
]


@pytest.mark.parametrize("path,method,endpoint", UPDATE_ROUTES)
def test_disabled_update_routes_never_dispatch_handlers(
    monkeypatch, path, method, endpoint
):
    monkeypatch.setitem(server.app.config, "UPDATES_ENABLED", False)
    handler = Mock(return_value={"ok": True})
    monkeypatch.setitem(server.app.view_functions, endpoint, handler)
    monkeypatch.setattr(server.app, "token", "fixture-token", raising=False)
    response = server.app.test_client().open(
        path,
        method=method,
        data=b"not a valid package or JSON document",
        headers={"token": "fixture-token", "X-Mower-Update": "1"},
    )
    assert response.status_code == 403
    assert response.json["error"] == "updates_disabled"
    handler.assert_not_called()


@pytest.mark.parametrize(
    "path,method,endpoint",
    [
        ("/software-update/start", "POST", "software_update.start"),
        ("/maa-update/start", "POST", "start_maa_update"),
        ("/maa-resource-update/start", "POST", "start_maa_resource_update"),
        ("/resource/install", "POST", "install_resource"),
        ("/resource-update/manual", "POST", "resource_update_manual"),
    ],
)
def test_enabled_updates_reach_existing_handlers(monkeypatch, path, method, endpoint):
    monkeypatch.setitem(server.app.config, "UPDATES_ENABLED", True)
    handler = Mock(return_value={"ok": True})
    monkeypatch.setitem(server.app.view_functions, endpoint, handler)
    monkeypatch.setattr(server.app, "token", "fixture-token", raising=False)
    response = server.app.test_client().open(
        path, method=method, headers={"token": "fixture-token", "X-Mower-Update": "1"}
    )
    assert response.status_code == 200
    handler.assert_called_once_with()


def test_disabled_instance_keeps_local_resource_version_reads(monkeypatch):
    monkeypatch.setitem(server.app.config, "UPDATES_ENABLED", False)
    monkeypatch.setattr(server.app, "token", "fixture-token", raising=False)
    check = Mock(return_value={"current_display": "local fixture"})
    monkeypatch.setattr(resource_version, "check_resource_update", check)
    response = server.app.test_client().get(
        "/resource-version?local=1", headers={"token": "fixture-token"}
    )
    assert response.status_code == 200
    assert response.json["current_display"] == "local fixture"
    check.assert_called_once_with(local_only=True)


@pytest.mark.parametrize("method", ["post", "patch"])
@pytest.mark.parametrize("choice", [False, True])
def test_configuration_api_cannot_change_update_authorization(
    monkeypatch, method, choice
):
    monkeypatch.setattr(server.app, "token", "fixture-token", raising=False)
    monkeypatch.setattr(config, "conf", Conf(extra_settings_visible=choice))
    save = Mock()
    monkeypatch.setattr(config, "save_conf", save)
    response = getattr(server.app.test_client(), method)(
        "/conf",
        json={"updates_enabled": not choice},
        headers={"token": "fixture-token"},
    )
    assert response.status_code == 403
    assert response.json["error"] == "manager_owned_setting"
    assert config.conf.updates_enabled is choice
    save.assert_not_called()


def test_automatic_checks_skip_before_settings_network_or_thread_creation(monkeypatch):
    monkeypatch.setattr(config, "updates_enabled", False)
    settings, check, thread = Mock(), Mock(), Mock()
    monkeypatch.setattr(software_update, "get_settings", settings)
    monkeypatch.setattr(software_update, "check", check)
    monkeypatch.setattr(software_update, "Thread", thread)
    assert software_update.request_auto_check() == {"ok": True, "scheduled": False}
    assert software_update.check_on_launch() is True
    settings.assert_not_called()
    check.assert_not_called()
    thread.assert_not_called()


@pytest.mark.parametrize("choice", [False, True])
@pytest.mark.parametrize("echo", [None, "extra_settings_visible", "updates_enabled"])
def test_ordinary_configuration_saves_preserve_update_choice(
    monkeypatch, tmp_path, choice, echo
):
    from arknights_mower import __main__
    from arknights_mower.utils.config import weekly_plan_loader

    monkeypatch.setattr(server.app, "token", "fixture-token", raising=False)
    monkeypatch.setenv("MOWER_MANAGED", "1")
    monkeypatch.setattr(config, "conf", Conf(extra_settings_visible=choice))
    monkeypatch.setattr(config, "conf_path", tmp_path / "conf.yml")
    monkeypatch.setattr(server, "mower_thread", None)
    monkeypatch.setattr(__main__, "device_control", Mock(active=False))
    monkeypatch.setattr(
        weekly_plan_loader,
        "get_weekly_plan_manager",
        lambda: Mock(get_active_plan_key=lambda: ""),
    )
    payload = {"theme": "dark"}
    if echo:
        payload[echo] = choice
    response = server.app.test_client().patch(
        "/conf", json=payload, headers={"token": "fixture-token"}
    )
    assert response.status_code == 200, response.data
    assert config.conf.updates_enabled is choice
    assert (
        yaml.safe_load(config.conf_path.read_text(encoding="utf-8"))[
            "extra_settings_visible"
        ]
        is choice
    )
    assert "updates_enabled" not in yaml.safe_load(
        config.conf_path.read_text(encoding="utf-8")
    )
