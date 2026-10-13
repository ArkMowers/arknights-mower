"""Offline contracts for consecutive skills and Control Center staffing changes."""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers import mastery, mastery_reader
from arknights_mower.solvers import mastery_support_runtime as runtime
from arknights_mower.solvers import mastery_support_state as state
from arknights_mower.tests.mastery_support_fixtures import database as database
from arknights_mower.tests.mastery_support_fixtures import stat
from arknights_mower.tests.workshop_plan_fixtures import next_skill as next_skill
from arknights_mower.utils import config
from arknights_mower.utils import mastery_db as db
from arknights_mower.utils import mastery_recommendation as rec
from arknights_mower.utils.mastery_optimizer import stage_route
from arknights_mower.utils.mastery_order import (
    basic_mastery_successor,
    consecutive_mastery_plans,
    halving_successor,
)
from arknights_mower.utils.mastery_support_data import actual_central_bonus
from arknights_mower.utils.mastery_support_types import (
    DEFAULT_SWAP_BUFFERS,
    StageSpec,
    stage_for,
)
from arknights_mower.utils.scheduler_task import TaskTypes


def plan(pid, cid="a", skill=0, status="idle", **extras):
    return dict(
        id=pid,
        char_id=cid,
        char_name="学员",
        skill_index=skill,
        skill_name="测试",
        status=status,
        target_level=3,
        **extras,
    )


def test_lower_mastery_first_and_operator_adjacency():
    plans = [plan(1, skill=0), plan(2, "b"), plan(3, skill=1)]
    ordered = consecutive_mastery_plans(plans, {("a", 0): 2, ("a", 1): 1})
    assert [p["id"] for p in ordered] == [3, 1, 2]
    assert [p["id"] for p in plans] == [1, 2, 3]
    plans[0]["status"] = "training"
    assert consecutive_mastery_plans(plans, {("a", 0): 2, ("a", 1): 1}) == [
        plans[0],
        plans[2],
        plans[1],
    ]


def test_basic_skill_first_when_partner_can_consume_cross_skill_halving():
    plans = [plan(1), plan(2, skill=1)]
    assert consecutive_mastery_plans(plans, {("a", 0): 2, ("a", 1): 0}) == plans[::-1]
    assert consecutive_mastery_plans(plans, {("a", 0): 0, ("a", 1): 0}) == plans


@pytest.mark.parametrize(
    "next_level,other,expected",
    [
        (0, False, False),
        (1, False, True),
        (2, False, True),
        (3, False, False),
        (1, True, False),
    ],
)
def test_final_stage_admission_depends_on_next_training(next_level, other, expected):
    current = plan(1, status="training")
    successor = plan(2, "b" if other else "a", skill=1)
    assert (
        bool(
            halving_successor(
                current,
                3,
                plans=[current, successor],
                levels={(successor["char_id"], 1): next_level},
            )
        )
        is expected
    )
    assert halving_successor(current, 2) is current


@pytest.mark.parametrize(
    "current_level,other,expected",
    [(0, False, True), (1, False, False), (0, True, False), (None, False, False)],
)
def test_basic_successor_only_excludes_reducers_from_mastery_three(
    current_level, other, expected
):
    current = plan(1, status="training")
    next_plan = plan(2, "b" if other else "a", skill=1)
    args = dict(
        plans=[current, next_plan], levels={(next_plan["char_id"], 1): current_level}
    )
    assert basic_mastery_successor(current, 3, **args) is expected
    assert not basic_mastery_successor(current, 2, **args)


