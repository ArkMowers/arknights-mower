"""A scheduled cover may train only when its removal leaves a valid schedule."""

import pickle
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import mastery, mastery_reader
from arknights_mower.tests.exhaust_replacement_tests import solver as solver
from arknights_mower.utils import (
    config,
    mastery_db,
    mastery_recommendation,
    schedule_roster,
)
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.mastery_support_data import trainee_schedule_conflict
from arknights_mower.utils.operators import Operator, Operators, build_global_plan
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    task_view,
)


def schedule(covers=("凯尔希", "芬")):
    return {
        "plan1": {
            "central": {
                "plans": [
                    {"agent": "能天使", "group": "生产组", "replacement": list(covers)}
                ]
            },
            "dormitory_1": {"plans": [{"agent": "Free"} for _ in range(5)]},
        }
    }


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=True))
    monkeypatch.setattr(
        schedule_roster,
        "collect_roster_warnings",
        MagicMock(side_effect=AssertionError("Unexpected roster access")),
    )


@pytest.mark.parametrize("as_model", [False, True])
def test_spare_cover_can_train_without_changing_configuration(as_model):
    document = schedule()
    plan = PlanModel(**document) if as_model else document
    before = deepcopy(plan)
    assert trainee_schedule_conflict("凯尔希", plan) is None
    assert plan == before
    assert trainee_schedule_conflict("凯尔希", plan, allow_replacements=False)


@pytest.mark.parametrize("backup", [False, True])
def test_only_cover_remains_blocked(backup):
    document = schedule()
    if backup:
        document["backup_plans"] = [
            {
                "name": "夜班",
                "plan": schedule(("凯尔希",))["plan1"],
                "trigger": {"left": "True", "operator": "", "right": ""},
            }
        ]
    else:
        document = schedule(("凯尔希",))
    reason = trainee_schedule_conflict("凯尔希", document)
    assert "替换组缺失" in reason
    if backup:
        assert "夜班" in reason


def test_shared_remaining_cover_cannot_cover_two_group_members():
    document = schedule()
    document["plan1"]["central"]["plans"].append(
        {"agent": "银灰", "group": "生产组", "replacement": ["凯尔希", "芬"]}
    )
    assert "替换组数量不够" in trainee_schedule_conflict("凯尔希", document)
    document["plan1"]["central"]["plans"][1]["replacement"].append("红")
    assert trainee_schedule_conflict("凯尔希", document) is None


def test_all_binding_columns_are_removed():
    document = schedule(("芬",))
    document["plan1"]["central"]["plans"][0]["group_bindings"] = [
        {"group": "备用组", "replacement": ["凯尔希"]}
    ]
    assert "每个绑组都需要替班" in trainee_schedule_conflict("凯尔希", document)


@pytest.mark.parametrize("backup", [False, True])
def test_fixed_primary_is_never_removed(backup):
    document = schedule()
    table = {"meeting": {"plans": [{"agent": "凯尔希", "replacement": ["红"]}]}}
    if backup:
        document["backup_plans"] = [{"plan": table}]
    else:
        document["plan1"].update(table)
    assert "固定主班" in trainee_schedule_conflict("凯尔希", document)


def test_explicit_backup_staffing_keeps_cover_reserved():
    document = schedule()
    document["backup_plans"] = [{"task": {"central": ["凯尔希"]}}]
    assert "换人任务" in trainee_schedule_conflict("凯尔希", document)


def test_incomplete_validation_does_not_admit_training(monkeypatch):
    from arknights_mower.utils import backup_validation

    def exceed(*args, **kwargs):
        raise backup_validation.BackupValidationLimitExceeded("验证预算已用尽")

    monkeypatch.setattr(backup_validation, "possible_backup_conditions", exceed)
    assert "验证预算已用尽" in trainee_schedule_conflict("凯尔希", schedule())


@pytest.mark.parametrize("spare", [False, True])
def test_candidate_dispatch_uses_removal_validation(monkeypatch, tmp_path, spare):
    document = schedule(("凯尔希", "芬") if spare else ("凯尔希",))
    monkeypatch.setattr(config, "plan", PlanModel(**document))
    monkeypatch.setattr(
        mastery_db,
        "get_path",
        lambda value: tmp_path / "data.db" if value.endswith("data.db") else tmp_path,
    )
    monkeypatch.setattr(mastery_db, "_tables_created", set())
    assert (
        mastery_db.insert_plan(
            "char_003_kalts", 0, 3, skill_name="指令：结构加固", char_name="凯尔希"
        )
        > 0
    )
    monkeypatch.setattr(
        mastery_recommendation,
        "_find_skill_data",
        lambda: str(tmp_path / "missing.json"),
    )
    monkeypatch.setattr(
        mastery_recommendation,
        "get_mastery_recommendations",
        lambda: {
            "has_data": True,
            "operators": [
                {
                    "char_id": "char_003_kalts",
                    "name": "凯尔希",
                    "profession": "MEDIC",
                    "recommendations": [
                        {
                            "skill_index": 0,
                            "skill_name": "指令：结构加固",
                            "current_level": 0,
                            "chain_needed_materials": [],
                        }
                    ],
                }
            ],
        },
    )
    result = mastery_recommendation.auto_schedule_mastery_tasks(inventory={})
    assert [entry["name"] for entry in result["scheduled"]] == (
        ["凯尔希"] if spare else []
    )
    assert [entry["name"] for entry in result["skipped"]] == (
        [] if spare else ["凯尔希"]
    )


