"""New operator rules reach the bundled mastery assistant planner."""

import pytest

from arknights_mower.tests.mastery_support_fixtures import owned
from arknights_mower.utils import mastery_support as support
from arknights_mower.utils.mastery_rules import compile_buff
from arknights_mower.utils.mastery_support_types import TrainingInputs

TALULAH = "char_4247_oxi"


@pytest.mark.parametrize(
    "target,elite,efficiency",
    [
        ("char_4187_graceb", 0, 30),  # Primal Guard, before the E2 unlock.
        ("char_4187_graceb", 1, 30),
        ("char_4187_graceb", 2, 75),
        ("char_4146_nymph", 0, 30),  # Primal Caster.
        ("char_4146_nymph", 2, 75),
        ("char_172_svrash", 2, 30),  # Other Guards retain only the base bonus.
        ("char_180_amgoat", 2, 30),
        ("char_103_angel", 2, 0),
    ],
)
def test_bundled_talulah_reaches_actual_support_plan(target, elite, efficiency):
    result = support.plan_supports(
        target,
        0,
        1,
        inputs=TrainingInputs(
            roster=[owned(target), owned(TALULAH, elite)], schedule=({}, 0)
        ),
    )
    stage = result["stages"][0]
    assert stage["operator"] == "塔露拉"
    assert stage["efficiency"] == efficiency
    assert result["hours"] == pytest.approx(8 / (1.05 + efficiency / 100))


@pytest.mark.parametrize("available", [False, True])
def test_bundled_talulah_requires_ownership_and_no_other_assignment(available):
    target = "char_4146_nymph"
    roster = [owned(target), *([owned(TALULAH)] if available else [])]
    options, _ = support.candidates(
        target, TrainingInputs(roster=roster, schedule=({}, 0))
    )
    assert ("塔露拉" in options) is available
    blocked, _ = support.candidates(
        target,
        TrainingInputs(roster=roster, schedule=({"塔露拉": {"central"}}, 0)),
    )
    assert "塔露拉" not in blocked


def test_profession_preview_does_not_assume_either_primal_branch():
    defaults = support.profession_training_routes(
        {"WARRIOR": "近卫", "CASTER": "术师"},
        inputs=TrainingInputs(roster=[owned(TALULAH)], schedule=({}, 0)),
    )["defaults"]
    for result in defaults.values():
        assert [stage["efficiency"] for stage in result["supports"]] == [30] * 3


def test_new_operator_can_be_the_trainee():
    options, _ = support.candidates(
        TALULAH,
        TrainingInputs(
            roster=[owned(TALULAH), owned("char_123_fang")], schedule=({}, 0)
        ),
    )
    assert "芬" in options
    assert "塔露拉" not in options


def test_branch_only_bonus_uses_compatible_single_branch_rules():
    effects = compile_buff(
        {
            "buffId": "train_spd_branches[000]",
            "roomType": "TRAINING",
            "efficiency": 45,
            "targets": [],
            "description": "进驻训练室协助位时，如果训练位干员分支为本源近卫或本源术师，则专精技能训练速度额外+45%",
        }
    )
    assert effects == [
        {"kind": "speed", "bonus": 0, "professions": [], "extra": 45, "branch": branch}
        for branch in ("primguard", "primcaster")
    ]


def test_unknown_branch_still_fails_generation():
    with pytest.raises(ValueError, match="未识别的干员分支"):
        compile_buff(
            {
                "buffId": "unknown_branch",
                "roomType": "TRAINING",
                "efficiency": 45,
                "description": "分支为本源近卫或未知分支，训练速度额外+45%",
            }
        )
