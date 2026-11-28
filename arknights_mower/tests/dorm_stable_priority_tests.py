"""宿舍事件按恢复层级分配快慢床位，同级保位且实际换床重新计时。"""

import copy
from datetime import datetime, timedelta
from itertools import product

import pytest

from arknights_mower.tests import dorm_release_tests, shift_backup_convergence_tests
from arknights_mower.tests.resting_priority_tests import set_tier
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Dormitory, Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.resting_priority import RestingTier, resting_tier
from arknights_mower.utils.scheduler_task import prioritize_new_dorm_recovery

op_data = dorm_release_tests.op_data
solver = shift_backup_convergence_tests.solver


@pytest.fixture
def residents(op_data):
    data = op_data
    data.plan.pop("dormitory_1")
    data.dorm = []
    for room, names in (
        ("dormitory_2", ["重岳", "絮雨", "乌尔比安"]),
        ("dormitory_3", ["夕", "安哲拉", "令"]),
        ("dormitory_4", ["乌有"]),
    ):
        fixed = ["杜林", "闪灵"] if len(names) == 3 else ["杜林"] * 4
        data.plan[room] = [Room(n, "", []) for n in fixed + ["Free"] * len(names)]
        for index, name in enumerate(names, len(fixed)):
            tier = (
                RestingTier.MAIN
                if name in ("重岳", "夕", "令", "乌有")
                else RestingTier.REPLACEMENT
            )
            op = set_tier(data, name, tier, 10)
            op.current_room, op.current_index = room, index
            data.dorm.append(Dormitory((room, index), name))
    data.global_plan["default_plan"].plan = copy.deepcopy(data.plan)
    return data


def occupant(data, room, index):
    op = data.get_current_operator(room, index)
    return op.name if op else ""


def test_arrival_moves_ling_to_earlier_ordinary_bed(residents):
    data = residents
    data.operators["令"].current_room, data.operators["令"].current_index = "central", 1
    data.dorm[-2].reset()
    original = copy.deepcopy([(b.position, b.name, b.time) for b in data.dorm])
    plan = {"dormitory_3": ["Current"] * 4 + ["令"]}

    result = prioritize_new_dorm_recovery(data, plan)
    projected = data.project_arrangements([result])

    assert "令" in projected.get_current_room("dormitory_2", True)[3:]
    assert occupant(projected, "dormitory_2", 2) == "重岳"
    assert occupant(projected, "dormitory_3", 2) == "夕"
    assert occupant(projected, "dormitory_4", 4) == "乌有"
    assert [(b.position, b.name, b.time) for b in data.dorm] == original
    assert plan == {"dormitory_3": ["Current"] * 4 + ["令"]}
    assert prioritize_new_dorm_recovery(projected, result) == result
    assert prioritize_new_dorm_recovery(projected, {}) == {}


def test_existing_higher_tier_target_can_take_earlier_target_on_departure(residents):
    data = residents
    set_tier(data, "重岳", RestingTier.PRIORITY_REPLACEMENT)
    data.operators["令"].mood = 24
    result = prioritize_new_dorm_recovery(
        data, {"dormitory_3": ["Current"] * 4 + ["Free"]}
    )
    projected = data.project_arrangements([result])
    assert (
        resting_tier(projected, occupant(projected, "dormitory_2", 2))
        == RestingTier.MAIN
    )
    assert "令" not in {b.name for b in projected.dorm}


def test_mood_changes_alone_do_not_fix_old_inversions(residents):
    residents.operators["令"].mood = 0
    assert prioritize_new_dorm_recovery(residents, {}) == {}


def test_cleaning_slow_tail_does_not_move_sorted_residents(residents):
    data = residents
    data.operators["令"].current_room, data.operators["令"].current_index = (
        "dormitory_2",
        3,
    )
    data.operators["絮雨"].current_room, data.operators["絮雨"].current_index = (
        "dormitory_3",
        4,
    )
    data.dorm[1].name, data.dorm[-2].name = "令", "絮雨"
    plan = {"dormitory_3": ["Current"] * 4 + ["Free"]}
    assert prioritize_new_dorm_recovery(data, plan) == plan


