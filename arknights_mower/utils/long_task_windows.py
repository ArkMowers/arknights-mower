"""Weekly execution windows for automatic long tasks, in scheduler local time."""

from datetime import datetime, timedelta
from functools import lru_cache

DAY_MINUTES = 24 * 60
WEEK_MINUTES = 7 * DAY_MINUTES
EVERY_DAY = tuple(range(7))
ONE_DAY = timedelta(days=1)
ONE_WEEK = timedelta(days=7)


def parse_long_task_clock(value):
    return datetime.strptime(value, "%H:%M").time()


@lru_cache(maxsize=64)
def _merged_windows(pairs):
    intervals = []
    for start, end, weekdays in pairs:
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
            intervals.append((midnight + start, min(stop, WEEK_MINUTES)))
            if stop > WEEK_MINUTES:
                intervals.append((0, stop - WEEK_MINUTES))
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    if len(merged) > 1 and merged[0][0] == 0 and merged[-1][1] == WEEK_MINUTES:
        start, _ = merged.pop()
        merged[0] = (start, WEEK_MINUTES + merged[0][1])
    return tuple(merged)


def long_task_window(conf, now):
    """Return the current cutoff (now when closed) and the next distinct opening."""
    weekly = getattr(conf, "maa_long_task_weekly_windows", None)
    if weekly is None:
        pairs = [
            (
                getattr(conf, "maa_rg_sleep_max", "0:00"),
                getattr(conf, "maa_rg_sleep_min", "0:00"),
                EVERY_DAY,
            )
        ]
        pairs.extend(
            (w.start, w.end, EVERY_DAY)
            for w in getattr(conf, "maa_long_task_extra_windows", ())
        )
    else:
        pairs = [(w.start, w.end, tuple(w.weekdays)) for w in weekly]
    windows = _merged_windows(tuple(pairs))
    if windows == ((0, WEEK_MINUTES),) or (weekly is None and not windows):
        return now + ONE_DAY, None
    if not windows:
        return now, None
    monday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=now.weekday()
    )
    cutoff = now
    opening = None
    for start, end in windows:
        begins = monday + timedelta(minutes=start)
        if begins > now:
            begins -= ONE_WEEK
        closes = begins + timedelta(minutes=end - start)
        if now < closes:
            cutoff = min(closes, now + ONE_DAY)
        following = begins + ONE_WEEK
        if opening is None or following < opening:
            opening = following
    return cutoff, opening
