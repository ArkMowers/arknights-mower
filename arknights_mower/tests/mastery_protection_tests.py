"""Protected training permits only the same observed trainee and skill."""

from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers import mastery
from arknights_mower.solvers import mastery_reader as reader
from arknights_mower.utils.scene import Scene


def plan(index=1):
    return {
        "id": 1,
        "char_id": "char_test",
        "char_name": "测试干员",
        "skill_index": index,
        "skill_name": f"技能{index + 1}",
        "target_level": 3,
        "status": "idle",
        "priority": 1,
    }


def protected_room(state="empty", skill_name=""):
    return reader.RoomState(
        state,
        panel=reader.RoomPanel(
            operator_name="测试干员", skill_name=skill_name, mastery_tier=2
        ),
        support_slot="逻各斯",
        train_slot="测试干员",
        protected=True,
        slots_reliable=True,
    )


@pytest.mark.parametrize(
    "tiers,requested",
    [([0, 1, 3], 1), ([2, 0, 3], 0), ([1, 2, 0], 1), ([0, None, 0], 1)],
)
def test_restart_empty_room_does_not_infer_previous_skill_from_historical_tiers(
    tiers, requested
):
    solver = MagicMock()
    solver.train_scene.return_value = Scene.TRAIN_SKILL_SELECT
    room = protected_room()
    room.panel = reader.RoomPanel(idle_marker=True)
    candidate = plan(requested)
    with (
        patch.object(reader.config.conf, "enable_mastery", True),
        patch.object(reader, "_read_slot_mastery_tier", side_effect=tiers),
        patch.object(reader, "_back_to_train_main") as back,
        patch.object(reader, "_next_idle_to_start", return_value=None),
    ):
        room.protected = reader._compute_protected(solver, room, scan_plan=candidate)
        start, _ = reader._reconcile(
            solver, room, None, [candidate], scan_plan=candidate
        )
    assert start is None
    assert room.protected
    back.assert_called_once()


def test_empty_room_does_not_admit_cached_panel_without_current_collection():
    room = protected_room(skill_name="技能A")
    with patch.object(reader, "resolve_panel_skill") as resolve:
        assert not reader._protected_plan_matches(plan(), room)
    resolve.assert_not_called()


@pytest.mark.parametrize(
    "state,collected,observed,requested,allowed",
    [
        ("waiting_collect", False, 0, 0, True),
        ("waiting_collect", False, 0, 1, False),
        ("waiting_collect", False, None, 1, False),
        ("empty", True, 1, 1, True),
        ("empty", True, 0, 1, False),
        ("empty", True, None, 1, False),
        ("empty", False, 1, 1, False),
        ("training", False, 1, 1, False),
    ],
)
def test_protected_identity_requires_direct_panel_or_same_observation_collection(
    state, collected, observed, requested, allowed
):
    room = protected_room(state, "技能A")
    room.collected = collected
    with patch.object(reader, "resolve_panel_skill", return_value=observed):
        assert reader._protected_plan_matches(plan(requested), room) is allowed
    assert room.protected


@pytest.mark.parametrize("operator", ["", "其他干员"])
def test_protected_collection_requires_same_observed_operator(operator):
    room = protected_room("waiting_collect", "技能A")
    room.panel.operator_name = operator
    with patch.object(reader, "resolve_panel_skill", return_value=1):
        assert not reader._protected_plan_matches(plan(), room)


@pytest.mark.parametrize("tiers", [[0, 0, 3], [3, 3, 3]])
def test_no_partial_mastery_releases_protection(tiers):
    solver = MagicMock()
    solver.train_scene.return_value = Scene.TRAIN_SKILL_SELECT
    with (
        patch.object(reader, "_read_slot_mastery_tier", side_effect=tiers),
        patch.object(reader, "_back_to_train_main") as back,
    ):
        assert not reader._train_slot_has_mastery(solver)
    back.assert_called_once()


@pytest.mark.parametrize("text", ["", "含混技能"])
def test_protected_collection_does_not_continue_an_unidentified_skill(text):
    room = protected_room()
    room.state = "waiting_collect"
    room.panel = reader.RoomPanel(
        operator_name="测试干员", skill_name=text, mastery_tier=2
    )
    candidate = plan()
    with (
        patch.object(reader, "resolve_panel_skill", return_value=None),
        patch.object(reader, "_collect_plan", return_value=candidate) as collect,
        patch.object(reader, "_collect_silent") as silent,
        patch.object(reader, "_promote_plan"),
        patch.object(reader, "_notify_protected"),
    ):
        start, _ = reader._reconcile(MagicMock(), room, candidate, [candidate])
    assert start is None
    collect.assert_not_called()
    silent.assert_not_called()
    assert room.protected


def test_protected_collection_continues_the_uniquely_matched_skill():
    room = protected_room()
    room.state = "waiting_collect"
    room.panel = reader.RoomPanel(
        operator_name="测试干员", skill_name="技能A", mastery_tier=2
    )
    wrong, correct = plan(1), plan(0)
    with (
        patch.object(reader, "resolve_panel_skill", return_value=0),
        patch.object(reader, "_collect_plan", return_value=correct) as collect,
        patch.object(reader, "_promote_plan"),
    ):
        start, _ = reader._reconcile(MagicMock(), room, None, [wrong, correct])
    assert start is correct
    collect.assert_called_once_with(collect.call_args.args[0], correct, room)
    assert room.protected


@pytest.mark.parametrize("state", ["empty", "waiting_collect"])
def test_start_boundary_rejects_a_different_protected_skill_before_mutation(state):
    room = protected_room("waiting_collect", "技能A")
    room.state = state
    solver = MagicMock()
    solver.train_scene.side_effect = RuntimeError("Unexpected training action")
    with (
        patch.object(reader, "resolve_panel_skill", return_value=0),
        patch.object(mastery, "_warn_training_room_group"),
        patch(
            "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
            return_value=None,
        ),
        patch(
            "arknights_mower.utils.mastery_recommendation.get_mastery_requirement_error",
            return_value=None,
        ),
        patch("arknights_mower.utils.mastery_db.update_plan_status") as update,
    ):
        mastery._start_new_training(solver, plan(1), room=room)
    update.assert_not_called()
    solver.train_scene.assert_not_called()
    solver.choose_train.assert_not_called()
    solver.ctap.assert_not_called()


def test_real_collection_retains_panel_for_same_skill_start_admission():
    room = protected_room("waiting_collect", "技能A")
    candidate = plan(0)
    solver = MagicMock()
    with (
        patch.object(reader, "resolve_panel_skill", return_value=0),
        patch.object(reader, "collect_flow"),
        patch.object(reader, "_tap_collect_confirm"),
        patch.object(reader, "_promote_plan"),
        patch("arknights_mower.utils.mastery_db.update_plan_status") as update,
    ):
        start, _ = reader._reconcile(solver, room, None, [candidate])
        assert start is candidate
        assert room.collected
        room.state = "empty"
        assert reader._protected_plan_matches(start, room)
        assert not reader._protected_plan_matches(plan(1), room)
    update.assert_called_once_with(candidate["id"], "idle")
    assert room.protected
