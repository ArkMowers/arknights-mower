from unittest.mock import patch

import pytest

from arknights_mower.utils import config, workshop_config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.plan_advanced import apply_advanced_settings


@pytest.mark.parametrize("limit", [-1, 0, 19])
def test_config_save_rejects_drone_reserve_below_twenty(limit):
    original = Conf(drone_count_limit=100, workshop_preset_migrated=True)
    before = original.model_dump()
    with (
        patch.object(config, "conf", original),
        patch.object(workshop_config, "save_conf") as save,
    ):
        with pytest.raises(ValueError, match="无人机使用阈值不能低于 20"):
            workshop_config.save_user_config({"drone_count_limit": limit})
        save.assert_not_called()
        assert config.conf is original
        assert original.model_dump() == before


@pytest.mark.parametrize("limit", [20, 100, "20"])
def test_config_save_accepts_drone_reserve_at_or_above_twenty(limit):
    original = Conf(drone_count_limit=0, workshop_preset_migrated=True)
    with (
        patch.object(config, "conf", original),
        patch.object(workshop_config, "save_conf") as save,
    ):
        workshop_config.save_user_config({"drone_count_limit": limit})
        save.assert_called_once()
        assert save.call_args.args[0].drone_count_limit == int(limit)
        assert original.drone_count_limit == 0


@pytest.mark.parametrize("limit", [-1, 0, 19, 19.5, None, "invalid"])
def test_plan_advanced_settings_reject_invalid_drone_reserve(limit):
    original = Conf(drone_count_limit=100)
    with pytest.raises(ValueError):
        apply_advanced_settings(original, {"drone_count_limit": limit})
    assert original.drone_count_limit == 100


@pytest.mark.parametrize("limit", [20, 100, "20"])
def test_plan_advanced_settings_accept_drone_reserve_at_or_above_twenty(limit):
    original = Conf(drone_count_limit=0)
    updated = apply_advanced_settings(original, {"drone_count_limit": limit})
    assert updated.drone_count_limit == int(limit)
    assert original.drone_count_limit == 0


@pytest.mark.parametrize("limit", [0, 19])
def test_legacy_drone_reserve_loads_without_rewriting_user_file(tmp_path, limit):
    path = tmp_path / "conf.yml"
    content = f"drone_count_limit: {limit}\n"
    path.write_text(content, encoding="utf-8")
    with (
        patch.object(config, "conf_path", path),
        patch.object(config, "conf", config.conf),
        patch.object(config, "_load_rescue_plan"),
        patch.object(config, "save_conf") as save,
    ):
        config.load_conf()
        assert config.conf.drone_count_limit == limit
        assert config.conf.updated({"free_room": True}).drone_count_limit == limit
        assert (
            apply_advanced_settings(config.conf, {"free_room": True}).drone_count_limit
            == limit
        )
        save.assert_not_called()
        assert path.read_text(encoding="utf-8") == content
