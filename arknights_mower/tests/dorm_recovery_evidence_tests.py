"""宿舍实读与原任务确认次数；未观测到的技能或速度不从排班补齐。"""

import pickle
from datetime import timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import (
    dorm_recovery_tests,
    scheduler_recovery_preservation_tests,
)
from arknights_mower.tests.dorm_recovery_tests import FINAL, ROOM, arrange
from arknights_mower.utils import config
from arknights_mower.utils.dorm_recovery import observed_recovery_recipient
from arknights_mower.utils.dorm_skills import dorm_skill_effects
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = dorm_recovery_tests.solver
scheduler = scheduler_recovery_preservation_tests.scheduler


def rows(samples, names=("隐德来希", "蜜莓", "星源", "结城理", "八幡海铃")):
    return [
        dict(agent=name, measured_mood=pixels * 24 / 310, recovery_seconds=seconds)
        for name, (pixels, seconds) in zip(names, samples, strict=True)
    ]


@pytest.mark.parametrize(
    ("samples", "target"),
    [
        ([(195, 10611), (145, 19924), (257, 6277)], "星源"),
        ([(197, 13595), (148, 14971), (261, 5930)], "结城理"),
        ([(205, 9697), (159, 18297), (0, None)], "星源"),
    ],
)
def test_b304_same_slot_measurements(samples, target):
    actual = rows([(310, None), (310, None), *samples])
    if samples[-1][1] is None:
        actual[-1] = {"agent": ""}
    assert observed_recovery_recipient(actual, {}) == target


@pytest.mark.parametrize(
    "first,second,target",
    [
        ((225, 7973), (179, 15882), "星源"),
        ((225, 7962), (179, 15871), "星源"),
        ((236, 6932), (286, 2830), "结城理"),
        ((239, 6640), (287, 2729), "结城理"),
    ],
)
def test_b304_batch_and_staged_arrivals_from_empty_beds(first, second, target):
    other = "结城理" if target == "星源" else "星源"
    actual = rows(
        [(310, None), (310, None), first, second, (0, None)],
        ("隐德来希", "波登可", target, other, ""),
    )
    assert observed_recovery_recipient(actual, {"波登可": (1, 1)}) == target


@pytest.mark.parametrize(
    "fourth,fifth,old_timer,common,short,ordinary",
    [
        ("芙兰卡", "莱欧斯", 1078, 6256, 4791, 6251),
        ("缠丸", "炎客", 1053, 6257, 4792, 6252),
    ],
)
def test_workshop_pair_before_and_after_original_recipient_leaves(
    fourth, fifth, old_timer, common, short, ordinary
):
    names = ("隐德来希", "蜜莓", "玫兰莎", fourth, fifth)
    samples = [(310, None), (310, None), (298, old_timer)]
    before = rows([*samples, (258, common), (258, common)], names)
    after = rows([*samples, (258, short), (258, ordinary)], names)
    after[2] = {"agent": ""}
    stages = {"蜜莓": (2, 60)}
    assert observed_recovery_recipient(before, stages) == "玫兰莎"
    assert observed_recovery_recipient(after, stages) == fourth
    # 保持床位和条宽不变，对调倒计时以检验程序没有按床号猜测。
    after[3]["recovery_seconds"], after[4]["recovery_seconds"] = ordinary, short
    assert observed_recovery_recipient(after, stages) == fifth


@pytest.mark.parametrize(
    "third,fourth,fifth",
    [
        ((258, 4878), (0, None), (0, None)),
        ((258, 5026), (129, 21909), (0, None)),
        ((259, 5003), (129, 21886), (297, 1560)),
    ],
)
def test_workshop_g1_multiple_sources_remain_unknown(third, fourth, fifth):
    names = (
        "隐德来希",
        "波登可",
        "断罪者",
        "安赛尔" if fourth[1] else "",
        "玫兰莎" if fifth[1] else "",
    )
    actual = rows([(310, None), (310, None), third, fourth, fifth], names)
    stages = {
        "隐德来希": (2, 70),
        "波登可": (2, 1),
        "断罪者": (1, 1),
        "安赛尔": (1, 55),
        "玫兰莎": (1, 55),
    }
    assert observed_recovery_recipient(actual, stages) is None


def test_single_remaining_resident_needs_baseline_even_with_unlocked_source():
    actual = rows(
        [(310, None), (310, None), (159, 13966), (0, None), (0, None)],
        ("隐德来希", "蜜莓", "结城理", "", ""),
    )
    assert observed_recovery_recipient(actual, {}) is None
    assert observed_recovery_recipient(actual, {"蜜莓": (1, 80)}) is None
    assert observed_recovery_recipient(actual, {"蜜莓": (2, 1)}) is None
    assert dorm_skill_effects("波登可", (0, 1)).single == {0.55}
    assert dorm_skill_effects("波登可", (1, 1)).single == {0.65}
    assert dorm_skill_effects("波登可", None).single == {0.55, 0.65}


@pytest.mark.parametrize("peer", [(310, None), (309, 20), (0, 28709)])
def test_one_usable_rate_above_room_range_does_not_prove_bonus(peer):
    actual = rows([(310, None), (310, None), (155, 6545), peer, (310, None)])
    assert observed_recovery_recipient(actual, {"蜜莓": (2, 1)}) is None


@pytest.mark.parametrize("invalid", [None, -1, 0, True, 1, 10**9, "04:30:00"])
def test_invalid_or_missing_countdown_does_not_establish_single(invalid):
    actual = rows([(310, None), (310, None), (195, 10611), (145, invalid), (257, 6277)])
    assert observed_recovery_recipient(actual, {}) is None


def test_incomplete_uncertain_and_special_residents_are_not_compared():
    base = rows([(310, None), (310, None), (195, 10611), (145, 19924), (257, 6277)])
    for change in (
        {"observed": False},
        {"measured_mood": 23.95},
        {"agent": "杜林"},
        {"agent": "冰酿"},
        {"agent": "闪灵"},
        {"agent": "结城理"},
        {"agent": "未知姓名"},
    ):
        actual = [*base[:2], {**base[2], **change}, *base[3:]]
        assert observed_recovery_recipient(actual, {}) is None
    base[4] = {"agent": "菲亚梅塔", "measured_mood": 2, "recovery_seconds": 39600}
    assert observed_recovery_recipient(base, {}) == "星源"
    base[1].update(measured_mood=12, recovery_seconds=18783)
    assert observed_recovery_recipient(base, {}) == "星源"


@pytest.mark.parametrize(
    "peers, samples, target",
    [
        (("结城理", "八幡海铃"), ((248, 5414), (276, 3958)), "结城理"),
        (("结城理", "八幡海铃"), ((252, 5138), (278, 3684)), "结城理"),
        (("八幡海铃", "结城理"), ((285, 2206), (259, 5918)), "八幡海铃"),
        (("八幡海铃", "结城理"), ((286, 2784), (260, 4433)), "结城理"),
    ],
)
def test_b104_single_recipient_with_two_ordinary_roommates_sharing_recovery(
    peers, samples, target
):
    actual = rows(
        [(310, None)] * 3 + list(samples), ("冰酿", "闪灵", "菲亚梅塔", *peers)
    )
    for stages in ({}, {"闪灵": (2, 1)}):
        assert observed_recovery_recipient(actual, stages) == target
    for index in (0, 1, 2):
        near_full = [dict(row) for row in actual]
        near_full[index]["recovery_seconds"] = 12
        assert observed_recovery_recipient(near_full, {}) is None
    actual[1]["agent"] = "桃金娘"
    assert observed_recovery_recipient(actual, {}) is None


