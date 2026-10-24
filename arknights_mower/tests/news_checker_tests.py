import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from arknights_mower import __main__ as mower_main
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.news_checker import MaintenanceInfo, NewsChecker
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    adjust_run_order_for_maintenance,
    protect_priority_tasks,
    scheduling,
)


class NewsCheckerTests(unittest.TestCase):
    def setUp(self):
        NewsChecker.last_check_date = None
        NewsChecker.cached_st = None
        NewsChecker.cached_et = None
        NewsChecker.cached_maintenance = None
        NewsChecker.last_check_ts = None
        probe_ids = patch.object(mower_main, "_flash_probe_ids", set())
        probe_ids.start()
        self.addCleanup(probe_ids.stop)
        mower_main._cancel_maintenance_timer()
        config.maintenance_recheck.clear()

    def tearDown(self):
        mower_main._cancel_maintenance_timer()
        config.maintenance_recheck.clear()

    def test_major_update_is_detected_from_client_download_notice(self):
        item = {
            "cid": "5102",
            "title": "[明日方舟]09月04日06:00版本更新停机维护公告",
            "brief": "新版本预下载现已开启",
        }
        detail = (
            "计划将于2026年09月04日06:00至12:00对客户端进行版本更新停机维护。"
            "本次更新为强制更新，需重新下载和安装。"
        )

        info = NewsChecker._parse_maintenance(
            item,
            detail,
            datetime(2026, 9, 2, 12, tzinfo=ZoneInfo("Asia/Shanghai")),
            ZoneInfo("Asia/Shanghai"),
        )

        self.assertEqual(info.update_type, "major")
        self.assertEqual(info.start, datetime(2026, 9, 4, 6))
        self.assertEqual(info.end, datetime(2026, 9, 4, 12))
        self.assertEqual(info.resume_at, datetime(2026, 9, 4, 11, 30))

    def test_flash_update_is_hot_update_without_early_resume(self):
        item = {
            "cid": "7367",
            "title": "[明日方舟]09月11日16:00闪断更新公告",
            "brief": "2026年09月11日16:00 ~ 16:10期间进行服务器闪断更新",
        }

        info = NewsChecker._parse_maintenance(
            item,
            item["brief"],
            datetime(2026, 9, 11, 12, tzinfo=ZoneInfo("Asia/Shanghai")),
            ZoneInfo("Asia/Shanghai"),
        )

        self.assertEqual(info.update_type, "hot")
        self.assertEqual(info.resume_at, datetime(2026, 9, 11, 16, 10))

    def test_maintenance_without_client_package_is_not_major(self):
        item = {
            "cid": "3",
            "title": "[明日方舟]09月12日16:00服务器停机维护公告",
            "brief": "2026年09月12日16:00 ~ 18:00进行服务器维护",
        }

        info = NewsChecker._parse_maintenance(
            item,
            "本次更新无需重新下载客户端，维护结束后可直接登录游戏。",
            datetime(2026, 9, 12, 8, tzinfo=ZoneInfo("Asia/Shanghai")),
            ZoneInfo("Asia/Shanghai"),
        )

        self.assertEqual(info.update_type, "hot")
        self.assertEqual(info.resume_at, datetime(2026, 9, 12, 17, 30))

    def test_24_hour_end_rolls_into_next_day(self):
        item = {
            "cid": "1",
            "title": "服务器闪断更新公告",
            "brief": "2026年09月11日23:50 ~ 24:00",
        }

        info = NewsChecker._parse_maintenance(
            item,
            item["brief"],
            datetime(2026, 9, 11, 12, tzinfo=ZoneInfo("Asia/Shanghai")),
            ZoneInfo("Asia/Shanghai"),
        )

        self.assertEqual(info.end, datetime(2026, 9, 12, 0, 0))

    def test_major_update_window_ends_half_an_hour_early(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 4, 6),
            end=datetime(2026, 9, 4, 12),
            update_type="major",
            title="版本更新停机维护公告",
            url="https://example.test/news/1",
            announcement_id="1",
        )

        self.assertTrue(info.active_at(datetime(2026, 9, 4, 6)))
        self.assertTrue(info.active_at(datetime(2026, 9, 4, 11, 29, 59)))
        self.assertFalse(info.active_at(datetime(2026, 9, 4, 11, 30)))
        self.assertEqual(info.resume_at, info.end - timedelta(minutes=30))

    def test_major_update_stops_instead_of_sleeping(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 4, 6),
            end=datetime(2026, 9, 4, 12),
            update_type="major",
            title="版本更新停机维护公告",
            url="https://example.test/news/1",
            announcement_id="1",
        )
        scheduler = Mock()

        with patch.object(mower_main, "_stop_for_major_update") as stop:
            stopped = mower_main._handle_maintenance(
                info, scheduler, datetime(2026, 9, 4, 6)
            )

        self.assertTrue(stopped)
        stop.assert_called_once_with(info)
        scheduler._idle_sleep.assert_not_called()

    def test_hot_update_pauses_until_announced_end(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 11, 16),
            end=datetime(2026, 9, 11, 16, 10),
            update_type="hot",
            title="闪断更新公告",
            url="https://example.test/news/2",
            announcement_id="2",
        )
        scheduler = Mock()
        scheduler.tasks = []

        with patch.object(mower_main, "logger"):
            stopped = mower_main._handle_maintenance(
                info, scheduler, datetime(2026, 9, 11, 16, 5)
            )

        self.assertFalse(stopped)
        scheduler.handle_idle_action.assert_called_once_with(300)
        scheduler._idle_sleep.assert_called_once_with(300, allow_wakeup=False)

    def test_flash_update_probes_at_two_minutes_for_recent_task(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 11, 16),
            end=datetime(2026, 9, 11, 16, 10),
            update_type="hot",
            title="闪断更新公告",
            url="https://example.test/news/2",
            announcement_id="2",
        )
        scheduler = Mock()
        scheduler.tasks = [SimpleNamespace(time=datetime(2026, 9, 11, 16, 12))]

        with patch.object(mower_main, "logger"):
            stopped = mower_main._handle_maintenance(
                info, scheduler, datetime(2026, 9, 11, 16)
            )

        self.assertFalse(stopped)
        scheduler.handle_idle_action.assert_called_once_with(120)
        scheduler._idle_sleep.assert_called_once_with(120, allow_wakeup=False)
        self.assertIn(info.announcement_id, mower_main._flash_probe_ids)

        scheduler.reset_mock()
        for minute in (2, 3, 5, 9):
            self.assertFalse(
                mower_main._handle_maintenance(
                    info, scheduler, datetime(2026, 9, 11, 16, minute)
                )
            )
        scheduler.handle_idle_action.assert_not_called()
        scheduler._idle_sleep.assert_not_called()

    def test_flash_update_first_check_after_two_minutes_does_not_sleep(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 11, 16),
            end=datetime(2026, 9, 11, 16, 10),
            update_type="hot",
            title="闪断更新公告",
            url="https://example.test/news/2",
            announcement_id="2",
        )
        scheduler = Mock()
        scheduler.tasks = [SimpleNamespace(time=datetime(2026, 9, 11, 16, 3))]

        self.assertFalse(
            mower_main._handle_maintenance(
                info, scheduler, datetime(2026, 9, 11, 16, 2)
            )
        )

        scheduler._idle_sleep.assert_not_called()
        self.assertIn(info.announcement_id, mower_main._flash_probe_ids)

    def test_interrupted_flash_wait_does_not_admit_early_probe(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 11, 16),
            end=datetime(2026, 9, 11, 16, 10),
            update_type="hot",
            title="闪断更新公告",
            url="https://example.test/news/2",
            announcement_id="2",
        )
        scheduler = Mock()
        scheduler.tasks = [SimpleNamespace(time=info.start)]
        scheduler._idle_sleep.side_effect = MowerExit

        with self.assertRaises(MowerExit):
            mower_main._handle_maintenance(info, scheduler, info.start)

        self.assertNotIn(info.announcement_id, mower_main._flash_probe_ids)

    def test_flash_probe_does_not_bypass_another_announcement(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 11, 16),
            end=datetime(2026, 9, 11, 16, 10),
            update_type="hot",
            title="闪断更新公告",
            url="https://example.test/news/2",
            announcement_id="2",
        )
        mower_main._flash_probe_ids.add("previous-update")
        scheduler = Mock()
        scheduler.tasks = []

        mower_main._handle_maintenance(info, scheduler, info.start)

        scheduler._idle_sleep.assert_called_once_with(600, allow_wakeup=False)

    def test_flash_update_does_not_probe_without_recent_task(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 11, 16),
            end=datetime(2026, 9, 11, 16, 10),
            update_type="hot",
            title="闪断更新公告",
            url="https://example.test/news/2",
            announcement_id="2",
        )
        scheduler = Mock()
        scheduler.tasks = [SimpleNamespace(time=datetime(2026, 9, 11, 16, 16))]

        with patch.object(mower_main, "logger"):
            mower_main._handle_maintenance(info, scheduler, datetime(2026, 9, 11, 16))

        scheduler._idle_sleep.assert_called_once_with(600, allow_wakeup=False)
        self.assertNotIn(info.announcement_id, mower_main._flash_probe_ids)

    def test_failed_flash_probe_waits_until_announced_end(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 11, 16),
            end=datetime(2026, 9, 11, 16, 10),
            update_type="hot",
            title="闪断更新公告",
            url="https://example.test/news/2",
            announcement_id="2",
        )
        mower_main._flash_probe_ids.add(info.announcement_id)

        with (
            patch.object(NewsChecker, "get_maintenance", return_value=info),
            patch.object(mower_main, "csleep") as sleep,
        ):
            retried = mower_main._wait_before_early_login_retry(
                datetime(2026, 9, 11, 16, 2)
            )

        self.assertTrue(retried)
        sleep.assert_called_once_with(480)

    def test_flash_probe_continues_dispatch_across_cached_announcement_checks(self):
        now = datetime.now()
        info = MaintenanceInfo(
            start=now - timedelta(minutes=6),
            end=now + timedelta(minutes=4),
            update_type="hot",
            title="闪断更新公告",
            url="https://example.test/news/2",
            announcement_id="2",
        )
        tasks = [
            SchedulerTask(time=now - timedelta(minutes=2)),
            SchedulerTask(time=now - timedelta(minutes=1)),
        ]
        original_times = [task.time for task in tasks]
        scheduler = Mock()
        scheduler.tasks = list(tasks)
        scheduler.initialize_operators.return_value = None
        scheduler.op_data.validate_backup_plans.return_value = {"success": True}
        executed = []

        def run_task():
            if not scheduler.tasks:
                raise MowerExit
            executed.append(scheduler.tasks.pop(0))

        scheduler.run.side_effect = run_task
        with (
            patch.object(config.conf, "automatic_rescue_enable", False),
            patch.object(mower_main, "base_scheduler", None),
            patch.object(mower_main, "initialize", return_value=scheduler),
            patch.object(mower_main, "refresh_resource_at_boundary"),
            patch.object(mower_main, "_apply_version_update_resting_threshold"),
            patch("arknights_mower.utils.crash_recovery.checkpoint_start"),
            patch.object(NewsChecker, "get_maintenance", return_value=info),
        ):
            mower_main.simulate(None)

        self.assertEqual(executed, tasks)
        self.assertEqual([task.time for task in executed], original_times)
        self.assertEqual(scheduler.run.call_count, 3)
        scheduler.handle_idle_action.assert_not_called()
        scheduler._idle_sleep.assert_not_called()

    def test_version_update_settings_have_requested_defaults(self):
        conf = Conf()

        self.assertEqual(conf.version_update_resting_threshold, 0.8)
        self.assertEqual(conf.version_update_threshold_advance_hours, 12)

    def test_major_update_threshold_hot_applies_to_all_runtime_plans(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 12, 6),
            end=datetime(2026, 9, 12, 12),
            update_type="major",
            title="版本更新停机维护公告",
            url="https://example.test/news/1",
            announcement_id="1",
        )
        current = SimpleNamespace(resting_threshold=0.65)
        default = SimpleNamespace(resting_threshold=0.65)
        backup = SimpleNamespace(resting_threshold=0.65)
        scheduler = SimpleNamespace(
            op_data=SimpleNamespace(config=current),
            global_plan={
                "default_plan": SimpleNamespace(config=default),
                "backup_plans": [SimpleNamespace(config=backup)],
            },
        )

        with (
            patch.object(config.conf, "version_update_resting_threshold", 0.8),
            patch.object(config.conf, "version_update_threshold_advance_hours", 12),
        ):
            changed = mower_main._apply_version_update_resting_threshold(
                info, scheduler, datetime(2026, 9, 11, 18)
            )

        self.assertTrue(changed)
        self.assertEqual(current.resting_threshold, 0.8)
        self.assertEqual(default.resting_threshold, 0.8)
        self.assertEqual(backup.resting_threshold, 0.8)

    def test_version_update_threshold_restores_daily_value_outside_window(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 12, 6),
            end=datetime(2026, 9, 12, 12),
            update_type="major",
            title="版本更新停机维护公告",
            url="https://example.test/news/1",
            announcement_id="1",
        )
        runtime = SimpleNamespace(resting_threshold=0.8)
        scheduler = SimpleNamespace(
            op_data=SimpleNamespace(config=runtime),
            global_plan={},
        )

        with (
            patch.object(config.conf, "resting_threshold", 0.65),
            patch.object(config.conf, "version_update_threshold_advance_hours", 12),
        ):
            changed = mower_main._apply_version_update_resting_threshold(
                info, scheduler, datetime(2026, 9, 11, 17, 59)
            )

        self.assertTrue(changed)
        self.assertEqual(runtime.resting_threshold, 0.65)

    def test_hot_update_does_not_enable_version_update_threshold(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 12, 6),
            end=datetime(2026, 9, 12, 6, 10),
            update_type="hot",
            title="闪断更新公告",
            url="https://example.test/news/2",
            announcement_id="2",
        )
        runtime = SimpleNamespace(resting_threshold=0.8)
        scheduler = SimpleNamespace(
            op_data=SimpleNamespace(config=runtime),
            global_plan={},
        )

        with (
            patch.object(config.conf, "resting_threshold", 0.65),
            patch.object(config.conf, "version_update_threshold_advance_hours", 12),
        ):
            mower_main._apply_version_update_resting_threshold(
                info, scheduler, datetime(2026, 9, 12, 5)
            )

        self.assertEqual(runtime.resting_threshold, 0.65)

    def test_future_major_update_arms_threshold_wakeup_first(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 12, 6),
            end=datetime(2026, 9, 12, 12),
            update_type="major",
            title="版本更新停机维护公告",
            url="https://example.test/news/1",
            announcement_id="1",
        )
        timer = Mock()

        with (
            patch.object(config.conf, "version_update_threshold_advance_hours", 12),
            patch.object(mower_main, "Timer", return_value=timer) as timer_class,
        ):
            mower_main._arm_maintenance_timer(info, datetime(2026, 9, 11, 17))

        self.assertEqual(timer_class.call_args.args[0], 3600)
        callback = timer_class.call_args.args[1]
        with patch.object(config.wake_scheduler, "set") as wake:
            callback()
        wake.assert_called_once_with()
        self.assertTrue(config.maintenance_recheck.is_set())

    def test_future_major_update_arms_stop_timer(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 4, 6),
            end=datetime(2026, 9, 4, 12),
            update_type="major",
            title="版本更新停机维护公告",
            url="https://example.test/news/1",
            announcement_id="1",
        )
        timer = Mock()

        mower_main._cancel_maintenance_timer()
        with patch.object(mower_main, "Timer", return_value=timer) as timer_class:
            mower_main._arm_maintenance_timer(info, datetime(2026, 9, 4, 5, 30))

        timer_class.assert_called_once()
        self.assertEqual(timer_class.call_args.args[0], 1800)
        self.assertTrue(timer.daemon)
        timer.start.assert_called_once_with()
        mower_main._cancel_maintenance_timer()

    def test_flash_update_timer_wakes_scheduler_for_maintenance(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 11, 16),
            end=datetime(2026, 9, 11, 16, 10),
            update_type="hot",
            title="闪断更新公告",
            url="https://example.test/news/2",
            announcement_id="2",
        )
        timer = Mock()

        with (
            patch.object(mower_main, "Timer", return_value=timer) as timer_class,
            patch.object(config.wake_scheduler, "set") as wake,
        ):
            mower_main._arm_maintenance_timer(info, datetime(2026, 9, 11, 15, 59))
            timer_class.call_args.args[1]()

        self.assertTrue(config.maintenance_recheck.is_set())
        wake.assert_called_once_with()

    def test_major_update_timer_stops_without_hot_update_wakeup(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 4, 6),
            end=datetime(2026, 9, 4, 12),
            update_type="major",
            title="版本更新停机维护公告",
            url="https://example.test/news/1",
            announcement_id="1",
        )
        timer = Mock()

        with (
            patch.object(mower_main, "Timer", return_value=timer) as timer_class,
            patch.object(mower_main, "_stop_for_major_update") as stop,
            patch.object(config.wake_scheduler, "set") as wake,
        ):
            mower_main._arm_maintenance_timer(info, datetime(2026, 9, 4, 5, 59))
            timer_class.call_args.args[1]()

        stop.assert_called_once_with(info)
        wake.assert_not_called()
        self.assertFalse(config.maintenance_recheck.is_set())

    def test_idle_wake_rechecks_maintenance_before_running_task(self):
        now = datetime.now()
        info = MaintenanceInfo(
            start=now,
            end=now + timedelta(minutes=10),
            update_type="hot",
            title="闪断更新公告",
            url="https://example.test/news/2",
            announcement_id="2",
        )
        scheduler = Mock()
        scheduler.tasks = [SchedulerTask(time=now + timedelta(minutes=1))]
        scheduler.initialize_operators.return_value = None
        scheduler.op_data.validate_backup_plans.return_value = {"success": True}

        with (
            patch.object(config.conf, "close_simulator_when_idle", False),
            patch.object(mower_main, "base_scheduler", None),
            patch.object(mower_main, "initialize", return_value=scheduler),
            patch.object(mower_main, "refresh_resource_at_boundary"),
            patch.object(mower_main, "_apply_version_update_resting_threshold"),
            patch.object(
                mower_main,
                "_resume_device_dispatch",
                side_effect=AssertionError("maintenance wake entered device recovery"),
            ) as recover,
            patch.object(
                NewsChecker, "get_maintenance", side_effect=[None, None, info]
            ) as get_maintenance,
            patch.object(mower_main, "_handle_maintenance", side_effect=MowerExit),
        ):
            mower_main.simulate(None)

        scheduler.rest_until_next_task.assert_called_once_with()
        scheduler.run.assert_not_called()
        recover.assert_not_called()
        self.assertEqual(get_maintenance.call_count, 3)

    def test_early_login_failure_retries_in_five_minutes(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 4, 6),
            end=datetime(2026, 9, 4, 12),
            update_type="major",
            title="版本更新停机维护公告",
            url="https://example.test/news/1",
            announcement_id="1",
        )

        with (
            patch.object(NewsChecker, "get_maintenance", return_value=info),
            patch.object(mower_main, "csleep") as sleep,
        ):
            retried = mower_main._wait_before_early_login_retry(
                datetime(2026, 9, 4, 11, 30)
            )

        self.assertTrue(retried)
        sleep.assert_called_once_with(300)

    def test_last_early_login_retry_is_capped_by_official_end(self):
        info = MaintenanceInfo(
            start=datetime(2026, 9, 4, 6),
            end=datetime(2026, 9, 4, 12),
            update_type="major",
            title="版本更新停机维护公告",
            url="https://example.test/news/1",
            announcement_id="1",
        )

        with (
            patch.object(NewsChecker, "get_maintenance", return_value=info),
            patch.object(mower_main, "csleep") as sleep,
        ):
            mower_main._wait_before_early_login_retry(datetime(2026, 9, 4, 11, 58))

        sleep.assert_called_once_with(120)

    def test_server_maintenance_also_retries_early_login(self):
        info = MaintenanceInfo(
            start=datetime(2026, 8, 8, 16),
            end=datetime(2026, 8, 8, 18),
            update_type="hot",
            title="服务器停机维护公告",
            url="https://example.test/news/3",
            announcement_id="3",
        )

        with (
            patch.object(NewsChecker, "get_maintenance", return_value=info),
            patch.object(mower_main, "csleep") as sleep,
        ):
            retried = mower_main._wait_before_early_login_retry(
                datetime(2026, 8, 8, 17, 30)
            )

        self.assertTrue(retried)
        sleep.assert_called_once_with(300)


