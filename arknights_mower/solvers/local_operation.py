import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from tzlocal import get_localzone

from arknights_mower.utils.datetime import get_server_time

MAX_AP = 210
DEFAULT_STAGE_DURATION_SECONDS = 8 * 60
FOLLOWUP_TASK_META = "本地刷关阈值复查"


@dataclass
class SanityProjection:
    current_ap: int
    threshold: int
    projection_minutes: int
    projected_ap: int
    excess_ap: int
    minutes_until_next_server_day: int
    next_server_day_local: datetime


def get_next_server_day_local() -> tuple[int, datetime]:
    server_now = get_server_time()
    next_server_day = (server_now + timedelta(days=1)).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    minutes_until_next_server_day = max(
        0,
        math.floor((next_server_day - server_now).total_seconds() / 60),
    )
    next_server_day_local = next_server_day.astimezone(get_localzone()).replace(
        tzinfo=None
    )
    return minutes_until_next_server_day, next_server_day_local


def build_sanity_projection(
    current_ap: int,
    threshold: int,
    maa_gap_hours: float,
) -> SanityProjection:
    current_ap = max(0, min(MAX_AP, int(current_ap)))
    threshold = max(0, min(MAX_AP, int(threshold)))
    minutes_until_next_server_day, next_server_day_local = get_next_server_day_local()
    projection_minutes = max(
        0,
        min(int(maa_gap_hours * 60), minutes_until_next_server_day),
    )
    projected_ap = min(MAX_AP, current_ap + projection_minutes // 6)
    excess_ap = max(0, projected_ap - threshold)
    return SanityProjection(
        current_ap=current_ap,
        threshold=threshold,
        projection_minutes=projection_minutes,
        projected_ap=projected_ap,
        excess_ap=excess_ap,
        minutes_until_next_server_day=minutes_until_next_server_day,
        next_server_day_local=next_server_day_local,
    )


def get_required_runs_total(
    current_ap: int,
    threshold: int,
    maa_gap_hours: float,
    ap_cost: int | None,
) -> tuple[int | None, SanityProjection]:
    projection = build_sanity_projection(current_ap, threshold, maa_gap_hours)
    if ap_cost is None or ap_cost <= 0:
        return None, projection
    if projection.excess_ap <= 0:
        return 0, projection
    return math.ceil(projection.excess_ap / ap_cost), projection


def get_stage_drain_runs_total(
    current_ap: int | None,
    ap_cost: int | None,
) -> int | None:
    if current_ap is None or ap_cost is None or ap_cost <= 0:
        return None
    return max(0, current_ap // ap_cost)


def compute_next_threshold_time(current_ap: int, threshold: int) -> datetime:
    current_ap = max(0, min(MAX_AP, int(current_ap)))
    threshold = max(0, min(MAX_AP, int(threshold)))
    now_local = datetime.now()
    minutes_until_next_server_day, next_server_day_local = get_next_server_day_local()
    if current_ap > threshold:
        return now_local
    points_needed = threshold - current_ap + 1
    minutes_to_exceed = max(0, points_needed * 6)
    if minutes_to_exceed <= minutes_until_next_server_day:
        return now_local + timedelta(minutes=minutes_to_exceed)
    return next_server_day_local
