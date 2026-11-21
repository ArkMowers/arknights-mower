"""Weekly execution windows for automatic long tasks, in scheduler local time."""

from datetime import datetime, timedelta
from functools import lru_cache

DAY_MINUTES = 24 * 60
WEEK_MINUTES = 7 * DAY_MINUTES
EVERY_DAY = tuple(range(7))
ONE_DAY = timedelta(days=1)
ONE_WEEK = timedelta(days=7)
MAA_LONG_TASK_TYPES = frozenset({"rogue", "copilot", "paradox", "sss", "rcl"})
TASK_FLAGS = (
    ("RG", "rogue"),
    ("COPILOT", "copilot"),
    ("PARADOX", "paradox"),
    ("SSS", "sss"),
    ("RCL", "rcl"),
    ("RA", "ra"),
    ("SF", "sf"),
    ("GARRISON", "garrison"),
)
TASK_TYPES = frozenset(kind for _, kind in TASK_FLAGS)


def parse_long_task_clock(value):
    return datetime.strptime(value, "%H:%M").time()


@lru_cache(maxsize=64)
def _merged_windows(pairs):
    intervals = []
    for start, end, weekdays, kind in pairs:
        try:
            times = [parse_long_task_clock(value) for value in (start, end)]
        except (ValueError, TypeError):
            continue
        start, end = (t.hour * 60 + t.minute for t in times)
        if start == end:
            start, end = 0, DAY_MINUTES
        elif end < start:
            end += DAY_MINUTES
        for weekday in weekdays:
            midnight = weekday * DAY_MINUTES
            stop = midnight + end
            intervals.append((midnight + start, min(stop, WEEK_MINUTES), kind))
            if stop > WEEK_MINUTES:
                intervals.append((0, stop - WEEK_MINUTES, kind))
    merged = []
    for start, end, kind in sorted(intervals, key=lambda interval: interval[:2]):
        if merged:
            previous_start, previous_end, previous_kind = merged[-1]
            if start < previous_end and kind != previous_kind:
                raise ValueError("不同类型的大型任务执行时段重叠")
            if start <= previous_end and kind == previous_kind:
                merged[-1] = (previous_start, max(previous_end, end), kind)
                continue
        merged.append((start, end, kind))
    if (
        len(merged) > 1
        and merged[0][0] == 0
        and merged[-1][1] == WEEK_MINUTES
        and merged[0][2] == merged[-1][2]
    ):
        start, _, kind = merged.pop()
        merged[0] = (start, WEEK_MINUTES + merged[0][1], kind)
    return tuple(merged)


def _weekly_pairs(weekly, default):
    return tuple(
        (
            window.start,
            window.end,
            tuple(window.weekdays),
            getattr(window, "task_type", None) or default,
        )
        for window in weekly
    )


def validate_long_task_windows(weekly, default):
    if weekly:
        _merged_windows(
            _weekly_pairs(weekly, default if default in TASK_TYPES else None)
        )


def long_task_schedule(conf, now):
    """Return the active automatic task type, cutoff and next distinct opening."""
    default = getattr(conf, "maa_long_task_type", None)
    if default is None:
        default = next(
            (kind for flag, kind in TASK_FLAGS if getattr(conf, flag, False)), None
        )
    elif default not in TASK_TYPES:
        default = None
    enabled = getattr(conf, "maa_rg_enable", 1) == 1
    weekly = getattr(conf, "maa_long_task_weekly_windows", None)
    if weekly is None:
        pairs = [
            (
                getattr(conf, "maa_rg_sleep_max", "0:00"),
                getattr(conf, "maa_rg_sleep_min", "0:00"),
                EVERY_DAY,
                default,
            )
        ]
        pairs.extend(
            (w.start, w.end, EVERY_DAY, default)
            for w in getattr(conf, "maa_long_task_extra_windows", ())
        )
    else:
        pairs = _weekly_pairs(weekly, default)
    windows = _merged_windows(tuple(pairs))
    if weekly is None and not windows:
        return default if enabled else None, now + ONE_DAY, None
    if len(windows) == 1 and windows[0][:2] == (0, WEEK_MINUTES):
        return windows[0][2] if enabled else None, now + ONE_DAY, None
    if not windows:
        return None, now, None
    monday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=now.weekday()
    )
    cutoff = now
    opening = None
    active = None
    for start, end, kind in windows:
        begins = monday + timedelta(minutes=start)
        if begins > now:
            begins -= ONE_WEEK
        closes = begins + timedelta(minutes=end - start)
        if now < closes:
            cutoff = min(closes, now + ONE_DAY)
            active = kind
        following = begins + ONE_WEEK
        if opening is None or following < opening:
            opening = following
    return active if enabled else None, cutoff, opening


def long_task_window(conf, now):
    _, cutoff, opening = long_task_schedule(conf, now)
    return cutoff, opening