@pytest.mark.parametrize("running", [False, True])
def test_basic_successor_replaces_even_the_fastest_reducer(
    database, monkeypatch, running
):
    from arknights_mower.solvers import mastery_support_swap as swap

    first_id = db.insert_plan("a", 0, 3, "测试", "学员")
    db.insert_plan("a", 1, 3, "下一技能", "学员")
    current = db.get_plan_by_id(first_id)
    route = stage_route(stat("逻各斯", 100, True), None, StageSpec(3, 24, 0, 10))
    route.update(first_halves=True, swap_halves=False, working_operator="逻各斯")
    db.save_support_plan(first_id, {"stages": [route]})
    current = db.get_plan_by_id(first_id)
    monkeypatch.setattr(rec, "get_current_mastery_level", lambda *_: 0)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", False)
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config, "plan", {})
    options = {
        "逻各斯": {3: stat("逻各斯", 100, True)},
        "普通教官": {3: stat("普通教官", 50)},
    }
    monkeypatch.setattr(runtime, "candidates", lambda *a, **kw: (options, 0))
    monkeypatch.setattr(runtime, "_observed_support", lambda _: ("逻各斯", "学员"))
    monkeypatch.setattr(runtime, "schedule_context", lambda: ({}, 0))
    solver = MagicMock(tasks=[], task=None)
    if not running:
        current["support_runtime"] = dict(
            level=2,
            working_operator="逻各斯",
            working_halves=True,
            working_since=(datetime.now() - timedelta(hours=6)).isoformat(),
        )
        runtime.prepare_plan_supports(solver, current, 3)
        prepared = stage_for(current, 3)
        assert prepared["operator"] == "普通教官"
        assert prepared["swap_target"] is None
        assert prepared["exclude_reducer"]
        assert prepared["activate_with"] == "逻各斯"
        assert prepared["half_inherited"]
        # The training-confirmation assistant placement consumes the same effective route.
        monkeypatch.setattr(swap, "place_support", MagicMock())
        assert mastery._arrange_support(solver, current, 3) is None
        assert swap.place_support.call_args.args[-1] == "普通教官"
        return

    current.update(status="training", swap_frozen=1)
    db.update_plan_status(first_id, "training", swap_frozen=1)
    panel = mastery_reader.RoomPanel(
        "学员",
        "测试",
        mastery_tier=3,
        countdown=datetime.now() + timedelta(hours=2),
        countdown_state="active",
    )
    room = mastery_reader.RoomState(
        "training", panel, support_slot="逻各斯", train_slot="学员", slots_reliable=True
    )
    monkeypatch.setattr(
        mastery_reader, "_read_slots_checked", lambda _: ("逻各斯", "学员", [], True)
    )
    assert runtime.recover(solver, current, room)
    assert solver.tasks[0].type == TaskTypes.SWAP_SUPPORT
    monkeypatch.setattr(swap, "candidates", lambda *a, **kw: (options, 0))
    monkeypatch.setattr(swap, "confirm_training_panel", lambda *a: panel)
    replacement = MagicMock(return_value=panel)
    monkeypatch.setattr(swap, "place_support", replacement)
    swap.perform_swap(solver, current, panel, "逻各斯")
    replacement.assert_called_once()
    assert replacement.call_args.args[-1] == "普通教官"


@pytest.mark.parametrize("frozen", [False, True])
def test_removed_basic_successor_restores_reducer_protection(
    database, monkeypatch, frozen
):
    from arknights_mower.solvers import mastery_support_swap as swap

    first_id = db.insert_plan("a", 0, 3, "测试", "学员")
    next_id = db.insert_plan("a", 1, 3, "下一技能", "学员")
    db.update_plan_status(next_id, "failed")
    route = stage_route(stat("普通教官", 50), None, StageSpec(3, 24, 0, 10))
    route.update(exclude_reducer=True, working_operator="逻各斯")
    assert db.save_support_plan(first_id, {"stages": [route]})
    db.update_plan_status(first_id, "training", swap_frozen=int(frozen))
    current = db.get_plan_by_id(first_id)
    state.save_runtime(current, route)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", False)
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config, "plan", {})
    panel = mastery_reader.RoomPanel(
        "学员",
        "测试",
        mastery_tier=3,
        countdown=datetime.now() + timedelta(hours=2),
        countdown_state="active",
    )
    room = mastery_reader.RoomState("training", panel)
    monkeypatch.setattr(
        mastery_reader, "_read_slots_checked", lambda _: ("逻各斯", "学员", [], True)
    )
    solver = MagicMock(tasks=[], task=None)
    assert not runtime.recover(solver, current, room)
    assert not stage_for(db.get_plan_by_id(first_id), 3)["exclude_reducer"]
    assert not solver.tasks

    # A swap queued before the queue edit must also preserve the current reducer.
    options = {
        "逻各斯": {3: stat("逻各斯", 100, True)},
        "普通教官": {3: stat("普通教官", 50)},
    }
    monkeypatch.setattr(swap, "candidates", lambda *a, **kw: (options, 0))
    monkeypatch.setattr(swap, "confirm_training_panel", lambda *a: panel)
    replacement = MagicMock(return_value=panel)
    monkeypatch.setattr(swap, "place_support", replacement)
    swap.perform_swap(solver, current, panel, "逻各斯")
    replacement.assert_not_called()


