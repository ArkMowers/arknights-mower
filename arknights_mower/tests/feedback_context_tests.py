"""反馈邮件的配置附件、时间标记和日志覆盖说明。"""

import json
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from io import BytesIO
from zipfile import ZipFile

import pytest

from arknights_mower.agent.tools import submit_issue
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.plan import PlanModel

START = "2026-10-20 12:00:00"
END = "2026-10-20 12:15:00"


@pytest.fixture
def feedback_context(monkeypatch, tmp_path):
    conf = Conf()
    conf.account = "private-account@example.test"
    conf.pass_code = "private-smtp-password"
    conf.ai_key = "private-ai-key"
    conf.webview.token = "private-web-token"
    conf.resting_threshold = 0.6
    conf.right_side_room_order = ["train", "contact", "recycle"]
    plan = PlanModel.model_validate(
        {"conf": {"exhaust_require": "能天使"}, "backup_plans": [{"name": "测试副表"}]}
    )
    monkeypatch.setattr(submit_issue.config, "conf", conf)
    monkeypatch.setattr(submit_issue.config, "plan", plan)
    monkeypatch.setattr(submit_issue, "__version__", "4.1.6-alpha.13+abcdef0")
    monkeypatch.setattr(submit_issue, "revision_info", lambda: "abcdef0123456789")
    monkeypatch.setenv("PRIVATE_FEEDBACK_TEST", "private-environment-secret")
    monkeypatch.setenv("MOWER_ANDROID", "1")
    monkeypatch.setattr(
        submit_issue, "get_path", lambda name: tmp_path / name.removeprefix("@app/")
    )
    sent = []
    monkeypatch.setattr(
        submit_issue.Email, "send", lambda email, recipients: sent.append(email.msg)
    )

    def collect(logs, screenshots, start, end, output, screenshot_times):
        files = []
        for name, data in (
            ("runtime.txt", b"excerpt"),
            ("screenshot-1.jpg", b"image"),
        ):
            path = output / name
            path.write_bytes(data)
            files.append(path)
        log_archive = output / "runtime.zip"
        with ZipFile(log_archive, "w") as archive:
            archive.writestr("runtime.txt", "完整日志\n")
        files.append(log_archive)
        manifest = output / "evidence.json"
        manifest.write_text(
            json.dumps(
                {
                    "screenshots": [
                        {
                            "file": "screenshot-1.jpg",
                            "source": "20261020-12/fixture.jpg",
                            "reason": "故障附近画面",
                        }
                    ],
                    "log_archive": {
                        "file": "runtime.zip",
                        "record_count": 2000,
                        "first_time": "2026-10-20 12:00:02",
                        "last_time": "2026-10-20 12:14:59",
                        "truncated": False,
                        "scan_complete": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        return [*files, manifest]

    monkeypatch.setattr(submit_issue, "collect_evidence", collect)
    return sent


def mail_parts(message):
    files = {
        part.get_filename(): part.get_payload(decode=True)
        for part in message.walk()
        if part.get_filename()
    }
    if len(files) == 1 and next(iter(files)).endswith(".zip"):
        with ZipFile(BytesIO(next(iter(files.values())))) as bundle:
            files = {name: bundle.read(name) for name in bundle.namelist()}
    body = next(
        part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
        for part in message.walk()
        if part.get_content_type() == "text/html"
    )
    return files, body


def send_bug():
    return submit_issue.submit_issue(
        "办公室异常，期望正常进入", start_time=START, end_time=END
    )


def test_bug_context_has_only_selected_settings_and_current_plan(feedback_context):
    assert send_bug() == "邮件发送成功！"
    files, body = mail_parts(feedback_context[0])
    context = json.loads(files["context.json"])
    assert set(context) == {
        "mower_version",
        "revision",
        "platform",
        "generated_at",
        "requested_interval",
        "settings",
        "configuration_note",
        "plan",
    }
    assert context["mower_version"] == "4.1.6-alpha.13+abcdef0"
    assert context["revision"] == "abcdef0123456789"
    assert context["mower_version"] in body
    assert context["revision"] in body
    readme = files["readme.txt"].decode()
    assert context["mower_version"] in readme and context["revision"] in readme
    assert context["platform"]["android"] is True
    assert set(context["platform"]) == {
        "system",
        "release",
        "machine",
        "python",
        "android",
    }
    assert context["settings"] == {
        "right_side_room_order": ["train", "contact", "recycle"]
    }
    plan = json.loads(files["plan.json"])
    assert plan["conf"]["exhaust_require"] == "能天使"
    assert plan["backup_plans"][0]["name"] == "测试副表"
    assert plan["advanced_settings"]["resting_threshold"] == 0.6
    for data in (files["context.json"], files["plan.json"]):
        assert b"private-" not in data
    assert context["plan"]["bytes"] == len(files["plan.json"])
    assert context["plan"]["status"] == "attached"
    assert "反馈生成时当前保存" in body
    assert "附带 1 张关键截图" in body
    assert "12:00:02" in body and "12:14:59" in body and "2000 条" in body
    assert "不代表整个区间内每个时刻都有日志" in body


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="需要操作系统支持TZ切换")
def test_date_and_interval_use_their_own_local_utc_offsets(
    feedback_context, monkeypatch
):
    with monkeypatch.context() as timezone:
        timezone.setenv("TZ", "America/New_York")
        time.tzset()
        try:
            assert send_bug() == "邮件发送成功！"
            message = feedback_context[0]
            files, body = mail_parts(message)
            context = json.loads(files["context.json"])
            assert context["requested_interval"] == {
                "start": "2026-10-20T12:00:00-04:00",
                "end": "2026-10-20T12:15:00-04:00",
            }
            generated = datetime.fromisoformat(context["generated_at"])
            assert parsedate_to_datetime(message["Date"]) == generated
            assert "2026-10-20T12:00:00-04:00" in body
        finally:
            timezone.undo()
            time.tzset()


def test_large_plan_is_attached_completely_with_allowlisted_settings(
    feedback_context, monkeypatch
):
    plan = PlanModel.model_validate({"backup_plans": [{"name": "长" * 90000}]})
    monkeypatch.setattr(submit_issue.config, "plan", plan)
    assert send_bug() == "邮件发送成功！"
    files, body = mail_parts(feedback_context[0])
    assert "plan.json" in files
    attached_plan = json.loads(files["plan.json"])
    assert attached_plan["backup_plans"][0]["name"] == "长" * 90000
    assert attached_plan["advanced_settings"]["resting_threshold"] == 0.6
    assert b"private-" not in files["plan.json"]
    context = json.loads(files["context.json"])
    assert context["plan"]["status"] == "attached"
    assert context["plan"]["bytes"] == len(files["plan.json"]) > 256 * 1024
    assert "当前保存" in body
    assert "省略" not in context["plan"].get("reason", "")


@pytest.mark.parametrize("truncated,complete", [(True, True), (False, False)])
def test_truncated_log_coverage_is_visible_in_body(
    feedback_context, monkeypatch, truncated, complete
):
    original = submit_issue.collect_evidence

    def collect(*args):
        paths = original(*args)
        manifest = paths[-1]
        evidence = json.loads(manifest.read_text(encoding="utf-8"))
        evidence["log_archive"].update(truncated=truncated, scan_complete=complete)
        manifest.write_text(json.dumps(evidence), encoding="utf-8")
        return paths

    monkeypatch.setattr(submit_issue, "collect_evidence", collect)
    assert send_bug() == "邮件发送成功！"
    _, body = mail_parts(feedback_context[0])
    assert ("达到附件字节上限" in body) is truncated
    assert ("日志来源未全部读取" in body) is not complete


def test_missing_archive_and_limited_sources_are_disclosed(
    feedback_context, monkeypatch
):
    original = submit_issue.collect_evidence

    def collect(*args):
        paths = original(*args)
        manifest = paths[-1]
        evidence = json.loads(manifest.read_text(encoding="utf-8"))
        evidence["log_archive"].update(
            file=None,
            first_time=None,
            last_time=None,
            scan_complete=False,
            archive_source_limited=True,
            unreadable_files=["runtime.log"],
        )
        manifest.write_text(json.dumps(evidence), encoding="utf-8")
        return [path for path in paths if path.name != "runtime.zip"]

    monkeypatch.setattr(submit_issue, "collect_evidence", collect)
    assert send_bug() == "邮件发送成功！"
    files, body = mail_parts(feedback_context[0])
    assert "runtime.log" not in files
    assert "runtime.zip" not in files
    assert "压缩日志未附加" in body
    assert "部分日志文件读取失败" in body
    assert "归档来源本身可能已有截断" in body


def test_missing_manifest_is_compatible_with_existing_tool_mocks(
    feedback_context, monkeypatch
):
    def collect(logs, screenshots, start, end, output, screenshot_times):
        path = output / "sample.log"
        path.write_text("可用日志", encoding="utf-8")
        return [path]

    monkeypatch.setattr(submit_issue, "collect_evidence", collect)
    assert send_bug() == "邮件发送成功！"
    _, body = mail_parts(feedback_context[0])
    assert "未提供压缩日志的实际覆盖信息" in body
    assert "附带 0 张关键截图" in body


def test_feature_keeps_existing_attachment_and_date_behavior(
    feedback_context, monkeypatch
):
    def forbidden(*args):
        raise AssertionError("功能建议不读取反馈上下文")

    monkeypatch.setattr(submit_issue, "_feedback_context", forbidden)
    monkeypatch.setattr(submit_issue, "collect_evidence", forbidden)
    assert (
        submit_issue.submit_issue("增加提示", issue_type="Feature") == "邮件发送成功！"
    )
    files, body = mail_parts(feedback_context[0])
    assert files == {}
    assert "Date" not in feedback_context[0]
    assert "增加提示" in body
    assert "4.1.6-alpha.13+abcdef0" in body


@pytest.mark.parametrize(
    "version", [None, "", "  ", "unknown", "UNKNOWN", "未知", "n/a", "4.1.6\nother"]
)
@pytest.mark.parametrize("issue_type", ["Bug", "Feature"])
def test_missing_version_rejects_before_collection_or_email(
    feedback_context, monkeypatch, version, issue_type
):
    from unittest.mock import Mock

    forbidden = Mock(side_effect=AssertionError("缺版本不得读取材料或发送"))
    monkeypatch.setattr(submit_issue, "__version__", version)
    monkeypatch.setattr(submit_issue, "collect_evidence", forbidden)
    monkeypatch.setattr(submit_issue, "collect_feedback_records", forbidden)
    monkeypatch.setattr(submit_issue, "collect_feedback_state", forbidden)
    monkeypatch.setattr(submit_issue, "Email", forbidden)
    result = submit_issue.submit_issue(
        "问题", issue_type=issue_type, start_time=START, end_time=END
    )
    assert "版本" in result and "尚未发送" in result
    forbidden.assert_not_called()
    assert not feedback_context


def test_unavailable_revision_is_distinct_from_required_version(
    feedback_context, monkeypatch
):
    monkeypatch.setattr(submit_issue, "revision_info", lambda: None)
    assert send_bug() == "邮件发送成功！"
    files, body = mail_parts(feedback_context[0])
    context = json.loads(files["context.json"])
    assert context["mower_version"] == "4.1.6-alpha.13+abcdef0"
    assert context["revision"] == "unknown"
    assert "提交号 unknown 表示未取得" in body


def test_inspection_requires_version_before_reading_records(
    feedback_context, monkeypatch
):
    from unittest.mock import Mock

    forbidden = Mock(side_effect=AssertionError("缺版本不得读取材料"))
    monkeypatch.setattr(submit_issue, "__version__", "unknown")
    monkeypatch.setattr(submit_issue, "collect_evidence", forbidden)
    result = json.loads(submit_issue.inspect_feedback(START, END))
    assert "版本" in result["error"] and result["sent"] is False
    forbidden.assert_not_called()
    assert not feedback_context
