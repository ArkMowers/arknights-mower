"""失败预演的附带宿舍动作不占有其他组的正常回班。"""

import copy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import dorm_release_tests
from arknights_mower.tests.resting_priority_tests import set_tier
from arknights_mower.utils.dorm_candidates import retained_task_reservations
from arknights_mower.utils.plan import Room
from arknights_mower.utils.resting_priority import RestingTier
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

op_data = dorm_release_tests.op_data
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
def test_normal_return_does_not_release_explicit_or_active_work(retained, protection):
    data, task = retained
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
