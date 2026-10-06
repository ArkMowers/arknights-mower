"""Backup relocations preserve recovery on entry and exit."""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import multi_group_shift_tests as shared
from arknights_mower.utils import config
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes, try_reorder

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(shared.base_schedule.logger, "debug", lambda *a, **k: None)
    monkeypatch.setattr(shared.base_schedule.logger, "info", lambda *a, **k: None)
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.enable_mastery = False
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(shared.base_schedule, "_is_mastery_busy", lambda name: False)
    s = object.__new__(shared.BaseSchedulerSolver)
    plan = {
        "central": [Room("森蚺", "甲", ["夕"]), Room("歌蕾蒂娅", "乙", ["重岳"])],
        "room_1_1": [Room("清流", "甲", ["结城理"], "制造站", "gold")],
        "room_1_2": [Room("乌尔比安", "乙", ["槐琥"], "制造站", "gold")],
        "dormitory_1": [
            Room("塑心", "", []),
            Room("冰酿", "", []),
            *[Room("Free", "", []) for _ in range(3)],
        ],
        "dormitory_2": [
            Room("闪灵", "", []),
            Room("流明", "", []),
            *[Room("Free", "", []) for _ in range(3)],
        ],
    }
    bp = Plan(
        {
            "room_1_1": deepcopy(plan["room_1_2"]),
            "room_1_2": deepcopy(plan["room_1_1"]),
        },
        PlanConfig("", "", ""),
        trigger=LogicExpression("op_data.operators['森蚺'].is_resting()", "==", "True"),
    )
    s.global_plan = {
        "default_plan": Plan(plan, PlanConfig("", "", "")),
        "backup_plans": [bp],
    }
    assert s.initialize_operators() is None
    s.tasks, s.task = [], None
    s.find_next_task = MagicMock(return_value=None)
    s.enter_room = MagicMock(side_effect=AssertionError("device access"))
    s.last_train_mood_read = datetime.now()
    s._suppress_train_correction = lambda plan: None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 22, datetime.now()
    return s


def recovery(s):
    return {
        bed.name: (bed.position, bed.time) for bed in s.op_data.all_dorms() if bed.name
    }


def finish(s, task, *, full=True):
    s.task, s.tasks = task, []
    if full:
        s._prepare_shift_cycle(task)
    else:
        s._prepare_shift_backup(task)
    assert s.op_data.swap_plan(task.backup_shift_conditions, refresh=True) is None
    s.op_data = s.op_data.project_arrangements([task.plan])
    for bed in s.op_data.all_dorms():
        if bed.name and bed.time is None:
            bed.time = datetime.now() + timedelta(hours=4)
    return task


def off(s, group):
    intent = {}
    for name in s.op_data.groups[group]:
        s.op_data.operators[name].mood = 0
    assert s.get_resting_plan(s.op_data.groups[group], [], intent, 0)
    shared.base_schedule._merge_dorm_arrangement(
        intent, try_reorder(s.op_data, intent) or {}
    )
    return finish(s, SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan=intent))


def test_downshift_relocation_does_not_cancel_its_trigger(solver):
    task = off(solver, "甲")
    assert task.backup_shift_conditions == [True]
    assert solver.op_data.operators["森蚺"].is_resting()
    assert solver.op_data.operators["清流"].is_resting()
    assert solver.op_data.operators["结城理"].current_room == "room_1_2"
    assert solver.op_data.operators["乌尔比安"].current_room == "room_1_1"


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("full", [False, True])
def test_exit_does_not_recall_another_resting_group(solver, explicit, full):
    s = solver
    if explicit:
        s.op_data.backup_plans[0].task = {
            "room_1_1": ["乌尔比安"],
            "room_1_2": ["结城理"],
        }
    off(s, "甲")
    off(s, "乙")
    before = recovery(s)
    for name in s.op_data.groups["甲"]:
        s.op_data.operators[name].mood = 24
    finish(
        s,
        SchedulerTask(
            task_type=TaskTypes.SHIFT_ON,
            task_plan={"central": ["森蚺", "Current"], "room_1_2": ["清流"]},
        ),
        full=full,
    )
    assert s.op_data.plan_condition == [False]
    for name in ("歌蕾蒂娅", "乌尔比安"):
        assert s.op_data.operators[name].is_resting()
        # 完整轮休可将住客转到另一组腾出的单回位；切表自身不重排床位。
        if not full:
            assert recovery(s)[name] == before[name]
    assert s.op_data.operators["槐琥"].current_room == "room_1_2"


def prepare_resting_relocation(s, *, both=False):
    s.op_data.backup_plans[0].trigger = LogicExpression("True", "==", "True")
    plan = {
        "central": ["夕", "重岳" if both else "Current"],
        "room_1_1": ["结城理"],
        "dormitory_1": ["Current", "Current", "森蚺", "清流", "Current"],
    }
    if both:
        plan.update(
            {
                "room_1_2": ["槐琥"],
                "dormitory_2": [
                    "Current",
                    "Current",
                    "歌蕾蒂娅",
                    "乌尔比安",
                    "Current",
                ],
            }
        )
    s.op_data = s.op_data.project_arrangements([plan])
    for bed in s.op_data.all_dorms():
        if bed.name:
            bed.time = datetime.now() + timedelta(hours=4)
            s.op_data.operators[bed.name].mood = 0


