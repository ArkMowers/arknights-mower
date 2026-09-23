"""Read-only mood history queries for custom observation cards.

No schema migration and no database initialization: works with both seven-column
packaged Mower databases and nine-column development databases.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

MAX_OPERATORS = 16
MAX_NAME_LENGTH = 40
MAX_SAMPLES_PER_OPERATOR = 600


def _open_history(database: str | Path):
    file = Path(database)
    if not file.is_file():
        return None
    connection = sqlite3.connect(f"{file.resolve().as_uri()}?mode=ro", uri=True, timeout=3)
    connection.row_factory = sqlite3.Row
    if "agent_action" not in {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }:
        connection.close()
        return None
    return connection


def available_mood_operators(database: str | Path) -> list[dict]:
    """Return operators with any recorded mood, without priority or group filters."""
    connection = _open_history(database)
    if connection is None:
        return []
    try:
        rows = connection.execute(
            """
            SELECT name, COUNT(*) AS sample_count, MAX("current_time") AS latest
            FROM agent_action
            WHERE name IS NOT NULL AND TRIM(name) <> ''
              AND mood IS NOT NULL AND "current_time" IS NOT NULL
            GROUP BY name
            ORDER BY latest DESC
            LIMIT 500
            """
        ).fetchall()
        return [
            {
                "name": row["name"],
                "sampleCount": row["sample_count"],
                "lastRecordedAt": row["latest"],
            }
            for row in rows
        ]
    finally:
        connection.close()


def _names(values) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("names must be an array")
    result = []
    for value in values:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > MAX_NAME_LENGTH:
            raise ValueError("invalid operator name")
        name = value.strip()
        if name not in result:
            result.append(name)
        if len(result) > MAX_OPERATORS:
            raise ValueError("too many operators")
    return result


def _point(timestamp, mood, related, event):
    try:
        instant = datetime.fromisoformat(timestamp)
        numeric = float(mood)
        if not 0 <= numeric <= 24:
            return None
        # SQLite timestamps are local wall times; emit an offset-aware timestamp
        # without inventing a fixed timezone for non-China deployments.
        when = instant.astimezone() if instant.tzinfo else instant.astimezone()
    except (TypeError, ValueError, OverflowError):
        return None
    point = {"x": when.isoformat(), "y": numeric}
    if related:
        point["relatedOperator"] = related
    if event:
        point["moodEvent"] = event
    return point


def selected_mood_series(database: str | Path, names: list[str]) -> list[dict]:
    """Read at most 600 newest valid observations per selected operator."""
    names = _names(names)
    if not names:
        return []
    connection = _open_history(database)
    if connection is None:
        return [{"name": name, "data": []} for name in names]
    try:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(agent_action)")}
        related_column = "related_operator" if "related_operator" in columns else "NULL"
        event_column = "mood_event" if "mood_event" in columns else "NULL"
        result = []
        for name in names:
            rows = connection.execute(
                f"""
                SELECT "current_time", mood, {related_column} AS related,
                       {event_column} AS event
                FROM agent_action
                WHERE name = ? AND "current_time" IS NOT NULL AND mood IS NOT NULL
                ORDER BY "current_time" DESC, rowid DESC LIMIT ?
                """,
                (name, MAX_SAMPLES_PER_OPERATOR),
            ).fetchall()
            points = []
            for row in reversed(rows):
                point = _point(row["current_time"], row["mood"], row["related"], row["event"])
                if point is not None:
                    points.append(point)
            result.append({"name": name, "data": points})
        return result
    finally:
        connection.close()
