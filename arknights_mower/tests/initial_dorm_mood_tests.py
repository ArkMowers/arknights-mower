"""初始化卡牌预估只读页面，实际位置与恢复计时保持独立。"""

import copy
import pickle
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, record
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests import dorm_release_tests, group_resting_capacity_tests
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.dorm_candidates import dorm_candidate_mood
from arknights_mower.utils.resting_priority import has_resting_mood
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

op_data = dorm_release_tests.op_data
ROOM = dorm_release_tests.ROOM


@pytest.fixture
def solver(op_data, monkeypatch):
    monkeypatch.setattr(record, "save_agent_action", MagicMock())
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    monkeypatch.setattr(base_schedule, "agent_card_selected", lambda img, scope: False)
    monkeypatch.setattr(base_schedule, "monotonic", MagicMock(return_value=0))
    monkeypatch.setattr(
        base_schedule, "estimate_agent_mood", lambda img, scope: img[scope]
    )
    instance = object.__new__(BaseSchedulerSolver)
    instance.op_data = op_data
    instance.task = None
    instance.tasks = []
    instance.defer_backup_plan_until_mood_read = True
    instance.recog = SimpleNamespace(img={0: 3, 1: 24}, w=1920, h=1080)
    for op in op_data.operators.values():
        op.mood, op.time_stamp = 24, datetime.now()
    op_data.operators["银灰"].time_stamp = None
    op_data.operators["红"].time_stamp = None
    op_data.config.resting_priority_replacement = ["红"]
    instance.enter_room = MagicMock()
    instance.find = MagicMock(return_value=True)
    instance.tap = MagicMock()
    instance.agent_arrange_room = MagicMock(
        side_effect=AssertionError("no trial admission")
    )
    instance.tap_confirm = MagicMock(side_effect=AssertionError("no confirmation"))
    instance.back_to_infrastructure = MagicMock()
    instance.no_pending_task = MagicMock(return_value=True)
    instance.swipe_left = MagicMock()
    instance.switch_arrange_order = MagicMock()
    instance.wait_for_agent_page = MagicMock(return_value=[("银灰", 0), ("红", 1)])
    instance.swipe_agent_page = MagicMock(return_value=(1, None))
    return instance


def test_startup_scans_cards_without_selection_or_occupancy_changes(solver):
    data = solver.op_data
    before = copy.deepcopy(data.operators)
    beds = copy.deepcopy([vars(bed) for bed in data.all_dorms()])
    task = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
    solver.tasks = [task]
    solver._read_initial_card_mood()
    assert dorm_candidate_mood(data, "银灰") == 3
    assert dorm_candidate_mood(data, "红") == 24
    assert {name: vars(op) for name, op in data.operators.items()} == {
        name: vars(op) for name, op in before.items()
    }
    assert [vars(bed) for bed in data.all_dorms()] == beds
    assert solver.tasks == [task]
    solver.swipe_left.assert_called_once_with(1, "ALL")
    solver.tap.assert_called_once_with((1920 * 0.38, 1080 * 0.95), interval=0.5)
    solver.switch_arrange_order.assert_called_once_with(
        "心情", solver.enter_room.call_args.args[0], True
    )
    solver.agent_arrange_room.assert_not_called()
    solver.tap_confirm.assert_not_called()
    solver.back_to_infrastructure.assert_called_once()
    assert not solver.enter_room.call_args.args[0].startswith("dorm")
    assert not has_resting_mood(data.operators["银灰"])


@pytest.mark.parametrize("failure", ["unreadable", "not_owned", "page_failed"])
def test_estimate_failure_does_not_block_startup_or_trigger_trial_admissions(
    solver, failure
):
    if failure == "unreadable":
        solver.recog.img = {0: None, 1: None}
    elif failure == "not_owned":
        solver.wait_for_agent_page.return_value = [("未知", 0)]
    else:
        solver.wait_for_agent_page.side_effect = RuntimeError("page failed")
    solver._read_initial_card_mood()
    assert dorm_candidate_mood(solver.op_data, "银灰") is None
    solver.back_to_infrastructure.assert_called_once()
    solver.agent_arrange_room.assert_not_called()


