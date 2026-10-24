"""共享心情引擎的边界、持久化和首次确认离线验证。"""

import copy
import json
import os
import pickle
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils import calculated_mood, config
from arknights_mower.utils.calculated_mood import CalculatedMood, sync_model

NOW = datetime(2026, 9, 30, 8)


def model(moods=None, rooms=None):
    value = CalculatedMood()
    value.at = NOW
    value.moods = dict(moods or {})
    value.rooms = rooms or {}
    value.enabled = True
    value.observed = {name: NOW for name in value.moods}
    return value


def central_model():
    value = model(
        {"阿米娅": 1, "桃金娘": 24},
        {
            "central": {"roster": ["阿米娅"], "level": 5},
            "room_1_1": {"roster": ["桃金娘"], "facility": "trade", "level": 3},
        },
    )
    value.stages = {"阿米娅": (2, 80), "桃金娘": (2, 70)}
    return value


def test_exhausted_global_skill_stops_at_exact_zero_and_query_splits_agree():
    direct = central_model()
    split = copy.deepcopy(direct)
    direct.advance(NOW + timedelta(hours=20))
    for seconds in (107, 1568, 3599, 3600, 6500, 13511, 30002, 72000):
        split.advance(NOW + timedelta(seconds=seconds))
    exhaustion = 1 / 0.95
    expected = 24 - exhaustion * 0.7 - (20 - exhaustion) * 0.75
    assert direct.moods["阿米娅"] == 0
    assert direct.moods["桃金娘"] == pytest.approx(expected, abs=1e-10)
    assert split.moods == pytest.approx(direct.moods, abs=1e-10)


def test_future_queries_and_deadlines_leave_live_state_unchanged():
    value = central_model()
    old = pickle.dumps(value)
    assert value.value("桃金娘", NOW + timedelta(hours=20)) < 10
    assert value.deadline("阿米娅", 0, NOW) == pytest.approx(
        NOW + timedelta(hours=1 / 0.95), abs=timedelta(microseconds=5)
    )
    assert pickle.dumps(value) == old


def test_recovery_deadline_accepts_already_reached_personal_upper_limit():
    value = model({"桃金娘": 23}, {"dormitory_1": {"roster": ["桃金娘"], "level": 5}})
    assert value.deadline("桃金娘", 20, NOW) == NOW
    assert value.deadline("桃金娘", 24, NOW) == NOW + timedelta(hours=1 / 4.15)


def test_success_event_once_and_readback_before_delayed_event_is_not_deducted_twice():
    value = model({"桃金娘": 20})
    start = NOW + timedelta(minutes=1)
    assert value.begin_event("batch", {"桃金娘": -4}, start)
    assert value.observe("桃金娘", 16, start + timedelta(seconds=2))
    assert not value.event("batch", {"桃金娘": -4}, start + timedelta(seconds=3))
    assert value.moods["桃金娘"] == 16
    assert value.event("second", {"桃金娘": -2}, start + timedelta(seconds=4))
    assert not value.event("second", {"桃金娘": -2}, start + timedelta(seconds=5))
    assert value.moods["桃金娘"] == 14
    assert not value.observe("桃金娘", 20, start)
    assert value.moods["桃金娘"] == 14


def test_uncertain_restart_requires_observation_and_hash_mismatch_discards_state():
    value = model({"桃金娘": 20, "阿米娅": 19})
    value.begin_event("uncertain", {"桃金娘": -4}, NOW)
    restored = pickle.loads(pickle.dumps(value)).restore()
    assert "桃金娘" not in restored.moods
    assert restored.moods["阿米娅"] == 19
    assert restored.observe("桃金娘", 16, NOW + timedelta(seconds=1))
    assert not restored.event("uncertain", {"桃金娘": -4}, NOW + timedelta(seconds=2))
    value.rules_hash = "old"
    assert value.restore().moods == {}


@pytest.mark.parametrize("invalid", [-1, 25, float("nan"), float("inf"), None])
def test_invalid_observation_preserves_previous_value(invalid):
    value = model({"桃金娘": 12})
    assert not value.observe("桃金娘", invalid, NOW)
    assert value.moods["桃金娘"] == 12


