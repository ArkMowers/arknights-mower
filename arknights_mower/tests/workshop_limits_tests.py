"""Workshop caps cover batch yields, reserves, byproducts and queued operators."""

import csv
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.data import workshop_formula  # noqa: E402
from arknights_mower.solvers import record  # noqa: E402
from arknights_mower.utils import config, workshop_limits  # noqa: E402
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem  # noqa: E402


@pytest.fixture
def inventory(monkeypatch, tmp_path):
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(
        record,
        "get_path",
        lambda name: tmp_path / "data.db" if name.endswith(".db") else tmp_path,
    )
    return record


@pytest.mark.parametrize(
    "name,stock,upper,lower,expected",
    [
        (
            "切削原液",
            {"切削原液": 3, "化合切削液": 158, "晶体元件": 50, "RMA70-12": 80},
            6,
            0,
            3,
        ),
        (
            "切削原液",
            {"切削原液": 6, "化合切削液": 158, "晶体元件": 50, "RMA70-12": 80},
            6,
            0,
            0,
        ),
        ("技巧概要·卷3", {"技巧概要·卷3": 0, "技巧概要·卷2": 22}, 30, 20, 0),
        ("技巧概要·卷3", {"技巧概要·卷3": 0, "技巧概要·卷2": 29}, 30, 20, 3),
        ("重装芯片", {"重装芯片": 3, "医疗芯片": 12}, 6, 0, 1),
        ("重装芯片", {"重装芯片": 5, "医疗芯片": 12}, 6, 0, 0),
        ("碳素", {"碳素": 0, "碳": 9999}, 9999, 0, 99),
        ("碳素", {"碳": 9999}, 9999, 0, 0),
        ("碳素", {"碳素": 0}, 9999, 0, 0),
    ],
)
def test_batch_budget(name, stock, upper, lower, expected):
    setting = WorkShopItem(self_upper_limit=upper, children_lower_limit=lower)
    assert (
        workshop_limits.batch_limit(name, workshop_formula[name], setting, stock)
        == expected
    )


def test_furniture_recipes_share_real_output_stock():
    name = "家具零件_碳素组"
    output, count, _ = workshop_limits.recipe_quantities(name, workshop_formula[name])
    assert output == "家具零件"
    stock = {output: 100, "碳素组": 8}
    setting = WorkShopItem(self_upper_limit=100 + 2 * count - 1, children_lower_limit=0)
    assert (
        workshop_limits.batch_limit(name, workshop_formula[name], setting, stock) == 1
    )


@pytest.mark.parametrize("gold", [None, 0])
def test_gold_is_assumed_sufficient_and_is_not_counted(gold):
    name = "聚合剂"
    recipe = workshop_formula[name]
    stock = {name: 0, **{child: 10 for child in recipe["items"]}}
    if gold is not None:
        stock["龙门币"] = gold
    setting = WorkShopItem(self_upper_limit=3, children_lower_limit=0)
    assert workshop_limits.batch_limit(name, recipe, setting, stock) == 3
    assert "龙门币" not in workshop_limits.batch_delta(name, recipe, 3)


@pytest.mark.parametrize("name", list(workshop_formula))
def test_old_resource_quantities_fall_back_to_matching_builtin(name):
    old = {
        k: v
        for k, v in workshop_formula[name].items()
        if k not in {"costs", "output_name", "output_count"}
    }
    assert workshop_limits.recipe_quantities(
        name, old
    ) == workshop_limits.recipe_quantities(name, workshop_formula[name])
    old["items"] = ["未知材料"]
    assert workshop_limits.recipe_quantities(name, old) is None


@pytest.mark.parametrize(
    "gap,cost,count", [(40, 2, 19), (8, 2, 3), (7, 2, 3), (4, 4, 1), (1, 4, 1)]
)
def test_deer_batch_stops_before_guaranteed_byproduct(gap, cost, count):
    assert workshop_limits.deer_batch_limit(gap, cost) == count


def test_only_guaranteed_outputs_and_inputs_are_counted(inventory):
    inventory.save_inventory_counts({"碳": 100, "碳素": 5})
    delta = workshop_limits.batch_delta("碳素", workshop_formula["碳素"], 10)
    inventory.apply_workshop_inventory(delta)
    assert inventory.get_inventory_counts() == {"碳": 70, "碳素": 15}


@pytest.mark.parametrize("batches", [0, -1, 1.5])
def test_invalid_batch_is_not_counted(batches):
    with pytest.raises(ValueError):
        workshop_limits.batch_delta("碳素", workshop_formula["碳素"], batches)