@pytest.mark.parametrize("lock", ["slot", "name"])
def test_priority_allocation_preserves_reserved_room(residents, lock):
    data = residents
    plan = {"dormitory_3": ["Current"] * 4 + ["Free"]}
    slots = {("dormitory_2", 3)} if lock == "slot" else set()
    names = {"絮雨"} if lock == "name" else set()
    result = prioritize_new_dorm_recovery(data, plan, slots, reserved_names=names)
    assert "dormitory_2" not in result


def test_custom_room_order_orders_ordinary_beds(residents):
    data = residents
    data.config.dorm_order = [
        "dormitory_3",
        "dormitory_2",
        "dormitory_4",
        "dormitory_1",
    ]
    # 新入住的低优替班不挤走同层级原住者，也不把令移到更慢的宿舍二。
    set_tier(data, "红", RestingTier.REPLACEMENT)
    result = prioritize_new_dorm_recovery(
        data, {"dormitory_2": ["Current"] * 4 + ["红"]}
    )
    projected = data.project_arrangements([result])
    assert occupant(projected, "dormitory_3", 4) == "令"


@pytest.mark.parametrize("ordinary_room", ["dormitory_2", "dormitory_3"])
def test_single_and_ordinary_orders_are_independent(residents, ordinary_room):
    data = residents
    other_room = "dormitory_3" if ordinary_room == "dormitory_2" else "dormitory_2"
    # 两类位置分别配置，单回顺序为 3→2→4，普通位顺序由参数决定。
    data.config.dorm_order = [
        "dormitory_3",
        "dormitory_2",
        "dormitory_4",
        f"{ordinary_room}_low",
        f"{other_room}_low",
    ]
    set_tier(data, "重岳", RestingTier.PRIORITY)
    set_tier(data, "夕", RestingTier.LOW_MAIN)
    result = prioritize_new_dorm_recovery(data, {}, configuration_changed=True)
    projected = data.project_arrangements([result])
    assert occupant(projected, "dormitory_3", 2) == "重岳"
    assert (
        resting_tier(projected, occupant(projected, "dormitory_2", 2))
        == RestingTier.MAIN
    )
    assert (
        resting_tier(projected, occupant(projected, "dormitory_4", 4))
        == RestingTier.MAIN
    )
    assert "夕" in projected.get_current_room(ordinary_room, True)[3:]
    assert prioritize_new_dorm_recovery(projected, {}, configuration_changed=True) == {}


def test_explicit_ordinary_group_can_precede_single_targets(residents):
    data = residents
    data.config.dorm_order = [
        "dormitory_3_low",
        "dormitory_2",
        "dormitory_3",
        "dormitory_4",
    ]
    set_tier(data, "令", RestingTier.PRIORITY)
    result = prioritize_new_dorm_recovery(data, {}, configuration_changed=True)
    projected = data.project_arrangements([result])
    assert "令" in projected.get_current_room("dormitory_3", True)[3:]
    assert occupant(projected, "dormitory_3", 2) == "乌有"
    assert prioritize_new_dorm_recovery(projected, {}, configuration_changed=True) == {}


def test_configuration_event_corrects_order_without_an_arrival(residents):
    data = residents
    result = prioritize_new_dorm_recovery(data, {}, configuration_changed=True)
    projected = data.project_arrangements([result])
    assert "令" in projected.get_current_room("dormitory_2", True)[3:]
    assert prioritize_new_dorm_recovery(projected, {}, configuration_changed=True) == {}


