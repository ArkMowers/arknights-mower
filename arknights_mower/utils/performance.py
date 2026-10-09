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
    "xhigh": PerformanceProfile("xhigh", False, 500, 0.1, 2.5, 3, 15),
    "high": PerformanceProfile("high", False, 500, 0.1, 2.5, 3, 15),
    "medium": PerformanceProfile("medium", True, 500, 0.5, 2.5, 5, 15),
    "low": PerformanceProfile("low", True, 750, 0.75, 6.0, 10, 30),
}


def is_android_runtime() -> bool:
    return os.environ.get("MOWER_ANDROID") == "1" or __system__ == "android"


def default_performance_mode() -> str:
    return "auto"


def default_performance_profile() -> PerformanceProfile:
    return PERFORMANCE_PRESETS["medium" if is_android_runtime() else "xhigh"]


def recommend_device_performance(cpu_cores: int, memory_mb: int) -> str:
    """Estimate a starting mode from guest resources, without game feedback."""
    if any(type(value) is not int or value <= 0 for value in (cpu_cores, memory_mb)):
        raise ValueError("设备 CPU 或内存信息无效")
    if cpu_cores < 2 or memory_mb < 1792:
        return "low"
    if cpu_cores < 4 or memory_mb < 3584:
        return "medium"
    return "high"


def auto_performance_mode(
    feedback_avg=None, feedback_count=0, previous_mode=None, mode_cap=None
):
    """Choose from acknowledged input lag, measured in extra observation frames.

    A frame can be delayed by the user's screenshot interval, so raw capture
    duration must not decide the selection strategy. Hysteresis prevents a
    single borderline acknowledgement from switching modes repeatedly.
    """
    android = is_android_runtime()
    if feedback_avg is None or feedback_count < 4:
        selected = "medium" if android else "xhigh"
    elif previous_mode == "xhigh" and not android:
        selected = "xhigh" if feedback_avg < 0.35 else "high"
    elif previous_mode == "high" and not android:
        if feedback_avg <= 0.2:
            selected = "xhigh"
        else:
            selected = "high" if feedback_avg < 0.5 else "medium"
    elif previous_mode == "low":
        selected = "low" if feedback_avg >= 0.9 else "medium"
    elif previous_mode == "medium":
        if feedback_avg >= 1.4:
            selected = "low"
        elif feedback_avg <= 0.2 and not android:
            selected = "high"
        else:
            selected = "medium"
    elif feedback_avg >= 1.2:
        selected = "low"
    elif feedback_avg >= 0.35 or android:
        selected = "medium"
    else:
        selected = "xhigh"
    if mode_cap in ("high", "medium", "low"):
        levels = ("low", "medium", "high", "xhigh")
        selected = levels[min(levels.index(selected), levels.index(mode_cap))]
    return selected


def lower_performance_mode(mode):
    """Move one step down through all automatic performance modes."""
    return {"xhigh": "high", "high": "medium", "medium": "low", "low": "low"}[mode]


def effective_performance_profile(
    conf, feedback_avg=None, feedback_count=0, previous_mode=None, mode_cap=None
):
    """Choose the selection strategy while keeping user timing values intact."""
    mode = conf.performance_mode
    if mode != "auto":
        selected = (
            "medium" if is_android_runtime() and mode in ("xhigh", "high") else mode
        )
    else:
        selected = auto_performance_mode(
            feedback_avg, feedback_count, previous_mode, mode_cap
        )
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
