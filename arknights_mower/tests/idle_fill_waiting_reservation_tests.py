"""空床补位、执行重验和候选选人均遵守仍在等待的换班预约。"""

import pickle
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import initial_bed_waiting_reservation_tests as initial
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    try_add_release_dorm,
)

solver = initial.solver
isolated_agent_history = initial.isolated_agent_history
waiting_destination = initial.waiting_destination
pytestmark = pytest.mark.usefixtures("offline_maintenance")


def prepare_idle_operator(data, name="梓兰"):
    op = data.operators[name]
    assert not op.current_room
    op.mood, op.time_stamp = 12, datetime.now()


def assert_available_bed_is_used(plan):
    row = plan.get("dormitory_2", ["Current"] * 5)
    assert row[0] == "Current"
    assert "梓兰" in row[1:4]


@pytest.mark.parametrize("target_source", ["plan", "expected"])
@pytest.mark.parametrize("restore", [False, True])
def test_initial_idle_fill_uses_other_beds_without_taking_waiting_target(
    waiting_destination,
):
    scheduler, data, protected = waiting_destination
    prepare_idle_operator(data)
    before, positions = pickle.dumps(protected), initial.native_positions(data)

    assert scheduler._fill_empty_dorms(primary_planned=True)

    fills = [task for task in scheduler.tasks if task.type == TaskTypes.FILL_DORM]
    assert len(fills) == 1
    assert_available_bed_is_used(fills[0].plan)
    assert pickle.dumps(protected) == before
    assert initial.native_positions(data) == positions


@pytest.mark.parametrize("target_source", ["plan", "expected"])
@pytest.mark.parametrize("restore", [False, True])
def test_idle_fill_execution_revalidation_preserves_waiting_target(
    waiting_destination,
):
    scheduler, data, protected = waiting_destination
    prepare_idle_operator(data)
    names, slots, _, _ = scheduler._dorm_recovery_reservations([])
    try_add_release_dorm(
        {},
        None,
        data,
        scheduler.tasks,
        empty_only=True,
        reserved_names=names,
        reserved_slots=slots,
    )
    assert len(scheduler.tasks) == 1
    task = scheduler.tasks[0]
    scheduler.task = task
    assert_available_bed_is_used(task.plan)
    before, positions, at = (
        pickle.dumps(protected),
        initial.native_positions(data),
        task.time,
    )
    scheduler._track_idle_dorm_shift = MagicMock()
    scheduler._finish_idle_dorm_shift = MagicMock()
    scheduler.preserve_resting_crafters = MagicMock()

    class SelectedRoom(Exception):
        pass

    # 保留完整执行前重验，停在实际房间操作边界，避免接触设备。
    scheduler.agent_arrange_room = MagicMock(side_effect=SelectedRoom)
    with pytest.raises(SelectedRoom):
        scheduler.agent_arrange(task.plan)

    assert_available_bed_is_used(task.plan)
    assert task.time == at
    assert pickle.dumps(protected) == before
    assert initial.native_positions(data) == positions
    scheduler.enter_room.assert_not_called()


@pytest.mark.parametrize("target_source", ["plan", "expected"])
@pytest.mark.parametrize("restore", [False, True])
def test_free_candidates_leave_waiting_named_idle_operator_available_to_its_task(
    waiting_destination, target_source
):
    scheduler, data, protected = waiting_destination
    prepare_idle_operator(data, "红")
    prepare_idle_operator(data)
    if target_source == "plan":
        protected.plan["dormitory_2"][0] = "红"
    else:
        protected.group_shift_expected = {("dormitory_2", 0): "红"}
    selected = SchedulerTask(
        task_type=TaskTypes.FILL_DORM,
        task_plan={"dormitory_2": ["Current", "Free", *["Current"] * 3]},
    )
    scheduler.tasks, scheduler.task = [selected], selected
    before, positions = pickle.dumps(protected), initial.native_positions(data)

    candidates = scheduler.get_dorm_candidates(room="dormitory_2")

    assert "红" not in candidates.recovering
    assert "红" not in candidates.filling
    assert "梓兰" in candidates.recovering
    assert pickle.dumps(protected) == before
    assert initial.native_positions(data) == positions


@pytest.mark.parametrize("target_source", ["plan", "expected"])
@pytest.mark.parametrize("restore", [False, True])
def test_waiting_retarget_and_release_refresh_departure_observation_without_actual_change(
    waiting_destination, target_source
):
    scheduler, data, protected = waiting_destination
    positions = initial.native_positions(data)
    names = ["伊内丝", "银灰", "讯使"]
    before = scheduler._departure_recovery_signature(names)
    assert scheduler._departure_recovery_signature(names) == before
    if target_source == "plan":
        protected.plan["dormitory_2"][:2] = ["Current", "克洛丝"]
    else:
        protected.group_shift_expected = {("dormitory_2", 1): "克洛丝"}

    retargeted = scheduler._departure_recovery_signature(names)

    assert retargeted != before
    assert scheduler._departure_recovery_signature(names) == retargeted
    scheduler.waiting_group_shifts.clear()
    released = scheduler._departure_recovery_signature(names)
    assert released != retargeted
    assert scheduler._departure_recovery_signature(names) == released
    assert initial.native_positions(data) == positions
