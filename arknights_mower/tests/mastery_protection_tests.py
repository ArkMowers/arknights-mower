"""Protected training preserves the trainee without restricting their skill."""

from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers import mastery
from arknights_mower.solvers import mastery_reader as reader
from arknights_mower.utils.scene import Scene


def plan(index=1, **values):
    result = {
        "id": 1,
        "char_id": "char_test",
        "char_name": "测试干员",
        "skill_index": index,
        "skill_name": f"技能{index + 1}",
        "target_level": 3,
        "status": "idle",
        "priority": 1,
    }
    result.update(values)
    return result


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


@pytest.mark.parametrize("tiers", [[0, 1, 3], [1, 2, 0], [0, None, 0]])
@pytest.mark.parametrize("requested", [0, 1, 2])
def test_restart_protected_room_admits_any_skill_of_same_trainee(tiers, requested):
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
    assert start is candidate
    assert room.protected
    back.assert_called_once()


@pytest.mark.parametrize(
    "operator,reliable", [("其他干员", True), ("", True), ("测试干员", False)]
)
def test_protected_room_requires_same_reliably_observed_trainee(operator, reliable):
    room = protected_room()
    room.train_slot = operator
    room.slots_reliable = reliable
    with patch.object(reader, "_next_idle_to_start", return_value=None):
        start, _ = reader._reconcile(MagicMock(), room, None, [], scan_plan=plan())
    assert start is None
    assert room.protected


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


def test_protected_collection_attributes_progress_to_observed_skill_only():
    room = protected_room("waiting_collect", "技能A")
    wrong, correct = plan(1, id=2), plan(0)
    with (
        patch.object(reader, "resolve_panel_skill", return_value=0),
        patch.object(reader, "_collect_plan", return_value=correct) as collect,
        patch.object(reader, "_promote_plan"),
    ):
        start, _ = reader._reconcile(MagicMock(), room, None, [wrong, correct])
    assert start is correct
    assert collect.call_args.args[1] is correct
    assert room.protected


@pytest.mark.parametrize("skill", ["技能A", "", "含混技能"])
def test_unplanned_protected_collection_does_not_block_other_skills(skill):
    room = protected_room("waiting_collect", skill)
    candidate = plan(1)
    with (
        patch.object(
            reader, "resolve_panel_skill", return_value=0 if skill == "技能A" else None
        ),
        patch.object(reader, "_collect_plan") as collect,
        patch.object(reader, "_collect_silent") as silent,
        patch.object(reader, "_notify_protected") as notify,
    ):
        start, _ = reader._reconcile(MagicMock(), room, None, [candidate])
    assert start is None
    collect.assert_not_called()
    silent.assert_called_once()
    notify.assert_not_called()
    assert room.protected


@pytest.mark.parametrize("operator", ["", "其他干员"])
def test_collected_observation_still_requires_same_trainee(operator):
    room = protected_room("waiting_collect", "技能A")
    room.panel.operator_name = operator
    assert not reader._protected_trainee_matches(plan(), room)


@pytest.mark.parametrize("state", ["empty", "waiting_collect"])
def test_start_boundary_rejects_different_trainee_before_mutation(state):
    room = protected_room(state, "技能A")
    solver = MagicMock()
    with patch("arknights_mower.utils.mastery_db.update_plan_status") as update:
        mastery._start_new_training(solver, plan(char_name="其他干员"), room=room)
    update.assert_not_called()
    solver.train_scene.assert_not_called()
    solver.choose_train.assert_not_called()
    solver.ctap.assert_not_called()


@pytest.mark.parametrize("state", ["empty", "waiting_collect"])
def test_start_boundary_allows_different_skill_of_same_trainee(state):
    room = protected_room(state, "技能A")
    with (
        patch.object(mastery, "_warn_training_room_group"),
        patch(
            "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
            side_effect=RuntimeError("past protection gate"),
        ),
        pytest.raises(RuntimeError, match="past protection gate"),
    ):
        mastery._start_new_training(MagicMock(), plan(2), room=room)
    assert room.protected


@pytest.mark.parametrize("status", ["idle", "failed"])
@pytest.mark.parametrize("protected", [False, True])
def test_mid_chain_shortage_blocks_later_plan_even_for_same_trainee(status, protected):
    room = protected_room()
    room.protected = protected
    waiting = plan(
        0, status=status, failed_reason="材料不足", expires_at="2026-10-01 12:00:00"
    )
    later = plan(1, id=2)
    start, _ = reader._reconcile(
        MagicMock(), room, None, [waiting, later], scan_plan=later
    )
    assert start is None
    assert room.protected is protected


def test_mid_chain_plan_can_resume_after_scan_confirms_its_materials():
    room = protected_room()
    waiting = plan(0, failed_reason="材料不足", expires_at="2026-10-01 12:00:00")
    start, _ = reader._reconcile(MagicMock(), room, None, [waiting], scan_plan=waiting)
    assert start is waiting
    assert room.protected
