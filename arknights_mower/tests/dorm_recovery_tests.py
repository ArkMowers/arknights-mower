"""单回排序的真实排班入口、两次确认、失败重试及休息周期回归。"""

import copy
import pickle
import sys
from collections import defaultdict, deque
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.solvers.base_mixin import AgentSelectionNotReady  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import config, performance  # noqa: E402
from arknights_mower.utils.dorm_recovery import recovery_order_plan  # noqa: E402
from arknights_mower.utils.operators import Operator, Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    prioritize_new_dorm_recovery,
)

ROOM = "dormitory_1"
FINAL = ["杜林", "琴柳", "红", "银灰", "陈"]


def room_readings(operators, names, recipient, bonus=0.7):
    """模拟未换算为个人上限的宿舍读数；受益者由游戏夹具指定，不从排班推导。"""
    rows = []
    for name in names:
        row = {"agent": name}
        if name and operators[name].time_stamp is not None:
            mood = operators[name].mood
            if type(mood) in (int, float) and 0 <= mood <= 24:
                row["measured_mood"] = mood
                row["mood_sampled"] = True
                if mood < 24:
                    row["recovery_seconds"] = round(
                        (24 - mood) * 3600 / (2.3 + (bonus if name == recipient else 0))
                    )
        rows.append(row)
    return rows


@pytest.fixture
def solver(monkeypatch):
    return prepare_dorm_solver(object.__new__(BaseSchedulerSolver), monkeypatch)


def prepare_dorm_solver(instance, monkeypatch):
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base_schedule, "save_exception", lambda e: None)
    config.conf.enable_mastery = False
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
    instance.game_recipient = None
    instance.physical = ["杜林", "琴柳", "红", "陈", "银灰"]

    def observe(
        room=ROOM,
        read_time_index=None,
        *,
        departing_plan=None,
        expected_agents=None,
        observed_facilities=None,
        read_dorm_evidence=False,
        record_dorm_evidence=False,
    ):
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
        return room_readings(
            instance.op_data.operators, instance.physical, instance.game_recipient
        )

    def choose(agents, room, fast_mode=True, **kwargs):
        if kwargs.get("recovery_padding") and "Free" in agents:
            from arknights_mower.utils.dorm_candidates import full_dorm_candidate
            from arknights_mower.utils.dorm_recovery import (
                DormRecoveryPaddingUnavailable,
            )
            from arknights_mower.utils.dorm_skills import is_single_recovery_manager

            # 此夹具的选人页只显示已配置的这些持有者；卡片现场选择另有专项。
            candidates = iter(
                name
                for name in instance.get_dorm_candidates(agents, room=room).filling
                if name in instance.op_data.operators
                and full_dorm_candidate(instance.op_data, name)
                and not is_single_recovery_manager(name)
            )
            while "Free" in agents:
                name = next(candidates, None)
                if name is None:
                    raise DormRecoveryPaddingUnavailable()
                agents[agents.index("Free")] = name
        instance.selected = agents.copy()

    def confirm(room, new_plan):
        before = instance.physical
        instance.physical = instance.selected + [""] * (5 - len(instance.selected))
        name = instance.game_recipient
        if (
            name not in before
            or name not in instance.physical
            or before.index(name) != instance.physical.index(name)
        ):
            instance.game_recipient = next(
                (
                    n
                    for n in instance.physical
                    if n
                    and n not in ("菲亚梅塔", "琴柳", "闪灵")
                    and instance.op_data.operators[n].mood < 24
                ),
                None,
            )
        instance.confirms.append(instance.physical.copy())

    instance.get_agent_from_room = MagicMock(side_effect=observe)
    # 此夹具用选人页提交临时名单，床边按钮由对应的实图测试提供。
    instance._remove_trailing_dorm_recipient = MagicMock(return_value=False)
    instance.choose_agent = MagicMock(side_effect=choose)
    instance.tap_confirm = MagicMock(side_effect=confirm)
    observe()
    return instance


def arrange(solver, agents=None):
    if agents is not None:
        solver.task.plan = {ROOM: agents.copy()}
    solver.agent_arrange_room({}, ROOM, solver.task.plan)


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize(
    "role, locked",
    [
        ("priority", True),
        ("main", True),
        ("low_main", True),
        ("priority_replacement", True),
        ("standby", False),
        ("replacement", False),
        ("idle", False),
    ],
)
def test_recovery_setup_requires_protected_tier_without_retention(
    solver, monkeypatch, role, locked, retained
):
    from arknights_mower.utils import operation_timing
    from arknights_mower.utils.scheduler_task import estimate_task_duration

    monkeypatch.setattr(
        operation_timing, "_dorm_durations", defaultdict(lambda: deque(maxlen=8))
    )
    plan = solver.global_plan["default_plan"]
    plan.config = PlanConfig(
        "",
        "",
        "银灰" if role == "low_main" else "",
        ope_resting_priority="银灰" if role == "priority" else "",
        resting_standby="银灰" if role == "standby" else "",
        resting_priority_replacement="银灰" if role == "priority_replacement" else "",
        free_room_exclusions="银灰" if retained else "",
    )
    plan.plan[ROOM][2] = Room("红", "", [])
    plan.plan["meeting"] = [Room("银灰", "", ["黑角"])]
    if role in ("priority_replacement", "replacement", "idle"):
        plan.plan["meeting"] = [
            Room("黑角", "", ["银灰"] if role != "idle" else ["安德切尔"])
        ]
    assert solver.initialize_operators() is None
    if "银灰" not in solver.op_data.operators:
        solver.op_data.add(Operator("银灰", ""))
    solver.op_data.add(Operator("陈", ""))
    for op in solver.op_data.operators.values():
        op.mood = 5 if op.name in ("银灰", "陈") else 24
        op.time_stamp = datetime.now()
    solver.get_agent_from_room()
    locked = locked and not retained
    before = pickle.dumps(solver.op_data)

    assert estimate_task_duration(
        solver.task, op_data=solver.op_data
    ).total_seconds() == (85 if locked else 70)
    assert pickle.dumps(solver.op_data) == before
    arrange(solver)

    assert solver.physical == FINAL
    assert len(solver.confirms) == (2 if locked else 1)
    assert solver.confirms[-1] == FINAL
    assert solver.op_data.operators["银灰"].dorm_recovery_room == (
        ROOM if locked else ""
    )
    assert {3, 4}.issubset(solver.reads[-1])


