"""Connection-test results must be safe to display and copy."""

import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from arknights_mower.solvers import player_info


class PlayerInfoProbeTests(unittest.TestCase):
    def setUp(self):
        self.account = SimpleNamespace(
            account="13800138000",
            password="secret-password",
            arknights_isCheck=False,
            sign_in_official=False,
            sign_in_bilibili=False,
            cultivate_select=True,
        )
        self.client = player_info.PlayerInfoClient()
        self.config_patch = patch.object(
            player_info.config,
            "conf",
            SimpleNamespace(skland_info=[self.account]),
        )
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)

    def test_success_masks_account_and_role(self):
        snapshot = SimpleNamespace(
            nickname="测试博士",
            uid="123456789",
            current_ap=92,
            full_recovery_time=datetime.datetime(
                2026, 9, 28, tzinfo=datetime.timezone.utc
            ),
        )
        with (
            patch.object(
                self.client,
                "_get_binding_list_with_retry",
                return_value=[
                    {"gameId": 1, "uid": snapshot.uid, "channelName": "bilibili服"}
                ],
            ),
            patch.object(self.client, "fetch_snapshot", return_value=snapshot) as fetch,
        ):
            result = "\n".join(self.client.probe_accounts())
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[1]["uid"], snapshot.uid)
        self.assertIn("连接成功 | AP=92", result)
        self.assertIn("138****8000", result)
        for sensitive in (
            self.account.account,
            self.account.password,
            snapshot.nickname,
            snapshot.uid,
        ):
            self.assertNotIn(sensitive, result)

    def test_snapshot_request_uses_original_uid(self):
        uid = "123456789"
        with patch.object(
            self.client,
            "_request_signed_json",
            return_value={"code": 0, "data": {"status": {"ap": {"current": 210}}}},
        ) as request:
            snapshot = self.client.fetch_snapshot(
                self.account, {"uid": uid, "channelName": "bilibili服"}
            )
        self.assertIs(request.call_args.args[0], self.account)
        self.assertEqual(
            parse_qs(urlsplit(request.call_args.args[2]).query), {"uid": [uid]}
        )
        self.assertEqual(snapshot.uid, uid)

    def test_binding_request_uses_original_account_and_token(self):
        token = "original-sign-token"
        with (
            patch.object(
                player_info, "restore_cached_session", return_value=None
            ) as cached,
            patch.object(
                player_info,
                "refresh_session",
                return_value={"cred": "original-cred", "sign_token": token},
            ) as refresh,
            patch.object(
                player_info, "get_binding_list", return_value=[{"uid": "1"}]
            ) as bindings,
            patch.dict(player_info.header),
        ):
            self.client._get_binding_list_with_retry(self.account)
        cached.assert_called_once_with(self.account.account)
        refresh.assert_called_once_with(self.account)
        bindings.assert_called_once_with(token)

    def test_failure_does_not_echo_exception_secrets(self):
        self.client.sign_token = "sensitive-sign-token"
        error = RuntimeError(
            "request failed: secret-password sensitive-sign-token 13800138000"
        )
        with (
            patch.object(
                self.client, "_get_binding_list_with_retry", side_effect=error
            ),
            patch.object(player_info.logger, "error") as logged,
        ):
            result = "\n".join(self.client.probe_accounts())
        self.assertIn("无法连接（RuntimeError）", result)
        self.assertIn("138****8000", result)
        for sensitive in (
            self.account.account,
            self.account.password,
            self.client.sign_token,
        ):
            self.assertNotIn(sensitive, result)
            self.assertNotIn(sensitive, str(logged.call_args))

    def test_retry_log_omits_account_uid_and_exception_text(self):
        self.client.sign_token = "sensitive-sign-token"
        url = "https://example.test/player/info?uid=123456789"
        error = RuntimeError("secret-password sensitive-sign-token")
        with (
            patch.object(
                self.client, "_ensure_session", side_effect=[None, RuntimeError("stop")]
            ),
            patch.object(player_info, "get_sign_header", return_value={}),
            patch.object(player_info.requests, "request", side_effect=error),
            patch.object(player_info.logger, "info") as logged,
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                self.client._request_signed_json(self.account, "get", url)
        entry = str(logged.call_args)
        self.assertIn("/player/info", entry)
        for sensitive in (
            self.account.account,
            self.account.password,
            self.client.sign_token,
            "123456789",
        ):
            self.assertNotIn(sensitive, entry)

    def test_snapshot_log_masks_identifiers(self):
        snapshot = SimpleNamespace(
            account=self.account.account,
            uid="123456789",
            nickname="测试博士",
            channel="官服",
            current_ap=92,
            full_recovery_time=datetime.datetime(
                2026, 9, 28, tzinfo=datetime.timezone.utc
            ),
            raw_ap={"current": 92},
        )
        with patch.object(player_info.logger, "info") as logged:
            self.client.log_snapshot(snapshot)
        entry = str(logged.call_args)
        self.assertIn("92", entry)
        for sensitive in (snapshot.account, snapshot.uid, snapshot.nickname):
            self.assertNotIn(sensitive, entry)


if __name__ == "__main__":
    unittest.main()
