"""普通接续保留实测召回依据，清零启动仍丢弃旧运行记录。"""

import pickle
from datetime import date, datetime
from threading import Event
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import record
from arknights_mower.tests import exhaust_replacement_tests
from arknights_mower.tests.native_replacement_coordination_tests import (
    seed_observed_recall_rates,
)
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.recall_estimates import estimated_recall_rates

solver = exhaust_replacement_tests.solver
pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def resume(solver, monkeypatch):
    import arknights_mower.__main__ as main

    data = solver.op_data
    solver.global_plan["default_plan"].plan["room_2_2"][0].replacement = ["槐琥"]
    data.operators["苍苔"].replacement = ["槐琥"]
    seed_observed_recall_rates(data)
    for name in ("苍苔", "絮雨"):
        data.operators[name].depletion_rate = 0
        data.operators[name].recall_work_rate_checked = True
    data.recall_recovery_rates = {("dormitory_1", "ordinary"): (3.0, datetime.now())}
    solver._state_restore_complete = True
    for field in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, field, date.min)
    solver.task_count = 0
    monkeypatch.setattr(main, "base_scheduler", solver)
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(main, "refresh_resource_at_boundary", lambda: None)

    def load(saved):
        assert solver.initialize_operators() is None
        restored = solver.op_data
        runner = MagicMock()
        runner.op_data = restored
        runner.initialize_operators.return_value = None
        runner.emergency_state = None
        runner.tasks = []
        runner.run.side_effect = MowerExit
        monkeypatch.setattr(main, "initialize", lambda *a, **kw: runner)
        main.simulate(saved)
        runner.run.assert_called_once_with()
        return restored

    return solver, load


def test_resume_preserves_complete_recall_plan_and_isolates_history(resume):
    solver, load = resume
    data = solver.op_data
    expected = {"room_2_2": ["苍苔"], "contact": ["絮雨"]}
    assert solver._plan_exhaust_support(["机械师"]) == expected
    snapshot = record.current_state()
    assert snapshot["recall_recovery_rates"] == data.recall_recovery_rates
    assert snapshot["recall_recovery_rates"] is not data.recall_recovery_rates
    saved = pickle.loads(pickle.dumps(snapshot))
    restored = load(saved)
    assert solver.op_data is not data
    for name in ("苍苔", "絮雨"):
        assert (
            restored.operators[name].recall_work_rate
            == data.operators[name].recall_work_rate
        )
        assert restored.operators[name].recall_work_rate_checked
    assert restored.recall_recovery_rates == saved["recall_recovery_rates"]
    assert restored.recall_recovery_rates is not saved["recall_recovery_rates"]
    assert solver._plan_exhaust_support(["机械师"]) == expected


def test_resume_keeps_rejected_work_sample_from_legacy_fallback(resume):
    solver, load = resume
    op = solver.op_data.operators["能天使"]
    op.recall_work_rate = None
    op.recall_work_rate_checked = True
    op.depletion_rate = 0.5
    saved = pickle.loads(pickle.dumps(record.current_state()))
    restored = load(saved)
    work, _ = estimated_recall_rates(restored, restored)
    assert "能天使" not in work
    assert restored.operators["能天使"].recall_work_rate_checked


@pytest.mark.parametrize("mode", ["legacy", "reset"])
def test_missing_or_reset_history_does_not_invent_estimates(resume, mode):
    solver, load = resume
    saved = pickle.loads(pickle.dumps(record.current_state()))
    if mode == "legacy":
        saved.pop("recall_recovery_rates", None)
        for op in saved["operators"].values():
            for attr in ("recall_work_rate", "recall_work_rate_checked"):
                if hasattr(op, attr):
                    delattr(op, attr)
    else:
        saved = None
    restored = load(saved)
    assert restored.recall_recovery_rates == {}
    for name in ("苍苔", "絮雨"):
        assert getattr(restored.operators[name], "recall_work_rate", None) is None
    if mode == "legacy":
        assert solver._plan_exhaust_support(["机械师"]) is None