def test_measured_later_bed_uses_the_ordinary_room_budget(solver, monkeypatch):
    from arknights_mower.tests.dorm_recovery_continuation_tests import (
        NEW,
        PEER,
        VIP,
        prepare_roommate_shift,
        start_after_release,
    )
    from arknights_mower.utils import operation_timing
    from arknights_mower.utils.scheduler_task import estimate_dorm_task_minutes

    start_after_release(solver, monkeypatch, bed=4)
    data = solver.op_data
    data.config.resting_priority.append(NEW)
    task = prepare_roommate_shift(solver, PEER, NEW, VIP)
    monkeypatch.setattr(
        operation_timing, "_dorm_durations", defaultdict(lambda: deque(maxlen=8))
    )
    before = pickle.dumps(data)
    assert estimate_dorm_task_minutes(task, ROOM, data) == 1.0
    assert pickle.dumps(data) == before
    assert solver.agent_arrange(task.plan) is not False
    assert len(solver.confirms) == 1
    assert "dorm_roommate_targets" not in vars(task)


def test_fill_a_vacancy_with_only_the_previous_seating_known(solver, monkeypatch):
    from arknights_mower.tests.dorm_recovery_continuation_tests import (
        MANAGERS,
        NEW,
        PEER,
        VIP,
        change_roommate,
        start_after_release,
    )
    from arknights_mower.utils.dorm_recovery import (
        active_recovery_position,
        verify_final_recovery,
    )

    start_after_release(solver, monkeypatch, bed=4)
    solver.physical[-1] = ""
    solver.game_recipient = None
    observed = solver.get_agent_from_room(read_dorm_evidence=True)
    data = solver.op_data
    verify_final_recovery(
        data,
        ROOM,
        solver.physical,
        observed,
        group_transitions={},
        can_repair=True,
        continued=VIP,
    )
    target = data.operators[VIP]
    assert not target.dorm_recovery_roster and target.dorm_roommate_roster
    expected = [*MANAGERS, PEER, VIP, NEW]
    assert change_roommate(solver, "", NEW, None) == expected
    assert solver.confirms == [expected]
    assert active_recovery_position(data, target) is None
    assert [name for name, _, _ in target.dorm_roommate_roster] == expected


def test_retention_change_still_completes_pending_roster_restoration(solver):
    assert solver.ensure_dorm_recovery_order(ROOM, FINAL.copy())
    solver.op_data.config.free_room_exclusions = ["银灰"]

    arrange(solver)

    solver.enter_room.assert_called_once_with(ROOM)
    assert solver.confirms == [["杜林", "琴柳", "黑角", "银灰", ""], FINAL]
    assert ROOM not in solver.task.dorm_recovery_restore


def test_admission_uses_full_recovery_budget_then_remaining_arrangement(
    solver, monkeypatch
):
    from arknights_mower.utils import operation_timing
    from arknights_mower.utils.scheduler_task import estimate_task_duration

    monkeypatch.setattr(
        operation_timing, "_dorm_durations", defaultdict(lambda: deque(maxlen=8))
    )
    ticks = iter([0, 50])
    monkeypatch.setattr(operation_timing, "perf_counter", lambda: next(ticks))
    before = pickle.dumps(solver.op_data)
    assert (
        estimate_task_duration(solver.task, op_data=solver.op_data).total_seconds()
        == 85
    )
    assert pickle.dumps(solver.op_data) == before
    solver.task.dorm_recovery_restore = [ROOM]
    assert (
        estimate_task_duration(solver.task, op_data=solver.op_data).total_seconds()
        == 70
    )
    del solver.task.dorm_recovery_restore
    arrange(solver)
    assert list(operation_timing._dorm_durations[(ROOM, True)]) == [50]
    assert (ROOM, False) not in operation_timing._dorm_durations
    solver.task.plan = {ROOM: FINAL.copy()}
    assert (
        estimate_task_duration(solver.task, op_data=solver.op_data).total_seconds()
        == 70
    )


def test_remaining_recovery_records_only_ordinary_arrangement(solver, monkeypatch):
    from arknights_mower.utils import operation_timing
    from arknights_mower.utils.scheduler_task import estimate_task_duration

    monkeypatch.setattr(
        operation_timing, "_dorm_durations", defaultdict(lambda: deque(maxlen=8))
    )
    assert solver.ensure_dorm_recovery_order(ROOM, FINAL.copy())
    assert solver.task.dorm_recovery_restore == [ROOM]
    assert (
        estimate_task_duration(solver.task, op_data=solver.op_data).total_seconds()
        == 70
    )
    ticks = iter([0, 30])
    monkeypatch.setattr(operation_timing, "perf_counter", lambda: next(ticks))
    arrange(solver)
    assert solver.physical == FINAL
    assert len(solver.confirms) == 2
    assert list(operation_timing._dorm_durations[(ROOM, False)]) == [30]
    assert (ROOM, True) not in operation_timing._dorm_durations


def test_admission_resolves_current_managers_without_changing_task_or_occupancy(
    solver, monkeypatch
):
    from arknights_mower.utils import operation_timing
    from arknights_mower.utils.scheduler_task import (
        defer_dorm_before_priority_task,
        estimate_task_duration,
    )

    monkeypatch.setattr(operation_timing, "_dorm_durations", {})
    solver.task.type = TaskTypes.RE_ORDER
    solver.task.plan = {ROOM: ["Current", "Current", "Current", "银灰", "陈"]}
    plan = copy.deepcopy(solver.task.plan)
    before = pickle.dumps(solver.op_data)
    assert (
        estimate_task_duration(solver.task, op_data=solver.op_data).total_seconds()
        == 85
    )
    now = solver.task.time
    order = SchedulerTask(
        time=now + timedelta(seconds=134), task_type=TaskTypes.RUN_ORDER
    )
    assert defer_dorm_before_priority_task(
        solver.task, [solver.task, order], ROOM, now, solver.op_data
    )
    assert solver.task.plan == plan
    assert pickle.dumps(solver.op_data) == before


@pytest.mark.parametrize("simple_fill, deferred", [(False, True), (True, False)])
def test_runtime_guard_uses_the_required_recovery_phase(
    solver, monkeypatch, simple_fill, deferred
):
    from arknights_mower.utils import operation_timing
    from arknights_mower.utils.scheduler_task import defer_dorm_before_priority_task

    monkeypatch.setattr(operation_timing, "_dorm_durations", {})
    solver.task.type = TaskTypes.RE_ORDER
    solver.task.simple_dorm_fill = simple_fill
    now = solver.task.time
    order = SchedulerTask(
        time=now + timedelta(seconds=134), task_type=TaskTypes.RUN_ORDER
    )
    tasks = [solver.task, order]
    before = pickle.dumps(solver.op_data)
    assert (
        defer_dorm_before_priority_task(solver.task, tasks, ROOM, now, solver.op_data)
        == deferred
    )
    assert pickle.dumps(solver.op_data) == before


