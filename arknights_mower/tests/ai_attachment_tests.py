"""Attachment admission, model input and retained ownership through real callers."""

import io
import json
import zipfile
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessageChunk
from PIL import Image

from arknights_mower.tests.ai_execution_tests import run_chat
from arknights_mower.tests.ai_execution_tests import runtime as runtime
from arknights_mower.tests.ai_history_tests import chat_profiles as chat_profiles
from arknights_mower.tests.ai_history_tests import headers
from arknights_mower.tests.ai_history_tests import history as history
from arknights_mower.tests.ai_history_tests import storage as storage
from arknights_mower.utils import ai_attachments, ai_history


def archive(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in entries.items():
            bundle.writestr(name, content)
    return output.getvalue()


def png():
    output = io.BytesIO()
    Image.new("RGB", (10, 10)).save(output, format="PNG")
    return output.getvalue()


def upload(runtime, name="run.log", raw=b"important log", **kwargs):
    return (
        runtime[0]
        .app.test_client()
        .post(
            "/ai/attachments",
            headers=kwargs.pop("headers", headers()),
            data={"file": (io.BytesIO(raw), name)},
            **kwargs,
        )
    )


@pytest.mark.parametrize(
    "name,raw,expected",
    [
        ("run.log", b"log evidence", "log evidence"),
        ("unknown.custom", b"plain source", "plain source"),
        (
            "word.docx",
            archive(
                {
                    "word/document.xml": "<document><p><t>document evidence</t></p></document>"
                }
            ),
            "document evidence",
        ),
        (
            "sheet.xlsx",
            archive(
                {
                    "xl/sharedStrings.xml": "<sst><si><t>sheet evidence</t></si></sst>",
                    "xl/worksheets/sheet1.xml": '<sheet><c r="A1" t="s"><v>0</v></c><c r="B1"><f>1+1</f><v>2</v></c></sheet>',
                }
            ),
            "sheet evidence",
        ),
        (
            "slides.pptx",
            archive({"ppt/slides/slide1.xml": "<slide><t>slide evidence</t></slide>"}),
            "slide evidence",
        ),
        (
            "logs.zip",
            archive({"run.log": "archive evidence", "binary.bin": b"\x00\xff"}),
            "archive evidence",
        ),
        ("screen.png", png(), "data:image/jpeg;base64,"),
        ("document.pdf", b"%PDF-1.7\nexample", "data:application/pdf;base64,"),
    ],
)
def test_upload_reaches_actual_model_and_history(runtime, name, raw, expected):
    response = upload(runtime, name, raw)
    assert response.status_code == 200, response.json
    metadata = response.json
    assert "content" not in metadata
    model = runtime[-1]([AIMessageChunk(content="read")])
    socket = run_chat(runtime, attachment_ids=[metadata["id"]])
    assert socket.sent[-1] == {"done": True}
    messages = json.dumps([m.content for m in model.inputs[0]], ensure_ascii=False)
    assert expected in messages
    saved = runtime[3].read(socket.sent[0]["conversation_id"])["turns"][0]
    assert saved["attachments"] == [metadata]
    assert expected not in json.dumps(saved, ensure_ascii=False)
    runtime[0].app.test_client().delete(
        "/ai/attachments/" + metadata["id"], headers=headers()
    )
    assert runtime[3].read(socket.sent[0]["conversation_id"])["turns"][0][
        "attachments"
    ] == [metadata]


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/ai/attachments"),
        *[
            (method, "/ai/attachments/" + "a" * 32)
            for method in ("DELETE", "GET", "HEAD")
        ],
    ],
)
@pytest.mark.parametrize("token", [None, "wrong"])
def test_upload_and_delete_require_token_before_work(
    runtime, monkeypatch, method, path, token
):
    storage = Mock(side_effect=AssertionError("storage accessed"))
    parser = Mock(side_effect=AssertionError("file parsed"))
    monkeypatch.setattr(runtime[0], "active_chat_history", storage)
    monkeypatch.setattr(ai_attachments, "normalize_attachment", parser)
    response = (
        runtime[0]
        .app.test_client()
        .open(path, method=method, headers={"token": token} if token else {})
    )
    assert response.status_code == 403
    storage.assert_not_called()
    parser.assert_not_called()


