from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.utils import config, performance
from arknights_mower.utils.config.conf import Conf, RIICPart
from arknights_mower.utils.device import device as device_module
from arknights_mower.utils.device.device import Device


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("android", "auto"),
        ("windows", "high"),
        ("darwin", "high"),
        ("linux", "high"),
    ],
)
def test_platform_performance_default(monkeypatch, platform, expected):
    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    monkeypatch.setattr(performance, "__system__", platform)
    assert RIICPart().performance_mode == expected


@pytest.mark.parametrize(("legacy", "expected"), [(False, "high"), (True, "medium")])
def test_legacy_boolean_migrates_when_no_timing_is_configured(legacy, expected):
    conf = RIICPart(low_frame_rate_mode=legacy)
    assert conf.performance_mode == expected


def test_existing_timing_keeps_values_without_custom_mode():
    conf = Conf(
        low_frame_rate_mode=False,
        run_order_delay=7.5,
        run_order_grandet_mode={"buffer_time": 22},
    )
    assert conf.performance_mode == "high"
    assert conf.run_order_delay == 7.5
    assert conf.run_order_grandet_mode.buffer_time == 22
    assert not performance.effective_performance_profile(conf).low_frame_rate


def test_existing_screenshot_interval_remains_independent():
    conf = Conf(screenshot_interval=650)
    assert conf.performance_mode == "high"
    assert conf.screenshot_interval == 650


@pytest.mark.parametrize(
    ("average", "expected"),
    [(0, "medium"), (0.34, "medium"), (0.35, "medium"), (1.19, "medium"), (1.2, "low")],
)
def test_auto_selects_profile_from_operation_feedback(monkeypatch, average, expected):
    monkeypatch.setenv("MOWER_ANDROID", "1")
    conf = RIICPart(performance_mode="auto")
    assert performance.effective_performance_profile(conf, average, 8).mode == expected


def test_android_high_and_legacy_fast_mode_use_medium(monkeypatch):
    monkeypatch.setenv("MOWER_ANDROID", "1")
    for settings in (
        {"performance_mode": "high"},
        {"performance_mode": "ultra"},
        {"low_frame_rate_mode": False},
    ):
        conf = RIICPart(**settings)
        assert conf.performance_mode == "medium"
        assert conf.low_frame_rate_mode
        assert performance.effective_performance_profile(conf).mode == "medium"
    direct = SimpleNamespace(performance_mode="high")
    assert performance.effective_performance_profile(direct).mode == "medium"


def test_desktop_auto_can_still_select_high(monkeypatch):
    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    monkeypatch.setattr(performance, "__system__", "darwin")
    conf = RIICPart(performance_mode="auto")
    assert performance.effective_performance_profile(conf, 0, 8).mode == "high"


def test_ultra_is_explicit_only_and_keeps_user_timing(monkeypatch):
    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    monkeypatch.setattr(performance, "__system__", "darwin")
    conf = Conf(performance_mode="ultra", selection_poll_interval=0.8)
    profile = performance.effective_performance_profile(conf, 2, 8)
    assert profile.mode == "ultra"
    assert not profile.low_frame_rate
    assert profile.poll_interval == 0.8
    conf.performance_mode = "auto"
    assert performance.effective_performance_profile(conf, 2, 8).mode == "low"


def test_explicit_auto_ignores_legacy_boolean_override(monkeypatch):
    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    monkeypatch.setattr(performance, "__system__", "darwin")
    monkeypatch.setattr(
        config, "conf", RIICPart(performance_mode="auto", low_frame_rate_mode=True)
    )
    monkeypatch.setattr(config, "operation_feedback_avg", 0)
    monkeypatch.setattr(config, "operation_feedback_count", 8)
    monkeypatch.setattr(config, "operation_feedback_mode", None)
    assert BaseMixin().performance_profile.mode == "high"
    monkeypatch.setattr(config, "operation_feedback_avg", 2)
    assert BaseMixin().performance_profile.mode == "medium"
    assert BaseMixin().performance_profile.mode == "low"


def test_auto_hysteresis_and_warmup(monkeypatch):
    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    monkeypatch.setattr(performance, "__system__", "darwin")
    choose = performance.auto_performance_mode
    assert choose(2, 3, "high") == "high"
    assert choose(0.49, 4, "high") == "high"
    assert choose(0.5, 4, "high") == "medium"
    assert choose(1.39, 4, "medium") == "medium"
    assert choose(1.4, 4, "medium") == "low"
    assert choose(0.9, 4, "low") == "low"
    assert choose(0.89, 4, "low") == "medium"


def test_selection_profile_snapshot_does_not_switch_mid_operation(monkeypatch):
    from arknights_mower.solvers.base_mixin import fixed_selection_profile

    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    monkeypatch.setattr(performance, "__system__", "darwin")
    monkeypatch.setattr(config, "conf", Conf(performance_mode="auto"))
    monkeypatch.setattr(config, "operation_feedback_avg", 0)
    monkeypatch.setattr(config, "operation_feedback_count", 4)
    monkeypatch.setattr(config, "operation_feedback_mode", None)
    solver = BaseMixin()

    @fixed_selection_profile
    def selection(self):
        assert self.performance_profile.mode == "high"
        self.record_operation_feedback(3)
        assert self.performance_profile.mode == "high"

    selection(solver)
    assert not hasattr(solver, "_selection_profile_snapshot")
    assert solver.performance_profile.mode == "medium"


