"""远期跑单允许空闲恢复，执行和原班恢复继续保护预约。"""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import dorm_empty_release_tests
from arknights_mower.utils.dorm_candidates import dorm_task_reservations
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    try_add_release_dorm,
)

pytestmark = pytest.mark.usefixtures("offline_maintenance")

op_data = dorm_empty_release_tests.op_data
solver = dorm_empty_release_tests.solver
ROOM = dorm_empty_release_tests.ROOM


@pytest.fixture
def recovery(solver):
    instance, selected = solver
    data = instance.op_data
    data._projection_now = datetime.now()
    data.operators["红"].current_room = "meeting"
    return instance, selected


def add_order(instance, name="但书", *, hours=8):
    data = instance.op_data
    data.add(Operator(name, "", mood=5, time_stamp=data._projection_now))
    order = SchedulerTask(
        time=data._projection_now + timedelta(hours=hours),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_1": ["Current", name, "Current"]},
        meta_data="room_1_1",
    )
    instance.tasks = [order]
    return order


@pytest.mark.parametrize("name", ["但书", "龙舌兰", "佩佩", "可露希尔"])
@pytest.mark.parametrize("hours", [1, 8])
@pytest.mark.parametrize("vacant", [False, True])
def test_future_order_allows_planned_recovery_and_free_selection(
    recovery, name, hours, vacant
):
    instance, selected = recovery
    if vacant:
        data = instance.op_data
        data.operators["空爆"].current_room = "meeting"
        data.dorm[0].name, data.dorm[0].time = "", None
        selected.pop()
    order = add_order(instance, name, hours=hours)
    original = deepcopy(order.__dict__)

    for _ in range(3):
        assert name in instance.get_dorm_candidates().recovering
        tasks = [order]
        try_add_release_dorm({}, None, instance.op_data, tasks)
        assert [task.plan for task in tasks if task is not order] == [
            {ROOM: ["Current"] * 4 + [name]}
        ]
        assert tasks.count(order) == 1
        assert order.__dict__ == original

    plan = instance.task.plan[ROOM]
    instance.choose_agent(plan, ROOM)
    assert plan[-1] == name
    assert selected == plan
    assert instance.tasks == [order]
    assert order.__dict__ == original


@pytest.mark.parametrize("reading", ["card", "unknown"])
def test_future_order_does_not_hide_candidates_without_measured_mood(recovery, reading):
    instance, _ = recovery
    add_order(instance)
    data = instance.op_data
    data.operators["但书"].time_stamp = None
    if reading == "card":
        data.dorm_mood_estimates["但书"] = (5, data._projection_now)

    candidates = instance.get_dorm_candidates()

    assert "但书" in candidates.unknown
    assert ("但书" in candidates.estimated_recovering) == (reading == "card")


@pytest.mark.parametrize(
    "protection",
    [
        "due",
        "retained",
        "failure",
        "original",
        "emergency_original",
        "restore",
        "confirmation",
        "submitted",
        "unnamed",
    ],
)
def test_due_or_started_order_keeps_recovery_reservation(recovery, protection):
    instance, _ = recovery
    order = add_order(instance)
    if protection == "due":
        order.time = instance.op_data._projection_now
    elif protection == "retained":
        order.execution_retained = True
    elif protection == "failure":
        order.execution_failure = {"reason": "换人未确认"}
    elif protection == "original":
        order.run_order_original_roster = {"room_1_1": ["银灰"]}
    elif protection == "emergency_original":
        order.emergency_original_roster = {"room_1_1": ["银灰"]}
    elif protection == "restore":
        order.run_order_restore_pending = True
    elif protection in ("confirmation", "submitted"):
        order.run_order_confirmation_pending = {
            "submitted": protection == "submitted",
            "target": ["但书"],
        }
    else:
        order.meta_data = ""

    assert "但书" not in instance.get_dorm_candidates().filling
    assert "但书" in dorm_task_reservations(instance.op_data, [order])[0]


def test_other_task_and_explicit_exclusions_still_reserve_same_operator(recovery):
    instance, _ = recovery
    order = add_order(instance)
    assert "但书" not in instance.get_dorm_candidates(["但书"]).filling
    staffing = SchedulerTask(
        time=order.time,
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": ["但书"]},
    )
    instance.tasks.append(staffing)
    assert "但书" not in instance.get_dorm_candidates().filling
    instance.tasks.remove(staffing)
    instance.op_data.config.free_blacklist.append("但书")
    assert "但书" not in instance.get_dorm_candidates().filling


def test_recovery_permission_ends_at_existing_order_deadline(recovery):
    instance, _ = recovery
    order = add_order(instance)
    original = deepcopy(order.__dict__)
    instance.op_data._projection_now = order.time - timedelta(seconds=1)
    instance.op_data.operators["但书"].time_stamp = instance.op_data._projection_now
    assert "但书" in instance.get_dorm_candidates().recovering
    instance.op_data._projection_now = order.time
    assert "但书" not in instance.get_dorm_candidates().filling
    assert order.__dict__ == original


def test_workshop_still_respects_future_order_working_assignment(recovery):
    from arknights_mower.utils.workshop_limits import workshop_operator_block_reason

    instance, _ = recovery
    order = add_order(instance)
    reason = workshop_operator_block_reason(instance.op_data, "但书", [order])
    assert reason is not None
    assert reason.code == "operator_reserved"
    assert "但书" in instance.get_dorm_candidates().recovering


def test_order_execution_and_compensation_release_only_after_completion(recovery):
    instance, _ = recovery
    order = add_order(instance)
    data = instance.op_data
    original_time = order.time
    original_plan = deepcopy(order.plan)
    assert "但书" in instance.get_dorm_candidates().recovering

    order.run_order_original_roster = {"room_1_1": ["银灰"]}
    data.operators["但书"].current_room = "room_1_1"
    assert "但书" not in instance.get_dorm_candidates().filling
    order.run_order_restore_pending = True
    data.operators["但书"].current_room = ""
    assert "但书" not in instance.get_dorm_candidates().filling
    assert order.time == original_time
    assert order.plan == original_plan

    instance.tasks.remove(order)
    assert "但书" in instance.get_dorm_candidates().recovering