@pytest.mark.parametrize("supplied_inventory", [False, True])
def test_joint_craftability_and_single_skill_preparation(
    database, tmp_path, monkeypatch, supplied_inventory
):
    a = db.insert_plan("a", 0, 3, "测试", "学员", priority=0)
    b = db.insert_plan("b", 0, 3, "测试", "乙", priority=1)
    second = db.insert_plan("a", 1, 3, "测试", "学员", priority=2)
    cultivate = tmp_path / "cultivate.json"
    skill_data = tmp_path / "skills.json"
    skill_data.write_text(
        json.dumps(
            {
                "items": {"book": {"name": "书"}, "raw": {"name": "原料"}},
                "composite": {"book": {"pathway": [{"id": "raw", "count": 2}]}},
            }
        )
    )
    monkeypatch.setattr(rec, "get_path", lambda _: cultivate)
    monkeypatch.setattr(rec, "_find_skill_data", lambda: skill_data)
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
        lambda _: None,
    )
    monkeypatch.setattr(
        rec,
        "get_mastery_recommendations",
        lambda: {
            "has_data": True,
            "operators": [
                {
                    "char_id": cid,
                    "name": cid,
                    "profession": "CASTER",
                    "recommendations": [
                        {
                            "skill_index": skill,
                            "skill_name": "测试",
                            "current_level": level,
                            "chain_needed_materials": [{"name": "书", "count": count}],
                        }
                        for skill, level, count in skills
                    ],
                }
                for cid, skills in [("a", [(0, 2, 5), (1, 1, 7)]), ("b", [(0, 0, 1)])]
            ],
        },
    )

    def schedule():
        if not supplied_inventory:
            return rec.auto_schedule_mastery_tasks()
        items = json.loads(cultivate.read_text())["data"]["items"]
        names = {"book": "书", "raw": "原料"}
        return rec.auto_schedule_mastery_tasks(
            inventory={names[item["id"]]: item["count"] for item in items}
        )

    cultivate.write_text(json.dumps({"data": {"items": [{"id": "book", "count": 7}]}}))
    result = schedule()
    assert [entry["char_id"] for entry in result["scheduled"]] == ["b"]
    assert all("联合材料" in entry["reason"] for entry in result["skipped"])
    cultivate.write_text(
        json.dumps(
            {
                "data": {
                    "items": [{"id": "book", "count": 7}, {"id": "raw", "count": 10}]
                }
            }
        )
    )
    ready = schedule()
    assert [
        (entry["char_id"], entry["skill_index"]) for entry in ready["scheduled"]
    ] == [("a", 1), ("b", 0)]
    assert "前序技能" in ready["skipped"][0]["reason"]
    assert [p["id"] for p in db.get_all_plans()] == [second, a, b]
    cultivate.write_text(json.dumps({"data": {"items": [{"id": "book", "count": 12}]}}))
    assert [
        entry["skill_index"]
        for entry in schedule()["scheduled"]
        if entry["char_id"] == "a"
    ] == [1]


