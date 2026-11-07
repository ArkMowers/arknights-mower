"""Keep recent slow network observations separate from saved configuration."""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Callable

ADAPTIVE_WAIT_SCENES = frozenset({"CONNECTING", "LOADING"})
NETWORK_EVIDENCE_SCENES = frozenset({"CONNECTING"})
OBSERVATION_TTL = timedelta(minutes=15)
MAX_OBSERVATIONS = 1024
MAX_COMPENSATION_SECONDS = 90.0
COMPENSATION_RATIO = 0.5


@dataclass(frozen=True)
class SlowNetworkEvent:
    """Measured network wait; each consumer decides whether it needs protection."""

    event_id: int
    scene: str
    observed_at: datetime
    duration_seconds: float
    timed_out: bool
    base_seconds: float = 0

    @property
    def compensation_seconds(self) -> float:
        return min(self.duration_seconds, MAX_COMPENSATION_SECONDS)


class NetworkAdaptation:
    """Share recent network facts while consuming each ordinary wait once."""

    def __init__(self):
        self._observations: deque[SlowNetworkEvent] = deque(maxlen=MAX_OBSERVATIONS)
        self._waiting_used: set[int] = set()
        self._next_event_id = 1
        self._observation_callback: Callable[[SlowNetworkEvent], None] | None = None

    def set_observation_callback(
        self, callback: Callable[[SlowNetworkEvent], None] | None
    ) -> None:
        self._observation_callback = callback

    @property
    def observations(self) -> tuple[SlowNetworkEvent, ...]:
        return tuple(self._observations)

    def _prune(self, now: datetime) -> None:
        self._observations = deque(
            (
                event
                for event in self._observations
                if timedelta(0) <= now - event.observed_at < OBSERVATION_TTL
            ),
            maxlen=MAX_OBSERVATIONS,
        )
        retained = {event.event_id for event in self._observations}
        self._waiting_used.intersection_update(retained)

    def record(
        self,
        scene: str,
        *,
        elapsed_seconds: float,
        base_seconds: float,
        observed_at: datetime,
        timed_out: bool = False,
    ) -> SlowNetworkEvent | None:
        """Accept elapsed monotonic time; a timeout remains an observed lower bound."""
        self._prune(observed_at)
        if (
            scene not in NETWORK_EVIDENCE_SCENES
            or not isfinite(elapsed_seconds)
            or not isfinite(base_seconds)
            or base_seconds <= 0
            or elapsed_seconds <= 0
        ):
            return None
        event = SlowNetworkEvent(
            self._next_event_id,
            scene,
            observed_at,
            float(elapsed_seconds),
            timed_out,
            float(base_seconds),
        )
        self._next_event_id += 1
        self._observations.append(event)
        self._prune(observed_at)
        if self._observation_callback is not None:
            self._observation_callback(event)
        return event

    def _largest_qualifying(
        self, now: datetime, base_seconds: float, *, unused_wait_only: bool = False
    ):
        self._prune(now)
        if not isfinite(base_seconds) or base_seconds <= 0:
            return None
        return max(
            (
                event
                for event in reversed(self._observations)
                if event.duration_seconds > base_seconds * COMPENSATION_RATIO
                and (not unused_wait_only or event.event_id not in self._waiting_used)
            ),
            key=lambda event: (
                event.duration_seconds,
                event.observed_at,
                event.event_id,
            ),
            default=None,
        )

    def peek_run_order(
        self, now: datetime, *, base_seconds: float
    ) -> SlowNetworkEvent | None:
        return self._largest_qualifying(now, base_seconds)

    def take_run_order(
        self, now: datetime, event_id: int | None = None, *, base_seconds: float
    ) -> SlowNetworkEvent | None:
        event = self.peek_run_order(now, base_seconds=base_seconds)
        if event is None or event_id is not None and event.event_id != event_id:
            return None
        return event

    def take_wait(
        self, scene: str, now: datetime, *, base_seconds: float
    ) -> SlowNetworkEvent | None:
        if scene not in ADAPTIVE_WAIT_SCENES:
            return None
        event = self._largest_qualifying(now, base_seconds, unused_wait_only=True)
        if event is not None:
            self._waiting_used.add(event.event_id)
            return event
        return None


def get_network_adaptation(owner) -> NetworkAdaptation:
    adaptation = owner.__dict__.get("network_adaptation")
    if not isinstance(adaptation, NetworkAdaptation):
        adaptation = NetworkAdaptation()
        owner.network_adaptation = adaptation
    return adaptation
