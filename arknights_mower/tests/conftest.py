import pytest


@pytest.fixture
def legacy_selection_conf(monkeypatch):
    """Isolate tests of the old boolean adapter from saved explicit modes."""
    from arknights_mower.utils import config

    legacy_conf = config.conf.model_copy(deep=True)
    legacy_conf.performance_mode = "high"
    legacy_conf.__pydantic_fields_set__.discard("performance_mode")
    monkeypatch.setattr(config, "conf", legacy_conf)


@pytest.fixture
def low_frame_rate(monkeypatch, legacy_selection_conf):
    """延迟画面回归显式启用适配，不依赖测试机器的平台默认值。"""
    from arknights_mower.utils import config

    monkeypatch.setattr(config.conf, "low_frame_rate_mode", True)
    # Time settings no longer change with the performance mode. These frame
    # fixtures provide six observations at the former medium sampling pace.
    monkeypatch.setattr(config.conf, "selection_poll_interval", 0.5)


@pytest.fixture
def offline_maintenance(monkeypatch):
    """Scheduling fixtures have no maintenance window and never fetch live news."""
    from arknights_mower.utils.news_checker import NewsChecker

    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: None)