@pytest.mark.parametrize(
    "hours,assistant,trainee,expected",
    [
        (6, "艾丽妮", "学员", True),
        (5, "艾丽妮", "学员", False),
        (6, "逻各斯", "学员", False),
        (6, "艾丽妮", "别人", False),
    ],
)
def test_cross_skill_halving_requires_observed_recorded_work(
    hours, assistant, trainee, expected
):
    now = datetime.now()
    following = plan(
        2,
        skill=1,
        support_runtime={
            "level": 3,
            "carry_from_skill": 0,
            "working_operator": "艾丽妮",
            "working_halves": True,
            "working_since": (now - timedelta(hours=hours, minutes=1)).isoformat(),
            "working_until": (now - timedelta(minutes=1)).isoformat(),
        },
    )
    assert (
        bool(runtime._carried_halving(following, 2, (assistant, trainee))) is expected
    )


def test_final_stage_gets_reducer_and_is_scheduled(database, monkeypatch):
    current_id = db.insert_plan("a", 0, 3, "测试", "学员")
    db.update_plan_status(current_id, "training")
    db.insert_plan("a", 1, 3, "测试", "学员", priority=1)
    monkeypatch.setattr(rec, "get_current_mastery_level", lambda *_: 1)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", False)
    current = db.get_plan_by_id(current_id)
    current["support_plan"] = {
        "stages": [stage_route(stat("快教官", 95), None, StageSpec(3, 24))]
    }
    db.save_support_plan(current_id, current["support_plan"])
    monkeypatch.setattr(
        runtime,
        "candidates",
        lambda *a, **kw: (
            {"快教官": {3: stat("快教官", 95)}, "艾丽妮": {3: stat("艾丽妮", 0, True)}},
            5,
        ),
    )
    monkeypatch.setattr(runtime, "_observed_support", lambda _: ("快教官", "学员"))
    solver = SimpleNamespace(tasks=[], task=None)
    runtime.prepare_plan_supports(solver, current, 3)
    route = stage_for(current, 3)
    assert route["swap_target"] == "艾丽妮"
    state.record_work(current, 3, "快教官")
    assert mastery._schedule_swap_if_needed(
        solver, current, datetime.now() + timedelta(hours=12), 3
    )
    assert len(solver.tasks) == 1
    assert mastery._get_plan_route(current, 3)["swap_target"] == "艾丽妮"


def test_legacy_final_stage_has_same_successor_rule(monkeypatch):
    current = plan(1)
    next_plan = plan(2, skill=1)
    monkeypatch.setattr(db, "get_all_plans", lambda: [current, next_plan])
    monkeypatch.setattr(rec, "get_current_mastery_level", lambda *_: 1)
    monkeypatch.setattr(
        rec, "get_skill_data", lambda: {"characters": {"a": {"profession": "CASTER"}}}
    )
    assert mastery._get_plan_route(current, 3)["swap_target"] == "逻各斯"
    monkeypatch.setattr(rec, "get_current_mastery_level", lambda *_: 0)
    assert mastery._get_plan_route(current, 3)["swap_target"] is None


def test_collect_transfers_work_record_and_starts_same_trainee_successor(
    database, monkeypatch
):
    first = db.insert_plan("a", 0, 3, "测试", "学员")
    second = db.insert_plan("a", 1, 3, "测试", "学员", priority=1)
    db.update_plan_status(first, "training")
    now = datetime.now()
    record = {
        "level": 3,
        "working_operator": "艾丽妮",
        "working_halves": True,
        "working_since": (now - timedelta(hours=6)).isoformat(),
        "working_until": now.isoformat(),
    }
    db.save_support_plan(first, record, runtime=True)
    monkeypatch.setattr(rec, "get_current_mastery_level", lambda *_: 1)
    monkeypatch.setattr(
        rec,
        "auto_schedule_mastery_tasks",
        lambda: {"scheduled": [{"char_id": "a", "skill_index": 1}]},
    )
    solver = SimpleNamespace(tasks=[], task=None)
    following = mastery_reader._reconcile_after_collect(
        solver, db.get_plan_by_id(first), mastery_reader.RoomPanel(mastery_tier=3)
    )
    assert following["id"] == second
    saved = json.loads(db.get_plan_by_id(second)["support_runtime"])
    assert saved["carry_from_skill"] == 0
    assert saved["working_since"] == record["working_since"]
    assert db.get_plan_by_id(first)["status"] == "completed"
    assert len(solver.tasks) == 1


def occupant(room):
    return SimpleNamespace(current_room=room, current_mood=lambda: 24)


