"""智能救急整组替班，按个人需求分床，退出时统一恢复岗位。"""

import pickle
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import emergency
from arknights_mower.tests.emergency_group_return_tests import (
    group_return as recovery_fixture,  # noqa: F401
)
from arknights_mower.tests.emergency_group_return_tests import (
    legacy_solver as legacy_solver,
)
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.utils.emergency_staffing import StaffingCandidate
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS, Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def staffing(recovery_fixture, monkeypatch):  # noqa: F811
    episode, solver = recovery_fixture, recovery_fixture.solver
    data = solver.op_data
    original = {data.operators[name].room: [name] for name in PRIMARY}
    original.update(
        {
            "dormitory_1": ["塑心", "冰酿", "", "", ""],
            "dormitory_2": ["闪灵", "白面鸮", "", "", ""],
        }
    )
    solver.op_data = data.project_arrangements([original])
    for name in PRIMARY:
        op = solver.op_data.operators[name]
        op.mood = 8
        solver.op_data.plan[op.room][0].facility = "制造站"
    episode.state["phase"] = "staffing"
    candidates = [StaffingCandidate("红", 24, ()), StaffingCandidate("初雪", 24, ())]
    solver._emergency_scan_workers = MagicMock(return_value=candidates)
    monkeypatch.setattr(emergency, "load_skill_snapshot", lambda: {})
    return episode


def staffing_task(solver):
    return next(
        task for task in solver.tasks if getattr(task, "emergency_staffing", False)
    )


def test_startup_keeps_other_primary_groups_and_uses_automatic_substitutes(staffing):
    solver = staffing.solver

    assert solver._emergency_schedule_staffing()

    task = staffing_task(solver)
    assert set(staffing.state["staffing_members"]) == set(PRIMARY[:2])
    working_rooms = {room for room in task.plan if not room.startswith("dorm")}
    assert working_rooms == {
        solver.op_data.operators[name].room for name in PRIMARY[:2]
    }
    chosen = {
        name for room in working_rooms for name in task.plan[room] if name != "Current"
    }
    assert chosen == {"红", "初雪"}
    assert not chosen.intersection(COVERS)
    projected = solver.op_data.project_arrangements([task.plan])
    for name in PRIMARY[:2]:
        assert projected.operators[name].is_resting()
        assert staffing.state["automatic_replacements"][name] in chosen
    for name in PRIMARY[2:]:
        op = projected.operators[name]
        assert (op.current_room, op.current_index) == (op.room, op.index)
    assert projected.get_current_room("dormitory_1", True)[:2] == ["塑心", "冰酿"]
    assert projected.operators["塑心"].current_room == "dormitory_1"
    assert len(staffing.saves) == 1
    assert staffing.saves[0]["state"]["staffing_plan"] == task.plan
    assert not staffing.plans
    solver.backup_plan_solver.assert_not_called()


def test_healthy_group_peer_leaves_work_without_consuming_recovery_bed(staffing):
    solver = staffing.solver
    solver.op_data.operators[PRIMARY[1]].mood = 24

    assert solver._emergency_schedule_staffing()

    projected = solver.op_data.project_arrangements([staffing_task(solver).plan])
    assert projected.operators[PRIMARY[0]].is_resting()
    healthy = projected.operators[PRIMARY[1]]
    assert (healthy.current_room, healthy.current_index) == ("", -1)
    assert set(staffing.state["staffing_members"]) == set(PRIMARY[:2])
    assert set(staffing.state["automatic_replacements"]) == set(PRIMARY[:2])
    assert PRIMARY[1] not in {
        name
        for room, row in staffing_task(solver).plan.items()
        if room.startswith("dorm")
        for name in row
    }


def test_staffing_does_not_scan_or_move_healthy_main_groups(staffing):
    solver = staffing.solver
    for name in PRIMARY:
        solver.op_data.operators[name].mood = 24

    assert solver._emergency_schedule_staffing()

    solver._emergency_scan_workers.assert_not_called()
    assert not any(getattr(task, "emergency_staffing", False) for task in solver.tasks)
    assert not staffing.state.get("staffing_plan")


def test_missing_one_substitute_keeps_complete_group_working_and_stores_no_partial_plan(
    staffing,
):
    solver = staffing.solver
    solver.op_data.operators[PRIMARY[2]].mood = 24
    solver.op_data.operators[PRIMARY[3]].mood = 24
    solver._emergency_scan_workers.return_value = [StaffingCandidate("红", 24, ())]

    assert not solver._emergency_schedule_staffing()

    assert not staffing.state.get("staffing_plan")
    assert not staffing.state.get("staffing_members")
    assert not staffing.saves
    assert not any(getattr(task, "emergency_staffing", False) for task in solver.tasks)
    assert all(solver.op_data.operators[name].is_working() for name in PRIMARY)


