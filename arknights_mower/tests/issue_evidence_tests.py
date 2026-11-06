"""反馈邮件的离线证据筛选与附件限制。"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from email import policy
from email.parser import BytesParser
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile

import pytest

from arknights_mower.agent.tools import issue_evidence, submit_issue
from arknights_mower.tests import feedback_records_tests

feedback_database = feedback_records_tests.database

START = "2026-10-20 12:00:00"
END = "2026-10-20 12:01:00"


@pytest.fixture
def feedback(tmp_path, monkeypatch):
    logs, images = tmp_path / "log", tmp_path / "screenshot"
    logs.mkdir()
    images.mkdir()
    monkeypatch.setattr(
        submit_issue, "get_path", lambda name: logs if name == "@app/log" else images
    )
    sent = []

    def send(email, recipients):
        sent.append((email.msg, recipients))

    monkeypatch.setattr(submit_issue.Email, "send", send)
    return logs, images, sent


def image(folder, second, data=b"unique screenshot", archive=False):
    stamp = int(datetime(2026, 10, 20, 12, 0, second).timestamp() * 10**9)
    target = folder / ("errors/123" if archive else "20261020-12") / f"{stamp}.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def write_logs(folder, lines):
    (folder / "runtime.log").write_text(
        "\n".join(
            f"2026-10-20 12:00:{second:02d} solver.py:1 {level} {text}"
            for second, level, text in lines
        ),
        encoding="utf-8",
    )


def parts(sent):
    attachments = {
        part.get_filename(): part.get_payload(decode=True)
        for part in sent[0][0].walk()
        if part.get_filename()
    }
    if len(attachments) != 1 or not next(iter(attachments), "").endswith(".zip"):
        return attachments
    with ZipFile(BytesIO(next(iter(attachments.values())))) as bundle:
        return {name: bundle.read(name) for name in bundle.namelist()}


def submit(**kwargs):
    return submit_issue.submit_issue(
        "选人失败，期望正常进驻", start_time=START, end_time=END, **kwargs
    )


def test_real_mail_selects_distinct_errors_and_deduplicates_bytes(feedback):
    logs, images, sent = feedback
    image(images, 0, b"normal")
    image(images, 10, b"failure")
    image(images, 15, b"duplicate repeated error")
    image(images, 20, b"failure", archive=True)
    image(images, 30, b"confirmation failure")
    write_logs(
        logs,
        [
            (0, "INFO", "正常运行"),
            (10, "ERROR", "选人失败"),
            (15, "ERROR", "选人失败"),
            (20, "ERROR", "进入失败"),
            (30, "CRITICAL", "确认失败"),
        ],
    )
    assert submit() == "邮件发送成功！"
    attachments = parts(sent)
    selected = {data for name, data in attachments.items() if name.endswith(".jpg")}
    assert selected == {b"failure", b"confirmation failure"}
    manifest = json.loads(attachments["evidence.json"])
    assert len(manifest["screenshots"]) == 2
    assert "ERROR" in manifest["screenshots"][0]["reason"]
    assert sent[0][1] == ["354013233@qq.com", "1273725854@qq.com"]
    assert len(sent[0][0].as_bytes()) < issue_evidence.MAX_MAIL_BYTES


def test_ai_feedback_tool_sends_database_evidence_with_original_fields(
    feedback, feedback_database, monkeypatch
):
    from unittest.mock import patch

    from langchain_core.messages import AIMessage

    from arknights_mower.agent import agent

    logs, _, sent = feedback
    write_logs(logs, [(10, "ERROR", "换班未完成")])
    get_path = submit_issue.get_path
    monkeypatch.setattr(
        submit_issue,
        "get_path",
        lambda name: (
            feedback_database if name == "@app/tmp/data.db" else get_path(name)
        ),
    )
    with closing(sqlite3.connect(feedback_database)) as connection, connection:
        connection.execute(
            "INSERT INTO log VALUES (?, ?, ?, ?)",
            (
                datetime.fromisoformat(START).timestamp(),
                "待执行任务",
                "ERROR",
                "首行\n详情",
            ),
        )
        connection.execute(
            "INSERT INTO agent_action (name,current_time,mood,current_room,related_operator,context_key,current_index) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "歌蕾蒂娅",
                "2026-10-20 12:00:10.125",
                15.25,
                "dormitory_1",
                "菲亚梅塔",
                "normal",
                4,
            ),
        )
        connection.execute(
            "INSERT INTO saved_state VALUES ('private', ?)", (b"private-blob",)
        )
    description = (
        "用户观察：换班未完成。\n期望行为：完成进驻。\n复现条件：未知。\n"
        "已查证据：12:00:10 的换班错误。\nAI推断：原因未定位。\n未确认事项：替班是否可用。"
    )
    call = {
        "name": "submit_issue",
        "args": {
            "description": description,
            "start_time": START,
            "end_time": END,
            "analysis": {
                "status": "unknown",
                "claims": [],
                "unknowns": ["替班是否可用尚未确认。"],
            },
        },
        "id": "bug-evidence",
    }
    with patch.object(agent, "build_llm") as build:
        build.return_value.invoke.side_effect = [
            AIMessage(content="", tool_calls=[call]),
            AIMessage(content="反馈已发送"),
        ]
        result = agent._run_manual_tool_loop(
            agent._build_messages("请反馈换班问题"), "offline-key"
        )
    assert result[-1] == "反馈已发送"
    attachments = parts(sent)
    tasks = [
        json.loads(line) for line in attachments["task_history.jsonl"].splitlines()
    ]
    operators = [
        json.loads(line) for line in attachments["operator_history.jsonl"].splitlines()
    ]
    assert tasks[0]["task"] == "待执行任务"
    assert tasks[0]["message"] == "首行\n详情"
    assert operators[0]["mood"] == 15.25
    assert operators[0]["current_time"] == "2026-10-20 12:00:10.125"
    assert operators[0]["current_room"] == "dormitory_1"
    assert operators[0]["related_operator"] == "菲亚梅塔"
    assert operators[0]["current_index"] == 4
    assert operators[0]["context_key"] == "normal"
    assert "AI推断：原因未定位" in attachments["readme.txt"].decode()
    assert all(b"private-blob" not in data for data in attachments.values())
    manifest = json.loads(attachments["evidence.json"])
    assert manifest["database_records"]["tables"]["log"]["row_count"] == 1
    assert manifest["database_records"]["tables"]["agent_action"]["row_count"] == 1


def test_missing_database_is_disclosed_without_creating_it(
    feedback, tmp_path, monkeypatch
):
    logs, _, sent = feedback
    write_logs(logs, [(10, "ERROR", "可用的运行日志")])
    database = tmp_path / "missing" / "data.db"
    get_path = submit_issue.get_path
    monkeypatch.setattr(
        submit_issue,
        "get_path",
        lambda name: database if name == "@app/tmp/data.db" else get_path(name),
    )
    assert submit() == "邮件发送成功！"
    attachments = parts(sent)
    assert "task_history.jsonl" not in attachments
    assert "operator_history.jsonl" not in attachments
    assert "runtime.log" in attachments
    metadata = json.loads(attachments["evidence.json"])["database_records"]
    assert all(
        row["reason"] == "missing_database" for row in metadata["tables"].values()
    )
    assert not database.exists() and not database.parent.exists()


def test_automatic_screenshot_keeps_early_error_outside_tail_preview(feedback):
    logs, images, sent = feedback
    image(images, 10, b"earliest relevant error")
    write_logs(
        logs,
        [
            (10, "ERROR", "最初进房失败"),
            *[(20, "DEBUG", f"后续帧{index}") for index in range(1200)],
        ],
    )
    assert submit() == "邮件发送成功！"
    attachments = parts(sent)
    metadata = json.loads(attachments["evidence.json"])
    selected = metadata["screenshots"][0]
    assert attachments[selected["file"]] == b"earliest relevant error"
    assert selected["anchor_time"] == "2026-10-20 12:00:10"
    assert "最初进房失败" not in attachments["runtime.txt"].decode()


def test_bug_sends_one_zip_matching_log_export_layout(feedback):
    from arknights_mower.utils.diagnostics import export_bundle

    logs, images, sent = feedback
    image(images, 10, b"selected original image")
    write_logs(logs, [(10, "ERROR", "进驻失败")])
    assert submit() == "邮件发送成功！"
    attachments = [part for part in sent[0][0].walk() if part.get_filename()]
    assert len(attachments) == 1
    assert attachments[0].get_filename() == (
        "feedback-20261020-120000-选人失败，期望正常进驻.zip"
    )
    with ZipFile(BytesIO(attachments[0].get_payload(decode=True))) as bundle:
        assert bundle.testzip() is None
        names = set(bundle.namelist())
        assert {
            "runtime.log",
            "runtime.txt",
            "readme.txt",
            "context.json",
            "plan.json",
            "evidence.json",
        } <= names
        assert not any(name.endswith(".zip") for name in names)
        metadata = json.loads(bundle.read("evidence.json"))
        selected = metadata["screenshots"][0]
        assert selected["file"] == f"screenshots/{selected['source']}"
        assert bundle.read(selected["file"]) == b"selected original image"
        assert bundle.getinfo(selected["file"]).compress_type == 0
        info = bundle.getinfo("runtime.log")
        assert info.compress_type == 8
        assert metadata["log_archive"]["file"] == "runtime.log"
        assert metadata["log_archive"]["bytes"] == info.compress_size
        assert metadata["log_archive"]["uncompressed_bytes"] == info.file_size
        plan = json.loads(bundle.read("plan.json"))
        with export_bundle(
            logs,
            images,
            datetime.fromisoformat(START),
            start=datetime.fromisoformat(START),
            end=datetime.fromisoformat(END),
            scheduling_plan=plan,
        ) as exported:
            with ZipFile(exported) as ordinary:
                assert {
                    "runtime.log",
                    "readme.txt",
                    "plan.json",
                    selected["file"],
                } <= set(ordinary.namelist())
                assert (
                    bundle.read("runtime.log").splitlines()
                    == ordinary.read("runtime.log").splitlines()
                )
                assert bundle.read(selected["file"]) == ordinary.read(selected["file"])
                assert bundle.read("plan.json") == ordinary.read("plan.json")
                for archive in (bundle, ordinary):
                    explanation = archive.read("readme.txt").decode()
                    assert START in explanation and END in explanation
                    assert "当前保存" in explanation


@pytest.mark.parametrize(
    "problem",
    [
        "办公室进房失败",
        "room selection failed",
        "办公室 room selection failed",
        "room; failed",
        "failure",
    ],
)
@pytest.mark.parametrize(
    "wire_policy", [policy.compat32, policy.SMTP], ids=["message-default", "smtp"]
)
def test_feedback_zip_filename_survives_mime_serialization(
    feedback, problem, wire_policy
):
    logs, _, sent = feedback
    write_logs(logs, [(10, "ERROR", "故障原始记录")])
    assert (
        submit_issue.submit_issue(problem, start_time=START, end_time=END)
        == "邮件发送成功！"
    )
    original = sent[0][0]
    parsed = BytesParser(policy=policy.default).parsebytes(
        original.as_bytes(policy=wire_policy)
    )
    attachments = list(parsed.iter_attachments())
    assert len(attachments) == 1
    attachment = attachments[0]
    assert attachment.get_content_disposition() == "attachment"
    assert attachment.get_filename() == f"feedback-20261020-120000-{problem}.zip"
    assert not attachment["Content-Disposition"].defects
    with ZipFile(BytesIO(attachment.get_payload(decode=True))) as bundle:
        assert bundle.testzip() is None
        assert "故障原始记录" in bundle.read("runtime.log").decode()


@pytest.mark.parametrize(
    "description,expected_problem",
    [
        (
            "\n版本：4.1.6\n平台：Android\n\n宿舍选人失败，无法进驻\n第二行细节",
            "宿舍选人失败，无法进驻",
        ),
        ("Version: 4.1.6\nPlatform: Windows\n\n办公室异常\n期望正常进入", "办公室异常"),
    ],
)
def test_bundle_name_uses_problem_line_after_version_and_platform(
    feedback, description, expected_problem
):
    logs, _, sent = feedback
    write_logs(logs, [(10, "ERROR", "故障")])
    assert (
        submit_issue.submit_issue(description, start_time=START, end_time=END)
        == "邮件发送成功！"
    )
    attachments = [part for part in sent[0][0].walk() if part.get_filename()]
    assert [part.get_filename() for part in attachments] == [
        f"feedback-20261020-120000-{expected_problem}.zip"
    ]


def test_bundle_problem_name_removes_unsafe_characters_and_limits_length(feedback):
    import unicodedata

    logs, _, sent = feedback
    write_logs(logs, [(10, "ERROR", "故障")])
    description = '../选人失败\\:*?"<>|\x00\x01' + "无法进驻" * 30
    assert (
        submit_issue.submit_issue(description, start_time=START, end_time=END)
        == "邮件发送成功！"
    )
    attachments = [part for part in sent[0][0].walk() if part.get_filename()]
    assert len(attachments) == 1
    name = attachments[0].get_filename()
    assert name.startswith("feedback-20261020-120000-") and name.endswith(".zip")
    problem = name.removeprefix("feedback-20261020-120000-").removesuffix(".zip")
    assert "选人失败" in problem
    assert 0 < len(problem) <= 40
    assert not any(character in problem for character in '/\\:*?"<>|')
    assert not any(
        unicodedata.category(character).startswith("C") for character in problem
    )
    assert PurePosixPath(name).name == name


def test_explicit_key_times_override_unrelated_errors_and_allow_no_images(feedback):
    logs, images, sent = feedback
    image(images, 0, b"unrelated error")
    image(images, 20, b"important arrangement")
    write_logs(logs, [(0, "ERROR", "无关报错"), (20, "INFO", "驻员名单异常")])
    assert submit(screenshot_times=["2026-10-20 12:00:21"]) == "邮件发送成功！"
    assert [data for name, data in parts(sent).items() if name.endswith(".jpg")] == [
        b"important arrangement"
    ]
    sent.clear()
    assert submit(screenshot_times=[]) == "邮件发送成功！"
    assert not any(name.endswith(".jpg") for name in parts(sent))


def test_archived_logs_and_screenshots_survive_normal_retention(feedback):
    logs, images, sent = feedback
    target = image(images, 10, b"archived failure", archive=True)
    (target.parent / "logs.json").write_text(
        json.dumps(
            [
                {
                    "time": "2026-10-20 12:00:10",
                    "message": "2026-10-20 12:00:10 solver.py:1 ERROR 选人失败",
                },
                {"time": "2026-10-20 13:00:00", "message": "范围外隐私内容"},
                None,
            ]
        ),
        encoding="utf-8",
    )
    assert submit() == "邮件发送成功！"
    attachments = parts(sent)
    assert b"archived failure" in attachments.values()
    assert "范围外隐私内容" not in attachments["runtime.txt"].decode()


def test_legacy_png_archive_screenshots_remain_available(feedback):
    logs, images, sent = feedback
    stamp = int(datetime(2026, 10, 20, 12, 0, 10).timestamp() * 10**9)
    archive = images / "errors" / "123"
    archive.mkdir(parents=True)
    (archive / f"{stamp}.png").write_bytes(b"legacy png failure")
    (archive / "logs.json").write_text(
        json.dumps(
            [
                {
                    "time": "2026-10-20 12:00:10",
                    "message": "2026-10-20 12:00:10 solver.py:1 ERROR 选人失败",
                }
            ]
        ),
        encoding="utf-8",
    )
    write_logs(logs, [(10, "INFO", "正常运行")])
    assert submit() == "邮件发送成功！"
    assert b"legacy png failure" in parts(sent).values()


def test_image_count_size_and_stale_frame_limits(feedback):
    logs, images, sent = feedback
    for second in range(10, 16):
        image(images, second, bytes([second]) * issue_evidence.MAX_IMAGE_BYTES)
    image(images, 0, b"oversize" * issue_evidence.MAX_IMAGE_BYTES)
    write_logs(
        logs,
        [
            (0, "ERROR", "超大图片"),
            *[
                (second, "ERROR", f"独立故障{chr(65 + second)}")
                for second in range(10, 16)
            ],
        ],
    )
    assert submit() == "邮件发送成功！"
    selected = [data for name, data in parts(sent).items() if name.endswith(".jpg")]
    assert len(selected) == 4
    assert sum(map(len, selected)) == 2 * 1024**2
    sent.clear()
    assert submit(screenshot_times=["2026-10-20 12:01:00"]) == "邮件发送成功！"
    assert not any(name.endswith(".jpg") for name in parts(sent))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_time": END, "end_time": START},
        {"start_time": START, "end_time": START},
        {"start_time": START, "end_time": "2026-10-20 12:16:00"},
        {"start_time": "bad", "end_time": END},
        {"screenshot_times": [START] * 5},
        {"screenshot_times": ["2026-10-20 11:59:00"]},
        {"screenshot_times": "not a list"},
    ],
)
def test_invalid_arguments_never_send(feedback, kwargs):
    logs, images, sent = feedback
    write_logs(logs, [(10, "ERROR", "选人失败")])
    arguments = {"start_time": START, "end_time": END, **kwargs}
    assert submit_issue.submit_issue("故障", **arguments) != "邮件发送成功！"
    assert sent == []


def test_missing_or_disappearing_screenshots_do_not_block_logs(feedback, monkeypatch):
    logs, images, sent = feedback
    target = image(images, 10)
    write_logs(logs, [(10, "ERROR", "故障")])
    original = issue_evidence._images

    def removed(*args):
        found = original(*args)
        target.unlink()
        return found

    monkeypatch.setattr(issue_evidence, "_images", removed)
    assert submit() == "邮件发送成功！"
    assert not any(name.endswith(".jpg") for name in parts(sent))
    sent.clear()
    (logs / "runtime.log").unlink()
    assert "未找到对应时间" in submit()
    assert sent == []


def test_log_excerpt_bounds_and_truncation_are_disclosed(feedback):
    logs, images, sent = feedback
    write_logs(
        logs, [(10, "INFO", f"行{index}" + "长" * 1500) for index in range(1002)]
    )
    assert submit() == "邮件发送成功！"
    attachments = parts(sent)
    assert len(attachments["runtime.txt"]) <= issue_evidence.MAX_EXCERPT_BYTES
    assert len(attachments["runtime.txt"].decode().splitlines()) <= 1000
    manifest = json.loads(attachments["evidence.json"])
    assert manifest["log_rows_truncated"] is True
    assert manifest["log_messages_truncated"] is True
    contents = attachments["runtime.log"].decode()
    assert len(contents.splitlines()) == 1002
    assert "行0" + "长" * 1500 in contents
    assert "行1001" + "长" * 1500 in contents
    assert manifest["log_archive"]["truncated"] is False


def test_compressed_logs_keep_interval_start_across_hour_and_duplicate_records(
    feedback,
):
    logs, _, sent = feedback
    first = "2026-10-20 11:59:05 solver.py:1 ERROR 最初失败\n"
    (logs / "runtime.log.2026-10-20_11").write_text(first * 2, encoding="utf-8")
    write_logs(logs, [(20, "DEBUG", f"后续读图{index}") for index in range(1200)])
    assert (
        submit_issue.submit_issue(
            "问题发生后不断读图", start_time="2026-10-20 11:59:00", end_time=END
        )
        == "邮件发送成功！"
    )
    attachments = parts(sent)
    contents = attachments["runtime.log"].decode()
    assert contents.startswith(first * 2)
    assert "后续读图1199" in contents
    manifest = json.loads(attachments["evidence.json"])
    assert manifest["log_archive"]["record_count"] == 1202
    assert manifest["log_archive"]["first_time"] == "2026-10-20 11:59:05"
    assert manifest["log_archive"]["last_time"] == "2026-10-20 12:00:20"
    assert manifest["log_archive"]["scan_complete"] is True
    assert manifest["excerpt"]["first_time"] == "2026-10-20 12:00:20"


def test_compressed_logs_preserve_long_rosters_and_multiline_stack(feedback):
    logs, _, sent = feedback
    roster = "全部驻员" * 40000
    stack = "\n".join(f"  File solver.py, line {index}" for index in range(500))
    original = (
        "2026-10-20 11:59:59 solver.py:1 INFO 范围外隐私\n"
        f"2026-10-20 12:00:10 solver.py:1 ERROR {roster}\n{stack}\n"
        "RuntimeError: 真正失败原因\n"
        "2026-10-20 12:01:01 solver.py:1 INFO 范围外尾部\n"
    )
    (logs / "runtime.log").write_text(original, encoding="utf-8")
    assert submit() == "邮件发送成功！"
    contents = parts(sent)["runtime.log"].decode()
    assert roster in contents and stack in contents
    assert "RuntimeError: 真正失败原因" in contents
    assert "范围外" not in contents


def test_archive_byte_budget_is_reported_without_claiming_complete_logs(
    feedback, monkeypatch
):
    logs, _, sent = feedback
    write_logs(logs, [(second, "INFO", "内容" * 80) for second in range(20)])
    monkeypatch.setattr(issue_evidence, "MAX_LOG_UNCOMPRESSED_BYTES", 1100)
    assert submit() == "邮件发送成功！"
    attachments = parts(sent)
    contents = attachments["runtime.log"]
    metadata = json.loads(attachments["evidence.json"])["log_archive"]
    assert len(contents) <= 1100
    assert metadata["uncompressed_bytes"] == len(contents)
    assert metadata["truncated"] is True
    assert metadata["scan_complete"] is False
    assert metadata["first_time"] == "2026-10-20 12:00:00"
    assert metadata["last_time"] == "2026-10-20 12:00:01"


def test_archive_fallback_is_marked_as_a_limited_source(feedback):
    _, images, sent = feedback
    folder = images / "errors" / "123"
    folder.mkdir(parents=True)
    (folder / "logs.json").write_text(
        json.dumps([{"time": START, "message": f"{START} solver.py:1 ERROR 归档故障"}]),
        encoding="utf-8",
    )
    assert submit() == "邮件发送成功！"
    metadata = json.loads(parts(sent)["evidence.json"])["log_archive"]
    assert metadata["source"] == "error_archive_excerpt"
    assert metadata["archive_source_limited"] is True
    assert metadata["record_count"] == 1


def test_compressed_byte_budget_produces_a_readable_bounded_zip(feedback, monkeypatch):
    import base64
    import random

    logs, _, sent = feedback
    generator = random.Random(42)
    write_logs(
        logs,
        [
            (second, "DEBUG", base64.b64encode(generator.randbytes(64 * 1024)).decode())
            for second in range(8)
        ],
    )
    monkeypatch.setattr(issue_evidence, "MAX_LOG_ARCHIVE_BYTES", 256 * 1024)
    assert submit() == "邮件发送成功！"
    attachments = parts(sent)
    message_files = [part for part in sent[0][0].walk() if part.get_filename()]
    with ZipFile(BytesIO(message_files[0].get_payload(decode=True))) as bundle:
        assert bundle.testzip() is None
        assert b"2026-10-20 12:00:00" in bundle.read("runtime.log")
    metadata = json.loads(attachments["evidence.json"])["log_archive"]
    assert metadata["bytes"] <= 256 * 1024
    assert metadata["truncated"] is True
    assert metadata["scan_complete"] is False


def test_unwritten_error_archive_is_not_claimed_as_a_compressed_log_source(
    feedback, monkeypatch
):
    logs, images, sent = feedback
    write_logs(logs, [(second, "INFO", "内容" * 80) for second in range(20)])
    folder = images / "errors" / "123"
    folder.mkdir(parents=True)
    (folder / "logs.json").write_text(
        json.dumps([{"time": START, "message": f"{START} solver.py:1 ERROR 归档故障"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(issue_evidence, "MAX_LOG_UNCOMPRESSED_BYTES", 1100)
    assert submit() == "邮件发送成功！"
    attachments = parts(sent)
    metadata = json.loads(attachments["evidence.json"])["log_archive"]
    assert "归档故障" not in attachments["runtime.log"].decode()
    assert metadata["source"] == "runtime_files"
    assert metadata["archive_source_limited"] is False
    body = next(
        part.get_payload(decode=True).decode()
        for part in sent[0][0].walk()
        if part.get_content_type() == "text/html"
    )
    assert "包含异常归档" not in body


def test_final_encoded_mail_limit_prevents_send(feedback, monkeypatch):
    logs, images, sent = feedback
    write_logs(logs, [(10, "ERROR", "故障")])
    monkeypatch.setattr(submit_issue, "MAX_MAIL_BYTES", 1024)
    assert "尚未发送" in submit()
    assert sent == []


def test_temporary_evidence_is_removed_after_smtp_failure(feedback, monkeypatch):
    logs, images, sent = feedback
    write_logs(logs, [(10, "ERROR", "故障")])
    evidence_paths = []
    original = issue_evidence.collect_evidence

    def collect(*args):
        files = original(*args)
        evidence_paths.extend(files)
        return files

    def failure(*args):
        assert all(path.exists() for path in evidence_paths)
        raise OSError("offline SMTP failure")

    monkeypatch.setattr(submit_issue, "collect_evidence", collect)
    monkeypatch.setattr(submit_issue.Email, "send", failure)
    assert "反馈发送失败" in submit()
    assert evidence_paths and all(not path.exists() for path in evidence_paths)


def test_packaging_failure_never_sends_and_removes_partial_bundle(
    feedback, monkeypatch
):
    from pathlib import Path

    logs, _, sent = feedback
    write_logs(logs, [(10, "ERROR", "故障")])
    partial = []
    original = ZipFile.write

    def fail_on_context(bundle, filename, arcname=None, **kwargs):
        if arcname == "context.json":
            partial.append(Path(bundle.filename))
            raise OSError("offline bundle write failure")
        return original(bundle, filename, arcname=arcname, **kwargs)

    monkeypatch.setattr(ZipFile, "write", fail_on_context)
    assert "反馈发送失败" in submit()
    assert sent == []
    assert partial and all(not path.exists() for path in partial)


def test_feature_feedback_does_not_collect_logs(feedback, monkeypatch):
    _, _, sent = feedback

    def forbidden(*args):
        raise AssertionError("功能建议不读取日志")

    monkeypatch.setattr(submit_issue, "collect_evidence", forbidden)
    monkeypatch.setattr(submit_issue, "collect_feedback_records", forbidden)
    assert submit(issue_type="Feature") == "邮件发送成功！"
    assert parts(sent) == {}


def test_repeated_error_can_use_later_frame_if_first_is_oversized(feedback):
    logs, images, sent = feedback
    image(images, 0, b"x" * (issue_evidence.MAX_IMAGE_BYTES + 1))
    image(images, 10, b"usable failure")
    write_logs(logs, [(0, "ERROR", "选人失败"), (10, "ERROR", "选人失败")])
    assert submit() == "邮件发送成功！"
    assert b"usable failure" in parts(sent).values()


def test_screenshot_links_outside_history_are_not_attached(feedback, tmp_path):
    logs, images, sent = feedback
    target = image(images, 10)
    target.unlink()
    outside = tmp_path / "private.jpg"
    outside.write_bytes(b"not diagnostic evidence")
    target.symlink_to(outside)
    write_logs(logs, [(10, "ERROR", "故障")])
    assert submit() == "邮件发送成功！"
    assert b"not diagnostic evidence" not in parts(sent).values()


def test_empty_error_message_does_not_prevent_feedback(feedback):
    logs, images, sent = feedback
    image(images, 10, b"error frame")
    write_logs(logs, [(10, "ERROR", "")])
    assert submit() == "邮件发送成功！"
    assert b"error frame" in parts(sent).values()
