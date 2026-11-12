"""Exercise confirmed tool actions through the stored chat and HTTP control paths."""

import json
import sqlite3
from contextlib import closing
from threading import Event, Thread
from unittest.mock import Mock

import httpx
import pytest
from langchain_core.messages import AIMessageChunk
from openai import APIConnectionError, APITimeoutError

from arknights_mower.agent import execution
from arknights_mower.tests.ai_history_tests import (
    chat_profiles as chat_profiles,
)
from arknights_mower.tests.ai_history_tests import (
    complete,
    headers,
)
from arknights_mower.tests.ai_history_tests import (
    history as history,
)
from arknights_mower.tests.ai_history_tests import (
    storage as storage,
)
from arknights_mower.tests.ai_security_tests import FakeSocket
from arknights_mower.tests.config_profile_chat_tests import chat
from arknights_mower.utils import ai_history, mastery_db


def tool_call(name, args=None, identifier="call-1"):
    return AIMessageChunk(
        content="", tool_calls=[{"name": name, "args": args or {}, "id": identifier}]
    )


class Model:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.inputs = []
        self.closed = 0

    def stream(self, messages):
        self.inputs.append(list(messages))
        response = self.responses.pop(0)
        try:
            if isinstance(response, Exception):
                raise response
            yield from response
        finally:
            self.closed += 1


@pytest.fixture
def runtime(history, monkeypatch):
    server, agent, profiles, store = history
    monkeypatch.setattr(agent.config.conf, "ai_type", "custom-local")

    def install(*responses):
        model = Model(*responses)
        monkeypatch.setattr(agent, "build_llm", lambda *a, **kw: model)
        return model

    return server, agent, profiles, store, install


def run_chat(
    runtime,
    *,
    conversation=None,
    retry_of=None,
    continue_of=None,
    continue_instruction=None,
    attachment_ids=None,
    message="请执行本次请求",
    mode="chat",
    decide="approve",
    on_event=None,
    request_id=None,
):
    server = runtime[0]

    class Socket(FakeSocket):
        def send(self, value):
            super().send(value)
            frame = json.loads(value)
            event = frame.get("event", {})
            if on_event:
                on_event(self, event)
            if event.get("type") == "approval" and decide:
                identifier = self.sent[0]["conversation_id"]
                response = server.app.test_client().post(
                    f"/ai/conversations/{identifier}/turns/{event['turn_id']}/control",
                    headers=headers(),
                    json={
                        "action": decide,
                        "approval_id": event["approval_id"],
                        "digest": event["digest"],
                    },
                )
                assert response.status_code == 200, response.json

    request = {
        "message": message,
        "generation": "0",
        "conversation_id": conversation,
        "mode": mode,
    }
    if retry_of is not None:
        request["retry_of"] = retry_of
    if continue_of is not None:
        request["continue_of"] = continue_of
    if continue_instruction is not None:
        request["continue_instruction"] = continue_instruction
    if attachment_ids is not None:
        request["attachment_ids"] = attachment_ids
    if request_id:
        request["request_id"] = request_id
    socket = Socket(json.dumps({"token": "chat-profile-token"}), json.dumps(request))
    chat(server, socket)
    return socket


def events(socket):
    return [frame["event"] for frame in socket.sent if "event" in frame]


def test_read_progress_evidence_and_final_answer_are_separate(runtime, monkeypatch):
    server, agent, _, store, install = runtime
    monkeypatch.setitem(agent.tool_func_map, "list_plans", lambda: "待执行计划 A")
    model = install(
        [tool_call("list_plans")],
        [AIMessageChunk(content="查到"), AIMessageChunk(content="计划 A")],
    )
    socket = run_chat(runtime)
    saved = store.read(socket.sent[0]["conversation_id"])["turns"][0]
    assert saved["assistant"] == "查到计划 A"
    assert saved["status"] == "complete"
    assert "正在" not in saved["assistant"]
    event = next(item for item in saved["events"] if item["type"] == "tool")
    assert event["status"] == "succeeded" and event["result"] == "待执行计划 A"
    assert event["observed_at"] and event["source"]
    assert f"[证据 {event['id']}]" in model.inputs[1][-1].content
    assert [
        item["text"] for item in events(socket) if item["type"] == "answer_delta"
    ] == ["查到", "计划 A"]
    assert model.closed == 2
    assert (
        server.app.test_client()
        .get(
            f"/ai/conversations/{socket.sent[0]['conversation_id']}", headers=headers()
        )
        .status_code
        == 200
    )
    assert len(model.inputs) == 2


def test_route_requires_exact_confirmation_and_verifies_persisted_change(runtime):
    server, _, _, store, install = runtime
    mastery_db.save_route("先锋", "[]")
    after = '[{"name":"桃金娘","skill_level":1,"efficiency":30}]'
    install(
        [tool_call("set_route", {"profession": "先锋", "supports_json": after})],
        [AIMessageChunk(content="已核对路线")],
    )
    observed = []

    def verify_before(socket, event):
        if event.get("type") == "approval":
            assert mastery_db.get_route("先锋")["supports"] == "[]"
            assert event["preview"]["before"] == []
            assert event["preview"]["after"][0]["name"] == "桃金娘"
            observed.append(event)
            response = server.app.test_client().post(
                f"/ai/conversations/{socket.sent[0]['conversation_id']}/turns/{event['turn_id']}/control",
                headers=headers(),
                json={
                    "action": "approve",
                    "approval_id": event["approval_id"],
                    "digest": "changed",
                },
            )
            assert response.status_code == 409

    socket = run_chat(runtime, on_event=verify_before)
    assert len(observed) == 1
    assert json.loads(mastery_db.get_route("先锋")["supports"]) == json.loads(after)
    saved = store.read(socket.sent[0]["conversation_id"])["turns"][0]
    assert saved["events"][-1]["status"] == "verified"
    assert "核对" in saved["events"][-1]["result"]