def test_cached_depot_reads_do_not_revert_crafting_after_reopening_database(inventory):
    old = {"碳": 100, "碳素": 5}
    inventory.save_inventory_counts(old)
    inventory.apply_workshop_inventory(
        workshop_limits.batch_delta("碳素", workshop_formula["碳素"], 3)
    )
    for _ in range(2):
        result = inventory.save_inventory_counts(old, scanned_counts=old, scanned_at=0)
        assert result == {"碳": 91, "碳素": 8}
        assert inventory.get_inventory_counts() == result
    # A new in-game scan counts loot, byproducts and training consumption too.
    actual = {"碳": 91, "碳素": 10}
    result = inventory.save_inventory_counts(
        old, scanned_counts=actual, scanned_at=10_000_000_000
    )
    assert result == actual
    assert (
        inventory.save_inventory_counts(
            old, scanned_counts=actual, scanned_at=10_000_000_000
        )
        == actual
    )


def test_unconfirmed_stock_stays_unknown_until_new_in_game_scan(inventory):
    old = {"碳": 100, "碳素": 5}
    inventory.save_inventory_counts(old)
    inventory.invalidate_workshop_inventory(old)
    assert inventory.save_inventory_counts(old, scanned_counts=old, scanned_at=0) == {}
    assert inventory.get_inventory_counts() == {}
    # Missing materials in a complete new scan mean zero; cached API values don't win.
    assert inventory.save_inventory_counts(
        old, scanned_counts={"碳": 91}, scanned_at=10_000_000_000
    ) == {"碳": 91, "碳素": 0}


@pytest.fixture
def game(monkeypatch, inventory):
    from arknights_mower.solvers import base_schedule as base

    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(
        base, "cultivateDepotSolver", lambda: SimpleNamespace(start=lambda: None)
    )
    monkeypatch.setattr(base, "save_exception", MagicMock())
    monkeypatch.setattr(base, "send_message", MagicMock())
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = MagicMock(w=1920, h=1080)
    solver.op_data = SimpleNamespace(operators={})
    state = SimpleNamespace(
        scene=base.Scene.FACTORY_DASHBOARD,
        selected=None,
        count=1,
        crafts=[],
        remaining=99,
        timeout=False,
    )
    for name in ["back_to_infrastructure", "enter_room", "swipe_noinertia", "sleep"]:
        setattr(solver, name, MagicMock())
    solver.factory_scene = lambda: state.scene
    solver.find = lambda name: name == "factory_warning" and state.remaining == 0
    solver.item_valid = lambda: state.remaining > 0
    materials = ["切削原液", "异铁块", "固源岩", "固源岩组", "聚合剂"]
    positions = {
        name: ((10 + i * 20, 10), (20 + i * 20, 20)) for i, name in enumerate(materials)
    }
    solver.item_list = lambda: [(name, pos, True) for name, pos in positions.items()]

    def tap(pos, **kwargs):
        if pos == (1920 * 0.45, 1080 * 0.65):
            state.scene = base.Scene.FACTORY_FORMULA
        elif pos == (1920 * 0.84, 1080 * 0.4):
            state.count = min(state.count + 1, max(1, state.remaining))
        elif pos == (1920 * 0.88, 1080 * 0.88):
            state.crafts.append((state.selected, state.count))
            state.remaining -= state.count
            state.scene = (
                base.Scene.FACTORY_DASHBOARD
                if state.timeout
                else base.Scene.FACTORY_PRODUCT_COLLECT
            )
        else:
            assert pos != (1920 * 0.95, 1080 * 0.4), "must not tap MAX"
            for name, box in positions.items():
                if pos == ((box[0][0] + box[1][0]) / 2, 15):
                    state.selected, state.count = name, 1
                    state.scene = base.Scene.FACTORY_DASHBOARD

    solver.tap = tap
    solver.back = lambda: setattr(state, "scene", base.Scene.FACTORY_DASHBOARD)

    inventory.save_inventory_counts(
        {
            "切削原液": 3,
            "化合切削液": 158,
            "晶体元件": 50,
            "RMA70-12": 80,
            "异铁块": 0,
            "异铁组": 10,
            "全新装置": 10,
            "聚酸酯组": 10,
        }
    )
    for name in ["蜜莓", "空爆", "锡兰"]:
        solver.op_data.operators[name] = SimpleNamespace(mood=24)
        config.conf.workshop_settings.append(
            RIICPart.WorkShopSetting(
                operator=name,
                items=[
                    WorkShopItem(
                        item_names=[material],
                        children_lower_limit=0,
                        self_upper_limit=6 if material == "切削原液" else 1,
                    )
                    for material in materials[:2]
                ],
            )
        )
    return solver, state, base


