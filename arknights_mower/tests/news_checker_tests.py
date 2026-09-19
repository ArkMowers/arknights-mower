import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from arknights_mower import __main__ as mower_main
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.news_checker import MaintenanceInfo, NewsChecker


class NewsCheckerTests(unittest.TestCase):
    def setUp(self):
        NewsChecker.last_check_date = None
        NewsChecker.cached_st = None
        NewsChecker.cached_et = None
        NewsChecker.cached_maintenance = None
        NewsChecker.last_check_ts = None
        mower_main._flash_probe_ids.clear()
        mower_main._cancel_maintenance_timer()

    def tearDown(self):
        mower_main._cancel_maintenance_timer()

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

    def test_flash_update_probes_at_five_minutes_for_recent_task(self):
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
        scheduler.handle_idle_action.assert_called_once_with(300)
        scheduler._idle_sleep.assert_called_once_with(300, allow_wakeup=False)
        self.assertIn(info.announcement_id, mower_main._flash_probe_ids)

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
                datetime(2026, 9, 11, 16, 5)
            )

        self.assertTrue(retried)
        sleep.assert_called_once_with(300)

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


if __name__ == "__main__":
    unittest.main()
