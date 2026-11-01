from itertools import product

import pytest
from pydantic import ValidationError

from arknights_mower.utils.config.conf import Conf


def test_value_shopping_defaults_do_not_change_old_configs():
    conf = Conf()
    assert conf.credit_shop_by_value is False
    assert conf.credit_shop_value_threshold == 0.045
    assert not conf.should_use_credit_shop_value
    saved = conf.model_dump(exclude_unset=True)
    assert "credit_shop_by_value" not in saved
    assert "credit_shop_value_threshold" not in saved


@pytest.mark.parametrize(
    "enabled,visits,mower_visits,shop,mower_shop",
    list(product([False, True], repeat=5)),
)
def test_value_shopping_requires_both_mower_runners(
    enabled, visits, mower_visits, shop, mower_shop
):
    conf = Conf(
        credit_shop_by_value=enabled,
        visit_friend_enable=visits,
        visit_friend_mode="mower" if mower_visits else "maa",
        maa_mall_enable=shop,
        maa_mall_mode="mower" if mower_shop else "maa",
        clue_credit_on_demand=False,
    )
    assert conf.should_use_credit_shop_value == all(
        (enabled, visits, mower_visits, shop, mower_shop)
    )
    assert not conf.should_defer_clue_credit


@pytest.mark.parametrize("threshold", [0, 0.032, 0.036, 0.043, 0.045])
def test_value_settings_survive_updates_and_reload(threshold):
    conf = Conf(
        credit_shop_by_value=True,
        credit_shop_value_threshold=threshold,
        clue_credit_on_demand=True,
        visit_friend_enable=True,
        visit_friend_mode="mower",
        maa_mall_enable=True,
        maa_mall_mode="mower",
        maa_mall_ignore_blacklist_when_full=True,
        maa_mall_buy="招聘许可",
        maa_mall_blacklist="家具零件",
    )
    for updates in (
        {"credit_shop_by_value": False},
        {"visit_friend_mode": "maa"},
        {"maa_mall_mode": "maa"},
    ):
        updated = conf.updated(updates)
        restored = Conf.model_validate_json(updated.model_dump_json(exclude_unset=True))
        assert not restored.should_use_credit_shop_value
        assert restored.credit_shop_by_value == updates.get(
            "credit_shop_by_value", True
        )
        assert restored.credit_shop_value_threshold == threshold
        assert restored.clue_credit_on_demand is True
        assert restored.maa_mall_ignore_blacklist_when_full is True
        assert restored.maa_mall_buy == "招聘许可"
        assert restored.maa_mall_blacklist == "家具零件"
        assert restored.updated(
            {
                "credit_shop_by_value": True,
                "visit_friend_mode": "mower",
                "maa_mall_mode": "mower",
            }
        ).should_use_credit_shop_value


@pytest.mark.parametrize("threshold", [-0.001, float("inf"), float("nan"), None])
def test_invalid_threshold_is_rejected_on_load_and_update(threshold):
    with pytest.raises(ValidationError):
        Conf(credit_shop_value_threshold=threshold)
    with pytest.raises(ValidationError):
        Conf().updated({"credit_shop_value_threshold": threshold})