@pytest.mark.parametrize("decision", ["reject", "stop", "timeout"])
def test_rejection_stop_and_expiry_never_write(runtime, monkeypatch, decision):
    _, _, _, store, install = runtime
    if decision == "timeout":
        monkeypatch.setattr(execution, "APPROVAL_SECONDS", 0)
    write = Mock(side_effect=AssertionError("unexpected write"))
    monkeypatch.setattr(mastery_db, "save_confirmed_route", write)
    install(
        [tool_call("set_route", {"profession": "先锋", "supports_json": "[]"})],
        [AIMessageChunk(content="未执行")],
    )
    socket = run_chat(runtime, decide=None if decision == "timeout" else decision)
    write.assert_not_called()
    saved = store.read(socket.sent[0]["conversation_id"])["turns"][0]
    assert saved["events"][-1]["status"] == "not_executed"
    assert saved["status"] == ("cancelled" if decision == "stop" else "complete")


def test_changed_route_while_waiting_requires_new_preview(runtime):
    _, _, _, _, install = runtime
    mastery_db.save_route("先锋", "[]")
    changed = '[{"name":"桃金娘"}]'
    install(
        [tool_call("set_route", {"profession": "先锋", "supports_json": "[]"})],
        [AIMessageChunk(content="未确认保存")],
    )
    socket = run_chat(
        runtime,
        on_event=lambda socket, event: (
            mastery_db.save_route("先锋", changed)
            if event.get("type") == "approval"
            else None
        ),
    )
    assert mastery_db.get_route("先锋")["supports"] == changed
    assert any(item.get("status") == "unknown" for item in events(socket))


@pytest.mark.parametrize("restart", ["retry_of", "continue_of"])
def test_retry_does_not_resend_accepted_mail_even_after_store_reopen(
    runtime, monkeypatch, restart
):
    _, agent, _, store, install = runtime
    sent = Mock(return_value="邮件发送成功！")
    monkeypatch.setitem(agent.tool_func_map, "submit_issue", sent)
    args = {"description": "功能建议", "issue_type": "Feature"}
    install([tool_call("submit_issue", args)], RuntimeError("response interrupted"))
    first = run_chat(runtime)
    identifier, turn_id = first.sent[0]["conversation_id"], first.sent[0]["turn_id"]
    assert sent.call_count == 1
    assert (
        ai_history.HistoryStore(store.profile_id).read(identifier)["turns"][0]["status"]
        == "interrupted"
    )
    # Explicit defaults are the same request, not a new operation.
    args.update(start_time=None, end_time=None, analysis=None)
    model = install(
        [tool_call("submit_issue", args)],
        [AIMessageChunk(content="此前邮件服务已接受，未重复发送")],
    )
    second = run_chat(runtime, conversation=identifier, **{restart: turn_id})
    assert sent.call_count == 1
    assert not any(item["type"] == "approval" for item in events(second))
    assert "未重复执行" in model.inputs[1][-1].content


@pytest.mark.parametrize("restart", ["retry_of", "continue_of"])
def test_unknown_write_after_exception_is_not_repeated(runtime, monkeypatch, restart):
    _, agent, _, _, install = runtime
    sent = Mock(side_effect=OSError("mail connection lost"))
    monkeypatch.setitem(agent.tool_func_map, "submit_issue", sent)
    args = {"description": "功能建议", "issue_type": "Feature"}
    install([tool_call("submit_issue", args)], RuntimeError("model failed"))
    first = run_chat(runtime)
    install(
        [tool_call("submit_issue", args)], [AIMessageChunk(content="需核实实际结果")]
    )
    second = run_chat(
        runtime,
        conversation=first.sent[0]["conversation_id"],
        **{restart: first.sent[0]["turn_id"]},
    )
    assert sent.call_count == 1
    assert any(item.get("status") == "not_repeated" for item in events(second))


def test_stop_during_started_write_preserves_result_and_prevents_next_call(
    runtime, monkeypatch
):
    server, agent, _, store, install = runtime
    entered, release = Event(), Event()
    calls = []

    def send_mail(**kwargs):
        calls.append("mail")
        entered.set()
        assert release.wait(5)
        return "邮件发送成功！"

    monkeypatch.setitem(agent.tool_func_map, "submit_issue", send_mail)
    model = install(
        [tool_call("submit_issue", {"description": "建议", "issue_type": "Feature"})],
        [AIMessageChunk(content="should not be requested")],
    )
    result = []
    worker = Thread(target=lambda: result.append(run_chat(runtime)))
    worker.start()
    try:
        assert entered.wait(5)
        identifier = store.list()[0]["id"]
        turn_id = store.read(identifier)["turns"][-1]["id"]
        response = server.app.test_client().post(
            f"/ai/conversations/{identifier}/turns/{turn_id}/control",
            headers=headers(),
            json={"action": "stop"},
        )
        assert response.status_code == 200
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert calls == ["mail"] and len(model.inputs) == 1
    saved = store.read(identifier)["turns"][-1]
    assert saved["status"] == "cancelled"
    assert saved["events"][-1]["status"] == "accepted"


