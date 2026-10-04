"""救急恢复使用具体宿舍轮换，不创建周期心情复查任务。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import emergency
from arknights_mower.tests.automatic_rescue_tests import (  # noqa: F401
    make_episode,
    offline,
)
from arknights_mower.tests.mass_mood_recovery_tests import (
    NOW,
    PRIMARY,
    solver,  # noqa: F401
)
from arknights_mower.utils import operators
from arknights_mower.utils.dorm_candidates import dorm_task_reservations
from arknights_mower.utils.workshop_limits import workshop_operator_block_reason


@pytest.fixture
def rotation(solver, monkeypatch):  # noqa: F811
    state = make_episode(solver)
    name = PRIMARY[0]
    state["targets"] = {name: 16}
    op = solver.op_data.operators[name]
    op._current_room, op.current_index = "dormitory_1", 2
    op.mood, op.time_stamp = 8, NOW
    bed = next(
        bed for bed in solver.op_data.all_dorms() if bed.position == ("dormitory_1", 2)
    )
    bed.name, bed.time = name, NOW + timedelta(hours=4)
    clock = {"now": NOW}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"]

    monkeypatch.setattr(emergency, "datetime", Clock)
    monkeypatch.setattr(operators, "datetime", Clock)
    solver._emergency_update_targets = MagicMock()
    solver._emergency_ready = MagicMock(return_value=False)
    solver._emergency_collect = MagicMock()
    solver._emergency_schedule_staffing = MagicMock(return_value=True)
    solver._open_emergency_beds = MagicMock()
    solver._emergency_plan_beds = MagicMock()
    solver.agent_arrange = MagicMock()
    return solver, op, bed, clock


def test_countdown_schedules_target_instead_of_full_mood_or_periodic_poll(rotation):
    scheduler, op, bed, clock = rotation
    scheduler._emergency_replan_releases()
    (task,) = scheduler.tasks
    assert task.time == NOW + timedelta(hours=2)
    assert task.emergency_recovery_release
    assert task.plan == {
        "dormitory_1": ["Current", "Current", "Free", "Current", "Current"]
    }
    assert task.time < bed.time
    assert task.meta_data == op.name
    scheduler.agent_arrange.assert_not_called()


def test_no_timing_retains_normal_refresh_without_extra_task(rotation):
    scheduler, op, bed, clock = rotation
    bed.time = None
    scheduler._emergency_replan_releases()
    assert not scheduler.tasks
    scheduler._emergency_read_rooms = MagicMock()
    scheduler._emergency_tick()
    assert not scheduler.tasks
    scheduler._emergency_read_rooms.assert_not_called()
    clock["now"] += timedelta(hours=2, seconds=1)
    scheduler._emergency_tick()
    scheduler._emergency_read_rooms.assert_called_once_with(
        {"dormitory_1"}, yield_to_releases=True
    )


def test_insufficient_actual_mood_reschedules_without_departure(rotation):
    scheduler, op, bed, clock = rotation
    scheduler._emergency_replan_releases()
    clock["now"] = scheduler.tasks[0].time

    def observe(rooms, **kwargs):
        assert rooms == {"dormitory_1"}
        op.mood, op.time_stamp = 12, clock["now"]
        bed.time = clock["now"] + timedelta(hours=3)
        scheduler.emergency_state.pop("pending_read_rooms", None)
        return True

    scheduler._emergency_read_rooms = MagicMock(side_effect=observe)
    scheduler._emergency_tick()
    scheduler.agent_arrange.assert_not_called()
    (task,) = scheduler.tasks
    assert task.emergency_recovery_release
    assert task.time == clock["now"] + timedelta(hours=1)
    assert not scheduler.emergency_state.get("ready_members")


def test_measured_target_releases_then_plans_new_resident(rotation):
    scheduler, op, bed, clock = rotation
    scheduler._emergency_replan_releases()
    clock["now"] = scheduler.tasks[0].time

    def observe(rooms, **kwargs):
        op.mood, op.time_stamp = 16, clock["now"]
        scheduler.emergency_state.pop("pending_read_rooms", None)
        return True

    def arrange(plan, **kwargs):
        assert plan["dormitory_1"][2] == ""
        op._current_room, op.current_index = "", -1
        bed.reset()

    scheduler._emergency_read_rooms = MagicMock(side_effect=observe)
    scheduler.agent_arrange.side_effect = arrange
    scheduler._emergency_tick()
    scheduler.agent_arrange.assert_called_once()
    assert op.name in scheduler.emergency_state["ready_members"]
    assert op.name in dorm_task_reservations(scheduler.op_data, [])[0]
    assert (
        workshop_operator_block_reason(scheduler.op_data, op.name, [])
        == "已被自动救急恢复安排预约"
    )
    assert (
        sum(
            call.args[0] is scheduler.emergency_state
            for call in scheduler._emergency_plan_beds.call_args_list
        )
        == 1
    )
    assert not scheduler.tasks


def test_changed_resident_does_not_execute_obsolete_release(rotation):
    scheduler, op, bed, clock = rotation
    scheduler._emergency_replan_releases()
    clock["now"] = scheduler.tasks[0].time
    op._current_room, op.current_index = op.room, op.index
    bed.name = PRIMARY[1]
    scheduler._emergency_read_rooms = MagicMock(return_value=True)
    scheduler._emergency_tick()
    scheduler.agent_arrange.assert_not_called()
    assert bed.name == PRIMARY[1]
    assert not scheduler.tasks


def test_target_above_upper_limit_does_not_schedule_false_completion(rotation):
    scheduler, op, bed, clock = rotation
    scheduler.emergency_state["targets"][op.name] = op.upper_limit + 1
    scheduler._emergency_replan_releases()
    assert not scheduler.tasks


def test_recovery_target_uses_personal_upper_countdown_without_changing_limits(
    rotation,
):
    scheduler, op, bed, clock = rotation
    op.lower_limit, op.upper_limit = 2, 12
    scheduler.emergency_state["targets"][op.name] = 10
    scheduler._emergency_replan_releases()
    (task,) = scheduler.tasks
    assert task.time == NOW + timedelta(hours=2)
    assert (op.lower_limit, op.upper_limit) == (2, 12)
    assert task.mood_limit == 10


def test_equal_personal_upper_uses_existing_mandatory_release_only(rotation):
    scheduler, op, bed, clock = rotation
    scheduler.op_data.config.operator_mood_limits = {op.name: {"lower": 0, "upper": 16}}
    scheduler.op_data.init_mood_limit()
    scheduler._emergency_replan_releases()
    (task,) = scheduler.tasks
    assert task.strict_mood_limit
    assert task.mood_limit == 16
    assert not getattr(task, "emergency_recovery_release", False)


@pytest.fixture
def merged_rotation(rotation):
    from arknights_mower.utils.operators import Dormitory
    from arknights_mower.utils.plan import Room

    scheduler, op, bed, clock = rotation
    data = scheduler.op_data
    data.plan["dormitory_2"] = [Room("Free", "", []) for _ in range(5)]
    for name, room, index, seconds, target in (
        (PRIMARY[1], "dormitory_1", 3, 21, 12),
        (PRIMARY[2], "dormitory_2", 2, 141, 18),
    ):
        member = data.operators[name]
        member._current_room, member.current_index = room, index
        member.mood, member.time_stamp = 8, NOW
        scheduler.emergency_state["targets"][name] = target
        full_time = NOW + timedelta(seconds=(7200 + seconds) * 16 / (target - 8))
        existing = next(
            (b for b in data.all_dorms() if b.position == (room, index)), None
        )
        if existing is None:
            data.dorm.append(Dormitory((room, index), name, full_time))
        else:
            existing.name, existing.time = name, full_time
    return rotation


def test_rescue_queue_merges_same_dorm_and_aligns_other_dorms(merged_rotation):
    scheduler, op, bed, clock = merged_rotation
    scheduler._emergency_replan_releases()
    assert len(scheduler.tasks) == 2
    assert {task.time for task in scheduler.tasks} == {NOW + timedelta(seconds=7341)}
    first = next(task for task in scheduler.tasks if "dormitory_1" in task.plan)
    assert first.plan["dormitory_1"].count("Free") == 2
    assert first.release_dorm_targets() == {
        PRIMARY[0]: ("dormitory_1", 2),
        PRIMARY[1]: ("dormitory_1", 3),
    }
    assert all(task.emergency_recovery_release for task in scheduler.tasks)
    assert scheduler.emergency_state["targets"] == {
        PRIMARY[0]: 16,
        PRIMARY[1]: 12,
        PRIMARY[2]: 18,
    }
    snapshot = [
        (task.time, task.plan.copy(), task.release_dorm_targets())
        for task in scheduler.tasks
    ]
    scheduler._emergency_replan_releases()
    assert [
        (task.time, task.plan, task.release_dorm_targets()) for task in scheduler.tasks
    ] == snapshot


@pytest.mark.parametrize("kind", ["RUN_ORDER", "FIAMMETTA", "WORKSHOP"])
def test_rescue_merge_does_not_cross_specialized_task(merged_rotation, kind):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    scheduler, op, bed, clock = merged_rotation
    barrier = SchedulerTask(
        time=NOW + timedelta(seconds=7210), task_type=getattr(TaskTypes, kind)
    )
    scheduler.tasks.append(barrier)
    scheduler._emergency_replan_releases()
    first = next(task for task in scheduler.tasks if task.meta_data == PRIMARY[0])
    assert first.time == NOW + timedelta(hours=2)
    assert barrier.time == NOW + timedelta(seconds=7210)
    assert len(scheduler.tasks) == 4


def test_rescue_queue_obeys_disabled_merge_interval(merged_rotation, monkeypatch):
    from arknights_mower.utils import config

    scheduler, op, bed, clock = merged_rotation
    monkeypatch.setattr(config.conf, "merge_interval", 0)
    scheduler._emergency_replan_releases()
    assert len(scheduler.tasks) == 3
    assert len({task.time for task in scheduler.tasks}) == 3


def test_merged_rescue_reads_all_due_rooms_and_keeps_unready_member(merged_rotation):
    scheduler, op, bed, clock = merged_rotation
    scheduler._emergency_replan_releases()
    clock["now"] = scheduler.tasks[0].time

    def observe(rooms, **kwargs):
        assert rooms == {"dormitory_1", "dormitory_2"}
        for name, mood in zip(PRIMARY, [16, 11, 18]):
            member = scheduler.op_data.operators[name]
            member.mood, member.time_stamp = mood, clock["now"]
        scheduler.emergency_state.pop("pending_read_rooms", None)
        return True

    def arrange(plan, **kwargs):
        scheduler.op_data = scheduler.op_data.project_arrangements([plan])
        plan.clear()

    scheduler._emergency_read_rooms = MagicMock(side_effect=observe)
    scheduler.agent_arrange.side_effect = arrange
    scheduler._emergency_tick()
    scheduler.agent_arrange.assert_called_once()
    assert scheduler.op_data.operators[PRIMARY[1]].is_resting()
    assert not scheduler.op_data.operators[PRIMARY[0]].is_resting()
    assert not scheduler.op_data.operators[PRIMARY[2]].is_resting()
    assert PRIMARY[1] not in scheduler.emergency_state["ready_members"]