@pytest.mark.parametrize("enabled", [False, True])
def test_b104_two_new_arrivals_to_a_full_room_with_fiammetta(
    solver, monkeypatch, enabled
):
    from datetime import datetime

    from arknights_mower.utils.plan import Room

    monkeypatch.setattr(config.conf, "test_mood_calculation", enabled)
    fixed = ["冰酿", "闪灵", "菲亚梅塔"]
    for index, name in enumerate(fixed):
        solver.op_data.plan[ROOM][index] = Room(name, "", [])
        solver.op_data.add(
            Operator(name, ROOM, index=index, mood=24, time_stamp=datetime.now())
        )
    solver.op_data.operators["黑角"].mood = 24
    solver.op_data.operators["红"].mood = 24
    solver.physical = fixed + ["黑角", "红"]
    solver.get_agent_from_room()
    if enabled:
        for op in solver.op_data.operators.values():
            solver.op_data.mood_model.observe(op.name, op.mood)
    final = fixed + ["银灰", "陈"]
    arrange(solver, final)
    assert solver.confirms == [final]
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM
    assert not solver.task.plan


def test_b104_direct_arrival_requires_full_residents_and_a_fixed_charger_pair():
    from arknights_mower.utils.dorm_recovery import direct_recovery_arrival

    names = ("冰酿", "闪灵", "菲亚梅塔", "桃金娘", "维什戴尔")
    actual = rows([(310, None)] * 5, names)
    goal = [*names[:3], "结城理", "八幡海铃"]
    assert direct_recovery_arrival(goal, "结城理", actual, {}, None)
    for index in range(5):
        partial = [dict(row) for row in actual]
        partial[index]["recovery_seconds"] = 12
        assert not direct_recovery_arrival(goal, "结城理", partial, {}, None)
    for changed in (
        [goal[1], goal[0], *goal[2:]],
        [*goal[:4], names[4]],
        [*goal[:4], "子月"],
    ):
        assert not direct_recovery_arrival(changed, "结城理", actual, {}, None)


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("verdict, expected", [("银灰", 1), (None, 1), ("陈", 3)])
def test_first_arrival_reads_back_once_before_deciding_to_repair(
    solver, monkeypatch, enabled, verdict, expected
):
    monkeypatch.setattr(config.conf, "test_mood_calculation", enabled)
    solver.physical = ["杜林", "琴柳", "红", "", ""]
    solver.op_data.operators["红"].mood = 24
    solver.get_agent_from_room()
    if enabled:
        for op in solver.op_data.operators.values():
            solver.op_data.mood_model.observe(op.name, op.mood)
    confirm = solver.tap_confirm.side_effect

    def game(room, plan):
        confirm(room, plan)
        if len(solver.confirms) == 1:
            solver.game_recipient = verdict

    solver.tap_confirm.side_effect = game
    solver.get_agent_from_room.reset_mock()
    arrange(solver)
    assert solver.get_agent_from_room.call_count == 1 + expected
    assert solver.get_agent_from_room.call_args_list[1].kwargs["record_dorm_evidence"]
    assert len(solver.confirms) == expected
    assert solver.confirms[0] == solver.confirms[-1] == FINAL
    assert bool(solver.op_data.operators["银灰"].dorm_recovery_room) == (
        verdict is not None
    )
    assert not solver.task.plan


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("roommate_stays", [False, True])
def test_arrivals_replacing_one_unfinished_resident(
    solver, monkeypatch, enabled, roommate_stays
):
    monkeypatch.setattr(config.conf, "test_mood_calculation", enabled)
    solver.op_data.operators["红"].mood = 24
    solver.op_data.operators["黑角"].mood = 9
    solver.physical = ["杜林", "琴柳", "红", "黑角", "陈" if roommate_stays else ""]
    solver.game_recipient = "陈" if roommate_stays else "黑角"
    solver.get_agent_from_room()
    if enabled:
        for op in solver.op_data.operators.values():
            solver.op_data.mood_model.observe(op.name, op.mood)
    solver.get_agent_from_room.reset_mock()
    arrange(solver)
    expected = [FINAL] if not roommate_stays else [FINAL[:-1] + [""], FINAL]
    assert solver.confirms == expected
    assert solver.get_agent_from_room.call_count == 1 + len(expected)
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM
    assert not solver.task.plan


@pytest.mark.parametrize(
    "unreadable",
    [{"measured_mood": None}, {"measured_mood": 24}, {"recovery_seconds": None}],
)
def test_two_new_arrivals_need_a_measurable_departing_resident(unreadable):
    from arknights_mower.utils.dorm_recovery import direct_recovery_arrival

    actual = rows(
        [(310, None), (310, None), (259, 4732), (0, None), (0, None)],
        ("隐德来希", "蜜莓", "行铃", "", ""),
    )
    goal = ["隐德来希", "蜜莓", "结城理", "八幡海铃", ""]
    assert direct_recovery_arrival(goal, "结城理", actual, {}, None)
    actual[2].update(unreadable)
    assert not direct_recovery_arrival(goal, "结城理", actual, {}, None)


def test_unsampled_departure_still_gets_a_room_read_before_correction(solver):
    solver.physical = ["杜林", "琴柳", "红", "", ""]
    solver.op_data.operators["红"].mood = 24
    solver.get_agent_from_room()
    observe = solver.get_agent_from_room.side_effect
    confirm = solver.tap_confirm.side_effect

    def game(room, plan):
        confirm(room, plan)
        if len(solver.confirms) == 1:
            solver.game_recipient = "陈"

    def read(room, *args, **kwargs):
        result = observe(room, *args, **kwargs)
        if len(solver.confirms) == 1 and not kwargs.get("departing_plan"):
            result[-1].pop("mood_sampled")
        return result

    solver.tap_confirm.side_effect = game
    solver.get_agent_from_room.side_effect = read
    solver.get_agent_from_room.reset_mock()
    arrange(solver)
    assert len(solver.confirms) == 3
    assert solver.get_agent_from_room.call_count == 5
    assert solver.get_agent_from_room.call_args_list[2].kwargs[
        "departing_plan"
    ] == FINAL[:-1] + [""]
    assert not solver.task.plan