@pytest.mark.parametrize(
    "before,after,refresh",
    [
        ("central", "dormitory_1", True),
        ("dormitory_1", "central", True),
        ("room_1_1", "dormitory_1", False),
        ("central", "central", False),
    ],
)
def test_only_actual_entry_or_exit_of_central_refreshes(
    before, after, refresh, monkeypatch
):
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    solver = MagicMock()
    solver.op_data.operators = {"阿斯卡纶": occupant(before), "芬": occupant("central")}
    previous = runtime.central_training_occupants(solver)
    solver.op_data.operators["阿斯卡纶"].current_room = after
    with (
        patch.object(db, "get_active_plan", return_value=plan(1, status="training")),
        patch.object(mastery_reader, "read_room_state") as read,
        patch.object(mastery_reader, "reconcile_short") as reconcile,
    ):
        runtime.refresh_after_central_change(solver, previous)
    assert read.called is refresh
    assert reconcile.called is refresh
    assert solver.back_to_infrastructure.called is refresh
    assert actual_central_bonus(solver, 5) == (5 if after == "central" else 0)


def test_staffing_refresh_replaces_existing_swap_deadline_without_duplicates():
    route = stage_route(stat("教官", 60), stat("艾丽妮", 0, True), StageSpec(2, 16, 5))
    route["working_operator"] = "教官"
    current = plan(1, support_plan={"stages": [route]})
    now = datetime(2026, 10, 11, 12)
    solver = SimpleNamespace(
        tasks=[],
        task=None,
        op_data=SimpleNamespace(operators={"阿斯卡纶": occupant("dormitory_1")}),
    )
    with patch.object(state, "datetime") as clock:
        clock.now.return_value = now
        first = state.schedule_support_swap(
            solver, current, now + timedelta(hours=8), 2
        )
        assert first == now + timedelta(hours=8) - timedelta(minutes=310 * 1.10 / 1.65)
        solver.op_data.operators["阿斯卡纶"].current_room = "central"
        second = state.schedule_support_swap(
            solver, current, now + timedelta(hours=7), 2
        )
    assert len(solver.tasks) == 1
    assert solver.tasks[0].time == second
    assert second == now + timedelta(hours=7) - timedelta(minutes=310 * 1.10 / 1.70)


def test_previous_default_map_migrates_to_ten_minutes(database):
    db.save_route_settings(
        5,
        mastery_swap_buffers={
            "no_central": 10,
            "central": 15,
            "central_unhalved_m2": 30,
        },
    )
    assert db.get_route_settings()["mastery_swap_buffers"] == DEFAULT_SWAP_BUFFERS
    assert set(DEFAULT_SWAP_BUFFERS.values()) == {10}


def test_queued_start_rechecks_joint_admission_before_any_room_mutation(
    database, monkeypatch
):
    first = db.insert_plan("a", 0, 3, "测试", "学员")
    db.insert_plan("a", 1, 3, "测试", "学员", priority=1)
    monkeypatch.setattr(rec, "get_current_mastery_level", lambda *_: 1)
    monkeypatch.setattr(rec, "get_mastery_requirement_error", lambda _: None)
    monkeypatch.setattr(
        rec, "auto_schedule_mastery_tasks", lambda: {"scheduled": [], "skipped": []}
    )
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
        lambda _: None,
    )
    solver = MagicMock()
    mastery._start_new_training(solver, db.get_plan_by_id(first))
    assert solver.mock_calls == []
    assert db.get_plan_by_id(first)["status"] == "idle"


