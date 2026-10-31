"""反馈邮件的离线证据筛选与附件限制。"""

import json
from datetime import datetime

import pytest

from arknights_mower.agent.tools import issue_evidence, submit_issue

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
    return {
        part.get_filename(): part.get_payload(decode=True)
        for part in sent[0][0].walk()
        if part.get_filename()
    }


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
    assert len(attachments["runtime.txt"].decode().splitlines()) == 1000
    manifest = json.loads(attachments["evidence.json"])
    assert manifest["log_rows_truncated"] is True
    assert manifest["log_messages_truncated"] is True


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


def test_feature_feedback_does_not_collect_logs(feedback, monkeypatch):
    _, _, sent = feedback

    def forbidden(*args):
        raise AssertionError("功能建议不读取日志")

    monkeypatch.setattr(submit_issue, "collect_evidence", forbidden)
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
