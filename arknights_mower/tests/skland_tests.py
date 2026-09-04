import datetime
import sys
import unittest
from unittest.mock import Mock, patch

# mastery_view_tests 等模块收集期会先往 sys.modules 塞 skland 的 MagicMock 桩
# （历史原因：skland 导入时 get_d_id 会联网）。本测试需要真实模块：删桩后导入
# （导入已惰性化、不再联网），测试结束恢复桩，避免影响后续依赖该桩的测试。
_saved_skland = sys.modules.get("arknights_mower.utils.skland")
sys.modules.pop("arknights_mower.utils.skland", None)
from arknights_mower.utils import skland  # noqa: E402


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


class TestEnsureDeviceId(unittest.TestCase):
    def setUp(self):
        skland._device_id = ""
        skland._device_id_failed = False

    def test_degraded_to_empty_on_failure(self):
        # 设备信息服务不可达 → 降级为空串，不抛异常；且失败一次后不再重试
        with patch.object(
            skland, "get_d_id", side_effect=Exception("fp-it down")
        ) as get_d:
            self.assertEqual(skland._ensure_device_id(), "")
            self.assertEqual(get_d.call_count, 1)
            # 再次触发：应为惰性短路，不再访问设备信息服务
            self.assertEqual(skland._ensure_device_id(), "")
            self.assertEqual(get_d.call_count, 1)

    def test_returns_device_id(self):
        with patch.object(skland, "get_d_id", return_value="B123"):
            self.assertEqual(skland._ensure_device_id(), "B123")


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


if __name__ == "__main__":
    unittest.main()