@pytest.mark.parametrize("next_level,swaps", [(0, False), (1, True)])
def test_final_stage_dispatch_actually_hands_off_only_for_eligible_successor(
    monkeypatch, next_level, swaps
):
    from arknights_mower.solvers import mastery_support_swap as swap

    current = plan(1, status="training")
    following = plan(2, skill=1)
    monkeypatch.setattr(db, "get_all_plans", lambda: [current, following])
    monkeypatch.setattr(rec, "get_current_mastery_level", lambda *_: next_level)
    route = stage_route(stat("教官", 95), stat("艾丽妮", 0, True), StageSpec(3, 24, 5))
    execution = swap.SwapExecution(SimpleNamespace(task=None), current, 3, route)
    execution.handoff = MagicMock()
    execution.collect = MagicMock()
    options = {"教官": {3: stat("教官", 95)}, "艾丽妮": {3: stat("艾丽妮", 0, True)}}
    panel = SimpleNamespace(countdown=datetime.now() + timedelta(minutes=310 * 1.1 / 2))
    monkeypatch.setattr(swap, "confirm_training_panel", lambda *_: panel)
    swap._apply_swap(execution, "教官", options, 5)
    assert execution.handoff.called is swaps
    assert execution.collect.called is not swaps


def test_record_transfer_failure_does_not_interrupt_completed_collection(
    database, monkeypatch
):
    first = db.insert_plan("a", 0, 3, "测试", "学员")
    db.insert_plan("a", 1, 3, "测试", "学员", priority=1)
    db.update_plan_status(first, "training")
    db.save_support_plan(first, {"level": 3}, runtime=True)
    monkeypatch.setattr(rec, "get_current_mastery_level", lambda *_: 1)
    monkeypatch.setattr(
        state, "save_runtime", MagicMock(side_effect=ValueError("write failed"))
    )
    assert (
        mastery_reader._reconcile_after_collect(
            MagicMock(),
            db.get_plan_by_id(first),
            mastery_reader.RoomPanel(mastery_tier=3),
        )
        is None
    )
    assert db.get_plan_by_id(first)["status"] == "completed"


def test_only_one_skill_chain_is_prepared_even_when_joint_crafting_is_possible(
    next_skill, monkeypatch
):
    from arknights_mower.tests.workshop_plan_fixtures import book_limit
    from arknights_mower.utils import growth
    from arknights_mower.utils.workshop_automation import calculate_workshop_plan

    monkeypatch.setattr(growth, "load_goals", lambda: [])
    box = json.loads(next_skill.cultivate.read_text())
    box["data"]["characters"][0]["skills"] = [{"level": 1}, {"level": 2}]
    next_skill.cultivate.write_text(json.dumps(box))
    skills = rec.get_skill_data()
    skills["characters"]["char_a"]["skills"] = [
        {"levels": [{"materials": [{"id": "3303", "count": count}]} for count in costs]}
        for costs in ((1, 2, 3), (1, 2, 7))
    ]
    next_skill.plans[:] = [
        plan(1, "char_a", skill=0, priority=0),
        plan(2, "char_a", skill=1, priority=1),
    ]
    result = calculate_workshop_plan(
        config.conf, local_stock={"技巧概要·卷2": 300, "技巧概要·卷3": 0}
    )
    assert result.focus["key"] == "skill:char_a:0"
    assert book_limit(result.settings) == 5

    # The first chain keeps its five books; the next quota adds seven more.
    result = calculate_workshop_plan(
        config.conf, local_stock={"技巧概要·卷2": 285, "技巧概要·卷3": 5}
    )
    assert result.focus["key"] == "skill:char_a:1"
    assert book_limit(result.settings) == 12


@pytest.mark.parametrize("cancel", [False, True])
def test_central_read_failure_preserves_confirmed_staffing_and_cancellation(
    monkeypatch, cancel
):
    from arknights_mower.utils.csleep import MowerExit

    monkeypatch.setattr(config.conf, "enable_mastery", True)
    solver = MagicMock()
    solver.op_data.operators = {"阿斯卡纶": occupant("central")}
    error = MowerExit("stopped") if cancel else ValueError("unreadable")
    with (
        patch.object(db, "get_active_plan", return_value=plan(1, status="training")),
        patch.object(mastery_reader, "read_room_state", side_effect=error),
    ):
        if cancel:
            with pytest.raises(MowerExit):
                runtime.refresh_after_central_change(solver, frozenset())
        else:
            runtime.refresh_after_central_change(solver, frozenset())
    assert solver.back_to_infrastructure.called is not cancel
    assert solver.op_data.operators["阿斯卡纶"].current_room == "central"
