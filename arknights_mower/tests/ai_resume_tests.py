"""Reconnect to stored chat without repeating model or tool execution."""

import json
from threading import Event, Thread
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessageChunk
from simple_websocket import ConnectionClosed

from arknights_mower.agent import execution
from arknights_mower.tests.ai_execution_tests import runtime as runtime
from arknights_mower.tests.ai_execution_tests import tool_call
from arknights_mower.tests.ai_history_tests import (
    chat_profiles as chat_profiles,
)
from arknights_mower.tests.ai_history_tests import (
    chat_socket,
    headers,
    post_control,
)
from arknights_mower.tests.ai_history_tests import (
    history as history,
)
from arknights_mower.tests.ai_history_tests import (
    storage as storage,
)
from arknights_mower.tests.ai_security_tests import FakeSocket
from arknights_mower.tests.config_profile_chat_tests import chat, create_profile
from arknights_mower.utils import ai_history, mastery_db


def resume(
    server,
    identifier=None,
    *,
    request_id=None,
    on_snapshot=None,
    token="chat-profile-token",
    generation="0",
):
    class Socket(FakeSocket):
        def send(self, value):
            super().send(value)
            frame = json.loads(value)
            if "snapshot" in frame and on_snapshot:
                on_snapshot(frame["snapshot"])

    socket = chat_socket(
        Socket,
        token=token,
        resume=True,
        conversation_id=identifier,
        request_id=request_id,
        generation=generation,
    )
    chat(server, socket)
    return socket


@pytest.mark.parametrize("decision", ["approve", "reject", "stop"])
def test_disconnect_during_confirmation_keeps_exact_pending_operation(
    runtime, monkeypatch, decision
):
    server, _, _, store, install = runtime
    mastery_db.save_route("先锋", "[]")
    after = '[{"name":"桃金娘"}]'
    model = install(
        [tool_call("set_route", {"profession": "先锋", "supports_json": after})],
        [AIMessageChunk(content="请求已处理")],
    )
    pending, holder = Event(), {}

    class Disconnect(FakeSocket):
        def send(self, value):
            frame = json.loads(value)
            if frame.get("event", {}).get("type") == "approval":
                holder.update(frame["event"])
                pending.set()
                raise ConnectionClosed()
            super().send(value)

    socket = chat_socket(
        Disconnect,
        message="保存路线",
        conversation_id=None,
        request_id="original-request",
    )
    worker = Thread(target=chat, args=(server, socket))
    worker.start()
    try:
        assert pending.wait(5)
        identifier = socket.sent[0]["conversation_id"]
        assert store.read(identifier)["busy"]
        assert create_profile(server).status_code == 409
        assert mastery_db.get_route("先锋")["supports"] == "[]"
        decided = False

        def on_snapshot(snapshot):
            nonlocal decided
            if decided or snapshot["status"] != "running":
                return
            event = next(e for e in snapshot["events"] if e["type"] == "approval")
            assert event == holder
            assert mastery_db.get_route("先锋")["supports"] == "[]"
            decided = True
            url = f"/ai/conversations/{identifier}/turns/{snapshot['turn_id']}/control"
            body = {
                "action": decision,
                "approval_id": event["approval_id"],
                "digest": event["digest"],
            }
            assert (
                server.app.test_client()
                .post(url, headers=headers(), json=body)
                .status_code
                == 200
            )
            if decision != "stop":
                assert (
                    server.app.test_client()
                    .post(url, headers=headers(), json=body)
                    .status_code
                    == 409
                )

        restored = resume(server, identifier, on_snapshot=on_snapshot)
        assert decided
        assert restored.sent[-1]["snapshot"]["status"] == (
            "cancelled" if decision == "stop" else "complete"
        )
        assert mastery_db.get_route("先锋")["supports"] == (
            after if decision == "approve" else "[]"
        )
        worker.join(5)
        assert not worker.is_alive()
        assert not store.read(identifier)["busy"]
        assert server.configuration_profiles_busy() is False
        count = len(model.inputs)
        resume(server, identifier)
        assert len(model.inputs) == count
    finally:
        if worker.is_alive():
            execution.control(
                store, socket.sent[0]["conversation_id"], holder["turn_id"], "stop"
            )
        worker.join(5)


