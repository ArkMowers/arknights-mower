"""Single-target confirmation uses full non-provider padding before the target."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.dorm_recovery_tests import FINAL, ROOM, arrange
from arknights_mower.tests.dorm_recovery_tests import solver as solver
from arknights_mower.utils.dorm_candidates import full_dorm_candidate
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import TaskTypes


@pytest.mark.parametrize("mood", [6, 15, 23])
def test_unfilled_padding_does_not_confirm_even_above_target_mood(solver, mood):
    solver.op_data.operators["黑角"].mood = mood
    arrange(solver)
    assert solver.confirms == [FINAL]
    assert not solver.op_data.operators["银灰"].dorm_recovery_room


def test_full_candidate_without_single_skill_replaces_low_fixed_cover(solver):
    solver.op_data.operators["黑角"].mood = 23
    solver.op_data.add(Operator("芬", "", mood=24, time_stamp=datetime.now()))
    arrange(solver)
    assert solver.confirms == [["杜林", "琴柳", "芬", "银灰", ""], FINAL]
    assert solver.op_data.operators["银灰"].dorm_recovery_index == 3


def test_full_idle_single_recovery_manager_cannot_supply_padding(solver):
    solver.op_data.config.free_blacklist.append("黑角")
    solver.op_data.add(Operator("闪灵", "", mood=24, time_stamp=datetime.now()))
    arrange(solver)
    assert solver.confirms == [FINAL]
    assert not solver.op_data.operators["银灰"].dorm_recovery_room


@pytest.mark.parametrize("mood", [6, 15, 23])
def test_readback_requires_full_padding_even_when_it_exceeds_target(solver, mood):
    read = solver.get_agent_from_room.side_effect

    def read_changed_mood(*args, **kwargs):
        result = read(*args, **kwargs)
        if solver.confirms and solver.physical != FINAL:
            solver.op_data.operators["黑角"].mood = mood
            solver.op_data.operators["黑角"].time_stamp = datetime.now()
        return result

    solver.get_agent_from_room.side_effect = read_changed_mood
    arrange(solver)
    assert solver.physical == FINAL
    assert all(row[3] == "银灰" for row in solver.confirms)
    assert not solver.op_data.operators["银灰"].dorm_recovery_room


def test_every_low_non_single_manager_before_target_uses_full_padding(solver):
    solver.op_data.operators["杜林"].mood = 1
    solver.op_data.add(Operator("芬", "", mood=24, time_stamp=datetime.now()))
    arrange(solver)
    temporary = solver.confirms[0]
    assert set(temporary[:3]) == {"琴柳", "芬", "黑角"}
    assert temporary[1] == "琴柳"
    assert temporary[3] == "银灰"
    assert solver.confirms[-1] == FINAL
    assert solver.op_data.operators["银灰"].dorm_recovery_index == 3


def test_preceding_single_managers_stay_even_when_not_full(solver):
    solver.op_data.add(Operator("闪灵", "", mood=1, time_stamp=datetime.now()))
    solver.op_data.operators["琴柳"].mood = 1
    final = ["闪灵", "琴柳", "红", "银灰", "陈"]
    arrange(solver, final)
    assert solver.confirms == [["闪灵", "琴柳", "黑角", "银灰", ""], final]
    assert solver.op_data.operators["银灰"].dorm_recovery_index == 3


def test_low_fixed_cover_and_priority_target_arriving_together_confirm_in_two_steps(
    solver,
):
    data = solver.op_data
    solver.op_data.add(Operator("芬", "", mood=24, time_stamp=datetime.now()))
    solver.physical = ["杜林", "琴柳", "桃金娘", "陈", ""]
    solver.get_agent_from_room()
    data.operators["红"].mood = 1
    data.operators["银灰"].resting_priority = "high"
    data.operators["黑角"]._current_room, data.operators["黑角"].current_index = (
        "meeting",
        0,
    )
    data.operators["银灰"]._current_room, data.operators["银灰"].current_index = "", -1
    solver.task.type = TaskTypes.SHIFT_OFF
    solver.task.group_shift_transitions = {"联动": True}
    arrange(solver)
    assert solver.confirms == [["杜林", "琴柳", "芬", "银灰", ""], FINAL]
    assert data.operators["银灰"].dorm_recovery_index == 3
    assert data.get_current_operator(ROOM, 2).name == "红"
    assert data.group_shift_state == {}


@pytest.mark.parametrize("measured", [None, 5])
def test_newer_green_card_can_supply_padding_without_overwriting_numeric_mood(
    solver, measured
):
    data = solver.op_data
    op = data.operators["黑角"]
    op.mood = measured or 24
    op.time_stamp = datetime.now() if measured is not None else None
    data.dorm_mood_estimates[op.name] = (24, datetime.now())
    read = solver.get_agent_from_room.side_effect

    def read_roster(*args, **kwargs):
        result = read(*args, **kwargs)
        if solver.confirms:
            # 正常入住换位会清除短期卡片缓存，不能丢失本次选人的证据。
            data.dorm_mood_estimates.pop(op.name, None)
        return result

    solver.get_agent_from_room.side_effect = read_roster
    arrange(solver)
    assert solver.confirms == [["杜林", "琴柳", "黑角", "银灰", ""], FINAL]
    assert data.operators["银灰"].dorm_recovery_index == 3
    assert op.mood == (measured or 24)
    assert (op.time_stamp is None) == (measured is None)


@pytest.mark.parametrize("age", [-1, 3600, 7200])
@pytest.mark.parametrize("inferred", [False, True])
def test_invalid_green_card_cache_cannot_supply_padding(solver, age, inferred):
    data = solver.op_data
    data.operators["黑角"].time_stamp = None
    estimate = (24, datetime.now() - timedelta(seconds=age))
    data.dorm_mood_estimates["黑角"] = (*estimate, False) if inferred else estimate
    arrange(solver)
    assert solver.confirms == [FINAL]
    assert not data.operators["银灰"].dorm_recovery_room


def test_new_yellow_card_excludes_padding_without_overwriting_measurement(solver):
    data = solver.op_data
    data.dorm_mood_estimates["黑角"] = (23.9, datetime.now())
    arrange(solver)
    assert solver.confirms == [FINAL]
    assert not data.operators["银灰"].dorm_recovery_room
    assert data.operators["黑角"].mood == 24


def test_green_card_single_provider_cannot_supply_padding(solver):
    data = solver.op_data
    data.config.free_blacklist.append("黑角")
    data.add(Operator("闪灵", ""))
    data.dorm_mood_estimates["闪灵"] = (24, datetime.now())
    arrange(solver)
    assert solver.confirms == [FINAL]
    assert not data.operators["银灰"].dorm_recovery_room


def test_inferred_full_padding_confirms_without_numeric_mood(solver):
    data = solver.op_data
    op = data.operators["黑角"]
    op.time_stamp = None
    data.dorm_mood_estimates[op.name] = (24, datetime.now(), False)
    assert full_dorm_candidate(data, op.name)
    arrange(solver)
    assert solver.confirms == [["杜林", "琴柳", "黑角", "银灰", ""], FINAL]
    assert data.operators["银灰"].dorm_recovery_index == 3
    assert op.time_stamp is None


@pytest.mark.parametrize("measured", [None, -1, 5, 23, 24])
@pytest.mark.parametrize("snapshot", [False, True])
@pytest.mark.parametrize("inferred", [False, True])
def test_full_candidate_uses_newer_estimate_without_mutating_measurement(
    solver, measured, snapshot, inferred
):
    data = solver.op_data
    op = data.operators["杜林"]
    now = datetime.now()
    op.mood = 24 if measured is None else measured
    op.time_stamp = None if measured is None else now - timedelta(minutes=10)
    estimates = {op.name: (24, now, False) if inferred else (24, now)}
    if not snapshot:
        data.dorm_mood_estimates.update(estimates)

    assert (
        full_dorm_candidate(
            data, op.name, estimates=estimates if snapshot else None, now=now
        )
        is True
    )
    assert op.mood == (24 if measured is None else measured)
    assert op.time_stamp == (None if measured is None else now - timedelta(minutes=10))


@pytest.mark.parametrize("full_fixed_index", [0, 2])
@pytest.mark.parametrize("measured", [None, 24])
def test_real_card_scan_keeps_full_fixed_occupants_in_temporary_roster(
    solver, monkeypatch, full_fixed_index, measured
):
    from arknights_mower.solvers import base_schedule

    data = solver.op_data
    fixed = FINAL[full_fixed_index]
    data.operators[fixed].mood = 24
    if measured is None:
        data.operators[fixed].time_stamp = None
    sample = data.operators[fixed].time_stamp
    monkeypatch.setattr(base_schedule, "agent_card_selected", lambda img, scope: False)
    monkeypatch.setattr(base_schedule, "estimate_agent_mood", lambda img, scope: 24)
    monkeypatch.setattr(base_schedule, "monotonic", lambda: 0)
    solver.recog.w, solver.recog.h = 1920, 1080
    solver.tap = MagicMock()
    solver.no_pending_task = MagicMock(return_value=True)
    solver.swipe_left = MagicMock()
    solver.switch_arrange_order = MagicMock()
    solver.wait_for_agent_page = MagicMock(return_value=[("黑角", 0)])
    solver.back_to_infrastructure = MagicMock()

    solver._scan_card_moods()
    assert data.dorm_mood_estimates[fixed][2] is False
    assert data.operators[fixed].time_stamp == sample
    arrange(solver)

    assert len(solver.confirms) == 2
    assert solver.confirms[0][full_fixed_index] == fixed
    assert solver.confirms[0][0] == "杜林"
    assert solver.confirms[-1] == FINAL
    assert data.operators["银灰"].dorm_recovery_index == 3


@pytest.mark.parametrize("calculated", [5, 24])
def test_calculated_mood_controls_single_recovery_target(
    solver, monkeypatch, calculated
):
    from arknights_mower.utils import config
    from arknights_mower.utils.calculated_mood import sync_model

    monkeypatch.setattr(config.conf, "test_mood_calculation", True)
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_recommendation.get_cultivate_snapshot",
        lambda: None,
    )
    data = solver.op_data
    target = data.operators["银灰"]
    measured = 24 if calculated == 5 else 5
    target.mood = measured
    now = datetime.now()
    for op in data.operators.values():
        data.mood_model.observe(op.name, calculated if op is target else op.mood, now)
    sync_model(data, now)

    arrange(solver)

    assert len(solver.confirms) == (2 if calculated == 5 else 1)
    assert solver.confirms[-1] == FINAL
    assert bool(target.dorm_recovery_room) is (calculated == 5)
    assert target.mood == measured


@pytest.mark.parametrize("observed", [False, True])
def test_unregistered_padding_never_blocks_normal_roster(solver, observed):
    from arknights_mower.data import agent_list
    from arknights_mower.solvers.base_mixin import AgentSelectionNotReady

    data = solver.op_data
    data.config.free_blacklist.append("黑角")
    now = datetime.now()
    data.dorm_mood_estimates.update(
        (name, (24, now) if observed else (24, now, False))
        for name in agent_list
        if name not in data.operators
    )
    choose = solver.choose_agent.side_effect

    def select(agents, *args, **kwargs):
        if any(name != "Free" and name not in data.operators for name in agents):
            raise AgentSelectionNotReady("干员列表已到末尾，返回房间重试")
        choose(agents, *args, **kwargs)

    solver.choose_agent.side_effect = select
    arrange(solver)
    assert solver.confirms == [FINAL]
    assert solver.choose_agent.call_count == 2
    assert not data.operators["银灰"].dorm_recovery_room


def test_padding_uses_idle_operator_without_moving_another_dorm_resident(solver):
    solver.physical = ["杜林", "琴柳", "红", "陈", "黑角"]
    solver.get_agent_from_room()
    arrange(solver)
    assert solver.confirms == [FINAL]
    assert not solver.op_data.operators["银灰"].dorm_recovery_room


def test_highest_full_idle_non_provider_is_selected(solver):
    data = solver.op_data
    data.operators["黑角"].mood = 23
    data.add(Operator("芬", "", mood=24, time_stamp=datetime.now()))
    data.add(Operator("闪灵", "", mood=24, time_stamp=datetime.now()))
    arrange(solver)
    assert solver.confirms == [["杜林", "琴柳", "芬", "银灰", ""], FINAL]
    assert data.operators["银灰"].dorm_recovery_index == 3
