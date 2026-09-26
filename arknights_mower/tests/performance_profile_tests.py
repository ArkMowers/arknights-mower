from types import SimpleNamespace

import pytest

from arknights_mower.utils import performance
from arknights_mower.utils.config.conf import Conf, RIICPart


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


def test_existing_timing_migrates_to_custom_without_overwriting_values():
    conf = Conf(
        low_frame_rate_mode=False,
        run_order_delay=7.5,
        run_order_grandet_mode={"buffer_time": 22},
    )
    assert conf.performance_mode == "custom"
    assert conf.run_order_delay == 7.5
    assert conf.run_order_grandet_mode.buffer_time == 22
    assert not performance.effective_performance_profile(conf).low_frame_rate


def test_existing_screenshot_interval_migrates_to_custom():
    conf = Conf(screenshot_interval=650)
    assert conf.performance_mode == "custom"
    assert conf.screenshot_interval == 650


@pytest.mark.parametrize(
    ("average", "expected"),
    [(100, "medium"), (250, "medium"), (251, "medium"), (699, "medium"), (700, "low")],
)
def test_auto_selects_profile_from_capture_cost(monkeypatch, average, expected):
    monkeypatch.setenv("MOWER_ANDROID", "1")
    conf = RIICPart(performance_mode="auto")
    assert performance.effective_performance_profile(conf, average, 8).mode == expected


def test_android_high_and_legacy_fast_mode_use_medium(monkeypatch):
    monkeypatch.setenv("MOWER_ANDROID", "1")
    for settings in ({"performance_mode": "high"}, {"low_frame_rate_mode": False}):
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
    assert performance.effective_performance_profile(conf, 100, 8).mode == "high"


def test_android_auto_uses_medium_during_warmup(monkeypatch):
    monkeypatch.setenv("MOWER_ANDROID", "1")
    conf = RIICPart(performance_mode="auto")
    profile = performance.effective_performance_profile(conf, 100, 7)
    assert profile.mode == "medium"
    assert profile.run_order_delay == 5


def test_low_preset_sets_all_linked_parameters():
    conf = Conf(
        performance_mode="low",
        low_frame_rate_mode=False,
        selection_poll_interval=0.1,
        selection_transition_timeout=2.5,
        run_order_delay=3,
        run_order_grandet_mode={"buffer_time": 15},
    )
    assert conf.low_frame_rate_mode
    assert conf.screenshot_interval == 750
    assert conf.selection_poll_interval == 0.75
    assert conf.selection_transition_timeout == 6
    assert conf.run_order_delay == 10
    assert conf.run_order_grandet_mode.buffer_time == 30


def test_custom_profile_uses_configured_values():
    conf = SimpleNamespace(
        performance_mode="custom",
        low_frame_rate_mode=True,
        screenshot_interval=650,
        selection_poll_interval=1.25,
        selection_transition_timeout=9,
        run_order_delay=12,
        run_order_grandet_mode=SimpleNamespace(buffer_time=40),
    )
    profile = performance.effective_performance_profile(conf)
    assert profile.screenshot_interval == 650
    assert (profile.poll_interval, profile.transition_timeout) == (1.25, 9)
    assert (profile.run_order_delay, profile.grandet_buffer_time) == (12, 40)
