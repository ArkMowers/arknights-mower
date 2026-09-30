"""停服大更新副表允许跑单干员主班，并在生效期间暂停全部跑单。"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers.base_schedule import (  # noqa: E402
    BaseSchedulerSolver,
    ProductSwitchDeferred,
)
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils import operators as operators_module  # noqa: E402
from arknights_mower.utils.logic_expression import LogicExpression  # noqa: E402
from arknights_mower.utils.news_checker import (  # noqa: E402
    MaintenanceInfo,
    NewsChecker,
)
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS, Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    adjust_run_order_for_maintenance,
)


def maintenance_trigger():
    return LogicExpression("op_data.major_maintenance_remaining_hours()", "<=", "0.5")


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(NewsChecker, "get_update_time", lambda: (None, None))
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: None)
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "room_1_1": [Room("鸿雪", "", ["但书", "孑"])],
                    "room_2_2": [Room("图耶", "", ["龙舌兰", "锏"])],
                    "dormitory_1": [Room("杜林", "", []), Room("蜜莓", "", [])]
                    + [Room("Free", "", []) for _ in range(3)],
                },
                PlanConfig("", "", ""),
            ),
            "backup_plans": [
                Plan(
                    {"room_1_1": [Room("但书", "", ["孑"])]},
                    PlanConfig("", "", ""),
                    trigger=maintenance_trigger(),
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
    return instance


@pytest.mark.parametrize("agent", TRADE_ORDER_AGENTS)
def test_maintenance_backup_accepts_trade_order_primary(solver, agent):
    data = solver.op_data
    data.backup_plans[0].plan["room_1_1"][0].agent = agent
    assert data.swap_plan([True], refresh=True) is None
    assert data.operators[agent].is_high()
    assert data.operators[agent].room == "room_1_1"
    assert data.run_order_rooms == {}


@pytest.mark.parametrize(
    "trigger",
    [
        None,
        LogicExpression("1", "==", "1"),
        LogicExpression("'op_data.major_maintenance_remaining_hours()'", "!=", "''"),
    ],
)
def test_other_backup_conditions_reject_trade_order_primary(solver, trigger):
    data = solver.op_data
    data.backup_plans[0].trigger = trigger
    assert "高效组不可用" in data.swap_plan([True], refresh=True)


def test_nested_maintenance_condition_accepts_trade_order_primary(solver):
    data = solver.op_data
    data.backup_plans[0].trigger = LogicExpression(
        LogicExpression("1", "==", "1"), "and", maintenance_trigger()
    )
    assert data.swap_plan([True], refresh=True) is None


def test_inactive_maintenance_backup_does_not_authorize_default_primary(solver):
    data = solver.op_data
    data.global_plan["default_plan"].plan["room_1_1"][0] = Room("但书", "", ["孑"])
    assert "高效组不可用" in data.swap_plan([False], refresh=True)


def test_later_nonmaintenance_override_does_not_inherit_permission(solver):
    data = solver.op_data
    data.backup_plans.append(
        Plan(
            {"room_1_1": [Room("但书", "", ["孑"])]},
            PlanConfig("", "", ""),
            trigger=LogicExpression("1", "==", "1"),
        )
    )
    assert "高效组不可用" in data.swap_plan([True, True], refresh=True)


def test_current_override_preserves_maintenance_primary(solver):
    data = solver.op_data
    data.backup_plans.append(
        Plan({"room_1_1": [Room("Current", "", [])]}, PlanConfig("", "", ""))
    )
    assert data.swap_plan([True, True], refresh=True) is None
    assert data.run_order_rooms == {}


def test_maintenance_without_trade_order_primary_keeps_running_orders(solver):
    data = solver.op_data
    data.backup_plans[0].plan = {}
    assert data.swap_plan([True], refresh=True) is None
    solver.plan_run_order("room_2_2")
    assert len(solver.tasks) == 1
    assert solver.tasks[0].type == TaskTypes.RUN_ORDER


def test_primary_trade_agent_in_other_replacements_keeps_primary_identity(solver):
    data = solver.op_data
    data.backup_plans[0].plan = {"room_1_1": [Room("龙舌兰", "", ["孑"])]}
    assert data.swap_plan([True], refresh=True) is None
    assert data.operators["龙舌兰"].is_high()
    assert data.operators["龙舌兰"].room == "room_1_1"


def test_active_maintenance_clears_only_order_tasks_and_resumes_on_exit(solver):
    data = solver.op_data
    orders = [
        SchedulerTask(task_type=kind, meta_data=room)
        for room in ("room_1_1", "room_2_2")
        for kind in (TaskTypes.RUN_ORDER, TaskTypes.REFRESH_TIME)
    ]
    kept = [
        SchedulerTask(task_type=TaskTypes.RUN_ORDER, task_plan={"room_1_1": ["鸿雪"]}),
        SchedulerTask(task_type=TaskTypes.SHIFT_ON),
        SchedulerTask(task_type=TaskTypes.SHIFT_OFF),
        SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE),
    ]
    solver.tasks = orders + kept
    assert data.swap_plan([True], refresh=True) is None
    solver.run_order_solver()
    solver.plan_run_order("room_2_2")
    assert solver.tasks == kept
    solver.get_run_order_time.assert_not_called()
    assert data.swap_plan([False], refresh=True) is None
    solver.plan_run_order("room_2_2")
    assert solver.tasks[:-1] == kept
    assert solver.tasks[-1].type == TaskTypes.RUN_ORDER
    assert solver.tasks[-1].meta_data == "room_2_2"
    solver.get_run_order_time.assert_called_once_with("room_2_2")


def test_backup_switch_removes_queued_orders_immediately(solver, monkeypatch):
    monkeypatch.setattr(
        solver.op_data, "major_maintenance_remaining_hours", lambda: 0.25
    )
    stale = SchedulerTask(task_type=TaskTypes.RUN_ORDER, meta_data="room_2_2")
    solver.tasks = [stale]
    solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [True]
    assert all(task is not stale for task in solver.tasks)
    assert solver.op_data.run_order_rooms == {}


def test_later_normal_primary_override_restores_orders(solver):
    data = solver.op_data
    data.backup_plans.append(
        Plan(
            {"room_1_1": [Room("鸿雪", "", ["但书", "孑"])]},
            PlanConfig("", "", ""),
        )
    )
    assert data.swap_plan([True, True], refresh=True) is None
    assert not data.run_order_paused
    assert set(data.run_order_rooms) == {"room_1_1", "room_2_2"}


def test_maintenance_primary_still_requires_regular_replacements(solver):
    data = solver.op_data
    data.backup_plans[0].plan["room_1_1"][0].replacement = []
    assert "替换组缺失" in data.swap_plan([True], refresh=True)


def maintenance_info(start):
    return MaintenanceInfo(
        start=start,
        end=start + timedelta(hours=6),
        update_type="major",
        title="停机维护",
        url="",
        announcement_id="test",
    )


def test_timer_wakes_at_threshold_and_preserves_other_tasks(solver, monkeypatch):
    info = maintenance_info(datetime.now() + timedelta(hours=2))
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: info)
    other = SchedulerTask(time=info.end, task_type=TaskTypes.SHIFT_ON)
    solver.tasks = [other]
    solver._schedule_maintenance_backup_check()
    solver._schedule_maintenance_backup_check()
    assert len(solver.tasks) == 2
    assert solver.tasks[0].time == info.start - timedelta(minutes=30)
    assert solver.tasks[0].meta_data == "maintenance_backup_check"
    assert solver.tasks[1] is other
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: None)
    solver._schedule_maintenance_backup_check()
    assert solver.tasks == [other]


def test_timer_handles_nested_thresholds_without_post_stop_check(solver, monkeypatch):
    info = maintenance_info(datetime.now() + timedelta(hours=2))
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: info)
    data = solver.op_data
    data.backup_plans[0].trigger = LogicExpression(
        maintenance_trigger(), "or", maintenance_trigger()
    )
    assert data.next_major_maintenance_check(info.start - timedelta(hours=1)) == (
        info.start - timedelta(minutes=30)
    )
    assert data.next_major_maintenance_check(info.start - timedelta(minutes=10)) is None
    assert data.next_major_maintenance_check(info.start) is None
    assert data.next_major_maintenance_check(info.end) is None


def test_maintenance_condition_expires_at_stop_and_exits_on_restart(
    solver, monkeypatch
):
    start = datetime(2026, 9, 30, 16)
    now = start - timedelta(minutes=30)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(operators_module, "datetime", Clock)
    info = maintenance_info(start)
    # 公告仍被缓存时，停服开始边界也必须使条件失效。
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: info)
    solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [True]
    assert solver.op_data.run_order_paused

    now = start - timedelta(microseconds=1)
    assert solver.op_data.evaluate_expression(str(maintenance_trigger()))
    now = start
    assert not solver.op_data.evaluate_expression(str(maintenance_trigger()))

    # 停服期间任务线程已停止，只检查条件失效，不执行换班。
    now = start + timedelta(hours=1)
    assert not solver.op_data.evaluate_expression(str(maintenance_trigger()))
    assert solver.op_data.plan_condition == [True]

    # 更新客户端后重启任务，首轮检查退出保存的维护副表。
    now = info.end + timedelta(minutes=1)
    solver.tasks = []
    solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [False]
    assert not solver.op_data.run_order_paused
    assert set(solver.op_data.run_order_rooms) == {"room_1_1", "room_2_2"}


def test_entry_advances_existing_maintenance_orders_before_swap(solver, monkeypatch):
    now = datetime.now()
    info = maintenance_info(now + timedelta(minutes=20))
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: info)
    monkeypatch.setattr(NewsChecker, "get_update_time", lambda: (info.start, info.end))
    order = SchedulerTask(
        time=info.start + timedelta(hours=1),
        task_type=TaskTypes.RUN_ORDER,
        meta_data="room_2_2",
        task_plan={"room_2_2": ["龙舌兰"]},
    )
    unaffected = SchedulerTask(
        time=info.end + timedelta(hours=2),
        task_type=TaskTypes.RUN_ORDER,
        meta_data="room_1_1",
    )
    solver.tasks = [order, unaffected]
    adjust_run_order_for_maintenance(solver.tasks)
    assert order.time > now
    solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [False]
    assert order.time <= datetime.now()
    assert order.adjusted
    assert order.maintenance_advance_before_backup
    assert not unaffected.adjusted
    solver.queue_product_switches.assert_not_called()
    solver.plan_run_order("room_1_1")
    solver.get_run_order_time.assert_not_called()

    # 失败后的延期保留，不能每次检查都拉回立即执行。
    order.time = datetime.now() + timedelta(minutes=5)
    deferred_time = order.time
    solver.backup_plan_solver()
    assert order.time == deferred_time
    assert solver.op_data.plan_condition == [False]

    # 已完成加速但原班尚未恢复时，仍等待恢复任务。
    restore = SchedulerTask(
        task_type=TaskTypes.RUN_ORDER, task_plan={"room_2_2": ["图耶"]}
    )
    restore.maintenance_advance_before_backup = True
    solver.tasks = [restore, unaffected]
    solver.maintenance_entry_pending = False
    solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [False]
    solver.tasks = [unaffected]
    solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [True]
    assert not solver.maintenance_entry_pending
    assert solver.op_data.run_order_rooms == {}
    assert unaffected not in solver.tasks


def test_shift_projection_cannot_bypass_pending_maintenance_orders(solver):
    solver.maintenance_entry_pending = True
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    with pytest.raises(ProductSwitchDeferred, match="提前跑单"):
        solver._prepare_shift_cycle(task)
    assert solver.op_data.plan_condition == [False]


def test_projected_backup_activation_advances_orders_first(solver, monkeypatch):
    info = maintenance_info(datetime.now() + timedelta(minutes=20))
    monkeypatch.setattr(NewsChecker, "get_update_time", lambda: (info.start, info.end))
    order = SchedulerTask(
        time=info.start + timedelta(hours=1),
        task_type=TaskTypes.RUN_ORDER,
        meta_data="room_2_2",
    )
    shift = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    shift.backup_shift_conditions = [True]
    solver.tasks = [order, shift]
    with pytest.raises(ProductSwitchDeferred, match="提前跑单"):
        solver._activate_shift_backup(shift)
    assert solver.op_data.plan_condition == [False]
    assert order.adjusted
    assert order.time < datetime.now()
