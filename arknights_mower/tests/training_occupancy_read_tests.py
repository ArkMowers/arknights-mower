"""训练室读回只有两槽身份与详情场景可信时才提交实际驻员。"""

import copy
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.solvers import mastery_reader, record  # noqa: E402
from arknights_mower.tests import shift_backup_convergence_tests as backup  # noqa: E402
from arknights_mower.utils import config, mastery_db, resting_priority  # noqa: E402
from arknights_mower.utils.dorm_candidates import dorm_candidates  # noqa: E402
from arknights_mower.utils.operators import Operator, Operators  # noqa: E402
from arknights_mower.utils.recognize import RecognizeError  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    try_add_release_dorm,
)

solver = backup.solver


@pytest.fixture
def training_reader(solver, monkeypatch):
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", False)
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)
    monkeypatch.setattr(mastery_db, "is_operator_busy", lambda name: False)
    data = solver.op_data
    for index, name in enumerate(("艾丽妮", "克莱门莎")):
        data.add(
            Operator(
                name,
                "",
                current_room="train",
                current_index=index,
                mood=17,
                time_stamp=datetime.now() - timedelta(hours=3),
            )
        )
    data.operators["艾丽妮"].resting_from_train = True
    for op in data.operators.values():
        if op.current_room != "train":
            op.mood = 24
    monkeypatch.setattr(resting_priority, "agent_list", list(data.operators))
    history = MagicMock()
    monkeypatch.setattr(record, "save_agent_action", history)
    monkeypatch.setattr(base, "save_agent_action", history)
    data.add = MagicMock(wraps=data.add)
    data.update_detail = MagicMock(wraps=data.update_detail)
    data.refresh_idle_dorm_search = MagicMock(wraps=data.refresh_idle_dorm_search)
    solver.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
    solver.turn_on_room_detail = MagicMock()
    solver._open_check_in_detail = MagicMock()
    solver.refresh_facility_state = MagicMock()
    solver.wait_product_complete = MagicMock()
    solver.train_scene = MagicMock(return_value=Scene.INFRA_DETAILS)
    solver.detect_room = MagicMock(return_value="train")
    close_position = ((1, 1), (2, 2))
    solver.find = MagicMock(
        side_effect=lambda name, *args, **kwargs: (
            close_position if name == "arrange_check_in_on" else None
        )
    )
    solver.tap = MagicMock(
        side_effect=lambda position, **kwargs: setattr(
            solver.train_scene, "return_value", Scene.TRAIN_MAIN
        )
    )
    solver.read_screen = MagicMock(side_effect=["艾丽妮", "克莱门莎"])
    solver.read_accurate_mood = MagicMock(return_value=18)
    solver.read_operator_time = MagicMock(
        return_value=datetime.now() + timedelta(hours=1)
    )
    solver.sleep = MagicMock()
    solver.last_train_mood_read = datetime.now() - timedelta(hours=3)
    data.room_observations = {"train": 4, "dormitory_1": 9}
    release = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]},
        meta_data="艾丽妮",
    )
    solver.tasks = [release]
    solver.find_next_task = MagicMock(return_value=release)
    solver.history = history
    return solver


def snapshot(instance):
    return (
        {
            name: copy.deepcopy(op.__dict__)
            for name, op in instance.op_data.operators.items()
        },
        [copy.deepcopy(bed.__dict__) for bed in instance.op_data.all_dorms()],
        [copy.deepcopy(task.__dict__) for task in instance.tasks],
        instance.last_train_mood_read,
        copy.deepcopy(instance.op_data.room_observations),
    )


@pytest.mark.parametrize("names", [[""] * 6, ["艾丽妮", "", "", ""]])
def test_unknown_names_leave_the_entire_observation_uncommitted(training_reader, names):
    s = training_reader
    s.read_screen.side_effect = names
    before = snapshot(s)

    with pytest.raises(RecognizeError):
        s.get_agent_from_room("train")

    assert snapshot(s) == before
    s.op_data.add.assert_not_called()
    s.op_data.update_detail.assert_not_called()
    s.op_data.refresh_idle_dorm_search.assert_not_called()
    s.history.assert_not_called()
    candidates = dorm_candidates(s.op_data)
    assert "艾丽妮" not in candidates.filling
    pending = []
    try_add_release_dorm({}, None, s.op_data, pending)
    assert all("艾丽妮" not in row for task in pending for row in task.plan.values())


def test_second_unknown_does_not_register_a_new_first_occupant(training_reader):
    s = training_reader
    s.read_screen.side_effect = ["红", "", "", ""]
    before = snapshot(s)

    with pytest.raises(RecognizeError):
        s.get_agent_from_room("train")

    assert snapshot(s) == before
    assert "红" not in s.op_data.operators
    s.history.assert_not_called()
    s.op_data.add.assert_not_called()


