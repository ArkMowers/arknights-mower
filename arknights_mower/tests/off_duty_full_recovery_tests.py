"""离岗回满主班先安排替班与入宿，独立纠错不等待恢复期限。"""

import pickle
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.dorm_group_tests import apply_plan
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils import dorm_candidates, group_recovery, resting_correction
from arknights_mower.utils.plan import Plan, PlanConfig
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


@pytest.fixture
def recovery(solver, monkeypatch):
    data = solver.op_data
    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(resting_correction, "datetime", Clock)
    monkeypatch.setattr(dorm_candidates, "datetime", Clock)
    op = data.operators[PRIMARY[0]]
    op.rest_in_full = op.exhaust_require = True
    data.config.rest_in_full = [op.name]
    data.config.exhaust_require = [op.name]
    data.global_plan["default_plan"].config.rest_in_full = [op.name]
    data.global_plan["default_plan"].config.exhaust_require = [op.name]
    data.exhaust_agent = [op.name]
    op._current_room, op.current_index = "", -1
    op.mood, op.time_stamp = 18, NOW
    solver.global_plan = data.global_plan
    solver.find = MagicMock(return_value=True)
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver.skip = MagicMock()
    solver._scan_card_moods = MagicMock(side_effect=AssertionError("已有有效心情"))
    solver.agent_arrange = MagicMock(
        side_effect=lambda plan, *a, **kw: (
            apply_plan(solver, plan),
            plan.clear(),
            True,
        )[2]
    )
    return solver, op


@pytest.fixture
def automatic_recovery(recovery, monkeypatch):
    solver, op = recovery
    data = solver.op_data
    data.runtime_conf = base_schedule.config.conf
    monkeypatch.setattr(group_recovery, "datetime", Clock)
    op.rest_in_full = op.exhaust_require = False
    data.config.rest_in_full = data.config.exhaust_require = []
    data.global_plan["default_plan"].config.rest_in_full = []
    data.global_plan["default_plan"].config.exhaust_require = []
    data.exhaust_agent = []
    op.group = "恢复组"
    data.groups[op.group] = [op.name]
    data.plan[op.room][op.index].group = op.group
    data.global_plan["default_plan"].plan[op.room][op.index].group = op.group
    data.group_shift_state[op.group] = True
    data.group_recovery_full_members[op.group] = [op.name]
    data.group_recovery_return_time[op.group] = NOW - timedelta(minutes=20)
    return solver, op


@pytest.mark.parametrize("initial", [False, True])
@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("card_only", [False, True])
def test_automatic_group_recovery_dispatches_missing_bed_before_recall(
    automatic_recovery, initial, restart, card_only
):
    solver, op = automatic_recovery
    if card_only:
        op.mood, op.time_stamp = 24, None
        solver.op_data.dorm_mood_estimates[op.name] = (
            18,
            Clock.fromtimestamp(NOW.timestamp()),
        )
    task = SchedulerTask(
        time=NOW - timedelta(minutes=20),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={op.room: [op.name]},
    )
    task.derived_correction, task.initial_staffing = True, initial
    original_time = task.time
    if restart:
        solver._retain_failed_task(
            task, "需要回满的主班心情尚未满足要求，且缺少有效恢复期限", []
        )
        task = pickle.loads(pickle.dumps(task))
        solver.tasks = [task]
        solver._resume_failed_tasks()
        assert not getattr(task, "execution_failure", None)
    solver.tasks, solver.task = [task], task
    solver.infra_main()
    assert solver.op_data.operators[op.name].is_resting()
    assert solver.op_data.get_current_room(op.room, True) == [COVERS[0]]
    assert not op.rest_in_full
    assert task.time == original_time
    assert task not in solver.tasks
    solver._scan_card_moods.assert_not_called()


def test_automatic_group_recovery_generated_correction_restores_bed(automatic_recovery):
    solver, op = automatic_recovery
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert op.name not in plan.get(op.room, [])
    assert any(op.name in row for room, row in plan.items() if room.startswith("dorm"))
    assert plan[op.room] == [COVERS[0]]
    assert not op.current_room