def test_training_cover_stays_protected_while_original_schedule_rotates(
    solver, monkeypatch
):
    model = PlanModel(**schedule())
    monkeypatch.setattr(config, "plan", model)
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    assert trainee_schedule_conflict("凯尔希") is None
    solver.global_plan = build_global_plan()
    assert solver.initialize_operators() is None
    solver.op_data.add(Operator("逻各斯", ""))
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "central": ["能天使"],
                "train": ["逻各斯", "凯尔希"],
            }
        ]
    )
    for operator in solver.op_data.operators.values():
        operator.mood, operator.time_stamp = 12, datetime.now()
    solver.op_data.operators["能天使"].mood = 0
    solver.train_room_state = mastery_reader.RoomState(
        "training",
        support_slot="逻各斯",
        train_slot="凯尔希",
        slots_read=True,
        slots_reliable=True,
    )
    monkeypatch.setattr(
        mastery_db, "get_active_plan", lambda: {"id": 1, "status": "training"}
    )
    solver.task = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="能天使")
    solver.find_next_task = MagicMock(return_value=None)
    solver.check_fia = MagicMock(return_value=([], None))
    solver.skip = MagicMock()
    solver.overtake_room()
    departure = next(task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF)
    assert departure.plan["central"] == ["芬"]
    assert "能天使" in departure.plan["dormitory_1"]
    assert "凯尔希" not in {name for names in departure.plan.values() for name in names}
    assert solver.op_data.operators["凯尔希"].current_room == "train"
    assert model == PlanModel(**schedule())
    solver.enter_room.assert_not_called()


@pytest.fixture
def start(monkeypatch):
    model = PlanModel(**schedule())
    monkeypatch.setattr(config, "plan", model)
    data = Operators(build_global_plan())
    assert data.init_and_validate() is None
    solver = MagicMock(op_data=data, tasks=[], waiting_group_shifts=[])
    plan = {
        "id": 1,
        "char_id": "char_003_kalts",
        "char_name": "凯尔希",
        "skill_index": 0,
        "target_level": 3,
        "status": "idle",
    }
    update = MagicMock()
    monkeypatch.setattr(mastery_db, "update_plan_status", update)
    monkeypatch.setattr(mastery_db, "should_notify", lambda *args: False)
    requirements = MagicMock(return_value="后续条件未满足")
    monkeypatch.setattr(
        mastery_recommendation, "get_mastery_requirement_error", requirements
    )
    return SimpleNamespace(
        solver=solver, plan=plan, update=update, requirements=requirements
    )


@pytest.mark.parametrize("level", [0, 1, 2])
def test_first_and_subsequent_stages_cross_schedule_gate(start, level):
    start.plan["current_level"] = level
    mastery._start_new_training(start.solver, start.plan)
    start.requirements.assert_called_once()
    start.update.assert_called_once_with(1, "failed", failed_reason="后续条件未满足")
    start.solver.enter_room.assert_not_called()


@pytest.mark.parametrize("room", ["central", "dormitory_1"])
def test_occupied_cover_waits_without_losing_plan_and_resumes_after_release(
    start, room
):
    operator = start.solver.op_data.operators["凯尔希"]
    if room.startswith("dorm"):
        start.solver.op_data.plan[room][0].agent = "红"
    operator.current_room, operator.current_index = room, 0
    before = deepcopy(start.plan)
    for _ in range(2):
        mastery._start_new_training(start.solver, start.plan)
    assert start.plan == before
    start.update.assert_not_called()
    start.requirements.assert_not_called()
    assert start.solver.tasks == []
    operator.current_room, operator.current_index = "", -1
    mastery._start_new_training(start.solver, start.plan)
    start.requirements.assert_called_once()


def test_dynamic_dorm_recovery_does_not_block_training(start):
    operator = start.solver.op_data.operators["凯尔希"]
    operator.current_room, operator.current_index = "dormitory_1", 0
    mastery._start_new_training(start.solver, start.plan)
    start.requirements.assert_called_once()