def test_failed_order_survives_restart_and_retries_only_on_room_change(solver):
    solver.physical = FINAL.copy()
    solver.game_recipient = "陈"
    solver.get_agent_from_room()
    confirm = solver.tap_confirm.side_effect

    def still_wrong(room, plan):
        confirm(room, plan)
        if solver.physical == FINAL:
            solver.game_recipient = "陈"

    solver.tap_confirm.side_effect = still_wrong
    scheduled = solver.task.time
    arrange(solver)
    assert len(solver.confirms) == 2
    assert not solver.op_data.operators["银灰"].dorm_recovery_room
    solver.op_data = pickle.loads(pickle.dumps(solver.op_data))
    for _ in range(3):
        arrange(solver, FINAL)
    assert len(solver.confirms) == 2 and solver.task.time == scheduled
    source = solver.op_data.operators["琴柳"]
    source.current_room = "dormitory_2"
    source.current_room = ROOM
    solver.tap_confirm.side_effect = confirm
    arrange(solver, FINAL)
    assert len(solver.confirms) == 4 and solver.task.time == scheduled
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM


def test_disconnect_after_direct_confirmation_reads_who_received_bonus(solver):
    solver.physical = ["杜林", "琴柳", "红", "", ""]
    solver.op_data.operators["红"].mood = 24
    solver.get_agent_from_room()
    confirm = solver.tap_confirm.side_effect

    def confirmed_before_disconnect(room, previous):
        confirm(room, previous)
        if len(solver.confirms) == 1:
            solver.game_recipient = "陈"
            raise RuntimeError("确认已送达，结果画面丢失")

    solver.tap_confirm.side_effect = confirmed_before_disconnect
    solver.get_agent_from_room.reset_mock()
    arrange(solver)
    assert solver.enter_room.call_count == 2
    assert solver.get_agent_from_room.call_count == 4
    assert solver.confirms == [FINAL, ["杜林", "琴柳", "红", "银灰", ""], FINAL]
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM
    assert not solver.task.plan


def test_unchanged_wrong_recipient_without_padding_does_not_reopen_selection(solver):
    solver.physical = FINAL.copy()
    solver.game_recipient = "红"
    solver.op_data.operators["黑角"].mood = 1
    solver.get_agent_from_room()
    for _ in range(3):
        arrange(solver, FINAL)
    solver.choose_agent.assert_called_once()
    assert not solver.confirms
    assert not solver.task.plan


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("verdict,count", [("银灰", 1), (None, 1), ("陈", 3)])
def test_two_measured_residents_swap_then_read_final_room(
    solver, monkeypatch, enabled, verdict, count
):
    monkeypatch.setattr(config.conf, "test_mood_calculation", enabled)
    solver.op_data.operators["红"].mood = 24
    solver.game_recipient = "陈"
    solver.get_agent_from_room()
    if enabled:
        for op in solver.op_data.operators.values():
            solver.op_data.mood_model.observe(op.name, op.mood)
    confirm = solver.tap_confirm.side_effect

    def deliver(room, plan):
        confirm(room, plan)
        if len(solver.confirms) == 1:
            solver.game_recipient = verdict

    solver.tap_confirm.side_effect = deliver
    arrange(solver)
    assert solver.confirms[0] == solver.confirms[-1] == FINAL
    assert len(solver.confirms) == count
    assert not solver.task.plan and not getattr(
        solver.task, "dorm_recovery_restore", []
    )
    assert bool(solver.op_data.operators["银灰"].dorm_recovery_room) == (
        verdict is not None
    )


def test_third_unfinished_resident_excludes_measured_swap(solver):
    solver.game_recipient = "陈"
    solver.get_agent_from_room()
    arrange(solver)
    assert len(solver.confirms) == 2 and solver.confirms[0] != FINAL
    assert solver.physical == FINAL


def test_empty_source_bar_does_not_hide_two_comparable_roommates():
    actual = rows(
        [(310, None), (171, 13115), (216, 11360), (0, 37560), (0, None)],
        ("隐德来希", "结城理", "星源", "Lancet-2", ""),
    )
    assert observed_recovery_recipient(actual, {"Lancet-2": (0, 30)}) == "结城理"


@pytest.mark.parametrize("seconds", [20, 1])
def test_full_width_with_running_countdown_is_still_an_unfinished_source(seconds):
    actual = rows(
        [(310, None), (310, seconds), (235, 7273), (286, 2929), (0, None)],
        ("隐德来希", "安赛尔", "结城理", "星源", ""),
    )
    assert observed_recovery_recipient(actual, {"安赛尔": (0, 1)}) == "结城理"
    actual[3] = {"agent": ""}
    assert observed_recovery_recipient(actual, {"安赛尔": (0, 1)}) is None


@pytest.mark.parametrize(
    "pixels,seconds", [(0, 28709), (309, 107), (309, 76), (309, 31)]
)
def test_edge_bar_alone_cannot_establish_a_measured_recipient(pixels, seconds):
    actual = rows(
        [(310, None), (310, None), (pixels, seconds), (0, None), (0, None)],
        ("隐德来希", "波登可", "星源", "", ""),
    )
    assert observed_recovery_recipient(actual, {"波登可": (1, 1)}) is None


@pytest.mark.parametrize("intermediate", [False, True])
def test_restart_after_delivery_with_stale_room_cache(solver, intermediate):
    from arknights_mower.solvers.base_schedule import MowerExit

    if not intermediate:
        solver.op_data.operators["红"].mood = 24
        solver.game_recipient = "陈"
    solver.get_agent_from_room()
    before = pickle.dumps(solver.op_data)
    planned = solver.task.plan[ROOM].copy()
    scheduled = solver.task.time
    deliver = solver.tap_confirm.side_effect

    def disconnect(room, plan):
        deliver(room, plan)
        raise MowerExit

    solver.tap_confirm.side_effect = disconnect
    with pytest.raises(MowerExit):
        arrange(solver)
    assert (solver.physical != planned) == intermediate
    assert solver.task.plan == {ROOM: planned}
    solver.task = pickle.loads(pickle.dumps(solver.task))
    solver.tasks = [solver.task]
    solver.op_data = pickle.loads(before)
    solver.tap_confirm.side_effect = deliver
    solver.get_agent_from_room.reset_mock()
    arrange(solver)
    assert solver.get_agent_from_room.called
    assert len(solver.confirms) == (2 if intermediate else 1)
    assert solver.physical == planned and not solver.task.plan
    assert solver.task.time == scheduled


@pytest.fixture
def dorm_dispatch(scheduler, monkeypatch):
    dispatch = scheduler.solver
    monkeypatch.delattr(dispatch, "initialize_operators")
    dorm_recovery_tests.prepare_dorm_solver(dispatch, monkeypatch)
    dispatch.game_recipient = "陈"
    dispatch.get_agent_from_room()
    dispatch._fill_empty_dorms = Mock()
    dispatch.plan_metadata = Mock()
    dispatch.仓库扫描 = Mock()
    now = scheduler.clock.now()
    original = dispatch.task
    original.time = now - timedelta(seconds=1)
    scan = SchedulerTask(now, task_type=TaskTypes.DEPOT)
    dispatch.tasks.append(scan)
    return dispatch, original, scan


