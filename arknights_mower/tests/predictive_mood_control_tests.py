"""预测调控复用真实轮休入口，固定场景比较两种语言的事件轨迹。"""

import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.tests.mood_calculation_projection_consumers_tests import (
    enable,
    observations,
)
from arknights_mower.utils import predictive_mood_control as control
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture(autouse=True)
def planning_clock(monkeypatch):
    """语义测试不消耗真实时间预算；预算用例自行推进此计时器。"""
    monkeypatch.setattr(control, "perf_counter", lambda: 0.0)


def test_dynamic_rollout_keeps_live_observations_clock_and_config(solver, monkeypatch):
    enable(solver.op_data, NOW, monkeypatch)
    monkeypatch.setattr(
        control,
        "datetime",
        type("Clock", (datetime,), {"now": classmethod(lambda cls, tz=None: NOW)}),
    )
    before = deepcopy(vars(solver.op_data.mood_model)), observations(solver.op_data)
    result = control.plan(solver, NOW)
    assert result["enumeratedCandidates"] > 1
    assert result["eventCount"] > 0
    assert result["snapshot"]["now"] == NOW.timestamp()
    assert (vars(solver.op_data.mood_model), observations(solver.op_data)) == before
    solver.enter_room.assert_not_called()


def test_same_input_reuses_plan_when_only_time_passes(solver, monkeypatch):
    enable(solver.op_data, NOW, monkeypatch)
    first = control.plan(solver, NOW)
    monkeypatch.setattr(
        control, "dynamic_rollout", lambda *a, **k: pytest.fail("cache missed")
    )
    second = control.plan(solver, NOW + timedelta(minutes=1))
    assert second is first and second["reused"]


def test_unknown_recovery_and_event_budget_keep_original_tasks(solver, monkeypatch):
    enable(solver.op_data, NOW, monkeypatch)
    original = SchedulerTask(
        time=NOW - timedelta(hours=1),
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={PRIMARY[0]: [COVERS[0]]},
    )
    original.execution_failure = {"reason": "failed"}
    solver.tasks = [original]
    control.reconcile(solver, NOW)
    assert solver.tasks == [original]
    solver.tasks = []
    snapshot = control.build_snapshot(solver, NOW)
    result = control.dynamic_rollout(solver, snapshot, max_events=0)
    assert result["exhausted"] and not result["complete"]
    assert not solver.tasks


def test_projection_uses_explicit_clock_and_frozen_configuration(solver, monkeypatch):
    enable(solver.op_data, NOW, monkeypatch)
    data = solver.op_data
    future = NOW + timedelta(hours=2)
    projected = data.project_arrangements(
        [], now=future, runtime_conf=data.runtime_conf.model_copy(deep=True)
    )
    assert projected.mood_model.at == future
    assert data.mood_model.at == NOW
    assert projected.operators[PRIMARY[0]].current_mood() == pytest.approx(22)
    projected.runtime_conf.rescue_threshold = 0.1
    assert data.runtime_conf.rescue_threshold == 0.75


def test_disable_removes_only_memory_wakeup_and_preserves_started_work(
    solver, monkeypatch
):
    enable(solver.op_data, NOW, monkeypatch)
    wake = SchedulerTask(time=NOW + timedelta(hours=1))
    wake.mood_control_event = {"at": wake.time.timestamp()}
    started = SchedulerTask(
        task_plan={"room_1_1": [COVERS[0]]}, task_type=TaskTypes.SHIFT_OFF
    )
    started.mood_physical_started = True
    started.execution_retained = True
    solver.tasks = [wake, started]
    solver._mood_control_cache = {"old": True}
    solver.op_data.runtime_conf.test_mood_calculation = False
    control.reconcile(solver, NOW)
    assert solver.tasks == [started]
    assert solver._mood_control_cache is None
    solver.op_data.runtime_conf.test_mood_calculation = True
    monkeypatch.setattr(
        control, "plan", lambda *a, **kw: pytest.fail("retained work replanned")
    )
    control.reconcile(solver, NOW)
    assert solver.tasks == [started]


