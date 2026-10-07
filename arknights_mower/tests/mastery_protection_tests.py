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


def protected_room(index):
    room = reader.RoomState(
        "empty",
        support_slot="逻各斯",
        train_slot="测试干员",
        protected=True,
        slots_reliable=True,
    )
    room.protected_skill_index = index
    return room


@pytest.mark.parametrize(
    "observed,requested,allowed",
    [(0, 0, True), (0, 1, False), (1, 1, True), (None, 1, False)],
)
def test_protected_empty_room_requires_same_skill_and_keeps_protection(
    observed, requested, allowed
):
    room = protected_room(observed)
    candidate = plan(requested)
    with patch.object(reader, "_next_idle_to_start", return_value=None):
        start, _ = reader._reconcile(
            MagicMock(), room, None, [candidate], scan_plan=candidate
        )
    assert start is (candidate if allowed else None)
    assert room.protected


def test_unreliable_trainee_does_not_admit_even_matching_skill():
    room = protected_room(1)
    room.slots_reliable = False
    candidate = plan()
    with patch.object(reader, "_next_idle_to_start", return_value=None):
        start, _ = reader._reconcile(
            MagicMock(), room, None, [candidate], scan_plan=candidate
        )
    assert start is None


@pytest.mark.parametrize(
    "tiers,protected,index",
    [
        ([0, 1, 3], True, 1),
        ([2, 0, 3], True, 0),
        ([1, 2, 0], True, None),
        ([0, None, 0], True, None),
        ([0, 0, 3], False, None),
    ],
)
def test_deep_read_records_only_a_unique_partial_mastery_skill(tiers, protected, index):
    solver = MagicMock()
    solver.train_scene.return_value = Scene.TRAIN_SKILL_SELECT
    room = protected_room(2)
    with (
        patch.object(reader, "_read_slot_mastery_tier", side_effect=tiers),
        patch.object(reader, "_back_to_train_main") as back,
    ):
        assert reader._train_slot_has_mastery(solver, room=room) is protected
    assert room.protected_skill_index == index
    back.assert_called_once()


@pytest.mark.parametrize("text", ["", "含混技能"])
def test_protected_collection_does_not_continue_an_unidentified_skill(text):
    room = protected_room(None)
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
    room = protected_room(None)
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


def test_start_boundary_rejects_a_different_protected_skill_before_mutation():
    room = protected_room(0)
    solver = MagicMock()
    solver.train_scene.side_effect = RuntimeError("Unexpected training action")
    with (
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
