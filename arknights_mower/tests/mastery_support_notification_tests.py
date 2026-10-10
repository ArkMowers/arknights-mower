"""Failed panel reads must preserve per-stage alerts and collection follow-up."""

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers import mastery_support_state as state
from arknights_mower.solvers.mastery_support_dispatch import run_planned_swap
from arknights_mower.tests.mastery_support_fixtures import database as database
from arknights_mower.utils import mastery_db as db


def test_unreadable_panel_alerts_once_per_saved_stage(database):
    pid = db.insert_plan("test", 0, 3, support_plan={"stages": []})
    solver = MagicMock()
    with (
        patch("arknights_mower.utils.email.send_message") as send,
        patch(
            "arknights_mower.solvers.mastery._schedule_collect_after_swap"
        ) as collect,
    ):
        for level in (1, 2):
            db.update_plan_status(pid, "training", swap_frozen=0)
            db.save_support_plan(pid, {"level": level}, runtime=True)
            plan = db.get_plan_by_id(pid)
            run_planned_swap(solver, plan, panel=None)
            run_planned_swap(solver, plan, panel=None)
            assert db.get_plan_by_id(pid)["swap_frozen"] == 1
        assert send.call_count == 2
        assert "专1：" in send.call_args_list[0].args[0]
        assert "专2：" in send.call_args_list[1].args[0]
        assert collect.call_count == 4
        # Cached progress must not become evidence for collection/device actions.
        assert all(call.kwargs["tier"] is None for call in collect.call_args_list)
    solver.choose_train.assert_not_called()
    with sqlite3.connect(database) as conn:
        assert conn.execute(
            "SELECT dedup_key FROM mastery_notify ORDER BY dedup_key"
        ).fetchall() == [(f"{pid}:1",), (f"{pid}:2",)]


@pytest.mark.parametrize("observed", [1, 2, 3])
def test_observed_stage_overrides_saved_notification_stage(database, observed):
    plan = {"id": 1, "support_runtime": {"level": 3}, "char_name": "学员"}
    with patch("arknights_mower.utils.email.send_message") as send:
        state.notify_support_failure(plan, observed, "读取失败")
    assert send.call_args.args[0] == f"学员 专{observed}：读取失败"
    assert not db.should_notify("support_swap", f"1:{observed}")


@pytest.mark.parametrize("observed", [None, True, "2", 0, 4, 2.0])
def test_invalid_observed_stage_uses_saved_stage(database, observed):
    plan = {"id": 1, "support_runtime": json.dumps({"level": 2})}
    with patch("arknights_mower.utils.email.send_message") as send:
        state.notify_support_failure(plan, observed, "读取失败")
    assert "专2：" in send.call_args.args[0]
    assert not db.should_notify("support_swap", "1:2")


@pytest.mark.parametrize(
    "runtime",
    [
        None,
        "",
        "{broken",
        "null",
        "[]",
        [],
        {},
        {"level": True},
        {"level": "2"},
        {"level": 0},
        {"level": 4},
        {"level": 2.0},
    ],
)
def test_unknown_stage_has_readable_deduplicated_alert(database, runtime):
    plan = {"id": 1, "support_runtime": runtime, "target_level": 3}
    with patch("arknights_mower.utils.email.send_message") as send:
        state.notify_support_failure(plan, None, "读取失败")
        state.notify_support_failure(plan, None, "读取失败")
    assert send.call_count == 1
    assert "专精阶段未知：" in send.call_args.args[0]
    assert "None" not in send.call_args.args[0]
    assert not db.should_notify("support_swap", "1:unknown")


def test_delete_plan_cleans_all_its_swap_alerts_only(database):
    pid = db.insert_plan("test", 0, 3)
    removed = [("support_swap", f"{pid}:{s}") for s in (1, 2, 3, "None", "unknown")]
    removed.append(("m3_collect", str(pid)))
    retained = [
        ("support_swap", f"{pid}0:1"),
        ("support_swap", f"{pid + 1}:unknown"),
        ("other", f"{pid}:1"),
    ]
    for kind, key in removed + retained:
        assert db.should_notify(kind, key)
    assert db.delete_plan(pid)
    assert db.get_plan_by_id(pid) is None
    with sqlite3.connect(database) as conn:
        assert set(
            conn.execute("SELECT notify_type, dedup_key FROM mastery_notify").fetchall()
        ) == set(retained)
