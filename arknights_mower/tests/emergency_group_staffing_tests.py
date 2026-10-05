"""救急主表完整下发与部分失败后的续排。"""

import pickle
from datetime import timedelta

import pytest

from arknights_mower.tests.emergency_group_return_tests import (
    group_return as recovery_fixture,  # noqa: F401
)
from arknights_mower.tests.emergency_group_return_tests import (
    legacy_solver as legacy_solver,
)
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def staffing(recovery_fixture, monkeypatch):  # noqa: F811
    episode, solver = recovery_fixture, recovery_fixture.solver
    data = solver.op_data
    original = {data.operators[name].room: [name] for name in PRIMARY}
    original.update(
        {
            "dormitory_1": ["塑心", "冰酿", "", "", ""],
            "dormitory_2": ["闪灵", "白面鸮", "", "", ""],
        }
    )
    solver.op_data = data.project_arrangements([original])
    for name in PRIMARY:
        op = solver.op_data.operators[name]
        op.mood = 8
        solver.op_data.plan[op.room][0].facility = "制造站"
    episode.state["phase"] = "staffing"
    episode.state["staffing_complete"] = False
    episode.state["rescue_plan"] = {
        data.operators[name].room: [COVERS[index]] for index, name in enumerate(PRIMARY)
    }
    return episode


def staffing_task(solver):
    return next(
        task for task in solver.tasks if getattr(task, "emergency_staffing", False)
    )


def test_all_workrooms_precede_dorm_tasks(staffing):
    solver = staffing.solver
    assert solver._emergency_schedule_staffing()
    task = staffing_task(solver)
    assert task.plan == staffing.state["rescue_plan"]
    assert all(not room.startswith("dorm") for room in task.plan)
    assert set(task.emergency_staffing_members) == set(PRIMARY)
    assert staffing.saves[0]["state"]["staffing_plan"] == task.plan
    solver.backup_plan_solver.assert_not_called()


def test_restart_only_requeues_outstanding_rooms(staffing):
    solver = staffing.solver
    assert solver._emergency_schedule_staffing()
    first = staffing_task(solver)
    room = next(iter(first.plan))
    solver.op_data = solver.op_data.project_arrangements([{room: first.plan[room]}])
    solver.emergency_state = pickle.loads(pickle.dumps(staffing.state))
    solver.tasks.clear()
    assert solver._emergency_schedule_staffing()
    assert room not in staffing_task(solver).plan
    assert len(staffing_task(solver).plan) == 3


def test_finished_manual_workers_keep_working_after_mood_drops(staffing):
    solver = staffing.solver
    staffing.state["dorm_replan_pending"] = True
    assert solver._emergency_schedule_staffing()
    solver.op_data = solver.op_data.project_arrangements([staffing_task(solver).plan])
    solver.tasks.clear()
    assert solver._emergency_reconcile_staffing()
    for name in COVERS:
        solver.op_data.operators[name].mood = 0
    assert solver._emergency_schedule_staffing()
    assert not solver.tasks


@pytest.mark.parametrize("mood", [None, 0, 8])
def test_known_low_worker_can_staff_but_unknown_blocks_roster(staffing, mood):
    solver = staffing.solver
    op = solver.op_data.operators[COVERS[-1]]
    op.mood = mood if mood is not None else 24
    op.time_stamp = NOW if mood is not None else None
    solver.op_data.dorm_mood_estimates.clear()
    assert solver._emergency_schedule_staffing() is (mood is not None)
    if mood is None:
        assert not solver.tasks
        assert not staffing.state.get("staffing_plan")
    else:
        assert staffing_task(solver).plan == staffing.state["rescue_plan"]


def test_near_strict_release_defers_whole_work_roster(staffing):
    solver = staffing.solver
    task = SchedulerTask(
        time=NOW + timedelta(seconds=50),
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]},
    )
    task.strict_mood_limit = True
    solver.tasks.append(task)
    assert not solver._emergency_schedule_staffing()
    assert solver.tasks == [task]


def test_specialized_compensation_precedes_rescue_staffing(staffing):
    solver = staffing.solver
    room = next(iter(staffing.state["rescue_plan"]))
    task = SchedulerTask(task_plan={room: [COVERS[0]]})
    task.emergency_original_roster = {room: [PRIMARY[0]]}
    solver.tasks.append(task)
    assert not solver._emergency_schedule_staffing()
    assert solver.tasks == [task]


