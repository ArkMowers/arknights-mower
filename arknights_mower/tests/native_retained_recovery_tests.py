"""失败预演的附带宿舍动作不占有其他组的正常回班。"""

import copy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import dorm_release_tests, mass_mood_recovery_tests
from arknights_mower.tests.resting_priority_tests import set_tier
from arknights_mower.utils.dorm_candidates import retained_task_reservations
from arknights_mower.utils.plan import Room
from arknights_mower.utils.resting_priority import RestingTier
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

op_data = dorm_release_tests.op_data
native_solver = mass_mood_recovery_tests.solver
ROOM = "dormitory_1"


@pytest.fixture
def retained(op_data):
    data = op_data
    data.plan["contact"] = [
        Room("伊内丝", "乙组", ["陈"]),
        Room("讯使", "乙组", ["黑角"]),
    ]
    data.groups["乙组"] = ["伊内丝", "讯使"]
    for index, (name, tier) in enumerate(
        (("伊内丝", RestingTier.MAIN), ("讯使", RestingTier.STANDBY))
    ):
        op = set_tier(data, name, tier, 24)
        op.room, op.index, op.group = "contact", index, "乙组"
        op.current_room, op.current_index = ROOM, index + 3
        op.mood_is_prediction = False
    data.plan["meeting"][0].group = "甲组"
    data.operators["银灰"].group = "甲组"
    data.groups["甲组"] = ["银灰"]
    task = SchedulerTask(
        time=datetime.now() - timedelta(hours=2),
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["红"],
            ROOM: ["Current", "Current", "银灰", "Current", "讯使"],
        },
    )
    task.execution_failure = {
        "snapshot": {
            "observations": {
                name: (op.current_room, op.current_index, op.time_stamp)
                for name, op in data.operators.items()
            }
        }
    }
    return data, task


def observed_return(data, *names):
    for name in names:
        op = data.operators[name]
        op.current_room, op.current_index = op.room, op.index
        op.mood_is_prediction = False
        op.time_stamp = datetime.now()


def test_incidental_reservations_release_only_requested_return(retained):
    data, task = retained
    before = copy.deepcopy(task.plan)
    held_names, held_slots = retained_task_reservations(data, [task])
    assert {"伊内丝", "讯使"} <= held_names
    names, slots = retained_task_reservations(data, [task], returning_groups={"乙组"})
    assert not {"伊内丝", "讯使"} & names
    assert not {(ROOM, 3), (ROOM, 4), ("contact", 0), ("contact", 1)} & slots
    assert "红" in names and ("meeting", 0) in slots
    assert task.plan == before
    assert (ROOM, 3) in held_slots


@pytest.mark.parametrize(
    "protection", ["primary", "explicit", "active", "product", "restore", "resumed"]
)
@pytest.mark.parametrize("primary", [False, True])
def test_normal_return_does_not_release_explicit_or_active_work(
    retained, protection, primary
):
    data, task = retained
    if primary:
        set_tier(data, "讯使", RestingTier.MAIN, 24)
    if protection == "primary":
        task.plan["contact"] = ["陈", "Current"]
    elif protection == "explicit":
        task.backup_explicit_slots = {(ROOM, 4)}
    elif protection == "active":
        task.backup_shift_active = True
    elif protection == "product":
        task.product_shift_locked = True
    elif protection == "restore":
        task.dorm_recovery_restore = [ROOM]
    else:
        del task.execution_failure
        task.execution_retained = True
    assert retained_task_reservations(
        data, [task], returning_groups={"乙组"}
    ) == retained_task_reservations(data, [task])


def test_another_tasks_explicit_group_reservation_survives_release(retained):
    data, incidental = retained
    explicit = copy.deepcopy(incidental)
    explicit.plan["contact"] = ["陈", "Current"]
    names, slots = retained_task_reservations(
        data, [incidental, explicit], returning_groups={"乙组"}
    )
    assert {"伊内丝", "讯使"} <= names
    assert ("contact", 0) in slots


