"""Offline admission, callback accounting and temporary chip-line execution."""

import copy
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import growth as runner
from arknights_mower.solvers import record
from arknights_mower.utils import config, growth
from arknights_mower.utils import growth_execution as execution
from arknights_mower.utils import mastery_recommendation as rec
from arknights_mower.utils.manufacture_product import DUALCHIP_PRODUCTS
from arknights_mower.utils.recognize import RecognizeError

pytestmark = pytest.mark.usefixtures("income_db")


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf(maa_growth_enable=True))
    config.stop_mower.clear()
    config.stop_maa.clear()
    names = {
        "2001": "基础作战记录",
        "2002": "初级作战记录",
        "2003": "中级作战记录",
        "2004": "高级作战记录",
        "3301": "技巧概要·卷1",
        "30011": "源岩",
        "3211": "先锋芯片",
        "3212": "先锋芯片组",
        "3213": "先锋双芯片",
        "32001": "芯片助剂",
        "4001": "龙门币",
    }
    definition = {
        "name": "测试干员",
        "profession": "PIONEER",
        "rarity": 6,
        "phases": [
            {"max_level": 2, "materials": []},
            {"max_level": 2, "materials": [{"id": "3211", "count": 2}]},
            {"max_level": 90, "materials": [{"id": "3213", "count": 4}]},
        ],
        "basic_skills": [
            [{"id": "3301", "count": 2}, {"id": "30011", "count": 1}] for _ in range(6)
        ],
        "basic_skill_requirements": [{"elite": 0, "level": 1}] * 3
        + [{"elite": 1, "level": 1}] * 3,
        "modules": [],
    }
    skills = {
        "items": {iid: {"name": name} for iid, name in names.items()},
        "characters": {"char_test": definition},
        "growth": {
            "characters": {"char_test": definition},
            "experience": [[100], [100], [100] * 89],
            "level_gold": [[10], [10], [10] * 89],
            "promotion_gold": [[100, 200]] * 6,
        },
    }
    snapshot = {
        "code": 0,
        "data": {
            "characters": [
                {"id": "char_test", "evolvePhase": 1, "level": 2, "mainSkillLevel": 6}
            ]
        },
    }
    goal = {"char_id": "char_test", "module_id": "skill7"}
    stock = {name: 10000 for name in names.values()}
    stock.update({"先锋双芯片": 0, "芯片助剂": 4, "先锋芯片组": 8})
    record.save_inventory_counts(stock)
    monkeypatch.setattr(rec, "get_skill_data", lambda: skills)
    monkeypatch.setattr(
        growth, "get_path", lambda name: tmp_path / name.rsplit("/", 1)[-1]
    )
    from arknights_mower.utils import path

    monkeypatch.setattr(
        path, "get_path", lambda name, **_: tmp_path / name.rsplit("/", 1)[-1]
    )
    (tmp_path / "cultivate.json").write_text(json.dumps(snapshot))
    return SimpleNamespace(
        skills=skills, snapshot=snapshot, goal=goal, stock=stock, tmp=tmp_path
    )


def actions(case, goals=None, plans=()):
    return list(
        execution.candidates(
            case.snapshot,
            case.skills,
            plans,
            goals or [case.goal],
            (),
            record.get_inventory_counts(),
        )
    )


def test_switch_defaults_off_and_round_trips_independently():
    conf = config.Conf()
    assert conf.maa_growth_enable is False
    enabled = config.Conf(maa_growth_enable=True, enable_mastery=False)
    assert config.Conf.model_validate_json(enabled.model_dump_json()).maa_growth_enable
    assert enabled.has_maa_tasks
    assert enabled.enable_mastery is False


def test_skill_seven_is_not_sent_before_elite_one(case):
    case.snapshot["data"]["characters"][0].update(evolvePhase=0, level=1)
    action = actions(case)[0]
    assert (action["field"], action["target"]) == ("evolvePhase", 1)
    assert action["costs"] == {"先锋芯片": 2, "龙门币": 110}
    assert "高级作战记录" in action["uncertain"]


