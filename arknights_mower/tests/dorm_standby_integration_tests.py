"""宿舍绑组与缺床候补同时启用时的换班、纠错及回班回归。"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.group_resting_capacity_tests import (
    COVERS,
    DEEP,
    apply_plan,
    occupy_beds,
)
from arknights_mower.tests.group_resting_capacity_tests import (
    solver as standby_solver,  # noqa: F401
)
from arknights_mower.utils.scheduler_task import TaskTypes, plan_metadata, try_reorder


@pytest.fixture
def combined_solver(standby_solver):  # noqa: F811
    solver = standby_solver
    plan = solver.global_plan["default_plan"]
    resident = plan.plan["dormitory_1"][0]
    resident.group = "深海"
    resident.replacement = ["隐德来希"]
    # 宿舍常驻成员即使也被填写进候补名单，仍只能跟随宿舍绑组换班。
    plan.config.resting_standby.append(resident.agent)
    observed = {room: solver.op_data.get_current_room(room, True) for room in plan.plan}
    assert solver.initialize_operators() is None
    apply_plan(solver, observed)
    for op in solver.op_data.operators.values():
        op.time_stamp = datetime.now()
        op.mood = 20
    solver.op_data.operators[DEEP[0]].mood = 0
    solver.total_agent = [solver.op_data.operators[name] for name in DEEP]
    return solver


def shift_off(solver):
    plan = solver.resting()
    assert plan["dormitory_1"][0] == "隐德来希"
    assert set(COVERS) <= {name for names in plan.values() for name in names}
    beds = try_reorder(solver.op_data, plan)
    apply_plan(solver, plan)
    apply_plan(solver, beds)
    solver.tasks = []


@pytest.mark.parametrize("occupants", ["high", "low", "replacement"])
def test_combined_group_round_trip_preserves_other_beds(combined_solver, occupants):
    solver = combined_solver
    data = solver.op_data
    before = occupy_beds(solver, occupants)
    shift_off(solver)
    assert data.operators["塑心"].resting_priority != "standby"
    assert data.operators["塑心"].current_room == ""
    assert not data.is_group_standby("塑心")
    expected = set(DEEP[1:]) if occupants != "replacement" else set()
    assert {name for name in DEEP if data.is_group_standby(name)} == expected
    assert "塑心" not in {bed.name for bed in data.dorm}
    if occupants != "replacement":
        assert [(bed.position, bed.name, bed.time) for bed in data.dorm[1:]] == before
    for _ in range(3):
        assert solver.agent_get_mood() is None
        assert solver.resting() == {}
        assert solver.tasks == []
    back = [
        task
        for task in plan_metadata(data, [])
        if task.type == TaskTypes.SHIFT_ON and DEEP[0] in task.plan.get("central", [])
    ]
    assert len(back) == 1
    assert back[0].plan["dormitory_1"][0] == "塑心"
    assert set(DEEP) <= {name for names in back[0].plan.values() for name in names}
    apply_plan(solver, back[0].plan)
    assert solver.agent_get_mood(skip_dorm=True) is None
    assert not any(data.is_group_standby(name) for name in DEEP)
    assert data.operators["隐德来希"].current_room == ""
    solver.enter_room.assert_not_called()


def test_combined_group_preserves_priority_and_ignores_absent_mood(
    combined_solver, monkeypatch
):
    solver = combined_solver
    data = solver.op_data
    order = data.groups["深海"].copy()
    original = {name: data.operators[name].resting_priority for name in order}
    with monkeypatch.context() as priority_patch:
        for name in ["塑心", *DEEP[1:]]:
            priority_patch.setattr(
                data.operators[name],
                "current_mood",
                MagicMock(side_effect=AssertionError("must not compare excluded mood")),
            )
        solver.rearrange_resting_priority("深海")
        assert data.groups["深海"] == order
        assert {
            name: data.operators[name].resting_priority for name in order
        } == original
    occupy_beds(solver, "low")
    shift_off(solver)
    for name in ["塑心", *DEEP[1:]]:
        data.operators[name].time_stamp = None
        monkeypatch.setattr(
            data.operators[name],
            "current_mood",
            MagicMock(side_effect=AssertionError("absent mood is not work mood")),
        )
    assert data.average_mood() == 0
    assert solver.agent_get_mood() is None
    assert plan_metadata(data, [])


def test_combined_group_recovers_missing_dorm_cover_without_recalling_standby(
    combined_solver,
):
    solver = combined_solver
    occupy_beds(solver, "low")
    shift_off(solver)
    # 模拟宿舍换人未完成，但工作成员已正常下班。
    apply_plan(
        solver, {"dormitory_1": ["塑心", "Current", "Current", "Current", "Current"]}
    )
    assert solver.agent_get_mood() == "self_correction"
    correction = solver.tasks.pop().plan
    assert correction == {
        "dormitory_1": ["隐德来希", "Current", "Current", "Current", "Current"]
    }
    apply_plan(solver, correction)
    assert solver.agent_get_mood() is None
    assert all(solver.op_data.is_group_standby(name) for name in DEEP[1:])


def test_combined_group_unavailable_dorm_cover_leaves_beds_unchanged(combined_solver):
    solver = combined_solver
    data = solver.op_data
    occupy_beds(solver, "low")
    cover = data.operators["隐德来希"]
    cover.current_room, cover.current_index = "train", 0
    before = [(bed.name, bed.time) for bed in data.dorm]
    plan, replacements = {}, []
    solver.get_resting_plan(data.groups["深海"], replacements, plan, 0)
    assert plan == {}
    assert replacements == []
    assert [(bed.name, bed.time) for bed in data.dorm] == before