def test_reconcile_waits_for_actual_complete_return_and_preserves_task(retained):
    from arknights_mower.utils.retained_recovery import reconcile_retained_recovery

    data, task = retained
    task.backup_shift_intent = copy.deepcopy(task.plan)
    task.dorm_fill_plan = {ROOM: ["Current", "Current", "Current", "Current", "讯使"]}
    before, time, failure = copy.deepcopy(task.plan), task.time, task.execution_failure
    assert reconcile_retained_recovery(data, task) == set()
    observed_return(data, "讯使")
    assert reconcile_retained_recovery(data, task) == set()
    observed_return(data, "伊内丝")
    data.operators["伊内丝"].mood_is_prediction = True
    assert reconcile_retained_recovery(data, task) == set()
    data.operators["伊内丝"].mood_is_prediction = False
    assert reconcile_retained_recovery(data, task) == {"乙组"}
    assert task.time is time and task.execution_failure is failure
    assert task.plan["meeting"] == before["meeting"]
    assert task.plan[ROOM] == ["Current", "Current", "银灰", "Current", "Current"]
    assert task.backup_shift_intent[ROOM][4] == "Current"
    assert task.dorm_fill_plan == {}
    assert reconcile_retained_recovery(data, task) == {"乙组"}


def test_original_intent_allows_cleanup_of_speculative_group_additions(retained):
    from arknights_mower.utils.retained_recovery import (
        reconcile_retained_recovery,
        retained_recovery_may_return,
    )

    data, task = retained
    task.backup_shift_intent = copy.deepcopy(task.plan)
    task.plan["contact"] = ["伊内丝", "讯使"]
    task.plan[ROOM][4] = "伊内丝"
    assert retained_recovery_may_return(data, task, "乙组")
    observed_return(data, "伊内丝", "讯使")
    reconcile_retained_recovery(data, task)
    assert task.plan[ROOM][4] == "Current"
    assert task.plan["contact"] == ["伊内丝", "讯使"]


def test_multigroup_explicit_intent_is_not_incidental(retained):
    from arknights_mower.utils.retained_recovery import retained_recovery_may_return

    data, task = retained
    follower = data.operators["讯使"]
    follower.group = "丙组"
    follower.group_bindings = [
        {"group": "乙组", "replacement": ["黑角"]},
        {"group": "丙组", "replacement": ["黑角"]},
    ]
    task.backup_explicit_slots = {(ROOM, 4)}
    assert not retained_recovery_may_return(data, task, "乙组")


def test_every_primary_anchor_must_be_observed_working(retained):
    from arknights_mower.utils.retained_recovery import reconcile_retained_recovery

    data, task = retained
    primary = set_tier(data, "能天使", RestingTier.MAIN, 24)
    primary.room, primary.index, primary.group = "contact", 2, "乙组"
    primary.current_room, primary.current_index = ROOM, 2
    data.plan["contact"].append(Room("能天使", "乙组", []))
    data.groups["乙组"].append("能天使")
    task.execution_failure["snapshot"]["observations"]["能天使"] = (
        ROOM,
        2,
        primary.time_stamp,
    )
    observed_return(data, "伊内丝", "讯使")
    before = copy.deepcopy(task.plan)
    assert reconcile_retained_recovery(data, task) == set()
    assert task.plan == before
    observed_return(data, "能天使")
    assert reconcile_retained_recovery(data, task) == {"乙组"}


def test_reconcile_keeps_unrelated_explicit_vacancies(retained):
    from arknights_mower.utils.retained_recovery import reconcile_retained_recovery

    data, task = retained
    task.plan["dormitory_2"] = ["", "Current", "Current", "Current", "Current"]
    task.plan[ROOM][3] = ""
    observed_return(data, "伊内丝", "讯使")
    reconcile_retained_recovery(data, task)
    assert task.plan["dormitory_2"][0] == ""
    assert task.plan[ROOM][3] == ""


def test_explicit_release_target_remains_reserved(retained):
    from arknights_mower.utils.retained_recovery import retained_recovery_may_return

    data, task = retained
    task.type = TaskTypes.RELEASE_DORM
    task.release_targets = {"讯使": (ROOM, 4)}
    task.plan[ROOM][4] = "Free"
    assert not retained_recovery_may_return(data, task, "乙组")


