"""本体回班遵守全组恢复要求，与收益演算使用相同的等待边界。"""

from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import dorm_group_tests as native
from arknights_mower.tests.dorm_group_tests import shift_off
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import TaskTypes, plan_metadata

solver = native.solver


@pytest.fixture
def resting(solver):
    shift_off(solver)
    data = solver.op_data
    data.commit_group_shifts({"联动": True})
    config.conf.group_rest_in_full_on_mood_gap = False
    now = datetime.now()
    for name, hours in [("伊内丝", 1), ("银灰", 3), ("讯使", 5)]:
        op = data.operators[name]
        op.mood, op.time_stamp = 5, now
        _, bed = data.get_dorm_by_name(name)
        bed.time = now + timedelta(hours=hours)
    return solver, now


def returns(data):
    return [t for t in plan_metadata(data, []) if t.type == TaskTypes.SHIFT_ON]


def test_low_priority_explicit_full_member_sets_group_deadline(resting):
    solver, now = resting
    data = solver.op_data
    data.operators["讯使"].resting_priority = "low"
    data.operators["讯使"].rest_in_full = True
    assert returns(data)[0].time == now + timedelta(hours=5)


def test_all_explicit_full_members_must_finish(resting):
    solver, now = resting
    data = solver.op_data
    for name in ("伊内丝", "银灰"):
        data.operators[name].rest_in_full = True
    assert returns(data)[0].time == now + timedelta(hours=3)


def test_explicit_full_and_gap_wait_are_cumulative_without_wait_cap(resting):
    solver, now = resting
    data = solver.op_data
    data.operators["伊内丝"].rest_in_full = True
    config.conf.group_rest_in_full_on_mood_gap = True
    config.conf.group_mood_gap_max_extra_wait_hours = 0.5
    assert returns(data)[0].time == now + timedelta(hours=5)


def test_unknown_explicit_full_deadline_blocks_group_return(resting):
    solver, _ = resting
    data = solver.op_data
    data.operators["讯使"].rest_in_full = True
    data.get_dorm_by_name("讯使")[1].time = None
    assert returns(data) == []


def test_shared_explicit_full_member_still_sets_deadline(resting):
    solver, now = resting
    data = solver.op_data
    op = data.operators["讯使"]
    op.group_bindings = [
        {"group": "联动", "replacement": ["红"]},
        {"group": "另一组", "replacement": ["红"]},
    ]
    op.rest_in_full = True
    data.group_shift_state["另一组"] = False
    assert returns(data)[0].time == now + timedelta(hours=5)


@pytest.fixture
def independent_full_member(resting):
    instance, now = resting
    data = instance.op_data
    op = data.operators["讯使"]
    op.group_bindings = [
        {"group": "", "replacement": ["红"]},
        {"group": "联动", "replacement": ["红"]},
    ]
    data.select_group_binding(op.name, "")
    op.rest_in_full = True
    return instance, now


@pytest.mark.parametrize("known_deadline", [False, True])
def test_independent_full_member_does_not_delay_bound_group(
    independent_full_member, known_deadline
):
    instance, now = independent_full_member
    data = instance.op_data
    if not known_deadline:
        data.get_dorm_by_name("讯使")[1].time = None

    tasks = returns(data)
    group_returns = [task for task in tasks if "meeting" in task.plan]
    assert len(group_returns) == 1
    assert group_returns[0].time == now + timedelta(minutes=52)
    assert group_returns[0].plan["meeting"] == ["伊内丝", "银灰"]
    assert "contact" not in group_returns[0].plan
    personal_returns = [task for task in tasks if "contact" in task.plan]
    assert len(personal_returns) == int(known_deadline)
    if known_deadline:
        assert personal_returns[0].time == now + timedelta(hours=5)
        assert personal_returns[0].plan["contact"] == ["讯使"]
    assert data.operators["讯使"].is_resting()


def test_independent_full_member_does_not_extend_latched_group_wait(
    independent_full_member,
):
    instance, now = independent_full_member
    data = instance.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    data.group_recovery_full_members["联动"] = ["伊内丝", "银灰", "讯使"]

    tasks = returns(data)
    group_return = next(task for task in tasks if "meeting" in task.plan)
    assert group_return.time == now + timedelta(hours=3)
    assert "contact" not in group_return.plan
    assert data.group_recovery_full_members["联动"] == ["伊内丝", "银灰"]
    personal_return = next(task for task in tasks if "contact" in task.plan)
    assert personal_return.time == now + timedelta(hours=5)


def test_independent_full_member_is_checked_only_for_personal_return(
    independent_full_member, monkeypatch
):
    from arknights_mower.utils.scheduler_task import SchedulerTask

    instance, now = independent_full_member
    group_return = SchedulerTask(
        time=now,
        task_plan={"meeting": ["伊内丝", "银灰"]},
        task_type=TaskTypes.SHIFT_ON,
    )
    personal_return = SchedulerTask(
        time=now,
        task_plan={"contact": ["讯使"]},
        task_type=TaskTypes.SHIFT_ON,
    )
    instance.tasks = [group_return, personal_return]
    monkeypatch.setattr(instance, "_read_recovery_rooms", lambda rooms: None)

    assert instance._verify_required_recovery(group_return)
    assert not instance._verify_required_recovery(personal_return)
    assert personal_return.time == now
    assert personal_return.plan == {"contact": ["讯使"]}
    assert personal_return.execution_failure