def test_baseline_wakeup_runs_real_memory_planning_without_extra_read(
    solver, monkeypatch
):
    data = solver.op_data
    data.operators[PRIMARY[0]].mood = 10
    enable(data, NOW, monkeypatch)
    result = control.plan(solver, NOW)
    wake = SchedulerTask(time=NOW)
    wake.mood_control_event = {
        "signature": result["signature"],
        "group": PRIMARY[0],
        "at": NOW.timestamp(),
    }
    solver.tasks = [wake]
    solver.total_agent = list(data.operators.values())
    control.consume_event(solver, wake, NOW)
    assert any(t.type == TaskTypes.SHIFT_OFF for t in solver.tasks)
    solver.enter_room.assert_not_called()


def test_policy_evidence_uses_soft_exception_but_not_group_exhaustion(
    solver, monkeypatch
):
    data = solver.op_data
    enable(data, NOW, monkeypatch)
    member = PRIMARY[0]
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"room_1_1": [COVERS[0]]}
    )
    task.ordinary_coordination = True
    task.coordination_request_names = [member]
    task.mood_control_evidence = {"group": member}
    solver.task = task
    solver._mood_control_projection = True
    solver._mood_control_allowed = {member}
    data.operators[member].mood = 23
    data.mood_model.observe(member, 23, NOW)
    assert solver._ordinary_coordination_needed([member], task)
    data.exhaust_agent.add(member)
    assert not solver._ordinary_coordination_needed([member], task)


def test_dynamic_matching_places_departure_in_real_bed_and_returns(solver, monkeypatch):
    shared_rotation(solver, monkeypatch)
    snapshot = control.build_snapshot(solver, NOW)
    result = control.dynamic_rollout(solver, snapshot)
    assert result["complete"]
    departures = [
        event for event in result["events"] if event["type"] == "departure-complete"
    ]
    returns = [
        event for event in result["events"] if event["type"] == "return-complete"
    ]
    assert len(departures) == len(returns) == len(snapshot["groups"])
    assert all(
        any(room.startswith("dorm") for room in plan)
        for plan in result["plans"].values()
    )
    assert all(event["time"] <= snapshot["horizon"] for event in result["events"])


def shared_rotation(solver, monkeypatch, source=None):
    source = source or {}
    from arknights_mower.utils import calculated_mood

    data = solver.op_data
    for name in PRIMARY[2:]:
        data.operators[name].workaholic = True
    for i, name in enumerate(PRIMARY[:2]):
        op = data.operators[name]
        op.mood = 2 + i
        op.lower_limit = source.get("lower", 0)
        op.replacement = [COVERS[0]]
        op.rest_in_full = True
    data.dorm = data.dorm[:1]
    data.config.resting_threshold = 0

    def rates(payload):
        result = {name: 0 for name in payload["moods"]}
        for room, state in payload["rooms"].items():
            for name in state["roster"]:
                if name not in (*PRIMARY[:2], COVERS[0]):
                    continue
                result[name] = (
                    -source.get("recoveryRate", 24)
                    if room.startswith("dorm")
                    else source.get("workBelow12", source.get("workRate", 1))
                    if payload["moods"].get(name, 24) <= 12 + 1e-8
                    else source.get("workRate", 1)
                )
        return dict(
            rates=result,
            thresholds=[0, 4, 8, 12, 16, 18, 20, 24],
            automaticTargets={},
        )

    monkeypatch.setattr(calculated_mood, "shared_rates", rates)
    enable(data, NOW, monkeypatch)
    monkeypatch.setattr(
        control,
        "datetime",
        type("Clock", (datetime,), {"now": classmethod(lambda cls, tz=None: NOW)}),
    )
    return data


def test_shared_resources_select_real_early_task_and_pass_all_ordinary_guards(
    solver, monkeypatch
):
    shared_rotation(solver, monkeypatch)
    result = control.plan(solver, NOW)
    assert result["decision"] == PRIMARY[0], result
    control.reconcile(solver, NOW)
    tasks = [t for t in solver.tasks if getattr(t, "mood_control_evidence", None)]
    assert len(tasks) == 1
    task = tasks[0]
    assert any(room.startswith("dorm") for room in task.plan)
    solver.task = task
    assert solver._ordinary_coordination_needed([PRIMARY[0]], task)
    assert solver._prepare_ordinary_departure(task)
    solver._validate_calculated_arrangement()
    solver._prepare_shift_cycle(task)
    assert task.plan and getattr(task, "mood_control_evidence", None)
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("backup_shift_active", True),
        ("backup_explicit_slots", (("room_1_1", 0),)),
        ("product_shift_locked", True),
        ("dorm_recovery_restore", (PRIMARY[0],)),
        ("run_order_restore_pending", True),
    ],
)
def test_early_evidence_rechecked_before_physical_action(
    solver, monkeypatch, attribute, value
):
    from arknights_mower.solvers.base_schedule import MoodArrangementChanged

    data = shared_rotation(solver, monkeypatch)
    control.reconcile(solver, NOW)
    task = next(t for t in solver.tasks if getattr(t, "mood_control_evidence", None))
    solver.task = task
    setattr(task, attribute, value)
    data.exhaust_agent.add(PRIMARY[0])
    data.mood_model.observe(PRIMARY[0], 20, NOW)
    assert not solver._prepare_ordinary_departure(task)
    with pytest.raises(MoodArrangementChanged):
        solver._validate_calculated_arrangement()