@pytest.mark.parametrize("waiting", [False, True])
@pytest.mark.parametrize("expected_only", [False, True])
def test_staffing_reservation_keeps_original_task_and_releases(
    start, waiting, expected_only
):
    task = SchedulerTask(
        time=datetime.now() - timedelta(minutes=3),
        task_plan={} if expected_only else {"central": ["凯尔希"]},
        task_type=TaskTypes.SHIFT_OFF,
    )
    if expected_only:
        task.group_shift_expected = {("central", 0): "凯尔希"}
    queue = start.solver.waiting_group_shifts if waiting else start.solver.tasks
    queue.append(task)
    original_time = task.time
    for _ in range(2):
        mastery._start_new_training(start.solver, start.plan)
    start.requirements.assert_not_called()
    start.update.assert_not_called()
    assert queue == [task] and task.time == original_time
    queue.clear()
    mastery._start_new_training(start.solver, start.plan)
    start.requirements.assert_called_once()


@pytest.mark.usefixtures("offline_maintenance")
@pytest.mark.parametrize("blocker", ["occupied", "queued", "suspended"])
@pytest.mark.parametrize("restored", [False, True])
def test_dispatch_retains_start_releases_independent_work_and_resumes(
    solver, monkeypatch, blocker, restored
):
    from arknights_mower.utils import workshop_automation

    monkeypatch.setattr(config, "plan", PlanModel(**schedule()))
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    solver.global_plan = build_global_plan()
    assert solver.initialize_operators() is None
    solver.waiting_group_shifts = []
    solver.refresh_connecting = False
    solver.find = MagicMock(return_value=True)
    solver.skip = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver._initialize_startup_facilities = MagicMock()
    solver._reconcile_initial_staffing = MagicMock()
    solver.craft_material = MagicMock()
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    plan = {
        "id": 1,
        "char_id": "char_003_kalts",
        "char_name": "凯尔希",
        "skill_index": 0,
        "target_level": 3,
        "status": "idle",
    }
    monkeypatch.setattr(mastery_db, "get_plan_by_id", lambda _: plan)
    update = MagicMock()
    monkeypatch.setattr(mastery_db, "update_plan_status", update)
    requirements = MagicMock(return_value="后续条件未满足")
    monkeypatch.setattr(
        mastery_recommendation, "get_mastery_requirement_error", requirements
    )
    room = mastery_reader.RoomState("empty")
    read = MagicMock(return_value=(plan, True, room))
    monkeypatch.setattr(mastery_reader, "reconcile_and_act", read)
    task = SchedulerTask(
        datetime.now() - timedelta(minutes=5), task_type=TaskTypes.SKILL_UPGRADE
    )
    task.plan_key = "1"
    at = task.time
    other = SchedulerTask(task_type=TaskTypes.WORKSHOP)
    staffing = SchedulerTask(
        task_plan={"central": ["凯尔希"]}, task_type=TaskTypes.SHIFT_OFF
    )
    solver.tasks, solver.task = [task], task
    if blocker == "occupied":
        op = solver.op_data.operators["凯尔希"]
        op.current_room, op.current_index = "central", 0
    elif blocker == "queued":
        solver.tasks.append(staffing)
    else:
        solver.waiting_group_shifts.append(staffing)
    solver.infra_main()
    assert task in solver.tasks and task.time == at
    assert task.execution_failure and task.mastery_trainee_wait == "凯尔希"
    update.assert_not_called()
    if restored:
        solver.tasks, solver.waiting_group_shifts = pickle.loads(
            pickle.dumps(
                (
                    solver.tasks,
                    solver.waiting_group_shifts,
                )
            )
        )
        task = next(p for p in solver.tasks if p.type == TaskTypes.SKILL_UPGRADE)
    solver.tasks.append(other)
    for _ in range(3):
        solver._resume_failed_tasks()
        assert task not in task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data)
        assert task.time == at and task.execution_failure
    solver.task = other
    solver.infra_main()
    solver.craft_material.assert_called_once()
    assert other not in solver.tasks
    assert task in solver.tasks and task.time == at
    read.assert_called_once()
    solver.op_data.operators["凯尔希"].current_room = ""
    solver.tasks = [task]
    solver.waiting_group_shifts.clear()
    solver._resume_failed_tasks()
    assert not hasattr(task, "execution_failure")
    assert task.time == at and task in task_view(
        solver.tasks, TaskScope.DISPATCH, solver.op_data
    )
    solver.task = task
    solver.infra_main()
    requirements.assert_called_once()
    assert task not in solver.tasks and task.time == at