@pytest.mark.parametrize("missing", ["先锋芯片", "龙门币", "基础作战记录"])
def test_promotion_needs_finished_chips_gold_and_exp(case, missing):
    case.snapshot["data"]["characters"][0].update(evolvePhase=0, level=1)
    if missing == "基础作战记录":
        record.invalidate_workshop_inventory(
            [case.skills["items"][iid]["name"] for iid in execution.EXP_IDS]
        )
    else:
        record.save_inventory_counts({missing: 0})
    assert actions(case) == []


def test_skill_upgrade_uses_one_paid_stage_and_no_mastery(case):
    action = actions(case)[0]
    assert (action["field"], action["target"]) == ("mainSkillLevel", 7)
    assert action["costs"] == {"技巧概要·卷1": 2, "源岩": 1}
    record.save_inventory_counts({"技巧概要·卷1": 0})
    assert actions(case) == []


def test_dualchip_admission_needs_existing_catalysts_not_red_tickets(case):
    goal = {**case.goal, "module_id": "elite2"}
    action = actions(case, [goal])[0]
    assert action["dual"] == {"3213": 4}
    record.save_inventory_counts({"芯片助剂": 3, "采购凭证": 100000})
    assert actions(case, [goal]) == []


def test_callbacks_commit_once_ignore_wrong_task_generation_identity(case, monkeypatch):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    action = actions(case)[0]
    execution.save_attempt(action)
    solver = object.__new__(BaseSchedulerSolver)
    generation = object()
    solver._maa_activity_generation = generation
    solver.maa_growth_run = {
        "action": action,
        "task_id": 42,
        "generation": generation,
        "finished": False,
    }
    payload = {
        "taskchain": "OperProgress",
        "taskid": 42,
        "what": "OperProgressDetail",
        "details": {
            "name": action["name"],
            "role": "Pioneer",
            "result": "Success",
            "result_detail": "Completed",
            "skill_level": 7,
        },
    }
    before = record.get_inventory_counts()
    runner.record_growth_callback(solver, 20003, payload, object())
    runner.record_growth_callback(solver, 20003, {**payload, "taskid": 41}, generation)
    runner.record_growth_callback(
        solver,
        20003,
        {**payload, "details": {**payload["details"], "name": "其他干员"}},
        generation,
    )
    assert record.get_inventory_counts() == before
    runner.record_growth_callback(solver, 20003, payload, generation)
    runner.record_growth_callback(solver, 20003, payload, generation)
    assert record.get_inventory_counts()["技巧概要·卷1"] == before["技巧概要·卷1"] - 2
    assert record.get_inventory_counts()["源岩"] == before["源岩"] - 1
    assert (
        json.loads((case.tmp / "cultivate.json").read_text())["data"]["characters"][0][
            "mainSkillLevel"
        ]
        == 7
    )
    assert execution.finish_attempt(action, success=True) is False


def test_old_cloud_keeps_progress_and_counts_even_force_refresh(case):
    action = actions(case)[0]
    execution.save_attempt(action)
    execution.finish_attempt(action, success=True)
    merged, protected = execution.reconcile_snapshot(case.snapshot)
    assert merged["data"]["characters"][0]["mainSkillLevel"] == 7
    record.save_inventory_counts(
        case.stock,
        scanned_counts={},
        cloud_counts=case.stock,
        cloud_at=9999999999,
        force_cloud=True,
        preserve_cloud=protected,
    )
    assert record.get_inventory_counts()["技巧概要·卷1"] == 9998
    fresh = copy.deepcopy(case.snapshot)
    fresh["data"]["characters"][0]["mainSkillLevel"] = 7
    _, protected = execution.reconcile_snapshot(fresh)
    assert protected == set()


def test_already_satisfied_does_not_guess_payment(case):
    action = actions(case)[0]
    execution.save_attempt(action)
    execution.finish_attempt(action, success=True, already=True)
    assert "技巧概要·卷1" not in record.get_inventory_counts()
    merged, _ = execution.reconcile_snapshot(case.snapshot)
    assert merged["data"]["characters"][0]["mainSkillLevel"] == 7


