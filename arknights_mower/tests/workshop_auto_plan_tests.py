"""Button and depot scan prepare only the next queued skill's complete chain."""

import json
import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.tests.workshop_plan_fixtures import (  # noqa: E402
    book_limit,
)
from arknights_mower.tests.workshop_plan_fixtures import (  # noqa: E402
    next_skill as next_skill,
)
from arknights_mower.utils import config, mastery_db  # noqa: E402
from arknights_mower.utils import mastery_recommendation as rec  # noqa: E402


def test_only_first_skill_by_queue_priority_is_prepared(next_skill):
    assert book_limit(rec.compute_workshop_config([], [], ["赫拉格"])) == 7
    next_skill.plans[0]["priority"] = 0
    assert book_limit(rec.compute_workshop_config([], [], ["赫拉格"])) == 5
    next_skill.plans.pop(0)
    assert book_limit(rec.compute_workshop_config([], [], ["赫拉格"])) == 7


def test_box_completed_head_is_skipped_before_selecting_next_skill(next_skill):
    next_skill.cultivate.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [{"id": "char_b", "skills": [{"level": 3}]}],
                    "items": [{"id": "3302", "count": 300}],
                }
            }
        )
    )
    assert book_limit(rec.compute_workshop_config([], [], ["赫拉格"])) == 5


@pytest.mark.parametrize("keys", [[], ["char_a_0"], ["char_a_0", "char_b_0"]])
def test_button_uses_real_queue_even_with_empty_or_stale_frontend_selection(
    next_skill, keys
):
    import server

    response = server.app.test_client().post(
        "/workshop-auto-config",
        json={
            "planned_skills": keys,
            "fodder_operators": [],
            "t5_operators": [],
            "book_operators": ["赫拉格"],
        },
    )
    assert response.status_code == 200
    assert book_limit(response.json["workshop_settings"]) == 7


@pytest.mark.parametrize("empty", [False, True])
def test_depot_scan_uses_same_next_skill_config_and_clears_finished_queue(
    next_skill, monkeypatch, empty
):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    if empty:
        next_skill.plans.clear()
    monkeypatch.setattr(mastery_db, "retry_failed_plans", lambda: 0)
    monkeypatch.setattr(
        rec, "auto_schedule_mastery_tasks", lambda: {"scheduled": [], "skipped": []}
    )
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config.conf, "workshop_settings", [])
    save = MagicMock()
    monkeypatch.setattr(config, "save_conf", save)
    solver = object.__new__(BaseSchedulerSolver)
    solver._dispatch_scan_start_tasks = MagicMock()
    solver._auto_schedule_mastery_after_scan()
    actual = [entry.model_dump() for entry in config.conf.workshop_settings]
    assert actual == [
        {**entry, "source": "mastery"}
        for entry in rec.compute_workshop_config([], [], ["赫拉格"])
    ]
    if empty:
        assert actual == []
    else:
        assert book_limit(actual) == 7
    save.assert_called_once()


def test_no_plans_never_falls_back_to_full_material_stockpiling(next_skill):
    import server

    next_skill.plans.clear()
    response = server.app.test_client().post("/workshop-auto-config", json={})
    assert response.status_code == 200
    assert response.json["workshop_settings"] == []


def test_workshop_time_uses_earliest_gap_without_disturbing_existing_jobs():
    from datetime import datetime, timedelta

    from arknights_mower.utils.scheduler_task import (
        SchedulerTask,
        next_workshop_task_time,
    )

    now = datetime(2026, 9, 9, 12)
    jobs = [SchedulerTask(time=now + timedelta(seconds=s)) for s in [-10, 0, 1, 3, 100]]
    snapshot = [job.time for job in jobs]
    assert next_workshop_task_time(jobs, now) == now + timedelta(seconds=5)
    assert next_workshop_task_time(
        jobs, now + timedelta(seconds=20)
    ) == now + timedelta(seconds=20)
    assert [job.time for job in jobs] == snapshot


