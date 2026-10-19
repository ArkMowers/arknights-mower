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


def test_gap_wait_does_not_reappear_after_confirmed_return_and_temporary_regroup(
    resting, monkeypatch
):
    from arknights_mower.solvers import record
    from arknights_mower.utils.group_recovery import group_recovery_deadline

    solver, now = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    returns(data)
    assert "讯使" in data.group_recovery_full_members["联动"]
    monkeypatch.setattr(record, "save_agent_action", lambda *a, **kw: None)
    member = data.operators["讯使"]
    data.update_detail(member.name, 14.09, member.room, member.index, True)
    # 临时副表改变组别并设为工作狂，随后离岗，再恢复原表。
    member.group, member.workaholic = "临时", True
    member.current_room, member.current_index = "", -1
    member.group, member.workaholic = "联动", False
    required, due = group_recovery_deadline(data, "联动", now=now)
    assert "讯使" not in required
    assert set(required) == {"伊内丝", "银灰"}
    assert due == now + timedelta(hours=3)
    # 显式回满仍独立生效，不能随旧组等待一起取消。
    member.rest_in_full = True
    assert "讯使" in group_recovery_deadline(data, "联动", now=now)[0]


def test_empty_gap_wait_does_not_add_idle_members_again(resting):
    from arknights_mower.utils.group_recovery import group_recovery_deadline

    solver, now = resting
    data = solver.op_data
    data.group_recovery_full_members["联动"] = []
    for name in ("伊内丝", "银灰", "讯使"):
        data.get_dorm_by_name(name)[1].reset()
        member = data.operators[name]
        member.current_room, member.current_index = "", -1
    assert group_recovery_deadline(data, "联动", now=now) == ([], None)


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


def test_wait_cap_shortens_only_gap_wait(resting):
    solver, now = resting
    data = solver.op_data
    data.operators["伊内丝"].rest_in_full = True
    config.conf.group_rest_in_full_on_mood_gap = True
    config.conf.group_mood_gap_max_extra_wait_hours = 0.5
    assert returns(data)[0].time == now + timedelta(hours=1, minutes=22)


def test_wait_cap_never_shortens_explicit_full_recovery(resting):
    solver, now = resting
    data = solver.op_data
    data.operators["讯使"].rest_in_full = True
    config.conf.group_rest_in_full_on_mood_gap = True
    config.conf.group_mood_gap_max_extra_wait_hours = 0.5
    assert returns(data)[0].time == now + timedelta(hours=5)


@pytest.mark.parametrize("max_wait", [0, 10])
def test_full_recovery_before_cap_returns_without_waiting_for_cap(resting, max_wait):
    solver, now = resting
    config.conf.group_rest_in_full_on_mood_gap = True
    config.conf.group_mood_gap_max_extra_wait_hours = max_wait
    assert returns(solver.op_data)[0].time == now + timedelta(hours=5)


def test_wait_cap_keeps_original_anchor_after_replanning_and_release(resting):
    solver, now = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    config.conf.group_mood_gap_max_extra_wait_hours = 0.5
    expected = now + timedelta(hours=1, minutes=22)
    assert returns(data)[0].time == expected
    release_observed(data, "伊内丝")
    data.get_dorm_by_name("银灰")[1].time += timedelta(hours=2)
    assert returns(data)[0].time == expected


def test_unknown_gap_deadline_keeps_known_wait_cap(resting):
    solver, now = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    config.conf.group_mood_gap_max_extra_wait_hours = 0.5
    returns(data)
    data.get_dorm_by_name("讯使")[1].time = None
    assert returns(data)[0].time == now + timedelta(hours=1, minutes=22)
    data.operators["讯使"].rest_in_full = True
    assert returns(data) == []


@pytest.mark.parametrize("explicit", [False, True])
def test_execution_stops_gap_requirement_at_cap_but_keeps_explicit_full(
    resting, monkeypatch, explicit
):
    from arknights_mower.solvers import base_schedule

    solver, now = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    config.conf.group_mood_gap_max_extra_wait_hours = 0.5
    task = returns(data)[0]
    data.operators["讯使"].rest_in_full = explicit
    cap = now + timedelta(hours=1, minutes=22)

    class Clock(datetime):
        @classmethod
        def now(cls):
            return cap

    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(solver, "_read_recovery_rooms", lambda rooms: None)
    assert solver._verify_required_recovery(task) is not explicit
    assert data.operators["讯使"].mood == 5


def test_free_room_releases_completed_member_without_resetting_group_wait(
    resting, monkeypatch
):
    from arknights_mower.utils.scheduler_task import SchedulerTask

    solver, now = resting
    data = solver.op_data
    data.config.free_room = True
    config.conf.group_rest_in_full_on_mood_gap = True
    config.conf.group_mood_gap_max_extra_wait_hours = 0.5
    return_time = returns(data)[0].time
    op = data.operators["伊内丝"]
    op.mood, op.time_stamp, op.mood_is_prediction = 24, datetime.now(), False
    _, bed = data.get_dorm_by_name(op.name)
    bed.time = now
    tasks = plan_metadata(data, [])
    release = next(t for t in tasks if t.type == TaskTypes.RELEASE_DORM)
    target = SchedulerTask(
        time=release.time,
        task_plan=release.plan,
        task_type=TaskTypes.RELEASE_DORM,
        meta_data=op.name,
    )

    def read(rooms):
        op.time_stamp = datetime.now()

    monkeypatch.setattr(solver, "_read_recovery_rooms", read)
    assert solver._verify_required_recovery(target)
    assert solver.prepare_release_dorm(target)
    release_observed(data, op.name)
    assert returns(data)[0].time == return_time
    assert data.operators["银灰"].is_resting()
    assert data.group_is_resting("联动")