@pytest.mark.parametrize(
    "scene,room", [(Scene.TRAIN_MAIN, "train"), (Scene.INFRA_DETAILS, "factory")]
)
def test_unconfirmed_training_detail_does_not_publish_occupancy(
    training_reader, scene, room
):
    s = training_reader
    s.train_scene.return_value = scene
    s.detect_room.return_value = room
    before = snapshot(s)

    with pytest.raises(RecognizeError):
        s.get_agent_from_room("train")

    assert snapshot(s) == before
    s.history.assert_not_called()
    s.op_data.update_detail.assert_not_called()


def test_scene_change_after_names_rejects_the_whole_read(training_reader):
    s = training_reader
    names = iter(("艾丽妮", "克莱门莎"))

    def read_name(*args, **kwargs):
        name = next(names)
        if name == "克莱门莎":
            s.train_scene.return_value = Scene.TRAIN_MAIN
        return name

    s.read_screen.side_effect = read_name
    before = snapshot(s)

    with pytest.raises(RecognizeError):
        s.get_agent_from_room("train", read_time_index=[0])

    assert snapshot(s) == before
    s.history.assert_not_called()
    s.op_data.update_detail.assert_not_called()


def test_duplicate_names_do_not_move_one_operator_between_both_slots(training_reader):
    s = training_reader
    s.read_screen.side_effect = ["艾丽妮", "艾丽妮"]
    before = snapshot(s)

    with pytest.raises(RecognizeError):
        s.get_agent_from_room("train")

    assert snapshot(s) == before
    s.history.assert_not_called()


@pytest.mark.parametrize("configured", [False, True])
def test_valid_read_commits_both_physical_slots_and_success_time(
    training_reader, configured
):
    s = training_reader
    if configured:
        s.op_data.plan["train"] = []
    old_time = s.last_train_mood_read
    s._training_mood_failure = {"previous_failure": True}

    result = s.get_agent_from_room("train")

    assert isinstance(result, list)
    assert [(row["agent"], row["mood"]) for row in result] == [
        ("艾丽妮", 18),
        ("克莱门莎", 18),
    ]
    assert s.op_data.get_current_room("train", True) == ["艾丽妮", "克莱门莎"]
    assert s.history.call_count == 2
    assert s.last_train_mood_read > old_time
    assert s._training_mood_failure is None
    assert s.op_data.room_observations == {"train": 5, "dormitory_1": 9}
    s.op_data.refresh_idle_dorm_search.assert_not_called()


@pytest.mark.parametrize("slot", [0, 1])
@pytest.mark.parametrize(
    "mood", [-1, float("nan"), 25, "unreadable", None, float("inf")]
)
@pytest.mark.parametrize("strict", [False, True])
def test_invalid_measured_mood_rejects_both_slots_before_any_commit(
    training_reader, slot, mood, strict
):
    s = training_reader
    data = s.op_data
    data.add(Operator("红", "", current_room="dormitory_1", current_index=2, mood=16))
    data.dorm[0].name = "红"
    data.dorm[0].time = datetime.now() + timedelta(hours=1)
    data.add.reset_mock()
    s.read_screen.side_effect = ["红", "克莱门莎"]
    measured = [18, 18]
    measured[slot] = mood
    s.read_accurate_mood.side_effect = measured
    before = snapshot(s)

    with pytest.raises(RecognizeError):
        s.get_agent_from_room("train", strict_observation=strict)

    assert snapshot(s) == before
    data.add.assert_not_called()
    data.update_detail.assert_not_called()
    data.refresh_idle_dorm_search.assert_not_called()
    s.history.assert_not_called()


@pytest.mark.parametrize("slot", [0, 1])
def test_fiammetta_in_either_training_slot_needs_no_implicit_dorm_timer(
    training_reader, slot
):
    s = training_reader
    names = ["艾丽妮", "克莱门莎"]
    names[slot] = "菲亚梅塔"
    s.read_screen.side_effect = names
    old_time = s.last_train_mood_read

    result = s.get_agent_from_room("train")

    assert [row["agent"] for row in result] == names
    assert s.op_data.get_current_room("train", True) == names
    assert s.op_data.operators["菲亚梅塔"].mood == 18
    assert s.history.call_count == 2
    assert s.last_train_mood_read > old_time
    assert s.op_data.room_observations == {"train": 5, "dormitory_1": 9}
    s.read_operator_time.assert_not_called()


def test_explicitly_empty_assistant_releases_the_old_support(training_reader):
    s = training_reader
    s.find.side_effect = lambda name, scope=None: (
        name == "infra_no_operator" and scope[0][1] == 135
    )
    s.read_screen.side_effect = ["克莱门莎"]

    result = s.get_agent_from_room("train")

    assert result[0] == {"agent": "", "mood": -1}
    assert s.op_data.get_train_support() is None
    assert s.op_data.operators["艾丽妮"].current_room == ""
    assert s.op_data.operators["艾丽妮"].current_index == -1
    assert s.history.call_count == 1
    s.op_data.refresh_idle_dorm_search.assert_called_once_with(
        reason="专精协助位干员已释放", names=["艾丽妮"]
    )
    assert "艾丽妮" in dorm_candidates(s.op_data).filling


