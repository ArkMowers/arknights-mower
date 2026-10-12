"""高优替班接管不依赖不养闲人，沿用统一候选、预约与严格层级。"""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import (
    dorm_empty_release_tests,
    dorm_release_tests,
    shift_backup_convergence_tests,
)
from arknights_mower.tests.resting_priority_tests import set_tier
from arknights_mower.utils.operators import Dormitory, Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.resting_priority import RestingTier
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    try_add_release_dorm,
)

ROOM = dorm_release_tests.ROOM
op_data = dorm_release_tests.op_data
solver = dorm_empty_release_tests.solver
shift_solver = shift_backup_convergence_tests.solver


@pytest.mark.parametrize("free_room", [False, True])
@pytest.mark.parametrize("empty_only", [False, True])
@pytest.mark.parametrize("resident_tier", list(RestingTier)[:-1])
def test_priority_takeover_preserves_strict_tiers(
    op_data, free_room, empty_only, resident_tier
):
    data = op_data
    data.config.free_room = free_room
    incoming = set_tier(data, "红", RestingTier.PRIORITY_REPLACEMENT, 5)
    resident = set_tier(data, "空爆", resident_tier, 12)
    resident.group = ""
    if resident.is_high():
        resident.room, resident.index = "meeting", 0
    resident.current_room, resident.current_index = ROOM, 4
    data.dorm[0].time = datetime.now() + timedelta(hours=4)
    tasks = []

    try_add_release_dorm({}, None, data, tasks, empty_only=empty_only)

    assert bool(tasks) is (resident_tier > RestingTier.PRIORITY_REPLACEMENT)
    if tasks:
        assert tasks[0].plan[ROOM][-1] == incoming.name
    assert (resident.current_room, resident.current_index) == (ROOM, 4)
    assert incoming.current_room == ""


@pytest.mark.parametrize("reason", ["name", "bed", "excluded", "working", "full"])
def test_priority_takeover_retains_candidate_and_bed_guards(op_data, reason):
    data = op_data
    data.config.free_room = False
    set_tier(data, "红", RestingTier.PRIORITY_REPLACEMENT, 5)
    tasks = []
    if reason == "name":
        tasks.append(SchedulerTask(task_plan={"meeting": ["红"]}))
    elif reason == "bed":
        tasks.append(SchedulerTask(task_plan={ROOM: ["Current"] * 4 + ["Free"]}))
    elif reason == "excluded":
        data.config.free_room_exclusions = ["空爆"]
    elif reason == "working":
        data.operators["红"].current_room = "meeting"
    else:
        data.operators["红"].mood = 24
    before = tasks.copy()

    try_add_release_dorm({}, None, data, tasks, empty_only=True)

    assert tasks == before


@pytest.mark.parametrize("free_room", [False, True])
def test_projection_admission_preserves_full_primary(op_data, free_room):
    data = op_data
    data.config.free_room = free_room
    set_tier(data, "红", RestingTier.PRIORITY_REPLACEMENT, 5)
    resident = set_tier(data, "空爆", RestingTier.MAIN, 24)
    resident.current_room, resident.current_index = ROOM, 4
    tasks = []
    try_add_release_dorm({}, None, data, tasks, empty_only=True)
    assert tasks == []


def test_vacancy_precedes_priority_takeover(op_data):
    data = op_data
    data.config.free_room = False
    set_tier(data, "红", RestingTier.PRIORITY_REPLACEMENT, 5)
    data.plan[ROOM][3] = Room("Free", "", [])
    data.dorm.insert(0, Dormitory((ROOM, 3)))
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks[0].plan[ROOM] == ["Current"] * 3 + ["红", "Current"]


