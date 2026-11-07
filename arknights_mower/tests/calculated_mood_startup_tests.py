"""通过实际运行状态恢复入口验证计算模式的启动实读与待办保留。"""

import io
import pickle
import sqlite3
from datetime import datetime, timedelta

import pytest

from arknights_mower.solvers import record
from arknights_mower.tests.recall_resume_tests import resume as resume
from arknights_mower.tests.recall_resume_tests import solver as solver
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.mark.parametrize("snapshot_kind", ["legacy", "incompatible", "compatible"])
def test_enabled_resume_reads_all_facilities_and_preserves_started_task(
    resume, monkeypatch, snapshot_kind
):
    from arknights_mower import __main__ as main
    from arknights_mower.data import base_room_list

    solver, load = resume
    monkeypatch.setattr(config.conf, "test_mood_calculation", True)
    task = SchedulerTask(
        time=datetime(2026, 10, 1, 8),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"room_2_2": ["苍苔"]},
    )
    task.execution_retained = True
    task.mood_physical_started = True
    solver.tasks = [task]
    saved = pickle.loads(pickle.dumps(record.current_state()))
    saved["initial_mood_pending"] = False
    saved["initial_mood_refresh_rooms"] = []
    if snapshot_kind == "legacy":
        saved.pop("calculated_mood")
    elif snapshot_kind == "incompatible":
        saved["calculated_mood"]["rules_hash"] = "previous-rules"

    load(saved)
    running = main.base_scheduler
    assert running.defer_backup_plan_until_mood_read
    assert running._initial_mood_refresh_rooms >= {
        room for room in base_room_list if not room.startswith("gaming")
    }
    retained = next(task for task in running.tasks if task.type == TaskTypes.SHIFT_ON)
    assert retained.time == datetime(2026, 10, 1, 8)
    assert retained.plan == {"room_2_2": ["苍苔"]}
    assert retained.retains_execution and retained.mood_physical_started


@pytest.mark.parametrize("queued", [False, True])
@pytest.mark.parametrize(
    "enabled,status,required",
    [
        (False, None, False),
        (False, "training", False),
        (True, None, False),
        (True, "idle", True),
        (True, "arranging", True),
        (True, "training", True),
        (True, "waiting_collect", True),
        (True, "failed", True),
    ],
)
def test_ordinary_resume_requires_training_read_only_for_mastery_plans(
    resume, monkeypatch, enabled, status, required, queued
):
    from arknights_mower import __main__ as main
    from arknights_mower.utils import mastery_db

    solver, load = resume
    monkeypatch.setattr(config.conf, "test_mood_calculation", False)
    monkeypatch.setattr(config.conf, "enable_mastery", enabled)
    monkeypatch.setattr(
        mastery_db,
        "get_reconcile_plans",
        lambda: [{"id": 1, "status": status}] if status else [],
    )
    task = SchedulerTask(
        time=datetime.now() + timedelta(days=1)
        if required
        else datetime(2026, 10, 1, 9),
        task_type=TaskTypes.SKILL_UPGRADE,
    )
    solver.tasks = [task] if queued else []
    saved = pickle.loads(pickle.dumps(record.current_state()))
    saved["initial_mood_pending"] = False
    saved["initial_mood_refresh_rooms"] = []
    load(saved)
    assert not main.base_scheduler.defer_backup_plan_until_mood_read
    assert main.base_scheduler._initial_mood_refresh_rooms == (
        {"train"} if required else set()
    )
    main.base_scheduler._read_agent_mood.assert_not_called()
    assert main.base_scheduler._state_restore_complete is True
    if required:
        observations = [
            pending
            for pending in main.base_scheduler.tasks
            if pending.type == TaskTypes.NOT_SPECIFIC and not pending.plan
        ]
        assert len(observations) == 1
        assert observations[0].time <= datetime.now()
    if queued:
        restored = next(
            task
            for task in main.base_scheduler.tasks
            if task.type == TaskTypes.SKILL_UPGRADE
        )
        assert restored.time == task.time


def test_saved_state_remains_readable_without_calculation_module(
    resume, monkeypatch, tmp_path
):
    solver, load = resume
    monkeypatch.setattr(config.conf, "test_mood_calculation", True)
    model = solver.op_data.mood_model
    operator = solver.op_data.operators["苍苔"]
    operator._mood_model = model
    operator._mood_conf = config.conf
    model.observe(operator.name, 13)
    task = SchedulerTask(
        time=datetime(2026, 10, 1, 8),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"room_2_2": [operator.name]},
    )
    task.execution_retained = True
    solver.tasks = [task]
    snapshot = record.current_state()
    database = tmp_path / "state.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE saved_state (time TEXT, state BLOB)")
    monkeypatch.setattr(record, "_conn", lambda: sqlite3.connect(database))
    assert record.save_state_to_db(snapshot)
    with sqlite3.connect(database) as connection:
        raw = connection.execute("SELECT state FROM saved_state").fetchone()[0]

    class PreviousVersionUnpickler(pickle.Unpickler):
        def find_class(self, module, name):
            assert module != "arknights_mower.utils.calculated_mood"
            return super().find_class(module, name)

    saved = PreviousVersionUnpickler(io.BytesIO(raw)).load()
    assert saved["calculated_mood"]["moods"][operator.name] == 13
    assert saved["tasks"][0].retains_execution
    assert saved["tasks"][0].time == task.time
    assert "_mood_model" not in vars(saved["operators"][operator.name])
    assert "_mood_conf" not in vars(saved["operators"][operator.name])
    assert operator._mood_model is model
    assert snapshot["operators"] is solver.op_data.operators
    restored = load(saved)
    assert restored.mood_model.moods[operator.name] == 13
    assert restored.operators[operator.name]._mood_model is restored.mood_model


@pytest.mark.parametrize("rescue", [False, True])
def test_calculated_resume_defers_training_observation_until_base_dispatch(
    resume, monkeypatch, rescue
):
    from arknights_mower import __main__ as main
    from arknights_mower.utils import mastery_db

    solver, load = resume
    monkeypatch.setattr(config.conf, "test_mood_calculation", True)
    monkeypatch.setattr(config.conf, "automatic_rescue_enable", rescue)
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(mastery_db, "get_reconcile_plans", lambda: [{"id": 1}])
    saved = pickle.loads(pickle.dumps(record.current_state()))
    load(saved)
    running = main.base_scheduler
    running._read_agent_mood.assert_not_called()
    assert running._state_restore_complete is True
    assert running._emergency_startup_pending is True
    assert "train" in running._initial_mood_refresh_rooms
