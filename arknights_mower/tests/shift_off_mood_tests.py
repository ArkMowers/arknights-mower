"""下班按剩余心情，宿舍优先级只参与床位分配。"""

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.utils import config, operators  # noqa: E402
from arknights_mower.utils.log import logger  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import try_reorder  # noqa: E402


@pytest.fixture(params=[False, True], ids=["legacy", "experimental"])
def solver(request, monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base, "_is_mastery_busy", lambda name: False)
    monkeypatch.setattr(logger, "disabled", True)
    config.conf.enable_mastery = False
    config.conf.experimental_dorm_logic = request.param
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
                experimental_dorm_logic=request.param,
            ),
        ),
        "backup_plans": [],
    }
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


@pytest.mark.parametrize("priority", ["high", "low", "standby"])
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


def test_shift_off_keeps_original_mood_margin_against_lower_limit(solver):
    data = solver.op_data
    data.operators["令"].mood = 8
    data.operators["令"].lower_limit = 12
    data.operators["歌蕾蒂娅"].mood = 1

    plan = solver.resting()

    assert plan["central"] == ["Mon3tr", "Current"]
    assert plan["room_1_1"] == ["伺夜"]


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
    data = solver.op_data
    first, second = "dormitory_1", "dormitory_2"
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
    assert next(bed for bed in data.dorm if bed.name == "黑键").position[0] == second
    dorm_plan = try_reorder(data, work_plan)
    assert dorm_plan[first] == ["Current", "Current", "黑键", "Current", "Current"]
    projected = data.project_arrangements([work_plan, dorm_plan])
    assert projected.operators["Mon3tr"].current_room == "central"
    assert projected.get_dorm_by_name("黑键")[1].position == (first, 2)
    assert sorted(bed.name for bed in projected.dorm if bed.name) == ["令", "黑键"]
    assert try_reorder(projected, {}) == {}
