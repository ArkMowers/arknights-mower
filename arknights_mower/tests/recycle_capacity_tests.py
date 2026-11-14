"""一级回收站容量不阻断其他设施的换班和崩溃恢复。"""

from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.multi_group_shift_tests import A
from arknights_mower.tests.multi_group_shift_tests import solver as solver
from arknights_mower.utils import config, crash_recovery
from arknights_mower.utils.plan import Room
from arknights_mower.utils.recognize import RecognizeError
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def recycling(solver, monkeypatch):
    plan = solver.global_plan["default_plan"].plan
    plan.pop("contact")
    plan["recycle"] = [Room("旅骨", "甲", ["芬"]), Room("迷迭香", "", ["香草"])]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    solver.task = None
    del solver._suppress_train_correction
    solver.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
    solver.turn_on_room_detail = MagicMock()
    solver.wait_product_complete = MagicMock()
    solver.find = MagicMock(return_value=None)
    solver.read_screen = MagicMock(side_effect=["旅骨", "", "", ""])
    solver.read_accurate_mood = MagicMock(return_value=20)
    solver.sleep = MagicMock()
    solver._can_refresh_idle_dorm_search = lambda: False
    solver.back = MagicMock()
    monkeypatch.setattr(base_schedule, "save_agent_action", lambda *a, **kw: None)
    return solver


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("configured", [1, 2])
def test_level_one_reader_confirms_only_existing_slot(
    recycling, strict, configured, caplog
):
    s = recycling
    if configured == 1:
        s.op_data.plan["recycle"] = s.op_data.plan["recycle"][:1]
    original = list(s.op_data.plan["recycle"])
    observed = s.get_agent_from_room(
        "recycle", force_mood=True, strict_observation=strict
    )
    assert [item["agent"] for item in observed] == ["旅骨"]
    assert s.op_data.recycle_capacity == 1
    assert s.op_data.get_current_room("recycle") == ["旅骨"]
    assert s.op_data.operators["迷迭香"].current_room == ""
    assert s.op_data.plan["recycle"] == original
    assert (getattr(s, "_recycle_unavailable", False) is True) == (configured == 2)
    assert ("一级回收站仅有一个岗位" in caplog.text) == (configured == 2)
    s.read_screen.reset_mock(side_effect=True)
    if configured == 2:
        for _ in range(3):
            s._read_room_mood("recycle", force_mood=True, strict_observation=True)
            assert s.get_agent_from_room("recycle") == []
        s.read_screen.assert_not_called()
        assert caplog.text.count("一级回收站仅有一个岗位") == 1
    else:
        s.read_screen.return_value = "旅骨"
        assert len(s.get_agent_from_room("recycle", strict_observation=True)) == 1
        s.read_screen.assert_called_once()


def test_level_two_empty_second_slot_retains_capacity(recycling):
    s = recycling
    s.find.side_effect = lambda name, **kw: (
        name == "infra_no_operator" and kw["scope"][0][1] == 344
    )
    s.read_screen.side_effect = ["旅骨"]
    observed = s.get_agent_from_room("recycle", strict_observation=True)
    assert [item["agent"] for item in observed] == ["旅骨", ""]
    assert s.op_data.get_current_room("recycle", True) == ["旅骨", ""]
    assert getattr(s, "_recycle_unavailable", False) is not True


def test_unrecognized_first_slot_still_rejects_strict_recovery(recycling):
    recycling.read_screen.side_effect = None
    recycling.read_screen.return_value = ""
    with pytest.raises(RecognizeError, match="第 1 槽位未核实"):
        recycling.get_agent_from_room("recycle", strict_observation=True)
    assert getattr(recycling, "_recycle_unavailable", False) is not True


def test_live_arrangement_skips_level_one_and_preserves_other_targets(recycling):
    s = recycling
    s.task = SchedulerTask(
        task_plan={"recycle": ["芬", "香草"], "meeting": ["陈", "Current"]}
    )
    s.enter_room = MagicMock()
    s.choose_agent = MagicMock(side_effect=AssertionError("no recycling selection"))
    original_time = s.task.time
    s.agent_arrange_room({}, "recycle", s.task.plan)
    assert s.task.plan == {"meeting": ["陈", "Current"]}
    assert s.task.time == original_time
    assert not s.tasks
    s.choose_agent.assert_not_called()
    s.enter_room.reset_mock()
    s.agent_arrange_room({}, "recycle", {"recycle": ["芬", "香草"]})
    s.enter_room.assert_not_called()


def test_unavailable_recycling_does_not_dispatch_collection_or_mood_reads(recycling):
    s = recycling
    s.get_agent_from_room("recycle", strict_observation=True)
    s.find = MagicMock(side_effect=AssertionError("no recycling lookup"))
    s.tap = MagicMock(side_effect=AssertionError("no recycling collection"))
    assert s.collect_recycling() is False
    assert s._read_recycling_operators() is None
    s._tap_recycling_collection((1, 1))
    s._initial_mood_refresh_rooms = {"recycle"}
    s._read_agent_mood()
    assert not s._initial_mood_refresh_rooms


