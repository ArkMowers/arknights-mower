"""待确认宿舍换班先统一取消，再准入、读房并登记恢复时间。"""

from datetime import datetime, timedelta
from threading import Event
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.dorm_group_tests import apply_plan
from arknights_mower.tests.dorm_group_tests import (
    grouped_free_capacity as grouped_free_capacity,
)
from arknights_mower.tests.dorm_group_tests import solver as solver
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.mark.parametrize("consumed_work", [False, True])
@pytest.mark.parametrize("free_resting", [False, True])
def test_single_recovery_uses_pending_mixed_binding_through_readback(
    solver, monkeypatch, consumed_work, free_resting
):
    plans = solver.global_plan["default_plan"].plan
    plans["meeting"][1].group = "另一组"
    plans["dormitory_1"][0].replacement = ["伊内丝"]
    plans["dormitory_1"][0].group_bindings = [
        {"group": "另一组", "replacement": ["Free"]}
    ]
    plans["dormitory_1"][1].agent = "琴柳"
    assert solver.initialize_operators() is None
    data = solver.op_data
    for name in ("泥岩", "能天使", "年"):
        data.add(Operator(name, ""))
    apply_plan(
        solver,
        {
            "meeting": ["伊内丝", "银灰"],
            "contact": ["讯使"],
            "dormitory_1": ["塑心", "琴柳", "泥岩", "能天使", "年"],
        },
    )
    for op in data.operators.values():
        op.mood, op.time_stamp = 5, datetime.now()
    data.commit_group_shifts({"联动": False, "另一组": not free_resting})
    incoming = "银灰" if free_resting else "伊内丝"
    work = (
        {"meeting": ["Current", "初雪"]}
        if free_resting
        else {"meeting": ["陈", "银灰"], "contact": ["红"]}
    )
    final = [incoming, "琴柳", "泥岩", "能天使", "年"]
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={**work, "dormitory_1": final.copy()},
    )
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    if consumed_work:
        apply_plan(solver, {room: task.plan.pop(room) for room in work})
        assert not solver._complete_group_shift(task)
        solver._prepare_group_shift(task, remember_targets=True)
    else:
        # 剩余明确工作目标必须优先于旧的待确认状态。
        task.group_shift_transitions = {
            group: not resting
            for group, resting in task.group_shift_transitions.items()
        }
    confirmed = dict(data.group_shift_state)
    remaining = list(task.plan["dormitory_1"])
    context = solver._execution_group_transitions()
    selected = []
    due = datetime.now() + timedelta(hours=2)
    monkeypatch.setattr(
        "arknights_mower.solvers.record.save_agent_action", lambda *a, **kw: None
    )
    solver.find = MagicMock(return_value=True)
    solver.choose_agent = MagicMock(
        side_effect=lambda names, *a, **kw: selected.extend(names)
    )
    solver.tap_confirm = MagicMock()

    def read_temporary_room(room):
        for op in data.operators.values():
            if op.current_room == room:
                op.current_room, op.current_index = "", -1
        names = selected + [""] * (5 - len(selected))
        for index, name in enumerate(names):
            if not name:
                continue
            data.update_detail(
                name, data.operators[name].mood, room, index, group_transitions=context
            )
        _, bed = data.get_dorm_by_name(incoming, group_transitions=context)
        assert bed is not None and bed.name == incoming
        bed.time = due
        return [{"agent": name} for name in names]

    solver.get_agent_from_room = MagicMock(side_effect=read_temporary_room)
    assert solver.ensure_dorm_recovery_order("dormitory_1", final)
    assert selected == [incoming, "琴柳"]
    target = data.operators[incoming]
    assert (target.dorm_recovery_room, target.dorm_recovery_index) == ("dormitory_1", 0)
    assert data.operators["泥岩"].dorm_recovery_room == ""
    assert data.get_dorm_by_name(incoming, group_transitions=context)[1].time is None
    assert task.plan["dormitory_1"] == remaining
    assert data.group_shift_state == confirmed
    # 临时阵容已读回，重试只恢复最终名单，不能再次清房或换目标。
    solver.tap_confirm.reset_mock()
    assert solver.ensure_dorm_recovery_order("dormitory_1", final)
    solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("off_shift", [False, True])
def test_explicit_work_targets_override_pending_context(solver, pending, off_shift):
    row = ["陈", "初雪"] if off_shift else ["伊内丝", "银灰"]
    task = SchedulerTask(task_plan={"meeting": row})
    task.group_shift_transitions = {"联动": pending}
    solver.task = task
    confirmed = dict(solver.op_data.group_shift_state)

    assert solver._execution_group_transitions() == {"联动": off_shift}
    assert task.group_shift_transitions == {"联动": pending}
    assert solver.op_data.group_shift_state == confirmed