@pytest.mark.parametrize("waiting", [False, True])
@pytest.mark.parametrize("retained", [False, True])
def test_own_return_reservation_allows_automatic_recovery_prerequisite(
    automatic_recovery, waiting, retained
):
    solver, op = automatic_recovery
    cover = solver.op_data.operators[COVERS[0]]
    cover._current_room, cover.current_index = op.room, op.index
    owner = SchedulerTask(
        time=NOW - timedelta(minutes=20),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={op.room: [op.name]},
    )
    if retained:
        solver._retain_failed_task(
            owner, "组员尚未确认回满心情，保留回班任务并等待有效恢复观察", []
        )
    solver.tasks = [] if waiting else [owner]
    solver.waiting_group_shifts = [owner] if waiting else []
    before = pickle.dumps(owner)

    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)

    assert any(op.name in row for room, row in plan.items() if room.startswith("dorm"))
    assert op.name not in plan.get(op.room, [])
    assert pickle.dumps(owner) == before
    assert not op.current_room


def test_own_return_recovery_keeps_other_task_name_and_bed_reservations(
    automatic_recovery,
):
    solver, op = automatic_recovery
    cover = solver.op_data.operators[COVERS[0]]
    cover._current_room, cover.current_index = op.room, op.index
    owner = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={op.room: [op.name]})
    other = SchedulerTask(
        task_type=TaskTypes.NOT_SPECIFIC,
        task_plan={"dormitory_1": ["Current", "Current", op.name]},
    )
    solver.tasks = [owner, other]
    before = pickle.dumps(solver.tasks)
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert not any(
        op.name in row for room, row in plan.items() if room.startswith("dorm")
    )
    assert pickle.dumps(solver.tasks) == before


@pytest.mark.parametrize(
    "flag",
    [
        "mood_physical_started",
        "derived_correction_started",
        "backup_shift_active",
        "product_shift_locked",
        "strict_mood_limit",
        "exhaust_support",
        "ordinary_coordination",
    ],
)
def test_recovery_does_not_borrow_a_protected_return_reservation(
    automatic_recovery, flag
):
    solver, op = automatic_recovery
    cover = solver.op_data.operators[COVERS[0]]
    cover._current_room, cover.current_index = op.room, op.index
    owner = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={op.room: [op.name]})
    setattr(owner, flag, True)
    solver.tasks = [owner]
    plan = {}
    assert not solver._complete_departed_recovery(plan, {op.name})
    assert plan == {}


@pytest.mark.parametrize("waiting", [False, True])
@pytest.mark.parametrize("retained", [False, True])
def test_own_return_can_use_its_only_currently_empty_cleanup_bed(
    automatic_recovery, waiting, retained
):
    solver, op = automatic_recovery
    data = solver.op_data
    data.dorm = data.dorm[:1]
    cover = data.operators[COVERS[0]]
    cover._current_room, cover.current_index = op.room, op.index
    owner = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={op.room: [op.name], "dormitory_1": ["Current", "Current", "Free"]},
    )
    if retained:
        solver._retain_failed_task(owner, "等待恢复", [])
    solver.tasks = [] if waiting else [owner]
    solver.waiting_group_shifts = [owner] if waiting else []
    before = pickle.dumps(owner)
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert plan.get("dormitory_1", [])[2:3] == [op.name]
    assert pickle.dumps(owner) == before


@pytest.mark.parametrize("other_waiting", [False, True])
def test_own_empty_cleanup_bed_still_respects_another_owners_reservation(
    automatic_recovery, other_waiting
):
    solver, op = automatic_recovery
    solver.op_data.dorm = solver.op_data.dorm[:1]
    owner = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={op.room: [op.name], "dormitory_1": ["Current", "Current", "Free"]},
    )
    other = SchedulerTask(
        task_type=TaskTypes.NOT_SPECIFIC,
        task_plan={"dormitory_1": ["Current", "Current", "Free"]},
    )
    solver.tasks = [owner] if other_waiting else [owner, other]
    solver.waiting_group_shifts = [other] if other_waiting else []
    plan = {}
    assert not solver._complete_departed_recovery(plan, {op.name})
    assert plan == {}


