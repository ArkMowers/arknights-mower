"""Current SS metadata is generated without activity-specific click coordinates."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from arknights_mower.utils import event_shop_data as generation
from arknights_mower.utils import maa_event_shop as runtime
from arknights_mower.utils.res_version import is_package_file

START = 1793487600
END = 1795291199
REWARD_END = 1795895999
ACTIVITY = {
    "basicInfo": {
        "act55side": {
            "name": "时间啊，向前！",
            "templateShopId": "shop_act55side",
            "hasStage": True,
            "startTime": START,
            "endTime": END,
            "rewardEndTime": REWARD_END,
        }
    },
    "zoneToActivity": {f"act55side_zone{i}": "act55side" for i in (1, 2, 3)},
}
ZONES = {
    f"act55side_zone{i}": {"zoneNameSecond": name}
    for i, name in enumerate(("残照终尽", "长冬初青", "世纪之春"), 1)
}
STAGES = {
    code: {
        "code": code,
        "zoneId": f"act55side_zone{i}",
        "stageDropInfo": {
            "displayDetailRewards": [
                {"type": "ACTIVITY_ITEM", "id": "act55side_token_record"}
            ]
        },
    }
    for i, code in enumerate(("TL-1", "TL-EX-1", "TL-S-1"), 1)
}


def generate(activity=None, zones=None, stages=None, now=START + 1):
    return generation.compile_activity_shops(
        activity or ACTIVITY,
        zones=ZONES if zones is None else zones,
        stages=STAGES if stages is None else stages,
        now=now,
    )


def test_current_ss_contains_navigation_metadata_and_no_coordinates():
    shop = generate()[0]
    assert shop["activity_id"] == "act55side"
    assert shop["chapters"] == {"normal": "残照终尽", "ex": "长冬初青", "s": "世纪之春"}
    assert set(shop["entry_names"]) == {"残照终尽", "长冬初青", "世纪之春"}
    assert shop["token_ids"] == ["act55side_token_record"]
    assert {"x", "y", "confirm_text"}.isdisjoint(shop)
    assert shop["end_ts"] == END
    assert shop["reward_end_ts"] == REWARD_END


@pytest.mark.parametrize("now", [START - 1, END, REWARD_END - 1])
def test_no_current_ss_after_battle_period_even_if_shop_rewards_remain(now):
    assert generate(now=now) == []


def test_special_event_and_activity_without_shop_are_not_ss_candidates():
    d = deepcopy(ACTIVITY)
    d["basicInfo"]["act55side"]["templateShopId"] = ""
    d["basicInfo"]["act999mini"] = dict(ACTIVITY["basicInfo"]["act55side"])
    assert generate(activity=d) == []


@pytest.mark.parametrize("missing", ["zones", "stages", "token"])
def test_incomplete_inputs_do_not_publish_empty_adaptation(missing):
    zones, stages = deepcopy(ZONES), deepcopy(STAGES)
    if missing == "zones":
        zones.clear()
    elif missing == "stages":
        stages.clear()
    else:
        for stage in stages.values():
            stage["stageDropInfo"]["displayDetailRewards"] = []
    with pytest.raises(ValueError):
        generate(zones=zones, stages=stages)


def test_generated_package_is_readable_and_respects_current_ss_window(
    tmp_path, monkeypatch
):
    output = tmp_path / "event_shop.json"
    generation.write_event_shop_data(
        ACTIVITY, output, zones=ZONES, stages=STAGES, now=START + 1
    )
    monkeypatch.setattr(runtime, "resource_pkg_path", lambda _: output)
    monkeypatch.setattr(
        runtime,
        "weekly_plan_uses_activity",
        lambda manager, activity, **kwargs: activity == "时间啊，向前！",
    )
    selected = runtime.select_shop(object(), START + 1)
    assert selected["token_ids"] == ["act55side_token_record"]
    assert selected["chapters"]["ex"] == "长冬初青"
    assert runtime.select_shop(object(), END) is None
    assert is_package_file("arknights_mower/data/event_shop.json")
    assert not is_package_file("arknights_mower/data/event_shop_layouts.json")


@pytest.fixture
def layouts():
    return json.loads(generation.LAYOUTS.read_text("utf-8"))


def test_legacy_client_geometry_helper_remains_readable(layouts):
    for chain in layouts["act55side"]["chains"]:
        assert generation.button_rect(chain) == pytest.approx(
            (1361.2812532, 205.0799474, 1561.2812532, 305.0799474)
        )


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


def test_later_chapter_titles_survive_before_stage_rows_are_available():
    stages = {"TL-1": STAGES["TL-1"]}
    shop = generate(stages=stages)[0]
    assert shop["chapters"]["ex"] == "长冬初青"
    assert shop["chapters"]["s"] == "世纪之春"
