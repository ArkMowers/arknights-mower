"""单回排序的真实排班入口、两次确认、失败重试及休息周期回归。"""

import copy
import pickle
import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.dorm_recovery import recovery_order_plan  # noqa: E402
from arknights_mower.utils.operators import Operator  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    prioritize_new_dorm_recovery,
)

ROOM = "dormitory_1"
FINAL = ["杜林", "琴柳", "红", "银灰", "陈"]


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base_schedule, "save_exception", lambda e: None)
    config.conf.enable_mastery = False
    instance = object.__new__(BaseSchedulerSolver)
    instance.global_plan = {
        "default_plan": Plan(
            {
                "meeting": [Room("银灰", "联动", ["黑角"])],
                ROOM: [
                    Room("杜林", "", []),
                    Room("琴柳", "", []),
                    Room("桃金娘", "联动", ["红"]),
                    Room("Free", "", []),
                    Room("Free", "", []),
                ],
            },
            PlanConfig("", "", ""),
        ),
        "backup_plans": [],
    }
    assert instance.initialize_operators() is None
    instance.op_data.add(Operator("陈", ""))
    for op in instance.op_data.operators.values():
        op.mood = 5 if op.name in ("红", "银灰", "陈") else 24
        op.time_stamp = datetime.now()
    instance.task = SchedulerTask(
        task_plan={ROOM: FINAL.copy()}, task_type=TaskTypes.SELF_CORRECTION
    )
    instance.tasks = [instance.task]
    instance.recog = MagicMock()
    instance.find = MagicMock(return_value=True)
    instance.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    instance.waiting_scene = []
    instance.enter_room = MagicMock()
    instance.turn_on_room_detail = MagicMock()
    instance.back = MagicMock()
    instance.ctap = MagicMock()
    instance.confirms = []
    instance.reads = []
    instance.selected = []
    instance.physical = ["杜林", "琴柳", "红", "陈", "银灰"]

    def observe(room=ROOM, read_time_index=None):
        instance.reads.append(list(read_time_index or []))
        for op in instance.op_data.operators.values():
            if op.current_room == room and op.name not in instance.physical:
                op.current_room = ""
                op.current_index = -1
        for index, name in enumerate(instance.physical):
            if name:
                op = instance.op_data.operators[name]
                op.current_room = room
                op.current_index = index
        return [{"agent": name} for name in instance.physical]

    def choose(agents, room, fast_mode=True, **kwargs):
        instance.selected = agents.copy()

    def confirm(room, new_plan):
        instance.physical = instance.selected + [""] * (5 - len(instance.selected))
        instance.confirms.append(instance.physical.copy())

    instance.get_agent_from_room = MagicMock(side_effect=observe)
    instance.choose_agent = MagicMock(side_effect=choose)
    instance.tap_confirm = MagicMock(side_effect=confirm)
    observe()
    return instance


def arrange(solver, agents=None):
    if agents is not None:
        solver.task.plan = {ROOM: agents.copy()}
    solver.agent_arrange_room({}, ROOM, solver.task.plan)


@pytest.mark.parametrize(
    "task_type",
    [TaskTypes.SHIFT_OFF, TaskTypes.SELF_CORRECTION, TaskTypes.NOT_SPECIFIC],
)
def test_clear_competitors_confirm_then_restore_exact_slots(solver, task_type):
    solver.task.type = task_type
    original = copy.deepcopy(solver.task.plan)
    arrange(solver)
    assert solver.confirms == [["杜林", "琴柳", "黑角", "银灰", ""], FINAL]
    assert solver.physical == original[ROOM]
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM
    assert solver.op_data.operators["银灰"].dorm_recovery_index == 3
    assert solver.op_data.operators["银灰"].dorm_recovery_fixed == (
        "杜林",
        "琴柳",
        "红",
    )
    assert solver.task.plan == {}
    assert solver.task.dorm_recovery_restore == []
    assert [3, 4] in solver.reads
    assert all(
        call.kwargs.get("preserve_dorm_occupants")
        for call in solver.choose_agent.call_args_list
    )


