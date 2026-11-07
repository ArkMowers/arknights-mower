"""副表关闭后的实际离站保留耗尽和限定跑单刷新。"""

import pickle
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

with pytest.MonkeyPatch.context() as imports:
    imports.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

from arknights_mower.utils import config
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def solver(monkeypatch, offline_maintenance):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data = Operators(
        {
            "default_plan": Plan(
                {
                    "room_1_1": [Room("阿罗玛", "", ["引星棘刺"])],
                    "room_1_2": [Room("槐琥", "", ["砾"])],
                    "dormitory_1": [
                        Room("杜林", "", []),
                        Room("桃金娘", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig("阿罗玛", "阿罗玛", ""),
            ),
            "backup_plans": [
                Plan(
                    {},
                    PlanConfig("", "", "", refresh_drained="槐琥"),
                    trigger=LogicExpression("True", "==", "False"),
                )
            ],
        }
    )
    assert solver.op_data.init_and_validate() is None
    # PlanConfig stores parsed room suffixes in refresh_trading_config.
    solver.op_data.backup_plans[0].config.refresh_trading_config = ["槐琥room_2_1"]
    assert solver.op_data.swap_plan([True], refresh=True) is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 2, datetime.now()
    solver.op_data.first_init = False
    solver.task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"room_1_2": ["砾"]}
    )
    solver.task.backup_shift_conditions = [False]
    solver.tasks = [
        solver.task,
        SchedulerTask(
            time=datetime.now() + timedelta(hours=2),
            task_type=TaskTypes.EXHAUST_OFF,
            meta_data="阿罗玛",
        ),
    ]
    solver._sync_run_order_tasks = MagicMock()
    solver.refresh_run_order_time = MagicMock()
    monkeypatch.setattr(
        Operators, "current_room_changed_callback", solver.current_room_changed
    )
    return solver


def test_removed_refresh_rules_run_only_on_actual_departure(solver):
    task = solver.task
    deadline = solver.tasks[1]
    stamp = solver.op_data.operators["阿罗玛"].time_stamp
    solver._activate_shift_backup(task)
    assert deadline in solver.tasks
    assert solver.op_data.operators["阿罗玛"].time_stamp == stamp
    solver.refresh_run_order_time.assert_not_called()
    solver.agent_arrange = MagicMock(
        side_effect=lambda *_: setattr(
            solver.op_data.operators["槐琥"], "current_room", ""
        )
    )
    solver._arrange_with_shift_refresh_rules(task, True)
    assert deadline not in solver.tasks
    assert solver.op_data.operators["阿罗玛"].time_stamp is None
    solver.refresh_run_order_time.assert_called_once_with("room_2_1")
    assert solver._complete_group_shift(task)
    assert not hasattr(task, "backup_refresh_rules")
    solver.refresh_run_order_time.reset_mock()
    solver.op_data.operators["槐琥"].current_room = "dormitory_1"
    solver.refresh_run_order_time.assert_not_called()


def test_infra_main_dispatch_preserves_refresh_until_actual_arrangement(solver):
    task, deadline = solver.task, solver.tasks[1]
    solver.find = MagicMock(return_value=True)
    solver.skip = MagicMock()
    solver.refresh_connecting = False
    solver._prepare_shift_cycle = MagicMock()
    solver._prepare_group_shift = MagicMock()
    solver._defer_conflicting_product_shift_slots = MagicMock()
    solver._switch_products_before_arrangement = MagicMock()
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.plan_metadata = MagicMock()

    def arrange(*_):
        assert solver.op_data.plan_condition == [False]
        assert deadline in solver.tasks
        solver.op_data.operators["槐琥"].current_room = ""

    solver.agent_arrange = MagicMock(side_effect=arrange)
    solver.infra_main()
    solver.agent_arrange.assert_called_once()
    assert all(item is not deadline for item in solver.tasks)
    assert solver.op_data.operators["阿罗玛"].time_stamp is None
    solver.refresh_run_order_time.assert_called_once_with("room_2_1")
    assert not hasattr(task, "backup_refresh_rules")
    assert not solver.op_data.operators["槐琥"].refresh_drained


def test_refresh_rules_survive_serialized_retry(solver):
    solver._activate_shift_backup(solver.task)
    task = pickle.loads(pickle.dumps(solver.task))
    solver.task = task
    solver.tasks[0] = task
    assert solver.op_data.swap_plan([False], refresh=True) is None
    solver._activate_shift_backup(task)
    solver.agent_arrange = MagicMock(
        side_effect=lambda *_: setattr(
            solver.op_data.operators["槐琥"], "current_room", ""
        )
    )
    solver._arrange_with_shift_refresh_rules(task, True)
    assert not any(t.type == TaskTypes.EXHAUST_OFF for t in solver.tasks)
    solver.refresh_run_order_time.assert_called_once_with("room_2_1")


def test_no_move_does_not_refresh_and_completion_discards_old_rules(solver):
    solver._activate_shift_backup(solver.task)
    solver._complete_group_shift(solver.task)
    solver.op_data.operators["槐琥"].current_room = ""
    assert any(t.type == TaskTypes.EXHAUST_OFF for t in solver.tasks)
    solver.refresh_run_order_time.assert_not_called()


@pytest.mark.parametrize(
    "old,new,expected",
    [
        ([True, ["room_2_1"]], [True, ["room_3_1"]], ["room_2_1", "room_3_1"]),
        ([True, []], [True, ["room_3_1"]], ["room_1_1", "room_2_1"]),
        ([True, ["room_2_1"]], [True, []], ["room_1_1", "room_2_1"]),
        ([False, []], [True, ["room_3_1"]], ["room_3_1"]),
    ],
)
def test_changed_trading_rules_preserve_scoped_rooms(solver, old, new, expected):
    solver.op_data.operators["槐琥"].refresh_order_room = old
    solver.op_data.global_plan["default_plan"].config.refresh_trading_config = (
        ["槐琥" + ",".join(new[1])] if new[0] else []
    )
    solver._activate_shift_backup(solver.task)
    solver.op_data.run_order_rooms = {"room_1_1": {}, "room_2_1": {}}
    solver.agent_arrange = MagicMock(
        side_effect=lambda *_: setattr(
            solver.op_data.operators["槐琥"], "current_room", ""
        )
    )
    solver._arrange_with_shift_refresh_rules(solver.task, True)
    assert [
        call.args[0] for call in solver.refresh_run_order_time.call_args_list
    ] == expected
    assert solver.op_data.operators["槐琥"].refresh_order_room == new


@pytest.mark.parametrize("failure", [False, True])
def test_deferred_or_failed_move_restores_flags_until_its_retry(solver, failure):
    solver._activate_shift_backup(solver.task)
    solver.agent_arrange = MagicMock(return_value=False)
    if failure:
        solver.agent_arrange.side_effect = RuntimeError("room read failed")
        with pytest.raises(RuntimeError, match="room read failed"):
            solver._arrange_with_shift_refresh_rules(solver.task, True)
    else:
        assert solver._arrange_with_shift_refresh_rules(solver.task, True) is False
    assert hasattr(solver.task, "backup_refresh_rules")
    op = solver.op_data.operators["槐琥"]
    assert not op.refresh_drained
    assert op.refresh_order_room == [False, []]
    op.current_room = ""
    solver.refresh_run_order_time.assert_not_called()
    assert any(t.type == TaskTypes.EXHAUST_OFF for t in solver.tasks)
    solver.agent_arrange = MagicMock(
        side_effect=lambda *_: setattr(op, "current_room", "dormitory_1")
    )
    solver._arrange_with_shift_refresh_rules(solver.task, True)
    assert not any(t.type == TaskTypes.EXHAUST_OFF for t in solver.tasks)
    solver.refresh_run_order_time.assert_called_once_with("room_2_1")


@pytest.mark.parametrize("coalesced", [False, True])
def test_cached_backup_transition_attaches_rules_to_physical_task(solver, coalesced):
    deadline = solver.tasks[1]
    solver.tasks, solver.task = [deadline], None
    pending = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={"room_1_2": ["砾"]}
    )
    pending.backup_refresh_rules = {"砾": (True, [True, ["room_3_1"]])}
    if coalesced:
        solver.tasks.append(pending)
    solver.queue_product_switches = MagicMock()
    solver._backup_transition_plan = MagicMock(return_value={"room_1_2": ["砾"]})
    generated = []
    assert solver.backup_plan_solver(generated_tasks=generated)
    task = next(t for t in generated if t.plan)
    assert "槐琥" in task.backup_refresh_rules
    if coalesced:
        assert all(item is not pending for item in solver.tasks)
        assert task.backup_refresh_rules["砾"] == pending.backup_refresh_rules["砾"]
    assert not solver.op_data.operators["槐琥"].refresh_drained
    assert deadline in solver.tasks
    solver.refresh_run_order_time.assert_not_called()
    solver.task = task
    solver._activate_shift_backup(task)
    solver.agent_arrange = MagicMock(
        side_effect=lambda *_: setattr(
            solver.op_data.operators["槐琥"], "current_room", ""
        )
    )
    solver._arrange_with_shift_refresh_rules(task, True)
    assert deadline not in solver.tasks
    solver.refresh_run_order_time.assert_called_once_with("room_2_1")


def test_unchanged_refresh_rules_do_not_capture_unrelated_operators(solver):
    solver.task.backup_shift_conditions = [True]
    solver._activate_shift_backup(solver.task)
    assert not hasattr(solver.task, "backup_refresh_rules")
    solver.agent_arrange = MagicMock(
        side_effect=lambda *_: setattr(
            solver.op_data.operators["砾"], "current_room", "dormitory_1"
        )
    )
    solver._arrange_with_shift_refresh_rules(solver.task, True)
    solver.refresh_run_order_time.assert_not_called()
    assert any(t.type == TaskTypes.EXHAUST_OFF for t in solver.tasks)
