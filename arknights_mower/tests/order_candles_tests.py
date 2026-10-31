"""Offline price candles use recorded orders, one read snapshot and token checks."""

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import order_candles


def timestamp(value):
    return int(
        datetime.fromisoformat(value)
        .replace(tzinfo=timezone(timedelta(hours=8)))
        .timestamp()
    )


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "data.db"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "CREATE TABLE trading_history "
            "(time INTEGER PRIMARY KEY, server_date TEXT, type TEXT, price INTEGER)"
        )
    return path


def insert(database, rows):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executemany(
            "INSERT INTO trading_history (time, server_date, type, price) "
            "VALUES (?, 'ignored-server-date', ?, ?)",
            [(timestamp(instant), kind, price) for instant, kind, price in rows],
        )


def test_hourly_candles_keep_time_order_and_exact_game_day_boundaries(database):
    insert(
        database,
        [
            ("2026-12-31 04:40:00", "龙舌兰", 2500),
            ("2026-12-31 04:10:00", "佩佩", 1000),
            ("2026-12-31 04:00:00", "漏单", 1500),
            ("2026-12-31 03:59:59", "但书", 2500),
            ("2027-01-01 03:59:59", "可露希尔", 1200),
            ("2027-01-01 04:00:00", "但书", 2000),
        ],
    )
    result = order_candles.get_order_candles(database, "2026-12-31", "2026-12-31", "1h")
    assert result.keys() == {
        "period",
        "startDate",
        "endDate",
        "timezone",
        "dayStartHour",
        "candles",
        "recordedCount",
        "amount",
    }
    assert result["timezone"] == "Asia/Shanghai"
    assert result["dayStartHour"] == 4
    assert result["recordedCount"] == 4
    assert result["amount"] == 6200
    assert len(result["candles"]) == 24
    assert result["candles"][0] == {
        "start": timestamp("2026-12-31 04:00:00"),
        "end": timestamp("2026-12-31 05:00:00"),
        "label": "2026-12-31 04:00",
        "open": 1500,
        "high": 2500,
        "low": 1000,
        "close": 2500,
        "mean": pytest.approx(5000 / 3),
        "count": 3,
        "amount": 5000,
    }
    assert result["candles"][-1] == {
        "start": timestamp("2027-01-01 03:00:00"),
        "end": timestamp("2027-01-01 04:00:00"),
        "label": "2027-01-01 03:00",
        "open": 1200,
        "high": 1200,
        "low": 1200,
        "close": 1200,
        "mean": 1200,
        "count": 1,
        "amount": 1200,
    }
    assert result["candles"][1] == {
        "start": timestamp("2026-12-31 05:00:00"),
        "end": timestamp("2026-12-31 06:00:00"),
        "label": "2026-12-31 05:00",
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "mean": None,
        "count": 0,
        "amount": 0,
    }


@pytest.mark.parametrize("period,expected_count", [("4h", 12), ("day", 2)])
def test_larger_candles_weight_each_record_and_align_at_four(
    database, period, expected_count
):
    insert(
        database,
        [
            ("2026-10-28 04:00:00", "漏单", 1000),
            ("2026-10-28 05:00:00", "但书", 2000),
            ("2026-10-28 05:10:00", "但书", 2500),
            ("2026-10-28 08:00:00", "可露希尔", 1200),
            ("2026-10-29 04:00:00", "龙舌兰", 2500),
        ],
    )
    result = order_candles.get_order_candles(
        database, "2026-10-28", "2026-10-29", period
    )
    first = result["candles"][0]
    assert len(result["candles"]) == expected_count
    assert first["open"] == 1000
    assert first["high"] == 2500
    assert first["low"] == 1000
    if period == "4h":
        assert first["close"] == 2500
        assert first["count"] == 3
        assert first["mean"] == pytest.approx(5500 / 3)
        assert first["amount"] == 5500
        assert first["end"] == timestamp("2026-10-28 08:00:00")
        assert result["candles"][1]["count"] == 1
    else:
        assert first["close"] == 1200
        assert first["count"] == 4
        assert first["mean"] == 1675
        assert first["amount"] == 6700
        assert first["label"] == "2026-10-28"
        assert first["end"] == timestamp("2026-10-29 04:00:00")
    assert result["recordedCount"] == 5
    assert result["amount"] == 9200


