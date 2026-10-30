"""上限离宿复用整组回班，保留清退期限及受阻任务。"""

import pickle
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import native_recovery_execution_tests as native
from arknights_mower.utils import config
from arknights_mower.utils.group_recovery import mood_limit_group_return
from arknights_mower.utils.scheduler_task import TaskTypes, plan_metadata

solver = native.solver
resting = native.resting
pytestmark = pytest.mark.usefixtures("offline_maintenance", "income_db")


@pytest.fixture
def cap_return(resting, monkeypatch):
    scheduler, _ = resting
    data = scheduler.op_data
    now = datetime.now()
    data.config.operator_mood_limits["伊内丝"] = {"lower": 0, "upper": 12}
    data.operators["伊内丝"].upper_limit = 12
    for name in ("伊内丝", "银灰", "讯使"):
        op = data.operators[name]
        op.mood, op.time_stamp = (11.95 if name == "伊内丝" else 21), now
        data.get_dorm_by_name(name)[1].time = now + timedelta(minutes=20)
    data.operators["伊内丝"].resting_priority = "low"
    data.get_dorm_by_name("伊内丝")[1].time = now + timedelta(seconds=60)
    tasks = plan_metadata(data, [], now=now)
    release = next(t for t in tasks if getattr(t, "strict_mood_limit", False))
    release.mood_limit_deadline = release.time
    release.time = now - timedelta(seconds=1)
    returning = next(t for t in tasks if t.type == TaskTypes.SHIFT_ON)
    scheduler.tasks, scheduler.task = tasks, release
    native.prepare_dispatch(scheduler, monkeypatch)
    return scheduler, release, returning, now


def test_cap_dispatch_returns_whole_group_without_changing_return_timestamp(cap_return):
    scheduler, release, returning, _ = cap_return
    at = returning.time
    assert at > datetime.now()
    scheduler.infra_main()
    assert scheduler.agent_arrange.call_count == 1
    assert scheduler.op_data.operators["伊内丝"].current_room == "meeting"
    assert scheduler.op_data.operators["银灰"].current_room == "meeting"
    assert scheduler.op_data.operators["讯使"].current_room == "contact"
    assert not scheduler.op_data.group_is_resting("联动")
    assert returning.time == at
    assert release.mood_limit_deadline > release.time


@pytest.mark.parametrize("evidence", ["bed", "unknown", "newer", "predicted"])
def test_return_threshold_counts_elapsed_recovery_without_rewriting_observations(
    cap_return, evidence
):
    scheduler, release, ordinary, now = cap_return
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.mood, op.time_stamp, op.depletion_rate = 10, now - timedelta(hours=1), 1
    bed = data.get_dorm_by_name(op.name)[1]
    bed.time = now + timedelta(minutes=5)
    if evidence == "unknown":
        bed.time = None
    elif evidence == "newer":
        data.dorm_mood_estimates[op.name] = (5, now)
    elif evidence == "predicted":
        op.mood_is_prediction = True
    original = op.mood, op.time_stamp, op.depletion_rate, bed.time, ordinary.time
    candidate = mood_limit_group_return(data, release, scheduler.tasks, now=now)
    assert (candidate is not None) == (evidence == "bed")
    assert (
        op.mood,
        op.time_stamp,
        op.depletion_rate,
        bed.time,
        ordinary.time,
    ) == original


def test_cap_dispatch_uses_recovery_since_last_observation(cap_return):
    scheduler, _, _, now = cap_return
    data = scheduler.op_data
    op = data.operators["讯使"]
    op.mood, op.time_stamp, op.depletion_rate = 10, now - timedelta(hours=1), 1
    data.get_dorm_by_name(op.name)[1].time = now + timedelta(minutes=5)
    scheduler.infra_main()
    assert data.operators["伊内丝"].current_room == "meeting"
    assert scheduler.op_data.operators["讯使"].current_room == "contact"


@pytest.mark.parametrize(
    "kind", ["gap", "explicit", "threshold", "identity", "started", "reserved", "late"]
)
def test_required_wait_or_unsafe_return_keeps_individual_release(cap_return, kind):
    scheduler, release, returning, now = cap_return
    data = scheduler.op_data
    if kind == "gap":
        data.group_recovery_full_members["联动"] = ["伊内丝", "银灰", "讯使"]
    elif kind == "explicit":
        data.operators["讯使"].rest_in_full = True
    elif kind == "threshold":
        data.operators["讯使"].mood = 5
    elif kind == "identity":
        data.operators["伊内丝"].current_index += 1
    elif kind == "started":
        returning.mood_physical_started = True
    elif kind == "reserved":
        returning.backup_explicit_slots = {("meeting", 0)}
    else:
        release.mood_limit_deadline = now + timedelta(seconds=10)
    original = deepcopy(returning.plan), returning.time
    assert mood_limit_group_return(data, release, scheduler.tasks, now=now) is None
    assert (returning.plan, returning.time) == original
    assert release in scheduler.tasks


