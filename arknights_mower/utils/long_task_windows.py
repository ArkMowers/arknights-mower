"""Daily execution windows for automatic long tasks, in scheduler local time."""

from datetime import datetime, timedelta
from functools import lru_cache


@lru_cache(maxsize=64)
def _merged_windows(pairs):
    intervals = []
    for start, end in pairs:
        try:
            times = [datetime.strptime(value, "%H:%M") for value in (start, end)]
        except (ValueError, TypeError):
            continue
        start, end = (t.hour * 60 + t.minute for t in times)
        if start == end:
            return ()
        if start < end:
            intervals.append((start, end))
        else:
            intervals.extend(((start, 1440), (0, end)))
    merged = []
    for start, end in sorted(intervals):
        if start == end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    if merged == [(0, 1440)]:
        return ()
    if len(merged) > 1 and merged[0][0] == 0 and merged[-1][1] == 1440:
        start, _ = merged.pop()
        merged[0] = (start, 1440 + merged[0][1])
    return tuple(merged)


def long_task_window(conf, now):
    """Return the current cutoff (now when closed) and the next distinct opening."""
    pairs = [
        (
            getattr(conf, "maa_rg_sleep_max", "0:00"),
            getattr(conf, "maa_rg_sleep_min", "0:00"),
        )
    ]
    pairs.extend(
        (w.start, w.end) for w in getattr(conf, "maa_long_task_extra_windows", ())
    )
    windows = _merged_windows(tuple(pairs))
    if not windows:
        return now + timedelta(days=1), None
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = now
    opening = None
    for start, end in windows:
        begins = midnight + timedelta(minutes=start)
        if begins > now:
            begins -= timedelta(days=1)
        closes = begins + timedelta(minutes=end - start)
        if now < closes:
            cutoff = closes
        following = begins + timedelta(days=1)
        if opening is None or following < opening:
            opening = following
    return cutoff, opening
