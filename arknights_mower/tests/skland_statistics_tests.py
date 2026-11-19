import csv
import datetime
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from arknights_mower.utils import path
from arknights_mower.utils.config.conf import SKLandPart
from arknights_mower.utils.skland_statistics import (
    ACCOUNT_FAILED,
    ACCOUNT_RECOVERED,
    SklandRecord,
    build_statistics,
    classify_outcome,
    current_streak,
    longest_streak,
    mask_account,
    parse_record,
    read_history,
)
from arknights_mower.views import skland as skland_view
from arknights_mower.views.skland import skland_bp

PHONE = "13800138000"


def record(
    date: str,
    account: str = "138****8000",
    game: str = "明日方舟官服",
    outcome: str = "signed",
) -> SklandRecord:
    return SklandRecord(
        date=datetime.date.fromisoformat(date),
        account=account,
        game=game,
        outcome=outcome,
        reward="龙门币×1000" if outcome == "signed" else "请勿重复签到！",
        item="龙门币" if outcome == "signed" else None,
        count=1000 if outcome == "signed" else 0,
    )


class OutcomeTests(unittest.TestCase):
    def test_legacy_rows_infer_success_from_reward_shape(self):
        row = ["2026/08/01", PHONE, "明日方舟官服", "龙门币×1000"]
        parsed = parse_record(row)
        self.assertEqual(parsed.outcome, "signed")
        self.assertEqual((parsed.item, parsed.count), ("龙门币", 1000))

    def test_new_rows_use_status_column(self):
        success = parse_record(
            ["2026/08/01", PHONE, "明日方舟官服", "龙门币×1000", "success", "0"]
        )
        failure = parse_record(
            ["2026/08/01", PHONE, "明日方舟官服", "网络错误", "failure", "1000"]
        )
        self.assertEqual(success.outcome, "signed")
        self.assertEqual(failure.outcome, "failed")

    def test_event_and_role_keys_are_exposed_without_raw_identifiers(self):
        row = ["2026/08/01", PHONE, "明日方舟官服", "龙门币×1000", "success", "0"]
        role_key = "a1" * 32
        event_id = "c8" * 16
        parsed = parse_record([*row, role_key, event_id]).to_dict()
        self.assertEqual(parsed["role_key"], role_key)
        self.assertEqual(parsed["event_id"], event_id)
        malformed = parse_record([*row, "raw-role", "raw-event"]).to_dict()
        self.assertNotIn("role_key", malformed)
        self.assertNotIn("event_id", malformed)

    def test_repeat_messages_are_not_failures(self):
        for message in ("请勿重复签到！", "今日已签到", "已经签到过了"):
            with self.subTest(message=message):
                self.assertEqual(classify_outcome("failure", message), "repeated")
                self.assertEqual(classify_outcome("", message), "repeated")

    def test_unknown_legacy_message_is_failure(self):
        self.assertEqual(classify_outcome("", "活动未开启"), "failed")

    def test_short_and_malformed_rows_are_skipped(self):
        self.assertIsNone(parse_record(["2026/08/01", PHONE]))
        self.assertIsNone(parse_record(["日期", "账号", "游戏", "奖励"]))
        self.assertIsNone(parse_record(["2026/08/01", "", "明日方舟官服", "龙门币×1"]))


class AccountPrivacyTests(unittest.TestCase):
    def test_phone_is_masked(self):
        self.assertEqual(mask_account(PHONE), "138****8000")

    def test_email_and_username_are_masked(self):
        self.assertEqual(mask_account("demo@example.com"), "d**o@example.com")
        self.assertEqual(mask_account("player123"), "pl*****23")
        self.assertEqual(mask_account("abc"), "***")

    def test_parsed_record_does_not_keep_raw_account(self):
        parsed = parse_record(["2026/08/01", PHONE, "明日方舟官服", "龙门币×1000"])
        self.assertNotIn(PHONE, json.dumps(parsed.to_dict(), ensure_ascii=False))

    def test_reward_text_masks_account_and_phone(self):
        parsed = parse_record(
            [
                "2026/08/01",
                PHONE,
                "明日方舟官服",
                f"账号{PHONE}登录失败",
                "failure",
                "1000",
            ]
        )
        self.assertNotIn(PHONE, parsed.reward)
        self.assertIn("****", parsed.reward)

    def test_plain_reward_text_is_unchanged(self):
        parsed = parse_record(["2026/08/01", PHONE, "明日方舟官服", "赤金×2"])
        self.assertEqual(parsed.reward, "赤金×2")

    def test_statistics_payload_does_not_contain_raw_account(self):
        records = [
            parse_record(["2026/08/01", PHONE, "明日方舟官服", "龙门币×1000"]),
            parse_record(["2026/08/02", PHONE, "明日方舟官服", "龙门币×1000"]),
        ]
        payload = build_statistics(
            records,
            start=datetime.date(2026, 8, 1),
            end=datetime.date(2026, 8, 2),
            today=datetime.date(2026, 8, 2),
        )
        self.assertNotIn(PHONE, json.dumps(payload, ensure_ascii=False))


class HistoryFileTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "skland.csv"

    def write(self, rows):
        with open(self.path, "w", encoding="gbk", newline="") as handle:
            csv.writer(handle).writerows(rows)

    def test_missing_file_returns_empty_history(self):
        self.assertEqual(read_history(self.path), [])

    def test_empty_file_returns_empty_history(self):
        self.path.write_bytes(b"")
        self.assertEqual(read_history(self.path), [])

    def test_reads_gbk_legacy_and_current_rows_together(self):
        self.write(
            [
                ["2026/08/01", PHONE, "明日方舟官服", "龙门币×1000"],
                [
                    "2026/08/02",
                    PHONE,
                    "终末地官服",
                    "请勿重复签到！",
                    "failure",
                    "1000",
                ],
            ]
        )
        records = read_history(self.path)
        self.assertEqual([row.outcome for row in records], ["signed", "repeated"])
        self.assertEqual(records[0].account, "138****8000")

    def test_unreadable_permission_is_left_to_the_caller(self):
        self.path.write_bytes(b"2026/08/01,x,y,z\n")
        with patch("builtins.open", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                read_history(self.path)

    def test_reads_a_utf8_saved_copy(self):
        with open(self.path, "w", encoding="utf-8-sig", newline="") as handle:
            csv.writer(handle).writerow(
                ["2026/08/01", PHONE, "明日方舟官服", "龙门币×1000"]
            )
        records = read_history(self.path)
        self.assertEqual([row.outcome for row in records], ["signed"])

    def test_unreadable_bytes_raise_oserror_not_unicode_error(self):
        self.path.write_bytes(b"\xff\xfe\x00invalid")
        with self.assertRaises(OSError):
            read_history(self.path)


class StreakTests(unittest.TestCase):
    def days(self, *values):
        return [datetime.date.fromisoformat(value) for value in values]

    def test_current_streak_accepts_yesterday_before_today_is_signed(self):
        days = self.days("2026-08-01", "2026-08-02", "2026-08-03")
        self.assertEqual(current_streak(days, datetime.date(2026, 8, 4)), 3)

    def test_current_streak_resets_after_a_missed_day(self):
        days = self.days("2026-08-01", "2026-08-02")
        self.assertEqual(current_streak(days, datetime.date(2026, 8, 4)), 0)

    def test_longest_streak_keeps_the_best_run(self):
        days = self.days(
            "2026-08-01", "2026-08-02", "2026-08-05", "2026-08-06", "2026-08-07"
        )
        self.assertEqual(longest_streak(days), 3)


class StatisticsTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            record("2026-08-01", account="138****8000", game="明日方舟官服"),
            record(
                "2026-08-01",
                account="138****8000",
                game="终末地官服",
                outcome="repeated",
            ),
            record("2026-08-02", account="138****8000", game="明日方舟官服"),
            record(
                "2026-08-02",
                account="139****9000",
                game="明日方舟官服",
                outcome="failed",
            ),
            record("2026-08-03", account="138****8000", game="明日方舟官服"),
        ]

    def build(self, **overrides):
        arguments = {
            "start": datetime.date(2026, 8, 1),
            "end": datetime.date(2026, 8, 3),
            "today": datetime.date(2026, 8, 3),
        }
        arguments.update(overrides)
        return build_statistics(self.records, **arguments)

    def test_range_only_filters_records_not_pairs(self):
        payload = self.build(start=datetime.date(2026, 8, 2))
        self.assertEqual(len(payload["records"]), 3)
        self.assertEqual(len(payload["pairs"]), 3)

    def test_pair_role_count_includes_roles_outside_the_requested_range(self):
        august = record("2026-08-03")
        july = record("2026-07-05")
        other_account = replace(august, account="139****9000", role_key="b" * 64)
        self.records = [
            august,
            replace(august, role_key="a" * 64),
            replace(july, role_key="b" * 64),
            other_account,
            replace(other_account, date=july.date),
        ]

        payload = self.build()

        first, second = payload["pairs"]
        self.assertTrue(first["multiple_roles"])
        self.assertNotIn("multiple_roles", second)
        self.assertTrue(all(row["date"] == "2026-08-03" for row in payload["records"]))

    def test_today_summary_counts_pending_pairs(self):
        payload = self.build(today=datetime.date(2026, 8, 4))
        self.assertEqual(
            payload["today"],
            {
                "date": "2026-08-04",
                "signed": 0,
                "repeated": 0,
                "failed": 0,
                "pending": 3,
                "total": 3,
            },
        )

    def test_today_summary_merges_multiple_rows_for_one_pair(self):
        rows = [
            record("2026-08-03", account="138****8000", game="明日方舟官服"),
            record(
                "2026-08-03",
                account="138****8000",
                game="明日方舟官服",
                outcome="repeated",
            ),
        ]
        payload = build_statistics(
            rows,
            start=datetime.date(2026, 8, 3),
            end=datetime.date(2026, 8, 3),
            today=datetime.date(2026, 8, 3),
        )
        self.assertEqual(payload["today"]["signed"], 1)
        self.assertEqual(payload["today"]["repeated"], 0)
        self.assertEqual(payload["today"]["pending"], 0)

    def test_account_filter_applies_to_pairs_and_today(self):
        payload = self.build(account="139****9000")
        self.assertEqual(
            [pair["account"] for pair in payload["pairs"]], ["139****9000"]
        )
        self.assertEqual(payload["today"]["total"], 1)
        self.assertEqual(
            [row["account"] for row in payload["records"]], ["139****9000"]
        )

    def test_today_records_are_returned_even_when_range_excludes_today(self):
        payload = self.build(
            start=datetime.date(2026, 8, 1),
            end=datetime.date(2026, 8, 1),
            today=datetime.date(2026, 8, 3),
        )
        self.assertEqual(
            {row["date"] for row in payload["today_records"]}, {"2026-08-03"}
        )
        self.assertNotIn("2026-08-03", {row["date"] for row in payload["records"]})

    def test_records_are_newest_first(self):
        payload = self.build()
        dates = [row["date"] for row in payload["records"]]
        self.assertEqual(dates, sorted(dates, reverse=True))


class SklandRouteTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.cache_path = self.data_dir / "instance" / "tmp" / "skland_rewards.json"
        self.enterContext(patch.object(path, "_data_dir", self.data_dir))
        self.enterContext(patch.object(path, "global_space", "instance"))
        self.account = SKLandPart.SKLandAccount(
            account=PHONE, password="test-password", sign_in_official=True
        )
        self.runtime_conf = skland_view.config.conf
        self.configuration = SimpleNamespace(skland_info=[self.account])
        self.enterContext(patch.object(skland_view.config, "conf", self.configuration))
        self.month = self.enterContext(
            patch.object(skland_view, "_reward_month", return_value="2026-11")
        )
        self.reward_pair = {
            "account": "138****8000",
            "game": "明日方舟官服",
            "role_index": 1,
            "reward_slots": [
                {
                    "index": 1,
                    "done": True,
                    "available": False,
                    "rewards": [{"item": "龙门币", "count": 2000}],
                }
            ],
            "progress_date": "2026-11-18",
            "signed_today": True,
        }
        self.records = [
            record("2026-08-01"),
            record("2026-08-02"),
        ]
        self.app = Flask(__name__)
        self.app.token = "skland-token"
        self.app.register_blueprint(skland_bp)
        self.client = self.app.test_client()
        self.headers = {"token": "skland-token"}

    def test_requires_session_token(self):
        with patch.object(skland_view, "_unambiguous_history") as read:
            for method in ("GET", "HEAD"):
                for headers in ({}, {"token": "wrong"}):
                    response = self.client.open(
                        "/skland/statistics", method=method, headers=headers
                    )
                    self.assertEqual(response.status_code, 403)
        read.assert_not_called()

    def test_statistics_uses_skland_day_for_default_range(self):
        with (
            patch.object(skland_view, "_unambiguous_history", return_value=([], [])),
            patch.object(
                skland_view, "skland_day", return_value=datetime.date(2026, 12, 1)
            ),
        ):
            response = self.client.get("/skland/statistics", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["range"]["end"], "2026-12-01")
        self.assertEqual(response.json["today"]["date"], "2026-12-01")

    def test_rejects_invalid_dates(self):
        response = self.client.get(
            "/skland/statistics?startDate=2026-08-02&endDate=2026-08-01",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("开始日期", response.json["error"])

    def test_returns_history_for_the_requested_range(self):
        with patch(
            "arknights_mower.views.skland._unambiguous_history",
            return_value=(self.records, []),
        ):
            response = self.client.get(
                "/skland/statistics?startDate=2026-08-01&endDate=2026-08-01",
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["records"]), 1)
        self.assertEqual(
            response.json["range"], {"start": "2026-08-01", "end": "2026-08-01"}
        )
        self.assertNotIn("ambiguous_accounts", response.json)

    def test_account_failures_are_grouped_without_a_game_or_role(self):
        other_phone = "13900139000"
        csv_path = path.get_path("@app/tmp/skland.csv")
        csv_path.parent.mkdir(parents=True)
        lookup = "读取森空岛签到角色失败"
        login = "森空岛登录失败"
        rows = [
            ["2026/10/31", PHONE, "", lookup, ACCOUNT_FAILED],
            ["2026/11/18", PHONE, "", login, ACCOUNT_FAILED],
            ["2026/11/18", PHONE, "", login, ACCOUNT_FAILED],
            ["2026/11/18", PHONE, "", "", ACCOUNT_RECOVERED],
            ["2026/11/18", other_phone, "", lookup, ACCOUNT_FAILED],
        ]
        with csv_path.open("w", encoding="gbk", newline="") as stream:
            csv.writer(stream).writerows(rows)

        query = {
            "startDate": "2026-11-18",
            "endDate": "2026-11-18",
            "game": "明日方舟官服",
        }
        response = self.client.get(
            "/skland/statistics", headers=self.headers, query_string=query
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["pairs"], [])
        self.assertEqual(response.json["games"], [])
        self.assertEqual(response.json["records"], [])
        self.assertEqual(response.json["today"]["total"], 0)
        self.assertEqual(response.json["first_account_failure_date"], "2026-10-31")
        entries = {
            entry["account"]: entry for entry in response.json["account_failures"]
        }
        self.assertEqual(
            entries[mask_account(PHONE)],
            {
                "account": mask_account(PHONE),
                "date": "2026-11-18",
                "attempts": 2,
                "messages": [login],
                "resolved": True,
            },
        )
        self.assertFalse(entries[mask_account(other_phone)]["resolved"])
        self.assertNotIn(PHONE, response.get_data(as_text=True))

        selected = self.client.get(
            "/skland/statistics",
            headers=self.headers,
            query_string={**query, "account": mask_account(other_phone)},
        )
        self.assertEqual(selected.json["first_account_failure_date"], "2026-11-18")
        self.assertEqual(
            selected.json["account_failures"], [entries[mask_account(other_phone)]]
        )

    def test_statistics_omit_colliding_account_masks(self):
        second_phone = "13800258000"
        third_phone = "13900138000"
        game = "明日方舟官服"
        masked = mask_account(PHONE)
        csv_path = path.get_path("@app/tmp/skland.csv")
        csv_path.parent.mkdir(parents=True)
        for collision_source in ("history", "configuration"):
            with self.subTest(collision_source=collision_source):
                accounts = [self.account]
                rows = [
                    ["2026/11/18", PHONE, game, "龙门币×1000"],
                    ["2026/11/18", third_phone, game, "龙门币×2000"],
                ]
                if collision_source == "history":
                    rows.append(["2026/11/18", second_phone, game, "签到失败"])
                else:
                    accounts.append(SKLandPart.SKLandAccount(account=second_phone))
                with csv_path.open("w", encoding="gbk", newline="") as stream:
                    csv.writer(stream).writerows(rows)
                with (
                    patch.object(self.configuration, "skland_info", accounts),
                    patch.object(
                        skland_view,
                        "skland_day",
                        return_value=datetime.date(2026, 11, 18),
                    ),
                ):
                    response = self.client.get(
                        "/skland/statistics", headers=self.headers
                    )
                    selected = self.client.get(
                        "/skland/statistics",
                        headers=self.headers,
                        query_string={"account": masked},
                    )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["ambiguous_accounts"], [masked])
                self.assertEqual(response.json["accounts"], [mask_account(third_phone)])
                self.assertEqual(response.json["today"]["total"], 1)
                self.assertEqual(response.json["today"]["signed"], 1)
                self.assertEqual(response.json["today"]["failed"], 0)
                for field in ("pairs", "records", "today_records"):
                    self.assertEqual(
                        [row["account"] for row in response.json[field]],
                        [mask_account(third_phone)],
                    )
                    self.assertEqual(selected.json[field], [])
                self.assertEqual(selected.status_code, 200)
                self.assertEqual(selected.json["ambiguous_accounts"], [masked])
                self.assertNotIn(PHONE, response.get_data(as_text=True))
                self.assertNotIn(second_phone, response.get_data(as_text=True))

    def test_busy_csv_returns_service_unavailable(self):
        with patch(
            "arknights_mower.views.skland._unambiguous_history",
            side_effect=PermissionError,
        ):
            response = self.client.get("/skland/statistics", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertIn("skland.csv", response.json["error"])

    def test_other_read_failures_return_service_unavailable(self):
        with patch(
            "arknights_mower.views.skland._unambiguous_history", side_effect=OSError
        ):
            response = self.client.get("/skland/statistics", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertIn("读取失败", response.json["error"])

    def test_rejects_ranges_longer_than_a_year(self):
        response = self.client.get(
            "/skland/statistics?startDate=2025-01-01&endDate=2026-11-14",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("366", response.json["error"])

    def test_default_range_covers_thirty_days(self):
        with patch(
            "arknights_mower.views.skland._unambiguous_history", return_value=([], [])
        ):
            response = self.client.get("/skland/statistics", headers=self.headers)
        start = datetime.date.fromisoformat(response.json["range"]["start"])
        end = datetime.date.fromisoformat(response.json["range"]["end"])
        self.assertEqual((end - start).days, 29)

    def test_reward_routes_require_token_before_accessing_configuration(self):
        with (
            patch.object(skland_view, "_reward_configuration") as configuration,
            patch.object(skland_view, "fetch_pair_rewards") as fetch,
            patch.object(skland_view, "get_path") as get_path,
        ):
            for method, path in (
                ("GET", "/skland/rewards"),
                ("HEAD", "/skland/rewards"),
                ("GET", "/skland/rewards?month=2026-10"),
                ("POST", "/skland/rewards/refresh"),
            ):
                for headers in ({}, {"token": "wrong"}):
                    self.assertEqual(
                        self.client.open(
                            path, method=method, headers=headers
                        ).status_code,
                        403,
                    )
        configuration.assert_not_called()
        fetch.assert_not_called()
        get_path.assert_not_called()

    def test_reward_get_reuses_cache_and_post_refreshes_progress(self):
        newer = {**self.reward_pair, "progress_date": "2026-11-19"}
        with patch.object(
            skland_view,
            "fetch_pair_rewards",
            side_effect=[([self.reward_pair], []), ([newer], [])],
        ) as fetch:
            self.assertFalse(self.get_rewards()["cached"])
            fetch.assert_not_called()
            result = self.refresh_rewards()
            self.assertTrue(result["cached"])
            self.assertEqual(result["pairs"], [self.reward_pair])
            cache = self.cache_path.read_text(encoding="utf-8")
            self.assertNotIn(self.account.account, cache)
            self.assertNotIn(self.account.password, cache)

            restarted_app = Flask(__name__)
            restarted_app.token = self.app.token
            restarted_app.register_blueprint(skland_bp)
            self.client = restarted_app.test_client()
            self.assertEqual(self.get_rewards(), result)
            fetch.assert_called_once_with([self.account])
            updated = self.refresh_rewards()
            self.assertEqual(updated["pairs"], [newer])
            self.assertEqual(self.get_rewards(), updated)
            self.assertEqual(fetch.call_count, 2)

    def test_partial_and_failed_refresh_preserve_last_good_progress(self):
        first = {**self.reward_pair, "role_key": "first-role"}
        second = {**self.reward_pair, "role_key": "second-role", "role_index": 2}
        newer = {**first, "progress_date": "2026-11-19"}
        merged = [newer, {**second, "stale": True}]
        with patch.object(
            skland_view,
            "fetch_pair_rewards",
            side_effect=[
                ([first, second], []),
                ([newer], ["部分角色读取失败"]),
                ([], ["账号读取失败"]),
                ([newer, second], []),
            ],
        ):
            self.assertEqual(self.refresh_rewards()["pairs"], [first, second])
            partial = self.refresh_rewards()
            self.assertTrue(partial["cached"])
            self.assertEqual(partial["pairs"], merged)
            self.assertEqual(self.get_rewards(), partial)

            failed = self.refresh_rewards()
            self.assertTrue(failed["cached"])
            self.assertEqual(
                failed["pairs"], [{**pair, "stale": True} for pair in merged]
            )
            self.assertEqual(failed["warnings"], ["账号读取失败"])
            self.assertEqual(self.get_rewards(), failed)

            self.assertEqual(self.refresh_rewards()["pairs"], [newer, second])
            self.assertEqual(self.get_rewards()["warnings"], [])

    def test_partial_refresh_does_not_assign_an_old_unkeyed_role_by_ordinal(self):
        previous = [
            {**self.reward_pair, "role_index": 1, "display_name": "甲"},
            {**self.reward_pair, "role_index": 2, "display_name": "乙"},
        ]
        fresh = {**previous[1], "role_index": 1, "role_key": "second-role"}
        with patch.object(
            skland_view,
            "fetch_pair_rewards",
            side_effect=[(previous, []), ([fresh], ["部分角色读取失败"])],
        ):
            self.assertEqual(self.refresh_rewards()["pairs"], previous)
            self.assertEqual(self.refresh_rewards()["pairs"], [fresh])
            self.assertEqual(self.get_rewards()["pairs"], [fresh])

    def test_reward_cache_shares_identical_tables_and_retains_role_progress(self):
        self.configuration.skland_info = [
            SKLandPart.SKLandAccount(
                account=account,
                sign_in_official=True,
                sign_in_bilibili=True,
                sign_in_endfield_official=True,
                sign_in_endfield_bilibili=True,
            )
            for account in (PHONE, "13900138001")
        ]
        coin = [{"item": "龙门币", "count": 2000}]
        card = [{"item": "招聘许可", "count": 1}]
        common = [coin, [], card]
        different_order = [card, [], coin]
        different_count = [[{"item": "龙门币", "count": 3000}], [], card]
        pairs = []
        for account in ("138****8000", "139****8001"):
            for game in ("明日方舟", "终末地"):
                for channel in ("官服", "bilibili服"):
                    completed = len(pairs) % 4
                    if len(pairs) == 6:
                        rewards = different_order
                    elif len(pairs) == 7:
                        rewards = different_count
                    else:
                        rewards = common
                    pairs.append(
                        {
                            **self.reward_pair,
                            "account": account,
                            "game": game + channel,
                            "signed_today": completed == 3,
                            "reward_slots": [
                                {
                                    "index": index,
                                    "done": index <= completed,
                                    "available": index == completed + 1,
                                    "rewards": items,
                                }
                                for index, items in enumerate(rewards, start=1)
                            ],
                        }
                    )

        with patch.object(
            skland_view, "fetch_pair_rewards", return_value=(pairs, [])
        ) as fetch:
            self.assertEqual(self.refresh_rewards()["pairs"], pairs)
            snapshot = json.loads(self.cache_path.read_text(encoding="utf-8"))
            self.assertEqual(
                snapshot["reward_tables"], [common, different_order, different_count]
            )
            self.assertEqual(
                [pair["reward_table"] for pair in snapshot["pairs"]],
                [0, 0, 0, 0, 0, 0, 1, 2],
            )
            self.assertTrue(
                all("reward_slots" not in pair for pair in snapshot["pairs"])
            )
            self.assertEqual(snapshot["pairs"][0]["done_slots"], [])
            self.assertEqual(snapshot["pairs"][0]["available_slots"], [1])
            self.assertEqual(snapshot["pairs"][1]["done_slots"], [1])
            self.assertEqual(snapshot["pairs"][1]["available_slots"], [2])
            self.assertEqual(self.get_rewards()["pairs"], pairs)
            fetch.assert_called_once_with(self.configuration.skland_info)

    def test_legacy_inline_reward_cache_is_reused(self):
        _, fingerprint = skland_view._reward_configuration()
        self.cache_path.parent.mkdir(parents=True)
        self.cache_path.write_text(
            json.dumps(
                {
                    "month": "2026-11",
                    "configuration": fingerprint,
                    "pairs": [self.reward_pair],
                    "warnings": [],
                }
            ),
            encoding="utf-8",
        )
        with patch.object(skland_view, "fetch_pair_rewards") as fetch:
            result = self.get_rewards()
            self.assertTrue(result["cached"])
            self.assertEqual(result["pairs"], [self.reward_pair])
            fetch.assert_not_called()

    def test_reward_cache_is_scoped_to_instance_month_and_account_configuration(self):
        with patch.object(
            skland_view, "fetch_pair_rewards", return_value=([self.reward_pair], [])
        ):
            self.assertTrue(self.refresh_rewards()["cached"])
        with patch.object(path, "global_space", "another-instance"):
            self.assertEqual(self.get_rewards()["pairs"], [])
        self.account.sign_in_official = False
        self.assertFalse(self.get_rewards()["cached"])
        self.account.sign_in_official = True
        self.assertTrue(self.get_rewards()["cached"])
        self.month.return_value = "2026-12"
        result = self.get_rewards()
        self.assertEqual(result["month"], "2026-12")
        self.assertFalse(result["cached"])
        self.assertEqual(result["pairs"], [])

    def test_past_reward_query_rejects_invalid_or_future_month_before_storage(self):
        with (
            patch.object(skland_view, "get_path") as get_path,
            patch.object(skland_view, "fetch_pair_rewards") as fetch,
        ):
            for month in ("", "2026-1", "2026-00", "2026-13", "2026-12", "../2026"):
                with self.subTest(month=month):
                    response = self.client.get(
                        "/skland/rewards",
                        query_string={"month": month},
                        headers=self.headers,
                    )
                    self.assertEqual(response.status_code, 400)
        get_path.assert_not_called()
        fetch.assert_not_called()

    def test_past_rewards_survive_rollover_and_account_changes_without_remote_read(
        self,
    ):
        next_pair = {**self.reward_pair, "progress_date": "2026-12-01"}
        with patch.object(
            skland_view,
            "fetch_pair_rewards",
            side_effect=[([self.reward_pair], []), ([next_pair], [])],
        ) as fetch:
            self.assertTrue(self.refresh_rewards()["cached"])
            self.month.return_value = "2026-12"
            self.account.sign_in_official = False
            self.account.sign_in_bilibili = True
            past = self.get_rewards("2026-11")
            self.assertTrue(past["cached"])
            self.assertEqual(past["pairs"], [self.reward_pair])
            self.assertEqual(past["earliest_month"], "2026-11")
            self.assertEqual(self.get_rewards()["earliest_month"], "2026-11")
            self.assertEqual(fetch.call_count, 1)
            latest = self.refresh_rewards()
            self.assertEqual(latest["pairs"], [next_pair])
            self.assertEqual(latest["earliest_month"], "2026-11")
            self.assertTrue(
                self.cache_path.with_suffix("").joinpath("2026-11.json").is_file()
            )
            self.assertEqual(self.get_rewards("2026-11"), past)
            self.assertFalse(self.get_rewards("2026-10")["cached"])
            self.assertEqual(self.get_rewards(), latest)
            self.assertEqual(fetch.call_count, 2)

    def test_monthly_cache_is_dropped_only_when_every_daily_reward_is_recorded(self):
        pair = {
            **self.reward_pair,
            "reward_slots": [
                {
                    "index": day,
                    "done": day <= 18,
                    "available": False,
                    "rewards": [{"item": "龙门币", "count": 1000 + day}],
                }
                for day in range(1, 31)
            ],
        }
        for last_reward, colliding_account in (
            ("龙门币×1030", None),
            ("请勿重复签到！", None),
            ("龙门币×1000", None),
            ("龙门币×1030", "13800258000"),
        ):
            accounts = [self.account]
            if colliding_account:
                accounts.append(SKLandPart.SKLandAccount(account=colliding_account))
            with (
                self.subTest(
                    last_reward=last_reward, colliding_account=colliding_account
                ),
                patch.object(self.configuration, "skland_info", accounts),
                patch.object(
                    path, "global_space", f"rollover-{last_reward}-{len(accounts)}"
                ),
                patch.object(
                    skland_view,
                    "fetch_pair_rewards",
                    side_effect=[([pair], []), ([], [])],
                ),
            ):
                self.month.return_value = "2026-11"
                self.assertTrue(self.refresh_rewards()["cached"])
                csv_path = path.get_path("@app/tmp/skland.csv")
                with csv_path.open("w", encoding="gbk", newline="") as stream:
                    writer = csv.writer(stream)
                    for day in range(1, 31):
                        writer.writerow(
                            [
                                f"2026/11/{day:02d}",
                                PHONE,
                                pair["game"],
                                last_reward if day == 30 else f"龙门币×{1000 + day}",
                            ]
                        )
                self.month.return_value = "2026-12"
                self.assertTrue(self.refresh_rewards()["cached"])
                past = self.get_rewards("2026-11")
                if last_reward != "龙门币×1030" or colliding_account:
                    self.assertTrue(past["cached"])
                    self.assertEqual(past["pairs"], [pair])
                    continue
                self.assertFalse(past["cached"])
                self.assertIsNone(past["earliest_month"])
                history = self.client.get(
                    "/skland/statistics?startDate=2026-11-01&endDate=2026-11-30",
                    headers=self.headers,
                )
                self.assertEqual(history.status_code, 200)
                rows = history.json["records"]
                self.assertEqual(len(rows), 30)
                self.assertEqual(rows[0]["date"], "2026-11-30")
                self.assertEqual(rows[0]["item"], "龙门币")
                self.assertEqual(rows[0]["count"], 1030)

    def test_archive_write_failure_preserves_prior_month(self):
        next_pair = {**self.reward_pair, "progress_date": "2026-12-01"}
        with patch.object(
            skland_view,
            "fetch_pair_rewards",
            side_effect=[([self.reward_pair], []), ([next_pair], [])],
        ):
            self.assertTrue(self.refresh_rewards()["cached"])
            previous_file = self.cache_path.read_bytes()
            self.month.return_value = "2026-12"
            with patch.object(
                skland_view.config, "atomic_write", side_effect=PermissionError
            ) as write:
                result = self.refresh_rewards()
            self.assertFalse(result["cached"])
            self.assertEqual(result["pairs"], [next_pair])
            self.assertEqual(result["warnings"], ["本月奖励缓存写入失败"])
            write.assert_called_once()
            self.assertEqual(
                write.call_args.args[0],
                self.cache_path.with_suffix("") / "2026-11.json",
            )
            self.assertEqual(self.cache_path.read_bytes(), previous_file)
            self.assertEqual(self.get_rewards("2026-11")["pairs"], [self.reward_pair])

    def test_invalid_cache_and_upstream_failure_allow_retry(self):
        self.cache_path.parent.mkdir(parents=True)
        self.cache_path.write_text("{", encoding="utf-8")
        previous_month_pair = {**self.reward_pair, "progress_date": "2026-10-31"}
        with patch.object(
            skland_view,
            "fetch_pair_rewards",
            side_effect=[
                ([], ["读取失败"]),
                ([previous_month_pair], []),
                ([self.reward_pair], []),
            ],
        ):
            self.assertFalse(self.get_rewards()["cached"])
            failed = self.refresh_rewards()
            self.assertFalse(failed["cached"])
            self.assertEqual(failed["warnings"], ["读取失败"])
            previous = self.refresh_rewards()
            self.assertFalse(previous["cached"])
            self.assertEqual(previous["pairs"], [])
            self.assertTrue(previous["warnings"])
            self.assertEqual(self.cache_path.read_text(encoding="utf-8"), "{")
            self.assertTrue(self.refresh_rewards()["cached"])
            self.assertEqual(self.get_rewards()["pairs"], [self.reward_pair])

    def test_invalid_reward_table_reference_is_refetched(self):
        _, fingerprint = skland_view._reward_configuration()
        self.cache_path.parent.mkdir(parents=True)
        self.cache_path.write_text(
            json.dumps(
                {
                    "month": "2026-11",
                    "configuration": fingerprint,
                    "pairs": [
                        {
                            "account": self.reward_pair["account"],
                            "game": self.reward_pair["game"],
                            "role_index": 1,
                            "reward_table": 0,
                            "done_slots": [],
                            "available_slots": [],
                        }
                    ],
                    "reward_tables": [],
                    "warnings": [],
                }
            ),
            encoding="utf-8",
        )
        with patch.object(
            skland_view, "fetch_pair_rewards", return_value=([self.reward_pair], [])
        ) as fetch:
            self.assertFalse(self.get_rewards()["cached"])
            fetch.assert_not_called()
            self.assertTrue(self.refresh_rewards()["cached"])
            self.assertEqual(self.get_rewards()["pairs"], [self.reward_pair])
            fetch.assert_called_once_with([self.account])

    def test_empty_success_is_cached(self):
        self.configuration.skland_info = []
        with patch.object(
            skland_view, "fetch_pair_rewards", return_value=([], [])
        ) as fetch:
            self.assertTrue(self.refresh_rewards()["cached"])
            self.assertTrue(self.get_rewards()["cached"])
            self.assertEqual(self.get_rewards()["pairs"], [])
            fetch.assert_called_once_with([])

    def test_reward_cache_write_failure_preserves_fetched_data(self):
        with (
            patch.object(
                skland_view, "fetch_pair_rewards", return_value=([self.reward_pair], [])
            ),
            patch.object(
                skland_view.config, "atomic_write", side_effect=PermissionError
            ),
        ):
            result = self.refresh_rewards()
            self.assertFalse(result["cached"])
            self.assertEqual(result["pairs"], [self.reward_pair])
            self.assertEqual(result["warnings"], ["本月奖励缓存写入失败"])
            self.assertFalse(self.get_rewards()["cached"])

    def get_rewards(self, month=None):
        response = self.client.get(
            "/skland/rewards",
            query_string={"month": month} if month is not None else None,
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        return response.json

    def refresh_rewards(self):
        response = self.client.post("/skland/rewards/refresh", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        return response.json

    def test_reward_refresh_rejects_concurrent_requests(self):
        self.enterContext(patch.object(skland_view.config, "conf", self.runtime_conf))
        self.enterContext(
            patch.object(self.runtime_conf, "skland_info", [self.account])
        )
        import server
        from arknights_mower.utils.config_profiles import current_generation

        entered, release = Event(), Event()
        headers = {
            **self.headers,
            "X-Mower-Config-Generation": current_generation(),
        }

        def fetch_rewards(_accounts):
            entered.set()
            self.assertTrue(release.wait(5))
            return [self.reward_pair], []

        def refresh():
            with server.app.test_client() as client:
                return client.post("/skland/rewards/refresh", headers=headers)

        with (
            patch.object(server.app, "token", self.app.token, create=True),
            patch.object(
                skland_view, "fetch_pair_rewards", side_effect=fetch_rewards
            ) as fetch,
            ThreadPoolExecutor(max_workers=2) as workers,
        ):
            first = workers.submit(refresh)
            try:
                self.assertTrue(entered.wait(3))
                second = workers.submit(refresh)
                self.assertEqual(second.result(timeout=2).status_code, 409)
            finally:
                release.set()
            self.assertEqual(first.result(timeout=3).status_code, 200)
        fetch.assert_called_once_with([self.account])


if __name__ == "__main__":
    unittest.main()
