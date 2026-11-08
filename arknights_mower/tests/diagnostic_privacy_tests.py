"""分享用诊断包隐藏合成敏感文字，并保留用户选择的图片和完整诊断。"""

import json
from datetime import datetime
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from arknights_mower.utils import config, path
from arknights_mower.utils.diagnostics import export_bundle
from arknights_mower.utils.log_privacy import LogRedactor


@pytest.mark.parametrize(
    "value",
    [
        "198.51.100.42:5555",
        "[2001:db8:1234::42]:5555",
        "2001:db8:1234::43",
        "[fe80::42%eth0]:5555",
        "adb.private.example.invalid:5555",
        "localhost:5555",
        "private.person@example.invalid",
        r"C:\Users\private-person\mower\module.py",
        r"C:\\Users\\private-person\\mower\\module.py",
        "/home/private-person/mower/module.py",
        "/Users/private-person/mower/module.py",
    ],
)
def test_recognized_private_values_keep_diagnostic_location(value):
    output = LogRedactor()(
        f"2026-11-08 10:30:00 module.py:42 ERROR 目标 {value}\n保留任务"
    )
    assert value not in output
    assert "private-person" not in output
    assert "2026-11-08 10:30:00 module.py:42 ERROR" in output
    assert output.endswith("\n保留任务")


def test_credentials_and_explicit_device_values_do_not_require_single_line_truncation():
    output = LogRedactor(["opaque-private-726154", "credential+with/slash"])(
        "2026-11-08 10:30:00 task.py:42 ERROR 保留任务\n"
        '  password={"nested": "secret-with-spaces 726154"}\n'
        "  https://service.invalid/?token=old-query-secret&ok=1\n"
        "  Authorization: Bearer old-bearer-secret\n"
        "  Bearer second-bearer-secret\n"
        "  使用 opaque-private-726154 和 credential%2Bwith%2Fslash\n"
        "  RuntimeError: 检查结束\n"
    )
    for secret in (
        "secret-with-spaces",
        "old-query-secret",
        "old-bearer-secret",
        "second-bearer-secret",
        "opaque-private-726154",
        "credential%2Bwith%2Fslash",
    ):
        assert secret not in output
    assert "2026-11-08 10:30:00 task.py:42 ERROR 保留任务" in output
    assert "RuntimeError: 检查结束" in output
    text = "无来源说明的 ordinary-identifier 保留"
    assert LogRedactor()(text) == text


@pytest.mark.parametrize("archived", [False, True])
@pytest.mark.parametrize("include_images", [False, True])
def test_export_redacts_live_and_archived_logs_without_rewriting_sources(
    monkeypatch, tmp_path, archived, include_images
):
    center = datetime(2026, 11, 8, 10, 30)
    stamp = str(int(center.timestamp() * 10**9))
    logs, shots = tmp_path / "logs", tmp_path / "shots"
    logs.mkdir()
    archive = shots / "errors" / stamp
    archive.mkdir(parents=True)
    sender = "private-sender-726154@example.invalid"
    token = "synthetic-token-726154"
    serial = "opaque-device-726154"
    password = "synthetic-password-726154"
    location = r"C:\Users\private-person-726154\private-instance-726154"
    conf = SimpleNamespace(
        account=sender,
        pass_code=password,
        recipient=[],
        adb="adb-private.example.invalid:16416",
        device=SimpleNamespace(last_serial=serial),
        webview=SimpleNamespace(token=token),
    )
    monkeypatch.setattr(config, "conf", conf)
    monkeypatch.setattr(path, "global_space", location)
    message = (
        "2026-11-08 10:30:00 task.py:42 ERROR 连接失败，保留任务\n"
        f"  token={token}\n  收件人={sender}\n"
        f"  实际目标 {serial}\n  地址 {conf.adb}\n"
        "  设备初始化完成：legacy-device-726154\n"
        "  ADB可连接的设备：legacy-usb-726154\n"
        "  ADB 可连接的设备：unrelated-usb-726154\n"
        "  设备未就绪：['retry-usb-726154']，重新选择端口 old-device-726154\n"
        f"  正在使用全局配置空间: {location}\n"
        "  对端 192.0.2.41:16416 [2001:db8::41]:16416\n"
        "  对端 2001:db8::42\n"
        f"  SMTP password: {password}\n"
        '  File "C:\\Users\\windows-person-726154\\mower\\task.py", line 42\n'
        '  File "/home/unix-person-726154/mower/task.py", line 42\n'
        '  File "/Users/macos-person-726154/mower/task.py", line 42\n'
        "  RuntimeError: 检查已结束，状态未改变\n" + "  诊断续行保持完整\n" * 1000
    )
    runtime = logs / "runtime.log"
    runtime.write_text(message, encoding="utf-8")
    saved = archive / "logs.json"
    saved.write_text(json.dumps([{"message": message}]), encoding="utf-8")
    image = archive / f"{stamp}.jpg"
    image.write_bytes(b"synthetic-original-image")

    with (
        export_bundle(
            logs,
            shots,
            center,
            archive_id=stamp if archived else None,
            include_screenshots=include_images,
        ) as stream,
        ZipFile(stream) as bundle,
    ):
        output = bundle.read("runtime.log").decode("utf-8")
        for sensitive in (
            sender,
            token,
            serial,
            password,
            location,
            conf.adb,
            "legacy-device-726154",
            "legacy-usb-726154",
            "unrelated-usb-726154",
            "retry-usb-726154",
            "old-device-726154",
            "192.0.2.41",
            "2001:db8::41",
            "2001:db8::42",
            "windows-person-726154",
            "unix-person-726154",
            "macos-person-726154",
        ):
            assert sensitive not in output
        assert "2026-11-08 10:30:00 task.py:42 ERROR 连接失败，保留任务" in output
        assert "ADB 可连接的设备：[已隐藏]" in output
        assert "设备未就绪：[已隐藏]，重新选择端口 [已隐藏]" in output
        assert "RuntimeError: 检查已结束，状态未改变" in output
        assert output.count("诊断续行保持完整") == 1000
        pictures = [name for name in bundle.namelist() if name.endswith(".jpg")]
        assert len(pictures) == int(include_images)
        if pictures:
            assert bundle.read(pictures[0]) == b"synthetic-original-image"
        assert "原始截图未经脱敏" in bundle.read("readme.txt").decode("utf-8")
    assert runtime.read_text(encoding="utf-8") == message
    assert json.loads(saved.read_text(encoding="utf-8")) == [{"message": message}]