def test_failed_correction_dispatches_independent_due_task(scheduler, dorm_dispatch):
    dispatch, original, scan = dorm_dispatch
    scheduled = original.time
    deliver = dispatch.tap_confirm.side_effect

    def wrong_after_restoration(room, plan):
        deliver(room, plan)
        if dispatch.physical == FINAL:
            dispatch.game_recipient = "陈"

    dispatch.tap_confirm.side_effect = wrong_after_restoration
    dispatch.run()
    assert dispatch.confirms == [["杜林", "琴柳", "黑角", "银灰", ""], FINAL]
    assert not original.plan and not original.dorm_recovery_restore
    assert original.time == scheduled
    target = dispatch.op_data.operators["银灰"]
    assert target.dorm_recovery_attempt and not target.dorm_recovery_room
    assert scan in dispatch.tasks
    dispatch.run()
    dispatch.仓库扫描.assert_called_once_with()
    assert scan not in dispatch.tasks and len(dispatch.confirms) == 2
    scheduler.io.assert_not_called()


def test_restart_after_failed_final_correction_does_not_clear_again(solver):
    from arknights_mower.solvers.base_schedule import MowerExit

    solver.game_recipient = "陈"
    solver.get_agent_from_room()
    before = pickle.dumps(solver.op_data)
    deliver = solver.tap_confirm.side_effect

    def disconnect_on_final(room, plan):
        deliver(room, plan)
        if solver.physical == FINAL:
            solver.game_recipient = "陈"
            raise MowerExit

    solver.tap_confirm.side_effect = disconnect_on_final
    with pytest.raises(MowerExit):
        arrange(solver)
    assert len(solver.confirms) == 2 and solver.task.dorm_recovery_restore == [ROOM]
    solver.task = pickle.loads(pickle.dumps(solver.task))
    solver.tasks = [solver.task]
    solver.op_data = pickle.loads(before)
    solver.get_agent_from_room.reset_mock()
    solver.tap_confirm.side_effect = deliver
    arrange(solver)
    assert solver.get_agent_from_room.called and len(solver.confirms) == 2
    assert not solver.task.plan and not solver.task.dorm_recovery_restore
    assert not solver.op_data.operators["银灰"].dorm_recovery_room
    arrange(solver, FINAL)
    assert len(solver.confirms) == 2


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("target_full", [False, True])
def test_correct_room_after_complete_operator_cache_loss(
    solver, monkeypatch, enabled, target_full
):
    solver.physical = FINAL.copy()
    if target_full:
        solver.op_data.operators["银灰"].mood = 24
    solver.game_recipient = "陈" if target_full else "银灰"
    samples = solver.get_agent_from_room()
    measured_at = solver.op_data.operators["银灰"].time_stamp
    monkeypatch.setattr(config.conf, "test_mood_calculation", enabled)
    assert solver.initialize_operators() is None
    solver.op_data.add(Operator("陈", ""))
    assert not any(solver.op_data.get_current_room(ROOM, True))
    assert all(op.time_stamp is None for op in solver.op_data.operators.values())
    observe = solver.get_agent_from_room.side_effect

    def read(room, *args, **kwargs):
        for sample in samples:
            op = solver.op_data.operators[sample["agent"]]
            op.mood = sample["measured_mood"]
            op.time_stamp = measured_at
            if enabled:
                solver.op_data.mood_model.observe(op.name, op.mood, measured_at)
        return observe(room, *args, **kwargs)

    solver.get_agent_from_room.side_effect = read
    arrange(solver)
    assert not solver.task.plan
    solver.enter_room.assert_called_once_with(ROOM)
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    assert solver.op_data.operators["银灰"].dorm_recovery_room == (
        "" if target_full else ROOM
    )


def test_interrupted_dorm_restoration_yields_until_new_room_observation(
    scheduler, dorm_dispatch
):
    dispatch, original, scan = dorm_dispatch
    scheduled = original.time
    observe = dispatch.get_agent_from_room.side_effect
    unreadable = True

    def read(room, *args, **kwargs):
        if dispatch.confirms and unreadable:
            raise RuntimeError("宿舍驻员无法读取")
        actual = observe(room, *args, **kwargs)
        dispatch._reconcile_room_observation(room, actual)
        return actual

    dispatch.get_agent_from_room.side_effect = read
    dispatch.run()
    assert len(dispatch.confirms) == 1 and dispatch.physical != FINAL
    assert original.execution_failure and original.dorm_recovery_restore == [ROOM]
    assert original.plan == {ROOM: FINAL} and original.time == scheduled
    assert any(t is original for t in dispatch.tasks)
    dispatch.run()
    dispatch.仓库扫描.assert_called_once_with()
    assert scan not in dispatch.tasks and len(dispatch.confirms) == 1
    assert original.execution_failure and original.time == scheduled

    unreadable = False
    dispatch.get_agent_from_room(ROOM)
    dispatch.run()
    assert dispatch.confirms == [["杜林", "琴柳", "黑角", "银灰", ""], FINAL]
    assert not original.plan and not original.dorm_recovery_restore
    assert all(t is not original for t in dispatch.tasks) and original.time == scheduled
    scheduler.io.assert_not_called()


def _bed_card(solver, top, name=None, *, show_button=True):
    from pathlib import Path

    import numpy as np
    from PIL import Image

    path = Path(__file__).parent / "fixtures/selection/b304_bed_yuki_20261125.png"
    gray = np.zeros((1080, 1920), dtype=np.uint8)
    with Image.open(path) as image:
        gray[top : top + 135, 1460:1862] = np.asarray(image)
    if not show_button:
        gray[top : top + 135, 1804:1862] = 49
    solver.recog.gray = gray
    if name is not None:
        solver.read_operator_in_room = Mock(return_value=name)
    solver.scroll_room_operators = Mock(return_value=top != 762)
    solver.find = Mock(
        side_effect=lambda item, **kw: item in ("room_detail", "confirm_blue") or None
    )
    solver.tap = Mock()
    del solver._remove_trailing_dorm_recipient