def test_reversed_order_correction_keeps_same_tier_targets(residents):
    data = residents
    data.config.dorm_order = [
        "dormitory_3",
        "dormitory_2",
        "dormitory_4",
        "dormitory_1",
    ]
    result = prioritize_new_dorm_recovery(data, {}, configuration_changed=True)
    projected = data.project_arrangements([result])
    assert result == {}
    assert occupant(projected, "dormitory_2", 2) == "重岳"
    assert occupant(projected, "dormitory_3", 2) == "夕"


def test_cross_room_projection_invalidates_all_affected_room_deadlines(residents):
    data = residents
    due = datetime.now() + timedelta(hours=3)
    for bed in data.dorm:
        bed.time = due
    projected = data.project_arrangements(
        [
            {
                "dormitory_2": ["Current"] * 3 + ["令", "Current"],
                "dormitory_3": ["Current"] * 4 + ["絮雨"],
            }
        ]
    )
    assert all(
        bed.time is None for bed in projected.dorm if bed.position[0] != "dormitory_4"
    )
    assert projected.dorm[-1].time == due
    assert all(bed.time == due for bed in data.dorm)


def test_projection_no_op_vacancies_preserve_room_deadlines(residents):
    data = residents
    data.get_dorm_by_name("乌尔比安")[1].reset()
    op = data.operators["乌尔比安"]
    op.current_room, op.current_index = "", -1
    due = datetime.now() + timedelta(hours=3)
    for bed in data.dorm:
        bed.time = due if bed.name else None
    projected = data.project_arrangements(
        [
            {
                "dormitory_2": ["Current"] * 4 + ["Free"],
                "dormitory_4": ["Current"] * 4 + ["乌有"],
            }
        ]
    )
    assert [(bed.name, bed.time) for bed in projected.dorm] == [
        (bed.name, due if bed.name else None) for bed in data.dorm
    ]


def test_batched_ordinary_clearance_fills_faster_beds_without_moving_targets(residents):
    data = residents
    # 两个较快普通床一起清空，只移动令和安哲拉，已有三个单回目标保位。
    plan = {"dormitory_2": ["Current"] * 3 + ["Free", "Free"]}
    result = prioritize_new_dorm_recovery(data, plan)
    projected = data.project_arrangements([result])
    assert "令" in projected.get_current_room("dormitory_2", True)[3:]
    assert occupant(projected, "dormitory_2", 2) == "重岳"
    assert occupant(projected, "dormitory_3", 2) == "夕"
    assert occupant(projected, "dormitory_4", 4) == "乌有"
    assert "安哲拉" in projected.get_current_room("dormitory_2", True)[3:]
    assert {bed.name for bed in projected.dorm if bed.name} == {
        "重岳",
        "夕",
        "令",
        "乌有",
        "安哲拉",
    }


def test_equal_speed_ordinary_slots_do_not_swap_for_tier_order(residents):
    data = residents
    data.operators["令"].current_room, data.operators["令"].current_index = (
        "dormitory_2",
        4,
    )
    (
        data.operators["乌尔比安"].current_room,
        data.operators["乌尔比安"].current_index,
    ) = "dormitory_3", 4
    data.dorm[2].name, data.dorm[-2].name = "令", "乌尔比安"
    assert prioritize_new_dorm_recovery(data, {}, configuration_changed=True) == {}


def test_only_full_fillers_do_not_move_to_empty_faster_beds(residents):
    data = residents
    for op in data.operators.values():
        op.mood = op.upper_limit
    plan = {"dormitory_2": ["Current", "Current", "Free", "Current", "Current"]}
    assert prioritize_new_dorm_recovery(data, plan) == plan