def test_reserved_beds_do_not_block_complete_worker_substitution(staffing):
    solver = staffing.solver
    reservation = SchedulerTask(
        task_type=TaskTypes.FILL_DORM,
        task_plan={room: ["Free"] * 5 for room in ("dormitory_1", "dormitory_2")},
    )
    solver.tasks.append(reservation)

    assert solver._emergency_schedule_staffing()

    solver._emergency_scan_workers.assert_called()
    task = staffing_task(solver)
    assert set(staffing.state["staffing_members"]) == set(PRIMARY[:2])
    assert set(task.plan) == {
        solver.op_data.operators[name].room for name in PRIMARY[:2]
    }
    projected = solver.op_data.project_arrangements([task.plan])
    assert all(not projected.operators[name].is_working() for name in PRIMARY[:2])
    assert all(not projected.operators[name].is_resting() for name in PRIMARY[:2])
    assert reservation in solver.tasks
    assert all(solver.op_data.operators[name].is_working() for name in PRIMARY)


def test_staffing_scan_reserves_other_primary_and_all_run_order_agents(staffing):
    solver = staffing.solver
    seen = []

    def scan(room, facility, reserved, **kwargs):
        seen.append(set(reserved))
        return [
            StaffingCandidate(PRIMARY[2], 24, ()),
            StaffingCandidate("但书", 24, ()),
            StaffingCandidate("红", 24, ()),
            StaffingCandidate("初雪", 24, ()),
        ]

    solver._emergency_scan_workers.side_effect = scan
    assert solver._emergency_schedule_staffing()

    assert seen
    assert all(set(PRIMARY).issubset(reserved) for reserved in seen)
    assert all(set(TRADE_ORDER_AGENTS).issubset(reserved) for reserved in seen)
    task = staffing_task(solver)
    assert all("但书" not in row for row in task.plan.values())
    assert all(PRIMARY[2] not in row for row in task.plan.values())


def test_strict_release_budget_discards_complete_scan_without_queueing_group(staffing):
    solver = staffing.solver
    release = SchedulerTask(
        time=NOW + timedelta(seconds=50),
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_2": ["Current", "Current", "Free", "Current", "Current"]},
    )
    release.strict_mood_limit = True
    solver.tasks.append(release)

    assert not solver._emergency_schedule_staffing()

    assert not staffing.state.get("staffing_plan")
    assert not staffing.saves
    assert not any(getattr(task, "emergency_staffing", False) for task in solver.tasks)
    assert release in solver.tasks


def test_restart_requeues_saved_remaining_plan_and_preserves_worker_reservation(
    staffing,
):
    solver = staffing.solver
    assert solver._emergency_schedule_staffing()
    task = staffing_task(solver)
    room = solver.op_data.operators[PRIMARY[0]].room
    solver.op_data = solver.op_data.project_arrangements([{room: task.plan[room]}])
    del staffing.state["staffing_plan"][room]
    saved = pickle.loads(pickle.dumps(staffing.state))
    solver.emergency_state = saved
    solver.tasks.remove(task)
    solver._emergency_scan_workers.reset_mock()

    assert solver._emergency_schedule_staffing()

    resumed = staffing_task(solver)
    assert resumed.plan == saved["staffing_plan"]
    assert room not in resumed.plan
    assert set(saved["staffing_members"]) == set(PRIMARY[:2])
    assert set(resumed.emergency_staffing_members) == set(saved["staffing_members"])
    solver._emergency_scan_workers.assert_not_called()


def test_ready_individuals_remain_idle_until_unified_restore(staffing):
    solver = staffing.solver
    staffing.state["ready_members"] = list(PRIMARY[:2])
    for name in PRIMARY[:2]:
        op = solver.op_data.operators[name]
        op._current_room, op.current_index = "", -1
    for name in PRIMARY[2:]:
        solver.op_data.operators[name].mood = 24

    assert solver._emergency_schedule_staffing()

    solver._emergency_scan_workers.assert_not_called()
    assert not staffing.state.get("staffing_plan")
    assert not staffing.state.get("staffing_rescore")
    assert staffing.state["ready_members"] == list(PRIMARY[:2])
    for name in PRIMARY[:2]:
        op = solver.op_data.operators[name]
        assert (op.current_room, op.current_index) == ("", -1)