def test_feedback_ewma_counts_operations_not_screenshots(monkeypatch):
    monkeypatch.setattr(config, "operation_feedback_avg", None)
    monkeypatch.setattr(config, "operation_feedback_count", 0)
    solver = BaseMixin()
    solver.record_operation_feedback(0)
    solver.record_operation_feedback(4)
    assert config.operation_feedback_avg == 0.75
    assert config.operation_feedback_count == 2


def test_capture_metrics_do_not_change_auto_mode(monkeypatch):
    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    monkeypatch.setattr(performance, "__system__", "darwin")
    monkeypatch.setattr(config, "conf", Conf(performance_mode="auto"))
    monkeypatch.setattr(config, "screenshot_avg", 1000)
    monkeypatch.setattr(config, "screenshot_count", 99)
    monkeypatch.setattr(config, "operation_feedback_avg", None)
    monkeypatch.setattr(config, "operation_feedback_count", 0)
    monkeypatch.setattr(config, "operation_feedback_mode", None)
    monkeypatch.setattr(
        config, "screenshot_time", datetime.now() - timedelta(seconds=10)
    )
    monkeypatch.setattr(device_module, "save_screenshot", lambda *_: None)
    device = object.__new__(Device)
    device.control = SimpleNamespace(
        mumu12IPC=SimpleNamespace(
            capture_display=lambda: np.zeros((2, 2, 3), dtype=np.uint8)
        )
    )

    device.screencap()
    assert config.screenshot_count == 100
    device.screencap()
    assert config.screenshot_count == 101
    assert BaseMixin().performance_profile.mode == "high"


def test_android_auto_uses_medium_during_warmup(monkeypatch):
    monkeypatch.setenv("MOWER_ANDROID", "1")
    conf = RIICPart(performance_mode="auto")
    profile = performance.effective_performance_profile(conf, 0, 3)
    assert profile.mode == "medium"
    assert profile.run_order_delay == 5


def test_low_mode_preserves_all_timing_parameters():
    conf = Conf(
        performance_mode="low",
        low_frame_rate_mode=False,
        selection_poll_interval=0.1,
        selection_transition_timeout=2.5,
        run_order_delay=3,
        run_order_grandet_mode={"buffer_time": 15},
    )
    assert conf.low_frame_rate_mode
    assert conf.screenshot_interval == 500
    assert conf.selection_poll_interval == 0.1
    assert conf.selection_transition_timeout == 2.5
    assert conf.run_order_delay == 3
    assert conf.run_order_grandet_mode.buffer_time == 15
    profile = performance.effective_performance_profile(conf)
    assert profile.mode == "low"
    assert profile.stable_page_matches == 2
    assert (profile.poll_interval, profile.run_order_delay) == (0.1, 3)


def test_legacy_custom_profile_migrates_and_keeps_configured_values():
    conf = Conf(
        performance_mode="custom",
        low_frame_rate_mode=True,
        screenshot_interval=650,
        selection_poll_interval=1.25,
        selection_transition_timeout=9,
        run_order_delay=12,
        run_order_grandet_mode={"buffer_time": 40},
    )
    profile = performance.effective_performance_profile(conf)
    assert conf.performance_mode == "medium"
    assert profile.screenshot_interval == 650
    assert (profile.poll_interval, profile.transition_timeout) == (1.25, 9)
    assert (profile.run_order_delay, profile.grandet_buffer_time) == (12, 40)


def test_explicit_mode_controls_selection_despite_legacy_boolean(monkeypatch):
    conf = Conf(
        performance_mode="high",
        low_frame_rate_mode=False,
        selection_poll_interval=0.1,
        selection_transition_timeout=9,
    )
    monkeypatch.setattr(config, "conf", conf)
    assert BaseMixin().selection_observation_timing() == (0.1, 6)
    conf.low_frame_rate_mode = True
    assert BaseMixin().selection_observation_timing() == (0.1, 6)
    conf.performance_mode = "medium"
    assert BaseMixin().selection_observation_timing() == (0.1, 91)


def test_switching_mode_does_not_change_numeric_values():
    conf = Conf(
        performance_mode="high",
        screenshot_interval=650,
        selection_poll_interval=1.25,
        selection_transition_timeout=9,
        run_order_delay=12,
        run_order_grandet_mode={"buffer_time": 40},
    )
    for mode in ("medium", "low", "auto", "high"):
        conf.performance_mode = mode
        profile = performance.effective_performance_profile(conf, 2, 8)
        assert (profile.screenshot_interval, profile.poll_interval) == (650, 1.25)
        assert (profile.transition_timeout, profile.run_order_delay) == (9, 12)
        assert profile.grandet_buffer_time == 40
