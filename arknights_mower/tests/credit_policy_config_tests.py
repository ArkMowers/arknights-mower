import itertools

import pytest

from arknights_mower.utils.config.conf import Conf

LEGACY_POLICIES = {
    "visit_friend_mode": "maa",
    "maa_mall_mode": "maa",
    "clue_credit_on_demand": False,
    "credit_shop_by_value": False,
    "maa_mall_ignore_blacklist_when_full": True,
    "maa_mall_only_buy_discount": True,
    "maa_mall_reserve_max_credit": True,
}


@pytest.mark.parametrize("legacy", [{}, LEGACY_POLICIES])
@pytest.mark.parametrize("visits,shopping", itertools.product([False, True], repeat=2))
def test_credit_policy_migration_preserves_task_switches_and_purchase_preferences(
    legacy, visits, shopping
):
    conf = Conf(
        **legacy,
        visit_friend_enable=visits,
        maa_mall_enable=shopping,
        credit_shop_value_threshold=0.032,
        maa_mall_buy="招聘许可",
        maa_mall_blacklist="家具零件",
        stage_plan_enable=False,
        maa_credit_fight=False,
    )
    for migrated in (
        conf,
        Conf(**conf.model_dump(exclude_unset=True)),
        conf.updated(LEGACY_POLICIES),
    ):
        assert migrated.visit_friend_mode == migrated.maa_mall_mode == "mower"
        assert migrated.clue_credit_on_demand is True
        assert migrated.credit_shop_by_value is True
        assert migrated.maa_mall_ignore_blacklist_when_full is False
        assert migrated.maa_mall_only_buy_discount is False
        assert migrated.maa_mall_reserve_max_credit is False
        assert migrated.visit_friend_enable is visits
        assert migrated.maa_mall_enable is shopping
        assert migrated.should_defer_clue_credit is (visits and shopping)
        assert migrated.should_use_credit_shop_value is shopping
        assert migrated.should_run_mower_mall is shopping
        assert migrated.should_run_maa_mall is False
        assert migrated.should_run_maa_visit_friend is False
        assert migrated.should_run_maa_mall_task is False
        assert migrated.credit_shop_value_threshold == 0.032
        assert migrated.maa_mall_buy == "招聘许可"
        assert migrated.maa_mall_blacklist == "家具零件"


def test_credit_fight_remains_an_independent_maa_task():
    conf = Conf(**LEGACY_POLICIES, stage_plan_enable=False, maa_credit_fight=True)
    assert conf.should_run_maa_mall_task is True
    assert conf.should_run_maa_mall is False
    assert conf.should_run_maa_visit_friend is False