@pytest.mark.parametrize(
    "disabled,generation,status", [(True, "0", 403), (False, "stale", 409)]
)
def test_disabled_and_stale_generation_reject_before_work(
    runtime, monkeypatch, disabled, generation, status
):
    monkeypatch.setitem(runtime[0].app.config, "AI_ASSISTANT_ENABLED", not disabled)
    storage = Mock(side_effect=AssertionError("storage accessed"))
    monkeypatch.setattr(runtime[0], "active_chat_history", storage)
    assert upload(runtime, headers=headers(generation)).status_code == status
    assert (
        runtime[0]
        .app.test_client()
        .delete("/ai/attachments/" + "a" * 32, headers=headers(generation))
        .status_code
        == status
    )
    for method in ("GET", "HEAD"):
        assert (
            runtime[0]
            .app.test_client()
            .open(
                "/ai/attachments/" + "a" * 32,
                method=method,
                headers=headers(generation),
            )
            .status_code
            == status
        )
    storage.assert_not_called()


@pytest.mark.parametrize(
    "name,raw",
    [
        ("audio.mp3", b"\xff\x00binary"),
        ("old.doc", b"\xd0\xcf\x11\xe0"),
        ("empty.txt", b""),
        ("large.txt", b"x" * (2 * 1024 * 1024 + 1)),
        ("bad.pdf", b"not a pdf"),
        ("bad.png", b"not an image"),
        ("bad.zip", b"not an archive"),
        ("huge.zip", archive({"run.log": "x" * (8 * 1024 * 1024 + 1)})),
        ("many.zip", archive({f"{i}.txt": "x" for i in range(257)})),
        (
            "entity.docx",
            archive(
                {
                    "word/document.xml": '<!DOCTYPE root [<!ENTITY x "expand">]><root>&x;</root>'
                }
            ),
        ),
        ("no-text.zip", archive({"audio.mp3": b"\xff"})),
    ],
)
def test_invalid_inputs_do_not_save_or_invoke_model(runtime, name, raw):
    model = runtime[-1]()
    response = upload(runtime, name, raw)
    assert response.status_code in (400, 413), response.json
    assert model.inputs == []
    with runtime[3]._db() as db:
        assert db.execute("SELECT count(*) FROM attachments").fetchone()[0] == 0


def test_files_follow_continuation_and_release_with_last_reference(runtime):
    store = runtime[3]
    metadata = upload(runtime).json
    model = runtime[-1](
        [AIMessageChunk(content="first")],
        TimeoutError("timeout"),
        [AIMessageChunk(content="continued")],
    )
    first = run_chat(runtime, attachment_ids=[metadata["id"]])
    identifier = first.sent[0]["conversation_id"]
    second = run_chat(runtime, conversation=identifier)
    source = second.sent[0]["turn_id"]
    # A later interrupted turn retains the input it actually used, even if its source is pruned.
    with store._db() as db:
        db.execute("DELETE FROM turns WHERE id=?", (first.sent[0]["turn_id"],))
    third = run_chat(runtime, conversation=identifier, continue_of=source)
    assert third.sent[-1] == {"done": True}
    assert "important log" in json.dumps([m.content for m in model.inputs[-1]])
    reopened = ai_history.HistoryStore(store.profile_id)
    assert reopened.read(identifier)["turns"][-1]["attachments"] == [metadata]
    reopened.delete(identifier)
    with store._db() as db:
        assert db.execute("SELECT count(*) FROM attachments").fetchone()[0] == 0


def test_ownership_expiry_and_capacity(runtime, monkeypatch):
    store = runtime[3]
    metadata = upload(runtime).json
    other = ai_history.HistoryStore("other-profile")
    other.delete_attachment(metadata["id"])
    with pytest.raises(ai_history.HistoryError):
        with other.turn(None, "read", attachment_ids=[metadata["id"]]):
            pytest.fail("foreign attachment accepted")
    with store._db() as db:
        db.execute("UPDATE attachments SET created=0 WHERE id=?", (metadata["id"],))
    model = runtime[-1]()
    assert "error" in run_chat(runtime, attachment_ids=[metadata["id"]]).sent[-1]
    assert model.inputs == []
    monkeypatch.setattr(ai_attachments, "MAX_PROFILE_BYTES", 1)
    assert upload(runtime).status_code == 413
    monkeypatch.setattr(ai_attachments, "MAX_PROFILE_BYTES", 8 * 1024 * 1024)
    monkeypatch.setattr(ai_attachments, "MAX_INSTANCE_BYTES", 1)
    assert upload(runtime).status_code == 413


