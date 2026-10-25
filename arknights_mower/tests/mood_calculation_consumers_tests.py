"""模型心情驱动替班检查、组恢复期限和召回估算。"""

import pickle
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.tests import native_group_recovery_sync_tests as recovery_tests
from arknights_mower.tests import replacement_check_tests as replacement_tests
from arknights_mower.utils import group_recovery, replacement_check
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.recall_estimates import estimated_recall_rates
from arknights_mower.utils.scheduler_task import SchedulerTask, find_next_task

clock = replacement_tests.clock
replacement_solver = replacement_tests.replacement_solver
solver = recovery_tests.solver
resting = recovery_tests.resting


@pytest.fixture
def calculated(monkeypatch):
    monkeypatch.setattr(
        Operators,
        "mood_calculation_enabled",
        property(lambda self: True),
        raising=False,
    )
    monkeypatch.setattr(
        Operators,
        "calculated_mood",
        lambda self, name, now=None: self.test_moods.get(name),
        raising=False,
    )
    monkeypatch.setattr(
        Operators,
        "calculated_mood_deadline",
        lambda self, name, target, now=None: self.test_deadlines.get(name),
        raising=False,
    )


def model_values(data, moods=None, deadlines=None):
    data.test_moods = moods or {}
    data.test_deadlines = deadlines or {}


def set_e0_box(monkeypatch, names):
    from arknights_mower.utils import mastery_recommendation
    from arknights_mower.utils.schedule_roster import _operator_ids_by_name

    ids = _operator_ids_by_name()
    snapshot = {
        "data": {
            "characters": [
                {"id": sorted(ids[name])[0], "evolvePhase": 0, "level": 1}
                for name in names
            ]
        }
    }
    monkeypatch.setattr(
        mastery_recommendation, "get_cultivate_snapshot", lambda: snapshot
    )


def create_check(instance):
    replacement_check.sync_replacement_checks(instance)
    assert len(instance.tasks) == 1
    return instance.tasks[0]


def test_calculated_replacement_deadline_does_not_read_room(
    replacement_solver, clock, calculated
):
    instance = replacement_solver
    # 模型包含中途改变的消耗；旧实测速率不能决定这次期限。
    expected = clock.now() + timedelta(hours=2, minutes=17)
    model_values(instance.op_data, {"薇薇安娜": 18}, {"薇薇安娜": expected})
    task = create_check(instance)
    assert replacement_check.run_replacement_check(instance, task) is False
    assert task.time == task.replacement_check_deadline == expected
    instance.enter_room.assert_not_called()
    instance.get_agent_from_room.assert_not_called()
    assert instance.op_data.operators["薇薇安娜"].mood == 24


@pytest.mark.parametrize("mood", [None, 18])
def test_unknown_calculated_replacement_timing_preserves_failure_and_dispatch(
    replacement_solver, clock, calculated, mood
):
    instance = replacement_solver
    model_values(instance.op_data, {"薇薇安娜": mood})
    task = create_check(instance)
    original_time = task.time
    assert replacement_check.run_replacement_check(instance, task) is False
    failure = task.execution_failure
    unrelated = SchedulerTask(meta_data="独立工作")
    instance.tasks.append(unrelated)
    for _ in range(3):
        clock.current += timedelta(hours=1)
        # 模型推进到下限也不是新的实测或阵容变化。
        instance.op_data.test_moods["薇薇安娜"] = 0
        replacement_check.sync_replacement_checks(instance)
        instance._resume_failed_tasks()
        assert task.execution_failure is failure
        assert task.time == original_time
        assert find_next_task(instance.tasks) is unrelated
        assert sum(queued is task for queued in instance.tasks) == 1
    instance.op_data.room_observations["central"] = 1
    instance._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert task.time == original_time and task.retains_execution
    instance.get_agent_from_room.assert_not_called()


def test_calculated_replacement_lower_limit_uses_existing_matching(
    replacement_solver, calculated
):
    instance = replacement_solver
    model_values(instance.op_data, {"薇薇安娜": 0, "赫默": 20, "歌蕾蒂娅": 2})
    # 旧实读仍为 24；替班检查与实际候补匹配都必须使用模型下限。
    assert instance.op_data.operators["薇薇安娜"].mood == 24
    instance.reading.update(mood=0)
    task = create_check(instance)
    assert replacement_check.run_replacement_check(instance, task) is True
    assert [queued.plan for queued in instance.tasks if queued is not task] == [
        {"central": ["赫默"]}
    ]
    instance.get_agent_from_room.assert_called_once()


def test_calculated_replacement_failure_survives_restart_without_timed_retry(
    replacement_solver, clock, calculated
):
    instance = replacement_solver
    model_values(instance.op_data)
    task = create_check(instance)
    original_time = task.time
    assert replacement_check.run_replacement_check(instance, task) is False
    restored = pickle.loads(pickle.dumps(task))
    instance.tasks = [restored]
    clock.current += timedelta(hours=4)
    instance.op_data.test_moods["薇薇安娜"] = 0
    replacement_check.sync_replacement_checks(instance)
    instance._resume_failed_tasks()
    assert instance.tasks[0] is restored
    assert restored.time == original_time and restored.execution_failure
    assert find_next_task(instance.tasks) is None
    instance.op_data.room_observations["central"] = 1
    instance._resume_failed_tasks()
    assert instance.tasks[0] is restored and restored.time == original_time
    assert not getattr(restored, "execution_failure", None)
    instance.get_agent_from_room.assert_not_called()


