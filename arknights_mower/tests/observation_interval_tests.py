"""慢截图计入采样间隔；仍需独立的新帧，连接遮罩仍打断稳定证据。"""

from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.tests.agent_page_observation_tests import page, solver_for
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.solver import BaseSolver

pytestmark = pytest.mark.usefixtures("low_frame_rate")


@pytest.mark.parametrize("duration,wait", [(0.1, 0.4), (0.5, 0), (1.6, 0)])
@pytest.mark.parametrize("verify", [False, True])
def test_capture_cost_is_included_in_sampling_interval(
    monkeypatch, duration, wait, verify
):
    clock = [0.0]
    monkeypatch.setattr(base_mixin, "perf_counter", lambda: clock[0])
    solver = solver_for(monkeypatch, [page()] * 2)

    def find(*args):
        solver.recog.img
        clock[0] += duration
        return False

    def sleep(seconds):
        clock[0] += seconds
        solver.recog.update()

    solver.find.side_effect = find
    solver.sleep.side_effect = sleep
    if verify:
        assert solver.wait_for_arranged_agents(["砾"]) == ["砾"]
    else:
        assert solver.wait_for_agent_page() == list(page())
    assert solver.recog.captures == 2
    assert solver.sleep.call_args.args[0] == pytest.approx(wait)
    assert clock[0] == pytest.approx(2 * duration + wait)


@pytest.mark.parametrize("duration,wait", [(0.1, 0.4), (1.6, 0)])
def test_sorting_still_requires_changed_and_stable_arrows(monkeypatch, duration, wait):
    clock = [0.0]
    monkeypatch.setattr(base_mixin, "perf_counter", lambda: clock[0])
    solver = BaseMixin()
    solver.recog = MagicMock()
    states = iter([("技能", False), ("心情", True), ("心情", True)])

    def detect(room):
        clock[0] += duration
        return next(states)

    solver.detect_arrange_order = MagicMock(side_effect=detect)
    solver.tap = MagicMock()
    solver.sleep = MagicMock()
    solver.switch_arrange_order("心情", "dormitory_1", True)
    assert solver.detect_arrange_order.call_count == 3
    assert solver.tap.call_count == 1
    assert solver.sleep.call_args.args[0] == pytest.approx(wait)


def test_zero_remaining_wait_still_honors_stop(monkeypatch):
    monkeypatch.setattr(base_mixin, "perf_counter", lambda: 2.0)
    solver = BaseMixin()
    solver.recog = MagicMock()
    solver.sleep = BaseSolver.sleep.__get__(solver)
    monkeypatch.setattr(base_mixin.config.stop_mower, "is_set", lambda: True)
    with pytest.raises(MowerExit):
        solver.wait_for_next_observation(2)
    solver.recog.update.assert_not_called()