def test_lost_ack_resumes_by_request_without_replaying_model(runtime):
    server, _, _, store, install = runtime
    disconnected, attached = Event(), Event()

    def response():
        assert disconnected.wait(5)
        yield AIMessageChunk(content="前半段")
        assert attached.wait(5)
        yield AIMessageChunk(content="后半段")

    model = install(response())

    class Disconnect(FakeSocket):
        def send(self, value):
            disconnected.set()
            raise ConnectionClosed()

    socket = chat_socket(
        Disconnect, message="查询", conversation_id=None, request_id="lost-ack"
    )
    worker = Thread(target=chat, args=(server, socket))
    worker.start()
    try:
        assert disconnected.wait(5)
        restored = resume(
            server, request_id="lost-ack", on_snapshot=lambda _: attached.set()
        )
        assert restored.sent[-1]["snapshot"]["assistant"] == "前半段后半段"
        assert restored.sent[-1]["snapshot"]["status"] == "complete"
        assert len(model.inputs) == 1
        assert len(store.list()) == 1
    finally:
        attached.set()
        worker.join(5)
    assert not worker.is_alive()


@pytest.mark.parametrize("token", [None, "wrong"])
def test_resume_authentication_precedes_storage(runtime, monkeypatch, token):
    server = runtime[0]
    storage_read = Mock(side_effect=AssertionError("unauthorized storage read"))
    monkeypatch.setattr(server, "active_chat_history", storage_read)
    socket = resume(server, "a" * 32, token=token)
    storage_read.assert_not_called()
    assert socket.closed


def test_resume_checks_generation_profile_and_request_identity(runtime, monkeypatch):
    server, agent, _, store, _ = runtime
    with store.turn(None, "saved", request_id="owned") as turn:
        turn.append("answer")
        turn.complete = True
    model = Mock(side_effect=AssertionError("resume must not invoke model"))
    monkeypatch.setattr(agent, "ask_llm", model)
    assert (
        resume(server, turn.conversation_id, generation="stale").sent[-1]["code"]
        == "configuration_changed"
    )
    assert "不属于" in resume(server, "b" * 32, request_id="owned").sent[-1]["error"]
    assert "未找到" in resume(server, request_id="not-accepted").sent[-1]["error"]
    other = ai_history.HistoryStore("other-profile")
    with other.turn(None, "foreign", request_id="foreign-request") as foreign:
        foreign.complete = True
    assert "不存在" in resume(server, foreign.conversation_id).sent[-1]["error"]
    assert "未找到" in resume(server, request_id="foreign-request").sent[-1]["error"]
    assert (
        resume(server, turn.conversation_id).sent[-1]["snapshot"]["assistant"]
        == "answer"
    )
    model.assert_not_called()


def test_stale_approval_after_process_restart_cannot_be_confirmed(runtime):
    server, _, _, store, _ = runtime
    with store.turn(None, "pending") as turn:
        turn.events.append(
            {
                "type": "approval",
                "status": "awaiting_approval",
                "approval_id": "old",
                "digest": "old",
                "id": "T1-1",
            }
        )
        store.save_progress(turn)
    restored = resume(server, turn.conversation_id).sent[-1]["snapshot"]
    assert restored["status"] == "interrupted"
    result = post_control(
        server,
        turn.conversation_id,
        turn.turn_id,
        action="approve",
        approval_id="old",
        digest="old",
    )
    assert result.status_code == 409


def test_old_request_reconnect_does_not_attach_to_a_newer_turn(runtime):
    server, _, _, store, _ = runtime
    with store.turn(None, "first", request_id="first-request") as old:
        old.append("first answer")
        old.complete = True
    with store.turn(
        old.conversation_id, "second", request_id="second-request"
    ) as current:
        run = execution.Execution(store, current, lambda _: None)
        with run.registered():
            response = resume(server, old.conversation_id, request_id="first-request")
            assert response.sent[-1]["snapshot"]["turn_id"] == old.turn_id
            assert response.sent[-1]["snapshot"]["assistant"] == "first answer"
            assert run.observers == 0


def test_observer_limit_and_disconnection_release_slots(runtime):
    server, _, _, store, _ = runtime
    with store.turn(None, "running") as turn:
        run = execution.Execution(store, turn, lambda _: None)
        with run.registered():
            streams = [
                execution.observe(store, turn.conversation_id)
                for _ in range(execution.MAX_OBSERVERS)
            ]
            try:
                for stream in streams:
                    next(stream)
                assert (
                    "连接过多" in resume(server, turn.conversation_id).sent[-1]["error"]
                )
                streams[0].close()
                assert run.observers == execution.MAX_OBSERVERS - 1

                class Disconnect(FakeSocket):
                    def send(self, value):
                        raise ConnectionClosed()

                socket = chat_socket(
                    Disconnect, resume=True, conversation_id=turn.conversation_id
                )
                chat(server, socket)
                assert run.observers == execution.MAX_OBSERVERS - 1
                assert not run.stopped
            finally:
                for stream in streams:
                    stream.close()
            assert run.observers == 0


