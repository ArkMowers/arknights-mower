"""Protected recovery tiers retain occupied beds across planning and dispatch."""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, record
from arknights_mower.tests import dorm_release_tests, mass_mood_recovery_tests
from arknights_mower.tests.resting_priority_tests import set_tier
from arknights_mower.utils import config, mastery_db
from arknights_mower.utils.operators import Dormitory, Operator
from arknights_mower.utils.resting_priority import RestingTier
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    try_add_release_dorm,
)

ROOM = dorm_release_tests.ROOM
op_data = dorm_release_tests.op_data
group_solver = mass_mood_recovery_tests.solver
PROTECTED = (
    RestingTier.PRIORITY,
    RestingTier.MAIN,
    RestingTier.LOW_MAIN,
    RestingTier.PRIORITY_REPLACEMENT,
)


@pytest.fixture(autouse=True)
def offline_observations(monkeypatch, offline_maintenance):
    monkeypatch.setattr(record, "save_agent_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)


def selection_solver(data, task=None):
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.op_data, solver.task = data, task
    solver.tasks = [task] if task else []
    return solver


def add_standby_anchor(data, incoming):
    incoming.index, incoming.replacement = 0, ["陈"]
    data.add(Operator("陈", ""))
    cover = data.operators["陈"]
    cover.current_room, cover.current_index = "meeting", 0
    anchor = data.operators["银灰"]
    anchor.group = incoming.group
    anchor.current_room, anchor.current_index = ROOM, 3
    data.groups[incoming.group] = [anchor.name, incoming.name]
    data.plan[ROOM][3].agent = "Free"
    anchor_bed = Dormitory((ROOM, 3))
    anchor_bed.name = anchor.name
    data.dorm.append(anchor_bed)
    assert data.is_standby(incoming.name)


@pytest.mark.parametrize("tier", PROTECTED)
@pytest.mark.parametrize("reading", ["unfinished", "full", "unknown", "predicted"])
@pytest.mark.parametrize("free_room", [False, True])
@pytest.mark.parametrize("entry", ["planner", "selection"])
def test_recovery_applicants_never_evict_protected_residents(
    op_data, tier, reading, free_room, entry
):
    data = op_data
    data.config.free_room = free_room
    resident = set_tier(data, "空爆", tier, 24 if reading == "full" else 12)
    resident.group = ""
    resident.current_room, resident.current_index = ROOM, 4
    incoming = set_tier(data, "红", RestingTier.PRIORITY, 5)
    if reading == "unknown":
        resident.time_stamp = None
    elif reading == "predicted":
        resident.mood, resident.mood_is_prediction = 24, True
    bed = data.dorm[0]
    # An expired countdown cannot authorize a takeover of a protected tier.
    bed.time = datetime.now() - timedelta(minutes=1)
    before = deepcopy(vars(bed))
    tasks = []

    if entry == "planner":
        try_add_release_dorm({}, None, data, tasks)
        assert tasks == []
    else:
        row = ["Current"] * 4 + ["Free"]
        selection_solver(data).preserve_resting_crafters(row, ROOM)
        assert row[-1] == resident.name

    assert vars(bed) == before
    assert resident.is_resting()
    assert not incoming.current_room


@pytest.mark.parametrize("tier", PROTECTED)
def test_protected_priority_replacement_does_not_yield_in_rescue(op_data, tier):
    data = op_data
    resident = set_tier(data, "空爆", tier, 24)
    resident.current_room, resident.current_index = ROOM, 4
    data.rescue_mode = True
    data.emergency_dorm_agents = {resident.name}
    incoming = set_tier(data, "红", RestingTier.PRIORITY, 5)
    assert not data._slot_takable(data.dorm[0], requester=incoming.name)


@pytest.mark.parametrize(
    "requester,resident_tier",
    [
        (RestingTier.STANDBY, RestingTier.REPLACEMENT),
        (RestingTier.STANDBY, RestingTier.IDLE),
        (RestingTier.REPLACEMENT, RestingTier.IDLE),
    ],
)
@pytest.mark.parametrize("upper", [12, 20, 24])
@pytest.mark.parametrize("offset", [-0.01, 0, 0.01, None])
@pytest.mark.parametrize("resident_mood", [2, 24])
@pytest.mark.parametrize("entry", ["planner", "selection"])
def test_lower_tier_takeovers_require_ninety_percent_mood(
    op_data, requester, resident_tier, upper, offset, resident_mood, entry
):
    data = op_data
    mood = 24 if offset is None else upper * 0.9 + offset
    incoming = set_tier(data, "红", requester, mood)
    incoming.upper_limit, incoming.depletion_rate = upper, 0
    if requester == RestingTier.STANDBY:
        add_standby_anchor(data, incoming)
    if offset is None:
        incoming.time_stamp = None
    resident = set_tier(data, "空爆", resident_tier, resident_mood)
    resident.current_room, resident.current_index = ROOM, 4
    data.dorm[0].time = datetime.now() + timedelta(hours=2)
    allowed = offset is not None and offset <= 0
    bed_before = deepcopy(vars(data.dorm[0]))
    if entry == "planner":
        tasks = []
        try_add_release_dorm({}, None, data, tasks)
        assert bool(tasks) is allowed
        if allowed:
            assert incoming.name in tasks[0].plan[ROOM]
    else:
        row = ["Current"] * 4 + ["Free"]
        selection_solver(data).preserve_resting_crafters(row, ROOM)
        assert (row[-1] != resident.name) is allowed
    assert vars(data.dorm[0]) == bed_before
    assert not incoming.current_room


@pytest.mark.parametrize("entry", ["planner", "selection"])
def test_ineligible_standby_does_not_block_eligible_replacement(op_data, entry):
    data = op_data
    standby = set_tier(data, "红", RestingTier.STANDBY, 22)
    add_standby_anchor(data, standby)
    incoming = set_tier(data, "陨星", RestingTier.REPLACEMENT, 5)
    resident = data.operators["空爆"]
    resident.mood = 2
    data.dorm[0].time = datetime.now() + timedelta(hours=2)
    if entry == "planner":
        tasks = []
        try_add_release_dorm({}, None, data, tasks)
        assert len(tasks) == 1
        assert incoming.name in tasks[0].plan[ROOM]
        assert standby.name not in tasks[0].plan[ROOM]
    else:
        row = ["Current"] * 4 + ["Free"]
        selection_solver(data).preserve_resting_crafters(row, ROOM)
        assert row[-1] == incoming.name
    assert resident.is_resting()
    assert data.dorm[0].name == resident.name


@pytest.mark.parametrize("upper", [12, 20, 24])
def test_queued_named_fill_rechecks_applicant_mood_threshold(op_data, upper):
    data = op_data
    resident = data.operators["空爆"]
    resident.mood = 2
    incoming = set_tier(data, "红", RestingTier.REPLACEMENT, upper * 0.9)
    incoming.upper_limit, incoming.depletion_rate = upper, 0
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    task = tasks[0]
    assert incoming.name in task.plan[ROOM]
    incoming.mood += 0.01
    before = deepcopy(vars(data.dorm[0]))
    solver = selection_solver(data, task)
    solver._emergency_frozen = lambda: False
    solver._track_idle_dorm_shift = lambda _: None
    solver._finish_idle_dorm_shift = lambda: None
    solver.agent_arrange_room = MagicMock(return_value=False)

    solver.agent_arrange(task.plan)

    assert incoming.name not in {name for row in task.plan.values() for name in row}
    assert vars(data.dorm[0]) == before
    assert resident.is_resting()


@pytest.mark.parametrize("tier", PROTECTED)
def test_empty_beds_remain_available_to_every_tier(op_data, tier):
    data = op_data
    data.operators["空爆"].current_room = ""
    bed = data.dorm[0]
    bed.reset()
    incoming = set_tier(data, "红", tier, 5)
    assert data._find_dorm_slot(incoming.name, set()) == 0


def test_normal_release_of_completed_priority_replacement_remains_allowed(op_data):
    data = op_data
    resident = set_tier(data, "空爆", RestingTier.PRIORITY_REPLACEMENT, 24)
    resident.current_room, resident.current_index = ROOM, 4
    task = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={ROOM: ["Current"] * 4 + ["Free"]},
        meta_data=resident.name,
    )
    solver = selection_solver(data, task)
    assert solver.prepare_release_dorm(task)
    solver.preserve_resting_crafters(task.plan[ROOM], ROOM)
    assert task.plan[ROOM][-1] != resident.name


