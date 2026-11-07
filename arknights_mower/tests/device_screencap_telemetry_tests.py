"""截图遥测日志记录在 DEBUG，不进入 INFO。"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np

from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device import device as device_module
from arknights_mower.utils.device.device import Device


def _make_device(monkeypatch, *, count):
    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    monkeypatch.setattr(config, "conf", Conf(performance_mode="auto"))
    monkeypatch.setattr(config, "screenshot_avg", 1000.0)
    monkeypatch.setattr(config, "screenshot_count", count)
    monkeypatch.setattr(config, "operation_feedback_avg", None)
    monkeypatch.setattr(config, "operation_feedback_count", 0)
    monkeypatch.setattr(config, "operation_feedback_mode", None)
    monkeypatch.setattr(
        config, "screenshot_time", datetime.now() - timedelta(seconds=10)
    )
    monkeypatch.setattr(device_module, "save_screenshot_frame", lambda *_, **__: None)
    monkeypatch.setattr(device_module.time, "sleep", lambda _: None)
    device = object.__new__(Device)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    device.session_control = SimpleNamespace(
        capture=lambda: SimpleNamespace(unwrap=lambda: frame)
    )
    return device


def test_screencap_telemetry_logs_at_debug(monkeypatch, caplog):
    """第 100 次截图的遥测行记录在 DEBUG，不写入 INFO。"""
    device = _make_device(monkeypatch, count=99)
    with caplog.at_level("DEBUG", logger="arknights_mower.utils.log"):
        device.screencap()
    assert config.screenshot_count == 100
    msgs = {r.getMessage(): r.levelname for r in caplog.records}
    telemetry = [m for m in msgs if "截图用时" in m and "平均用时" in m]
    assert telemetry, f"未找到截图遥测日志行；实际消息：{list(msgs)}"
    for msg in telemetry:
        assert msgs[msg] == "DEBUG", f"遥测行 {msg!r} 级别为 {msgs[msg]}，预期 DEBUG"


def test_screencap_non_telemetry_call_emits_no_info_for_timing(monkeypatch, caplog):
    """非整百次截图不产生任何遥测日志行。"""
    device = _make_device(monkeypatch, count=100)
    with caplog.at_level("DEBUG", logger="arknights_mower.utils.log"):
        device.screencap()
    assert config.screenshot_count == 101
    timing_msgs = [r for r in caplog.records if "截图用时" in r.getMessage()]
    assert not timing_msgs, f"非整百次时不应产生遥测日志，实际：{timing_msgs}"