def test_only_known_lmd_type_price_pairs_are_samples(database):
    rows = [
        ("漏单", 1000),
        ("漏单", 1500),
        ("漏单", 2000),
        ("但书", 2000),
        ("但书", 2500),
        ("龙舌兰", 2500),
        ("佩佩", 1000),
        ("可露希尔", 1200),
        ("源石", 20),
        ("源石", 2500),
        ("未识别", 2000),
        ("但书", 1000),
        ("佩佩", 2000),
        ("漏单", 0),
        ("漏单", -1000),
        ("漏单", None),
        ("漏单", 1500.5),
        ("漏单", "unknown"),
        (None, 1500),
    ]
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executemany(
            "INSERT INTO trading_history (time, type, price) VALUES (?, ?, ?)",
            [
                (timestamp("2026-10-28 04:00:00") + index, kind, price)
                for index, (kind, price) in enumerate(rows)
            ],
        )
    result = order_candles.get_order_candles(
        database, "2026-10-28", "2026-10-28", "day"
    )
    assert result["recordedCount"] == 8
    assert result["amount"] == 13700
    assert result["candles"][0]["mean"] == 1712.5
    assert result["candles"][0]["open"] == 1000
    assert result["candles"][0]["close"] == 1200


@pytest.mark.parametrize(
    "start,end,period",
    [
        (None, "2026-10-28", "4h"),
        ("2026-10-28", None, "4h"),
        ("2026-1-01", "2026-10-28", "4h"),
        ("2026-02-30", "2026-10-28", "4h"),
        ("2026-10-29", "2026-10-28", "4h"),
        ("2025-10-27", "2026-10-28", "4h"),
        ("2026-10-28", "2026-10-28", "5m"),
        ("2026-10-28", "2026-10-28", []),
        ("9999-12-31", "9999-12-31", "day"),
    ],
)
def test_invalid_range_rejects_before_database_access(monkeypatch, start, end, period):
    path = Mock(side_effect=AssertionError("invalid query accessed a database path"))
    monkeypatch.setattr(order_candles, "Path", path)
    with pytest.raises(ValueError):
        order_candles.get_order_candles("unused.db", start, end, period)
    path.assert_not_called()


@pytest.mark.parametrize(
    "start,end", [("2024-01-01", "2024-12-31"), ("1990-09-15", "1991-09-15")]
)
def test_maximum_range_is_bounded_and_missing_database_is_not_created(
    tmp_path, start, end
):
    path = tmp_path / "absent" / "data.db"
    result = order_candles.get_order_candles(path, start, end, "1h")
    assert len(result["candles"]) == 8784
    assert result["candles"][0]["start"] == timestamp(start + " 04:00:00")
    assert result["candles"][-1]["end"] - result["candles"][0]["start"] == 366 * 86400
    assert result["recordedCount"] == result["amount"] == 0
    assert all(row["mean"] is None for row in result["candles"])
    assert not path.parent.exists()


def test_invalid_only_history_keeps_every_price_unknown(database):
    insert(database, [("2026-10-28 04:00:00", "源石", 20)])
    result = order_candles.get_order_candles(database, "2026-10-28", "2026-10-28")
    assert result["recordedCount"] == result["amount"] == 0
    assert all(
        row["mean"] is row["open"] is row["high"] is row["low"] is row["close"] is None
        and row["count"] == row["amount"] == 0
        for row in result["candles"]
    )


def test_missing_table_returns_empty_buckets_without_schema_changes(tmp_path):
    path = tmp_path / "empty.db"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
    before = path.read_bytes()
    result = order_candles.get_order_candles(path, "2026-10-28", "2026-10-28")
    assert result["period"] == "4h"
    assert len(result["candles"]) == 6
    assert result["recordedCount"] == 0
    assert path.read_bytes() == before


def test_query_opens_readonly_and_does_not_change_history(database, monkeypatch):
    insert(database, [("2026-10-28 04:01:00", "漏单", 1000)])
    before = database.read_bytes()
    connect = sqlite3.connect
    seen = []

    def open_readonly(address, **kwargs):
        connection = connect(address, **kwargs)
        seen.append((address, kwargs))
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("CREATE TABLE prohibited (value TEXT)")
        return connection

    monkeypatch.setattr(order_candles.sqlite3, "connect", open_readonly)
    result = order_candles.get_order_candles(database, "2026-10-28", "2026-10-28")
    assert result["recordedCount"] == 1
    assert "?mode=ro" in seen[0][0]
    assert seen[0][1]["uri"] is True
    assert seen[0][1]["timeout"] == order_candles.QUERY_TIMEOUT
    assert database.read_bytes() == before