@pytest.mark.parametrize(
    "tiers",
    product(
        (RestingTier.MAIN, RestingTier.LOW_MAIN, RestingTier.REPLACEMENT), repeat=4
    ),
)
def test_all_tier_combinations_preserve_residents_and_converge(residents, tiers):
    data = residents
    for name, level in zip(("重岳", "夕", "令", "乌有"), tiers):
        set_tier(data, name, level)
    before = {bed.name for bed in data.dorm}
    result = prioritize_new_dorm_recovery(data, {}, configuration_changed=True)
    projected = data.project_arrangements([result])
    targets = [
        occupant(projected, room, index)
        for room, index in (("dormitory_2", 2), ("dormitory_3", 2), ("dormitory_4", 4))
    ]
    levels = [resting_tier(projected, name) for name in targets]
    for room in ("dormitory_2", "dormitory_3"):
        levels.extend(
            sorted(
                resting_tier(projected, name)
                for name in projected.get_current_room(room, True)[3:]
            )
        )
    assert levels == sorted(levels)
    assert {bed.name for bed in projected.dorm} == before
    assert prioritize_new_dorm_recovery(projected, {}, configuration_changed=True) == {}


def test_backup_order_only_change_reorders_ordinary_beds_and_keeps_equal_targets(
    solver,
):
    plans = copy.deepcopy(solver.op_data.global_plan)
    plans["default_plan"].plan["dormitory_2"] = [
        Room(name, "", []) for name in ["闪灵", "蜜莓", "Free", "Free", "Free"]
    ]
    plans["backup_plans"] = [
        Plan(
            {},
            PlanConfig("", "", "", dorm_order="dormitory_2,dormitory_1"),
            trigger=LogicExpression("True", "==", "True"),
        )
    ]
    solver.op_data = Operators(plans)
    assert solver.op_data.init_and_validate() is None
    for name in ("空爆", "年", "能天使"):
        solver.op_data.add(Operator(name, ""))
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "central": ["陈"],
                "room_1_2": ["酒神", "食铁兽"],
                "dormitory_1": ["杜林", "桃金娘", "薇薇安娜", "野鬃", "空爆"],
                "dormitory_2": ["闪灵", "蜜莓", "灰毫", "年", "能天使"],
            }
        ]
    )
    for op in solver.op_data.operators.values():
        op.mood, op.time_stamp = 12, datetime.now()
    before = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    generated = []
    assert solver.backup_plan_solver(generated_tasks=generated)
    projected = solver.op_data.project_arrangements([generated[0].plan])
    assert projected.operators["野鬃"].current_room == "dormitory_2"
    assert occupant(projected, "dormitory_1", 2) == "薇薇安娜"
    assert occupant(projected, "dormitory_2", 2) == "灰毫"
    assert {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    } == before


@pytest.mark.parametrize(
    "kind", ["ordinary", "due", "strict", "retained", "product", "emergency", "unnamed"]
)
def test_future_release_does_not_reserve_priority_reallocation(residents, kind):
    from arknights_mower.utils.dorm_candidates import dorm_task_reservations
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    data = residents
    task = SchedulerTask(
        time=datetime.now() + timedelta(hours=2),
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_3": ["Current"] * 4 + ["Free"]},
        meta_data="令",
    )
    if kind == "due":
        task.time = datetime.now() - timedelta(seconds=1)
    elif kind == "strict":
        task.strict_mood_limit = True
    elif kind == "retained":
        task.execution_retained = True
    elif kind == "product":
        task.product_shift_locked = True
    elif kind == "emergency":
        task.emergency_recovery_release = True
    elif kind == "unnamed":
        task.meta_data = ""
    before = copy.deepcopy(task.__dict__)
    names, slots = dorm_task_reservations(data, [task])
    assert (("dormitory_3", 4) in slots) == (kind != "ordinary")
    # 新入住触发重排时，高优主班应先于普通替班使用前排床位。
    plan = {"dormitory_4": ["Current"] * 4 + ["絮雨"]}
    result = prioritize_new_dorm_recovery(data, plan, slots, reserved_names=names)
    projected = data.project_arrangements([result])
    if kind == "ordinary":
        assert projected.operators["令"].current_room == "dormitory_4"
        assert prioritize_new_dorm_recovery(projected, {}) == {}
    else:
        assert (
            projected.operators["令"].current_room,
            projected.operators["令"].current_index,
        ) == ("dormitory_3", 4)
    assert task.__dict__ == before
