"""反馈证据检查、源码推断及发送校验的真实工具调用路径。"""

import json
from collections import Counter
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage

from arknights_mower.agent import agent
from arknights_mower.agent.execution import MAX_RESULT_CHARS, Execution
from arknights_mower.agent.tools import submit_issue
from arknights_mower.tests import feedback_state_tests, issue_evidence_tests
from arknights_mower.tests.issue_evidence_tests import (
    END,
    START,
    parts,
    write_logs,
)
from arknights_mower.utils import ai_history

feedback = issue_evidence_tests.feedback
state_database = feedback_state_tests.database


@pytest.fixture
def evidence(feedback, state_database, monkeypatch):
    logs, images, sent = feedback
    monkeypatch.setattr(
        submit_issue,
        "get_path",
        lambda name: {
            "@app/log": logs,
            "@app/screenshot": images,
            "@app/tmp/data.db": state_database,
        }[name],
    )
    (logs / "runtime.log").write_text(
        "2026-10-20 12:00:10 arknights_mower/solvers/record.py:70 ERROR "
        "训练室计划未匹配，保留原任务\n",
        encoding="utf-8",
    )
    return logs, sent, state_database


def inspect(**kwargs):
    return json.loads(submit_issue.inspect_feedback(START, END, **kwargs))


def test_inspection_reads_actual_state_and_source_without_sending(evidence):
    _, sent, database = evidence
    before = database.read_bytes()
    report = inspect(focus_terms=["训练室"])
    references = report["references"]
    assert references["sources"]
    assert any("训练室计划未匹配" in row["text"] for row in references["records"])
    assert any(
        row["kind"] == "current_snapshot" and "failed" in row["text"]
        for row in references["records"]
    )
    assert report["current_state"]["current_snapshot_not_historical"] is True
    assert (
        report["current_state"]["scheduler_runtime"]["reason"]
        == "no_synchronized_snapshot"
    )
    source = references["sources"][0]
    assert source["file"] == "arknights_mower/solvers/record.py"
    assert source["historical_source_verified"] is False
    assert source["source_sha256"] and source["text"]
    assert database.read_bytes() == before
    assert sent == []