def test_projection_never_notifies_real_clock_position_setters(solver, monkeypatch):
    from arknights_mower.utils.calculated_mood import CalculatedMood

    enable(solver.op_data, NOW, monkeypatch)
    monkeypatch.setattr(
        CalculatedMood,
        "move",
        lambda *a, **k: pytest.fail("real position notification"),
    )
    projected = solver.op_data.project_arrangements(
        [{"room_1_1": [COVERS[0]], "dormitory_1": ["Current", "Current", PRIMARY[0]]}],
        now=NOW + timedelta(minutes=5),
    )
    assert projected.mood_model.at == NOW + timedelta(minutes=5)
    assert projected.operators[PRIMARY[0]].current_room == "dormitory_1"
    assert solver.op_data.mood_model.at == NOW
    assert solver.op_data.operators[PRIMARY[0]].current_room == "room_1_1"


def test_actual_started_state_invalidates_early_cache(solver, monkeypatch):
    shared_rotation(solver, monkeypatch)
    control.reconcile(solver, NOW)
    task = next(t for t in solver.tasks if getattr(t, "mood_control_evidence", None))
    solver.task = task
    task.mood_physical_started = True
    result = control.plan(solver, NOW)
    assert result["status"] == "insufficient" and result["decision"] is None
    assert not result["reused"]
    assert solver.tasks == [task]


def test_consumed_event_advances_to_next_existing_departure(solver, monkeypatch):
    enable(solver.op_data, NOW, monkeypatch)
    result = {
        "signature": "same-input",
        "decision": None,
        "events": [
            {
                "type": "departure-start",
                "group": PRIMARY[i],
                "time": (NOW + timedelta(hours=i + 1)).timestamp(),
            }
            for i in range(2)
        ],
    }
    monkeypatch.setattr(control, "plan", lambda *a, **k: result)
    solver._plan_primary_recovery = lambda **k: None
    control.reconcile(solver, NOW)
    first = solver.tasks[0]
    control.consume_event(solver, first, NOW + timedelta(hours=1))
    assert len(solver.tasks) == 1
    assert solver.tasks[0].time == NOW + timedelta(hours=2)
    assert not solver.tasks[0].plan
    control.reconcile(solver, NOW + timedelta(hours=1))
    assert len(solver.tasks) == 1 and solver.tasks[0].time == NOW + timedelta(hours=2)


def test_critical_task_never_invents_resource_release(solver, monkeypatch):
    from arknights_mower.utils import scheduler_task

    shared_rotation(solver, monkeypatch)
    monkeypatch.setattr(
        scheduler_task,
        "estimate_task_duration",
        lambda task, **kw: timedelta(minutes=10),
    )
    critical = SchedulerTask(
        time=NOW + timedelta(minutes=5),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_2": ["Current"]},
    )
    solver.tasks = [critical]
    snapshot = control.build_snapshot(solver, NOW)
    result = control.dynamic_rollout(solver, snapshot, PRIMARY[0], NOW.timestamp())
    assert not result["events"] and not result["complete"]
    assert solver.tasks == [critical]


@pytest.mark.parametrize(
    "kind,seconds", [(TaskTypes.DEPOT, 60), (TaskTypes.CLUE_PARTY, 180)]
)
def test_pure_service_window_delays_without_inventing_staffing(
    solver, monkeypatch, kind, seconds
):
    shared_rotation(solver, monkeypatch)
    service = SchedulerTask(time=NOW + timedelta(seconds=30), task_type=kind)
    solver.tasks = [service]
    before = observations(solver.op_data)
    result = control.dynamic_rollout(
        solver, control.build_snapshot(solver, NOW), PRIMARY[0], NOW.timestamp()
    )
    departure = next(e for e in result["events"] if e["type"] == "departure-start")
    assert departure["time"] == (service.time + timedelta(seconds=seconds)).timestamp()
    assert result["complete"] and solver.tasks == [service]
    assert observations(solver.op_data) == before


