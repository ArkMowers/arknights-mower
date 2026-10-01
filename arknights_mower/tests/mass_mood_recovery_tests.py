"""集中恢复的触发、回班时刻和床位保护使用离线驻员快照。"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.utils import config, operators, scheduler_task  # noqa: E402
from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402

NOW = datetime(2026, 9, 30, 8)
PRIMARY = ["伊内丝", "银灰", "讯使", "能天使"]
COVERS = ["陈", "槐琥", "斥罪", "结城理"]


@pytest.fixture
def solver(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.enable_mastery = False
    config.conf.rescue_threshold = 0.75
    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    monkeypatch.setattr(operators, "datetime", Clock)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    data = Operators(
        {
            "default_plan": Plan(
                {
                    **{
                        f"room_{(index - 1) // 3 + 1}_{(index - 1) % 3 + 1}": [
                            Room(name, "", [COVERS[index - 1]])
                        ]
                        for index, name in enumerate(PRIMARY, 1)
                    },
                    "dormitory_1": [Room("冰酿", "", []), Room("闪灵", "", [])]
                    + [Room("Free", "", []) for _ in range(3)],
                },
                PlanConfig("", "", "", resting_priority_replacement=",".join(COVERS)),
            ),
            "backup_plans": [],
        }
    )
    assert data.init_and_validate() is None
    for operator in data.operators.values():
        operator.mood, operator.time_stamp, operator.depletion_rate = 24, NOW, 0
        operator._current_room, operator.current_index = operator.room, operator.index
    instance = object.__new__(base_schedule.BaseSchedulerSolver)
    instance.op_data = data
    instance.tasks, instance.task = [], None
    instance.check_fia = MagicMock(return_value=(None, None))
    instance._refresh_deferred_product_reservations = MagicMock()
    instance.enter_room = MagicMock(
        side_effect=AssertionError("unexpected device read")
    )
    return instance


def set_moods(data, values):
    for name, mood in zip(PRIMARY, values):
        data.operators[name].mood = mood


def admit(data, names, hours, *, activate=True):
    if activate:
        data.rescue_needed()
    plan = {"dormitory_1": ["冰酿", "闪灵", *names, *(["Free"] * (3 - len(names)))]}
    for name in names:
        operator = data.operators[name]
        if operator.is_high():
            plan[operator.room] = [operator.replacement[0]]
    projected = data.project_arrangements([plan])
    for name, duration in zip(names, hours):
        projected.get_dorm_by_name(name)[1].time = NOW + timedelta(hours=duration)
    return projected


def test_stale_early_return_is_rebuilt_before_execution(solver):
    data = solver.op_data
    set_moods(data, [0] * 4)
    solver.op_data = admit(data, PRIMARY[:1], [5])
    stale = SchedulerTask(NOW, {"room_1_1": [PRIMARY[0]]}, TaskTypes.SHIFT_ON)
    order = SchedulerTask(NOW + timedelta(hours=1), task_type=TaskTypes.RUN_ORDER)
    solver.tasks = [stale, order]
    solver.task = stale
    solver.plan_metadata()
    assert not any(task is stale for task in solver.tasks)
    assert order in solver.tasks
    solver.find = MagicMock(return_value=True)
    solver.skip = MagicMock()
    solver.agent_arrange = MagicMock()
    assert solver.infra_main()
    solver.agent_arrange.assert_not_called()


def test_reordering_keeps_protected_residents_in_their_beds(solver):
    data = solver.op_data
    set_moods(data, [0] * 4)
    data.operators[COVERS[0]].mood = 0
    data = admit(data, COVERS[:1], [5])
    data.rescue_needed()
    position = data.get_dorm_by_name(COVERS[0])[1].position
    data.assign_dorm(PRIMARY[1])
    plan = scheduler_task.try_reorder(data, {"room_1_2": [COVERS[1]]})
    assert plan.get(position[0], ["Current"] * 5)[position[1]] == "Current"
    assert data.get_dorm_by_name(COVERS[0])[1].position == position
    assert data.get_dorm_by_name(COVERS[0])[1].time == NOW + timedelta(hours=5)


def test_rescue_exclusions_follow_shared_resting_rules(solver):
    data = solver.op_data
    set_moods(data, [0] * 4)
    data.rescue_needed()
    resident = data.operators["冰酿"]
    resident.replacement = COVERS[:3]
    data.config.free_blacklist.append(COVERS[0])
    data.operators[COVERS[1]].workaholic = True
    assert data.assign_dorm(COVERS[0]) is None
    assert data.assign_dorm(COVERS[1]) is None
    rescue_covers = data.replacement_candidates(resident)
    data.rescue_mode = False
    assert data.replacement_candidates(resident) == rescue_covers


@pytest.mark.parametrize(
    "moods,expected",
    [([0, 0, 24, 24], True), ([0, 24, 24, 24], False), ([9] * 4, False)],
)
def test_majority_trigger_uses_individual_rescue_lines(solver, moods, expected):
    set_moods(solver.op_data, moods)
    assert solver.op_data.rescue_needed() is expected


@pytest.mark.parametrize("grouped", [False, True])
def test_recovery_uses_full_bed_deadlines_not_thirty_minutes(solver, grouped):
    data = solver.op_data
    set_moods(data, [0] * 4)
    if grouped:
        data.groups["恢复"] = PRIMARY[:2]
        for name in PRIMARY[:2]:
            data.operators[name].group = "恢复"
    data = admit(data, PRIMARY[:2], [5, 6])
    retained = [
        SchedulerTask(NOW + timedelta(hours=2), task_type=TaskTypes.RUN_ORDER),
        SchedulerTask(NOW + timedelta(minutes=2), task_type=TaskTypes.SKILL_UPGRADE),
    ]
    tasks = scheduler_task.plan_metadata(data, retained)
    returns = [task for task in tasks if task.type == TaskTypes.SHIFT_ON]
    assert all(any(task is original for task in tasks) for original in retained)
    assert sorted(task.time for task in returns) == (
        [NOW + timedelta(hours=6)]
        if grouped
        else [NOW + timedelta(hours=5), NOW + timedelta(hours=6)]
    )


def test_unknown_recovery_deadline_does_not_recall_group(solver):
    data = solver.op_data
    set_moods(data, [0] * 4)
    data.groups["恢复"] = PRIMARY[:2]
    for name in PRIMARY[:2]:
        data.operators[name].group = "恢复"
    data = admit(data, PRIMARY[:2], [5, 6])
    data.get_dorm_by_name(PRIMARY[1])[1].time = None
    tasks = scheduler_task.plan_metadata(data, [])
    assert not any(task.type == TaskTypes.SHIFT_ON for task in tasks)


def test_mass_recovery_allows_exhaust_group_to_rest_before_zero(solver):
    data = solver.op_data
    set_moods(data, [5] * 4)
    data.exhaust_agent.update(PRIMARY[:2])
    data.exhaust_group.add("恢复")
    data.groups["恢复"] = PRIMARY[:2]
    for name in PRIMARY[:2]:
        data.operators[name].group = "恢复"
        data.operators[name].exhaust_require = True
    solver.total_agent = list(data.operators.values())
    plan = solver.resting()
    assert data.rescue_mode
    assert solver.ideal_resting_count == len(data.dorm)
    assert plan["room_1_1"] == [COVERS[0]]
    assert plan["room_1_2"] == [COVERS[1]]
    assert {bed.name for bed in data.dorm} >= set(PRIMARY[:2])
    solver.enter_room.assert_not_called()


def test_no_support_recall_of_unrecovered_group(solver):
    data = solver.op_data
    set_moods(data, [0] * 4)
    data = admit(data, PRIMARY[:1], [5])
    data.operators[PRIMARY[1]].replacement = [COVERS[0]]
    data.rescue_needed()
    solver.op_data = data
    assert solver._plan_exhaust_support([PRIMARY[1]]) is None
    assert data.operators[PRIMARY[0]].is_resting()


def test_one_low_operator_out_of_two_does_not_enter(solver):
    data = solver.op_data
    data.main_recovery_limits = {
        name: data.main_recovery_limits[name] for name in PRIMARY[:2]
    }
    set_moods(data, [0, 24, 24, 24])
    assert not data.rescue_needed()


def test_rescue_ordinary_filling_uses_only_remaining_vacancies(solver):
    data = solver.op_data
    set_moods(data, [0] * 4)
    data.rescue_needed()
    scheduler_task.try_add_release_dorm({}, None, data, solver.tasks, empty_only=True)
    assert len(solver.tasks) == 1
    fill = solver.tasks[0]
    assert fill.type == TaskTypes.FILL_DORM
    vacancies = scheduler_task.vacant_dorm_slots(data)
    assert all(
        (room, index) in vacancies
        for room, names in fill.plan.items()
        for index, name in enumerate(names)
        if name != "Current"
    )


def test_unknown_readings_do_not_count_as_low_baseline_mood(solver):
    data = solver.op_data
    set_moods(data, [0] * 4)
    for name in PRIMARY[1:]:
        data.operators[name].time_stamp = None
    assert not data.rescue_needed()


def test_zero_mood_workers_and_blacklist_are_excluded_from_baseline(solver):
    original = solver.op_data
    original.config.workaholic = PRIMARY[:1]
    original.config.free_blacklist = PRIMARY[1:2]
    assert original.init_and_validate() is None
    assert set(original.main_recovery_limits) == set(PRIMARY[2:])
    set_moods(original, [0, 0, 24, 24])
    assert not original.rescue_needed()


def test_custom_ranges_wait_until_majority_completes_recovery(solver):
    data = solver.op_data
    data.config.operator_mood_limits = {
        name: {"lower": 10, "upper": 20} for name in PRIMARY
    }
    assert data.init_and_validate() is None
    set_moods(data, [13, 13, 20, 20])
    assert data.rescue_needed()
    set_moods(data, [15, 15, 20, 20])
    assert data.rescue_needed()
    set_moods(data, [20, 15, 20, 20])
    assert not data.rescue_needed()
    assert not data.rescue_armed


def test_completed_baseline_snapshot_is_isolated_in_projection(solver):
    data = solver.op_data
    set_moods(data, [0, 0, 24, 24])
    assert data.rescue_needed()
    assert data.rescue_completed == set(PRIMARY[2:])
    projected = data.project_arrangements([])
    projected.rescue_completed.clear()
    assert data.rescue_completed == set(PRIMARY[2:])


def test_active_rescue_backup_keeps_unfinished_primary_protected_after_mode_exit(
    solver,
):
    data = solver.op_data
    set_moods(data, [0] * 4)
    data = admit(data, PRIMARY[:1], [5])
    set_moods(data, [0, 24, 24, 24])
    assert not data.rescue_needed()
    data.rescue_plan_active = True
    assert data.is_rescue_recovering(PRIMARY[0])
    data.operators[PRIMARY[0]].mood = data.operators[PRIMARY[0]].upper_limit
    assert not data.is_rescue_recovering(PRIMARY[0])


def test_protected_replacement_keeps_bed_and_is_not_borrowed(solver):
    data = solver.op_data
    set_moods(data, [0] * 4)
    data.operators[COVERS[0]].mood = 0
    data = admit(data, [COVERS[0]], [5])
    bed = data.get_dorm_by_name(COVERS[0])[1]
    assert data.is_rescue_recovering(COVERS[0])
    assert not data._slot_takable(bed, False, requester=PRIMARY[0])
    assert COVERS[0] not in data.replacement_candidates(data.operators[PRIMARY[0]])
    data.operators[COVERS[0]].mood = data.operators[COVERS[0]].upper_limit
    data.rescue_needed()
    assert not data.is_rescue_recovering(COVERS[0])
    assert COVERS[0] in data.replacement_candidates(data.operators[PRIMARY[0]])


def test_zero_rescue_threshold_disables_protection(solver):
    data = solver.op_data
    set_moods(data, [0] * 4)
    data = admit(data, PRIMARY[:1], [5])
    assert data.rescue_needed()
    config.conf.rescue_threshold = 0
    assert not data.rescue_needed()
    assert not data.is_rescue_recovering(PRIMARY[0])


def test_unknown_formal_recovery_resident_is_not_borrowed(solver):
    data = solver.op_data
    set_moods(data, [0] * 4)
    data = admit(data, [COVERS[0]], [5])
    data.operators[COVERS[0]].time_stamp = None
    assert data.is_rescue_recovering(COVERS[0])
    assert COVERS[0] not in data.replacement_candidates(data.operators[PRIMARY[0]])
    bed = data.get_dorm_by_name(COVERS[0])[1]
    assert not data._slot_takable(bed, False, requester=PRIMARY[0])


def test_majority_completion_requires_fresh_trigger_before_reentry(solver):
    data = solver.op_data
    set_moods(data, [0] * 4)
    assert data.rescue_needed()
    set_moods(data, [24, 24, 24, 0])
    assert not data.rescue_needed()
    set_moods(data, [0, 0, 0, 0])
    assert not data.rescue_needed()
    set_moods(data, [24] * 4)
    assert not data.rescue_needed()
    set_moods(data, [0] * 4)
    assert data.rescue_needed()
