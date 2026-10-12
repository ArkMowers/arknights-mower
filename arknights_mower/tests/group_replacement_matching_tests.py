"""共享替班冲突不能阻止已有完整替班方案的整组下班。"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.exhaust_replacement import plan_exhaust_support  # noqa: E402
from arknights_mower.utils.log import logger  # noqa: E402
from arknights_mower.utils.operators import Operator, Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import try_reorder  # noqa: E402

MEMBERS = ["令", "絮雨", "黑键", "迷迭香", "苍苔"]


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(logger, "disabled", True)
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.rescue_threshold = 0
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    rooms = {
        "central": [Room("令", "感知", ["Mon3tr"])],
        "contact": [Room("絮雨", "感知", ["斥罪"])],
        "room_1_1": [Room("黑键", "感知", ["伺夜"])],
        "room_3_3": [Room("迷迭香", "感知", ["结城理", "酒神"])],
        "room_2_2": [Room("苍苔", "感知", ["槐琥", "引星棘刺", "结城理"])],
    }
    for index, residents in enumerate([("冰酿", "闪灵"), ("塑心", "杜林")], 1):
        rooms[f"dormitory_{index}"] = [
            *[Room(name, "", []) for name in residents],
            *[Room("Free", "", []) for _ in range(3)],
        ]
    data = Operators(
        {
            "default_plan": Plan(
                rooms,
                PlanConfig("", "", ""),
            ),
            "backup_plans": [],
        }
    )
    assert data.init_and_validate() is None
    now = datetime.now()
    for operator in data.operators.values():
        operator.mood, operator.time_stamp, operator.depletion_rate = 24, now, 0
        operator._current_room, operator.current_index = operator.room, operator.index
    for index, name in enumerate(MEMBERS):
        data.operators[name].mood = 5 + index
    for name in ("槐琥", "引星棘刺"):
        data.operators[name]._current_room = "meeting"
        data.operators[name].current_index = 0
    instance = object.__new__(base_schedule.BaseSchedulerSolver)
    instance.op_data, instance.tasks = data, []
    instance.check_fia = MagicMock(return_value=(None, None))
    instance._refresh_deferred_product_reservations = MagicMock()
    return instance


def test_perception_group_reassigns_shared_cover_and_admits_every_member(solver):
    data = solver.op_data
    plan, replacements = {}, []
    solver.get_resting_plan(MEMBERS.copy(), replacements, plan, 0)
    assert plan["room_3_3"] == ["酒神"]
    assert plan["room_2_2"] == ["结城理"]
    assert len(replacements) == len(set(replacements)) == len(MEMBERS)
    dorm_plan = try_reorder(data, plan)
    assert set(MEMBERS) <= {name for room in dorm_plan.values() for name in room}
    assert all(
        data.operators[name].current_room == data.operators[name].room
        for name in MEMBERS
    )


@pytest.mark.parametrize("failure", ["missing_cover", "no_beds", "reserved_cover"])
def test_failed_group_preserves_existing_plan_and_beds(solver, failure):
    data = solver.op_data
    replacements = ["陈"]
    plan = {"meeting": ["陈"]}
    if failure == "missing_cover":
        data.operators["迷迭香"].replacement = ["结城理"]
    elif failure == "reserved_cover":
        replacements.append("酒神")
    else:
        for index, bed in enumerate(data.dorm):
            name = ["银灰", "能天使", "讯使", "鸿雪", "温蒂", "清流"][index]
            data.add(
                Operator(
                    name,
                    "meeting",
                    operator_type="high",
                    resting_priority="high",
                    mood=0,
                )
            )
            resident = data.operators[name]
            resident._current_room, resident.current_index = bed.position
            bed.name, bed.time = name, datetime.now() + timedelta(hours=5)
    before_beds = [(bed.name, bed.time) for bed in data.dorm]
    before_replacements = replacements.copy()
    solver.get_resting_plan(MEMBERS.copy(), replacements, plan, 0)
    assert plan == {"meeting": ["陈"]}
    assert replacements == before_replacements
    assert [(bed.name, bed.time) for bed in data.dorm] == before_beds


def test_failed_group_reports_actual_shared_cover_shortage(solver, monkeypatch):
    solver.op_data.operators["迷迭香"].replacement = ["结城理"]
    recorded = MagicMock()
    monkeypatch.setattr(logger, "debug", recorded)
    plan, replacements = {}, []
    solver.get_resting_plan(MEMBERS.copy(), replacements, plan, 0)
    message, _, shortage, unmatched, options = recorded.call_args.args
    assert "未匹配成员" in message
    assert shortage == 1
    assert unmatched == ["苍苔"]
    assert options["迷迭香"] == options["苍苔"] == ["结城理"]
    assert plan == {} and replacements == []


def test_mass_recovery_takes_legacy_idle_beds_regardless_of_completion(solver):
    data = solver.op_data
    data.rescue_mode = True
    for name, mood in [("埃癸斯", 24), ("苏苏洛", 0)]:
        data.add(Operator(name, "", mood=mood))
    for bed, name in zip(data.dorm, ["埃癸斯", "苏苏洛"]):
        op = data.operators[name]
        op._current_room, op.current_index = bed.position
        op.time_stamp = datetime.now()
        bed.name, bed.time = name, datetime.now() + timedelta(hours=5)
    assert data._slot_takable(data.dorm[0], requester="令")
    assert data._slot_takable(data.dorm[1], requester="令")


def test_shared_covers_keep_original_preferences_when_already_feasible(solver):
    data = solver.op_data
    data.operators["苍苔"].replacement.append("陈")
    data.add(Operator("陈", "", mood=24))
    plan = {}
    solver.get_resting_plan(MEMBERS.copy(), [], plan, 0)
    assert plan["room_3_3"] == ["结城理"]
    assert plan["room_2_2"] == ["陈"]


def test_resting_attempts_failed_group_once_and_retries_next_round(solver):
    data = solver.op_data
    solver.total_agent = [data.operators[name] for name in MEMBERS]
    solver.plan_metadata = MagicMock()
    solver.get_resting_plan = MagicMock(wraps=solver.get_resting_plan)
    data.operators["迷迭香"].replacement = ["结城理"]
    assert solver.resting() == {}
    assert solver.get_resting_plan.call_count == 1
    assert solver.tasks == []
    solver.get_resting_plan.reset_mock()
    data.operators["迷迭香"].replacement.append("酒神")
    plan = solver.resting()
    assert plan["room_3_3"] == ["酒神"]
    assert plan["room_2_2"] == ["结城理"]
    assert solver.get_resting_plan.call_count == 1
    assert len(solver.tasks) == 1


def test_full_member_does_not_prevent_later_low_member_from_triggering_group(solver):
    data = solver.op_data
    data.operators["令"].mood = 24
    data.operators["令"].lower_limit = 23
    solver.total_agent = [data.operators[name] for name in MEMBERS]
    solver.plan_metadata = MagicMock()
    solver.get_resting_plan = MagicMock(wraps=solver.get_resting_plan)
    plan = solver.resting()
    assert solver.total_agent[0].name == "令"
    assert plan["room_3_3"] == ["酒神"]
    assert plan["room_2_2"] == ["结城理"]
    assert solver.get_resting_plan.call_count == 1


def test_exhaust_support_accepts_complete_shared_free_cover_matching(solver):
    can_rest = MagicMock(return_value=True)
    assert (
        plan_exhaust_support(
            solver.op_data, MEMBERS.copy(), can_rest, lambda name: False
        )
        == {}
    )
    can_rest.assert_called_once()


@pytest.mark.parametrize("with_trade_order", [False, True])
def test_only_ordinary_cover_at_mood_floor_allows_group_shift(solver, with_trade_order):
    data = solver.op_data
    if with_trade_order:
        data.operators["令"].replacement.append("但书")
        data.add(Operator("但书", ""))
    cover = data.operators["Mon3tr"]
    cover.mood, cover.lower_limit = 0, 0
    before = {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    plan, replacements = {}, []

    solver.get_resting_plan(MEMBERS.copy(), replacements, plan, 0)

    assert plan["central"] == ["Mon3tr"]
    assert len(replacements) == len(set(replacements)) == len(MEMBERS)
    assert set(MEMBERS) <= {
        name for row in try_reorder(data, plan).values() for name in row
    }
    assert cover.current_room == ""
    assert {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    } == before


@pytest.mark.parametrize("runtime_flag", [False, True])
def test_configured_zero_mood_cover_keeps_priority_and_admits_group(
    solver, runtime_flag
):
    data = solver.op_data
    primary = data.operators["令"]
    primary.replacement.append("红")
    data.add(Operator("红", "", mood=24, time_stamp=datetime.now()))
    data.config.workaholic = ["Mon3tr"]
    cover = data.operators["Mon3tr"]
    cover.workaholic = runtime_flag
    cover.mood, cover.lower_limit = 0, 0
    plan = {}

    solver.get_resting_plan(MEMBERS.copy(), [], plan, 0)

    assert plan["central"] == ["Mon3tr"]
    assert data.replacement_candidates(primary) == ["Mon3tr", "红"]


def test_zero_mood_configuration_reaches_shu_as_a_replacement(solver):
    data = solver.op_data
    data.config.workaholic = ["黍"]
    data.operators["令"].replacement = ["黍", "红"]
    data.add(Operator("黍", "", mood=0, time_stamp=datetime.now()))
    data.add(Operator("红", "", mood=24, time_stamp=datetime.now()))
    assert data.operators["黍"].workaholic
    plan = {}

    solver.get_resting_plan(MEMBERS.copy(), [], plan, 0)

    assert plan["central"] == ["黍"]


@pytest.mark.parametrize("configuration", ["inherit", "add", "remove"])
def test_zero_mood_cover_uses_effective_backup_configuration(solver, configuration):
    data = solver.op_data
    data.global_plan["default_plan"].plan["central"][0].replacement.append("红")
    data.global_plan["default_plan"].config.workaholic = (
        [] if configuration == "add" else ["Mon3tr"]
    )
    data.backup_plans.append(
        Plan(
            {},
            PlanConfig(
                "",
                "",
                "",
                workaholic="Mon3tr" if configuration == "add" else "",
                removed_operators=(
                    {"workaholic": "Mon3tr"} if configuration == "remove" else {}
                ),
            ),
        )
    )
    assert data.swap_plan([True], refresh=True) is None
    data.operators["Mon3tr"].mood = 0
    data.operators["Mon3tr"].time_stamp = datetime.now()
    data.operators["红"].time_stamp = datetime.now()
    plan = {}

    solver.get_resting_plan(MEMBERS.copy(), [], plan, 0)

    assert plan["central"] == ["红" if configuration == "remove" else "Mon3tr"]
    assert data.operators["Mon3tr"].workaholic is (configuration != "remove")


@pytest.mark.parametrize("other_cover_busy", [False, True])
def test_multiple_ordinary_covers_retain_mood_filter(solver, other_cover_busy):
    data = solver.op_data
    data.operators["令"].replacement.append("红")
    data.add(Operator("红", "", mood=24, time_stamp=datetime.now()))
    data.operators["Mon3tr"].mood = 0
    if other_cover_busy:
        data.operators["红"].current_room = "meeting"
        data.operators["红"].current_index = 0
    plan = {}

    solver.get_resting_plan(MEMBERS.copy(), [], plan, 0)

    if other_cover_busy:
        assert plan == {}
    else:
        assert plan["central"] == ["红"]


@pytest.mark.parametrize("blocked", ["working", "reserved", "mastery"])
def test_only_exhausted_cover_retains_other_admission_checks(
    solver, monkeypatch, blocked
):
    data = solver.op_data
    cover = data.operators["Mon3tr"]
    cover.mood = 0
    data.config.workaholic = [cover.name]
    if blocked == "working":
        cover.current_room, cover.current_index = "meeting", 0
    elif blocked == "reserved":
        data.reserved_product_replacements.add(cover.name)
    else:
        monkeypatch.setattr(
            base_schedule, "_is_mastery_busy", lambda name: name == cover.name
        )
    before = [(bed.name, bed.time) for bed in data.dorm]
    plan, replacements = {}, []

    solver.get_resting_plan(MEMBERS.copy(), replacements, plan, 0)

    assert plan == {} and replacements == []
    assert [(bed.name, bed.time) for bed in data.dorm] == before


def test_exhaust_support_coordinates_only_unmatched_member_after_group_matching(solver):
    data = solver.op_data
    for operator in (
        Operator(
            "芙兰卡",
            "room_1_2",
            index=0,
            replacement=["陈"],
            operator_type="high",
            mood=0,
        ),
        Operator(
            "能天使",
            "room_1_3",
            index=0,
            replacement=["陈", "红"],
            operator_type="high",
            mood=5,
        ),
        Operator("陈", "", mood=24),
        Operator("红", "", mood=24),
    ):
        data.add(operator)
        operator.time_stamp = datetime.now()
    data.plan["room_1_2"] = [Room("芙兰卡", "", ["陈"])]
    data.plan["room_1_3"] = [Room("能天使", "", ["陈", "红"])]
    data.operators["芙兰卡"]._current_room = "room_1_2"
    data.operators["陈"]._current_room = "room_1_3"
    data.operators["陈"].current_index = 0
    bed = data.dorm[-1]
    data.operators["能天使"]._current_room, data.operators["能天使"].current_index = (
        bed.position
    )
    bed.name, bed.time = "能天使", datetime.now() + timedelta(hours=5)
    before = [(candidate.name, candidate.time) for candidate in data.dorm]
    can_rest = MagicMock(return_value=True)
    assert plan_exhaust_support(
        data, [*MEMBERS, "芙兰卡"], can_rest, lambda name: False
    ) == {"room_1_3": ["红"]}
    assert data.operators["陈"].current_room == "room_1_3"
    assert [(candidate.name, candidate.time) for candidate in data.dorm] == before
    can_rest.assert_called_once()
