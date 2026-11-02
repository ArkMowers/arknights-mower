"""自动合成按当前配方加成排列已配置的普通空闲加工干员。"""

import pytest

from arknights_mower.tests import dorm_release_tests
from arknights_mower.tests.resting_priority_tests import set_tier
from arknights_mower.utils import config
from arknights_mower.utils.dorm_candidates import dorm_candidates
from arknights_mower.utils.resting_priority import (
    RestingTier,
    crafting_rest_candidates,
    crafting_rest_order,
    resting_key,
    resting_tier,
)

op_data = dorm_release_tests.op_data


@pytest.fixture
def crafting(op_data, monkeypatch):
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config.conf, "workshop_auto_active", True)
    monkeypatch.setattr(config.conf, "fodder_operators", ["九色鹿", "号角", "蜜莓"])
    monkeypatch.setattr(config.conf, "t5_operators", ["年", "蜜莓"])
    monkeypatch.setattr(config.conf, "book_operators", ["赫拉格", "司霆惊蛰", "年"])
    for name in ["九色鹿", "年", "赫拉格", "号角", "蜜莓", "司霆惊蛰", "芬", "香草"]:
        op = set_tier(op_data, name, RestingTier.IDLE, 23)
        op.current_room = ""
    monkeypatch.setattr(
        "arknights_mower.utils.dorm_candidates.busy_resting_names", lambda: set()
    )
    return op_data


def test_no_pending_recipe_retains_fallback_order_without_promoting_crafters(crafting):
    names = ["九色鹿", "年", "赫拉格", "号角", "蜜莓", "司霆惊蛰"]
    baseline = ["年", "芬", "赫拉格", "司霆惊蛰", "香草", "九色鹿", "蜜莓", "号角"]
    for mood, name in enumerate(baseline, 1):
        crafting.operators[name].mood = mood
    expected = ["九色鹿", "芬", "年", "赫拉格", "香草", "号角", "蜜莓", "司霆惊蛰"]
    assert crafting_rest_order(crafting, baseline) == expected
    candidates = dorm_candidates(crafting).recovering
    assert [n for n in candidates if n in names + ["芬", "香草"]] == expected
    assert baseline[1] == expected[1] == "芬"
    assert baseline[4] == expected[4] == "香草"


@pytest.mark.parametrize("switch", ["enable_mastery", "workshop_auto_active"])
def test_disabled_crafting_retains_mood_order(crafting, monkeypatch, switch):
    monkeypatch.setattr(config.conf, switch, False)
    crafting.operators["芬"].mood = 1
    assert crafting_rest_order(crafting, ["年", "芬", "九色鹿"]) == [
        "年",
        "芬",
        "九色鹿",
    ]


@pytest.mark.parametrize(
    "tier",
    [
        RestingTier.PRIORITY,
        RestingTier.MAIN,
        RestingTier.LOW_MAIN,
        RestingTier.PRIORITY_REPLACEMENT,
        RestingTier.STANDBY,
        RestingTier.REPLACEMENT,
    ],
)
def test_crafting_does_not_override_other_identity(crafting, tier):
    set_tier(crafting, "九色鹿", tier, 23)
    set_tier(crafting, "芬", tier, 1)
    assert resting_key(crafting, "芬") < resting_key(crafting, "九色鹿")
    assert resting_key(crafting, "九色鹿") < resting_key(crafting, "年")


def test_training_support_remains_replacement(crafting):
    crafting.operators["芬"].resting_from_train = True
    assert resting_tier(crafting, "芬") == RestingTier.REPLACEMENT
    assert resting_key(crafting, "芬") < resting_key(crafting, "九色鹿")


def test_blacklist_still_excludes_crafter(crafting):
    crafting.config.free_blacklist.append("九色鹿")
    assert resting_tier(crafting, "九色鹿") == RestingTier.EXCLUDED
    assert "九色鹿" not in dorm_candidates(crafting).recovering


def test_configuration_change_takes_effect_without_cached_order(crafting, monkeypatch):
    monkeypatch.setattr(config.conf, "fodder_operators", ["号角", "九色鹿"])
    assert crafting_rest_order(crafting, ["年", "芬", "九色鹿", "号角"]) == [
        "号角",
        "芬",
        "年",
        "九色鹿",
    ]


