"""稳定页面只作为上一帧证据，复用时仍实际采集并检查当前画面。"""

import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin  # noqa: E402
from arknights_mower.solvers.base_mixin import BaseMixin  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.solver import BaseSolver  # noqa: E402

pytestmark = pytest.mark.usefixtures("low_frame_rate")


def page(names=("砾", "苍苔", "杜林", "芬"), offset=0):
    return tuple(
        (
            name,
            (
                (630 + i // 2 * 215 + offset, 488 + i % 2 * 421),
                (818 + i // 2 * 215 + offset, 520 + i % 2 * 421),
            ),
        )
        for i, name in enumerate(names)
    )


class LazyRecognizer:
    def __init__(self, frames):
        self.frames = iter(frames)
        self._img = None
        self.captures = 0

    def update(self):
        self._img = None

    @property
    def img(self):
        if self._img is None:
            # 每次采样都返回独立对象；update 本身没有采样。
            self._img = list(next(self.frames))
            self.captures += 1
        return self._img


def solver_for(monkeypatch, frames):
    solver = BaseMixin()
    solver.recog = LazyRecognizer(frames)
    solver.find = MagicMock(side_effect=lambda *args: bool(solver.recog.img) and False)
    solver.tap = MagicMock(side_effect=lambda *args, **kwargs: solver.recog.update())
    solver.sleep = MagicMock(side_effect=lambda *args, **kwargs: solver.recog.update())
    solver.swipe_noinertia = MagicMock(
        side_effect=lambda *args, **kwargs: solver.recog.update()
    )
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: img)
    monkeypatch.setattr(base_mixin, "operator_list_train", lambda img: img)
    return solver


@pytest.mark.parametrize(
    "train,full_scan", [(False, True), (False, False), (True, True)]
)
def test_swipe_result_needs_one_fresh_frame_before_selecting(
    monkeypatch, train, full_scan
):
    before, after = page(("杜林", "芬", "香草", "炎熔")), page()
    solver = solver_for(monkeypatch, [after] * 3)
    moved, observed = solver.swipe_agent_page(
        before, ["砾"], train=train, full_scan=full_scan, return_page=True
    )
    assert moved == 1 and solver.recog.captures == 2
    assert solver.scan_agent(
        ["砾"], train=train, full_scan=full_scan, observation=observed
    )[0] == ["砾"]
    assert solver.recog.captures == 3
    solver.tap.assert_called_once_with(after[0][1], interval=0.2)
    assert observed.image is None and not observed.page


def observe(solver, **kwargs):
    stable = solver.wait_for_agent_page(**kwargs)
    return solver.observe_agent_page(stable, **kwargs)


def test_changed_coordinates_need_another_fresh_frame(monkeypatch):
    moved = page(offset=90)
    solver = solver_for(monkeypatch, [page(), page(), moved, moved])
    observed = observe(solver)
    solver.scan_agent(["砾"], observation=observed)
    assert solver.recog.captures == 4
    solver.tap.assert_called_once_with(moved[0][1], interval=0.2)


def test_changed_names_do_not_click_previous_target(monkeypatch):
    other = page(("香草", "炎熔", "杜林", "芬"))
    solver = solver_for(monkeypatch, [page(), page(), other, other])
    observed = observe(solver)
    assert solver.scan_agent(["砾"], observation=observed)[0] == []
    solver.tap.assert_not_called()
    assert solver.recog.captures == 4


@pytest.mark.parametrize(
    "invalidation", ["input", "layout", "training", "recognizer", "reused"]
)
def test_invalid_observation_falls_back_to_full_wait(monkeypatch, invalidation):
    solver = solver_for(monkeypatch, [page()] * 6)
    observed = observe(solver)
    kwargs = {}
    if invalidation == "input":
        solver.tap((100, 100))
    elif invalidation == "layout":
        kwargs["full_scan"] = False
    elif invalidation == "training":
        kwargs["train"] = True
    elif invalidation == "recognizer":
        observed.recognizer = object()
    else:
        assert observed.consume(solver.recog, full_scan=True, train=False)
    solver.wait_for_agent_page(observation=observed, **kwargs)
    assert solver.recog.captures == 4
    assert observed.consume(solver.recog, full_scan=True, train=False) is None


def test_connecting_breaks_seed_continuity(monkeypatch):
    solver = solver_for(monkeypatch, [page()] * 5)
    observed = observe(solver)
    overlays = iter([True, False, False])
    solver.find.side_effect = lambda *args: bool(solver.recog.img) and next(overlays)
    solver.wait_for_agent_page(observation=observed)
    assert solver.recog.captures == 5


def test_filter_reset_seeds_verification_but_requires_fresh_frame(monkeypatch):
    targets = ["苍苔", "砾"]
    solver = solver_for(monkeypatch, [page()] * 4)
    solver.profession_filter = MagicMock(side_effect=lambda *_: solver.recog.update())
    count, observed = solver.swipe_left(0, "ALL", return_page=True)
    # 入口面板状态读取一帧，切筛选后仍完整读取两帧，不复用入口旧图。
    assert count == 0 and solver.recog.captures == 3
    assert [call.args[0] for call in solver.profession_filter.call_args_list] == [
        "PIONEER",
        "ALL",
    ]
    solver.swipe_noinertia.assert_not_called()
    assert solver.wait_for_arranged_agents(
        targets, ordered=False, observation=observed
    ) == ["砾", "苍苔"]
    assert solver.recog.captures == 4
    assert observed.image is None


def test_final_verification_keeps_order_requirement(monkeypatch):
    solver = solver_for(monkeypatch, [page()] * 8)
    observed = observe(solver)
    assert not solver.verify_agent(["苍苔", "砾"], "room_1_1", observation=observed)
    assert solver.recog.captures == 8
    solver.tap.assert_not_called()


def test_clipped_new_frame_does_not_pass_verification(monkeypatch):
    solver = solver_for(monkeypatch, [page()] * 2 + [page(offset=160), page(), page()])
    observed = observe(solver)
    assert solver.wait_for_arranged_agents(["砾", "苍苔"], observation=observed) == [
        "砾",
        "苍苔",
    ]
    assert solver.recog.captures == 5


def test_next_target_after_input_is_located_again(monkeypatch):
    moved = page(("杜林", "芬", "苍苔", "砾"))
    solver = solver_for(monkeypatch, [page()] * 3 + [moved] * 2)
    observed = observe(solver)
    assert solver.scan_agent(["砾", "苍苔"], observation=observed)[0] == ["砾", "苍苔"]
    assert [call.args[0] for call in solver.tap.call_args_list] == [
        page()[0][1],
        moved[2][1],
    ]
    assert solver.recog.captures == 5


def test_stop_still_checked_before_consumers_fresh_frame(monkeypatch):
    solver = solver_for(monkeypatch, [page()] * 2)
    observed = observe(solver)
    solver.recog.update = MagicMock(side_effect=MowerExit)
    with pytest.raises(MowerExit):
        solver.scan_agent(["砾"], observation=observed)
    assert observed.image is None
    solver.tap.assert_not_called()
    assert solver.recog.captures == 2


def test_observation_copies_page_coordinates(monkeypatch):
    solver = solver_for(monkeypatch, [page()])
    mutable = [["砾", [[630, 488], [818, 520]]]]
    solver.recog.img
    observed = solver.observe_agent_page(mutable)
    mutable[0][1][0][0] = 999
    assert (
        observed.consume(solver.recog, full_scan=True, train=False)[0][1][0][0] == 630
    )


@pytest.mark.parametrize("interval", [0, -0.1])
def test_real_swipe_without_wait_invalidates_seed_without_capture(
    monkeypatch, interval
):
    solver = solver_for(monkeypatch, [page()] * 3)
    observed = observe(solver)
    solver.device = MagicMock()
    monkeypatch.setattr(config, "stop_mower", MagicMock(is_set=lambda: False))
    solver.sleep.reset_mock()

    BaseSolver.swipe_noinertia(solver, (650, 540), (500, 0), interval=interval)

    solver.device.swipe_ext.assert_called_once()
    solver.sleep.assert_not_called()
    assert solver.recog._img is None
    assert solver.recog.captures == 2
    assert observed.consume(solver.recog, full_scan=True, train=False) is None
    solver.recog.img
    assert solver.recog.captures == 3


def test_real_swipe_stop_before_input_does_not_capture_or_wait(monkeypatch):
    solver = solver_for(monkeypatch, [page()] * 2)
    observe(solver)
    image = solver.recog._img
    solver.device = MagicMock()
    monkeypatch.setattr(config, "stop_mower", MagicMock(is_set=lambda: True))
    solver.sleep.reset_mock()

    with pytest.raises(MowerExit):
        BaseSolver.swipe_noinertia(solver, (650, 540), (500, 0), interval=0)

    solver.device.swipe_ext.assert_not_called()
    solver.sleep.assert_not_called()
    assert solver.recog._img is image
    assert solver.recog.captures == 2


def test_real_swipe_propagates_input_stop_without_wait(monkeypatch):
    solver = solver_for(monkeypatch, [page()] * 2)
    observe(solver)
    solver.device = MagicMock()
    solver.device.swipe_ext.side_effect = MowerExit
    monkeypatch.setattr(config, "stop_mower", MagicMock(is_set=lambda: False))
    solver.sleep.reset_mock()

    with pytest.raises(MowerExit):
        BaseSolver.swipe_noinertia(solver, (650, 540), (500, 0), interval=0)

    solver.device.swipe_ext.assert_called_once()
    solver.sleep.assert_not_called()
    assert solver.recog.captures == 2


def test_empty_verification_still_consumes_observation(monkeypatch):
    solver = solver_for(monkeypatch, [page()] * 2)
    observed = observe(solver)
    assert solver.wait_for_arranged_agents([], observation=observed) == []
    assert observed.image is None
    assert solver.recog.captures == 2
