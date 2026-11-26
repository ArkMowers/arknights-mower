"""普通下班按心情余量分配替班和床位。"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.utils import config, operators  # noqa: E402
from arknights_mower.utils.log import logger  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import try_reorder  # noqa: E402


@pytest.fixture
def solver(monkeypatch, request):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base, "_is_mastery_busy", lambda name: False)
    monkeypatch.setattr(logger, "disabled", True)
    config.conf.enable_mastery = False
    config.conf.rescue_threshold = 0
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.global_plan = {
        "default_plan": Plan(
            {
                "central": [
                    Room("令", "感知", ["Mon3tr"]),
                    Room("歌蕾蒂娅", "深海", ["夕"]),
                ],
                "room_1_1": [Room("黑键", "感知", ["伺夜"])],
                "room_2_1": [Room("幽灵鲨", "深海", ["伺夜"])],
                "dormitory_1": [
                    Room("杜林", "", []),
                    Room("闪灵", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
                "dormitory_2": [
                    Room("冰酿", "", []),
                    Room("蜜莓", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            PlanConfig(
                "",
                "",
                "",
                ope_resting_priority="歌蕾蒂娅",
            ),
        ),
        "backup_plans": [],
    }
    aliases = getattr(request, "param", None)
    if isinstance(aliases, dict):
        for slots in instance.global_plan["default_plan"].plan.values():
            for slot in slots:
                slot.group = aliases.get(slot.group, slot.group)
    assert instance.initialize_operators() is None
    monkeypatch.setattr(operators.Operators, "current_room_changed_callback", None)
    for op in instance.op_data.operators.values():
        op.current_room, op.current_index = op.room, op.index
        op.time_stamp = datetime.now()
        op.mood = 24
        op.depletion_rate = 0
    instance.op_data.operators["令"].mood = 0
    instance.op_data.operators["歌蕾蒂娅"].mood = 10
    instance.tasks = []
    instance.task = None
    instance.plan_metadata = MagicMock()
    instance.check_fia = MagicMock(return_value=({}, None))
    instance.total_agent = [
        instance.op_data.operators[name]
        for name in ("歌蕾蒂娅", "幽灵鲨", "令", "黑键")
    ]
    return instance


@pytest.mark.parametrize("priority", ["high", "low"])
def test_dorm_priority_does_not_take_shared_cover_from_exhausted_group(
    solver, priority
):
    data = solver.op_data
    data.operators["令"].resting_priority = priority

    plan = solver.resting()

    assert plan["central"] == ["Mon3tr", "Current"]
    assert plan["room_1_1"] == ["伺夜"]
    assert "room_2_1" not in plan
    assert {bed.name for bed in data.dorm if bed.name} == {"令", "黑键"}
    assert data.config.ope_resting_priority == ["歌蕾蒂娅"]


def test_low_mood_standby_does_not_initiate_group_or_take_shared_cover(solver):
    data = solver.op_data
    data.operators["令"].resting_priority = "standby"
    data.config.resting_standby = ["令"]

    plan = solver.resting()

    assert plan["central"] == ["Current", "夕"]
    assert plan["room_2_1"] == ["伺夜"]
    assert "room_1_1" not in plan
    assert {bed.name for bed in data.dorm if bed.name} == {"歌蕾蒂娅", "幽灵鲨"}


def test_shift_off_keeps_original_mood_margin_against_lower_limit(solver):
    config.conf.rescue_threshold = 0
    data = solver.op_data
    data.operators["令"].mood = 8
    data.operators["令"].lower_limit = 12
    data.operators["歌蕾蒂娅"].mood = 1

    plan = solver.resting()

    assert plan["central"] == ["Mon3tr", "Current"]
    assert plan["room_1_1"] == ["伺夜"]


@pytest.mark.parametrize(
    "evidence",
    [
        "rate",
        "countdown",
        "different_member",
        "unknown_after",
        "unknown_between",
        "incomplete_group",
        "different_seat",
        "observed_seat",
        "source_observed_first",
        "position_without_mood",
        "projected_seat",
        "projected_countdown",
        "projected_same_seat",
        "legacy_full_mood_timer",
        "prediction_and_card",
        "unknown",
        "newer_card",
        "at_floor",
        "above_threshold",
        "equal_time",
        "smaller_margin",
    ],
)
def test_shared_cover_is_assigned_by_mood_margin(solver, evidence):
    data = solver.op_data
    now = data._projection_now = datetime.now()
    slow, fast = (data.operators[name] for name in ("令", "歌蕾蒂娅"))
    slow.mood, slow.lower_limit, slow.depletion_rate = 6, 4, 0.5
    fast.mood, fast.lower_limit, fast.depletion_rate = 4, 0, 2
    slow.time_stamp = fast.time_stamp = now
    if evidence == "countdown":
        fast.depletion_rate = 0.25
        fast.exhaust_time = now + timedelta(hours=2)
    elif evidence == "different_member":
        fast.mood = 23
        other = data.operators["幽灵鲨"]
        other.mood, other.time_stamp, other.depletion_rate = 4, now, 2
    elif evidence in ("unknown_after", "unknown_between"):
        data.operators["黑键"].mood = 8 if evidence == "unknown_after" else 3
    elif evidence == "incomplete_group":
        fast.replacement = []
    elif evidence == "different_seat":
        fast.current_index = 4
    elif evidence == "position_without_mood":
        fast.current_index = 2
        fast.time_stamp = now - timedelta(hours=1)
        data.update_detail(fast.name, 8, fast.room, fast.index, update_time=False)
        data.update_detail(fast.name, 4, fast.room, fast.index, update_time=True)
        data._projection_now = fast.time_stamp
        assert fast.depletion_rate == 0
    elif evidence in ("observed_seat", "source_observed_first"):
        if evidence == "source_observed_first":
            fast.current_room, fast.current_index = "room_1_1", 1
            solver._reconcile_room_observation(
                "room_1_1", [{"agent": "黑键"}, {"agent": ""}]
            )
            assert (fast.current_room, fast.time_stamp) == ("", None)
        else:
            fast.current_index = 2
        fast.exhaust_time = now + timedelta(minutes=1)
        data.update_detail(
            fast.name, fast.mood, fast.room, fast.index, update_time=True
        )
        data._projection_now = fast.time_stamp
        assert fast.depletion_rate == 0 and fast.exhaust_time is None
    elif evidence.startswith("projected_"):
        if evidence != "projected_same_seat":
            fast.current_index = 2
        if evidence == "projected_countdown":
            fast.exhaust_time = now + timedelta(minutes=1)
        projected = data.project_arrangements(
            [{"central": ["Current", fast.name]}], now=now
        ).project_arrangements([], now=now)
        assert fast.current_index == (1 if evidence == "projected_same_seat" else 2)
        solver.op_data = data = projected
        solver.total_agent = [data.operators[op.name] for op in solver.total_agent]
    elif evidence == "legacy_full_mood_timer":
        data.config.resting_threshold = 0.9
        slow.mood, slow.lower_limit, slow.depletion_rate = 24, 19, 1
        slow.time_stamp = now - timedelta(hours=2)
        slow.exhaust_time = slow.time_stamp + timedelta(milliseconds=2)
        fast.mood, fast.depletion_rate = 4, 4
    elif evidence == "prediction_and_card":
        slow.mood_is_prediction = True
        data.dorm_mood_estimates[slow.name] = (6, now)
    elif evidence == "unknown":
        slow.depletion_rate = 0
    elif evidence == "newer_card":
        slow.time_stamp -= timedelta(minutes=5)
        data.dorm_mood_estimates[slow.name] = (6, now)
    elif evidence == "at_floor":
        slow.mood = slow.lower_limit
    elif evidence == "above_threshold":
        fast.mood, fast.depletion_rate = 23, 50
    elif evidence == "equal_time":
        fast.depletion_rate = 1
    elif evidence == "smaller_margin":
        fast.mood = 1

    plan = solver.resting()

    if evidence == "smaller_margin":
        assert plan["central"] == ["Current", "夕"]
        assert plan["room_2_1"] == ["伺夜"]
        assert {bed.name for bed in data.dorm if bed.name} == {"歌蕾蒂娅", "幽灵鲨"}
    else:
        assert plan["central"] == ["Mon3tr", "Current"]
        assert plan["room_1_1"] == ["伺夜"]
        assert {bed.name for bed in data.dorm if bed.name} == {"令", "黑键"}


@pytest.mark.parametrize("solver", [{"深海": "甲", "感知": "乙"}], indirect=True)
@pytest.mark.parametrize("hunter_in_dorm", [False, True])
def test_tidal_watch_keeps_shared_cover_with_the_smaller_mood_margin(
    solver, monkeypatch, hunter_in_dorm
):
    from arknights_mower.tests.mood_calculation_consumers_tests import set_e0_box

    data = solver.op_data
    now = data._projection_now = datetime.now()
    for room, slots in data.plan.items():
        if room.startswith("room_"):
            for slot in slots:
                slot.facility = "manufacture"
    hunter = operators.Operator("斯卡蒂", "")
    data.add(hunter)
    hunter.current_room, hunter.current_index = (
        ("dormitory_2", 4) if hunter_in_dorm else ("room_1_1", 1)
    )
    set_e0_box(monkeypatch, data.operators)
    monkeypatch.setattr(data.runtime_conf or config.conf, "test_mood_calculation", True)
    slow, fast = data.operators["令"], data.operators["歌蕾蒂娅"]
    slow.lower_limit = fast.lower_limit = 0
    for name in data.operators:
        data.mood_model.observe(name, {slow.name: 2, fast.name: 3}.get(name, 24), now)

    plan = solver.resting()

    assert plan["central"] == ["Mon3tr", "Current"]
    assert {bed.name for bed in data.dorm if bed.name} == {"令", "黑键"}


def test_dorm_priority_still_assigns_first_bed_within_selected_group(solver):
    data = solver.op_data
    data.config.ope_resting_priority = ["黑键"]
    data.operators["黑键"].mood = 10

    plan = solver.resting()
    dorm_plan = try_reorder(data, plan)

    assert plan["room_1_1"] == ["伺夜"]
    room, index = data.dorm[0].position
    assert dorm_plan[room][index] == "黑键"
    assert "令" in {name for names in dorm_plan.values() for name in names}


def test_idle_fill_waits_until_working_group_has_reserved_beds(solver):
    data = solver.op_data
    data.add(operators.Operator("红", "", mood=0, time_stamp=datetime.now()))
    solver.total_agent.insert(0, data.operators["红"])
    # 只留整组所需的两个床位，普通补床不能先占一个而阻止整组下班。
    data.dorm = data.dorm[:2]

    plan = solver.resting()

    assert plan["room_1_1"] == ["伺夜"]
    assert {bed.name for bed in data.dorm} == {"令", "黑键"}


@pytest.mark.parametrize("solver", [True], indirect=True)
def test_newcomer_uses_vip_vacated_by_same_shift_replacement(solver):
    config.conf.rescue_threshold = 0
    data = solver.op_data
    first = "dormitory_1"
    # 首个宿舍只剩一个动态床位，正被本轮即将上岗的替班占用。
    for index, name in ((3, "红"), (4, "陈")):
        data.plan[first][index] = Room(name, "", [])
    data.dorm = [bed for bed in data.dorm if data.is_effective_free_slot(bed)]
    cover = data.operators["Mon3tr"]
    cover.current_room, cover.current_index = first, 2
    data.dorm[0].name = cover.name
    data.config.ope_resting_priority = ["黑键"]
    data.operators["黑键"].mood = 8

    work_plan = solver.resting()

    assert work_plan["central"][0] == "Mon3tr"
    assert next(bed for bed in data.dorm if bed.name == "黑键").position == (first, 2)
    assert (cover.current_room, cover.current_index) == (first, 2)
    dorm_plan = try_reorder(data, work_plan)
    assert dorm_plan[first] == ["Current", "Current", "黑键", "Current", "Current"]
    projected = data.project_arrangements([work_plan, dorm_plan])
    assert projected.operators["Mon3tr"].current_room == "central"
    assert projected.get_dorm_by_name("黑键")[1].position == (first, 2)
    assert sorted(bed.name for bed in projected.dorm if bed.name) == ["令", "黑键"]
    assert try_reorder(projected, {}) == {}