def test_fixed_rooms_join_rescue_dispatch_and_reconcile(staffing, monkeypatch):
    from arknights_mower.utils import config
    from arknights_mower.utils.operators import Operator

    monkeypatch.setattr(config.conf, "enable_mastery", False)
    solver = staffing.solver
    for name in ("泡普卡", "安赛尔"):
        solver.op_data.add(Operator(name, "", mood=24, time_stamp=NOW))
    staffing.state["rescue_plan"].update(
        {"factory": ["泡普卡"], "train": ["安赛尔", ""]}
    )
    assert solver._emergency_schedule_staffing()
    task = staffing_task(solver)
    assert task.plan["factory"] == ["泡普卡"]
    assert task.plan["train"] == ["安赛尔", ""]
    assert "" not in solver.op_data.operators
    solver.op_data = solver.op_data.project_arrangements([task.plan])
    solver.tasks.clear()
    assert solver._emergency_reconcile_staffing()
    assert staffing.state["staffing_complete"]


@pytest.mark.parametrize("follows", [False, True])
def test_rescue_training_uses_existing_assistant_protection(
    staffing, monkeypatch, follows
):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from arknights_mower.solvers import base_schedule, emergency
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
    from arknights_mower.utils import config
    from arknights_mower.utils.operators import Operator

    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", follows)
    monkeypatch.setattr(base_schedule, "_training_room_scan_disabled", False)
    monkeypatch.setattr(emergency, "busy_resting_names", lambda: set())
    solver = staffing.solver
    solver._suppress_train_correction = (
        BaseSchedulerSolver._suppress_train_correction.__get__(solver)
    )
    solver._train_mastery_active = MagicMock(return_value=True)
    solver._train_protected = MagicMock(return_value=False)
    solver.train_room_state = SimpleNamespace(
        state="training", locked=True, protected=False
    )
    solver.op_data.add(Operator("泡普卡", "", mood=24, time_stamp=NOW))
    staffing.state["rescue_plan"]["train"] = ["泡普卡", "安赛尔"]
    assert solver._emergency_schedule_staffing()
    plan = staffing_task(solver).plan
    if follows:
        assert plan["train"] == ["泡普卡", "Current"]
    else:
        assert "train" not in plan
    # 执行期间新出现的训练保护也不把已完成普通驻员部署卡在核对阶段。
    staffing.state["staffing_plan"] = {"train": ["泡普卡", "安赛尔"]}
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", False)
    solver.tasks.clear()
    assert solver._emergency_reconcile_staffing()


@pytest.mark.parametrize("complete", [False, True])
def test_rescue_group_leaves_together_without_reserving_beds(staffing, complete):
    from arknights_mower.utils.operators import Operator

    solver, state = staffing.solver, staffing.state
    solver.op_data = solver.op_data.project_arrangements([state["rescue_plan"]])
    data = solver.op_data
    state["staffing_complete"] = True
    state["phase"] = "recovering"
    rooms = list(state["rescue_plan"])[:2]
    state["worker_groups"] = {room: ["救急绑组"] for room in rooms}
    state["worker_replacements"] = {
        rooms[0]: [["年", "杜林"] if complete else ["年"]],
        rooms[1]: [["年"]],
    }
    for name in ("年", "杜林"):
        data.add(Operator(name, "", mood=24, time_stamp=NOW))
    data.operators[COVERS[0]].mood = 0
    original = {room: list(row) for room, row in state["rescue_plan"].items()}
    beds = [(bed.position, bed.name) for bed in data.all_dorms()]

    assert solver._emergency_schedule_staffing()

    if complete:
        task = staffing_task(solver)
        assert task.plan == {rooms[0]: ["杜林"], rooms[1]: ["年"]}
        assert not any(room.startswith("dorm") for room in task.plan)
        assert set(state["standby_workers"]) == set(COVERS[:2])
        solver._emergency_sync_reservations()
        assert not set(COVERS[:2]) & data.emergency_reserved_agents
    else:
        assert not solver.tasks
        assert state["rescue_plan"] == original
    assert [(bed.position, bed.name) for bed in data.all_dorms()] == beds


def test_original_primary_leaving_rescue_joins_recovery(staffing):
    from arknights_mower.utils.operators import Operator

    solver, state = staffing.solver, staffing.state
    room = next(iter(state["rescue_plan"]))
    name = PRIMARY[0]
    state["rescue_plan"][room] = [name]
    state["targets"].pop(name, None)
    state["worker_replacements"] = {room: [["年"]]}
    state["staffing_complete"] = True
    state["phase"] = "recovering"
    solver.op_data = solver.op_data.project_arrangements([state["rescue_plan"]])
    solver.op_data.add(Operator("年", "", mood=24, time_stamp=NOW))
    solver.op_data.operators[name].mood = 0

    assert solver._emergency_schedule_staffing()

    assert name in state["targets"]
    assert name not in state.get("standby_workers", [])
    assert staffing_task(solver).plan == {room: ["年"]}


