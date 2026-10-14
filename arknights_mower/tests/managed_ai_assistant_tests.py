"""Offline coverage of manager-owned assistant authorization."""

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
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from manager import Api


@pytest.mark.parametrize("choice", [None, False, True])
def test_launch_defaults_and_explicit_choices_do_not_change_standalone_behavior(choice):
    conf = Conf() if choice is None else Conf(ai_assistant_enabled=choice)
    assert conf.assistant_enabled_for_launch(managed=False) is True
    assert conf.assistant_enabled_for_launch(managed=True) is (choice is True)
    if choice is None:
        assert "ai_assistant_enabled" not in conf.model_dump(exclude_unset=True)
    else:
        assert conf.model_dump(exclude_unset=True)["ai_assistant_enabled"] is choice


@pytest.mark.parametrize(
    "managed,choice,expected",
    [(False, False, True), (True, None, False), (True, True, True)],
)
def test_fresh_server_uses_actual_launch_mode_and_saved_choice(
    tmp_path, managed, choice, expected
):
    directory = tmp_path / "config"
    directory.mkdir()
    if choice is not None:
        (directory / "conf.yml").write_text(
            f"ai_assistant_enabled: {str(choice).lower()}\n", encoding="utf-8"
        )
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, server; print(json.dumps(server.app.config['AI_ASSISTANT_ENABLED']))",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={
            **os.environ,
            "MOWER_DATA_DIR": str(tmp_path),
            "MOWER_MANAGED": "1" if managed else "0",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout.strip().splitlines()[-1]) is expected


def test_saved_manager_choice_survives_abnormal_process_exit(tmp_path):
    storage = tmp_path / "instances.json"
    instance = tmp_path / "instance"
    script = (
        "import os, sys\n"
        "from manager import Api\n"
        "api = Api(sys.argv[1])\n"
        "api.add('fixture', sys.argv[2])\n"
        "api.update_settings(0, {'token': '', 'port': None, 'ai_assistant_enabled': True})\n"
        "os._exit(19)\n"
    )
    process = subprocess.run(
        [sys.executable, "-c", script, str(storage), str(instance)],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "MOWER_DATA_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert process.returncode == 19, process.stderr
    assert Api(storage).get_instances()[0]["ai_assistant_enabled"] is True


@pytest.mark.parametrize("choice", [0, 1, "true", "false", [], {}])
def test_assistant_configuration_rejects_non_boolean_values(choice):
    with pytest.raises(ValidationError):
        Conf(ai_assistant_enabled=choice)


def test_status_uses_launch_snapshot_not_later_configuration_or_environment(
    monkeypatch,
):
    monkeypatch.setitem(server.app.config, "AI_ASSISTANT_ENABLED", False)
    monkeypatch.setattr(server, "mower_thread", None)
    monkeypatch.setattr(config, "conf", Conf(ai_assistant_enabled=True))
    monkeypatch.setenv("MOWER_MANAGED", "0")
    assert server.app.test_client().get("/status").json["ai_assistant_enabled"] is False


@pytest.mark.parametrize("method", ["post", "patch"])
def test_configuration_api_cannot_change_manager_owned_choice(monkeypatch, method):
    monkeypatch.setattr(server.app, "token", "test-secret", raising=False)
    monkeypatch.setattr(config, "conf", Conf(ai_assistant_enabled=False))
    save = Mock()
    monkeypatch.setattr(config, "save_conf", save)
    response = getattr(server.app.test_client(), method)(
        "/conf", json={"ai_assistant_enabled": True}, headers={"token": "test-secret"}
    )
    assert response.status_code == 403
    assert response.json["error"] == "manager_owned_setting"
    assert config.conf.ai_assistant_enabled is False
    save.assert_not_called()


@pytest.mark.parametrize("method", ["post", "patch"])
@pytest.mark.parametrize("choice", [None, False, True])
@pytest.mark.parametrize("echo", [False, True])
def test_ordinary_settings_save_preserves_manager_choice(
    monkeypatch, tmp_path, method, choice, echo
):
    from arknights_mower import __main__
    from arknights_mower.utils.config import weekly_plan_loader

    target = tmp_path / "conf.yml"
    monkeypatch.setattr(server.app, "token", "test-secret", raising=False)
    monkeypatch.setattr(config, "conf", Conf(ai_assistant_enabled=choice))
    monkeypatch.setattr(config, "conf_path", target)
    monkeypatch.setattr(server, "mower_thread", None)
    monkeypatch.setattr(__main__, "device_control", Mock(active=False))
    monkeypatch.setattr(
        weekly_plan_loader,
        "get_weekly_plan_manager",
        lambda: Mock(get_active_plan_key=lambda: ""),
    )
    payload = {"theme": "dark"}
    if echo:
        payload["ai_assistant_enabled"] = choice
    response = getattr(server.app.test_client(), method)(
        "/conf",
        json=payload,
        headers={"token": "test-secret"},
    )
    assert response.status_code == 200, response.data
    saved = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert saved["theme"] == "dark"
    assert saved["ai_assistant_enabled"] is choice
    assert config.conf.ai_assistant_enabled is choice


@pytest.mark.parametrize("enabled", [False, True])
def test_chat_authorization_precedes_model_dispatch(monkeypatch, enabled):
    monkeypatch.setitem(server.app.config, "AI_ASSISTANT_ENABLED", enabled)
    monkeypatch.setattr(server.app, "token", "test-secret", raising=False)
    ws = Mock()
    ws.receive.side_effect = [
        json.dumps({"token": "test-secret"}),
        json.dumps({"message": "hello"}),
        None,
    ]
    from arknights_mower.agent import agent

    ask = Mock(return_value=iter(["reply"]))
    monkeypatch.setattr(agent, "ask_llm", ask)
    with server.app.test_request_context(
        "/ws/chat", headers={"Host": "localhost", "Origin": "http://localhost"}
    ):
        server.app.view_functions["ws_chat"].__wrapped__(ws)
    frames = [json.loads(call.args[0]) for call in ws.send.call_args_list]
    if enabled:
        ask.assert_called_once()
        assert frames == [{"reply": "reply"}, {"done": True}]
    else:
        ask.assert_not_called()
        ws.receive.assert_called_once()
        ws.close.assert_called_once()
        assert frames == [
            {
                "error": "当前实例暂未开启该功能，请联系管理员。",
                "code": "ai_assistant_disabled",
            }
        ]
