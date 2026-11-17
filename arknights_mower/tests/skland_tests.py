import datetime
import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

# mastery_view_tests 等模块收集期会先往 sys.modules 塞 skland 的 MagicMock 桩
# （历史原因：skland 导入时 get_d_id 会联网）。本测试需要真实模块：删桩后导入
# （导入已惰性化、不再联网），测试结束恢复桩，避免影响后续依赖该桩的测试。
_saved_skland = sys.modules.get("arknights_mower.utils.skland")
sys.modules.pop("arknights_mower.utils.skland", None)
from arknights_mower.solvers import skland as sign_module  # noqa: E402
from arknights_mower.utils import (  # noqa: E402
    skland,
    skland_log,
)
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.skland_statistics import (  # noqa: E402
    ACCOUNT_FAILED,
    ACCOUNT_RECOVERED,
    read_history,
    read_sign_in_state,
)


def tearDownModule():
    sys.modules["arknights_mower.utils.skland"] = _saved_skland


# 服务器 Date 头 / 错误响应 timestamp 用的服务器时刻；SERVER_EPOCH 由其派生，
# 二者共用同一来源，避免手写成对之后改一个漏一个
SERVER_DATE = "Fri, 28 Aug 2026 23:43:24 GMT"
SERVER_EPOCH = int(
    datetime.datetime.strptime(SERVER_DATE, "%a, %d %b %Y %H:%M:%S GMT")
    .replace(tzinfo=datetime.timezone.utc)
    .timestamp()
)
# 测试里 mock 的本机 epoch（比服务器快 10 秒，对应真实偏差）
LOCAL_EPOCH = SERVER_EPOCH + 10


class TestDeviceRequestCryptoCompatibility(unittest.TestCase):
    def test_legacy_field_ciphertext_is_preserved_without_deprecation_warning(self):
        from cryptography.utils import CryptographyDeprecationWarning

        from arknights_mower.utils import SecuritySm

        with warnings.catch_warnings():
            warnings.simplefilter("error", CryptographyDeprecationWarning)
            encrypted = SecuritySm._DES(
                {"appId": "default", "platform": "Win32", "time": 0, "protocol": 102}
            )
        self.assertEqual(
            encrypted,
            {
                "xx": "Xoz/PL65pzA=",
                "gm": "HvYa39S0OS4=",
                "nb": "xkZOSOvhiVg=",
                "protocol": 102,
            },
        )


class TestSyncServerTime(unittest.TestCase):
    def setUp(self):
        skland.server_time_offset = 0

    def test_sync_from_date_header(self):
        resp = Mock()
        resp.headers = {"Date": SERVER_DATE}
        resp.json = Mock(return_value={})
        with patch("time.time", return_value=LOCAL_EPOCH):
            skland._sync_server_time(resp)
        self.assertEqual(skland.server_time_offset, SERVER_EPOCH - LOCAL_EPOCH)

    def test_sync_from_body_timestamp(self):
        resp = Mock()
        resp.headers = {}
        resp.json = Mock(return_value={"timestamp": str(SERVER_EPOCH)})
        with patch("time.time", return_value=LOCAL_EPOCH):
            skland._sync_server_time(resp)
        self.assertEqual(skland.server_time_offset, SERVER_EPOCH - LOCAL_EPOCH)

    def test_sync_no_source_keeps_offset(self):
        skland.server_time_offset = 7
        resp = Mock()
        resp.headers = {}
        resp.json = Mock(return_value={})
        skland._sync_server_time(resp)
        self.assertEqual(skland.server_time_offset, 7)


