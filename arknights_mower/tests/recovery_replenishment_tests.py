"""回班等待保留原安排，并在同轮检查独立的源石碎片补货。"""

import pickle
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests import native_recovery_execution_tests as recovery
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = recovery.solver
resting = recovery.resting


@pytest.fixture
def replenishment(resting, monkeypatch):
    scheduler, _ = resting
    scheduler.op_data.operators["讯使"].rest_in_full = True
    scheduler.op_data.products = {
        "room_2_3": "orirock",
        "room_3_2": "orirock_device",
    }
    scheduler.global_plan["default_plan"].products = scheduler.op_data.products.copy()
    # 保留真实派发筛选，失败任务和恢复等待不能占用补货时间预算。
    del scheduler.find_next_task
    scheduler.find = Mock(
        side_effect=lambda resource, **kw: (
            resource in ("control_central", "manufacture_product_change_confirm")
        )
    )
    scheduler.recog = SimpleNamespace(w=1920, h=1080, update=Mock())
    scheduler.scene = Mock(return_value=base_schedule.Scene.INFRA_MAIN)
    scheduler.enter_room = Mock()
    scheduler._wait_drone_interface = Mock()
    scheduler._wait_product_resource = Mock()
    scheduler.scene_graph_navigation = Mock()
    scheduler.tap = Mock()
    scheduler.sleep = Mock()
    scheduler._read_manufacture_queue_count = Mock(side_effect=[54, 54, 28, 28])
    scheduler.agent_arrange = Mock()
    scheduler._scan_card_moods = Mock()
    scheduler.collect_recycling = Mock(return_value=False)
    monkeypatch.setattr(base_schedule.detector, "infra_notification", lambda img: None)
    scheduler.recog.img = None
    scheduler.enable_party = False
    scheduler.drone_room = scheduler.drone_time = None
    scheduler.refresh_connecting = False
    scheduler.planned = scheduler.todo_task = scheduler.collect_notification = False
    scheduler.error = False
    scheduler.reload_time = datetime.now() - timedelta(hours=config.conf.maa_gap + 1)
    return scheduler


def pending_return(scheduler, *, initial=False, observed_deadline=False):
    task = recovery.returning_task()
    task.execution_retained = True
    if initial:
        task.type = TaskTypes.SELF_CORRECTION
        task.initial_staffing = True
        task.initial_staffing_returns = {"伊内丝", "银灰", "讯使"}
    task.time -= timedelta(minutes=20)
    scheduler.tasks, scheduler.task = [task], task
    op = scheduler.op_data.operators["讯使"]

    def read(rooms):
        op.mood, op.time_stamp = 18, datetime.now()
        scheduler.op_data.get_dorm_by_name(op.name)[1].time = (
            datetime.now() + timedelta(minutes=31) if observed_deadline else None
        )

    scheduler._read_recovery_rooms = Mock(side_effect=read)
    return task


def finish_dispatch(scheduler):
    for _ in range(6):
        if scheduler.infra_main():
            return
    pytest.fail("基建派发未在有限步骤内结束")


@pytest.mark.parametrize("initial", [False, True])
@pytest.mark.parametrize("observed_deadline", [False, True])
def test_recovery_pause_checks_both_shard_rooms_before_ending_dispatch(
    replenishment, initial, observed_deadline
):
    scheduler = replenishment
    task = pending_return(
        scheduler, initial=initial, observed_deadline=observed_deadline
    )
    original_plan, original_time = deepcopy(task.plan), task.time
    started_at = datetime.now()

    # 与 BaseSolver.run 相同：只有 transition 返回真值才结束本轮。
    finish_dispatch(scheduler)

    assert [c.args[0] for c in scheduler.enter_room.call_args_list] == [
        "room_2_3",
        "room_3_2",
    ]
    assert [c.args[0] for c in scheduler.tap.call_args_list] == [
        (1450, 305),
        (1425, 895),
        (1450, 305),
        (1425, 895),
    ]
    assert scheduler.reload_time >= started_at
    scheduler.agent_arrange.assert_not_called()
    assert task.plan == original_plan and task.time == original_time
    scheduler._read_recovery_rooms.assert_called_once()
    if observed_deadline:
        assert task in scheduler.waiting_group_shifts
        assert task not in scheduler.tasks
    else:
        assert task in scheduler.tasks
        assert task.execution_failure


@pytest.mark.parametrize("constraint", ["interval", "critical_task"])
def test_recovery_pause_preserves_replenishment_interval_and_task_budget(
    replenishment, constraint
):
    scheduler = replenishment
    pending_return(scheduler)
    assert scheduler.infra_main() is None
    if constraint == "interval":
        scheduler.reload_time = datetime.now()
    else:
        scheduler.tasks.append(
            SchedulerTask(
                time=datetime.now() + timedelta(seconds=90),
                task_type=TaskTypes.DEPOT,
            )
        )
    original_time = scheduler.reload_time

    finish_dispatch(scheduler)

    scheduler.enter_room.assert_not_called()
    scheduler.tap.assert_not_called()
    assert scheduler.reload_time == original_time


def test_retained_return_survives_restart_yields_to_other_work_and_resumes(
    replenishment,
):
    from arknights_mower.tests.dorm_group_tests import apply_plan

    scheduler = replenishment
    task = pending_return(scheduler)
    original_time, original_plan = task.time, deepcopy(task.plan)
    finish_dispatch(scheduler)
    restored = pickle.loads(pickle.dumps(task))
    scheduler.tasks = [restored]
    for _ in range(3):
        scheduler._resume_failed_tasks()
        assert restored.execution_failure
        assert restored.time == original_time and restored.plan == original_plan
    scheduler._read_recovery_rooms.assert_called_once()

    independent = SchedulerTask(task_type=TaskTypes.DEPOT)
    scheduler.tasks.append(independent)
    scheduler.task = independent
    scheduler.仓库扫描 = Mock()
    scheduler.infra_main()
    scheduler.仓库扫描.assert_called_once()
    assert all(t is not independent for t in scheduler.tasks)
    assert any(t is restored for t in scheduler.tasks)

    op = scheduler.op_data.operators["讯使"]
    op.mood, op.time_stamp = 24, datetime.now()
    scheduler._resume_failed_tasks()
    assert not getattr(restored, "execution_failure", None)
    assert restored.time == original_time and restored.plan == original_plan

    def arrange(plan, *args, **kwargs):
        apply_plan(scheduler, plan)
        plan.clear()
        return True

    scheduler.agent_arrange.side_effect = arrange
    scheduler.task = restored
    scheduler.infra_main()
    assert op.is_working()
    assert all(t is not restored for t in scheduler.tasks)
    scheduler._read_recovery_rooms.assert_called_once()
    assert scheduler.tap.call_count == 4
