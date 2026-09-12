"""两种选人模式的兼容性、等待预算与平台默认值。"""

from importlib import import_module
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import AgentSelectionNotReady, BaseMixin
from arknights_mower.tests.agent_page_observation_tests import page, solver_for
from arknights_mower.tests.agent_selection_settle_tests import sort_reader
from arknights_mower.tests.selection_filter_reset_tests import configure_real_filter
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf, RIICPart
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.solver import BaseSolver

conf_module = import_module("arknights_mower.utils.config.conf")


@pytest.mark.parametrize("platform", ["android", "linux", "windows", "darwin"])
def test_platform_default_only_applies_to_missing_setting(monkeypatch, platform):
    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    monkeypatch.setattr(conf_module, "__system__", platform)
    conf = Conf()
    assert conf.low_frame_rate_mode is (platform == "android")
    assert "low_frame_rate_mode" not in conf.model_dump(exclude_unset=True)
    for enabled in (False, True):
        explicit = Conf(low_frame_rate_mode=enabled)
        restored = Conf(**explicit.model_dump(exclude_unset=True))
        assert restored.low_frame_rate_mode is enabled


def test_android_embedded_runtime_defaults_on_even_when_python_reports_linux(
    monkeypatch,
):
    monkeypatch.setattr(conf_module, "__system__", "linux")
    monkeypatch.setenv("MOWER_ANDROID", "1")
    assert RIICPart().low_frame_rate_mode
    assert not RIICPart(low_frame_rate_mode=False).low_frame_rate_mode


@pytest.mark.parametrize("enabled", [False, True])
def test_unknown_bystander_does_not_block_known_target(monkeypatch, enabled):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    solver = solver_for(monkeypatch, [page(("砾", ""))] * 6)
    assert solver.scan_agent(["砾"])[0] == ["砾"]
    solver.tap.assert_called_once()
    assert solver.recog.captures == (2 if enabled else 1)


