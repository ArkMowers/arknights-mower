"""Confirmed training pays its current stage once in the shared inventory."""

import json
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import mastery, mastery_reader, record
from arknights_mower.tests.mastery_support_fixtures import database as database
from arknights_mower.utils import email, mastery_db, mastery_recommendation
from arknights_mower.utils.scene import Scene

pytestmark = pytest.mark.usefixtures("income_db")


@pytest.fixture
def training(monkeypatch):
    data = {
        "items": {
            "3303": {"name": "技巧概要·卷3"},
            "30115": {"name": "D32钢"},
        },
        "characters": {
            "char_128_plosis": {
                "skills": [
                    {},
                    {
                        "levels": [
                            {
                                "materials": [
                                    {"id": "3303", "count": books},
                                    {"id": "30115", "count": steel},
                                ]
                            }
                            for books, steel in ((8, 4), (12, 6), (15, 6))
                        ]
                    },
                ]
            }
        },
    }
    monkeypatch.setattr(mastery_recommendation, "get_skill_data", lambda: data)
    monkeypatch.setattr(record, "workshop_inventory_changed", Event())
    monkeypatch.setattr(record, "battle_inventory_active", Event())
    start = datetime.now()
    monkeypatch.setattr(
        mastery, "_read_train_countdown", lambda _: start + timedelta(hours=8)
    )
    monkeypatch.setattr(
        mastery, "_re_read_train_countdown", lambda _: start + timedelta(hours=8)
    )
    monkeypatch.setattr(
        mastery,
        "_read_panel_text",
        lambda _: mastery_reader.RoomPanel(operator_name="白面鸮", skill_name="脑啡肽"),
    )
    monkeypatch.setattr(mastery, "_count_lit_mastery_icons", lambda _: 1)
    monkeypatch.setattr(mastery, "_arrange_support", lambda *_: None)
    monkeypatch.setattr(mastery, "_schedule_swap_if_needed", lambda *_: None)
    monkeypatch.setattr(mastery, "_schedule_collect_checked", lambda *_: None)
    monkeypatch.setattr(mastery_db, "update_plan_status", MagicMock(return_value=True))
    monkeypatch.setattr(email, "send_message", MagicMock())
    solver = MagicMock()
    solver.train_scene.return_value = Scene.TRAIN_MAIN
    plan = {
        "id": 1,
        "char_id": "char_128_plosis",
        "char_name": "白面鸮",
        "skill_index": 1,
        "skill_name": "脑啡肽",
        "target_level": 3,
        "status": "arranging",
    }
    return SimpleNamespace(
        solver=solver, plan=plan, deadline=start + timedelta(seconds=10)
    )


def confirm(training, **kwargs):
    return mastery._confirm_training_started(
        training.solver, training.plan, training.deadline, **kwargs
    )


@pytest.mark.parametrize("level,books,steel", [(1, 8, 4), (2, 12, 6), (3, 15, 6)])
def test_confirmed_training_deducts_only_the_observed_stage(
    training, monkeypatch, level, books, steel
):
    monkeypatch.setattr(mastery, "_count_lit_mastery_icons", lambda _: level)
    record.save_inventory_counts({"技巧概要·卷3": 70, "D32钢": 20, "碳": 99})
    record.workshop_inventory_changed.clear()

    assert confirm(training, step_level=3) == "started"
    assert record.get_inventory_counts() == {
        "技巧概要·卷3": 70 - books,
        "D32钢": 20 - steel,
        "碳": 99,
    }
    assert record.workshop_inventory_changed.is_set()


def test_reconfirmation_restart_and_recreated_plan_never_pay_twice(
    training, monkeypatch
):
    record.save_inventory_counts({"技巧概要·卷3": 70, "D32钢": 20})
    assert confirm(training) == "started"
    record.workshop_inventory_changed.clear()
    monkeypatch.setattr(record, "_tables_created", False)
    training.plan["id"] = 2

    assert confirm(training) == "started"
    assert record.get_inventory_counts() == {"技巧概要·卷3": 62, "D32钢": 16}
    assert not record.workshop_inventory_changed.is_set()
    with record._conn() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM mastery_inventory_consumption"
            ).fetchone()[0]
            == 1
        )


def test_next_confirmed_stage_has_its_own_payment(training, monkeypatch):
    record.save_inventory_counts({"技巧概要·卷3": 70, "D32钢": 20})
    assert confirm(training) == "started"
    monkeypatch.setattr(mastery, "_count_lit_mastery_icons", lambda _: 2)
    assert confirm(training) == "started"
    assert record.get_inventory_counts() == {"技巧概要·卷3": 50, "D32钢": 10}


def test_unreadable_training_icons_use_the_checked_selection_stage(
    training, monkeypatch
):
    record.save_inventory_counts({"技巧概要·卷3": 70, "D32钢": 20})
    monkeypatch.setattr(mastery, "_count_lit_mastery_icons", lambda _: None)
    assert confirm(training, step_level=2) == "started"
    assert record.get_inventory_counts() == {"技巧概要·卷3": 58, "D32钢": 14}


