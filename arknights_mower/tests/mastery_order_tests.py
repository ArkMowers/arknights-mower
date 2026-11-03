import json
import tempfile
from pathlib import Path

from arknights_mower.utils.mastery_db import (
    auto_interleave_new_plans,
    get_all_plans,
    insert_plan,
    update_plan_status,
)
from arknights_mower.utils.mastery_order import interleave_mastery_plans


def _supports(name):
    return {"stages": [{"level": 1, "operator": name}]}


def _plan(plan_id, char_id, status="idle"):
    return {
        "id": plan_id,
        "char_id": char_id,
        "status": status,
        "support_plan": _supports("甲协助" if char_id in ("a", "c") else "乙协助"),
    }


def test_interleave_keeps_operator_skills_together():
    plans = [
        _plan(1, "a"),
        _plan(2, "a"),
        _plan(3, "c"),
        _plan(4, "b"),
        _plan(5, "d"),
    ]
    assert [p["id"] for p in interleave_mastery_plans(plans)] == [
        1,
        2,
        4,
        3,
        5,
    ]


def test_interleave_keeps_active_operator_and_its_next_skill_together():
    plans = [
        _plan(1, "a", "training"),
        _plan(2, "c"),
        _plan(3, "a"),
        _plan(4, "b"),
        _plan(5, "failed", "failed"),
    ]
    assert [p["id"] for p in interleave_mastery_plans(plans)] == [
        1,
        3,
        4,
        2,
        5,
    ]


def test_new_plan_is_appended_then_interleaved_before_next_idle_selection():
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "plans.db")
        a = insert_plan(
            "a",
            0,
            3,
            "技能一",
            "甲",
            priority=0,
            path=path,
            support_plan=_supports("甲协助"),
        )
        c = insert_plan(
            "c",
            0,
            3,
            "技能一",
            "丙",
            priority=1,
            path=path,
            support_plan=_supports("甲协助"),
        )
        b = insert_plan(
            "b",
            0,
            3,
            "技能一",
            "乙",
            priority=2,
            path=path,
            support_plan=_supports("乙协助"),
        )
        a_next = insert_plan(
            "a", 1, 3, "技能二", "甲", path=path, support_plan=_supports("丙协助")
        )
        assert auto_interleave_new_plans(
            [a_next],
            path=path,
        )
        assert [p["id"] for p in get_all_plans(path)] == [a, a_next, b, c]


def test_active_operator_stays_first_when_a_new_operator_is_added():
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "plans.db")
        a = insert_plan(
            "a", 0, 3, "技能一", "甲", path=path, support_plan=_supports("甲协助")
        )
        update_plan_status(a, "training", path=path)
        c = insert_plan(
            "c", 0, 3, "技能一", "丙", path=path, support_plan=_supports("甲协助")
        )
        b = insert_plan(
            "b", 0, 3, "技能一", "乙", path=path, support_plan=_supports("乙协助")
        )
        assert auto_interleave_new_plans(
            [b],
            path=path,
        )
        assert [p["id"] for p in get_all_plans(path)] == [a, b, c]


def test_new_skill_preserves_custom_order_and_appends_to_tail(tmp_path):
    path = str(tmp_path / "plans.db")
    a = insert_plan(
        "a",
        0,
        3,
        "技能一",
        "甲",
        priority=0,
        path=path,
        support_plan=_supports("甲协助"),
    )
    c = insert_plan(
        "c",
        0,
        3,
        "技能一",
        "丙",
        priority=1,
        path=path,
        support_plan=_supports("甲协助"),
    )
    b = insert_plan(
        "b",
        0,
        3,
        "技能一",
        "乙",
        priority=2,
        path=path,
        support_plan=_supports("乙协助"),
    )
    a_next = insert_plan(
        "a", 1, 3, "技能二", "甲", path=path, support_plan=_supports("丙协助")
    )
    assert auto_interleave_new_plans(
        [a_next],
        path=path,
        order=["skill:a:0", "module:a:x", "skill:c:0", "skill:b:0"],
    )
    assert [p["id"] for p in get_all_plans(path)] == [a, c, b, a_next]


def test_saved_order_keeps_active_and_confirmed_material_wait_first(tmp_path):
    path = str(tmp_path / "plans.db")
    a = insert_plan(
        "a",
        0,
        3,
        "技能一",
        "甲",
        priority=0,
        path=path,
        support_plan=_supports("甲协助"),
    )
    b = insert_plan(
        "b",
        0,
        3,
        "技能一",
        "乙",
        priority=1,
        path=path,
        support_plan=_supports("甲协助"),
    )
    c = insert_plan(
        "c", 0, 3, "技能一", "丙", path=path, support_plan=_supports("甲协助")
    )
    for status in ("arranging", "training", "waiting_collect", "idle"):
        update_plan_status(
            b,
            status,
            expires_at="2026-10-08 12:00:00",
            failed_reason="材料不足",
            path=path,
        )
        assert auto_interleave_new_plans(
            [c],
            path=path,
            order=["skill:a:0", "skill:b:0"],
        )
        assert [p["id"] for p in get_all_plans(path)] == [b, a, c]


def test_different_professions_share_assistants_and_same_profession_can_differ():
    plans = [_plan(1, "a"), _plan(2, "c"), _plan(3, "b")]
    plans[0]["profession"], plans[1]["profession"], plans[2]["profession"] = (
        "CASTER",
        "MEDIC",
        "CASTER",
    )
    assert [p["id"] for p in interleave_mastery_plans(plans)] == [1, 3, 2]


def test_partial_assistant_overlap_counts_swaps_and_other_skills():
    plans = [_plan(1, "a", "training"), _plan(2, "a"), _plan(3, "c"), _plan(4, "b")]
    plans[0]["support_plan"] = _supports("首协助")
    plans[1]["support_plan"] = {
        "stages": [{"level": 2, "operator": "另一协助", "swap_target": "接替者"}]
    }
    plans[2]["support_plan"] = _supports("接替者")
    assert [p["id"] for p in interleave_mastery_plans(plans)] == [1, 2, 4, 3]


def test_executing_stage_overrides_saved_assistants_and_skips_past_stages():
    plans = [_plan(1, "a", "training"), _plan(2, "b"), _plan(3, "c")]
    plans[0]["support_plan"] = json.dumps(
        {
            "stages": [
                {"level": 1, "operator": "乙协助"},
                {"level": 2, "operator": "旧协助"},
            ]
        }
    )
    plans[0]["support_runtime"] = json.dumps({"level": 2, "operator": "甲协助"})
    assert [p["id"] for p in interleave_mastery_plans(plans)] == [1, 2, 3]


def test_missing_assistants_do_not_invent_profession_conflicts():
    plans = [
        {"id": n, "char_id": str(n), "status": "idle", "profession": "CASTER"}
        for n in range(3)
    ]
    assert interleave_mastery_plans(plans) == plans


def test_carried_record_from_previous_skill_does_not_hide_unstarted_stages():
    plans = [_plan(1, "a", "arranging"), _plan(2, "c"), _plan(3, "b")]
    plans[0]["support_runtime"] = {
        "level": 3,
        "operator": "乙协助",
        "carry_from_skill": 0,
    }
    assert [p["id"] for p in interleave_mastery_plans(plans)] == [1, 3, 2]
