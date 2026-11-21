"""Saved configurations stay isolated from active and stale assistant messages."""

import json
from threading import Event, RLock, Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from simple_websocket import ConnectionClosed

from arknights_mower.tests.ai_security_tests import FakeSocket
from arknights_mower.tests.config_profiles_tests import storage as storage


@pytest.fixture
def chat_profiles(storage, monkeypatch):
    import arknights_mower.__main__ as main
    import server
    from arknights_mower.agent import agent
    from arknights_mower.utils import config_profiles, mastery_db

    monkeypatch.setattr(server.app, "token", "chat-profile-token", raising=False)
    monkeypatch.setitem(server.app.config, "AI_ASSISTANT_ENABLED", True)
    monkeypatch.setattr(server, "mower_thread", None)
    monkeypatch.setattr(server, "active_job", lambda: None)
    monkeypatch.setattr(server, "_job_running", lambda job: False)
    monkeypatch.setattr(server.resource_update, "running", lambda: False)
    monkeypatch.setattr(server, "shutdown", SimpleNamespace(closing=False))
    monkeypatch.setattr(server, "_performance_test_status", lambda: {"status": "idle"})
    monkeypatch.setattr(server, "maa_check_job", {"status": "idle"})
    monkeypatch.setattr(
        main,
        "device_control",
        SimpleNamespace(active=False, configuration_lock=RLock()),
    )
    monkeypatch.setattr(mastery_db, "get_path", storage)
    config_profiles.list_profiles()
    return server, agent, config_profiles


def create_profile(server):
    return server.app.test_client().post(
        "/config-profiles",
        headers={
            "token": "chat-profile-token",
            "X-Mower-Settings": "1",
            "X-Mower-Config-Generation": "0",
        },
        json={"name": "next", "inherit": []},
    )


def chat(server, socket):
    with server.app.test_request_context(
        "/ws/chat", headers={"Host": "localhost", "Origin": "http://localhost"}
    ):
        server.app.view_functions["ws_chat"].__wrapped__(socket)


def test_active_chat_blocks_switch_until_its_tool_finishes(
    chat_profiles, storage, monkeypatch
):
    server, agent, profiles = chat_profiles
    from arknights_mower.agent.tools.mastery_plan import set_route
    from arknights_mower.utils import config
    from arknights_mower.utils.mastery_db import get_route

    entered, release = Event(), Event()
    before_conf = config.conf_path.read_bytes()
    before_database = storage("@app/tmp/data.db").read_bytes()

    def ask(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        yield set_route("先锋", "[]")

    monkeypatch.setattr(agent, "ask_llm", ask)
    socket = FakeSocket(
        json.dumps({"token": "chat-profile-token"}),
        json.dumps({"message": "save route", "generation": "0"}),
    )
    worker = Thread(target=chat, args=(server, socket))
    worker.start()
    try:
        assert entered.wait(5)
        assert server.configuration_profiles_busy() is True
        response = create_profile(server)
        assert response.status_code == 409
        assert "AI" in response.json["message"]
        imported = server.app.test_client().post(
            "/config-backup/import",
            headers={
                "token": "chat-profile-token",
                "X-Mower-Settings": "1",
                "X-Mower-Config-Generation": "0",
            },
            data=b"not parsed while chat is running",
        )
        assert imported.status_code == 409
        assert "AI" in imported.json["message"]
        assert profiles.current_generation() == "0"
        assert config.conf_path.read_bytes() == before_conf
        assert storage("@app/tmp/data.db").read_bytes() == before_database
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert socket.sent[-1] == {"done": True}
    assert get_route("先锋")["supports"] == "[]"
    assert server.configuration_profiles_busy() is False
    assert create_profile(server).status_code == 200
    assert get_route("先锋") is None


@pytest.mark.parametrize("generation", [None, "0"])
def test_idle_connection_allows_switch_but_rejects_its_old_message(
    chat_profiles, monkeypatch, generation
):
    server, agent, _ = chat_profiles
    ask = Mock(return_value=iter(["unexpected"]))
    monkeypatch.setattr(agent, "ask_llm", ask)

    class IdleSocket(FakeSocket):
        def receive(self, timeout=None):
            if timeout is None:
                assert server.configuration_profiles_busy() is False
                assert create_profile(server).status_code == 200
            return super().receive(timeout)

    message = {"message": "old page"}
    if generation is not None:
        message["generation"] = generation
    socket = IdleSocket(
        json.dumps({"token": "chat-profile-token"}), json.dumps(message)
    )
    chat(server, socket)
    ask.assert_not_called()
    assert socket.sent[-1]["code"] == "configuration_changed"
    assert socket.closed
    assert server.configuration_profiles_busy() is False


@pytest.mark.parametrize("failure", ["model", "disconnect"])
def test_chat_failure_releases_profile_admission(chat_profiles, monkeypatch, failure):
    server, agent, _ = chat_profiles

    def ask(*args, **kwargs):
        assert server.configuration_profiles_busy() is True
        if failure == "model":
            raise ValueError("model failed")
        yield "reply"

    monkeypatch.setattr(agent, "ask_llm", ask)
    socket = FakeSocket(
        json.dumps({"token": "chat-profile-token"}),
        json.dumps({"message": "hello", "generation": "0"}),
    )
    if failure == "disconnect":
        socket.send = Mock(side_effect=ConnectionClosed())
    chat(server, socket)
    assert server.configuration_profiles_busy() is False
    assert create_profile(server).status_code == 200