def test_protected_recycling_occupants_cannot_be_moved_through_other_rooms(recycling):
    s = recycling
    s.get_agent_from_room("recycle", strict_observation=True)
    plan = {"dormitory_1": ["旅骨", "迷迭香", "Free"], "meeting": ["陈", "Current"]}
    s._suppress_facility_arrangement(plan)
    assert plan == {
        "dormitory_1": ["Current", "Current", "Free"],
        "meeting": ["陈", "Current"],
    }


def test_dispatch_completes_other_group_members_without_recycling_retry(
    recycling, monkeypatch
):
    s = recycling
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"meeting": ["陈", "Current"], "recycle": ["芬", "Current"]},
    )
    s.task, s.tasks = task, [task]
    s._prepare_group_shift(task, remember_targets=True)
    original_time = task.time
    s.get_agent_from_room("recycle", strict_observation=True)
    s.find = MagicMock(return_value=(1, 1))
    s.refresh_connecting = False
    s._prepare_shift_cycle = MagicMock()
    s._switch_products_before_arrangement = MagicMock()
    s.backup_plan_solver = MagicMock(return_value=False)
    s.skip = MagicMock()
    monkeypatch.setattr(base_schedule, "protect_priority_tasks", lambda *a, **kw: None)

    def arrange(plan, get_time):
        s._suppress_facility_arrangement(plan)
        assert "recycle" not in plan
        assert not {"旅骨", "迷迭香"} & {name for row in plan.values() for name in row}
        projected = s.op_data.project_arrangements([plan])
        s.op_data.operators, s.op_data.dorm = projected.operators, projected.dorm
        plan.clear()

    s.agent_arrange = MagicMock(side_effect=arrange)
    s.infra_main()
    s.agent_arrange.assert_called_once()
    assert task.time == original_time
    assert task not in s.tasks
    assert not task.group_shift_expected
    assert s.op_data.group_is_resting("甲")
    assert s.op_data.operators[A].is_resting()
    assert s.op_data.operators["旅骨"].current_room == "recycle"


def test_crash_recovery_continues_after_detecting_level_one(recycling, monkeypatch):
    from arknights_mower.solvers import record

    s = recycling
    s.enter_room = MagicMock()
    s.back_to_infrastructure = MagicMock()
    read_room_mood = s._read_room_mood
    observed = []

    def read(room, **kwargs):
        observed.append(room)
        if room == "recycle":
            return read_room_mood(room, **kwargs)

    s._read_room_mood = read
    s.op_data.plan["room_3_3"] = [Room("芬", "", [])]
    monkeypatch.setattr(config.stop_mower, "is_set", lambda: False)
    monkeypatch.setattr(record, "save_current_state", lambda: True)
    replanned = MagicMock()
    monkeypatch.setattr(crash_recovery, "replan_dynamic_tasks", replanned)
    monkeypatch.setattr(crash_recovery, "refresh_workshop_inventory", lambda _: None)
    crash_recovery.observe_scheduler(s)
    assert s._state_restore_complete
    assert observed.index("recycle") < observed.index("room_3_3")
    replanned.assert_called_once_with(s)
    s.enter_room.reset_mock()
    crash_recovery.observe_scheduler(s)
    assert "recycle" not in [call.args[0] for call in s.enter_room.call_args_list]
    assert s._state_restore_complete
    assert s.op_data.operators["旅骨"].current_room == "recycle"


def test_skipped_recycling_alone_does_not_commit_group_transition(recycling):
    s = recycling
    s.get_agent_from_room("recycle", strict_observation=True)
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"recycle": ["芬", "Current"]}
    )
    s.task, s.tasks = task, [task]
    original_time = task.time
    for _ in range(3):
        s._prepare_group_shift(task, remember_targets=True)
        assert not task.plan
        assert s._complete_group_shift(task)
        assert not s.op_data.group_is_resting("甲")
        assert task.time == original_time
        assert len(s.tasks) == 1


def test_explicit_two_operator_task_is_skipped_with_one_operator_main_plan(recycling):
    s = recycling
    s.op_data.plan["recycle"] = s.op_data.plan["recycle"][:1]
    s.get_agent_from_room("recycle", strict_observation=True)
    assert getattr(s, "_recycle_unavailable", False) is not True
    task = SchedulerTask(
        task_plan={"recycle": ["旅骨", "迷迭香"], "meeting": ["陈", "Current"]}
    )
    original_time = task.time
    s._suppress_facility_arrangement(task.plan)
    assert s._recycle_unavailable
    assert task.plan == {"meeting": ["陈", "Current"]}
    assert task.time == original_time


def test_level_one_collection_statistics_read_only_existing_slot(recycling):
    s = recycling
    s.op_data.plan["recycle"] = s.op_data.plan["recycle"][:1]
    s.get_agent_from_room("recycle", strict_observation=True)
    s.scene_graph_navigation, s.enter_room = MagicMock(), MagicMock()
    s.detect_room = MagicMock(return_value="recycle")
    s.find.side_effect = lambda name, **kw: name == "room_detail"
    s.get_color = MagicMock(return_value=np.array([255, 255, 255]))
    s.read_screen.reset_mock(side_effect=True)
    s.read_screen.return_value = "旅骨"
    assert s._read_recycling_operators() == ["旅骨"]
    s.read_screen.assert_called_once()