@pytest.mark.parametrize("tier", PROTECTED)
def test_queued_named_fill_rechecks_newly_protected_resident(op_data, tier):
    data = op_data
    resident = data.operators["空爆"]
    resident.mood = 12
    incoming = set_tier(data, "红", RestingTier.PRIORITY_REPLACEMENT, 5)
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    task = tasks[0]
    assert incoming.name in task.plan[ROOM]
    set_tier(data, resident.name, tier, 12)
    resident.current_room, resident.current_index = ROOM, 4
    bed_before = deepcopy(vars(data.dorm[0]))
    solver = selection_solver(data, task)
    solver._emergency_frozen = lambda: False
    solver._track_idle_dorm_shift = lambda _: None
    solver._finish_idle_dorm_shift = lambda: None
    solver.agent_arrange_room = MagicMock(return_value=False)

    solver.agent_arrange(task.plan)

    assert incoming.name not in {name for row in task.plan.values() for name in row}
    assert vars(data.dorm[0]) == bed_before
    assert resident.is_resting()


@pytest.mark.parametrize("strict_task", [False, True])
def test_personal_mood_limit_still_releases_a_protected_resident(op_data, strict_task):
    data = op_data
    resident = set_tier(data, "空爆", RestingTier.PRIORITY_REPLACEMENT, 12)
    resident.current_room, resident.current_index = ROOM, 4
    resident.upper_limit = 12
    data.config.operator_mood_limits = {resident.name: {"lower": 0, "upper": 12}}
    task = SchedulerTask(
        task_plan={ROOM: ["Current"] * 4 + ["Free"]},
        meta_data=resident.name,
    )
    task.strict_mood_limit = strict_task
    solver = selection_solver(data, task)
    solver.preserve_resting_crafters(task.plan[ROOM], ROOM)
    assert task.plan[ROOM][-1] != resident.name