def test_attachment_count_summary_and_excerpt(runtime):
    metadata = upload(runtime, raw=b"A" * 6001 + b"tail").json
    assert metadata["truncated"]
    model = runtime[-1]()
    assert "error" in run_chat(runtime, attachment_ids=[metadata["id"]] * 5).sent[-1]
    assert (
        "error"
        in run_chat(runtime, attachment_ids=[metadata["id"]], mode="summary").sent[-1]
    )
    assert not model.inputs
    model = runtime[-1]([AIMessageChunk(content="read")])
    run_chat(runtime, attachment_ids=[metadata["id"]])
    content = json.dumps([m.content for m in model.inputs[0]], ensure_ascii=False)
    assert "tail" in content and "不代表完整文件" in content


@pytest.mark.parametrize(
    "name,raw",
    [
        ("brackets.txt", b"[" * 12000),
        (
            "cells.xlsx",
            archive(
                {
                    "xl/sharedStrings.xml": "<sst><si><t>"
                    + "x" * 20000
                    + "</t></si></sst>",
                    "xl/worksheets/sheet1.xml": "<sheet>"
                    + '<c t="s"><v>0</v></c>' * 1000
                    + "</sheet>",
                }
            ),
        ),
    ],
)
def test_extracted_text_stays_bounded(runtime, name, raw):
    response = upload(runtime, name, raw)
    assert response.status_code == 200
    assert response.json["truncated"]
    with runtime[3]._db() as db:
        payload = json.loads(
            db.execute(
                "SELECT payload FROM attachments WHERE id=?", (response.json["id"],)
            ).fetchone()[0]
        )
    assert len(payload["content"]) <= 6000


@pytest.mark.parametrize("count", [2, 3, 4])
def test_continue_counts_shared_files_once_and_preserves_original_requirements(
    runtime, count
):
    files = [
        upload(runtime, f"log-{i}.txt", f"evidence-{i}".encode()).json["id"]
        for i in range(count)
    ]
    model = runtime[-1](
        [AIMessageChunk(content="first analysis")],
        TimeoutError("timeout"),
        [AIMessageChunk(content="continued analysis")],
    )
    first = run_chat(
        runtime, message="重点检查订单，不要分析训练", attachment_ids=files
    )
    identifier = first.sent[0]["conversation_id"]
    second = run_chat(
        runtime, conversation=identifier, message="按照刚才的目标深入分析"
    )
    third = run_chat(
        runtime, conversation=identifier, continue_of=second.sent[0]["turn_id"]
    )
    assert third.sent[-1] == {"done": True}
    content = json.dumps([m.content for m in model.inputs[-1]], ensure_ascii=False)
    assert "重点检查订单，不要分析训练" in content
    assert "按照刚才的目标深入分析" in content
    for i in range(count):
        assert f"evidence-{i}" in content
    blocks = [
        block
        for message in model.inputs[-1]
        if isinstance(message.content, list)
        for block in message.content
    ]
    assert (
        sum(block.get("text", "").startswith("用户附件：") for block in blocks) == count
    )


@pytest.mark.parametrize(
    "name,raw,kind",
    [
        ("run.log", b"x" * 8000 + b"evidence", "text"),
        ("screen.png", png(), "image"),
        ("document.pdf", b"%PDF-1.7\nexample", "pdf"),
    ],
)
def test_preview_returns_saved_input_without_model_call(runtime, name, raw, kind):
    model = runtime[-1]()
    metadata = upload(runtime, name, raw).json
    client = runtime[0].app.test_client()
    path = "/ai/attachments/" + metadata["id"]
    response = client.get(path, headers=headers())
    assert response.status_code == 200
    assert response.json["kind"] == kind
    if kind == "text":
        assert response.json["content"] == raw.decode()[-6000:]
        assert response.json["truncated"]
    elif kind == "image":
        assert response.json["content"].startswith("data:image/jpeg;base64,")
    else:
        assert "content" not in response.json
    assert client.head(path, headers=headers()).status_code == 200
    assert model.inputs == []


def test_preview_rejects_foreign_expired_and_deleted_attachments(runtime):
    client = runtime[0].app.test_client()
    metadata = upload(runtime).json
    path = "/ai/attachments/" + metadata["id"]
    with runtime[3]._db() as db:
        db.execute(
            "UPDATE attachments SET profile='other' WHERE id=?", (metadata["id"],)
        )
    assert client.get(path, headers=headers()).status_code == 404
    with runtime[3]._db() as db:
        db.execute(
            "UPDATE attachments SET profile=?,created=0 WHERE id=?",
            (runtime[3].profile_id, metadata["id"]),
        )
    assert client.get(path, headers=headers()).status_code == 404
    metadata = upload(runtime).json
    path = "/ai/attachments/" + metadata["id"]
    client.delete(path, headers=headers())
    assert client.get(path, headers=headers()).status_code == 404
