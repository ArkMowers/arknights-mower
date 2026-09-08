"""Workshop curated regressions."""

import pytest

from arknights_mower.tests.workshop_fixtures import (
    empty_schedule as empty_schedule,
)
from arknights_mower.tests.workshop_fixtures import (
    facility,
    owned,
)
from arknights_mower.tests.workshop_fixtures import (
    game as game,
)
from arknights_mower.utils import workshop_recommendation as workshop


@pytest.mark.parametrize("minimum", [50, 80, 95])
def test_curated_recommendations_have_independent_material_and_book_floors(
    game, minimum
):
    meta, ids = game
    names = [
        "九色鹿",
        "蚀清",
        "莱伊",
        "空爆",
        "蜜莓",
        "缇缇",
        "年",
        "号角",
        "熔泉",
        "休谟斯",
        "维荻",
        "特克诺",
        "子月",
        "赫拉格",
    ]
    result = workshop.recommend_workshop_operators(
        owned(ids, *names), meta, min_bonus=minimum
    )
    recommended = {
        key: [entry["name"] for entry in entries]
        for key, entries in result["recommendations"].items()
    }
    assert recommended["fodder_operators"] == [
        "九色鹿",
        "蚀清",
        "号角",
        "休谟斯",
        "熔泉",
    ]
    assert recommended["t5_operators"] == ["年"]
    assert set(recommended["book_operators"]) == {"子月", "赫拉格"}
    sesa = result["recommendations"]["fodder_operators"][1]
    assert sesa["material_scope"] == "t4"
    assert set(sesa["bonuses"].values()) == {80}
    for category, entries in result["recommendations"].items():
        for entry in entries:
            if entry["name"] not in {"九色鹿", "蚀清"}:
                assert min(entry["bonuses"].values()) >= (
                    80 if category == "book_operators" else 90
                )
    if minimum <= 80:
        assert "莱伊" in result["defaults"]["t5_operators"]
        assert "蜜莓" in result["defaults"]["fodder_operators"]
    else:
        assert (
            "蚀清" not in result["defaults"]["fodder_operators"]
        )  # One-click honors its configured floor.


def test_curated_exceptions_still_require_ownership_unlock_and_schedule(game):
    meta, ids = game
    locked = workshop.recommend_workshop_operators(owned(ids, "蚀清", elite=1), meta)
    assert locked["recommendations"]["fodder_operators"] == []
    blocked = workshop.recommend_workshop_operators(
        owned(ids, "九色鹿", "蚀清"),
        meta,
        plan={"backup_plans": [{"plan": {"central": facility("蚀清", ["九色鹿"])}}]},
    )
    assert all(not entries for entries in blocked["recommendations"].values())
    assert all(not entries for entries in blocked["defaults"].values())
