import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from arknights_mower.utils.news_checker import NewsChecker


class TestNewsChecker(unittest.TestCase):
    def test_build_update_time_accepts_24_hour_end(self):
        news_tz = ZoneInfo("Asia/Shanghai")

        start_dt, end_dt = NewsChecker._build_update_time(
            2026, 5, 2, 16, 0, 24, 0, news_tz
        )

        self.assertEqual(start_dt, datetime(2026, 5, 2, 16, 0, tzinfo=news_tz))
        self.assertEqual(end_dt, datetime(2026, 5, 3, 0, 0, tzinfo=news_tz))

    def test_build_update_time_rolls_overnight_end_forward(self):
        news_tz = ZoneInfo("Asia/Shanghai")

        start_dt, end_dt = NewsChecker._build_update_time(
            2026, 5, 2, 23, 0, 1, 30, news_tz
        )

        self.assertEqual(start_dt, datetime(2026, 5, 2, 23, 0, tzinfo=news_tz))
        self.assertEqual(end_dt, datetime(2026, 5, 3, 1, 30, tzinfo=news_tz))


if __name__ == "__main__":
    unittest.main()
