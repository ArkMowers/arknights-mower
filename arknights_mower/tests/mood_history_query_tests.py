"""Offline regression tests for seven/nine-column read-only mood history."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from arknights_mower.solvers.mood_history_query import (
    MAX_OPERATORS,
    available_mood_operators,
    selected_mood_series,
)


class MoodHistoryQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.database = Path(self.tmp.name) / "data.db"

    def create_data(self, include_events=False):
        connection = sqlite3.connect(self.database)
        columns = """
            name TEXT, agent_current_room TEXT, current_room TEXT,
            is_high INTEGER, agent_group TEXT, mood REAL, current_time TEXT
        """
        if include_events:
            columns += ", related_operator TEXT, mood_event TEXT"
        connection.execute(f"CREATE TABLE agent_action ({columns})")
        for name, ts, mood in [
            ("阿米娅", "2026-09-22 12:00:00.000000", 23),
            ("阿米娅", "2026-09-22 10:00:00.000000", 24),
            ("低优先记录干员", "2026-09-21 10:00:00.000000", 11),
        ]:
            columns_sql = (
                "name, agent_current_room, current_room, is_high,"
                " agent_group, mood, current_time"
            )
            data = [name, "room_1_1", "room_1_1", 0, "临时组", mood, ts]
            if include_events:
                columns_sql += ", related_operator, mood_event"
                data.extend(["阿米娅", "fiammetta_before"])
            placeholders = ", ".join("?" for _ in data)
            connection.execute(
                f"INSERT INTO agent_action ({columns_sql}) VALUES ({placeholders})",
                data,
            )
        connection.commit()
        connection.close()

    def test_missing_database_is_not_created(self):
        self.assertEqual(available_mood_operators(self.database), [])
        self.assertEqual(
            selected_mood_series(self.database, ["阿米娅"]),
            [{"name": "阿米娅", "data": []}],
        )
        self.assertFalse(self.database.exists())

    def test_legacy_seven_columns_include_non_priority_history(self):
        self.create_data()
        catalog = available_mood_operators(self.database)
        self.assertEqual({r["name"] for r in catalog}, {"阿米娅", "低优先记录干员"})
        self.assertEqual(
            next(r["sampleCount"] for r in catalog if r["name"] == "阿米娅"), 2
        )
        results = selected_mood_series(self.database, ["阿米娅", "无历史"])
        self.assertEqual([r["name"] for r in results], ["阿米娅", "无历史"])
        self.assertEqual([r["data"][0]["y"] for r in results[:1]], [24])
        self.assertEqual(results[1]["data"], [])
        self.assertNotIn("moodEvent", results[0]["data"][0])
        self.assertIn("+", results[0]["data"][0]["x"])

    def test_nine_columns_keep_explicit_events(self):
        self.create_data(include_events=True)
        result = selected_mood_series(self.database, ["阿米娅"])
        self.assertEqual(result[0]["data"][0]["moodEvent"], "fiammetta_before")
        self.assertEqual(result[0]["data"][0]["relatedOperator"], "阿米娅")

    def test_input_limits_and_unchanged_database(self):
        self.create_data()
        before = self.database.read_bytes()
        for invalid in ([""], [8], ["z" * 41], ["operator"] * (MAX_OPERATORS + 1)):
            with self.assertRaises(ValueError):
                # Duplicate names must not count toward the limit.
                if invalid[0] == "operator":
                    invalid = [str(i) for i in range(MAX_OPERATORS + 1)]
                selected_mood_series(self.database, invalid)
        self.assertEqual(self.database.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