def test_same_final_positions_still_fix_unknown_arrival_order(solver):
    solver.physical = FINAL.copy()
    solver.get_agent_from_room()
    arrange(solver)
    assert len(solver.confirms) == 2


def test_current_resolved_before_compact_confirmation(solver):
    arrange(solver, ["Current", "Current", "Current", "银灰", "陈"])
    assert solver.confirms[-1] == FINAL
    assert all("Current" not in names for names in solver.confirms)


def test_only_once_while_target_stays_in_room(solver):
    arrange(solver)
    count = len(solver.confirms)
    arrange(solver, FINAL)
    assert len(solver.confirms) == count
    # 同宿舍换位也会重新判定单回，不能继续沿用旧标记。
    target = solver.op_data.operators["银灰"]
    target.current_index = 4
    assert recovery_order_plan(solver.op_data, ROOM, FINAL) is not None


def test_backup_plan_manager_change_reconfirms_same_target(solver):
    arrange(solver)
    backup = Plan(
        {
            ROOM: [
                Room("陈", "", []),
                *[Room("Current", "", []) for _ in range(4)],
            ]
        },
        PlanConfig("", "", ""),
    )
    solver.op_data.global_plan["backup_plans"] = [backup]
    solver.op_data.backup_plans = [backup]
    assert solver.op_data.swap_plan([True], refresh=True) is None
    updated = ["陈", "琴柳", "红", "银灰", "黑角"]
    arrange(solver, updated)
    assert solver.confirms[-2:] == [
        ["陈", "琴柳", "杜林", "银灰", ""],
        updated,
    ]
    target = solver.op_data.operators["银灰"]
    assert target.dorm_recovery_room == ROOM
    assert target.dorm_recovery_fixed == ("陈", "琴柳", "红")


def test_target_leaves_then_returns_needs_new_confirmation(solver):
    arrange(solver)
    target = solver.op_data.operators["银灰"]
    target.current_room = "meeting"
    target.current_room = ROOM
    assert target.dorm_recovery_room == ""
    assert target.dorm_recovery_fixed == ()
    arrange(solver, FINAL)
    assert len(solver.confirms) == 4


def test_changing_target_clears_previous_single_recovery_recipient(solver):
    arrange(solver)
    new_plan = ["杜林", "琴柳", "红", "陈", "银灰"]
    arrange(solver, new_plan)
    assert solver.confirms[-2] == ["杜林", "琴柳", "黑角", "陈", ""]
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""
    assert solver.op_data.operators["陈"].dorm_recovery_room == ROOM


def test_higher_priority_admission_reestablishes_single_recovery_and_reads_times(
    solver,
):
    solver.op_data.config.experimental_dorm_logic = True
    arrange(solver)
    # 银灰已经获得单回；陈尚在宿舍外，计划新入住最后一个动态位。
    solver.physical[-1] = ""
    solver.get_agent_from_room(ROOM)
    solver.op_data.config.ope_resting_priority = ["陈"]
    plan = prioritize_new_dorm_recovery(
        solver.op_data, {ROOM: ["Current"] * 4 + ["陈"]}
    )
    assert plan[ROOM][3:] == ["陈", "银灰"]
    arrange(solver, plan[ROOM])
    assert solver.confirms[-2:] == [
        ["杜林", "琴柳", "黑角", "陈", ""],
        ["杜林", "琴柳", "红", "陈", "银灰"],
    ]
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""
    assert solver.op_data.operators["陈"].dorm_recovery_room == ROOM
    assert {3, 4}.issubset(solver.reads[-1])
    assert solver.op_data.operators["银灰"].current_room == ROOM


def test_full_replacement_kept_and_full_free_occupant_temporarily_removed(solver):
    solver.op_data.operators["红"].mood = 24
    solver.op_data.operators["陈"].mood = 24
    arrange(solver)
    assert solver.confirms == [["杜林", "琴柳", "红", "银灰", ""], FINAL]