def test_table_check_and_aggregation_share_one_snapshot(database, monkeypatch):
    insert(database, [("2026-10-28 04:01:00", "漏单", 1000)])
    connect = sqlite3.connect
    with closing(connect(database)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    inserted = False

    def trace(sql):
        nonlocal inserted
        if "WITH aggregated AS" in sql and not inserted:
            inserted = True
            with closing(connect(database)) as writer, writer:
                writer.execute(
                    "INSERT INTO trading_history (time, type, price) VALUES (?, '龙舌兰', 2500)",
                    (timestamp("2026-10-28 05:00:00"),),
                )

    def open_snapshot(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connection.set_trace_callback(trace)
        return connection

    monkeypatch.setattr(order_candles.sqlite3, "connect", open_snapshot)
    first = order_candles.get_order_candles(database, "2026-10-28", "2026-10-28")
    second = order_candles.get_order_candles(database, "2026-10-28", "2026-10-28")
    assert inserted
    assert first["recordedCount"] == 1
    assert first["amount"] == 1000
    assert second["recordedCount"] == 2
    assert second["amount"] == 3500


@pytest.fixture
def web(database, monkeypatch):
    import server

    monkeypatch.setattr(server.app, "token", "order-candle-session", raising=False)
    monkeypatch.setattr(server, "get_path", lambda _: database.parent)
    return server.app.test_client()


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("token", [None, "invalid"])
def test_http_rejects_missing_and_invalid_token_without_path_or_database_access(
    web, monkeypatch, token, method
):
    import server

    path = Mock(side_effect=AssertionError("unauthorized path access"))
    connect = Mock(side_effect=AssertionError("unauthorized database access"))
    monkeypatch.setattr(server, "get_path", path)
    monkeypatch.setattr(order_candles.sqlite3, "connect", connect)
    response = getattr(web, method)(
        "/report/order-candles?startDate=invalid",
        headers={} if token is None else {"token": token},
    )
    assert response.status_code == 403
    path.assert_not_called()
    connect.assert_not_called()


def test_http_current_token_reads_the_real_database_and_validates_input(web, database):
    insert(database, [("2026-10-28 04:00:00", "但书", 2000)])
    headers = {"token": "order-candle-session"}
    response = web.get(
        "/report/order-candles?startDate=2026-10-28&endDate=2026-10-28&period=day",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json["recordedCount"] == 1
    assert response.json["candles"][0]["open"] == 2000
    assert (
        web.head(
            "/report/order-candles?startDate=2026-10-28&endDate=2026-10-28",
            headers=headers,
        ).status_code
        == 200
    )
    for query in (
        "",
        "?startDate=bad&endDate=2026-10-28",
        "?startDate=2026-10-28&endDate=2026-10-28&period=5m",
    ):
        assert (
            web.get("/report/order-candles" + query, headers=headers).status_code == 400
        )


@pytest.mark.parametrize("failure", ["corrupt", "schema", "directory"])
def test_http_database_failure_is_visible_instead_of_empty_history(
    web, database, failure
):
    if failure == "corrupt":
        database.write_bytes(b"not a sqlite database")
    elif failure == "schema":
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("DROP TABLE trading_history")
            connection.execute("CREATE TABLE trading_history (time INTEGER)")
    else:
        database.unlink()
        database.mkdir()
    response = web.get(
        "/report/order-candles?startDate=2026-10-28&endDate=2026-10-28",
        headers={"token": "order-candle-session"},
    )
    assert response.status_code == 503
    assert "读取失败" in response.json["error"]


def test_sqlite_query_budget_stops_expensive_reads(database, monkeypatch):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executemany(
            "INSERT INTO trading_history (time, type, price) VALUES (?, '漏单', 1000)",
            [(timestamp("2026-10-28 04:00:00") + index,) for index in range(2000)],
        )
    instants = iter((0, 4))
    monkeypatch.setattr(order_candles.time, "monotonic", lambda: next(instants, 4))
    with pytest.raises(sqlite3.OperationalError, match="interrupted"):
        order_candles.get_order_candles(database, "2026-10-28", "2026-10-28")
