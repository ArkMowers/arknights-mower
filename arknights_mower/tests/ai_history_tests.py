"""Persistent assistant history through storage, HTTP and WebSocket callers."""

import json
import sqlite3
from contextlib import closing
from unittest.mock import Mock

import pytest
from simple_websocket import ConnectionClosed

from arknights_mower.tests.ai_security_tests import FakeSocket
from arknights_mower.tests.config_profile_chat_tests import chat
from arknights_mower.tests.config_profile_chat_tests import (
    chat_profiles as chat_profiles,
)
from arknights_mower.tests.config_profiles_tests import storage as storage
from arknights_mower.utils import ai_history


@pytest.fixture
def history(chat_profiles, storage, monkeypatch):
    server, agent, profiles = chat_profiles
    monkeypatch.setattr(ai_history, "get_path", storage)
    return server, agent, profiles, server.active_chat_history()


def chat_socket(
    socket_type=FakeSocket, *, token="chat-profile-token", generation="0", **request
):
    return socket_type(
        json.dumps({"token": token}),
        json.dumps({"generation": generation, **request}),
    )


def post_control(server, conversation_id, turn_id, **body):
    return server.app.test_client().post(
        f"/ai/conversations/{conversation_id}/turns/{turn_id}/control",
        headers=headers(),
        json=body,
    )


def send(server, text, identifier=None, socket_type=FakeSocket):
    socket = chat_socket(socket_type, message=text, conversation_id=identifier)
    chat(server, socket)
    return socket


def headers(generation="0"):
    return {"token": "chat-profile-token", "X-Mower-Config-Generation": generation}


def complete(store, user="hello", reply="world", identifier=None):
    with store.turn(identifier, user) as turn:
        turn.append(reply)
        turn.complete = True
    return turn.conversation_id


def test_streamed_reply_survives_new_socket_and_store_without_replaying(
    history, monkeypatch
):
    server, agent, _, store = history
    contexts = []

    def ask(text, context, api_key, **kwargs):
        contexts.append(context)
        yield "完整"
        yield "回复<!--MOWER_MISS_STATE:{}-->"

    monkeypatch.setattr(agent, "ask_llm", ask)
    socket = send(server, "first")
    identifier = socket.sent[0]["conversation_id"]
    assert socket.sent[-1] == {"done": True}
    reopened = ai_history.HistoryStore(store.profile_id)
    assert (
        reopened.read(identifier)["turns"][0]["assistant"]
        == "完整回复<!--MOWER_MISS_STATE:{}-->"
    )
    client = server.app.test_client()
    assert (
        client.get("/ai/conversations", headers=headers()).json["conversations"][0][
            "id"
        ]
        == identifier
    )
    assert (
        client.get(f"/ai/conversations/{identifier}", headers=headers()).json["turns"][
            0
        ]["status"]
        == "complete"
    )
    assert len(contexts) == 1
    send(server, "second", identifier)
    assert contexts[1] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "完整回复<!--MOWER_MISS_STATE:{}-->"},
    ]


@pytest.mark.parametrize("failure", ["model", "disconnect", "empty", "oversize"])
def test_failed_stream_is_persisted_and_never_replayed(history, monkeypatch, failure):
    server, agent, _, store = history

    def ask(*args, **kwargs):
        if failure == "empty":
            return
        yield "partial"
        if failure == "oversize":
            yield "x" * (ai_history.MAX_REPLY_CHARS + 1)
        raise ValueError("failed")

    class Disconnect(FakeSocket):
        def send(self, value):
            data = json.loads(value)
            if "reply" in data:
                raise ConnectionClosed()
            super().send(value)

    monkeypatch.setattr(agent, "ask_llm", ask)
    socket = send(
        server,
        "hello",
        socket_type=Disconnect if failure == "disconnect" else FakeSocket,
    )
    identifier = socket.sent[0]["conversation_id"]
    saved = store.read(identifier)
    assert saved["turns"][0]["status"] == "interrupted"
    assert saved["turns"][0]["assistant"] == ("" if failure == "empty" else "partial")
    assert not saved["busy"]
    model = Mock(return_value=iter(["new answer"]))
    monkeypatch.setattr(agent, "ask_llm", model)
    server.app.test_client().get(f"/ai/conversations/{identifier}", headers=headers())
    model.assert_not_called()
    send(server, "new question", identifier)
    assert model.call_args.kwargs["context"] == []


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/ai/conversations"),
        ("HEAD", "/ai/conversations"),
        ("DELETE", "/ai/conversations"),
        ("GET", "/ai/conversations/abc"),
        ("HEAD", "/ai/conversations/abc"),
        ("DELETE", "/ai/conversations/abc"),
    ],
)
@pytest.mark.parametrize("token", [None, "wrong"])
def test_history_requires_token_before_storage(
    history, monkeypatch, method, path, token
):
    server, _, _, _ = history
    access = Mock(side_effect=AssertionError("storage accessed"))
    monkeypatch.setattr(server, "active_chat_history", access)
    response = server.app.test_client().open(
        path, method=method, headers={"token": token} if token else {}
    )
    assert response.status_code == 403
    access.assert_not_called()


