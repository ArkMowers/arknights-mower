from arknights_mower.utils.config.conf import Conf


def test_new_shop_blacklist_excludes_upgrade_materials_and_furniture_only():
    first, second = Conf(), Conf()
    assert first.maa_event_shop.blacklist == ["数据增补条", "数据增补仪", "家具零件"]
    assert "模组数据块" not in first.maa_event_shop.blacklist
    assert first.maa_event_shop.switch_source == ""
    first.maa_event_shop.blacklist.clear()
    assert second.maa_event_shop.blacklist == ["数据增补条", "数据增补仪", "家具零件"]


def test_saved_empty_or_custom_blacklist_is_preserved():
    for saved in ([], ["技巧概要", "模组数据块"]):
        conf = Conf(maa_event_shop={"blacklist": saved, "switch_source": "活动"})
        assert conf.maa_event_shop.blacklist == saved
        assert conf.maa_event_shop.switch_source == "活动"
