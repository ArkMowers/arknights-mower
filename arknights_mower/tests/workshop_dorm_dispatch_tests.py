"""清退与加工独立调度；无收益的加工在实际调人前结束。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import dorm_empty_release_tests
from arknights_mower.utils import config, workshop_automation
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = dorm_empty_release_tests.solver
op_data = dorm_empty_release_tests.op_data


def test_release_preparation_keeps_dorm_plan_without_crafting(solver):
    instance, _ = solver
    config.conf.workshop_settings = [RIICPart.WorkShopSetting(operator="空爆")]
    instance.craft_material = MagicMock()
    plan = instance.task.plan.copy()

    assert instance.prepare_release_dorm(instance.task)

    assert instance.task.plan == plan
    assert instance.task.type == TaskTypes.RELEASE_DORM
    instance.craft_material.assert_not_called()


@pytest.fixture
def crafting(monkeypatch):
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="谬因")
    instance.tasks = [instance.task]
    instance.enter_room = MagicMock()
    instance.agent_arrange = MagicMock()
    instance.generate_product = MagicMock()
    instance.get_agent_from_room = MagicMock(return_value=[{"agent": "特克诺"}])
    instance.op_data = SimpleNamespace(
        operators={
            "谬因": SimpleNamespace(
                current_room="dormitory_1", current_index=4, mood=24
            ),
            "特克诺": SimpleNamespace(current_room="factory", current_index=0, mood=24),
        },
        plan={"dormitory_1": ["Current"] * 5},
    )
    setting = RIICPart.WorkShopSetting(
        operator="谬因",
        items=[
            WorkShopItem(
                item_names=["提纯源岩"], children_lower_limit=0, self_upper_limit=6
            )
        ],
    )
    snapshot = SimpleNamespace(settings=[setting])
    monkeypatch.setattr(
        workshop_automation, "workshop_task_snapshot", lambda _: snapshot
    )
    stock = {"固源岩组": 4, "提纯源岩": 5}
    monkeypatch.setattr(base, "get_inventory_counts", lambda: stock)
    return instance, setting, stock, snapshot


@pytest.mark.parametrize(
    "reason", ["scope", "stock", "cap", "disabled", "mood", "reserved"]
)
def test_invalid_crafting_never_moves_dorm_operators(crafting, reason, caplog):
    instance, setting, stock, _ = crafting
    if reason == "scope":
        setting.items[0].item_names = ["糖聚块"]
    elif reason == "stock":
        stock["固源岩组"] = 3
    elif reason == "cap":
        stock["提纯源岩"] = 6
    elif reason == "disabled":
        setting.enabled = False
    elif reason == "mood":
        instance.op_data.operators["谬因"].current_mood = lambda: 0
    else:
        instance.tasks.append(
            SchedulerTask(
                task_type=TaskTypes.SHIFT_OFF,
                task_plan={"dormitory_1": ["Current"] * 4 + ["谬因"]},
            )
        )
    restoration = {}

    assert instance._craft_material(restoration) is None

    instance.enter_room.assert_not_called()
    instance.agent_arrange.assert_not_called()
    instance.generate_product.assert_not_called()
    assert restoration == {}
    expected = {
        "scope": "糖聚块缺少仓库读数",
        "stock": "固源岩组库存 3，需 4",
        "cap": "提纯源岩成品达到合成上限",
        "disabled": "加工站任务被禁用",
        "protected": "正在集中恢复",
        "mood": "心情不足（当前 0.0，需大于 0）",
        "reserved": "已被下班任务预约",
    }
    assert expected[reason] in caplog.text
    assert "请检查合成数量" not in caplog.text


def test_valid_crafting_preserves_real_restoration_and_bound_snapshot(crafting):
    instance, _, _, snapshot = crafting
    restoration = {}

    assert instance._craft_material(restoration) == "谬因"

    instance.agent_arrange.assert_called_once_with({"factory": ["谬因"]})
    instance.generate_product.assert_called_once_with("谬因", snapshot=snapshot)
    assert restoration == {
        "factory": ["特克诺"],
        "dormitory_1": ["Current"] * 4 + ["谬因"],
    }
