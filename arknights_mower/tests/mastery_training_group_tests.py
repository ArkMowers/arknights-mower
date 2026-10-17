"""Warn about scheduled training-room groups without blocking mastery."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers import mastery
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.mastery_support_data import training_room_group_warning
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
    warning = training_room_group_warning(PlanModel(**plan) if as_model else plan)
    assert "赫默（组名：训练组）" in warning
    assert ("备用排班「夜班」" if backup else "主排班") in warning


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
    assert training_room_group_warning(plan) is None


@pytest.mark.parametrize("automatic", [False, True])
@pytest.mark.parametrize("backup", [False, True])
@pytest.mark.parametrize("follow_schedule", [False, True])
def test_start_group_only_warns_when_not_following_schedule(
    automatic, backup, follow_schedule
):
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
        patch(
            "arknights_mower.utils.config.conf",
            SimpleNamespace(assistant_follows_schedule=follow_schedule),
        ),
        patch(
            "arknights_mower.utils.mastery_recommendation.get_mastery_requirement_error",
            return_value="后续校验失败",
        ),
        patch("arknights_mower.utils.mastery_db.update_plan_status") as update,
        patch("arknights_mower.utils.mastery_db.should_notify", return_value=True),
        patch("arknights_mower.utils.email.send_message") as notify,
    ):
        mastery._start_new_training(solver, plan)
    assert solver.mock_calls == []
    update.assert_called_once_with(1, "failed", failed_reason="后续校验失败")
    if follow_schedule:
        notify.assert_not_called()
    else:
        notify.assert_called_once()
        assert "赫默" in notify.call_args.args[0]
        assert "本次继续执行" in notify.call_args.args[0]
        assert notify.call_args.kwargs["level"] == "WARNING"


def test_start_does_not_mutate_training_room_for_scheduled_trainee():
    plan = {
        "id": 1,
        "char_id": "test",
        "char_name": "异客",
        "skill_index": 1,
        "skill_name": "聚焦指令",
        "target_level": 3,
    }
    solver = MagicMock()
    reason = "异客 出现在非训练室排班（room_1_1），不能进行专精训练"
    with (
        patch(
            "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
            return_value=reason,
        ),
        patch("arknights_mower.utils.mastery_db.update_plan_status") as update,
        patch("arknights_mower.utils.mastery_db.should_notify", return_value=True),
        patch("arknights_mower.utils.email.send_message") as notify,
    ):
        mastery._start_new_training(solver, plan)
    assert solver.mock_calls == []
    update.assert_not_called()
    notify.assert_called_once()
    assert reason in notify.call_args.args[0]


def test_start_defers_when_trainee_name_cannot_be_resolved():
    plan = {
        "id": 1,
        "char_id": "char_missing",
        "char_name": None,
        "skill_index": 1,
        "skill_name": "测试技能",
        "target_level": 3,
    }
    solver = MagicMock()
    with (
        patch.object(mastery, "get_char_name", return_value="char_missing"),
        patch(
            "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict"
        ) as conflict,
        patch("arknights_mower.utils.mastery_db.update_plan_status") as update,
        patch.object(mastery.logger, "warning") as warning,
    ):
        mastery._start_new_training(solver, plan)
    conflict.assert_not_called()
    update.assert_not_called()
    assert solver.mock_calls == []
    assert "排班冲突未复核" in warning.call_args.args[0]


def test_pending_swap_warns_but_continues_dispatch():
    plan = {
        "id": 1,
        "status": "training",
        "swap_frozen": 0,
        "char_id": "test",
        "char_name": "异客",
        "skill_index": 1,
        "skill_name": "聚焦指令",
        "target_level": 3,
        "support_plan": {"stages": []},
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
        patch("arknights_mower.utils.mastery_db.should_notify", return_value=True),
        patch("arknights_mower.utils.email.send_message") as notify,
        patch.object(mastery, "read_main_panel", return_value=panel),
        patch(
            "arknights_mower.solvers.mastery_support_dispatch.run_planned_swap"
        ) as dispatch,
    ):
        mastery.run_swap_support(solver)
    dispatch.assert_called_once_with(solver, plan, panel)
    notify.assert_called_once()
    assert "训练组" in notify.call_args.args[0]
    assert notify.call_args.kwargs["level"] == "WARNING"