def test_interrupted_run_never_replays_unchanged_inventory_after_restart(case):
    action = actions(case)[0]
    execution.save_attempt(action)
    execution.recover_attempts()
    assert execution.blocked(action)
    assert "技巧概要·卷1" not in record.get_inventory_counts()
    execution.recover_attempts()
    assert execution.blocked(action)
    # A real new observation, even with the same count, releases the failed action.
    record.save_inventory_counts(case.stock)
    assert not execution.blocked(action)
    assert actions(case)


def test_chip_guard_overrides_every_missing_material_entry(tmp_path):
    root = tmp_path / "cache"
    execution.prepare_guard(root, split=True)
    tasks = json.loads((root / "resource/tasks/tasks.json").read_text())
    assert len(tasks) == 6
    assert tasks["OperProgress@Dualchip"]["action"] == "DoNothing"
    assert all(task["templThreshold"] > 1 for task in tasks.values())
    assert all(task["next"] == [] for task in tasks.values())
    legacy = root / "resource/tasks.json"
    legacy.write_text('{"stage": {"algorithm": "JustReturn"}}')
    execution.prepare_guard(root, split=False)
    assert "stage" in json.loads(legacy.read_text())
    assert "OperProgress@SkillUpMaterial0" in json.loads(legacy.read_text())


@pytest.fixture
def chip_solver(case):
    solver = MagicMock()
    solver.MAA = None
    solver.op_data.plan = {
        room: [SimpleNamespace(facility="制造站")] for room in ("room_1_1", "room_1_2")
    }
    solver.op_data.facility_states = {}
    solver.read_manufacture_product.return_value = "gold"
    solver._read_manufacture_queue_count.return_value = 0
    solver._product_ocr_text.return_value = "先锋双芯片"

    def survey(room, target, **kwargs):
        return {
            "room": room,
            "current_product": "gold",
            "target_product": target,
            "needs_switch": True,
            "available_drones": 100,
            "current_remaining": 500 if room == "room_1_1" else 600,
            "total_seconds": 500 if room == "room_1_1" else 600,
            "production_rate": 1 if room == "room_1_1" else 3,
            "production_rate_observed": True,
            "observed_at": datetime.now(),
        }

    solver._survey_manufacture_switch.side_effect = survey

    def accelerate(observation):
        observation.update(
            remaining_after_acceleration=0, accelerated_at=datetime.now()
        )

    solver._execute_manufacture_acceleration.side_effect = accelerate
    return solver


def test_chip_line_selects_actual_fastest_station_restores_and_never_changes_staff(
    case, chip_solver
):
    action = actions(case, [{**case.goal, "module_id": "elite2"}])[0]
    # The station with 600 base seconds finishes sooner at its observed 3x speed.
    chip_solver.read_manufacture_product.side_effect = [RecognizeError("chip"), "gold"]
    assert runner.manufacture_chips(
        chip_solver, action, datetime.now() + timedelta(minutes=5)
    )
    assert chip_solver._survey_manufacture_switch.call_count == 2
    assert (
        chip_solver._execute_manufacture_acceleration.call_args.args[0]["room"]
        == "room_1_2"
    )
    chip_solver._select_manufacture_recipe.assert_called_once()
    assert chip_solver._select_manufacture_recipe.call_args.kwargs["count"] == 4
    assert (
        chip_solver._select_manufacture_recipe.call_args.args[0]
        == DUALCHIP_PRODUCTS["3213"]
    )
    chip_solver._select_manufacture_product.assert_called_once_with("gold")
    chip_solver.choose_agent.assert_not_called()
    chip_solver.sleep.assert_not_called()
    assert record.get_inventory_counts()["先锋双芯片"] == 4
    assert record.get_inventory_counts()["先锋芯片组"] == 0
    assert record.get_inventory_counts()["芯片助剂"] == 0
    assert runner._chip_state() is None
    assert runner.restore_chip_product(chip_solver)
    assert record.get_inventory_counts()["先锋双芯片"] == 4


