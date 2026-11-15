import copy
import pickle
from datetime import datetime

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests import dorm_order_transition_tests, dorm_release_tests
from arknights_mower.utils import config
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.operators import Operator, Operators, build_global_plan
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes, plan_metadata

op_data = dorm_release_tests.op_data
solver = dorm_order_transition_tests.solver


@pytest.mark.parametrize("main", [False, True])
def test_backup_switch_layers_round_trip_and_restore_without_persisting(
    monkeypatch, main
):
    conf = config.Conf(free_room=main)
    monkeypatch.setattr(config, "conf", conf)
    model = PlanModel.model_validate(
        {
            "plan1": {},
            "backup_plans": [
                {"plan": {}, "conf": {"free_room": True}},
                {"plan": {}, "conf": {"free_room": False}},
                {"plan": {}, "conf": {"free_room": None}},
                {"plan": {}, "conf": {}},
            ],
        }
    )
    model = PlanModel.model_validate_json(model.model_dump_json())
    before = copy.deepcopy(model.model_dump())
    data = Operators(build_global_plan(plan_model=model, conf_model=conf))
    for flags, expected in [
        ([False, False, False, False], main),
        ([True, False, True, True], True),
        ([True, True, True, True], False),
        ([True, False, False, False], True),
        ([False, True, False, False], False),
        ([False, False, True, True], main),
    ]:
        assert data.swap_plan(flags) is None
        assert data.config.free_room is expected
        assert conf.free_room is main
    assert model.model_dump() == before


def release(name="空爆", strict=False):
    return SchedulerTask(
        time=datetime.now(),
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_1": ["Current"] * 4 + ["Free"]},
        meta_data=name,
        strict_mood_limit=strict,
    )


def test_disabled_switch_rechecks_saved_release_without_touching_return(op_data):
    instance = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
    instance.op_data = op_data
    returning = SchedulerTask(task_type=TaskTypes.SHIFT_ON, meta_data="dorm0")
    instance.tasks = [returning]
    task = release()
    op_data.config.free_room = False
    assert instance.prepare_release_dorm(task) is False
    assert task.plan == {}
    assert instance.tasks == [returning]
    assert returning.meta_data == "dorm0"
    assert op_data.dorm[0].name == "空爆"
    op_data.config.free_room = True
    regenerated = plan_metadata(op_data, [])
    assert any(
        t.type == TaskTypes.RELEASE_DORM and t.meta_data == "空爆" for t in regenerated
    )


def test_disabled_switch_keeps_personal_limit_release(op_data):
    instance = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
    instance.op_data, instance.tasks = op_data, []
    occupant = op_data.operators["空爆"]
    op_data.plan["meeting"][0].replacement.append("空爆")
    occupant.upper_limit = occupant.mood = 12
    op_data.config.operator_mood_limits[occupant.name] = {"lower": 0, "upper": 12}
    op_data.config.free_room = False
    task = release(strict=True)
    assert instance.prepare_release_dorm(task) is True
    assert task.plan


@pytest.mark.parametrize("path", ["cached", "shift"])
def test_backup_disable_cancels_only_ordinary_releases(solver, path):
    data = solver.op_data
    data.global_plan["default_plan"].config.free_room = True
    data.backup_plans[0].config.dorm_order = data.config.dorm_order.copy()
    data.backup_plans[0].config.free_room = False
    data.global_plan["default_plan"].config.operator_mood_limits["芬"] = {
        "lower": 0,
        "upper": 12,
    }
    ordinary, strict = release(), release("芬", strict=True)
    strict.plan = {"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]}
    strict.mood_limit = 12
    unrelated = SchedulerTask(task_type=TaskTypes.SKLAND)
    solver.tasks = [ordinary, strict, unrelated]
    if path == "cached":
        solver.backup_plan_solver()
    else:
        task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
        task.backup_shift_conditions = [True]
        solver._activate_shift_backup(task)
    assert data.config.free_room is False
    assert not any(t is ordinary for t in solver.tasks)
    assert any(t.strict_mood_limit and t.meta_data == "芬" for t in solver.tasks)
    assert any(t is unrelated for t in solver.tasks)


@pytest.mark.parametrize("merged", [False, True])
def test_disabled_switch_rejects_single_and_merged_release_after_cache_restore(
    op_data, merged
):
    instance = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
    instance.op_data, instance.tasks = op_data, []
    op_data.config.free_room = False
    task = release()
    if merged:
        task.release_targets = {"空爆": ("dormitory_1", 4)}
    task = pickle.loads(pickle.dumps(task))
    assert instance.prepare_release_dorm(task) is False
    assert task.plan == {}
    assert op_data.operators["空爆"].current_room == "dormitory_1"


@pytest.mark.parametrize("path", ["cached", "shift"])
def test_backup_enable_immediately_plans_release_and_exit_removes_it(solver, path):
    data = solver.op_data
    data.global_plan["default_plan"].config.free_room = False
    data.config.free_room = False
    data.backup_plans[0].config.free_room = True
    data.backup_plans[0].config.dorm_order = data.config.dorm_order.copy()
    data.add(Operator("空爆", ""))
    op = data.operators["空爆"]
    op._current_room, op.current_index = "dormitory_1", 3
    op.mood, op.time_stamp = 24, datetime.now()
    bed = next(b for b in data.dorm if b.position == ("dormitory_1", 3))
    bed.name, bed.time = op.name, datetime.now()
    unrelated = SchedulerTask(task_type=TaskTypes.SKLAND)
    solver.tasks = [unrelated]
    if path == "cached":
        solver.backup_plan_solver()
    else:
        task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
        task.backup_shift_conditions = [True]
        solver.tasks.append(task)
        solver._activate_shift_backup(task)
        assert any(t is task for t in solver.tasks)
    releases = [
        t
        for t in solver.tasks
        if t.type == TaskTypes.RELEASE_DORM and "空爆" in t.release_dorm_targets()
    ]
    assert len(releases) == 1
    assert releases[0].release_dorm_targets()["空爆"] == ("dormitory_1", 3)
    assert releases[0].time <= datetime.now()
    assert any(t is unrelated for t in solver.tasks)
    if path == "cached":
        from arknights_mower.utils.logic_expression import LogicExpression

        data.backup_plans[0].trigger = LogicExpression("False", "==", "True")
        solver.backup_plan_solver()
    else:
        task.backup_shift_conditions = [False]
        task.backup_shift_active = False
        solver._activate_shift_backup(task)
    assert not any(
        t.type == TaskTypes.RELEASE_DORM and not t.strict_mood_limit
        for t in solver.tasks
    )
    assert any(t is unrelated for t in solver.tasks)
