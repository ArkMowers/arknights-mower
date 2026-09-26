"""Consecutive workshop tasks share one staff restoration."""

from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils import config, workshop_automation
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def batch(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 9, 10, 10)

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(config.conf, "enable_mastery", False)
    snapshot = SimpleNamespace()
    snapshots = MagicMock(return_value=snapshot)
    monkeypatch.setattr(workshop_automation, "workshop_task_snapshot", snapshots)
    errors = MagicMock()
    monkeypatch.setattr(base, "save_exception", errors)
    solver = object.__new__(base.BaseSchedulerSolver)
    rooms = {
        "factory": ["特克诺"],
        "dormitory_1": ["蜜莓", "年", "空爆", "同寝干员", "宿管"],
    }
    solver.op_data = SimpleNamespace(
        plan=deepcopy(rooms),
        operators={
            name: SimpleNamespace(current_room=room, current_index=i, mood=24)
            for room, names in rooms.items()
            for i, name in enumerate(names)
        },
    )
    solver.tasks = [
        SchedulerTask(
            time=Clock.now() + timedelta(seconds=i * 2),
            task_type=TaskTypes.WORKSHOP,
            meta_data=name,
        )
        for i, name in enumerate(["蜜莓", "年", "空爆"])
    ]
    solver.task = solver.tasks[0]
    solver.enter_room = MagicMock()
    solver.find = MagicMock(return_value=True)
    solver.backup_plan_solver = MagicMock()
    arrangements = []
    crafts = []

    def arrange(plan):
        arrangements.append(deepcopy(plan))
        for room, names in plan.items():
            for i, name in enumerate(names):
                if name == "Current":
                    continue
                for op in solver.op_data.operators.values():
                    if op.current_room == room and op.current_index == i:
                        op.current_room, op.current_index = "", -1
                op = solver.op_data.operators[name]
                op.current_room, op.current_index = room, i

    def craft(name, snapshot):
        assert solver.task.meta_data == name
        assert solver.op_data.operators[name].current_room == "factory"
        crafts.append(name)
        solver.op_data.operators[name].mood = 0
        Clock.current += timedelta(seconds=30)

    solver.agent_arrange = MagicMock(side_effect=arrange)
    solver.generate_product = MagicMock(side_effect=craft)
    return SimpleNamespace(
        solver=solver,
        clock=Clock,
        crafts=crafts,
        arrangements=arrangements,
        errors=errors,
        snapshots=snapshots,
    )


def test_consecutive_operators_restore_factory_and_shared_dorm_only_once(batch):
    batch.solver.infra_main()
    assert batch.crafts == ["蜜莓", "年", "空爆"]
    assert batch.arrangements == [
        {"factory": ["蜜莓"]},
        {"factory": ["年"]},
        {"factory": ["空爆"]},
        {
            "factory": ["特克诺"],
            "dormitory_1": ["蜜莓", "年", "空爆", "Current", "Current"],
        },
    ]
    assert batch.solver.tasks == []
    assert batch.solver.task is None
    for room, names in batch.solver.op_data.plan.items():
        for i, name in enumerate(names):
            op = batch.solver.op_data.operators[name]
            assert (op.current_room, op.current_index) == (room, i)
    batch.errors.assert_not_called()


@pytest.mark.parametrize("boundary", ["other", "future", "plan", "release"])
def test_batch_stops_at_task_boundary(batch, boundary):
    solver = batch.solver
    if boundary == "other":
        solver.tasks.insert(
            1,
            SchedulerTask(
                time=batch.clock.now() + timedelta(seconds=1),
                task_type=TaskTypes.SHIFT_ON,
            ),
        )
    elif boundary == "future":
        for task in solver.tasks[1:]:
            task.time += timedelta(hours=1)
    elif boundary == "plan":
        solver.tasks[1].plan = {"factory": ["年"]}
    else:
        solver.task.type = TaskTypes.RELEASE_DORM
    pending = solver.tasks[1:]
    solver.craft_material()
    assert batch.crafts == ["蜜莓"]
    assert len(batch.arrangements) == 2
    assert batch.arrangements[-1]["factory"] == ["特克诺"]
    assert all(any(t is task for t in solver.tasks) for task in pending)
    batch.errors.assert_not_called()