@pytest.mark.parametrize("cover_mood", [1, 24, None])
def test_pending_fixed_cover_behind_target_uses_same_context(solver, cover_mood):
    plans = solver.global_plan["default_plan"].plan
    plans[ROOM][0] = Room("杜林", "联动", ["银灰"])
    plans[ROOM][2].group_bindings = [{"group": "另一组", "replacement": ["Free"]}]
    plans["contact"] = [Room("讯使", "另一组", ["芬"])]
    assert solver.initialize_operators() is None
    data = solver.op_data
    data.add(Operator("陈", ""))
    for op in data.operators.values():
        op.mood, op.time_stamp = 5, datetime.now()
    data.operators["琴柳"].mood = 24
    cover = data.operators["红"]
    cover.mood = cover_mood if cover_mood is not None else 24
    if cover_mood is None:
        cover.time_stamp = None
    data.commit_group_shifts({"联动": False, "另一组": True})
    solver.task.group_shift_transitions = {"联动": True, "另一组": False}
    solver.physical = ["黑角", "琴柳", "红", "银灰", "陈"]
    solver.get_agent_from_room()
    final = ["银灰", "琴柳", "红", "陈", "黑角"]

    arrange(solver, final)

    temporary = ["银灰", "琴柳", "红" if cover_mood == 24 else "", "", ""]
    assert solver.confirms == [temporary, final]
    assert solver.op_data.operators["银灰"].dorm_recovery_index == (
        0 if cover_mood is not None else -1
    )
    assert data.group_shift_state == {"联动": False, "另一组": True}


def test_simple_fill_skips_temporary_recovery_arrangement(solver):
    solver.task.type = TaskTypes.FILL_DORM
    solver.task.simple_dorm_fill = True
    arrange(solver)
    assert solver.confirms == [FINAL]
    assert solver.physical == FINAL
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""


@pytest.mark.parametrize("enabled", [False, True])
def test_idle_departure_observation_precedes_selection(solver, enabled):
    solver.op_data.config.free_room = enabled
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver.prepare_dorm_selection = MagicMock(return_value=[])
    target = ["杜林", "琴柳", "红", "陈", "黑角"]
    solver.task.plan = {ROOM: target.copy()}
    observe = solver.get_agent_from_room.side_effect
    choose = solver.choose_agent.side_effect
    events = []

    def read(room, read_time_index=None, *, departing_plan=None, expected_agents=None):
        events.append("departure" if departing_plan is not None else "readback")
        if departing_plan is not None:
            assert departing_plan == target
        return observe(room, read_time_index)

    def select(*args, **kwargs):
        events.append("selection")
        return choose(*args, **kwargs)

    solver.get_agent_from_room.side_effect = read
    solver.choose_agent.side_effect = select
    arrange(solver)
    assert events == ["departure", "selection", "readback"]
    assert solver.physical == target


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
        ("琴柳", 1, solver.op_data.operators["琴柳"].dorm_position_version),
    )
    assert solver.task.plan == {}
    assert solver.task.dorm_recovery_restore == []
    assert [3, 4] in solver.reads
    assert all(
        call.kwargs.get("preserve_dorm_occupants")
        for call in solver.choose_agent.call_args_list
    )


def test_same_final_positions_without_distinguishable_bonus_do_not_clear(solver):
    solver.physical = FINAL.copy()
    solver.get_agent_from_room()
    arrange(solver)
    assert not solver.confirms
    assert not solver.op_data.operators["银灰"].dorm_recovery_room


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


def test_ordinary_replacement_refreshes_room_timing_without_repeating_single_target(
    solver,
):
    arrange(solver)
    confirmations = len(solver.confirms)
    due = datetime.now() + timedelta(hours=3)
    for bed in solver.op_data.all_dorms():
        bed.time = due
    target = solver.op_data.operators["银灰"]
    marker = (
        target.dorm_recovery_room,
        target.dorm_recovery_index,
        target.dorm_recovery_fixed,
    )
    read = solver.get_agent_from_room.side_effect
    observed = []

    def observe(
        room,
        read_time_index=None,
        *,
        departing_plan=None,
        expected_agents=None,
        read_dorm_evidence=False,
        record_dorm_evidence=False,
    ):
        if departing_plan is None:
            observed.append(
                ([bed.time for bed in solver.op_data.all_dorms()], read_time_index)
            )
        return read(room, read_time_index)

    solver.get_agent_from_room.side_effect = observe
    arrange(solver, ["杜林", "琴柳", "红", "银灰", "黑角"])
    assert len(solver.confirms) == confirmations + 1
    assert observed[-1] == ([None, None], [3, 4])
    assert (
        target.dorm_recovery_room,
        target.dorm_recovery_index,
        target.dorm_recovery_fixed,
    ) == marker


def test_already_matching_roster_refreshes_timing_after_cross_room_arrangement(solver):
    arrange(solver)
    due = datetime.now() + timedelta(hours=3)
    for bed in solver.op_data.all_dorms():
        bed.time = due
    confirmations = len(solver.confirms)
    solver.task.plan = {ROOM: FINAL.copy()}
    solver.agent_arrange_room({}, ROOM, solver.task.plan, get_time=True)
    assert len(solver.confirms) == confirmations
    assert all(bed.time is None for bed in solver.op_data.all_dorms())
    assert solver.reads[-1] == [3, 4]


def test_backup_plan_ordinary_manager_change_keeps_same_target(solver):
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
    assert len(solver.confirms) == 3
    assert solver.confirms[-1] == updated
    target = solver.op_data.operators["银灰"]
    assert target.dorm_recovery_room == ROOM
    assert target.dorm_recovery_fixed == (
        ("琴柳", 1, solver.op_data.operators["琴柳"].dorm_position_version),
    )


def test_target_leaves_then_returns_needs_new_confirmation(solver):
    arrange(solver)
    target = solver.op_data.operators["银灰"]
    target.current_room = "meeting"
    target.current_room = ROOM
    assert target.dorm_recovery_room == ""
    assert target.dorm_recovery_fixed == ()
    arrange(solver, FINAL)
    assert len(solver.confirms) == 2
    assert target.dorm_recovery_room == ROOM


@pytest.mark.parametrize("name", ["琴柳", "银灰", "杜林", "红", "陈"])
@pytest.mark.parametrize("move", ["leave", "same_room"])
def test_resident_moves_invalidate_evidence_without_forcing_another_confirmation(
    solver, name, move
):
    arrange(solver)
    op = solver.op_data.operators[name]
    old_index = op.current_index
    if move == "leave":
        op.current_room = ""
        op.current_room = ROOM
    else:
        op.current_index = 4 if old_index != 4 else 3
        op.current_index = old_index
    assert recovery_order_plan(solver.op_data, ROOM, FINAL) is not None
    previous = solver.confirms.copy()
    arrange(solver, FINAL)
    assert solver.confirms == previous
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM


