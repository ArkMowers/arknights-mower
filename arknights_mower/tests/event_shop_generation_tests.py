"""Verified client layouts generate usable resource-package shop entries."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from arknights_mower.utils import event_shop_data as generation
from arknights_mower.utils import maa_event_shop as runtime
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.res_version import is_package_file

ACTIVITY = {
    "basicInfo": {
        "act55side": {
            "name": "时间啊，向前！",
            "templateShopId": "shop_act55side",
            "startTime": 1793487600,
            "endTime": 1795291199,
            "rewardEndTime": 1795895999,
        }
    }
}


@pytest.fixture
def layouts():
    return json.loads(generation.LAYOUTS.read_text("utf-8"))


def test_real_client_layout_gives_same_exact_rect_for_both_visuals(layouts):
    for chain in layouts["act55side"]["chains"]:
        assert generation.button_rect(chain) == pytest.approx(
            (1361.2812532, 205.0799474, 1561.2812532, 305.0799474)
        )


def test_generated_package_selects_shop_through_reward_window(tmp_path, monkeypatch):
    output = tmp_path / "event_shop.json"
    generation.write_event_shop_data(ACTIVITY, output)
    monkeypatch.setattr(runtime, "resource_pkg_path", lambda _: output)
    conf = Conf(maa_event_shop={"activity": "时间啊，向前！"}).maa_event_shop
    during_rewards = ACTIVITY["basicInfo"]["act55side"]["endTime"] + 1
    result = runtime.select_shop(conf, during_rewards)
    assert (result["x"], result["y"]) == (1461, 255)
    assert result["confirm_text"] == "炮火所掩埋的"
    assert result["end_ts"] == 1795895999
    assert runtime.select_shop(conf, 1793487599) is None
    assert runtime.select_shop(conf, 1795895999) is None
    assert is_package_file("arknights_mower/data/event_shop.json")
    assert not is_package_file("arknights_mower/data/event_shop_layouts.json")


def test_generated_entry_reaches_navigation_click_and_title_confirmation(
    tmp_path, monkeypatch
):
    from arknights_mower.solvers import event_shop

    output = tmp_path / "event_shop.json"
    generation.write_event_shop_data(ACTIVITY, output)
    monkeypatch.setattr(runtime, "resource_pkg_path", lambda _: output)
    conf = Conf(maa_event_shop={"activity": "时间啊，向前！"}).maa_event_shop
    selected = runtime.select_shop(conf, 1793487601)
    solver = object.__new__(event_shop.EventShopNavigation)
    solver.recog = MagicMock()
    monkeypatch.setattr(solver, "enter_activity_from_terminal", lambda: False)
    for method in (
        "scene_graph_navigation",
        "open_activity_overview_until_ready",
        "find_stage_image_and_enter",
        "tap",
        "wait_for_scene_stable",
    ):
        monkeypatch.setattr(solver, method, MagicMock(return_value=True))
    monkeypatch.setattr(
        event_shop.rapidocr,
        "engine",
        MagicMock(return_value=([[[], "炮火所掩埋的", 0.99]], None)),
    )
    assert solver.run(selected)
    solver.find_stage_image_and_enter.assert_called_once_with(
        "时间啊，向前！", max_swipes=10
    )
    assert solver.tap.call_args_list == [
        call((490, 1014), interval=0.2),
        call((1461, 255)),
    ]


def test_real_studio_dump_regenerates_the_button_layout(tmp_path):
    root = Path(__file__).resolve().parents[2]
    script = root / ".agents/skills/mower-version-update/scripts/extract_shop_layout.py"
    spec = importlib.util.spec_from_file_location("shop_layout_extract", script)
    extractor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extractor)
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/event_shop_act55side.json").read_text(
            "utf-8"
        )
    )
    asset_list = tmp_path / "assets.xml"
    asset_list.write_text(fixture["asset_list"], "utf-8")
    for relative, text in fixture["files"].items():
        output = tmp_path / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, "utf-8")
    chains = extractor.extract_chains(tmp_path, asset_list, fixture["container"])
    assert len(chains) == 2
    assert {chain[-2]["name"] for chain in chains} == {"kv_01_ui", "kv_02_ui"}
    assert len({chain[-1]["id"] for chain in chains}) == 2
    for chain in chains:
        assert generation.button_rect(chain) == pytest.approx(
            (1361.2812532, 205.0799474, 1561.2812532, 305.0799474)
        )


def test_parent_translation_and_scale_affect_click_rect(layouts):
    chain = layouts["act55side"]["chains"][0]
    chain[-2]["m_AnchoredPosition"] = {"x": -100, "y": -40}
    chain[-1]["m_LocalScale"] = {"x": 0.5, "y": 0.5, "z": 1}
    assert generation.button_rect(chain) == pytest.approx(
        (1311.2812532, 270.0799474, 1411.2812532, 320.0799474)
    )


@pytest.mark.parametrize("fault", ["rotation", "outside", "nan", "different_visual"])
def test_unresolved_geometry_is_rejected(layouts, fault):
    chain = layouts["act55side"]["chains"][0]
    if fault == "rotation":
        chain[-1]["m_LocalRotation"]["z"] = 0.5
    elif fault == "outside":
        chain[-1]["m_AnchoredPosition"]["x"] = 1920
    elif fault == "nan":
        chain[-1]["m_AnchoredPosition"]["x"] = float("nan")
    else:
        chain[-1]["m_AnchoredPosition"]["x"] += 10
    with pytest.raises(ValueError):
        generation.compile_activity_shops(ACTIVITY, layouts)


@pytest.mark.parametrize("fault", ["missing", "shop_id", "window", "title"])
def test_missing_activity_and_unverified_identity_do_not_publish(layouts, fault):
    activity = deepcopy(ACTIVITY)
    if fault == "missing":
        activity["basicInfo"].clear()
    elif fault == "shop_id":
        activity["basicInfo"]["act55side"]["templateShopId"] = "other_shop"
    elif fault == "window":
        activity["basicInfo"]["act55side"]["rewardEndTime"] = 1
    else:
        layouts["act55side"]["confirm_text"] = ""
    with pytest.raises(ValueError):
        generation.compile_activity_shops(activity, layouts)
