"""训练室配置身份不占用空闲替班，真实专精驻员仍受保护。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, mastery_reader
from arknights_mower.solvers.base_schedule import _is_mastery_busy
from arknights_mower.tests.exhaust_replacement_tests import solver as solver
from arknights_mower.utils import config, mastery_db
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def training_cover(solver, monkeypatch):
    plan = solver.global_plan["default_plan"]
    plan.config = PlanConfig("", "令", "")
    plan.plan = {
        "central": [Room("令", "感知", ["重岳"])],
        "contact": [Room("歌蕾蒂娅", "深海", ["夕"])],
        "train": [
            Room("褐果", "感知", ["余"]),
            Room("桃金娘", "感知", ["望"]),
        ],
        "dormitory_1": [
            Room("冰酿", "", []),
            Room(
                "撷英调香师",
                "深海",
                ["白面鸮"],
                group_bindings=[{"group": "感知", "replacement": ["桃金娘"]}],
            ),
            *[Room("Free", "", []) for _ in range(3)],
        ],
    }
    assert solver.initialize_operators() is None
    for name in ("百炼嘉维尔", "佩佩"):
        solver.op_data.add(Operator(name, ""))
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "central": ["令"],
                "contact": ["夕"],
                "train": ["百炼嘉维尔", "佩佩"],
                "dormitory_1": ["冰酿", "白面鸮", "歌蕾蒂娅", "Free", "Free"],
            }
        ]
    )
    now = datetime.now()
    for op in solver.op_data.operators.values():
        op.mood, op.time_stamp = 12, now
    solver.op_data.operators["令"].mood = 0
    for bed in solver.op_data.dorm:
        if bed.name:
            bed.time = now + timedelta(hours=1)
    config.conf.enable_mastery = True
    monkeypatch.setattr(
        mastery_db,
        "get_active_plan",
        lambda: {"id": 1, "status": "training", "char_name": "佩佩"},
    )
    monkeypatch.setattr(mastery_db, "is_operator_busy", lambda name: False)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", _is_mastery_busy)
    solver.train_room_state = mastery_reader.RoomState(
        "training",
        support_slot="百炼嘉维尔",
        train_slot="佩佩",
        slots_read=True,
        slots_reliable=True,
    )
    solver.find_next_task = MagicMock(return_value=None)
    solver.check_fia = MagicMock(return_value=([], None))
    solver.skip = MagicMock()
    solver.task = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="令")
    return solver


def test_exhaust_recalls_other_group_and_uses_idle_configured_training_cover(
    training_cover,
):
    s = training_cover
    original, before = s.task, s.task.time
    s.overtake_room()
    support = next(task for task in s.tasks if getattr(task, "exhaust_support", False))
    assert support.plan["contact"] == ["歌蕾蒂娅"]
    assert "train" not in support.plan
    assert original in s.tasks and original.time == before
    assert s.op_data.operators["歌蕾蒂娅"].is_resting()
    assert s.op_data.operators["桃金娘"].current_room == ""
    s.task = support
    assert s._coordination_support_valid(support.plan, ["令"])

    s.op_data = s.op_data.project_arrangements([support.plan])
    s.tasks, s.task = [], original
    s.overtake_room()
    departure = next(task for task in s.tasks if task.type == TaskTypes.SHIFT_OFF)
    assert departure.plan["central"] == ["重岳"]
    assert departure.plan["dormitory_1"][1] == "桃金娘"
    assert "令" in departure.plan["dormitory_1"]
    assert "train" not in departure.plan
    s.task = departure
    s._prepare_group_shift(departure, remember_targets=True)
    assert departure.plan["dormitory_1"][1] == "桃金娘"
    assert "train" not in departure.plan
    assert not any(room == "train" for room, _ in departure.group_shift_expected)
    assert s.op_data.operators["百炼嘉维尔"].current_room == "train"
    assert s.op_data.operators["佩佩"].current_room == "train"
    s.enter_room.assert_not_called()


def after_deep_sea_return(solver):
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "contact": ["歌蕾蒂娅"],
                "dormitory_1": ["冰酿", "撷英调香师", "Free", "Free", "Free"],
            }
        ]
    )


@pytest.mark.parametrize("active", [False, True])
def test_same_configuration_allows_idle_cover_before_and_during_mastery(
    training_cover, monkeypatch, active
):
    s = training_cover
    after_deep_sea_return(s)
    if not active:
        monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)
        s.train_room_state.state = "empty"
    plan = {}
    s.get_resting_plan(["令"], [], plan, 0)
    assert plan["central"] == ["重岳"]
    assert plan["dormitory_1"][1] == "桃金娘"
    assert s.op_data.operators["桃金娘"].current_room == ""
    assert s.op_data.operators["佩佩"].current_room == "train"


@pytest.mark.parametrize("observed", ["training", "read_failed"])
def test_ordinary_shift_keeps_idle_training_cover_through_confirmation(
    training_cover, observed
):
    s = training_cover
    after_deep_sea_return(s)
    if observed == "read_failed":
        s.train_room_state = mastery_reader.RoomState(read_failed=True)
    plan = {}
    s.get_resting_plan(["令", "褐果", "桃金娘"], [], plan, 0)
    assert plan["central"] == ["重岳"]
    assert plan["dormitory_1"][1] == "桃金娘"
    assert "train" not in plan
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan=plan)
    s.task, s.tasks = task, [task]
    s._prepare_group_shift(task, remember_targets=True)
    assert task.group_shift_expected["dormitory_1", 1] == "桃金娘"
    assert not any(room == "train" for room, _ in task.group_shift_expected)
    s.op_data = s.op_data.project_arrangements([task.plan])
    task.plan.clear()
    assert s._complete_group_shift(task)
    assert s.op_data.group_is_resting("感知")
    assert s.op_data.operators["令"].is_resting()
    assert s.op_data.operators["桃金娘"].current_room == "dormitory_1"
    assert s.op_data.operators["百炼嘉维尔"].current_room == "train"
    assert s.op_data.operators["佩佩"].current_room == "train"


@pytest.mark.parametrize(
    "blocker", ["actual_training", "mastery_reservation", "other_task"]
)
def test_real_occupancy_and_reservations_still_block_both_shift_paths(
    training_cover, monkeypatch, blocker
):
    s = training_cover
    after_deep_sea_return(s)
    if blocker == "actual_training":
        s.op_data = s.op_data.project_arrangements(
            [{"train": ["百炼嘉维尔", "桃金娘"]}]
        )
    elif blocker == "mastery_reservation":
        monkeypatch.setattr(
            mastery_db, "is_operator_busy", lambda name: name == "桃金娘"
        )
    else:
        reserved = SchedulerTask(
            task_type=TaskTypes.SELF_CORRECTION,
            task_plan={
                "dormitory_1": ["Current", "Current", "Current", "桃金娘", "Current"]
            },
        )
        reserved.execution_retained = True
        s.tasks.append(reserved)
    plan = {}
    s.get_resting_plan(["令"], [], plan, 0)
    assert plan == {}
    original, before = s.task, s.task.time
    s.overtake_room()
    assert original in s.tasks and original.time == before
    assert original.execution_failure
    assert not any(getattr(task, "exhaust_support", False) for task in s.tasks)
    assert not any(task.type == TaskTypes.SHIFT_OFF for task in s.tasks)
    assert s.op_data.operators["令"].current_room == "central"


@pytest.mark.parametrize("recycle_unavailable", [False, True])
def test_preparation_protects_actual_sources_but_keeps_configured_idle_cover(
    training_cover,
    recycle_unavailable,
):
    s = training_cover
    s._recycle_unavailable = recycle_unavailable
    plan = {
        "train": ["褐果", "桃金娘"],
        "central": ["百炼嘉维尔"],
        "dormitory_1": ["Current", "桃金娘", "佩佩", "Current", "Current"],
    }
    s._suppress_facility_arrangement(plan)
    assert "train" not in plan
    assert "central" not in plan
    assert plan["dormitory_1"] == ["Current", "桃金娘", "Current", "Current", "Current"]


def test_training_departure_reopens_original_failure_without_timed_retry(
    training_cover,
):
    s = training_cover
    after_deep_sea_return(s)
    s.op_data = s.op_data.project_arrangements([{"train": ["百炼嘉维尔", "桃金娘"]}])
    original, before = s.task, s.task.time
    s.overtake_room()
    independent = SchedulerTask(task_type=TaskTypes.NOT_SPECIFIC)
    s.tasks.append(independent)
    for _ in range(3):
        s._resume_failed_tasks()
        assert original.execution_failure
        assert s.tasks == [original, independent]
        assert original.time == before
    s.op_data = s.op_data.project_arrangements([{"train": ["百炼嘉维尔", "佩佩"]}])
    s._resume_failed_tasks()
    assert not hasattr(original, "execution_failure")
    assert original.time == before
    s.overtake_room()
    departure = next(task for task in s.tasks if task.type == TaskTypes.SHIFT_OFF)
    assert departure.plan["dormitory_1"][1] == "桃金娘"
    assert "令" in departure.plan["dormitory_1"]
    assert independent in s.tasks


@pytest.mark.parametrize("follow", [False, True])
def test_follow_setting_only_removes_owned_training_positions(training_cover, follow):
    s = training_cover
    config.conf.assistant_follows_schedule = follow
    saved_plan = deepcopy(
        {room: [vars(slot) for slot in row] for room, row in s.op_data.plan.items()}
    )
    plan = {
        "train": ["褐果", "桃金娘"],
        "central": ["百炼嘉维尔"],
        "dormitory_1": ["Current", "桃金娘", "佩佩", "Current", "Current"],
    }
    s._suppress_facility_arrangement(plan)
    if follow:
        assert plan["train"] == ["褐果", "Current"]
        assert plan["central"] == ["百炼嘉维尔"]
    else:
        assert "train" not in plan
        assert "central" not in plan
    assert plan["dormitory_1"][1:3] == ["桃金娘", "Current"]
    assert {
        room: [vars(slot) for slot in row] for room, row in s.op_data.plan.items()
    } == saved_plan


def test_following_assistant_can_rest_with_group_while_trainee_stays(training_cover):
    s = training_cover
    config.conf.assistant_follows_schedule = True
    after_deep_sea_return(s)
    s.op_data = s.op_data.project_arrangements([{"train": ["褐果", "佩佩"]}])
    original_plan = deepcopy(
        {room: [vars(slot) for slot in row] for room, row in s.op_data.plan.items()}
    )
    plan = {}
    s.get_resting_plan(["令", "褐果", "桃金娘"], [], plan, 0)
    assert plan["central"] == ["重岳"]
    assert plan["train"] == ["余", "Current"]
    assert plan["dormitory_1"][1] == "桃金娘"
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan=plan)
    s.task, s.tasks = task, [task]
    s._prepare_group_shift(task, remember_targets=True)
    assert task.group_shift_expected["train", 0] == "余"
    assert ("train", 1) not in task.group_shift_expected
    s.op_data = s.op_data.project_arrangements([task.plan])
    task.plan.clear()
    assert s._complete_group_shift(task)
    assert s.op_data.group_is_resting("感知")
    assert s.op_data.operators["褐果"].is_resting()
    assert s.op_data.operators["佩佩"].current_room == "train"
    assert s.op_data.operators["佩佩"].current_index == 1
    assert {
        room: [vars(slot) for slot in row] for room, row in s.op_data.plan.items()
    } == original_plan


@pytest.mark.parametrize("first_group", ["深海", "感知"])
@pytest.mark.parametrize("entry", ["metadata", "execution"])
def test_idle_training_cover_stays_until_last_shared_group_returns(
    training_cover, first_group, entry
):
    s = training_cover
    data = s.op_data
    shared = data.operators["撷英调香师"]
    shared.replacement = ["桃金娘"]
    shared.group_bindings[0]["replacement"] = ["桃金娘"]
    # 两组共用同一替班，桃金娘只具有训练室配置身份，实际在固定宿舍位。
    s.op_data = data.project_arrangements(
        [
            {
                "central": ["重岳"],
                "contact": ["夕"],
                "dormitory_1": ["冰酿", "桃金娘", "令", "歌蕾蒂娅", "Free"],
            }
        ]
    )
    data = s.op_data
    now = datetime.now()
    first = "歌蕾蒂娅" if first_group == "深海" else "令"
    last = "令" if first_group == "深海" else "歌蕾蒂娅"
    for name, hours in ((first, 1), (last, 2)):
        op = data.operators[name]
        op.mood = 10
        data.get_dorm_by_name(name)[1].time = now + timedelta(hours=hours)
    s.tasks, s.task = [], None

    s.plan_metadata()

    returns = sorted(
        (task for task in s.tasks if task.type == TaskTypes.SHIFT_ON),
        key=lambda task: task.time,
    )
    assert len(returns) == 2
    first_task, last_task = returns
    original_time = first_task.time
    if entry == "metadata":
        assert first_task.plan.get("dormitory_1", ["Current", "Current"])[1] in (
            "Current",
            "桃金娘",
        )
    else:
        # 旧版本已生成的错误目标也必须在执行准备时重新整理。
        first_task.plan.setdefault("dormitory_1", ["Current"] * 5)[1] = "撷英调香师"
    s.task = first_task
    s._prepare_group_shift(first_task, remember_targets=True)
    assert first_task.plan.get("dormitory_1", ["Current", "Current"])[1] in (
        "Current",
        "桃金娘",
    )
    assert first_task.time == original_time
    s.op_data = data.project_arrangements([first_task.plan])
    first_task.plan.clear()
    assert s._complete_group_shift(first_task)
    assert s.op_data.get_current_operator("dormitory_1", 1).name == "桃金娘"
    assert s.op_data.group_is_resting("感知" if first_group == "深海" else "深海")
    s.task, s.tasks = last_task, [last_task]
    s._prepare_group_shift(last_task, remember_targets=True)
    final = s.op_data.project_arrangements([last_task.plan])
    assert final.get_current_operator("dormitory_1", 1).name == "撷英调香师"
    assert data.operators["百炼嘉维尔"].current_room == "train"
    assert data.operators["佩佩"].current_room == "train"