def test_calculated_group_return_uses_model_deadline_without_changing_observation(
    resting, calculated
):
    instance, now = resting
    data = instance.op_data
    data.operators["讯使"].rest_in_full = True
    expected = now + timedelta(hours=2, minutes=13)
    model_values(data, {"讯使": 10}, {"讯使": expected})
    old_deadline = data.get_dorm_by_name("讯使")[1].time
    required, deadline = group_recovery.group_recovery_deadline(data, "联动", now=now)
    assert required == ["讯使"]
    assert deadline == expected
    assert data.get_dorm_by_name("讯使")[1].time == old_deadline
    assert data.operators["讯使"].mood == 5


def test_unknown_calculated_recovery_does_not_reuse_old_fullness_or_countdown(
    resting, calculated
):
    instance, now = resting
    data = instance.op_data
    model_values(data)
    operator = data.operators["讯使"]
    operator.mood = 24
    operator.rest_in_full = True
    assert not group_recovery.recovery_mood_complete(data, operator, now)
    assert group_recovery.observed_recovery_deadline(data, operator.name, now) is None
    assert group_recovery.group_recovery_deadline(data, "联动", now=now) == (
        [operator.name],
        None,
    )


def test_calculated_full_recovery_completes_without_promoting_measured_mood(
    resting, calculated
):
    instance, now = resting
    data = instance.op_data
    operator = data.operators["讯使"]
    operator.rest_in_full = True
    model_values(data, {operator.name: 24})
    assert group_recovery.group_recovery_deadline(data, "联动", now=now) == (
        [operator.name],
        now,
    )
    assert operator.mood == 5


def test_calculated_recall_rates_use_admitted_roster_and_preserve_unknown():
    def operator(*, working=False, resting=False):
        return SimpleNamespace(is_working=lambda: working, is_resting=lambda: resting)

    admitted = SimpleNamespace(
        operators={
            "工作": operator(working=True),
            "零消耗": operator(working=True),
            "恢复": operator(resting=True),
            "未知": operator(working=True),
        },
        calculated_mood_rate=Mock(side_effect=[1.5, 0, -3.25, None]),
    )
    original = SimpleNamespace(mood_calculation_enabled=True)
    assert estimated_recall_rates(original, admitted) == (
        {"工作": 1.5, "零消耗": 0},
        {"恢复": 3.25},
    )
    assert admitted.calculated_mood_rate.call_count == 4


def test_real_projection_recall_rates_follow_new_rooms_without_mutating_source(
    replacement_solver, clock, monkeypatch
):
    from arknights_mower.utils import calculated_mood

    monkeypatch.setattr(calculated_mood, "datetime", clock)
    data = replacement_solver.op_data
    data.runtime_conf = SimpleNamespace(test_mood_calculation=True)
    data.global_plan["default_plan"].plan = deepcopy(data.plan)
    set_e0_box(monkeypatch, data.operators)
    now = clock.now()
    for name in data.operators:
        data.mood_model.observe(name, 12, now)
    # 中枢驻员减耗 0.05，薇薇安娜的「金盏花诗会」额外减耗 0.05。
    assert data.calculated_mood_rate("薇薇安娜", now) == pytest.approx(0.9)
    before = deepcopy(vars(data.mood_model))
    admitted = data.project_arrangements(
        [{"central": ["赫默"], "dormitory_1": ["Current", "Current", "薇薇安娜"]}]
    )
    work, recovery = estimated_recall_rates(data, admitted, now)
    assert work["赫默"] == pytest.approx(0.95)
    assert recovery["薇薇安娜"] == pytest.approx(4)
    assert "薇薇安娜" not in work
    assert admitted.mood_model is not data.mood_model
    assert vars(data.mood_model) == before
    assert data.operators["薇薇安娜"].current_room == "central"


def test_calculation_environment_change_replans_check_without_clock_source(
    replacement_solver, clock, calculated
):
    instance = replacement_solver
    expected = clock.now() + timedelta(hours=4)
    model_values(instance.op_data, {"薇薇安娜": 12}, {"薇薇安娜": expected})
    task = create_check(instance)
    assert replacement_check.run_replacement_check(instance, task) is False
    source = deepcopy(task.replacement_check_source)
    clock.current += timedelta(hours=1)
    replacement_check.sync_replacement_checks(instance)
    assert task.replacement_check_source == source and task.time == expected
    instance.op_data.mood_model.stages["薇薇安娜"] = (2, 90)
    next_deadline = clock.now() + timedelta(hours=5)
    instance.op_data.test_deadlines["薇薇安娜"] = next_deadline
    replacement_check.sync_replacement_checks(instance)
    assert task.time == next_deadline
    assert replacement_check.run_replacement_check(instance, task) is False
    assert task.time == next_deadline
    instance.get_agent_from_room.assert_not_called()
