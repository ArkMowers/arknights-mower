"""长产物等待只提前执行不改变产物的独立回班。"""

import copy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import jsonpickle
import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import product_cover_dorm_tests as cover
from arknights_mower.tests import product_shift_cycle_resume_tests as resume
from arknights_mower.tests.shift_backup_convergence_tests import LogicExpression
from arknights_mower.utils.scheduler_task import plan_metadata

shared_product_cycle = resume.shared_product_cycle
solver = resume.solver
waiting_cover = cover.waiting_cover


@pytest.fixture
def long_cycle(shared_product_cycle):
    instance, task = shared_product_cycle
    instance.op_data.backup_plans[0].trigger = LogicExpression(
        "op_data.operators['森蚺'].is_working()", "==", "True"
    )
    for name in ("年", "黍"):
        instance.op_data.operators[name].mood = 14
    instance._prepare_group_shift(task)
    instance._prepare_shift_cycle(task)
    return instance, task


def defer(instance, task, minutes, *, room_deferrals=()):
    deadline = base.datetime.now() + timedelta(minutes=minutes)
    instance.switch_base_products = MagicMock(
        side_effect=base.ProductSwitchDeferred(
            "无人机不足", ready_at=deadline, room_deferrals=room_deferrals
        )
    )
    with pytest.raises(base.ProductSwitchDeferred):
        instance._switch_products_before_arrangement(task)
    return deadline


@pytest.mark.parametrize(
    "minutes, split", [(14, False), (15, False), (15 + 1 / 60, True), (16, True)]
)
def test_long_wait_boundary(long_cycle, monkeypatch, minutes, split):
    instance, task = long_cycle
    frozen = datetime.now()

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls):
            return frozen

    monkeypatch.setattr(base, "datetime", FrozenDateTime)
    original_time = task.time
    defer(instance, task, minutes)
    assert hasattr(task, "product_wait_return_task") is split
    assert task.time == original_time
    assert instance.op_data.operators["森蚺"].is_working()
    assert not instance.op_data.group_is_resting("自动化")
    if split:
        early = task.product_wait_return_task
        assert instance.tasks == [task, early]
        assert early.group_shift_transitions == {"感知": False}
        assert task.group_shift_transitions == {"自动化": True}
        assert task.ordinary_coordination
        assert task.coordination_request_names == ["森蚺"]
        assert "森蚺" not in early.plan.get("dormitory_1", ())
        assert set(early.plan.get("dormitory_1", ())) & {"年", "黍"}
        assert instance._products_after_arrangement(early.plan)[0] == {
            "room_1_2": "exp3"
        }
        assert "虎狼丸" in task.product_lock_names


def test_urgent_handoff_obligations_keep_original_batch(long_cycle):
    instance, task = long_cycle
    task.urgent_recovery_request_names = ["森蚺"]
    task.urgent_recovery_support_names = ["夕"]
    original_plan = copy.deepcopy(task.plan)
    defer(instance, task, 20)
    assert not hasattr(task, "product_wait_return_task")
    assert task.plan == original_plan
    assert task.urgent_recovery_request_names == ["森蚺"]


def test_return_that_changes_product_still_waits(shared_product_cycle):
    instance, task = shared_product_cycle
    instance._prepare_group_shift(task)
    instance._prepare_shift_cycle(task)
    defer(instance, task, 20)
    assert not hasattr(task, "product_wait_return_task")
    assert instance.tasks == [task]
    assert instance.op_data.group_is_resting("感知")
    assert instance.op_data.operators["森蚺"].is_working()


def test_unknown_or_short_room_keeps_batch(long_cycle):
    instance, task = long_cycle
    defer(
        instance,
        task,
        20,
        room_deferrals=(base.ProductSwitchDeferred("制造倒计时", ready_at=None),),
    )
    assert not hasattr(task, "product_wait_return_task")


@pytest.mark.parametrize("longest, split", [(14, False), (20, True)])
def test_batch_wait_uses_latest_room_observation(long_cycle, longest, split):
    instance, task = long_cycle
    defer(
        instance,
        task,
        20,
        room_deferrals=(
            base.ProductSwitchDeferred(
                "制造倒计时", ready_at=datetime.now() + timedelta(minutes=10)
            ),
            base.ProductSwitchDeferred(
                "无人机不足", ready_at=datetime.now() + timedelta(minutes=longest)
            ),
        ),
    )
    assert hasattr(task, "product_wait_return_task") is split


def test_unrelated_explicit_work_is_not_lost(long_cycle):
    instance, task = long_cycle
    task.plan["meeting"][0] = "塞雷娅"
    original_plan = copy.deepcopy(task.plan)
    defer(instance, task, 20)
    assert not hasattr(task, "product_wait_return_task")
    assert task.plan == original_plan


def test_fill_that_changes_nonproduct_backup_keeps_original_batch(long_cycle):
    instance, task = long_cycle
    instance.op_data.backup_plans[1].trigger = LogicExpression(
        "op_data.operators['年'].is_resting()", "==", "True"
    )
    original_plan = copy.deepcopy(task.plan)
    defer(instance, task, 20)
    assert not hasattr(task, "product_wait_return_task")
    assert task.plan == original_plan


def test_prepared_return_survives_task_metadata_cleanup(long_cycle):
    instance, task = long_cycle
    defer(instance, task, 20)
    early = task.product_wait_return_task
    instance.tasks = plan_metadata(instance.op_data, instance.tasks)
    assert any(queued is early for queued in instance.tasks)
    assert any(queued is task for queued in instance.tasks)
    assert early.retains_execution


