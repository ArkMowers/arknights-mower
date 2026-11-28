"""产物切换暂缓保留原任务说明，独立换班另列真实目标。"""

from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.raw_schedule_log_tests import base, capture
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.utils.task_presentation import build_task_presentation


def operator(current, index, primary="", *, high=False):
    return SimpleNamespace(
        current_room=current,
        current_index=index,
        room=primary,
        index=0,
        is_high=lambda: high,
    )


@pytest.fixture
def pending(caplog, monkeypatch):
    capture(caplog, monkeypatch)
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = SimpleNamespace(
        products={"room_1_2": "gold"},
        operators={
            "红": operator("dormitory_2", 3),
            "鸿雪": operator("room_1_1", 0, "room_1_1", high=True),
            "陈": operator("", -1, "central", high=True),
        },
        facility_states={
            "room_1_1": {"facility": "trade"},
            "room_1_2": {"facility": "manufacture", "product": "gold"},
        },
        get_current_operator=lambda room, index: None,
    )
    task = SchedulerTask(
        time=datetime(2026, 11, 5, 18, 3, 0),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"room_1_1": ["红"], "dormitory_1": ["鸿雪"], "central": ["陈"]},
    )
    instance.tasks = [task]
    instance._product_switching_enabled = MagicMock(return_value=True)
    instance._products_after_arrangement = MagicMock(
        side_effect=[
            ({"room_1_2": "gold"}, {}),
            ({"room_1_2": "exp3"}, {"room_1_2": [SimpleNamespace(facility="制造站")]}),
        ]
    )
    instance._split_long_product_wait = MagicMock()
    instance._product_dependent_slots = MagicMock(
        return_value={
            ("room_1_1", 0),
            ("dormitory_1", 0),
        }
    )
    return instance, task


def arrangements(caplog):
    return [record for record in caplog.records if hasattr(record, "log_task")]


@pytest.fixture
def reserved_arrangement(pending):
    instance, owner = pending
    owner.time = datetime(2026, 11, 5, 18, 21, 36, 847068)
    owner.plan = {
        "room_1_1": ["红", "Current", "Current"],
        "dormitory_1": ["Current", "Current", "鸿雪", "Current", "Current"],
    }
    owner.product_shift_locked = True
    owner.product_lock_slots = {("room_1_1", 0), ("dormitory_1", 2)}
    owner.product_lock_names = {"红", "鸿雪"}
    instance.op_data.operators["Lancet-2"] = operator("", -1)
    task = SchedulerTask(
        time=datetime(2026, 11, 5, 18, 16, 36, 847068),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={
            "room_1_1": ["陈", "Current", "Current"],
            "central": ["Lancet-2"],
        },
    )
    instance.tasks = [owner, task]
    return instance, owner, task


def test_reserved_work_position_logs_both_tasks_without_changing_their_deadlines(
    reserved_arrangement, caplog
):
    instance, owner, task = reserved_arrangement
    owner_before = deepcopy(owner.__dict__)
    original_time = task.time

    with pytest.raises(base.ProductSwitchDeferred) as caught:
        instance._defer_conflicting_product_shift_slots(task)

    assert caught.value.dependencies == (owner,)
    assert caught.value.ready_at is None
    assert owner.__dict__ == owner_before
    assert task.plan == {"room_1_1": ["陈", "Current", "Current"]}
    independent = instance.tasks[2]
    assert task.time == independent.time == original_time
    assert independent.plan == {"central": ["Lancet-2"]}
    retained, ready = arrangements(caplog)
    assert retained.getMessage() == (
        "贸易站 B101 第1位已预留给红，需等待任务「红上班；鸿雪休息」完成，"
        "任务「陈上班」暂缓执行：\n    贸易站 B101：陈、Current、Current"
    )
    assert ready.getMessage() == (
        f"已生成可先执行的任务「Lancet-2上班」，执行时间 {original_time}\n"
        "    控制中枢：Lancet-2"
    )
    assert retained.log_task["rooms"] == [
        {"id": "room_1_1", "label": "贸易站 B101", "agents": task.plan["room_1_1"]}
    ]
    assert ready.log_task["rooms"] == [
        {"id": "central", "label": "控制中枢", "agents": ["Lancet-2"]}
    ]
    retained_before = deepcopy(retained.log_task)
    task.plan["room_1_1"][0] = "砾"
    assert retained.log_task == retained_before