@pytest.mark.parametrize("index,top", [(3, 532), (3, 762), (4, 741)])
@pytest.mark.parametrize("show_button", [True, False])
def test_bedside_button_requires_the_named_visible_card(
    solver, index, top, show_button
):
    from arknights_mower.utils.recognize import RecognizeError

    _bed_card(solver, top, show_button=show_button)
    retained = ["隐德来希", "蜜莓", "国度", "八幡海铃"][0 : index - 1] + ["八幡海铃"]
    actual = [dict(agent=n, measured_mood=24) for n in retained[:-1]]
    actual += [
        dict(agent=retained[-1], measured_mood=19),
        dict(agent="结城理", mood_sampled=True),
    ]
    actual += [{"agent": ""}] * (4 - index)
    assert (
        solver._remove_trailing_dorm_recipient(
            ROOM, actual, retained, retained[-1], "结城理"
        )
        is show_button
    )
    if show_button:
        ((x, y),) = solver.tap.call_args.args
        assert x == 1833 and abs(y - top - 98) <= 1
    else:
        solver.tap.assert_not_called()
    solver.tap.reset_mock()
    actual[index]["agent"] = "行铃"
    with pytest.raises(RecognizeError, match="住客已变化"):
        solver._remove_trailing_dorm_recipient(
            ROOM, actual, retained, retained[-1], "行铃"
        )
    solver.tap.assert_not_called()


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("outcome", ["delivered", "missed", "disconnected"])
def test_bedside_correction_from_original_task(solver, monkeypatch, enabled, outcome):
    from arknights_mower.solvers.base_schedule import MowerExit

    monkeypatch.setattr(config.conf, "test_mood_calculation", enabled)
    solver.op_data.operators["红"].mood = 24
    solver.game_recipient = "陈"
    solver.physical = FINAL.copy()
    solver.get_agent_from_room()
    if enabled:
        for op in solver.op_data.operators.values():
            solver.op_data.mood_model.observe(op.name, op.mood)
    _bed_card(solver, 741, "陈")
    scheduled = solver.task.time
    old_data = pickle.dumps(solver.op_data)

    def remove(point):
        assert point == (1833, 839)
        assert solver.task.plan == {
            ROOM: FINAL
        } and solver.task.dorm_recovery_restore == [ROOM]
        if outcome != "missed":
            solver.physical[-1] = ""
            solver.game_recipient = "银灰"
        if outcome == "disconnected":
            raise MowerExit

    solver.tap.side_effect = remove
    if outcome == "disconnected":
        with pytest.raises(MowerExit):
            arrange(solver)
        assert solver.physical == FINAL[:-1] + [""] and not solver.confirms
        solver.task = pickle.loads(pickle.dumps(solver.task))
        solver.tasks = [solver.task]
        solver.op_data = pickle.loads(old_data)
        solver.get_agent_from_room.reset_mock()
    arrange(solver)
    assert solver.get_agent_from_room.called
    assert (
        solver.physical == FINAL
        and not solver.task.plan
        and not solver.task.dorm_recovery_restore
    )
    assert solver.confirms == ([] if outcome == "missed" else [FINAL])
    solver.tap.assert_called_once()
    assert solver.task.time == scheduled
    if outcome == "missed":
        for _ in range(2):
            arrange(solver, FINAL)
        solver.tap.assert_called_once()
        assert not solver.confirms
        source = solver.op_data.operators["琴柳"]
        source.current_room = "dormitory_2"
        source.current_room = ROOM
        arrange(solver, FINAL)
        assert solver.tap.call_count == 2


@pytest.mark.parametrize(
    "change",
    [
        "unsampled",
        "another_unfinished",
        "running_full_bar",
        "retained",
        "different_roster",
        "extra_bed",
    ],
)
def test_ambiguous_departure_never_uses_bedside_button(solver, change):
    retained = ["隐德来希", "蜜莓", "八幡海铃"]
    actual = rows(
        [(310, None), (310, None), (275, 4000), (264, 4300), (0, None)],
        (*retained, "结城理", ""),
    )
    actual[3]["mood_sampled"] = change != "unsampled"
    if change == "another_unfinished":
        actual[0]["measured_mood"] = 10
    if change == "running_full_bar":
        actual[1]["recovery_seconds"] = 20
    if change == "retained":
        solver.op_data.config.free_room_exclusions = ["结城理"]
    if change == "different_roster":
        retained[0] = "国度"
    if change == "extra_bed":
        actual[4]["agent"] = "絮雨"
    del solver._remove_trailing_dorm_recipient
    assert not solver._remove_trailing_dorm_recipient(
        ROOM, actual, retained, "八幡海铃", "结城理"
    )
    solver.recog.update.assert_not_called()


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("winner,keep", [("银灰", True), ("陈", False), (None, False)])
def test_release_keeps_the_intended_recipient_in_an_equivalent_free_bed(
    solver, monkeypatch, enabled, winner, keep
):
    from arknights_mower.tests.dorm_recovery_tests import room_readings
    from arknights_mower.utils.dorm_recovery import active_recovery_position
    from arknights_mower.utils.scheduler_task import prioritize_new_dorm_recovery

    monkeypatch.setattr(config.conf, "test_mood_calculation", enabled)
    solver.op_data.operators["红"].mood = 24
    after = [*FINAL[:3], "陈", "银灰"]
    before = [*FINAL[:3], "黑角", "银灰"]

    def observe(roster):
        solver.physical = roster.copy()
        solver.get_agent_from_room()
        for bed in solver.op_data.dorm:
            if bed.position[0] == ROOM:
                bed.name = roster[bed.position[1]]
        if enabled:
            for op in solver.op_data.operators.values():
                solver.op_data.mood_model.observe(op.name, op.mood)

    observe(before)
    solver.task = SchedulerTask(
        task_plan={ROOM: ["Current"] * 3 + ["陈", "Current"]},
        task_type=TaskTypes.RELEASE_DORM,
        meta_data="黑角",
    )
    solver.tasks = [solver.task]
    solver.prepare_release_dorm = Mock(return_value=True)
    solver._dorm_recovery_reservations = Mock(return_value=(set(), set(), set(), set()))

    def deliver(plan, get_time):
        observe(after)
        # 对照为相同实际床位、相同身份及相同名单，只有游戏给出的倒计时不同。
        raw = room_readings(solver.op_data.operators, after, winner)
        assert prioritize_new_dorm_recovery(
            solver.op_data, {}, previous_arrangements={ROOM: before}
        ) == {ROOM: ["Current"] * 3 + ["银灰", "陈"]}
        solver._complete_room_arrangement({}, ROOM, plan, observed=raw)
        return True

    solver.agent_arrange = Mock(side_effect=deliver)
    solver.arrange_release_dorm()
    reorders = [t for t in solver.tasks if t.type == TaskTypes.RE_ORDER]
    assert len(reorders) == int(not keep)
    op = solver.op_data.operators["银灰"]
    assert active_recovery_position(solver.op_data, op) == ((ROOM, 4) if keep else None)
    assert solver.op_data.get_current_room(ROOM, True) == after and not solver.task.plan
    assert not hasattr(solver, "_release_dorm_readings")
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize(
    "case",
    [
        "explicit_order",
        "fixed_bed",
        "move_another_roommate",
        "stale_roster",
        "missing_mood",
        "incomplete_slot",
    ],
)
def test_measured_swap_preserves_room_constraints(solver, case):
    from arknights_mower.utils.dorm_recovery import keep_measured_dorm_swap
    from arknights_mower.utils.plan import Room

    solver.op_data.operators["红"].mood = 24
    solver.game_recipient = "银灰"
    actual = solver.get_agent_from_room()
    proposed = ["Current"] * 3 + ["银灰", "陈"]
    if case == "explicit_order":
        solver.op_data.config.dorm_order.append(ROOM + "_low")
    if case == "fixed_bed":
        solver.op_data.plan[ROOM][4] = Room("陈", "", [])
    if case == "move_another_roommate":
        proposed[2] = "黑角"
    if case == "stale_roster":
        solver.op_data.operators["陈"].current_room = "meeting"
    if case == "missing_mood":
        actual[0].pop("measured_mood")
    if case == "incomplete_slot":
        actual[-1]["observed"] = False
    assert not keep_measured_dorm_swap(solver.op_data, ROOM, proposed, actual)
    assert not solver.op_data.operators["银灰"].dorm_recovery_room