def test_merged_normal_release_checks_each_occupied_bed(op_data):
    data = op_data
    resident = set_tier(data, "空爆", RestingTier.PRIORITY_REPLACEMENT, 24)
    resident.current_room, resident.current_index = ROOM, 4
    task = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={ROOM: ["Current"] * 4 + ["Free"]},
        meta_data="其他干员,空爆",
    )
    task.release_targets = {resident.name: (ROOM, 4)}
    solver = selection_solver(data, task)
    solver.preserve_resting_crafters(task.plan[ROOM], ROOM)
    assert task.plan[ROOM][-1] != resident.name


def test_standby_takeover_does_not_recall_completed_protected_group_member(
    group_solver,
):
    data = group_solver.op_data
    names = mass_mood_recovery_tests.PRIMARY[:2]
    data.groups["轮休"] = names
    for name in names:
        data.operators[name].group = "轮休"
    for bed, name in zip(data.dorm, mass_mood_recovery_tests.PRIMARY[:3]):
        op = data.operators[name]
        op._current_room, op.current_index = bed.position
        op.mood = 24 if name == names[1] else 12
        bed.name, bed.time = name, mass_mood_recovery_tests.NOW + timedelta(hours=3)
    data.operators[names[0]].resting_priority = "standby"
    data.config.resting_standby = [names[0]]
    incoming = data.operators["陈"]
    incoming._current_room, incoming.current_index = "", -1
    incoming.mood = 5
    original = SchedulerTask(
        time=mass_mood_recovery_tests.NOW + timedelta(hours=3),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={data.operators[name].room: [name] for name in names},
    )
    tasks = [original]
    before = deepcopy(vars(data.dorm[1]))

    try_add_release_dorm({}, None, data, tasks)

    fill = next(task for task in tasks if task is not original)
    assert not any(
        names[1] in row
        for room, row in fill.plan.items()
        if not room.startswith("dorm")
    )
    assert data.project_arrangements([fill.plan]).operators[names[1]].is_resting()
    assert original in tasks
    assert vars(data.dorm[1]) == before


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT])
def test_replanned_named_fill_yields_to_critical_task_before_live_compensation(
    op_data, kind
):
    data = op_data
    set_tier(data, "红", RestingTier.PRIORITY_REPLACEMENT, 5)
    data.operators["空爆"].mood = 12
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    task = tasks[0]
    critical = SchedulerTask(
        time=datetime.now() + timedelta(seconds=30),
        task_type=kind,
        task_plan={"meeting": ["银灰"]},
    )
    config.conf.enable_mastery = kind == TaskTypes.SWAP_SUPPORT
    solver = selection_solver(data, task)
    solver.tasks.append(critical)
    solver._emergency_frozen = lambda: False
    solver._track_idle_dorm_shift = lambda _: None
    solver.agent_arrange_room = MagicMock(return_value=False)
    before = deepcopy(vars(data.dorm[0]))

    assert solver.agent_arrange(task.plan) is False

    assert task.time > critical.time
    assert solver.tasks[0] is critical
    solver.agent_arrange_room.assert_not_called()
    assert vars(data.dorm[0]) == before