def test_cross_room_matching_keeps_unique_candidate_for_constrained_facility(staffing):
    solver = staffing.solver
    rooms = [solver.op_data.operators[name].room for name in PRIMARY[:2]]
    efficient = StaffingCandidate(
        "红", 24, ({"skillIcon": "speed", "des": "生产力+30%"},)
    )
    other = StaffingCandidate("初雪", 24, ())

    def scan(room, facility, reserved, **kwargs):
        assert "红" not in reserved and "初雪" not in reserved
        return [efficient, other] if room == rooms[0] else [efficient]

    solver._emergency_scan_workers.side_effect = scan

    assert solver._emergency_schedule_staffing()

    task = staffing_task(solver)
    assert task.plan[rooms[0]] == ["初雪"]
    assert task.plan[rooms[1]] == ["红"]
    assert staffing.state["automatic_replacements"] == {
        PRIMARY[0]: "初雪",
        PRIMARY[1]: "红",
    }


@pytest.mark.parametrize("release_plan", [{}, {"dormitory_1": ["Current"] * 5}])
def test_pending_individual_release_blocks_new_group_departure(staffing, release_plan):
    solver = staffing.solver
    staffing.state["release_plan"] = release_plan

    assert solver._emergency_schedule_staffing()

    solver._emergency_scan_workers.assert_not_called()
    assert not staffing.state.get("staffing_plan")


def test_fixed_member_skill_changes_best_remaining_worker_without_becoming_candidate():
    from arknights_mower.tests.emergency_staffing_tests import candidate
    from arknights_mower.utils.emergency_staffing import select_workers

    fixed = candidate("泡泡", ["bskill_man_limit&cost2", "bskill_man_spd_variable31"])
    storage = candidate("火神", ["bskill_man_spd&limit&cost2"])
    generic = candidate("赫默", ["bskill_man_spd2"])
    assert select_workers([storage, generic], "制造站", "gold", 1) == ["赫默"]
    assert select_workers(
        [fixed, storage, generic], "制造站", "gold", 1, fixed=[fixed]
    ) == ["火神"]


def prepare_rescore(staffing):
    from arknights_mower.utils.plan import Room

    solver = staffing.solver
    data = solver.op_data
    room = data.operators[PRIMARY[0]].room
    old_room = data.operators[PRIMARY[2]].room
    data.operators[PRIMARY[2]].room = room
    data.operators[PRIMARY[2]].index = 1
    data.plan[room].append(Room(PRIMARY[2], "后恢复", [COVERS[2]], facility="制造站"))
    del data.plan[old_room]
    second_room = data.operators[PRIMARY[3]].room
    solver.op_data = data.project_arrangements(
        [
            {
                room: [PRIMARY[0], COVERS[2]],
                second_room: [COVERS[3]],
                "dormitory_2": ["闪灵", "白面鸮", PRIMARY[2], PRIMARY[3], ""],
            }
        ]
    )
    staffing.state["phase"] = "recovering"
    staffing.state["staffing_rescore"] = True
    return room, second_room


def test_global_rescore_keeps_primary_fixed_and_recombines_actual_temporary_workers(
    staffing, monkeypatch
):
    solver = staffing.solver
    room, second_room = prepare_rescore(staffing)
    fixed_skill = {"skillIcon": "bskill_man_spd_variable31", "des": "固定组合"}
    storage_skill = {"skillIcon": "capacity", "des": "生产力-5%，仓库容量上限+18"}
    generic_skill = {"skillIcon": "speed", "des": "生产力+30%"}
    monkeypatch.setattr(
        emergency, "unlocked_skills", lambda name, facility, snapshot: None
    )
    seen = []

    def scan(target_room, facility, reserved, *, fixed=(), **kwargs):
        seen.append((target_room, set(fixed)))
        assert COVERS[2] not in reserved and COVERS[3] not in reserved
        assert set(PRIMARY).issubset(reserved)
        return [
            StaffingCandidate(PRIMARY[0], 24, (fixed_skill,)),
            StaffingCandidate(COVERS[2], 24, (generic_skill,)),
            StaffingCandidate(COVERS[3], 24, (storage_skill,)),
        ]

    solver._emergency_scan_workers.side_effect = scan
    before = {name: op.mood for name, op in solver.op_data.operators.items()}

    assert solver._emergency_schedule_staffing()

    task = staffing_task(solver)
    assert task.plan == {room: ["Current", COVERS[3]], second_room: [COVERS[2]]}
    assert set(target for target, _ in seen) == {room, second_room}
    assert dict(seen)[room] == {PRIMARY[0]}
    assert not staffing.state.get("staffing_rescore")
    assert {name: op.mood for name, op in solver.op_data.operators.items()} == before
    projected = solver.op_data.project_arrangements([task.plan])
    assert projected.get_current_room(room, True) == [PRIMARY[0], COVERS[3]]
    assert all(projected.operators[name].is_resting() for name in PRIMARY[2:])
    solver.backup_plan_solver.assert_not_called()