def test_group_block_during_split_retains_original_product_wait(
    long_cycle, monkeypatch
):
    instance, task = long_cycle
    original_plan = copy.deepcopy(task.plan)

    def blocked(*_args, **_kwargs):
        raise base.GroupShiftBlocked({"感知"})

    monkeypatch.setattr(base.BaseSchedulerSolver, "_prepare_group_shift", blocked)
    defer(instance, task, 20)
    assert not hasattr(task, "product_wait_return_task")
    assert task.plan == original_plan


def test_real_dispatch_completes_independent_return_before_departure(long_cycle):
    instance, task = long_cycle
    original = task
    deadline = datetime.now() + timedelta(minutes=20)
    instance.switch_base_products = MagicMock(
        side_effect=base.ProductSwitchDeferred("无人机不足", ready_at=deadline)
    )
    instance.infra_main()
    early = task.product_wait_return_task
    assert task is original and task.time == deadline
    instance.agent_arrange.side_effect = lambda plan, *_args, **_kwargs: setattr(
        instance, "op_data", instance.op_data.project_arrangements([plan])
    )
    instance.task = early
    instance.infra_main()
    assert early not in instance.tasks
    assert task in instance.tasks and task.time == deadline
    assert not instance.op_data.group_is_resting("感知")
    assert not instance.op_data.group_is_resting("自动化")
    assert instance.op_data.evaluate_backup_selection().conditions == [True, False]
    instance.switch_base_products.side_effect = lambda *_args, **_kwargs: (
        instance.op_data.update_facility_state("room_1_2", "manufacture", "gold")
    )
    task.time = datetime.now() - timedelta(seconds=1)
    instance.task = task
    instance.infra_main()
    assert task not in instance.tasks
    assert instance.op_data.group_is_resting("自动化")
    assert not instance.op_data.group_is_resting("感知")


@pytest.mark.parametrize("serialized", [False, True])
def test_split_return_then_finish_original_departure(long_cycle, serialized):
    instance, task = long_cycle
    deadline = defer(instance, task, 20)
    assert hasattr(task, "product_wait_return_task")
    task.time = deadline
    if serialized:
        instance.tasks = jsonpickle.decode(jsonpickle.encode(instance.tasks))
        task = instance.tasks[0]
    early = task.product_wait_return_task
    for _ in range(2):
        instance._split_long_product_wait(
            task,
            base.ProductSwitchDeferred("无人机不足", ready_at=deadline),
            {"room_1_2": "exp3"},
        )
        with pytest.raises(base.ProductSwitchDeferred) as waiting:
            instance._prepare_shift_cycle(task)
        assert waiting.value.dependencies == (early,)
        instance._prepare_shift_cycle(early)
        assert len(instance.tasks) == 2
        assert task.time == deadline
        assert instance.op_data.evaluate_backup_selection().conditions == [True, False]
    instance.task = early
    instance._prepare_group_shift(early)
    instance._prepare_shift_cycle(early)
    instance._activate_shift_backup(early)
    instance._prepare_group_shift(early, remember_targets=True)
    instance.op_data = instance.op_data.project_arrangements([early.plan])
    assert instance._complete_group_shift(early)
    instance.tasks.remove(early)
    assert not instance.op_data.group_is_resting("感知")
    assert not instance.op_data.group_is_resting("自动化")
    assert instance.op_data.operators["森蚺"].is_working()
    assert instance.op_data.evaluate_backup_selection().conditions == [True, False]
    instance.task = task
    instance._prepare_group_shift(task)
    instance._prepare_shift_cycle(task)
    instance.switch_base_products.side_effect = lambda *_args, **_kwargs: (
        instance.op_data.update_facility_state("room_1_2", "manufacture", "gold")
    )
    instance._switch_products_before_arrangement(task)
    instance._activate_shift_backup(task)
    instance._prepare_group_shift(task, remember_targets=True)
    instance.op_data = instance.op_data.project_arrangements([task.plan])
    assert instance._complete_group_shift(task)
    assert instance.op_data.group_is_resting("自动化")
    assert not instance.op_data.group_is_resting("感知")
    assert instance.op_data.operators["森蚺"].is_resting()
    assert task.time == deadline


@pytest.mark.parametrize("empty", ["", "Free"])
def test_explicit_clear_is_not_lost_during_split(long_cycle, empty):
    instance, task = long_cycle
    task.plan["meeting"][0] = empty
    original = copy.deepcopy(task.plan)
    defer(instance, task, 20)
    assert not hasattr(task, "product_wait_return_task")
    assert task.plan == original


def test_split_replaces_old_retention_empty_slot_metadata(long_cycle):
    instance, task = long_cycle
    task.backup_retention_empty_slots = {("dormitory_1", 2): "令"}
    defer(instance, task, 20)
    assert hasattr(task, "product_wait_return_task")
    assert ("dormitory_1", 2) not in task.backup_retention_empty_slots


def test_retention_release_keeps_original_clear_obligation(waiting_cover):
    instance, task = waiting_cover
    instance.op_data.backup_plans[0].trigger = LogicExpression(
        "op_data.operators['森蚺'].is_working()", "==", "True"
    )
    task.plan["dormitory_2"] = ["Current", "Current", "Free", "Current", "Current"]
    instance._record_backup_retention(task, {"芬"})
    assert task.plan["dormitory_2"][2] == ""
    assert task.backup_retention_empty_slots == {("dormitory_2", 2): "芬"}
    original = copy.deepcopy(task.plan)
    defer(instance, task, 20)
    assert not hasattr(task, "product_wait_return_task")
    assert task.plan == original
    assert task.backup_retention_empty_slots == {("dormitory_2", 2): "芬"}