@pytest.mark.parametrize("exhausted", [False, True])
def test_primary_bed_move_releases_return_and_is_pruned_after_observation(
    retained, exhausted
):
    from arknights_mower.utils.retained_recovery import reconcile_retained_recovery

    data, task = retained
    primary = set_tier(data, "讯使", RestingTier.MAIN, 24)
    primary.exhaust_require = exhausted
    primary.rest_in_full = exhausted
    task.backup_shift_intent = copy.deepcopy(task.plan)
    task.dorm_fill_plan = {ROOM: ["Current"] * 4 + ["讯使"]}
    task.group_shift_expected = {(ROOM, 4): "讯使", ("meeting", 0): "红"}
    task.group_shift_transitions = {"甲组": True, "乙组": True}
    before, time, failure = copy.deepcopy(task.plan), task.time, task.execution_failure
    for _ in range(3):
        assert reconcile_retained_recovery(data, task) == set()
        assert task.plan == before
    names, slots = retained_task_reservations(data, [task], returning_groups={"乙组"})
    assert not {"伊内丝", "讯使"} & names
    assert not {(ROOM, 3), (ROOM, 4), ("contact", 0), ("contact", 1)} & slots
    observed_return(data, "伊内丝", "讯使")
    assert reconcile_retained_recovery(data, task) == {"乙组"}
    assert task.plan[ROOM] == ["Current", "Current", "银灰", "Current", "Current"]
    assert task.backup_shift_intent[ROOM][4] == "Current"
    assert task.dorm_fill_plan == {}
    assert task.group_shift_expected == {("meeting", 0): "红"}
    assert task.group_shift_transitions == {"甲组": True}
    assert task.plan["meeting"] == ["红"]
    assert task.time is time and task.execution_failure is failure


@pytest.mark.parametrize("exhausted", [False, True])
def test_scheduler_resume_prunes_a_returned_primary_without_replacing_task(
    retained, native_solver, exhausted
):
    from arknights_mower.utils.scheduler_task import find_next_task

    data, task = retained
    primary = set_tier(data, "讯使", RestingTier.MAIN, 24)
    primary.exhaust_require = exhausted
    primary.rest_in_full = exhausted
    native_solver.op_data = data
    independent = SchedulerTask(datetime.now(), task_type=TaskTypes.WORKSHOP)
    native_solver.tasks, native_solver.task = [task, independent], None
    native_solver._retain_failed_task(task, "替班冲突", list(task.plan))
    time, before = task.time, copy.deepcopy(task.plan)
    for _ in range(3):
        native_solver._resume_failed_tasks()
        assert task.execution_failure
        assert task.plan == before
        assert find_next_task(native_solver.tasks) is independent
    observed_return(data, "伊内丝", "讯使")
    native_solver._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert any(pending is task for pending in native_solver.tasks)
    assert task.time is time
    assert task.plan[ROOM][4] == "Current"
    assert task.plan["meeting"] == ["红"]


@pytest.fixture
def occupied_admission_bed(op_data):
    data = op_data
    now = datetime.now()
    primary = data.operators["银灰"]
    primary.current_room, primary.current_index = ROOM, 4
    primary.mood, primary.time_stamp, primary.depletion_rate = 24, now, 0
    primary.mood_is_prediction = False
    data.operators["空爆"].current_room = ""
    data.operators["空爆"].current_index = -1
    data.operators["红"].current_room, data.operators["红"].current_index = "meeting", 0
    data.dorm[0].name = primary.name
    data.dorm[0].time = now - timedelta(minutes=1)
    failed = SchedulerTask(
        time=now - timedelta(hours=1),
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={ROOM: ["Current"] * 4 + ["空爆"]},
    )
    failed.execution_failure = {"reason": "等待床位", "snapshot": {}}
    return data, failed, now


def individual_returns(tasks):
    return [
        task
        for task in tasks
        if task.type == TaskTypes.SHIFT_ON and task.plan.get("meeting") == ["银灰"]
    ]