@pytest.mark.parametrize("capacity", [1, 2])
@pytest.mark.parametrize("second_cleanup", [False, True])
def test_independent_return_owners_do_not_borrow_each_others_cleanup_beds(
    automatic_recovery, capacity, second_cleanup, monkeypatch
):
    solver, first = automatic_recovery
    data = solver.op_data
    second = data.operators[PRIMARY[1]]
    second._current_room, second.current_index = "", -1
    first.mood, second.mood, second.group = 10, 12, "另一恢复组"
    data.groups[second.group] = [second.name]
    data.plan[second.room][second.index].group = second.group
    data.global_plan["default_plan"].plan[second.room][
        second.index
    ].group = second.group
    data.group_shift_state[second.group] = True
    data.group_recovery_full_members[second.group] = [second.name]
    data.group_recovery_return_time[second.group] = NOW - timedelta(minutes=20)
    data.dorm = data.dorm[:capacity]
    solver.tasks = [
        SchedulerTask(
            task_type=TaskTypes.SHIFT_ON,
            task_plan={
                op.room: [op.name],
                "dormitory_1": ["Current", "Current"]
                + ["Free" if index == bed else "Current" for index in (2, 3)],
            },
        )
        for op, bed in ((first, 3), (second, 2))
    ]
    if not second_cleanup:
        del solver.tasks[1].plan["dormitory_1"]
    for owner in solver.tasks:
        solver._retain_failed_task(owner, "等待组员回满", [])
    before = pickle.dumps(solver.tasks)
    plan = {}
    assert solver._complete_departed_recovery(plan, {first.name, second.name}) is (
        capacity == 2
    )
    if capacity == 2:
        assert plan["dormitory_1"][2:] == [second.name, first.name, "Current"]
    else:
        assert plan == {}
    assert all(not bed.name for bed in data.dorm)
    assert pickle.dumps(solver.tasks) == before
    if capacity == 2 and not second_cleanup:
        from arknights_mower.utils import operators, scheduler_task

        for op, name in ((first, COVERS[0]), (second, COVERS[1])):
            data.operators[name]._current_room = op.room
            data.operators[name].current_index = op.index
        owners = list(solver.tasks)
        original = [(task.time, pickle.dumps(task.plan)) for task in owners]
        correction = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan=plan)
        correction.derived_correction = True
        solver.tasks.insert(0, correction)
        solver.task = correction
        solver.infra_main()
        assert all(
            solver.op_data.operators[op.name].is_resting() for op in (first, second)
        )
        assert all(task in solver.tasks for task in owners)
        assert [(task.time, pickle.dumps(task.plan)) for task in owners] == original
        at = NOW + timedelta(hours=3.5)
        monkeypatch.setattr(Clock, "now", classmethod(lambda cls, tz=None: at))
        monkeypatch.setattr(operators, "datetime", Clock)
        monkeypatch.setattr(scheduler_task, "datetime", Clock)
        for op in (first, second):
            actual = solver.op_data.operators[op.name]
            actual.mood, actual.time_stamp = 24, at
            solver.op_data.get_dorm_by_name(op.name)[1].time = at
        solver._resume_failed_tasks()
        for owner in owners:
            assert owner in solver.tasks
            solver.task = owner
            solver.infra_main()
            assert owner not in solver.tasks
        for op in (first, second):
            assert solver.op_data.get_current_room(op.room, True) == [op.name]


@pytest.mark.parametrize("mode", ["once", "forced"])
def test_backup_group_return_mode_retains_its_recovery_semantics(
    automatic_recovery, mode
):
    solver, op = automatic_recovery
    owner = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={op.room: [op.name]})
    owner.backup_group_request = (0, op.group, "on", mode)
    solver.tasks = [owner]
    plan = {}
    assert solver._complete_departed_recovery(plan, {op.name}) is (mode == "once")