class TestGenerateSignatureTimestamp(unittest.TestCase):
    def setUp(self):
        skland.server_time_offset = 0

    def test_timestamp_uses_server_offset(self):
        skland.server_time_offset = 10
        with (
            patch("time.time", return_value=LOCAL_EPOCH),
            patch.object(skland, "_ensure_device_id", return_value="B123"),
        ):
            _, header_ca = skland.generate_signature("tok", "/api/path", "a=1")
        self.assertEqual(header_ca["timestamp"], str(LOCAL_EPOCH + 10 - 2))
        # 签名输入携带真实平台/设备/版本字段，与请求头一致
        self.assertEqual(header_ca["platform"], "1")
        self.assertEqual(header_ca["vName"], "1.62.0")
        self.assertEqual(header_ca["dId"], "B123")

    def test_zero_offset_keeps_minus_two(self):
        # 偏移为 0（本机时钟准）时保持原 -2 秒行为，零回归
        with (
            patch("time.time", return_value=1000000000),
            patch.object(skland, "_ensure_device_id", return_value="B123"),
        ):
            _, header_ca = skland.generate_signature("tok", "/api/path", "")
        self.assertEqual(header_ca["timestamp"], "999999998")


class TestGetBindingList(unittest.TestCase):
    def setUp(self):
        skland.server_time_offset = 0
        # get_sign_header 走 generate_signature，会调 _ensure_device_id，隔离设备指纹网络
        self._did = patch.object(skland, "_ensure_device_id", return_value="B123")
        self._did.start()

    def tearDown(self):
        self._did.stop()

    def _resp(self, body):
        fake = Mock()
        fake.headers = {}
        fake.json = Mock(return_value=body)
        return fake

    def test_error_without_data_returns_empty(self):
        # 非 0 code 的错误响应没有 data 字段，原代码掉进 resp["data"]["list"] 崩 KeyError
        fake = self._resp({"code": 1000, "message": "请勿修改设备本地时间"})
        with patch("requests.get", return_value=fake):
            self.assertEqual(skland.get_binding_list("tok"), [])

    def test_error_message_is_logged_with_credentials_redacted(self):
        fake = self._resp(
            {"code": 1000, "message": "服务暂时不可用，账号 13800138000 secret-token"}
        )
        with (
            patch("requests.get", return_value=fake),
            patch.object(skland.logger, "info") as info,
        ):
            self.assertEqual(skland.get_binding_list("secret-token"), [])
        logged = str(info.call_args_list)
        self.assertIn("1000", logged)
        self.assertIn("服务暂时不可用", logged)
        self.assertIn("138****8000", logged)
        self.assertIn("se********en", logged)
        self.assertNotIn("13800138000", logged)
        self.assertNotIn("secret-token", logged)

    def test_not_logged_in_returns_empty(self):
        fake = self._resp({"code": 1000, "message": "用户未登录"})
        with patch("requests.get", return_value=fake):
            self.assertEqual(skland.get_binding_list("tok"), [])

    def test_success_returns_binding_list(self):
        body = {
            "code": 0,
            "data": {
                "list": [
                    {
                        "appCode": "arknights",
                        "bindingList": [{"gameId": 1, "uid": "u1"}],
                    },
                    {
                        "appCode": "endfield",
                        "bindingList": [{"gameId": 3, "uid": "u3"}],
                    },
                    {"appCode": "other", "bindingList": [{"gameId": 9, "uid": "u9"}]},
                ]
            },
        }
        fake = self._resp(body)
        with patch("requests.get", return_value=fake):
            result = skland.get_binding_list("tok")
        self.assertEqual(
            result, [{"gameId": 1, "uid": "u1"}, {"gameId": 3, "uid": "u3"}]
        )


class TestLoginSyncsServerTime(unittest.TestCase):
    def setUp(self):
        skland.server_time_offset = 0

    def test_login_calibrates_offset_and_wires_did(self):
        fake = Mock()
        fake.headers = {"Date": SERVER_DATE}
        fake.json = Mock(return_value={"status": 0, "data": {"token": "abc"}})
        account = Mock(account="13800000000", password="pw")
        fake_did = "B" + "0" * 16
        with (
            patch("requests.post", return_value=fake),
            patch("time.time", return_value=LOCAL_EPOCH),
            patch.object(skland, "_ensure_device_id", return_value=fake_did),
        ):
            token = skland.log(account)
        self.assertEqual(token, "abc")
        self.assertEqual(skland.server_time_offset, SERVER_EPOCH - LOCAL_EPOCH)
        self.assertEqual(skland.header_login["dId"], fake_did)

    def test_login_fails_fast_when_no_did(self):
        # 取不到 dId 时不以空串继续请求，提前抛错而非误报「设备信息无效」
        account = Mock(account="13800000000", password="pw")
        with patch.object(skland, "_ensure_device_id", return_value=""):
            with self.assertRaises(Exception):
                skland.log(account)