def test_completed_request_does_not_consume_an_equal_started_arrangement(
    native_solver, occupied_admission_bed
):
    data, completed, _ = occupied_admission_bed
    completed.ordinary_coordination = True
    completed.coordination_request_names = ["银灰"]
    started = copy.deepcopy(completed)
    started.group_shift_expected = {(ROOM, 4): "空爆"}
    assert started == completed
    native_solver.op_data = data
    native_solver.tasks = [started, completed]
    native_solver._retain_failed_task(started, "未完成的进驻确认", [ROOM])
    native_solver._retain_failed_task(completed, "等待床位", [ROOM])
    native_solver._resume_failed_tasks()
    assert any(task is started for task in native_solver.tasks)
    assert not any(task is completed for task in native_solver.tasks)


def test_ungrouped_recovered_primary_returns_before_a_waiting_bed_admission(
    occupied_admission_bed,
):
    from arknights_mower.utils.scheduler_task import plan_metadata

    data, failed, now = occupied_admission_bed
    original_plan, original_time = copy.deepcopy(failed.plan), failed.time
    for _ in range(3):
        planned = plan_metadata(data, [failed], now=now)
        assert individual_returns(planned)
        assert any(t is failed for t in planned)
        assert failed.plan == original_plan
        assert failed.time == original_time
        assert data.operators["银灰"].current_room == ROOM


@pytest.mark.parametrize(
    "protection",
    [
        "started",
        "backup",
        "product",
        "restore",
        "own-work",
        "own-work-empty",
        "named-rest",
        "resumed",
    ],
)
def test_individual_return_keeps_real_retained_obligations(
    occupied_admission_bed, protection
):
    from arknights_mower.utils.scheduler_task import plan_metadata

    data, failed, now = occupied_admission_bed
    if protection == "started":
        failed.group_shift_expected = {(ROOM, 4): "空爆"}
    elif protection == "backup":
        failed.backup_shift_active = True
    elif protection == "product":
        failed.product_shift_locked = True
    elif protection == "restore":
        failed.dorm_recovery_restore = [ROOM]
    elif protection == "own-work":
        failed.plan["meeting"] = ["红"]
    elif protection == "own-work-empty":
        failed.plan["meeting"] = [""]
    elif protection == "named-rest":
        failed.plan[ROOM][4] = "银灰"
    else:
        del failed.execution_failure
        failed.execution_retained = True
    planned = plan_metadata(data, [failed], now=now)
    assert not individual_returns(planned)
    assert any(task is failed for task in planned)


def test_waiting_bed_does_not_change_the_individual_recovery_deadline(
    occupied_admission_bed,
):
    from arknights_mower.utils.scheduler_task import plan_metadata

    data, failed, now = occupied_admission_bed
    data.operators["银灰"].mood = 8
    due = data.dorm[0].time = now + timedelta(hours=4)
    for _ in range(3):
        planned = plan_metadata(data, [failed], now=now)
        assert individual_returns(planned)[0].time == due - timedelta(minutes=8)
        assert data.operators["银灰"].current_room == ROOM


def test_individual_bed_return_respects_another_tasks_working_slot(
    occupied_admission_bed,
):
    from arknights_mower.utils.scheduler_task import plan_metadata

    data, failed, now = occupied_admission_bed
    other = SchedulerTask(
        time=now, task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["红"]}
    )
    other.execution_failure = {"reason": "实际岗位预约", "snapshot": {}}
    assert not individual_returns(plan_metadata(data, [failed, other], now=now))


