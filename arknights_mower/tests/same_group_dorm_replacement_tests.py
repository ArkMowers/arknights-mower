"""同组工作主班与宿舍主班双向替班保留完整轮休和单回确认。"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.dorm_recovery import recovery_order_plan  # noqa: E402
from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    TaskTypes,
    plan_metadata,
    try_reorder,
)

WORKER = "凯尔希·思衡托"
RESIDENT = "斥罪"
ROOM = "dormitory_3"


def make_solver(monkeypatch, reciprocal=False, index=0):
    monkeypatch.setattr(base_schedule.logger, "disabled", True)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    config.conf.enable_mastery = False
    config.conf.rescue_threshold = 0
    row = [Room("杜林", "", []), Room("蜜莓", "", [])]
    row += [Room("Free", "", []) for _ in range(3)]
    row[index] = Room(RESIDENT, "公招", [WORKER] if reciprocal else ["夜莺"])
    solver = object.__new__(BaseSchedulerSolver)
    solver.global_plan = {
        "default_plan": Plan(
            {"contact": [Room(WORKER, "公招", [RESIDENT])], ROOM: row},
            PlanConfig("", "", ""),
        ),
        "backup_plans": [],
    }
    solver.tasks = []
    solver._refresh_deferred_product_reservations = lambda: None
    solver.check_fia = lambda: (None, None)
    return solver


def initialize(solver):
    assert solver.initialize_operators() is None
    Operators.current_room_changed_callback = None
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                room: [slot.agent for slot in row]
                for room, row in solver.op_data.plan.items()
            }
        ]
    )
    for op in solver.op_data.operators.values():
        op.time_stamp, op.mood = datetime.now(), 24
    solver.op_data.operators[WORKER].mood = 5


@pytest.mark.parametrize("reciprocal", [False, True])
def test_cross_role_replacements_preserve_primary_identity(monkeypatch, reciprocal):
    solver = make_solver(monkeypatch, reciprocal)
    initialize(solver)
    data = solver.op_data
    assert data.groups["公招"] == [WORKER, RESIDENT]
    for name, room in [(WORKER, "contact"), (RESIDENT, ROOM)]:
        assert data.operators[name].is_high()
        assert (data.operators[name].room, data.operators[name].group) == (room, "公招")
    assert data.is_same_group_dorm_replacement(data.operators[WORKER], RESIDENT)
    assert (
        data.is_same_group_dorm_replacement(data.operators[RESIDENT], WORKER)
        is reciprocal
    )


@pytest.mark.parametrize("invalid", ["empty", "different", "work_work", "self"])
def test_primary_replacements_reject_invalid_relationships(monkeypatch, invalid):
    solver = make_solver(monkeypatch, reciprocal=True)
    plan = solver.global_plan["default_plan"].plan
    if invalid == "empty":
        plan["contact"][0].group = plan[ROOM][0].group = ""
    elif invalid == "different":
        plan[ROOM][0].group = "其他"
    elif invalid == "work_work":
        plan["meeting"] = [plan[ROOM][0]]
        plan[ROOM][0] = Room("杜林", "", [])
    else:
        plan["contact"][0].replacement = [WORKER]
    assert "替换组不可用高效组干员" in solver.initialize_operators()


@pytest.mark.parametrize("reciprocal", [False, True])
@pytest.mark.parametrize("index", [0, 2])
def test_complete_shift_uses_fixed_or_dynamic_bed(monkeypatch, reciprocal, index):
    solver = make_solver(monkeypatch, reciprocal, index)
    initialize(solver)
    before = solver.op_data.get_current_room(ROOM, True)
    plan, covers = {}, []
    solver.get_resting_plan(solver.op_data.groups["公招"].copy(), covers, plan, 0)
    assert plan["contact"] == [RESIDENT]
    assert plan[ROOM][index] == (WORKER if reciprocal else "夜莺")
    if not reciprocal:
        base_schedule._merge_dorm_arrangement(
            plan, try_reorder(solver.op_data, plan) or {}
        )
    projected = solver.op_data.project_arrangements([plan])
    _, bed = projected.get_dorm_by_name(WORKER)
    assert bed is not None
    assert (bed.position == (ROOM, index)) is reciprocal
    assert projected.get_refresh_index(ROOM, projected.get_current_room(ROOM, True))
    assert solver.op_data.get_current_room(ROOM, True) == before
    if reciprocal:
        assert not projected.is_effective_free_slot(bed)
        assert projected.operators[WORKER].name not in {b.name for b in projected.dorm}


@pytest.mark.parametrize("index", [0, 2])
def test_fixed_recovery_times_generate_whole_group_return(monkeypatch, index):
    solver = make_solver(monkeypatch, reciprocal=True, index=index)
    initialize(solver)
    data = solver.op_data.project_arrangements(
        [
            {
                "contact": [RESIDENT],
                ROOM: [WORKER if i == index else "Current" for i in range(5)],
            }
        ]
    )
    _, bed = data.get_dorm_by_name(WORKER)
    assert bed is not None
    bed.time = datetime.now() + timedelta(hours=3)
    tasks = plan_metadata(data, [])
    returned = [task for task in tasks if task.type == TaskTypes.SHIFT_ON]
    assert len(returned) == 1
    assert returned[0].plan["contact"] == [WORKER]
    assert returned[0].plan[ROOM][index] == RESIDENT
    actual = data.project_arrangements([returned[0].plan])
    assert actual.get_dorm_by_name(WORKER) == (None, None)
    assert data.get_dorm_by_name(WORKER)[1].time == bed.time


def test_fixed_recovery_is_single_target_before_free_slots(monkeypatch):
    solver = make_solver(monkeypatch, reciprocal=True)
    initialize(solver)
    row = [WORKER, "蜜莓", "Free", "Free", "Free"]
    assert recovery_order_plan(solver.op_data, ROOM, row) == [WORKER, "蜜莓"]


def test_missing_dorm_cover_preserves_entire_group(monkeypatch):
    solver = make_solver(monkeypatch)
    initialize(solver)
    solver.op_data.operators["夜莺"].current_room = "meeting"
    plan, covers = {}, []
    solver.get_resting_plan(solver.op_data.groups["公招"].copy(), covers, plan, 0)
    assert plan == {}
    assert covers == []
    assert all(not bed.name for bed in solver.op_data.all_dorms())


def resting_state(solver, reciprocal=False, index=0):
    plan, covers = {}, []
    solver.get_resting_plan(solver.op_data.groups["公招"].copy(), covers, plan, 0)
    if not reciprocal:
        base_schedule._merge_dorm_arrangement(
            plan, try_reorder(solver.op_data, plan) or {}
        )
    solver.op_data = solver.op_data.project_arrangements([plan])
    _, bed = solver.op_data.get_dorm_by_name(WORKER)
    bed.time = datetime.now() + timedelta(hours=3)
    return bed


def mock_arrangement(solver, monkeypatch, final, *, contact_cover=RESIDENT):
    """模拟游戏确认与读房，使用真实位置、恢复记录和倒计时更新。"""
    from arknights_mower.utils.operators import Operator
    from arknights_mower.utils.scheduler_task import SchedulerTask

    monkeypatch.setattr(base_schedule, "save_exception", lambda e: None)
    for name in ("黑角", "陈", "银灰"):
        solver.op_data.add(Operator(name, "", mood=24, time_stamp=datetime.now()))
    solver.physical = final.copy()
    solver.op_data = solver.op_data.project_arrangements(
        [{"contact": [contact_cover], ROOM: final}]
    )
    solver.task = SchedulerTask(
        task_plan={ROOM: final.copy()}, task_type=TaskTypes.SHIFT_OFF
    )
    solver.tasks = [solver.task]
    solver.recog = MagicMock()
    solver.find = MagicMock(return_value=True)
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver.waiting_scene = []
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.back = MagicMock()
    solver.ctap = MagicMock()
    solver.confirms, solver.reads = [], []
    solver.deadline = datetime.now() + timedelta(hours=2)

    def observe(room=ROOM, read_time_index=None, *, departing_plan=None):
        solver.reads.append(list(read_time_index or []))
        for op in solver.op_data.operators.values():
            if op.current_room == room and op.name not in solver.physical:
                op.current_room, op.current_index = "", -1
        for i, name in enumerate(solver.physical):
            if name:
                op = solver.op_data.operators[name]
                missing = solver.op_data.update_detail(name, op.mood, room, i)
                if i in (read_time_index or []) or missing == i:
                    solver.op_data.refresh_dorm_time(
                        room, i, {"agent": name, "time": solver.deadline}
                    )
        return [{"agent": name} for name in solver.physical]

    def choose(agents, room, fast_mode=True, **kwargs):
        solver.selected = agents.copy()

    def confirm(room, new_plan):
        solver.physical = solver.selected + [""] * (5 - len(solver.selected))
        solver.confirms.append(solver.physical.copy())

    solver.get_agent_from_room = MagicMock(side_effect=observe)
    solver.choose_agent = MagicMock(side_effect=choose)
    solver.tap_confirm = MagicMock(side_effect=confirm)
    observe()


@pytest.mark.parametrize("mood", [0, 5, 24, -1, None])
@pytest.mark.parametrize("padding", [False, True])
def test_ordinary_dorm_cover_competes_in_actual_lock_confirmation(
    monkeypatch, mood, padding
):
    solver = make_solver(monkeypatch)
    initialize(solver)
    final = ["夜莺", "蜜莓", WORKER, "陈", "银灰"]
    mock_arrangement(solver, monkeypatch, final)
    cover = solver.op_data.operators["夜莺"]
    cover.mood = mood if mood is not None else 24
    cover.time_stamp = datetime.now() if mood is not None else None
    if not padding:
        solver.op_data.operators["黑角"].current_room = "meeting"
    solver.agent_arrange_room({}, ROOM, solver.task.plan)
    target = solver.op_data.operators[WORKER]
    assert solver.physical == final
    confirmed = mood == 24 or padding
    assert (target.dorm_recovery_room == ROOM) is confirmed
    if confirmed:
        assert solver.confirms[0][:3] == [
            "夜莺" if mood == 24 else "黑角",
            "蜜莓",
            WORKER,
        ]
        assert all(row[2] == WORKER for row in solver.confirms)
        assert tuple(name for name, _, _ in target.dorm_recovery_fixed) == ("蜜莓",)
    else:
        assert len(solver.confirms) == 0


@pytest.mark.parametrize("index", [0, 2])
def test_fixed_single_target_reads_final_roster_countdown(monkeypatch, index):
    solver = make_solver(monkeypatch, reciprocal=True, index=index)
    initialize(solver)
    final = (
        [WORKER, "蜜莓", "陈", "银灰", "黑角"]
        if index == 0
        else ["杜林", "蜜莓", WORKER, "陈", "银灰"]
    )
    mock_arrangement(solver, monkeypatch, final)
    solver.agent_arrange_room({}, ROOM, solver.task.plan)
    target = solver.op_data.operators[WORKER]
    assert target.dorm_recovery_index == index
    assert solver.physical == final
    assert index in solver.reads[-1]
    assert solver.op_data.get_dorm_by_name(WORKER)[1].time == solver.deadline


def test_recovery_lock_tracks_provider_and_target_movement(monkeypatch):
    from arknights_mower.utils.dorm_recovery import recovery_managers

    solver = make_solver(monkeypatch, reciprocal=True)
    initialize(solver)
    final = [WORKER, "蜜莓", "陈", "银灰", "黑角"]
    mock_arrangement(solver, monkeypatch, final)
    solver.agent_arrange_room({}, ROOM, solver.task.plan)
    target = solver.op_data.operators[WORKER]
    assert recovery_order_plan(solver.op_data, ROOM, final) is None
    # 普通群回成员更换不使单回失效。
    changed = [WORKER, "蜜莓", "银灰", "陈", "黑角"]
    solver.op_data = solver.op_data.project_arrangements([{ROOM: changed}])
    assert recovery_order_plan(solver.op_data, ROOM, changed) is None
    manager = solver.op_data.operators["蜜莓"]
    manager.current_room, manager.current_index = "", -1
    manager.current_room, manager.current_index = ROOM, 1
    assert recovery_order_plan(solver.op_data, ROOM, changed) is not None
    target = solver.op_data.operators[WORKER]
    target.dorm_recovery_fixed = recovery_managers(solver.op_data, ROOM, changed)
    solver.op_data.update_detail(WORKER, 5, ROOM, 2)
    assert target.dorm_recovery_room == ""


@pytest.mark.parametrize("reciprocal", [False, True])
def test_cached_correction_retains_valid_rotation_and_repairs_vacancy(
    monkeypatch, reciprocal
):
    solver = make_solver(monkeypatch, reciprocal)
    initialize(solver)
    resting_state(solver, reciprocal)
    solver._suppress_train_correction = lambda plan: None
    assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
    solver.op_data.operators[RESIDENT].current_room = ""
    solver.op_data.operators[RESIDENT].current_index = -1
    correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert correction["contact"] == [RESIDENT]
    assert not any(WORKER in row for row in correction.values())


def test_unavailable_dorm_cover_never_steals_working_resident(monkeypatch):
    from arknights_mower.utils.resting_correction import correct_group_dorms

    solver = make_solver(monkeypatch)
    initialize(solver)
    resting_state(solver)
    cover = solver.op_data.operators["夜莺"]
    cover.current_room, cover.current_index = "meeting", 0
    correction = {}
    correct_group_dorms(solver.op_data, correction, lambda name: False)
    assert correction == {}
    assert solver.op_data.operators[RESIDENT].current_room == "contact"


@pytest.mark.parametrize("reciprocal", [False, True])
def test_exhaust_support_keeps_dorm_members_in_matching_without_triggering(
    monkeypatch, reciprocal
):
    solver = make_solver(monkeypatch, reciprocal)
    solver.global_plan["default_plan"].config.exhaust_require = [WORKER, RESIDENT]
    initialize(solver)
    data = solver.op_data
    assert WORKER in data.exhaust_agent
    assert RESIDENT not in data.exhaust_agent
    data.operators[WORKER].mood = 0
    before = data.get_current_room(ROOM, True)
    assert solver._plan_exhaust_support(data.groups["公招"].copy()) == {}
    assert data.get_current_room(ROOM, True) == before
    plan, covers = {}, []
    solver.get_resting_plan(data.groups["公招"].copy(), covers, plan, 0)
    assert plan["contact"] == [RESIDENT]
    assert plan[ROOM][0] == (WORKER if reciprocal else "夜莺")


@pytest.mark.parametrize(
    "blocked", ["busy", "reserved", "exhausted", "working_elsewhere"]
)
def test_blocked_primary_cover_preserves_whole_shift(monkeypatch, blocked):
    solver = make_solver(monkeypatch, reciprocal=True)
    initialize(solver)
    data = solver.op_data
    if blocked == "busy":
        monkeypatch.setattr(
            base_schedule, "_is_mastery_busy", lambda name: name == RESIDENT
        )
    elif blocked == "reserved":
        data.reserved_product_replacements.add(RESIDENT)
    elif blocked == "exhausted":
        data.operators[RESIDENT].mood = 0
    else:
        data.operators[RESIDENT].current_room = "train"
    before = data.get_current_room(ROOM, True)
    plan, covers = {}, []
    solver.get_resting_plan(data.groups["公招"].copy(), covers, plan, 0)
    assert plan == {} and covers == []
    assert data.get_current_room(ROOM, True) == before
    assert all(not bed.name for bed in data.all_dorms())


def test_fixed_records_survive_refresh_and_snapshot_without_free_capacity(monkeypatch):
    import pickle

    solver = make_solver(monkeypatch, reciprocal=True)
    initialize(solver)
    bed = resting_state(solver, reciprocal=True)
    deadline = bed.time
    data = solver.op_data
    assert data.swap_plan([], refresh=True) is None
    bed = data.get_dorm_by_name(WORKER)[1]
    assert bed.time == deadline and bed.name == WORKER
    assert not data.is_effective_free_slot(bed)
    restored = pickle.loads(pickle.dumps(data))
    projection = restored.project_arrangements([])
    projection.get_dorm_by_name(WORKER)[1].time = None
    assert restored.get_dorm_by_name(WORKER)[1].time == deadline
    assert data.get_dorm_by_name(WORKER)[1].time == deadline


def test_fixed_target_is_preserved_during_dynamic_bed_priority(monkeypatch):
    from arknights_mower.utils.operators import Operator
    from arknights_mower.utils.scheduler_task import prioritize_new_dorm_recovery

    solver = make_solver(monkeypatch, reciprocal=True)
    initialize(solver)
    resting_state(solver, reciprocal=True)
    data = solver.op_data
    data.add(Operator("陈", "", mood=0, time_stamp=datetime.now()))
    plan = {ROOM: ["Current", "Current", "Current", "Current", "陈"]}
    result = prioritize_new_dorm_recovery(data, plan)
    projected = data.project_arrangements([result])
    assert projected.operators[WORKER].current_index == 0
    assert projected.get_dorm_by_name(WORKER)[1].position == (ROOM, 0)


def test_personal_limit_releases_fixed_occupant_without_free_capacity(monkeypatch):
    from arknights_mower.utils.scheduler_task import plan_mood_limit_releases

    solver = make_solver(monkeypatch, reciprocal=True)
    initialize(solver)
    bed = resting_state(solver, reciprocal=True)
    data = solver.op_data
    data.config.operator_mood_limits[WORKER] = {"lower": 0, "upper": 12}
    data.init_mood_limit()
    bed.time = datetime.now() - timedelta(seconds=1)
    (task,) = plan_mood_limit_releases(data)
    assert task.strict_mood_limit and task.meta_data == WORKER
    assert task.plan[ROOM][0] == "Free"
    assert solver.prepare_release_dorm(task)
    projected = data.project_arrangements([task.plan])
    assert projected.get_dorm_by_name(WORKER) == (None, None)
    assert not projected.is_effective_free_slot(projected.get_group_dorm(ROOM, 0))
    # 已确认个人上限离宿后的记账，与真实读房保留原回班预约的语义一致。
    projected.operators[WORKER].rest_mood_release_limit = 12
    solver.op_data = projected
    solver._suppress_train_correction = lambda plan: None
    correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert WORKER not in correction.get(ROOM, [])


def test_normal_rotation_uses_fixed_bed_with_all_dynamic_beds_occupied(monkeypatch):
    solver = make_solver(monkeypatch, reciprocal=True)
    plan = solver.global_plan["default_plan"].plan
    for i, (primary, cover) in enumerate(
        (("陈", "黑角"), ("银灰", "夜莺"), ("能天使", "芬"))
    ):
        plan[f"room_{i + 1}_1"] = [Room(primary, "", [cover])]
    initialize(solver)
    data = solver.op_data.project_arrangements(
        [{ROOM: [RESIDENT, "蜜莓", "陈", "银灰", "能天使"]}]
    )
    for bed in data.dorm:
        bed.time = datetime.now() + timedelta(hours=4)
    solver.op_data = data
    solver.total_agent = list(data.operators.values())
    solver.plan_metadata = lambda: None
    solver.resting()
    task = next(task for task in solver.tasks if "contact" in task.plan)
    assert task.plan["contact"] == [RESIDENT]
    assert task.plan[ROOM][0] == WORKER
    assert {bed.name for bed in data.dorm} == {"陈", "银灰", "能天使"}


def test_exhaust_support_recalls_rotated_group_without_splitting_reciprocal_pair(
    monkeypatch,
):
    from arknights_mower.utils.exhaust_replacement import plan_exhaust_support

    solver = make_solver(monkeypatch, reciprocal=True)
    plan = solver.global_plan["default_plan"].plan
    plan["meeting"] = [Room("银灰", "公招", ["黑角"])]
    plan["room_1_1"] = [Room("能天使", "", ["黑角"])]
    initialize(solver)
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "contact": [RESIDENT],
                "meeting": ["黑角"],
                ROOM: [WORKER, "蜜莓", "银灰", "Free", "Free"],
            }
        ]
    )
    data = solver.op_data
    support = plan_exhaust_support(
        data,
        ["能天使"],
        lambda state: state.operators["黑角"].current_room == "",
        lambda name: False,
    )
    assert support["contact"] == [WORKER]
    assert support["meeting"] == ["银灰"]
    assert support[ROOM][0] == RESIDENT
    assert data.operators[WORKER].is_resting()
    assert data.operators[RESIDENT].current_room == "contact"


def test_reserved_fixed_slot_preserves_entire_group(monkeypatch):
    solver = make_solver(monkeypatch, reciprocal=True)
    initialize(solver)
    solver.op_data.reserved_product_beds[ROOM, 0] = "其他组"
    plan, covers = {}, []
    solver.get_resting_plan(solver.op_data.groups["公招"].copy(), covers, plan, 0)
    assert plan == {} and covers == []


def test_fixed_alternative_matches_group_when_dynamic_capacity_is_insufficient(
    monkeypatch,
):
    solver = make_solver(monkeypatch, reciprocal=True)
    plan = solver.global_plan["default_plan"].plan
    plan[ROOM][0].replacement = ["夜莺", WORKER]
    for i, (primary, cover) in enumerate(
        (("陈", "黑角"), ("银灰", "芬"), ("能天使", "砾"))
    ):
        plan[f"room_{i + 1}_1"] = [Room(primary, "公招", [cover])]
    initialize(solver)
    plan, covers = {}, []
    solver.get_resting_plan(solver.op_data.groups["公招"].copy(), covers, plan, 0)
    assert plan[ROOM][0] == WORKER
    assert {bed.name for bed in solver.op_data.dorm} == {"陈", "银灰", "能天使"}


def make_dorm_pair(monkeypatch, *, different_rooms=False, mixed=False):
    solver = make_solver(monkeypatch)
    plan = solver.global_plan["default_plan"].plan
    plan["contact"][0].replacement = ["黑角"]
    plan[ROOM][0].replacement = ["蜜莓"]
    other_room, other_index = ROOM, 1
    if different_rooms:
        plan[ROOM][1] = Room("杜林", "", [])
        other_room, other_index = "dormitory_2", 0
        plan[other_room] = [Room("蜜莓", "公招", [RESIDENT]), Room("冰酿", "", [])]
        plan[other_room] += [Room("Free", "", []) for _ in range(3)]
    else:
        plan[ROOM][1] = Room("蜜莓", "公招", [WORKER] if mixed else [RESIDENT])
    if mixed:
        plan["contact"][0].replacement = [RESIDENT]
    return solver, (other_room, other_index)


@pytest.mark.parametrize("different_rooms", [False, True])
def test_same_group_dorm_primaries_swap_without_recovery_bed_records(
    monkeypatch, different_rooms
):
    solver, other = make_dorm_pair(monkeypatch, different_rooms=different_rooms)
    initialize(solver)
    data = solver.op_data
    assert data.group_dorm == []
    assert data.group_dorm_bed_count(data.groups["公招"]) == 0
    plan, covers = {}, []
    solver.get_resting_plan(data.groups["公招"].copy(), covers, plan, 0)
    assert plan["contact"] == ["黑角"]
    assert plan[ROOM][0] == "蜜莓"
    assert plan[other[0]][other[1]] == RESIDENT
    base_schedule._merge_dorm_arrangement(plan, try_reorder(data, plan) or {})
    projected = data.project_arrangements([plan])
    for name, native, index in ((RESIDENT, ROOM, 0), ("蜜莓", *other)):
        op = projected.operators[name]
        assert (op.room, op.index, op.group) == (native, index, "公招")
        assert op.is_high()
        assert projected.get_dorm_by_name(name) == (None, None)
    assert sum(bool(bed.name) for bed in projected.all_dorms()) == 1
    assert projected.get_dorm_by_name(WORKER)[1] is not None
    solver.op_data = projected
    solver._suppress_train_correction = lambda plan: None
    assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
    projected.get_dorm_by_name(WORKER)[1].time = datetime.now() + timedelta(hours=2)
    returned = next(
        task for task in plan_metadata(projected, []) if task.type == TaskTypes.SHIFT_ON
    )
    assert returned.plan["contact"] == [WORKER]
    assert returned.plan[ROOM][0] == RESIDENT
    assert returned.plan[other[0]][other[1]] == "蜜莓"


def test_dorm_and_working_primary_cycle_tracks_only_working_recovery(monkeypatch):
    solver, other = make_dorm_pair(monkeypatch, mixed=True)
    initialize(solver)
    data = solver.op_data
    assert data.get_group_dorm(ROOM, 0) is None
    assert data.get_group_dorm(*other) is not None
    assert data.group_dorm_bed_count(data.groups["公招"]) == 1
    plan, covers = {}, []
    solver.get_resting_plan(data.groups["公招"].copy(), covers, plan, 0)
    assert plan["contact"] == [RESIDENT]
    assert plan[ROOM][:2] == ["蜜莓", WORKER]
    assert all(not bed.name for bed in data.dorm)
    projected = data.project_arrangements([plan])
    assert projected.get_dorm_by_name("蜜莓") == (None, None)
    assert projected.get_dorm_by_name(WORKER)[1].position == other
    assert not projected.is_effective_free_slot(projected.get_group_dorm(*other))
    solver.op_data = projected
    solver._suppress_train_correction = lambda plan: None
    assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}


@pytest.mark.parametrize("blocked", ["busy", "reserved", "missing"])
def test_unavailable_dorm_primary_keeps_entire_group_native(monkeypatch, blocked):
    solver, _ = make_dorm_pair(monkeypatch)
    initialize(solver)
    data = solver.op_data
    if blocked == "busy":
        monkeypatch.setattr(
            base_schedule, "_is_mastery_busy", lambda name: name == "蜜莓"
        )
    elif blocked == "reserved":
        data.reserved_product_replacements.add("蜜莓")
    else:
        data.operators["蜜莓"].current_room = "train"
    before = data.get_current_room(ROOM, True)
    plan, covers = {}, []
    solver.get_resting_plan(data.groups["公招"].copy(), covers, plan, 0)
    assert plan == {} and covers == []
    assert data.get_current_room(ROOM, True) == before
    assert all(not bed.name for bed in data.all_dorms())


def test_dorm_swap_exhaust_matching_does_not_add_dorm_exhaustion_triggers(monkeypatch):
    solver, _ = make_dorm_pair(monkeypatch)
    solver.global_plan["default_plan"].config.exhaust_require = [
        WORKER,
        RESIDENT,
        "蜜莓",
    ]
    initialize(solver)
    data = solver.op_data
    assert data.exhaust_agent == {WORKER}
    data.operators[WORKER].mood = 0
    data.operators[RESIDENT].mood = data.operators["蜜莓"].mood = 0
    assert solver._plan_exhaust_support(data.groups["公招"].copy()) == {}
    plan, covers = {}, []
    solver.get_resting_plan(data.groups["公招"].copy(), covers, plan, 0)
    assert plan[ROOM][:2] == ["蜜莓", RESIDENT]
    assert sum(bool(bed.name) for bed in data.all_dorms()) == 1


def test_temporarily_absent_dorm_primaries_do_not_trigger_normal_shift(monkeypatch):
    solver, _ = make_dorm_pair(monkeypatch)
    initialize(solver)
    data = solver.op_data
    data.operators[WORKER].mood = 24
    for name in (RESIDENT, "蜜莓"):
        data.operators[name].current_room, data.operators[name].current_index = "", -1
        data.operators[name].mood = 0
    solver.find_next_task = MagicMock(return_value=None)
    assert solver._plan_primary_recovery(scan_moods=False)
    assert solver.tasks == []
    assert RESIDENT not in {op.name for op in solver.total_agent}
    assert "蜜莓" not in {op.name for op in solver.total_agent}
    solver._suppress_train_correction = lambda plan: None
    correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert "contact" not in correction
    assert correction[ROOM][:2] == [RESIDENT, "蜜莓"]


@pytest.mark.parametrize("invalid", ["empty", "different", "self"])
def test_dorm_primary_replacements_reject_invalid_group_or_self(monkeypatch, invalid):
    solver, _ = make_dorm_pair(monkeypatch)
    plan = solver.global_plan["default_plan"].plan
    if invalid == "empty":
        plan[ROOM][0].group = plan[ROOM][1].group = ""
    elif invalid == "different":
        plan[ROOM][1].group = "其他"
    else:
        plan[ROOM][0].replacement = [RESIDENT]
    assert "替换组不可用高效组干员: 房间->dormitory_3" in solver.initialize_operators()


def test_dorm_swaps_do_not_reduce_required_working_bed_capacity(monkeypatch):
    solver, _ = make_dorm_pair(monkeypatch)
    plan = solver.global_plan["default_plan"].plan
    for i, (primary, cover) in enumerate(
        (("陈", "夜莺"), ("银灰", "芬"), ("能天使", "砾"))
    ):
        plan[f"room_{i + 1}_1"] = [Room(primary, "公招", [cover])]
    assert (
        solver.initialize_operators()
        == "公招 分组无法排班,所需宿舍数4大于当前有效宿舍数3"
    )


@pytest.mark.parametrize("mixed", [False, True])
def test_dorm_primary_exchange_confirms_actual_single_recovery_and_countdown(
    monkeypatch, mixed
):
    from arknights_mower.utils.operators import Operator

    solver, _ = make_dorm_pair(monkeypatch, mixed=mixed)
    initialize(solver)
    final = [
        "蜜莓",
        WORKER if mixed else RESIDENT,
        "陈" if mixed else WORKER,
        "银灰" if mixed else "陈",
        "黑角" if mixed else "银灰",
    ]
    mock_arrangement(
        solver, monkeypatch, final, contact_cover=RESIDENT if mixed else "黑角"
    )
    if not mixed:
        solver.op_data.operators[RESIDENT].mood = 0
        solver.op_data.add(Operator("芬", "", mood=24, time_stamp=datetime.now()))
    solver.agent_arrange_room({}, ROOM, solver.task.plan)
    target = solver.op_data.operators[WORKER]
    assert solver.physical == final
    assert target.dorm_recovery_index == (1 if mixed else 2)
    assert tuple(name for name, _, _ in target.dorm_recovery_fixed) == ("蜜莓",)
    assert target.dorm_recovery_index in solver.reads[-1]
    assert solver.op_data.get_dorm_by_name(WORKER)[1].time == solver.deadline
    assert solver.op_data.get_dorm_by_name("蜜莓") == (None, None)
    assert solver.op_data.get_dorm_by_name(RESIDENT) == (None, None)
    assert (
        sum(
            bool(bed.name) and solver.op_data.operators[bed.name].is_high()
            for bed in solver.op_data.all_dorms()
        )
        == 1
    )
