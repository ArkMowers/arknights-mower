"""Growth recipe changes reuse remaining mood across projects and operators."""

import pytest

from arknights_mower.tests.workshop_batch_tests import batch as batch
from arknights_mower.tests.workshop_queue_tests import queue as queue
from arknights_mower.utils import (
    config,
    scheduler_task,
    workshop_automation,
    workshop_limits,
    workshop_mood,
)
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.workshop_automation import (
    workshop_task_snapshot as real_workshop_task_snapshot,
)
from arknights_mower.utils.workshop_limits import (
    workshop_material_block_reason as real_workshop_material_block_reason,
)


@pytest.mark.parametrize("mood,expected", [(1, []), (2, ["年", "泥岩"])])
def test_continuation_requires_enough_mood_for_one_recipe(
    queue, monkeypatch, mood, expected
):
    data, tasks = queue
    monkeypatch.setattr(workshop_mood, "operator_mood_rules", lambda name: ([], True))
    for setting in config.conf.workshop_settings:
        setting.items[0].item_names = ["技巧概要·卷3"]
    for operator in data.operators.values():
        operator.mood = mood
    scheduler_task.try_workshop_tasks(data, tasks, minimum_mood=0)
    assert [task.meta_data for task in tasks] == expected


@pytest.mark.parametrize("known,expected", [(False, "心情不足"), (True, None)])
def test_continuation_uses_only_unlocked_recipe_mood_reduction(
    monkeypatch, known, expected
):
    rules = [{"tabs": ["技巧概要"], "mode": "subtract", "value": 1}]
    monkeypatch.setattr(
        workshop_mood, "operator_mood_rules", lambda name: (rules, known)
    )
    item = WorkShopItem(
        item_names=["技巧概要·卷3"], self_upper_limit=2, children_lower_limit=0
    )
    reason = workshop_limits.workshop_material_block_reason(
        "赫拉格", [item], {"技巧概要·卷3": 0, "技巧概要·卷2": 6}, 1
    )
    assert reason is None if expected is None else expected in reason


def test_unaffordable_recipe_does_not_hide_an_affordable_recipe(monkeypatch):
    monkeypatch.setattr(workshop_mood, "operator_mood_rules", lambda name: ([], True))
    item = WorkShopItem(
        item_names=["提纯源岩", "技巧概要·卷3"],
        self_upper_limit=2,
        children_lower_limit=0,
    )
    assert (
        workshop_limits.workshop_material_block_reason(
            "空爆",
            [item],
            {"提纯源岩": 0, "固源岩组": 4, "技巧概要·卷3": 0, "技巧概要·卷2": 6},
            2,
        )
        is None
    )


def test_queued_operator_with_insufficient_remaining_mood_never_enters_factory(
    batch, monkeypatch
):
    from arknights_mower.solvers import base_schedule as base

    solver = batch.solver
    monkeypatch.setattr(
        workshop_limits,
        "workshop_material_block_reason",
        real_workshop_material_block_reason,
    )
    monkeypatch.setattr(workshop_mood, "operator_mood_rules", lambda name: ([], True))
    monkeypatch.setattr(
        base,
        "get_inventory_counts",
        lambda: {"技巧概要·卷3": 0, "技巧概要·卷2": 6},
    )
    batch.snapshots.return_value.settings[0].items = [
        WorkShopItem(
            item_names=["技巧概要·卷3"],
            self_upper_limit=2,
            children_lower_limit=0,
        )
    ]
    solver.op_data.operators[solver.task.meta_data].mood = 1
    assert solver._craft_material({}) is None
    solver.enter_room.assert_not_called()
    solver.agent_arrange.assert_not_called()
    solver.generate_product.assert_not_called()


def test_project_advances_continue_until_both_operators_use_all_mood(
    batch, monkeypatch
):
    from arknights_mower.solvers import base_schedule as base

    solver = batch.solver
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    monkeypatch.setattr(scheduler_task, "datetime", batch.clock)
    monkeypatch.setattr(
        "arknights_mower.utils.workshop_recommendation.prioritize_workshop_settings",
        lambda settings: settings,
    )
    monkeypatch.setattr(base, "try_workshop_tasks", scheduler_task.try_workshop_tasks)
    stock = {"技巧概要·卷3": 0, "技巧概要·卷2": 24}
    monkeypatch.setattr(scheduler_task, "get_inventory_counts", lambda: dict(stock))
    monkeypatch.setattr(base, "get_inventory_counts", lambda: dict(stock))
    names = ["年", "空爆"]
    for name in names:
        solver.op_data.operators[name].mood = 8
    config.conf.workshop_auto_active = True
    config.conf.workshop_generation = 1
    project_targets = [1, 3, 8]
    project = 0

    def configure():
        config.conf.workshop_settings = (
            [
                RIICPart.WorkShopSetting(
                    operator=name,
                    source="mastery",
                    items=[
                        WorkShopItem(
                            item_names=["技巧概要·卷3"],
                            self_upper_limit=project_targets[project],
                            children_lower_limit=0,
                        )
                    ],
                )
                for name in names
            ]
            if project < len(project_targets)
            else []
        )

    configure()
    solver.tasks.clear()
    scheduler_task.try_workshop_tasks(solver.op_data, solver.tasks, minimum_mood=0)
    solver.task = solver.tasks[0]
    batch.snapshots.side_effect = real_workshop_task_snapshot
    batches = []

    def craft(name, snapshot):
        nonlocal project
        assert snapshot.is_current()
        op = solver.op_data.operators[name]
        count = min(op.mood // 2, project_targets[project] - stock["技巧概要·卷3"])
        assert count > 0
        batches.append((project, name, count))
        stock["技巧概要·卷3"] += count
        stock["技巧概要·卷2"] -= count * 3
        op.mood -= count * 2
        batch.clock.current += scheduler_task.timedelta(seconds=30)
        if stock["技巧概要·卷3"] == project_targets[project]:
            project += 1
            configure()
            config.conf.workshop_generation += 1

    solver.generate_product.side_effect = craft
    solver.craft_material()
    assert batches == [(0, "年", 1), (1, "年", 2), (2, "年", 1), (2, "空爆", 4)]
    assert stock == {"技巧概要·卷3": 8, "技巧概要·卷2": 0}
    assert all(solver.op_data.operators[name].mood == 0 for name in names)
    assert solver.tasks == []
    assert batch.arrangements[-1]["factory"] == ["特克诺"]
    batch.errors.assert_not_called()