def test_takeover_keeps_original_idle_mood_policy(crafting):
    from arknights_mower.utils.operators import Dormitory
    from arknights_mower.utils.plan import Room

    room = dorm_release_tests.ROOM
    crafting.plan[room][3] = Room("Free", "", [])
    crafting.dorm = [Dormitory((room, 3), "九色鹿"), Dormitory((room, 4), "芬")]
    for bed in crafting.dorm:
        op = crafting.operators[bed.name]
        op.current_room, op.current_index = bed.position
    crafting.operators["芬"].mood = 1
    crafting.operators["银灰"].mood = 10
    assert crafting._find_dorm_slot("银灰", set()) == 0
    # 内部先后顺序不允许加工干员挤出同层仍在休息的住客。
    assert crafting._find_dorm_slot("年", set()) is None


def test_fixed_dorm_manager_does_not_become_idle_candidate(crafting):
    manager = crafting.operators["杜林"]
    config.conf.fodder_operators.insert(0, manager.name)
    manager.current_room = dorm_release_tests.ROOM
    manager.current_index = 0
    manager.mood = 10
    assert resting_tier(crafting, manager.name) != RestingTier.IDLE
    assert manager.name not in dorm_candidates(crafting).recovering


def test_unadmitted_first_choice_moves_ahead_before_bed_limit(crafting):
    crafting.operators["年"].mood = 1
    crafting.operators["芬"].mood = 2
    crafting.operators["九色鹿"].mood = 20
    candidates = dorm_candidates(crafting).recovering
    relevant = [name for name in candidates if name in {"年", "芬", "九色鹿"}]
    assert relevant[:1] == ["九色鹿"]
    assert relevant == ["九色鹿", "芬", "年"]


def test_unavailable_first_choice_does_not_replace_eligible_crafter(crafting):
    crafting.operators["九色鹿"].current_room = "factory"
    crafting.operators["年"].mood = 1
    assert "九色鹿" not in dorm_candidates(crafting).recovering
    assert dorm_candidates(crafting).recovering.index("年") < dorm_candidates(
        crafting
    ).recovering.index("赫拉格")


def test_crafting_order_applies_to_single_target_allocation(crafting):
    from arknights_mower.utils.operators import Dormitory
    from arknights_mower.utils.plan import Room
    from arknights_mower.utils.scheduler_task import prioritize_new_dorm_recovery

    room = dorm_release_tests.ROOM
    crafting.plan[room][3] = Room("Free", "", [])
    crafting.dorm = [Dormitory((room, 3)), Dormitory((room, 4), "年")]
    crafting.operators["空爆"].current_room = ""
    crafting.operators["年"].current_room = room
    crafting.operators["年"].current_index = 4
    crafting.operators["年"].mood = 1
    plan = {room: ["Current"] * 3 + ["九色鹿", "Current"]}
    assert prioritize_new_dorm_recovery(crafting, plan)[room][3:] == [
        "九色鹿",
        "Current",
    ]
    assert crafting.operators["年"].current_index == 4


def test_completed_crafter_does_not_take_an_unfinished_candidates_position(crafting):
    crafting.operators["九色鹿"].mood = 24
    assert crafting_rest_order(crafting, ["年", "芬", "九色鹿"]) == [
        "年",
        "芬",
        "九色鹿",
    ]


def test_card_estimated_candidates_share_internal_order(crafting):
    from datetime import datetime

    for name, mood in (("年", 1), ("芬", 2), ("九色鹿", 20)):
        crafting.operators[name].time_stamp = None
        crafting.dorm_mood_estimates[name] = (mood, datetime.now())
    candidates = dorm_candidates(crafting)
    expected = ["九色鹿", "芬", "年"]
    for names in (
        candidates.unknown,
        candidates.estimated_recovering,
        candidates.filling,
    ):
        assert [name for name in names if name in expected] == expected


def test_green_card_does_not_join_crafting_recovery_order(crafting):
    from datetime import datetime

    crafting.operators["九色鹿"].time_stamp = None
    crafting.dorm_mood_estimates["九色鹿"] = (24, datetime.now())
    candidates = dorm_candidates(crafting)
    assert "九色鹿" not in candidates.estimated_recovering
    assert crafting_rest_order(crafting, ["年", "芬", "九色鹿"]) == [
        "年",
        "芬",
        "九色鹿",
    ]


def test_fill_task_preserves_crafting_order_after_candidate_merge(crafting):
    from arknights_mower.utils.scheduler_task import try_add_release_dorm

    room = dorm_release_tests.ROOM
    crafting.dorm[0].reset()
    crafting.operators["空爆"].current_room = "meeting"
    crafting.operators["红"].current_room = "meeting"
    crafting.operators["九色鹿"].mood = 20
    crafting.operators["年"].mood = 1
    tasks = []
    try_add_release_dorm({}, None, crafting, tasks)
    assert tasks[0].plan[room][4] == "九色鹿"


