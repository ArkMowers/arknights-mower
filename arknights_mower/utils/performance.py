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
    def stable_page_matches(self) -> int:
        """Low performance waits for one extra matching selection frame."""
        return 2 if self.mode == "low" else 1

    @property
    def transition_attempts(self) -> int:
        return ceil(self.transition_timeout / self.poll_interval) + 1


PERFORMANCE_PRESETS = {
    "ultra": PerformanceProfile("ultra", False, 500, 0.1, 2.5, 3, 15),
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
    """Choose the selection strategy while keeping user timing values intact."""
    mode = conf.performance_mode
    if mode != "auto":
        selected = (
            "medium" if is_android_runtime() and mode in ("ultra", "high") else mode
        )
    else:
        # The capture/decoding EWMA avoids switching on a single slow frame.
        if screenshot_avg is None or screenshot_count < 8:
            selected = "medium" if is_android_runtime() else "high"
        elif screenshot_avg <= 250 and not is_android_runtime():
            selected = "high"
        elif screenshot_avg < 700:
            selected = "medium"
        else:
            selected = "low"
    profile = PERFORMANCE_PRESETS[selected]
    defaults = default_performance_profile()
    grandet = getattr(conf, "run_order_grandet_mode", None)
    return PerformanceProfile(
        selected,
        profile.low_frame_rate,
        getattr(conf, "screenshot_interval", defaults.screenshot_interval),
        getattr(conf, "selection_poll_interval", defaults.poll_interval),
        getattr(conf, "selection_transition_timeout", defaults.transition_timeout),
        getattr(conf, "run_order_delay", defaults.run_order_delay),
        getattr(grandet, "buffer_time", defaults.grandet_buffer_time),
    )
