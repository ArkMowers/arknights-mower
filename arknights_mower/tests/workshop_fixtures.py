"""Shared workshop test data; fixtures stay local to importing suites."""

import json
from pathlib import Path

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.config.plan import PlanModel


@pytest.fixture(autouse=True)
def empty_schedule(monkeypatch):
    monkeypatch.setattr(config, "plan", PlanModel(), raising=False)


def buff(text):
    return {"roomType": "WORKSHOP", "description": text}


@pytest.fixture
def game():
    meta = json.loads((Path(__file__).parents[1] / "data/skill_data.json").read_text())[
        "workshop"
    ]["operators"]
    return meta, {entry["name"]: cid for cid, entry in meta.items()}


def owned(ids, *names, elite=2, level=90):
    return [{"id": ids[name], "evolvePhase": elite, "level": level} for name in names]


def recipe(cost=4, tab="精英材料"):
    return {"apCost": cost, "tab": tab}


def item(name):
    return {"item_names": [name], "children_lower_limit": 7, "self_upper_limit": 12}


def facility(name, replacement=()):
    return {"plans": [{"agent": name, "replacement": list(replacement)}]}


SPECIALISTS = [
    ("贾维", 2, "改量装置", 4, 90),
    ("奥斯塔", 2, "聚酸酯块", 4, 90),
    ("泥岩", 2, "提纯源岩", 4, 90),
    ("熔泉", 2, "异铁块", 4, 90),
    ("号角", 2, "炽合金块", 4, 100),
    ("维荻", 1, "酮阵列", 4, 80),
    ("特克诺", 2, "晶体电子单元", 8, 80),
    ("折桠", 2, "异铁组", 2, 90),
    ("谬因", 2, "提纯源岩", 4, 90),
    ("休谟斯", 1, "糖组", 2, 90),
    ("缇缇", 2, "双极纳米片", 8, 80),
]