def test_early_execution_waits_for_cap_without_resetting_original_task(
    resting, monkeypatch
):
    solver, now = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    config.conf.group_mood_gap_max_extra_wait_hours = 0.5
    task = returns(data)[0]
    original_time, original_plan = task.time, dict(task.plan)
    solver.tasks = [task]

    def read(rooms):
        for op in data.operators.values():
            if op.current_room in rooms:
                op.time_stamp = datetime.now()

    monkeypatch.setattr(solver, "_read_recovery_rooms", read)
    assert not solver._verify_required_recovery(task)
    observers = [
        t for t in solver.tasks if getattr(t, "recovery_observation_rooms", None)
    ]
    assert max(t.time for t in observers) == now + timedelta(hours=1, minutes=22)
    solver._resume_waiting_group_shifts()
    solver._resume_waiting_group_shifts()
    assert task in solver.waiting_group_shifts
    assert task.time == original_time and task.plan == original_plan
    assert not getattr(task, "execution_failure", None)


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


def test_full_recovery_latch_restores_and_isolates_saved_state(resting, monkeypatch):
    solver, _ = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    returns(data)
    saved = {
        group: list(names) for group, names in data.group_recovery_full_members.items()
    }
    from arknights_mower import __main__ as main
    from arknights_mower.solvers.record import current_state

    for attr in (
        "daily_visit_friend",
        "daily_report",
        "daily_skland",
        "daily_mail",
        "task_count",
    ):
        setattr(solver, attr, None)
    monkeypatch.setattr(main, "base_scheduler", solver)
    snapshot = current_state()
    anchors = snapshot["group_recovery_return_time"]
    assert anchors == data.group_recovery_return_time
    data.restore_group_shift_state({"联动": True}, saved, anchors)
    assert data.group_recovery_return_time == anchors
    projected = data.project_arrangements([])
    projected.commit_group_shifts({"联动": False})
    assert data.group_recovery_return_time == anchors
    data.group_recovery_full_members["联动"].remove("伊内丝")
    assert "伊内丝" in saved["联动"]
    data.restore_group_shift_state({"联动": False}, saved, anchors)
    assert data.group_recovery_full_members == {}
    assert data.group_recovery_return_time == {}


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


@pytest.mark.parametrize(
    "exclusions, delayed",
    [(["联动"], False), (["其他组", "联动"], False), (["其他组"], True)],
)
def test_gap_exclusions_apply_only_to_named_groups(resting, exclusions, delayed):
    solver, now = resting
    config.conf.group_rest_in_full_on_mood_gap = True
    config.conf.group_mood_gap_exclusions = exclusions
    expected = timedelta(hours=5) if delayed else timedelta(minutes=52)
    assert returns(solver.op_data)[0].time == now + expected


def test_excluding_latched_group_clears_only_its_wait_and_can_be_removed(resting):
    solver, now = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    assert returns(data)[0].time == now + timedelta(hours=5)
    data.group_recovery_full_members["其他组"] = ["其他成员"]
    data.group_recovery_return_time["其他组"] = now
    config.conf.group_mood_gap_exclusions = ["联动"]
    assert returns(data)[0].time == now + timedelta(minutes=52)
    assert "联动" not in data.group_recovery_full_members
    assert "联动" not in data.group_recovery_return_time
    assert data.group_recovery_full_members == {"其他组": ["其他成员"]}
    assert data.group_recovery_return_time == {"其他组": now}
    config.conf.group_mood_gap_exclusions = []
    assert returns(data)[0].time == now + timedelta(hours=5)


def test_excluded_group_still_waits_for_explicit_full_recovery(resting):
    solver, now = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    config.conf.group_mood_gap_exclusions = ["联动"]
    data.operators["讯使"].rest_in_full = True
    assert returns(data)[0].time == now + timedelta(hours=5)
    data.get_dorm_by_name("讯使")[1].time = None
    assert returns(data) == []


@pytest.mark.parametrize("explicit", [False, True])
def test_saved_return_respects_exclusion_and_explicit_full(
    resting, monkeypatch, explicit
):
    solver, _ = resting
    data = solver.op_data
    config.conf.group_rest_in_full_on_mood_gap = True
    task = returns(data)[0]
    config.conf.group_mood_gap_exclusions = ["联动"]
    data.operators["讯使"].rest_in_full = explicit
    monkeypatch.setattr(solver, "_read_recovery_rooms", lambda rooms: None)
    assert solver._verify_required_recovery(task) is not explicit
