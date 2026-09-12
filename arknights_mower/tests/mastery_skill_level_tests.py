"""基础技能等级与专精等级分开读取，未满 7 级不得添加或执行专精。"""

import json
import sys
from unittest.mock import MagicMock

import pytest
from flask import Flask

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import mastery  # noqa: E402
from arknights_mower.utils import mastery_db as db  # noqa: E402
from arknights_mower.utils import mastery_recommendation as rec  # noqa: E402
from arknights_mower.views import mastery as view  # noqa: E402

CHAR_ID = "char_4186_tmoris"


@pytest.fixture
def roster(tmp_path, monkeypatch):
    path = tmp_path / "cultivate.json"
    skills_path = tmp_path / "skill_data.json"
    skills_path.write_text(
        json.dumps(
            {
                "characters": {
                    CHAR_ID: {
                        "name": "八幡海铃",
                        "profession": "WARRIOR",
                        "skills": [
                            {
                                "name": "测试技能",
                                "levels": [{"materials": [], "time": 1}] * 3,
                            }
                        ],
                    }
                },
                "items": {},
            }
        )
    )
    monkeypatch.setattr(rec, "get_path", lambda _: path)
    monkeypatch.setattr(rec, "_find_skill_data", lambda: skills_path)
    monkeypatch.setattr(rec, "_skill_data_cache", None)

    def write(level, mastery_level=0):
        char = {
            "id": CHAR_ID,
            "evolvePhase": 2,
            "level": 50,
            "skills": [{"level": mastery_level}],
        }
        if level is not None:
            char["mainSkillLevel"] = level
        path.write_text(json.dumps({"data": {"characters": [char], "items": []}}))

    write(1)
    return write


@pytest.mark.parametrize("level", range(1, 8))
def test_recommendation_preserves_actual_base_level(roster, level):
    roster(level)
    op = rec.get_mastery_recommendations()["operators"][0]
    assert op["main_skill_level"] == level
    assert op["recommendations"][0]["current_level"] == 0
    assert bool(op["mastery_error"]) == (level < 7)


@pytest.mark.parametrize("mastery_level", [1, 2])
def test_mastery_and_base_level_remain_separate(roster, mastery_level):
    roster(7, mastery_level)
    op = rec.get_mastery_recommendations()["operators"][0]
    assert op["main_skill_level"] == 7
    assert op["recommendations"][0]["current_level"] == mastery_level
    assert op["mastery_error"] is None


@pytest.mark.parametrize("mode", ["auto", "route"])
@pytest.mark.parametrize("level", range(1, 7))
def test_all_plan_modes_reject_low_base_level_before_insert(
    roster, monkeypatch, level, mode
):
    roster(level)
    insert = MagicMock()
    monkeypatch.setattr(db, "insert_plan", insert)
    plan_id, reason = db.add_plan_checked(CHAR_ID, 0, support_mode=mode)
    assert plan_id == -1
    assert f"仅 {level} 级" in reason
    insert.assert_not_called()


def test_level_seven_can_be_added_after_sync(roster, monkeypatch):
    insert = MagicMock(return_value=42)
    monkeypatch.setattr(db, "insert_plan", insert)
    assert db.add_plan_checked(CHAR_ID, 0, support_mode="route")[0] == -1
    roster(7)
    assert db.add_plan_checked(CHAR_ID, 0, support_mode="route") == (42, None)
    insert.assert_called_once()


@pytest.mark.parametrize("level", [None, True, "7", 0])
def test_unknown_or_invalid_level_is_not_assumed_seven(roster, level):
    roster(level)
    op = rec.get_mastery_recommendations()["operators"][0]
    assert "无法确认" in op["mastery_error"]
    assert db.add_plan_checked(CHAR_ID, 0, support_mode="route")[0] == -1


@pytest.mark.parametrize("legacy", [False, True])
def test_api_rejects_low_level_and_does_not_dispatch(roster, monkeypatch, legacy):
    app = Flask(__name__)
    app.register_blueprint(view.mastery_bp)
    insert, dispatch = MagicMock(), MagicMock()
    monkeypatch.setattr(db, "insert_plan", insert)
    monkeypatch.setattr(view, "_dispatch_new_plans_immediately", dispatch)
    payload = (
        {"八幡海铃": 0}
        if legacy
        else {"items": [{"name": "八幡海铃", "skill_index": 0}]}
    )
    result = (
        app.test_client().post("/mastery-plan", json=payload).get_json()["results"][0]
    )
    assert result["status"] == "error"
    assert "仅 1 级" in result["reason"]
    insert.assert_not_called()
    dispatch.assert_not_called()


def test_legacy_low_level_plan_is_not_scheduled_or_prepared(roster, monkeypatch):
    plan = {
        "id": 1,
        "char_id": CHAR_ID,
        "skill_index": 0,
        "status": "idle",
        "target_level": 3,
    }
    monkeypatch.setattr(db, "get_all_plans", lambda: [plan])
    assert rec.auto_schedule_mastery_tasks()["scheduled"] == []
    assert rec.compute_workshop_config([], [], []) == []
    roster(7)
    assert rec.auto_schedule_mastery_tasks()["scheduled"][0]["char_id"] == CHAR_ID


def test_already_queued_low_level_plan_does_not_arrange_staff(roster, monkeypatch):
    solver = MagicMock()
    update = MagicMock()
    monkeypatch.setattr(db, "update_plan_status", update)
    mastery._start_new_training(solver, {"id": 1, "char_id": CHAR_ID})
    assert update.call_args.args == (1, "failed")
    assert "仅 1 级" in update.call_args.kwargs["failed_reason"]
    assert solver.mock_calls == []
