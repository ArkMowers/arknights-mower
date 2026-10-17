"""真实用尽交接到恢复结束之间不能反向或连续强制召回。"""

from copy import deepcopy
from datetime import datetime
from unittest.mock import MagicMock

from arknights_mower.tests.exhaust_replacement_tests import solver as solver
from arknights_mower.utils.dorm_candidates import retained_task_reservations
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.utils.urgent_recovery import active_urgent_recovery


def start_handoff(solver):
    data = solver.op_data
    data.operators["机械师"].group = "用尽组"
    data.operators["机械师"].group_bindings = [
        {"group": "用尽组", "replacement": ["槐琥"]}
    ]
    data.plan["room_3_3"][0].group = "用尽组"
    data.groups["用尽组"] = ["机械师"]
    data.group_shift_state["用尽组"] = False
    data.operators["苍苔"].replacement = ["槐琥"]
    data.plan["room_2_2"][0].replacement = ["槐琥"]
    data.operators["苍苔"].mood = 0
    data.operators["絮雨"].mood = 0
    solver.check_fia = MagicMock(return_value=([], None))
    solver.skip = MagicMock()
    request = solver.task
    solver.overtake_room()
    support = next(
        task for task in solver.tasks if getattr(task, "exhaust_support", False)
    )
    return request, support


def confirm_arrangement(solver, task):
    solver.task = task
    solver._prepare_group_shift(task, remember_targets=True)
    solver.op_data = solver.op_data.project_arrangements([task.plan])
    assert solver._complete_group_shift(task)
    solver.tasks[:] = [pending for pending in solver.tasks if pending is not task]


def test_low_mood_supporters_cannot_reverse_or_chain_recall(solver):
    request, support = start_handoff(solver)
    assert set(support.urgent_recovery_support_names) == {"苍苔", "絮雨"}
    assert solver.op_data.urgent_recovery_supporters == {}
    confirm_arrangement(solver, support)
    original_time = request.time
    assert request.urgent_recovery_reserved_names == ["槐琥", "斥罪"]
    solver.task = request
    solver.overtake_room()
    departure = next(task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF)
    assert request.time == original_time
    assert departure.urgent_recovery_request_names == ["机械师"]
    confirm_arrangement(solver, departure)
    solver.tasks[:] = [task for task in solver.tasks if task is not request]
    assert solver.op_data.urgent_recovery_supporters == {"机械师": ["苍苔", "絮雨"]}
    assert solver.op_data.operators["机械师"].is_resting()
    assert solver.op_data.operators["苍苔"].current_mood() == 0
    solver.task = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="苍苔")
    assert solver._plan_exhaust_support(["苍苔", "絮雨"], urgent=True) is None
    solver.op_data.operators["能天使"].replacement = ["槐琥"]
    solver.op_data.plan["meeting"][0].replacement = ["槐琥"]
    for _ in range(3):
        assert solver._plan_exhaust_support(["能天使"], urgent=True) is None
    assert solver.op_data.operators["机械师"].is_resting()
    returning = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON, task_plan={"room_3_3": ["机械师"]}
    )
    confirm_arrangement(solver, returning)
    assert solver.op_data.urgent_recovery_supporters == {}
    plan = {}
    solver.get_resting_plan(
        ["苍苔", "絮雨"], [], plan, solver.op_data.active_high_resting_count()
    )
    assert plan["room_2_2"] == ["槐琥"]


def test_pending_handoff_reserves_freed_resources_for_original_request(solver):
    request, support = start_handoff(solver)
    names, slots = retained_task_reservations(solver.op_data, [support, request])
    assert {"槐琥", "斥罪"} <= names
    assert {("dormitory_1", 2), ("dormitory_1", 3)} <= slots
    own_names, own_slots = retained_task_reservations(
        solver.op_data, [support, request], current_task=request
    )
    assert "槐琥" not in own_names
    assert ("dormitory_1", 2) not in own_slots
    confirm_arrangement(solver, support)
    solver.task = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="苍苔")
    assert solver._plan_exhaust_support(["苍苔", "絮雨"], urgent=True) is None
    plan = {}
    solver.get_resting_plan(
        ["苍苔", "絮雨"], [], plan, solver.op_data.active_high_resting_count()
    )
    assert not plan
    assert request.time <= datetime.now()