@pytest.mark.parametrize("busy_log", [False, True])
def test_real_ai_tool_loop_inspects_code_then_sends_cited_inference(
    evidence, monkeypatch, tmp_path, busy_log
):
    logs, sent, _ = evidence
    if busy_log:
        with (logs / "runtime.log").open("a", encoding="utf-8") as log:
            for second in range(11, 60):
                log.write(
                    f"2026-10-20 12:00:{second:02d} scheduler.py:1 INFO 训练室 "
                    + "x" * 950
                    + "\n"
                )
    round_number = 0
    inspected = None
    inspection_args = {"start_time": START, "end_time": END, "focus_terms": ["训练室"]}

    def stream(messages):
        nonlocal inspected, round_number
        round_number += 1
        if round_number == 1:
            yield AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "inspect_feedback",
                        "args": inspection_args,
                        "id": "inspect",
                    }
                ],
            )
        elif round_number == 2:
            result = messages[-1].content.split("\n", 1)[-1]
            assert len(result) <= MAX_RESULT_CHARS
            report = json.loads(result)
            inspected = report["references"]
            source = inspected["sources"][0]
            assert any(row["id"] == source["record_id"] for row in inspected["records"])
            analysis = {
                "status": "analyzed",
                "claims": [
                    {
                        "kind": "code_inference",
                        "text": "源码定义记录结构；这条错误尚不能证明训练已开始。",
                        "references": [source["record_id"], source["id"]],
                    }
                ],
                "unknowns": ["故障发生时的源码版本和实际训练状态仍未确认。"],
            }
            yield AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "submit_issue",
                        "id": "submit",
                        "args": {
                            **inspection_args,
                            "description": "用户观察：训练未开始。期望：正常开始。",
                            "analysis": analysis,
                        },
                    }
                ],
            )
        else:
            assert messages[-1].content.endswith("邮件发送成功！")
            yield AIMessage(content="已反馈，并注明待确认事项。")

    model = Mock()
    model.stream.side_effect = stream
    monkeypatch.setattr(agent, "build_llm", lambda *args, **kwargs: model)
    monkeypatch.setattr(agent.config.conf, "ai_type", "custom-local")
    monkeypatch.setattr(agent.config.conf, "ai_context_tokens", 256000)
    monkeypatch.setattr(ai_history, "get_path", lambda _: tmp_path / "chat.sqlite3")
    store = ai_history.HistoryStore("feedback-profile")
    approvals = []
    question = "请反馈训练问题并分析相关代码"
    with store.turn(None, question) as turn:

        def send(frame):
            event = frame["event"]
            if event["type"] == "approval":
                approvals.append(event)
                assert not sent
                run.control("approve", event["approval_id"], event["digest"])

        run = Execution(store, turn, send)
        with run.registered():
            result = list(agent.ask_llm(question, api_key="offline-key", execution=run))
    assert len(approvals) == 1
    assert (
        approvals[0]["preview"]["content"]["description"]
        == "用户观察：训练未开始。期望：正常开始。"
    )
    assert result[-1] == "已反馈，并注明待确认事项。"
    contents = parts(sent)
    index = json.loads(contents["references.json"])
    if busy_log:
        assert len(json.dumps(index, ensure_ascii=False)) > MAX_RESULT_CHARS
        assert (
            inspected["coverage"]["inspection_omitted_records"]
            == len(index["records"]) - len(inspected["records"])
            > 0
        )
        assert inspected["sources"] == index["sources"]
        assert all(row in index["records"] for row in inspected["records"])
        assert ("x" * 950).encode() in contents["runtime.log"]
    else:
        assert inspected == index
    analysis = json.loads(contents["analysis.json"])
    source = index["sources"][0]
    assert analysis["claims"][0]["references"] == [source["record_id"], source["id"]]
    assert source["text"].encode() in contents["references.json"].replace(
        b"\\n", b"\n"
    ).replace(b'\\"', b'"')
    assert "推断" in analysis["note"]
    assert "failed" in contents["mastery_plans.jsonl"].decode()
    body = next(
        part.get_payload(decode=True).decode()
        for part in sent[0][0].walk()
        if part.get_content_type() == "text/html"
    )
    assert "AI 分析（推断" in body
    assert "arknights_mower/solvers/record.py:" in body
    assert source["id"] in body
    assert all(not name.endswith(".zip") for name in contents)


def test_unknown_reference_is_rejected_before_email(evidence):
    _, sent, _ = evidence
    result = submit_issue.submit_issue_ai(
        description="训练问题",
        start_time=START,
        end_time=END,
        analysis={
            "status": "analyzed",
            "claims": [
                {
                    "kind": "log_interpretation",
                    "text": "没有执行",
                    "references": ["made-up"],
                }
            ],
            "unknowns": [],
        },
    )
    assert "引用不属于" in result
    assert not sent


def test_changed_record_cannot_reuse_inspected_reference(evidence):
    logs, sent, _ = evidence
    index = inspect()["references"]
    record = next(row for row in index["records"] if row["kind"] == "runtime_log")
    write_logs(logs, [(10, "ERROR", "原始记录已变更")])
    result = submit_issue.submit_issue_ai(
        description="训练问题",
        start_time=START,
        end_time=END,
        analysis={
            "status": "analyzed",
            "claims": [
                {
                    "kind": "log_interpretation",
                    "text": "保留原任务",
                    "references": [record["id"]],
                }
            ],
            "unknowns": [],
        },
    )
    assert "引用不属于" in result
    assert not sent


def test_ai_cannot_send_without_analysis_or_unknown_report(evidence):
    _, sent, _ = evidence
    result = submit_issue.submit_issue_ai(
        description="训练问题", start_time=START, end_time=END
    )
    assert "尚未发送" in result and "inspect_feedback" in result
    assert not sent


