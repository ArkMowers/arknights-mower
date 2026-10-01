import sys
from copy import deepcopy
from datetime import datetime, timedelta
from importlib import import_module
from threading import Event
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import config, operators, scheduler_task
from arknights_mower.utils.dorm_candidates import dorm_candidates
from arknights_mower.utils.exhaust_replacement import plan_exhaust_support
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.resting_priority import RestingTier, resting_tier
from arknights_mower.utils.scheduler_task import TaskTypes, plan_metadata

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())
base_schedule = import_module("arknights_mower.solvers.base_schedule")

NOW = datetime(2026, 9, 30, 8)
PRIMARY = ["伊内丝", "银灰", "讯使", "能天使"]
COVERS = ["陈", "槐琥", "斥罪", "结城理"]
ROOMS = ["room_1_1", "room_1_2", "room_1_3", "room_2_1"]


@pytest.fixture
def data(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.enable_mastery = False
    config.conf.rescue_threshold = 0.75
    monkeypatch.setattr(operators, "datetime", Clock)
    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    instance = Operators(
        {
            "default_plan": Plan(
                {
                    **{
                        room: [Room(name, "", [cover])]
                        for room, name, cover in zip(ROOMS, PRIMARY, COVERS)
                    },
                    "dormitory_1": [Room("冰酿", "", []), Room("闪灵", "", [])]
                    + [Room("Free", "", []) for _ in range(3)],
                },
                PlanConfig("", "", "", resting_priority_replacement="斥罪"),
            ),
            "backup_plans": [],
        }
    )
    assert instance.init_and_validate() is None
    for op in instance.operators.values():
        op.mood, op.time_stamp, op.depletion_rate = 24, NOW, 0
        op._current_room, op.current_index = op.room, op.index
    return instance


def set_moods(data, values):
    for name, mood in zip(PRIMARY, values):
        data.operators[name].mood = mood


def configure_rescue(data, plan=None, conf=None):
    backup = Plan(
        plan
        if plan is not None
        else {
            ROOMS[0]: [Room("陈", "救急", [])],
            ROOMS[1]: [Room("槐琥", "救急", [])],
        },
        conf or PlanConfig("", "", ""),
        LogicExpression("op_data.rescue_needed()", "==", "True"),
        name="救急",
    )
    data.global_plan["backup_plans"] = data.backup_plans = [backup]
    data.plan_condition = [False]
    return backup


def admit(data, names):
    arrangements = {
        "dormitory_1": ["冰酿", "闪灵", *names, *(["Free"] * (3 - len(names)))],
        **{
            data.operators[name].room: [data.operators[name].replacement[0]]
            for name in names
            if data.operators[name].is_high()
        },
    }
    projected = data.project_arrangements([arrangements])
    for name in names:
        projected.get_dorm_by_name(name)[1].time = NOW + timedelta(hours=4)
    return projected


@pytest.mark.parametrize(
    ("moods", "expected"),
    [([0, 24, 24, 24], False), ([0, 0, 24, 24], True), ([0, 0, 0, 0], True)],
)
def test_entry_uses_count_not_average_mood(data, moods, expected):
    set_moods(data, moods)
    assert data.rescue_needed() is expected
    assert data.evaluate_expression("op_data.rescue_needed() == True") is expected


def test_unknown_mood_never_votes_low_or_complete(data):
    set_moods(data, [0, 0, 0, 0])
    for name in PRIMARY[1:]:
        data.operators[name].time_stamp = None
    assert not data.rescue_needed()
    data.operators[PRIMARY[1]].time_stamp = NOW
    assert data.rescue_needed()
    set_moods(data, [24, 24, 24, 24])
    assert data.rescue_needed()


def test_entry_and_completion_follow_individual_main_plan_limits(data):
    baseline = data.global_plan["default_plan"].config
    baseline.mood_limits = {"lower": 4, "upper": 20}
    baseline.operator_mood_limits = {PRIMARY[0]: {"lower": 8, "upper": 16}}
    assert data.swap_plan([], refresh=True) is None
    set_moods(data, [10.9, 9.9, 9.9, 9.9])
    assert data.main_recovery_limits[PRIMARY[0]] == (8, 16)
    assert data.main_recovery_limits[PRIMARY[1]] == (4, 20)
    assert data.rescue_needed()
    set_moods(data, [15.9, 19.9, 19.9, 19.9])
    assert data.rescue_needed()
    set_moods(data, [16, 20, 19.9, 19.9])
    assert data.rescue_needed()
    set_moods(data, [16, 20, 20, 19.9])
    assert not data.rescue_needed()


def test_both_count_and_line_boundaries_are_strict(data):
    set_moods(data, [9, 9, 24, 24])
    assert not data.rescue_needed()
    set_moods(data, [8.9, 8.9, 24, 24])
    assert data.rescue_needed()
    assert data.rescue_needed()
    set_moods(data, [24, 8.9, 24, 24])
    assert not data.rescue_needed()


def test_completed_returns_are_counted_once_and_do_not_oscillate(data):
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    set_moods(data, [24, 0, 0, 0])
    assert data.rescue_needed()
    set_moods(data, [0, 24, 0, 0])
    assert data.rescue_needed()
    set_moods(data, [0, 0, 24, 0])
    assert not data.rescue_needed()
    assert not data.rescue_needed()
    set_moods(data, [24, 24, 24, 0])
    assert not data.rescue_needed()
    set_moods(data, [0, 0, 24, 24])
    assert data.rescue_needed()


def test_rescue_condition_projection_does_not_mutate_live_episode(data):
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    projected = data.project_arrangements([])
    set_moods(projected, [24, 24, 24, 0])
    assert not projected.rescue_needed()
    assert data.rescue_mode
    assert data.rescue_completed == set()
    assert data.operators[PRIMARY[0]].mood == 0


def test_disabled_rescue_clears_episode_without_dorm_changes(data):
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    before = deepcopy(data.dorm)
    config.conf.rescue_threshold = 0
    assert not data.rescue_needed()
    assert data.rescue_completed == set()
    assert [bed.name for bed in data.dorm] == [bed.name for bed in before]


def test_rescue_backup_workers_need_no_cover_and_restore_on_exit(data):
    backup = configure_rescue(data)
    set_moods(data, [0, 0, 0, 0])
    assert data.evaluate_expression(str(backup.trigger))
    assert data.swap_plan([True], refresh=True) is None
    for name in COVERS[:2]:
        assert data.operators[name].workaholic
        assert data.operators[name].replacement == []
        assert resting_tier(data, name) == RestingTier.EXCLUDED
        assert data.assign_dorm(name) is None
    assert not data.operators[PRIMARY[2]].workaholic
    assert data.swap_plan([False], refresh=True) is None
    assert not data.operators[COVERS[0]].workaholic
    assert data.plan[ROOMS[0]][0].agent == PRIMARY[0]


def test_custom_main_limits_survive_becoming_idle_in_rescue_backup(data):
    baseline = data.global_plan["default_plan"].config
    baseline.operator_mood_limits = {
        PRIMARY[0]: {"lower": 8, "upper": 16},
        COVERS[2]: {"lower": 4, "upper": 18},
    }
    assert data.swap_plan([], refresh=True) is None
    configure_rescue(
        data, conf=PlanConfig("", "", "", mood_limits={"lower": 0, "upper": 24})
    )
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    assert data.swap_plan([True], refresh=True) is None
    assert not data.operators[PRIMARY[0]].is_high()
    assert data.operators[PRIMARY[0]].lower_limit == 8
    assert data.operators[PRIMARY[0]].upper_limit == 16
    assert data.operators[COVERS[2]].upper_limit == 18
    assert data.has_rest_mood_limit(PRIMARY[0])


def test_fallback_rescue_preserves_main_limits_under_an_ordinary_backup(data):
    baseline = data.global_plan["default_plan"].config
    baseline.operator_mood_limits = {PRIMARY[0]: {"lower": 8, "upper": 16}}
    assert data.swap_plan([], refresh=True) is None
    backup = Plan(
        {},
        PlanConfig("", "", "", mood_limits={"lower": 0, "upper": 12}),
        LogicExpression("True", "==", "True"),
    )
    data.global_plan["backup_plans"] = data.backup_plans = [backup]
    assert data.swap_plan([True], refresh=True) is None
    assert data.operators[PRIMARY[1]].upper_limit == 12
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    assert data.operators[PRIMARY[0]].upper_limit == 16
    assert data.operators[PRIMARY[1]].upper_limit == 24
    set_moods(data, [16, 24, 24, 0])
    assert not data.rescue_needed()
    assert data.operators[PRIMARY[0]].upper_limit == 16
    assert data.operators[PRIMARY[1]].upper_limit == 12


def test_rescue_entry_rescales_existing_countdown_to_main_upper_limit(data):
    backup = Plan({}, PlanConfig("", "", "", mood_limits={"lower": 0, "upper": 12}))
    data.global_plan["backup_plans"] = data.backup_plans = [backup]
    assert data.swap_plan([True], refresh=True) is None
    set_moods(data, [0, 0, 0, 0])
    data = admit(data, PRIMARY[:1])
    bed = data.get_dorm_by_name(PRIMARY[0])[1]
    bed.time = NOW + timedelta(hours=2)
    assert data.rescue_needed()
    assert data.operators[PRIMARY[0]].upper_limit == 24
    assert bed.time == NOW + timedelta(hours=4)


def test_priority_uses_main_plan_identity_even_after_rescue_swap(data):
    configure_rescue(data)
    set_moods(data, [0, 0, 0, 0])
    data.operators[COVERS[2]].mood = 0
    assert data.rescue_needed()
    assert data.swap_plan([True], refresh=True) is None
    for name in [*PRIMARY, COVERS[2]]:
        assert resting_tier(data, name) == (
            RestingTier.PRIORITY_REPLACEMENT if name == COVERS[2] else RestingTier.MAIN
        )
    data.operators[PRIMARY[0]]._current_room = ""
    data.operators[PRIMARY[1]]._current_room = ""
    assert {PRIMARY[0], PRIMARY[1], COVERS[2]} <= set(dorm_candidates(data).recovering)
    data.config.free_blacklist.append(PRIMARY[0])
    assert resting_tier(data, PRIMARY[0]) == RestingTier.EXCLUDED
    assert PRIMARY[0] not in dorm_candidates(data).filling


def test_empty_rescue_backup_inherits_main_without_automatic_zero_mood_workers(data):
    configure_rescue(data, plan={})
    assert data.swap_plan([True], refresh=True) is None
    assert data.rescue_plan_active
    assert data.rescue_workers == set()
    assert data.plan[ROOMS[0]][0].agent == PRIMARY[0]
    assert not data.operators[PRIMARY[0]].workaholic


def test_normal_backups_keep_replacement_validation_and_priority(data):
    backup = configure_rescue(data)
    backup.trigger = LogicExpression("True", "==", "True")
    assert not backup.uses_rescue_condition
    assert "替换组缺失" in data.swap_plan([True], refresh=True)


@pytest.mark.parametrize(
    "expression", ["op_data.rescue_needed ( )", "False or op_data.rescue_needed()"]
)
def test_custom_and_nested_rescue_expressions_are_recognized(data, expression):
    backup = configure_rescue(data)
    backup.trigger.left = expression
    assert backup.uses_rescue_condition


def test_quoted_method_name_does_not_mark_a_backup_as_rescue(data):
    backup = configure_rescue(data)
    backup.trigger.left = "'op_data.rescue_needed()'"
    assert not backup.uses_rescue_condition


def test_later_normal_backup_retains_normal_override_priority(data):
    rescue = configure_rescue(data)
    normal = Plan({ROOMS[0]: [Room("伊内丝", "", ["陈"])]}, PlanConfig("", "", ""))
    data.global_plan["backup_plans"] = data.backup_plans = [rescue, normal]
    assert data.swap_plan([True, True], refresh=True) is None
    assert data.plan[ROOMS[0]][0].agent == "伊内丝"
    assert "伊内丝" not in data.rescue_workers


def test_fallback_keeps_occupied_beds_and_uses_existing_vacancies(data):
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    data = admit(data, PRIMARY[:2])
    before = deepcopy(data.dorm)
    assert not data._slot_takable(data.dorm[0], requester=PRIMARY[2])
    slot = data.assign_dorm(PRIMARY[2])
    assert slot is not None
    assert slot.position == data.dorm[2].position
    assert data.dorm[0].name == before[0].name
    assert data.dorm[1].name == before[1].name
    assert len(data.dorm) == 3


def test_fallback_exhausted_primaries_use_normal_shift_without_clear(data):
    baseline = data.global_plan["default_plan"].config
    baseline.exhaust_require = PRIMARY.copy()
    assert data.swap_plan([], refresh=True) is None
    set_moods(data, [0, 0, 0, 0])
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.op_data, solver.tasks = data, []
    solver.total_agent = list(data.operators.values())
    solver._refresh_deferred_product_reservations = MagicMock()
    solver.plan_metadata = MagicMock()
    solver.resting()
    assert solver.tasks
    assert all(task.type == TaskTypes.SHIFT_OFF for task in solver.tasks)
    assert {bed.name for bed in data.dorm} == set(PRIMARY[:3])
    assert all(
        not room.startswith("dorm") for task in solver.tasks for room in task.plan
    )
    assert not any(getattr(task, "rescue_dorm_clear", False) for task in solver.tasks)


def test_rescue_keeps_shared_candidates_and_excludes_blacklisted_workers(
    data, monkeypatch
):
    monkeypatch.setattr(
        "arknights_mower.utils.resting_priority.agent_list",
        [*data.operators, "伊芙利特"],
    )
    set_moods(data, [0, 0, 0, 0])
    data.operators[COVERS[2]].mood = 0
    data.config.free_blacklist.append(COVERS[2])
    assert data.rescue_needed()
    candidates = dorm_candidates(data)
    assert candidates.unknown == ["伊芙利特"]
    assert "伊芙利特" in candidates.filling
    assert COVERS[2] not in candidates.filling
    data.operators[PRIMARY[0]].workaholic = True
    assert data.assign_dorm(PRIMARY[0]) is None


def test_rescue_recovery_return_uses_personal_deadline_without_early_offset(data):
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    data = admit(data, PRIMARY[:2])
    tasks = plan_metadata(data, [])
    returns = [task for task in tasks if task.type == TaskTypes.SHIFT_ON]
    assert returns
    assert all(task.time == NOW + timedelta(hours=4) for task in returns)


@pytest.mark.parametrize("low_priority", [False, True])
def test_rescue_group_return_waits_for_each_individual_upper_limit(data, low_priority):
    baseline = data.global_plan["default_plan"]
    for room in ROOMS[:2]:
        baseline.plan[room][0].group = "救急恢复组"
    if low_priority:
        baseline.config.resting_priority = [PRIMARY[1]]
    assert data.swap_plan([], refresh=True) is None
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    data = admit(data, PRIMARY[:2])
    data.get_dorm_by_name(PRIMARY[1])[1].time = NOW + timedelta(hours=5)
    returns = [
        task for task in plan_metadata(data, []) if task.type == TaskTypes.SHIFT_ON
    ]
    assert returns
    assert all(task.time >= NOW + timedelta(hours=5) for task in returns)


def test_rescue_priority_replacement_release_waits_for_its_upper_limit(data):
    set_moods(data, [0, 0, 0, 0])
    data.operators[COVERS[2]].mood = 0
    assert data.rescue_needed()
    data = admit(data, [*PRIMARY[:2], COVERS[2]])
    releases = [
        task
        for task in plan_metadata(data, [])
        if task.type == TaskTypes.RELEASE_DORM
        and task.plan.get("dormitory_1", [])[4] == "Free"
    ]
    assert releases
    assert all(task.time == NOW + timedelta(hours=4) for task in releases)


def test_rescue_preserves_occupied_beds_even_without_registered_resident(data):
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    bed = data.dorm[0]
    bed.name = "未登记干员"
    assert not data._slot_takable(bed, requester=PRIMARY[0])


def test_rescue_resolves_uncached_lower_priority_resident_before_takeover(data):
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    bed = data.dorm[0]
    resident = data.operators[COVERS[0]]
    resident._current_room, resident.current_index = bed.position
    assert bed.name == ""
    assert data._slot_takable(bed, requester=PRIMARY[0])


def test_rescue_waits_for_existing_residents_cap_instead_of_clearing_beds(data):
    set_moods(data, [0, 0, 0, 0])
    data.operators[COVERS[0]].mood = 5
    assert data.rescue_needed()
    data = admit(data, [COVERS[0]])
    before = deepcopy(data.dorm)
    releases = [
        task for task in plan_metadata(data, []) if task.type == TaskTypes.RELEASE_DORM
    ]
    assert len(releases) == 1
    assert releases[0].time == NOW + timedelta(hours=4)
    assert data.dorm[0].name == before[0].name
    assert data.dorm[0].time == before[0].time


def test_ordinary_replacement_recovery_can_yield_without_candidate_promotion(data):
    set_moods(data, [0, 0, 0, 0])
    data.operators[COVERS[0]].mood = 5
    assert data.rescue_needed()
    assert COVERS[0] not in data.main_rescue_priority
    assert resting_tier(data, COVERS[0]) == RestingTier.REPLACEMENT
    assert not data.is_rescue_recovering(COVERS[0])
    data = admit(data, [COVERS[0]])
    assert not data.is_rescue_recovering(COVERS[0])
    assert resting_tier(data, COVERS[0]) == RestingTier.REPLACEMENT
    assert COVERS[0] in data.replacement_candidates(data.operators[PRIMARY[0]])
    assert data._slot_takable(data.dorm[0], requester=PRIMARY[0])


@pytest.mark.parametrize("cached_bed", [False, True])
def test_known_temporary_fill_yields_without_joining_formal_recovery(data, cached_bed):
    set_moods(data, [0, 0, 0, 0])
    data.operators[COVERS[0]].mood = 5
    assert data.rescue_needed()
    data = admit(data, [COVERS[0]])
    resident = data.operators[COVERS[0]]
    resident.temporary_dorm_fill = True
    if not cached_bed:
        data.dorm[0].name = ""
    assert not data.is_rescue_recovering(resident.name)
    assert data._slot_takable(data.dorm[0], requester=PRIMARY[0])


@pytest.mark.parametrize("unknown", ["missing_sample", "invalid_mood"])
def test_known_lower_identity_yields_even_with_unknown_mood(data, unknown):
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    data = admit(data, [COVERS[0]])
    resident = data.operators[COVERS[0]]
    resident.temporary_dorm_fill = True
    if unknown == "missing_sample":
        resident.time_stamp = None
    else:
        resident.mood = -1
    assert data._slot_takable(data.dorm[0], requester=PRIMARY[0])


def test_completed_existing_recovery_can_release_its_bed(data):
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    data = admit(data, [COVERS[0]])
    resident = data.operators[COVERS[0]]
    assert resident.mood == resident.upper_limit
    assert not data.is_rescue_recovering(resident.name)
    assert data._slot_takable(data.dorm[0], requester=PRIMARY[0])


def test_rescue_preserves_idle_release_exclusions(data):
    set_moods(data, [0, 0, 0, 0])
    data.operators[COVERS[0]].mood = 5
    assert data.rescue_needed()
    data = admit(data, [COVERS[0]])
    data.config.free_room = True
    data.config.free_room_exclusions = [COVERS[0]]
    assert not any(
        task.type == TaskTypes.RELEASE_DORM for task in plan_metadata(data, [])
    )


def test_unfinished_main_priority_replacement_is_not_borrowed_for_exhaust(data):
    set_moods(data, [0, 0, 0, 0])
    data.operators[COVERS[2]].mood = 0
    assert data.rescue_needed()
    data = admit(data, [COVERS[2]])
    assert data.is_rescue_recovering(COVERS[2])
    assert (
        plan_exhaust_support(data, [PRIMARY[2]], lambda _: True, lambda _: False)
        is None
    )
    assert data.get_dorm_by_name(COVERS[2])[1].time == NOW + timedelta(hours=4)


def test_rescue_condition_survives_plan_schema_round_trip(data, monkeypatch):
    main = data.global_plan["default_plan"]
    raw = {
        "plan1": {
            room: {
                "plans": [
                    {"agent": slot.agent, "replacement": slot.replacement}
                    for slot in slots
                ]
            }
            for room, slots in main.plan.items()
        },
        "backup_plans": [
            {
                "name": "救急",
                "trigger": {
                    "left": "op_data.rescue_needed()",
                    "operator": "==",
                    "right": "True",
                },
            }
        ],
    }
    model = config.PlanModel.model_validate_json(
        config.PlanModel(**raw).model_dump_json()
    )
    monkeypatch.setattr(config, "plan", model)
    result = operators.build_global_plan()
    assert len(result["backup_plans"]) == 1
    assert result["backup_plans"][0].uses_rescue_condition
    assert result["backup_plans"][0].plan == {}


@pytest.mark.parametrize("name", ["陈", "斥罪"])
@pytest.mark.parametrize("assignment", ["plan", "task"])
def test_rescue_explicit_dorm_assignments_cannot_bypass_exclusions(
    data, name, assignment
):
    backup = configure_rescue(data)
    dorm_names = ["Current", "Current", name, "Current", "Current"]
    if assignment == "task":
        backup.task = {"dormitory_1": dorm_names}
    else:
        backup.plan["dormitory_1"] = [Room(agent, "", []) for agent in dorm_names]
    data.global_plan["default_plan"].config.free_blacklist.append("斥罪")
    assert "禁止安排" in data.swap_plan([True], refresh=True)


def test_initial_workaholic_and_blacklist_do_not_vote_for_rescue(data):
    baseline = data.global_plan["default_plan"].config
    baseline.workaholic = PRIMARY[:1]
    baseline.free_blacklist = PRIMARY[1:2]
    assert data.swap_plan([], refresh=True) is None
    set_moods(data, [0, 0, 24, 24])
    assert not data.rescue_needed()
    assert set(data.main_recovery_limits) == set(PRIMARY[2:])
    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    assert data.assign_dorm(PRIMARY[0]) is None
    assert data.assign_dorm(PRIMARY[1]) is None


def test_main_ling_xi_limits_are_used_by_rescue(data):
    baseline = data.global_plan["default_plan"]
    baseline.plan[ROOMS[0]] = [Room("令", "感知", ["陈"])]
    baseline.plan[ROOMS[1]] = [Room("银灰", "感知", ["槐琥"])]
    baseline.config.ling_xi = 1
    assert data.swap_plan([], refresh=True) is None
    assert data.main_recovery_limits["令"] == (0, 12)
    assert data.main_recovery_limits["银灰"] == (12, 24)
    data.operators["令"].mood = 4.4
    data.operators["令"].time_stamp = NOW
    data.operators["银灰"].mood = 16.4
    assert data.rescue_needed()


def test_rescue_backup_converges_without_default_worker_identity_oscillation(data):
    configure_rescue(data)
    set_moods(data, [0, 0, 0, 0])
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.op_data, solver.tasks, solver.task = data, [], None
    solver._sync_run_order_tasks = MagicMock()
    solver.queue_product_switches = MagicMock()
    solver._backup_transition_plan = MagicMock(return_value={})
    solver.backup_plan_solver()
    assert data.plan_condition == [True]
    assert data.rescue_mode
    set_moods(data, [24, 24, 24, 0])
    solver.backup_plan_solver()
    assert data.plan_condition == [False]
    assert not data.rescue_mode


def test_rescue_backup_transition_frees_main_workers_for_priority_recovery(data):
    configure_rescue(data)
    set_moods(data, [0, 0, 0, 0])
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.op_data, solver.tasks, solver.task = data, [], None
    solver._sync_run_order_tasks = MagicMock()
    solver.queue_product_switches = MagicMock()
    solver._refresh_deferred_product_reservations = MagicMock()
    assert solver.backup_plan_solver()
    transitions = [task for task in solver.tasks if task.plan]
    assert len(transitions) == 1
    assert transitions[0].plan[ROOMS[0]] == [COVERS[0]]
    assert transitions[0].plan[ROOMS[1]] == [COVERS[1]]
    projected = data.project_arrangements([transitions[0].plan])
    assert set(dorm_candidates(projected).recovering) == set(PRIMARY[:2])
    assert all(projected.operators[name].workaholic for name in COVERS[:2])


@pytest.mark.parametrize("changed_limits", [False, True])
def test_rescue_episode_survives_restart_only_for_same_main_limits(
    data, monkeypatch, changed_limits
):
    from arknights_mower import __main__ as main
    from arknights_mower.solvers.record import current_state

    set_moods(data, [0, 0, 0, 0])
    assert data.rescue_needed()
    set_moods(data, [24, 0, 0, 0])
    assert data.rescue_needed()
    instance = object.__new__(base_schedule.BaseSchedulerSolver)
    instance.op_data, instance.tasks = data, []
    for attr in (
        "daily_visit_friend",
        "daily_report",
        "daily_skland",
        "daily_mail",
        "task_count",
    ):
        setattr(instance, attr, 0)
    monkeypatch.setattr(main, "base_scheduler", instance)
    saved = current_state()
    assert saved["rescue_state"]["completed"] == PRIMARY[:1]
    fresh = data.project_arrangements([])
    fresh.rescue_mode = False
    fresh.rescue_completed.clear()
    if changed_limits:
        fresh.main_recovery_limits = dict(fresh.main_recovery_limits)
        fresh.main_recovery_limits[PRIMARY[0]] = (0, 20)
    restarted = object.__new__(base_schedule.BaseSchedulerSolver)
    restarted.op_data = fresh
    restarted.initialize_operators = MagicMock(return_value=None)
    fresh.validate_backup_plans = MagicMock(return_value={"success": True})
    monkeypatch.setattr(main, "initialize", MagicMock(return_value=restarted))
    monkeypatch.setattr(main.config, "stop_mower", Event())
    monkeypatch.setattr(main.config.conf, "close_simulator_when_idle", False)

    class ReachedScheduling(BaseException):
        pass

    monkeypatch.setattr(
        main, "refresh_resource_at_boundary", MagicMock(side_effect=ReachedScheduling)
    )
    with pytest.raises(ReachedScheduling):
        main.simulate(saved)
    assert fresh.rescue_mode is not changed_limits
    assert fresh.rescue_completed == (set() if changed_limits else {PRIMARY[0]})


@pytest.mark.parametrize(
    "tier",
    [RestingTier.MAIN, RestingTier.LOW_MAIN, RestingTier.STANDBY, RestingTier.PRIORITY],
)
def test_rescue_backup_keeps_original_primary_tier_without_automatic_promotion(
    data, tier
):
    name = PRIMARY[0]
    baseline = data.global_plan["default_plan"].config
    if tier == RestingTier.LOW_MAIN:
        baseline.resting_priority = [name]
    elif tier == RestingTier.STANDBY:
        baseline.resting_standby = [name]
    elif tier == RestingTier.PRIORITY:
        baseline.ope_resting_priority = [name]
    assert data.swap_plan([], refresh=True) is None
    before = resting_tier(data, name)
    assert before == tier
    configure_rescue(data)
    assert data.swap_plan([True], refresh=True) is None
    assert not data.operators[name].is_high()
    assert resting_tier(data, name) == before
    assert resting_tier(data, COVERS[0]) == RestingTier.EXCLUDED


def test_rescue_backup_keeps_escalated_standby_tier_until_actual_return(data):
    name = PRIMARY[0]
    data.global_plan["default_plan"].config.resting_standby = [name]
    assert data.swap_plan([], refresh=True) is None
    data.operators[name].standby_low_priority = True
    configure_rescue(data)
    assert data.swap_plan([True], refresh=True) is None
    assert data.operators[name].standby_low_priority
    assert resting_tier(data, name) == RestingTier.LOW_MAIN