def test_rollout_horizon_limits_events_and_coverage(solver, monkeypatch):
    shared_rotation(solver, monkeypatch)
    snapshot = control.build_snapshot(solver, NOW)
    snapshot["horizon"] = (NOW + timedelta(seconds=1)).timestamp()
    result = control.dynamic_rollout(solver, snapshot, PRIMARY[0], NOW.timestamp())
    assert not result["complete"] and not result["events"]
    assert result["nodeCount"] == 1
    assert result["score"][:2] == [0, 0]


def test_unknown_observation_recovers_only_after_new_evidence(solver, monkeypatch):
    data = shared_rotation(solver, monkeypatch)
    data.mood_model.observed.pop(PRIMARY[0])
    data.mood_model.moods.pop(PRIMARY[0])
    result = control.plan(solver, NOW)
    assert result["status"] == "insufficient" and result["decision"] is None
    data.mood_model.observe(PRIMARY[0], 2, NOW)
    recovered = control.plan(solver, NOW)
    assert not recovered["reused"] and recovered["decision"] == PRIMARY[0]


def test_protected_workplace_still_counts_uncovered_time(solver, monkeypatch):
    data = shared_rotation(solver, monkeypatch)
    baseline = control.dynamic_rollout(solver, control.build_snapshot(solver, NOW))
    protected = PRIMARY[2]
    data.operators[protected].workaholic = False
    data.mood_model.observe(protected, 0, NOW)
    solver._protected_facility_names = lambda: {protected}
    snapshot = control.build_snapshot(solver, NOW)
    result = control.dynamic_rollout(solver, snapshot)
    assert protected not in {name for g in snapshot["groups"] for name in g["members"]}
    assert result["score"][1] - baseline["score"][1] == pytest.approx(
        snapshot["horizon"] - snapshot["now"]
    )


def test_backup_expansion_rechecks_final_operation_window(solver, monkeypatch):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
    from arknights_mower.utils import scheduler_task

    shared_rotation(solver, monkeypatch)
    monkeypatch.setattr(
        scheduler_task,
        "estimate_task_duration",
        lambda task, **kw: timedelta(seconds=300 * len(task.plan)),
    )

    def expand(self, task):
        task.plan["room_1_3"] = ["Current"]

    monkeypatch.setattr(BaseSchedulerSolver, "_prepare_shift_backup", expand)
    snapshot = control.build_snapshot(solver, NOW)
    snapshot["horizon"] = (NOW + timedelta(seconds=700)).timestamp()
    result = control.dynamic_rollout(solver, snapshot, PRIMARY[0], NOW.timestamp())
    assert not result["events"] and not result["complete"]
    assert not solver.tasks


def test_future_new_decision_does_not_admit_old_departure(solver, monkeypatch):
    shared_rotation(solver, monkeypatch)
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    task.mood_control_evidence = {"group": PRIMARY[0]}
    monkeypatch.setattr(
        control,
        "plan",
        lambda *a, **k: dict(
            decision=PRIMARY[0],
            dependencies={PRIMARY[0]: [PRIMARY[0]]},
            events=[
                dict(
                    type="departure-start",
                    group=PRIMARY[0],
                    time=(NOW + timedelta(hours=1)).timestamp(),
                )
            ],
        ),
    )
    assert not control.admits(solver, [PRIMARY[0]], task)


def test_emergency_freeze_clears_only_prediction_and_never_dispatches(
    solver, monkeypatch
):
    shared_rotation(solver, monkeypatch)
    result = control.plan(solver, NOW)
    wake = SchedulerTask(time=NOW)
    wake.mood_control_event = {
        "signature": result["signature"],
        "group": PRIMARY[0],
        "at": NOW.timestamp(),
    }
    real = SchedulerTask(
        time=NOW + timedelta(hours=1),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"room_1_2": [PRIMARY[1]]},
    )
    solver.tasks = [wake, real]
    solver.emergency_state = {"phase": "recovering"}
    solver._plan_primary_recovery = lambda **kw: pytest.fail(
        "ordinary planning during emergency"
    )
    control.consume_event(solver, wake, NOW)
    assert solver.tasks == [real]
    assert solver._mood_control_cache is None


