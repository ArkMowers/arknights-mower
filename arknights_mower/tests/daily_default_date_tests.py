"""新建调度器的每日记录初始日期早于当前游戏日，与本机时区无关。"""

import sys
from datetime import datetime, timedelta, timezone
from threading import Event
from unittest.mock import Mock

import pytest
import pytz

sys.modules.setdefault("arknights_mower.utils.skland", Mock())

from arknights_mower.solvers import base_schedule  # noqa: E402

SERVER_ZONE = pytz.timezone("Asia/Dubai")


@pytest.mark.parametrize("offset", [-5, 0, 8, 9, 10, 14])
@pytest.mark.parametrize("server_hour", [0, 12, 23])
def test_new_scheduler_keeps_daily_work_due_in_current_game_day(
    monkeypatch, offset, server_hour
):
    server_now = SERVER_ZONE.localize(datetime(2026, 11, 1, server_hour, 30))
    local_zone = timezone(timedelta(hours=offset))

    class LocalClock(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return server_now.astimezone(local_zone).replace(tzinfo=None)
            return server_now.astimezone(tz)

    monkeypatch.setattr(base_schedule, "datetime", LocalClock)
    monkeypatch.setattr(base_schedule, "get_server_time", lambda: server_now)
    monkeypatch.setattr(base_schedule, "workshop_inventory_changed", Event())

    scheduler = base_schedule.BaseSchedulerSolver(device=Mock(), recog=Mock())

    # 调度器以 daily_X < 当前游戏日 决定是否执行；UTC+9 在游戏日末段曾落在当天。
    game_day = server_now.date()
    for name in (
        "daily_report",
        "daily_skland",
        "daily_mail",
        "daily_event_sign_in",
        "daily_visit_friend",
    ):
        assert getattr(scheduler, name) == game_day - timedelta(days=1), name
    assert scheduler.daily_event_sign_in_attempt is None
    assert scheduler.daily_visit_friend_attempt is None