def test_recovery_protection_isolated_and_requires_observed_completion(solver):
    data = solver.op_data
    data.urgent_recovery_supporters = {"苍苔": ["机械师"], "絮雨": ["机械师"]}
    projected = data.project_arrangements([])
    projected.urgent_recovery_supporters["苍苔"].append("能天使")
    assert data.urgent_recovery_supporters["苍苔"] == ["机械师"]
    data.operators["苍苔"].mood = 24
    data.operators["苍苔"].mood_is_prediction = True
    assert set(active_urgent_recovery(data)) == {"苍苔", "絮雨"}
    data.operators["苍苔"].mood_is_prediction = False
    assert active_urgent_recovery(data) == {"絮雨": ["机械师"]}
    before = deepcopy(data.urgent_recovery_supporters)
    solver.check_fia = MagicMock(return_value=([], None))
    assert solver._plan_exhaust_support(["机械师"], urgent=True) == {
        "room_2_2": ["引星棘刺"]
    }
    data.operators["苍苔"].replacement = ["槐琥"]
    data.plan["room_2_2"][0].replacement = ["槐琥"]
    assert solver._plan_exhaust_support(["机械师"], urgent=True) is None
    assert data.urgent_recovery_supporters == before


def dependency_solver(solver, *, shared=False, second_group=False):
    from datetime import timedelta

    from arknights_mower.utils.plan import Room

    plan = solver.global_plan["default_plan"].plan
    plan["room_3_3"][0].group = "红松"
    plan["room_3_3"][0].replacement = ["引星棘刺"] if shared else ["桃金娘"]
    if shared:
        plan["meeting"][0] = Room(
            "能天使",
            "感知",
            ["陈"],
            group_bindings=[
                {"group": "红松", "replacement": ["桃金娘"]},
                *([{"group": "其他", "replacement": ["陈"]}] if second_group else []),
            ],
        )
        if second_group:
            plan["room_1_1"] = [Room("德克萨斯", "其他", ["结城理"])]
            plan["dormitory_2"] = [Room("Free", "", []) for _ in range(5)]
    else:
        plan["dormitory_1"][1] = Room("闪灵", "感知", ["桃金娘"])
    assert solver.initialize_operators() is None
    arrangement = {
        "room_3_3": ["机械师"],
        "room_2_2": ["槐琥"],
        "contact": ["斥罪"],
        "meeting": ["陈" if shared else "能天使"],
        "dormitory_1": [
            "冰酿",
            "闪灵" if shared else "桃金娘",
            "苍苔",
            "絮雨",
            "能天使" if shared else "Free",
        ],
    }
    if second_group:
        arrangement["room_1_1"] = ["结城理"]
        arrangement["dormitory_2"] = ["德克萨斯", "Free", "Free", "Free", "Free"]
    solver.op_data = solver.op_data.project_arrangements([arrangement])
    now = datetime.now()
    for worker in solver.op_data.operators.values():
        worker.mood, worker.time_stamp = 12, now
    solver.op_data.operators["机械师"].mood = 0
    for bed in solver.op_data.dorm:
        if bed.name:
            bed.time = now + timedelta(hours=4)
    solver.check_fia = MagicMock(return_value=([], None))
    solver.skip = MagicMock()
    return solver


def test_urgent_recall_releases_fixed_dorm_cover_through_its_own_group(solver):
    s = dependency_solver(solver)
    data = s.op_data
    assert data.is_dorm_replacement("桃金娘")
    assert s._plan_exhaust_support(["机械师"], urgent=False) is None
    plan = s._plan_exhaust_support(["机械师"], urgent=True)
    assert plan is not None
    assert plan["dormitory_1"][1] == "闪灵"
    assert plan["room_2_2"] == ["苍苔"]
    assert plan["contact"] == ["絮雨"]
    assert data.get_current_operator("dormitory_1", 1).name == "桃金娘"
    assert (
        s._coordination_admission(data.project_arrangements([plan]), ["机械师"])
        is not None
    )