@pytest.mark.parametrize("skip", ["stale", "exhausted"])
def test_skipped_middle_task_does_not_restore_early(batch, skip):
    if skip == "stale":
        batch.snapshots.side_effect = [SimpleNamespace(), None, SimpleNamespace()]
    else:
        op = batch.solver.op_data.operators["年"]
        op.mood, op.current_room, op.current_index = 0, "", -1
    batch.solver.infra_main()
    assert batch.crafts == ["蜜莓", "空爆"]
    assert len(batch.arrangements) == 3
    assert batch.arrangements[-1]["dormitory_1"] == [
        "蜜莓",
        "Current",
        "空爆",
        "Current",
        "Current",
    ]
    assert batch.solver.tasks == []
    batch.errors.assert_not_called()


def test_original_factory_operator_can_also_craft_in_the_batch(batch):
    batch.solver.tasks[1].meta_data = "特克诺"
    batch.solver.infra_main()
    assert batch.crafts == ["蜜莓", "特克诺", "空爆"]
    assert len(batch.arrangements) == 4
    assert batch.arrangements[-1]["factory"] == ["特克诺"]
    batch.errors.assert_not_called()


@pytest.mark.parametrize("empty_factory", [False, True])
def test_single_resident_operator_does_not_need_restoration(batch, empty_factory):
    solver = batch.solver
    if empty_factory:
        resident = solver.op_data.operators["特克诺"]
        resident.current_room, resident.current_index = "", -1
    else:
        solver.task.meta_data = "特克诺"
    solver.tasks[:] = solver.tasks[:1]
    solver.infra_main()
    assert len(batch.arrangements) == 1
    batch.errors.assert_not_called()


def test_empty_factory_keeps_first_operator_and_restores_other_borrowed_staff(batch):
    resident = batch.solver.op_data.operators["特克诺"]
    resident.current_room, resident.current_index = "", -1
    batch.solver.infra_main()
    assert batch.crafts == ["蜜莓", "年", "空爆"]
    assert batch.arrangements[-1] == {
        "factory": ["蜜莓"],
        "dormitory_1": ["Current", "年", "空爆", "Current", "Current"],
    }
    batch.errors.assert_not_called()


@pytest.mark.parametrize("change", ["remove", "postpone", "insert", "handoff"])
def test_batch_rechecks_live_queue_before_switching(batch, monkeypatch, change):
    solver = batch.solver
    craft = solver.generate_product.side_effect

    def update_queue(name, snapshot):
        craft(name, snapshot)
        if change == "remove":
            solver.tasks[:] = solver.tasks[:1]
        elif change == "postpone":
            for task in solver.tasks[1:]:
                task.time += timedelta(hours=1)
        else:
            solver.tasks.append(
                SchedulerTask(
                    time=batch.clock.now()
                    + timedelta(seconds=60 if change == "handoff" else -60),
                    task_type=TaskTypes.SWAP_SUPPORT
                    if change == "handoff"
                    else TaskTypes.SHIFT_ON,
                )
            )

    if change == "handoff":
        monkeypatch.setattr(config.conf, "enable_mastery", True)
    solver.generate_product.side_effect = update_queue
    solver.craft_material()
    assert batch.crafts == ["蜜莓"]
    assert len(batch.arrangements) == 2
    batch.errors.assert_not_called()


def test_failure_restores_all_borrowed_operators_and_keeps_unfinished_tasks(batch):
    solver = batch.solver
    craft = solver.generate_product.side_effect

    def fail_second(name, snapshot):
        if name == "年":
            raise RuntimeError("加工失败")
        craft(name, snapshot)

    solver.generate_product.side_effect = fail_second
    pending = solver.tasks[1:]
    solver.infra_main()
    assert batch.crafts == ["蜜莓"]
    assert batch.arrangements[-1] == {
        "factory": ["特克诺"],
        "dormitory_1": ["蜜莓", "年", "Current", "Current", "Current"],
    }
    assert all(any(t is task for t in solver.tasks) for task in pending)
    batch.errors.assert_called_once()


def test_equal_task_objects_are_consumed_by_identity(batch):
    for task in batch.solver.tasks:
        task.time = batch.clock.now()
    assert batch.solver.tasks[0] == batch.solver.tasks[1]
    batch.solver.infra_main()
    assert batch.crafts == ["蜜莓", "年", "空爆"]
    assert batch.solver.tasks == []


def test_stop_signal_does_not_switch_to_another_operator(batch):
    first = batch.solver.task
    batch.solver.generate_product.side_effect = base.MowerExit()
    with pytest.raises(base.MowerExit):
        batch.solver.craft_material()
    assert batch.solver.task is first
    assert len(batch.solver.tasks) == 3
    assert batch.arrangements == [{"factory": ["蜜莓"]}]
    batch.errors.assert_not_called()