def test_supplementary_window_keeps_prior_task_and_final_zip_sizes(evidence):
    logs, sent, _ = evidence
    path = logs / "runtime.log"
    path.write_text(
        "2026-10-20 11:30:05 scheduler.py:1 INFO 原始任务创建\n" + path.read_text(),
        encoding="utf-8",
    )
    windows = [
        {
            "start_time": "2026-10-20 11:30:00",
            "end_time": "2026-10-20 11:31:00",
            "reason": "原任务早于故障时段创建",
        }
    ]
    report = inspect(evidence_windows=windows)
    assert any(
        row["member"] == "windows/1/runtime.log" and "原始任务创建" in row["text"]
        for row in report["references"]["records"]
    )
    assert (
        submit_issue.submit_issue(
            "训练问题",
            start_time=START,
            end_time=END,
            evidence_windows=windows,
        )
        == "邮件发送成功！"
    )
    contents = parts(sent)
    assert "原始任务创建" in contents["windows/1/runtime.log"].decode()
    manifest = json.loads(contents["evidence.json"])
    segment = json.loads(contents["windows/1/evidence.json"])
    assert manifest["additional_windows"]["windows"][0]["logs"] == segment["logs"]
    from io import BytesIO
    from zipfile import ZipFile

    attachment = next(part for part in sent[0][0].walk() if part.get_filename())
    with ZipFile(BytesIO(attachment.get_payload(decode=True))) as bundle:
        info = bundle.getinfo("windows/1/runtime.log")
        assert segment["log_archive"]["bytes"] == info.compress_size
        assert segment["log_archive"]["uncompressed_bytes"] == info.file_size
    assert all(not name.endswith(".zip") for name in contents)


def test_large_inspection_preview_keeps_supplementary_window_records(feedback):
    logs, _, sent = feedback
    (logs / "runtime.log").write_text(
        "".join(
            f"2026-10-20 {minute}:{second:02d} scheduler INFO 训练室 "
            + "x" * 950
            + "\n"
            for minute in ("11:30", "12:00")
            for second in range(30)
        ),
        encoding="utf-8",
    )
    arguments = {
        "start_time": START,
        "end_time": END,
        "focus_terms": ["训练室"],
        "evidence_windows": [
            {
                "start_time": "2026-10-20 11:30:00",
                "end_time": "2026-10-20 11:31:00",
                "reason": "核对问题发生前的训练室记录",
            }
        ],
    }
    result = submit_issue.inspect_feedback(**arguments)
    assert len(result) <= MAX_RESULT_CHARS
    preview = json.loads(result)["references"]
    assert sent == []
    assert submit_issue.submit_issue("训练室问题", **arguments) == "邮件发送成功！"
    index = json.loads(parts(sent)["references.json"])

    primary, supplementary = "runtime.log", "windows/1/runtime.log"
    full_records = index["records"]
    assert Counter(row["member"] for row in full_records) == {
        primary: 24,
        supplementary: 24,
    }
    preview_records = preview["records"]
    counts = Counter(row["member"] for row in preview_records)
    assert counts[primary] and counts[supplementary], counts
    assert abs(counts[primary] - counts[supplementary]) <= 1
    assert preview["coverage"]["inspection_omitted_records"] == len(full_records) - len(
        preview_records
    )
    shown = {row["id"] for row in preview_records}
    assert preview_records == [row for row in full_records if row["id"] in shown]


@pytest.mark.parametrize("token", [None, "incorrect"])
def test_chat_rejects_feedback_inspection_before_model_or_collection(
    monkeypatch, token
):
    import server
    from arknights_mower.tests.ai_security_tests import FakeSocket

    monkeypatch.setattr(server.app, "token", "inspection-token", raising=False)
    forbidden = Mock(side_effect=AssertionError("未授权请求不能读取反馈材料"))
    monkeypatch.setattr(agent, "ask_llm", forbidden)
    monkeypatch.setitem(agent.tool_func_map, "inspect_feedback", forbidden)
    frames = [json.dumps({"message": "inspect_feedback"})]
    if token is not None:
        frames.insert(0, json.dumps({"token": token}))
    socket = FakeSocket(*frames)
    with server.app.test_request_context(
        "/ws/chat", headers={"Host": "localhost", "Origin": "http://localhost"}
    ):
        server.app.view_functions["ws_chat"].__wrapped__(socket)
    assert socket.closed
    forbidden.assert_not_called()
