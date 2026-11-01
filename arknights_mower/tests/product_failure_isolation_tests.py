"""切产物识别失败仅暂停对应房间，独立任务继续派发。"""

from datetime import timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import scheduler_recovery_preservation_tests as recovery
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    find_next_task,
    task_view,
)

scheduler = recovery.scheduler


@pytest.mark.parametrize(
    "failure_stage",
    [
        "manufacture_survey",
        "trade_survey",
        "acceleration",
        "manufacture_change",
        "trade_change",
    ],
)
def test_room_recognition_failure_keeps_independent_product_dispatchable(
    scheduler, monkeypatch, failure_stage
):
    solver = scheduler.solver
    monkeypatch.setattr(recovery.config.conf.product_switching, "enable", True)
    solver.op_data.products = {}
    solver.op_data.facility_states = {}
    solver.op_data.run_order_rooms = {}
    now = scheduler.clock.now()
    failed_room, independent_room = "room_1_1", "room_1_2"
    trade_failure = failure_stage.startswith("trade_")
    failed = SchedulerTask(
        now - timedelta(seconds=1),
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=f"{failed_room},{'orundum' if trade_failure else 'exp3'}",
    )
    independent = SchedulerTask(
        now - timedelta(seconds=1),
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=f"{independent_room},exp3",
    )
    solver.tasks, solver.task = [failed, independent], failed

    def reject(stage, room):
        if stage == failure_stage and room == failed_room:
            raise scheduler.module.RecognizeError("目标房间识别未确认")

    def manufacture_survey(room, target):
        reject("manufacture_survey", room)
        return {
            "room": room,
            "facility": "manufacture",
            "target_product": target,
            "current_product": "gold",
            "needs_switch": True,
            "total_seconds": 3780,
            "current_remaining": 180,
            "production_rate": 1.0,
            "production_rate_observed": True,
            "observed_at": now,
            "available_drones": 100,
            "drone_count": 1,
            "wait_seconds": 0,
        }

    def trade_survey(room, target):
        reject("trade_survey", room)
        return {
            "room": room,
            "facility": "trade",
            "target_product": target,
            "current_product": "lmd",
            "needs_switch": True,
            "switchable": True,
        }

    solver._survey_manufacture_switch = Mock(side_effect=manufacture_survey)
    solver._survey_trade_switch = Mock(side_effect=trade_survey)
    solver._execute_manufacture_acceleration = Mock(
        side_effect=lambda item: reject("acceleration", item["room"]) or 0
    )
    solver._change_manufacture_product = Mock(
        side_effect=lambda item, **kwargs: reject("manufacture_change", item["room"])
    )
    solver._change_trade_product = Mock(
        side_effect=lambda item: reject("trade_change", item["room"])
    )
    monkeypatch.setattr(scheduler.module, "save_exception", Mock())

    solver.infra_main()

    assert failed.execution_failure["rooms"] == (failed_room,)
    assert not getattr(independent, "execution_failure", None)
    assert find_next_task(solver.tasks) is independent
    assert failed.time == independent.time == now - timedelta(seconds=1)

    for _ in range(3):
        scheduler.clock.current += timedelta(minutes=5)
        solver._resume_failed_tasks()
        dispatch = task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data)
        assert all(task is not failed for task in dispatch)
        assert any(task is independent for task in dispatch)

    solver.task = independent
    solver.infra_main()

    assert any(task is failed for task in solver.tasks)
    assert all(task is not independent for task in solver.tasks)
    assert any(
        call.args[0]["room"] == independent_room
        for call in solver._change_manufacture_product.call_args_list
    )
    assert failed.time == now - timedelta(seconds=1)
    scheduler.io.assert_not_called()


