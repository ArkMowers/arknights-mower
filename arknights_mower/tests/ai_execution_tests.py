"""Exercise confirmed tool actions through the stored chat and HTTP control paths."""

import json
import sqlite3
from contextlib import closing
from threading import Event, Thread
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessageChunk

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
        "message": "请执行本次请求",
        "generation": "0",
        "conversation_id": conversation,
        "mode": mode,
    }
    if retry_of is not None:
        request["retry_of"] = retry_of
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


def test_retry_does_not_resend_accepted_mail_even_after_store_reopen(
    runtime, monkeypatch
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
    second = run_chat(runtime, conversation=identifier, retry_of=turn_id)
    assert sent.call_count == 1
    assert not any(item["type"] == "approval" for item in events(second))
    assert "未重复执行" in model.inputs[1][-1].content


def test_unknown_write_after_exception_is_not_repeated(runtime, monkeypatch):
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
        retry_of=first.sent[0]["turn_id"],
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
