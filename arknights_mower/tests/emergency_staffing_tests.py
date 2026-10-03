"""设施内评分、实际技能与临时上岗门槛。"""

from dataclasses import replace
from datetime import datetime

import cv2
import numpy as np
import pytest

from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils.emergency_staffing import (
    StaffingCandidate,
    card_skills,
    eligible_worker,
    facility_score,
    select_workers,
    skill_index,
)
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS, Operator


def candidate(name, icons, mood=24):
    skills = tuple(s for s in skill_index()[name] if s["skillIcon"] in icons)
    return StaffingCandidate(name, mood, skills)


def test_product_specific_bonus_and_combination_selection():
    gold = candidate("斑点", ["bskill_man_gold1"])
    generic = candidate("赫默", ["bskill_man_spd2"])
    assert select_workers([generic, gold], "制造站", "gold", 1) == ["斑点"]
    assert select_workers([generic, gold], "制造站", "exp", 1) == ["赫默"]


def test_storage_synergy_beats_individual_greedy_choice():
    bubble = candidate("泡泡", ["bskill_man_limit&cost2", "bskill_man_spd_variable31"])
    vulcan = candidate("火神", ["bskill_man_spd&limit&cost2"])
    vermeil = candidate("红云", ["bskill_man_limit&cost1", "bskill_man_spd_variable11"])
    baseline = candidate("赫默", ["bskill_man_spd2"])
    group = select_workers([bubble, vulcan, vermeil, baseline], "制造站", "gold", 3)
    assert "泡泡" in group and "火神" in group
    assert facility_score(
        [bubble, vulcan, baseline], "制造站", "gold"
    ) > facility_score([vermeil, vulcan, baseline], "制造站", "gold")


def test_cross_facility_effect_has_no_assumed_bonus():
    rosemary = candidate("迷迭香", ["bskill_man_spd_bd_n1", "bskill_man_spd_bd2"])
    assert rosemary.skills
    assert facility_score([rosemary], "制造站", "gold") == 0


@pytest.mark.parametrize("name", TRADE_ORDER_AGENTS)
def test_every_trade_order_agent_is_excluded_even_without_order_configuration(
    solver, name
):
    op = Operator(name, "", mood=24, time_stamp=datetime.now())
    solver.op_data.add(op)
    assert not eligible_worker(solver.op_data, name, 24, set())


@pytest.mark.parametrize("mood", [None, 0, 15.9])
def test_unknown_or_low_card_mood_cannot_staff(solver, mood):
    solver.op_data.config.resting_threshold = 0.65
    op = next(iter(solver.op_data.operators.values()))
    assert not eligible_worker(solver.op_data, op.name, mood, set())


def test_personal_normal_shift_line_and_reservation_are_used(solver):
    op = next(iter(solver.op_data.operators.values()))
    op.lower_limit, op.upper_limit = 6, 20
    line = solver.op_data.resting_mood_threshold(op) + 1
    assert not eligible_worker(solver.op_data, op.name, line - 0.1, set())
    assert eligible_worker(solver.op_data, op.name, line, set())
    assert not eligible_worker(solver.op_data, op.name, 24, {op.name})


def test_ties_preserve_current_worker_and_selection_is_unique():
    a = StaffingCandidate("A", 20, ())
    b = StaffingCandidate("B", 24, ())
    assert select_workers([a, b, replace(a)], "制造站", "gold", 1, current={"A"}) == [
        "A"
    ]
    assert len(set(select_workers([a, b, replace(a)], "制造站", "gold", 3))) == 2


def test_no_candidates_returns_vacancy():
    assert select_workers([], "制造站", "gold", 3) == []


def test_current_icon_does_not_assume_elite_upgrade(tmp_path, monkeypatch):
    from arknights_mower.utils import emergency_staffing as module

    icon = cv2.imread(str(module.skill_icon_path("bskill_man_spd1")))
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    # 选人姓名框上方的技能区域，使用真实资源图标生成离线输入。
    frame[400:460, 620:680] = cv2.cvtColor(
        cv2.resize(icon, (60, 60)), cv2.COLOR_BGR2RGB
    )
    skills = card_skills(frame, ((620, 488), (820, 520)), "赫默", "制造站")
    assert {s["skillIcon"] for s in skills} == {"bskill_man_spd1"}
    frame[400:460, 620:680] //= 4
    assert card_skills(frame, ((620, 488), (820, 520)), "赫默", "制造站") == ()