@pytest.mark.parametrize(
    "cleanup", ["settled", "missing_observation", "target_changed"]
)
def test_room_cleanup_preserves_other_room_task_and_progress(
    scheduler, monkeypatch, cleanup
):
    solver = scheduler.solver
    monkeypatch.setattr(recovery.config.conf.product_switching, "enable", True)
    settled_room, pending_room = "room_1_1", "room_1_2"
    solver.op_data.plan = {
        room: [Room("Lancet-2", "", [], "制造站", target)]
        for room, target in ((settled_room, "gold"), (pending_room, "exp3"))
    }
    solver.op_data.products = {settled_room: "gold", pending_room: "exp3"}
    solver.op_data.facility_states = {
        room: {"facility": "manufacture", "product": "gold"}
        for room in (settled_room, pending_room)
    }
    if cleanup == "missing_observation":
        del solver.op_data.facility_states[settled_room]
    elif cleanup == "target_changed":
        solver.op_data.facility_states[settled_room]["product"] = "exp3"
    settled = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=f"{settled_room},{'exp3' if cleanup == 'target_changed' else 'gold'}",
    )
    pending = SchedulerTask(
        scheduler.clock.now(),
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=f"{pending_room},exp3",
    )
    pending.product_switch_progress = {
        pending_room: {"boundary_total": 3600, "accelerated": True}
    }
    solver.tasks, solver.task = [settled, pending], None

    type(solver).queue_product_switches(solver)

    assert len(solver.tasks) == (2 if cleanup == "target_changed" else 1)
    assert any(task is pending for task in solver.tasks)
    assert pending.product_switch_progress == {
        pending_room: {"boundary_total": 3600, "accelerated": True}
    }
    assert pending.time == scheduler.clock.now()
    scheduler.io.assert_not_called()


@pytest.mark.parametrize("unknown_first", [False, True])
def test_dispatch_keeps_each_product_deadline_and_unknown_dependency(
    scheduler, monkeypatch, unknown_first
):
    solver = scheduler.solver
    monkeypatch.setattr(recovery.config.conf.product_switching, "enable", True)
    solver.op_data.products = {}
    solver.op_data.facility_states = {}
    solver.op_data.run_order_rooms = {}
    now = scheduler.clock.now()
    tasks = [
        SchedulerTask(now, task_type=TaskTypes.SWITCH_PRODUCT, meta_data=f"{room},exp3")
        for room in ("room_1_1", "room_1_2")
    ]
    solver.tasks, solver.task = tasks[:], tasks[0]
    solver._survey_manufacture_switch = Mock(
        side_effect=lambda room, target: {
            "room": room,
            "facility": "manufacture",
            "target_product": target,
            "current_product": "gold",
            "needs_switch": True,
            "total_seconds": 3780,
            "current_remaining": 180,
            "production_rate": 1.0,
            "production_rate_observed": True,
            "observed_at": now,
            "available_drones": 100,
            "drone_count": 1,
            "wait_seconds": 0,
        }
    )
    solver._execute_manufacture_acceleration = Mock(return_value=0)

    def pending(observation):
        first = observation["room"] == "room_1_1"
        raise scheduler.module.ProductSwitchDeferred(
            "当前份等待生产确认",
            ready_at=None
            if first and unknown_first
            else now + timedelta(seconds=9 if first else 59),
            rooms=[observation["room"]],
        )

    solver._change_manufacture_product = Mock(side_effect=pending)
    solver.infra_main()
    assert tasks[1].time == now + timedelta(seconds=59)
    assert not getattr(tasks[1], "execution_failure", None)
    if unknown_first:
        assert tasks[0].time == now
        assert tasks[0].execution_failure["rooms"] == ("room_1_1",)
        scheduler.clock.current += timedelta(seconds=20)
        solver._resume_failed_tasks()
        assert all(
            task is not tasks[0]
            for task in task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data)
        )
    else:
        assert tasks[0].time == now + timedelta(seconds=9)
        assert not getattr(tasks[0], "execution_failure", None)
    assert all(any(queued is task for queued in solver.tasks) for task in tasks)
    scheduler.io.assert_not_called()