def test_retained_return_can_recover_then_dispatch_the_same_task(
    automatic_recovery, monkeypatch
):
    from arknights_mower.utils import operators, scheduler_task

    solver, op = automatic_recovery
    data = solver.op_data
    cover = data.operators[COVERS[0]]
    cover._current_room, cover.current_index = op.room, op.index
    owner = SchedulerTask(
        time=NOW - timedelta(minutes=20),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={op.room: [op.name]},
    )
    solver._retain_failed_task(owner, "等待回满观察", [])
    original_time, original_plan = owner.time, pickle.dumps(owner.plan)
    solver.tasks = [owner]
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    correction = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan=plan)
    correction.derived_correction = True
    solver.tasks.insert(0, correction)
    solver.task = correction
    solver.infra_main()
    data = solver.op_data
    op = data.operators[op.name]
    assert op.is_resting()
    assert owner in solver.tasks
    assert owner.time == original_time
    assert pickle.dumps(owner.plan) == original_plan
    assert data.get_current_room(op.room, True) == [COVERS[0]]

    at = NOW + timedelta(hours=3.5)
    monkeypatch.setattr(Clock, "now", classmethod(lambda cls, tz=None: at))
    monkeypatch.setattr(operators, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    op.mood, op.time_stamp = 24, at
    _, bed = data.get_dorm_by_name(op.name)
    bed.time = at
    solver._resume_failed_tasks()
    assert owner in solver.tasks
    assert not getattr(owner, "execution_failure", None)
    assert owner.time == original_time
    solver.task = owner
    solver.infra_main()
    assert solver.op_data.get_current_room(op.room, True) == [op.name]
    assert owner not in solver.tasks


@pytest.mark.parametrize("independent", [False, True])
def test_group_return_only_releases_required_group_recovery_members(
    automatic_recovery, independent
):
    solver, op = automatic_recovery
    data = solver.op_data
    peer = data.operators[PRIMARY[1]]
    peer.group = op.group
    data.groups[op.group].append(peer.name)
    data.plan[peer.room][peer.index].group = op.group
    data.global_plan["default_plan"].plan[peer.room][peer.index].group = op.group
    if independent:
        op.rest_in_full = True
        data.config.rest_in_full = [op.name]
        data.global_plan["default_plan"].config.rest_in_full = [op.name]
        op.group_bindings = [
            {"group": op.group, "replacement": op.replacement},
            {"group": "", "replacement": op.replacement},
        ]
        for plan in (data.plan, data.global_plan["default_plan"].plan):
            plan[op.room][op.index].group_bindings = [
                {"group": "", "replacement": op.replacement}
            ]
    owner = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON, task_plan={peer.room: [peer.name]}
    )
    solver._retain_failed_task(owner, "等待整组恢复", [])
    solver.tasks = [owner]
    before = pickle.dumps(owner)
    names, _ = dorm_candidates.retained_task_reservations(
        data, [owner], recovering_name=op.name
    )
    assert (op.name in names) is independent
    if not independent:
        assert solver._complete_departed_recovery({}, {op.name})
    assert pickle.dumps(owner) == before


@pytest.mark.parametrize(
    "kind", ["named-target", "occupied-cleanup", "product", "urgent"]
)
def test_own_return_does_not_release_other_recovery_obligations(
    automatic_recovery, kind
):
    solver, op = automatic_recovery
    data = solver.op_data
    data.dorm = data.dorm[:1]
    owner = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={op.room: [op.name], "dormitory_1": ["Current", "Current", "Free"]},
    )
    if kind == "named-target":
        owner.plan["dormitory_1"][2] = PRIMARY[1]
    elif kind == "occupied-cleanup":
        resident = data.operators[PRIMARY[1]]
        resident._current_room, resident.current_index = data.dorm[0].position
        resident.mood = 18
        data.dorm[0].name = resident.name
    elif kind == "product":
        data.reserved_product_replacements.add(op.name)
    elif kind == "urgent":
        owner.urgent_recovery_reserved_names = [op.name]
    solver.tasks = [owner]
    plan = {}
    assert not solver._complete_departed_recovery(plan, {op.name})
    assert plan == {}