def test_rescore_shortage_keeps_flag_and_actual_temporary_workers_until_complete_matching(
    staffing,
):
    solver = staffing.solver
    room, second_room = prepare_rescore(staffing)
    solver._emergency_scan_workers.return_value = [StaffingCandidate(COVERS[2], 24, ())]
    original = {
        target: solver.op_data.get_current_room(target, True)
        for target in (room, second_room)
    }

    assert not solver._emergency_schedule_staffing()

    assert staffing.state["staffing_rescore"]
    assert not staffing.state.get("staffing_plan")
    assert not any(getattr(task, "emergency_staffing", False) for task in solver.tasks)
    assert {
        target: solver.op_data.get_current_room(target, True) for target in original
    } == original


def test_rescore_does_not_keep_lower_scoring_current_temporary_worker(staffing):
    solver = staffing.solver
    room, second_room = prepare_rescore(staffing)
    replacement = StaffingCandidate(
        "红", 24, ({"skillIcon": "speed", "des": "生产力+30%"},)
    )
    solver._emergency_scan_workers.return_value = [
        StaffingCandidate(COVERS[2], 24, ()),
        StaffingCandidate(COVERS[3], 24, ()),
        replacement,
    ]

    assert solver._emergency_schedule_staffing()

    task = staffing_task(solver)
    assert "红" in {name for row in task.plan.values() for name in row}
    assert task.plan.get(room, ["Current", "Current"])[0] == "Current"
    assert not staffing.state.get("staffing_rescore")


def test_initial_departure_scores_replacements_with_fixed_primary_skills(staffing):
    from arknights_mower.tests.emergency_staffing_tests import candidate

    solver = staffing.solver
    data = solver.op_data
    room = data.operators[PRIMARY[0]].room
    data.plan[room].append(Room("泡泡", "", []))
    data.add(
        Operator(
            "泡泡",
            room,
            index=1,
            current_room=room,
            current_index=1,
            mood=24,
            time_stamp=NOW,
        )
    )
    fixed = candidate("泡泡", ["bskill_man_limit&cost2", "bskill_man_spd_variable31"])
    storage = candidate("火神", ["bskill_man_spd&limit&cost2"])
    generic = candidate("赫默", ["bskill_man_spd2"])
    solver._emergency_scan_workers.return_value = [fixed, storage, generic]

    assert solver._emergency_schedule_staffing()

    assert staffing_task(solver).plan[room] == ["火神", "Current"]
    assert solver._emergency_scan_workers.call_args_list[0].kwargs["fixed"] == ["泡泡"]


def test_bound_manager_free_replacement_does_not_change_worker_departure(staffing):
    solver = staffing.solver
    data = solver.op_data
    manager = data.operators["塑心"]
    manager.replacement = ["Free"]
    data.plan[manager.room][manager.index].replacement = ["Free"]

    assert solver._emergency_schedule_staffing()

    task = staffing_task(solver)
    row = task.plan[manager.room]
    assert row[manager.index] == "Current"
    assert row[1] == "Current"
    assert set(staffing.state["staffing_members"]) == set(PRIMARY[:2])
    projected = data.project_arrangements([task.plan])
    assert projected.operators["塑心"].current_room == manager.room
    assert all(projected.operators[name].is_resting() for name in PRIMARY[:2])


def test_bound_manager_replacement_shortage_does_not_block_worker_substitution(
    staffing,
):
    solver = staffing.solver
    solver.op_data.operators["黑角"]._current_room = "train"
    for name in PRIMARY[2:]:
        solver.op_data.operators[name].mood = 24

    assert solver._emergency_schedule_staffing()

    solver._emergency_scan_workers.assert_called()
    task = staffing_task(solver)
    assert set(staffing.state["staffing_members"]) == set(PRIMARY[:2])
    assert all("黑角" not in row for row in task.plan.values())
    projected = solver.op_data.project_arrangements([task.plan])
    assert all(not projected.operators[name].is_working() for name in PRIMARY[:2])
    assert projected.operators["塑心"].current_room == "dormitory_1"
    assert solver.op_data.operators["黑角"].current_room == "train"