def test_gap_excludes_standby_member(resting):
    solver, now = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    data.operators["讯使"].resting_priority = "standby"
    data.get_dorm_by_name("银灰")[1].time = now + timedelta(hours=1.5)
    assert returns(data)[0].time == now + timedelta(hours=1, minutes=-8)


def test_gap_latch_survives_shorter_gap_and_projection(resting):
    solver, now = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    assert returns(data)[0].time == now + timedelta(hours=5)
    data.get_dorm_by_name("伊内丝")[1].time = now + timedelta(hours=4)
    data.get_dorm_by_name("银灰")[1].time = now + timedelta(hours=4.5)
    projected = data.project_arrangements([])
    projected.commit_group_shifts({"联动": False})
    assert returns(data)[0].time == now + timedelta(hours=5)
    data.commit_group_shifts({"联动": False})
    data.commit_group_shifts({"联动": True})
    assert returns(data)[0].time == now + timedelta(hours=4, minutes=-8)


def test_ordinary_return_ignores_unrelated_exhaustion(resting, monkeypatch):
    solver, now = resting
    data = solver.op_data
    from arknights_mower.utils.operators import Operator

    worker = data.operators["泥岩"]
    worker.operator_type = "high"
    worker.room = worker.current_room = "factory"
    monkeypatch.setattr(Operator, "predict_exhaust", lambda self: now)
    assert returns(data)[0].time == now + timedelta(hours=1, minutes=-8)


def release_observed(data, name):
    op = data.operators[name]
    _, bed = data.get_dorm_by_name(name)
    bed.reset()
    op.current_room, op.current_index = "", -1
    op.mood, op.time_stamp, op.depletion_rate = op.upper_limit, datetime.now(), 0
    op.mood_is_prediction = False


def test_gap_wait_survives_early_members_leaving(resting):
    solver, now = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    assert returns(data)[0].time == now + timedelta(hours=5)
    release_observed(data, "伊内丝")
    release_observed(data, "银灰")
    assert returns(data)[0].time == now + timedelta(hours=5)


def test_released_anchor_waits_for_last_shared_explicit_full_member(resting):
    solver, now = resting
    data = solver.op_data
    op = data.operators["讯使"]
    op.group_bindings = [
        {"group": "联动", "replacement": ["红"]},
        {"group": "另一组", "replacement": ["红"]},
    ]
    op.rest_in_full = True
    data.group_shift_state["另一组"] = False
    release_observed(data, "伊内丝")
    release_observed(data, "银灰")
    assert returns(data)[0].time == now + timedelta(hours=5)


def test_completed_group_keeps_return_after_last_bed_is_released(resting):
    solver, _ = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    returns(data)
    for name in ("伊内丝", "银灰", "讯使"):
        release_observed(data, name)
    tasks = returns(data)
    assert len(tasks) == 1
    assert tasks[0].plan["meeting"] == ["伊内丝", "银灰"]
    assert tasks[0].time <= datetime.now()


def test_predicted_full_does_not_confirm_required_member(resting):
    solver, _ = resting
    data = solver.op_data
    data.operators["讯使"].rest_in_full = True
    release_observed(data, "讯使")
    data.operators["讯使"].mood_is_prediction = True
    assert returns(data) == []


def test_full_recovery_latch_restores_and_isolates_saved_state(resting):
    solver, _ = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    returns(data)
    saved = {
        group: list(names) for group, names in data.group_recovery_full_members.items()
    }
    data.restore_group_shift_state({"联动": True}, saved)
    data.group_recovery_full_members["联动"].remove("伊内丝")
    assert "伊内丝" in saved["联动"]
    data.restore_group_shift_state({"联动": False}, saved)
    assert data.group_recovery_full_members == {}


@pytest.mark.parametrize("explicit", [False, True])
def test_future_recovery_return_ignores_only_incidental_failed_dorm_move(
    resting, explicit
):
    from arknights_mower.utils.scheduler_task import SchedulerTask

    solver, now = resting
    data = solver.op_data
    data.operators["讯使"].resting_priority = "standby"
    failed = SchedulerTask(
        time=now - timedelta(minutes=30),
        task_plan={
            "room_1_1": ["泥岩"],
            "dormitory_1": ["Current"] * 4 + ["讯使"],
        },
        task_type=TaskTypes.SHIFT_OFF,
    )
    failed.execution_failure = {"reason": "替班等待", "snapshot": {}}
    if explicit:
        failed.backup_explicit_slots = {("dormitory_1", 4)}
    original_time = failed.time
    tasks = plan_metadata(data, [failed])
    planned = [task for task in tasks if task.type == TaskTypes.SHIFT_ON]
    assert (len(planned) == 0) if explicit else (len(planned) == 1)
    if not explicit:
        assert planned[0].time == now + timedelta(hours=1, minutes=-8)
    assert any(task is failed for task in tasks)
    assert failed.time == original_time
    assert failed.plan["dormitory_1"][-1] == "讯使"