def test_splitting_a_return_keeps_its_own_empty_recovery_bed(automatic_recovery):
    solver, op = automatic_recovery
    task = SchedulerTask(
        time=NOW - timedelta(minutes=20),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={
            op.room: [op.name],
            "dormitory_1": ["Current", "Current", "Free", "Current", "Current"],
        },
    )
    before = pickle.dumps(task.plan)
    pending = []
    group_recovery.split_recovery_return(solver.op_data, task, pending, [op.name])
    assert pickle.dumps(task.plan) == before
    assert pending == []


def test_splitting_own_recovery_still_releases_an_independent_group(automatic_recovery):
    solver, op = automatic_recovery
    other = solver.op_data.operators[PRIMARY[1]]
    task = SchedulerTask(
        time=NOW - timedelta(minutes=20),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={
            op.room: [op.name],
            other.room: [other.name],
            "dormitory_1": ["Current", "Current", "Free", "Current", "Current"],
        },
    )
    time = task.time
    pending = []
    group_recovery.split_recovery_return(
        solver.op_data, task, pending, (name for name in [op.name])
    )
    assert task.plan == {
        op.room: [op.name],
        "dormitory_1": ["Current", "Current", "Free", "Current", "Current"],
    }
    assert len(pending) == 1
    assert pending[0].plan == {other.room: [other.name]}
    assert task.time == pending[0].time == time


@pytest.mark.parametrize(
    "kind",
    [
        "capped",
        "excluded",
        "forced",
        "working-group",
        "standby",
        "independent",
        "working",
        "full",
        "unknown",
    ],
)
def test_automatic_group_recovery_obeys_current_eligibility(automatic_recovery, kind):
    solver, op = automatic_recovery
    data = solver.op_data
    if kind == "capped":
        data.runtime_conf.group_mood_gap_max_extra_wait_hours = 1
        data.group_recovery_return_time[op.group] = NOW - timedelta(hours=2)
    elif kind == "excluded":
        data.runtime_conf.group_mood_gap_exclusions = [op.group]
    elif kind == "forced":
        data.backup_plans.append(
            Plan(
                {},
                PlanConfig("", "", ""),
                group_tasks=[{"group": op.group, "action": "on", "mode": "forced"}],
            )
        )
        data.plan_condition = [True]
    elif kind == "working-group":
        data.group_shift_state[op.group] = False
    elif kind == "standby":
        op.resting_priority = "standby"
    elif kind == "independent":
        op.group_bindings = [
            {"group": op.group, "replacement": op.replacement},
            {"group": "", "replacement": op.replacement},
        ]
    elif kind == "working":
        op._current_room, op.current_index = op.room, op.index
    elif kind == "full":
        op.mood = op.upper_limit
    elif kind == "unknown":
        op.time_stamp = None
    assert op.name not in resting_correction.off_duty_full_recovery_members(data)


def test_automatic_group_recovery_preserves_episode_without_duty_cache(
    automatic_recovery,
):
    solver, op = automatic_recovery
    del solver.op_data.group_shift_state[op.group]
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert any(op.name in row for room, row in plan.items() if room.startswith("dorm"))
    assert op.name not in plan.get(op.room, [])


def test_explicit_recovery_remains_required_after_automatic_wait_cap(
    automatic_recovery,
):
    solver, op = automatic_recovery
    data = solver.op_data
    op.rest_in_full = True
    data.runtime_conf.group_mood_gap_max_extra_wait_hours = 1
    data.group_recovery_return_time[op.group] = NOW - timedelta(hours=2)
    assert op.name in resting_correction.off_duty_full_recovery_members(data)


