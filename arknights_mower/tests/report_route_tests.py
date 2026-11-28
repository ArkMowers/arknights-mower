"""基报接口校验实例凭据，并保留完整历史和各字段的独立读数。"""

import csv
import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server

ROUTES = ("/report/getReportData", "/report/getOrundumData")
TOKEN = "report-route-tests"
REPORT_HEADERS = (
    "",
    "作战录像",
    "赤金",
    "龙门币订单",
    "龙门币订单数",
    "合成玉",
    "合成玉订单数量",
)


class TestReportRoutes(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "report.csv"
        self.get_path = self.enterContext(
            patch.object(server, "get_path", return_value=str(self.path))
        )
        self.enterContext(patch.object(server.app, "token", TOKEN, create=True))
        self.headers = {"token": TOKEN}

    def tearDown(self):
        self.temp.cleanup()

    def write_report(self, readings):
        first_date = datetime.date(2026, 8, 1)
        with self.path.open("w", encoding="gbk", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(REPORT_HEADERS)
            for offset, (amount, count) in enumerate(readings):
                writer.writerow(
                    [
                        first_date + datetime.timedelta(days=offset),
                        18000,
                        61500,
                        62500,
                        37,
                        amount,
                        count,
                    ]
                )

    def test_unauthorized_requests_do_not_access_report(self):
        with (
            patch.object(server.os.path, "exists") as exists,
            patch.object(server, "read_dicts") as read_dicts,
        ):
            for route in ROUTES:
                for method in ("GET", "HEAD"):
                    for headers in ({}, {"token": "another-instance"}):
                        with self.subTest(route=route, method=method, headers=headers):
                            response = self.client.open(
                                route,
                                method=method,
                                headers=headers,
                                environ_base={"REMOTE_ADDR": "192.0.2.10"},
                            )
                            self.assertEqual(response.status_code, 403)
                            self.get_path.assert_not_called()
                            exists.assert_not_called()
                            read_dicts.assert_not_called()

    def test_current_token_reads_report_for_get_and_head(self):
        self.write_report([(600, 2)])
        with patch.object(server, "read_dicts", wraps=server.read_dicts) as read_dicts:
            for route in ROUTES:
                for method in ("GET", "HEAD"):
                    with self.subTest(route=route, method=method):
                        read_dicts.reset_mock()
                        response = self.client.open(
                            route, method=method, headers=self.headers
                        )
                        self.assertEqual(response.status_code, 200)
                        read_dicts.assert_called_once_with(
                            str(self.path), encoding="gbk"
                        )
                        if method == "GET":
                            self.assertEqual(
                                response.get_json()[-1]["日期"], "2026-07-31"
                            )
                        else:
                            self.assertEqual(response.data, b"")

    def test_missing_report_returns_empty_list(self):
        for route in ROUTES:
            with self.subTest(route=route):
                resp = self.client.get(route, headers=self.headers)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.get_json(), [])

    def test_header_only_report_returns_empty_list(self):
        self.path.write_text(
            ",作战录像,赤金,龙门币订单,龙门币订单数,合成玉,合成玉订单数量\n",
            encoding="gbk",
        )
        for route in ROUTES:
            with self.subTest(route=route):
                resp = self.client.get(route, headers=self.headers)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.get_json(), [])

    def test_locked_report_returns_error(self):
        self.path.write_text("", encoding="gbk")
        with patch.object(server, "read_dicts", side_effect=PermissionError):
            for route in ROUTES:
                with self.subTest(route=route):
                    resp = self.client.get(route, headers=self.headers)
                    self.assertEqual(resp.status_code, 503)
                    self.assertIn("占用", resp.get_json()["error"])

    def test_orundum_history_covers_thirty_days_and_older_records(self):
        for days in (30, 60):
            with self.subTest(days=days):
                self.write_report([(600, 1)] * days)
                response = self.client.get(ROUTES[1], headers=self.headers)
                self.assertEqual(response.status_code, 200)
                rows = response.get_json()
                expected_dates = [
                    str(datetime.date(2026, 7, 31) + datetime.timedelta(days=offset))
                    for offset in range(days)
                ]
                self.assertEqual([row["日期"] for row in rows], expected_dates)
                self.assertEqual([row["合成玉"] for row in rows], [600] * days)
                self.assertEqual([row["合成玉订单数量"] for row in rows], [1] * days)
                self.assertEqual([row["抽数"] for row in rows], [1.0] * days)
                self.assertEqual(
                    [row["累计制造合成玉"] for row in rows],
                    [600 * count for count in range(1, days + 1)],
                )

    def test_all_zero_orundum_readings_are_retained(self):
        self.write_report([(0, 0)] * 30)

        response = self.client.get(ROUTES[1], headers=self.headers)

        self.assertEqual(response.status_code, 200)
        rows = response.get_json()
        self.assertEqual(len(rows), 30)
        self.assertEqual(rows[0]["日期"], "2026-07-31")
        self.assertEqual(rows[-1]["日期"], "2026-08-29")
        for row in rows:
            self.assertEqual(row["合成玉"], 0)
            self.assertEqual(row["合成玉订单数量"], 0)
            self.assertEqual(row["抽数"], 0)
            self.assertEqual(row["累计制造合成玉"], 0)

    def test_all_unknown_orundum_readings_preserve_independent_order_counts(self):
        self.write_report([(None, 0), (None, 3), (None, None)])

        response = self.client.get(ROUTES[1], headers=self.headers)

        self.assertEqual(response.status_code, 200)
        rows = response.get_json()
        self.assertEqual(len(rows), 15)
        self.assertTrue(all(row["合成玉"] == "-" for row in rows[:-3]))
        self.assertEqual(
            rows[-3:],
            [
                {
                    "日期": date,
                    "合成玉": None,
                    "合成玉订单数量": count,
                    "抽数": None,
                    "累计制造合成玉": None,
                }
                for date, count in (
                    ("2026-07-31", 0),
                    ("2026-08-01", 3),
                    ("2026-08-02", None),
                )
            ],
        )

    def test_unknown_fields_do_not_clear_other_readings_or_become_zero(self):
        self.write_report([(600, None), (None, 3), (0, 0), (1200, 2)])

        response = self.client.get(ROUTES[1], headers=self.headers)

        self.assertEqual(response.status_code, 200)
        rows = response.get_json()[-4:]
        self.assertEqual([row["合成玉"] for row in rows], [600, None, 0, 1200])
        self.assertEqual([row["合成玉订单数量"] for row in rows], [None, 3, 0, 2])
        self.assertEqual([row["抽数"] for row in rows], [1.0, None, 0, 2.0])
        self.assertEqual(
            [row["累计制造合成玉"] for row in rows], [600, None, 600, 1800]
        )


if __name__ == "__main__":
    unittest.main()
