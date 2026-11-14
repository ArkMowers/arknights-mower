"""运行日志的每日记录接口只读取调度器或最近一次运行缓存，并按游戏日判断。"""

import json
import pickle
import sqlite3
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytz

from arknights_mower.solvers import record
from arknights_mower.tests import device_settings_route_tests as settings_routes

SERVER_ZONE = pytz.timezone("Asia/Dubai")
GAME_DAY = date(2026, 11, 1)
DAILY = ("skland", "mail", "event_sign_in", "report", "visit_friend")
MAA = ("credit_fight", "recruit", "orundum", "mining", "specialaccess", "signinevent")
RECORDS = {*DAILY, *(f"maa_{key}" for key in MAA)}
NO_RECORDS = {
    "game_day": "2026-11-01",
    "source": "none",
    "records": {},
    "activities": {},
}


def server_time(day, hour=12, minute=0):
    return SERVER_ZONE.localize(datetime(day.year, day.month, day.day, hour, minute))


class DailyStatusTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        self.enterContext(patch.object(self.main, "base_scheduler", None))
        self.enterContext(
            patch.object(
                self.server, "get_server_time", return_value=server_time(GAME_DAY)
            )
        )
        self.enterContext(
            patch.dict(
                self.server.daily_status_cache, {"snapshot": None, "values": None}
            )
        )
        self.database = self.path.with_name("data.db")
        self.enterContext(
            patch.object(self.server, "get_path", return_value=self.database)
        )
        self.execute("CREATE TABLE saved_state (time TEXT, state BLOB)")

        @contextmanager
        def connect():
            connection = sqlite3.connect(self.database)
            try:
                yield connection
            finally:
                connection.close()

        self.enterContext(patch.object(record, "_conn", connect))
        self.worker = Mock()
        self.worker.is_alive.return_value = True

    def execute(self, sql, *params):
        connection = sqlite3.connect(self.database)
        try:
            rows = connection.execute(sql, params).fetchall()
            connection.commit()
            return rows
        finally:
            connection.close()

    def save(self, state, saved_at="2026-11-01 08:00:00.000001"):
        blob = state if isinstance(state, bytes) else pickle.dumps(state)
        self.execute("DELETE FROM saved_state")
        self.execute("INSERT INTO saved_state VALUES (?, ?)", saved_at, blob)

    def scheduler(self, **values):
        yesterday = GAME_DAY - timedelta(days=1)
        defaults = {
            "daily_skland": yesterday,
            "daily_mail": yesterday,
            "daily_event_sign_in": yesterday,
            "daily_event_sign_in_attempt": None,
            "daily_report": yesterday,
            "daily_visit_friend": yesterday,
            "daily_visit_friend_attempt": None,
            "maa_daily_completed": {},
            "_state_restore_complete": True,
        }
        return SimpleNamespace(**(defaults | values))

    def run_live(self, scheduler):
        self.main.base_scheduler = scheduler
        self.server.mower_thread = self.worker

    def get(self):
        response = self.client.get("/daily-status", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        return response.json

    def test_daily_status_requires_instance_token(self):
        self.run_live(self.scheduler())
        for headers in ({}, {"token": "wrong-token"}):
            with self.subTest(headers=headers):
                response = self.client.get("/daily-status", headers=headers)
                self.assertEqual(response.status_code, 403)

    def test_live_records_follow_scheduler_date_comparisons(self):
        yesterday = GAME_DAY - timedelta(days=1)
        tomorrow = GAME_DAY + timedelta(days=1)
        # 完成日期、尝试日期、有尝试记录时的状态。
        cases = (
            (yesterday, None, "pending"),
            (yesterday, yesterday, "pending"),
            (yesterday, GAME_DAY, "attempted"),
            (None, GAME_DAY, "attempted"),
            (GAME_DAY, GAME_DAY, "done"),
            (GAME_DAY, None, "done"),
            # daily_X < 游戏日才会重新运行，晚于当天的日期同样跳过。
            (tomorrow, None, "done"),
            (datetime(2026, 11, 1, 6), None, "pending"),
        )
        for name in DAILY:
            has_attempt = name in ("event_sign_in", "visit_friend")
            for completion, attempt, expected in cases:
                if not has_attempt and expected == "attempted":
                    expected = "pending"
                with self.subTest(name=name, completion=completion, attempt=attempt):
                    self.run_live(
                        self.scheduler(
                            **{
                                f"daily_{name}": completion,
                                f"daily_{name}_attempt": attempt,
                            }
                        )
                    )
                    body = self.get()
                    self.assertEqual(body["source"], "live")
                    self.assertEqual(body["game_day"], "2026-11-01")
                    self.assertEqual(set(body["records"]), RECORDS)
                    self.assertEqual(body["records"][name], expected)

    def test_maa_records_require_current_game_day(self):
        self.run_live(
            self.scheduler(
                maa_daily_completed={
                    "credit_fight": GAME_DAY,
                    "recruit": GAME_DAY - timedelta(days=1),
                    "orundum": GAME_DAY + timedelta(days=1),
                    "specialaccess": GAME_DAY,
                }
            )
        )
        self.assertEqual(
            {
                key: value
                for key, value in self.get()["records"].items()
                if key.startswith("maa_")
            },
            {
                "maa_credit_fight": "done",
                "maa_recruit": "pending",
                "maa_orundum": "pending",
                "maa_mining": "pending",
                "maa_specialaccess": "done",
                "maa_signinevent": "pending",
            },
        )

    def test_game_day_changes_at_server_midnight_not_local_date(self):
        # 迪拜 23:59 是中国时间 03:59；UTC+9 的本机时钟此时已是次日 04:59。
        local_clock = SimpleNamespace(
            now=lambda *args: datetime(2026, 11, 2, 4, 59),
            date=SimpleNamespace(today=lambda: date(2026, 11, 2)),
        )
        self.run_live(
            self.scheduler(
                daily_skland=GAME_DAY, maa_daily_completed={"recruit": GAME_DAY}
            )
        )
        with patch.object(self.server, "datetime", local_clock):
            for now, game_day, expected in (
                (server_time(GAME_DAY, 23, 59), "2026-11-01", "done"),
                (
                    server_time(GAME_DAY + timedelta(days=1), 0, 0),
                    "2026-11-02",
                    "pending",
                ),
            ):
                with (
                    self.subTest(now=now),
                    patch.object(self.server, "get_server_time", return_value=now),
                ):
                    body = self.get()
                    self.assertEqual(body["game_day"], game_day)
                    self.assertEqual(body["records"]["skland"], expected)
                    self.assertEqual(body["records"]["maa_recruit"], expected)

    def test_live_worker_reports_none_until_state_restoration_completes(self):
        self.save(
            {"daily_skland": GAME_DAY, "maa_daily_completed": {"recruit": GAME_DAY}}
        )
        for scheduler in (None, self.scheduler(_state_restore_complete=False)):
            with self.subTest(scheduler=scheduler):
                self.run_live(scheduler)
                self.assertEqual(self.get(), NO_RECORDS)

    def test_stopped_worker_reports_latest_saved_snapshot(self):
        yesterday = GAME_DAY - timedelta(days=1)
        state = {
            "tasks": [],
            "operators": {},
            "daily_skland": GAME_DAY,
            "daily_mail": yesterday,
            "daily_event_sign_in": yesterday,
            "daily_event_sign_in_attempt": GAME_DAY,
            "daily_report": GAME_DAY,
            "daily_visit_friend": GAME_DAY,
            "daily_visit_friend_attempt": None,
            "maa_daily_completed": {"recruit": GAME_DAY, "mining": yesterday},
        }
        self.assertTrue(record.save_state_to_db(state))
        expected = {name: "pending" for name in RECORDS} | {
            "skland": "done",
            "event_sign_in": "attempted",
            "report": "done",
            "visit_friend": "done",
            "maa_recruit": "done",
        }
        self.worker.is_alive.return_value = False
        for worker in (None, self.worker):
            with self.subTest(worker=worker):
                self.server.mower_thread = worker
                body = self.get()
                self.assertEqual(body["source"], "saved")
                self.assertEqual(body["records"], expected)

    def test_older_snapshot_reports_missing_records_as_pending(self):
        self.save(
            {
                "daily_skland": GAME_DAY,
                "daily_mail": GAME_DAY,
                "daily_report": GAME_DAY,
                "daily_visit_friend": GAME_DAY,
            }
        )
        records = self.get()["records"]
        self.assertEqual(
            records,
            {name: "pending" for name in RECORDS}
            | {name: "done" for name in ("skland", "mail", "report", "visit_friend")},
        )

    def test_saved_snapshot_is_parsed_once_per_row(self):
        self.save({"daily_report": GAME_DAY})
        with patch.object(pickle, "loads", side_effect=pickle.loads) as loads:
            for _ in range(3):
                self.assertEqual(self.get()["records"]["report"], "done")
            self.assertEqual(loads.call_count, 1)
            self.save(
                {"daily_report": GAME_DAY - timedelta(days=1)},
                saved_at="2026-11-01 09:00:00.000001",
            )
            for _ in range(2):
                self.assertEqual(self.get()["records"]["report"], "pending")
            self.assertEqual(loads.call_count, 2)

    def test_unreadable_snapshot_reports_none_and_logs_once_per_row(self):
        for index, blob in enumerate((b"", pickle.dumps(["not", "a", "snapshot"]))):
            saved_at = f"2026-11-01 0{index}:00:00.000001"
            self.save(blob, saved_at=saved_at)
            with (
                self.subTest(blob=blob),
                self.assertLogs(self.server.logger, "WARNING") as logs,
            ):
                for _ in range(3):
                    self.assertEqual(self.get(), NO_RECORDS)
                self.assertEqual(len(logs.records), 1)
                self.assertIn(saved_at, logs.output[0])

    def test_replaced_snapshot_is_parsed_when_its_timestamp_is_reused(self):
        self.save({"daily_report": GAME_DAY})
        self.assertEqual(self.get()["records"]["report"], "done")

        self.save(b"invalid")
        with self.assertLogs(self.server.logger, "WARNING") as logs:
            self.assertEqual(self.get(), NO_RECORDS)
            self.assertEqual(self.get(), NO_RECORDS)
        self.assertEqual(len(logs.records), 1)

        self.save({"daily_mail": GAME_DAY})
        records = self.get()["records"]
        self.assertEqual(records["report"], "pending")
        self.assertEqual(records["mail"], "done")

    def test_missing_or_unreadable_database_reports_none(self):
        self.assertEqual(self.get(), NO_RECORDS)
        self.execute("DROP TABLE saved_state")
        self.assertEqual(self.get(), NO_RECORDS)

    def test_requests_leave_scheduler_records_and_saved_row_unchanged(self):
        scheduler = self.scheduler(
            daily_report=GAME_DAY,
            daily_visit_friend_attempt=GAME_DAY,
            maa_daily_completed={"recruit": GAME_DAY},
        )
        before = dict(vars(scheduler))
        completed = scheduler.maa_daily_completed
        self.save({"daily_report": GAME_DAY})
        saved_rows = self.execute("SELECT time, state FROM saved_state")
        guard = AssertionError("daily status only reads records")
        with (
            patch.object(record, "current_state", side_effect=guard),
            patch.object(record, "save_state_to_db", side_effect=guard),
        ):
            self.run_live(scheduler)
            with patch.object(record, "_conn", side_effect=guard):
                self.assertEqual(self.get()["source"], "live")
            self.worker.is_alive.return_value = False
            self.assertEqual(self.get()["source"], "saved")
        self.assertEqual(vars(scheduler), before)
        self.assertIs(scheduler.maa_daily_completed, completed)
        self.assertEqual(completed, {"recruit": GAME_DAY})
        self.assertEqual(
            self.execute("SELECT time, state FROM saved_state"), saved_rows
        )

    def test_activity_route_reads_live_facts_and_keeps_task_identity_and_order(self):
        from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

        zone = pytz.timezone("Asia/Shanghai")
        checked = zone.localize(datetime(2026, 11, 1, 9, 30))
        first = SchedulerTask(
            time=checked + timedelta(minutes=35), task_type=TaskTypes.CLUE
        )
        blocked = SchedulerTask(time=checked, task_type=TaskTypes.CLUE_PARTY)
        blocked.execution_failure = {"reason": "waiting for observed dependency"}
        tasks = [first, blocked]
        observations = {
            "stage-plan": {
                "at": checked,
                "runner": "mower",
                "outcome": "checked",
                "stage": "1-7",
                "executed_runs": 6,
                "reason": "sanity_drain",
            }
        }
        scheduler = self.scheduler(
            tasks=tasks,
            last_execution={"recruit": checked, "maa": checked},
            last_clue=checked,
            drone_time=checked,
            reload_time=checked,
            party_time=checked + timedelta(days=1),
            display_observations=observations,
        )
        self.run_live(scheduler)
        before = dict(vars(scheduler))
        for _ in range(2):
            activity = self.get()["activities"]
            self.assertEqual(activity["clue"]["scheduled_count"], 2)
            self.assertEqual(activity["clue"]["blocked_count"], 1)
            self.assertEqual(
                datetime.fromisoformat(activity["clue"]["next_task_at"]), first.time
            )
            self.assertEqual(
                datetime.fromisoformat(activity["recruit"]["last_checked_at"]), checked
            )
            self.assertNotIn("done", activity["recruit"].values())
            self.assertNotIn("last_checked_at", activity["stage-plan"])
            self.assertEqual(
                activity["stage-plan"]["last_observation"]["executed_runs"], 6
            )
        self.assertEqual(vars(scheduler), before)
        self.assertIs(scheduler.tasks, tasks)
        self.assertIs(tasks[0], first)
        self.assertIs(tasks[1], blocked)
        self.assertIs(scheduler.display_observations, observations)

    def test_saved_activity_does_not_restore_live_clocks_or_running(self):
        from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

        observed = pytz.timezone("Asia/Shanghai").localize(datetime(2026, 11, 1, 9, 30))
        self.save(
            {
                "last_execution": {"recruit": observed},
                "last_clue": observed,
                "drone_time": observed,
                "reload_time": observed,
                "display_observations": {
                    "stage-plan": {
                        "at": observed,
                        "runner": "maa",
                        "outcome": "running",
                    }
                },
                "tasks": [SchedulerTask(time=observed, task_type=TaskTypes.RUN_ORDER)],
            }
        )
        rows = self.execute("SELECT time, state FROM saved_state")
        body = self.get()
        self.assertEqual(body["source"], "saved")
        for key in ("recruit", "clue", "drone", "reload"):
            self.assertNotIn("last_checked_at", body["activities"][key])
        self.assertEqual(
            body["activities"]["stage-plan"]["last_observation"]["outcome"], "stopped"
        )
        self.assertEqual(body["activities"]["runorder"]["scheduled_count"], 1)
        self.assertEqual(self.execute("SELECT time, state FROM saved_state"), rows)

    def test_weekly_annihilation_observation_expires_on_monday_at_four_in_china(self):
        zone = pytz.timezone("Asia/Shanghai")
        observation = {
            "at": zone.localize(datetime(2026, 11, 1, 23)),
            "runner": "mower",
            "outcome": "reward_full",
        }
        scheduler = self.scheduler(display_observations={"annihilation": observation})
        self.run_live(scheduler)
        for moment, expected_week, present in (
            (zone.localize(datetime(2026, 11, 2, 3, 59, 59)), "2026-10-26", True),
            (zone.localize(datetime(2026, 11, 2, 4)), "2026-11-02", False),
        ):
            with (
                self.subTest(moment=moment),
                patch.object(
                    self.server,
                    "get_server_time",
                    return_value=moment.astimezone(SERVER_ZONE),
                ),
            ):
                activity = self.get()["activities"]["annihilation"]
                self.assertEqual(activity["week_start"], expected_week)
                self.assertEqual("last_observation" in activity, present)
        self.assertIs(scheduler.display_observations["annihilation"], observation)

    def test_long_queue_progress_matches_current_configuration_without_creating_runs(
        self,
    ):
        from arknights_mower.utils import config
        from arknights_mower.utils.maa_copilot import queue_key

        conf = config.Conf(
            maa_rg_enable=1,
            maa_long_task_type="sss",
            sss={
                "scripts": [{"id": "a" * 64, "times": 1}, {"id": "b" * 64, "times": 3}]
            },
        )
        self.execute(
            "CREATE TABLE maa_sss_progress (id INTEGER PRIMARY KEY, payload TEXT)"
        )
        self.execute(
            "INSERT INTO maa_sss_progress VALUES (1, ?)",
            json.dumps(
                {"key": queue_key(conf.sss), "next": 1, "completed": 2, "failed": True}
            ),
        )
        self.run_live(self.scheduler())
        before = self.execute("SELECT payload FROM maa_sss_progress")
        with patch.object(config, "conf", conf):
            activity = self.get()["activities"]["long"]
            self.assertEqual(
                activity["progress"],
                {
                    "completed": 1,
                    "total": 2,
                    "failed": True,
                    "rounds": 2,
                    "round_total": 3,
                },
            )
            conf.sss.scripts[1].times = 4
            self.assertNotIn("progress", self.get()["activities"]["long"])
        self.assertEqual(self.execute("SELECT payload FROM maa_sss_progress"), before)

    def test_activity_authorization_precedes_all_state_and_filesystem_reads(self):
        with (
            patch.object(
                self.server,
                "_daily_status_values",
                side_effect=AssertionError("state read"),
            ),
            patch.object(
                self.server, "get_path", side_effect=AssertionError("filesystem read")
            ),
        ):
            for method in ("GET", "HEAD"):
                for headers in ({}, {"token": "invalid"}):
                    with self.subTest(method=method, headers=headers):
                        self.assertEqual(
                            self.client.open(
                                "/daily-status", method=method, headers=headers
                            ).status_code,
                            403,
                        )

    def test_authenticated_head_reads_status_without_a_response_body(self):
        self.run_live(self.scheduler())
        with patch.object(
            self.server,
            "_daily_status_values",
            wraps=self.server._daily_status_values,
        ) as read:
            response = self.client.head("/daily-status", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"")
        read.assert_called_once()

    def test_status_query_does_not_create_missing_database_or_parent(self):
        missing = self.database.parent / "not-created" / "data.db"
        with patch.object(self.server, "get_path", return_value=missing):
            self.assertEqual(self.get(), NO_RECORDS)
        self.assertFalse(missing.parent.exists())

    def test_old_or_malformed_observations_do_not_invent_completion(self):
        scheduler = self.scheduler(
            display_observations={
                "stage-plan": {"at": "bad", "outcome": "completed"},
                "depot": {
                    "at": "2026-11-01T09:00:00+08:00",
                    "outcome": "future-result",
                },
                "mission": ["not an observation"],
                "annihilation": {"at": "2026-11-01T09:00:00+08:00", "outcome": []},
            }
        )
        self.run_live(scheduler)
        activity = self.get()["activities"]
        self.assertEqual(activity["stage-plan"], {})
        self.assertEqual(activity["depot"], {})
        self.assertEqual(activity["mission"], {})

    def test_retained_admitted_task_is_not_mislabelled_as_blocked(self):
        from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

        task = SchedulerTask(
            time=datetime(2026, 11, 1, 20), task_type=TaskTypes.RUN_ORDER
        )
        task.execution_retained = True
        self.run_live(self.scheduler(tasks=[task]))
        activity = self.get()["activities"]["runorder"]
        self.assertNotIn("blocked_count", activity)
        self.assertIn("next_task_at", activity)

    def test_run_order_restoration_can_finish_while_reading_queue(self):
        from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

        class FinishingRestoration(SchedulerTask):
            @property
            def run_order_restore_pending(self):
                self.__dict__.pop("run_order_original_roster", None)
                return True

        restoring = FinishingRestoration(task_type=TaskTypes.RUN_ORDER)
        restoring.run_order_original_roster = {"room_2_1": ["但书"]}
        task = SchedulerTask(
            task_type=TaskTypes.RUN_ORDER,
            task_plan={"room_2_1": ["但书"]},
            meta_data="room_2_1",
        )
        self.run_live(self.scheduler(tasks=[restoring, task]))

        activity = self.get()["activities"]["runorder"]

        self.assertEqual(activity["scheduled_count"], 2)
        self.assertNotIn("blocked_count", activity)
        self.assertNotIn("run_order_original_roster", vars(restoring))

    def test_run_order_queue_can_be_read_while_an_operator_is_added(self):
        from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

        class ObservedOperator:
            @property
            def current_room(self):
                operators["斑点"] = SimpleNamespace(current_room="")
                return "room_2_1"

        operators = {"龙舌兰": ObservedOperator()}
        restoring = SchedulerTask(task_type=TaskTypes.RUN_ORDER)
        restoring.run_order_restore_pending = True
        restoring.run_order_original_roster = {"room_2_1": ["但书"]}
        task = SchedulerTask(
            task_type=TaskTypes.RUN_ORDER,
            task_plan={"room_2_1": ["但书"]},
            meta_data="room_2_1",
        )
        self.run_live(
            self.scheduler(
                tasks=[restoring, task],
                op_data=SimpleNamespace(operators=operators, plan={}),
            )
        )

        activity = self.get()["activities"]["runorder"]

        self.assertEqual(activity["scheduled_count"], 2)
        self.assertEqual(activity["blocked_count"], 1)
        self.assertIn("斑点", operators)

    def test_native_sanity_followup_keeps_its_real_plan_time(self):
        from arknights_mower.solvers.local_operation import FOLLOWUP_TASK_META
        from arknights_mower.utils.scheduler_task import SchedulerTask

        task = SchedulerTask(
            time=datetime(2026, 11, 1, 20, 4, 5, 123456), meta_data=FOLLOWUP_TASK_META
        )
        self.run_live(self.scheduler(tasks=[task]))
        activity = self.get()["activities"]["stage-plan"]
        self.assertEqual(activity["scheduled_count"], 1)
        self.assertEqual(activity["next_task_at"], task.time.astimezone().isoformat())

    def test_untyped_staffing_plan_is_base_work_but_empty_probe_is_not(self):
        from arknights_mower.utils.scheduler_task import SchedulerTask

        task = SchedulerTask(
            time=datetime(2026, 11, 1, 20),
            task_plan={"dormitory_1": ["Current", "砾", "Free"]},
        )
        self.run_live(self.scheduler(tasks=[SchedulerTask(), task]))
        activity = self.get()["activities"]
        self.assertEqual(activity["base"]["scheduled_count"], 1)
        self.assertEqual(activity["dorm"]["scheduled_count"], 1)

    def test_large_queue_reports_partial_counts_without_fabricating_next_time(self):
        from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

        task = SchedulerTask(
            time=datetime(2026, 11, 1, 20), task_type=TaskTypes.RUN_ORDER
        )
        self.run_live(self.scheduler(tasks=[task] * 10_001))
        activity = self.get()["activities"]["runorder"]
        self.assertEqual(activity["scheduled_count"], 10_000)
        self.assertTrue(activity["queue_truncated"])
        self.assertNotIn("next_task_at", activity)
