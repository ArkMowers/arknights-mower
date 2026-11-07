"""离宿后的分床只依据已完成房间的实际驻员变化。"""

import copy
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import (
    dorm_arrangement_observation_tests,
    dorm_empty_release_tests,
)
from arknights_mower.utils.operators import Dormitory, Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    prioritize_new_dorm_recovery,
)

incident = dorm_arrangement_observation_tests.incident
solver = dorm_empty_release_tests.solver
op_data = dorm_empty_release_tests.op_data
ROOM = dorm_empty_release_tests.ROOM
OTHER = "dormitory_2"


@pytest.fixture
def release_solver(solver, monkeypatch):
    instance, _ = solver
    data = instance.op_data
    monkeypatch.setattr(
        "arknights_mower.solvers.record.save_agent_action", lambda *a, **kw: None
    )
    data.plan[OTHER] = [Room("Free", "", [])]
    data.update_detail("红", 10, OTHER, 0, True)
    data.dorm.append(Dormitory((OTHER, 0), "红"))
    instance.tasks = [instance.task]
    return instance


@pytest.mark.parametrize("outcome", ["success", "partial", "exception"])
@pytest.mark.parametrize("donor_mood", [10, 24])
def test_retained_resident_never_creates_departure_event(
    release_solver, outcome, donor_mood
):
    instance = release_solver
    data = instance.op_data
    data.operators["红"].mood = donor_mood
    original = {room: data.get_current_room(room, True) for room in (ROOM, OTHER)}

    def arrange(plan, get_time):
        if not plan:
            return True
        instance.preserve_resting_crafters(plan[ROOM], ROOM)
        assert plan[ROOM][-1] == "空爆"
        plan.clear()
        if outcome == "exception":
            raise RuntimeError("后续操作失败")
        return outcome == "success"

    instance.agent_arrange = MagicMock(side_effect=arrange)
    if outcome == "exception":
        with pytest.raises(RuntimeError, match="后续操作失败"):
            instance.arrange_release_dorm()
    else:
        instance.arrange_release_dorm()
    assert instance.task.plan == {}
    assert data.is_full_dorm_fallback("空爆")
    assert {room: data.get_current_room(room, True) for room in original} == original
    assert instance.tasks == [instance.task]
    # 即使旧清退再次派发，也不能生成换床或补床任务。
    for _ in range(3):
        instance.task.plan = {ROOM: ["Current"] * 4 + ["Free"]}
        instance.arrange_release_dorm()
        assert instance.tasks == [instance.task]


@pytest.mark.parametrize("registered", [True, False])
@pytest.mark.parametrize("incoming_mood", [8, 24])
def test_actual_arrival_survives_release_reallocation(
    release_solver, registered, incoming_mood
):
    instance = release_solver
    data = instance.op_data
    incoming = "陈" if registered else "芬"
    if registered:
        data.add(Operator(incoming, "", mood=incoming_mood, time_stamp=datetime.now()))

    def arrange(plan, get_time):
        if not registered:
            data.add(
                Operator(incoming, "", mood=incoming_mood, time_stamp=datetime.now())
            )
        data.update_detail("空爆", 24, "", -1, True)
        data.update_detail(incoming, incoming_mood, ROOM, 4, True)
        plan.clear()
        return True

    instance.agent_arrange = MagicMock(side_effect=arrange)
    instance.arrange_release_dorm()
    assert instance.task.plan == {}
    reorders = [t.plan for t in instance.tasks if t.type == TaskTypes.RE_ORDER]
    after = data.project_arrangements(reorders)
    assert {bed.name for bed in after.dorm if bed.name} == {incoming, "红"}
    assert after.get_current_operator(ROOM, 4).name == "红"
    assert after.get_current_operator(OTHER, 0).name == incoming
    assert prioritize_new_dorm_recovery(after, {}) == {}
    assert not after.operators["空爆"].current_room
    assert data.operators[incoming].current_room == ROOM


