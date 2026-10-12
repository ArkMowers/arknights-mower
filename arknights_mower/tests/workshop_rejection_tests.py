"""A game-rejected recipe cannot cycle through workers on unchanged stock."""

from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.workshop_batch_tests import batch as batch
from arknights_mower.tests.workshop_limits_tests import game as game
from arknights_mower.tests.workshop_limits_tests import inventory as inventory
from arknights_mower.utils import config, scheduler_task, workshop_limits
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.mark.parametrize("rejection", ["list", "submit"])
def test_game_rejection_blocks_queued_workers_without_changing_stock(
    game, inventory, monkeypatch, rejection
):
    solver, state, base = game
    before = inventory.get_inventory_counts()
    if rejection == "list":
        listing = solver.item_list
        solver.item_list = lambda: [(name, pos, False) for name, pos, _ in listing()]
    else:
        solver.item_valid = lambda: False
    solver.generate_product("蜜莓")
    assert state.crafts == []
    assert inventory.get_inventory_counts() == before
    assert workshop_limits.blocked_workshop_recipes(before) == {"切削原液", "异铁块"}

    solver.agent_arrange = MagicMock()
    solver.generate_product = MagicMock()
    solver.enter_room.reset_mock()
    for name in ("空爆", "锡兰"):
        solver.task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data=name)
        assert solver._craft_material({}) is None
    solver.agent_arrange.assert_not_called()
    solver.enter_room.assert_not_called()
    solver.generate_product.assert_not_called()

    monkeypatch.setattr(
        "arknights_mower.utils.workshop_recommendation.prioritize_workshop_settings",
        lambda settings: settings,
    )
    scheduler_task.try_workshop_tasks(solver.op_data, solver.tasks)
    assert solver.tasks == []
    base.save_exception.assert_not_called()


def test_rejected_recipe_does_not_stop_other_materials(game, inventory):
    solver, state, base = game
    listing = solver.item_list
    solver.item_list = lambda: [
        (name, pos, name != "切削原液") for name, pos, _ in listing()
    ]
    solver.generate_product("蜜莓")
    assert state.crafts == [("异铁块", 1)]
    assert workshop_limits.blocked_workshop_recipes(
        inventory.get_inventory_counts()
    ) == {"切削原液"}
    base.save_exception.assert_not_called()


def test_confirmed_ingredient_change_releases_only_affected_recipe(game, inventory):
    stock = inventory.get_inventory_counts()
    for name in ("切削原液", "异铁块"):
        workshop_limits.reject_workshop_recipe(name, stock)
    inventory.apply_workshop_inventory({"化合切削液": 1})
    assert workshop_limits.blocked_workshop_recipes(
        inventory.get_inventory_counts()
    ) == {"异铁块"}


@pytest.mark.parametrize("refresh", ["inventory", "configuration"])
def test_new_observation_or_configuration_allows_retry_at_same_counts(
    game, inventory, refresh
):
    stock = inventory.get_inventory_counts()
    workshop_limits.reject_workshop_recipe("切削原液", stock)
    assert workshop_limits.blocked_workshop_recipes(stock) == {"切削原液"}
    if refresh == "inventory":
        inventory.save_inventory_counts(stock)
    else:
        config.conf.workshop_generation += 1
    assert workshop_limits.blocked_workshop_recipes(stock) == set()


def test_recognition_error_reports_failure_and_stop_signal_propagates(game):
    solver, state, base = game
    solver.factory_scene = MagicMock(side_effect=ValueError("recognition failed"))
    assert solver.generate_product("蜜莓") is False
    base.save_exception.assert_called_once()
    solver.factory_scene.side_effect = base.MowerExit()
    with pytest.raises(base.MowerExit):
        solver.generate_product("蜜莓")


def test_failed_execution_restores_staff_without_trying_next_worker(batch):
    solver = batch.solver
    solver.generate_product.side_effect = None
    solver.generate_product.return_value = False
    solver.craft_material()
    assert solver.generate_product.call_count == 1
    assert batch.arrangements == [
        {"factory": ["蜜莓"]},
        {
            "factory": ["特克诺"],
            "dormitory_1": ["蜜莓", "Current", "Current", "Current", "Current"],
        },
    ]
    assert len(solver.tasks) == 3


def test_cached_or_unrelated_snapshot_does_not_release_rejected_recipe(
    game, inventory, monkeypatch
):
    stock = inventory.get_inventory_counts()
    monkeypatch.setattr(workshop_limits, "time", lambda: 100)
    workshop_limits.reject_workshop_recipe("切削原液", stock)
    for _ in range(2):
        inventory.save_inventory_counts(stock, scanned_counts=stock, scanned_at=99)
        assert workshop_limits.blocked_workshop_recipes(stock) == {"切削原液"}
    inventory.save_inventory_counts(stock, scanned_counts={"异铁块": 0}, scanned_at=101)
    assert workshop_limits.blocked_workshop_recipes(stock) == {"切削原液"}
    inventory.save_inventory_counts(
        stock, scanned_counts={"化合切削液": stock["化合切削液"]}, scanned_at=101
    )
    assert workshop_limits.blocked_workshop_recipes(stock) == set()


def test_recipe_color_does_not_fabricate_zero_inventory(game, inventory, monkeypatch):
    import numpy as np

    from arknights_mower.solvers import base_mixin

    solver, state, base = game
    stock = inventory.get_inventory_counts()
    solver.recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    monkeypatch.setattr(
        base_mixin.rapidocr,
        "engine",
        lambda *args, **kwargs: (
            [([[0, 0], [50, 0], [50, 20], [0, 20]], "切削原液", 0.99)],
            None,
        ),
    )
    rows = base_mixin.BaseMixin.item_list(solver)
    assert rows[0][0] == "切削原液"
    assert rows[0][2] is False
    assert inventory.get_inventory_counts() == stock


def test_legacy_recipe_rejection_tracks_actual_output(game, inventory, monkeypatch):
    from arknights_mower.data import workshop_formula

    name = "家具零件_碳素"
    recipe = workshop_formula[name]
    legacy = {
        key: value
        for key, value in recipe.items()
        if key not in ("output_name", "output_count", "costs")
    }
    monkeypatch.setitem(workshop_formula, name, legacy)
    stock = {"碳素": 20, "家具零件": 10}
    workshop_limits.reject_workshop_recipe(name, stock)
    assert workshop_limits.blocked_workshop_recipes(stock) == {name}
    assert workshop_limits.blocked_workshop_recipes({**stock, "家具零件": 11}) == set()
