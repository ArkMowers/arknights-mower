"""副表显式岗位和原位心情核对参与完整换班预演。"""

import copy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils import config, dorm_candidates, operators
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base, "_is_mastery_busy", lambda name: False)
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    config.conf.enable_mastery = False
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = Operators(
        {
            "default_plan": Plan(
                {
                    "central": [Room("歌蕾蒂娅", "深海", ["夕"])],
                    "recycle": [Room("旅骨", "深海", ["星源"])],
                    "meeting": [Room("跃跃", "", ["虎狼丸"])],
                    "contact": [Room("令", "感知", ["重岳"])],
                    "dormitory_1": [
                        Room(
                            "撷英调香师",
                            "深海",
                            ["白面鸮"],
                            group_bindings=[
                                {"group": "感知", "replacement": ["白面鸮"]}
                            ],
                        ),
                        Room("杜林", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig("", "歌蕾蒂娅", ""),
            ),
            "backup_plans": [
                Plan(
                    {},
                    PlanConfig("", "", ""),
                    trigger=LogicExpression(
                        "op_data.operators['歌蕾蒂娅'].current_room == 'central'",
                        "and",
                        "op_data.operators['歌蕾蒂娅'].current_mood() < 10",
                    ),
                    task={"central": ["夕"]},
                )
            ],
        }
    )
    assert instance.op_data.init_and_validate() is None
    for op in instance.op_data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 24, datetime.now()
    for name in ("歌蕾蒂娅", "跃跃", "撷英调香师"):
        op = instance.op_data.operators[name]
        op._current_room, op.current_index = "", -1
    for name, room in (
        ("夕", "central"),
        ("虎狼丸", "meeting"),
        ("白面鸮", "dormitory_1"),
    ):
        op = instance.op_data.operators[name]
        op._current_room, op.current_index = room, 0
    instance.op_data.operators["歌蕾蒂娅"].mood = 0
    instance.op_data.operators["夕"].mood = 0.01
    worker = instance.op_data.operators["旅骨"]
    worker.mood, worker.time_stamp = 15, datetime.now() - timedelta(hours=3)
    instance.op_data.commit_group_shifts({"深海": True, "感知": False})
    instance.op_data.first_init = False
    instance.tasks, instance.task = [], None
    instance.find_next_task = MagicMock(return_value=None)
    instance._read_agent_mood = MagicMock()
    instance.enter_room = MagicMock(side_effect=AssertionError("device access"))
    instance._sync_run_order_tasks = MagicMock()
    return instance


def positions(data):
    return {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }


def projection_source_state(data):
    return copy.deepcopy(
        {
            "operators": {name: vars(op) for name, op in data.operators.items()},
            "dorms": [vars(bed) for bed in data.all_dorms()],
            "groups": data.groups,
            "group_shift_state": data.group_shift_state,
            "group_recovery_full_members": data.group_recovery_full_members,
            "group_recovery_return_time": data.group_recovery_return_time,
            "urgent_recovery_supporters": data.urgent_recovery_supporters,
            "recall_recovery_rates": data.recall_recovery_rates,
            "plan_condition": data.plan_condition,
            "plan": {
                room: [vars(slot) for slot in slots]
                for room, slots in data.plan.items()
            },
            "config": vars(data.config),
        }
    )


@pytest.mark.parametrize("clock_mode", ["live", "explicit", "inherited"])
def test_arrangement_projection_observations_respect_clock_scope(
    solver, monkeypatch, clock_mode
):
    class Clock(datetime):
        current = datetime(2026, 10, 1, 10)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(operators, "datetime", Clock)
    monkeypatch.setattr(dorm_candidates, "datetime", Clock)
    data = solver.op_data
    original = data.operators["旅骨"]
    original.mood, original.time_stamp, original.depletion_rate = 12, Clock.current, 0
    projected = data.project_arrangements(
        [], **({"now": Clock.current} if clock_mode != "live" else {})
    )
    if clock_mode != "explicit":
        projected = projected.project_arrangements([])
    Clock.current += timedelta(minutes=1)
    observed = projected.operators["旅骨"]
    observed.mood, observed.time_stamp = 6, Clock.current

    assert dorm_candidates.dorm_candidate_mood(projected, "旅骨") == (
        6 if clock_mode == "live" else None
    )
    assert dorm_candidates.dorm_candidate_mood(projected, "旅骨", Clock.current) == 6
    assert dorm_candidates.dorm_candidate_mood(data, "旅骨") == 12
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("unknown", [False, True], ids=["stale", "unknown"])
def test_same_post_check_preserves_resting_group_and_requested_read(solver, unknown):
    data = solver.op_data
    if unknown:
        data.operators["旅骨"].time_stamp = None
    before = positions(data), dict(data.group_shift_state)
    plan = solver.agent_get_mood(
        read_rooms=False, return_plan=True, explicit_slots={("central", 0)}
    )
    assert plan["recycle"] == ["旅骨"]
    assert "撷英调香师" not in [name for row in plan.values() for name in row]
    assert (positions(data), data.group_shift_state) == before
    solver._read_agent_mood.assert_not_called()
    solver.enter_room.assert_not_called()


def test_covered_departure_converges_without_recalling_primary(solver):
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={"meeting": ["跃跃"]})
    solver.task, solver.tasks = task, [task]
    before = projection_source_state(solver.op_data)
    solver._prepare_shift_cycle(task)
    assert task.plan["meeting"] == ["跃跃"]
    assert "central" not in task.plan
    assert task.plan.get("dormitory_1", ["Current"])[0] == "Current"
    assert not task.backup_explicit_slots
    assert "歌蕾蒂娅" in task.plan["dormitory_1"]
    assert "深海" not in task.group_shift_transitions
    assert projection_source_state(solver.op_data) == before
    assert solver.tasks == [task]
    solver.enter_room.assert_not_called()


def test_actual_primary_return_still_restores_shared_dorm_member(solver):
    data = solver.op_data
    data.operators["歌蕾蒂娅"].mood = 24
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert plan["central"] == ["歌蕾蒂娅"]
    assert plan["dormitory_1"][0] == "撷英调香师"
    assert data.arrangement_group_transitions(plan)["深海"] is False
    assert data.group_is_resting("深海")
    solver.enter_room.assert_not_called()


def test_unknown_same_post_mood_still_queues_the_room_check(solver):
    solver.op_data.operators["旅骨"].time_stamp = None
    result = solver.agent_get_mood(read_rooms=False, explicit_slots={("central", 0)})
    assert result == "self_correction"
    assert len(solver.tasks) == 1
    task = solver.tasks[0]
    assert task.type == TaskTypes.SELF_CORRECTION
    assert task.plan["recycle"] == ["旅骨"]
    assert task.plan.get("dormitory_1", ["Current"])[0] != "撷英调香师"
    assert solver.op_data.operators["旅骨"].time_stamp is None
    assert solver.op_data.group_is_resting("深海")
    solver.enter_room.assert_not_called()


def test_explicit_departure_survives_its_own_condition_deactivation(solver):
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"central": ["歌蕾蒂娅"], "dormitory_1": ["撷英调香师"]},
    )
    solver.task, solver.tasks = task, [task]
    before = projection_source_state(solver.op_data)
    solver._prepare_shift_backup(task)
    assert task.plan["central"] == ["夕"]
    assert task.plan["dormitory_1"][0] == "Current"
    assert task.backup_explicit_slots == {("central", 0), ("dormitory_1", 2)}
    assert task.plan["dormitory_1"][2] == "歌蕾蒂娅"
    assert getattr(task, "backup_shift_conditions", [False]) == [False]
    assert solver.op_data.plan_condition == [False]
    assert projection_source_state(solver.op_data) == before
    assert solver.tasks == [task]
    solver.enter_room.assert_not_called()