@pytest.mark.parametrize(
    "guard", [None, "started", "support", "explicit", "not-resting"]
)
def test_completed_ordinary_request_releases_only_observed_finished_work(
    native_solver, occupied_admission_bed, guard
):
    data, failed, now = occupied_admission_bed
    solver = native_solver
    solver.op_data = data
    failed.ordinary_coordination = True
    failed.coordination_request_names = ["银灰"]
    if guard == "started":
        failed.group_shift_expected = {(ROOM, 4): "空爆"}
    elif guard == "support":
        failed.exhaust_support = True
    elif guard == "explicit":
        failed.backup_explicit_slots = {(ROOM, 4)}
    elif guard == "not-resting":
        data.operators["银灰"].current_room = "meeting"
        data.operators["银灰"].current_index = 0
    other = SchedulerTask(time=now, task_type=TaskTypes.SKILL_UPGRADE)
    solver.tasks = [failed, other]
    solver._retain_failed_task(failed, "等待床位", [ROOM])
    original_plan, original_time = copy.deepcopy(failed.plan), failed.time
    for _ in range(3):
        solver._resume_failed_tasks()
        assert any(task is failed for task in solver.tasks) is (guard is not None)
        assert any(task is other for task in solver.tasks)
        assert failed.plan == original_plan
        assert failed.time == original_time


@pytest.mark.parametrize("unfinished", [False, True])
def test_completed_request_uses_requested_group_not_shared_working_binding(
    native_solver, retained, unfinished
):
    data, failed = retained
    follower = data.operators["讯使"]
    follower.resting_priority = "high"
    follower.group, follower.shift_group = "甲组", "甲组"
    follower.group_bindings = [
        {"group": "甲组", "replacement": ["黑角"]},
        {"group": "乙组", "replacement": ["伊内丝"]},
    ]
    follower.current_room, follower.current_index = "contact", 1
    observed_return(data, "银灰")
    data.operators["伊内丝"].replacement = ["讯使"]
    if unfinished:
        observed_return(data, "伊内丝")
    failed.ordinary_coordination = True
    failed.coordination_request_names = ["伊内丝"]
    assert data.shift_request_groups(failed.coordination_request_names) == ["乙组"]
    solver = native_solver
    solver.op_data, solver.tasks = data, [failed]
    other = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
    solver.tasks.append(other)
    solver._retain_failed_task(failed, "等待床位", [ROOM])
    plan, time = copy.deepcopy(failed.plan), failed.time
    for _ in range(3):
        solver._resume_failed_tasks()
        assert any(task is failed for task in solver.tasks) is unfinished
        assert any(task is other for task in solver.tasks)
        assert failed.plan == plan and failed.time == time
        assert follower.current_room == "contact"


@pytest.mark.parametrize("forced", [None, "exhausted", "full"])
def test_completed_request_allows_optional_idle_standby(
    native_solver, retained, forced
):
    data, failed = retained
    standby = data.operators["讯使"]
    standby.current_room, standby.current_index = "", -1
    if forced == "exhausted":
        standby.exhaust_require = True
    elif forced == "full":
        data.config.rest_in_full.append(standby.name)
    failed.ordinary_coordination = True
    failed.coordination_request_names = ["伊内丝"]
    solver = native_solver
    solver.op_data, solver.tasks = data, [failed]
    other = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
    solver.tasks.append(other)
    solver._retain_failed_task(failed, "等待床位", [ROOM])
    plan, time = copy.deepcopy(failed.plan), failed.time
    for _ in range(3):
        solver._resume_failed_tasks()
        assert any(task is failed for task in solver.tasks) is (forced is not None)
        assert any(task is other for task in solver.tasks)
        assert failed.plan == plan and failed.time == time


@pytest.mark.parametrize("working", [False, True])
def test_completed_independent_request_still_requires_its_own_admission(
    native_solver, occupied_admission_bed, working
):
    data, failed, _ = occupied_admission_bed
    op = data.operators["银灰"]
    op.group_bindings = [
        {"group": "", "replacement": ["红"]},
        {"group": "甲组", "replacement": ["空爆"]},
    ]
    assert op.independent_rest
    if working:
        observed_return(data, op.name)
    failed.ordinary_coordination = True
    failed.coordination_request_names = [op.name]
    solver = native_solver
    solver.op_data, solver.tasks = data, [failed]
    solver._retain_failed_task(failed, "等待床位", [ROOM])
    for _ in range(3):
        solver._resume_failed_tasks()
        assert any(task is failed for task in solver.tasks) is working