def test_both_resting_covers_move_without_spare(solver):
    s = solver
    prepare_resting_relocation(s, both=True)
    before = recovery(s)
    task = finish(s, SchedulerTask(task_type=TaskTypes.SELF_CORRECTION), full=False)
    assert task.plan == {"room_1_1": ["槐琥"], "room_1_2": ["结城理"]}
    assert recovery(s) == before


@pytest.mark.parametrize("blocking", ["mastery", "reservation"])
def test_protected_relocation_shortage_preserves_state(solver, monkeypatch, blocking):
    s = solver
    prepare_resting_relocation(s)
    before = recovery(s)
    if blocking == "mastery":
        monkeypatch.setattr(
            shared.base_schedule, "_is_mastery_busy", lambda n: n in ("清流", "结城理")
        )
    else:
        s.tasks = [
            SchedulerTask(task_plan={"contact": ["结城理"], "factory": ["清流"]})
        ]
    pending = list(s.tasks)
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    with pytest.raises(shared.base_schedule.ProductSwitchDeferred):
        s._prepare_shift_backup(task)
    assert s.op_data.plan_condition == [False]
    assert recovery(s) == before
    assert s.tasks == pending


def test_explicit_entry_primary_keeps_its_precedence(solver):
    s = solver
    prepare_resting_relocation(s)
    s.op_data.backup_plans[0].task = {"room_1_2": ["清流"]}
    finish(s, SchedulerTask(task_type=TaskTypes.SELF_CORRECTION), full=False)
    assert s.op_data.operators["清流"].current_room == "room_1_2"


def test_relocated_worker_releases_cover_for_resting_primary(solver):
    s = solver
    # 新岗位的当前驻员虽可替班，迁移中的在岗主班仍需本人到岗。
    s.op_data.backup_plans[0].plan["room_1_1"][0].replacement = ["结城理"]
    task = off(s, "甲")
    assert task.backup_shift_conditions == [True]
    assert s.op_data.operators["乌尔比安"].current_room == "room_1_1"
    assert s.op_data.operators["结城理"].current_room == "room_1_2"


def test_relocation_allows_required_dorm_layout_migration(solver):
    s = solver
    prepare_resting_relocation(s)
    dorm = deepcopy(s.op_data.plan["dormitory_1"])
    dorm[3] = Room("白面鸮", "", [])
    s.op_data.backup_plans[0].plan["dormitory_1"] = dorm
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    s._prepare_shift_backup(task)
    assert task.backup_shift_conditions == [True]
    assert s.op_data.swap_plan(task.backup_shift_conditions, refresh=True) is None
    projected = s.op_data.project_arrangements([task.plan])
    op = projected.operators["清流"]
    assert op.is_resting()
    assert (op.current_room, op.current_index) != ("dormitory_1", 3)
    assert projected.get_dorm_by_name("清流")[1].time is None
    assert projected.get_current_operator("dormitory_1", 3).name == "白面鸮"


def test_reserved_source_cover_cannot_migrate(solver):
    from arknights_mower.utils.resting_correction import preserve_backup_replacements

    s = solver
    prepare_resting_relocation(s)
    beds = deepcopy(s.op_data.all_dorms())
    assert s.op_data.swap_plan([True], refresh=True) is None
    # 保留原岗位上的替班供任务使用；主班可用时沿用提前回班兜底。
    plan = {"room_1_1": ["乌尔比安"]}
    assert preserve_backup_replacements(
        s.op_data,
        plan,
        {("room_1_2", 0)},
        beds,
        lambda name: False,
        reserved_slots={("room_1_1", 0)},
    )
    assert plan["room_1_2"] == ["清流"]


def test_independent_backup_transition_preserves_rest(solver):
    s = solver
    prepare_resting_relocation(s)
    before = recovery(s)
    generated = []
    s.backup_plan_solver(generated_tasks=generated)
    assert s.op_data.plan_condition == [True]
    task = next(t for t in generated if t.plan)
    assert task.plan["room_1_2"] == ["结城理"]
    assert s.op_data.operators["清流"].is_resting()
    assert recovery(s) == before


@pytest.mark.parametrize("changed", ["group", "facility"])
def test_changed_group_or_facility_retains_explicit_primary_semantics(solver, changed):
    s = solver
    prepare_resting_relocation(s)
    slot = s.op_data.backup_plans[0].plan["room_1_2"][0]
    if changed == "group":
        slot.group = "乙"
    else:
        slot.facility = "贸易站"
        slot.product = "lmd"
    task = finish(s, SchedulerTask(task_type=TaskTypes.SELF_CORRECTION), full=False)
    assert task.plan["room_1_2"] == ["清流"]
