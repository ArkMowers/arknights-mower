"""Automatic growth switches preserve saved choices and their dependency."""

import pytest

from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config_profile_groups import CONF_GROUPS


@pytest.mark.parametrize("legacy", [False, True])
def test_legacy_combined_switch_seeds_crafting(legacy):
    conf = Conf(enable_mastery=legacy)
    assert conf.enable_crafting is legacy
    restored = Conf.model_validate_json(conf.model_dump_json(exclude_unset=True))
    assert restored.enable_crafting is legacy
    assert restored.enable_mastery is legacy


@pytest.mark.parametrize("crafting", [False, True])
@pytest.mark.parametrize("mastery", [False, True])
@pytest.mark.parametrize("maa", [False, True])
def test_split_switch_dependency_survives_reload(crafting, mastery, maa):
    conf = Conf(enable_crafting=crafting, enable_mastery=mastery, maa_growth_enable=maa)
    restored = Conf.model_validate_json(conf.model_dump_json())
    assert restored.enable_crafting is crafting
    assert restored.enable_mastery is mastery
    assert restored.maa_growth_enable is maa
    assert restored.mastery_enabled == (crafting and mastery)
    assert restored.maa_growth_enabled == (crafting and maa)


def test_unset_defaults_do_not_become_saved_choices():
    conf = Conf()
    assert conf.enable_crafting
    assert "enable_crafting" not in conf.model_dump(exclude_unset=True)


def test_partial_save_retains_preferences_and_resumes_effective_state():
    conf = Conf(maa_growth_enable=True).updated({"enable_crafting": False})
    assert conf.enable_mastery
    assert conf.maa_growth_enable
    assert not conf.mastery_enabled
    assert not conf.maa_growth_enabled
    conf = Conf.model_validate_json(conf.model_dump_json())
    conf = conf.updated({"enable_crafting": True})
    assert conf.mastery_enabled
    assert conf.maa_growth_enabled
    assert "enable_crafting" in CONF_GROUPS["base"]