@pytest.mark.parametrize("conflict", ["bed", "operator"])
def test_reservation_wait_names_the_actual_bed_or_operator(
    reserved_arrangement, caplog, conflict
):
    instance, owner, task = reserved_arrangement
    if conflict == "bed":
        task.plan = {
            "dormitory_1": ["Current", "Current", "陈", "Current", "Current"],
            "central": ["Lancet-2"],
        }
        expected = "宿舍1 第3张床已预留给鸿雪"
    else:
        task.plan = {
            "room_2_1": ["红", "Current", "Current"],
            "central": ["Lancet-2"],
        }
        instance.op_data.facility_states["room_2_1"] = {"facility": "manufacture"}
        expected = "干员红已被预留"

    with pytest.raises(base.ProductSwitchDeferred) as caught:
        instance._defer_conflicting_product_shift_slots(task)

    retained, ready = arrangements(caplog)
    assert caught.value.dependencies == (owner,)
    assert retained.getMessage().startswith(
        expected + "，需等待任务「红上班；鸿雪休息」完成，"
    )
    assert "床位或替班" not in retained.getMessage()
    assert "槽位" not in retained.getMessage()
    assert "切换产物" not in retained.getMessage()
    assert ready.log_task["title"] == "Lancet-2上班"


def test_a_group_reservation_retains_the_whole_task_and_logs_no_independent_task(
    reserved_arrangement, caplog
):
    instance, owner, task = reserved_arrangement
    task.group_shift_transitions = {"示例组": True}
    original = deepcopy(task.plan)
    original_time = task.time

    with pytest.raises(base.ProductSwitchDeferred) as caught:
        instance._defer_conflicting_product_shift_slots(task)

    assert caught.value.dependencies == (owner,)
    assert instance.tasks == [owner, task]
    assert task.time == original_time and task.plan == original
    records = arrangements(caplog)
    assert len(records) == 1
    assert records[0].log_task["rooms"] == [
        {"id": "room_1_1", "label": "贸易站 B101", "agents": original["room_1_1"]},
        {"id": "central", "label": "控制中枢", "agents": ["Lancet-2"]},
    ]


def test_released_reservation_does_not_announce_another_wait(
    reserved_arrangement, caplog
):
    instance, owner, task = reserved_arrangement
    instance.tasks.remove(owner)
    original = deepcopy(task.plan)

    instance._defer_conflicting_product_shift_slots(task)

    assert task.plan == original
    assert instance.tasks == [task]
    assert arrangements(caplog) == []


@pytest.mark.parametrize("production", [True, False])
def test_real_product_switch_caller_logs_retained_and_independent_tasks(
    pending, caplog, production
):
    instance, task = pending
    original_time = task.time
    error = base.ProductSwitchDeferred(
        "当前产物尚未完成" if production else "无人机不足：需要5架，当前1架",
        rooms=["room_1_2"],
        log_reason="production" if production else None,
    )
    instance.switch_base_products = MagicMock(side_effect=error)

    with pytest.raises(base.ProductSwitchDeferred) as raised:
        instance._switch_products_before_arrangement(task)

    assert raised.value is error
    assert task is instance.tasks[0] and task.time == original_time
    assert task.plan == {"room_1_1": ["红"], "dormitory_1": ["鸿雪"]}
    assert task.product_shift_locked is True
    independent = instance.tasks[1]
    assert independent.plan == {"central": ["陈"]}
    retained, ready = arrangements(caplog)
    if production:
        assert retained.getMessage() == (
            "制造站 B102 需等待当前产物完成，再切换产物 赤金 → 中级作战记录，"
            "任务「红上班；鸿雪休息」暂缓执行：\n"
            "    贸易站 B101：红\n    宿舍1：鸿雪"
        )
    else:
        assert "无人机不足：需要5架，当前1架" in retained.getMessage()
        assert "需等待当前产物完成" not in retained.getMessage()
    assert ready.getMessage() == (
        f"已生成可先执行的任务「陈上班」，执行时间 {independent.time}\n    控制中枢：陈"
    )
    assert retained.log_task["title"] == "红上班；鸿雪休息"
    assert ready.log_task["actions"] == [
        {"kind": "operator", "subject": "陈", "action": "上班"}
    ]
    assert [
        (entry["id"], entry["agents"]) for entry in retained.log_task["rooms"]
    ] == list(task.plan.items())
    before = deepcopy(retained.log_task)
    task.plan["room_1_1"][0] = "砾"
    assert retained.log_task == before


