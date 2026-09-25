"""深海一高优、六候补：显式启用待命，原低优保持原有行为。"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.config.plan import PlanModel  # noqa: E402
from arknights_mower.utils.log import logger  # noqa: E402
from arknights_mower.utils.operators import Operator, build_global_plan  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.resting_priority import (  # noqa: E402
    RestingTier,
    resting_tier,
)
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    plan_metadata,
    try_add_release_dorm,
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
    config.conf.experimental_dorm_logic = True
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
            rooms,
            PlanConfig(
                "",
                "",
                "",
                resting_standby=",".join(DEEP[1:]),
                ope_resting_priority=DEEP[0],
                experimental_dorm_logic=True,
            ),
        ),
        "backup_plans": [],
    }
    assert instance.initialize_operators() is None
    instance.tasks = []
    instance.find_next_task = MagicMock(return_value=None)
    instance.enter_room = MagicMock(
        side_effect=AssertionError("unexpected device read")
    )
    # 本夹具只验证宿舍调度；模拟训练室刚被扫描，避免无设备实例进入读房流程。
    instance.last_train_mood_read = datetime.now()
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
    assert {name for name in DEEP if data.is_standby(name)} == expected_standby
    assert data.operators[DEEP[0]].is_resting()
    assert [data.operators[n].resting_priority for n in DEEP] == [
        "high",
        *["standby"] * 6,
    ]
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
    assert not any(data.is_standby(name) for name in DEEP)
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
    assert all(solver.op_data.is_standby(n) for n in DEEP[1:])


@pytest.mark.parametrize(
    "failure", ["no_bed", "exhaust", "full", "no_anchor", "full_anchor", "cover"]
)
def test_required_beds_and_replacements_fail_without_partial_assignment(
    solver, failure
):
    occupy_beds(solver, "high")
    data = solver.op_data
    if failure == "no_bed":
        data.config.ope_resting_priority = []
        data.add(
            Operator(
                "年", "meeting", operator_type="high", resting_priority="high", mood=5
            )
        )
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
    assert all(solver.op_data.is_standby(n) for n in DEEP[1:])
    assert solver.agent_get_mood() is None
    assert solver.tasks == []


def test_missing_cover_is_repaired_without_recalling_standby_group(solver):
    occupy_beds(solver, "low")
    shift_off(solver)
    apply_plan(solver, {"meeting": ["Free", "Current"]})
    assert not solver.op_data.is_standby(DEEP[1])
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
    assert not data.is_standby(DEEP[1])


def test_ordinary_low_cannot_evict_resting_main_or_another_replacement(solver):
    occupy_beds(solver, "replacement")
    data = solver.op_data
    data.add(Operator("年", "", mood=5))
    data.plan["central"][0].replacement.append("年")
    room, index = data.dorm[0].position
    names = ["Current"] * 5
    names[index] = "年"
    apply_plan(solver, {room: names})
    assert data.assign_dorm(COVERS[0]) is None
    shift_off(solver)
    assert data.assign_dorm(COVERS[0]) is None


@pytest.mark.parametrize("occupants", ["replacement", "high", "low"])
def test_low_main_requires_beds_but_can_take_resting_replacements(solver, occupants):
    conf = solver.global_plan["default_plan"].config
    conf.resting_standby = []
    conf.resting_priority = DEEP[1:]
    assert solver.initialize_operators() is None
    occupy_beds(solver, occupants)
    data = solver.op_data
    data.operators[DEEP[0]].mood = 0
    before = [(bed.name, bed.time) for bed in data.dorm]
    plan, replacements = {}, []
    solver.get_resting_plan(data.groups["深海"], replacements, plan, 0)
    if occupants == "replacement":
        assert replacements == COVERS
        assert {bed.name for bed in data.dorm} >= set(DEEP)
        assert plan
        return
    assert plan == {}
    assert replacements == []
    assert [(bed.name, bed.time) for bed in data.dorm] == before
    assert all(data.operators[name].resting_priority == "low" for name in DEEP[1:])


@pytest.mark.parametrize(
    "name,invalid",
    [
        (COVERS[0], "replacement"),
        ("塑心", "dorm"),
        (DEEP[1], "workaholic"),
        (DEEP[1], "exhaust_require"),
        (DEEP[1], "rest_in_full"),
    ],
)
def test_candidate_setting_only_applies_to_eligible_main(solver, name, invalid):
    conf = solver.global_plan["default_plan"].config
    conf.resting_standby = [name]
    if invalid in ("workaholic", "exhaust_require", "rest_in_full"):
        setattr(conf, invalid, [name])
    assert solver.initialize_operators() is None
    assert solver.op_data.operators[name].resting_priority != "standby"
    assert not solver.op_data._can_standby(solver.op_data.operators[name])


def test_workshop_selection_does_not_disable_group_standby(solver):
    name = DEEP[1]
    solver.global_plan["default_plan"].config.resting_standby = [name]
    config.conf.t5_operators = [name]
    assert solver.initialize_operators() is None
    assert solver.op_data.operators[name].resting_priority == "standby"
    assert solver.op_data._can_standby(solver.op_data.operators[name])


def test_ungrouped_candidate_waits_without_bed_and_fills_later_free_bed(solver):
    name = OTHERS[0]
    observed = {
        room: [slot.agent for slot in slots]
        for room, slots in solver.op_data.plan.items()
    }
    solver.global_plan["default_plan"].config.resting_standby = [name]
    assert solver.initialize_operators() is None
    apply_plan(solver, observed)
    data = solver.op_data
    now = datetime.now()

    occupants = [OTHERS[1], *OTHERS[2:], DEEP[0], DEEP[1]]
    assert len(occupants) == len(data.dorm)
    for index, (bed, occupant_name) in enumerate(zip(data.dorm, occupants)):
        occupant = data.operators[occupant_name]
        occupant.current_room, occupant.current_index = bed.position
        occupant.resting_priority = "high"
        occupant.mood = 5
        occupant.time_stamp = now
        bed.name = occupant_name
        bed.time = now + timedelta(hours=1 if index == 0 else 2)

    candidate = data.operators[name]
    # 默认急救线为 50% 换班阈值 × 75% 急救阈值，即 9 点；10 点仍为候补。
    candidate.mood = 10
    candidate.time_stamp = now
    solver.total_agent = [candidate]

    plan = solver.resting()

    assert plan == {"room_1_1": [OTHER_COVERS[0], "Current", "Current"]}
    assert candidate.resting_priority == "standby"
    assert data.get_dorm_by_name(name)[0] is None
    apply_plan(solver, plan)
    assert data.is_standby(name)

    tasks = plan_metadata(data, [])
    assert all(
        name not in {agent for agents in task.plan.values() for agent in agents}
        for task in tasks
        if task.type == TaskTypes.SHIFT_ON
    )

    data.config.free_room = True
    bed = next(
        bed for bed in data.dorm if data.is_effective_free_slot(bed) and bed.name
    )
    occupant = data.get_current_operator(*bed.position)
    occupant.current_room, occupant.current_index = "", -1
    bed.reset()
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks
    room, index = bed.position
    assert tasks[0].plan[room][index] == name


def test_full_standby_does_not_refill_vacant_bed(solver):
    occupy_beds(solver, "high")
    shift_off(solver)
    data = solver.op_data
    data.config.free_room = True
    for op in data.operators.values():
        op.mood, op.depletion_rate, op.time_stamp = 24, 0, datetime.now()
    assert data.is_standby(DEEP[1])
    bed = data.dorm[-1]
    data.operators[bed.name].current_room = ""
    bed.reset()
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks == []


def test_grouped_candidate_fills_on_deferral_without_changing_return_time(solver):
    occupy_beds(solver, "high")
    shift_off(solver)
    data = solver.op_data
    candidate = DEEP[1]
    assert data.is_standby(candidate)

    data.config.free_room = True
    baseline_tasks = plan_metadata(data, [])
    baseline_return_time = min(
        task.time for task in baseline_tasks if task.type == TaskTypes.SHIFT_ON
    )
    bed = next(
        bed
        for bed in data.dorm
        if data.is_effective_free_slot(bed) and bed.name and bed.name not in DEEP
    )
    occupant = data.get_current_operator(*bed.position)
    occupant.current_room, occupant.current_index = "", -1
    bed.reset()

    tasks = plan_metadata(data, [])
    return_tasks = [task for task in tasks if task.type == TaskTypes.SHIFT_ON]
    assert return_tasks
    solver.tasks = tasks
    assert not solver._fill_dorm_after_run_order_deferral()
    assert all(task.type == TaskTypes.SHIFT_ON for task in tasks)
    deferred = SchedulerTask()
    deferred.deferred_by_run_order = True
    tasks.append(deferred)
    assert solver._fill_dorm_after_run_order_deferral()
    assert not solver._fill_dorm_after_run_order_deferral()
    fill_tasks = [
        task
        for task in tasks
        if task.type != TaskTypes.SHIFT_ON
        and candidate in {agent for agents in task.plan.values() for agent in agents}
    ]
    assert fill_tasks
    room, index = bed.position
    assert fill_tasks[0].plan[room][index] == candidate
    assert abs(
        min(task.time for task in return_tasks) - baseline_return_time
    ) < timedelta(seconds=1)


def test_candidate_below_rescue_line_stays_low_until_return(solver):
    data = solver.op_data
    candidate = data.operators[DEEP[1]]
    now = datetime.now()
    candidate.time_stamp = now
    candidate.mood = 8.9

    data.update_standby_low_priority(candidate, now)
    assert candidate.standby_low_priority
    assert solver._resting_tier(candidate).name == "LOW_MAIN"
    assert not data._can_standby(candidate)

    # 恢复越过急救线也不在休息途中降回候补。
    candidate.current_room, candidate.current_index = data.dorm[0].position
    candidate.mood = 20
    data.update_standby_low_priority(candidate, now)
    assert candidate.standby_low_priority
    assert solver._resting_tier(candidate).name == "LOW_MAIN"

    # 实际回到自己的工作位后解除本轮升级。
    data.update_detail(candidate.name, 20, candidate.room, candidate.index)
    assert not candidate.standby_low_priority
    assert solver._resting_tier(candidate).name == "STANDBY"


@pytest.mark.parametrize("previous_room", ["dormitory_1", ""])
def test_low_mood_return_resets_rescue_but_working_candidate_can_escalate(
    solver, previous_room
):
    data = solver.op_data
    candidate = data.operators[DEEP[1]]
    candidate.current_room = previous_room
    candidate.current_index = 2 if previous_room else -1
    candidate.standby_low_priority = True
    candidate.time_stamp = datetime.now()

    data.update_detail(candidate.name, 8.9, candidate.room, candidate.index)
    assert not candidate.standby_low_priority
    assert data._can_standby(candidate)

    # 下一次在岗读数仍低于急救线时，可开启新一轮急救，不能永久豁免。
    data.update_detail(candidate.name, 8.8, candidate.room, candidate.index)
    assert candidate.standby_low_priority
    assert not data._can_standby(candidate)


def test_candidate_below_rescue_line_cannot_wait_without_bed(solver):
    occupy_beds(solver, "high")
    data = solver.op_data
    candidate = data.operators[DEEP[1]]
    candidate.mood = 8.9
    candidate.time_stamp = datetime.now()
    data.update_standby_low_priority(candidate)

    before = [(bed.name, bed.time) for bed in data.dorm]
    plan, replacements = {}, []
    solver.get_resting_plan(data.groups["深海"], replacements, plan, 0)

    assert plan == {}
    assert replacements == []
    assert [(bed.name, bed.time) for bed in data.dorm] == before


def test_ungrouped_candidate_extension_is_disabled_with_stable_logic(solver):
    name = OTHERS[0]
    conf = solver.global_plan["default_plan"].config
    conf.resting_standby = [name]
    conf.experimental_dorm_logic = False

    assert solver.initialize_operators() is None
    assert solver.op_data.operators[name].resting_priority != "standby"
    assert not solver.op_data._can_standby(solver.op_data.operators[name])


def test_normal_low_gets_last_spare_bed_before_candidate(solver):
    occupy_beds(solver, "high")
    data = solver.op_data
    normal = data.operators[DEEP[1]]
    normal.resting_priority = "low"
    room, index = data.dorm[1].position
    names = ["Current"] * 5
    names[index] = "Free"
    apply_plan(solver, {room: names})
    beds = data.assign_dorm_group(DEEP)
    assert {bed.name for bed in beds} == {DEEP[0], DEEP[1]}
    assert data.operators[DEEP[2]].resting_priority == "standby"


def test_priority_rearrangement_preserves_explicit_candidates(solver):
    before = solver.op_data.groups["深海"].copy()
    solver.rearrange_resting_priority("深海")
    assert solver.op_data.groups["深海"] == before
    assert all(
        solver.op_data.operators[name].resting_priority == "standby"
        for name in DEEP[1:]
    )
    assert solver.op_data.operators[DEEP[0]].resting_priority == "high"


def test_normal_low_controls_return_before_candidate_when_no_high_member(solver):
    data = solver.op_data
    data.operators[DEEP[0]].resting_priority = "low"
    shift_off(solver)
    now = datetime.now()
    for bed in data.dorm:
        if bed.name in DEEP:
            bed.time = now + (
                timedelta(hours=8) if bed.name == DEEP[0] else timedelta(minutes=10)
            )
    tasks = plan_metadata(data, [])
    back = next(task for task in tasks if DEEP[0] in task.plan.get("central", []))
    assert back.time > now + timedelta(hours=7)


def test_normal_low_precedes_candidate_in_resting_and_dorm_order(solver):
    data = solver.op_data
    data.operators[DEEP[1]].resting_priority = "low"
    data.operators[DEEP[1]].mood = 20
    # 高于默认 9 点急救线，仍保持候补层级。
    data.operators[DEEP[2]].mood = 10
    assert solver._resting_tier(data.operators[DEEP[1]]) < solver._resting_tier(
        data.operators[DEEP[2]]
    )
    shift_off(solver)
    names = [bed.name for bed in data.dorm]
    assert names.index(DEEP[1]) < names.index(DEEP[2])


def test_candidate_config_round_trip_and_backup_merge(solver, monkeypatch):
    raw = {
        "plan1": {
            room: {
                "plans": [
                    {
                        "agent": slot.agent,
                        "group": slot.group,
                        "replacement": slot.replacement,
                    }
                    for slot in slots
                ]
            }
            for room, slots in solver.global_plan["default_plan"].plan.items()
        },
        "conf": {"resting_priority": DEEP[1]},
        "backup_plans": [{"conf": {"resting_standby": DEEP[2]}}],
    }
    old = PlanModel(**raw)
    assert old.conf.resting_standby == ""
    assert old.conf.resting_priority_replacement == ""
    assert old.conf.free_room_exclusions == ""
    old.conf.free_room_exclusions = OTHER_COVERS[0]
    old.backup_plans[0].conf.free_room_exclusions = ",".join(OTHER_COVERS[:2])
    old.conf.resting_priority_replacement = OTHER_COVERS[0]
    old.backup_plans[0].conf.resting_priority_replacement = ",".join(OTHER_COVERS[:2])
    old.conf.resting_standby = DEEP[1]
    loaded = PlanModel.model_validate_json(old.model_dump_json())
    monkeypatch.setattr(config, "plan", loaded)
    solver.global_plan = build_global_plan()
    assert solver.initialize_operators() is None
    assert (
        resting_tier(solver.op_data, OTHER_COVERS[0])
        == RestingTier.PRIORITY_REPLACEMENT
    )
    assert resting_tier(solver.op_data, OTHER_COVERS[1]) == RestingTier.REPLACEMENT
    assert solver.op_data.operators[DEEP[1]].resting_priority == "standby"
    assert solver.op_data.operators[DEEP[2]].resting_priority == "high"
    assert solver.op_data.swap_plan([True], refresh=True) is None
    assert (
        resting_tier(solver.op_data, OTHER_COVERS[1])
        == RestingTier.PRIORITY_REPLACEMENT
    )
    assert solver.op_data.config.resting_priority_replacement == OTHER_COVERS[:2]
    assert solver.op_data.config.free_room_exclusions == OTHER_COVERS[:2]
    assert solver.op_data.operators[DEEP[2]].resting_priority == "standby"
    assert solver.op_data.swap_plan([False], refresh=True) is None
    assert solver.op_data.config.free_room_exclusions == [OTHER_COVERS[0]]
    assert resting_tier(solver.op_data, OTHER_COVERS[1]) == RestingTier.REPLACEMENT
    assert solver.op_data.operators[DEEP[2]].resting_priority == "high"
