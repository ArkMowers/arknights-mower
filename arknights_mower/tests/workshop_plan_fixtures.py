"""Shared queued skills and stock fixtures for workshop preparation tests."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.utils import config, mastery_db  # noqa: E402
from arknights_mower.utils import mastery_recommendation as rec  # noqa: E402
from arknights_mower.utils import workshop_recommendation as workshop  # noqa: E402


@pytest.fixture
def next_skill(monkeypatch, tmp_path):
    from arknights_mower.utils import workshop_config

    monkeypatch.setattr(config, "conf", config.Conf())
    import server

    monkeypatch.setattr(server.app, "token", "", raising=False)
    monkeypatch.setattr(config, "save_conf", MagicMock())
    monkeypatch.setattr(rec, "_skill_data_cache", None)
    monkeypatch.setattr(workshop_config, "get_path", lambda _: tmp_path / "preset.json")
    config.conf.enable_mastery = True
    config.conf.workshop_settings = []
    config.conf.workshop_manual_backup = None
    config.conf.workshop_preset_migrated = False
    config.conf.workshop_generation = 0
    config.conf.workshop_deer_fodder = config.Conf().workshop_deer_fodder
    cultivate = tmp_path / "cultivate.json"
    data = json.loads((Path(__file__).parents[1] / "data/skill_data.json").read_text())
    stock = [
        {"id": key, "count": 300}
        for key, item in data["items"].items()
        if item.get("rarity") == 3 or key == "3302"
    ]
    cultivate.write_text(json.dumps({"data": {"characters": [], "items": stock}}))
    skills = tmp_path / "skill_data.json"
    skills.write_text(json.dumps({"items": data["items"]}))
    monkeypatch.setattr(rec, "get_path", lambda _: cultivate)
    monkeypatch.setattr(rec, "_find_skill_data", lambda: skills)
    plans = [
        {
            "id": 1,
            "char_id": "char_a",
            "skill_index": 0,
            "target_level": 3,
            "status": "idle",
            "priority": 2,
        },
        {
            "id": 2,
            "char_id": "char_b",
            "skill_index": 0,
            "target_level": 3,
            "status": "idle",
            "priority": 1,
        },
    ]
    monkeypatch.setattr(
        mastery_db,
        "get_all_plans",
        lambda: sorted(plans, key=lambda p: (p["priority"], p["id"])),
    )
    monkeypatch.setattr(
        rec,
        "get_mastery_recommendations",
        lambda: {
            "has_data": True,
            "operators": [
                {
                    "char_id": cid,
                    "name": cid,
                    "profession": "CASTER",
                    "recommendations": [
                        {
                            "skill_index": 0,
                            "skill_name": "一技能",
                            "current_level": 0,
                            "chain_needed_materials": [
                                {"name": "技巧概要·卷3", "count": count}
                            ],
                        }
                    ],
                }
                for cid, count in [("char_a", 5), ("char_b", 7)]
            ],
        },
    )
    monkeypatch.setattr(workshop, "available_operators", lambda: {})
    monkeypatch.setattr(config, "plan", {})
    monkeypatch.setattr(config.conf, "fodder_operators", [])
    monkeypatch.setattr(config.conf, "t5_operators", [])
    monkeypatch.setattr(config.conf, "book_operators", ["赫拉格"])
    return SimpleNamespace(plans=plans, cultivate=cultivate)


def book_limit(settings):
    return next(
        item["self_upper_limit"]
        for entry in settings
        for item in entry["items"]
        if "技巧概要·卷3" in item["item_names"]
    )