def test_chip_failure_restores_and_does_not_invent_output(case, chip_solver):
    action = actions(case, [{**case.goal, "module_id": "elite2"}])[0]
    chip_solver._select_manufacture_recipe.side_effect = RecognizeError("cancelled")
    with pytest.raises(RecognizeError):
        runner.manufacture_chips(
            chip_solver, action, datetime.now() + timedelta(minutes=5)
        )
    assert "先锋双芯片" not in record.get_inventory_counts()
    assert runner._chip_state() is None


def test_growth_yields_to_due_tasks_and_off_switch(case, chip_solver):
    chip_solver.find_next_task.return_value = SimpleNamespace(time=datetime.now())
    runner.run_growth(chip_solver)
    chip_solver.initialize_maa.assert_not_called()
    chip_solver.find_next_task.return_value = None
    config.conf.maa_growth_enable = False
    runner.run_growth(chip_solver)
    chip_solver.initialize_maa.assert_not_called()


def test_real_scheduler_callback_and_run_cleanup_confirm_supplied_skill(case):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    solver = object.__new__(BaseSchedulerSolver)
    solver.MAA = None
    solver.maa_callback = None
    solver.recog = MagicMock()
    solver.sleep = MagicMock()
    submitted = []
    closed = []

    class Core:
        def append_task(self, task, params):
            submitted.append((task, params))
            return 42

        def start(self):
            return True

        def running(self):
            solver.on_maa_callback(
                20003,
                json.dumps(
                    {
                        "taskchain": "OperProgress",
                        "taskid": 42,
                        "what": "OperProgressDetail",
                        "details": {
                            "name": "测试干员",
                            "role": "Pioneer",
                            "result": "Success",
                            "result_detail": "Completed",
                            "skill_level": 7,
                        },
                    }
                ).encode(),
                None,
                observation_run=solver._maa_activity_generation,
            )
            return False

        def stop(self):
            return True

        def close(self):
            closed.append(True)

    def initialize():
        solver.MAA = Core()
        solver._maa_activity_generation = object()

    solver.initialize_maa = initialize
    action = actions(case)[0]
    assert runner._run_maa(solver, action, datetime.now() + timedelta(minutes=5))
    assert submitted == [
        (
            "OperProgress",
            {"plans": [{"role": "Pioneer", "name": "测试干员", "skill_level": 7}]},
        )
    ]
    assert closed == [True]
    assert solver.MAA is None
    assert solver.maa_growth_run is None
    assert not record.battle_inventory_active.is_set()
    solver.recog.reset_after_external_control.assert_called_once()
    assert record.get_inventory_counts()["技巧概要·卷1"] == 9998


def test_task_chain_completion_alone_never_confirms_progress(case):
    action = actions(case)[0]
    execution.save_attempt(action)
    generation = object()
    solver = SimpleNamespace(
        _maa_activity_generation=generation,
        maa_growth_run={
            "action": action,
            "task_id": 42,
            "generation": generation,
            "finished": False,
        },
    )
    runner.record_growth_callback(
        solver, 10002, {"taskchain": "OperProgress", "taskid": 42}, generation
    )
    assert not solver.maa_growth_run["finished"]
    assert record.get_inventory_counts()["技巧概要·卷1"] == 10000


def test_local_progress_is_not_applied_to_another_account(case):
    action = actions(case)[0]
    execution.save_attempt(action)
    execution.finish_attempt(action, success=True)
    other = {**case.snapshot, "_mower_player": {"uid": "different"}}
    merged, protected = execution.reconcile_snapshot(other)
    assert merged["data"]["characters"][0]["mainSkillLevel"] == 6
    assert protected == set()


def test_partial_promotion_failure_does_not_invent_elite_or_keep_spendable_stock(case):
    case.snapshot["data"]["characters"][0].update(evolvePhase=0, level=1)
    action = actions(case, [{**case.goal, "module_id": "elite2"}])[0]
    execution.save_attempt(action)
    execution.finish_attempt(action)
    merged, protected = execution.reconcile_snapshot(case.snapshot)
    assert merged["data"]["characters"][0]["evolvePhase"] == 0
    assert "龙门币" not in record.get_inventory_counts()
    assert "先锋芯片" not in record.get_inventory_counts()
    assert protected == set()  # Fresh inventory can release an unconfirmed failure.


