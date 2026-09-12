"""Do not let mastery replace occupants managed by a scheduled group."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers import mastery
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.mastery_support_data import training_room_group_error
from arknights_mower.utils.scene import Scene


def grouped_schedule(backup=False, index=0):
    slots = [{"agent": "Current"}, {"agent": "Current"}]
    slots[index] = {"agent": "赫默", "group": "训练组"}
    table = {"train": {"plans": slots}}
    return {
        "default": "plan1",
        "plan1": {} if backup else table,
        "backup_plans": [{"name": "夜班", "plan": table}] if backup else [],
    }


@pytest.mark.parametrize("backup", [False, True])
@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("as_model", [False, True])
def test_training_group_reports_both_slots_and_schedule_types(backup, index, as_model):
    plan = grouped_schedule(backup, index)
    error = training_room_group_error(PlanModel(**plan) if as_model else plan)
    assert "赫默（组名：训练组）" in error
    assert ("备用排班「夜班」" if backup else "主排班") in error


@pytest.mark.parametrize(
    "train",
    [
        None,
        {"plans": []},
        {"plans": [{"agent": "赫默", "group": ""}]},
        {"plans": [{"agent": "Current", "group": "旧组名"}]},
    ],
)
def test_unbound_training_room_allows_groups_in_other_rooms(train):
    plan = {
        "plan1": {
            "train": train,
            "room_3_2": {"plans": [{"agent": "赫默", "group": "生产组"}]},
        }
    }
    assert training_room_group_error(plan) is None


@pytest.mark.parametrize("automatic", [False, True])
@pytest.mark.parametrize("backup", [False, True])
def test_start_fails_before_changing_either_slot(automatic, backup):
    plan = {
        "id": 1,
        "char_id": "test",
        "char_name": "异客",
        "skill_index": 1,
        "skill_name": "聚焦指令",
        "target_level": 3,
        "support_plan": {"stages": []} if automatic else None,
    }
    solver = MagicMock()
    with (
        patch(
            "arknights_mower.utils.config.plan", PlanModel(**grouped_schedule(backup))
        ),
        patch("arknights_mower.utils.mastery_db.update_plan_status") as update,
        patch("arknights_mower.utils.email.send_message") as notify,
    ):
        mastery._start_new_training(solver, plan)
    assert solver.mock_calls == []
    update.assert_called_once()
    assert update.call_args.args == (1, "failed")
    assert "训练组" in update.call_args.kwargs["failed_reason"]
    notify.assert_called_once()
    assert "赫默" in notify.call_args.args[0]
    assert notify.call_args.kwargs["level"] == "ERROR"


@pytest.mark.parametrize("automatic", [False, True])
def test_pending_swap_freezes_without_selecting_anyone_and_keeps_collection(automatic):
    plan = {
        "id": 1,
        "status": "training",
        "swap_frozen": 0,
        "char_name": "异客",
        "target_level": 3,
        "support_plan": {"stages": []} if automatic else None,
    }
    panel = SimpleNamespace(
        mastery_tier=2,
        countdown_state="active",
        countdown=datetime.now() + timedelta(hours=6),
    )
    solver = MagicMock()
    solver.train_scene.return_value = Scene.TRAIN_MAIN
    with (
        patch("arknights_mower.utils.config.plan", PlanModel(**grouped_schedule())),
        patch(
            "arknights_mower.utils.config.conf",
            SimpleNamespace(enable_mastery=True, assistant_follows_schedule=False),
        ),
        patch("arknights_mower.utils.mastery_db.get_active_plan", return_value=plan),
        patch("arknights_mower.utils.mastery_db.update_plan_status") as update,
        patch("arknights_mower.utils.mastery_db.should_notify", return_value=True),
        patch("arknights_mower.utils.email.send_message") as notify,
        patch.object(mastery, "read_main_panel", return_value=panel),
        patch.object(mastery, "_schedule_collect_after_swap") as collect,
        patch.object(mastery, "_read_slots_checked") as slots,
    ):
        mastery.run_swap_support(solver)
    solver.choose_train.assert_not_called()
    slots.assert_not_called()
    update.assert_called_once_with(1, "training", swap_frozen=1)
    collect.assert_called_once_with(solver, plan, tier=2)
    notify.assert_called_once()
    assert "训练组" in notify.call_args.args[0]
