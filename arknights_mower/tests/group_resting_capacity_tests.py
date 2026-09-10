"""深海一高优、六低优：接管替班或待命，且正常往返不产生叫回纠错。"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.log import logger  # noqa: E402
from arknights_mower.utils.operators import Operator  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    TaskTypes,
    plan_metadata,
    try_reorder,
)

DEEP = ["歌蕾蒂娅", "能天使", "蕾缪安", "乌尔比安", "安哲拉", "斯卡蒂", "幽灵鲨"]
COVERS = ["薇薇安娜", "火哨", "巫恋", "苍苔", "砾", "多萝西", "淬羽赫默"]
OTHERS = ["令", "夕", "森蚺", "温蒂", "清流", "絮雨", "槐琥", "鸿雪"]
OTHER_COVERS = ["阿米娅", "陈", "初雪", "红", "黑角", "芬", "翎羽", "香草"]


def apply_plan(solver, plan):
    data = solver.op_data
    end_times = {bed.name: bed.time for bed in data.dorm if bed.name}
    for room, names in plan.items():
        for index, name in enumerate(names):
            if name == "Current":
                continue
            occupant = data.get_current_operator(room, index)
            if occupant:
                occupant.current_room, occupant.current_index = "", -1
            if name not in ("Free", ""):
                op = data.operators[name]
                op.current_room, op.current_index = room, index
                op.time_stamp = datetime.now()
    for bed in data.dorm:
        occupant = data.get_current_operator(*bed.position)
        bed.name = occupant.name if occupant else ""
        bed.time = (
            end_times.get(occupant.name) or datetime.now() + timedelta(hours=8)
            if occupant
            else None
        )


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(logger, "disabled", True)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    config.conf.enable_mastery = False
    for field in (
        "fodder_operators",
        "t5_operators",
        "book_operators",
        "workshop_settings",
    ):
        setattr(config.conf, field, [])
    config.conf.workshop_manual_backup = None
    slots = [Room(name, "深海", [cover]) for name, cover in zip(DEEP, COVERS)]
    others = [Room(name, "", [cover]) for name, cover in zip(OTHERS, OTHER_COVERS)]
    rooms = {
        "central": slots[:1],
        "meeting": slots[1:3],
        "room_2_2": slots[3:5],
        "room_3_3": slots[5:],
        "room_1_1": others[:3],
        "room_1_2": others[3:6],
        "room_3_2": others[6:],
    }
    for index, residents in enumerate(
        [("塑心", "冰酿"), ("流明", "蜜莓"), ("杜林", "车尔尼")], 1
    ):
        rooms[f"dormitory_{index}"] = [
            *[Room(name, "", []) for name in residents],
            *[Room("Free", "", []) for _ in range(3)],
        ]
    instance = object.__new__(BaseSchedulerSolver)
    instance.global_plan = {
        "default_plan": Plan(
            rooms, PlanConfig("", "", ",".join(DEEP[1:]), ope_resting_priority=DEEP[0])
        ),
        "backup_plans": [],
    }
    assert instance.initialize_operators() is None
    instance.tasks = []
    instance.find_next_task = MagicMock(return_value=None)
    instance.enter_room = MagicMock(
        side_effect=AssertionError("unexpected device read")
    )
    instance._suppress_train_correction = lambda plan: None
    instance.plan_metadata = MagicMock()
    apply_plan(
        instance,
        {room: [slot.agent for slot in slots] for room, slots in rooms.items()},
    )
    for op in instance.op_data.operators.values():
        op.mood = 20
        op.time_stamp = datetime.now()
    instance.op_data.operators[DEEP[0]].mood = 0
    instance.total_agent = [instance.op_data.operators[name] for name in DEEP]
    return instance


def occupy_beds(solver, kind):
    """只留一个空位，其余由普通替班或正在休息的其他主力占据。"""
    data = solver.op_data
    occupants = OTHERS if kind != "replacement" else OTHER_COVERS
    if kind != "replacement":
        apply_plan(
            solver,
            {
                room: [s.replacement[0] for s in data.plan[room]]
                for room in ("room_1_1", "room_1_2", "room_3_2")
            },
        )
        for name in OTHERS:
            data.operators[name].resting_priority = kind
    else:
        for name in OTHER_COVERS:
            data.operators[name].mood = 5
    arrangement = {}
    for bed, name in zip(data.dorm[1:], occupants):
        room, index = bed.position
        arrangement.setdefault(room, ["Current"] * 5)[index] = name
    apply_plan(solver, arrangement)
    return [(bed.position, bed.name, bed.time) for bed in data.dorm[1:]]


def shift_off(solver):
    plan = solver.resting()
    assert plan
    assert [name for names in plan.values() for name in names] == COVERS
    beds = try_reorder(solver.op_data, plan)
    apply_plan(solver, plan)
    apply_plan(solver, beds)
    solver.tasks = []


@pytest.mark.parametrize("occupants", ["replacement", "high", "low"])
def test_deep_group_one_empty_bed_round_trip_without_correction(solver, occupants):
    before = occupy_beds(solver, occupants)
    shift_off(solver)
    data = solver.op_data
    expected_standby = set(DEEP[1:]) if occupants != "replacement" else set()
    assert {name for name in DEEP if data.is_group_standby(name)} == expected_standby
    assert data.operators[DEEP[0]].is_resting()
    assert [data.operators[n].resting_priority for n in DEEP] == ["high", *["low"] * 6]
    if occupants != "replacement":
        assert all(data.operators[name].is_resting() for name in OTHERS)
        assert [(bed.position, bed.name, bed.time) for bed in data.dorm[1:]] == before
    for _ in range(3):
        assert solver.agent_get_mood() is None
        assert solver.resting() == {}
        assert solver.tasks == []
    tasks = plan_metadata(data, [])
    back = [
        task
        for task in tasks
        if task.type == TaskTypes.SHIFT_ON and DEEP[0] in task.plan.get("central", [])
    ]
    assert len(back) == 1
    assert set(DEEP) <= {name for names in back[0].plan.values() for name in names}
    apply_plan(solver, back[0].plan)
    assert solver.agent_get_mood(skip_dorm=True) is None
    assert not any(data.is_group_standby(name) for name in DEEP)
    assert all(data.operators[n].current_room == data.operators[n].room for n in DEEP)
    solver.enter_room.assert_not_called()


def test_unrelated_correction_does_not_recall_standby_group(solver):
    occupy_beds(solver, "low")
    shift_off(solver)
    op = solver.op_data.operators["冰酿"]
    op.current_room, op.current_index = "", -1
    assert solver.agent_get_mood() == "self_correction"
    plan = solver.tasks.pop().plan
    assert plan == {"dormitory_1": ["Current", "冰酿", "Current", "Current", "Current"]}
    apply_plan(solver, plan)
    assert solver.agent_get_mood() is None
    assert all(solver.op_data.is_group_standby(n) for n in DEEP[1:])


@pytest.mark.parametrize(
    "failure", ["no_bed", "exhaust", "full", "no_anchor", "full_anchor", "cover"]
)
def test_required_beds_and_replacements_fail_without_partial_assignment(
    solver, failure
):
    occupy_beds(solver, "high")
    data = solver.op_data
    if failure == "no_bed":
        data.add(Operator("年", "meeting", operator_type="high", mood=5))
        room, index = data.dorm[0].position
        names = ["Current"] * 5
        names[index] = "年"
        apply_plan(solver, {room: names})
    elif failure in ("exhaust", "full"):
        setattr(
            data.operators[DEEP[1]],
            "exhaust_require" if failure == "exhaust" else "rest_in_full",
            True,
        )
    elif failure == "no_anchor":
        data.operators[DEEP[0]].resting_priority = "low"
    elif failure == "full_anchor":
        data.operators[DEEP[0]].mood = 24
    else:
        data.operators[COVERS[-1]].current_room = "contact"
    before = [(bed.name, bed.time) for bed in data.dorm]
    plan, replacements = {}, []
    solver.get_resting_plan(data.groups["深海"], replacements, plan, 0)
    assert plan == {}
    assert replacements == []
    assert [(bed.name, bed.time) for bed in data.dorm] == before


def test_standby_with_stale_mood_does_not_affect_work_mood(solver, monkeypatch):
    occupy_beds(solver, "low")
    shift_off(solver)
    data = solver.op_data
    # 仅依赖配置和读取到的实际阵容；待命成员心情未知也不触发进房纠错。
    for name in DEEP[1:]:
        data.operators[name].time_stamp = None
        monkeypatch.setattr(
            data.operators[name],
            "current_mood",
            MagicMock(side_effect=AssertionError("standby mood is not work mood")),
        )
    assert data.average_mood() == 0
    assert solver.agent_get_mood() is None
    assert plan_metadata(data, [])


def test_restart_rebuilds_standby_from_observed_rooms(solver):
    occupy_beds(solver, "low")
    shift_off(solver)
    previous = solver.op_data
    observed = {room: previous.get_current_room(room, True) for room in previous.plan}
    assert solver.initialize_operators() is None
    assert solver.op_data is not previous
    for name, op in solver.op_data.operators.items():
        op.mood = previous.operators[name].mood
        op.time_stamp = datetime.now()
    apply_plan(solver, observed)
    for name in DEEP[1:]:
        solver.op_data.operators[name].time_stamp = None
    assert all(solver.op_data.is_group_standby(n) for n in DEEP[1:])
    assert solver.agent_get_mood() is None
    assert solver.tasks == []


def test_missing_cover_is_repaired_without_recalling_standby_group(solver):
    occupy_beds(solver, "low")
    shift_off(solver)
    apply_plan(solver, {"meeting": ["Free", "Current"]})
    assert not solver.op_data.is_group_standby(DEEP[1])
    assert solver.agent_get_mood() == "self_correction"
    plan = solver.tasks.pop().plan
    assert plan == {"meeting": [COVERS[1], "Current"]}
    apply_plan(solver, plan)
    for _ in range(3):
        assert solver.agent_get_mood() is None
        assert solver.tasks == []


@pytest.mark.parametrize(
    "invalid", ["anchor_working", "wrong_room", "priority_changed"]
)
def test_standby_does_not_hide_invalid_group_state(solver, invalid):
    occupy_beds(solver, "low")
    shift_off(solver)
    data = solver.op_data
    if invalid == "anchor_working":
        apply_plan(solver, {"central": [DEEP[0]]})
    elif invalid == "wrong_room":
        data.operators[DEEP[1]].current_room = "contact"
    else:
        data.operators[DEEP[1]].resting_priority = "high"
    assert not data.is_group_standby(DEEP[1])


def test_ordinary_low_cannot_evict_resting_main_or_another_replacement(solver):
    occupy_beds(solver, "replacement")
    data = solver.op_data
    data.add(Operator("年", "", mood=5))
    room, index = data.dorm[0].position
    names = ["Current"] * 5
    names[index] = "年"
    apply_plan(solver, {room: names})
    assert data.assign_dorm(COVERS[0]) is None
    shift_off(solver)
    assert data.assign_dorm(COVERS[0]) is None