def test_completed_receipt_is_never_admitted_again_with_an_old_file(case):
    action = actions(case)[0]
    execution.save_attempt(action)
    execution.finish_attempt(action, success=True)
    assert execution.blocked(action)


def test_native_recipe_uses_verified_exact_quantity_and_never_max(case):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    solver = object.__new__(BaseSchedulerSolver)
    solver._tap_product_point = MagicMock()
    solver._wait_product_resource = MagicMock()
    solver._fill_manufacture_queue = MagicMock()
    solver.recog = MagicMock()
    solver._product_ocr_text = MagicMock(return_value="4")
    solver._select_manufacture_recipe(DUALCHIP_PRODUCTS["3213"], count=4)
    assert (
        sum(
            call.args == ((1300, 305),)
            for call in solver._tap_product_point.call_args_list
        )
        == 3
    )
    solver._fill_manufacture_queue.assert_not_called()
    solver._product_ocr_text.return_value = "1"
    solver._tap_product_point.reset_mock()
    with pytest.raises(RecognizeError, match="份数未确认"):
        solver._select_manufacture_recipe(DUALCHIP_PRODUCTS["3213"], count=4)
    assert ((1425, 895),) not in [
        call.args for call in solver._tap_product_point.call_args_list
    ]


def test_idle_growth_dispatches_from_saved_goal_then_wakes_native_mastery(
    case, monkeypatch
):
    from arknights_mower.utils import mastery_db

    monkeypatch.setattr(
        rec, "get_path", lambda name: case.tmp / name.rsplit("/", 1)[-1]
    )
    monkeypatch.setattr(mastery_db, "get_all_plans", lambda: [])
    (case.tmp / "growth_plan.json").write_text(json.dumps([case.goal]))
    submitted = []

    def execute(solver, action, deadline):
        submitted.append(action)
        assert action["field"] == "mainSkillLevel"
        assert action["target"] == 7
        assert deadline > datetime.now()
        execution.save_attempt(action)
        execution.finish_attempt(action, success=True)
        execution.publish_progress()
        return True

    monkeypatch.setattr(runner, "_run_maa", execute)
    solver = SimpleNamespace(
        MAA=None,
        find_next_task=MagicMock(return_value=None),
        _auto_schedule_mastery_after_scan=MagicMock(),
    )
    runner.run_growth(solver)
    runner.run_growth(solver)
    assert len(submitted) == 1
    assert record.get_inventory_counts()["技巧概要·卷1"] == 9998
    solver._auto_schedule_mastery_after_scan.assert_called_once()


def test_unavailable_core_does_not_spend_or_retry_unchanged_materials(case):
    action = actions(case)[0]
    execution.reject_attempt(action)
    assert actions(case) == []
    assert record.get_inventory_counts()["技巧概要·卷1"] == 10000
    record.save_inventory_counts(
        {"技巧概要·卷1": 10000},
        scanned_counts={"技巧概要·卷1": 10000},
        scanned_at=datetime.now().timestamp(),
    )
    assert actions(case)


def test_earlier_ready_mastery_reserves_materials_before_later_skill_goal(case):
    char = case.snapshot["data"]["characters"][0]
    char.update(evolvePhase=2, level=1, mainSkillLevel=7, skills=[{"level": 0}])
    definition = case.skills["characters"]["char_test"]
    definition["skills"] = [{"levels": [{"materials": [{"id": "3301", "count": 2}]}]}]
    case.snapshot["data"]["characters"].append(
        {"id": "char_next", "evolvePhase": 1, "level": 2, "mainSkillLevel": 6}
    )
    case.skills["growth"]["characters"]["char_next"] = copy.deepcopy(definition)
    case.skills["characters"]["char_next"] = copy.deepcopy(definition)
    plan = {
        "id": 1,
        "char_id": "char_test",
        "skill_index": 0,
        "target_level": 1,
        "status": "idle",
    }
    goal = {"char_id": "char_next", "module_id": "skill7"}
    record.save_inventory_counts({"技巧概要·卷1": 2})
    assert actions(case, [goal], [plan]) == []
    record.save_inventory_counts({"技巧概要·卷1": 4})
    assert actions(case, [goal], [plan])[0]["char_id"] == "char_next"