@pytest.mark.parametrize("error", [MowerExit(), ConnectionError()])
def test_partial_estimates_survive_cancelled_scan(solver, error):
    solver.wait_for_agent_page.side_effect = [[("银灰", 0)], error]
    with pytest.raises(type(error)):
        solver._read_initial_card_mood()
    assert dorm_candidate_mood(solver.op_data, "银灰") == 3
    solver.back_to_infrastructure.assert_called_once()


@pytest.mark.parametrize("reason", ["all_measured", "no_facility", "imminent"])
def test_no_selection_page_when_not_needed_or_unavailable(solver, reason):
    if reason == "all_measured":
        for op in solver.op_data.operators.values():
            op.time_stamp = datetime.now()
    elif reason == "no_facility":
        solver.op_data.plan = {ROOM: solver.op_data.plan[ROOM]}
    else:
        solver.no_pending_task.return_value = False
    solver._read_initial_card_mood()
    solver.enter_room.assert_not_called()


def test_startup_card_scan_has_time_budget(solver, monkeypatch):
    monkeypatch.setattr(base_schedule, "monotonic", MagicMock(side_effect=[0, 0, 46]))
    solver.wait_for_agent_page.return_value = [("银灰", 0)]
    solver._read_initial_card_mood()
    assert solver.wait_for_agent_page.call_count == 1
    solver.swipe_agent_page.assert_not_called()
    assert dorm_candidate_mood(solver.op_data, "银灰") == 3


def test_startup_card_scan_has_page_budget(solver):
    solver.wait_for_agent_page.side_effect = [[(f"其他{i}", 0)] for i in range(30)]
    solver._read_initial_card_mood()
    assert solver.wait_for_agent_page.call_count == 20
    assert solver.swipe_agent_page.call_count == 19
    solver.back_to_infrastructure.assert_called_once()


def test_deadline_preserves_partial_estimates(solver):
    solver.no_pending_task.side_effect = [True, True, False]
    solver.wait_for_agent_page.return_value = [("银灰", 0)]
    solver._read_initial_card_mood()
    assert solver.wait_for_agent_page.call_count == 1
    assert dorm_candidate_mood(solver.op_data, "银灰") == 3


def test_actual_mood_overrides_card_and_estimate_expiry_keeps_unknown(solver):
    data = solver.op_data
    solver._read_initial_card_mood()
    op = data.operators["银灰"]
    assert op.current_mood() == 24  # 通用计时、加工和充能消费者仍不取得卡片预估。
    data.dorm_mood_estimates["银灰"] = (3, datetime.now() - timedelta(hours=1))
    assert dorm_candidate_mood(data, "银灰") is None
    data.update_detail("银灰", 12, "meeting", 0, True)
    data.dorm_mood_estimates["银灰"] = (3, datetime.now())
    assert dorm_candidate_mood(data, "银灰") == pytest.approx(12)


def test_legacy_probe_room_is_really_read_despite_recent_cache(solver, monkeypatch):
    monkeypatch.setattr(base_schedule, "_training_room_scan_disabled", True)
    solver._initial_mood_refresh_rooms = {ROOM}
    for op in solver.op_data.operators.values():
        op.need_to_refresh = lambda: False
    resident = solver.op_data.operators["空爆"]
    resident.current_room = ROOM
    resident.time_stamp = datetime.now()
    solver.get_agent_from_room = MagicMock(return_value=[{"agent": "空爆", "mood": 12}])
    solver.back = MagicMock()
    solver._read_agent_mood()
    solver.enter_room.assert_called_once_with(ROOM)
    solver.get_agent_from_room.assert_called_once()
    assert solver._initial_mood_refresh_rooms == set()
    solver.agent_arrange_room.assert_not_called()


def test_saved_state_uses_live_operators_and_tasks_without_card_estimates(
    solver, monkeypatch
):
    from arknights_mower import __main__ as main

    monkeypatch.setattr(main, "base_scheduler", solver)
    for attr in (
        "daily_visit_friend",
        "daily_report",
        "daily_skland",
        "daily_mail",
        "task_count",
    ):
        setattr(solver, attr, 0)
    solver._read_initial_card_mood()
    solver._initial_mood_refresh_rooms = {ROOM}
    snapshot = pickle.loads(pickle.dumps(record.current_state()))
    assert snapshot["operators"]["银灰"].time_stamp is None
    assert snapshot["initial_mood_pending"]
    assert snapshot["initial_mood_refresh_rooms"] == [ROOM]
    assert "initial_mood_probe_layout" not in snapshot
    assert "dorm_mood_estimates" not in snapshot
    assert record.current_state()["operators"] is solver.op_data.operators
    assert record.current_state()["tasks"] is solver.tasks