def test_stop_between_model_chunks_closes_stream(runtime):
    server, _, _, store, install = runtime
    model = install(
        [AIMessageChunk(content="partial"), AIMessageChunk(content="must not appear")]
    )

    def stop(socket, event):
        if event.get("type") == "answer_delta":
            response = server.app.test_client().post(
                f"/ai/conversations/{socket.sent[0]['conversation_id']}/turns/{event['turn_id']}/control",
                headers=headers(),
                json={"action": "stop"},
            )
            assert response.status_code == 200

    socket = run_chat(runtime, on_event=stop)
    saved = store.read(socket.sent[0]["conversation_id"])["turns"][-1]
    assert saved["assistant"] == "partial" and saved["status"] == "cancelled"
    assert model.closed == 1


@pytest.mark.parametrize(
    "path", ["/ai/conversations/abc/summary", "/ai/conversations/abc/turns/1/control"]
)
@pytest.mark.parametrize("token", [None, "wrong"])
def test_controls_reject_credentials_before_storage(runtime, monkeypatch, path, token):
    server = runtime[0]
    access = Mock(side_effect=AssertionError("storage accessed"))
    monkeypatch.setattr(server, "active_chat_history", access)
    response = server.app.test_client().post(
        path, headers={"token": token} if token else {}, data="not json"
    )
    assert response.status_code == 403
    access.assert_not_called()


def test_controls_reject_stale_generation_disabled_and_ended_turn(runtime, monkeypatch):
    server, _, _, store, _ = runtime
    identifier = complete(store)
    client = server.app.test_client()
    for suffix in ("summary", "turns/1/control"):
        path = f"/ai/conversations/{identifier}/{suffix}"
        assert (
            client.post(
                path, headers=headers("old"), json={"action": "stop"}
            ).status_code
            == 409
        )
        monkeypatch.setitem(server.app.config, "AI_ASSISTANT_ENABLED", False)
        assert client.post(path, headers=headers(), json={}).status_code == 403
        monkeypatch.setitem(server.app.config, "AI_ASSISTANT_ENABLED", True)
    assert (
        client.post(
            f"/ai/conversations/{identifier}/turns/1/control",
            headers=headers(),
            json={"action": "stop"},
        ).status_code
        == 409
    )


def test_request_id_and_retry_target_prevent_duplicate_dispatch(runtime):
    _, _, _, _, install = runtime
    model = install([AIMessageChunk(content="answer")])
    first = run_chat(runtime, request_id="same-request")
    duplicate = run_chat(runtime, request_id="same-request")
    assert "已接收" in duplicate.sent[-1]["error"]
    invalid = run_chat(
        runtime,
        conversation=first.sent[0]["conversation_id"],
        retry_of=first.sent[0]["turn_id"],
    )
    assert "未完成" in invalid.sent[-1]["error"]
    assert len(model.inputs) == 1


def test_summary_is_read_only_and_requires_explicit_adoption(runtime):
    server, _, _, store, install = runtime
    identifier = complete(store, "目标：检查专精", "建议先查状态")
    model = install(
        [
            AIMessageChunk(
                content="目标：检查专精。事实：尚未查询。未完成：核对当前状态。"
            )
        ]
    )
    socket = run_chat(runtime, conversation=identifier, mode="summary")
    turn_id = socket.sent[0]["turn_id"]
    assert "只整理" in model.inputs[0][0].content
    assert store.read(identifier)["summary"] == ""
    response = server.app.test_client().post(
        f"/ai/conversations/{identifier}/summary",
        headers=headers(),
        json={"turn_id": turn_id},
    )
    assert response.status_code == 200
    with store.turn(identifier, "继续") as turn:
        assert "历史摘要" in turn.context[0]["content"]
        assert "尚未查询" in turn.context[0]["content"]
        assert turn.context_info["summary_source"] == turn_id
    assert (
        server.app.test_client()
        .post(
            f"/ai/conversations/{identifier}/summary",
            headers=headers(),
            json={"turn_id": None},
        )
        .status_code
        == 200
    )
    assert store.read(identifier)["summary"] == ""


@pytest.mark.parametrize("workflow", ["manual", "graph"])
def test_legacy_model_workflows_cannot_bypass_confirmation(
    runtime, monkeypatch, workflow
):
    from langchain_core.messages import AIMessage

    _, agent, _, _, _ = runtime
    write = Mock(side_effect=AssertionError("write bypassed confirmation"))
    monkeypatch.setitem(agent.tool_func_map, "submit_issue", write)
    model = Mock()
    model.invoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "submit_issue", "args": {"description": "x"}, "id": "write"}
            ],
        ),
        AIMessage(content="需要确认"),
    ]
    monkeypatch.setattr(agent, "build_llm", lambda *a, **k: model)
    if workflow == "manual":
        agent._run_manual_tool_loop(agent._build_messages("send"), "key")
    else:
        if agent.StateGraph is None:
            pytest.skip("optional graph dependency")
        agent.build_workflow("key").invoke({"messages": agent._build_messages("send")})
    write.assert_not_called()
    assert "未执行" in model.invoke.call_args.args[0][-1].content