def test_future_early_wakeup_materializes_once_at_predicted_time(solver, monkeypatch):
    shared_rotation(solver, monkeypatch)
    original = SchedulerTask(time=NOW + timedelta(hours=1))
    solver.tasks = [original]
    result = control.reconcile(solver, NOW)
    assert result["decision"] == PRIMARY[0]
    wake = next(t for t in solver.tasks if getattr(t, "mood_control_event", None))
    assert wake.time == NOW + timedelta(hours=1)
    assert not any(getattr(t, "mood_control_evidence", None) for t in solver.tasks)
    control.consume_event(solver, wake, wake.time)
    evidence = [t for t in solver.tasks if getattr(t, "mood_control_evidence", None)]
    assert len(evidence) == 1 and evidence[0].time == wake.time
    assert original in solver.tasks
    control.reconcile(solver, wake.time)
    assert [
        t for t in solver.tasks if getattr(t, "mood_control_evidence", None)
    ] == evidence
    assert not any(getattr(t, "mood_control_event", None) for t in solver.tasks)


def test_backup_group_change_cannot_reuse_original_departure_identity(
    solver, monkeypatch
):
    from arknights_mower.solvers import record
    from arknights_mower.utils.logic_expression import LogicExpression
    from arknights_mower.utils.news_checker import NewsChecker
    from arknights_mower.utils.plan import Plan, PlanConfig, Room

    data = shared_rotation(solver, monkeypatch)
    backup = Plan(
        {
            "room_1_1": [Room(PRIMARY[0], "joined", [COVERS[0]])],
            "room_1_2": [Room(PRIMARY[1], "joined", [COVERS[0]])],
        },
        PlanConfig("", "", ""),
        trigger=LogicExpression("True", "==", "True"),
    )
    data.global_plan["backup_plans"] = [backup]
    data.backup_plans = [backup]
    data.plan_condition = [False]
    monkeypatch.setattr(record, "get_inventory_counts", lambda *a: {})
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: None)
    result = control.plan(solver, NOW)
    assert result["decision"] is None and result["status"] == "insufficient"
    assert not result["events"]
    assert data.operators[PRIMARY[0]].group == ""


def test_group_completion_waits_for_all_derived_return_tasks(solver, monkeypatch):
    from arknights_mower.utils import calculated_mood, scheduler_task

    data = solver.op_data
    data.groups["joined"] = list(PRIMARY[:2])
    for name in PRIMARY[:2]:
        data.operators[name].group = "joined"
        data.operators[name].mood = 2
        data.operators[name].rest_in_full = True
        for slots in data.global_plan["default_plan"].plan.values():
            for slot in slots:
                if slot.agent == name:
                    slot.group = "joined"
    for name in PRIMARY[2:]:
        data.operators[name].workaholic = True
    data.config.resting_threshold = 0

    def rates(payload):
        return dict(
            rates={
                name: (
                    -24
                    if any(
                        name in state["roster"]
                        for room, state in payload["rooms"].items()
                        if room.startswith("dorm")
                    )
                    else 1
                )
                if name in (*PRIMARY[:2], *COVERS[:2])
                else 0
                for name in payload["moods"]
            },
            thresholds=[0, 24],
            automaticTargets={},
        )

    monkeypatch.setattr(calculated_mood, "shared_rates", rates)
    enable(data, NOW, monkeypatch)
    snapshot = control.build_snapshot(solver, NOW)
    original = scheduler_task.plan_metadata
    due_by_room = {}

    def split(data, tasks, **kwargs):
        derived = original(data, tasks, **kwargs)
        split_tasks = []
        for task in derived:
            if task.type == TaskTypes.SHIFT_ON and len(task.plan) > 1:
                split_tasks.extend(
                    SchedulerTask(
                        time=max(
                            task.time,
                            due_by_room.setdefault(
                                room, task.time + timedelta(minutes=i * 2)
                            ),
                        ),
                        task_type=TaskTypes.SHIFT_ON,
                        task_plan={room: row},
                    )
                    for i, (room, row) in enumerate(task.plan.items())
                )
            else:
                split_tasks.append(task)
        return split_tasks

    monkeypatch.setattr(scheduler_task, "plan_metadata", split)
    result = control.dynamic_rollout(solver, snapshot, "joined", NOW.timestamp())
    assert result["complete"], result
    returned = [e for e in result["events"] if e["type"] == "return-complete"]
    assert len(returned) == 2 and returned[1]["time"] > returned[0]["time"]