def test_urgent_recall_resolves_disjoint_shared_bindings(solver):
    s = dependency_solver(solver, shared=True)
    candidates = ["机械师", "能天使"]
    assert s._plan_exhaust_support(candidates, urgent=False) is None
    plan = s._plan_exhaust_support(candidates, urgent=True)
    assert plan is not None
    assert plan["room_2_2"] == ["苍苔"]
    assert plan["contact"] == ["絮雨"]
    assert (
        s._coordination_admission(s.op_data.project_arrangements([plan]), candidates)
        is not None
    )
    assert s.op_data.group_is_resting("感知")


def test_urgent_recall_combines_two_blocking_groups_before_committing(solver):
    s = dependency_solver(solver, shared=True, second_group=True)
    candidates = ["机械师", "能天使"]
    plan = s._plan_exhaust_support(candidates, urgent=True)
    assert plan is not None
    assert plan["room_2_2"] == ["苍苔"]
    assert plan["room_1_1"] == ["德克萨斯"]
    assert s.op_data.group_is_resting("感知")
    assert s.op_data.group_is_resting("其他")
    s.op_data.operators["德克萨斯"].rest_in_full = True
    assert s._plan_exhaust_support(candidates, urgent=True) is None
    assert s.op_data.get_current_operator("room_1_1", 0).name == "结城理"


def test_actual_partial_admission_protects_request_before_other_rooms_finish(solver):
    request, support = start_handoff(solver)
    support.plan["dormitory_1"] = ["冰酿", "闪灵", "机械师", "Current", "Current"]
    solver.task = support
    old_position = ("room_3_3", 0)
    solver.op_data = solver.op_data.project_arrangements(
        [{"dormitory_1": support.plan["dormitory_1"]}]
    )
    solver._record_dorm_admission("机械师", "dormitory_1", 2, old_position)
    assert solver.op_data.urgent_recovery_supporters == {"机械师": ["苍苔", "絮雨"]}
    assert support.plan["room_2_2"] == ["苍苔"]
    assert request in solver.tasks


def test_support_transfer_does_not_claim_another_group_with_shared_follower(solver):
    request, support = start_handoff(solver)
    request.coordination_request_names.append("能天使")
    request.urgent_recovery_request_names.append("能天使")
    support.urgent_recovery_request_names.append("能天使")
    support.coordination_request_names.append("能天使")
    unrelated = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="絮雨")
    unrelated.coordination_request_names = ["絮雨", "能天使"]
    solver.tasks.append(unrelated)
    confirm_arrangement(solver, support)
    assert request.urgent_recovery_reserved_names
    assert not hasattr(unrelated, "urgent_recovery_request_names")


def test_shared_followers_do_not_own_an_independent_recovery_episode(solver):
    from arknights_mower.utils.urgent_recovery import complete_urgent_recovery

    s = dependency_solver(solver, shared=True)
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    task.urgent_recovery_request_names = ["苍苔", "能天使"]
    task.urgent_recovery_support_names = ["机械师"]
    complete_urgent_recovery(s.op_data, task, [])
    assert s.op_data.urgent_recovery_supporters == {"苍苔": ["机械师"]}


