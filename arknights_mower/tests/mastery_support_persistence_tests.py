"""Mastery assistant persistence regressions."""

import sqlite3

import pytest

from arknights_mower.tests.mastery_support_fixtures import (
    context_game as context_game,
)
from arknights_mower.tests.mastery_support_fixtures import (
    database as database,
)
from arknights_mower.tests.mastery_support_fixtures import (
    game as game,
)
from arknights_mower.utils import mastery_db as db
from arknights_mower.utils import mastery_support as support


def test_schema_migrates_and_keeps_old_plan(database):
    schema = db._PLAN_SCHEMA.replace("support_plan TEXT,", "").replace(
        "support_runtime TEXT,", ""
    )
    with sqlite3.connect(database) as conn:
        conn.execute(schema)
        conn.execute(
            "INSERT INTO mastery_plan (char_id, skill_index, target_level) VALUES ('old', 0, 3)"
        )
    row = db.get_plan_by_id(1)
    assert row["char_id"] == "old"
    assert row["support_plan"] is None and row["support_runtime"] is None


def test_edit_atomic_guard_clears_failed_runtime_and_rejects_stale_edit(database):
    pid = db.insert_plan("test", 0, 3, support_plan={"version": 1, "stages": []})
    db.save_support_plan(pid, {"level": 1}, runtime=True)
    original = db.get_plan_by_id(pid)
    assert db.save_support_plan(pid, {"version": 1, "stages": [1]}, expected=original)
    assert db.get_plan_by_id(pid)["support_runtime"] is None
    assert not db.save_support_plan(
        pid, {"version": 1, "stages": [2]}, expected=original
    )
    original = db.get_plan_by_id(pid)
    db.update_plan_status(pid, "arranging")
    assert not db.save_support_plan(pid, {}, expected=original)


def test_running_future_edit_keeps_runtime_and_notification_cleanup(database):
    pid = db.insert_plan("test", 0, 3, support_plan={"stages": []})
    db.update_plan_status(pid, "training")
    db.save_support_plan(pid, {"level": 1, "working_operator": "逻各斯"}, runtime=True)
    original = db.get_plan_by_id(pid)
    assert db.save_support_plan(pid, {"stages": [2]}, expected=original)
    assert db.get_plan_by_id(pid)["support_runtime"] == original["support_runtime"]
    assert db.should_notify("support_swap", f"{pid}:1")
    assert not db.should_notify("support_swap", f"{pid}:1")
    db.delete_plan(pid)
    assert db.should_notify("support_swap", f"{pid}:1")


def test_running_stage_is_immutable_but_future_stages_are_editable(context_game):
    _, ids = context_game
    saved = support.plan_supports(ids["能天使"], 0, 3)
    plan = {
        "char_id": ids["能天使"],
        "status": "training",
        "target_level": 3,
        "support_plan": saved,
        "support_runtime": {"level": 1},
    }
    edits = [
        {
            "level": s["level"],
            "operator": s["operator"],
            "swap_target": s["swap_target"],
        }
        for s in saved["stages"]
    ]
    edits[1]["operator"] = "芬"
    assert support.edit_supports(plan, edits)["stages"][1]["operator"] == "芬"
    edits[0]["operator"] = "芬"
    with pytest.raises(support.SupportPlanError, match="已开始"):
        support.edit_supports(plan, edits)
