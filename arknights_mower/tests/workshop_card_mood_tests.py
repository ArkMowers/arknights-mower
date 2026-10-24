"""加工准入复用满心情卡牌预估，实际加工仍使用进站读数。"""

from copy import deepcopy
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, record
from arknights_mower.utils import config, scheduler_task, workshop_automation
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.utils.workshop_status import workshop_status


@pytest.fixture(params=["manual", "mastery"])
def case(request, monkeypatch):
    automatic = request.param == "mastery"
    setting = RIICPart.WorkShopSetting(
        operator="赫拉格",
        source=request.param,
        items=[
            WorkShopItem(
                item_names=["技巧概要·卷3"],
                self_upper_limit=7,
                children_lower_limit=0,
            )
        ],
    )
    monkeypatch.setattr(
        config,
        "conf",
        config.Conf(workshop_auto_active=automatic, workshop_settings=[setting]),
    )
    monkeypatch.setattr(record, "workshop_inventory_changed", Event())
    monkeypatch.setattr(workshop_automation, "_refresh_error", None)
    monkeypatch.setattr(
        workshop_automation, "refresh_workshop_after_inventory_change", lambda: True
    )
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    monkeypatch.setattr(
        workshop_automation,
        "calculate_workshop_plan",
        lambda *args, **kwargs: SimpleNamespace(focus=None, recipe="技巧概要·卷3"),
    )
    stock = {"技巧概要·卷3": 0, "技巧概要·卷2": 21}
    monkeypatch.setattr(record, "get_inventory_counts", lambda: stock)
    monkeypatch.setattr(scheduler_task, "get_inventory_counts", lambda: stock)
    monkeypatch.setattr(base_schedule, "get_inventory_counts", lambda: stock)
    data = SimpleNamespace(
        operators={"赫拉格": Operator("赫拉格", "", mood=-1)},
        dorm_mood_estimates={"赫拉格": (24, datetime.now())},
        is_standby=lambda name: False,
        plan={},
    )
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.op_data, solver.tasks, solver.task = data, [], None
    solver.sleeping = False
    solver.enter_room = MagicMock()
    solver.get_agent_from_room = MagicMock(return_value=[{"agent": "年"}])
    solver.agent_arrange = MagicMock()
    solver.generate_product = MagicMock()
    snapshot = SimpleNamespace(settings=[setting], is_current=lambda: True)
    monkeypatch.setattr(
        workshop_automation, "workshop_task_snapshot", lambda _: snapshot
    )
    return SimpleNamespace(solver=solver, data=data, setting=setting, stock=stock)


@pytest.mark.parametrize("inferred", [False, True])
def test_full_card_allows_status_queue_and_pre_move_check_without_measured_cache(
    case, inferred
):
    solver, data = case.solver, case.data
    if inferred:
        mood, observed = data.dorm_mood_estimates["赫拉格"]
        data.dorm_mood_estimates["赫拉格"] = (mood, observed, False)
    before = deepcopy(vars(data.operators["赫拉格"]))
    estimates = deepcopy(data.dorm_mood_estimates)
    assert workshop_status(solver, running=True)["execution"] == "ready"
    scheduler_task.try_workshop_tasks(data, solver.tasks)
    assert [task.meta_data for task in solver.tasks] == ["赫拉格"]
    solver.task = solver.tasks[0]
    restoration = {}
    assert solver._craft_material(restoration) == "赫拉格"
    solver.agent_arrange.assert_called_once_with({"factory": ["赫拉格"]})
    solver.generate_product.assert_called_once()
    assert restoration == {"factory": ["年"]}
    assert vars(data.operators["赫拉格"]) == before
    assert data.dorm_mood_estimates == estimates


@pytest.mark.parametrize("reason", ["expired", "future", "yellow", "red", "missing"])
def test_unusable_full_card_blocks_status_and_dispatch(case, reason):
    estimates = case.data.dorm_mood_estimates
    if reason == "expired":
        estimates["赫拉格"] = (24, datetime.now() - timedelta(hours=1))
    elif reason == "future":
        estimates["赫拉格"] = (24, datetime.now() + timedelta(minutes=1))
    elif reason in ("yellow", "red"):
        estimates["赫拉格"] = (23.9 if reason == "yellow" else 0, datetime.now())
    else:
        estimates.clear()
    status = workshop_status(case.solver, running=True)
    assert status["execution"] == "waiting"
    assert status["blockers"][0]["code"] == "mood_unknown"
    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)
    assert case.solver.tasks == []


@pytest.mark.parametrize("measured", [0, 1, 20])
def test_numeric_mood_takes_priority_and_keeps_manual_and_batch_thresholds(
    case, measured
):
    op = case.data.operators["赫拉格"]
    op.mood, op.time_stamp = measured, datetime.now()
    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)
    expected = case.setting.source == "mastery" and measured >= 2
    assert bool(case.solver.tasks) == expected
    if not expected:
        assert (
            workshop_status(case.solver, running=True)["blockers"][0]["code"]
            == "mood_insufficient"
        )


def test_expired_card_keeps_automatic_guard_and_manual_room_read(case):
    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)
    assert len(case.solver.tasks) == 1
    case.solver.task = case.solver.tasks[0]
    case.data.dorm_mood_estimates["赫拉格"] = (
        24,
        datetime.now() - timedelta(hours=1),
    )
    if case.setting.source == "mastery":
        assert case.solver._craft_material({}) is None
        case.solver.enter_room.assert_not_called()
        case.solver.agent_arrange.assert_not_called()
    else:
        # 已排入的手动任务沿用未知心情入站读取；新入队仍须超过 22。
        assert case.solver._craft_material({}) == "赫拉格"
        case.solver.agent_arrange.assert_called_once_with({"factory": ["赫拉格"]})


@pytest.mark.parametrize("reservation", ["task", "rescue"])
def test_full_card_keeps_operator_reservations(case, reservation):
    if reservation == "task":
        case.solver.tasks.append(
            SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan={"train": ["赫拉格"]})
        )
    else:
        case.data.emergency_reserved_agents = {"赫拉格"}
    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)
    assert not any(t.type == TaskTypes.WORKSHOP for t in case.solver.tasks)
    assert (
        workshop_status(case.solver, running=True)["blockers"][0]["code"]
        == "operator_reserved"
    )


def test_full_card_does_not_bypass_material_shortage(case):
    case.stock["技巧概要·卷2"] = 2
    scheduler_task.try_workshop_tasks(case.data, case.solver.tasks)
    assert case.solver.tasks == []
    assert (
        workshop_status(case.solver, running=True)["blockers"][0]["code"]
        == "material_shortage"
    )