@pytest.mark.parametrize("occupied", [False, True])
def test_crafting_order_preserves_existing_targets_and_global_order(crafting, occupied):
    from arknights_mower.utils.operators import Dormitory
    from arknights_mower.utils.plan import Room
    from arknights_mower.utils.scheduler_task import prioritize_new_dorm_recovery

    room, other = dorm_release_tests.ROOM, "dormitory_2"
    crafting.plan[room][3] = Room("Free", "", [])
    crafting.plan[other] = [Room("Free", "", []), Room("Free", "", [])]
    crafting.operators["空爆"].current_room = ""
    crafting.dorm = [
        Dormitory((room, 3), "年" if occupied else ""),
        Dormitory((room, 4), "" if occupied else "年"),
        Dormitory((other, 0), "芬"),
        Dormitory((other, 1), "九色鹿"),
    ]
    for bed in crafting.dorm:
        if bed.name:
            op = crafting.operators[bed.name]
            op.current_room, op.current_index = bed.position
    crafting.operators["九色鹿"].mood = 1
    crafting.operators["赫拉格"].mood = 2
    plan = {
        room: ["Current"] * 3
        + (["Current", "赫拉格"] if occupied else ["赫拉格", "Current"])
    }
    result = prioritize_new_dorm_recovery(crafting, plan)
    projected = crafting.project_arrangements([result])
    assert projected.get_current_operator(room, 3).name == (
        "年" if occupied else "九色鹿"
    )
    # 新单回归属触发全宿舍重排，加工名单仍按九色鹿、年、赫拉格排序。
    assert projected.get_current_operator(other, 0).name == ("芬" if occupied else "年")
    assert projected.get_current_operator(other, 1).name == (
        "九色鹿" if occupied else "芬"
    )
    assert projected.get_current_operator(room, 4).name == "赫拉格"
    assert set(result) == ({room} if occupied else {room, other})


def test_highest_recipe_bonus_precedes_configured_t4_preferences(crafting, monkeypatch):
    from arknights_mower.tests.workshop_fixtures import owned
    from arknights_mower.utils import workshop_recommendation as workshop
    from arknights_mower.utils.config.conf import RIICPart
    from arknights_mower.utils.workshop_data import operator_metadata

    metadata = operator_metadata()
    ids = {entry["name"]: cid for cid, entry in metadata.items()}
    names = ["九色鹿", "镜匠", "蚀清", "年", "号角"]
    available = workshop.available_operators(owned(ids, *names), metadata)
    monkeypatch.setattr(workshop, "available_operators", lambda: available)
    monkeypatch.setattr(config.conf, "fodder_operators", names)
    monkeypatch.setattr(config.conf, "t5_operators", [])
    monkeypatch.setattr(config.conf, "book_operators", [])
    settings = workshop.allocate_workshop_items(
        [("fodder_operators", names, [{"item_names": ["炽合金块"]}])],
        available=available,
    )
    monkeypatch.setattr(
        config.conf,
        "workshop_settings",
        [RIICPart.WorkShopSetting(**entry) for entry in settings],
    )
    for name in names:
        set_tier(crafting, name, RestingTier.IDLE, 0).current_room = ""
    crafting.operators["号角"].mood = 20
    assert crafting_rest_candidates(crafting, names) == [
        "号角",
        "镜匠",
        "蚀清",
        "九色鹿",
        "年",
    ]
    assert [entry["operator"] for entry in settings if entry["items"]] == [
        "九色鹿",
        "镜匠",
        "蚀清",
        "号角",
    ]


def test_unconfigured_special_operators_receive_no_crafting_rest_priority(
    crafting, monkeypatch
):
    from arknights_mower.utils.config.conf import RIICPart, WorkShopItem

    monkeypatch.setattr(config.conf, "fodder_operators", ["蜜莓"])
    monkeypatch.setattr(config.conf, "t5_operators", [])
    monkeypatch.setattr(config.conf, "book_operators", [])
    monkeypatch.setattr(
        config.conf,
        "workshop_settings",
        [
            RIICPart.WorkShopSetting(
                operator="蜜莓", items=[WorkShopItem(item_names=["糖聚块"])]
            )
        ],
    )
    names = ["镜匠", "蜜莓", "蚀清", "九色鹿", "年"]
    for name in names:
        set_tier(crafting, name, RestingTier.IDLE, 5)
    assert crafting_rest_candidates(crafting, names) == ["蜜莓"]
    assert crafting_rest_order(crafting, names) == names