@pytest.mark.parametrize(
    "first,second,last",
    [((283, 3273), (232, 7617), ""), ((284, 3088), (234, 7432), "安比尔")],
)
def test_indigo_ordinary_target_from_room_screenshots(first, second, last):
    actual = rows(
        [(310, None), first, second, (310, None), (310, None)],
        ("隐德来希", "星源", "结城理", "深靛", last),
    )
    assert observed_recovery_recipient(actual, {}) == "结城理"


@pytest.mark.parametrize(
    "blue,other,who",
    [
        ((304, 470), (277, 3910), None),
        ((305, 621), (278, 3119), None),
        ((155, 13091), (155, 18783), "蓝毒"),
        ((155, 18783), (155, 15158), "结城理"),
        ((155, 15158), (155, 18783), None),
    ],
)
def test_indigo_extra_only_applies_when_blue_poison_is_the_recipient(blue, other, who):
    from arknights_mower.utils.dorm_recovery import direct_recovery_arrival

    names = ["隐德来希", "深靛", "蓝毒", "结城理", ""]
    actual = rows([(310, None), (310, None), blue, other, (0, None)], names)
    assert observed_recovery_recipient(actual, {}) == who
    assert not direct_recovery_arrival(names, "蓝毒", actual, {}, who)


@pytest.mark.parametrize(
    "provider, ordinary, self_sample, recipient",
    [
        ("蜜莓", ((284, 2406), (264, 5562)), (309, 60), "结城理"),
        ("絮雨", ((284, 3113), (264, 5542)), (309, 40), None),
        ("蜜莓", ((284, 3093), (264, 4232)), (309, 20), "行铃"),
    ],
)
def test_two_ordinary_roommates_distinguish_bonus_with_lunacub_present(
    provider, ordinary, self_sample, recipient
):
    actual = rows(
        [(310, None), (310, None), *ordinary, self_sample],
        ("隐德来希", provider, "结城理", "行铃", "子月"),
    )
    assert observed_recovery_recipient(actual, {"蜜莓": (2, 1)}) == recipient
    # 自回住客也能接受外来单回，不能用她的速度代替第二个普通人的读数。
    actual[3] = {"agent": ""}
    assert observed_recovery_recipient(actual, {"蜜莓": (2, 1)}) is None


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("outcome", ["delivered", "wrong", "missed", "interrupted"])
@pytest.mark.parametrize("last_bed", ["", "红"])
def test_one_confirmation_replaces_neighbor_and_restores_recipient(
    solver, monkeypatch, enabled, outcome, last_bed
):
    from datetime import datetime

    from arknights_mower.solvers.base_schedule import MowerExit
    from arknights_mower.utils.plan import Room

    monkeypatch.setattr(config.conf, "test_mood_calculation", enabled)
    fixed = ["隐德来希", "琴柳"]
    solver.op_data.plan[ROOM][0] = Room(fixed[0], "", [])
    solver.op_data.plan[ROOM][2] = Room("Free", "", [])
    solver.op_data.add(
        Operator(fixed[0], ROOM, index=0, mood=24, time_stamp=datetime.now())
    )
    solver.physical = fixed + ["黑角", "陈", ""]
    solver.op_data.operators["黑角"].mood = 12
    solver.game_recipient = "陈"
    final = fixed + ["银灰", "陈", last_bed]
    solver.task.plan = {ROOM: final.copy()}
    if not last_bed:
        solver.task.backup_retention_empty_slots = {(ROOM, 4): "红"}
    solver.get_agent_from_room()
    if enabled:
        for op in solver.op_data.operators.values():
            solver.op_data.mood_model.observe(op.name, op.mood)
    _bed_card(solver, 532, "陈")
    start = solver.task.time
    cached = pickle.dumps(solver.op_data)
    confirm = solver.tap_confirm.side_effect

    def remove(point):
        assert point == (1833, 630)
        assert solver.task.plan == {
            ROOM: final
        } and solver.task.dorm_recovery_restore == [ROOM]
        if outcome != "missed":
            solver.physical[3] = ""
            solver.game_recipient = "黑角"
        if outcome == "interrupted":
            raise MowerExit

    def deliver(room, plan):
        confirm(room, plan)
        solver.game_recipient = "陈" if outcome in ("wrong", "missed") else "银灰"

    solver.tap.side_effect = remove
    solver.tap_confirm.side_effect = deliver
    if outcome == "interrupted":
        with pytest.raises(MowerExit):
            arrange(solver)
        solver.task = pickle.loads(pickle.dumps(solver.task))
        solver.tasks = [solver.task]
        solver.op_data = pickle.loads(cached)
        solver.get_agent_from_room.reset_mock()
    arrange(solver)
    assert solver.physical == final and solver.confirms == [final]
    assert not solver.task.plan and not solver.task.dorm_recovery_restore
    assert solver.task.time == start
    if outcome in ("wrong", "missed"):
        arrange(solver, final)
        assert not solver.op_data.operators["银灰"].dorm_recovery_room
    else:
        assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM
    solver.tap.assert_called_once()
    assert solver.confirms == [final]


@pytest.mark.parametrize(
    "change",
    ["source", "self", "shared", "targeted", "charger", "missing_sample", "fifth"],
)
def test_replacing_beside_recipient_rejects_other_rosters(change):
    from arknights_mower.utils.dorm_recovery import fourth_bed_removals

    names = ["隐德来希", "蜜莓", "虎狼丸", "行铃", ""]
    target = "结城理"
    if change in {"self", "shared", "targeted", "charger"}:
        names[0] = {
            "self": "子月",
            "shared": "冰酿",
            "targeted": "深靛",
            "charger": "菲亚梅塔",
        }[change]
    if change == "source":
        target = "安赛尔"
    if change == "fifth":
        names[4] = "能天使"
    actual = rows(
        [(310, None), (310, None), (149, 19434), (265, 4186), (0, None)], names
    )
    actual[2]["mood_sampled"] = change != "missing_sample"
    goal = [*names[:2], target, *names[3:]]
    assert not fourth_bed_removals(goal, target, actual, None, {})
    assert not fourth_bed_removals(goal, target, actual, "行铃", {})


