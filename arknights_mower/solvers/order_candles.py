"""Read recorded LMD order prices without creating or changing the database."""

from __future__ import annotations

import re
import sqlite3
import stat
import time
from datetime import date, datetime, timedelta, timezone
from datetime import time as wall_time
from pathlib import Path

MAX_DAYS = 366
QUERY_TIMEOUT = 3
_PERIOD_SECONDS = {"1h": 3600, "4h": 14400, "day": 86400}
# The game calendar keeps UTC+8; historical civil DST cannot add game hours.
_SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
    ):
        raise ValueError("请提供 YYYY-MM-DD 格式的起止日期")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("起止日期无效") from exc


def _range(start_date, end_date, period):
    start = _date(start_date)
    end = _date(end_date)
    if not isinstance(period, str) or period not in _PERIOD_SECONDS:
        raise ValueError("订单周期仅支持 1h、4h 或 day")
    if not 0 <= (end - start).days < MAX_DAYS:
        raise ValueError("起止日期须按先后排列，且最多包含 366 个游戏日")
    try:
        stop = end + timedelta(days=1)
        first = int(datetime.combine(start, wall_time(4), _SHANGHAI).timestamp())
        last = int(datetime.combine(stop, wall_time(4), _SHANGHAI).timestamp())
    except (ValueError, OverflowError) as exc:
        raise ValueError("起止日期超出支持范围") from exc
    return first, last, _PERIOD_SECONDS[period]


def get_order_candles(database, start_date, end_date, period="4h"):
    """Aggregate known LMD orders into Shanghai game-day-aligned price buckets."""
    first, last, seconds = _range(start_date, end_date, period)
    candles = []
    for start in range(first, last, seconds):
        instant = datetime.fromtimestamp(start, _SHANGHAI)
        candles.append(
            {
                "start": start,
                "end": min(start + seconds, last),
                "label": instant.strftime(
                    "%Y-%m-%d" if period == "day" else "%Y-%m-%d %H:%M"
                ),
                "open": None,
                "high": None,
                "low": None,
                "close": None,
                "mean": None,
                "count": 0,
                "amount": 0,
            }
        )
    result = {
        "period": period,
        "startDate": start_date,
        "endDate": end_date,
        "timezone": "Asia/Shanghai",
        "dayStartHour": 4,
        "candles": candles,
        "recordedCount": 0,
        "amount": 0,
    }
    path = Path(database)
    try:
        metadata = path.stat()
    except FileNotFoundError:
        return result
    if not stat.S_ISREG(metadata.st_mode):
        raise OSError("订单数据库不是普通文件")

    deadline = time.monotonic() + QUERY_TIMEOUT
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=QUERY_TIMEOUT
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        connection.execute("BEGIN")
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='trading_history'"
        ).fetchone():
            return result
        rows = connection.execute(
            """
            WITH aggregated AS (
                SELECT CAST((time - ?) / ? AS INTEGER) AS bucket,
                       MIN(time) AS first_time, MAX(time) AS last_time,
                       MIN(price) AS low, MAX(price) AS high,
                       COUNT(*) AS count, SUM(price) AS amount
                FROM trading_history
                WHERE time >= ? AND time < ?
                  AND typeof(time) = 'integer' AND typeof(price) = 'integer'
                  AND (
                      (type = '但书' AND price IN (2000, 2500))
                      OR (type = '漏单' AND price IN (1000, 1500, 2000))
                      OR (type = '龙舌兰' AND price = 2500)
                      OR (type = '佩佩' AND price = 1000)
                      OR (type = '可露希尔' AND price = 1200)
                  )
                GROUP BY bucket
            )
            SELECT bucket, first.price AS open, high, low, last.price AS close,
                   amount * 1.0 / count AS mean, count, amount
            FROM aggregated
            JOIN trading_history first ON first.time = first_time
            JOIN trading_history last ON last.time = last_time
            ORDER BY bucket
            """,
            (first, seconds, first, last),
        ).fetchall()
        for row in rows:
            candle = candles[row["bucket"]]
            for key in ("open", "high", "low", "close", "mean", "count", "amount"):
                candle[key] = row[key]
            result["recordedCount"] += row["count"]
            result["amount"] += row["amount"]
        return result
    finally:
        connection.close()