def test_multiple_operators_recheck_caps_after_each_confirmed_batch(game, inventory):
    solver, state, base = game
    state.remaining = 3
    solver.op_data.operators["蜜莓"].mood = 12
    solver.generate_product("蜜莓")
    state.remaining = 99
    solver.generate_product("空爆")
    solver.generate_product("锡兰")
    base.save_exception.assert_not_called()
    assert state.crafts == [("切削原液", 3), ("异铁块", 1)]
    assert inventory.get_inventory_counts()["切削原液"] == 6
    assert inventory.get_inventory_counts()["异铁块"] == 1


def test_same_operator_switches_material_when_cap_is_reached(game, inventory):
    solver, state, base = game
    solver.generate_product("蜜莓")
    base.save_exception.assert_not_called()
    assert state.crafts == [("切削原液", 3), ("异铁块", 1)]


def test_unconfirmed_completion_blocks_following_operators_from_reusing_unknown_stock(
    game, inventory
):
    solver, state, base = game
    state.timeout = True
    solver.generate_product("蜜莓")
    assert "切削原液" not in inventory.get_inventory_counts()
    assert "化合切削液" not in inventory.get_inventory_counts()
    state.timeout = False
    solver.generate_product("空爆")
    assert state.crafts == [("切削原液", 3), ("异铁块", 1)]
    assert base.send_message.call_count == 1


def test_mood_budget_limits_clicks_before_game_can_clamp_quantity(game, inventory):
    solver, state, base = game
    state.remaining = 2
    solver.op_data.operators["蜜莓"].mood = 8
    solver.generate_product("蜜莓")
    state.remaining = 99
    solver.generate_product("空爆")
    base.save_exception.assert_not_called()
    assert state.crafts == [("切削原液", 2), ("切削原液", 1), ("异铁块", 1)]
    assert inventory.get_inventory_counts()["切削原液"] == 6


@pytest.mark.parametrize("mood", [0, 0.5, 3])
def test_insufficient_mood_skips_all_unaffordable_recipes_without_scanning(game, mood):
    solver, state, base = game
    solver.op_data.operators["蜜莓"].mood = mood
    solver.item_list = MagicMock(wraps=solver.item_list)
    solver.factory_scene = MagicMock(wraps=solver.factory_scene)
    solver.generate_product("蜜莓")
    base.save_exception.assert_not_called()
    solver.item_list.assert_not_called()
    solver.factory_scene.assert_not_called()
    assert state.crafts == []


@pytest.mark.parametrize(
    "mood,expected", [(3, [("固源岩", 3)]), (7, [("切削原液", 1), ("固源岩", 3)])]
)
def test_remaining_mood_selects_only_affordable_materials_and_stops_without_rescan(
    game, inventory, mood, expected
):
    solver, state, base = game
    solver.op_data.operators["蜜莓"].mood = mood
    config.conf.workshop_settings[0].items.append(
        WorkShopItem(item_names=["固源岩"], self_upper_limit=10, children_lower_limit=0)
    )
    inventory.save_inventory_counts({"固源岩": 0, "源岩": 99})
    solver.item_list = MagicMock(wraps=solver.item_list)
    solver.generate_product("蜜莓")
    base.save_exception.assert_not_called()
    assert state.crafts == expected
    assert solver.op_data.operators["蜜莓"].mood == 0
    assert solver.item_list.call_count == len(expected)


@pytest.mark.parametrize("known_exhausted", [True, False])
def test_exhausted_operator_skips_before_entry_or_immediately_after_existing_mood_read(
    game, monkeypatch, known_exhausted
):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    solver, state, base = game
    solver.task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="蜜莓")
    solver.op_data.operators = {
        "蜜莓": SimpleNamespace(
            mood=0 if known_exhausted else 24, current_room="", current_index=-1
        ),
        "特克诺": SimpleNamespace(mood=24, current_room="factory", current_index=0),
    }

    def arrange(plan):
        if plan == {"factory": ["蜜莓"]}:
            solver.op_data.operators["蜜莓"].mood = 0

    solver.agent_arrange = MagicMock(side_effect=arrange)
    solver.factory_scene = MagicMock(wraps=solver.factory_scene)
    sync = MagicMock()
    monkeypatch.setattr(
        base, "cultivateDepotSolver", lambda: SimpleNamespace(start=sync)
    )
    solver.craft_material()
    base.save_exception.assert_not_called()
    sync.assert_not_called()
    solver.factory_scene.assert_not_called()
    assert state.crafts == []
    if known_exhausted:
        solver.enter_room.assert_not_called()
        solver.agent_arrange.assert_not_called()
    else:
        assert [call.args[0] for call in solver.agent_arrange.call_args_list] == [
            {"factory": ["蜜莓"]},
            {"factory": ["特克诺"]},
        ]