def test_database_query_tool_is_read_only_and_does_not_create_files(
    runtime, storage, monkeypatch
):
    from arknights_mower.agent.tools import call_db

    monkeypatch.setattr(call_db, "get_path", storage)
    database = storage("@app/tmp/data.db")
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE log(time INTEGER,task TEXT,level TEXT,message TEXT)")
        db.execute("INSERT INTO log VALUES (1,'task','ERROR','<script>data</script>')")
    for query in (
        "DELETE FROM log",
        "DROP TABLE log",
        "PRAGMA user_version=9",
        "ATTACH DATABASE ':memory:' AS extra",
        "SELECT * FROM saved_state",
        "SELECT randomblob(2000000)",
        "SELECT " + "1," * 64 + "1",
    ):
        assert call_db.call_db(query).startswith("SQL 执行失败")
    text = call_db.call_db("SELECT message FROM log ORDER BY time DESC LIMIT 1")
    assert "&lt;script&gt;" in text
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT COUNT(*) FROM log").fetchone()[0] == 1
    missing = storage("@app/tmp/missing.db")
    monkeypatch.setattr(call_db, "get_path", lambda _: missing)
    assert call_db.call_db("SELECT 1").startswith("SQL 执行失败")
    assert not missing.exists()


def test_confirmation_cannot_change_arguments_or_be_used_twice(runtime):
    server, _, _, _, install = runtime
    install(
        [tool_call("set_route", {"profession": "先锋", "supports_json": "[]"})],
        [AIMessageChunk(content="done")],
    )

    def confirm(socket, event):
        if event.get("type") != "approval":
            return
        path = f"/ai/conversations/{socket.sent[0]['conversation_id']}/turns/{event['turn_id']}/control"
        body = {
            "action": "approve",
            "approval_id": event["approval_id"],
            "digest": event["digest"],
        }
        client = server.app.test_client()
        assert (
            client.post(
                path,
                headers=headers(),
                json={**body, "arguments": {"profession": "近卫"}},
            ).status_code
            == 400
        )
        assert mastery_db.get_route("先锋") is None
        assert client.post(path, headers=headers(), json=body).status_code == 200
        assert client.post(path, headers=headers(), json=body).status_code == 409

    run_chat(runtime, decide=None, on_event=confirm)
    assert mastery_db.get_route("先锋")["supports"] == "[]"
    assert mastery_db.get_route("近卫") is None


def test_failed_read_is_not_reported_as_success(runtime, monkeypatch):
    _, agent, _, _, install = runtime
    monkeypatch.setitem(
        agent.tool_func_map, "call_db", lambda query: "SQL 执行失败: missing table"
    )
    model = install(
        [tool_call("call_db", {"query": "SELECT * FROM log"})],
        [AIMessageChunk(content="未能读取日志")],
    )
    socket = run_chat(runtime)
    assert any(item.get("status") == "failed" for item in events(socket))
    assert "状态：failed" in model.inputs[1][-1].content


def test_failed_plan_confirmation_uses_exact_ids_and_checks_state(runtime):
    _, _, _, _, install = runtime
    # The existing storage owner creates the real schema.
    mastery_db.get_all_plans()
    with mastery_db._conn() as db:
        db.execute(
            "INSERT INTO mastery_plan(char_id,skill_index,target_level,status) VALUES ('one',0,1,'failed')"
        )
        db.commit()
    install(
        [tool_call("retry_plan_tool", {"char_id": "ignored", "skill_index": 0})],
        [AIMessageChunk(content="核对结果")],
    )
    previews = []

    def change(socket, event):
        if event.get("type") == "approval":
            previews.append(event["preview"])
            with mastery_db._conn() as db:
                db.execute(
                    "INSERT INTO mastery_plan(char_id,skill_index,target_level,status) VALUES ('two',0,1,'failed')"
                )
                db.commit()

    first = run_chat(runtime, on_event=change)
    assert len(previews[0]["plans"]) == 1
    assert len(mastery_db.get_failed_plans()) == 2
    assert not mastery_db.get_all_plans()
    assert any(item.get("status") == "unknown" for item in events(first))
    install(
        [tool_call("retry_plan_tool", {"char_id": "", "skill_index": 0})],
        [AIMessageChunk(content="已核对")],
    )
    second = run_chat(runtime)
    assert {row["status"] for row in mastery_db.get_all_plans()} == {"idle"}
    assert any(item.get("status") == "verified" for item in events(second))


def test_add_plan_success_text_without_readback_is_not_verified(runtime, monkeypatch):
    _, agent, _, _, install = runtime

    def add(char_id, skill_index, skill_name="", target_level=3):
        return "已添加专精计划: claimed"

    monkeypatch.setitem(agent.tool_func_map, "add_mastery_plan", add)
    install(
        [
            tool_call(
                "add_mastery_plan", {"char_id": "char_103_angel", "skill_index": 0}
            )
        ],
        [AIMessageChunk(content="请核实")],
    )
    socket = run_chat(runtime)
    outcomes = [
        item for item in events(socket) if item.get("status") in {"unknown", "verified"}
    ]
    assert outcomes[-1]["status"] == "unknown"
    assert "未能确认" in outcomes[-1]["result"]


