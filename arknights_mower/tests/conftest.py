import pytest


@pytest.fixture
def low_frame_rate(monkeypatch):
    """延迟画面回归显式启用适配，不依赖测试机器的平台默认值。"""
    from arknights_mower.utils import config

    monkeypatch.setattr(config.conf, "low_frame_rate_mode", True)