@pytest.mark.parametrize("entry", ["prepare", "arrange"])
@pytest.mark.parametrize("released_index", [2, 3, 4])
def test_entire_batch_cancels_caps_before_capacity(
    grouped_free_capacity, monkeypatch, entry, released_index
):
    instance = grouped_free_capacity
    data = instance.op_data
    monkeypatch.setattr(config, "stop_mower", Event())
    error_log = MagicMock()
    monkeypatch.setattr(base_schedule.logger, "error", error_log)
    data.operators["银灰"].group = "外组"
    names = ["银灰", "冰酿", "泥岩", "能天使", "年"]
    released = names[released_index]
    data.plan["meeting"][0].replacement.append(released)
    data.config.operator_mood_limits[released] = {"lower": 0, "upper": 12}
    data.operators[released].upper_limit = 12
    data.operators[released].mood = 12
    data.operators[released].time_stamp = datetime.now()
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"dormitory_1": names}
    )
    task.group_shift_transitions = {"联动": True}
    task.group_shift_expected = {
        ("dormitory_1", 0): "银灰",
        ("dormitory_1", released_index): released,
    }
    instance.task, instance.tasks = task, [task]

    def select_room(new_plan, room, plan, **kwargs):
        instance.prepare_dorm_selection(plan[room], room)
        return new_plan

    monkeypatch.setattr(instance, "agent_arrange_room", select_room)
    if entry == "prepare":
        instance.prepare_dorm_selection(task.plan["dormitory_1"], "dormitory_1")
    else:
        instance.agent_arrange(task.plan)

    assert task.plan["dormitory_1"][0] == "银灰"
    assert released not in task.plan["dormitory_1"]
    assert task.group_shift_expected == {("dormitory_1", 0): "银灰"}
    assert not config.stop_mower.is_set()
    error_log.assert_not_called()


@pytest.mark.parametrize("entry", ["auto_read", "explicit_read", "room_retry"])
@pytest.mark.parametrize("confirmation_retry", [False, True])
@pytest.mark.parametrize(
    "named_cover,free_resting", [("黑角", True), ("伊内丝", True), ("伊内丝", False)]
)
def test_mixed_pending_bed_records_observed_recovery_before_confirmation(
    solver, monkeypatch, entry, confirmation_retry, named_cover, free_resting
):
    plans = solver.global_plan["default_plan"].plan
    plans["meeting"][1].group = "另一组"
    plans["dormitory_1"][0].replacement = [named_cover]
    plans["dormitory_1"][0].group_bindings = [
        {"group": "另一组", "replacement": ["Free"]}
    ]
    assert solver.initialize_operators() is None
    data = solver.op_data
    data.commit_group_shifts({"联动": False, "另一组": not free_resting})
    for name in ("泥岩", "能天使", "年"):
        data.add(Operator(name, ""))
    apply_plan(
        solver,
        {
            "meeting": ["伊内丝", "银灰"],
            "contact": ["讯使"],
            "dormitory_1": ["塑心", "冰酿", "泥岩", "能天使", "年"],
        },
    )
    for op in data.operators.values():
        op.mood, op.time_stamp = 5, datetime.now()
    incoming = "银灰" if free_resting else named_cover
    work = (
        {"meeting": ["Current", "初雪"]}
        if free_resting
        else {"meeting": ["陈", "银灰"], "contact": ["红"]}
    )
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            **work,
            "dormitory_1": [incoming, "冰酿", "Current", "Current", "Current"],
        },
    )
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    apply_plan(solver, {room: task.plan.pop(room) for room in work})
    if confirmation_retry:
        assert not solver._complete_group_shift(task)
        solver._prepare_group_shift(task, remember_targets=True)
    # 联动下班时，完整任务还必须让讯使入宿，不能只确认固定替班。
    observed = [incoming, "冰酿", "泥岩", "能天使", "年"]
    if not free_resting:
        assert task.plan["dormitory_1"][2] == "讯使"
        assert task.group_shift_expected["dormitory_1", 2] == "讯使"
        observed[2] = "讯使"
    due = datetime.now() + timedelta(hours=6)
    monkeypatch.setattr(
        "arknights_mower.solvers.record.save_agent_action", lambda *args, **kwargs: None
    )
    solver.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
    solver.find = MagicMock(return_value=None)
    solver.enter_room = MagicMock()
    solver.refresh_facility_state = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.wait_product_complete = MagicMock()
    solver.scroll_room_operators = MagicMock()
    solver.read_screen = MagicMock(side_effect=observed)
    solver.read_accurate_mood = MagicMock(return_value=5)
    solver.read_operator_time = MagicMock(return_value=due)
    if entry == "room_retry":
        task.arrangement_retry_room = "dormitory_1"
        task.arrangement_retry_count = 1
        solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
        solver.back = MagicMock()
        solver.choose_agent = MagicMock(
            side_effect=AssertionError("unexpected selection")
        )
        solver.tap_confirm = MagicMock(
            side_effect=AssertionError("unexpected confirmation")
        )
        solver.agent_arrange_room({}, "dormitory_1", task.plan, get_time=True)
        solver.choose_agent.assert_not_called()
        solver.tap_confirm.assert_not_called()
    else:
        indexes = None
        if entry == "explicit_read":
            indexes = data.get_refresh_index(
                "dormitory_1",
                task.plan["dormitory_1"],
                group_transitions=solver._execution_group_transitions(),
            )
            assert 0 in indexes
        solver.get_agent_from_room("dormitory_1", indexes)
    beds = [bed for bed in data.all_dorms() if bed.name == incoming]
    assert len(beds) == 1
    bed = beds[0]
    assert bed.position == ("dormitory_1", 0) and bed.time == due
    assert data.group_is_resting("另一组") is (not free_resting)
    data.correct_dorm(group_transitions=solver._execution_group_transitions())
    assert bed.name == incoming and bed.time == due
    solver.read_screen = MagicMock(side_effect=observed)
    solver.read_operator_time.reset_mock()
    solver.get_agent_from_room("dormitory_1")
    solver.read_operator_time.assert_not_called()
    assert bed.name == incoming and bed.time == due
    task.plan.clear()
    assert solver._complete_group_shift(task)
    assert data.group_is_resting("另一组") is free_resting
    data.correct_dorm()
    assert bed.name == incoming and bed.time == due