@pytest.mark.parametrize("mood", [None, 0])
def test_global_rescore_rejects_unknown_or_zero_candidate_mood(staffing, mood):
    solver = staffing.solver
    room, other = prepare_rescore(staffing)
    original = {
        target: solver.op_data.get_current_room(target, True)
        for target in (room, other)
    }
    solver._emergency_scan_workers.return_value = [
        StaffingCandidate(name, mood, ()) for name in COVERS[2:]
    ]

    assert not solver._emergency_schedule_staffing()

    assert staffing.state["staffing_rescore"]
    assert not staffing.state.get("staffing_plan")
    assert {
        target: solver.op_data.get_current_room(target, True) for target in original
    } == original


def test_global_rescore_reserves_specialized_working_occupants(staffing):
    solver = staffing.solver
    prepare_rescore(staffing)
    solver.op_data.add(
        Operator(
            "阿", "", current_room="factory", current_index=0, mood=24, time_stamp=NOW
        )
    )
    observed = []

    def scan(room, facility, reserved, **kwargs):
        observed.append(set(reserved))
        return [
            StaffingCandidate("阿", 24, ()),
            StaffingCandidate("红", 24, ({"skillIcon": "speed", "des": "生产力+30%"},)),
            *(StaffingCandidate(name, 24, ()) for name in COVERS[2:]),
        ]

    solver._emergency_scan_workers.side_effect = scan
    assert solver._emergency_schedule_staffing()
    assert observed and all("阿" in reserved for reserved in observed)
    assert all("阿" not in row for row in staffing_task(solver).plan.values())
    assert solver.op_data.operators["阿"].current_room == "factory"


@pytest.mark.parametrize("mood", [None, 0, 8])
def test_group_departure_selection_does_not_apply_work_threshold_to_resting_primaries(
    staffing, monkeypatch, mood
):
    from arknights_mower.solvers import base_mixin

    solver = staffing.solver
    assert solver._emergency_schedule_staffing()
    solver.task = staffing_task(solver)
    solver.recog = SimpleNamespace(img=object())
    monkeypatch.setattr(base_mixin, "estimate_agent_mood", lambda *args: mood)
    name = PRIMARY[0]
    op = solver.op_data.operators[name]
    measured = (op.mood, op.time_stamp)

    assert solver.observe_agent_moods(
        [(name, ((0, 0), (1, 1)))], [name], None, False
    ) == {name}
    assert (op.mood, op.time_stamp) == measured


@pytest.mark.parametrize("mood", [None, 0, 8])
def test_group_departure_still_rechecks_working_replacement_mood(
    staffing, monkeypatch, mood
):
    from arknights_mower.solvers import base_mixin

    solver = staffing.solver
    assert solver._emergency_schedule_staffing()
    solver.task = staffing_task(solver)
    name = next(
        name
        for room, row in solver.task.plan.items()
        if not room.startswith("dorm")
        for name in row
        if name != "Current"
    )
    solver.recog = SimpleNamespace(img=object())
    monkeypatch.setattr(base_mixin, "estimate_agent_mood", lambda *args: mood)

    with pytest.raises(base_mixin.AgentSelectionNotReady, match="心情不足或无法读取"):
        solver.observe_agent_moods([(name, ((0, 0), (1, 1)))], [name], None, False)


@pytest.mark.parametrize("mood", [None, 0, 8])
@pytest.mark.parametrize("role", ["dorm_replacement", "fixed_primary"])
def test_group_selection_preserves_normal_dorm_and_original_primary_rules(
    staffing, monkeypatch, mood, role
):
    from arknights_mower.solvers import base_mixin

    solver = staffing.solver
    name = "黑角" if role == "dorm_replacement" else PRIMARY[2]
    room = solver.op_data.operators[PRIMARY[2]].room
    solver.task = SchedulerTask(
        task_plan={
            "dormitory_1": ["黑角", "Current", "Current", "Current", "Current"],
            room: [PRIMARY[2]],
        }
    )
    solver.task.emergency_staffing = True
    solver.task.emergency_staffing_members = list(PRIMARY[:2])
    solver.recog = SimpleNamespace(img=object())
    monkeypatch.setattr(base_mixin, "estimate_agent_mood", lambda *args: mood)
    op = solver.op_data.operators[name]
    measured = (op.mood, op.time_stamp)

    assert solver.observe_agent_moods(
        [(name, ((0, 0), (1, 1)))], [name], None, False
    ) == {name}
    assert (op.mood, op.time_stamp) == measured
