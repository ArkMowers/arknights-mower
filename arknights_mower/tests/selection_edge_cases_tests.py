"""筛选迟到高亮与无关卡片异常的真实调用路径回归。"""

import hashlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import AgentSelectionNotReady, BaseMixin
from arknights_mower.tests.agent_page_observation_tests import page, solver_for
from arknights_mower.tests.character_name_roi_tests import name_frame
from arknights_mower.tests.selection_filter_reset_tests import configure_real_filter
from arknights_mower.utils import character_recognize as recognition
from arknights_mower.utils import config


@pytest.mark.parametrize("enabled,delay", [(False, 0.2), (False, 0.8), (True, 0.8)])
@pytest.mark.parametrize("opened", [False, True])
def test_same_profession_waits_for_all_then_restores_without_repeated_inputs(
    monkeypatch, enabled, delay, opened
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    solver = solver_for(monkeypatch, [page()] * 10)
    state = configure_real_filter(solver, monkeypatch, initial="MEDIC", opened=opened)
    apply_tap = solver.device.tap.side_effect
    clock = [0.0]
    pending = []

    def sleep(interval=1):
        clock[0] += interval
        while pending and pending[0][0] <= clock[0] + 1e-8:
            apply_tap(pending.pop(0)[1])
        solver.recog.update()

    solver.device.tap.side_effect = lambda pos: pending.append((clock[0] + delay, pos))
    solver.sleep.side_effect = sleep
    solver.profession_filter("MEDIC")
    assert state["changes"] == ["ALL", "MEDIC"]
    assert state["label"] == "MEDIC" and state["opened"]
    assert not pending  # 返回后不能还有一个迟到的 ALL 将筛选改回去。
    solver._close_profession_filter()
    assert not state["opened"] and not pending
    taps = [c.args[0] for c in solver.device.tap.call_args_list]
    assert taps.count((1860, 60)) == (1 if opened else 2)
    assert taps.count((1918, 135)) == 1
    assert taps.count((1918, 795)) == 1


@pytest.mark.parametrize("enabled", [False, True])
def test_immediate_filter_feedback_needs_no_poll_waits(monkeypatch, enabled):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    solver = solver_for(monkeypatch, [page()] * 10)
    configure_real_filter(solver, monkeypatch, initial="MEDIC", opened=True)
    solver.profession_filter("MEDIC")
    assert [c.args[0] for c in solver.sleep.call_args_list] == [0.1, 0.1]


@pytest.mark.parametrize("enabled", [False, True])
def test_unacknowledged_all_prevents_target_click_and_times_out(monkeypatch, enabled):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    solver = solver_for(monkeypatch, [page()] * 10)
    configure_real_filter(solver, monkeypatch, initial="MEDIC", opened=True)
    solver.device.tap.side_effect = None  # 输入未生效，MEDIC 一直高亮。
    with pytest.raises(AgentSelectionNotReady, match="职业筛选尚未生效"):
        solver.profession_filter("MEDIC")
    solver.device.tap.assert_called_once_with((1918, 135))
    assert sum(c.args[0] for c in solver.sleep.call_args_list) == pytest.approx(2.6)


@pytest.fixture(params=["empty", "oversized"])
def damaged_name_frame(monkeypatch, request):
    # 保留实际分割、阈值及轮廓代码；仅模板匹配用像素指纹，避免依赖合成名字的内容。
    monkeypatch.setattr(
        recognition,
        "_match_name_template",
        lambda train, shape, pixels: hashlib.sha256(pixels).hexdigest(),
    )
    frame = name_frame(1)
    healthy = recognition.operator_list(frame)
    if request.param == "empty":
        frame[909:941, 1712:1903] = 0
    else:
        frame[519, 1712:1915] = 0
        frame[909:941, 1712:1915] = 255
    return frame, healthy


def test_damaged_card_keeps_coordinates_and_other_names(damaged_name_frame):
    frame, healthy = damaged_name_frame
    actual = recognition.operator_list(frame)
    assert len(actual) == len(healthy) == 12
    assert actual[:10] == healthy[:10]
    assert actual[-1][0] == ""
    assert actual[-1][1] is not None


@pytest.mark.parametrize("enabled", [False, True])
def test_damaged_bystander_does_not_block_real_page_selection(
    monkeypatch, damaged_name_frame, enabled
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    frame, healthy = damaged_name_frame
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=None)
    solver.sleep = MagicMock()
    solver.tap = MagicMock()
    read = MagicMock(wraps=recognition.operator_list)
    monkeypatch.setattr(base_mixin, "operator_list", read)
    target = healthy[0][0]
    selected, actual = solver.scan_agent([target])
    assert selected == [target]
    solver.tap.assert_called_once_with(healthy[0][1], interval=0.2 if enabled else 0)
    assert len(actual) == 12 and actual[-1][0] == ""
    assert all(c.kwargs["full_scan"] for c in read.call_args_list)
    solver.tap.reset_mock()
    with pytest.raises(AgentSelectionNotReady):
        solver.verify_agent([n for n, _ in healthy], "room_1_1")
    solver.tap.assert_not_called()
