"""Button and depot scan share ordered growth preparation."""

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
from arknights_mower.utils import workshop_automation as auto  # noqa: E402


def test_only_first_skill_by_queue_priority_is_prepared(next_skill):
    assert book_limit(auto.calculate_workshop_plan(config.conf).settings) == 7
    next_skill.plans[0]["priority"] = 0
    assert book_limit(auto.calculate_workshop_plan(config.conf).settings) == 5
    next_skill.plans.pop(0)
    assert book_limit(auto.calculate_workshop_plan(config.conf).settings) == 7


def test_box_completed_head_is_skipped_before_selecting_next_skill(next_skill):
    data = json.loads(next_skill.cultivate.read_text())
    data["data"]["characters"][1]["skills"][0]["level"] = 3
    next_skill.cultivate.write_text(json.dumps(data))
    assert book_limit(auto.calculate_workshop_plan(config.conf).settings) == 5


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
        for entry in auto.calculate_workshop_plan(config.conf).settings
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