@pytest.mark.parametrize(
    "last",
    [
        "结城理",
        "行铃",
        "虎狼丸",
        "安赛尔",
        "子月",
        "冰酿",
        "深靛",
        "菲亚梅塔",
        "Current",
        "Free",
    ],
)
def test_two_new_roommates_require_a_distinct_ordinary_last_arrival(last):
    from arknights_mower.utils.dorm_recovery import fourth_bed_removals

    names = ["隐德来希", "蜜莓", "虎狼丸", "行铃", ""]
    observed = rows(
        [(310, None), (310, None), (161, 18002), (284, 2361), (26, None)], names
    )
    observed[2]["mood_sampled"] = observed[3]["mood_sampled"] = True
    assert not fourth_bed_removals(
        [*names[:2], "结城理", "行铃", last], "结城理", observed, "行铃", {}
    )


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("measurable", [True, False])
def test_middle_bed_correction_uses_measured_mood_and_keeps_the_fifth_slot(
    solver, monkeypatch, enabled, measurable
):
    from datetime import datetime

    from arknights_mower.utils.plan import Room

    monkeypatch.setattr(config.conf, "test_mood_calculation", enabled)
    fixed = ["隐德来希", "琴柳"]
    final = fixed + ["银灰", "陈", "黑角"]
    solver.op_data.plan[ROOM][0] = Room(fixed[0], "", [])
    solver.op_data.plan[ROOM][2] = Room("Free", "", [])
    solver.op_data.add(
        Operator(fixed[0], ROOM, index=0, mood=24, time_stamp=datetime.now())
    )
    solver.op_data.operators["黑角"].mood = 22 if measurable else 23.95
    solver.op_data.operators["银灰"].mood = 20
    solver.game_recipient = "陈"
    solver.physical = final.copy()
    solver.get_agent_from_room()
    if enabled:
        for op in solver.op_data.operators.values():
            solver.op_data.mood_model.observe(op.name, op.mood)
    _bed_card(solver, 532, "陈")

    def remove(point):
        assert solver.task.plan == {
            ROOM: final
        } and solver.task.dorm_recovery_restore == [ROOM]
        assert solver.physical == final and point == (1833, 630)
        solver.physical[3] = ""
        solver.game_recipient = "银灰"

    solver.tap.side_effect = remove
    arrange(solver, final)
    assert solver.physical == final and not solver.task.plan
    assert solver.confirms == ([final] if measurable else [final[:3] + ["", ""], final])
    if measurable:
        solver.tap.assert_called_once()
        assert any(
            c.kwargs.get("expected_agents") == [*final[:3], "", "黑角"]
            for c in solver.get_agent_from_room.call_args_list
        )
    else:
        solver.tap.assert_not_called()
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM


@pytest.mark.parametrize(
    "third,fifth,beds",
    [
        (291, 296, (3,)),
        (291, 295, (4, 3)),
        (289, 293, (4, 3)),
        (291, 294, (4, 3)),
        (290, 290, (4, 3)),
        (295, 292, (4, 3)),
        (295, 291, (4, 3)),
        (296, 291, (4, 3)),
    ],
)
def test_bedside_removal_compares_original_pixel_widths(third, fifth, beds):
    from arknights_mower.utils.dorm_recovery import fourth_bed_removals

    names = ["隐德来希", "蜜莓", "行铃", "虎狼丸", "能天使"]

    def ordinary_seconds(pixels):
        return round((310 - pixels) * 24 * 3600 / (310 * 2.3))

    actual = rows(
        [
            (310, None),
            (310, None),
            (third, ordinary_seconds(third)),
            (168, 13131),
            (fifth, ordinary_seconds(fifth)),
        ],
        names,
    )
    assert observed_recovery_recipient(actual, {}) == names[3]
    actual[3]["mood_sampled"] = actual[4]["mood_sampled"] = True
    assert fourth_bed_removals(names, names[2], actual, names[3], {}) == beds
    actual[4]["mood_sampled"] = False
    assert fourth_bed_removals(names, names[2], actual, names[3], {}) == (
        (3,) if beds == (3,) else ()
    )


@pytest.fixture(params=(False, True), ids=("measured", "calculated"))
def full_dorm_with_wrong_recipient(solver, monkeypatch, request):
    from datetime import datetime

    from arknights_mower.utils.plan import Room

    monkeypatch.setattr(config.conf, "test_mood_calculation", request.param)
    final = ["隐德来希", "琴柳", "银灰", "陈", "黑角"]
    solver.op_data.plan[ROOM][0] = Room(final[0], "", [])
    solver.op_data.plan[ROOM][2] = Room("Free", "", [])
    solver.op_data.add(
        Operator(final[0], ROOM, index=0, mood=24, time_stamp=datetime.now())
    )
    solver.op_data.operators["黑角"].mood = 12
    solver.op_data.operators["银灰"].mood = 19
    solver.physical = final.copy()
    solver.game_recipient = "陈"
    solver.task.plan = {ROOM: final.copy()}
    solver.get_agent_from_room()
    if request.param:
        for op in solver.op_data.operators.values():
            solver.op_data.mood_model.observe(op.name, op.mood)
    _bed_card(solver, 741)
    gray = solver.recog.gray
    gray[532:667, 1460:1862] = gray[741:876, 1460:1862].copy()
    # 标记三个姓名裁区的首像素，使读回使用点击后的实际床位。
    for index, top in ((2, 323), (3, 532), (4, 741)):
        gray[top + 25, 1460] = index
    solver.read_operator_in_room = Mock(
        side_effect=lambda crop: solver.physical[int(crop[0, 0])]
    )
    solver.find.side_effect = lambda item, **kw: (
        solver.physical[4] == ""
        if item == "infra_no_operator"
        else item in ("room_detail", "confirm_blue")
    )
    taps = []

    def remove(point):
        index = {(1833, 839): 4, (1833, 630): 3}[point]
        assert solver.task.dorm_recovery_restore == [ROOM] and solver.task.plan == {
            ROOM: final
        }
        taps.append(index)
        solver.physical[index] = ""
        if index == 3:
            solver.game_recipient = "银灰"

    solver.tap.side_effect = remove
    return solver, final, taps


@pytest.mark.parametrize(
    "outcome",
    (
        "delivered",
        "missed_first",
        "missed_second",
        "unreadable_third",
        "lost_after_first",
        "lost_after_second",
        "lost_after_confirm",
        "wrong",
    ),
)
def test_two_bedside_departures_belong_to_original_task(
    full_dorm_with_wrong_recipient, outcome
):
    from arknights_mower.solvers.base_schedule import MowerExit

    solver, final, taps = full_dorm_with_wrong_recipient
    start = solver.task.time
    cached = pickle.dumps(solver.op_data)
    remove = solver.tap.side_effect
    confirm = solver.tap_confirm.side_effect
    read_name = solver.read_operator_in_room.side_effect

    def tap(point):
        index = {(1833, 839): 4, (1833, 630): 3}[point]
        if (outcome, index) in (("missed_first", 4), ("missed_second", 3)):
            taps.append(index)
            return
        remove(point)
        if (outcome, index) in (("lost_after_first", 4), ("lost_after_second", 3)):
            raise MowerExit

    def deliver(room, plan):
        confirm(room, plan)
        if outcome == "wrong":
            solver.game_recipient = "陈"
        if outcome == "lost_after_confirm" and len(solver.confirms) == 1:
            raise MowerExit

    solver.tap.side_effect = tap
    solver.tap_confirm.side_effect = deliver
    if outcome == "unreadable_third":
        solver.read_operator_in_room.side_effect = lambda crop: (
            "" if int(crop[0, 0]) == 2 else read_name(crop)
        )
    if outcome.startswith("lost_"):
        with pytest.raises(MowerExit):
            arrange(solver)
        solver.task = pickle.loads(pickle.dumps(solver.task))
        solver.tasks = [solver.task]
        solver.op_data = pickle.loads(cached)
        solver.get_agent_from_room.reset_mock()
    arrange(solver)
    assert solver.get_agent_from_room.called and solver.task.time == start
    assert (
        solver.physical == final
        and not solver.task.plan
        and not solver.task.dorm_recovery_restore
    )
    assert taps == (
        [4]
        if outcome in ("missed_first", "lost_after_first", "unreadable_third")
        else [4, 3]
    )
    assert solver.confirms == ([] if outcome == "missed_first" else [final])
    if solver.game_recipient == "陈":
        previous = taps.copy(), solver.confirms.copy()
        for _ in range(2):
            arrange(solver, final)
        assert (taps, solver.confirms) == previous
        assert not solver.op_data.operators["银灰"].dorm_recovery_room
    else:
        assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM


