"""Roguelike gift operators cannot be selected as training-room trainees."""

import json
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import mastery_db as db
from arknights_mower.utils import mastery_recommendation as rec


def test_recommendations_exclude_gift_operators_but_keep_regular_trainees(
    tmp_path, monkeypatch
):
    ids = ["char_4195_radian", "char_4230_mcnist", "char_103_angel"]
    roster = tmp_path / "cultivate.json"
    roster.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [
                        {"id": cid, "evolvePhase": 2, "skills": [{"level": 0}]}
                        for cid in ids
                    ]
                }
            }
        )
    )
    skills = tmp_path / "skill_data.json"
    skills.write_text(
        json.dumps(
            {
                "characters": {
                    cid: {
                        "name": name,
                        "skills": [
                            {
                                "name": "测试技能",
                                "levels": [{"materials": [], "time": 28800}] * 3,
                            }
                        ],
                    }
                    for cid, name in zip(ids, ["电弧", "机械师", "能天使"])
                }
            }
        )
    )
    monkeypatch.setattr(rec, "get_path", lambda _: roster)
    monkeypatch.setattr(rec, "_find_skill_data", lambda: skills)
    result = rec.get_mastery_recommendations()
    assert result["has_data"]
    assert [op["name"] for op in result["operators"]] == ["能天使"]


@pytest.mark.parametrize("char_id", ["char_4195_radian", "char_4230_mcnist"])
@pytest.mark.parametrize("support_mode", ["auto", "route"])
def test_plan_creation_rejects_gift_operators_before_reading_box(
    monkeypatch, char_id, support_mode
):
    read_box = MagicMock(side_effect=AssertionError("Should reject before reading BOX"))
    insert = MagicMock()
    monkeypatch.setattr(rec, "get_current_mastery_level", read_box)
    monkeypatch.setattr(db, "insert_plan", insert)
    plan_id, error = db.add_plan_checked(char_id, 0, support_mode=support_mode)
    assert plan_id == -1
    assert "无法在训练室专精" in error
    read_box.assert_not_called()
    insert.assert_not_called()
