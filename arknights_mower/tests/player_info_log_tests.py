"""森空岛理智读取的日志：实时日志只显示理智结果和角色读取失败。"""

import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from arknights_mower.solvers import player_info

UTC = datetime.timezone.utc
SENSITIVE = ("secret-password", "13800138000", "123456789", "测试博士")


class PlayerInfoLogTests(unittest.TestCase):
    def setUp(self):
        self.account = SimpleNamespace(
            account="13800138000",
            password="secret-password",
            arknights_isCheck=True,
            sign_in_official=True,
            sign_in_bilibili=False,
            cultivate_select=True,
        )
        self.client = player_info.PlayerInfoClient()
        config_patch = patch.object(
            player_info.config, "conf", SimpleNamespace(skland_info=[self.account])
        )
        config_patch.start()
        self.addCleanup(config_patch.stop)

    def snapshot(self, fetched_at):
        return SimpleNamespace(
            account=self.account.account,
            uid="123456789",
            nickname="测试博士",
            channel="官服",
            current_ap=92,
            full_recovery_time=datetime.datetime(2026, 9, 28, tzinfo=UTC),
            fetched_at=fetched_at,
            raw_ap={"current": 92},
        )

    def test_snapshot_reports_sanity_in_one_user_line(self):
        cases = (
            (datetime.datetime(2026, 9, 27, 20, tzinfo=UTC), "，预计 "),
            (datetime.datetime(2026, 9, 28, 1, tzinfo=UTC), "，已经回满"),
        )
        for fetched_at, tail in cases:
            with self.subTest(tail=tail):
                with self.assertLogs(player_info.logger, "DEBUG") as captured:
                    self.client.log_snapshot(self.snapshot(fetched_at))
                shown = [r for r in captured.records if r.levelname != "DEBUG"]
                self.assertEqual([r.levelname for r in shown], ["INFO"])
                message = shown[0].getMessage()
                self.assertTrue(message.startswith("从森空岛读取到角色 "), message)
                self.assertIn("的理智为 92" + tail, message)
                for record in captured.records:
                    for sensitive in SENSITIVE:
                        self.assertNotIn(sensitive, record.getMessage())

    def test_fetch_details_stay_out_of_live_log(self):
        # 原始理智与按恢复时间计算的值不一致，且没有基建数据：两者都只给开发者看。
        response = {"code": 0, "data": {"status": {"ap": {"current": 5}}}}
        with (
            patch.object(self.client, "_request_signed_json", return_value=response),
            patch.object(self.client, "iter_account_snapshots", return_value=iter(())),
            self.assertLogs(player_info.logger, "DEBUG") as captured,
        ):
            self.client.fetch_snapshot(
                self.account, {"uid": "123456789", "channelName": "官服"}
            )
            self.assertIsNone(self.client.get_first_available_snapshot())
        self.assertEqual({r.levelname for r in captured.records}, {"DEBUG"})

    def test_failed_role_logs_one_error_without_secrets(self):
        binding = {
            "gameId": 1,
            "uid": "123456789",
            "channelName": "官服",
            "nickName": "测试博士",
        }
        error = RuntimeError("secret-password 13800138000 123456789")
        with (
            patch.object(
                self.client, "_get_binding_list_with_retry", return_value=[binding]
            ),
            patch.object(self.client, "fetch_snapshot", side_effect=error),
            self.assertLogs(player_info.logger, "DEBUG") as captured,
        ):
            self.assertEqual(list(self.client.iter_account_snapshots()), [])
        shown = [r for r in captured.records if r.levelname != "DEBUG"]
        self.assertEqual([r.levelname for r in shown], ["ERROR"])
        message = shown[0].getMessage()
        self.assertIn("的信息失败（RuntimeError），跳过这个角色", message)
        for sensitive in SENSITIVE:
            self.assertNotIn(sensitive, message)


if __name__ == "__main__":
    unittest.main()