def test_initialization_blocks_backup_and_position_callbacks(solver):
    data = solver.op_data
    data.evaluate_expression = MagicMock(
        side_effect=AssertionError("must not evaluate")
    )
    data.swap_plan = MagicMock(side_effect=AssertionError("must not switch"))
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON)
    task.backup_shift_conditions = [True]
    assert not solver.backup_plan_solver()
    solver._prepare_shift_backup(task)
    solver._activate_shift_backup(task)
    assert solver._products_after_arrangement({}) == (data.products, data.plan)
    solver._cancel_pending_shift_on = MagicMock()
    solver.current_room_changed(data.operators["银灰"], started_working=True)
    solver._cancel_pending_shift_on.assert_not_called()


def test_initial_estimate_triggers_main_group_shift_without_writing_measured_cache(
    monkeypatch,
):
    instance = group_resting_capacity_tests.solver.__wrapped__(monkeypatch)
    data = instance.op_data
    name = group_resting_capacity_tests.DEEP[0]
    op = data.operators[name]
    op.mood, op.time_stamp = 24, None
    data.dorm_mood_estimates[name] = (0, datetime.now())
    assert instance.resting()
    assert op.mood == 24 and op.time_stamp is None
    assert not has_resting_mood(op)


def test_unknown_main_does_not_trigger_off_shift_without_a_card(monkeypatch):
    instance = group_resting_capacity_tests.solver.__wrapped__(monkeypatch)
    data = instance.op_data
    for name in group_resting_capacity_tests.DEEP:
        data.operators[name].mood = -1
        data.operators[name].time_stamp = None
    assert instance.resting() == {}


def test_failed_actual_initial_read_keeps_gate_closed(solver):
    solver.planned = False
    solver.skip = MagicMock()
    solver._read_agent_mood = MagicMock(side_effect=RuntimeError("room failed"))
    solver._read_initial_card_mood = MagicMock()
    solver.backup_plan_solver = MagicMock()
    solver.infra_main()
    assert solver.defer_backup_plan_until_mood_read
    solver._read_initial_card_mood.assert_not_called()
    solver.backup_plan_solver.assert_not_called()


def test_low_card_estimate_preserves_startup_occupancy_correction_order(monkeypatch):
    instance = group_resting_capacity_tests.solver.__wrapped__(monkeypatch)
    data = instance.op_data
    name = group_resting_capacity_tests.DEEP[0]
    op = data.operators[name]
    op.current_room, op.current_index = "", -1
    op.mood, op.time_stamp = 24, None
    data.dorm_mood_estimates[name] = (0, datetime.now())
    assert (
        instance.agent_get_mood(skip_dorm=True, read_rooms=False) == "self_correction"
    )
    assert instance.tasks[0].type == TaskTypes.SELF_CORRECTION
    assert instance.tasks[0].plan[op.room][op.index] == name
    assert dorm_candidate_mood(data, name) == 0


def test_first_green_non_target_stops_and_defaults_all_later_candidates(solver):
    data = solver.op_data
    data.operators["红"].time_stamp = None
    solver.wait_for_agent_page.return_value = [("银灰", 0), ("空爆", 1), ("红", 2)]
    # 绿色卡牌后的范围不可读取，证明扫描真正终止而不是读完整页。
    solver._read_initial_card_mood()
    assert dorm_candidate_mood(data, "银灰") == 3
    assert dorm_candidate_mood(data, "红") == 24
    assert data.dorm_mood_estimates["迷迭香"][0] == 24
    solver.swipe_agent_page.assert_not_called()
    assert not has_resting_mood(data.operators["红"])


def test_unreadable_card_before_green_remains_unknown(solver):
    solver.recog.img = {0: None, 1: 24}
    solver._read_initial_card_mood()
    assert dorm_candidate_mood(solver.op_data, "银灰") is None
    assert dorm_candidate_mood(solver.op_data, "红") == 24
    solver.swipe_agent_page.assert_not_called()