def test_single_manager_changes_slot_reconfigures_in_final_slot(solver):
    arrange(solver)
    updated = ["琴柳", "杜林", "红", "银灰", "陈"]
    arrange(solver, updated)
    assert solver.confirms[-2:] == [["琴柳", "杜林", "黑角", "银灰", ""], updated]
    assert solver.op_data.operators["银灰"].dorm_recovery_fixed == (
        ("琴柳", 0, solver.op_data.operators["琴柳"].dorm_position_version),
    )


def test_single_manager_replacement_is_kept_during_confirmation(solver):
    arrange(solver)
    solver.op_data.add(Operator("闪灵", ""))
    manager = solver.op_data.operators["闪灵"]
    manager.mood = 5
    manager.time_stamp = datetime.now()
    solver.op_data.plan[ROOM][1].replacement = ["闪灵"]
    solver.op_data.refresh_dorm_manager_flags(force=True)
    updated = ["杜林", "闪灵", "红", "银灰", "陈"]
    arrange(solver, updated)
    assert solver.confirms[-2:] == [["杜林", "闪灵", "黑角", "银灰", ""], updated]
    assert solver.op_data.operators["银灰"].dorm_recovery_fixed == (
        ("闪灵", 1, manager.dorm_position_version),
    )


def test_no_single_manager_does_not_do_extra_confirmation(solver):
    solver.op_data.plan[ROOM][1].agent = "黑角"
    solver.op_data.refresh_dorm_manager_flags(force=True)
    updated = ["杜林", "黑角", "红", "银灰", "陈"]
    arrange(solver, updated)
    assert solver.confirms == [updated]
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""


@pytest.mark.parametrize("manager_index", [2, 3, 4])
def test_single_manager_in_later_slots_keeps_final_position(solver, manager_index):
    from arknights_mower.utils.dorm_recovery import recovery_managers

    solver.op_data.add(Operator("芬", ""))
    solver.op_data.operators["芬"].mood = 24
    solver.op_data.operators["芬"].time_stamp = datetime.now()
    solver.op_data.config.ope_resting_priority = ["陈"]
    updated = ["杜林", "黑角", "银灰", "陈"]
    updated.insert(manager_index, "琴柳")
    managers = recovery_managers(solver.op_data, ROOM, updated)
    assert [(name, index) for name, index, _ in managers] == [("琴柳", manager_index)]
    arrange(solver, updated)
    assert len(solver.confirms) == 2
    assert all(row[manager_index] == "琴柳" for row in solver.confirms)
    assert solver.physical == updated
    target = "银灰" if manager_index == 2 else "陈"
    assert solver.op_data.operators[target].dorm_recovery_index == updated.index(target)
    assert recovery_order_plan(solver.op_data, ROOM, updated) is None


def test_idle_single_manager_in_free_slot_is_not_its_own_target(solver):
    from arknights_mower.utils.dorm_recovery import recovery_managers, recovery_target

    solver.op_data.plan[ROOM] = [Room("Free", "", []) for _ in range(5)]
    solver.op_data.add(Operator("闪灵", ""))
    manager = solver.op_data.operators["闪灵"]
    manager.mood = 1
    manager.time_stamp = datetime.now()
    updated = ["闪灵", "银灰", "陈", "红", "黑角"]
    assert not manager.single_recovery_manager
    assert recovery_target(solver.op_data, ROOM, updated).name == "银灰"
    assert [
        (name, index)
        for name, index, _ in recovery_managers(solver.op_data, ROOM, updated)
    ] == [("闪灵", 0)]
    arrange(solver, updated)
    assert solver.physical == updated
    assert manager.dorm_recovery_room == ""
    assert solver.op_data.operators["银灰"].dorm_recovery_index == 1


@pytest.mark.parametrize("fixed", [0, 1, 2])
def test_dorm_without_single_manager_only_confirms_final_roster(solver, fixed):
    updated = ["杜林", "黑角", "红", "银灰", "陈"]
    solver.op_data.plan[ROOM] = [
        Room(name if index < fixed else "Free", "", [])
        for index, name in enumerate(updated)
    ]
    arrange(solver, updated)
    solver.enter_room.assert_called_once_with(ROOM)
    assert solver.confirms == [updated]
    assert all(not op.dorm_recovery_room for op in solver.op_data.operators.values())


def test_missing_manager_still_restores_pending_final_roster(solver):
    updated = ["杜林", "黑角", "红", "银灰", "陈"]
    solver.task.dorm_recovery_restore = [ROOM]
    solver.physical = ["杜林", "黑角", "", "", ""]
    arrange(solver, updated)
    assert solver.confirms == [updated]
    assert solver.physical == updated
    assert solver.task.dorm_recovery_restore == []


def test_non_single_replacement_does_not_inherit_primary_skill(solver):
    solver.op_data.plan[ROOM][1].replacement = ["黑角"]
    updated = ["杜林", "黑角", "红", "银灰", "陈"]
    arrange(solver, updated)
    assert solver.confirms == [updated]


@pytest.mark.parametrize(
    "sources", [("闪灵", "琴柳"), ("蜜莓", "琴柳"), ("琴柳", "蜜莓")]
)
def test_multiple_possible_providers_complete_roster_without_claiming_first(
    solver, sources
):
    from arknights_mower.utils.dorm_recovery import recovery_managers

    for name in sources:
        if name not in solver.op_data.operators:
            solver.op_data.add(Operator(name, ""))
    updated = [*sources, "红", "银灰", "陈"]
    assert [
        entry[0] for entry in recovery_managers(solver.op_data, ROOM, updated)
    ] == list(sources)
    arrange(solver, updated)
    assert solver.confirms == [updated]
    assert not solver.op_data.operators["银灰"].dorm_recovery_fixed
    assert not solver.task.plan


@pytest.fixture
def readback_solver(solver):
    """只返回本次读房实际请求的数据，名单核对不附赠全房倒计时。"""
    read = solver.get_agent_from_room.side_effect

    def observe(room=ROOM, read_time_index=None, **kwargs):
        rows = read(room, read_time_index, **kwargs)
        for bed in solver.op_data.dorm:
            bed.name = solver.physical[bed.position[1]]
        if not (kwargs.get("read_dorm_evidence") or kwargs.get("record_dorm_evidence")):
            for index, row in enumerate(rows):
                if index not in (read_time_index or ()):
                    row.pop("recovery_seconds", None)
                    if not solver.op_data.mood_calculation_enabled:
                        row.pop("measured_mood", None)
        return rows

    solver.get_agent_from_room.side_effect = observe
    return solver


