"""上下班直接执行副表收敛后的最终阵容，避免红松/深海先换错站再纠错。"""

import copy
import pickle
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils import config
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.mark.parametrize("state", ["missing", "none", "legacy"])
def test_backup_guard_preserves_legacy_dispatch_before_operators_are_ready(state):
    instance = object.__new__(base.BaseSchedulerSolver)
    if state != "missing":
        instance.op_data = (
            None if state == "none" else SimpleNamespace(experimental_dorm_logic=False)
        )
    instance._legacy_backup_plan_solver = MagicMock(return_value=False)
    assert instance.backup_plan_solver() is False
    instance._legacy_backup_plan_solver.assert_called_once()


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = Operators(
        {
            "default_plan": Plan(
                {
                    "central": [Room("薇薇安娜", "红松", ["陈"])],
                    "room_1_2": [
                        Room("野鬃", "红松", ["酒神"]),
                        Room("灰毫", "红松", ["食铁兽"]),
                    ],
                    "room_2_2": [
                        Room("乌尔比安", "深海", ["苍苔"]),
                        Room("安哲拉", "深海", ["引星棘刺"]),
                    ],
                    "dormitory_1": [
                        Room("杜林", "", []),
                        Room("桃金娘", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig("", "", "", experimental_dorm_logic=True),
            ),
            "backup_plans": [
                Plan(
                    {
                        "room_1_2": [
                            Room("乌尔比安", "深海", ["酒神"]),
                            Room("安哲拉", "深海", ["食铁兽"]),
                        ],
                        "room_2_2": [
                            Room("野鬃", "红松", ["苍苔"]),
                            Room("灰毫", "红松", ["引星棘刺"]),
                        ],
                    },
                    PlanConfig("", "", ""),
                    trigger=LogicExpression(
                        "op_data.operators['薇薇安娜'].is_working()", "!=", "True"
                    ),
                    task={
                        "room_1_2": ["乌尔比安", "安哲拉"],
                        "room_2_2": ["苍苔", "引星棘刺"],
                    },
                )
            ],
        }
    )
    assert instance.op_data.init_and_validate() is None
    for op in instance.op_data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 12, datetime.now()
    instance.op_data.first_init = False
    instance.tasks, instance.task = [], None
    instance._sync_run_order_tasks = MagicMock()
    instance.queue_product_switches = MagicMock()
    instance.find = MagicMock(return_value=True)
    instance.skip = MagicMock()
    instance.refresh_connecting = False
    monkeypatch.setattr(
        Operators, "current_room_changed_callback", instance.current_room_changed
    )
    return instance


def downshift(solver, kind=TaskTypes.SHIFT_OFF):
    task = SchedulerTask(
        task_type=kind,
        task_plan={
            "central": ["陈"],
            "room_1_2": ["酒神", "食铁兽"],
            "dormitory_1": ["Current", "Current", "薇薇安娜", "野鬃", "灰毫"],
        },
    )
    solver.tasks = [task]
    solver.task = task
    return task


def resting(solver):
    data = solver.op_data
    assert data.swap_plan([True], refresh=True) is None
    solver.op_data = data.project_arrangements(
        [
            {
                "central": ["陈"],
                "room_1_2": ["乌尔比安", "安哲拉"],
                "room_2_2": ["苍苔", "引星棘刺"],
                "dormitory_1": ["杜林", "桃金娘", "薇薇安娜", "野鬃", "灰毫"],
            }
        ]
    )
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={
            "central": ["薇薇安娜"],
            "room_2_2": ["野鬃", "灰毫"],
        },
    )
    solver.tasks = [task]
    solver.task = task
    return task


def positions(data):
    return {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }


@pytest.mark.parametrize("kind", [TaskTypes.SHIFT_OFF, TaskTypes.EXHAUST_OFF])
def test_downshift_merges_backup_actions_without_first_installing_replacements(
    solver, kind
):
    task = downshift(solver, kind)
    before = positions(solver.op_data)
    solver._prepare_shift_backup(task)
    assert task.plan["room_1_2"] == ["乌尔比安", "安哲拉"]
    assert task.plan["room_2_2"] == ["苍苔", "引星棘刺"]
    assert task.plan["dormitory_1"][2:] == ["薇薇安娜", "野鬃", "灰毫"]
    assert task.backup_shift_conditions == [True]
    assert solver.op_data.plan_condition == [False]
    assert positions(solver.op_data) == before
    assert solver.tasks == [task]


def test_upshift_skips_backup_posts_and_returns_directly_to_main_posts(solver):
    task = resting(solver)
    before = positions(solver.op_data)
    solver._prepare_shift_backup(task)
    assert task.plan["room_1_2"] == ["野鬃", "灰毫"]
    assert task.plan["room_2_2"] == ["乌尔比安", "安哲拉"]
    assert task.backup_shift_conditions == [False]
    assert positions(solver.op_data) == before
    assert solver.op_data.plan_condition == [True]
    names = [
        name
        for agents in task.plan.values()
        for name in agents
        if name not in ("Current", "Free", "")
    ]
    assert len(names) == len(set(names))


def test_backup_actions_can_trigger_another_backup_before_any_real_arrangement(solver):
    bp = Plan(
        {},
        PlanConfig("", "", ""),
        trigger=LogicExpression(
            "op_data.operators['乌尔比安'].current_room", "==", "'room_1_2'"
        ),
        task={"dormitory_1": ["桃金娘", "杜林", "Current", "Current", "Current"]},
    )
    solver.op_data.backup_plans.append(bp)
    solver.op_data.plan_condition.append(False)
    task = downshift(solver)
    solver._prepare_shift_backup(task)
    assert task.backup_shift_conditions == [True, True]
    assert task.plan["dormitory_1"][:2] == ["桃金娘", "杜林"]
    assert solver.op_data.plan_condition == [False, False]


def test_cycle_keeps_live_state_queue_and_original_task_unchanged(solver):
    solver.op_data.backup_plans[0].task["central"] = ["薇薇安娜"]
    task = downshift(solver)
    original = copy.deepcopy(task.plan)
    before = positions(solver.op_data)
    with pytest.raises(ValueError, match="循环"):
        solver._prepare_shift_backup(task)
    assert task.plan == original
    assert solver.op_data.plan_condition == [False]
    assert positions(solver.op_data) == before
    assert not hasattr(task, "backup_shift_active")


def test_activation_changes_configuration_but_never_fakes_actual_positions(solver):
    task = resting(solver)
    before = positions(solver.op_data)
    solver._prepare_shift_backup(task)
    solver._activate_shift_backup(task)
    assert solver.op_data.plan_condition == [False]
    assert positions(solver.op_data) == before
    assert not solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [False]
    # 宿舍延期或换人失败后重试，保持同一个最终方案。
    expected = copy.deepcopy(task.plan)
    solver._prepare_shift_backup(task)
    assert task.plan == expected
    solver.plan_metadata()
    assert solver.tasks == [task]


def test_another_shift_waits_for_partially_completed_transaction(solver):
    active = resting(solver)
    solver._prepare_shift_backup(active)
    solver._activate_shift_backup(active)
    other = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan={"central": ["陈"]})
    solver.tasks.append(other)
    with pytest.raises(base.ProductSwitchDeferred, match="上一轮"):
        solver._prepare_shift_backup(other)
    assert other.plan == {"central": ["陈"]}


def test_product_delay_keeps_real_configuration_and_all_actions_pending(solver):
    task = downshift(solver)
    intent = copy.deepcopy(task.plan)
    before = positions(solver.op_data)
    solver._switch_products_before_arrangement = MagicMock(
        side_effect=base.ProductSwitchDeferred("等待切产物", minutes=5)
    )
    solver.agent_arrange = MagicMock()
    solver.infra_main()
    assert not getattr(task, "backup_shift_active", False)
    assert task in solver.tasks
    assert task.backup_shift_intent == intent
    assert task.time > datetime.now() + timedelta(minutes=4)
    assert solver.op_data.plan_condition == [False]
    assert positions(solver.op_data) == before
    solver.agent_arrange.assert_not_called()


def test_failed_arrangement_retains_final_task_for_retry(solver):
    task = resting(solver)
    solver.agent_arrange = MagicMock(side_effect=RuntimeError("读屏失败"))
    solver.infra_main()
    assert task in solver.tasks
    assert task.backup_shift_active
    assert not solver.backup_plan_solver()
    assert task.plan["room_1_2"] == ["野鬃", "灰毫"]


def test_restart_restores_active_transaction_configuration_without_replaying_intent(
    solver,
):
    task = downshift(solver)
    solver._prepare_shift_backup(task)
    solver._activate_shift_backup(task)
    task.plan.pop("central")  # 已确认的工作房间不应在重启后重做。
    task = pickle.loads(pickle.dumps(task))
    solver.tasks = [task]
    solver.task = task
    assert solver.op_data.swap_plan([False], refresh=True) is None
    before = positions(solver.op_data)
    solver._prepare_shift_backup(task)
    solver._activate_shift_backup(task)
    assert solver.op_data.plan_condition == [True]
    assert "central" not in task.plan
    assert positions(solver.op_data) == before


def test_prepared_shift_waits_if_fiammetta_becomes_due(solver):
    task = downshift(solver)
    solver._prepare_shift_backup(task)
    solver.tasks.append(SchedulerTask(task_type=TaskTypes.FIAMMETTA))
    with pytest.raises(base.ProductSwitchDeferred, match="肥鸭"):
        solver._prepare_shift_backup(task)
    assert solver.op_data.plan_condition == [False]


def test_cancel_old_return_also_invalidates_saved_simulation_intent(solver):
    task = resting(solver)
    solver._prepare_shift_backup(task)
    solver.task = None
    solver.op_data.update_detail("野鬃", 20, "room_1_2", 0, True)
    assert all("野鬃" not in names for names in task.plan.values())
    assert not hasattr(task, "backup_shift_intent")
    assert not hasattr(task, "backup_shift_conditions")
    solver._prepare_shift_backup(task)
    assert all(
        "野鬃" not in names or room == "room_1_2" for room, names in task.plan.items()
    )


@pytest.mark.parametrize("direction", [downshift, resting])
def test_infra_main_executes_only_one_final_arrangement(solver, direction):
    task = direction(solver)
    seen = []

    def arrange(plan, get_time):
        seen.append(copy.deepcopy(plan))
        solver.op_data = solver.op_data.project_arrangements([plan])
        return True

    solver.agent_arrange = MagicMock(side_effect=arrange)
    solver.infra_main()
    assert len(seen) == 1
    expected = ["乌尔比安", "安哲拉"] if direction is downshift else ["野鬃", "灰毫"]
    assert seen[0]["room_1_2"] == expected
    assert not any(t.meta_data == "副表内存收敛" for t in solver.tasks)
    assert not task.backup_shift_active


def test_product_lock_keeps_converged_shift_as_one_transaction(solver):
    task = downshift(solver)
    solver._prepare_shift_backup(task)
    solver._reserve_deferred_product_shift(task, {("central", 0)})
    assert solver.tasks == [task]
    assert task.product_lock_slots == {
        (room, index)
        for room, names in task.plan.items()
        for index, name in enumerate(names)
        if name != "Current"
    }
    assert solver.op_data.plan_condition == [False]


@pytest.mark.parametrize("kind", [TaskTypes.FIAMMETTA, TaskTypes.RUN_ORDER])
def test_special_tasks_are_not_simulated_as_normal_shifts(solver, kind):
    task = downshift(solver, kind)
    original = copy.deepcopy(task.plan)
    solver._prepare_shift_backup(task)
    assert task.plan == original
    assert not hasattr(task, "backup_shift_conditions")


def test_due_fiammetta_and_legacy_mode_keep_original_behavior(solver):
    task = downshift(solver)
    solver.tasks.append(
        SchedulerTask(
            task_type=TaskTypes.FIAMMETTA, time=datetime.now() - timedelta(seconds=1)
        )
    )
    solver._prepare_shift_backup(task)
    assert not hasattr(task, "backup_shift_conditions")
    solver.tasks.pop()
    solver.op_data.config.experimental_dorm_logic = False
    solver._prepare_shift_backup(task)
    assert not hasattr(task, "backup_shift_conditions")
