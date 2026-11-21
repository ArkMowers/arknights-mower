"""长产物等待按真实剩余时间说明两批任务，不改派发责任。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import product_long_wait_tests as existing
from arknights_mower.tests.raw_schedule_log_tests import capture
from arknights_mower.utils.task_presentation import (
    build_task_presentation,
    format_backup_changes,
)

base = existing.base
long_cycle = existing.long_cycle
shared_product_cycle = existing.shared_product_cycle
solver = existing.solver


@pytest.fixture
def frozen_cycle(long_cycle, caplog, monkeypatch):
    instance, task = long_cycle
    now = datetime.now()

    class Clock(datetime):
        @classmethod
        def now(cls):
            return now

    monkeypatch.setattr(base, "datetime", Clock)
    capture(caplog, monkeypatch)
    return instance, task, now


def task_records(caplog):
    return [record for record in caplog.records if hasattr(record, "log_task")]


def test_real_caller_explains_the_projected_remaining_task_and_early_task(
    frozen_cycle, caplog
):
    instance, task, now = frozen_cycle
    original_time = task.time
    positions = {
        name: (op.current_room, op.current_index)
        for name, op in instance.op_data.operators.items()
    }

    deadline = existing.defer(instance, task, 16)

    early = task.product_wait_return_task
    assert instance.tasks == [task, early] and task.time == original_time
    assert deadline == now + timedelta(minutes=16)
    assert task.plan == {
        "central": ["夕", "Current"],
        "meeting": ["Current", "虎狼丸"],
        "dormitory_1": ["Current", "Current", "森蚺", "跃跃", "Current"],
    }
    assert early.plan == {
        "central": ["Current", "令"],
        "meeting": ["Current", "跃跃"],
        "dormitory_1": ["Current", "Current", "黍", "Current", "年"],
    }
    retained = [
        record for record in task_records(caplog) if "暂缓执行：" in record.getMessage()
    ]
    ready = [
        record
        for record in task_records(caplog)
        if record.getMessage().startswith("已生成可先执行的任务")
    ]
    assert len(retained) == len(ready) == 1
    assert retained[0].getMessage() == (
        "制造站 B102 切换产物 中级作战记录 → 赤金时无人机不足，预计还需等待 16 分钟，"
        "任务「自动化休息；夕、虎狼丸上班」暂缓执行：\n"
        "    控制中枢：夕、Current\n    会客室：Current、虎狼丸\n"
        "    宿舍1：Current、Current、森蚺、跃跃、Current"
    )
    assert ready[0].getMessage() == (
        f"已生成可先执行的任务「感知上班；黍、年休息」，执行时间 {early.time}\n"
        "    控制中枢：Current、令\n    会客室：Current、跃跃\n"
        "    宿舍1：Current、Current、黍、Current、年"
    )
    assert "黍下班" not in retained[0].getMessage()
    assert retained[0].log_task["rooms"] == [
        {"id": room, "label": label, "agents": names}
        for (room, names), label in zip(
            task.plan.items(), ["控制中枢", "会客室", "宿舍1"]
        )
    ]
    assert early.execution_retained and early.product_wait_independent_return
    assert task.product_shift_locked
    assert {
        name: (op.current_room, op.current_index)
        for name, op in instance.op_data.operators.items()
    } == positions
    snapshot = deepcopy(retained[0].log_task)
    task.plan["central"][0] = "陈"
    assert retained[0].log_task == snapshot


@pytest.mark.parametrize("minutes,split", [(14, False), (15, False), (16, True)])
def test_only_the_existing_long_wait_boundary_creates_the_two_part_notice(
    frozen_cycle, caplog, minutes, split
):
    instance, task, _ = frozen_cycle
    existing.defer(instance, task, minutes)
    assert hasattr(task, "product_wait_return_task") is split
    notices = [
        record
        for record in task_records(caplog)
        if "预计还需等待" in record.getMessage()
    ]
    assert len(notices) == int(split)


def test_production_wait_does_not_claim_drone_shortage(frozen_cycle, caplog):
    instance, task, now = frozen_cycle
    instance.switch_base_products = MagicMock(
        side_effect=base.ProductSwitchDeferred(
            "当前产物尚未完成",
            ready_at=now + timedelta(minutes=16),
            rooms=["room_1_2"],
            log_reason="production",
        )
    )
    with pytest.raises(base.ProductSwitchDeferred):
        instance._switch_products_before_arrangement(task)
    notice = next(
        record
        for record in task_records(caplog)
        if "预计还需等待" in record.getMessage()
    )
    assert "当前产物尚未完成" in notice.getMessage()
    assert "无人机不足" not in notice.getMessage()


def test_named_backup_changes_remain_in_raw_log_and_metadata(frozen_cycle, caplog):
    instance, task, _ = frozen_cycle
    for index, plan in enumerate(instance.op_data.backup_plans):
        plan.name = f"副表{index + 1}"
    names = [plan.name for plan in instance.op_data.backup_plans]
    for change, index in zip(task.log_backup_changes, task.log_backup_change_indices):
        change["name"] = names[index]
    captured_changes = deepcopy(task.log_backup_changes)

    existing.defer(instance, task, 16)

    early = task.product_wait_return_task
    after_return = instance.op_data.project_arrangements([early.plan])
    after_return.commit_group_shifts(early.group_shift_transitions)
    retained = next(
        record for record in task_records(caplog) if "暂缓执行：" in record.getMessage()
    )
    changes = build_task_presentation(task, after_return)["backups"]
    assert changes and all(change["name"] in names for change in changes)
    assert retained.log_task["backups"] == changes
    assert format_backup_changes(changes) in retained.getMessage()
    assert [plan.name for plan in instance.op_data.backup_plans] == names
    assert task.log_backup_changes == captured_changes


def test_unmapped_room_deferrals_show_the_last_required_deadline(frozen_cycle, caplog):
    instance, task, now = frozen_cycle

    existing.defer(
        instance,
        task,
        0,
        room_deferrals=(
            base.ProductSwitchDeferred("制造倒计时", ready_at=now),
            base.ProductSwitchDeferred(
                "无人机不足", ready_at=now + timedelta(minutes=16)
            ),
        ),
    )

    assert instance.tasks == [task, task.product_wait_return_task]
    notice = next(
        record
        for record in task_records(caplog)
        if "预计还需等待" in record.getMessage()
    )
    assert "预计还需等待 16 分钟" in notice.getMessage()