def test_disabled_and_stale_history_requests_do_not_access_storage(
    history, monkeypatch
):
    server, _, _, _ = history
    access = Mock(side_effect=AssertionError("storage accessed"))
    monkeypatch.setattr(server, "active_chat_history", access)
    for method in ("GET", "HEAD", "DELETE"):
        assert (
            server.app.test_client()
            .open("/ai/conversations", method=method, headers=headers("stale"))
            .status_code
            == 409
        )
        monkeypatch.setitem(server.app.config, "AI_ASSISTANT_ENABLED", False)
        assert (
            server.app.test_client()
            .open("/ai/conversations", method=method, headers=headers())
            .status_code
            == 403
        )
        monkeypatch.setitem(server.app.config, "AI_ASSISTANT_ENABLED", True)
    access.assert_not_called()


def test_profile_switch_keeps_history_separate_and_restores_it(history, monkeypatch):
    server, agent, profiles, store = history
    identifier = complete(store)
    original = store.profile_id
    profiles.create_profile("second", [], expected_generation="0")
    generation = profiles.current_generation()
    client = server.app.test_client()
    assert (
        client.get("/ai/conversations", headers=headers(generation)).json[
            "conversations"
        ]
        == []
    )
    for method in ("GET", "DELETE"):
        assert (
            client.open(
                f"/ai/conversations/{identifier}",
                method=method,
                headers=headers(generation),
            ).status_code
            == 404
        )
    model = Mock()
    monkeypatch.setattr(agent, "ask_llm", model)
    socket = chat_socket(
        message="cross profile", generation=generation, conversation_id=identifier
    )
    chat(server, socket)
    model.assert_not_called()
    profiles.activate_profile(original, [], expected_generation=generation)
    assert (
        client.get(
            f"/ai/conversations/{identifier}",
            headers=headers(profiles.current_generation()),
        ).json["turns"][0]["assistant"]
        == "world"
    )


def test_active_turn_rejects_concurrent_send_delete_and_clear(history):
    server, _, _, store = history
    identifier = complete(store)
    with store.turn(identifier, "active"):
        for candidate in (store, ai_history.HistoryStore(store.profile_id)):
            with pytest.raises(ai_history.HistoryError):
                with candidate.turn(identifier, "duplicate"):
                    pytest.fail("concurrent turn admitted")
        client = server.app.test_client()
        assert client.get(f"/ai/conversations/{identifier}", headers=headers()).json[
            "busy"
        ]
        for suffix in ("", f"/{identifier}"):
            assert (
                client.delete(
                    f"/ai/conversations{suffix}", headers=headers()
                ).status_code
                == 409
            )
    assert (
        client.delete(f"/ai/conversations/{identifier}", headers=headers()).status_code
        == 200
    )
    assert store.list() == []
    complete(store)
    assert client.delete("/ai/conversations", headers=headers()).status_code == 200
    assert store.list() == []


def test_pending_turn_after_crash_is_interrupted_on_reopen(history):
    _, _, _, store = history
    identifier = complete(store)
    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute(
            "INSERT INTO turns(conversation,user) VALUES (?,?)",
            (identifier, "possibly executed"),
        )
    reopened = ai_history.HistoryStore(store.profile_id)
    assert reopened.read(identifier)["turns"][-1]["status"] == "interrupted"
    with reopened.turn(identifier, "verify result") as turn:
        assert turn.context == []