def test_disconnected_confirmation_expires_without_writing(runtime, monkeypatch):
    server, _, _, store, install = runtime
    monkeypatch.setattr(execution, "APPROVAL_SECONDS", 0.01)
    write = Mock(side_effect=AssertionError("expired confirmation must not write"))
    monkeypatch.setattr(mastery_db, "save_confirmed_route", write)
    install(
        [tool_call("set_route", {"profession": "先锋", "supports_json": "[]"})],
        [AIMessageChunk(content="未执行")],
    )

    class Disconnect(FakeSocket):
        def send(self, value):
            if json.loads(value).get("event", {}).get("type") == "approval":
                raise ConnectionClosed()
            super().send(value)

    socket = chat_socket(Disconnect, message="保存路线", conversation_id=None)
    chat(server, socket)
    restored = resume(server, socket.sent[0]["conversation_id"]).sent[-1]["snapshot"]
    assert restored["events"][-1]["status"] == "not_executed"
    write.assert_not_called()


def test_real_websocket_reconnect_preserves_confirmation(runtime):
    from simple_websocket import Client
    from werkzeug.serving import make_server

    server, _, _, store, install = runtime
    install(
        [tool_call("set_route", {"profession": "先锋", "supports_json": "[]"})],
        [AIMessageChunk(content="保存完成")],
    )
    service = make_server("127.0.0.1", 0, server.app, threaded=True)
    worker = Thread(target=service.serve_forever, daemon=True)
    worker.start()
    sockets = []
    identifier, turn_id = None, None
    try:
        url = f"ws://127.0.0.1:{service.server_port}/ws/chat"
        first = Client.connect(url)
        sockets.append(first)
        first.send(json.dumps({"token": "chat-profile-token"}))
        first.send(
            json.dumps(
                {"message": "保存路线", "generation": "0", "conversation_id": None}
            )
        )
        ack = json.loads(first.receive(timeout=3))
        identifier, turn_id = ack["conversation_id"], ack["turn_id"]
        for _ in range(10):
            event = json.loads(first.receive(timeout=3)).get("event", {})
            if event.get("type") == "approval":
                break
        assert event["type"] == "approval"
        first.close()
        second = Client.connect(url)
        sockets.append(second)
        second.send(json.dumps({"token": "chat-profile-token"}))
        second.send(
            json.dumps(
                {
                    "resume": True,
                    "conversation_id": identifier,
                    "turn_id": turn_id,
                    "generation": "0",
                }
            )
        )
        snapshot = json.loads(second.receive(timeout=3))["snapshot"]
        assert snapshot["events"][-1] == event
        assert mastery_db.get_route("先锋") is None
        response = post_control(
            server,
            identifier,
            turn_id,
            action="approve",
            approval_id=event["approval_id"],
            digest=event["digest"],
        )
        assert response.status_code == 200
        for _ in range(10):
            snapshot = json.loads(second.receive(timeout=3))["snapshot"]
            if snapshot["status"] != "running":
                break
        assert snapshot["status"] == "complete"
        assert snapshot["assistant"] == "保存完成"
        assert not store.read(identifier)["busy"]
    finally:
        if identifier:
            try:
                execution.control(store, identifier, turn_id, "stop")
            except ai_history.HistoryError:
                pass
        for socket in sockets:
            try:
                socket.close()
            except ConnectionClosed:
                pass
        service.shutdown()
        worker.join(5)
        service.server_close()


def test_disabled_assistant_rejects_resume_before_history_access(runtime, monkeypatch):
    server = runtime[0]
    monkeypatch.setitem(server.app.config, "AI_ASSISTANT_ENABLED", False)
    read = Mock(side_effect=AssertionError("disabled history access"))
    monkeypatch.setattr(server, "active_chat_history", read)
    socket = resume(server, "a" * 32)
    assert socket.sent[-1]["code"] == "ai_assistant_disabled"
    read.assert_not_called()


def test_detached_execution_admission_is_bounded(runtime, monkeypatch):
    server, agent, _, store, _ = runtime
    monkeypatch.setattr(execution, "MAX_ACTIVE_RUNS", 1)
    ask = Mock(side_effect=AssertionError("over-capacity dispatch"))
    monkeypatch.setattr(agent, "ask_llm", ask)
    with store.turn(None, "occupied") as turn:
        run = execution.Execution(store, turn, lambda _: None)
        with run.registered():
            socket = chat_socket(message="excess", conversation_id=None)
            chat(server, socket)
            assert "会话过多" in socket.sent[-1]["error"]
            assert not run.stopped
    ask.assert_not_called()
    assert not any(key[0] == str(store.path) for key in execution._running)
    assert server.configuration_profiles_busy() is False