def test_configured_zero_mood_worker_does_not_trigger_replacement(staffing):
    solver, state = staffing.solver, staffing.state
    room = next(iter(state["rescue_plan"]))
    solver.op_data = solver.op_data.project_arrangements([state["rescue_plan"]])
    solver.op_data.operators[COVERS[0]].mood = 0
    solver.op_data.config.workaholic.append(COVERS[0])
    state["worker_replacements"] = {room: [[COVERS[1]]]}
    state["staffing_complete"] = True
    assert solver._emergency_schedule_staffing()
    assert not solver.tasks


@pytest.mark.parametrize("configured_low", [False, True])
def test_group_member_without_replacement_keeps_working_at_zero(
    staffing, configured_low
):
    from arknights_mower.utils.operators import Operator

    solver, state = staffing.solver, staffing.state
    solver.op_data = solver.op_data.project_arrangements([state["rescue_plan"]])
    data = solver.op_data
    rooms = list(state["rescue_plan"])[:2]
    state["worker_groups"] = {room: ["同组"] for room in rooms}
    state["worker_replacements"] = {rooms[0]: [[]], rooms[1]: [["年"]]}
    state["staffing_complete"] = True
    data.operators[COVERS[0]].mood = 0
    data.operators[COVERS[1]].mood = 0 if configured_low else 24
    data.add(Operator("年", "", mood=24, time_stamp=NOW))

    assert solver._emergency_schedule_staffing()

    assert state["rescue_plan"][rooms[0]] == [COVERS[0]]
    assert COVERS[0] not in state.get("standby_workers", [])
    if configured_low:
        assert staffing_task(solver).plan == {rooms[1]: ["年"]}
    else:
        assert not solver.tasks


def test_staffing_completion_syncs_reservations_before_first_dorm_plan(staffing):
    from unittest.mock import MagicMock

    solver, state = staffing.solver, staffing.state
    state["dorm_replan_pending"] = True
    assert solver._emergency_schedule_staffing()
    solver.op_data = solver.op_data.project_arrangements([staffing_task(solver).plan])
    solver.tasks.clear()
    solver._emergency_sync_reservations()
    assert set(PRIMARY) <= solver.op_data.emergency_reserved_agents
    state["next_read"] = NOW + timedelta(hours=1)
    solver.plan_metadata = MagicMock()
    solver._emergency_update_targets = MagicMock()
    solver._emergency_ready = MagicMock(return_value=False)
    solver._open_emergency_beds = MagicMock()
    solver._emergency_replan_releases = MagicMock()

    def plan_beds(current_state):
        assert not set(PRIMARY) & solver.op_data.emergency_reserved_agents

    solver._emergency_plan_beds = MagicMock(side_effect=plan_beds)
    solver._emergency_tick()
    solver._emergency_plan_beds.assert_called_once_with(state)


@pytest.mark.parametrize("offset,replace", [(-0.01, True), (0, False), (0.01, False)])
def test_rescue_worker_rotates_only_below_personal_rescue_line(
    staffing, offset, replace
):
    from arknights_mower.utils.operators import Operator

    solver, state = staffing.solver, staffing.state
    solver.op_data = solver.op_data.project_arrangements([state["rescue_plan"]])
    data = solver.op_data
    state["staffing_complete"] = True
    state["phase"] = "recovering"
    room = next(iter(state["rescue_plan"]))
    state["worker_replacements"] = {room: [["杜林"]]}
    data.add(Operator("杜林", "", mood=24, time_stamp=NOW))
    op = data.operators[COVERS[0]]
    op.lower_limit, op.upper_limit = 4, 20
    op.mood = data.rescue_mood_threshold(op) + offset
    assert op.mood < data.resting_mood_threshold(op)
    assert solver._emergency_replace_low_workers() is replace


@pytest.mark.parametrize("normal_member", [False, True])
def test_departed_rescue_workers_can_fill_beds_only_when_in_normal_roster(
    staffing, normal_member
):
    from arknights_mower.utils.dorm_candidates import (
        dorm_candidates,
        dorm_task_reservations,
    )
    from arknights_mower.utils.operators import Operator

    solver, state = staffing.solver, staffing.state
    name = COVERS[0] if normal_member else "杜林"
    if not normal_member:
        solver.op_data.add(Operator(name, "", mood=0, time_stamp=NOW))
    op = solver.op_data.operators[name]
    op._current_room, op.current_index, op.mood = "", -1, 0
    state["standby_workers"] = [name]
    solver._emergency_sync_reservations()
    reserved, _ = dorm_task_reservations(solver.op_data, [])
    candidates = dorm_candidates(solver.op_data, reserved)
    assert (name in candidates.recovering) is normal_member
    # 专项任务预约仍保护正常表中出现的离岗干员。
    task = SchedulerTask(task_plan={"central": [name]})
    reserved, _ = dorm_task_reservations(solver.op_data, [task])
    assert name not in dorm_candidates(solver.op_data, reserved).recovering