def test_existing_departure_event_preserves_queue_without_replanning(
    solver, monkeypatch
):
    shared_rotation(solver, monkeypatch)
    real = SchedulerTask(
        time=NOW + timedelta(minutes=5),
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"room_1_1": [COVERS[0]]},
    )
    wake = SchedulerTask(time=NOW)
    wake.mood_control_event = {
        "signature": "old",
        "group": PRIMARY[0],
        "at": NOW.timestamp(),
    }
    solver.tasks = [wake, real]
    before = deepcopy(vars(real))
    monkeypatch.setattr(
        control, "plan", lambda *a, **kw: pytest.fail("existing departure replanned")
    )
    solver._plan_primary_recovery = lambda **kw: pytest.fail(
        "existing departure replaced"
    )
    control.consume_event(solver, wake, NOW)
    assert solver.tasks == [real] and vars(real) == before


@pytest.mark.parametrize(
    "kind,plan",
    [
        (TaskTypes.RUN_ORDER, {}),
        (TaskTypes.RUN_ORDER, {"room_1_3": [PRIMARY[2]]}),
        (TaskTypes.NOT_SPECIFIC, {"room_1_3": [PRIMARY[2]]}),
        (TaskTypes.EXHAUST_OFF, {"room_1_3": [PRIMARY[2]]}),
    ],
)
def test_late_unknown_task_invalidates_complete_horizon(
    solver, monkeypatch, kind, plan
):
    shared_rotation(solver, monkeypatch)
    pending = SchedulerTask(
        time=NOW + timedelta(hours=10),
        task_type=kind,
        task_plan=deepcopy(plan),
    )
    solver.tasks = [pending]
    before = deepcopy(vars(pending))
    result = control.plan(solver, NOW)
    assert result["decision"] is None and result["status"] == "insufficient"
    assert not result["complete"]
    assert solver.tasks == [pending] and vars(pending) == before
    assert max(e["time"] for e in result["events"]) < pending.time.timestamp()


def test_known_return_still_runs_after_all_participant_groups_return(
    solver, monkeypatch
):
    shared_rotation(solver, monkeypatch)
    pending = SchedulerTask(
        time=NOW + timedelta(hours=10),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"room_1_3": [PRIMARY[2]]},
    )
    solver.tasks = [pending]
    result = control.dynamic_rollout(solver, control.build_snapshot(solver, NOW))
    participant_ends = [
        e["time"]
        for e in result["events"]
        if e["type"] == "return-complete" and e["group"] != "existing"
    ]
    known = [e for e in result["events"] if e["group"] == "existing"]
    assert result["complete"]
    assert max(participant_ends) < pending.time.timestamp()
    assert (
        known[0]["type"] == "return-start"
        and known[0]["time"] == pending.time.timestamp()
    )
    assert solver.tasks == [pending]


SHARED_CASES = json.loads(
    (
        Path(__file__).parents[2]
        / "ui/src/__tests__/fixtures/predictiveMoodControl.json"
    ).read_text()
)


