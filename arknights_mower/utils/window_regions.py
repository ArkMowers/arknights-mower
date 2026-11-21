"""Bounded HTML hit regions shared with native window event handlers."""

from math import isfinite
from threading import Lock

RESIZE_EDGES = frozenset(
    (
        "left",
        "right",
        "top",
        "bottom",
        "top-left",
        "top-right",
        "bottom-left",
        "bottom-right",
    )
)
MAX_REGIONS = 128


def _number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
    )


class WindowHitRegions:
    def __init__(self):
        self._lock = Lock()
        self._snapshot = (0, 0, ())

    def update(self, payload):
        """Replace one viewport snapshot; invalid input clears stale regions."""
        try:
            width, height = payload["width"], payload["height"]
            regions = payload["regions"]
            if (
                not all(
                    _number(value) and 0 < value <= 65536 for value in (width, height)
                )
                or not isinstance(regions, list)
                or len(regions) > MAX_REGIONS
            ):
                raise ValueError("Invalid window viewport")
            parsed = []
            for region in regions:
                x, y, w, h = (region[key] for key in ("x", "y", "width", "height"))
                if not all(_number(value) for value in (x, y, w, h)) or not (
                    x >= 0
                    and y >= 0
                    and w > 0
                    and h > 0
                    and x + w <= width + 0.01
                    and y + h <= height + 0.01
                ):
                    raise ValueError("Invalid window region")
                if region["kind"] == "move":
                    action = "move"
                elif region["kind"] == "resize" and region.get("edge") in RESIZE_EDGES:
                    action = region["edge"]
                else:
                    raise ValueError("Unknown window region")
                parsed.append((action, x, y, w, h))
            # A corner or edge overlapping the title bar owns the press.
            parsed.sort(key=lambda item: (item[0] == "move", "-" not in item[0]))
            snapshot = (width, height, tuple(parsed))
        except (KeyError, TypeError, ValueError, OverflowError):
            with self._lock:
                self._snapshot = (0, 0, ())
            return False
        with self._lock:
            self._snapshot = snapshot
        return True

    def hit_test(self, x, y, width, height):
        with self._lock:
            css_width, css_height, regions = self._snapshot
        if not regions or not all(_number(value) for value in (x, y, width, height)):
            return None
        # Never stretch an old snapshot over a resized window: that could turn
        # a control button into a drag region before ResizeObserver reports it.
        if abs(width - css_width) > 1 or abs(height - css_height) > 1:
            return None
        for action, left, top, w, h in regions:
            if left <= x < left + w and top <= y < top + h:
                return action
        return None