@pytest.mark.parametrize(
    "current,index",
    [
        (None, -1),
        ("dormitory_2", -1),
        ("room_1_1", 0),
        ("room_1_1", 2),
        ("room_2_1", 0),
    ],
)
def test_working_target_does_not_invent_a_return_from_unknown_or_working_source(
    current, index
):
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"room_1_1": ["红", "Current", "Free"]},
    )
    data = SimpleNamespace(operators={"红": operator(current, index)})
    assert build_task_presentation(task, data)["actions"] == []


def test_unregistered_working_target_keeps_the_existing_fallback():
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={"central": ["陈"]}
    )
    assert (
        build_task_presentation(task, SimpleNamespace(operators={}))["title"] == "纠错"
    )


def test_each_deferred_facility_keeps_its_own_reason_and_unknown_product(
    pending, caplog
):
    instance, task = pending
    instance.op_data.facility_states["room_1_2"].pop("product")
    instance.op_data.facility_states["room_2_2"] = {
        "facility": "manufacture",
        "product": "exp3",
    }
    production = base.ProductSwitchDeferred(
        "等待当前产物", rooms=["room_1_2"], log_reason="production"
    )
    resources = base.ProductSwitchDeferred("无人机不足", rooms=["room_2_2"])
    error = base.ProductSwitchDeferred(
        "多个设施暂缓",
        rooms=["room_1_2", "room_2_2"],
        room_deferrals=[production, resources],
    )
    slots = {
        (room, index)
        for room, names in task.plan.items()
        for index in range(len(names))
    }
    instance._reserve_deferred_product_shift(
        task, slots, deferred=error, targets={"room_1_2": "exp3", "room_2_2": "gold"}
    )
    message = arrangements(caplog)[0].getMessage()
    assert (
        "制造站 B102 需等待当前产物完成，再切换产物 尚未确认 → 中级作战记录" in message
    )
    assert "制造站 B202 暂不能切换产物 中级作战记录 → 赤金（无人机不足）" in message
    assert "制造站 B202 需等待当前产物完成" not in message


def test_accelerated_observation_distinguishes_production_and_confirmation_waits(
    monkeypatch,
):
    started = datetime(2026, 11, 5, 18)
    now = [started]

    class Clock(datetime):
        @classmethod
        def now(cls):
            return now[0]

    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(
        base.config,
        "conf",
        SimpleNamespace(
            product_switching=SimpleNamespace(grandet_mode=True, waiting_seconds=20)
        ),
    )
    instance = object.__new__(base.BaseSchedulerSolver)
    instance._open_manufacture_product_detail = MagicMock()
    instance.read_manufacture_product = MagicMock(return_value="gold")
    instance._cache_facility_state = MagicMock()
    instance._manufacture_is_idle = MagicMock(return_value=False)
    instance._read_manufacture_speed = MagicMock(return_value=2)
    instance._product_switch_entry_lead_seconds = MagicMock(return_value=3)
    instance._tap_drone_accelerate = MagicMock()
    instance._select_manufacture_product = MagicMock()
    observation = {
        "room": "room_1_2",
        "current_product": "gold",
        "target_product": "exp3",
        "accelerated_at": started,
        "remaining_after_acceleration": 20,
        "production_rate": 2,
        "production_rate_observed": True,
    }
    original = deepcopy(observation)
    for elapsed, reason in [(0, "production"), (12, "confirmation")]:
        now[0] = started + timedelta(seconds=elapsed)
        with pytest.raises(base.ProductSwitchDeferred) as deferred:
            instance._change_manufacture_product(observation)
        assert deferred.value.log_reason == reason
        assert deferred.value.ready_at == started + timedelta(seconds=27)
        assert observation == original
    instance._tap_drone_accelerate.assert_not_called()
    instance._select_manufacture_product.assert_not_called()
