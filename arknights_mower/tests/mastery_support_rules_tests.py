"""Mastery assistant rules regressions."""

import pytest

from arknights_mower.tests.mastery_support_fixtures import (
    facility as facility,
)
from arknights_mower.tests.mastery_support_fixtures import (
    game as game,
)
from arknights_mower.tests.mastery_support_fixtures import (
    owned as owned,
)
from arknights_mower.utils import mastery_support as support
from arknights_mower.utils.mastery_rules import compile_buff, compile_training_data


@pytest.mark.parametrize("backup", [False, True])
@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize("booster", sorted(support.CONTROL_TRAINERS))
def test_central_all_primary_backup_and_replacements(backup, replacement, booster):
    table = {
        "central": facility("普通干员", [booster]) if replacement else facility(booster)
    }
    plan = {
        "default": "plan1",
        "plan1": {} if backup else table,
        "backup_plans": [{"plan": table}] if backup else [],
    }
    blocked, central = support.schedule_context(plan)
    assert central == 5
    assert blocked[booster] == {"central"}


def test_schedule_excludes_every_nontraining_room_and_ignores_placeholders():
    plan = {
        "plan1": {
            "train": facility("逻各斯", ["艾丽妮"]),
            "room_1_1": facility("甲", ["乙", "Current"]),
            "dormitory_1": facility("丙", ["Free"]),
        },
        "backup_plans": [
            {
                "plan": {
                    "gaming_1": facility("丁", ["戊"]),
                    "meeting": facility("阿斯卡纶"),
                }
            }
        ],
    }
    blocked, central = support.schedule_context(plan)
    assert set(blocked) == {"甲", "乙", "丙", "丁", "戊", "阿斯卡纶"}
    assert central == 0


def test_generated_resources_cover_unskilled_trainers_and_reducer_unlocks(game):
    data, ids = game
    assert data[ids["芬"]]["subProfessionId"]
    logos = data[ids["逻各斯"]]
    target = {"profession": "CASTER"}
    assert not support.trainer_stats(logos, owned(ids["逻各斯"], 1), target, 1)[
        "halves"
    ]
    assert support.trainer_stats(logos, owned(ids["逻各斯"]), target, 1)["halves"]


def test_branch_bonus_and_upgrades_do_not_double_count():
    rule = compile_buff(
        {
            "buffId": "branch",
            "roomType": "TRAINING",
            "efficiency": 30,
            "targets": ["WARRIOR"],
            "description": "近卫干员的专精技能训练速度+30%，如果训练目标的分支为领主，训练速度额外+45%",
        }
    )
    meta = {
        "name": "教官",
        "groups": [
            [
                {"elite": 0, "level": 1, "effects": [{"kind": "speed", "bonus": 20}]},
                {"elite": 2, "level": 1, "effects": rule},
            ]
        ],
    }
    assert (
        support.trainer_stats(
            meta, owned("x"), {"profession": "WARRIOR", "subProfessionId": "lord"}, 1
        )["efficiency"]
        == 75
    )
    assert (
        support.trainer_stats(
            meta, owned("x"), {"profession": "WARRIOR", "subProfessionId": "fighter"}, 1
        )["efficiency"]
        == 30
    )


def test_generator_preserves_empty_upgrade_replacing_training_skill():
    chars = {
        "char_a": {"name": "甲", "profession": "WARRIOR", "subProfessionId": "lord"}
    }
    building = {
        "buffs": {
            "train": {
                "buffId": "train",
                "roomType": "TRAINING",
                "description": "训练速度+30%",
                "efficiency": 30,
            }
        },
        "chars": {
            "char_a": {
                "buffChar": [
                    {
                        "buffData": [
                            {
                                "buffId": "train",
                                "cond": {"phase": "PHASE_0", "level": 1},
                            },
                            {
                                "buffId": "not_training",
                                "cond": {"phase": "PHASE_2", "level": 1},
                            },
                        ]
                    }
                ]
            }
        },
    }
    meta = compile_training_data(chars, building)["operators"]["char_a"]
    assert support.unlocked(meta, owned("char_a")) == []
    assert support.unlocked(meta, owned("char_a", 0))[0]["bonus"] == 30