def test_automatic_group_recovery_waits_for_capacity_then_uses_released_bed(
    automatic_recovery,
):
    solver, op = automatic_recovery
    data = solver.op_data
    for bed, name in zip(data.dorm, PRIMARY[1:]):
        resident = data.operators[name]
        resident._current_room, resident.current_index = bed.position
        resident.rest_in_full = True
        resident.mood = 10
        bed.name, bed.time = name, NOW + timedelta(hours=3)
    blocked = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert op.name not in [name for row in blocked.values() for name in row]
    assert not op.current_room
    bed = data.dorm[0]
    resident = data.operators[bed.name]
    resident._current_room, resident.current_index = "", -1
    resident.mood, resident.time_stamp = 24, NOW
    bed.reset()
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert any(op.name in row for room, row in plan.items() if room.startswith("dorm"))
    assert op.name not in plan.get(op.room, [])


@pytest.mark.parametrize("initial", [False, True])
@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("exhaust", [False, True])
@pytest.mark.parametrize("card_only", [False, True])
def test_correction_sends_idle_full_recovery_primary_to_dorm(
    recovery, initial, restart, exhaust, card_only
):
    solver, op = recovery
    op.exhaust_require = exhaust
    solver.op_data.config.exhaust_require = [op.name] if exhaust else []
    solver.global_plan["default_plan"].config.exhaust_require = (
        [op.name] if exhaust else []
    )
    if card_only:
        op.mood, op.time_stamp = 24, None
        solver.op_data.dorm_mood_estimates[op.name] = (
            18,
            base_schedule.datetime.fromtimestamp(NOW.timestamp()),
        )
        assert dorm_candidates.dorm_candidate_mood(solver.op_data, op.name) == 18
    independent = solver.op_data.operators[PRIMARY[1]]
    independent._current_room, independent.current_index = "", -1
    task = SchedulerTask(
        time=NOW - timedelta(minutes=20),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={op.room: [op.name], "room_1_2": [PRIMARY[1]]},
    )
    task.derived_correction, task.initial_staffing = True, initial
    solver.tasks, solver.task = [task], task
    original_time = task.time
    if restart:
        solver._retain_failed_task(
            task, "需要回满的主班心情尚未满足要求，且缺少有效恢复期限", []
        )
        task.backup_shift_intent = {room: row.copy() for room, row in task.plan.items()}
        task.backup_shift_conditions = []
        task = pickle.loads(pickle.dumps(task))
        solver.tasks = [task]
        solver._resume_failed_tasks()
        assert not getattr(task, "execution_failure", None)
        solver.task = task
    solver.infra_main()
    assert solver.op_data.operators[op.name].is_resting()
    assert solver.op_data.get_current_room(op.room, True) == [COVERS[0]]
    assert solver.op_data.operators[PRIMARY[1]].current_room == "room_1_2"
    assert task.time == original_time
    assert task not in solver.tasks


def test_generated_correction_keeps_off_duty_primary_resting(recovery):
    solver, op = recovery
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert op.name not in plan.get(op.room, [])
    assert any(op.name in row for room, row in plan.items() if room.startswith("dorm"))
    assert plan[op.room] == [COVERS[0]]
    assert not op.current_room


@pytest.mark.parametrize("initial", [False, True])
def test_new_card_observation_replaces_idle_primary_before_arrangement(
    recovery, initial
):
    solver, op = recovery
    op.mood, op.time_stamp = 24, None

    solver.op_data.dorm_mood_estimates[op.name] = (
        18,
        Clock.fromtimestamp(NOW.timestamp()),
    )
    task = SchedulerTask(
        time=NOW,
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={op.room: [op.name]},
    )
    task.derived_correction, task.initial_staffing = True, initial
    solver.tasks, solver.task = [task], task
    solver.infra_main()
    assert solver.op_data.operators[op.name].is_resting()
    assert solver.op_data.get_current_room(op.room, True) == [COVERS[0]]
    solver._scan_card_moods.assert_not_called()


@pytest.mark.parametrize("exhaust", [False, True])
def test_full_recovery_does_not_send_working_primary_to_rest(recovery, exhaust):
    solver, op = recovery
    op.exhaust_require = exhaust
    op._current_room, op.current_index = op.room, op.index
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert not any(
        op.name in row for room, row in plan.items() if room.startswith("dorm")
    )
    assert op.is_working()