def test_unknown_stage_never_guesses_the_plan_target(training, monkeypatch):
    record.save_inventory_counts({"技巧概要·卷3": 70, "D32钢": 20})
    monkeypatch.setattr(mastery, "_count_lit_mastery_icons", lambda _: None)
    assert confirm(training) == "started"
    assert record.get_inventory_counts() == {"技巧概要·卷3": 70, "D32钢": 20}
    assert "库存扣减失败" in email.send_message.call_args.args[0]


@pytest.mark.parametrize("failure", ["materials", "identity", "unconfirmed"])
def test_unconfirmed_or_failed_training_does_not_deduct(training, monkeypatch, failure):
    record.save_inventory_counts({"技巧概要·卷3": 70, "D32钢": 20})
    if failure == "materials":
        training.solver.train_scene.return_value = Scene.TRAIN_SKILL_UPGRADE_ERROR
    elif failure == "identity":
        monkeypatch.setattr(
            mastery,
            "_read_panel_text",
            lambda _: mastery_reader.RoomPanel(operator_name="夜莺", skill_name="圣域"),
        )
    else:
        training.deadline = datetime.now() - timedelta(seconds=1)

    assert confirm(training) == ("timeout" if failure == "unconfirmed" else "failed")
    assert record.get_inventory_counts() == {"技巧概要·卷3": 70, "D32钢": 20}
    with record._conn() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM mastery_inventory_consumption"
            ).fetchone()[0]
            == 0
        )


def test_assistant_failure_keeps_the_confirmed_payment(training, monkeypatch):
    record.save_inventory_counts({"技巧概要·卷3": 70, "D32钢": 20})
    monkeypatch.setattr(mastery, "_arrange_support", lambda *_: "协助位不可用")
    assert confirm(training) == "started"
    assert record.get_inventory_counts() == {"技巧概要·卷3": 62, "D32钢": 16}


def test_missing_or_insufficient_counts_remain_unknown_after_payment(training):
    record.save_inventory_counts({"D32钢": 1, "碳": 99})
    assert confirm(training) == "started"
    assert record.get_inventory_counts() == {"碳": 99}


def test_payment_and_receipt_roll_back_together(training):
    record.save_inventory_counts({"技巧概要·卷3": 70, "D32钢": 20})
    record.workshop_inventory_changed.clear()
    with record._conn() as conn:
        conn.execute(
            "CREATE TRIGGER reject_payment BEFORE UPDATE ON inventory "
            "BEGIN SELECT RAISE(ABORT, 'payment failed'); END"
        )
    assert confirm(training) == "started"
    assert record.get_inventory_counts() == {"技巧概要·卷3": 70, "D32钢": 20}
    assert not record.workshop_inventory_changed.is_set()
    with record._conn() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM mastery_inventory_consumption"
            ).fetchone()[0]
            == 0
        )
    assert "库存扣减失败" in email.send_message.call_args.args[0]


def test_lagging_cloud_does_not_restore_books_spent_on_training(training):
    record.save_inventory_counts({"技巧概要·卷3": 70, "D32钢": 20})
    assert confirm(training) == "started"
    record.save_inventory_counts(
        {"技巧概要·卷3": 70, "D32钢": 20},
        scanned_counts={},
        cloud_counts={"技巧概要·卷3": 70, "D32钢": 20},
        cloud_at=datetime.now().timestamp() + 10,
    )
    assert record.get_inventory_counts() == {"技巧概要·卷3": 62, "D32钢": 16}


def test_later_plan_admission_uses_paid_stock_instead_of_old_cloud_cache(
    training, database, tmp_path, monkeypatch
):
    record.save_inventory_counts({"技巧概要·卷3": 70, "D32钢": 20})
    assert confirm(training, step_level=1) == "started"
    mastery_db.insert_plan("char_waiting", 0, 1, "等待技能", "等待干员")
    resources = tmp_path / "skills.json"
    resources.write_text(json.dumps({"items": {"3303": {"name": "技巧概要·卷3"}}}))
    cloud = tmp_path / "cultivate.json"
    cloud.write_text(json.dumps({"data": {"items": [{"id": "3303", "count": 70}]}}))
    monkeypatch.setattr(mastery_recommendation, "_find_skill_data", lambda: resources)
    monkeypatch.setattr(mastery_recommendation, "get_path", lambda _: cloud)
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
        lambda _: None,
    )
    monkeypatch.setattr(
        mastery_recommendation,
        "get_mastery_recommendations",
        lambda: {
            "has_data": True,
            "operators": [
                {
                    "char_id": "char_waiting",
                    "name": "等待干员",
                    "profession": "MEDIC",
                    "recommendations": [
                        {
                            "skill_index": 0,
                            "skill_name": "等待技能",
                            "current_level": 0,
                            "chain_needed_materials": [
                                {"name": "技巧概要·卷3", "count": 63}
                            ],
                        }
                    ],
                }
            ],
        },
    )
    result = mastery_recommendation.auto_schedule_mastery_tasks()
    assert result["scheduled"] == []
    assert result["skipped"][0]["char_id"] == "char_waiting"
    record.save_inventory_counts({"技巧概要·卷3": 63})
    assert (
        mastery_recommendation.auto_schedule_mastery_tasks()["scheduled"][0]["char_id"]
        == "char_waiting"
    )