@pytest.mark.parametrize("reading", ["measured", "estimated"])
@pytest.mark.parametrize("free_room", [False, True])
def test_priority_takeover_reuses_selection_and_preserves_observations(
    solver, reading, free_room
):
    instance, selected = solver
    data = instance.op_data
    data.config.free_room = free_room
    candidate = set_tier(data, "红", RestingTier.PRIORITY_REPLACEMENT, 5)
    if reading == "estimated":
        candidate.mood, candidate.time_stamp = 24, None
        data.dorm_mood_estimates[candidate.name] = (5, datetime.now())
    before = deepcopy(vars(candidate))
    tasks = []

    try_add_release_dorm({}, None, data, tasks)

    assert tasks[0].plan[ROOM][-1] == candidate.name
    instance.task = tasks[0]
    plan = selected[:4] + [candidate.name]
    instance.choose_agent(plan, ROOM)
    assert selected == plan
    assert vars(candidate) == before


def test_priority_admission_orders_recovery_gap_and_excludes_ordinary_fill(op_data):
    data = op_data
    data.config.free_room = False
    set_tier(data, "红", RestingTier.PRIORITY_REPLACEMENT, 20)
    data.add(Operator("陈", ""))
    second = set_tier(data, "陈", RestingTier.PRIORITY_REPLACEMENT, 10)
    second.time_stamp = None
    data.dorm_mood_estimates[second.name] = (10, datetime.now())
    data.add(Operator("斥罪", "", mood=0, time_stamp=datetime.now()))
    tasks = []

    try_add_release_dorm({}, None, data, tasks, empty_only=True)

    assert tasks[0].plan[ROOM][-1] == second.name


def test_unobserved_priority_name_never_becomes_explicit_projection_staff(op_data):
    data = op_data
    data.config.free_room = False
    data.operators["红"].current_room = "meeting"
    data.config.ope_resting_priority = ["陈"]
    data.dorm_mood_estimates["陈"] = (5, datetime.now())
    tasks = []
    try_add_release_dorm({}, None, data, tasks, empty_only=True)
    assert tasks == []


def test_priority_takeover_keeps_group_anchor_and_standby_return(op_data):
    data = op_data
    data.config.free_room = False
    set_tier(data, "红", RestingTier.PRIORITY_REPLACEMENT, 5)
    standby = set_tier(data, "空爆", RestingTier.STANDBY, 20)
    standby.room, standby.index, standby.group = "room_1_1", 0, "轮休"
    anchor = data.operators["银灰"]
    anchor.group, anchor.mood = standby.group, 5
    anchor.current_room, anchor.current_index = ROOM, 3
    data.plan["room_1_1"] = [Room(standby.name, standby.group, [])]
    data.plan[ROOM][3] = Room("Free", "", [])
    data.groups[standby.group] = [anchor.name, standby.name]
    data.dorm.insert(0, Dormitory((ROOM, 3), anchor.name))
    future = SchedulerTask(
        time=datetime.now() + timedelta(hours=2),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": [anchor.name], "room_1_1": [standby.name]},
    )
    tasks = [future]

    try_add_release_dorm({}, None, data, tasks, empty_only=True)

    assert tasks[0] is future
    assert future.plan == {"meeting": [anchor.name], "room_1_1": [standby.name]}
    assert tasks[1].plan[ROOM] == ["Current"] * 4 + ["红"]
    assert (anchor.current_room, anchor.current_index) == (ROOM, 3)


def test_shift_projection_admits_freed_priority_cover_without_idle_release(
    shift_solver,
):
    instance = shift_solver
    data = instance.op_data
    data.config.free_room = False
    data.config.resting_priority_replacement = ["陈"]
    data.global_plan["default_plan"].config.resting_priority_replacement = ["陈"]
    for op in data.operators.values():
        op.mood, op.depletion_rate = 24, 0
    for bed, name in zip(data.dorm, ["空爆", "斥罪", "杜宾"]):
        data.add(Operator(name, "", mood=24, time_stamp=datetime.now()))
        resident = data.operators[name]
        resident.current_room, resident.current_index = bed.position
        bed.name = name
    cover = data.operators["陈"]
    cover.current_room, cover.current_index, cover.mood = "central", 0, 5
    main = data.operators["薇薇安娜"]
    main.current_room, main.current_index = "", -1
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"central": [main.name]},
    )
    instance.task, instance.tasks = task, [task]
    before = shift_backup_convergence_tests.positions(data)

    instance._prepare_shift_cycle(task)

    assert task.plan["central"] == [main.name]
    assert cover.name in task.plan[ROOM]
    assert shift_backup_convergence_tests.positions(data) == before
    assert instance.tasks == [task]