@pytest.mark.parametrize(
    "material,expected",
    [
        ("炽合金块", ["号角", "空爆", "蜜莓"]),
        ("糖聚块", ["蜜莓", "空爆", "号角"]),
    ],
)
def test_current_recipe_bonus_precedes_lowest_mood_in_real_fill_task(
    crafting, monkeypatch, material, expected
):
    from arknights_mower.tests.workshop_fixtures import owned
    from arknights_mower.utils import workshop_recommendation as workshop
    from arknights_mower.utils.config.conf import RIICPart
    from arknights_mower.utils.scheduler_task import try_add_release_dorm
    from arknights_mower.utils.workshop_data import operator_metadata

    metadata = operator_metadata()
    ids = {entry["name"]: cid for cid, entry in metadata.items()}
    names = ["空爆", "蜜莓", "号角"]
    available = workshop.available_operators(owned(ids, *names), metadata)
    monkeypatch.setattr(workshop, "available_operators", lambda: available)
    monkeypatch.setattr(config.conf, "fodder_operators", names)
    monkeypatch.setattr(config.conf, "t5_operators", [])
    monkeypatch.setattr(config.conf, "book_operators", [])
    settings = workshop.allocate_workshop_items(
        [("fodder_operators", names, [{"item_names": [material]}])],
        available=available,
    )
    monkeypatch.setattr(
        config.conf,
        "workshop_settings",
        [RIICPart.WorkShopSetting(**entry) for entry in settings],
    )
    for name, mood in zip(names, [0, 3, 20]):
        op = set_tier(crafting, name, RestingTier.IDLE, mood)
        op.current_room = ""
    assert crafting_rest_order(crafting, names) == expected
    crafting.dorm[0].reset()
    crafting.operators["红"].current_room = "meeting"
    for name in ["九色鹿", "年", "赫拉格", "司霆惊蛰", "芬", "香草"]:
        crafting.operators[name].mood = 24
    tasks = []
    try_add_release_dorm({}, None, crafting, tasks)
    assert tasks[0].plan[dorm_release_tests.ROOM][4] == expected[0]


def test_current_assignments_and_unlocks_are_read_again_after_recipe_changes(
    crafting, monkeypatch
):
    from arknights_mower.tests.workshop_fixtures import owned
    from arknights_mower.utils import workshop_recommendation as workshop
    from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
    from arknights_mower.utils.workshop_data import operator_metadata

    metadata = operator_metadata()
    ids = {entry["name"]: cid for cid, entry in metadata.items()}
    names = ["空爆", "蜜莓", "号角"]
    roster = owned(ids, "空爆", "号角") + owned(ids, "蜜莓", elite=0)
    available = workshop.available_operators(roster, metadata)
    monkeypatch.setattr(workshop, "available_operators", lambda: available)
    monkeypatch.setattr(config.conf, "fodder_operators", names)
    for name in names:
        set_tier(crafting, name, RestingTier.IDLE, 5).current_room = ""
    settings = [
        RIICPart.WorkShopSetting(
            operator=name, items=[WorkShopItem(item_names=["炽合金块"])]
        )
        for name in names
    ]
    runtime_conf = config.conf.model_copy(deep=True)
    runtime_conf.workshop_settings = settings
    crafting.runtime_conf = runtime_conf
    assert crafting_rest_order(crafting, names) == ["号角", "空爆", "蜜莓"]
    for entry in settings:
        entry.items = [WorkShopItem(item_names=["糖聚块"])]
    assert crafting_rest_order(crafting, names) == ["空爆", "蜜莓", "号角"]
    settings[0].enabled = False
    assert crafting_rest_order(crafting, names) == ["蜜莓", "号角", "空爆"]
    settings[1].items = []
    assert crafting_rest_order(crafting, names) == ["号角", "空爆", "蜜莓"]


def test_pending_recipe_fallback_does_not_require_a_cached_roster(
    crafting, monkeypatch
):
    from arknights_mower.utils import workshop_recommendation as workshop
    from arknights_mower.utils.config.conf import RIICPart, WorkShopItem

    def unavailable():
        raise workshop.WorkshopRecommendationError("没有缓存的干员数据")

    monkeypatch.setattr(workshop, "available_operators", unavailable)
    monkeypatch.setattr(
        config.conf,
        "workshop_settings",
        [
            RIICPart.WorkShopSetting(
                operator="蜜莓", items=[WorkShopItem(item_names=["糖聚块"])]
            )
        ],
    )
    assert crafting_rest_order(crafting, ["号角", "芬", "蜜莓"]) == [
        "蜜莓",
        "芬",
        "号角",
    ]