@pytest.mark.parametrize("case", SHARED_CASES, ids=lambda case: case["id"])
def test_shared_production_trajectories(solver, monkeypatch, case):
    from arknights_mower.utils import operation_timing, scheduler_task

    source = case["input"]
    if "maxEvents" in source:
        monkeypatch.setattr(control, "MAX_EVENTS", source["maxEvents"])
    data = shared_rotation(solver, monkeypatch, source)
    names = {"A": PRIMARY[0], "B": PRIMARY[1], "X": COVERS[0]}
    for short, mood in source["moods"].items():
        data.operators[names[short]].mood = mood
        data.mood_model.observe(names[short], mood, NOW)
    data.config.resting_threshold = source["threshold"]
    data.exhaust_agent.update(names[short] for short in source["exhaust"])
    for short in ("A", "B"):
        data.operators[names[short]].rest_in_full = short in source["restInFull"]
    seconds = source["roomSeconds"]
    monkeypatch.setattr(
        scheduler_task,
        "estimate_task_duration",
        lambda task, **kwargs: timedelta(seconds=seconds * len(task.plan)),
    )
    monkeypatch.setattr(
        operation_timing, "estimate_dorm_minutes", lambda *args: seconds / 60
    )
    monkeypatch.setattr(
        operation_timing, "estimate_work_minutes", lambda *args: seconds / 60
    )
    result = control.plan(solver, NOW)
    reverse = {value: "operator:" + key for key, value in names.items()}
    actual = dict(
        decision=reverse.get(result["decision"]),
        status=result["status"],
        score=result["score"],
        events=[
            dict(
                time=e["time"] - NOW.timestamp(),
                type=e["type"],
                group=reverse[e["group"]],
            )
            for e in result["events"]
        ],
        nextWake=None
        if result["nextWake"] is None
        else result["nextWake"] - NOW.timestamp(),
    )
    expected = case["expected"]
    diagnostics = {
        "work-skill-boundary": (4, 4, 170, 32, 44),
        "shared-bed-cover-early": (4, 4, 162, 32, 41),
        "exhaust-hard-limit": (1, 1, 40, 8, 40),
        "nonzero-exhaust-hard-limit": (1, 1, 46, 8, 46),
        "slow-recovery-no-complete-chain": (4, 4, 60, 8, 15),
        "full-recovery-remains-binding": (4, 4, 139, 32, 35),
        "node-budget-41": (4, 4, 162, 32, 41),
        "node-budget-40": (2, 4, 80, 16, 41),
    }
    assert (
        tuple(
            result[k]
            for k in (
                "candidates",
                "enumeratedCandidates",
                "processedNodes",
                "eventCount",
                "maxCandidateNodes",
            )
        )
        == diagnostics[case["id"]]
    )
    assert actual["decision"] == expected["decision"]
    assert actual["status"] == expected["status"]
    assert actual["score"] == pytest.approx(expected["score"], abs=0.01)
    assert len(actual["events"]) == len(expected["events"])
    for got, want in zip(actual["events"], expected["events"]):
        assert got["type"] == want["type"] and got["group"] == want["group"]
        assert got["time"] == pytest.approx(want["time"], abs=0.01)
    assert actual["nextWake"] == pytest.approx(expected["nextWake"], abs=0.01)


def test_service_queue_does_not_expand_candidate_search(solver, monkeypatch):
    shared_rotation(solver, monkeypatch)
    solver.tasks = [
        SchedulerTask(
            time=NOW + timedelta(minutes=5 * (i + 1)), task_type=TaskTypes.DEPOT
        )
        for i in range(10)
    ]
    result = control.plan(solver, NOW)
    assert result["enumeratedCandidates"] == 4
    assert result["status"] == "feasible" and result["decision"] == PRIMARY[0]
    assert len(solver.tasks) == 10


def test_expired_other_group_event_does_not_hide_due_decision(solver, monkeypatch):
    shared_rotation(solver, monkeypatch)
    result = dict(
        signature="same",
        decision=PRIMARY[1],
        events=[
            dict(type="departure-start", group=name, time=NOW.timestamp())
            for name in PRIMARY[:2]
        ],
        plans={PRIMARY[1]: {"room_1_2": [COVERS[0]]}},
        dependencies={PRIMARY[1]: [PRIMARY[1]]},
    )
    monkeypatch.setattr(control, "plan", lambda *a, **kw: result)
    control.reconcile(solver, NOW)
    assert [t.mood_control_evidence["group"] for t in solver.tasks] == [PRIMARY[1]]


def test_candidate_truncation_keeps_baseline_without_evaluating_partial_search(
    solver, monkeypatch
):
    shared_rotation(solver, monkeypatch)
    monkeypatch.setattr(control, "MAX_CANDIDATES", 2)
    original = control.dynamic_rollout
    calls = []

    def rollout(*args, **kwargs):
        calls.append(args[2:] if len(args) > 2 else ())
        return original(*args, **kwargs)

    monkeypatch.setattr(control, "dynamic_rollout", rollout)
    result = control.plan(solver, NOW)
    assert result["status"] == "budget-exhausted" and result["decision"] is None
    assert result["enumeratedCandidates"] == 2 and calls == [()]