def test_missing_beds_does_not_block_independent_correction(recovery):
    solver, op = recovery
    # 三名不同主班占用全部床位，恢复中的成员不被挤出。
    for bed, name in zip(solver.op_data.dorm, PRIMARY[1:]):
        resident = solver.op_data.operators[name]
        resident._current_room, resident.current_index = bed.position
        resident.rest_in_full = True
        resident.mood = 10
        bed.name = name
        bed.time = NOW + timedelta(hours=3)
    solver.global_plan["default_plan"].config.rest_in_full = PRIMARY
    task = SchedulerTask(
        time=NOW,
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={op.room: [op.name], "room_1_2": [PRIMARY[1]]},
    )
    task.derived_correction = True
    solver.tasks, solver.task = [task], task
    solver.infra_main()
    assert not getattr(task, "execution_failure", None)
    assert not op.is_working()
    assert solver.op_data.get_current_room(op.room, True) == [COVERS[0]]
    assert solver.op_data.get_current_room("room_1_2", True) == [COVERS[1]]

    # 真实床位释放后，普通纠错即可补入宿舍，无需定时重试任务。
    data = solver.op_data
    bed = data.dorm[0]
    resident = data.operators[bed.name]
    resident._current_room, resident.current_index = "", -1
    resident.mood, resident.time_stamp = 24, NOW
    bed.reset()
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert any(op.name in row for room, row in plan.items() if room.startswith("dorm"))
    assert op.name not in plan.get(op.room, [])


def test_missing_cover_keeps_full_primary_off_duty_and_corrects_independent_room(
    recovery,
):
    solver, op = recovery
    solver.op_data.operators[COVERS[0]].mood = 0
    independent = solver.op_data.operators[PRIMARY[1]]
    independent._current_room, independent.current_index = "", -1
    task = SchedulerTask(
        time=NOW,
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={op.room: [op.name], independent.room: [independent.name]},
    )
    task.derived_correction = True
    solver.tasks, solver.task = [task], task
    solver.infra_main()
    assert not getattr(task, "execution_failure", None)
    assert not solver.op_data.operators[op.name].is_working()
    assert solver.op_data.operators[independent.name].current_room == independent.room


def test_dorm_resident_without_deadline_keeps_cover(recovery):
    solver, op = recovery
    data = solver.op_data
    bed = data.dorm[0]
    bed.name, bed.time = op.name, None
    op._current_room, op.current_index = bed.position
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert plan[op.room] == [COVERS[0]]
    assert not any(
        op.name in row for room, row in plan.items() if not room.startswith("dorm")
    )


def test_confirmed_full_resident_can_return_without_recovery_countdown(recovery):
    solver, op = recovery
    bed = solver.op_data.dorm[0]
    bed.name, bed.time = op.name, None
    op._current_room, op.current_index = bed.position
    op.mood, op.time_stamp = op.upper_limit, NOW
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={op.room: [op.name]})
    solver.tasks, solver.task = [task], task

    assert not getattr(task, "execution_failure", None)
    solver._scan_card_moods.assert_not_called()


@pytest.mark.parametrize("started", [False, True])
def test_correction_preserves_explicit_return_or_started_arrangement(recovery, started):
    solver, op = recovery
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={op.room: [op.name]}
    )
    task.derived_correction = True
    if started:
        task.derived_correction_started = True
    else:
        task.initial_staffing = True
        task.initial_staffing_returns = {op.name}
    solver.tasks = [task]
    assert not solver._prepare_correction_recovery(task)
    assert task.plan == {op.room: [op.name]}


@pytest.mark.parametrize("mood", [None, 24])
def test_unobserved_or_full_primary_is_not_sent_to_dorm(recovery, mood):
    solver, op = recovery
    op.mood, op.time_stamp = 24, NOW if mood is not None else None
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert not any(
        op.name in row for room, row in plan.items() if room.startswith("dorm")
    )