@pytest.mark.parametrize(
    "reservation", ("fourth", "fifth", "slot", "excluded", "waiting")
)
def test_reserved_roommate_stays_until_released(
    full_dorm_with_wrong_recipient, reservation
):
    solver, final, taps = full_dorm_with_wrong_recipient
    if reservation == "excluded":
        solver.op_data.config.free_room_exclusions.append("黑角")
    else:
        plan = (
            {ROOM: ["Current"] * 4 + ["Free"]}
            if reservation == "slot"
            else {"meeting": ["陈" if reservation == "fourth" else "黑角"]}
        )
        reserved = SchedulerTask(task_plan=plan, task_type=TaskTypes.SELF_CORRECTION)
        if reservation == "waiting":
            solver.waiting_group_shifts = [reserved]
        else:
            solver.tasks.append(reserved)
    for _ in range(2):
        arrange(solver, final)
        assert solver.physical == final and not solver.task.plan
        assert not taps and not solver.confirms
    solver.tasks = [solver.task]
    solver.waiting_group_shifts = []
    solver.op_data.config.free_room_exclusions = []
    arrange(solver, final)
    assert taps == [4, 3] and solver.confirms == [final]


def test_unreadable_fourth_button_keeps_reserved_fifth_in_its_bed(
    full_dorm_with_wrong_recipient,
):
    solver, final, taps = full_dorm_with_wrong_recipient
    solver.op_data.operators["银灰"].mood = 8
    solver.tasks.append(
        SchedulerTask(
            task_plan={"meeting": ["黑角"]}, task_type=TaskTypes.SELF_CORRECTION
        )
    )
    gray = solver.recog.gray
    icon = gray[596:664, 1804:1862].copy()
    gray[596:664, 1804:1862] = 49
    arrange(solver)
    assert not taps and not solver.confirms and solver.physical == final
    # 对第 5 床的预约仍有效，只恢复辨认出的第 4 床按钮。
    gray[596:664, 1804:1862] = icon
    arrange(solver, final)
    assert taps == [3] and solver.confirms == [final]


@pytest.mark.parametrize("legacy", [False, True])
def test_fifth_finishes_after_failed_correction(full_dorm_with_wrong_recipient, legacy):
    solver, final, taps = full_dorm_with_wrong_recipient
    confirm = solver.tap_confirm.side_effect

    def still_wrong(room, plan):
        confirm(room, plan)
        solver.game_recipient = "陈"

    solver.tap_confirm.side_effect = still_wrong
    arrange(solver)
    assert taps == [4, 3] and solver.confirms == [final]
    target = solver.op_data.operators["银灰"]
    if legacy:
        target.dorm_recovery_attempt = target.dorm_recovery_attempt[:2]
    solver.op_data.operators["黑角"].mood = 21
    arrange(solver, final)
    assert taps == [4, 3]
    solver.op_data.operators["黑角"].mood = 24
    for _ in range(3):
        arrange(solver, final)
    assert taps == ([4, 3] if legacy else [4, 3, 3])
    assert solver.confirms == ([final] if legacy else [final, final])


@pytest.mark.parametrize(
    "case",
    [
        "overlap",
        "near_full",
        "zero",
        "no_timer",
        "unmeasured",
        "source_unfinished",
        "fifth_self",
    ],
)
def test_middle_bed_needs_two_distinct_measurable_ordinary_roommates(case):
    from arknights_mower.utils.dorm_recovery import fourth_bed_removals

    names = ["隐德来希", "蜜莓", "行铃", "能天使", "结城理"]
    if case == "fifth_self":
        names[4] = "子月"
    actual = rows(
        [(310, None), (310, None), (269, 4898), (289, 1938), (289, 2534)], names
    )
    actual[3]["mood_sampled"] = case != "unmeasured"
    if case == "overlap":
        actual[4]["measured_mood"] = 271 * 24 / 310
    if case == "near_full":
        actual[4]["measured_mood"] = 309 * 24 / 310
    if case == "zero":
        actual[2]["measured_mood"] = 0
    if case == "no_timer":
        actual[2]["recovery_seconds"] = None
    if case == "source_unfinished":
        actual[1]["recovery_seconds"] = 20
    assert not fourth_bed_removals(names, names[2], actual, names[3], {})


@pytest.mark.parametrize(
    "peers,times,expected",
    [
        (("行铃", "能天使"), ((267, 3962), (287, 2801)), "行铃"),
        (("能天使", "行铃"), ((288, 2646), (269, 3813)), "行铃"),
    ],
)
def test_cross_room_departure_before_the_original_room_is_confirmed(
    peers, times, expected
):
    names = ["隐德来希", "蜜莓", "", *peers]
    raw = rows([(310, None), (310, None), (27, None), *times], names)
    assert observed_recovery_recipient(raw, {}) == expected
    if peers[0] == "能天使":
        compact = ["隐德来希", "蜜莓", *peers, ""]
        raw = rows(
            [(310, None), (310, None), (288, 2023), (269, 4964), (27, None)], compact
        )
        assert observed_recovery_recipient(raw, {}) == "能天使"


@pytest.mark.parametrize(
    "roommates, before, after",
    [
        (
            ("图耶", "行铃", "虎狼丸"),
            ((0, 36370), (282, 2593), (159, 18301)),
            ((0, 27857), (282, 3376), (159, 18274)),
        ),
        (
            ("虎狼丸", "行铃", "图耶"),
            ((159, 18232), (282, 2532), (0, 36300)),
            ((159, 18204), (282, 3297), (0, 27803)),
        ),
    ],
)
def test_borrowed_trader_has_no_individual_rate_at_zero_pixels(
    roommates, before, after
):
    names = ("隐德来希", "蜜莓", *roommates)
    full = [(310, None), (310, None)]
    assert observed_recovery_recipient(rows(full + list(before), names), {}) == "行铃"
    assert observed_recovery_recipient(rows(full + list(after), names), {}) is None


@pytest.mark.parametrize(
    ("samples", "recipient"),
    [
        ([(309, 2), (295, 1704), (172, 16630)], None),
        ([(310, None), (295, 1702), (172, 16628)], None),
        ([(310, None), (296, 1701), (172, 12747)], "虎狼丸"),
    ],
)
def test_natural_recovery_releases_third_bed_bonus_before_the_fifth_timer_updates(
    samples, recipient
):
    names = ("隐德来希", "蜜莓", "结城理", "行铃", "虎狼丸")
    actual = rows([(310, None), (310, None), *samples], names)
    assert observed_recovery_recipient(actual, {"蜜莓": (2, 1)}) == recipient
