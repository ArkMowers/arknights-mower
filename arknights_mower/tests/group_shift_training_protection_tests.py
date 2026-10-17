"""专精保护的训练位不成为绑组确认的永久重试目标。"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, mastery_reader
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests import base_scheduler_tests
from arknights_mower.tests.multi_group_shift_tests import A
from arknights_mower.tests.multi_group_shift_tests import solver as solver
from arknights_mower.utils import config, mastery_db
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def training_group(solver, monkeypatch):
    plan = solver.global_plan["default_plan"].plan
    plan.pop("contact")
    plan["train"] = [Room("褐果", "甲", ["望"]), Room("桃金娘", "甲", ["余"])]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.time_stamp = datetime.now()
    del solver._suppress_train_correction
    config.conf.enable_mastery = True
    monkeypatch.setattr(base_schedule, "_training_room_scan_disabled", False)
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)
    return solver


@pytest.mark.parametrize("source", ["queue", "database", "observed"])
@pytest.mark.parametrize("follow", [False, True])
@pytest.mark.parametrize("other_confirmed", [False, True])
def test_protected_training_does_not_requeue_but_other_targets_still_confirm(
    training_group, monkeypatch, source, follow, other_confirmed
):
    s = training_group
    config.conf.assistant_follows_schedule = follow
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"meeting": ["陈", "Current"], "train": ["望", "余"]},
    )
    s.task, s.tasks = task, [task]
    s._prepare_group_shift(task, remember_targets=True)
    # Protection can become known only when the task enters the training room.
    if source == "queue":
        s.tasks.append(SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE))
        s.find_next_task.side_effect = lambda **kw: next(
            (t for t in s.tasks if t.type == kw.get("task_type")), None
        )
    elif source == "database":
        monkeypatch.setattr(mastery_db, "get_active_plan", lambda: {"id": 1})
    else:
        s.train_room_state = mastery_reader.RoomState("training")
    observed = {}
    if other_confirmed:
        observed.update(
            {room: row for room, row in task.plan.items() if room != "train"}
        )
    if follow:
        observed["train"] = ["望", "Current"]
    projected = s.op_data.project_arrangements([observed])
    s.op_data.operators, s.op_data.dorm = projected.operators, projected.dorm
    task.plan.clear()
    assert s._complete_group_shift(task) is other_confirmed
    assert s.op_data.group_is_resting("甲") is other_confirmed
    if not other_confirmed:
        assert task.plan["meeting"] == ["陈", "Current"]
        assert "train" not in task.plan
        assert any(
            A in row for room, row in task.plan.items() if room.startswith("dorm")
        )
        assert ("train", 1) not in task.group_shift_expected
        if not follow:
            assert ("train", 0) not in task.group_shift_expected


def test_assistant_follow_does_not_retain_protected_targets(training_group):
    s = training_group
    config.conf.assistant_follows_schedule = True
    s.train_room_state = mastery_reader.RoomState("training")
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"train": ["望", "余"]}
    )
    s.task, s.tasks = task, [task]
    s._prepare_group_shift(task, remember_targets=True)
    task.plan.clear()
    assert s._complete_group_shift(task)
    assert not task.plan
    assert not s.op_data.group_is_resting("甲")


def test_training_only_skipped_transition_does_not_commit_group(training_group):
    s = training_group
    config.conf.assistant_follows_schedule = False
    s.train_room_state = mastery_reader.RoomState("training")
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"train": ["望", "余"]}
    )
    s.task, s.tasks = task, [task]
    s._prepare_group_shift(task, remember_targets=True)
    task.plan.clear()
    assert s._complete_group_shift(task)
    assert not s.op_data.group_is_resting("甲")
    assert s.op_data.operators[A].current_room == "meeting"


@pytest.mark.parametrize("follow", [False, True])
@pytest.mark.parametrize("resting", [False, True])
def test_partial_group_targets_skip_protected_training_without_waiting(
    training_group, follow, resting
):
    s = training_group
    config.conf.assistant_follows_schedule = follow
    s.train_room_state = mastery_reader.RoomState("training")
    s.op_data.commit_group_shifts({"甲": not resting})
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF if resting else TaskTypes.SHIFT_ON,
        task_plan={"meeting": ["陈" if resting else A, "Current"]},
    )
    s.task, s.tasks = task, [task]
    before = task.time
    s._prepare_group_shift(task, remember_targets=True)
    assert task.time == before
    assert ("train", 1) not in task.group_shift_expected
    assert ("train", 0) not in task.group_shift_expected
    projected = s.op_data.project_arrangements([task.plan])
    projected.group_shift_state = dict(s.op_data.group_shift_state)
    s.op_data = projected
    task.plan.clear()
    assert s._complete_group_shift(task)
    assert s.op_data.group_is_resting("甲") is resting


def test_dispatch_finishes_group_after_live_training_gate_skips_room(
    training_group, monkeypatch
):
    s = training_group
    config.conf.assistant_follows_schedule = False
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"meeting": ["陈", "Current"], "train": ["望", "余"]},
    )
    s.task, s.tasks = task, [task]
    s.find = MagicMock(return_value=(1, 1))
    s.refresh_connecting = False
    s._prepare_shift_cycle = MagicMock()
    s._switch_products_before_arrangement = MagicMock()
    s.backup_plan_solver = MagicMock(return_value=False)
    s.skip = MagicMock()
    s.enter_room, s.back = MagicMock(), MagicMock()
    s.turn_on_room_detail = MagicMock(side_effect=AssertionError("protected room"))
    monkeypatch.setattr(
        base_schedule, "protect_priority_tasks", lambda tasks, **kwargs: None
    )
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *a, **kw: mastery_reader.RoomState("training"),
    )
    monkeypatch.setattr(mastery_reader, "reconcile_short", lambda *a, **kw: False)

    def arrange(plan, get_time):
        s.agent_arrange_room({}, "train", plan)
        s._suppress_train_arrangement(plan)
        completed = {room: plan.pop(room) for room in list(plan) if room != "train"}
        projected = s.op_data.project_arrangements([completed])
        s.op_data.operators, s.op_data.dorm = projected.operators, projected.dorm
        assert not plan

    s.agent_arrange = MagicMock(side_effect=arrange)
    s.infra_main()
    s.agent_arrange.assert_called_once()
    s.turn_on_room_detail.assert_not_called()
    assert task not in s.tasks
    assert s.op_data.group_is_resting("甲")
    assert not task.group_shift_expected
    assert s.op_data.get_current_room("train", True) == ["褐果", "桃金娘"]


@pytest.mark.parametrize("follow", [False, True])
@pytest.mark.parametrize("state", ["training", "waiting_collect", "unreadable"])
@pytest.mark.parametrize("other_confirmed", [False, True])
def test_mastery_off_confirms_assistant_without_requeueing_busy_trainee(
    training_group, monkeypatch, follow, state, other_confirmed
):
    monkeypatch.setattr(BaseSchedulerSolver, "__init__", lambda _: None)
    config.conf.enable_mastery = False
    config.conf.assistant_follows_schedule = follow
    plan = {"train": ["望", "余"], "meeting": ["陈", "Current"]}
    s = base_scheduler_tests.TestTrainGateReadThenJudge._make_solver(plan)
    s.op_data = training_group.op_data
    s.find_next_task = MagicMock(return_value=None)
    s._resume_waiting_group_shifts = MagicMock()
    task = s.task
    s._prepare_group_shift(task, remember_targets=True)
    s.choose_train = MagicMock()

    def select(names, **kwargs):
        assert names == ["望", "Current"]
        projected = s.op_data.project_arrangements([{"train": names}])
        s.op_data.operators, s.op_data.dorm = projected.operators, projected.dorm

    s.choose_train.side_effect = select
    s.get_agent_from_room = MagicMock(
        side_effect=lambda *a, **kw: [
            {"agent": name} for name in s.op_data.get_current_room("train", True)
        ]
    )
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *a, **kw: (
            None if state == "unreadable" else mastery_reader.RoomState(state)
        ),
    )
    reconcile = MagicMock(side_effect=AssertionError("mastery disabled"))
    monkeypatch.setattr(mastery_reader, "reconcile_short", reconcile)

    s.agent_arrange_room({}, "train", plan)
    s.choose_train.assert_called_once()
    assert s.op_data.get_current_room("train", True) == ["望", "桃金娘"]
    if other_confirmed:
        projected = s.op_data.project_arrangements([task.plan])
        s.op_data.operators, s.op_data.dorm = projected.operators, projected.dorm
    plan.clear()

    assert s._complete_group_shift(task) is other_confirmed
    assert s.op_data.group_is_resting("甲") is other_confirmed
    assert ("train", 1) not in task.group_shift_expected
    if not other_confirmed:
        assert task.plan["meeting"] == ["陈", "Current"]
        assert "train" not in task.plan
        assert any(
            A in row for room, row in task.plan.items() if room.startswith("dorm")
        )
    reconcile.assert_not_called()


def test_mastery_off_skipped_only_trainee_does_not_commit_group(
    training_group, monkeypatch
):
    s = training_group
    config.conf.enable_mastery = False
    config.conf.assistant_follows_schedule = False
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"train": ["Current", "余"]},
    )
    s.task, s.tasks = task, [task]
    s._prepare_group_shift(task, remember_targets=True)
    s.enter_room, s.back = MagicMock(), MagicMock()
    s.turn_on_room_detail = MagicMock(side_effect=AssertionError("no named target"))
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *a, **kw: mastery_reader.RoomState("training"),
    )

    s.agent_arrange_room({}, "train", task.plan)

    assert not task.plan
    assert s._complete_group_shift(task)
    assert not s.op_data.group_is_resting("甲")
    assert s.op_data.get_current_room("train", True) == ["褐果", "桃金娘"]


@pytest.mark.parametrize("follow", [False, True])
def test_protected_training_does_not_require_replacements_or_beds(
    training_group, follow
):
    s = training_group
    config.conf.assistant_follows_schedule = follow
    s.train_room_state = mastery_reader.RoomState("training")
    for name in ("褐果", "桃金娘"):
        s.op_data.operators[name].replacement = []
    result = {}
    s.get_resting_plan(s.op_data.shift_group_members("甲"), [], result, 0)
    assert result["meeting"][0] == "陈"
    assert "train" not in result
    assert all(
        name not in ("褐果", "桃金娘") for row in result.values() for name in row
    )
    assert s.op_data.get_current_room("train", True) == ["褐果", "桃金娘"]


@pytest.mark.parametrize("restart", [False, True])
def test_protected_source_occupant_is_skipped_in_other_room_and_confirmation(
    training_group, restart
):
    import pickle

    s = training_group
    config.conf.assistant_follows_schedule = True
    s.train_room_state = mastery_reader.RoomState("training")
    trainee = s.op_data.operators[A]
    trainee._current_room, trainee.current_index = "train", 1
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": [A, "Current"], "train": ["褐果", "桃金娘"]},
    )
    task.group_shift_transitions = {"甲": False}
    task.group_shift_expected = {("meeting", 0): A, ("train", 1): "桃金娘"}
    if restart:
        task = pickle.loads(pickle.dumps(task))
    s.task, s.tasks = task, [task]
    before = task.time
    s._prepare_group_shift(task, remember_targets=True)
    assert not task.plan
    assert s._complete_group_shift(task)
    assert not task.group_shift_expected
    assert task.time == before
    assert trainee.current_room == "train"


@pytest.mark.parametrize("observed", ["training", "unreliable", "unreadable"])
def test_live_source_training_is_skipped_before_other_room_selection(
    training_group, monkeypatch, observed
):
    s = training_group
    trainee = s.op_data.operators[A]
    trainee._current_room, trainee.current_index = "train", 1
    s.train_room_state = None
    plan = {"meeting": [A, "Current"], "contact": ["银灰"]}
    task = SchedulerTask(task_plan=plan, task_type=TaskTypes.SHIFT_ON)
    s.task, s.tasks = task, [task]
    s._track_idle_dorm_shift = MagicMock()
    s._finish_idle_dorm_shift = MagicMock()
    s.back_to_infrastructure = MagicMock()
    read = MagicMock(
        return_value=None
        if observed == "unreadable"
        else mastery_reader.RoomState("empty", slots_read=True, slots_reliable=False)
        if observed == "unreliable"
        else mastery_reader.RoomState(observed)
    )
    monkeypatch.setattr(mastery_reader, "read_room_state", read)
    executed = []

    def arrange(new_plan, room, plan, **kwargs):
        executed.append(room)
        del plan[room]
        return new_plan

    s.agent_arrange_room = MagicMock(side_effect=arrange)
    before = task.time
    s.agent_arrange(plan)
    read.assert_called_once_with(s)
    assert executed == ["contact"]
    assert not plan
    assert task.time == before
    assert trainee.current_room == "train"


def test_protected_only_predecessor_does_not_block_other_group_work(training_group):
    s = training_group
    s.train_room_state = mastery_reader.RoomState("training")
    predecessor = SchedulerTask(task_plan={}, task_type=TaskTypes.SHIFT_OFF)
    predecessor.group_shift_transitions = {"甲": True}
    predecessor.group_shift_expected = {("train", 0): "望"}
    task = SchedulerTask(
        task_plan={"meeting": ["陈", "Current"]}, task_type=TaskTypes.SHIFT_OFF
    )
    s.task, s.tasks = task, [predecessor, task]
    before = task.time
    s._prepare_group_shift(task, remember_targets=True)
    assert task.plan["meeting"][0] == "陈"
    assert "train" not in task.plan
    assert task.time == before
    assert not getattr(task, "group_shift_predecessors", ())


@pytest.fixture
def shared_training_group(solver, monkeypatch):
    s = solver
    plan = s.global_plan["default_plan"].plan
    plan["train"] = [plan.pop("contact")[0], Room("桃金娘", "", ["余"])]
    assert s.initialize_operators() is None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.time_stamp = datetime.now()
    config.conf.enable_mastery = True
    monkeypatch.setattr(base_schedule, "_training_room_scan_disabled", False)
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)
    s.train_room_state = mastery_reader.RoomState("training")
    return s


@pytest.mark.parametrize("resting", [False, True])
@pytest.mark.parametrize("available", [False, True])
def test_shared_training_skips_matching_and_confirmation(
    shared_training_group, resting, available
):
    s = shared_training_group
    if not available:
        for name in ("红", "黑角"):
            s.op_data.operators[name]._current_room = "factory"
    s.op_data.commit_group_shifts({"甲": not resting})
    if not resting:
        cover = s.op_data.operators["红"]
        cover._current_room, cover.current_index = "train", 0
        s.op_data.operators["讯使"]._current_room = ""
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF if resting else TaskTypes.SHIFT_ON,
        task_plan={"meeting": ["陈" if resting else A, "Current"]},
    )
    s.task, s.tasks = task, [task]
    before = task.time
    s._prepare_group_shift(task, remember_targets=True)
    assert "train" not in task.plan
    assert not any(room == "train" for room, _ in task.group_shift_expected)
    s.op_data = s.op_data.project_arrangements([task.plan])
    task.plan.clear()
    assert s._complete_group_shift(task)
    assert s.op_data.group_is_resting("甲") is resting
    assert task.time == before
    assert s.op_data.get_current_operator("train", 0).name == (
        "讯使" if resting else "红"
    )


def test_protected_shared_slot_creates_no_cross_group_predecessor(
    shared_training_group,
):
    s = shared_training_group
    first = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["陈", "Current"]}
    )
    s.task, s.tasks = first, [first]
    s._prepare_group_shift(first, remember_targets=True)
    second = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["Current", "初雪"]}
    )
    s.task, s.tasks = second, [first, second]
    before = second.time
    s._prepare_group_shift(second, remember_targets=True)
    assert second.plan["meeting"] == ["Current", "初雪"]
    assert "train" not in second.plan
    first_beds = {
        slot for slot in first.group_shift_expected if slot[0].startswith("dorm")
    }
    second_beds = {
        slot for slot in second.group_shift_expected if slot[0].startswith("dorm")
    }
    assert first_beds.isdisjoint(second_beds)
    assert second.time == before
    assert not getattr(second, "group_shift_predecessors", ())


def test_protected_shared_slot_does_not_suppress_generated_return(
    shared_training_group,
):
    from datetime import timedelta

    from arknights_mower.tests.multi_group_shift_tests import shift_off

    s = shared_training_group
    assert shift_off(s, "甲")[0]
    data = s.op_data
    data.commit_group_shifts({"甲": True, "乙": True})
    data.get_dorm_by_name(A)[1].time = datetime.now() + timedelta(hours=1)
    data.operators[A].mood = 10
    data.operators["银灰"].depletion_rate = 0
    # The remaining binding has no available cover, but mastery owns this slot.
    data.operators["黑角"]._current_room = "factory"
    s.plan_metadata()
    returns = [t for t in s.tasks if t.type == TaskTypes.SHIFT_ON]
    assert returns
    assert any(t.plan.get("meeting", [None])[0] == A for t in returns)
    assert all("train" not in t.plan for t in returns)
    assert data.get_current_operator("train", 0).name == "讯使"
    assert data.group_is_resting("甲")
