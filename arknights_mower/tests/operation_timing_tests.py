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
    monkeypatch.setattr(logger, "info", reports.append)

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
