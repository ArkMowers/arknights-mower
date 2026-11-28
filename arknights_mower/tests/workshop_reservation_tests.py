"""加工可借用普通入宿安排中的干员，工作及未完成交接继续受保护。"""

from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils import config, scheduler_task, workshop_automation
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.dorm_candidates import dorm_task_reservations
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.utils.workshop_limits import workshop_operator_block_reason


@pytest.fixture
def workshop(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    setting = RIICPart.WorkShopSetting(
        operator="九色鹿",
        items=[
            WorkShopItem(item_names=["碳素", "糖聚块"], self_upper_limit=99),
        ],
    )
    config.conf.workshop_settings = [setting]
    stock = {
        "碳": 120,
        "碳素": 0,
        "糖组": 120,
        "异铁组": 120,
        "轻锰矿": 120,
        "糖聚块": 0,
        "龙门币": 10000,
    }
    data = SimpleNamespace(
        operators={
            "九色鹿": SimpleNamespace(
                name="九色鹿",
                mood=24,
                group="",
                current_room="dormitory_4",
                current_index=3,
            ),
        },
        is_standby=lambda name: False,
        plan={"dormitory_4": ["Current"] * 5},
    )
    monkeypatch.setattr(scheduler_task, "get_inventory_counts", lambda: stock)
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    monkeypatch.setattr(
        workshop_automation, "refresh_workshop_after_inventory_change", lambda: True
    )
    return SimpleNamespace(data=data, setting=setting, stock=stock)


def dorm_shift(task_type=TaskTypes.SHIFT_ON):
    return SchedulerTask(
        time=datetime.now() + timedelta(hours=2),
        task_type=task_type,
        task_plan={
            "dormitory_1": ["Current"] * 4 + ["九色鹿"],
            "room_2_1": ["Current", "Current", "结城理"],
        },
    )


@pytest.mark.parametrize(
    "task_type",
    [
        TaskTypes.SHIFT_ON,
        TaskTypes.SHIFT_OFF,
        TaskTypes.RE_ORDER,
        TaskTypes.FILL_DORM,
        TaskTypes.SELF_CORRECTION,
    ],
)
def test_dorm_destination_allows_one_workshop_task_without_changing_shift(
    workshop, task_type
):
    shift = dorm_shift(task_type)
    before = deepcopy(shift.__dict__)
    tasks = [shift]
    for _ in range(3):
        scheduler_task.try_workshop_tasks(workshop.data, tasks)
    assert tasks[0] is shift
    assert shift.__dict__ == before
    assert [(task.type, task.meta_data) for task in tasks[1:]] == [
        (TaskTypes.WORKSHOP, "九色鹿")
    ]
    assert "九色鹿" in dorm_task_reservations(workshop.data, [shift])[0]


@pytest.mark.parametrize("room", ["room_2_1", "central", "train", "factory"])
def test_work_destination_still_blocks_workshop(workshop, room):
    shift = dorm_shift()
    shift.plan[room] = ["九色鹿"]
    tasks = [shift]
    scheduler_task.try_workshop_tasks(workshop.data, tasks)
    assert tasks == [shift]
    assert (
        workshop_operator_block_reason(workshop.data, "九色鹿", tasks).code
        == "operator_reserved"
    )


@pytest.mark.parametrize(
    "protection",
    [
        "execution_retained",
        "execution_failure",
        "run_order_original_roster",
        "emergency_original_roster",
        "emergency_staffing_members",
        "urgent_recovery_reserved_names",
        "emergency_reserved_agents",
    ],
)
def test_dorm_destination_does_not_remove_other_reservations(workshop, protection):
    shift = dorm_shift()
    if protection == "emergency_reserved_agents":
        workshop.data.emergency_reserved_agents = {"九色鹿"}
    elif protection.endswith("original_roster"):
        setattr(shift, protection, {"dormitory_4": ["九色鹿"]})
    elif protection == "execution_failure":
        shift.execution_failure = {"reason": "未完成换人"}
    elif protection == "execution_retained":
        shift.execution_retained = True
    else:
        setattr(shift, protection, ["九色鹿"])
    tasks = [shift]
    scheduler_task.try_workshop_tasks(workshop.data, tasks)
    assert tasks == [shift]
    assert (
        workshop_operator_block_reason(workshop.data, "九色鹿", tasks).code
        == "operator_reserved"
    )


def test_crafting_borrows_from_actual_dorm_and_keeps_future_destination(
    workshop, monkeypatch
):
    from arknights_mower.solvers import base_schedule as base

    shift = dorm_shift()
    before = deepcopy(shift.__dict__)
    task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="九色鹿")
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.task = task
    solver.tasks = [task, shift]
    solver.op_data = workshop.data
    solver.enter_room = Mock()
    solver.get_agent_from_room = Mock(return_value=[{"agent": "空爆"}])
    solver.agent_arrange = Mock(return_value=True)
    solver.generate_product = Mock(return_value=True)
    monkeypatch.setattr(
        workshop_automation,
        "workshop_task_snapshot",
        lambda task: SimpleNamespace(settings=[workshop.setting]),
    )
    monkeypatch.setattr(base, "get_inventory_counts", lambda: workshop.stock)
    restore = {}
    assert solver._craft_material(restore) == "九色鹿"
    solver.agent_arrange.assert_called_once_with({"factory": ["九色鹿"]})
    solver.generate_product.assert_called_once()
    assert restore == {
        "factory": ["空爆"],
        "dormitory_4": ["Current", "Current", "Current", "九色鹿", "Current"],
    }
    assert shift.__dict__ == before


def test_status_allows_dorm_destination_without_mutating_tasks(workshop, monkeypatch):
    from arknights_mower.solvers import record
    from arknights_mower.utils.workshop_status import workshop_status

    shift = dorm_shift()
    before = deepcopy(shift.__dict__)
    monkeypatch.setattr(record, "get_inventory_counts", lambda: workshop.stock)
    scheduler = SimpleNamespace(op_data=workshop.data, tasks=[shift], task=None)
    status = workshop_status(scheduler, running=True)
    assert status["execution"] == "ready"
    assert status["blockers"] == []
    assert scheduler.tasks == [shift]
    assert shift.__dict__ == before