@pytest.mark.parametrize("free_room", [False, True])
@pytest.mark.parametrize("entry", ["metadata", "future_work", "direct"])
def test_idle_release_switch_only_controls_ordinary_task_creation(
    op_data, free_room, entry
):
    from arknights_mower.utils.scheduler_task import add_release_dorm, plan_metadata

    data = op_data
    data.config.free_room = free_room
    resident = data.operators["空爆"]
    resident.mood = 10
    data.dorm[0].time = datetime.now() + timedelta(hours=2)
    tasks = []
    if entry == "metadata":
        tasks = plan_metadata(data, tasks)
    elif entry == "future_work":
        try_add_release_dorm(
            {"meeting": [resident.name]},
            datetime.now() + timedelta(hours=3),
            data,
            tasks,
        )
    else:
        add_release_dorm(tasks, data, resident.name)
    releases = [task for task in tasks if task.type == TaskTypes.RELEASE_DORM]
    assert bool(releases) is free_room
    if releases:
        assert releases[0].release_dorm_targets() == {resident.name: (ROOM, 4)}
        assert releases[0].time == data.dorm[0].time
    assert (resident.current_room, resident.current_index) == (ROOM, 4)


@pytest.mark.parametrize("free_room", [False, True])
@pytest.mark.parametrize("current", ["manager", "recovering"])
def test_shared_refresh_indices_include_auto_free_recovery_only(
    op_data, free_room, current
):
    data = op_data
    data.config.free_room = free_room
    manager = data.operators["桃金娘"]
    manager.group, manager.replacement = "联动", ["Free"]
    data.plan[ROOM][3] = Room(manager.name, manager.group, manager.replacement)
    data.dorm.insert(0, Dormitory((ROOM, 3)))
    name = manager.name if current == "manager" else "红"
    data.operators[name].current_room, data.operators[name].current_index = ROOM, 3
    indices = data.get_refresh_index(ROOM, ["Current"] * 5)
    assert indices == ([4] if current == "manager" else [3, 4])
    assert data.get_refresh_index(ROOM, ["Current"] * 3 + [manager.name, "Free"]) == [4]


@pytest.mark.parametrize("free_room", [False, True])
def test_shared_planning_admits_ordinary_cover_despite_nearby_unrelated_task(
    solver, free_room
):
    from unittest.mock import MagicMock

    instance, _ = solver
    data = instance.op_data
    data.config.free_room = free_room
    data.operators["红"].mood = 5
    data.dorm[0].reset()
    data.operators["空爆"].current_room = ""
    instance._plan_primary_recovery = MagicMock(return_value=True)
    instance._fill_empty_dorms = MagicMock()
    existing = SchedulerTask(
        task_plan={"meeting": ["银灰"]},
        time=datetime.now() + timedelta(minutes=1),
    )
    instance.tasks = [existing]
    assert instance._plan_dorm_recovery()
    assert instance.tasks[0] is existing
    assert instance.tasks[1].plan == {ROOM: ["Current"] * 4 + ["红"]}
    assert data.dorm[0].name == ""


@pytest.mark.parametrize("free_room", [False, True])
def test_explicit_full_roster_is_preserved_during_selection(solver, free_room):
    instance, selected = solver
    instance.op_data.config.free_room = free_room
    instance.task.type = TaskTypes.SELF_CORRECTION
    instance.task.meta_data = ""
    plan = selected.copy()
    instance.prepare_dorm_selection(plan, ROOM)
    assert plan == selected