def test_retention_and_context_have_independent_bounds(history, monkeypatch):
    _, _, _, store = history
    identifier = complete(store, "0", "reply")
    for index in range(1, 105):
        complete(store, str(index), "reply", identifier)
    assert len(store.read(identifier)["turns"]) == 100
    with store.turn(identifier, "next") as turn:
        assert len(turn.context) == 20
        assert turn.context[0]["content"] == "95"
    for _ in range(10):
        complete(store, "large", "x" * 32768, identifier)
    saved = store.read(identifier)["turns"]
    assert sum(len(row["user"]) + len(row["assistant"]) for row in saved) <= 262144
    with store.turn(identifier, "next") as turn:
        assert turn.context == []
    for index in range(25):
        complete(store, f"conversation {index}")
    assert len(store.list()) == 20
    assert store.list()[-1]["title"] == "conversation 5"
    monkeypatch.setattr(ai_history, "MAX_INSTANCE_CONVERSATIONS", 21)
    other = ai_history.HistoryStore("other-profile")
    complete(other)
    complete(other)
    assert len(store.list()) + len(other.list()) == 21


def test_instance_storage_and_configuration_export_are_separate(
    history, storage, monkeypatch, tmp_path
):
    _, _, profiles, store = history
    from arknights_mower.utils.config_backup import read_archive

    complete(store)
    files, tmp = read_archive(profiles.export_current_archive(), include_tmp=True)
    assert all("ai-history" not in name for name in (*files, *tmp))
    monkeypatch.setattr(
        ai_history, "get_path", lambda _: tmp_path / "other" / "ai-history.sqlite3"
    )
    assert ai_history.HistoryStore(store.profile_id).list() == []


def test_separate_process_restores_text_and_marks_abandoned_turn(history):
    import subprocess
    import sys

    _, _, _, store = history
    identifier = complete(store)
    code = """
import json, os, sys
from pathlib import Path
from arknights_mower.utils import ai_history
ai_history.get_path = lambda _: Path(sys.argv[1])
store = ai_history.HistoryStore(sys.argv[2])
assert store.read(sys.argv[3])["turns"][0]["assistant"] == "world"
with store.turn(sys.argv[3], "interrupted in another process"):
    os._exit(0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(store.path), store.profile_id, identifier],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr.decode()
    restored = store.read(identifier)
    assert restored["turns"][-1]["status"] == "interrupted"
    assert restored["busy"] is False


def test_eviction_failure_rolls_back_new_conversation(history, monkeypatch):
    _, _, _, store = history
    monkeypatch.setattr(ai_history, "MAX_CONVERSATIONS", 1)
    with store.turn(None, "active") as active:
        with pytest.raises(ai_history.HistoryError):
            complete(store, "rejected")
        assert [item["id"] for item in store.list()] == [active.conversation_id]
    assert store.read(active.conversation_id)["turns"][0]["user"] == "active"


def test_storage_failure_does_not_dispatch_model_or_reset_history(history, monkeypatch):
    server, agent, _, store = history
    store.path.write_bytes(b"not a sqlite database")
    model = Mock()
    monkeypatch.setattr(agent, "ask_llm", model)
    response = server.app.test_client().get("/ai/conversations", headers=headers())
    assert response.status_code == 503
    send(server, "hello")
    model.assert_not_called()
    assert store.path.read_bytes() == b"not a sqlite database"


def test_valid_head_and_clear_leave_other_profiles_untouched(history):
    server, _, _, store = history
    identifier = complete(store)
    other = ai_history.HistoryStore("other-profile")
    other_id = complete(other)
    client = server.app.test_client()
    for suffix in ("", f"/{identifier}"):
        response = client.head(f"/ai/conversations{suffix}", headers=headers())
        assert response.status_code == 200
        assert response.data == b""
    assert client.delete("/ai/conversations", headers=headers()).status_code == 200
    assert other.read(other_id)["turns"][0]["assistant"] == "world"


def test_legacy_socket_retains_all_reply_chunks(history, monkeypatch):
    server, agent, _, _ = history
    calls = []

    def ask(user_input, context, api_key):
        calls.append(list(context))
        yield "first chunk "
        yield "last chunk"

    monkeypatch.setattr(agent, "ask_llm", ask)
    socket = FakeSocket(
        json.dumps({"token": "chat-profile-token"}),
        json.dumps({"message": "one", "generation": "0"}),
        json.dumps({"message": "two", "generation": "0"}),
    )
    chat(server, socket)
    assert calls[1][-1] == {"role": "assistant", "content": "first chunk last chunk"}
