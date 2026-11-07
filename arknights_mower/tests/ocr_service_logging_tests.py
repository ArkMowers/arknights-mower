"""共享 OCR 的诊断经过共用 logger，且在立即退出前同步写入 stderr。"""

import io
import os
import subprocess
import sys
from unittest.mock import Mock

import pytest

from arknights_mower.utils import log, ocr_service, ocr_shared


@pytest.fixture
def isolated_stderr_handler(monkeypatch):
    previous = log._stderr_handler
    if previous is not None:
        log.logger.removeHandler(previous)
    monkeypatch.setattr(log, "_stderr_handler", None)
    try:
        yield
    finally:
        current = log._stderr_handler
        if current is not None:
            log.logger.removeHandler(current)
            current.close()
        if previous is not None:
            log.logger.addHandler(previous)


def test_service_diagnostics_use_shared_logger_and_sync_stderr(
    monkeypatch, isolated_stderr_handler
):
    stream = io.StringIO()
    monkeypatch.setattr(ocr_service.sys, "stderr", stream)
    warning = Mock(wraps=log.logger.warning)
    monkeypatch.setattr(log.logger, "warning", warning)
    file_handler, screenshot_store = log.fhlr, log.get_screenshot_store()

    ocr_service._log("service-first-diagnostic")
    handler = log._stderr_handler
    ocr_service._log("service-second-diagnostic")

    assert warning.call_args_list[0].args == ("%s", "service-first-diagnostic")
    assert warning.call_args_list[1].args == ("%s", "service-second-diagnostic")
    assert stream.getvalue().count("service-first-diagnostic") == 1
    assert stream.getvalue().count("service-second-diagnostic") == 1
    assert log._stderr_handler is handler
    assert log.logger.handlers.count(handler) == 1
    assert log.fhlr is file_handler
    assert log.get_screenshot_store() is screenshot_store


def test_stderr_handler_reuses_explicit_stream_and_can_rebind(
    isolated_stderr_handler,
):
    first, second = io.StringIO(), io.StringIO()
    log.init_stderr_logging(first)
    handler = log._stderr_handler
    log.init_stderr_logging(first)
    assert log._stderr_handler is handler
    assert log.logger.handlers.count(handler) == 1

    log.init_stderr_logging(second)
    log.logger.warning("rebound-service-diagnostic")
    assert first.getvalue() == ""
    assert second.getvalue().count("rebound-service-diagnostic") == 1
    assert log._stderr_handler is handler


def test_service_diagnostic_survives_immediate_exit_before_app_initialization(tmp_path):
    source = """
import builtins
import os
import sys
sys.dont_write_bytecode = True
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name in ('webview', 'flask', 'arknights_mower.utils.config'):
        raise AssertionError('service imported application UI or config: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from arknights_mower.utils.ocr_service import _log
_log('service-immediate-exit-diagnostic')
from arknights_mower.utils import log
assert log.fhlr is None
assert log.get_screenshot_store() is None
assert 'arknights_mower.utils.config' not in sys.modules
os._exit(0)
"""
    data_root = tmp_path / "unused-data-root"
    result = subprocess.run(
        [sys.executable, "-c", source],
        env={**os.environ, "MOWER_DATA_DIR": str(data_root)},
        capture_output=True,
        check=True,
        timeout=15,
    )
    assert result.stderr.count(b"service-immediate-exit-diagnostic") == 1
    assert not data_root.exists()


def test_service_launch_preserves_utf8_log_tail_with_other_parent_encoding(
    tmp_path, monkeypatch
):
    from arknights_mower.utils import path as mower_path

    monkeypatch.setattr(mower_path, "_data_dir", tmp_path)
    monkeypatch.setenv("PYTHONIOENCODING", "ascii")
    marker = "共享 OCR 服务启动失败：测试原因"
    source = (
        "import os\n"
        "from arknights_mower.utils.ocr_service import _log\n"
        f"_log({marker!r})\n"
        "os._exit(0)\n"
    )
    monkeypatch.setattr(
        ocr_shared, "service_command", lambda directory: [sys.executable, "-c", source]
    )
    process = ocr_shared.start_service(tmp_path)
    try:
        assert process.wait(timeout=15) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    assert marker in ocr_shared.read_service_log(tmp_path)
