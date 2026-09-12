"""Shared fixtures for mastery assistant tests."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import mastery_db as db
from arknights_mower.utils import mastery_support as support
from arknights_mower.utils import mastery_support_data as support_data
from arknights_mower.utils.mastery_support_types import StageSpec


@pytest.fixture
def game():
    data = json.loads((Path(__file__).parents[1] / "data/skill_data.json").read_text())[
        "training"
    ]["operators"]
    return data, {m["name"]: cid for cid, m in data.items()}


def owned(cid, elite=2):
    return {"id": cid, "evolvePhase": elite, "level": 90}


def stat(name, efficiency=0, halves=False):
    return {
        "name": name,
        "efficiency": efficiency,
        "halves": halves,
    }


def facility(name="", replacement=None):
    return {"plans": [{"agent": name, "replacement": replacement or []}]}


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = str(tmp_path / "mastery.db")
    original = db._conn
    monkeypatch.setattr(db, "_conn", lambda p=None: original(p or path))
    return path


@pytest.fixture
def context_game(game, monkeypatch):
    data, ids = game
    monkeypatch.setattr("arknights_mower.utils.config.plan", {})
    monkeypatch.setattr(support_data, "training_data", lambda: data)
    roster = [owned(ids[n]) for n in ("能天使", "假日威龙陈", "芬", "艾丽妮", "逻各斯")]
    monkeypatch.setattr(support_data, "owned_roster", lambda: roster)
    monkeypatch.setattr(support_data, "schedule_context", lambda *a, **kw: ({}, 0))
    return data, ids


def swap_case(names=("艾丽妮", "逻各斯")):
    route = support.stage_route(
        stat("快教官", 100), stat("艾丽妮", 30, True), StageSpec(2, 16, 0, 10)
    )
    route.update(first_halves=False, swap_halves=True, working_operator="快教官")
    plan = {
        "id": 1,
        "char_id": "target",
        "char_name": "学员",
        "skill_name": "一技能·测试",
        "target_level": 3,
        "support_plan": {"stages": [route]},
    }
    panel = SimpleNamespace(
        mastery_tier=2,
        countdown_state="active",
        countdown=datetime.now() + timedelta(seconds=5.2 * 3600 * 1.35 / 2.05),
        operator_name="学员",
        skill_name="测试",
    )
    solver = MagicMock()
    options = {"快教官": {2: stat("快教官", 100)}}
    for n in names:
        options[n] = {2: stat(n, 30 if n == "艾丽妮" else 0, True)}
    return plan, panel, solver, options