def test_unknown_replacement_mood_is_not_assumed_full(solver):
    solver.op_data.operators["红"].mood = 24
    solver.op_data.operators["红"].time_stamp = None
    assert recovery_order_plan(solver.op_data, ROOM, FINAL) == [
        "杜林",
        "琴柳",
        "黑角",
        "银灰",
    ]


@pytest.mark.parametrize(
    "agents", [["杜林", "琴柳"], ["杜林", "琴柳", "红", "Free", "陈"]]
)
def test_no_concrete_vip_or_short_special_plan_does_not_clear(solver, agents):
    assert recovery_order_plan(solver.op_data, ROOM, agents) is None


def test_full_target_does_not_start_recovery_cycle(solver):
    solver.op_data.operators["银灰"].mood = 24
    assert recovery_order_plan(solver.op_data, ROOM, FINAL) is None


def test_fiammetta_charge_does_not_use_recovery_reordering(solver):
    solver.task.type = TaskTypes.FIAMMETTA
    assert not solver.ensure_dorm_recovery_order(ROOM, FINAL)
    solver.tap_confirm.assert_not_called()


def test_intermediate_confirmation_failure_keeps_restore_plan_and_no_success_marker(
    solver,
):
    solver.tap_confirm.side_effect = RuntimeError("confirmation failed")
    with pytest.raises(RuntimeError, match="confirmation failed"):
        arrange(solver)
    assert solver.task.plan == {ROOM: FINAL}
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""


def test_compact_selection_failure_retries_with_full_selection(solver):
    choose = solver.choose_agent.side_effect
    modes = []

    def fail_fast_selection(agents, room, fast_mode=True, **kwargs):
        modes.append(fast_mode)
        if fast_mode:
            assert solver.task.plan == {ROOM: FINAL}
            assert solver.op_data.operators["银灰"].dorm_recovery_room == ""
            raise RuntimeError("检测到干员选择错误，重新选择")
        return choose(agents, room, fast_mode, **kwargs)

    solver.choose_agent.side_effect = fail_fast_selection
    arrange(solver)
    assert modes == [True, False, False]
    assert solver.confirms == [["杜林", "琴柳", "黑角", "银灰", ""], FINAL]
    assert solver.physical == FINAL
    assert solver.task.plan == {}
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM


def test_read_failure_keeps_restore_plan_then_retry_does_not_clear_twice(solver):
    read = solver.get_agent_from_room.side_effect
    calls = 0

    def fail_after_confirmation(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            # 已确认清房，但这次识别失败，不能提前写成功标记。
            assert solver.op_data.operators["银灰"].dorm_recovery_room == ""
            raise RuntimeError("read failed")
        return read(*args)

    solver.get_agent_from_room.side_effect = fail_after_confirmation
    arrange(solver)
    assert solver.physical == FINAL
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM
    assert solver.task.plan == {}


def test_restore_failure_retries_without_repeating_successful_clear(solver):
    confirm = solver.tap_confirm.side_effect
    calls = 0

    def fail_restore(room, new_plan):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("restore failed")
        return confirm(room, new_plan)

    solver.tap_confirm.side_effect = fail_restore
    arrange(solver)
    assert solver.confirms == [["杜林", "琴柳", "黑角", "银灰", ""], FINAL]


def test_confirmation_error_reconciles_already_arranged_room(solver):
    confirm = solver.tap_confirm.side_effect
    calls = 0

    def arrange_then_fail(room, new_plan):
        nonlocal calls
        calls += 1
        if calls == 2:
            confirm(room, new_plan)
            raise RuntimeError("post-confirm read failed")
        return confirm(room, new_plan)

    solver.tap_confirm.side_effect = arrange_then_fail
    solver.detect_room = MagicMock(return_value=ROOM)

    arrange(solver)

    assert solver.confirms == [["杜林", "琴柳", "黑角", "银灰", ""], FINAL]
    assert solver.choose_agent.call_count == 2
    assert solver.task.plan == {}


def test_shadow_rebuild_and_pickle_preserve_cycle(solver):
    arrange(solver)
    target = solver.op_data.operators["银灰"]
    restored = pickle.loads(pickle.dumps(target))
    assert restored.dorm_recovery_room == ROOM
    assert restored.dorm_recovery_index == 3
    assert restored.dorm_recovery_fixed == ("杜林", "琴柳", "红")
    solver.op_data.shadow_copy = {"银灰": restored}
    solver.op_data.add(Operator("银灰", "meeting", group="联动"))
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM
    assert solver.op_data.operators["银灰"].dorm_recovery_index == 3
    assert solver.op_data.operators["银灰"].dorm_recovery_fixed == (
        "杜林",
        "琴柳",
        "红",
    )
    assert recovery_order_plan(solver.op_data, ROOM, FINAL) is None


def test_old_operator_without_marker_is_compatible(solver):
    del solver.op_data.operators["银灰"].dorm_recovery_room
    assert recovery_order_plan(solver.op_data, ROOM, FINAL)


def test_old_marker_without_fixed_managers_reconfirms(solver):
    target = solver.op_data.operators["银灰"]
    target.dorm_recovery_room = ROOM
    target.current_room = ROOM
    del target.dorm_recovery_fixed
    assert recovery_order_plan(solver.op_data, ROOM, FINAL)


def test_mood_read_at_24_clears_marker(solver):
    target = solver.op_data.operators["银灰"]
    target.dorm_recovery_room = ROOM
    target.dorm_recovery_fixed = ("杜林", "琴柳", "红")
    solver.op_data.update_detail("银灰", 24, ROOM, 3)
    assert target.dorm_recovery_room == ""
    assert target.dorm_recovery_fixed == ()


def test_first_shift_does_not_clear_for_occupant_replaced_by_pending_bed_task(solver):
    from datetime import timedelta

    bed_task = SchedulerTask(
        time=solver.task.time + timedelta(milliseconds=2),
        task_plan={ROOM: FINAL.copy()},
        task_type=TaskTypes.SHIFT_OFF,
    )
    solver.tasks.append(bed_task)
    assert not solver.ensure_dorm_recovery_order(ROOM, solver.physical)
    solver.tap_confirm.assert_not_called()
    solver.task = bed_task
    solver.tasks = [bed_task]
    arrange(solver)
    assert len(solver.confirms) == 2


def test_same_target_and_only_full_fixed_occupants_needs_no_extra_confirmation(solver):
    solver.op_data.operators["红"].mood = 24
    solver.physical = ["杜林", "琴柳", "红", "银灰", ""]
    solver.get_agent_from_room()
    assert solver.ensure_dorm_recovery_order(ROOM, FINAL)
    solver.tap_confirm.assert_not_called()
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM


def test_readback_with_remaining_competitor_never_marks_success(solver):
    solver.tap_confirm.side_effect = lambda room, new_plan: None
    with pytest.raises(Exception, match="宿舍单回排序确认失败"):
        arrange(solver)
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""
    assert solver.task.plan == {ROOM: FINAL}


def test_target_reaches_full_during_confirmation_does_not_keep_cycle_marker(solver):
    read = solver.get_agent_from_room.side_effect

    def full_on_read(*args):
        result = read(*args)
        solver.op_data.operators["银灰"].mood = 24
        return result

    solver.get_agent_from_room.side_effect = full_on_read
    arrange(solver)
    assert solver.physical == FINAL
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""


def test_ordinary_dorm_without_group_still_clears_other_free_beds(solver):
    solver.op_data.plan[ROOM][2] = Room("桃金娘", "", [])
    solver.physical = ["杜林", "琴柳", "桃金娘", "陈", "银灰"]
    solver.get_agent_from_room()
    final = ["杜林", "琴柳", "桃金娘", "银灰", "陈"]
    arrange(solver, final)
    assert solver.confirms == [["杜林", "琴柳", "桃金娘", "银灰", ""], final]


def test_restoring_lower_mood_competitors_never_moves_single_recovery_target(solver):
    """按游戏规则模拟：原目标换位置后，会重新给当时心情最低的人。"""
    solver.op_data.operators["红"].mood = 1
    solver.op_data.operators["陈"].mood = 2
    confirm = solver.tap_confirm.side_effect
    recipient = None
    recipients = []

    def confirm_with_recovery(room, new_plan):
        nonlocal recipient
        before = solver.physical.copy()
        confirm(room, new_plan)
        after = solver.physical
        if (
            recipient is None
            or recipient not in after
            or before.index(recipient) != after.index(recipient)
        ):
            recipient = min(
                (name for name in after if name),
                key=lambda name: solver.op_data.operators[name].mood,
            )
        recipients.append(recipient)

    solver.tap_confirm.side_effect = confirm_with_recovery
    arrange(solver)

    assert recipients == ["银灰", "银灰"]
    assert [names.index("银灰") for names in solver.confirms] == [3, 3]
    assert solver.physical == FINAL


@pytest.mark.parametrize(
    "unavailable",
    [
        "unknown",
        "not_full",
        "working",
        "blacklisted",
        "workaholic",
        "limit",
        "reserved",
    ],
)
def test_no_safe_padding_restores_roster_without_compressing_target(
    solver, unavailable
):
    padding = solver.op_data.operators["黑角"]
    if unavailable == "unknown":
        padding.time_stamp = None
    elif unavailable == "not_full":
        padding.mood = 23
    elif unavailable == "working":
        padding.current_room = "meeting"
    elif unavailable == "blacklisted":
        solver.op_data.config.free_blacklist.append(padding.name)
    elif unavailable == "workaholic":
        padding.workaholic = True
    elif unavailable == "limit":
        solver.op_data.config.experimental_dorm_logic = True
        solver.op_data.config.operator_mood_limits = {"黑角": {"upper": 12}}
        padding.upper_limit = 12
    else:
        solver.tasks.append(SchedulerTask(task_plan={"meeting": [padding.name]}))

    arrange(solver)

    assert solver.confirms == [FINAL]
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""


def test_padding_actual_mood_is_checked_before_recording_single_recovery(solver):
    read = solver.get_agent_from_room.side_effect

    def read_changed_mood(*args):
        result = read(*args)
        solver.op_data.operators["黑角"].mood = 1
        return result

    solver.get_agent_from_room.side_effect = read_changed_mood
    arrange(solver)

    assert solver.physical == FINAL
    assert all(names.index("银灰") == 3 for names in solver.confirms)
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""


def test_same_room_move_invalidates_record_on_real_readback(solver):
    arrange(solver)
    target = solver.op_data.operators["银灰"]
    solver.op_data.update_detail(target.name, 5, ROOM, 4)
    assert target.dorm_recovery_room == ""
    assert target.dorm_recovery_index == -1


def test_old_marker_without_position_requires_confirmation(solver):
    arrange(solver)
    del solver.op_data.operators["银灰"].dorm_recovery_index
    assert recovery_order_plan(solver.op_data, ROOM, FINAL) is not None


@pytest.mark.parametrize("padding_mood", [24, 1])
def test_final_roster_reads_time_again_even_when_target_keeps_same_slot(
    solver, padding_mood
):
    from datetime import timedelta

    solver.op_data.config.experimental_dorm_logic = True
    old_time = datetime.now() + timedelta(hours=1)
    final_time = old_time + timedelta(hours=1)
    read = solver.get_agent_from_room.side_effect
    observed = []

    def read_timer(*args):
        result = read(*args)
        solver.op_data.operators["黑角"].mood = padding_mood
        target = solver.op_data.operators["银灰"]
        if target.current_index == 3:
            _, bed = solver.op_data.get_dorm_by_name(target.name)
            observed.append(bed.time)
            bed.name = target.name
            bed.time = final_time if solver.physical == FINAL else old_time
        return result

    solver.get_agent_from_room.side_effect = read_timer
    arrange(solver)

    assert observed[-1] is None
    assert solver.op_data.get_dorm_by_name("银灰")[1].time == final_time
