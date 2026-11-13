"""心情不足时按实际效率替换当前阶段协助者，并保存执行方案。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import mastery
from arknights_mower.solvers import mastery_support_runtime as runtime
from arknights_mower.tests.mastery_support_fixtures import database as database
from arknights_mower.utils import config
from arknights_mower.utils import mastery_db as db
from arknights_mower.utils.mastery_mood import (
    SupportMoodWait,
    support_mood_requirements,
)
from arknights_mower.utils.mastery_support_types import has_planned_supports, stage_for


def trainer(name, efficiency, halves=False):
    return {
        level: dict(name=name, efficiency=efficiency, halves=halves)
        for level in (1, 2, 3)
    }


@pytest.fixture
def case(database, monkeypatch):
    monkeypatch.setattr(
        config,
        "conf",
        SimpleNamespace(assistant_follows_schedule=False, enable_mastery=True),
    )
    monkeypatch.setattr(runtime, "schedule_context", lambda: ({}, 5))
    monkeypatch.setattr(runtime, "_observed_support", lambda _: ("", "学员"))
    monkeypatch.setattr(runtime, "basic_mastery_successor", lambda *a: False)
    monkeypatch.setattr(
        runtime,
        "halving_successor",
        lambda p, level: p if level < p["target_level"] else None,
    )
    monkeypatch.setattr(
        mastery,
        "halving_successor",
        lambda p, level: p if level < p["target_level"] else None,
        raising=False,
    )
    options = {}
    monkeypatch.setattr(runtime, "candidates", lambda *a, **k: (options, 5))
    solver = SimpleNamespace(
        op_data=SimpleNamespace(operators={}, dorm_mood_estimates={}),
        task=SimpleNamespace(),
    )

    def mood(name, value):
        solver.op_data.dorm_mood_estimates[name] = (value, datetime.now())

    def plan(route, legacy=False, target=3):
        pid = db.insert_plan(
            "trainee",
            0,
            target,
            char_name="学员",
            support_plan=None if legacy else {"stages": [route]},
        )
        value = db.get_plan_by_id(pid)
        if legacy:
            monkeypatch.setattr(
                mastery,
                "get_route_config",
                lambda profession, level: dict(route, level=level),
            )
            monkeypatch.setattr(
                "arknights_mower.utils.mastery_recommendation.get_skill_data",
                lambda: {"characters": {"trainee": {"profession": "CASTER"}}},
            )
        return value

    return SimpleNamespace(options=options, solver=solver, mood=mood, plan=plan)


@pytest.mark.parametrize("legacy", [False, True])
def test_full_alternative_replaces_tired_primary_and_survives_reload(
    case, legacy, monkeypatch
):
    case.options.update(
        {
            name: trainer(name, speed)
            for name, speed in (("原协助", 100), ("替代协助", 30), ("慢协助", 0))
        }
    )
    case.mood("原协助", 1)
    case.mood("替代协助", 24)
    case.mood("慢协助", 24)
    plan = case.plan(dict(level=2, operator="原协助", efficiency=100), legacy, target=2)
    prepare = (
        runtime.prepare_legacy_support_mood if legacy else runtime.prepare_plan_supports
    )
    prepare(case.solver, plan, 2)
    restored = db.get_plan_by_id(plan["id"])
    route = stage_for(restored, 2)
    assert route["operator"] == "替代协助"
    assert route["efficiency"] == 30
    assert route["hours"] == pytest.approx(16 / 1.4)
    assert support_mood_requirements(route) == {"替代协助": pytest.approx(16 / 1.35)}
    assert restored["support_plan"] == plan["support_plan"]
    assert stage_for(restored, 3) is None
    place = Mock()
    monkeypatch.setattr(
        "arknights_mower.solvers.mastery_support_swap.place_support", place
    )
    # Reuse the persisted stage through the real placement caller.
    assert mastery._get_plan_route(restored, 2)["operator"] == "替代协助"
    assert mastery._arrange_support(case.solver, restored, 2) is None
    place.assert_called_once_with(case.solver, restored, 2, "替代协助")


@pytest.mark.parametrize("legacy", [False, True])
def test_irene_replaces_logos_with_her_own_efficiency(case, legacy):
    case.options.update(
        {"逻各斯": trainer("逻各斯", 30, True), "艾丽妮": trainer("艾丽妮", 0, True)}
    )
    case.mood("逻各斯", 0)
    case.mood("艾丽妮", 24)
    plan = case.plan(
        dict(level=2, operator="逻各斯", efficiency=30, first_halves=True), legacy
    )
    prepare = (
        runtime.prepare_legacy_support_mood if legacy else runtime.prepare_plan_supports
    )
    prepare(case.solver, plan, 2)
    route = stage_for(db.get_plan_by_id(plan["id"]), 2)
    assert route["operator"] == "艾丽妮"
    assert route["efficiency"] == 0
    assert route["first_halves"] is True
    assert route["hours"] == pytest.approx(16 / 1.1)
    assert support_mood_requirements(route) == {"艾丽妮": pytest.approx(16 / 1.05)}


def test_tired_swap_reducer_is_replaced_and_tail_is_recalculated(case):
    case.options.update(
        {
            "快教官": trainer("快教官", 100),
            "逻各斯": trainer("逻各斯", 30, True),
            "艾丽妮": trainer("艾丽妮", 0, True),
        }
    )
    for name, value in (("快教官", 24), ("逻各斯", 0), ("艾丽妮", 24)):
        case.mood(name, value)
    plan = case.plan(
        dict(
            level=2,
            operator="快教官",
            efficiency=100,
            swap_target="逻各斯",
            swap_efficiency=30,
            swap_halves=True,
        )
    )
    runtime.prepare_plan_supports(case.solver, plan, 2)
    route = stage_for(db.get_plan_by_id(plan["id"]), 2)
    assert route["operator"] == "快教官"
    assert route["swap_target"] == "艾丽妮"
    assert route["swap_efficiency"] == 0
    assert route["swap_halves"] is True
    required = support_mood_requirements(route)
    assert required["艾丽妮"] == pytest.approx(5 + 10 / 60, abs=0.001)
    assert required["快教官"] == pytest.approx(
        (16 - (5 + 10 / 60) * 1.05) / 2.05, abs=0.001
    )


def test_no_affordable_replacement_retains_alternative_requirements(case):
    case.options.update(
        {"原协助": trainer("原协助", 100), "替代协助": trainer("替代协助", 30)}
    )
    case.mood("原协助", 0)
    case.mood("替代协助", 1)
    plan = case.plan(dict(level=2, operator="原协助", efficiency=100), target=2)
    with pytest.raises(SupportMoodWait) as wait:
        runtime.prepare_plan_supports(case.solver, plan, 2)
    assert {"替代协助": pytest.approx(16 / 1.35)} in wait.value.alternatives
    assert db.get_plan_by_id(plan["id"])["support_runtime"] is None


def test_unknown_replacements_use_one_scan_before_selecting(case):
    case.options.update(
        {"原协助": trainer("原协助", 100), "替代协助": trainer("替代协助", 30)}
    )
    case.mood("原协助", 0)
    case.solver._scan_card_moods = Mock(
        side_effect=lambda **k: case.mood("替代协助", 24)
    )
    case.solver.enter_room = Mock()
    plan = case.plan(dict(level=2, operator="原协助", efficiency=100), target=2)
    runtime.prepare_plan_supports(case.solver, plan, 2)
    assert stage_for(db.get_plan_by_id(plan["id"]), 2)["operator"] == "替代协助"
    case.solver._scan_card_moods.assert_called_once_with(mastery=True)
    case.solver.enter_room.assert_called_once_with("train", max_attempts=1)


def test_legacy_replacement_does_not_override_the_next_stage(case):
    case.options.update(
        {"原协助": trainer("原协助", 100), "替代协助": trainer("替代协助", 30)}
    )
    case.mood("原协助", 0)
    case.mood("替代协助", 24)
    plan = case.plan(dict(level=2, operator="原协助", efficiency=100), legacy=True)
    runtime.prepare_legacy_support_mood(case.solver, plan, 2)
    plan = db.get_plan_by_id(plan["id"])
    assert mastery._get_plan_route(plan, 2)["operator"] == "替代协助"
    assert mastery._get_plan_route(plan, 3)["operator"] == "原协助"
    case.mood("原协助", 24)
    runtime.prepare_legacy_support_mood(case.solver, plan, 3)
    restored = db.get_plan_by_id(plan["id"])
    assert not has_planned_supports(restored)
    assert mastery._get_plan_route(restored, 3)["operator"] == "原协助"


def test_replacement_keeps_observed_inherited_halving(case, monkeypatch):
    case.options.update(
        {"逻各斯": trainer("逻各斯", 30, True), "艾丽妮": trainer("艾丽妮", 30, True)}
    )
    case.mood("逻各斯", 0)
    case.mood("艾丽妮", 24)
    plan = case.plan(
        dict(level=2, operator="逻各斯", efficiency=30, first_halves=True), target=2
    )
    from arknights_mower.solvers.mastery_support_state import save_runtime

    save_runtime(
        plan,
        {
            "level": 1,
            "working_operator": "艾丽妮",
            "working_halves": True,
            "working_since": (datetime.now() - timedelta(hours=6)).isoformat(),
        },
    )
    monkeypatch.setattr(runtime, "_observed_support", lambda _: ("艾丽妮", "学员"))
    runtime.prepare_plan_supports(case.solver, plan, 2)
    route = stage_for(db.get_plan_by_id(plan["id"]), 2)
    assert route["operator"] == "艾丽妮"
    assert route["half_inherited"] is True
    assert route["activate_with"] == "艾丽妮"
    assert route["hours"] == pytest.approx(8 / 1.4)


def test_replacement_keeps_required_reducer_attendance(case):
    case.options.update(
        {"逻各斯": trainer("逻各斯", 30, True), "普通协助": trainer("普通协助", 100)}
    )
    case.mood("逻各斯", 0)
    case.mood("普通协助", 24)
    plan = case.plan(dict(level=2, operator="逻各斯", efficiency=30, first_halves=True))
    with pytest.raises(SupportMoodWait):
        runtime.prepare_plan_supports(case.solver, plan, 2)
    assert db.get_plan_by_id(plan["id"])["support_runtime"] is None


@pytest.mark.parametrize("legacy", [False, True])
def test_restarted_training_recovers_the_replacement_not_the_configured_assistant(
    case, legacy, monkeypatch
):
    from arknights_mower.solvers import mastery_reader
    from arknights_mower.utils.scheduler_task import TaskTypes

    case.options.update(
        {"原协助": trainer("原协助", 100), "替代协助": trainer("替代协助", 30)}
    )
    case.mood("原协助", 0)
    case.mood("替代协助", 24)
    plan = case.plan(dict(level=2, operator="原协助", efficiency=100), legacy, target=2)
    prepare = (
        runtime.prepare_legacy_support_mood if legacy else runtime.prepare_plan_supports
    )
    prepare(case.solver, plan, 2)
    restored = db.get_plan_by_id(plan["id"])
    case.solver.tasks = []
    room = SimpleNamespace(
        panel=SimpleNamespace(
            mastery_tier=2, countdown=datetime.now() + timedelta(hours=10)
        )
    )
    monkeypatch.setattr(
        mastery_reader, "_read_slots_checked", lambda _: ("原协助", "学员", None, True)
    )
    assert mastery_reader._maybe_recover_swap(case.solver, restored, room)
    task = case.solver.tasks[0]
    assert task.type == TaskTypes.SWAP_SUPPORT
    assert task.plan_key == str(plan["id"])
    assert task.meta_data == "学员 换入替代协助"