def test_synergy_survives_large_candidate_pool():
    bubble = candidate("泡泡", ["bskill_man_limit&cost2", "bskill_man_spd_variable31"])
    vulcan = candidate("火神", ["bskill_man_spd&limit&cost2"])
    baseline = candidate("赫默", ["bskill_man_spd2"])
    fillers = [replace(baseline, name=f"Filler-{n}") for n in range(60)]
    group = select_workers([*fillers, bubble, vulcan], "制造站", "gold", 3)
    assert "泡泡" in group and "火神" in group


def test_fixed_efficiency_remains_counted_with_mood_consumption_clause():
    vulcan = candidate("火神", ["bskill_man_spd&limit&cost2"])
    assert facility_score([vulcan], "制造站", "gold") == -5


def test_actual_exp_product_ids_are_supported():
    skill = {"skillIcon": "local-exp", "des": "作战记录生产力+30%"}
    worker = StaffingCandidate("EXP", 24, (skill,))
    assert facility_score([worker], "制造站", "exp3") == 30
    assert facility_score([worker], "制造站", "gold") == 0


def test_synergy_pool_still_enforces_hard_candidate_budget(monkeypatch):
    from arknights_mower.utils import emergency_staffing as module

    real_combinations = module.combinations
    observed = []

    def combinations(pool, count):
        observed.append(len(pool))
        return real_combinations(pool, count)

    monkeypatch.setattr(module, "combinations", combinations)
    worker = candidate("火神", ["bskill_man_spd&limit&cost2"])
    select_workers(
        [replace(worker, name=f"Storage-{n}") for n in range(80)], "制造站", "gold", 3
    )
    assert observed == [48]


def test_control_fixed_bonus_and_local_mood_recovery():
    amiya = candidate("阿米娅", ["bskill_ctrl_t_spd"])
    scavenger = candidate("清道夫", ["bskill_ctrl_cost"])
    assert facility_score([amiya], "中枢", "") == 7
    assert facility_score([scavenger], "中枢", "") == 0.05
    # The same global trade bonus cannot stack through multiple carriers.
    assert facility_score([amiya, replace(amiya, name="Other")], "中枢", "") == 7


@pytest.mark.parametrize("level,capacity", [(1, 6), (2, 8), (3, 10)])
def test_jaye_uses_actual_trade_station_level(level, capacity):
    jaye = candidate("孑", ["bskill_tra_limit_diff", "bskill_tra_limit_count"])
    assert facility_score([jaye], "贸易站", "lmd", level=level) == capacity * 4
    generic = StaffingCandidate(
        "普通贸易干员", 24, ({"skillIcon": "trade30", "des": "订单获取效率+30%"},)
    )
    if level == 1:
        assert select_workers([jaye, generic], "贸易站", "lmd", 1, level=level) == [
            generic.name
        ]
    assert (
        facility_score([jaye, generic], "贸易站", "lmd", level=level)
        == 30 + (capacity - 3) * 4
    )


def test_unknown_trade_level_or_unmeasured_orders_have_no_assumed_jaye_bonus():
    jaye = candidate("孑", ["bskill_tra_limit_diff", "bskill_tra_limit_count"])
    assert facility_score([jaye], "贸易站", "lmd") == 0
    e0 = candidate("孑", ["bskill_tra_limit_diff"])
    assert facility_score([e0], "贸易站", "lmd", level=1) == 0


def test_rhine_pair_beats_bubble_vulcan_in_two_slot_factory():
    dorothy = candidate("多萝西", ["bskill_man_skill_spd2", "bskill_man_spd2"])
    silence = candidate("淬羽赫默", ["bskill_man_spd3"])
    bubble = candidate("泡泡", ["bskill_man_limit&cost2", "bskill_man_spd_variable31"])
    vulcan = candidate("火神", ["bskill_man_spd&limit&cost2"])
    assert facility_score([dorothy, silence], "制造站", "gold", level=2) == 65
    assert facility_score([bubble, vulcan], "制造站", "gold", level=2) == 62
    assert set(
        select_workers([dorothy, silence, bubble, vulcan], "制造站", "gold", 2, level=2)
    ) == {"多萝西", "淬羽赫默"}
    bena = candidate("贝娜", ["bskill_man_spd&limit&cost4"])
    assert facility_score([bubble, vulcan, bena], "制造站", "gold", level=3) == 93
    # Base warehouse capacity never participates in operator-added storage synergy.
    assert facility_score([bubble, vulcan], "制造站", "gold", level=3) == 62
