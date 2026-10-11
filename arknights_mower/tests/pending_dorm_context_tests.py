"""已开始换班的恢复记录跨调度任务、空闲轮次和读房保持有效。"""

from datetime import datetime, timedelta
from threading import Event
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.dorm_group_tests import solver as solver
from arknights_mower.tests.dorm_state_restore_tests import (
    recovery_snapshot as recovery_snapshot,
)
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import SchedulerTask


def prepare_scheduler_entry(instance, monkeypatch):
    monkeypatch.setattr(config, "maintenance_recheck", Event())
    for name in (
        "handle_error",
        "_emergency_filter_tasks",
        "_schedule_maintenance_backup_check",
        "_sync_run_order_tasks",
        "_resume_waiting_group_shifts",
        "_fill_empty_dorms",
        "backup_plan_solver",
        "queue_product_switches",
    ):
        monkeypatch.setattr(instance, name, MagicMock())
    monkeypatch.setattr(instance, "_product_switching_enabled", lambda: True)
    monkeypatch.setattr(base_schedule, "save_log", MagicMock())
    monkeypatch.setattr(base_schedule.SceneGraphSolver, "run", MagicMock())
    for attr in ("party_time", "free_clue", "credit_fight"):
        setattr(instance, attr, None)


@pytest.mark.parametrize(
    "dispatch", ["pending", "intervening", "competing_shift", "idle"]
)
def test_scheduler_entry_retains_started_shift_recovery(
    recovery_snapshot, monkeypatch, offline_maintenance, dispatch
):
    instance, pending, incoming, due = recovery_snapshot
    pending.time = datetime.now() + timedelta(minutes=10)
    intervening = SchedulerTask(time=datetime.now() - timedelta(seconds=1))
    if dispatch == "pending":
        pending.time = intervening.time
    elif dispatch in ("intervening", "competing_shift"):
        if dispatch == "competing_shift":
            intervening.plan = {"meeting": ["伊内丝", "银灰"]}
            intervening.group_shift_transitions = {
                group: not resting
                for group, resting in pending.group_shift_transitions.items()
            }
        instance.tasks.insert(0, intervening)
    prepare_scheduler_entry(instance, monkeypatch)
    confirmed = dict(instance.op_data.group_shift_state)
    instance.run()
    assert (
        instance.task
        is {
            "pending": pending,
            "intervening": intervening,
            "competing_shift": intervening,
            "idle": None,
        }[dispatch]
    )
    assert instance.op_data.group_shift_state == confirmed
    if dispatch == "competing_shift":
        with pytest.raises(base_schedule.ProductSwitchDeferred):
            instance._prepare_group_shift(intervening)
    pending.plan.clear()
    assert instance._complete_group_shift(pending)
    bed = instance.op_data.get_dorm_by_name(incoming)[1]
    assert (bed.name, bed.time) == (incoming, due)


@pytest.mark.parametrize("current", ["intervening", "idle"])
@pytest.mark.parametrize("read_indexes", [None, [0]])
@pytest.mark.parametrize("cached", [False, True])
def test_room_observation_uses_started_queue_context(
    recovery_snapshot, monkeypatch, current, read_indexes, cached
):
    instance, pending, incoming, due = recovery_snapshot
    instance.task = SchedulerTask() if current == "intervening" else None
    data = instance.op_data
    confirmed = dict(data.group_shift_state)
    if not cached:
        for bed in data.all_dorms():
            bed.reset()
    instance.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
    instance.find = MagicMock(return_value=None)
    for name in (
        "refresh_facility_state",
        "turn_on_room_detail",
        "wait_product_complete",
        "scroll_room_operators",
    ):
        monkeypatch.setattr(instance, name, MagicMock())
    names = [incoming, "冰酿", "泥岩", "能天使", "年"]
    instance.read_screen = MagicMock(side_effect=names)
    instance.read_accurate_mood = MagicMock(return_value=5)
    instance.read_operator_time = MagicMock(return_value=due)
    instance.get_agent_from_room("dormitory_1", read_indexes)
    assert data.group_shift_state == confirmed
    pending.plan.clear()
    assert instance._complete_group_shift(pending)
    bed = data.get_dorm_by_name(incoming)[1]
    assert bed is not None and (bed.name, bed.time) == (incoming, due)


@pytest.mark.parametrize("source", ["future", "removed", "waiting"])
def test_unstarted_or_removed_shift_cannot_supply_queue_context(
    recovery_snapshot, source
):
    instance, pending, _, _ = recovery_snapshot
    if source == "future":
        pending.group_shift_expected = {}
    else:
        instance.tasks.clear()
        if source == "waiting":
            instance.waiting_group_shifts = [pending]
    instance.task = None
    assert instance._execution_group_transitions() == {}


def test_current_explicit_return_overrides_started_queue_context(recovery_snapshot):
    instance, pending, _, _ = recovery_snapshot
    row = ["伊内丝", "银灰"]
    current = SchedulerTask(task_plan={"meeting": row})
    instance.task = current
    context = instance._execution_group_transitions()
    assert context["联动"] is False
    assert context["另一组"] is False
    assert pending.group_shift_expected
    assert instance.op_data.group_is_resting("联动") is False


def test_suspending_another_shift_retains_started_recovery(
    recovery_snapshot, monkeypatch
):
    instance, pending, incoming, due = recovery_snapshot
    other = SchedulerTask(task_plan={"meeting": ["伊内丝", "银灰"]})
    instance.task = other
    instance.tasks.insert(0, other)
    monkeypatch.setattr(instance, "_refresh_deferred_product_reservations", MagicMock())
    instance._suspend_group_shift(other, {"另一组"})
    assert instance.tasks == [pending]
    assert instance.waiting_group_shifts == [other]
    pending.plan.clear()
    assert instance._complete_group_shift(pending)
    bed = instance.op_data.get_dorm_by_name(incoming)[1]
    assert (bed.name, bed.time) == (incoming, due)