def test_batch_deadline_exhaustion_is_cached_without_new_wakes(solver, monkeypatch):
    shared_rotation(solver, monkeypatch)
    clock = [0.0]
    monkeypatch.setattr(control, "perf_counter", lambda: clock[0])
    original = control.build_snapshot

    def snapshot(*args, **kwargs):
        result = original(*args, **kwargs)
        clock[0] = control.MAX_PLANNING_SECONDS + 0.1
        return result

    monkeypatch.setattr(control, "build_snapshot", snapshot)
    result = control.reconcile(solver, NOW)
    assert result["status"] == "budget-exhausted" and result["decision"] is None
    assert result["processedNodes"] == 0 and not solver.tasks
    monkeypatch.setattr(
        control, "build_snapshot", lambda *a: pytest.fail("expired batch retried")
    )
    assert control.plan(solver, NOW + timedelta(minutes=1))["reused"]


def test_readback_revalidation_compares_only_baseline_and_requested_group(
    solver, monkeypatch
):
    data = shared_rotation(solver, monkeypatch)
    result = control.reconcile(solver, NOW)
    task = next(t for t in solver.tasks if getattr(t, "mood_control_evidence", None))
    solver.task = task
    data.mood_model.observe(PRIMARY[0], 2, NOW + timedelta(microseconds=1))
    original = control.dynamic_rollout
    calls = []

    def rollout(*args, **kwargs):
        calls.append(args[2] if len(args) > 2 else None)
        return original(*args, **kwargs)

    monkeypatch.setattr(control, "dynamic_rollout", rollout)
    monkeypatch.setattr(
        control,
        "datetime",
        type("Clock", (datetime,), {"now": classmethod(lambda cls: NOW)}),
    )
    assert control.admits(solver, [PRIMARY[0]], task)
    assert calls == [None, PRIMARY[0]]
    assert result["decision"] == PRIMARY[0]


def test_rollout_mutable_inputs_are_deeply_isolated(solver, monkeypatch):
    from arknights_mower.solvers.base_schedule import (
        BaseSchedulerSolver,
        GroupShiftBlocked,
    )

    data = shared_rotation(solver, monkeypatch)
    solver.waiting_group_shifts = [{"names": [PRIMARY[0]]}]
    task = SchedulerTask(time=NOW + timedelta(hours=20), task_type=TaskTypes.DEPOT)
    task.extra = {"nested": ["original"]}
    solver.tasks = [task]
    before = control._plain(
        (
            vars(data.config),
            data.runtime_conf.model_dump(),
            data.plan,
            data.group_shift_state,
            solver.waiting_group_shifts,
            vars(task),
        )
    )

    def mutate(trial, task):
        assert trial.op_data.eval_model is data.eval_model
        trial.op_data.config.free_room = not data.config.free_room
        trial.op_data.runtime_conf.rescue_threshold = 0.1
        trial.op_data.plan["room_1_1"][0].replacement.append("changed")
        trial.op_data.group_shift_state["changed"] = True
        trial.waiting_group_shifts[0]["names"].append("changed")
        trial.tasks[0].extra["nested"].append("changed")
        raise GroupShiftBlocked("projection stopped")

    monkeypatch.setattr(BaseSchedulerSolver, "_prepare_shift_backup", mutate)
    result = control.dynamic_rollout(
        solver, control.build_snapshot(solver, NOW), PRIMARY[0], NOW.timestamp()
    )
    assert not result["complete"]
    assert (
        control._plain(
            (
                vars(data.config),
                data.runtime_conf.model_dump(),
                data.plan,
                data.group_shift_state,
                solver.waiting_group_shifts,
                vars(task),
            )
        )
        == before
    )


def test_rescue_start_removes_prediction_before_its_due_time(solver, monkeypatch):
    shared_rotation(solver, monkeypatch)
    wake = SchedulerTask(time=NOW + timedelta(hours=1))
    wake.mood_control_event = {"at": wake.time.timestamp()}
    real = SchedulerTask(time=NOW + timedelta(minutes=5), task_type=TaskTypes.DEPOT)
    solver.tasks = [wake, real]
    solver._mood_control_cache = {"old": True}
    solver.emergency_state = {"phase": "recovering"}
    solver._emergency_filter_tasks()
    assert solver.tasks == [real] and solver._mood_control_cache is None


def test_initial_deadline_node_limit_reports_budget_exhaustion(solver, monkeypatch):
    shared_rotation(solver, monkeypatch)
    monkeypatch.setattr(control, "MAX_INITIAL_NODES", 0)
    result = control.plan(solver, NOW)
    assert result["status"] == "budget-exhausted" and result["budgetExhausted"]
    assert result["decision"] is None and result["candidates"] == 0