@pytest.mark.parametrize("old_mood,room", [(0, "dormitory_1"), (-1, "")])
def test_resting_or_unknown_mood_is_refreshed_by_existing_entry_read(
    game, old_mood, room
):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    solver, state, base = game
    solver.task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="蜜莓")
    solver.op_data.operators = {
        "蜜莓": SimpleNamespace(mood=old_mood, current_room=room, current_index=2),
    }

    def arrange(plan):
        solver.op_data.operators["蜜莓"].mood = 24
        solver.op_data.operators["蜜莓"].current_room = "factory"

    solver.agent_arrange = MagicMock(side_effect=arrange)
    solver.craft_material()
    base.save_exception.assert_not_called()
    solver.agent_arrange.assert_called_once_with({"factory": ["蜜莓"]})
    assert state.crafts == [("切削原液", 3), ("异铁块", 1)]


def test_count_and_byproducts_do_not_require_new_ocr(game):
    solver, state, base = game
    solver.get_number = MagicMock(side_effect=AssertionError("Unexpected number OCR"))
    solver.generate_product("蜜莓")
    base.save_exception.assert_not_called()
    solver.get_number.assert_not_called()
    assert state.crafts == [("切削原液", 3), ("异铁块", 1)]


@pytest.mark.parametrize(
    "agent,elite,material,expected,cost",
    [
        ("蜜莓", 0, "固源岩", 24, 1),
        ("蜜莓", 0, "固源岩组", 12, 2),
        ("蜜莓", 0, "切削原液", 6, 4),
        ("蜜莓", 0, "聚合剂", 3, 8),
        ("缇缇", 0, "聚合剂", 3, 8),
        ("缇缇", 2, "聚合剂", 6, 4),
        ("年", 0, "聚合剂", 2, 10),
        ("泥岩", 0, "切削原液", 12, 2),
        ("止颂", 2, "固源岩组", 8, 3),
    ],
)
def test_unlocked_costs_limit_actual_button_clicks(
    game, inventory, monkeypatch, agent, elite, material, expected, cost
):
    from arknights_mower.utils import workshop_data, workshop_mood

    solver, state, base = game
    cid = next(
        (
            cid
            for cid, meta in workshop_mood._bundled_moods().items()
            if meta["name"] == agent
        ),
        "char_test",
    )
    monkeypatch.setattr(
        workshop_data,
        "owned_roster",
        lambda: [{"id": cid, "evolvePhase": elite, "level": 1}],
    )
    config.conf.workshop_settings = [
        RIICPart.WorkShopSetting(
            operator=agent,
            items=[
                WorkShopItem(
                    item_names=[material], self_upper_limit=100, children_lower_limit=0
                )
            ],
        )
    ]
    output, _, costs = workshop_limits.recipe_quantities(
        material, workshop_formula[material]
    )
    inventory.save_inventory_counts({output: 0, **{child: 999 for child in costs}})
    solver.op_data.operators[agent] = SimpleNamespace(mood=24)
    state.remaining = expected
    solver.generate_product(agent)
    base.save_exception.assert_not_called()
    assert state.crafts == [(material, expected)]
    assert inventory.get_inventory_counts()[output] == expected
    assert solver.op_data.operators[agent].mood == 24 - expected * cost


def test_real_depot_read_keeps_crafted_counts_in_database_and_page(
    inventory, monkeypatch, tmp_path
):
    from arknights_mower.data import key_mapping
    from arknights_mower.utils import depot

    monkeypatch.setattr(
        depot, "get_path", lambda name: tmp_path / name.rsplit("/", 1)[-1]
    )
    cloud = {"data": {"items": [{"id": key_mapping["碳素"][0], "count": "5"}]}}
    (tmp_path / "cultivate.json").write_text(json.dumps(cloud))
    with (tmp_path / "depotresult.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Data", "json"])
        writer.writerow([1, json.dumps({"碳": 100, "碳素": 5}), "{}"])
    depot.读取仓库()
    inventory.apply_workshop_inventory({"碳": -9, "碳素": 3})
    for _ in range(2):
        page, ids, _ = depot.读取仓库()
        assert inventory.get_inventory_counts()["碳素"] == 8
        assert json.loads(ids)[key_mapping["碳素"][0]] == 8
        assert page["K未分类"]["碳素"]["number"] == 8
