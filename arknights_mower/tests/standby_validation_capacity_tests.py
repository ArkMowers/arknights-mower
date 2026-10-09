"""排班校验按必需恢复成员计算床位，候补仍需完整替班。"""

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import try_reorder  # noqa: E402

WORKERS = ["陈", "银灰", "能天使", "讯使", "芬", "翎羽", "香草", "年"]
COVERS = ["夜莺", "砾", "红", "黑角", "初雪", "杜宾", "梅尔", "赫默"]
GROUP = "sees队"


@pytest.fixture
def plan(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base_schedule.logger, "disabled", True)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    rows = [Room(name, GROUP, [cover]) for name, cover in zip(WORKERS, COVERS)]
    rooms = {"central": rows[:5], "room_1_1": rows[5:]}
    for index, residents in enumerate(
        [("杜林", "蜜莓"), ("塑心", "冰酿"), ("流明", "闪灵")], 1
    ):
        rooms[f"dormitory_{index}"] = [
            *[Room(name, "", []) for name in residents],
            *[Room("Free", "", []) for _ in range(3)],
        ]
    rooms["dormitory_3"][2:4] = [Room("温蒂", "", []), Room("清流", "", [])]
    rooms["dormitory_1"][0] = Room("杜林", GROUP, ["炎熔"])
    return {
        "default_plan": Plan(
            rooms, PlanConfig("", "", "", resting_standby=",".join(WORKERS[-3:]))
        ),
        "backup_plans": [],
    }


@pytest.mark.parametrize("multi_group", [False, True])
@pytest.mark.parametrize("standby_mood", [5, 20])
def test_eight_workers_with_three_standby_validate_and_shift_with_seven_beds(
    plan, multi_group, standby_mood
):
    if multi_group:
        candidate = plan["default_plan"].plan["room_1_1"][2]
        candidate.group = "另一组"
        candidate.group_bindings = [{"group": GROUP, "replacement": [COVERS[-1]]}]
        plan["default_plan"].plan["contact"] = [Room("阿米娅", "另一组", ["苏苏洛"])]
    data = Operators(plan)
    assert data.init_and_validate() is None
    assert len(data.dorm) == 7
    for op in data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5, datetime.now()
    for name in WORKERS[-3:]:
        data.operators[name].mood = standby_mood
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.op_data, solver.tasks = data, []
    solver._refresh_deferred_product_reservations = lambda: None
    solver.check_fia = lambda: (None, None)
    arrangement, replacements = {}, []
    admitted = solver.get_resting_plan(
        data.groups[GROUP].copy(), replacements, arrangement, 0
    )
    if standby_mood == 5:
        assert not admitted
        assert arrangement == {} and replacements == []
        assert not any(bed.name for bed in data.all_dorms())
        return
    assert admitted
    beds = try_reorder(data, arrangement) or {}
    projected = data.project_arrangements([arrangement, beds])
    assert all(projected.get_dorm_by_name(name)[1] is not None for name in WORKERS[:5])
    assert any(projected.is_standby(name) for name in WORKERS[-3:])
    assert set(COVERS) <= set(replacements)


@pytest.mark.parametrize(
    "restriction", ["ordinary", "exhaust_require", "rest_in_full", "all_standby"]
)
def test_standby_setting_does_not_bypass_mandatory_recovery(plan, restriction):
    conf = plan["default_plan"].config
    if restriction == "ordinary":
        conf.resting_standby = []
    elif restriction == "all_standby":
        conf.resting_standby = WORKERS
    else:
        setattr(conf, restriction, WORKERS[-3:])
    assert Operators(plan).init_and_validate() == (
        f"{GROUP} 分组无法排班,所需宿舍数8大于当前有效宿舍数7"
    )


def test_standby_still_requires_unique_replacements(plan):
    plan["default_plan"].plan["room_1_1"][2].replacement = [COVERS[-2]]
    assert Operators(plan).init_and_validate() == f"{GROUP} 分组无法排班,替换组数量不够"


def test_fixed_standby_does_not_reduce_mandatory_bed_demand(plan):
    rooms = plan["default_plan"].plan
    rooms["dormitory_1"][0].replacement = [WORKERS[-1]]
    rooms["dormitory_1"][2:4] = [Room("车尔尼", "", []), Room("爱丽丝", "", [])]
    rooms["dormitory_2"][2] = Room("安赛尔", "", [])
    assert Operators(plan).init_and_validate() == (
        f"{GROUP} 分组无法排班,所需宿舍数5大于当前有效宿舍数4"
    )