def enable(solver, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(calculated_mood, "datetime", Clock)
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_recommendation.get_cultivate_snapshot",
        lambda: None,
    )
    config.conf.test_mood_calculation = True
    data = solver.op_data
    for room, slots in data.plan.items():
        if room.startswith("room_"):
            for slot in slots:
                slot.facility = "manufacture"
    for op in data.operators.values():
        data.mood_model.observe(op.name, 12, NOW)
    sync_model(data, NOW)
    return data


def test_projection_moves_same_index_between_rooms_and_keeps_live_roster(
    solver, monkeypatch
):
    data = enable(solver, monkeypatch)
    original = copy.deepcopy(data.mood_model.positions)
    projected = data.project_arrangements(
        [{"dormitory_1": ["伊内丝", "Current", "Current", "Current", "Current"]}]
    )
    assert projected.mood_model.positions["伊内丝"] == ("dormitory_1", 0)
    future = NOW + timedelta(hours=1)
    assert projected.operators["伊内丝"].current_mood(
        future
    ) == projected.calculated_mood("伊内丝", future)
    assert data.mood_model.positions == original
    projected.mood_model.observe("伊内丝", 1, NOW)
    assert data.mood_model.moods["伊内丝"] == 12


@pytest.mark.parametrize("facility", ["制造站", "贸易站", "发电站"])
def test_default_disabled_product_switching_uses_plan_facility_rate(
    solver, monkeypatch, facility
):
    data = enable(solver, monkeypatch)
    assert not config.conf.product_switching.enable
    data.plan["room_1_1"][0].facility = facility
    data.plan["room_1_1"][0].agent = "伊内丝"
    sync_model(data, NOW)
    assert data.calculated_mood("伊内丝", NOW + timedelta(hours=1)) < 12


def test_toggle_off_uses_original_observation_and_exhaust_exemptions(
    solver, monkeypatch
):
    data = enable(solver, monkeypatch)
    op = data.operators["伊内丝"]
    assert op.current_mood(NOW) == 12
    config.conf.test_mood_calculation = False
    assert op.current_mood(NOW) == 24
    config.conf.test_mood_calculation = True
    for attr in ("workaholic", "exhaust_require"):
        setattr(op, attr, True)
        assert op.predict_exhaust() == NOW + timedelta(hours=24)
        setattr(op, attr, False)


def confirm_solver(solver, monkeypatch, task_type=None):
    from arknights_mower.solvers import base_schedule
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    data = enable(solver, monkeypatch)
    op = data.operators["伊内丝"]
    op.current_room, op.current_index = "dormitory_1", 2
    op.rest_in_full = True
    data.mood_model.observe(op.name, 24, NOW)
    solver.task = SchedulerTask(
        task_type=task_type or TaskTypes.SHIFT_ON,
        task_plan={op.room: [op.name]},
        time=NOW,
    )
    solver.tasks = [solver.task]
    solver.recog = SimpleNamespace(w=1920, h=1080, update=MagicMock())
    solver.tap = MagicMock()
    solver.sleep = MagicMock()
    solver.back = MagicMock()
    solver.find = MagicMock(return_value=None)
    monkeypatch.setattr(
        base_schedule, "save_current_state", MagicMock(return_value=True)
    )
    return op, base_schedule


def test_real_confirmation_cancels_predicted_full_return_after_room_readback(
    solver, monkeypatch
):
    op, base = confirm_solver(solver, monkeypatch)
    # The normal room visit finds less mood than the forecast used to schedule.
    solver.op_data.mood_model.observe(op.name, 23.99, NOW)
    with pytest.raises(base.MoodArrangementChanged):
        solver.tap_confirm(op.room)
    solver.tap.assert_not_called()
    # A later normal visit proves recovery, then the same intent may be confirmed.
    solver.op_data.mood_model.observe(op.name, 24, NOW)
    solver.tap_confirm(op.room)