def test_previously_scanned_low_and_unknown_moods_survive_later_green(solver):
    data = solver.op_data
    data.operators["爱丽丝"].time_stamp = None
    solver.recog.img = {0: 3, 1: 24, 2: None}
    solver.wait_for_agent_page.side_effect = [
        [("银灰", 0), ("爱丽丝", 2)],
        [("空爆", 1)],
    ]
    solver._read_initial_card_mood()
    assert dorm_candidate_mood(data, "银灰") == 3
    assert dorm_candidate_mood(data, "爱丽丝") is None
    assert dorm_candidate_mood(data, "红") == 24
    assert solver.swipe_agent_page.call_count == 1


def test_yellow_near_full_does_not_stop_ascending_scan(solver):
    solver.recog.img = {0: 23.9, 1: 24}
    solver.wait_for_agent_page.side_effect = [[("银灰", 0)], [("空爆", 1)]]
    solver._read_initial_card_mood()
    assert dorm_candidate_mood(solver.op_data, "银灰") == 23.9
    assert dorm_candidate_mood(solver.op_data, "红") == 24
    assert solver.swipe_agent_page.call_count == 1


@pytest.mark.parametrize("selected", [True, None])
def test_unconfirmed_clear_never_infers_full_from_pinned_green(
    solver, monkeypatch, selected
):
    monkeypatch.setattr(
        base_schedule, "agent_card_selected", lambda img, scope: selected
    )
    solver.wait_for_agent_page.return_value = [("空爆", 1), ("银灰", 0)]
    solver._read_initial_card_mood()
    assert solver.op_data.dorm_mood_estimates == {}
    solver.back_to_infrastructure.assert_called_once()


def test_overlap_unreadable_card_keeps_prior_low_observation(solver):
    pages = iter([[("银灰", 0)], [("银灰", 2), ("空爆", 1)]])
    solver.recog.img = {0: 3, 1: 24, 2: None}
    solver.wait_for_agent_page.side_effect = lambda **kwargs: next(pages)
    solver._read_initial_card_mood()
    assert dorm_candidate_mood(solver.op_data, "银灰") == 3
    assert dorm_candidate_mood(solver.op_data, "红") == 24


def test_initial_and_idle_planning_share_one_scan_per_run(solver):
    solver._read_initial_card_mood()
    solver._scan_card_moods()
    assert solver.enter_room.call_count == 1
    solver._card_moods_scanned_this_run = False
    solver._scan_card_moods()
    assert solver.enter_room.call_count == 2


def test_idle_scan_refreshes_even_when_all_primary_mood_is_measured(solver):
    for op in solver.op_data.operators.values():
        op.time_stamp = datetime.now()
    solver._scan_card_moods()
    solver.enter_room.assert_called_once()
    assert solver.op_data.dorm_mood_estimates["迷迭香"][0] == 24


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("scan_moods", [False, True])
def test_real_primary_planning_observes_cards_before_candidate_selection(
    solver, monkeypatch, enabled, scan_moods
):
    solver.op_data.config.free_room = enabled
    solver.defer_backup_plan_until_mood_read = False
    solver.find_next_task = MagicMock(return_value=None)
    events = []
    solver._scan_card_moods = MagicMock(side_effect=lambda: events.append("scan"))
    solver.resting = MagicMock(side_effect=lambda: events.append("primary") or {})
    monkeypatch.setattr(base_schedule, "try_reorder", lambda *args: {})
    assert solver._plan_primary_recovery(scan_moods=scan_moods)
    assert events == (["scan", "primary"] if enabled and scan_moods else ["primary"])


def test_queued_shift_does_not_scan_or_replan_candidates(solver):
    solver.op_data.config.free_room = True
    solver.defer_backup_plan_until_mood_read = False
    solver.tasks = [SchedulerTask(task_type=TaskTypes.SHIFT_OFF)]
    solver._scan_card_moods = MagicMock()
    solver.resting = MagicMock()
    assert solver._plan_primary_recovery() is None
    solver._scan_card_moods.assert_not_called()
    solver.resting.assert_not_called()


@pytest.mark.parametrize("error", [MowerExit(), ConnectionError()])
def test_real_primary_planning_propagates_scan_transport_failures(solver, error):
    solver.op_data.config.free_room = True
    solver.defer_backup_plan_until_mood_read = False
    solver._scan_card_moods = MagicMock(side_effect=error)
    solver.resting = MagicMock()
    with pytest.raises(type(error)):
        solver._plan_primary_recovery()
    solver.resting.assert_not_called()
