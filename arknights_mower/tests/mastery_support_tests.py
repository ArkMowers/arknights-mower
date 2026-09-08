"""Automatic mastery rules, roster exclusions, plan persistence and safe handoffs."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from arknights_mower.solvers import mastery_support_runtime as runtime
from arknights_mower.utils import mastery_db as db
from arknights_mower.utils import mastery_support as support
from arknights_mower.utils.mastery_rules import compile_buff, compile_training_data
from arknights_mower.utils.scene import Scene
from arknights_mower.views.mastery import mastery_bp


@pytest.fixture
def game():
    data = json.loads((Path(__file__).parents[1] / "data/skill_data.json").read_text())[
        "training"
    ]["operators"]
    return data, {m["name"]: cid for cid, m in data.items()}


def owned(cid, elite=2):
    return {"id": cid, "evolvePhase": elite, "level": 90}


@pytest.mark.parametrize("elite,expected", [(0, []), (1, ["杜宾"] * 3)])
def test_profession_defaults_require_unlocked_training_skill(game, elite, expected):
    data, ids = game
    result = support.profession_training_routes(
        {"WARRIOR": "近卫"},
        roster=[owned(ids["杜宾"], elite), owned(ids["阿斯卡纶"]), owned(ids["芬"])],
        metadata=data,
        context=({}, 0, {}),
    )["defaults"]["近卫"]
    assert [s["name"] for s in result["supports"]] == expected
    assert not result["half_off"]
    assert all(not s["swap"] for s in result["supports"])


def test_profession_defaults_exclude_dynamic_skills_and_scheduled_trainers(game):
    data, ids = game
    names = ["余", "乌尔比安", "赤冬", "燧石", "百炼嘉维尔", "杜宾"]
    context = support.schedule_context(
        {
            "plan1": {"room_1_1": facility("赤冬", ["百炼嘉维尔"])},
            "backup_plans": [{"plan": {"dormitory_1": facility("", ["燧石"])}}],
        }
    )
    result = support.profession_training_routes(
        {"WARRIOR": "近卫"},
        roster=[owned(ids[n]) for n in names],
        metadata=data,
        context=context,
    )["defaults"]["近卫"]
    assert [s["name"] for s in result["supports"]] == ["杜宾"] * 3


@pytest.mark.parametrize(
    "name,profession",
    [("仇白", "WARRIOR"), ("提丰", "SNIPER"), ("纯烬艾雅法拉", "MEDIC")],
)
def test_profession_defaults_keep_base_bonus_without_branch_extra(
    game, name, profession
):
    data, ids = game
    result = support.profession_training_routes(
        {profession: "职业"},
        roster=[owned(ids[name])],
        metadata=data,
        context=({}, 5, {}),
    )["defaults"]["职业"]
    assert [s["efficiency"] for s in result["supports"]] == [30] * 3
    assert all(s["name"] == name and not s["swap"] for s in result["supports"])


def test_profession_defaults_preserve_halving_route(game):
    data, ids = game
    result = support.profession_training_routes(
        {"WARRIOR": "近卫"},
        roster=[owned(ids[n]) for n in ["赤冬", "燧石", "百炼嘉维尔", "艾丽妮"]],
        metadata=data,
        context=({}, 5, {}),
    )["defaults"]["近卫"]
    assert result["half_off"]
    assert any(s["swap_name"] == "艾丽妮" for s in result["supports"])
    assert not result["supports"][-1]["swap"]


def test_reference_trainers_keep_original_defaults_and_mark_ownership(game):
    from arknights_mower.solvers.mastery import DEFAULT_ROUTES, PROF_MAP

    data, ids = game
    result = support.profession_reference_trainers(
        DEFAULT_ROUTES,
        PROF_MAP,
        roster=[owned(ids["赤冬"], 1), owned(ids["燧石"])],
        metadata=data,
    )
    for label, stages in result.items():
        for level, trainer in stages.items():
            original = DEFAULT_ROUTES[label][f"level_{level}"]
            assert (trainer["name"], trainer["efficiency"]) == (
                original["operator"],
                original["efficiency"],
            )
    assert result["近卫"][1]["owned"] is True
    assert result["近卫"][1]["unlocked"] is False  # E1 only has the base +30%.
    assert result["近卫"][2]["unlocked"] is True
    assert result["近卫"][3]["owned"] is False


def test_reference_trainers_do_not_infer_unowned_from_missing_roster(game):
    from arknights_mower.solvers.mastery import DEFAULT_ROUTES, PROF_MAP

    data, _ = game
    result = support.profession_reference_trainers(
        DEFAULT_ROUTES, PROF_MAP, roster=None, metadata=data
    )
    assert len(result) == 8
    assert all(
        t["owned"] is None and t["unlocked"] is None
        for stages in result.values()
        for t in stages.values()
    )


def stat(name, efficiency=0, halves=False):
    return {
        "name": name,
        "efficiency": efficiency,
        "halves": halves,
    }


def facility(name="", replacement=None):
    return {"plans": [{"agent": name, "replacement": replacement or []}]}


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
    blocked, central, _ = support.schedule_context(plan, active={})
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
    blocked, central, _ = support.schedule_context(plan)
    assert set(blocked) == {"甲", "乙", "丙", "丁", "戊", "阿斯卡纶"}
    assert central == 0


def test_generated_resources_cover_unskilled_trainers_and_reducer_unlocks(game):
    data, ids = game
    assert data[ids["芬"]]["subProfessionId"]
    logos = data[ids["逻各斯"]]
    target = {"profession": "CASTER"}
    assert not support.trainer_stats(logos, owned(ids["逻各斯"], 1), target, 1, {})[
        "halves"
    ]
    assert support.trainer_stats(logos, owned(ids["逻各斯"]), target, 1, {})["halves"]


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
            meta,
            owned("x"),
            {"profession": "WARRIOR", "subProfessionId": "lord"},
            1,
            {},
        )["efficiency"]
        == 75
    )
    assert (
        support.trainer_stats(
            meta,
            owned("x"),
            {"profession": "WARRIOR", "subProfessionId": "fighter"},
            1,
            {},
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


def test_auto_excludes_dynamic_trainers_but_allows_unskilled_manual(game):
    data, ids = game
    roster = [
        owned(ids[n]) for n in ("能天使", "余", "乌尔比安", "芬", "逻各斯", "艾丽妮")
    ]
    options, _ = support.candidates(
        ids["能天使"], roster, data, ({"逻各斯": {"central"}}, 0, {})
    )
    assert set(options) == {"芬", "艾丽妮"}
    options, _ = support.candidates(
        ids["能天使"],
        roster,
        data,
        ({"能天使": {"dormitory_1"}, "逻各斯": {"central"}}, 0, {}),
    )
    assert set(options) == {"芬", "艾丽妮"}


def test_continuous_chain_earns_half_but_single_final_stage_does_not(game):
    data, ids = game
    roster = [owned(ids[n]) for n in ("能天使", "假日威龙陈", "W", "艾丽妮", "逻各斯")]
    chain = support.plan_supports(
        ids["能天使"], 0, 3, roster=roster, metadata=data, context=({}, 0, {})
    )
    assert not chain["stages"][0]["half_inherited"]
    assert chain["stages"][1]["half_inherited"]
    assert chain["stages"][2]["half_inherited"]
    assert chain["stages"][2]["swap_target"] is None
    for stage in chain["stages"][:-1]:
        assert stage["hours"] - (stage["switch_after"] or 0) >= 310 / 60
    final = support.plan_supports(
        ids["能天使"], 2, 3, roster=roster, metadata=data, context=({}, 0, {})
    )
    assert not final["stages"][0]["half_inherited"]
    assert final["stages"][0]["operator"] == "W"
    assert final["hours"] == pytest.approx(24 / 2)


def test_no_reducer_uses_fixed_speed_and_never_schedules_swap(game):
    data, ids = game
    result = support.plan_supports(
        ids["能天使"],
        0,
        3,
        roster=[owned(ids[n]) for n in ("能天使", "芬")],
        metadata=data,
        context=({}, 5, {}),
    )
    assert result["hours"] == pytest.approx(48 / 1.1)
    assert all(
        s["swap_target"] is None and not s["half_inherited"] for s in result["stages"]
    )


def test_manual_speed_is_not_an_eligibility_check():
    route = support.stage_route(
        stat("普通教官"), stat("速度更快的自选教官", 50), 2, 16, 0, 10, manual=True
    )
    assert route["swap_target"] == "速度更快的自选教官"


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = str(tmp_path / "mastery.db")
    original = db._conn
    monkeypatch.setattr(db, "_conn", lambda p=None: original(p or path))
    return path


def test_schema_migrates_and_keeps_old_plan(database):
    schema = db._PLAN_SCHEMA.replace("support_plan TEXT,", "").replace(
        "support_runtime TEXT,", ""
    )
    with sqlite3.connect(database) as conn:
        conn.execute(schema)
        conn.execute(
            "INSERT INTO mastery_plan (char_id, skill_index, target_level) VALUES ('old', 0, 3)"
        )
    row = db.get_plan_by_id(1)
    assert row["char_id"] == "old"
    assert row["support_plan"] is None and row["support_runtime"] is None


def test_edit_atomic_guard_clears_failed_runtime_and_rejects_stale_edit(database):
    pid = db.insert_plan("test", 0, 3, support_plan={"version": 1, "stages": []})
    db.save_support_plan(pid, {"level": 1}, runtime=True)
    original = db.get_plan_by_id(pid)
    assert db.save_support_plan(pid, {"version": 1, "stages": [1]}, expected=original)
    assert db.get_plan_by_id(pid)["support_runtime"] is None
    assert not db.save_support_plan(
        pid, {"version": 1, "stages": [2]}, expected=original
    )
    original = db.get_plan_by_id(pid)
    db.update_plan_status(pid, "arranging")
    assert not db.save_support_plan(pid, {}, expected=original)


def test_running_future_edit_keeps_runtime_and_notification_cleanup(database):
    pid = db.insert_plan("test", 0, 3, support_plan={"stages": []})
    db.update_plan_status(pid, "training")
    db.save_support_plan(pid, {"level": 1, "working_operator": "逻各斯"}, runtime=True)
    original = db.get_plan_by_id(pid)
    assert db.save_support_plan(pid, {"stages": [2]}, expected=original)
    assert db.get_plan_by_id(pid)["support_runtime"] == original["support_runtime"]
    assert db.should_notify("support_swap", f"{pid}:1")
    assert not db.should_notify("support_swap", f"{pid}:1")
    db.delete_plan(pid)
    assert db.should_notify("support_swap", f"{pid}:1")


@pytest.fixture
def context_game(game, monkeypatch):
    data, ids = game
    monkeypatch.setattr(support, "training_data", lambda: data)
    roster = [owned(ids[n]) for n in ("能天使", "假日威龙陈", "芬", "艾丽妮", "逻各斯")]
    monkeypatch.setattr(support, "owned_roster", lambda: roster)
    monkeypatch.setattr(support, "schedule_context", lambda *a, **kw: ({}, 0, {}))
    return data, ids


def test_route_api_personal_defaults_and_unowned_manual_choice(database, context_game):
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    with patch("arknights_mower.views.mastery.config.conf") as conf:
        conf.webview.token = ""
        client = app.test_client()
        data = client.get("/mastery-route").json
        assert data["best_trainers"]["近卫"]["1"]["name"] == "赤冬"
        assert data["best_trainers"]["近卫"]["1"]["owned"] is False
        allowed = {"假日威龙陈", "艾丽妮", "逻各斯"}
        assert all(
            s["name"] in allowed and (not s["swap"] or s["swap_name"] in allowed)
            for route in data["defaults"].values()
            for s in route["supports"]
        )
        personal = data["defaults"]["狙击"]
        assert (
            client.post(
                "/mastery-route", json={"profession": "狙击", **personal}
            ).status_code
            == 200
        )
        saved = client.get("/mastery-route").json["routes"]
        assert json.loads(saved[0]["supports"]) == personal["supports"]
        manual = [{"name": "赤冬", "skill_level": 1, "efficiency": 75}]
        assert (
            client.post(
                "/mastery-route", json={"profession": "近卫", "supports": manual}
            ).status_code
            == 200
        )
        saved = client.get("/mastery-route").json["routes"]
        warrior = next(r for r in saved if r["profession"] == "近卫")
        assert json.loads(warrior["supports"]) == manual


def test_route_api_keeps_reference_without_roster(database, context_game):
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    with (
        patch("arknights_mower.views.mastery.config.conf") as conf,
        patch.object(
            support, "owned_roster", side_effect=support.SupportPlanError("请同步练度")
        ),
    ):
        conf.webview.token = ""
        response = app.test_client().get("/mastery-route")
    assert response.status_code == 200
    assert response.json["defaults"] == {}
    assert response.json["defaults_error"] == "请同步练度"
    assert response.json["best_trainers"]["近卫"]["1"]["owned"] is None


def test_api_creates_atomic_plan_and_allows_unskilled_manual_choice(
    database, context_game
):
    _, ids = context_game
    with patch(
        "arknights_mower.utils.mastery_recommendation.get_current_mastery_level",
        return_value=0,
    ):
        pid, error = db.add_plan_checked(ids["能天使"], 0, 3, char_name="能天使")
    assert error is None
    plan = db.get_plan_by_id(pid)
    assert support.decode_supports(plan)["stages"]
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    stages = [
        {"level": s["level"], "operator": "芬", "swap_target": None}
        for s in support.decode_supports(plan)["stages"]
    ]
    with (
        patch("arknights_mower.views.mastery.config.conf") as conf,
        patch.object(
            support, "schedule_context", return_value=({"能天使": {"room_1_1"}}, 0, {})
        ),
    ):
        conf.webview.token = ""
        response = app.test_client().patch(
            "/mastery-plan/supports", json={"id": pid, "stages": stages}
        )
    assert response.status_code == 200, response.json
    assert response.json["support_plan"]["stages"][0]["efficiency"] == 0
    with patch.object(
        support, "schedule_context", return_value=({"芬": {"dormitory_1"}}, 5, {})
    ):
        with pytest.raises(support.SupportPlanError, match="非训练室排班"):
            support.edit_supports(plan, stages)


def test_running_stage_is_immutable_but_future_stages_are_editable(context_game):
    _, ids = context_game
    saved = support.plan_supports(ids["能天使"], 0, 3)
    plan = {
        "char_id": ids["能天使"],
        "status": "training",
        "target_level": 3,
        "support_plan": saved,
        "support_runtime": {"level": 1},
    }
    edits = [
        {
            "level": s["level"],
            "operator": s["operator"],
            "swap_target": s["swap_target"],
        }
        for s in saved["stages"]
    ]
    edits[1]["operator"] = "芬"
    assert support.edit_supports(plan, edits)["stages"][1]["operator"] == "芬"
    edits[0]["operator"] = "芬"
    with pytest.raises(support.SupportPlanError, match="已开始"):
        support.edit_supports(plan, edits)


@pytest.mark.parametrize("scheduled_trainee", [False, True])
def test_preflight_preserves_planned_reducer_without_changing_occupants(
    context_game, scheduled_trainee
):
    _, ids = context_game
    route = support.stage_route(stat("艾丽妮", 30, True), None, 1, 8, 0, 10)
    plan = {
        "id": 1,
        "char_id": ids["能天使"],
        "char_name": "能天使",
        "target_level": 3,
        "support_plan": {"stages": [route]},
    }
    solver = MagicMock()
    with (
        patch.object(
            runtime,
            "context",
            return_value=({"能天使": {"room_1_1"}} if scheduled_trainee else {}, 0, {}),
        ),
        patch.object(runtime, "persist") as persist,
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("", "能天使", None, True),
        ),
        patch(
            "arknights_mower.utils.config.conf",
            SimpleNamespace(assistant_follows_schedule=False),
        ),
    ):
        runtime.prepare(solver, plan, 1)
    assert persist.call_args.args[1]["operator"] == "艾丽妮"
    assert persist.call_args.args[1]["hours"] == pytest.approx(8 / 1.35)
    solver.choose_train.assert_not_called()
    solver.profession_filter.assert_not_called()
    solver.switch_arrange_order.assert_not_called()
    solver.ctap.assert_not_called()


def swap_case(names=("艾丽妮", "逻各斯")):
    route = support.stage_route(
        stat("快教官", 100), stat("艾丽妮", 30, True), 2, 16, 0, 10
    )
    route.update(first_halves=False, swap_halves=True, working_operator="快教官")
    plan = {
        "id": 1,
        "char_id": "target",
        "char_name": "学员",
        "skill_name": "一技能·测试",
        "target_level": 3,
        "support_plan": {"stages": [route]},
    }
    panel = SimpleNamespace(
        mastery_tier=2,
        countdown_state="active",
        countdown=datetime.now() + timedelta(seconds=5.2 * 3600 * 1.35 / 2.05),
        operator_name="学员",
        skill_name="测试",
    )
    solver = MagicMock()
    options = {"快教官": {2: stat("快教官", 100)}}
    for n in names:
        options[n] = {2: stat(n, 30 if n == "艾丽妮" else 0, True)}
    return plan, panel, solver, options


@pytest.mark.parametrize(
    "names,expected_alerts", [(("艾丽妮", "逻各斯"), 1), (("艾丽妮",), 1), ((), 0)]
)
def test_swap_insufficient_training_retains_current_and_alerts_only_if_reducers_exist(
    names, expected_alerts
):
    plan, panel, solver, options = swap_case(names)
    panel.countdown = datetime.now() + timedelta(hours=1)
    with (
        patch.object(runtime, "candidates", return_value=(options, 0)),
        patch.object(runtime, "context", return_value=({}, 0, {})),
        patch.object(runtime, "confirmed_panel", return_value=panel),
        patch.object(runtime, "warning") as warn,
        patch(
            "arknights_mower.solvers.mastery_reader._plan_matches_room",
            return_value=True,
        ),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("快教官", "学员", None, True),
        ),
        patch("arknights_mower.solvers.mastery._schedule_collect_after_swap"),
        patch.object(db, "update_plan_status") as update,
    ):
        runtime.perform_swap(solver, plan, panel, "快教官", True)
    assert warn.call_count == expected_alerts
    solver.choose_train.assert_not_called()
    assert update.call_args.kwargs["swap_frozen"] == 1


def test_delayed_alternate_is_persisted_and_queue_preserves_dispatch_task():
    plan, panel, solver, options = swap_case(names=("逻各斯",))
    with (
        patch.object(runtime, "candidates", return_value=(options, 0)),
        patch.object(runtime, "context", return_value=({}, 0, {})),
        patch.object(runtime, "confirmed_panel", return_value=panel),
        patch.object(runtime, "persist") as persist,
        patch.object(runtime, "enqueue") as enqueue,
        patch(
            "arknights_mower.solvers.mastery_reader._plan_matches_room",
            return_value=True,
        ),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("快教官", "学员", None, True),
        ),
    ):
        runtime.perform_swap(solver, plan, panel, "快教官", True)
    assert persist.call_args.args[1]["swap_target"] == "逻各斯"
    assert enqueue.call_args.args[2] > datetime.now()
    solver.choose_train.assert_not_called()
    from arknights_mower.utils.scheduler_task import TaskTypes

    task = SimpleNamespace(
        type=TaskTypes.SWAP_SUPPORT, plan_key="1", time=datetime.now()
    )
    solver.task, solver.tasks = task, [task]
    runtime.enqueue(solver, plan, datetime.now(), "逻各斯")
    assert len(solver.tasks) == 2 and solver.tasks[0] is task


def test_waiting_collection_time_does_not_earn_five_hour_credit(context_game):
    _, ids = context_game
    route = support.stage_route(stat("艾丽妮", 30, True), None, 2, 16, 0, 10)
    now = datetime.now()
    plan = {
        "id": 1,
        "char_id": ids["能天使"],
        "char_name": "能天使",
        "target_level": 3,
        "support_plan": {"stages": [route]},
        "support_runtime": {
            "level": 1,
            "working_operator": "艾丽妮",
            "working_halves": True,
            "working_since": (now - timedelta(hours=10)).isoformat(),
            "working_until": (now - timedelta(hours=6)).isoformat(),
        },
    }
    solver = MagicMock()
    with (
        patch.object(runtime, "context", return_value=({}, 0, {})),
        patch.object(runtime, "persist") as persist,
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("艾丽妮", "能天使", None, True),
        ),
        patch(
            "arknights_mower.utils.config.conf",
            SimpleNamespace(assistant_follows_schedule=False),
        ),
    ):
        runtime.prepare(solver, plan, 2)
    assert not persist.call_args.args[1]["half_inherited"]
    assert persist.call_args.args[1]["hours"] == pytest.approx(16 / 1.35)


def test_full_roster_route_search_is_bounded(game):
    data, ids = game
    with patch.object(support, "stage_route", wraps=support.stage_route) as calculate:
        support.plan_supports(
            ids["能天使"],
            0,
            3,
            roster=[owned(cid) for cid in data],
            metadata=data,
            context=({}, 5, {}),
        )
    # Candidate count grows with the roster; route search retains only useful representatives.
    assert calculate.call_count < 200


def test_start_validates_route_before_confirmation_and_rechecks_tier():
    from arknights_mower.solvers import mastery

    plan = {
        "id": 10,
        "char_id": "target",
        "char_name": "学员",
        "skill_name": "一技能·测试",
        "skill_index": 0,
        "target_level": 3,
        "support_plan": {"stages": []},
    }
    solver = MagicMock()
    solver.recog.w, solver.recog.h = 1920, 1080
    solver.train_scene.side_effect = [
        Scene.TRAIN_MAIN,
        Scene.TRAIN_MAIN,
        Scene.TRAIN_SKILL_SELECT,
        Scene.TRAIN_MAIN,
        Scene.TRAIN_SKILL_SELECT,
        Scene.TRAIN_SKILL_UPGRADE,
    ]
    events = []

    def prepare(*args):
        assert solver.ctap.call_count == 0
        assert solver.choose_train.call_count == 0
        events.append("route")

    def confirm(*args, **kwargs):
        events.append("start")
        return "started"

    with (
        patch.object(runtime, "prepare", side_effect=prepare),
        patch.object(db, "get_plan_by_id", return_value=plan.copy()),
        patch.object(db, "update_plan_status"),
        patch.object(mastery, "_read_train_countdown3", return_value=("failed", None)),
        patch.object(mastery, "_training_slots", return_value=("", "学员")),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slot_mastery_tier",
            return_value=0,
        ) as tier,
        patch.object(mastery, "_confirm_training_started", side_effect=confirm),
    ):
        mastery._start_new_training(solver, plan)
    assert events == ["route", "start"]
    assert tier.call_count == 2


def test_adding_scheduled_trainee_keeps_assistant_exclusions(database, context_game):
    _, ids = context_game
    with (
        patch.object(
            support,
            "schedule_context",
            return_value=(
                {"能天使": {"dormitory_1"}, "假日威龙陈": {"room_1_1"}},
                0,
                {},
            ),
        ),
        patch(
            "arknights_mower.utils.mastery_recommendation.get_current_mastery_level",
            return_value=0,
        ),
    ):
        pid, error = db.add_plan_checked(ids["能天使"], 0, 3, char_name="能天使")
    assert pid > 0 and error is None
    plan = db.get_plan_by_id(pid)
    assert plan["status"] == "idle"
    stages = support.decode_supports(plan)["stages"]
    assert len(stages) == 3
    assert all(s["operator"] not in {"能天使", "假日威龙陈"} for s in stages)


@pytest.mark.parametrize("legacy_payload", [False, True])
def test_plan_api_allows_scheduled_trainee(database, context_game, legacy_payload):
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    payload = (
        {"能天使": 0}
        if legacy_payload
        else {"items": [{"name": "能天使", "skill_index": 0}]}
    )
    with (
        patch("arknights_mower.views.mastery.config.conf") as conf,
        patch.object(
            support, "schedule_context", return_value=({"能天使": {"room_1_1"}}, 0, {})
        ),
        patch(
            "arknights_mower.utils.mastery_recommendation.get_current_mastery_level",
            return_value=0,
        ),
    ):
        conf.webview.token = ""
        response = app.test_client().post("/mastery-plan", json=payload)
    assert response.status_code == 200
    result = response.json["results"][0]
    assert result["status"] == "added"
    assert support.decode_supports(db.get_plan_by_id(result["id"]))["stages"]


def test_placing_support_allows_scheduled_trainee_but_not_scheduled_assistant():
    solver = MagicMock()
    plan = {"char_name": "学员"}
    panel = SimpleNamespace(countdown=datetime.now() + timedelta(hours=6))
    with (
        patch.object(runtime, "context", return_value=({"学员": {"room_1_1"}}, 0, {})),
        patch.object(runtime, "confirmed_panel", return_value=panel),
        patch.object(runtime, "record_work"),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("教官", "学员", None, True),
        ),
    ):
        assert runtime.place(solver, plan, 1, "教官") is panel
    solver.choose_train.assert_called_once_with(["教官", "Current"])
    solver.choose_train.reset_mock()
    with patch.object(
        runtime,
        "context",
        return_value=({"学员": {"room_1_1"}, "教官": {"central"}}, 0, {}),
    ):
        with pytest.raises(support.SupportPlanError, match="不能作为专精协助者"):
            runtime.place(solver, plan, 1, "教官")
    solver.choose_train.assert_not_called()


def test_recovery_uses_saved_route_without_solving_or_reading_roster():
    route = support.stage_route(stat("教官", 50), stat("逻各斯", 0, True), 2, 16, 0, 10)
    plan = {
        "id": 1,
        "target_level": 3,
        "support_plan": {"stages": [route]},
        "support_runtime": {**route, "working_operator": "教官"},
    }
    panel = SimpleNamespace(
        mastery_tier=2, countdown=datetime.now() + timedelta(hours=8)
    )
    solver = MagicMock()
    solver.tasks = []
    with (
        patch.object(runtime, "refresh_end"),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("教官", "学员", None, True),
        ),
        patch.object(runtime, "candidates") as candidates,
        patch.object(support, "plan_supports") as optimize,
    ):
        assert runtime.recover(solver, plan, SimpleNamespace(panel=panel))
    candidates.assert_not_called()
    optimize.assert_not_called()
    assert len(solver.tasks) == 1
