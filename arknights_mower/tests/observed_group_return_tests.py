"""Observed working groups restore their dormitory members through confirmed tasks."""

# ruff: noqa: E402

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    config.conf.enable_mastery = False
    instance = object.__new__(BaseSchedulerSolver)
    instance.global_plan = {
        "default_plan": Plan(
            {
                "central": [
                    Room("森蚺", "自动化", ["夕"]),
                    Room("令", "感知", ["重岳"]),
                ],
                "meeting": [Room("绮良", "自动化", ["能天使"])],
                "dormitory_2": [
                    Room("流明", "自动化", ["妮芙"]),
                    Room("冰酿", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
                "dormitory_3": [
                    Room("塑心", "感知", ["妮芙"]),
                    Room("闪灵", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            PlanConfig("", "", ""),
        ),
        "backup_plans": [],
    }
    assert instance.initialize_operators() is None
    instance.tasks = []
    instance.task = None
    instance.waiting_group_shifts = []
    instance.find_next_task = MagicMock(return_value=None)
    instance._read_agent_mood = MagicMock()
    instance._suppress_train_correction = lambda plan: None
    instance.enter_room = MagicMock(side_effect=AssertionError("device access"))
    for op in instance.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    instance.op_data.operators["流明"]._current_room = ""
    instance.op_data.operators["流明"].current_index = -1
    instance.op_data.operators["妮芙"]._current_room = "dormitory_2"
    instance.op_data.operators["妮芙"].current_index = 0
    instance.op_data.commit_group_shifts({"自动化": True, "感知": False})
    return instance


def test_observed_return_restores_manager_and_releases_shared_cover(solver):
    data = solver.op_data
    data.operators["令"].mood = 0
    data.operators["绮良"].mood = 5
    assert solver.agent_get_mood() == "self_correction"
    task = solver.tasks[-1]
    assert task.plan["dormitory_2"][0] == "流明"
    assert data.group_is_resting("自动化")
    assert data.is_dorm_replacement("妮芙")

    solver.task = task
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    solver._prepare_group_shift(task, remember_targets=True)
    assert task.group_shift_transitions["自动化"] is False
    assert task.group_shift_transitions["感知"] is True
    assert task.plan["dormitory_2"][0] == "流明"
    assert task.plan["dormitory_3"][0] == "妮芙"
    assert "绮良" not in task.group_shift_expected.values()
    assert not solver._complete_group_shift(task)
    assert data.group_is_resting("自动化")

    solver.op_data = data.project_arrangements([task.plan])
    # Room readback changes occupancy; only completion confirms live group state.
    solver.op_data.group_shift_state = dict(data.group_shift_state)
    assert solver._complete_group_shift(task)
    assert not solver.op_data.group_is_resting("自动化")
    assert solver.op_data.group_is_resting("感知")
    assert solver.op_data.get_current_operator("dormitory_2", 0).name == "流明"
    assert solver.op_data.get_current_operator("dormitory_3", 0).name == "妮芙"


@pytest.mark.parametrize("location", ["", "dormitory_2", "room_1_1"])
def test_partial_or_misplaced_group_does_not_authorize_return(solver, location):
    solver.op_data.operators["绮良"]._current_room = location
    assert solver._observed_group_return_plan() == {}
    assert solver.op_data.group_is_resting("自动化")


def test_wrong_slot_does_not_authorize_return(solver):
    solver.op_data.operators["森蚺"].current_index = 1
    assert solver._observed_group_return_plan() == {}


def test_due_fiammetta_preserves_group_state(solver):
    solver.tasks = [SchedulerTask(task_type=TaskTypes.FIAMMETTA)]
    assert solver._observed_group_return_plan() == {}
    assert solver.op_data.group_is_resting("自动化")


def test_unknown_position_reading_does_not_authorize_return(solver):
    solver.op_data.operators["森蚺"].time_stamp = None
    assert solver._observed_group_return_plan() == {}


@pytest.mark.parametrize("source", ["task", "tasks", "waiting_group_shifts"])
@pytest.mark.parametrize(
    "protection",
    ["group_shift_expected", "backup_shift_active", "dorm_recovery_restore"],
)
def test_unfinished_arrangement_preserves_group_state(solver, source, protection):
    pending = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"meeting": ["能天使"]},
    )
    setattr(
        pending,
        protection,
        {("meeting", 0): "能天使"} if protection == "group_shift_expected" else True,
    )
    setattr(solver, source, pending if source == "task" else [pending])
    assert solver._observed_group_return_plan() == {}
    assert solver.op_data.group_is_resting("自动化")


def test_cached_projection_does_not_infer_observed_return(solver):
    assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
    assert solver.op_data.group_is_resting("自动化")


@pytest.mark.parametrize("guard", ["_initial_mood_read_pending", "_emergency_frozen"])
def test_guarded_observation_does_not_authorize_return(solver, monkeypatch, guard):
    monkeypatch.setattr(solver, guard, lambda: True)
    assert solver._observed_group_return_plan() == {}


def test_incomplete_observation_does_not_generate_return(solver):
    solver._read_agent_mood.return_value = False
    assert solver.agent_get_mood() is None
    assert solver.tasks == []
    assert solver.op_data.group_is_resting("自动化")


def test_read_only_plan_does_not_infer_return(solver):
    assert solver.agent_get_mood(return_plan=True) == {}
    assert solver.op_data.group_is_resting("自动化")


def test_workaholic_member_does_not_block_observed_return(solver):
    solver.op_data.operators["绮良"].workaholic = True
    solver.op_data.operators["绮良"]._current_room = ""
    assert solver.agent_get_mood() == "self_correction"
    assert solver.tasks[-1].plan["dormitory_2"][0] == "流明"


def test_group_without_ordinary_working_members_does_not_infer_return(solver):
    for name in ("森蚺", "绮良"):
        solver.op_data.operators[name].workaholic = True
    assert solver._observed_group_return_plan() == {}


def test_healthy_working_state_needs_no_correction(solver):
    solver.op_data.commit_group_shifts({"自动化": False})
    solver.op_data = solver.op_data.project_arrangements([{"dormitory_2": ["流明"]}])
    assert solver.agent_get_mood() is None
    assert solver.tasks == []


@pytest.mark.parametrize("promoted", [False, True])
def test_standby_member_does_not_block_fixed_anchor_return(solver, promoted):
    data = solver.op_data
    standby = data.operators["绮良"]
    standby.resting_priority = "standby"
    standby.standby_low_priority = promoted
    standby._current_room, standby.current_index = "", -1
    standby.time_stamp = None
    assert not data.is_group_shift_anchor(standby)
    assert solver._observed_group_return_plan() == {"central": ["森蚺", "Current"]}
    assert data.group_is_resting("自动化")


def test_only_working_standby_members_do_not_authorize_return(solver):
    data = solver.op_data
    data.operators["森蚺"]._current_room = ""
    data.operators["森蚺"].current_index = -1
    data.operators["绮良"].resting_priority = "standby"
    assert solver._observed_group_return_plan() == {}
    assert data.group_is_resting("自动化")
