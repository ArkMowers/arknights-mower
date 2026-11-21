from collections import defaultdict, deque
from types import SimpleNamespace

import pytest

from arknights_mower.utils import operation_timing as timing


def test_nested_steps_report_exclusive_time_without_double_counting(monkeypatch):
    clock = iter([0, 1, 2, 5, 7, 9])
    monkeypatch.setattr(timing, "perf_counter", lambda: next(clock))
    measure = timing.OperationTiming()
    outer = measure.enter("selection")
    inner = measure.enter("capture")
    measure.leave(inner)
    measure.leave(outer)
    report = measure.report("room_1_1", "returned")
    assert report["total_s"] == 9
    assert report["steps"]["selection"] == {"count": 1, "total_s": 6, "own_s": 3}
    assert report["steps"]["capture"]["own_s"] == 3
    assert report["other_s"] == 3


def test_error_closes_step_and_clears_room_context(monkeypatch):
    from arknights_mower.utils.log import logger

    reports = []
    monkeypatch.setattr(logger, "debug", reports.append)

    @timing.timed_step("names")
    def fail():
        timing.record_selection_retry()
        raise ValueError("test")

    @timing.timed_room
    def run(room):
        fail()

    with pytest.raises(ValueError):
        run("dormitory_1")
    assert timing._current.get() is None
    assert '"retries": 1' in reports[0]
    assert '"outcome": "ValueError"' in reports[0]
    assert '"names"' in reports[0]


def test_steps_outside_room_do_not_create_profiles():
    @timing.timed_step("names")
    def value():
        return 42

    assert value() == 42
    assert timing._current.get() is None


@pytest.mark.parametrize(
    "task_type", ["RUN_ORDER", "FIAMMETTA", "WORKSHOP", "SKILL_UPGRADE", "SWAP_SUPPORT"]
)
def test_specialized_room_operations_do_not_inflate_ordinary_budget(
    monkeypatch, task_type
):
    monkeypatch.setattr(timing, "_work_durations", defaultdict(lambda: deque(maxlen=8)))
    ticks = iter([0, 180, 180, 200])
    monkeypatch.setattr(timing, "perf_counter", lambda: next(ticks))

    @timing.timed_room
    def arrange(self, room):
        return {}

    solver = SimpleNamespace(task=SimpleNamespace(type=SimpleNamespace(name=task_type)))
    arrange(solver, "room_1_1")
    assert timing.estimate_work_minutes("room_1_1") * 60 == 45
    solver.task.type.name = "SHIFT_ON"
    arrange(solver, "room_1_1")
    assert list(timing._work_durations["room_1_1"]) == [20]
    assert timing.estimate_work_minutes("room_1_1") * 60 == 45


def test_full_recovery_history_does_not_inflate_ordinary_dorm_budget(monkeypatch):
    monkeypatch.setattr(timing, "_dorm_durations", defaultdict(lambda: deque(maxlen=8)))
    ticks = iter([0, 100, 100, 130])
    monkeypatch.setattr(timing, "perf_counter", lambda: next(ticks))

    @timing.timed_room
    def arrange(room, *, single_recovery=False):
        if single_recovery:
            timing.record_dorm_recovery()

    arrange("dormitory_1", single_recovery=True)
    arrange("dormitory_1")
    assert timing.estimate_dorm_minutes("dormitory_1") * 60 == 60
    assert timing.estimate_dorm_minutes("dormitory_1", single_recovery=True) * 60 == 135


@pytest.mark.parametrize("result", [None, False])
def test_unfinished_room_does_not_update_history(monkeypatch, result):
    monkeypatch.setattr(timing, "_work_durations", defaultdict(lambda: deque(maxlen=8)))
    ticks = iter([0, 180])
    monkeypatch.setattr(timing, "perf_counter", lambda: next(ticks))

    @timing.timed_room
    def arrange(self, room):
        return result

    solver = SimpleNamespace(
        task=SimpleNamespace(type=SimpleNamespace(name="SHIFT_ON"))
    )
    arrange(solver, "room_1_1")
    assert timing.estimate_work_minutes("room_1_1") * 60 == 45


def test_nested_room_call_records_once_and_retains_only_eight_samples(monkeypatch):
    monkeypatch.setattr(timing, "_dorm_durations", defaultdict(lambda: deque(maxlen=8)))
    ticks = iter(range(20))
    monkeypatch.setattr(timing, "perf_counter", lambda: next(ticks))

    @timing.timed_room
    def inner(room):
        timing.record_dorm_recovery()

    @timing.timed_room
    def outer(room):
        inner(room)

    for _ in range(10):
        outer("dormitory_1")
    assert list(timing._dorm_durations[("dormitory_1", True)]) == [1] * 8
    assert ("dormitory_1", False) not in timing._dorm_durations