@pytest.mark.parametrize("outcome", ["partial", "exception"])
def test_partial_release_preserves_unfinished_room_and_observed_departure(
    release_solver, outcome
):
    instance = release_solver
    data = instance.op_data
    data.operators["红"].mood = 24
    task = instance.task
    task.plan[OTHER] = ["Free"]
    task.meta_data = "空爆,红"
    task.release_targets = {"空爆": (ROOM, 4), "红": (OTHER, 0)}
    task.strict_mood_limit = True
    data.config.operator_mood_limits = {name: {"upper": 24} for name in ("空爆", "红")}
    data.plan["meeting"][0].replacement.append("空爆")
    original_time = task.time
    original = copy.deepcopy(task.plan)

    def arrange(plan, get_time):
        data.update_detail("空爆", 24, "", -1, True)
        del plan[ROOM]
        plan[OTHER][0] = "陈"
        if outcome == "exception":
            raise RuntimeError("第二间选人失败")
        return False

    instance.agent_arrange = MagicMock(side_effect=arrange)
    if outcome == "exception":
        with pytest.raises(RuntimeError, match="第二间选人失败"):
            instance.arrange_release_dorm()
    else:
        assert instance.arrange_release_dorm()[0] is False
    assert task.plan == {OTHER: original[OTHER]}
    assert task.time == original_time
    assert instance.tasks == [task]
    assert data.operators["红"].current_room == OTHER


def test_real_arrangement_skip_keeps_full_resident_without_reorder(incident):
    instance, physical, _ = incident
    data = instance.op_data
    data.operators["陈"].mood = 24
    task = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={ROOM: ["Current"] * 3 + ["Free", "Current"]},
        meta_data="芬",
    )
    instance.task, instance.tasks = task, [task]
    original = copy.deepcopy(physical)

    assert instance.arrange_release_dorm()[0] is not False

    assert physical == original
    assert instance.tasks == [task]
    assert task.plan == {}
    instance.tap_confirm.assert_not_called()


def test_observed_compaction_preserves_remaining_full_resident(release_solver):
    instance = release_solver
    data = instance.op_data
    data.plan[ROOM][3] = Room("Free", "", [])
    data.dorm.insert(0, Dormitory((ROOM, 3), "桃金娘"))
    instance.task.plan = {ROOM: ["Current"] * 3 + ["Free", "Current"]}
    instance.task.meta_data = "桃金娘"
    instance.task.strict_mood_limit = True
    data.config.operator_mood_limits = {"桃金娘": {"upper": 24}}
    data.plan["meeting"][0].replacement.append("桃金娘")

    def arrange(plan, get_time):
        data.update_detail("桃金娘", 24, "", -1, True)
        data.update_detail("空爆", 24, ROOM, 3, True)
        plan.clear()
        return True

    instance.agent_arrange = MagicMock(side_effect=arrange)
    instance.arrange_release_dorm()
    reorders = [t.plan for t in instance.tasks if t.type == TaskTypes.RE_ORDER]
    after = data.project_arrangements(reorders)
    assert {bed.name for bed in after.dorm if bed.name} == {"红", "空爆"}
    assert after.get_current_operator(ROOM, 3).name == "红"
    assert after.get_current_operator(OTHER, 0).name == "空爆"
    assert data.get_current_operator(ROOM, 3).name == "空爆"
    assert data.get_current_operator(ROOM, 4) is None


def test_observed_departure_does_not_take_reserved_donor(release_solver):
    instance = release_solver
    waiting = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={"meeting": ["红"]})
    waiting.execution_retained = True
    instance.tasks.append(waiting)

    def arrange(plan, get_time):
        instance.op_data.update_detail("空爆", 24, "", -1, True)
        plan.clear()
        return True

    instance.agent_arrange = MagicMock(side_effect=arrange)
    instance.arrange_release_dorm()
    assert instance.tasks == [instance.task, waiting]
    assert instance.op_data.operators["红"].current_room == OTHER


def test_observed_single_target_change_reranks_same_tier_residents(release_solver):
    instance = release_solver
    data = instance.op_data
    data.plan[OTHER].append(Room("Free", "", []))
    for name, mood in (("陈", 8), ("苍苔", 1)):
        data.add(Operator(name, "", mood=mood, time_stamp=datetime.now()))
        data.plan["meeting"][0].replacement.append(name)
    data.update_detail("苍苔", 1, OTHER, 1, True)
    data.dorm.append(Dormitory((OTHER, 1), "苍苔"))

    def arrange(plan, get_time):
        data.update_detail("空爆", 24, "", -1, True)
        data.update_detail("陈", 8, ROOM, 4, True)
        plan.clear()
        return True

    instance.agent_arrange = MagicMock(side_effect=arrange)
    instance.arrange_release_dorm()
    reorders = [t.plan for t in instance.tasks if t.type == TaskTypes.RE_ORDER]
    after = data.project_arrangements(reorders)
    assert after.get_current_operator(ROOM, 4).name == "苍苔"
    assert after.get_current_operator(OTHER, 0).name == "陈"
    assert after.get_current_operator(OTHER, 1).name == "红"
    assert data.get_current_operator(ROOM, 4).name == "陈"
    assert data.get_current_operator(OTHER, 0).name == "红"
