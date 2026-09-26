"""测试宿舍逻辑：卖玉停止跑单，但保留正常心情扫描与换班。"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import mastery_reader  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.logic_expression import LogicExpression  # noqa: E402
from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.enable_mastery = False
    config.conf.experimental_dorm_logic = True
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "room_1_1": [Room("鸿雪", "", ["但书", "孑"])],
                    "room_2_2": [Room("图耶", "", ["龙舌兰", "锏"])],
                    "dormitory_1": [Room("杜林", "", []), Room("蜜莓", "", [])]
                    + [Room("Free", "", []) for _ in range(3)],
                },
                PlanConfig("", "", "", experimental_dorm_logic=True),
                products={"room_1_1": "lmd", "room_2_2": "lmd"},
            ),
            "backup_plans": [
                Plan(
                    {},
                    PlanConfig("", "", ""),
                    trigger=LogicExpression("1", "==", "1"),
                    products={"room_1_1": "orundum"},
                )
            ],
        }
    )
    assert data.init_and_validate() is None
    for op in data.operators.values():
        op.current_room, op.current_index = op.room, op.index
        op.time_stamp = datetime.now()
    instance = object.__new__(BaseSchedulerSolver)
    instance.op_data = data
    instance.tasks = []
    instance.task = None
    instance.get_run_order_time = MagicMock(
        return_value=datetime.now() + timedelta(hours=1)
    )
    instance.queue_product_switches = MagicMock()
    instance._suppress_train_correction = MagicMock()
    return instance


@pytest.mark.parametrize("source", ["plan", "observed"])
def test_orundum_does_not_create_run_order_even_with_trade_agents(solver, source):
    if source == "plan":
        solver.op_data.products["room_1_1"] = "orundum"
    else:
        solver.op_data.update_facility_state("room_1_1", "trade", "orundum")
    solver.plan_run_order("room_1_1")
    assert solver.tasks == []
    solver.get_run_order_time.assert_not_called()
    assert set(solver.op_data.run_order_rooms) == {"room_2_2"}


def test_reading_actual_orundum_cancels_new_run_order(solver):
    def read_order(room):
        solver.op_data.update_facility_state(room, "trade", "orundum")
        return datetime.now() - timedelta(minutes=1)

    solver.get_run_order_time.side_effect = read_order
    solver.plan_run_order("room_1_1")
    assert solver.tasks == []
    assert "room_1_1" not in solver.op_data.run_order_rooms


def test_swap_rebuilds_rooms_after_removing_trade_replacements(solver):
    data = solver.op_data
    backup = data.backup_plans[0]
    backup.products = {}
    backup.plan = {"room_1_1": [Room("鸿雪", "", ["孑"])]}
    assert data.swap_plan([True], refresh=True) is None
    assert set(data.run_order_rooms) == {"room_2_2"}
    solver.plan_run_order("room_1_1")
    assert solver.tasks == []
    solver.get_run_order_time.assert_not_called()
    assert data.swap_plan([False], refresh=True) is None
    assert set(data.run_order_rooms) == {"room_1_1", "room_2_2"}


def test_sync_removes_only_invalid_order_and_order_refresh_tasks(solver):
    removed = [
        SchedulerTask(task_type=kind, meta_data="room_1_1")
        for kind in (TaskTypes.RUN_ORDER, TaskTypes.REFRESH_TIME)
    ]
    kept = [
        SchedulerTask(task_type=TaskTypes.RUN_ORDER, meta_data="room_2_2"),
        SchedulerTask(task_type=TaskTypes.REFRESH_TIME, meta_data="room_2_2"),
        SchedulerTask(task_type=TaskTypes.RUN_ORDER, task_plan={"room_1_1": ["鸿雪"]}),
        *[
            SchedulerTask(task_type=kind, meta_data="room_1_1")
            for kind in (
                TaskTypes.SHIFT_ON,
                TaskTypes.SHIFT_OFF,
                TaskTypes.EXHAUST_OFF,
                TaskTypes.SELF_CORRECTION,
                TaskTypes.NOT_SPECIFIC,
            )
        ],
    ]
    solver.tasks = removed + kept
    solver.op_data.products["room_1_1"] = "orundum"
    timestamps = {name: op.time_stamp for name, op in solver.op_data.operators.items()}

    solver._sync_run_order_tasks()

    assert solver.tasks == kept
    assert {
        name: op.time_stamp for name, op in solver.op_data.operators.items()
    } == timestamps


def test_backup_convergence_removes_queued_orders_immediately(solver):
    stale = SchedulerTask(task_type=TaskTypes.RUN_ORDER, meta_data="room_1_1")
    other = SchedulerTask(task_type=TaskTypes.RUN_ORDER, meta_data="room_2_2")
    solver.tasks = [stale, other]
    solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [True]
    assert all(task is not stale for task in solver.tasks)
    assert any(task is other for task in solver.tasks)
    assert set(solver.op_data.run_order_rooms) == {"room_2_2"}


def test_returning_to_lmd_waits_for_actual_product_and_resumes(solver):
    data = solver.op_data
    data.update_facility_state("room_1_1", "trade", "orundum")
    assert data.swap_plan([True], refresh=True) is None
    assert data.swap_plan([False], refresh=True) is None
    solver.plan_run_order("room_1_1")
    assert solver.tasks == []
    data.update_facility_state("room_1_1", "trade", "lmd")
    solver.plan_run_order("room_1_1")
    assert len(solver.tasks) == 1
    assert solver.tasks[0].plan == {"room_1_1": ["但书"]}
    assert solver.tasks[0].time == solver.get_run_order_time.return_value


def test_orundum_room_still_gets_normal_mood_scan(solver, monkeypatch):
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *args, **kwargs: mastery_reader.RoomState(state="empty"),
    )
    data = solver.op_data
    data.products["room_1_1"] = "orundum"
    target = data.operators["鸿雪"]
    target.time_stamp = datetime.now() - timedelta(hours=3)
    solver._sync_run_order_tasks()
    solver.enter_room = MagicMock()
    solver.back = MagicMock()
    solver.get_agent_from_room = MagicMock(return_value=[{"agent": "鸿雪", "mood": 10}])

    solver.agent_get_mood(return_plan=True)

    # 常规巡检还会检查训练室；这里约束卖玉房间仍被正常扫描一次。
    assert solver.enter_room.call_args_list.count(call("room_1_1")) == 1
    assert solver.get_agent_from_room.call_args_list.count(call("room_1_1", None)) == 1


def test_sync_does_not_change_legacy_queue(solver):
    solver.op_data.config.experimental_dorm_logic = False
    solver.op_data.products["room_1_1"] = "orundum"
    task = SchedulerTask(task_type=TaskTypes.RUN_ORDER, meta_data="room_1_1")
    solver.tasks = [task]
    solver._sync_run_order_tasks()
    assert solver.tasks == [task]
    assert "room_1_1" in solver.op_data.run_order_rooms
