"""职业筛选在丢失输入后恢复，等待过程保留有限预算与停止语义。"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import AgentSelectionNotReady, BaseMixin
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.solver import BaseSolver

pytestmark = pytest.mark.usefixtures("legacy_selection_conf")


@pytest.fixture(autouse=True)
def isolated_operation_feedback(monkeypatch):
    monkeypatch.setattr(config, "operation_feedback_avg", None)
    monkeypatch.setattr(config, "operation_feedback_count", 0)


@pytest.fixture
def scheduler_selection(monkeypatch):
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower.tests.choose_agent_filter_tests import selection_solver

    return selection_solver


class FilterPanel:
    """只模拟设备输入、确认按钮坐标、职业颜色和时间。"""

    def __init__(
        self,
        *,
        train=False,
        opened=False,
        lost_taps=(),
        animation_duration=0,
        moving=False,
    ):
        self.train = train
        self.opened = opened
        self.label = "MEDIC"
        self.lost_taps = lost_taps
        self.now = 0.0
        self.panel_taps = []
        self.label_taps = []
        self.stop_at = float("inf")
        self.animation_duration = animation_duration
        self.moving = moving
        self.animation_start = None

    def sleep(self, interval):
        if self.now + interval >= self.stop_at:
            self.now = self.stop_at
            raise MowerExit
        self.now += interval
        if (
            self.animation_start is not None
            and self.now - self.animation_start >= self.animation_duration
        ):
            self.opened = not self.opened
            self.animation_start = None

    def find(self, name):
        if name != ("confirm_train" if self.train else "confirm_blue"):
            return None
        x = (
            (1554 if self.opened else 1669)
            if self.train
            else (1609 if self.opened else 1724)
        )
        if self.animation_start is not None and self.moving:
            progress = (self.now - self.animation_start) / self.animation_duration
            x += (1 if self.opened else -1) * int(10 * progress)
        return ((x, 50), (x + 40, 90))

    def tap(self, position):
        if position == (1860, 60):
            self.panel_taps.append(self.now)
            if len(self.panel_taps) not in self.lost_taps:
                assert self.animation_start is None, "动画期间不得追加侧栏切换输入"
                if self.animation_duration:
                    self.animation_start = self.now
                else:
                    self.opened = not self.opened
            return
        assert self.opened, "职业点击必须等侧栏打开后发出"
        assert position == (1918, 135)
        self.label_taps.append(position)
        self.label = "ALL"

    def color(self, position):
        assert self.opened, "职业颜色只在已打开的侧栏读取"
        assert position == (1918, 135)
        return 0, 0, 255 if self.label == "ALL" else 0


def filter_solver(monkeypatch, *, solver=None, **panel_options):
    panel = FilterPanel(**panel_options)
    solver = BaseMixin() if solver is None else solver
    solver.device = SimpleNamespace(tap=MagicMock(side_effect=panel.tap))
    solver.tap = BaseSolver.tap.__get__(solver)
    solver.get_pos = BaseSolver.get_pos
    solver.sleep = panel.sleep
    solver.find = panel.find
    solver.get_color = panel.color
    monkeypatch.setattr(base_mixin, "perf_counter", lambda: panel.now)
    monkeypatch.setattr(config.conf, "selection_poll_interval", 0.1)
    monkeypatch.setattr(config.conf, "selection_transition_timeout", 2.5)
    monkeypatch.setattr(
        config,
        "stop_mower",
        SimpleNamespace(is_set=lambda: panel.now >= panel.stop_at),
    )
    return solver, panel


def test_choose_agent_recovers_lost_close_before_reordering_roster(
    monkeypatch, scheduler_selection
):
    targets = ["冰酿", "闪灵", "菲亚梅塔", "爱丽丝"]
    solver, selected = scheduler_selection(monkeypatch, residents=targets)
    select_card = solver.tap
    solver, panel = filter_solver(
        monkeypatch, solver=solver, opened=True, lost_taps=(1,)
    )
    solver.profession_filter = BaseMixin.profession_filter.__get__(solver)

    def tap(position):
        if position == (1860, 60) or position[0] == 1918:
            panel.tap(position)
        else:
            assert not panel.opened and panel.label == "ALL"
            select_card(position)

    solver.device.tap.side_effect = tap

    solver.choose_agent(targets.copy(), "dormitory_1")

    assert selected == targets
    assert solver.last_room == "dormitory_1"
    assert panel.label == "ALL" and not panel.opened
    assert panel.panel_taps[1] - panel.panel_taps[0] >= 1.0
    assert select_card.call_count == len(targets) + 1


def test_choose_train_ope_recovers_lost_close_before_selecting_free_operator(
    monkeypatch, scheduler_selection
):
    solver, selected = scheduler_selection(monkeypatch, residents=[])
    scan_cards = solver.scan_agent.side_effect
    solver, panel = filter_solver(
        monkeypatch, solver=solver, train=True, opened=True, lost_taps=(1,)
    )
    solver.profession_filter = BaseMixin.profession_filter.__get__(solver)

    def scan(*args, **kwargs):
        assert not panel.opened and panel.label == "ALL"
        return scan_cards(*args, **kwargs)

    solver.scan_agent.side_effect = scan
    solver.ctap = MagicMock()
    solver.verify_agent = MagicMock(
        side_effect=lambda expected, *args, **kwargs: expected == selected
    )

    solver.choose_train_ope("Free")

    assert selected == ["伊芙利特"]
    assert solver.last_room == "train"
    assert panel.label == "ALL" and not panel.opened
    assert len(panel.panel_taps) == 2
    assert panel.panel_taps[1] - panel.panel_taps[0] >= 1.0
    solver.verify_agent.assert_called_once_with(["伊芙利特"], "train", train=True)


@pytest.mark.parametrize("train", [False, True])
@pytest.mark.parametrize("opened", [False, True])
@pytest.mark.parametrize("poll_interval", [0.1, 0.5])
def test_lost_first_panel_input_restores_all_and_closes(
    monkeypatch, train, opened, poll_interval
):
    solver, panel = filter_solver(
        monkeypatch, train=train, opened=opened, lost_taps=(1,)
    )
    monkeypatch.setattr(config.conf, "selection_poll_interval", poll_interval)

    solver.profession_filter()

    assert panel.label == "ALL"
    assert panel.opened is False
    assert len(panel.panel_taps) == (2 if opened else 3)
    assert panel.panel_taps[1] - panel.panel_taps[0] >= max(1.0, poll_interval * 3)


@pytest.mark.parametrize("train", [False, True])
@pytest.mark.parametrize("animation_duration,moving", [(0.8, False), (1.8, True)])
def test_delayed_panel_feedback_does_not_toggle_again(
    monkeypatch, train, animation_duration, moving
):
    solver, panel = filter_solver(
        monkeypatch,
        train=train,
        animation_duration=animation_duration,
        moving=moving,
    )

    solver.profession_filter()

    assert panel.label == "ALL"
    assert panel.opened is False
    assert len(panel.panel_taps) == 2
    assert panel.animation_start is None


@pytest.mark.parametrize("opened", [False, True])
@pytest.mark.parametrize("timeout", [2.5, 6.0])
def test_ignored_inputs_exhaust_existing_budget_with_bounded_taps(
    monkeypatch, opened, timeout
):
    solver, panel = filter_solver(monkeypatch, opened=opened, lost_taps=range(1, 100))
    monkeypatch.setattr(config.conf, "selection_transition_timeout", timeout)
    panel.label = "ALL"

    with pytest.raises(AgentSelectionNotReady, match="职业筛选失败"):
        solver.profession_filter()

    assert panel.opened is opened
    assert 2 <= len(panel.panel_taps) <= 3
    assert all(
        later - earlier >= 1.0
        for earlier, later in zip(panel.panel_taps, panel.panel_taps[1:])
    )
    assert timeout <= round(panel.now, 6) <= timeout + 0.1


@pytest.mark.parametrize("buttons", [(), (1650,), (1609, 1669)])
def test_unreadable_or_conflicting_state_never_authorizes_input(monkeypatch, buttons):
    solver, panel = filter_solver(monkeypatch)
    matches = dict(zip(("confirm_blue", "confirm_train"), buttons))
    solver.find = lambda name: (
        ((matches[name], 50), (matches[name] + 40, 90)) if name in matches else None
    )

    with pytest.raises(AgentSelectionNotReady, match="职业筛选失败"):
        solver.profession_filter()

    solver.device.tap.assert_not_called()
    assert panel.label == "MEDIC"
    assert 2.5 <= round(panel.now, 6) <= 2.6


def test_missing_feedback_restarts_stability_wait_before_retry(monkeypatch):
    solver, panel = filter_solver(monkeypatch, opened=True, lost_taps=(1,))
    panel.label = "ALL"

    def intermittent_button(name):
        if panel.panel_taps and panel.now < 0.4:
            return None
        return panel.find(name)

    solver.find = intermittent_button

    solver.profession_filter()

    assert panel.opened is False
    assert len(panel.panel_taps) == 2
    assert panel.panel_taps[1] >= 1.4


@pytest.mark.parametrize("opened", [False, True])
@pytest.mark.parametrize("stop_at", [0, 0.5])
def test_stop_before_input_or_during_retry_prevents_further_input(
    monkeypatch, opened, stop_at
):
    solver, panel = filter_solver(monkeypatch, opened=opened, lost_taps=(1,))
    panel.label = "ALL"
    panel.stop_at = stop_at

    with pytest.raises(MowerExit):
        solver.profession_filter()

    assert panel.opened is opened
    assert len(panel.panel_taps) == (0 if stop_at == 0 else 1)
    assert all(tapped_at < stop_at for tapped_at in panel.panel_taps)
