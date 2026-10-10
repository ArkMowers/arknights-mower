"""Mastery assistant persistence regressions."""

import sqlite3
from datetime import datetime

import pytest

from arknights_mower.solvers import mastery_support_state as state
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


def _running_plan():
    """一个「协助者正在帮忙、working_until 与本次读数不同」的计划。"""
    return {
        "id": 1,
        "target_level": 3,
        "support_plan": {
            "version": 1,
            "stages": [
                {
                    "level": 1,
                    "operator": "逻各斯",
                    "working_operator": "逻各斯",
                    "working_until": "2026-01-01T00:00:00",
                }
            ],
        },
    }


def test_refresh_end_reports_save_failure_instead_of_raising(database, monkeypatch):
    """出勤记录写不进去时回报失败而不是抛出。

    这个时间戳决定下一级能不能算满 5 小时减半，但调用方跑在训练已经开起来之后——
    写不进去只能补一句邮件，不能变成「计划失败」。
    """
    plan = _running_plan()
    end = datetime(2026, 1, 2, 3, 0, 0)

    def boom(*args, **kwargs):
        raise RuntimeError("写失败")

    monkeypatch.setattr(db, "save_support_plan", boom)
    assert state.refresh_end(plan, 1, end) is False

    monkeypatch.setattr(db, "save_support_plan", lambda *a, **k: False)
    assert state.refresh_end(plan, 1, end) is False


def test_refresh_end_saves_and_skips_when_unchanged(database, monkeypatch):
    plan = _running_plan()
    end = datetime(2026, 1, 2, 3, 0, 0)
    saved = {}
    monkeypatch.setattr(
        db, "save_support_plan", lambda pid, route, **k: saved.update(route) or True
    )
    assert state.refresh_end(plan, 1, end) is True
    assert saved["working_until"] == end.isoformat()

    # 同值再调一次 → 不重复写库（同款跳过）
    saved.clear()
    assert state.refresh_end(plan, 1, end) is True
    assert saved == {}


def test_refresh_end_noop_without_working_operator(database, monkeypatch):
    plan = _running_plan()
    plan["support_plan"]["stages"][0]["working_operator"] = None
    monkeypatch.setattr(
        db,
        "save_support_plan",
        lambda *a, **k: pytest.fail("没有在帮忙的协助者时不该写库"),
    )
    assert state.refresh_end(plan, 1, datetime(2026, 1, 2, 3, 0, 0)) is True