@pytest.mark.parametrize("calculated", [False, True], ids=["measured", "calculated"])
@pytest.mark.parametrize(
    "winner, policy, keep",
    [
        ("银灰", "default", True),
        ("陈", "default", False),
        (None, "default", False),
        ("银灰", "explicit_beds", False),
    ],
)
def test_release_uses_measured_recipient_with_two_providers(
    readback_solver, monkeypatch, calculated, winner, policy, keep
):
    from arknights_mower.utils.calculated_mood import sync_model
    from arknights_mower.utils.dorm_recovery import active_recovery_position

    solver = readback_solver
    data = solver.op_data
    monkeypatch.setattr(config.conf, "test_mood_calculation", calculated)
    data.add(Operator("安赛尔", ROOM, 0, mood=24, time_stamp=datetime.now()))
    data.plan[ROOM][0] = Room("安赛尔", "", [])
    data.operators["红"].mood = 24
    if policy == "explicit_beds":
        data.config.dorm_order.append(ROOM + "_low")
    before = ["安赛尔", "琴柳", "红", "黑角", "银灰"]
    after = [*before[:3], "陈", "银灰"]
    solver.physical = before.copy()
    solver.game_recipient = winner
    solver.get_agent_from_room()
    if calculated:
        for op in data.operators.values():
            data.mood_model.observe(op.name, op.mood)
    task = SchedulerTask(
        task_plan={ROOM: ["Current"] * 3 + ["陈", "Current"]},
        task_type=TaskTypes.RELEASE_DORM,
        meta_data="黑角",
    )
    solver.task, solver.tasks = task, [task]
    solver.prepare_release_dorm = MagicMock(return_value=True)

    assert solver.arrange_release_dorm()[0] is not False

    reorders = [t.plan for t in solver.tasks if t.type == TaskTypes.RE_ORDER]
    assert reorders == ([] if keep else [{ROOM: ["Current"] * 3 + ["银灰", "陈"]}])
    assert not task.plan and solver.confirms == [after]
    target = data.operators["银灰"]
    assert active_recovery_position(data, target) == ((ROOM, 4) if keep else None)
    assert active_recovery_position(data, data.operators["陈"]) is None
    if keep:
        assert [name for name, _, _ in target.dorm_recovery_fixed] == ["安赛尔", "琴柳"]
        assert [name for name, _, _ in target.dorm_recovery_roster] == after
    if calculated:
        assert sync_model(data).single_targets == {}


@pytest.mark.parametrize("winner", ["银灰", "陈", None])
@pytest.mark.parametrize("current", [False, True])
def test_multi_source_final_read_only_records_the_scheduled_target(
    readback_solver, winner, current
):
    from arknights_mower.utils.dorm_recovery import active_recovery_position

    solver = readback_solver
    data = solver.op_data
    data.add(Operator("安赛尔", ROOM, 0, mood=24, time_stamp=datetime.now()))
    data.plan[ROOM][0] = Room("安赛尔", "", [])
    data.operators["红"].mood = 24
    solver.physical = ["安赛尔", *FINAL[1:]]
    solver.game_recipient = winner
    solver.get_agent_from_room()
    solver.task.plan = {ROOM: ["Current"] * 5 if current else solver.physical.copy()}
    solver.get_agent_from_room.reset_mock()

    assert solver.agent_arrange(solver.task.plan) is not False

    assert not solver.task.plan
    assert solver.get_agent_from_room.call_count == 1
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    assert active_recovery_position(data, data.operators["银灰"]) == (
        (ROOM, 3) if winner == "银灰" else None
    )
    assert all(op.dorm_recovery_attempt is None for op in data.operators.values())
    assert active_recovery_position(data, data.operators["陈"]) is None


@pytest.mark.parametrize("recipient", ["银灰", "陈", None])
def test_two_source_confirmation_delivered_before_disconnect(
    readback_solver, recipient
):
    from arknights_mower.utils.dorm_recovery import active_recovery_position

    solver = readback_solver
    data = solver.op_data
    data.add(Operator("安赛尔", ROOM, 0, mood=24, time_stamp=datetime.now()))
    data.plan[ROOM][0] = Room("安赛尔", "", [])
    data.operators["红"].mood = 24
    final = ["安赛尔", *FINAL[1:]]
    solver.task.plan = {ROOM: final.copy()}
    confirm = solver.tap_confirm.side_effect

    def deliver(room, plan):
        confirm(room, plan)
        solver.game_recipient = recipient
        raise RuntimeError("确认已送达，结果画面丢失")

    solver.tap_confirm.side_effect = deliver
    assert solver.agent_arrange(solver.task.plan) is not False

    assert solver.confirms == [final] and not solver.task.plan
    assert solver.enter_room.call_count == 2
    assert solver.get_agent_from_room.call_args.kwargs.get("read_dorm_evidence")
    assert active_recovery_position(data, data.operators["银灰"]) == (
        (ROOM, 3) if recipient == "银灰" else None
    )


def test_scheduled_resident_can_receive_a_roommates_bonus_despite_own_skill(
    readback_solver,
):
    from arknights_mower.utils.dorm_recovery import active_recovery_position

    solver = readback_solver
    data = solver.op_data
    data.add(Operator("安赛尔", ROOM, 0, mood=24, time_stamp=datetime.now()))
    data.add(Operator("波登可", "", mood=8, time_stamp=datetime.now()))
    data.config.ope_resting_priority.append("波登可")
    data.plan[ROOM][0] = Room("安赛尔", "", [])
    data.operators["红"].mood = data.operators["陈"].mood = 24
    solver.physical = ["安赛尔", "琴柳", "红", "波登可", "陈"]
    solver.get_agent_from_room()
    solver.task.plan = {ROOM: solver.physical.copy()}
    solver.get_agent_from_room.reset_mock()

    assert solver.agent_arrange(solver.task.plan) is not False

    target = data.operators["波登可"]
    assert active_recovery_position(data, target) == (ROOM, 3)
    assert solver.get_agent_from_room.call_count == 1
    solver.tap_confirm.assert_not_called()
    solver.choose_agent.assert_not_called()


def test_later_single_manager_in_free_slot_is_not_proactively_confirmed(solver):
    from arknights_mower.utils.dorm_recovery import recovery_target

    solver.op_data.plan[ROOM] = [Room("Free", "", []) for _ in range(5)]
    for name in ("闪灵", "安赛尔"):
        solver.op_data.add(Operator(name, ""))
        solver.op_data.operators[name].mood = 5
        solver.op_data.operators[name].time_stamp = datetime.now()
    updated = ["安赛尔", "闪灵", "银灰", "陈", "红"]
    assert recovery_target(solver.op_data, ROOM, updated) is None
    assert recovery_order_plan(solver.op_data, ROOM, updated) is None
    arrange(solver, updated)
    assert len(solver.confirms) == 1
    assert solver.physical == updated
    assert solver.op_data.operators["闪灵"].dorm_recovery_room == ""
    assert solver.op_data.operators["安赛尔"].dorm_recovery_room == ""


