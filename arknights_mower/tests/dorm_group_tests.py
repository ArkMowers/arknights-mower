"""宿舍成员跟随工作组换班，固定岗位不占用轮休床位。"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.operators import Operator  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    generate_plan_by_drom,
    try_reorder,
)


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    config.conf.enable_mastery = False
    instance = object.__new__(BaseSchedulerSolver)
    instance.global_plan = {
        "default_plan": Plan(
            {
                "meeting": [
                    Room("伊内丝", "联动", ["陈"]),
                    Room("银灰", "联动", ["初雪"]),
                ],
                "contact": [Room("讯使", "联动", ["红"])],
                "dormitory_1": [
                    Room("塑心", "联动", ["黑角"]),
                    Room("冰酿", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            PlanConfig("", "", ""),
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
    for name in ["泥岩", "能天使", "年"]:
        instance.op_data.add(Operator(name, ""))
    actual = {
        "meeting": ["伊内丝", "银灰"],
        "contact": ["讯使"],
        "dormitory_1": ["塑心", "冰酿", "泥岩", "能天使", "年"],
    }
    apply_plan(instance, actual)
    for op in instance.op_data.operators.values():
        op.time_stamp = datetime.now()
        op.mood = 5 if op.group and not op.room.startswith("dorm") else 24
    return instance


def apply_plan(solver, plan):
    for room, names in plan.items():
        for index, name in enumerate(names):
            if name in ("Current", "Free"):
                continue
            for op in solver.op_data.operators.values():
                if op.current_room == room and op.current_index == index:
                    op.current_room, op.current_index = "", -1
            op = solver.op_data.operators[name]
            op.current_room, op.current_index = room, index
            op.time_stamp = datetime.now()
    for dorm in solver.op_data.dorm:
        op = solver.op_data.get_current_operator(*dorm.position)
        dorm.name = op.name if op else ""
        dorm.time = datetime.now() + timedelta(hours=4) if op else None


def shift_off(solver):
    plan, replacements = {}, []
    solver.get_resting_plan(solver.op_data.groups["联动"], replacements, plan, 0)
    beds = try_reorder(solver.op_data, plan)
    apply_plan(solver, plan)
    apply_plan(solver, beds)
    return plan, replacements


def test_group_larger_than_bed_count_validates_and_round_trip_converges(solver):
    data = solver.op_data
    assert len(data.groups["联动"]) == 4
    assert len(data.dorm) == 3
    original_order = data.groups["联动"].copy()
    plan, replacements = shift_off(solver)
    assert plan == {
        "meeting": ["陈", "初雪"],
        "contact": ["红"],
        "dormitory_1": ["黑角", "Current", "Current", "Current", "Current"],
    }
    assert len(replacements) == len(set(replacements)) == 4
    assert {d.name for d in data.dorm} == {"伊内丝", "银灰", "讯使"}
    assert data.operators["塑心"].current_room == ""
    assert data.groups["联动"] == original_order
    assert solver.agent_get_mood() is None
    assert solver.tasks == []
    tasks = generate_plan_by_drom(
        {datetime.now() + timedelta(hours=4): (data.dorm, True)}, data
    )
    assert len(tasks) == 1
    assert tasks[0].type == TaskTypes.SHIFT_ON
    assert tasks[0].plan["dormitory_1"][0] == "塑心"
    apply_plan(solver, tasks[0].plan)
    assert solver.agent_get_mood(skip_dorm=True) is None
    assert data.operators["黑角"].current_room == ""
    # 下一轮仍可使用相同替班。
    assert shift_off(solver)[0]["dormitory_1"][0] == "黑角"


@pytest.mark.parametrize("failure", ["busy", "working", "missing", "duplicate", "beds"])
def test_failed_group_assignment_is_atomic(solver, monkeypatch, failure):
    data = solver.op_data
    if failure == "busy":
        monkeypatch.setattr(
            base_schedule, "_is_mastery_busy", lambda name: name == "黑角"
        )
    elif failure == "working":
        data.operators["黑角"].current_room = "central"
    elif failure == "missing":
        data.operators["塑心"].replacement = []
    elif failure == "duplicate":
        data.operators["塑心"].replacement = ["陈"]
    else:
        data.operators["泥岩"].operator_type = "high"
    before = [(d.name, d.time) for d in data.dorm]
    plan, replacements = {}, []
    solver.get_resting_plan(data.groups["联动"], replacements, plan, 0)
    assert plan == {}
    assert replacements == []
    assert [(d.name, d.time) for d in data.dorm] == before


def test_replacement_can_move_from_free_bed_in_same_dorm(solver):
    apply_plan(
        solver, {"dormitory_1": ["Current", "Current", "黑角", "Current", "Current"]}
    )
    plan, _ = shift_off(solver)
    assert plan["dormitory_1"][0] == "黑角"
    assert "黑角" not in [d.name for d in solver.op_data.dorm]


def test_exhaust_off_includes_dorm_replacement(solver):
    solver.task = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="伊内丝")
    solver.overtake_room()
    assert solver.tasks[0].type == TaskTypes.SHIFT_OFF
    assert solver.tasks[0].plan["dormitory_1"][0] == "黑角"
    assert "塑心" not in [d.name for d in solver.op_data.dorm]


def test_working_group_does_not_treat_resident_as_resting_witness(solver):
    # 引入无关房间的错误以执行整组一致性检查。
    solver.op_data.operators["冰酿"].current_room = ""
    solver.op_data.operators["冰酿"].current_index = -1
    assert solver.agent_get_mood() == "self_correction"
    assert solver.tasks[0].plan == {
        "dormitory_1": ["Current", "冰酿", "Current", "Current", "Current"]
    }


def test_restart_with_absent_stale_resident_preserves_cover(solver):
    shift_off(solver)
    solver.op_data.operators["塑心"].time_stamp = None
    assert solver.agent_get_mood() is None
    assert solver.tasks == []


def test_correction_completes_partial_dorm_shift_and_restores_after_return(solver):
    shift_off(solver)
    apply_plan(
        solver, {"dormitory_1": ["塑心", "Current", "Current", "Current", "Current"]}
    )
    assert solver.agent_get_mood() == "self_correction"
    assert solver.tasks[-1].plan["dormitory_1"][0] == "黑角"
    apply_plan(solver, solver.tasks.pop().plan)
    assert solver.agent_get_mood(skip_dorm=True) is None
    apply_plan(solver, {"meeting": ["伊内丝", "银灰"], "contact": ["讯使"]})
    assert solver.agent_get_mood() == "self_correction"
    assert solver.tasks[-1].plan["dormitory_1"][0] == "塑心"
    apply_plan(solver, solver.tasks.pop().plan)
    assert solver.agent_get_mood(skip_dorm=True) is None


def test_other_group_cannot_borrow_occupied_dorm_cover(solver):
    shift_off(solver)
    data = solver.op_data
    data.add(
        Operator("砾", "central", index=0, replacement=["黑角"], operator_type="high")
    )
    data.plan["central"] = [Room("砾", "", ["黑角"])]
    plan = {}
    solver.get_resting_plan(["砾"], [], plan, 0)
    assert plan == {}
    assert data.is_dorm_replacement("黑角")


def test_full_mood_cover_is_preserved_during_actual_selection(solver, monkeypatch):
    agents = ["黑角", "冰酿", "陈", "红", "初雪"]
    monkeypatch.setattr(solver, "preserve_resting_crafters", lambda agents, room: None)
    monkeypatch.setattr(
        solver.op_data,
        "get_current_room",
        MagicMock(side_effect=RuntimeError("before UI")),
    )
    with pytest.raises(RuntimeError, match="before UI"):
        solver.choose_agent(agents, "dormitory_1")
    assert agents == ["黑角", "冰酿", "Free", "Free", "Free"]


@pytest.mark.parametrize("field", ["exhaust_require", "rest_in_full"])
def test_resident_mood_flags_do_not_control_work_group(solver, field):
    setattr(solver.global_plan["default_plan"].config, field, ["塑心"])
    assert solver.initialize_operators() is None
    groups = (
        solver.op_data.exhaust_group
        if field == "exhaust_require"
        else solver.op_data.rest_in_full_group
    )
    assert "联动" not in groups


def test_validation_rejects_missing_resident_cover(solver):
    solver.global_plan["default_plan"].plan["dormitory_1"][0].replacement = []
    assert "替换组数量不够" in solver.initialize_operators()


def test_validation_rejects_group_without_working_trigger(solver):
    solver.global_plan["default_plan"].plan["dormitory_1"][0].group = "只有宿舍"
    assert "非宿舍干员" in solver.initialize_operators()


def test_absent_resident_does_not_change_average_work_mood(solver):
    before = solver.op_data.average_mood()
    solver.op_data.operators["塑心"].current_room = ""
    assert solver.op_data.average_mood() == before


def test_correction_does_not_steal_cover_or_recall_workers(solver):
    shift_off(solver)
    apply_plan(
        solver, {"dormitory_1": ["塑心", "Current", "Current", "Current", "Current"]}
    )
    solver.op_data.operators["黑角"].current_room = "central"
    assert solver.agent_get_mood() is None
    assert solver.tasks == []
    assert solver.op_data.group_is_resting("联动")


def test_correction_can_use_next_available_resident_cover(solver):
    shift_off(solver)
    apply_plan(
        solver, {"dormitory_1": ["塑心", "Current", "Current", "Current", "Current"]}
    )
    solver.op_data.operators["黑角"].current_room = "central"
    solver.op_data.operators["塑心"].replacement.append("泥岩")
    solver.op_data.plan["dormitory_1"][0].replacement.append("泥岩")
    assert solver.agent_get_mood() == "self_correction"
    assert solver.tasks[0].plan["dormitory_1"][0] == "泥岩"
    assert "meeting" not in solver.tasks[0].plan


@pytest.mark.parametrize("resident", ["Free", "菲亚梅塔"])
def test_validation_rejects_special_dorm_group_members(solver, resident):
    solver.global_plan["default_plan"].plan["dormitory_1"][0].agent = resident
    assert "不能参与宿舍绑组换班" in solver.initialize_operators()


def test_multiple_residents_swap_without_using_extra_beds(solver):
    slot = solver.global_plan["default_plan"].plan["dormitory_1"][1]
    slot.group, slot.replacement = "联动", ["砾"]
    assert solver.initialize_operators() is None
    for name in ["伊内丝", "银灰", "讯使"]:
        solver.op_data.operators[name].mood = 5
    plan, _ = shift_off(solver)
    assert plan["dormitory_1"][:2] == ["黑角", "砾"]
    assert {d.name for d in solver.op_data.dorm} == {"伊内丝", "银灰", "讯使"}
    assert solver.agent_get_mood() is None


def test_mood_driven_resting_schedules_resident_cover(solver, monkeypatch):
    monkeypatch.setattr(solver, "plan_metadata", lambda: None)
    solver.total_agent = [
        op
        for op in solver.op_data.operators.values()
        if op.is_high() and not op.room.startswith("dorm")
    ]
    solver.resting()
    assert solver.tasks[0].type == TaskTypes.SHIFT_OFF
    assert solver.tasks[0].plan["dormitory_1"][0] == "黑角"
    assert {d.name for d in solver.op_data.dorm} == {"伊内丝", "银灰", "讯使"}


def set_resident_candidates(solver, names):
    solver.op_data.operators["塑心"].replacement = names.copy()
    solver.op_data.plan["dormitory_1"][0].replacement = names.copy()


@pytest.mark.parametrize(
    "first_mood,second_mood,first_known,second_known,expected",
    [
        (20, 5, True, True, "泥岩"),
        (5, 20, True, True, "黑角"),
        (5, 5, True, True, "黑角"),
        (0, 20, False, True, "泥岩"),
        (20, 0, True, False, "黑角"),
        (20, 0, False, False, "黑角"),
        (-1, 20, True, True, "泥岩"),
    ],
)
def test_dorm_candidates_prefer_lowest_known_mood(
    solver, first_mood, second_mood, first_known, second_known, expected
):
    set_resident_candidates(solver, ["黑角", "泥岩"])
    for name, mood, known in [
        ("黑角", first_mood, first_known),
        ("泥岩", second_mood, second_known),
    ]:
        op = solver.op_data.operators[name]
        op.mood = mood
        op.time_stamp = datetime.now() if known else None
    plan, _ = shift_off(solver)
    assert plan["dormitory_1"][0] == expected
    assert solver.op_data.operators["塑心"].replacement == ["黑角", "泥岩"]
    solver.enter_room.assert_not_called()


def test_dorm_candidate_order_uses_predicted_current_mood(solver):
    set_resident_candidates(solver, ["黑角", "泥岩"])
    first = solver.op_data.operators["黑角"]
    first.mood = 10
    first.time_stamp = datetime.now() - timedelta(hours=2)
    first.depletion_rate = -2  # 已恢复到约 14 点。
    solver.op_data.operators["泥岩"].mood = 12
    assert shift_off(solver)[0]["dormitory_1"][0] == "泥岩"


def test_dorm_candidates_compare_current_mood_without_subtracting_limit(solver):
    set_resident_candidates(solver, ["黑角", "泥岩"])
    solver.op_data.operators["黑角"].mood = 10
    solver.op_data.operators["黑角"].lower_limit = 9
    solver.op_data.operators["泥岩"].mood = 8
    assert shift_off(solver)[0]["dormitory_1"][0] == "泥岩"


@pytest.mark.parametrize("unavailable", ["working", "busy", "reserved"])
def test_lowest_mood_dorm_candidate_must_still_be_available(
    solver, monkeypatch, unavailable
):
    set_resident_candidates(solver, ["黑角", "泥岩"])
    solver.op_data.operators["黑角"].mood = 0
    solver.op_data.operators["泥岩"].mood = 10
    used = []
    if unavailable == "working":
        solver.op_data.operators["黑角"].current_room = "central"
    elif unavailable == "busy":
        monkeypatch.setattr(
            base_schedule, "_is_mastery_busy", lambda name: name == "黑角"
        )
    else:
        used.append("黑角")
    plan = {}
    solver.get_resting_plan(solver.op_data.groups["联动"], used, plan, 0)
    assert plan["dormitory_1"][0] == "泥岩"


def test_normal_workplace_keeps_configured_replacement_order(solver):
    solver.op_data.operators["伊内丝"].replacement = ["陈", "泥岩"]
    solver.op_data.operators["陈"].mood = 24
    solver.op_data.operators["泥岩"].mood = 0
    assert shift_off(solver)[0]["meeting"][0] == "陈"


def test_dorm_correction_selects_low_mood_cover_but_does_not_churn(solver):
    set_resident_candidates(solver, ["黑角", "泥岩"])
    solver.op_data.operators["黑角"].mood = 20
    solver.op_data.operators["泥岩"].mood = 5
    shift_off(solver)
    # 模拟宿舍换班尚未执行，组内工作干员已经休息。
    apply_plan(
        solver, {"dormitory_1": ["塑心", "Current", "Current", "Current", "Current"]}
    )
    assert solver.agent_get_mood() == "self_correction"
    assert solver.tasks[-1].plan == {
        "dormitory_1": ["泥岩", "Current", "Current", "Current", "Current"]
    }
    apply_plan(solver, solver.tasks.pop().plan)
    # 候选心情高低反转，已入驻的有效替班仍保留，不拉工作组回班。
    solver.op_data.operators["黑角"].mood = 0
    solver.op_data.operators["泥岩"].mood = 24
    for _ in range(2):
        assert solver.agent_get_mood() is None
        assert solver.tasks == []
        assert solver.op_data.get_current_operator("dormitory_1", 0).name == "泥岩"
        assert solver.op_data.group_is_resting("联动")


@pytest.mark.parametrize("mood", [0, 12, 24, -1])
def test_resident_mood_does_not_compete_for_worker_replacements(
    solver, monkeypatch, mood
):
    resident = solver.op_data.operators["塑心"]
    resident.mood = mood
    # 即使宿舍成员最先配置、心情最低，也不能先抢走工作成员唯一的替班。
    solver.op_data.groups["联动"].remove("塑心")
    solver.op_data.groups["联动"].insert(0, "塑心")
    set_resident_candidates(solver, ["陈", "黑角"])
    solver.op_data.operators["陈"].mood = 0
    monkeypatch.setattr(
        resident,
        "current_mood",
        MagicMock(side_effect=AssertionError("resident mood must not be compared")),
    )
    plan, _ = shift_off(solver)
    assert plan["meeting"][0] == "陈"
    assert plan["dormitory_1"][0] == "黑角"
    resident.current_mood.assert_not_called()


def test_resting_priority_ignores_resident_mood_and_priority(solver, monkeypatch):
    resident = solver.op_data.operators["塑心"]
    original_group = solver.op_data.groups["联动"].copy()
    resident.resting_priority = "high"
    for name in ["伊内丝", "银灰", "讯使"]:
        solver.op_data.operators[name].resting_priority = "low"
    monkeypatch.setattr(
        resident,
        "current_mood",
        MagicMock(side_effect=AssertionError("resident mood must not be compared")),
    )
    solver.rearrange_resting_priority("联动")
    assert resident.resting_priority == "high"
    assert all(
        solver.op_data.operators[name].resting_priority == "low"
        for name in ["伊内丝", "银灰", "讯使"]
    )
    assert solver.op_data.groups["联动"] == original_group
    resident.current_mood.assert_not_called()


def test_fia_working_target_does_not_compare_resident_mood(solver, monkeypatch):
    resident = solver.op_data.operators["塑心"]
    monkeypatch.setattr(
        resident,
        "current_mood",
        MagicMock(side_effect=AssertionError("resident mood must not be compared")),
    )
    monkeypatch.setattr(solver, "check_fia", lambda: (["伊内丝"], "dormitory_1"))
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA)
    solver.plan_fia()
    assert solver.tasks[0].plan["dormitory_1"] == ["伊内丝", "菲亚梅塔"]
    resident.current_mood.assert_not_called()


@pytest.mark.parametrize("lower_limit,selected", [(0, False), (2, True), (6, True)])
def test_fia_keeps_group_comparison_relative_to_lower_limit(
    solver, monkeypatch, lower_limit, selected
):
    for name, mood in [("伊内丝", 10), ("银灰", 8), ("讯使", 24)]:
        solver.op_data.operators[name].mood = mood
    solver.op_data.operators["伊内丝"].lower_limit = lower_limit
    monkeypatch.setattr(config.conf, "fia_fool", True)
    monkeypatch.setattr(solver, "check_fia", lambda: (["伊内丝"], "dormitory_1"))
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA)
    solver.plan_fia()
    assert bool(solver.tasks[0].plan) is selected
    if selected:
        assert solver.tasks[0].plan["dormitory_1"] == ["伊内丝", "菲亚梅塔"]


@pytest.mark.parametrize("ling_xi", [1, 2])
@pytest.mark.parametrize("room", ["central", "dormitory_1"])
def test_ling_xi_group_mood_limits_exclude_dorm_residents(solver, ling_xi, room):
    data = solver.op_data
    data.config.ling_xi = ling_xi
    data.add(Operator("夕", room, index=0, group="联动", operator_type="high"))
    data.init_mood_limit()
    assert data.operators["塑心"].lower_limit == 0
    assert data.operators["伊内丝"].lower_limit == (12 if room == "central" else 0)


@pytest.mark.parametrize(
    "name,group",
    [("塑心", ""), ("菲亚梅塔", ""), ("菲亚梅塔", "感知")],
)
def test_mood_sort_excludes_ungrouped_dorms_and_fia(solver, name, group):
    operator = Operator(name, "dormitory_1", group=group, replacement=["黑角", "泥岩"])
    solver.op_data.operators["黑角"].mood = 20
    solver.op_data.operators["泥岩"].mood = 0
    assert solver.op_data.replacement_candidates(operator) == ["黑角", "泥岩"]
    assert operator.replacement == ["黑角", "泥岩"]


def test_fia_keeps_original_priority_instead_of_dorm_candidate_mood_sort(
    solver, monkeypatch
):
    candidates = ["伊内丝", "讯使"]
    for name, mood in [("伊内丝", 10), ("讯使", 2)]:
        operator = solver.op_data.operators[name]
        operator.group = ""
        operator.mood = mood
    monkeypatch.setattr(solver, "check_fia", lambda: (candidates, "dormitory_1"))
    monkeypatch.setattr(
        solver.op_data,
        "replacement_candidates",
        MagicMock(
            side_effect=AssertionError("Fia must not use dorm candidate sorting")
        ),
    )
    monkeypatch.setattr(config.conf, "fia_fool", True)
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA)
    solver.plan_fia()
    assert solver.tasks[0].plan["dormitory_1"] == ["伊内丝", "菲亚梅塔"]
    assert candidates == ["伊内丝", "讯使"]
    solver.op_data.replacement_candidates.assert_not_called()


@pytest.fixture
def legacy_solver(solver):
    solver.global_plan["default_plan"].plan["dormitory_1"][0].group = ""
    solver.op_data.plan["dormitory_1"][0].group = ""
    solver.op_data.operators["塑心"].group = ""
    solver.op_data.groups["联动"].remove("塑心")
    return solver


def test_ungrouped_dorm_does_not_run_group_correction(legacy_solver, monkeypatch):
    from arknights_mower.utils import resting_correction

    correction = MagicMock(side_effect=AssertionError("dorm groups are disabled"))
    monkeypatch.setattr(resting_correction, "correct_group_dorms", correction)
    assert not legacy_solver.op_data.has_dorm_groups()
    assert legacy_solver.agent_get_mood() is None
    assert legacy_solver.tasks == []
    correction.assert_not_called()


def test_ungrouped_absent_resident_keeps_legacy_average_mood(legacy_solver):
    data = legacy_solver.op_data
    data.operators["塑心"].current_room = ""
    assert data.average_mood() == pytest.approx(39 / 96)


def test_ungrouped_resident_keeps_legacy_exhaust_flag(legacy_solver):
    legacy_solver.global_plan["default_plan"].config.exhaust_require = ["塑心"]
    assert legacy_solver.initialize_operators() is None
    assert "塑心" in legacy_solver.op_data.exhaust_agent
    assert not legacy_solver.op_data.has_dorm_groups()


def test_ungrouped_fixed_slot_keeps_legacy_full_mood_release(
    legacy_solver, monkeypatch
):
    agents = ["黑角", "冰酿", "陈", "红", "初雪"]
    monkeypatch.setattr(
        legacy_solver, "preserve_resting_crafters", lambda agents, room: None
    )
    monkeypatch.setattr(
        legacy_solver.op_data,
        "get_current_room",
        MagicMock(side_effect=RuntimeError("before UI")),
    )
    with pytest.raises(RuntimeError, match="before UI"):
        legacy_solver.choose_agent(agents, "dormitory_1")
    assert agents == ["Free", "冰酿", "Free", "Free", "Free"]


@pytest.mark.parametrize("operation", ["shift", "priority"])
def test_normal_group_keeps_legacy_in_place_order(legacy_solver, operation):
    data = legacy_solver.op_data
    original = data.groups["联动"]
    for name, mood in [("伊内丝", 10), ("银灰", 8), ("讯使", 3)]:
        data.operators[name].mood = mood
    if operation == "shift":
        plan, _ = shift_off(legacy_solver)
        assert "dormitory_1" not in plan
    else:
        legacy_solver.rearrange_resting_priority("联动")
    assert data.groups["联动"] is original
    assert original == ["讯使", "银灰", "伊内丝"]