def test_recovery_dependencies_survive_snapshot_but_new_initialization_clears_them(
    solver, monkeypatch
):
    import pickle
    from threading import Event

    from arknights_mower import __main__ as mower
    from arknights_mower.solvers import base_schedule, record
    from arknights_mower.utils import config

    solver.op_data.urgent_recovery_supporters = {"苍苔": ["机械师"]}
    for attr in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, attr, datetime.now().date())
    solver.task_count = 7
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(mower, "base_scheduler", solver)
    saved = pickle.loads(pickle.dumps(record.current_state()))
    assert solver.initialize_operators() is None
    assert solver.op_data.urgent_recovery_supporters == {}
    monkeypatch.setattr(mower, "initialize", lambda *a, **kw: solver)
    monkeypatch.setattr(mower.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(mower, "refresh_resource_at_boundary", lambda: None)
    solver.emergency_state = None
    solver.tasks, solver.task = [], None
    solver.run = MagicMock(side_effect=base_schedule.MowerExit)
    mower.simulate(saved)
    solver.run.assert_called_once()
    assert solver.op_data.urgent_recovery_supporters == {"苍苔": ["机械师"]}


def test_final_support_records_extra_recall_and_preserves_completed_rooms(solver):
    request, support = start_handoff(solver)
    data = solver.op_data
    data = solver.op_data = data.project_arrangements(
        [
            {
                "meeting": ["陈"],
                "dormitory_1": ["Current", "Current", "Current", "Current", "能天使"],
            }
        ]
    )
    support.plan["meeting"] = ["能天使"]
    solver.task = support
    solver._prepare_group_shift(support, remember_targets=True)
    assert set(support.urgent_recovery_support_names) == {"苍苔", "絮雨", "能天使"}
    solver.op_data = data.project_arrangements([{"meeting": ["能天使"]}])
    del support.plan["meeting"]
    solver._prepare_group_shift(support, remember_targets=True)
    assert "能天使" in support.urgent_recovery_support_names
    assert ("dormitory_1", 4) in support.urgent_recovery_reserved_slots
    assert request in solver.tasks


def test_recovery_departure_keeps_identity_during_backup_coalescing(solver):
    departure = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"room_3_3": ["槐琥"]}
    )
    departure.urgent_recovery_request_names = ["机械师"]
    departure.urgent_recovery_support_names = ["苍苔"]
    solver.tasks = [departure]
    original_time, original_plan = departure.time, deepcopy(departure.plan)
    _, consumed = solver._coalesce_backup_transition({"room_3_3": ["机械师"]})
    assert departure not in consumed
    assert solver.tasks == [departure]
    assert departure.time == original_time
    assert departure.plan == original_plan
    assert departure.urgent_recovery_request_names == ["机械师"]
    assert departure.urgent_recovery_support_names == ["苍苔"]


def ungrouped_support(solver):
    for name in ("苍苔", "絮雨"):
        op = solver.op_data.operators[name]
        op.group, op.group_bindings = "", []
    solver.op_data.groups, solver.op_data.group_shift_state = {}, {}
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"room_2_2": ["苍苔"], "contact": ["絮雨"]},
    )
    task.exhaust_support = True
    task.coordination_request_names = ["机械师"]
    solver.task = task
    solver._prepare_group_shift(task, remember_targets=True)
    return task


def test_ungrouped_partial_support_preserves_actual_return_and_original_bed(solver):
    support = ungrouped_support(solver)
    assert not getattr(support, "group_shift_expected", {})
    solver.op_data = solver.op_data.project_arrangements([{"room_2_2": ["苍苔"]}])
    del support.plan["room_2_2"]
    solver._prepare_group_shift(support, remember_targets=True)
    assert support.urgent_recovery_started
    assert set(support.urgent_recovery_support_names) == {"苍苔", "絮雨"}
    assert ("dormitory_1", 2) in support.urgent_recovery_reserved_slots
    assert support.urgent_recovery_initial_positions["苍苔"] == ("dormitory_1", 2)


def test_unstarted_support_replans_without_preserving_abandoned_returns(solver):
    support = ungrouped_support(solver)
    assert set(support.urgent_recovery_support_names) == {"苍苔", "絮雨"}
    support.plan = {"contact": ["絮雨"]}
    solver._prepare_group_shift(support, remember_targets=True)
    assert not getattr(support, "urgent_recovery_started", False)
    assert support.urgent_recovery_support_names == ["絮雨"]
    assert support.urgent_recovery_reserved_slots == [("dormitory_1", 3)]
    assert solver.op_data.operators["苍苔"].is_resting()