def test_multiple_possible_sources_never_start_another_setup(solver):
    solver.op_data.add(Operator("闪灵", ROOM, 0))
    solver.op_data.operators["闪灵"].mood = 24
    solver.op_data.operators["闪灵"].time_stamp = datetime.now()
    updated = ["闪灵", "琴柳", "红", "银灰", "陈"]
    arrange(solver, updated)
    later = solver.op_data.operators["琴柳"]
    later.current_room = ""
    later.current_room = ROOM
    assert recovery_order_plan(solver.op_data, ROOM, updated) is None


def test_old_all_manager_marker_reconfirms(solver):
    arrange(solver)
    solver.op_data.operators["银灰"].dorm_recovery_fixed = ("杜林", "琴柳", "红")
    assert recovery_order_plan(solver.op_data, ROOM, FINAL) is not None


def test_all_configured_dorm_slots_and_replacements_are_matched(solver, monkeypatch):
    from arknights_mower.utils import dorm_skills

    solver.op_data.add(Operator("闪灵", ""))
    solver.op_data.add(Operator("安赛尔", ""))
    solver.op_data.plan[ROOM][2].replacement.append("闪灵")
    matcher = MagicMock(wraps=dorm_skills.is_single_recovery_manager)
    monkeypatch.setattr(dorm_skills, "is_single_recovery_manager", matcher)
    solver.op_data.refresh_dorm_manager_flags(force=True)
    assert {call.args[0] for call in matcher.call_args_list} == {
        "杜林",
        "琴柳",
        "桃金娘",
        "红",
        "闪灵",
    }
    assert solver.op_data.operators["闪灵"].single_recovery_manager
    assert not solver.op_data.operators["安赛尔"].single_recovery_manager


def test_complete_roster_queries_reuse_skill_cache(solver):
    from arknights_mower.utils import dorm_skills
    from arknights_mower.utils.dorm_recovery import recovery_managers

    recovery_managers(solver.op_data, ROOM, FINAL)
    before = dorm_skills.is_single_recovery_manager.cache_info()
    for _ in range(10):
        recovery_managers(solver.op_data, ROOM, FINAL)
    after = dorm_skills.is_single_recovery_manager.cache_info()
    assert after.misses == before.misses
    assert after.hits > before.hits


def test_resource_reload_updates_roster_skills(solver, monkeypatch, tmp_path):
    from arknights_mower.utils import dorm_skills

    empty = tmp_path / "skill.json"
    empty.write_text("[]")
    lookup = MagicMock(return_value=empty)
    monkeypatch.setattr(dorm_skills, "resource_pkg_path", lookup)
    dorm_skills.clear_dorm_skill_cache()
    try:
        assert recovery_order_plan(solver.op_data, ROOM, FINAL) is None
        assert not solver.op_data.operators["琴柳"].single_recovery_manager
        assert dorm_skills.is_single_recovery_manager.cache_info().misses == 5
        assert recovery_order_plan(solver.op_data, ROOM, FINAL) is None
        assert dorm_skills.is_single_recovery_manager.cache_info().misses == 5
        lookup.assert_called_once_with(dorm_skills.BUILDING_SKILL_DATA)
    finally:
        dorm_skills.clear_dorm_skill_cache()


def test_old_pickle_index_remains_compatible():
    op = Operator("琴柳", ROOM)
    op.__dict__["current_index"] = 1
    old = pickle.loads(pickle.dumps(op))
    assert old.current_index == 1
    old.current_index = 0
    assert old.current_index == 0
    assert old.__dict__["current_index"] == 0


def test_changing_target_clears_previous_single_recovery_recipient(solver):
    arrange(solver)
    solver.op_data.config.ope_resting_priority = ["陈"]
    new_plan = ["杜林", "琴柳", "红", "陈", "银灰"]
    arrange(solver, new_plan)
    assert solver.confirms[-2] == ["杜林", "琴柳", "黑角", "陈", ""]
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""
    assert solver.op_data.operators["陈"].dorm_recovery_room == ROOM