def test_crashed_write_attempt_is_retained_and_not_repeated(runtime):
    import subprocess
    import sys

    _, _, _, store, _ = runtime
    code = """
import os, sys
from pathlib import Path
from arknights_mower.utils import ai_history
from arknights_mower.agent.execution import Execution
ai_history.get_path = lambda _: Path(sys.argv[1])
store = ai_history.HistoryStore(sys.argv[2])
with store.turn(None, "send") as turn:
    def send(frame):
        event = frame["event"]
        if event["type"] == "approval":
            run.control("approve", event["approval_id"], event["digest"])
    run = Execution(store, turn, send)
    with run.registered():
        run.execute("submit_issue", {"description":"suggestion", "issue_type":"Feature"}, {"submit_issue": lambda **kw: os._exit(0)}, {})
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(store.path), store.profile_id],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr.decode()
    identifier = store.list()[0]["id"]
    saved = store.read(identifier)["turns"][-1]
    assert saved["status"] == "interrupted"
    with store.turn(identifier, "send", retry_of=saved["id"]) as turn:
        sent = Mock(side_effect=AssertionError("crashed operation replayed"))
        run = execution.Execution(store, turn, lambda _: None)
        with run.registered():
            text = run.execute(
                "submit_issue",
                {"description": "suggestion", "issue_type": "Feature"},
                {"submit_issue": sent},
                {},
            )
    assert "未重复执行" in text and "attempted" in text
    sent.assert_not_called()


def test_old_history_schema_migrates_without_losing_text(runtime):
    _, _, _, store, _ = runtime
    identifier = "a" * 32
    with closing(sqlite3.connect(store.path)) as db, db:
        db.executescript(
            "CREATE TABLE conversations(id TEXT PRIMARY KEY,profile TEXT NOT NULL,title TEXT NOT NULL,updated REAL NOT NULL); CREATE TABLE turns(id INTEGER PRIMARY KEY AUTOINCREMENT,conversation TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,user TEXT NOT NULL,assistant TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'interrupted');"
        )
        db.execute(
            "INSERT INTO conversations VALUES (?,?,?,1)",
            (identifier, store.profile_id, "old"),
        )
        db.execute(
            "INSERT INTO turns(conversation,user,assistant,status) VALUES (?,'question','answer','complete')",
            (identifier,),
        )
    saved = store.read(identifier)
    assert saved["turns"][0]["assistant"] == "answer"
    assert saved["turns"][0]["events"] == [] and saved["summary"] == ""
    with store.turn(identifier, "continue") as turn:
        assert turn.context[-1]["content"] == "answer"


def test_context_notice_reports_actual_truncation(runtime):
    _, _, _, store, _ = runtime
    identifier = None
    for index in range(12):
        identifier = complete(store, str(index), "reply", identifier)
    with store.turn(identifier, "next") as turn:
        assert turn.context_info == {
            "retained_turns": 12,
            "included_turns": 10,
            "limited": True,
            "summary_source": 0,
        }
        assert turn.context[0]["content"] == "2"


def test_oversized_stream_preserves_only_bounded_interrupted_draft(runtime):
    _, _, _, store, install = runtime
    install([AIMessageChunk(content="x" * 40000)])
    socket = run_chat(runtime)
    turn = store.read(socket.sent[0]["conversation_id"])["turns"][0]
    assert turn["status"] == "interrupted"
    assert len(turn["assistant"]) == ai_history.MAX_REPLY_CHARS


def test_summary_excerpts_large_turn_and_reports_omission(runtime):
    store = runtime[3]
    with store.turn(None, "问题") as first:
        first.events = [{"result": "x" * 50000}]
        store.save_progress(first)
        first.append("回答")
        first.complete = True
    with store.turn(first.conversation_id, "摘要", mode="summary") as summary:
        assert summary.context_info["limited"]
        assert len(summary.context[0]["content"]) <= 48000
        assert "用户：问题" in summary.context[0]["content"]
        assert "记录已截断" in summary.context[0]["content"]


def test_retry_confirmation_rejects_changed_target_of_same_plan(runtime, monkeypatch):
    from arknights_mower.utils import mastery_recommendation
    from arknights_mower.views import mastery

    server, _, _, _, install = runtime
    monkeypatch.setattr(
        mastery_recommendation, "get_current_mastery_level", lambda *_: 0
    )
    monkeypatch.setattr(
        mastery_recommendation, "get_mastery_requirement_error", lambda *_: "未精二"
    )
    monkeypatch.setattr(mastery, "refresh_workshop_after_plan_change", lambda: None)
    identifier = mastery_db.insert_plan(
        "char_test", 0, 1, char_name="测试", skill_name="测试技能"
    )
    with mastery_db._conn() as db:
        db.execute("UPDATE mastery_plan SET status='failed' WHERE id=?", (identifier,))
        db.commit()
    previews = []

    def change_target(socket, event):
        if event.get("type") != "approval":
            return
        previews.append(event["preview"]["plans"])
        response = server.app.test_client().patch(
            "/mastery-plan/target",
            headers=headers(),
            json={"id": identifier, "target_level": 3},
        )
        assert response.status_code == 200, response.json
        assert mastery_db.get_plan_by_id(identifier)["status"] == "failed"

    install(
        [tool_call("retry_plan_tool", {"char_id": "", "skill_index": 0})],
        [AIMessageChunk(content="请重新核对")],
    )
    first = run_chat(runtime, on_event=change_target)
    assert previews[0][0]["target_level"] == 1
    saved = mastery_db.get_plan_by_id(identifier)
    assert saved["target_level"] == 3
    assert saved["status"] == "failed"
    assert not any(item.get("status") == "verified" for item in events(first))

    install(
        [tool_call("retry_plan_tool", {"char_id": "", "skill_index": 0})],
        [AIMessageChunk(content="已核对")],
    )
    second = run_chat(runtime)
    approval = next(item for item in events(second) if item.get("type") == "approval")
    assert approval["preview"]["plans"][0]["target_level"] == 3
    assert mastery_db.get_plan_by_id(identifier)["status"] == "idle"
    assert any(item.get("status") == "verified" for item in events(second))


@pytest.mark.parametrize(
    "field,value",
    [
        ("skill_index", 1),
        ("failed_reason", "材料不足"),
        ("support_plan", '{"changed":true}'),
    ],
)
def test_retry_confirmation_rejects_other_changed_plan_contents(runtime, field, value):
    install = runtime[4]
    identifier = mastery_db.insert_plan("char_test", 0, 1)
    with mastery_db._conn() as db:
        db.execute("UPDATE mastery_plan SET status='failed' WHERE id=?", (identifier,))
        db.commit()

    def change(socket, event):
        if event.get("type") == "approval":
            with mastery_db._conn() as db:
                db.execute(
                    f"UPDATE mastery_plan SET {field}=? WHERE id=?", (value, identifier)
                )
                db.commit()

    install(
        [tool_call("retry_plan_tool", {"char_id": "", "skill_index": 0})],
        [AIMessageChunk(content="请重新核对")],
    )
    socket = run_chat(runtime, on_event=change)
    saved = mastery_db.get_plan_by_id(identifier)
    assert saved[field] == value
    assert saved["status"] == "failed"
    result = next(item for item in events(socket) if item.get("status") == "unknown")
    assert "内容已改变" in result["result"]


def test_continue_carries_original_goal_completed_reads_and_partial_answer(
    runtime, monkeypatch
):
    server, agent, _, store, install = runtime
    identifier = complete(store, "背景问题", "此前背景")
    read = Mock(return_value="已查到计划 A，等待训练")
    monkeypatch.setitem(agent.tool_func_map, "list_plans", read)
    install([tool_call("list_plans")], [AIMessageChunk(content="尚未完成的分析")])

    def stop(socket, event):
        if event.get("type") == "answer_delta":
            response = server.app.test_client().post(
                f"/ai/conversations/{identifier}/turns/{event['turn_id']}/control",
                headers=headers(),
                json={"action": "stop"},
            )
            assert response.status_code == 200

    first = run_chat(runtime, conversation=identifier, on_event=stop)
    target = first.sent[0]["turn_id"]
    assert store.read(identifier)["turns"][-1]["status"] == "cancelled"
    model = install([AIMessageChunk(content="继续分析剩余工作")])
    second = run_chat(runtime, conversation=identifier, continue_of=target)
    assert len(model.inputs) == 1
    context = "\n".join(str(msg.content) for msg in model.inputs[0])
    for expected in (
        "此前背景",
        "已查到计划 A，等待训练",
        "尚未完成的分析",
        "旧确认全部失效",
    ):
        assert expected in context
    assert model.inputs[0][-1].content == "请执行本次请求"
    assert read.call_count == 1
    saved = store.read(identifier)["turns"][-1]
    assert saved["continued_from"] == target and saved["user"] == "请执行本次请求"
    assert saved["status"] == "complete"
    assert second.sent[0]["turn_id"] != target


def test_continue_replaces_stopped_approval_and_rejects_old_confirmation(runtime):
    server, _, _, store, install = runtime
    args = {"profession": "先锋", "supports_json": "[]"}
    install([tool_call("set_route", args)])
    first = run_chat(runtime, decide="stop")
    old = next(event for event in events(first) if event["type"] == "approval")
    identifier = first.sent[0]["conversation_id"]
    install([tool_call("set_route", args)], [AIMessageChunk(content="已完成")])

    def verify(socket, event):
        if event.get("type") != "approval":
            return
        assert event["approval_id"] != old["approval_id"]
        response = server.app.test_client().post(
            f"/ai/conversations/{identifier}/turns/{event['turn_id']}/control",
            headers=headers(),
            json={
                "action": "approve",
                "approval_id": old["approval_id"],
                "digest": old["digest"],
            },
        )
        assert response.status_code == 409
        assert event["preview"]["after"] == []

    second = run_chat(
        runtime, conversation=identifier, continue_of=old["turn_id"], on_event=verify
    )
    assert any(item.get("status") == "verified" for item in events(second))
    assert store.read(identifier)["turns"][-1]["status"] == "complete"


def test_repeated_continuation_survives_pruning_and_reopen(runtime, monkeypatch):
    _, _, _, store, install = runtime
    monkeypatch.setattr(ai_history, "MAX_TURNS", 1)
    with store.turn(None, "原始目标") as first:
        first.append("首轮进度")
    identifier, target = first.conversation_id, first.turn_id
    for index in range(3):
        store = ai_history.HistoryStore(store.profile_id)
        with store.turn(identifier, "继续", continue_of=target) as turn:
            assert turn.user_input == "原始目标"
            assert "首轮进度" in turn.context[0]["content"]
            for prior in range(index):
                assert f"后续进度{prior}" in turn.context[0]["content"]
            turn.append(f"后续进度{index}")
        target = turn.turn_id
        assert len(store.read(identifier)["turns"]) == 1
    model = install([AIMessageChunk(content="完成剩余工作")])
    run_chat(runtime, conversation=identifier, continue_of=target)
    assert model.inputs[0][-1].content == "原始目标"
    assert "后续进度2" in model.inputs[0][1].content


def test_continuation_bounds_and_retention_include_progress(runtime, monkeypatch):
    _, _, _, store, _ = runtime
    monkeypatch.setattr(ai_history, "MAX_HISTORY_CHARS", 40000)
    with store.turn(None, "goal") as first:
        first.append("旧草稿" * 8000)
    with store.turn(first.conversation_id, "继续", continue_of=first.turn_id) as second:
        assert second.context_info["continuation_limited"]
        second.append("新草稿" * 8000)
    with store.turn(first.conversation_id, "继续", continue_of=second.turn_id) as third:
        third.append("最终草稿")
    target = third.turn_id
    for index in range(6):
        with store.turn(first.conversation_id, "继续", continue_of=target) as current:
            current.append(f"进度{index}" + "\\" * 3900)
        target = current.turn_id
    with store.turn(first.conversation_id, "继续", continue_of=target) as final:
        assert final.context_info["continuation_limited"]
        assert "进度5" in final.context[0]["content"]
        assert final.user_input == "goal"
    with closing(sqlite3.connect(store.path)) as db:
        records = db.execute(
            "SELECT user,assistant,events,operations,continuation FROM turns"
        ).fetchall()
    assert sum(len(value) for row in records for value in row) <= 40000
    assert all(len(row[-1]) <= ai_history.MAX_CONTINUATION_CHARS for row in records)
    assert store.read(first.conversation_id)["turns"][-1]["continued_from"] == target


@pytest.mark.parametrize(
    "case", ["complete", "older", "both", "summary", "foreign", "busy"]
)
def test_invalid_continuation_never_dispatches_model(runtime, case):
    _, _, _, store, install = runtime
    with store.turn(
        None, "original", mode="summary" if case == "summary" else "chat"
    ) as first:
        first.complete = case == "complete"
    identifier = first.conversation_id
    kwargs = {"continue_of": first.turn_id}
    if case == "older":
        complete(store, identifier=identifier)
    elif case == "both":
        kwargs["retry_of"] = first.turn_id
    elif case == "foreign":
        identifier = complete(ai_history.HistoryStore("other-profile"))
    model = install([AIMessageChunk(content="must not run")])
    if case == "busy":
        with store.turn(identifier, "active"):
            result = run_chat(runtime, conversation=identifier, **kwargs)
    else:
        result = run_chat(runtime, conversation=identifier, **kwargs)
    assert "error" in result.sent[-1]
    assert model.inputs == []


@pytest.mark.parametrize("token", [None, "wrong"])
def test_continue_requires_auth_before_storage(runtime, monkeypatch, token):
    server = runtime[0]
    access = Mock(side_effect=AssertionError("storage accessed"))
    monkeypatch.setattr(server, "active_chat_history", access)
    socket = FakeSocket(
        json.dumps({"token": token}),
        json.dumps(
            {
                "message": "继续",
                "conversation_id": "a" * 32,
                "continue_of": 1,
                "continue_instruction": "先核对计划",
                "generation": "0",
            }
        ),
    )
    chat(server, socket)
    access.assert_not_called()
    assert socket.closed and socket.close_reason == 4401


def test_continue_with_requirements_preserves_goal_progress_and_later_changes(
    runtime, monkeypatch
):
    server, agent, _, store, install = runtime
    monkeypatch.setattr(ai_history, "MAX_TURNS", 1)
    monkeypatch.setitem(agent.tool_func_map, "list_plans", lambda: "原先查询的计划 A")
    install([tool_call("list_plans")], RuntimeError("interrupted"))
    first = run_chat(runtime)
    identifier = first.sent[0]["conversation_id"]
    model = install(RuntimeError("interrupted again"))
    requirement = "继续，但先不要发邮件"
    second = run_chat(
        runtime,
        conversation=identifier,
        continue_of=first.sent[0]["turn_id"],
        continue_instruction=requirement,
    )
    inputs = "\n".join(str(message.content) for message in model.inputs[0])
    assert "请执行本次请求" in inputs and "原先查询的计划 A" in inputs
    assert requirement in model.inputs[0][-1].content
    saved = (
        server.app.test_client()
        .get(f"/ai/conversations/{identifier}", headers=headers())
        .json
    )
    assert len(saved["turns"]) == 1
    assert saved["turns"][0]["continue_instruction"] == requirement
    assert saved["turns"][0]["user"] == "请执行本次请求"
    reopened = ai_history.HistoryStore(store.profile_id)
    assert reopened.read(identifier)["turns"][0]["continue_instruction"] == requirement
    next_requirement = "只分析计划 A 的剩余步骤"
    model = install([AIMessageChunk(content="已按新要求分析")])
    run_chat(
        runtime,
        conversation=identifier,
        continue_of=second.sent[0]["turn_id"],
        continue_instruction=next_requirement,
    )
    assert len(model.inputs) == 1
    assert requirement in model.inputs[0][-1].content
    assert next_requirement in model.inputs[0][-1].content
    assert model.inputs[0][-1].content.index(requirement) < model.inputs[0][
        -1
    ].content.index(next_requirement)
    with reopened.turn(identifier, "普通后续问题") as followup:
        assert requirement in followup.context[0]["content"]
        assert next_requirement in followup.context[0]["content"]


def test_new_requirements_do_not_authorize_writes(runtime, monkeypatch):
    _, agent, _, _, install = runtime
    send = Mock(return_value="邮件发送成功！")
    monkeypatch.setitem(agent.tool_func_map, "submit_issue", send)
    args = {"description": "建议", "issue_type": "Feature"}
    install([tool_call("submit_issue", args)])
    first = run_chat(runtime, decide="stop")
    install([tool_call("submit_issue", args)], [AIMessageChunk(content="未发送")])
    second = run_chat(
        runtime,
        conversation=first.sent[0]["conversation_id"],
        continue_of=first.sent[0]["turn_id"],
        continue_instruction="继续并发送",
        decide="reject",
    )
    assert any(event["type"] == "approval" for event in events(second))
    send.assert_not_called()


@pytest.mark.parametrize(
    "instruction,target", [(True, True), ("a" * 4001, True), ("新增要求", False)]
)
def test_invalid_continuation_requirements_never_start_turn(
    runtime, instruction, target
):
    _, _, _, store, install = runtime
    with store.turn(None, "goal") as first:
        pass
    model = install([AIMessageChunk(content="must not run")])
    result = run_chat(
        runtime,
        conversation=first.conversation_id,
        continue_of=first.turn_id if target else None,
        continue_instruction=instruction,
    )
    assert "error" in result.sent[-1]
    assert model.inputs == []
    assert len(store.read(first.conversation_id)["turns"]) == 1


def test_requirement_capacity_rejects_instead_of_dropping_prior_restrictions(runtime):
    _, _, _, store, install = runtime
    with store.turn(None, "goal") as first:
        pass
    requirement = "约束" * 1500
    with store.turn(
        first.conversation_id,
        "继续",
        continue_of=first.turn_id,
        continue_instruction=requirement,
    ) as second:
        second.append("progress")
    with store.turn(
        first.conversation_id,
        "继续",
        continue_of=second.turn_id,
        continue_instruction=requirement,
    ) as third:
        third.append("progress")
    model = install([AIMessageChunk(content="must not run")])
    result = run_chat(
        runtime,
        conversation=first.conversation_id,
        continue_of=third.turn_id,
        continue_instruction=requirement,
    )
    assert "累计补充要求" in result.sent[-1]["error"]
    assert model.inputs == []
    with store.turn(first.conversation_id, "继续", retry_of=third.turn_id) as retry:
        assert retry.continuation["instructions"] == [requirement, requirement]
        assert (
            len(json.dumps(retry.continuation, ensure_ascii=False))
            <= ai_history.MAX_CONTINUATION_CHARS
        )


@pytest.mark.parametrize(
    "failure,code",
    [
        (TimeoutError("timeout"), "model_timeout"),
        (
            APITimeoutError(request=httpx.Request("POST", "https://model.invalid")),
            "model_timeout",
        ),
        (httpx.ReadTimeout("read timed out"), "model_timeout"),
        (
            APIConnectionError(request=httpx.Request("POST", "https://model.invalid")),
            "model_connection",
        ),
        (httpx.ConnectError("cannot connect"), "model_connection"),
        (ValueError("bad response"), "model_error"),
    ],
)
def test_model_failure_kind_survives_history_and_reconnection(runtime, failure, code):
    server, _, _, store, install = runtime
    model = install(failure)
    socket = run_chat(runtime)
    identifier = socket.sent[0]["conversation_id"]
    assert socket.sent[-1]["status"] == "interrupted"
    assert socket.sent[-1]["code"] == code
    assert model.closed == 1
    saved = (
        server.app.test_client()
        .get(f"/ai/conversations/{identifier}", headers=headers())
        .json["turns"][-1]
    )
    assert saved["failure"]["code"] == code
    reopened = ai_history.HistoryStore(store.profile_id)
    snapshot = list(execution.observe(reopened, identifier))[-1]["snapshot"]
    assert snapshot["failure"] == saved["failure"]
    assert snapshot["status"] == "interrupted"


def test_user_stop_is_distinct_from_model_failure_after_reload(runtime):
    server, _, _, store, install = runtime
    install([tool_call("set_route", {"profession": "先锋", "supports_json": "[]"})])
    socket = run_chat(runtime, decide="stop")
    assert socket.sent[-1]["status"] == "cancelled"
    assert socket.sent[-1]["code"] == "execution_stopped"
    identifier = socket.sent[0]["conversation_id"]
    saved = (
        server.app.test_client()
        .get(f"/ai/conversations/{identifier}", headers=headers())
        .json["turns"][-1]
    )
    assert saved["status"] == "cancelled" and saved["failure"] == {}
    snapshot = list(
        execution.observe(ai_history.HistoryStore(store.profile_id), identifier)
    )[-1]["snapshot"]
    assert snapshot["status"] == "cancelled" and snapshot["failure"] == {}


def test_stop_while_provider_is_blocked_stays_cancelled_after_timeout(
    runtime, monkeypatch
):
    server, agent, _, store, _ = runtime
    entered, release = Event(), Event()

    class BlockingModel:
        def stream(self, messages):
            entered.set()
            assert release.wait(5)
            raise TimeoutError("provider timeout")
            yield

    monkeypatch.setattr(agent, "build_llm", lambda *args, **kwargs: BlockingModel())
    results = []
    worker = Thread(target=lambda: results.append(run_chat(runtime)))
    worker.start()
    try:
        assert entered.wait(5)
        identifier = store.list()[0]["id"]
        target = store.read(identifier)["turns"][-1]["id"]
        response = server.app.test_client().post(
            f"/ai/conversations/{identifier}/turns/{target}/control",
            headers=headers(),
            json={"action": "stop"},
        )
        assert response.status_code == 200
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert results[0].sent[-1]["status"] == "cancelled"
    assert results[0].sent[-1]["code"] == "execution_stopped"
    saved = store.read(identifier)["turns"][-1]
    assert saved["status"] == "cancelled" and saved["failure"] == {}
