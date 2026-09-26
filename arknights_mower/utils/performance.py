import os
from dataclasses import dataclass
from math import ceil

from arknights_mower import __system__


@dataclass(frozen=True)
class PerformanceProfile:
    mode: str
    low_frame_rate: bool
    screenshot_interval: int
    poll_interval: float
    transition_timeout: float
    run_order_delay: float
    grandet_buffer_time: int

    @property
    def transition_attempts(self) -> int:
        return ceil(self.transition_timeout / self.poll_interval) + 1


PERFORMANCE_PRESETS = {
    "high": PerformanceProfile("high", False, 500, 0.1, 2.5, 3, 15),
    "medium": PerformanceProfile("medium", True, 500, 0.5, 2.5, 5, 15),
    "low": PerformanceProfile("low", True, 750, 0.75, 6.0, 10, 30),
}


def is_android_runtime() -> bool:
    return os.environ.get("MOWER_ANDROID") == "1" or __system__ == "android"


def default_performance_mode() -> str:
    return "auto" if is_android_runtime() else "high"


def default_performance_profile() -> PerformanceProfile:
    return PERFORMANCE_PRESETS["medium" if is_android_runtime() else "high"]


def effective_performance_profile(conf, screenshot_avg=None, screenshot_count=0):
    """Resolve a fixed/custom profile or adapt AUTO from the capture pipeline EWMA."""
    mode = conf.performance_mode
    if mode == "custom":
        return PerformanceProfile(
            "custom",
            conf.low_frame_rate_mode,
            conf.screenshot_interval,
            conf.selection_poll_interval,
            conf.selection_transition_timeout,
            conf.run_order_delay,
            conf.run_order_grandet_mode.buffer_time,
        )
    if mode != "auto":
        return PERFORMANCE_PRESETS[
            "medium" if is_android_runtime() and mode == "high" else mode
        ]

    # Keep the previous platform default during warm-up. screenshot_avg is an
    # EWMA of actual capture/decoding cost, so a transient slow frame does not
    # immediately move the device between profiles.
    if screenshot_avg is None or screenshot_count < 8:
        selected = "medium" if is_android_runtime() else "high"
    elif screenshot_avg <= 250 and not is_android_runtime():
        selected = "high"
    elif screenshot_avg < 700:
        selected = "medium"
    else:
        selected = "low"
    profile = PERFORMANCE_PRESETS[selected]
    return PerformanceProfile(
        selected,
        profile.low_frame_rate,
        profile.screenshot_interval,
        profile.poll_interval,
        profile.transition_timeout,
        profile.run_order_delay,
        profile.grandet_buffer_time,
    )