def test_fixed_matching_prefers_required_workers_over_standby(plan):
    rooms = plan["default_plan"].plan
    rooms["dormitory_1"][0].replacement = [WORKERS[-1], WORKERS[0]]
    rooms["dormitory_1"][2:4] = [Room("车尔尼", "", []), Room("爱丽丝", "", [])]
    rooms["dormitory_2"][2] = Room("安赛尔", "", [])
    assert Operators(plan).init_and_validate() is None


@pytest.mark.parametrize("mandatory_backup", [False, True])
def test_backup_combinations_recheck_standby_eligibility(plan, mandatory_backup):
    plan["backup_plans"] = [
        Plan(
            {},
            PlanConfig(",".join(WORKERS[-3:]) if mandatory_backup else "", "", ""),
            name="回满限制",
        )
    ]
    data = Operators(plan)
    assert data.init_and_validate() is None
    result = data.validate_backup_plans()
    assert result["success"] is not mandatory_backup
    if mandatory_backup:
        assert "回满限制" in result["message"]
        assert "所需宿舍数8大于当前有效宿舍数7" in result["message"]
    assert data.config.resting_standby == WORKERS[-3:]
    assert data.operators[WORKERS[-1]].resting_priority == "standby"


@pytest.mark.parametrize("secondary", [False, True])
@pytest.mark.parametrize("working_state", [False, True])
def test_validation_counts_own_dynamic_free_capacity_without_live_state(
    plan, secondary, working_state
):
    conf = plan["default_plan"].config
    conf.resting_standby = []
    rooms = plan["default_plan"].plan
    if secondary:
        rooms["dormitory_1"][0] = Room(
            "杜林",
            "另一组",
            ["炎熔"],
            group_bindings=[{"group": GROUP, "replacement": ["Free"]}],
        )
        rooms["contact"] = [Room("阿米娅", "另一组", ["苏苏洛"])]
    else:
        rooms["dormitory_1"][0].replacement = ["Free"]
    data = Operators(plan)
    data.group_shift_state[GROUP] = not working_state
    assert data.init_and_validate() is None
    assert data.validate_backup_plans()["success"]
    data.group_shift_state[GROUP] = False
    for op in data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5, datetime.now()
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.op_data, solver.tasks = data, []
    solver._refresh_deferred_product_reservations = lambda: None
    solver.check_fia = lambda: (None, None)
    arrangement, replacements = {}, []
    assert solver.get_resting_plan(
        data.shift_group_members(GROUP), replacements, arrangement, 0
    )
    projected = data.project_arrangements(
        [arrangement, try_reorder(data, arrangement) or {}]
    )
    assert all(projected.get_dorm_by_name(name)[1] is not None for name in WORKERS)


@pytest.mark.parametrize("secondary", [False, True])
def test_validation_cannot_borrow_other_resting_groups_dynamic_free_capacity(
    plan, secondary
):
    plan["default_plan"].config.resting_standby = []
    rooms = plan["default_plan"].plan
    rooms["contact"] = [Room("阿米娅", "另一组", ["苏苏洛"])]
    if secondary:
        rooms["dormitory_1"][0] = Room(
            "杜林",
            GROUP,
            ["炎熔"],
            group_bindings=[{"group": "另一组", "replacement": ["Free"]}],
        )
    else:
        rooms["dormitory_1"][0] = Room("杜林", "另一组", ["Free"])
    data = Operators(plan)
    data.group_shift_state["另一组"] = True
    assert data.init_and_validate() == (
        f"{GROUP} 分组无法排班,所需宿舍数8大于当前有效宿舍数7"
    )


@pytest.mark.parametrize("closes_capacity", [False, True])
def test_backup_validation_rechecks_group_scoped_free_capacity(plan, closes_capacity):
    plan["default_plan"].config.resting_standby = []
    plan["default_plan"].plan["dormitory_1"][0].replacement = ["Free"]
    plan["backup_plans"] = [
        Plan(
            {
                "dormitory_1": [
                    Room("杜林", GROUP, ["炎熔"] if closes_capacity else ["Free"])
                ]
            },
            PlanConfig("", "", ""),
            name="宿管替班",
        )
    ]
    data = Operators(plan)
    assert data.init_and_validate() is None
    result = data.validate_backup_plans()
    assert result["success"] is not closes_capacity
    if closes_capacity:
        assert "所需宿舍数8大于当前有效宿舍数7" in result["message"]
