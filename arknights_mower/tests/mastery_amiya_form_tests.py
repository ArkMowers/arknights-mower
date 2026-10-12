"""Amiya form checks preserve reducers and resume after a fresh room observation."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import mastery  # noqa: E402
from arknights_mower.solvers import mastery_reader as reader  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import config, mastery_db, rapidocr  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


def skill_text(name, index=0, confidence=0.99):
    y = 210 + 316 * index
    return [[(240, y), (520, y), (520, y + 35), (240, y + 35)], name, confidence]


@pytest.fixture
def case(monkeypatch):
    candidate = dict(
        id=1,
        char_id="char_1001_amiya2",
        char_name="阿米娅",
        skill_index=1,
        skill_name="二技能·影霄·绝影",
        target_level=3,
        status="idle",
    )
    solver = MagicMock()
    solver.tasks = []
    solver.task = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
    solver.task.plan_key = "1"
    solver.tasks.append(solver.task)
    solver.amiya_pending_plan_id = None
    solver.recog = SimpleNamespace(
        img=np.zeros((1080, 1920, 3), dtype=np.uint8),
        w=1920,
        h=1080,
        update=MagicMock(),
    )
    slots = [{"agent": "逻各斯"}, {"agent": "阿米娅"}]
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", False)
    monkeypatch.setattr(config, "plan", {})
    monkeypatch.setattr(mastery_db, "get_plan_by_id", lambda _: candidate)
    monkeypatch.setattr(mastery_db, "get_all_plans", lambda: [candidate])
    monkeypatch.setattr(mastery_db, "get_reconcile_plans", lambda: [candidate])
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)
    update = MagicMock()
    monkeypatch.setattr(mastery_db, "update_plan_status", update)
    monkeypatch.setattr(mastery_db, "should_notify", lambda *_: True)
    monkeypatch.setattr(mastery, "_warn_training_room_group", lambda _: None)
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
        lambda _: None,
    )
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_recommendation.get_mastery_requirement_error",
        lambda _: None,
    )
    monkeypatch.setattr(reader, "_settle_in_room", lambda _: Scene.TRAIN_MAIN)
    monkeypatch.setattr(
        reader, "read_main_panel", lambda _: reader.RoomPanel(idle_marker=True)
    )
    monkeypatch.setattr(
        reader, "_read_slots_checked", lambda _: (*["逻各斯", "阿米娅"], slots, True)
    )
    monkeypatch.setattr(reader, "_compute_protected", lambda *a, **kw: True)
    monkeypatch.setattr(mastery, "_read_train_countdown3", lambda _: ("failed", None))
    started = MagicMock(return_value="started")
    monkeypatch.setattr(mastery, "_confirm_training_started", started)
    notification = MagicMock()
    monkeypatch.setattr("arknights_mower.utils.email.send_message", notification)
    ocr = MagicMock(return_value=([skill_text("精神爆发", 1)], 0))
    monkeypatch.setattr(rapidocr, "engine", ocr)
    return solver, candidate, started, notification, update, ocr


def test_dispatch_missing_form_preserves_halving_and_next_visit_resumes(
    case, monkeypatch
):
    solver, candidate, started, notification, update, ocr = case
    solver.train_scene.side_effect = [
        Scene.TRAIN_MAIN,
        Scene.TRAIN_SKILL_SELECT,
        Scene.TRAIN_SKILL_SELECT,
    ]
    mastery.run_mastery_task(solver)
    assert solver.amiya_pending_plan_id == candidate["id"]
    started.assert_not_called()
    solver.choose_train.assert_not_called()
    solver.ctap.assert_not_called()
    update.assert_any_call(
        candidate["id"], "idle", failed_reason=reader.AMIYA_FORM_WAIT_REASON
    )
    assert not any(call.args[1] == "failed" for call in update.call_args_list)
    assert notification.call_args.kwargs["level"] == "ERROR"
    assert "手动切换" in notification.call_args.args[0]
    assert "本轮跳过所有训练室操作" in notification.call_args.args[0]
    recheck = next(task for task in solver.tasks if task is not solver.task)
    assert recheck.plan_key == "1"
    assert recheck.time > solver.task.time

    # A fresh visit checks the new frame instead of treating the previous skip as a pause.
    solver.train_scene.side_effect = None
    solver.train_scene.return_value = Scene.TRAIN_SKILL_SELECT
    ocr.return_value = ([skill_text("影霄·绝影", 1)], 0)

    def back_to_main(_):
        solver.train_scene.side_effect = [
            Scene.TRAIN_MAIN,
            Scene.TRAIN_SKILL_SELECT,
            Scene.TRAIN_SKILL_SELECT,
            Scene.TRAIN_SKILL_UPGRADE,
        ]
        return True

    monkeypatch.setattr(reader, "_back_to_train_main", back_to_main)
    mastery.run_mastery_task(solver)
    assert solver.amiya_pending_plan_id is None
    assert solver.enter_room.call_count == 2
    started.assert_called_once()
    assert solver.ctap.call_count == 1


@pytest.mark.parametrize("result", ["精神爆发", None])
def test_later_room_visits_still_read_and_do_not_collect_or_arrange(
    case, monkeypatch, result
):
    solver, candidate, _, _, _, ocr = case
    solver.amiya_pending_plan_id = candidate["id"]
    solver.train_scene.return_value = Scene.TRAIN_SKILL_SELECT
    ocr.return_value = ([skill_text(result, 1)] if result else [], 0)
    monkeypatch.setattr(reader, "_back_to_train_main", lambda _: True)
    collect = MagicMock()
    monkeypatch.setattr(reader, "_collect_plan", collect)
    monkeypatch.setattr(reader, "_collect_silent", collect)
    for _ in range(2):
        room = reader.read_room_state(solver)
        assert room.amiya_form_waiting
        assert reader._reconcile(
            solver, room, None, [candidate], scan_plan=candidate
        ) == (None, True)
    assert solver.enter_room.call_count == 2
    assert ocr.call_count >= 2
    collect.assert_not_called()
    solver.choose_train.assert_not_called()
    solver.ctap.assert_not_called()
    assert len([t for t in solver.tasks if t is not solver.task]) == 1


def test_unreadable_skill_does_not_claim_wrong_form(case):
    solver, candidate, started, notification, _, ocr = case
    room = reader.RoomState(
        "empty", train_slot="阿米娅", support_slot="逻各斯", slots_reliable=True
    )
    solver.train_scene.side_effect = [Scene.TRAIN_MAIN, Scene.TRAIN_SKILL_SELECT] + [
        Scene.TRAIN_SKILL_SELECT
    ] * 3
    ocr.return_value = ([], 0)
    mastery._start_new_training(solver, candidate, room=room)
    started.assert_not_called()
    assert notification.call_args.kwargs["level"] == "WARNING"
    assert "读取失败" in notification.call_args.args[0]
    assert "显示其他升变" not in notification.call_args.args[0]


def test_later_confirmed_mismatch_escalates_an_unreadable_warning(case, monkeypatch):
    solver, candidate, _, notification, _, _ = case
    seen = set()

    def notify_once(kind, key):
        new = (kind, key) not in seen
        seen.add((kind, key))
        return new

    monkeypatch.setattr(mastery_db, "should_notify", notify_once)
    room = reader.RoomState(
        "empty", train_slot="阿米娅", support_slot="逻各斯", slots_reliable=True
    )
    mastery._defer_amiya_form(solver, candidate, room, None)
    assert notification.call_args.kwargs["level"] == "WARNING"
    solver.train_scene.return_value = Scene.TRAIN_SKILL_SELECT
    monkeypatch.setattr(reader, "_back_to_train_main", lambda _: True)
    for _ in range(2):
        assert reader.read_room_state(solver).amiya_form_waiting
    assert notification.call_count == 2
    assert notification.call_args.kwargs["level"] == "ERROR"
    assert "手动切换" in notification.call_args.args[0]
    solver.choose_train.assert_not_called()


@pytest.mark.parametrize("follow", [False, True])
def test_arrangement_gate_blocks_both_slots_only_for_current_observation(
    case, monkeypatch, follow
):
    solver, _, _, _, _, _ = case
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", follow)
    room = reader.RoomState("empty", amiya_form_waiting=True)
    monkeypatch.setattr(reader, "read_room_state", lambda *a, **kw: room)
    new_plan = {"train": ["褐果", "阿米娅"]}
    BaseSchedulerSolver.agent_arrange_room(solver, new_plan, "train", new_plan)
    assert new_plan == {}
    solver.turn_on_room_detail.assert_not_called()
    solver.choose_train.assert_not_called()


def test_amiya_selection_clears_a_preexisting_profession_filter():
    solver = MagicMock()
    solver.scan_agent.return_value = (["阿米娅"], [])
    solver.verify_agent.return_value = True
    BaseSchedulerSolver.choose_train_ope(solver, "阿米娅")
    solver.profession_filter.assert_called_once_with("ALL")
    solver.scan_agent.assert_called_once()
    assert solver.swipe_left.call_args.kwargs["special_filter"] == "ALL"


@pytest.mark.parametrize(
    "cid,index,name,row,score,expected",
    [
        ("char_002_amiya", 1, "精神爆发", 1, 0.99, True),
        ("char_1001_amiya2", 1, "影霄·绝影", 1, 0.99, True),
        ("char_1037_amiya3", 0, "哀恸共情", 0, 0.99, True),
        ("char_002_amiya", 2, "慈悲愿景", 1, 0.99, False),
        ("char_1001_amiya2", 1, "精神爆发", 1, 0.99, False),
        ("char_1001_amiya2", 1, "影霄·绝影", 0, 0.99, None),
        ("char_1001_amiya2", 1, "影霄·绝影", 1, 0.5, None),
        ("char_1001_amiya2", 1, "", 1, 0.99, None),
    ],
)
def test_skill_read_confirms_name_form_and_slot(
    case, cid, index, name, row, score, expected
):
    solver, candidate, _, _, _, ocr = case
    solver.train_scene.return_value = Scene.TRAIN_SKILL_SELECT
    candidate.update(char_id=cid, skill_index=index)
    ocr.return_value = ([skill_text(name, row, score)], 0)
    assert reader.read_amiya_skill_available(solver, candidate) is expected
    assert ocr.call_count <= 3


@pytest.mark.parametrize("error", ["cancel", "recovery", "ocr"])
def test_form_reader_preserves_cancellation_and_bounds_ocr_failures(case, error):
    from arknights_mower.utils.csleep import MowerExit
    from arknights_mower.utils.device.recovery import DeviceRecoveryError

    solver, candidate, _, _, _, ocr = case
    solver.train_scene.return_value = Scene.TRAIN_SKILL_SELECT
    fault = {"cancel": MowerExit, "recovery": DeviceRecoveryError, "ocr": RuntimeError}[
        error
    ]
    ocr.side_effect = fault("offline fault")
    if error == "ocr":
        assert reader.read_amiya_skill_available(solver, candidate) is None
        assert ocr.call_count == 3
    else:
        with pytest.raises(fault):
            reader.read_amiya_skill_available(solver, candidate)
        assert ocr.call_count == 1
        solver.sleep.assert_not_called()


def test_real_ocr_reads_rendered_amiya_skill_names(case, monkeypatch):
    from pathlib import Path

    from PIL import Image, ImageDraw, ImageFont
    from rapidocr_onnxruntime import RapidOCR

    solver, candidate, _, _, _, _ = case
    solver.train_scene.return_value = Scene.TRAIN_SKILL_SELECT
    monkeypatch.setattr(rapidocr, "engine", RapidOCR(text_score=0.3))
    font = ImageFont.truetype(
        str(Path(__file__).parents[1] / "fonts/SourceHanSansCN-Medium-mastery.ttf"), 32
    )
    for cid, index, name in (
        ("char_002_amiya", 1, "精神爆发"),
        ("char_1001_amiya2", 1, "影霄·绝影"),
        ("char_1037_amiya3", 0, "哀恸共情"),
    ):
        image = Image.new("RGB", (1920, 1080), (40, 40, 40))
        ImageDraw.Draw(image).text(
            (240, 325 + 316 * index), name, font=font, fill="white"
        )
        solver.recog.img = np.asarray(image)
        candidate.update(char_id=cid, skill_index=index)
        assert reader.read_amiya_skill_available(solver, candidate) is True
