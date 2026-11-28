"""启动器崩溃兜底：不完整的实例快照绝不能把 Mower 挡在启动之外。

现场故障是冻结包的父进程在 `show_existing_instance` 里撞上登记文件的
PermissionError，异常冒出主线程后被 PyInstaller 变成无日志弹窗。这里覆盖两条
防线：扫描必须 best-effort 且永不抛；真有异常时必须留下 tmp/launcher.log。
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils import instance_supervisor as supervisor
from arknights_mower.utils import path
from arknights_mower.utils import update_runtime as runtime


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """把 @app 重定向到 tmp_path，避免读到本机真实数据目录。"""
    data = tmp_path / "data"
    monkeypatch.setattr(path, "_data_dir", data)
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "updates")
    return data


def fake_message_box(monkeypatch):
    """替换 ctypes.windll.user32.MessageBoxW，测试里绝不真的弹窗。"""
    import ctypes

    shown = Mock(return_value=1)
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(user32=SimpleNamespace(MessageBoxW=shown)),
        raising=False,
    )
    return shown


def test_registration_scan_error_never_blocks_launch(isolated_data, monkeypatch):
    """InstanceScanError 必须被吞掉：启动器只回答“要不要复用窗口”。"""

    def unreadable(**kwargs):
        raise runtime.InstanceScanError(
            "无法完整读取实例登记，请稍后重试或检查文件权限："
            "D:/Mower/tmp/updates/x/instances/a.json（[Errno 13] Permission denied）"
        )

    monkeypatch.setattr(runtime, "instances", unreadable)
    directory = isolated_data / "account/tmp/process-supervision"
    assert supervisor.show_existing_instance(directory) is False


def test_os_error_scan_failure_is_treated_as_no_instance(isolated_data, monkeypatch):
    """目录本身读不了（OSError/权限）同样只当作没有已有实例。"""

    def unreadable(**kwargs):
        raise PermissionError(13, "Permission denied", "D:/Mower/tmp/updates")

    monkeypatch.setattr(runtime, "instances", unreadable)
    directory = isolated_data / "account/tmp/process-supervision"
    assert supervisor.show_existing_instance(directory) is False


def test_launch_scan_is_best_effort_and_short(isolated_data, monkeypatch):
    """扫描必须显式 best-effort：strict=False，且预算很短。"""
    scan = Mock(return_value=[])
    monkeypatch.setattr(runtime, "instances", scan)
    directory = isolated_data / "account/tmp/process-supervision"
    assert supervisor.show_existing_instance(directory) is False
    scan.assert_called_once()
    assert scan.call_args.kwargs["strict"] is False
    assert 0 < scan.call_args.kwargs["timeout"] <= 1


def test_ready_matching_instance_is_still_asked_to_show(isolated_data, monkeypatch):
    """回归保护：兜底不能把“复用已有窗口”这个功能改死。"""
    instance = {
        "id": "existing",
        "kind": "instance",
        "ready": True,
        "space": "account",
        "data_dir": str(isolated_data),
    }
    monkeypatch.setattr(runtime, "instances", Mock(return_value=[instance]))
    send = Mock()
    monkeypatch.setattr(runtime, "send_instance_command", send)
    directory = isolated_data / "account/tmp/process-supervision"
    assert supervisor.show_existing_instance(directory) is True
    send.assert_called_once_with(instance, "show")


@pytest.mark.parametrize(
    "unavailable",
    ["not_ready", "other_space", "shutdown_requested"],
)
def test_unavailable_instance_is_not_reused(isolated_data, monkeypatch, unavailable):
    """未就绪、别的 space、已请求退出的实例都不能被复用。"""
    instance = {
        "id": "existing",
        "kind": "instance",
        "ready": True,
        "space": "account",
        "data_dir": str(isolated_data),
    }
    if unavailable == "not_ready":
        instance["ready"] = False
    elif unavailable == "other_space":
        instance["space"] = "other"
    else:
        runtime.write_json(runtime.state_dir() / "shutdown/existing.json", {})
    monkeypatch.setattr(runtime, "instances", Mock(return_value=[instance]))
    send = Mock()
    monkeypatch.setattr(runtime, "send_instance_command", send)
    directory = isolated_data / "account/tmp/process-supervision"
    assert supervisor.show_existing_instance(directory) is False
    send.assert_not_called()


def test_launcher_failure_is_written_to_tmp_log(isolated_data, monkeypatch):
    """诊断文件必须落到 @app/tmp/launcher.log，并带上异常类型与消息。"""
    import webview_ui

    shown = fake_message_box(monkeypatch)
    error = runtime.InstanceScanError("无法完整读取实例登记：Permission denied")
    webview_ui.report_launcher_failure(error)

    log = isolated_data / "tmp/launcher.log"
    assert log.exists()
    text = log.read_text(encoding="utf-8")
    assert "InstanceScanError" in text
    assert "无法完整读取实例登记" in text
    if sys.platform == "win32":
        assert shown.call_count == 1
        caption, message = shown.call_args.args[2], shown.call_args.args[1]
        assert caption == "Mower 启动失败"
        assert "无法启动 Mower" in message
        assert "launcher.log" in message
    else:
        shown.assert_not_called()


def test_log_is_appended_and_rotated_once_over_the_limit(isolated_data, monkeypatch):
    """日志按追加写入；超过 1 MB 时旧文件改名，不重启也无法回收磁盘。"""
    import webview_ui

    fake_message_box(monkeypatch)
    tmp = isolated_data / "tmp"
    tmp.mkdir(parents=True)
    (tmp / "launcher.log").write_text("上一轮的诊断\n", encoding="utf-8")
    webview_ui.report_launcher_failure(RuntimeError("第一次"))
    webview_ui.report_launcher_failure(RuntimeError("第二次"))
    text = (tmp / "launcher.log").read_text(encoding="utf-8")
    assert "第一次" in text and "第二次" in text

    oversized = "x" * (webview_ui.LAUNCHER_LOG_LIMIT + 1)
    (tmp / "launcher.log").write_text(oversized, encoding="utf-8")
    webview_ui.report_launcher_failure(RuntimeError("超限之后"))
    rotated = tmp / "launcher.log.1"
    assert rotated.read_text(encoding="utf-8") == oversized
    assert "超限之后" in (tmp / "launcher.log").read_text(encoding="utf-8")


def test_unwritable_log_path_still_reports_and_never_raises(isolated_data, monkeypatch):
    """落盘失败不能连累用户提示，更不能在异常处理器里再抛。"""
    import webview_ui

    shown = fake_message_box(monkeypatch)

    def unreadable(path, space=None):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(path, "get_path", unreadable)
    webview_ui.report_launcher_failure(RuntimeError("目录不可写"))
    if sys.platform == "win32":
        shown.assert_called_once()
    else:
        shown.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="非 Windows 平台不弹消息框")
def test_non_windows_platform_skips_the_message_box(isolated_data, monkeypatch):
    """非 Windows 平台没有 MessageBoxW：不弹窗，也不抛。"""
    import webview_ui

    shown = fake_message_box(monkeypatch)
    webview_ui.report_launcher_failure(RuntimeError("非 Windows 平台"))
    shown.assert_not_called()
    assert (Path(isolated_data) / "tmp/launcher.log").exists()
