"""副表条件未变时省去回退快照，实际切换仍保留恢复所需状态。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def solver(monkeypatch):
    def reject_network(*args, **kwargs):
        raise AssertionError("network access")

    monkeypatch.setattr("requests.sessions.Session.request", reject_network)
    from arknights_mower.solvers import base_schedule

    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config.conf, "enable_mastery", False)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    instance = object.__new__(base_schedule.BaseSchedulerSolver)
    instance.op_data = Operators(
        {
            "default_plan": Plan(
                {
                    "meeting": [Room("伊内丝", "一组", ["陈", "砾"])],
                    "room_1_1": [Room("芬", "", ["香草"], "制造站", "gold")],
                    "dormitory_1": [
                        Room("塑心", "", []),
                        *[Room("Free", "", []) for _ in range(4)],
                    ],
                },
                PlanConfig("", "", ""),
            ),
            "backup_plans": [
                Plan(
                    {"meeting": [Room("伊内丝", "一组", ["砾"])]},
                    PlanConfig("", "", ""),
                    trigger=LogicExpression(
                        "op_data.operators['伊内丝'].current_mood()", "<", "12"
                    ),
                )
            ],
        }
    )
    assert instance.op_data.init_and_validate() is None
    for op in instance.op_data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 24, datetime.now()
    instance.op_data.first_init = False
    instance.tasks = [SchedulerTask(task_type=TaskTypes.DEPOT)]
    instance.task = None
    instance._sync_run_order_tasks = MagicMock()
    instance.queue_product_switches = MagicMock()
    return instance


@pytest.mark.parametrize("active", [False, True])
def test_unchanged_backup_conditions_preserve_tasks_without_snapshots(solver, active):
    data = solver.op_data
    if active:
        data.operators["伊内丝"].mood = 5
        assert data.swap_plan([True], refresh=True) is None
    pending = solver.tasks[0]
    deadline = pending.time
    with (
        patch.object(
            data, "project_arrangements", wraps=data.project_arrangements
        ) as project,
        patch.object(solver, "_exhaust_task_signatures") as exhaust,
        patch("copy.deepcopy", wraps=deepcopy) as copy_state,
    ):
        assert solver.backup_plan_solver() is False
        assert solver.backup_plan_solver() is False
    project.assert_not_called()
    exhaust.assert_not_called()
    copy_state.assert_not_called()
    assert solver.op_data is data
    assert data.plan_condition == [active]
    assert solver.tasks == [pending]
    assert pending.time == deadline


@pytest.mark.parametrize("products_ready", [False, True])
def test_unchanged_backup_runs_maintenance_and_product_checks_first(
    solver, monkeypatch, products_ready
):
    data = solver.op_data
    data.backup_plans[0].products = {"room_1_1": "gold"}
    events = []

    def maintenance(conditions, backup_group):
        events.append(("maintenance", conditions, backup_group))
        return False

    def products():
        events.append(("products", None))
        return products_ready

    monkeypatch.setattr(solver, "_advance_orders_before_maintenance", maintenance)
    monkeypatch.setattr(solver, "_switch_products_before_backup_plan", products)
    with patch.object(
        data, "project_arrangements", wraps=data.project_arrangements
    ) as project:
        assert solver.backup_plan_solver() is False
    assert events == [("maintenance", [False], "default"), ("products", None)]
    project.assert_not_called()
    assert data.plan_condition == [False]


def test_changed_backup_keeps_isolated_snapshot_for_unavailable_cover(
    solver, monkeypatch
):
    from arknights_mower.solvers import base_schedule

    data = solver.op_data.project_arrangements(
        [
            {
                "meeting": ["陈"],
                "dormitory_1": ["Current", "伊内丝", "Current", "Current", "Current"],
            }
        ]
    )
    solver.op_data = data
    data.operators["伊内丝"].mood = 5
    bed = data.get_dorm_by_name("伊内丝")[1]
    bed.time = datetime.now() + timedelta(hours=4)
    data.operators["砾"]._current_room, data.operators["砾"].current_index = (
        "factory",
        0,
    )
    monkeypatch.setattr(
        base_schedule, "_is_mastery_busy", lambda name: name == "伊内丝"
    )
    positions = {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    recovery = [(bed.position, bed.name, bed.time) for bed in data.all_dorms()]
    pending, deadline = solver.tasks[0], solver.tasks[0].time

    assert solver.backup_plan_solver() is False

    restored = solver.op_data
    assert restored is not data
    assert restored.eval_model is data.eval_model
    assert restored.plan_condition == [False]
    assert restored.plan["meeting"][0].replacement == ["陈", "砾"]
    assert restored.group_is_resting("一组")
    assert {
        name: (op.current_room, op.current_index)
        for name, op in restored.operators.items()
    } == positions
    assert [
        (bed.position, bed.name, bed.time) for bed in restored.all_dorms()
    ] == recovery
    assert restored.operators["伊内丝"] is not data.operators["伊内丝"]
    assert solver.tasks == [pending]
    assert pending.time == deadline


def test_changed_observation_activates_backup_after_unchanged_check(solver):
    assert solver.backup_plan_solver() is False
    solver.op_data.operators["伊内丝"].mood = 5

    assert solver.backup_plan_solver() is False

    assert solver.op_data.plan_condition == [True]
    assert solver.op_data.plan["meeting"][0].replacement == ["砾"]
    assert solver.op_data.get_current_operator("meeting", 0).name == "伊内丝"
    assert len(solver.tasks) == 2


def test_unchanged_backup_does_not_emit_convergence_timing(solver, monkeypatch):
    from arknights_mower.solvers import base_schedule as base

    info = MagicMock()
    monkeypatch.setattr(base.logger, "info", info)
    assert solver.backup_plan_solver() is False
    assert not any("收敛演算耗时" in call.args[0] for call in info.call_args_list)


def test_backup_timing_includes_initial_selection_and_all_rounds(solver, monkeypatch):
    from arknights_mower.solvers import base_schedule as base

    solver.op_data.operators["伊内丝"].mood = 5
    ticks = iter([1.0, 1.25, 2.0, 2.5])
    monkeypatch.setattr(base, "perf_counter", lambda: next(ticks))
    info = MagicMock()
    monkeypatch.setattr(base.logger, "info", info)

    assert solver.backup_plan_solver() is False
    assert solver.op_data.plan_condition == [True]

    records = [call for call in info.call_args_list if "收敛演算耗时" in call.args[0]]
    assert len(records) == 1
    assert records[0].args[1:] == ("副表切换", 0.75, "副表切换 2 轮", "已收敛")
    assert base._backup_timing_runtime.current is None