@pytest.mark.parametrize(
    "protection",
    [
        "execution_retained",
        "mood_physical_started",
        "backup_shift_active",
        "dorm_recovery_restore",
    ],
)
def test_confirmation_preserves_started_or_explicit_arrangements(
    solver, monkeypatch, protection
):
    op, base = confirm_solver(solver, monkeypatch)
    solver.op_data.mood_model.observe(op.name, 20, NOW)
    setattr(solver.task, protection, True)
    solver.tap_confirm(op.room)
    assert solver.task.plan == {op.room: [op.name]}


def test_real_confirmation_storage_failure_prevents_first_physical_tap(
    solver, monkeypatch
):
    op, base = confirm_solver(solver, monkeypatch)
    monkeypatch.setattr(base, "save_current_state", lambda: False)
    solver.find = lambda template, **kwargs: (
        (100, 200) if template == "confirm_blue" else None
    )
    with pytest.raises(base.RecognizeError, match="无法保存"):
        solver.tap_confirm(op.room)
    solver.tap.assert_not_called()
    assert not solver.task.mood_physical_started
    assert not solver.task.execution_retained


def test_collected_package_resources_run_with_crlf_without_node(tmp_path):
    import build_assets

    collected = build_assets._collect_arknights_mower_datas()
    package = tmp_path / "arknights_mower"
    for source, destination in collected:
        if destination != "arknights_mower/data/mood":
            continue
        target = tmp_path / destination / Path(source).name
        target.parent.mkdir(parents=True, exist_ok=True)
        text = Path(source).read_text("utf-8")
        target.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    runtime = package / "utils" / "calculated_mood.py"
    runtime.parent.mkdir()
    shutil.copyfile(calculated_mood.__file__, runtime)
    script = """import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('shipped_mood',sys.argv[1]); module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
print(json.dumps(module.shared_rates({'moods':{'能天使':24},'rooms':{'room_1_1':{'roster':['能天使'],'facility':'manufacture','level':3}}})['rates']))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(runtime)],
        cwd=tmp_path,
        env={
            key: value
            for key, value in {**os.environ, "PATH": ""}.items()
            if key != "PYTHONPATH"
        },
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["能天使"] == 1


def test_initialization_reads_all_staffed_facilities_once_despite_recent_cache(
    solver, monkeypatch
):
    from arknights_mower.data import base_room_list
    from arknights_mower.solvers import base_schedule as base
    from arknights_mower.solvers import mastery_reader

    enable(solver, monkeypatch)
    config.conf.enable_mastery = True
    monkeypatch.setattr(base, "_training_room_scan_disabled", False)
    solver.defer_backup_plan_until_mood_read = True
    solver._initial_mood_refresh_rooms = set()
    solver._read_room_mood = MagicMock()
    solver.enter_room = MagicMock()
    solver.back = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver.last_train_mood_read = NOW
    state = mastery_reader.RoomState("empty", slots_read=True)
    read_train = MagicMock(return_value=(state, []))
    monkeypatch.setattr(mastery_reader, "read_room_state", read_train)
    monkeypatch.setattr(mastery_reader, "reconcile_short", MagicMock())
    solver._read_agent_mood()
    expected = set(base_room_list) - {"train", "gaming_1", "gaming_2", "gaming_3"}
    assert {call.args[0] for call in solver._read_room_mood.call_args_list} == expected
    assert all(
        call.kwargs["force_mood"] for call in solver._read_room_mood.call_args_list
    )
    read_train.assert_called_once()
    assert "factory" not in solver.op_data.plan
    assert "factory" in expected
    solver.defer_backup_plan_until_mood_read = False
    solver._read_room_mood.reset_mock()
    read_train.reset_mock()
    solver._read_agent_mood()
    solver._read_room_mood.assert_not_called()
    read_train.assert_not_called()


def test_initial_cards_seed_multiple_pages_without_overwriting_actual_room_mood(
    solver, monkeypatch
):
    from arknights_mower.solvers import base_schedule as base

    data = enable(solver, monkeypatch)
    data.mood_model.moods = {"伊内丝": 7}
    data.mood_model.observed = {"伊内丝": NOW}
    solver._initial_mood_room_observations = {"伊内丝"}
    data.mood_model.moods["银灰"] = 20
    data.mood_model.observed["银灰"] = NOW - timedelta(days=1)
    solver.defer_backup_plan_until_mood_read = True
    solver.recog = SimpleNamespace(img={0: 3, 1: None, 2: 24}, w=1920, h=1080)
    for method in (
        "enter_room",
        "turn_on_room_detail",
        "tap",
        "swipe_left",
        "switch_arrange_order",
        "back_to_infrastructure",
    ):
        setattr(solver, method, MagicMock())
    solver.find = MagicMock(return_value=True)
    solver.no_pending_task = MagicMock(return_value=True)
    solver.wait_for_agent_page = MagicMock(
        side_effect=[[("银灰", 0), ("能天使", 1)], [("伊内丝", 2)]]
    )
    solver.swipe_agent_page = MagicMock(return_value=(1, None))
    monkeypatch.setattr(base, "monotonic", lambda: 0)
    monkeypatch.setattr(base, "agent_card_selected", lambda *args: False)
    monkeypatch.setattr(base, "estimate_agent_mood", lambda img, scope: img[scope])
    solver._read_initial_card_mood()
    assert data.mood_model.moods["银灰"] == 3
    assert data.mood_model.moods["伊内丝"] == 7
    assert "能天使" not in data.mood_model.moods
    assert data.mood_model.moods["讯使"] == 24
    assert solver.wait_for_agent_page.call_count == 2
    solver.defer_backup_plan_until_mood_read = False
    solver._card_moods_scanned_this_run = False
    solver.enter_room.reset_mock()
    solver._scan_card_moods()
    solver.enter_room.assert_not_called()


def test_every_normal_training_visit_reads_both_slots_without_age_requirement(
    solver, monkeypatch
):
    import numpy as np

    from arknights_mower.solvers import base_schedule as base
    from arknights_mower.utils.scene import Scene

    data = enable(solver, monkeypatch)
    solver.recog = SimpleNamespace(gray=np.zeros((1080, 1920), dtype=np.uint8))
    solver.train_scene = MagicMock(return_value=Scene.INFRA_DETAILS)
    solver.detect_room = MagicMock(return_value="train")
    solver.wait_product_complete = MagicMock()
    solver.find = MagicMock(return_value=None)
    solver.read_screen = MagicMock(side_effect=["伊内丝", "银灰", "伊内丝", "银灰"])
    solver.read_accurate_mood = MagicMock(side_effect=[17, 18, 16, 19])
    for index, name in enumerate(("伊内丝", "银灰")):
        op = data.operators[name]
        op.current_room, op.current_index = "train", index
        op.time_stamp, op.mood = NOW, 20
    first = base.BaseSchedulerSolver._observe_training_room(solver, [], None, False)
    second = base.BaseSchedulerSolver._observe_training_room(solver, [], None, False)
    assert [entry["mood"] for entry in first] == [17, 18]
    assert [entry["mood"] for entry in second] == [16, 19]
    assert all(entry["update_time"] for entry in first + second)
    assert solver.read_accurate_mood.call_count == 4


def test_box_cache_change_updates_unlocked_skills_without_restarting(
    solver, monkeypatch
):
    from arknights_mower.utils.schedule_roster import _operator_ids_by_name

    data = enable(solver, monkeypatch)
    op = data.operators["伊内丝"]
    op.current_room, op.current_index = "central", 0
    data.plan["central"] = []
    cid = next(iter(_operator_ids_by_name()["伊内丝"]))
    payload = {"data": {"characters": [{"id": cid, "evolvePhase": 0, "level": 1}]}}
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_recommendation.get_cultivate_snapshot",
        lambda: payload,
    )
    sync_model(data, NOW)
    assert data.mood_model.stages[op.name] == (0, 1)
    replacement = {"data": {"characters": [{"id": cid, "evolvePhase": 2, "level": 90}]}}
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_recommendation.get_cultivate_snapshot",
        lambda: replacement,
    )
    sync_model(data, NOW)
    assert data.mood_model.stages[op.name] == (2, 90)


def test_facility_level_uses_startup_snapshot_during_live_plan_edit(
    solver, monkeypatch
):
    data = enable(solver, monkeypatch)
    data.facility_levels = {"dormitory_1": 2}
    sync_model(data, NOW)
    monkeypatch.setattr(config.plan, "facility_levels", {"dormitory_1": 5})
    sync_model(data, NOW)
    assert data.mood_model.rooms["dormitory_1"]["level"] == 2
    projected = data.project_arrangements([])
    assert projected.mood_model.rooms["dormitory_1"]["level"] == 2


def test_unrecognized_occupied_facility_keeps_rate_and_scheduling_mood_unknown(
    solver, monkeypatch
):
    data = enable(solver, monkeypatch)
    data.plan["room_1_1"][0].facility = ""
    assert data.calculated_mood("伊内丝", NOW) is None
    assert data.calculated_mood_rate("伊内丝", NOW) is None
    assert data.calculated_mood_deadline("伊内丝", 0, NOW) is None
    assert data.mood_model.moods["伊内丝"] == 12


@pytest.mark.parametrize("readback", [22, None])
@pytest.mark.parametrize("save_ok", [True, False])
def test_real_workshop_batch_persists_once_then_calibrates_actual_mood(
    solver, monkeypatch, readback, save_ok
):
    from arknights_mower.solvers import base_schedule as base
    from arknights_mower.utils import workshop_automation, workshop_mood
    from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
    from arknights_mower.utils.operators import Operator
    from arknights_mower.utils.scene import Scene

    data = enable(solver, monkeypatch)
    config.conf.enable_mastery = False
    setting = RIICPart.WorkShopSetting(
        operator="泥岩",
        items=[
            WorkShopItem(
                item_names=["固源岩"], self_upper_limit=3, children_lower_limit=0
            )
        ],
    )
    config.conf.workshop_settings = [setting]
    data.add(
        Operator(
            "泥岩", "", current_room="factory", current_index=0, mood=24, time_stamp=NOW
        )
    )
    data.mood_model.observe("泥岩", 24, NOW)
    sync_model(data, NOW)
    snapshot = SimpleNamespace(settings=[setting], is_current=lambda: True)
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    solver.recog = MagicMock(w=1920, h=1080)
    solver.factory_scene = MagicMock(
        side_effect=[
            Scene.FACTORY_DASHBOARD,
            Scene.FACTORY_DASHBOARD,
            Scene.FACTORY_FORMULA,
            Scene.FACTORY_DASHBOARD,
            Scene.FACTORY_PRODUCT_COLLECT,
        ]
    )
    solver.tap = MagicMock()
    solver.back = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver.swipe_noinertia = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.find = MagicMock(return_value=False)
    solver.item_list = lambda: [("固源岩", ((10, 10), (20, 20)), True)]
    solver.item_valid = lambda: True
    solver.sleep = MagicMock()
    stock = {"固源岩": 0, "源岩": 9}
    monkeypatch.setattr(base, "get_inventory_counts", lambda: dict(stock))
    monkeypatch.setattr(
        base,
        "apply_workshop_inventory",
        lambda delta: stock.update(
            {name: stock.get(name, 0) + count for name, count in delta.items()}
        ),
    )
    monkeypatch.setattr(base, "invalidate_workshop_inventory", MagicMock())
    monkeypatch.setattr(base, "send_message", MagicMock())
    errors = MagicMock()
    monkeypatch.setattr(base, "save_exception", errors)
    saved = []

    def persist():
        saved.append(copy.deepcopy(data.mood_model))
        return save_ok

    monkeypatch.setattr(base, "save_current_state", persist)
    original_event = data.mood_model.event
    data.mood_model.event = MagicMock(wraps=original_event)
    costs = MagicMock(wraps=workshop_mood.operator_mood_rules)
    monkeypatch.setattr(workshop_mood, "operator_mood_rules", costs)

    def observe_factory(*args, **kwargs):
        assert "泥岩" not in data.mood_model.moods
        if readback is not None:
            data.update_detail("泥岩", readback, "factory", 0, True)
        return [{"agent": "泥岩", "mood": readback}]

    solver.get_agent_from_room = MagicMock(side_effect=observe_factory)
    solver.generate_product("泥岩", snapshot=snapshot)
    produce = (1920 * 0.88, 1080 * 0.88)
    submissions = [
        call for call in solver.tap.call_args_list if call.args[0] == produce
    ]
    assert len(submissions) == int(save_ok)
    costs.assert_called_once_with("泥岩", assume_maximum=True)
    assert saved[0].pending_events
    assert saved[0].moods["泥岩"] == 24
    if not save_ok:
        assert not data.mood_model.pending_events
        base.invalidate_workshop_inventory.assert_not_called()
        solver.get_agent_from_room.assert_not_called()
        data.mood_model.event.assert_not_called()
        return
    errors.assert_not_called()
    data.mood_model.event.assert_called_once()
    assert data.mood_model.event.call_args.args[1] == {"泥岩": -6}
    assert len(data.mood_model.events) == 1
    assert not data.mood_model.pending_events
    assert "泥岩" not in saved[1].moods
    solver.get_agent_from_room.assert_called_once_with("factory", force_mood=True)
    if readback is None:
        assert data.calculated_mood("泥岩", NOW) is None
        assert data.operators["泥岩"].mood == 24
    else:
        assert data.calculated_mood("泥岩", NOW) == 22
        assert data.operators["泥岩"].mood == 22


def test_training_entry_stops_old_work_rate_and_departure_uses_new_room_rate(
    solver, monkeypatch
):
    data = enable(solver, monkeypatch)
    op = data.operators["伊内丝"]
    op.depletion_rate = 1.5
    data.update_detail(op.name, 17, "train", 0, True)
    assert op.depletion_rate == 0
    assert op.current_mood(NOW + timedelta(hours=1)) == 17
    assert data.calculated_mood(op.name, NOW + timedelta(hours=1)) == 17
    data.update_detail(op.name, 17, op.room, op.index, True)
    assert data.calculated_mood(op.name, NOW + timedelta(hours=1)) < 17


def test_personal_release_target_is_rechecked_before_actual_confirmation(
    solver, monkeypatch
):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    op, base = confirm_solver(solver, monkeypatch)
    solver.task = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]},
        meta_data=op.name,
        mood_limit=20,
    )
    solver.op_data.mood_model.observe(op.name, 19.99, NOW)
    with pytest.raises(base.MoodArrangementChanged):
        solver.tap_confirm("dormitory_1")
    solver.tap.assert_not_called()
    solver.op_data.mood_model.observe(op.name, 20, NOW)
    solver.tap_confirm("dormitory_1")


def test_group_gap_cap_allows_ordinary_return_without_an_extra_full_mood_rule(
    solver, monkeypatch
):
    op, base = confirm_solver(solver, monkeypatch)
    op.rest_in_full = False
    op.group = "恢复组"
    data = solver.op_data
    data.groups[op.group] = [op.name]
    data.group_shift_state[op.group] = True
    data.group_recovery_full_members[op.group] = [op.name]
    data.group_recovery_return_time[op.group] = NOW
    config.conf.group_mood_gap_max_extra_wait_hours = 1
    data.mood_model.observe(op.name, 12, NOW)
    with pytest.raises(base.MoodArrangementChanged):
        solver.tap_confirm(op.room)
    data.group_recovery_return_time[op.group] = NOW - timedelta(hours=2)
    solver.tap_confirm(op.room)
    solver.tap.assert_not_called()


def test_identical_forecasts_reuse_rates_without_sharing_mutable_results(monkeypatch):
    import threading

    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    value = central_model()
    before = pickle.dumps(value)
    expected = value.value("桃金娘", NOW + timedelta(hours=20))
    calculate = MagicMock(wraps=calculated_mood._runtime.calculate)
    monkeypatch.setattr(calculated_mood._runtime, "calculate", calculate)
    assert value.value("桃金娘", NOW + timedelta(hours=20)) == expected
    calculate.assert_not_called()
    assert pickle.dumps(value) == before
    payload = {"moods": {"桃金娘": 12}, "rooms": {}}
    first = calculated_mood.shared_rates(payload)
    first["rates"]["桃金娘"] = 99
    first["thresholds"].clear()
    second = calculated_mood.shared_rates(payload)
    assert second["rates"]["桃金娘"] == 0
    assert second["thresholds"] == [0, 4, 8, 12, 16, 18, 20, 24]


def test_shared_rate_cache_is_bounded_and_preserves_exact_mood_inputs(monkeypatch):
    import threading

    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    for index in range(257):
        calculated_mood.shared_rates({"moods": {"桃金娘": index / 100}, "rooms": {}})
    assert len(calculated_mood._runtime.rate_results) == 256
    calculate = MagicMock(wraps=calculated_mood._runtime.calculate)
    monkeypatch.setattr(calculated_mood._runtime, "calculate", calculate)
    calculated_mood.shared_rates({"moods": {"桃金娘": 2.56}, "rooms": {}})
    calculate.assert_not_called()
    calculated_mood.shared_rates({"moods": {"桃金娘": 0}, "rooms": {}})
    calculate.assert_called_once()


def test_same_roster_keeps_rate_cache_after_discovering_skill_thresholds(monkeypatch):
    value = central_model()
    shared = MagicMock(wraps=calculated_mood.shared_rates)
    monkeypatch.setattr(calculated_mood, "shared_rates", shared)
    assert value._rates()["桃金娘"] == pytest.approx(0.7)
    assert value._rates()["桃金娘"] == pytest.approx(0.7)
    assert shared.call_count == 1
    value.observe("阿米娅", 0, NOW)
    assert value._rates()["桃金娘"] == pytest.approx(0.75)
    assert shared.call_count == 2


def test_same_future_roster_query_advances_once_and_observation_invalidates(
    monkeypatch,
):
    import threading

    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    value = central_model()
    advance = CalculatedMood.advance
    projected_advances = []

    def counted(model, now=None):
        if model is not value:
            projected_advances.append(now)
        return advance(model, now)

    monkeypatch.setattr(CalculatedMood, "advance", counted)
    future = NOW + timedelta(hours=20)
    assert value.value("阿米娅", future) == 0
    expected = 24 - (1 / 0.95) * 0.7 - (20 - 1 / 0.95) * 0.75
    assert value.value("桃金娘", future) == pytest.approx(expected)
    assert projected_advances == [future]
    value.observe("阿米娅", 0, NOW)
    assert value.value("桃金娘", future) == pytest.approx(9)
    assert projected_advances == [future, future]


def test_automatic_target_survives_crossing_then_changes_at_full_mood(monkeypatch):
    value = model(
        {"闪灵": 12, "芬": 5, "香草": 6},
        {"dormitory_1": {"roster": ["闪灵", "芬", "香草"], "level": 5}},
    )
    shared = MagicMock(wraps=calculated_mood.shared_rates)
    monkeypatch.setattr(calculated_mood, "shared_rates", shared)
    assert value._rates()["芬"] == pytest.approx(-4.75)
    assert value._rates()["芬"] == pytest.approx(-4.75)
    assert shared.call_count == 1
    value.observe("芬", 7, NOW)
    assert value._rates()["芬"] == pytest.approx(-4.75)
    value.observe("芬", 24, NOW)
    assert value._rates()["芬"] == pytest.approx(-4)
    assert value._rates()["香草"] == pytest.approx(-4.75)
    assert shared.call_count == 2


def test_unobserved_occupied_global_provider_does_not_gain_default_full_mood():
    value = central_model()
    del value.moods["阿米娅"]
    assert value.value("桃金娘", NOW + timedelta(hours=1)) == pytest.approx(23.25)
    assert value.value("阿米娅", NOW + timedelta(hours=1)) is None


def test_future_cache_is_bounded(monkeypatch):
    import threading

    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    value = model({"桃金娘": 12})
    for seconds in range(33):
        assert value.value("桃金娘", NOW + timedelta(seconds=seconds)) == 12
    assert len(calculated_mood._runtime.future_values) == 32


def test_deadlines_reuse_identical_boundary_steps_and_calibrate_after_observation(
    monkeypatch,
):
    import threading

    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    value = central_model()
    value.moods = {"阿米娅": 1, "芬": 24, "香草": 24}
    value.rooms["room_1_1"]["roster"] = ["芬", "香草"]
    advance = CalculatedMood.advance
    advances = []

    def counted(model, now=None):
        advances.append(now)
        return advance(model, now)

    monkeypatch.setattr(CalculatedMood, "advance", counted)
    before = pickle.dumps(value)
    exhaustion = 1 / 0.95
    expected = NOW + timedelta(hours=exhaustion + (24 - exhaustion * 0.9) / 0.95)
    first = value.deadline("芬", 0, NOW)
    first_steps = len(advances)
    assert first == pytest.approx(expected, abs=timedelta(microseconds=5))
    assert value.deadline("香草", 0, NOW) == first
    assert len(advances) == first_steps
    assert pickle.dumps(value) == before
    value.observe("阿米娅", 0, NOW)
    assert value.deadline("香草", 0, NOW) == pytest.approx(
        NOW + timedelta(hours=24 / 0.95), abs=timedelta(microseconds=5)
    )
    assert value.moods["香草"] == 24


def test_deadline_step_cache_keeps_horizon_and_target_limits(monkeypatch):
    import threading

    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    value = central_model()
    full = value.deadline("桃金娘", 0, NOW)
    assert full is not None
    assert value.deadline("桃金娘", 0, NOW, max_hours=1) is None
    earlier = value.deadline("桃金娘", 12, NOW)
    assert earlier is not None and NOW < earlier < full
    assert value.deadline("桃金娘", 24, NOW) == NOW


def test_owner_deadline_queries_share_baseline_while_wall_clock_advances(
    solver,
    monkeypatch,
):
    import threading

    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    data = enable(solver, monkeypatch)

    class AdvancingClock(datetime):
        seconds = 0

        @classmethod
        def now(cls, tz=None):
            cls.seconds += 1
            return NOW + timedelta(seconds=cls.seconds)

    monkeypatch.setattr(calculated_mood, "datetime", AdvancingClock)
    before = pickle.dumps(data.mood_model)
    target_time = NOW + timedelta(minutes=30)
    first = data.calculated_mood_deadline("伊内丝", 0, target_time)
    assert first is not None and first > target_time
    original = CalculatedMood.advance
    advances = []

    def counted(model, now=None):
        advances.append(now)
        return original(model, now)

    monkeypatch.setattr(CalculatedMood, "advance", counted)
    assert data.calculated_mood_deadline("伊内丝", 0, target_time) == first
    assert not advances
    count = len(next(iter(calculated_mood._runtime.deadline_trajectories.values())))
    for name in ("银灰", "讯使", "能天使"):
        assert data.calculated_mood_deadline(name, 0, target_time) is not None
    assert len(calculated_mood._runtime.deadline_trajectories) == 1
    assert (
        len(next(iter(calculated_mood._runtime.deadline_trajectories.values())))
        >= count
    )
    assert pickle.dumps(data.mood_model) == before
    sync_model(data, target_time)
    assert data.mood_model.at == target_time


def test_owner_query_advances_old_inputs_before_applying_changed_room_level(
    solver,
    monkeypatch,
):
    data = enable(solver, monkeypatch)
    op = data.operators["伊内丝"]
    op.current_room, op.current_index = "dormitory_1", 2
    sync_model(data, NOW)
    old_rate = data.mood_model._rates()[op.name]
    assert old_rate < 0

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW + timedelta(hours=1)

    monkeypatch.setattr(calculated_mood, "datetime", Clock)
    data.facility_levels["dormitory_1"] = 1
    data.calculated_mood_deadline(op.name, 24, NOW + timedelta(hours=2))
    assert data.mood_model.at == NOW + timedelta(hours=1)
    assert data.mood_model.moods[op.name] == pytest.approx(12 - old_rate)
    assert data.mood_model.rooms["dormitory_1"]["level"] == 1