class DailyResetSchedulingTests(unittest.TestCase):
    def setUp(self):
        conf = Conf(enable_mastery=True, run_order_delay=5)
        conf.run_order_grandet_mode.enable = False
        for replacement in (
            patch.object(config, "conf", conf),
            patch.object(NewsChecker, "get_maintenance", return_value=None),
            patch(
                "requests.sessions.Session.request",
                side_effect=AssertionError("offline test requested network"),
            ),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)

    def local_time(self, hour, minute=0, second=0, day=14):
        return (
            datetime(
                2026, 10, day, hour, minute, second, tzinfo=ZoneInfo("Asia/Shanghai")
            )
            .astimezone()
            .replace(tzinfo=None)
        )

    def test_daily_reset_is_instantaneous_and_rolls_at_four(self):
        for hour, minute, second, expected_day in (
            (0, 0, 0, 14),
            (3, 59, 59, 14),
            (4, 0, 0, 15),
            (4, 0, 1, 15),
            (23, 59, 59, 15),
        ):
            with self.subTest(hour=hour, minute=minute, second=second):
                now = self.local_time(hour, minute, second)
                reset = NewsChecker.get_daily_reset(now)
                self.assertEqual(reset.start, self.local_time(4, day=expected_day))
                self.assertEqual(reset.end, reset.start)
                self.assertEqual(reset.resume_at, reset.start)
                self.assertEqual(reset.update_type, "hot")
                self.assertTrue(reset.is_flash_update)
                self.assertFalse(reset.active_at(reset.start))
                self.assertFalse(reset.allows_early_login)

    def test_reset_uses_server_time_with_a_utc_clock(self):
        now = datetime(2026, 10, 13, 19, 59, tzinfo=ZoneInfo("UTC"))
        reset = NewsChecker.get_daily_reset(now)
        self.assertEqual(reset.start, datetime(2026, 10, 13, 20))
        self.assertEqual(reset.announcement_id, "daily-reset-2026-10-14")

    def test_scheduling_advances_orders_and_preserves_restoration(self):
        now = self.local_time(3)
        before = SchedulerTask(self.local_time(3, 52), task_type=TaskTypes.RUN_ORDER)
        crossing = SchedulerTask(self.local_time(3, 58), task_type=TaskTypes.RUN_ORDER)
        later = SchedulerTask(self.local_time(3, 59), task_type=TaskTypes.RUN_ORDER)
        after = SchedulerTask(self.local_time(4, 5), task_type=TaskTypes.RUN_ORDER)
        outside = SchedulerTask(self.local_time(4, 10), task_type=TaskTypes.RUN_ORDER)
        restore = SchedulerTask(
            self.local_time(3, 59),
            task_type=TaskTypes.RUN_ORDER,
            task_plan={"room_1_1": ["鸿雪"]},
        )
        restore.run_order_original_roster = {"room_1_1": ["鸿雪"]}
        restore.run_order_restore_pending = True
        ordinary = SchedulerTask(self.local_time(5))
        tasks = [before, crossing, later, after, outside, restore, ordinary]

        scheduling(tasks, time_now=now)

        self.assertEqual(before.time, self.local_time(3, 52))
        self.assertEqual(crossing.time, self.local_time(3, 55))
        self.assertEqual(later.time, self.local_time(3, 55))
        self.assertTrue(before.adjusted)
        self.assertTrue(crossing.adjusted)
        self.assertTrue(later.adjusted)
        self.assertEqual(after.time, self.local_time(4, 5))
        self.assertFalse(after.adjusted)
        self.assertEqual(restore.time, self.local_time(3, 59))
        self.assertFalse(restore.adjusted)
        self.assertEqual(outside.time, self.local_time(4, 10))
        self.assertEqual(ordinary.time, self.local_time(5))
        times = [task.time for task in tasks]
        scheduling(tasks, time_now=now)
        self.assertEqual([task.time for task in tasks], times)

    def test_daily_orders_use_configured_entry_delay_and_exact_boundaries(self):
        cases = (
            (5, (3, 49, 59), (3, 49, 59), False),
            (5, (3, 50, 0), (3, 50, 0), True),
            (5, (3, 54, 59), (3, 54, 59), True),
            (5, (3, 55, 0), (3, 55, 0), True),
            (5, (3, 59, 59), (3, 55, 0), True),
            (5, (4, 0, 0), (4, 0, 0), False),
            (5, (4, 5, 0), (4, 5, 0), False),
            (10, (3, 39, 59), (3, 39, 59), False),
            (10, (3, 40, 0), (3, 40, 0), True),
            (10, (3, 49, 59), (3, 49, 59), True),
            (10, (3, 50, 0), (3, 50, 0), True),
            (10, (3, 59, 59), (3, 50, 0), True),
            (10, (4, 0, 0), (4, 0, 0), False),
            (3, (3, 51, 59), (3, 51, 59), False),
            (3, (3, 52, 0), (3, 52, 0), True),
            (3, (3, 56, 59), (3, 56, 59), True),
            (3, (3, 57, 0), (3, 55, 0), True),
            (7.5, (3, 44, 59), (3, 44, 59), False),
            (7.5, (3, 45, 0), (3, 45, 0), True),
            (7.5, (3, 52, 30), (3, 52, 30), True),
            (7.5, (3, 59, 59), (3, 52, 30), True),
        )
        config.conf.run_order_grandet_mode.enable = True
        config.conf.run_order_grandet_mode.buffer_time = 30
        for delay, start, expected, adjusted in cases:
            with self.subTest(delay=delay, start=start):
                config.conf.run_order_delay = delay
                task = SchedulerTask(
                    self.local_time(*start), task_type=TaskTypes.RUN_ORDER
                )
                for _ in range(2):
                    scheduling([task], time_now=self.local_time(3))
                    self.assertEqual(task.time, self.local_time(*expected))
                    self.assertEqual(task.adjusted, adjusted)

    def test_daily_adjustment_is_idempotent_and_keeps_retained_work(self):
        task = SchedulerTask(self.local_time(3, 58), task_type=TaskTypes.RUN_ORDER)
        retained = SchedulerTask(self.local_time(3, 59), task_type=TaskTypes.RUN_ORDER)
        retained.execution_retained = True
        tasks = [task, retained]
        self.assertEqual(
            adjust_run_order_for_maintenance(tasks, now=self.local_time(3)), [task]
        )
        for now in (self.local_time(3), self.local_time(3, 59), self.local_time(4)):
            self.assertEqual(adjust_run_order_for_maintenance(tasks, now=now), [])
            self.assertEqual(task.time, self.local_time(3, 55))
            self.assertTrue(task.adjusted)
            self.assertEqual(retained.time, self.local_time(3, 59))
            self.assertFalse(retained.adjusted)

    def test_after_reset_does_not_adjust_unplanned_orders_retroactively(self):
        before = SchedulerTask(self.local_time(3, 59), task_type=TaskTypes.RUN_ORDER)
        after = SchedulerTask(self.local_time(4, 1), task_type=TaskTypes.RUN_ORDER)
        tasks = [before, after]
        scheduling(tasks, time_now=self.local_time(4))
        self.assertEqual(before.time, self.local_time(3, 59))
        self.assertEqual(after.time, self.local_time(4, 1))
        self.assertFalse(before.adjusted)
        self.assertFalse(after.adjusted)

    def test_announced_maintenance_and_daily_reset_both_advance_orders(self):
        announcement = MaintenanceInfo(
            start=self.local_time(6),
            end=self.local_time(12),
            update_type="major",
            title="版本更新停机维护公告",
            url="https://example.test/news/major",
            announcement_id="major",
        )
        reset_order = SchedulerTask(
            self.local_time(3, 58), task_type=TaskTypes.RUN_ORDER
        )
        maintenance_order = SchedulerTask(
            self.local_time(8), task_type=TaskTypes.RUN_ORDER
        )
        with patch.object(NewsChecker, "get_maintenance", return_value=announcement):
            adjusted = adjust_run_order_for_maintenance(
                [reset_order, maintenance_order], now=self.local_time(3)
            )
            self.assertIs(NewsChecker.get_maintenance(), announcement)
        self.assertCountEqual(adjusted, [reset_order, maintenance_order])
        self.assertEqual(reset_order.time, self.local_time(3, 55))
        self.assertEqual(maintenance_order.time, self.local_time(5, 49, 59))

    def test_overlapping_windows_converge_in_one_pass(self):
        for start, end, original, expected in (
            ((4, 5), (4, 15), (4, 10), (3, 54, 59)),
            ((4, 8), (4, 15), (4, 10), (3, 55, 0)),
            ((3, 58), (4, 10), (3, 59), (3, 47, 59)),
        ):
            with self.subTest(start=start):
                task = SchedulerTask(
                    self.local_time(*original), task_type=TaskTypes.RUN_ORDER
                )
                with patch.object(
                    NewsChecker,
                    "get_update_time",
                    return_value=(self.local_time(*start), self.local_time(*end)),
                ):
                    adjusted = adjust_run_order_for_maintenance(
                        [task], now=self.local_time(3)
                    )
                    self.assertEqual(adjusted, [task])
                    self.assertEqual(task.time, self.local_time(*expected))
                    self.assertEqual(
                        adjust_run_order_for_maintenance(
                            [task], now=self.local_time(3)
                        ),
                        [],
                    )
                    self.assertEqual(task.time, self.local_time(*expected))

    def test_daily_reset_advances_handoffs_through_both_dispatch_entries(self):
        for entry in (scheduling, protect_priority_tasks):
            for hour, minute in ((3, 55), (4, 0)):
                with self.subTest(entry=entry.__name__, hour=hour, minute=minute):
                    task = SchedulerTask(
                        self.local_time(hour, minute), task_type=TaskTypes.SWAP_SUPPORT
                    )
                    entry([task], time_now=self.local_time(3))
                    self.assertEqual(task.time, self.local_time(3, 48, 59))
                    self.assertTrue(task.advance_support_swap)
                    entry([task], time_now=self.local_time(3))
                    self.assertEqual(task.time, self.local_time(3, 48, 59))

    def test_refresh_does_not_pause_or_stop_automation(self):
        reset = NewsChecker.get_daily_reset(self.local_time(3))
        with (
            patch.object(mower_main, "_stop_for_major_update") as stop,
            patch.object(mower_main, "csleep") as sleep,
        ):
            self.assertFalse(mower_main._handle_maintenance(reset, None, reset.start))
        stop.assert_not_called()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