@pytest.mark.parametrize(
    "status,deadline",
    [
        ("idle", None),
        ("arranging", "2999-01-01 00:00:00"),
        ("waiting_collect", "2999-01-01 00:00:00"),
        ("training", None),
        ("training", "2000-01-01 00:00:00"),
        ("training", "invalid"),
    ],
)
def test_no_lookahead_without_a_confirmed_live_training_countdown(
    next_skill, status, deadline
):
    next_skill.plans[1].update(status=status, expires_at=deadline)
    assert book_limit(rec.compute_workshop_config([], [], ["赫拉格"])) == 7


def test_live_training_allows_exactly_one_next_skill_and_reserves_remaining_steps(
    next_skill, monkeypatch
):
    next_skill.plans[1].update(status="training", expires_at="2999-01-01 00:00:00")
    next_skill.plans.append(
        {
            "id": 3,
            "char_id": "char_c",
            "skill_index": 0,
            "target_level": 3,
            "status": "idle",
            "priority": 3,
        }
    )
    data = rec.get_mastery_recommendations()
    data["operators"].append(
        {
            "char_id": "char_c",
            "recommendations": [
                {
                    "skill_index": 0,
                    "chain_needed_materials": [{"name": "技巧概要·卷3", "count": 100}],
                }
            ],
        }
    )
    training = data["operators"][1]["recommendations"][0]
    training["stages"] = [
        {
            "to_level": level + 7,
            "needed_materials": [{"name": "技巧概要·卷3", "count": count}],
        }
        for level, count in [(1, 1), (2, 2), (3, 4)]
    ]
    monkeypatch.setattr(rec, "get_mastery_recommendations", lambda: data)
    # B is training M1 (already paid); keep its M2+M3 books (6) plus A's chain (5).
    assert book_limit(rec.compute_workshop_config([], [], ["赫拉格"])) == 11
    next_skill.plans[:] = [next_skill.plans[1]]
    assert rec.compute_workshop_config([], [], ["赫拉格"]) == []


def test_lookahead_defers_recipes_using_material_reserved_for_active_training(
    next_skill, monkeypatch
):
    next_skill.plans[1].update(status="training", expires_at="2999-01-01 00:00:00")
    data = rec.get_mastery_recommendations()
    data["operators"][1]["recommendations"][0].update(
        stages=[
            {"to_level": 8, "needed_materials": []},
            {"to_level": 9, "needed_materials": [{"name": "糖组", "count": 2}]},
        ]
    )
    data["operators"][0]["recommendations"][0]["chain_needed_materials"] = [
        {"name": "糖聚块", "count": 1}
    ]
    monkeypatch.setattr(rec, "get_mastery_recommendations", lambda: data)
    result = rec.compute_workshop_config(["空爆"], [], [])
    assert all(
        "糖聚块" not in task["item_names"]
        for entry in result
        for task in entry["items"]
    )
    # After training finishes the reservation no longer blocks that recipe.
    next_skill.plans[:] = [next_skill.plans[0]]
    result = rec.compute_workshop_config(["空爆"], [], [])
    assert any(
        "糖聚块" in task["item_names"] for entry in result for task in entry["items"]
    )


def test_stocked_idle_head_still_does_not_unlock_the_following_skill(next_skill):
    next_skill.cultivate.write_text(
        json.dumps(
            {"data": {"characters": [], "items": [{"id": "3303", "count": 999}]}}
        )
    )
    assert book_limit(rec.compute_workshop_config([], [], ["赫拉格"])) == 7


def test_missing_active_skill_costs_prevent_lookahead(next_skill, monkeypatch):
    next_skill.plans[1].update(status="training", expires_at="2999-01-01 00:00:00")
    data = rec.get_mastery_recommendations()
    data["operators"].pop(1)
    monkeypatch.setattr(rec, "get_mastery_recommendations", lambda: data)
    assert rec.compute_workshop_config([], [], ["赫拉格"]) == []
