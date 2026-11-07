"""T1/T2 reserves agree between planning, API persistence and actual batch limits."""

from unittest.mock import Mock

import pytest

from arknights_mower.data import workshop_formula
from arknights_mower.tests.workshop_plan_fixtures import next_skill as next_skill
from arknights_mower.utils import config, workshop_config
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.growth_workshop import next_recipe
from arknights_mower.utils.mastery_materials import MaterialBudget
from arknights_mower.utils.workshop_limits import batch_limit


@pytest.fixture(autouse=True)
def isolated_conf(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())


def test_reserves_default_to_100_and_preserve_saved_explicit_values():
    assert (RIICPart().workshop_t1_reserve, RIICPart().workshop_t2_reserve) == (
        100,
        100,
    )
    configured = RIICPart(workshop_t1_reserve=0, workshop_t2_reserve=250)
    restored = RIICPart(**configured.model_dump())
    assert (restored.workshop_t1_reserve, restored.workshop_t2_reserve) == (0, 250)


@pytest.mark.parametrize(
    "name,child,stock,lower,batches",
    [
        ("糖", "代糖", 109, 0, 3),
        ("糖", "代糖", 102, 0, 0),
        ("糖", "代糖", 109, 105, 1),
        ("糖组", "糖", 112, 0, 3),
        ("糖组", "糖", 103, 0, 0),
        ("糖组", "糖", 112, 110, 0),
        ("技巧概要·卷3", "技巧概要·卷2", 6, 0, 2),
        ("碳素", "碳", 6, 0, 2),
    ],
)
def test_runtime_keeps_global_and_higher_group_reserves(
    name, child, stock, lower, batches
):
    setting = WorkShopItem(children_lower_limit=lower, self_upper_limit=99)
    assert (
        batch_limit(name, workshop_formula[name], setting, {name: 0, child: stock})
        == batches
    )


def test_budget_and_next_recipe_use_only_surplus_but_direct_t2_demand_uses_own_stock():
    skills = {
        "items": {
            "30021": {"name": "代糖", "rarity": 1},
            "30022": {"name": "糖", "rarity": 2},
            "30023": {"name": "糖组", "rarity": 3},
        }
    }
    formulas = {name: workshop_formula[name] for name in ("糖", "糖组")}
    stock = {"30021": 100, "30022": 112, "30023": 0}
    budget = MaterialBudget(skills, stock, formulas)
    assert budget.calculate([{"id": "30023", "count": 3}])["craftable"]
    assert not budget.calculate([{"id": "30023", "count": 4}])["craftable"]
    _, items = next_recipe(
        [("skill", [{"id": "30023", "count": 3}])], skills, stock, formulas
    )
    assert items == [
        {"item_names": ["糖组"], "children_lower_limit": 0, "self_upper_limit": 3}
    ]
    assert budget.calculate([{"id": "30022", "count": 112}])["available"]


@pytest.mark.parametrize("method", ["post", "patch"])
@pytest.mark.parametrize("token", [None, "wrong-instance"])
def test_reserve_writes_require_instance_token_before_parsing(
    next_skill, monkeypatch, method, token
):
    from flask import Request

    import server

    monkeypatch.setattr(server.app, "token", "workshop-token")
    forbidden = Mock(side_effect=AssertionError("Unauthorized config access"))
    monkeypatch.setattr(Request, "get_json", forbidden)
    monkeypatch.setattr(workshop_config, "save_conf", forbidden)
    response = getattr(server.app.test_client(), method)(
        "/conf",
        json={"workshop_t1_reserve": 0, "workshop_t2_reserve": 0},
        headers={"token": token} if token else {},
    )
    assert response.status_code == 403
    forbidden.assert_not_called()


@pytest.mark.parametrize("method", ["post", "patch"])
def test_valid_token_saves_independent_reserves_and_omitted_fields(
    next_skill, monkeypatch, method
):
    import server

    monkeypatch.setattr(server.app, "token", "workshop-token")
    client = server.app.test_client()
    response = getattr(client, method)(
        "/conf",
        json={"workshop_t1_reserve": 0, "workshop_t2_reserve": 230},
        headers={"token": "workshop-token"},
    )
    assert response.status_code == 200
    assert (config.conf.workshop_t1_reserve, config.conf.workshop_t2_reserve) == (
        0,
        230,
    )
    workshop_config.save_user_config({"workshop_protect_t2_device_rock": True})
    assert (config.conf.workshop_t1_reserve, config.conf.workshop_t2_reserve) == (
        0,
        230,
    )


@pytest.mark.parametrize("field", ["workshop_t1_reserve", "workshop_t2_reserve"])
@pytest.mark.parametrize("value", [-1, 1000000])
def test_invalid_reserve_does_not_replace_configuration(next_skill, field, value):
    import server

    previous = config.conf
    response = server.app.test_client().patch("/conf", json={field: value})
    assert response.status_code == 400
    assert config.conf is previous