def test_failed_attempt_does_not_repeat_after_replan_or_restart(cap_return):
    scheduler, release, returning, now = cap_return
    deadline, at = release.mood_limit_deadline, returning.time
    assert (
        mood_limit_group_return(scheduler.op_data, release, scheduler.tasks, now=now)
        is not None
    )
    assert (
        mood_limit_group_return(scheduler.op_data, release, scheduler.tasks, now=now)
        is None
    )
    scheduler.tasks = plan_metadata(scheduler.op_data, scheduler.tasks, now=now)
    assert (
        next(t for t in scheduler.tasks if getattr(t, "strict_mood_limit", False))
        is release
    )
    restored = pickle.loads(pickle.dumps(release))
    assert (
        mood_limit_group_return(scheduler.op_data, restored, scheduler.tasks, now=now)
        is None
    )
    assert release.mood_limit_deadline == deadline
    assert returning.time == at


def test_full_wait_still_dispatches_individual_departure(cap_return):
    scheduler, release, _, _ = cap_return
    scheduler.op_data.operators["讯使"].rest_in_full = True
    scheduler.infra_main()
    assert release.mood_limit_deadline > release.time
    assert scheduler.op_data.operators["讯使"].is_resting()
    assert scheduler.op_data.group_is_resting("联动")


@pytest.mark.parametrize("explicit", [False, True])
def test_calculated_confirmation_keeps_explicit_full_recovery(
    cap_return, monkeypatch, explicit
):
    from arknights_mower.solvers.base_schedule import MoodArrangementChanged
    from arknights_mower.utils import calculated_mood

    scheduler, release, _, now = cap_return
    data = scheduler.op_data
    returning = mood_limit_group_return(data, release, scheduler.tasks, now=now)
    assert returning is not None
    scheduler.task = returning
    config.conf.test_mood_calculation = True
    monkeypatch.setattr(calculated_mood, "sync_model", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        data, "calculated_mood", lambda name, *_: data.operators[name].mood
    )
    monkeypatch.setattr(data, "replacement_exhausted", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        data,
        "calculated_mood_deadline",
        lambda name, *args, **kwargs: data.get_dorm_by_name(name)[1].time,
    )
    data.operators["伊内丝"].rest_in_full = explicit
    if explicit:
        with pytest.raises(MoodArrangementChanged):
            scheduler._validate_calculated_arrangement()
    else:
        scheduler._validate_calculated_arrangement()


def test_blocked_dispatch_retains_return_and_runs_original_release(
    cap_return, monkeypatch
):
    from arknights_mower.solvers.base_schedule import GroupShiftBlocked

    scheduler, release, _, now = cap_return
    deadline = release.mood_limit_deadline
    original_prepare = scheduler._prepare_shift_cycle
    monkeypatch.setattr(
        scheduler,
        "_prepare_shift_cycle",
        lambda task: (_ for _ in ()).throw(GroupShiftBlocked({"联动"})),
    )
    scheduler.infra_main()
    assert len(scheduler.waiting_group_shifts) == 1
    suspended = scheduler.waiting_group_shifts[0]
    at = suspended.time
    scheduler.agent_arrange.assert_not_called()
    for _ in range(3):
        assert (
            mood_limit_group_return(
                scheduler.op_data, release, scheduler.tasks, now=now
            )
            is None
        )
    monkeypatch.setattr(scheduler, "_prepare_shift_cycle", original_prepare)
    scheduler.task = release
    scheduler.infra_main()
    assert scheduler.agent_arrange.call_count == 1
    assert scheduler.waiting_group_shifts == [suspended]
    assert suspended.time == at
    assert release.mood_limit_deadline == deadline
    scheduler.op_data.group_shift_state["联动"] = False
    scheduler._resume_waiting_group_shifts()
    assert any(t is suspended for t in scheduler.tasks)
    assert suspended.time == at


def test_cap_return_does_not_advance_other_merged_targets(cap_return):
    scheduler, release, ordinary, now = cap_return
    ordinary.plan["factory"] = ["泥岩"]
    original, at = deepcopy(ordinary.plan), ordinary.time
    candidate = mood_limit_group_return(
        scheduler.op_data, release, scheduler.tasks, now=now
    )
    assert candidate is not None
    assert "factory" not in candidate.plan
    assert ordinary.plan == original
    assert ordinary.time == at


def test_retained_slot_reservation_keeps_cap_departure(cap_return):
    from arknights_mower.utils.scheduler_task import SchedulerTask

    scheduler, release, ordinary, now = cap_return
    retained = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={"contact": ["红"]}
    )
    retained.execution_retained = True
    scheduler.tasks.append(retained)
    assert (
        mood_limit_group_return(scheduler.op_data, release, scheduler.tasks, now=now)
        is None
    )
    assert not getattr(release, "mood_limit_return_attempted", False)
    assert retained in scheduler.tasks
    assert ordinary in scheduler.tasks
