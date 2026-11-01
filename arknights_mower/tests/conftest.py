import json
from pathlib import Path

import pytest


def pytest_generate_tests(metafunc):
    if "contained_skill_roster" not in metafunc.fixturenames:
        return
    path = Path(__file__).parents[1] / "data/skill_data.json"
    characters = json.loads(path.read_text(encoding="utf-8"))["characters"]
    rosters = []
    for cid, char in characters.items():
        skills = [
            (index, skill["name"])
            for index, skill in enumerate(char.get("skills", []))
            if skill.get("name")
        ]
        if any(a != b and a in b for _, a in skills for _, b in skills):
            rosters.append(pytest.param((cid, char["name"], skills), id=cid))
    metafunc.parametrize("contained_skill_roster", rosters)


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


@pytest.fixture
def income_db(tmp_path, monkeypatch):
    """Give valuation readers an isolated database without touching saved user data."""
    import sqlite3
    from contextlib import contextmanager

    from arknights_mower.solvers import record

    path = tmp_path / "income.db"
    monkeypatch.setattr(record, "_tables_created", False)
    with sqlite3.connect(path) as connection:
        record._ensure_tables(connection)

    @contextmanager
    def connect():
        with sqlite3.connect(path) as connection:
            yield connection

    monkeypatch.setattr(record, "_conn", connect)
    return path