def test_higher_priority_admission_reestablishes_single_recovery(solver):
    arrange(solver)
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
        "Free",
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

    def fail_after_confirmation(*args, **kwargs):
        if "departing_plan" in kwargs:
            return read(*args, **kwargs)
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
    assert restored.dorm_recovery_fixed == (
        ("琴柳", 1, solver.op_data.operators["琴柳"].dorm_position_version),
    )
    solver.op_data.shadow_copy = {"银灰": restored}
    solver.op_data.add(Operator("银灰", "meeting", group="联动"))
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM
    assert solver.op_data.operators["银灰"].dorm_recovery_index == 3
    assert solver.op_data.operators["银灰"].dorm_recovery_fixed == (
        ("琴柳", 1, solver.op_data.operators["琴柳"].dorm_position_version),
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


@pytest.mark.parametrize("calculated", [False, True], ids=["measured", "calculated"])
@pytest.mark.parametrize("current", [False, True])
def test_only_unfinished_target_is_recorded_without_confirmation(
    readback_solver, monkeypatch, calculated, current
):
    from arknights_mower.utils.calculated_mood import sync_model
    from arknights_mower.utils.dorm_recovery import active_recovery_position

    solver = readback_solver
    data = solver.op_data
    monkeypatch.setattr(config.conf, "test_mood_calculation", calculated)
    for name in ("陈", "红"):
        data.operators[name].mood = 24
    if calculated:
        for op in data.operators.values():
            data.mood_model.observe(op.name, op.mood)
    solver.physical = FINAL.copy()
    solver.game_recipient = "银灰"
    solver.get_agent_from_room()
    if current:
        solver.task.plan = {ROOM: ["Current"] * 5}
    solver.get_agent_from_room.reset_mock()

    assert solver.agent_arrange(solver.task.plan) is not False

    target = data.operators["银灰"]
    assert not solver.task.plan
    assert solver.get_agent_from_room.call_count == 1
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    assert active_recovery_position(data, target) == (ROOM, 3)
    assert [name for name, _, _ in target.dorm_recovery_roster] == FINAL
    if calculated:
        assert sync_model(data).single_targets == {"琴柳": "银灰"}


@pytest.mark.parametrize(
    "after", ["银灰", "陈", None], ids=["same", "changed", "unknown"]
)
def test_only_unfinished_target_in_temporary_roster_is_checked_after_restoration(
    solver, after
):
    from arknights_mower.utils.dorm_recovery import active_recovery_position

    data = solver.op_data
    data.operators["红"].mood = 24
    temporary = ["杜林", "琴柳", "红", "银灰", ""]
    solver.physical = temporary.copy()
    solver.get_agent_from_room()
    assert solver.ensure_dorm_recovery_order(ROOM, FINAL)
    target = data.operators["银灰"]
    assert active_recovery_position(data, target) == (ROOM, 3)
    assert [name for name, _, _ in target.dorm_recovery_roster] == temporary
    assert solver.task.dorm_recovery_restore == [ROOM] and solver.task.plan == {
        ROOM: FINAL
    }
    solver.tap_confirm.assert_not_called()

    confirm = solver.tap_confirm.side_effect

    def restore(room, plan):
        confirm(room, plan)
        solver.game_recipient = after

    solver.tap_confirm.side_effect = restore
    assert solver.agent_arrange(solver.task.plan) is not False
    assert solver.confirms == [FINAL]
    assert not solver.task.plan and not solver.task.dorm_recovery_restore
    assert active_recovery_position(data, target) == (
        (ROOM, 3) if after == "银灰" else None
    )
    assert [name for name, _, _ in target.dorm_recovery_roster] == (
        FINAL if after == "银灰" else []
    )


def test_readback_with_remaining_competitor_never_marks_success(solver):
    solver.tap_confirm.side_effect = lambda room, new_plan: None
    with pytest.raises(base_schedule.RoomArrangementDeferred):
        arrange(solver)
    selections = solver.choose_agent.call_args_list
    assert sum(bool(call.kwargs.get("recovery_padding")) for call in selections) == 1
    assert all(call.args[0] == FINAL for call in selections[1:])
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""
    assert solver.task.dorm_recovery_restore == [ROOM]
    assert solver.task.plan == {ROOM: FINAL}


@pytest.mark.parametrize(
    ("platform", "initial_mode", "lowered_mode"),
    [
        ("windows", "xhigh", "high"),
        ("darwin", "xhigh", "high"),
        ("linux", "xhigh", "high"),
        ("android", "xhigh", "high"),
    ],
)
def test_preselection_feedback_failures_downgrade_auto_mode(
    solver, monkeypatch, platform, initial_mode, lowered_mode
):
    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    monkeypatch.setattr(performance, "__system__", platform)
    config.conf.performance_mode = "auto"
    monkeypatch.setattr(config, "operation_feedback_avg", None)
    monkeypatch.setattr(config, "operation_feedback_count", 0)
    monkeypatch.setattr(config, "operation_feedback_mode", None)
    monkeypatch.setattr(config, "operation_feedback_cap", None)
    monkeypatch.setattr(config, "operation_failure_streak", 0)
    monkeypatch.setattr(config, "operation_recovery_successes", 0)
    solver.choose_agent.side_effect = AgentSelectionNotReady("排序反馈未到")
    assert solver.performance_profile.mode == initial_mode

    for _ in range(2):
        with pytest.raises(AgentSelectionNotReady, match="排序反馈未到"):
            solver.ensure_dorm_recovery_order(ROOM, FINAL)

    assert solver.choose_agent.call_count == 2
    assert config.operation_feedback_cap == lowered_mode
    assert solver.performance_profile.mode == lowered_mode
    assert config.operation_failure_streak == 0


def test_target_reaches_full_during_confirmation_does_not_keep_cycle_marker(solver):
    read = solver.get_agent_from_room.side_effect

    def full_on_read(*args, **kwargs):
        if "departing_plan" in kwargs:
            return read(*args, **kwargs)
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
    if unavailable == "working":
        padding.current_room = "meeting"
    elif unavailable == "blacklisted":
        solver.op_data.config.free_blacklist.append(padding.name)
    elif unavailable == "workaholic":
        padding.workaholic = True
    elif unavailable == "limit":
        solver.op_data.config.operator_mood_limits = {"黑角": {"upper": 12}}
        padding.upper_limit = 12
    else:
        solver.tasks.append(SchedulerTask(task_plan={"meeting": [padding.name]}))

    arrange(solver)

    assert solver.confirms == [FINAL]
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""


def test_padding_actual_mood_is_checked_before_recording_single_recovery(solver):
    read = solver.get_agent_from_room.side_effect

    def read_changed_mood(*args, **kwargs):
        if "departing_plan" not in kwargs:
            solver.op_data.operators["黑角"].mood = 1
            solver.game_recipient = "红" if solver.physical == FINAL else "黑角"
        return read(*args, **kwargs)

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

    old_time = datetime.now() + timedelta(hours=1)
    final_time = old_time + timedelta(hours=1)
    read = solver.get_agent_from_room.side_effect
    observed = []

    def read_timer(*args, **kwargs):
        if "departing_plan" in kwargs:
            return read(*args, **kwargs)
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


@pytest.mark.parametrize("mood", [23, 15])
def test_non_full_idle_candidates_do_not_confirm_single_recovery(solver, mood):
    solver.op_data.operators["黑角"].mood = mood
    solver.op_data.add(Operator("芬", ""))
    other = solver.op_data.operators["芬"]
    other.mood, other.time_stamp = mood - 1, datetime.now()
    arrange(solver)
    assert solver.confirms == [FINAL]
    assert all(names[3] == "银灰" for names in solver.confirms)
    assert solver.op_data.operators["银灰"].dorm_recovery_index == -1


def test_full_preceding_resident_is_not_replaced_by_idle_padding(solver):
    solver.op_data.operators["红"].mood = 24
    arrange(solver)
    assert solver.confirms == [["杜林", "琴柳", "红", "银灰", ""], FINAL]
    assert solver.op_data.operators["银灰"].dorm_recovery_index == 3


@pytest.mark.parametrize("index", [0, 2])
@pytest.mark.parametrize("mood", [0, 5, 23, None])
def test_preceding_fiammetta_keeps_position_and_does_not_block_recovery(
    solver, index, mood
):
    solver.op_data.plan[ROOM][index] = Room("菲亚梅塔", "", ["银灰"])
    solver.op_data.add(
        Operator(
            "菲亚梅塔",
            ROOM,
            index=index,
            mood=mood if mood is not None else 1,
            time_stamp=datetime.now() if mood is not None else None,
        )
    )
    solver.physical[index] = "菲亚梅塔"
    solver.get_agent_from_room()
    final = FINAL.copy()
    final[index] = "菲亚梅塔"
    temporary = ["杜林", "琴柳", "黑角", "银灰", ""]
    temporary[index] = "菲亚梅塔"

    arrange(solver, final)

    assert solver.confirms == [temporary, final]
    assert all(names[index] == "菲亚梅塔" for names in solver.confirms)
    target = solver.op_data.operators["银灰"]
    assert (target.dorm_recovery_room, target.dorm_recovery_index) == (ROOM, 3)
    assert solver.op_data.operators["菲亚梅塔"].dorm_recovery_room == ""
    assert recovery_order_plan(solver.op_data, ROOM, final) is None


def test_preceding_fiammetta_needs_no_idle_padding(solver):
    solver.op_data.plan[ROOM][2] = Room("菲亚梅塔", "", ["银灰"])
    solver.op_data.add(
        Operator("菲亚梅塔", ROOM, index=2, mood=0, time_stamp=datetime.now())
    )
    solver.physical[2] = "菲亚梅塔"
    solver.get_agent_from_room()
    solver.op_data.config.free_blacklist.extend(["黑角", "红"])
    final = ["杜林", "琴柳", "菲亚梅塔", "银灰", "陈"]

    arrange(solver, final)

    assert solver.confirms == [["杜林", "琴柳", "菲亚梅塔", "银灰", ""], final]
    assert solver.op_data.operators["银灰"].dorm_recovery_index == 3


def test_retained_full_resident_readback_must_not_compete_with_target(solver):
    solver.op_data.operators["红"].mood = 24
    read = solver.get_agent_from_room.side_effect

    def read_mood(*args, **kwargs):
        if "departing_plan" not in kwargs and solver.confirms:
            solver.op_data.operators["红"].mood = 1
            solver.game_recipient = "红"
        return read(*args, **kwargs)

    solver.get_agent_from_room.side_effect = read_mood
    arrange(solver)
    assert solver.physical == FINAL
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ""


@pytest.mark.parametrize(
    "name, boosted, unboosted",
    [("波登可", 14400, 18783), ("子月", 11676, 14400)],
)
@pytest.mark.parametrize("case", ["target", "explicit_beds", "other", "unclear"])
def test_release_keeps_last_bed_for_measured_target_with_own_skill(
    readback_solver, name, boosted, unboosted, case
):
    from arknights_mower.utils.dorm_recovery import (
        active_recovery_position,
        keep_measured_dorm_swap,
        observed_recovery_recipient,
    )

    solver = readback_solver
    data = solver.op_data
    now = datetime.now()
    data.add(Operator("安赛尔", ROOM, 0, mood=24, time_stamp=now))
    data.plan[ROOM][0] = Room("安赛尔", "", [])
    data.add(Operator(name, "", mood=12, time_stamp=now))
    data.config.ope_resting_priority.append(name)
    if case == "explicit_beds":
        data.config.dorm_order.append(ROOM + "_low")
    data.operators["红"].mood, data.operators["陈"].mood = 24, 12
    before = ["安赛尔", "琴柳", "红", "黑角", name]
    after = [*before[:3], "陈", name]
    solver.physical = before.copy()
    solver.get_agent_from_room()
    read = solver.get_agent_from_room.side_effect
    last_read = []

    def observe(*args, **kwargs):
        rows = read(*args, **kwargs)
        if solver.physical == after:
            # 两人心情均为 12。子月的两组计时都含自回，只有一组另含室友单回。
            for row, seconds in zip(
                rows[3:], (14400, unboosted) if case == "other" else (18783, boosted)
            ):
                if "recovery_seconds" in row:
                    row["recovery_seconds"] = seconds
            if case == "unclear":
                rows[3].pop("recovery_seconds", None)
            last_read[:] = rows
        return rows

    solver.get_agent_from_room.side_effect = observe
    task = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={ROOM: ["Current"] * 3 + ["陈", "Current"]},
        meta_data="黑角",
    )
    solver.task, solver.tasks = task, [task]
    solver.prepare_release_dorm = MagicMock(return_value=True)

    assert solver.arrange_release_dorm()[0] is not False
    assert not task.plan and solver.confirms == [after]
    assert data.get_current_room(ROOM, True) == after
    recipient = {"other": "陈", "unclear": None}.get(case, name)
    assert observed_recovery_recipient(last_read, {}) == recipient
    swap = ["Current"] * 3 + [name, "陈"]
    reorders = [t.plan for t in solver.tasks if t.type == TaskTypes.RE_ORDER]
    assert reorders == ([] if case == "target" else [{ROOM: swap}])
    position = active_recovery_position(data, data.operators[name])
    assert position == ((ROOM, 4) if case == "target" else None)
    if case == "target":
        assert keep_measured_dorm_swap(data, ROOM, swap)
        for other_clock in (14400, None):
            reading = [row.copy() for row in last_read]
            reading[3]["recovery_seconds"] = other_clock
            reading[4]["recovery_seconds"] = unboosted
            assert not keep_measured_dorm_swap(data, ROOM, swap, reading)