def test_restart_restores_chip_product_once_and_off_switch_keeps_compensation(
    case, chip_solver
):
    state = {
        "room": "room_1_2",
        "original": "gold",
        "produced": True,
        "delta": {"先锋双芯片": 4, "先锋芯片组": -8, "芯片助剂": -4},
    }
    runner._chip_state(state)
    chip_solver.read_manufacture_product.side_effect = [RecognizeError("chip"), "gold"]
    chip_solver.find_next_task.return_value = None
    config.conf.maa_growth_enable = False
    runner.run_growth(chip_solver)
    assert runner._chip_state() is None
    assert record.get_inventory_counts()["先锋双芯片"] == 4
    runner.run_growth(chip_solver)
    assert record.get_inventory_counts()["先锋双芯片"] == 4
    chip_solver.initialize_maa.assert_not_called()


@pytest.mark.parametrize("observed", [0, 1, None])
def test_promotion_payment_requires_matching_game_observed_starting_phase(
    case, observed
):
    case.snapshot["data"]["characters"][0].update(evolvePhase=0, level=2)
    action = actions(case, [{**case.goal, "module_id": "elite2"}])[0]
    execution.save_attempt(action)
    generation = object()
    solver = SimpleNamespace(
        _maa_activity_generation=generation,
        maa_growth_run={
            "action": action,
            "task_id": 42,
            "generation": generation,
            "finished": False,
        },
    )
    if observed is not None:
        runner.record_growth_callback(
            solver,
            20001,
            {
                "taskchain": "OperProgress",
                "taskid": 42,
                "details": {"task": f"OperProgress@CurrentElite{observed}"},
            },
            generation,
        )
    runner.record_growth_callback(
        solver,
        20003,
        {
            "taskchain": "OperProgress",
            "taskid": 42,
            "what": "OperProgressDetail",
            "details": {
                "name": "测试干员",
                "role": "Pioneer",
                "result": "Success",
                "result_detail": "Completed",
                "elite": 2,
            },
        },
        generation,
    )
    stock = record.get_inventory_counts()
    if observed == 0:
        assert stock["先锋芯片"] == 9998
    else:
        assert "先锋芯片" not in stock
    assert (
        json.loads((case.tmp / "cultivate.json").read_text())["data"]["characters"][0][
            "evolvePhase"
        ]
        == 2
    )


def test_cloud_regression_after_catchup_cannot_restore_old_payment(case):
    action = actions(case)[0]
    execution.save_attempt(action)
    execution.finish_attempt(action, success=True)
    fresh = copy.deepcopy(case.snapshot)
    fresh["data"]["characters"][0]["mainSkillLevel"] = 7
    assert execution.reconcile_snapshot(fresh)[1] == set()
    merged, protected = execution.reconcile_snapshot(case.snapshot)
    assert merged["data"]["characters"][0]["mainSkillLevel"] == 7
    assert "技巧概要·卷1" in protected


def test_growth_guard_overrides_downloaded_definitions_without_rewriting_unchanged_cache(
    tmp_path,
):
    root = tmp_path / "cache"
    path = root / "resource/tasks/tasks.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "OperProgress@Dualchip": {
                    "algorithm": "JustReturn",
                    "action": "ClickRect",
                },
                "ActivityStage": {"algorithm": "JustReturn"},
            }
        )
    )
    execution.prepare_guard(root, split=True)
    result = json.loads(path.read_text())
    assert result["OperProgress@Dualchip"]["action"] == "DoNothing"
    assert result["OperProgress@Dualchip"]["templThreshold"] == 2.0
    assert "ActivityStage" in result
    stamp = path.stat().st_mtime_ns
    execution.prepare_guard(root, split=True)
    assert path.stat().st_mtime_ns == stamp