def test_confirmed_assistant_replacement_releases_its_old_dorm_bed(training_reader):
    s = training_reader
    data = s.op_data
    data.add(Operator("红", "", current_room="dormitory_1", current_index=2, mood=16))
    data.dorm[0].name = "红"
    data.dorm[0].time = datetime.now() + timedelta(hours=1)
    s.read_screen.side_effect = ["红", "克莱门莎"]

    result = s.get_agent_from_room("train", departing_plan=["红", "Current"])

    assert [row["agent"] for row in result] == ["红", "克莱门莎"]
    assert data.get_train_support() == "红"
    assert (data.dorm[0].name, data.dorm[0].time) == ("", None)
    assert data.operators["艾丽妮"].current_room == ""
    assert "艾丽妮" in dorm_candidates(data).filling
    s.op_data.refresh_idle_dorm_search.assert_called_once()


def test_time_read_failure_keeps_position_mood_and_history(training_reader):
    s = training_reader
    s.read_operator_time.side_effect = RecognizeError("倒计时未识别")
    before = snapshot(s)

    with pytest.raises(RecognizeError):
        s.get_agent_from_room("train", read_time_index=[0])

    assert snapshot(s) == before
    s.history.assert_not_called()


def test_manual_training_uses_the_same_public_read_boundary(training_reader):
    s = training_reader
    config.conf.enable_mastery = False
    s.read_screen.side_effect = [""] * 6
    before = snapshot(s)

    with pytest.raises(RecognizeError):
        s.get_agent_from_room("train")

    assert snapshot(s) == before
    s.history.assert_not_called()


def test_main_page_opens_detail_once_before_observing(training_reader):
    s = training_reader
    s.train_scene.return_value = Scene.TRAIN_MAIN

    def open_detail():
        s.train_scene.return_value = Scene.INFRA_DETAILS

    s._open_check_in_detail.side_effect = open_detail

    result = s.get_agent_from_room("train")

    assert [row["agent"] for row in result] == ["艾丽妮", "克莱门莎"]
    s._open_check_in_detail.assert_called_once()
    s.turn_on_room_detail.assert_not_called()
    s.recog.update.assert_not_called()


def test_second_unknown_keeps_the_new_supports_current_dorm_and_bed(training_reader):
    s = training_reader
    data = s.op_data
    data.add(Operator("红", "", current_room="dormitory_1", current_index=2, mood=16))
    data.dorm[0].name = "红"
    data.dorm[0].time = datetime.now() + timedelta(hours=1)
    s.read_screen.side_effect = ["红", "", "", ""]
    before = snapshot(s)

    with pytest.raises(RecognizeError):
        s.get_agent_from_room("train")

    assert snapshot(s) == before
    s.op_data.update_detail.assert_not_called()
    s.op_data.refresh_idle_dorm_search.assert_not_called()
    s.history.assert_not_called()


@pytest.mark.parametrize("failure", [base.MowerExit, base.DeviceRecoveryError])
def test_interrupted_observation_propagates_without_state_changes(
    training_reader, failure
):
    s = training_reader
    interruption = failure("训练室读回中止")
    s.read_screen.side_effect = ["艾丽妮", interruption]
    before = snapshot(s)

    with pytest.raises(failure) as caught:
        s.get_agent_from_room("train")

    assert caught.value is interruption
    assert snapshot(s) == before
    s.history.assert_not_called()


def test_cached_mood_does_not_overwrite_its_original_sample(training_reader):
    s = training_reader
    op = s.op_data.operators["艾丽妮"]
    op.mood = 21
    op.depletion_rate = 1
    op.time_stamp = datetime.now() - timedelta(hours=1)
    sample_time = op.time_stamp

    result = s.get_agent_from_room("train")

    assert result[0]["mood"] == pytest.approx(20, abs=0.01)
    assert (op.mood, op.time_stamp, op.depletion_rate) == (21, sample_time, 1)
    assert s.history.call_count == 1


def test_mastery_reader_reports_unknown_without_clearing_actual_support(
    training_reader,
):
    s = training_reader
    s.read_screen.side_effect = [""] * 6
    before = snapshot(s)

    result = mastery_reader._read_slots_checked(s)

    assert result == ("", "", [], False)
    assert snapshot(s) == before
    s.history.assert_not_called()
    s.op_data.refresh_idle_dorm_search.assert_not_called()
    s.tap.assert_called_once_with(((1, 1), (2, 2)), interval=0.5)
    assert s.train_scene() == Scene.TRAIN_MAIN


def test_navigation_failure_does_not_invalidate_a_committed_observation(
    training_reader, monkeypatch
):
    s = training_reader
    old_time = s.last_train_mood_read
    monkeypatch.setattr(
        mastery_reader,
        "_close_room_detail",
        MagicMock(side_effect=RecognizeError("关闭详情失败")),
    )

    with pytest.raises(RecognizeError):
        mastery_reader._read_slots_checked(s)

    assert s.op_data.get_current_room("train", True) == ["艾丽妮", "克莱门莎"]
    assert s.last_train_mood_read > old_time
    assert s.history.call_count == 2