@pytest.mark.parametrize("current", [False, True], ids=["named", "current"])
def test_ownership_only_check_preserves_another_residents_deadline(
    readback_solver, current
):
    solver = readback_solver
    data = solver.op_data
    solver.physical = FINAL.copy()
    solver.game_recipient = "银灰"
    solver.get_agent_from_room()
    bed = next(bed for bed in data.all_dorms() if bed.position == (ROOM, 4))
    bed.time = deadline = datetime.now() + timedelta(hours=7)
    solver.get_agent_from_room.reset_mock()
    if current:
        solver.task.plan[ROOM] = ["Current", "Current", "Current", "银灰", "Current"]

    solver.agent_arrange_room({}, ROOM, solver.task.plan, get_time=False)

    assert not solver.task.plan and solver.get_agent_from_room.call_count == 1
    assert (bed.name, bed.time) == ("陈", deadline)
    solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize("calculated", [False, True])
def test_cold_multi_source_dorm_reads_occupants_and_deadlines_together(
    readback_solver, monkeypatch, calculated
):
    solver = readback_solver
    data = solver.op_data
    monkeypatch.setattr(config.conf, "test_mood_calculation", calculated)
    data.add(Operator("安赛尔", ROOM, 0, mood=24, time_stamp=datetime.now()))
    data.plan[ROOM][0] = Room("安赛尔", "", [])
    solver.physical = ["安赛尔", *FINAL[1:]]
    solver.game_recipient = "银灰"
    for op in data.operators.values():
        op.current_room, op.current_index = "", -1
    for bed in data.all_dorms():
        bed.reset()
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=True)
    solver.task.plan = {ROOM: solver.physical.copy()}

    solver.agent_arrange_room({}, ROOM, solver.task.plan, get_time=True)

    assert not solver.task.plan
    solver.get_agent_from_room.assert_called_once()
    observed = solver.get_agent_from_room.call_args.kwargs
    assert observed["read_dorm_evidence"] and observed["read_time_index"] == [3, 4]
    assert data.operators["银灰"].dorm_recovery_room == ROOM
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