@pytest.mark.parametrize("enabled", [False, True])
def test_unknown_selected_name_still_cannot_pass_final_verification(
    monkeypatch, enabled
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    solver = solver_for(monkeypatch, [page(("砾", ""))] * 6)
    with pytest.raises(AgentSelectionNotReady):
        solver.verify_agent(["砾", "芬"], "room_1_1")
    solver.tap.assert_not_called()


@pytest.mark.parametrize("enabled", [False, True])
def test_same_page_batch_has_no_added_waits_when_disabled(monkeypatch, enabled):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    names = ["砾", "芬", "杜林"]
    solver = solver_for(monkeypatch, [page(names)] * 6)
    solver.device = MagicMock()
    solver.get_pos = BaseSolver.get_pos
    solver.tap = BaseSolver.tap.__get__(solver)
    assert solver.scan_agent(names.copy())[0] == names
    assert solver.recog.captures == (6 if enabled else 1)
    assert solver.device.tap.call_count == 3
    waits = sum(call.args[0] for call in solver.sleep.call_args_list)
    assert waits == pytest.approx(2.1 if enabled else 0)


@pytest.mark.parametrize("enabled", [False, True])
def test_sort_does_not_wait_for_second_frame_when_disabled(monkeypatch, enabled):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    desired = ("技能", False)
    frames = [("心情", True), desired, desired] if enabled else [desired]
    solver = sort_reader(frames)
    solver.switch_arrange_order("技能", "room_1_1")
    solver.tap.assert_called_once_with((1210, 60), interval=0.5)
    assert solver.sleep.call_count == (1 if enabled else 0)


def test_disabled_reset_without_scroll_neither_taps_nor_captures(monkeypatch):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", False)
    solver = BaseMixin()
    solver.find = MagicMock(side_effect=AssertionError("无需截图"))
    solver.profession_filter = MagicMock(side_effect=AssertionError("无需切筛选"))
    solver.swipe_noinertia = MagicMock(side_effect=AssertionError("无需拖动"))
    assert solver.swipe_left(0, "ALL") == 0
    assert solver.swipe_left(0, "ALL", return_page=True) == (0, None)


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("opened", [False, True])
@pytest.mark.parametrize("train", [False, True])
@pytest.mark.parametrize("profession", ["ALL", "MEDIC"])
def test_already_all_filter_skips_redundant_input(
    monkeypatch, enabled, opened, train, profession
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    solver = solver_for(monkeypatch, [page()] * 10)
    state = configure_real_filter(solver, monkeypatch, opened=opened, train=train)
    solver.profession_filter(profession)
    taps = [c.args[0] for c in solver.device.tap.call_args_list]
    assert (1918, 135) not in taps
    assert state["label"] == profession and state["opened"]
    assert taps.count((1860, 60)) == (0 if opened else 1)
    assert taps.count((1918, 795)) == (1 if profession == "MEDIC" else 0)
    # ALL 已高亮时，不增加标签点击及对应等待。
    assert sum(c.args[0] for c in solver.sleep.call_args_list) == pytest.approx(
        0.1 * len(taps)
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_noop_all_filter_still_obeys_stop(monkeypatch, enabled):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    solver = solver_for(monkeypatch, [page()] * 2)
    configure_real_filter(solver, monkeypatch)
    monkeypatch.setattr(config, "stop_mower", MagicMock(is_set=lambda: True))
    with pytest.raises(MowerExit):
        solver.profession_filter("ALL")
    solver.device.tap.assert_not_called()


@pytest.mark.parametrize("opened,waits", [(False, 0.9), (True, 0.7)])
def test_adapted_filter_reset_uses_explicit_short_tap_intervals(
    monkeypatch, opened, waits
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", True)
    solver = solver_for(monkeypatch, [page()] * 10)
    configure_real_filter(solver, monkeypatch, opened=opened)
    solver.swipe_left(0, "ALL")
    assert sum(c.args[0] for c in solver.sleep.call_args_list) == pytest.approx(waits)


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("profession", ["ALL", "MEDIC"])
def test_filter_reset_still_switches_away_and_back_with_two_label_taps(
    monkeypatch, enabled, profession
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    solver = solver_for(monkeypatch, [page()] * 10)
    state = configure_real_filter(solver, monkeypatch, initial=profession)
    solver.swipe_left(4, profession)
    assert state["changes"] == (
        ["PIONEER", "ALL"] if profession == "ALL" else ["ALL", "MEDIC"]
    )
    assert state["label"] == profession and state["offset"] == 0
    assert solver.device.tap.call_count == 2
    assert sum(c.args[0] for c in solver.sleep.call_args_list) == pytest.approx(
        0.7 if enabled else 0.2
    )


def test_fast_scan_retains_narrow_region_retry(monkeypatch):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", False)
    solver = solver_for(monkeypatch, [page()] * 3)
    read = MagicMock(side_effect=[ValueError("边缘卡片识别失败"), page()])
    monkeypatch.setattr(base_mixin, "operator_list", read)
    assert solver.scan_agent(["砾"])[0] == ["砾"]
    assert [c.kwargs["full_scan"] for c in read.call_args_list] == [True, False]
    solver.tap.assert_called_once()


@pytest.mark.parametrize("enabled", [False, True])
def test_stop_is_checked_by_real_tap_in_both_modes(monkeypatch, enabled):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    solver = solver_for(monkeypatch, [page()] * 6)
    solver.device = MagicMock()
    solver.tap = BaseSolver.tap.__get__(solver)
    monkeypatch.setattr(config, "stop_mower", MagicMock(is_set=lambda: True))
    with pytest.raises(MowerExit):
        solver.scan_agent(["砾"])
    solver.device.tap.assert_not_called()


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("room", ["room_1_1", "dormitory_1", "central"])
def test_verified_roster_does_not_reset_filter_in_either_mode(
    monkeypatch, enabled, room
):
    from arknights_mower.tests.choose_agent_filter_tests import (
        RESIDENTS,
        selection_solver,
    )

    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    solver, selected = selection_solver(monkeypatch, residents=RESIDENTS)
    solver.choose_agent(RESIDENTS.copy(), room)
    assert selected == RESIDENTS
    solver.swipe_left.assert_not_called()
    assert solver.tap.call_count == len(RESIDENTS) + 1
    assert solver.switch_arrange_order.call_count == 2
    assert [c.kwargs["interval"] for c in solver.tap.call_args_list] == [0.5] + [
        0.2 if enabled else 0
    ] * len(RESIDENTS)


@pytest.mark.parametrize("enabled", [False, True])
def test_resting_operator_shortcut_only_runs_with_adaptation_disabled(
    monkeypatch, enabled
):
    from types import SimpleNamespace

    from arknights_mower.tests.choose_agent_filter_tests import selection_solver

    monkeypatch.setattr(config.conf, "low_frame_rate_mode", enabled)
    solver, selected = selection_solver(monkeypatch, residents=[])
    solver.op_data.operators["伊芙利特"] = SimpleNamespace(
        mood=10, upper_limit=24, room="dormitory_1", is_resting=lambda: True
    )
    solver.choose_agent(["伊芙利特"], "dormitory_1")
    assert selected == ["伊芙利特"]
    assert solver.swipe_noinertia.call_count == (0 if enabled else 3)


def test_fast_training_search_stops_at_unchanged_end_page(monkeypatch):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    monkeypatch.setattr(config.conf, "low_frame_rate_mode", False)
    solver = object.__new__(BaseSchedulerSolver)
    solver.profession_filter = MagicMock()
    solver.scan_agent = MagicMock(
        return_value=([], page(("杜林", "芬", "苍苔", "炎熔")))
    )
    solver.swipe_noinertia = MagicMock()
    solver.verify_agent = MagicMock()
    with pytest.raises(AgentSelectionNotReady, match="末尾"):
        solver.choose_train_ope("砾")
    assert solver.swipe_noinertia.call_count == 3
    solver.verify_agent.assert_not_called()


def test_delayed_filter_inputs_are_acknowledged_without_repeated_toggles(monkeypatch):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", True)
    solver = solver_for(monkeypatch, [page()] * 10)
    state = configure_real_filter(solver, monkeypatch, initial="MEDIC", opened=False)
    device_tap = solver.device.tap.side_effect
    clock = [0.0]
    pending = []

    def tap_later(position):
        pending.append((clock[0] + 0.8, position))

    def sleep(interval=1):
        clock[0] += interval
        while pending and pending[0][0] <= clock[0]:
            device_tap(pending.pop(0)[1])
        solver.recog.update()

    solver.device.tap.side_effect = tap_later
    solver.sleep.side_effect = sleep
    assert solver.swipe_left(0, "MEDIC") == 0
    assert state["label"] == "MEDIC" and not state["opened"]
    assert state["changes"] == ["ALL", "MEDIC"]
    assert not pending
    panel_taps = [
        c for c in solver.device.tap.call_args_list if c.args[0] == (1860, 60)
    ]
    assert len(panel_taps) == 2  # 一次打开、一次关闭；迟到帧不能触发重复开关。


def test_android_user_can_save_disabled_mode_and_reload_after_restart(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    monkeypatch.setattr(conf_module, "__system__", "android")
    monkeypatch.setattr(config, "conf_path", tmp_path / "conf.yml")
    monkeypatch.setattr(config, "conf", Conf(low_frame_rate_mode=False))
    config.save_conf()
    assert "low_frame_rate_mode: false" in config.conf_path.read_text()
    config.conf = Conf()  # 模拟重启前重新构造默认配置。
    assert config.conf.low_frame_rate_mode
    config.load_conf()
    assert not config.conf.low_frame_rate_mode