class TestEnsureDeviceId(unittest.TestCase):
    def setUp(self):
        skland._device_id = ""
        skland._device_id_failed = False
        # 隔离落盘路径：不触碰真实配置目录
        self._tmp = tempfile.TemporaryDirectory()
        self._did_file = Path(self._tmp.name) / "skland_device_id.json"
        self._patch_file = patch.object(skland, "_DEVICE_ID_FILE", self._did_file)
        self._patch_file.start()
        self.addCleanup(self._patch_file.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def test_uses_persisted_did(self):
        # 有落盘 dId 直接复用、不再联网去取
        self._did_file.write_text(json.dumps({"dId": "Bpersisted"}), "utf-8")
        with patch.object(skland, "get_d_id") as get_d:
            self.assertEqual(skland._ensure_device_id(), "Bpersisted")
            get_d.assert_not_called()

    def test_fetches_and_persists_when_no_persisted(self):
        # 无落盘时才去 fp-it 取，成功后落盘
        with (
            patch.object(skland, "get_d_id", return_value="B123"),
            patch("time.sleep"),
        ):
            self.assertEqual(skland._ensure_device_id(), "B123")
        self.assertEqual(json.loads(self._did_file.read_text("utf-8")), {"dId": "B123"})

    def test_degraded_to_empty_after_retries(self):
        # 设备信息服务持续不可达 → 重试几次后降级为空串，不抛异常；且失败后不再重试
        with (
            patch.object(
                skland, "get_d_id", side_effect=Exception("fp-it down")
            ) as get_d,
            patch("time.sleep"),
        ):
            self.assertEqual(skland._ensure_device_id(), "")
            self.assertEqual(get_d.call_count, skland._DEVICE_ID_RETRIES)
            # 再次触发：应为惰性短路，不再访问设备信息服务
            self.assertEqual(skland._ensure_device_id(), "")
            self.assertEqual(get_d.call_count, skland._DEVICE_ID_RETRIES)

    def test_retries_until_success(self):
        # 服务偶发超时：前几次失败、最后一次成功 → 返回真实 dId，而非降级为空串
        side = [Exception("timeout"), Exception("timeout"), "B123"]
        with (
            patch.object(skland, "get_d_id", side_effect=side) as get_d,
            patch("time.sleep"),
        ):
            self.assertEqual(skland._ensure_device_id(), "B123")
            self.assertEqual(get_d.call_count, skland._DEVICE_ID_RETRIES)
            self.assertFalse(skland._device_id_failed)

    def test_returns_device_id(self):
        with patch.object(skland, "get_d_id", return_value="B123"):
            self.assertEqual(skland._ensure_device_id(), "B123")

    def test_get_cred_invalidates_did_on_device_invalid(self):
        # 换 cred 遇「设备信息无效」→ 清掉内存与落盘 dId，避免连续复用同一个失效 dId
        self._did_file.write_text(json.dumps({"dId": "Bbad"}), "utf-8")
        skland._device_id = "Bbad"
        fake = Mock()
        fake.json = Mock(return_value={"code": 10001, "message": "设备信息无效"})
        with patch("requests.post", return_value=fake):
            with self.assertRaises(Exception):
                skland.get_cred("grant")
        self.assertEqual(skland._device_id, "")
        self.assertFalse(skland._device_id_failed)
        self.assertFalse(self._did_file.exists())


class TestAuthChainNetworkRetry(unittest.TestCase):
    """认证链路网络重试：瞬时网络错误重试、认证被拒不重试。"""

    def setUp(self):
        skland.server_time_offset = 0

    def _resp(self, body, status_code=200):
        fake = Mock()
        fake.headers = {}
        fake.status_code = status_code
        fake.json = Mock(return_value=body)
        return fake

    def test_get_cred_retries_transient_then_succeeds(self):
        # zonai.skland.com 瞬时连接超时 → 重试一次后成功，而非直接抛错中断任务
        good = self._resp({"code": 0, "data": {"cred": "c", "token": "t"}})
        with (
            patch(
                "requests.post",
                side_effect=[requests.exceptions.ConnectTimeout(), good],
            ),
            patch("time.sleep"),
        ):
            self.assertEqual(skland.get_cred("grant"), {"cred": "c", "token": "t"})

    def test_get_cred_raises_after_retries_exhausted(self):
        # 网络持续不可达 → 重试耗尽后抛出最后的瞬时异常，不静默吞掉
        with (
            patch(
                "requests.post", side_effect=requests.exceptions.ConnectTimeout()
            ) as post,
            patch("time.sleep"),
        ):
            with self.assertRaises(requests.exceptions.ConnectTimeout):
                skland.get_cred("grant")
        self.assertEqual(post.call_count, skland._AUTH_NETWORK_RETRIES)

    def test_get_grant_code_retries_transient_then_succeeds(self):
        # as.hypergryph.com 瞬时拒连 → 重试一次后成功
        good = self._resp({"status": 0, "data": {"code": "g"}})
        with (
            patch(
                "requests.post",
                side_effect=[requests.exceptions.ConnectionError(), good],
            ),
            patch("time.sleep"),
        ):
            self.assertEqual(skland.get_grant_code("tok"), "g")

    def test_get_cred_sets_request_timeout(self):
        # 回归护栏：cred 请求必须带超时，避免 connect timeout=None 无限期悬挂
        good = self._resp({"code": 0, "data": {"cred": "c", "token": "t"}})
        with patch("requests.post", return_value=good) as post:
            skland.get_cred("grant")
        self.assertEqual(
            post.call_args.kwargs.get("timeout"), skland._AUTH_REQUEST_TIMEOUT
        )
        self.assertEqual(post.call_count, 1)

    def test_login_retries_transient_then_succeeds(self):
        # 登录请求（as.hypergryph.com）瞬时连接超时 → 重试一次后成功
        fake = self._resp({"status": 0, "data": {"token": "tok"}})
        fake.headers = {"Date": SERVER_DATE}
        account = Mock(account="13800000000", password="pw")
        with (
            patch(
                "requests.post",
                side_effect=[requests.exceptions.ConnectTimeout(), fake],
            ),
            patch("time.time", return_value=LOCAL_EPOCH),
            patch.object(skland, "_ensure_device_id", return_value="B" + "0" * 16),
            patch("time.sleep"),
        ):
            self.assertEqual(skland.log(account), "tok")

    def test_get_binding_list_retries_transient_then_succeeds(self):
        # 仓库扫描取绑定角色列表也是 zonai.skland.com 的直连 GET，瞬时超时同样重试
        body = {
            "code": 0,
            "data": {
                "list": [
                    {
                        "appCode": "arknights",
                        "bindingList": [{"gameId": 1, "uid": "u1"}],
                    },
                ]
            },
        }
        good = self._resp(body)
        with (
            patch(
                "requests.get",
                side_effect=[requests.exceptions.ConnectTimeout(), good],
            ),
            patch.object(skland, "_ensure_device_id", return_value="B123"),
            patch("time.sleep"),
        ):
            self.assertEqual(
                skland.get_binding_list("tok"), [{"gameId": 1, "uid": "u1"}]
            )


class TestSignHeaderFields(unittest.TestCase):
    def setUp(self):
        skland.server_time_offset = 0

    def test_sign_header_carries_real_fields(self):
        # 请求头带上的签名字段与签名输入一致（真实平台/设备/版本，而非空串）
        with patch.object(skland, "_ensure_device_id", return_value="B123"):
            h = skland.get_sign_header(skland.binding_url, "get", None, "tok")
        self.assertEqual(h["platform"], "1")
        self.assertEqual(h["vName"], "1.62.0")
        self.assertEqual(h["dId"], "B123")
        self.assertTrue(h["sign"])

    def test_signature_reproducible_with_same_fields(self):
        # dId 稳定时，同一路径与时间戳下签名可复现，字段自洽不引入随机性
        with (
            patch("time.time", return_value=LOCAL_EPOCH),
            patch.object(skland, "_ensure_device_id", return_value="B123"),
        ):
            s1, _ = skland.generate_signature("tok", "/api/path", "a=1")
        with (
            patch("time.time", return_value=LOCAL_EPOCH),
            patch.object(skland, "_ensure_device_id", return_value="B123"),
        ):
            s2, _ = skland.generate_signature("tok", "/api/path", "a=1")
        self.assertEqual(s1, s2)


class TestSignInRecording(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.solver = sign_module.SKLand()
        self.solver.record_path = self.folder / "skland.csv"
        self.today = datetime.date(2026, 11, 30)
        self.enterContext(
            patch.object(
                sign_module,
                "skland_day",
                side_effect=lambda timestamp=None: (
                    self.today
                    if timestamp is None
                    else skland_log.skland_day(timestamp)
                ),
            )
        )
        self.account = SimpleNamespace(
            account="13800138000",
            arknights_isCheck=True,
            endfield_isCheck=False,
            sign_in_bilibili=False,
            sign_in_official=True,
            sign_in_endfield_official=True,
            sign_in_endfield_bilibili=False,
        )
        self.role = {
            "gameId": 1,
            "uid": "role-1",
            "channelName": "官服",
            "nickName": "私密昵称",
        }
        self.enterContext(
            patch.object(
                sign_module.config,
                "conf",
                SimpleNamespace(skland_info=[self.account]),
            )
        )
        self.enterContext(patch.object(sign_module, "log", return_value="secret-token"))
        self.enterContext(patch.object(sign_module, "get_sign_header", return_value={}))
        self.enterContext(
            patch.object(
                sign_module,
                "get_cred_by_token",
                return_value={"cred": "secret-cred", "token": "sign-token"},
            )
        )
        self.bindings = self.enterContext(
            patch.object(sign_module, "get_binding_list", return_value=[self.role])
        )
        self.post = self.enterContext(patch.object(sign_module.requests, "post"))

    @staticmethod
    def response(body, date=None):
        return Mock(headers={"Date": date}, json=Mock(return_value=body))

    def test_signing_without_enabled_accounts_is_skipped(self):
        self.account.sign_in_official = False
        with patch.object(sign_module.logger, "warning") as warning:
            self.assertIsNone(self.solver.start())
        sign_module.log.assert_not_called()
        self.post.assert_not_called()
        self.assertFalse(self.solver.record_path.exists())
        self.assertIn("未启用任何账号", warning.call_args.args[0])

    def test_signing_without_enabled_bindings_remains_incomplete(self):
        self.bindings.return_value = []
        with patch.object(sign_module.logger, "warning") as warning:
            self.assertFalse(self.solver.start())
        self.post.assert_not_called()
        (failure,) = read_history(self.solver.record_path)
        self.assertEqual(failure.outcome, ACCOUNT_FAILED)
        self.assertEqual(failure.game, "")
        self.assertIsNone(failure.role_key)
        self.assertIn("没有可签到的已启用角色", failure.reward)
        self.assertNotIn(self.account.account, str(warning.call_args_list))

    def test_unsaved_response_does_not_complete_signing(self):
        self.post.return_value = self.response({"code": 0, "data": {"awards": []}})
        with patch.object(sign_module, "append_dict_rows", side_effect=OSError):
            self.assertFalse(self.solver.start())
        self.post.assert_called_once()
        self.assertFalse(self.solver.record_path.exists())

    def test_encoding_failure_does_not_leave_a_partial_event(self):
        self.post.return_value = self.response(
            {
                "code": 0,
                "data": {
                    "awards": [
                        {"resource": {"name": "龙门币"}},
                        {"resource": {"name": "奖励🎁"}},
                    ]
                },
            }
        )
        self.solver.record_path.write_text("", encoding="gbk")

        self.assertFalse(self.solver.start())
        self.assertEqual(self.solver.record_path.read_bytes(), b"")
        self.assertFalse(self.solver.start())
        self.assertEqual(self.post.call_count, 2)

    def test_multi_reward_event_writes_a_completion_marker(self):
        self.post.return_value = self.response(
            {
                "code": 0,
                "data": {
                    "awards": [
                        {"resource": {"name": "龙门币"}, "count": 5},
                        {"resource": {"name": "赤金"}, "count": 7},
                    ]
                },
            }
        )

        self.assertTrue(self.solver.start())

        rows = self.solver.record_path.read_text(encoding="gbk").splitlines()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1].split(",")[4], "event_committed")
        completed, failures, _ = read_sign_in_state(self.solver.record_path)
        self.assertEqual(len(completed), 1)
        self.assertFalse(failures)

    def test_partially_written_event_is_retried_and_not_completed(self):
        # 上一次签到只写入了同一事件的第一条奖励，完成标记没有落盘。
        today = self.today.strftime("%Y/%m/%d")
        role_key = sign_module.sign_role_key(
            self.account.account, "明日方舟官服", self.role["uid"]
        )
        self.solver.record_path.write_text(
            f"{today},13800138000,明日方舟官服,龙门币×500,success,0,"
            f"{role_key},{'a' * 32}\n",
            encoding="gbk",
        )
        self.post.return_value = self.response({"code": 0, "data": {"awards": []}})

        self.assertTrue(self.solver.start())

        self.post.assert_called_once()
        completed, failures, _ = read_sign_in_state(self.solver.record_path)
        self.assertEqual(len(completed), 1)
        self.assertFalse(failures)
        (record,) = read_history(self.solver.record_path)
        self.assertNotEqual(record.event_id, "a" * 32)

    def test_login_failure_keeps_the_next_account_eligible(self):
        second = SimpleNamespace(**{**vars(self.account), "account": "13900139000"})
        sign_module.config.conf.skland_info.append(second)
        sign_module.log.side_effect = (
            RuntimeError(f"登录失败：{self.account.account} provider-text"),
            "secret-token",
        )
        self.post.return_value = self.response({"code": 0, "data": {"awards": []}})

        with patch.object(sign_module.logger, "warning") as warning:
            results = self.solver.test_sign()

        self.assertEqual(sign_module.log.call_count, 2)
        self.post.assert_called_once()
        failure, record = read_history(self.solver.record_path)
        self.assertEqual(failure.account, "138****8000")
        self.assertEqual(failure.outcome, ACCOUNT_FAILED)
        self.assertEqual(failure.game, "")
        self.assertIsNone(failure.role_key)
        self.assertEqual(record.account, "139****9000")
        self.assertEqual(record.outcome, "signed")
        self.assertIn("登录失败", results[-1])
        self.assertNotIn(self.account.account, results[-1])
        self.assertNotIn(self.account.account, str(warning.call_args_list))
        self.assertNotIn(
            "provider-text", self.solver.record_path.read_text(encoding="gbk")
        )

    def test_binding_lookup_recovers_even_if_roles_are_already_signed(self):
        self.post.return_value = self.response({"code": 0, "data": {"awards": []}})
        self.bindings.side_effect = ([self.role], requests.Timeout(), [self.role])

        self.assertTrue(self.solver.start())
        self.assertFalse(self.solver.start())
        self.assertTrue(self.solver.start())

        self.post.assert_called_once()
        signed, failure, recovered = read_history(self.solver.record_path)
        self.assertEqual(signed.outcome, "signed")
        self.assertEqual(failure.outcome, ACCOUNT_FAILED)
        self.assertIn("读取森空岛签到角色失败", failure.reward)
        self.assertEqual(recovered.outcome, ACCOUNT_RECOVERED)
        self.assertEqual((failure.date, recovered.date), (signed.date, signed.date))
        self.assertEqual(recovered.game, "")
        self.assertIsNone(recovered.role_key)

    def test_cancellation_exits_at_authentication_or_signing(self):
        for operation in (sign_module.log, self.post):
            with self.subTest(operation=operation):
                operation.side_effect = MowerExit
                try:
                    with self.assertRaises(MowerExit):
                        self.solver.start()
                finally:
                    operation.side_effect = None
        self.assertFalse(self.solver.record_path.exists())

    def test_manual_signing_test_keeps_the_provider_failure_message(self):
        self.post.return_value = self.response(
            {"code": 22, "message": "服务暂时不可用"}
        )
        (result,) = self.solver.test_sign()
        self.assertIn("签到失败，服务暂时不可用", result)

    def test_signing_logs_keep_server_message_and_redact_identity(self):
        solver = self.solver
        responses = (
            {
                "code": 1000,
                "message": "今日已签到：私密昵称 13800138000 secret-token",
            },
            {"code": 0, "data": {"awards": [{"resource": {"name": "龙门币"}}]}},
        )
        for response in responses:
            with self.subTest(response_code=response["code"]):
                solver.record_path = self.folder / f"privacy-{response['code']}.csv"
                self.post.return_value = self.response(response)
                with patch.object(sign_module.logger, "info") as info:
                    self.assertTrue(solver.start())
                logged = str(info.call_args_list)
                parsed = read_history(solver.record_path)[0]
                for secret in (
                    "私密昵称",
                    "13800138000",
                    "secret-token",
                    "secret-cred",
                ):
                    self.assertNotIn(secret, logged)
                    self.assertNotIn(secret, parsed.reward)
                if response["code"]:
                    self.assertIn("1000", logged)
                    self.assertIn("今日已签到", logged)
                self.assertTrue(solver.reward)
                self.assertEqual(solver.reward[0]["code"], response["code"])
                self.assertEqual(
                    solver.reward[0]["status"],
                    "failure" if response["code"] else "success",
                )

    def test_failed_rows_do_not_count_as_signed_today(self):
        today = self.today.strftime("%Y/%m/%d")
        role_key = skland_log.sign_role_key("13800138000", "明日方舟官服", "role-1")
        cases = (
            ("服务暂时不可用", "failure", False),
            ("请勿重复签到！", "failure", True),
            ("龙门币×500", "success", True),
        )
        self.post.return_value = self.response({"code": 0, "data": {"awards": []}})
        solver = self.solver
        for reward, status, expected in cases:
            with self.subTest(status=status, reward=reward):
                self.post.reset_mock()
                solver.record_path.write_text(
                    f"{today},13800138000,明日方舟官服,{reward},{status},1,{role_key}\n",
                    encoding="gbk",
                )
                self.assertTrue(solver.start())
                self.assertEqual(self.post.call_count, 0 if expected else 1)

    def test_legacy_row_stays_readable_and_never_skips_the_observed_role(self):
        today = self.today.strftime("%Y/%m/%d")
        solver = self.solver
        self.post.return_value = self.response({"code": 1000, "message": "今日已签到"})
        for encoding in ("gbk", "utf-8-sig"):
            with self.subTest(encoding=encoding):
                self.post.reset_mock()
                solver.record_path.write_text(
                    f"{today},13800138000,明日方舟官服,龙门币×500,success,0\n",
                    encoding=encoding,
                )
                self.assertTrue(solver.start())
                self.assertTrue(solver.start())
                self.post.assert_called_once()
                legacy, scoped = read_history(solver.record_path)
                self.assertEqual((legacy.item, legacy.count), ("龙门币", 500))
                self.assertIsNone(legacy.role_key)
                self.assertEqual(scoped.outcome, "repeated")
                self.assertTrue(scoped.event_id)
                self.assertTrue(scoped.role_key)

    def test_same_region_retry_only_signs_the_failed_role(self):
        self.account.arknights_isCheck = False
        self.account.endfield_isCheck = True
        self.bindings.return_value = [
            {
                "gameId": 3,
                "channelName": "官服",
                "roles": [
                    {"roleId": "role-A", "serverId": "1"},
                    {"roleId": "role-B", "serverId": "1"},
                ],
            }
        ]
        today = self.today.strftime("%Y/%m/%d")
        self.solver.record_path.write_text(
            f"{today},13800138000,终末地官服,折金票×50,success,0\n",
            encoding="gbk",
        )
        success = self.response(
            {
                "code": 0,
                "data": {
                    "awardIds": [{"id": "item"}],
                    "resourceInfoMap": {"item": {"name": "折金票", "count": 100}},
                },
            }
        )
        failure = self.response({"code": 22, "message": "签到服务暂时不可用"})
        self.post.side_effect = (success, failure, success)

        self.assertFalse(self.solver.start())
        self.assertTrue(self.solver.start())
        roles = [call.kwargs["json"]["roleId"] for call in self.post.call_args_list]
        self.assertEqual(roles, ["role-A", "role-B", "role-B"])
        first, failed, recovered = read_history(self.solver.record_path)[1:]
        self.assertNotEqual(first.role_key, failed.role_key)
        self.assertEqual(failed.role_key, recovered.role_key)
        self.assertEqual(
            [first.outcome, failed.outcome, recovered.outcome],
            ["signed", "failed", "signed"],
        )
        self.assertNotIn("role-B", self.solver.record_path.read_text(encoding="gbk"))

    def test_role_failures_are_saved_and_do_not_skip_the_next_role(self):
        self.bindings.return_value = [
            {**self.role, "uid": f"role-{index}"} for index in range(1, 5)
        ]
        self.post.side_effect = (
            self.response(
                {
                    "code": 0,
                    "data": {
                        "awards": [
                            {"resource": {"name": "龙门币"}, "count": 3},
                            {"resource": {"name": "龙门币"}, "count": 2},
                            {"resource": {"name": "赤金"}, "count": 7},
                        ]
                    },
                },
                "Mon, 30 Nov 2026 16:02:00 GMT",
            ),
            requests.exceptions.ConnectionError("连接中断 secret-token"),
            self.response(None, "Mon, 30 Nov 2026 16:02:00 GMT"),
            self.response({"code": 0, "data": {"awards": []}}),
        )
        self.assertFalse(self.solver.start())

        first, second, connection, malformed, last = read_history(
            self.solver.record_path
        )
        self.assertEqual((first.date, second.date), (datetime.date(2026, 12, 1),) * 2)
        self.assertEqual((first.item, first.count), ("龙门币", 5))
        self.assertEqual((second.item, second.count), ("赤金", 7))
        self.assertTrue(first.event_id)
        self.assertEqual(first.event_id, second.event_id)
        self.assertEqual(connection.date, self.today)
        self.assertEqual(malformed.date, datetime.date(2026, 12, 1))
        self.assertEqual(
            [connection.outcome, malformed.outcome, last.outcome],
            ["failed", "failed", "signed"],
        )
        self.assertEqual(
            [call.kwargs["json"]["uid"] for call in self.post.call_args_list],
            ["role-1", "role-2", "role-3", "role-4"],
        )
        self.assertNotIn(
            "secret-token", self.solver.record_path.read_text(encoding="gbk")
        )

    def test_record_log_omits_reward_account_data(self):
        solver = self.solver
        solver.reward = [
            {"nickName": "13800138000", "game": "明日方舟官服", "reward": "私密奖励"}
        ]
        with patch.object(sign_module.logger, "info") as info:
            self.assertTrue(solver.record_log())
        logged = str(info.call_args_list)
        self.assertNotIn("13800138000", logged)
        self.assertIn("138****8000", logged)
        self.assertIn("私密奖励", logged)
        self.assertIn("    账号 138****8000：", logged)
        self.assertIn("        明日方舟官服：签到结果，私密奖励", logged)
        self.assertIn("的森空岛签到记录，共 1 条：", logged)

    def test_redaction_preserves_text_and_hides_known_secrets(self):
        conf = SimpleNamespace(
            skland_info=[
                SimpleNamespace(account="user@example.com", password="secret-password")
            ]
        )
        with patch.object(skland_log.config, "conf", conf):
            result = skland_log.redact_signing_text(
                "签到失败 user@example.com 13800138000 secret-password 角色昵称 token-123",
                "角色昵称",
                "token-123",
            )
        self.assertIn("签到失败", result)
        self.assertIn("u**r@example.com", result)
        self.assertIn("138****8000", result)
        self.assertIn("se***********rd", result)
        self.assertIn("角**称", result)
        self.assertIn("to*****23", result)
        self.assertNotIn("已隐藏", result)
        for secret in (
            "user@example.com",
            "13800138000",
            "secret-password",
            "角色昵称",
            "token-123",
        ):
            self.assertNotIn(secret, result)


if __name__ == "__main__":
    unittest.main()
