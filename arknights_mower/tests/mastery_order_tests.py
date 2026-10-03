import tempfile
from pathlib import Path

from arknights_mower.utils.mastery_db import (
    auto_interleave_new_plans,
    get_all_plans,
    insert_plan,
    update_plan_status,
)
from arknights_mower.utils.mastery_order import interleave_mastery_plans


def _plan(plan_id, char_id, status="idle"):
    return {"id": plan_id, "char_id": char_id, "status": status}


def test_interleave_keeps_operator_skills_together():
    plans = [
        _plan(1, "a"),
        _plan(2, "a"),
        _plan(3, "c"),
        _plan(4, "b"),
        _plan(5, "d"),
    ]
    professions = {"a": "WARRIOR", "c": "WARRIOR", "b": "SNIPER", "d": "SNIPER"}
    assert [p["id"] for p in interleave_mastery_plans(plans, professions)] == [
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
    professions = {"a": "WARRIOR", "c": "WARRIOR", "b": "SNIPER"}
    assert [p["id"] for p in interleave_mastery_plans(plans, professions)] == [
        1,
        3,
        4,
        2,
        5,
    ]


def test_new_plan_is_appended_then_interleaved_before_next_idle_selection():
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "plans.db")
        a = insert_plan("a", 0, 3, "技能一", "甲", priority=0, path=path)
        c = insert_plan("c", 0, 3, "技能一", "丙", priority=1, path=path)
        b = insert_plan("b", 0, 3, "技能一", "乙", priority=2, path=path)
        a_next = insert_plan("a", 1, 3, "技能二", "甲", path=path)
        assert auto_interleave_new_plans(
            [a_next],
            path=path,
            professions={"a": "WARRIOR", "c": "WARRIOR", "b": "SNIPER"},
        )
        assert [p["id"] for p in get_all_plans(path)] == [a, a_next, b, c]


def test_active_operator_stays_first_when_a_new_operator_is_added():
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "plans.db")
        a = insert_plan("a", 0, 3, "技能一", "甲", path=path)
        update_plan_status(a, "training", path=path)
        c = insert_plan("c", 0, 3, "技能一", "丙", path=path)
        b = insert_plan("b", 0, 3, "技能一", "乙", path=path)
        assert auto_interleave_new_plans(
            [b],
            path=path,
            professions={"a": "WARRIOR", "c": "WARRIOR", "b": "SNIPER"},
        )
        assert [p["id"] for p in get_all_plans(path)] == [a, b, c]
