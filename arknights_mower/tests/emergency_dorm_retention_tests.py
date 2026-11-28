"""救急达标和重分床保留宿舍住客，并允许正常交接。"""

import copy
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests.automatic_rescue_tests import make_episode
from arknights_mower.tests.automatic_rescue_tests import offline as offline
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.emergency_recovery import emergency_dorm_plan
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

ROOM = "dormitory_1"


@pytest.fixture(params=[False, True], ids=["observed", "calculated"])
def instance(solver, request, monkeypatch):
    if request.param:
        monkeypatch.setattr(
            Operators, "mood_calculation_enabled", property(lambda self: True)
        )
        monkeypatch.setattr(
            Operators,
            "calculated_mood",
            lambda self, name, now=None: (
                self.operators[name].mood if name in self.operators else None
            ),
        )
    make_episode(solver)
    return solver


@pytest.mark.parametrize("personal_limit", [False, True])
@pytest.mark.parametrize("requested", [2, 3])
@pytest.mark.parametrize("stale_bed", [False, True])
def test_entry_reallocation_keeps_full_retained_resident(
    instance, personal_limit, requested, stale_bed
):
    state, data = instance.emergency_state, instance.op_data
    state["targets"] = {name: 16 for name in PRIMARY[:requested]}
    arrangement = {data.operators[name].room: [""] for name in PRIMARY[:requested]}
    arrangement[ROOM] = ["冰酿", "闪灵", COVERS[0], "", PRIMARY[0]]
    instance.op_data = data = data.project_arrangements([arrangement])
    data.config.free_room_exclusions = [COVERS[0]]
    for name in PRIMARY[:requested]:
        data.operators[name].mood = 8
    if personal_limit:
        data.config.operator_mood_limits[COVERS[0]] = {"upper": 12}
        data.operators[COVERS[0]].upper_limit = 12
    data.operators[COVERS[0]].mood = data.operators[COVERS[0]].upper_limit
    if stale_bed:
        data.get_dorm_by_name(COVERS[0])[1].name = ""
    before = data.get_current_room(ROOM, True)

    plan = emergency_dorm_plan(data, state, reallocate=True)

    after = data.project_arrangements([plan])
    assert after.operators[COVERS[0]].is_resting()
    assert (
        len(
            [name for name in PRIMARY[:requested] if after.operators[name].is_resting()]
        )
        == 2
    )
    assert data.get_current_room(ROOM, True) == before
    assert instance.tasks == []


def test_failed_retained_reallocation_preserves_original_arrangement(
    instance, monkeypatch
):
    data = instance.op_data.project_arrangements(
        [{ROOM: ["冰酿", "闪灵", COVERS[0], "", ""]}]
    )
    instance.op_data = data
    data.config.free_room_exclusions = [COVERS[0]]
    task = SchedulerTask(time=NOW + timedelta(minutes=7), task_type=TaskTypes.RECRUIT)
    instance.tasks = [task]
    before = copy.deepcopy(vars(task)), data.get_current_room(ROOM, True)
    original = Operators._find_dorm_slot

    def find(self, name, *args, **kwargs):
        return None if name == COVERS[0] else original(self, name, *args, **kwargs)

    monkeypatch.setattr(Operators, "_find_dorm_slot", find)
    assert (
        emergency_dorm_plan(
            data, instance.emergency_state, instance.tasks, reallocate=True
        )
        == {}
    )
    assert instance.tasks == [task] and vars(task) == before[0]
    assert data.get_current_room(ROOM, True) == before[1]
    instance.emergency_state["dorm_replan_pending"] = True
    for _ in range(2):
        instance._emergency_plan_beds(instance.emergency_state)
        assert instance.tasks == [task] and vars(task) == before[0]
        assert data.get_current_room(ROOM, True) == before[1]
        assert not instance.emergency_state["dorm_replan_pending"]


def test_ready_retained_resident_cancels_old_release_and_allows_handoff(
    instance, monkeypatch
):
    state, data = instance.emergency_state, instance.op_data
    name = PRIMARY[0]
    instance.op_data = data = data.project_arrangements(
        [{ROOM: ["冰酿", "闪灵", name, "", ""]}]
    )
    data.config.free_room_exclusions = [name]
    state["targets"] = {name: 16}
    state["release_members"] = [name]
    state["release_plan"] = {ROOM: ["Current", "Current", "", "Current", "Current"]}
    instance._emergency_operation_fits = MagicMock(return_value=True)
    instance._emergency_save = MagicMock()
    instance.agent_arrange = MagicMock()
    before = data.get_current_room(ROOM, True)

    assert instance._emergency_release_ready()
    assert not instance._emergency_release_ready()
    assert state["ready_members"] == [name]
    assert "release_members" not in state and "release_plan" not in state
    assert data.get_current_room(ROOM, True) == before
    assert data.operators[name].mood == 24
    instance.agent_arrange.assert_not_called()
    assert instance.tasks == []
    assert instance._emergency_ready()

    def correction(self, **kwargs):
        op = self.op_data.operators[name]
        return {} if op.is_working() else {op.room: [name]}

    def arrange(plan, **kwargs):
        instance.op_data = instance.op_data.project_arrangements([plan])
        return True

    monkeypatch.setattr(BaseSchedulerSolver, "agent_get_mood", correction)
    instance.agent_arrange.side_effect = arrange
    instance.backup_plan_solver = MagicMock(return_value=False)
    instance._emergency_read_rooms = MagicMock(return_value=True)
    instance.plan_metadata = MagicMock()
    assert instance._emergency_restore()
    assert instance.emergency_state is None
    assert instance.op_data.operators[name].is_working()


def test_ready_retained_resident_keeps_bed_during_manager_restoration(instance):
    state, data = instance.emergency_state, instance.op_data
    name = PRIMARY[0]
    instance.op_data = data = data.project_arrangements(
        [{ROOM: [name, "闪灵", "", "", ""]}]
    )
    data.config.free_room_exclusions = [name]
    state["targets"] = {name: 16}
    state["ready_members"] = [name]

    instance._open_emergency_beds()
    instance._emergency_plan_beds(state)

    final = data.project_arrangements([task.plan for task in instance.tasks])
    assert final.operators[name].is_resting()
    assert data.plan[ROOM][0].agent == "Free"
    assert instance._emergency_ready()


def test_recovery_completion_keeps_retained_residents_pending_move(instance):
    state, data = instance.emergency_state, instance.op_data
    name = PRIMARY[0]
    instance.op_data = data = data.project_arrangements(
        [{ROOM: ["冰酿", "闪灵", name, "", ""]}]
    )
    data.config.free_room_exclusions = [name]
    state["targets"] = {name: 16}
    task = SchedulerTask(
        time=NOW + timedelta(minutes=3),
        task_plan={ROOM: ["Current", "Current", COVERS[0], name, "Current"]},
        task_type=TaskTypes.FILL_DORM,
    )
    task.emergency_dorm = True
    instance.task, instance.tasks = task, [task]
    instance._emergency_save = MagicMock()
    before = copy.deepcopy(vars(task))

    assert instance._emergency_release_ready()
    assert vars(task) == before
    assert instance.tasks == [task]
    instance.prepare_dorm_selection(task.plan[ROOM], ROOM)
    after = data.project_arrangements([task.plan])
    assert after.operators[name].is_resting()
    assert after.operators[name].current_index == 3
