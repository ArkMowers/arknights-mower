import unittest
from unittest.mock import MagicMock, patch

from arknights_mower.utils import config
from arknights_mower.utils.device.adb_client.core import Client


def _client() -> Client:
    client = object.__new__(Client)
    client.device_id = "127.0.0.1:16928"
    client.adb_bin = "adb"
    return client


class TestAdbClientConnectionError(unittest.TestCase):
    """#157：run()/__run() 的重连循环必须兜住 base ConnectionError(b'closed')。

    此前 except 元组是 (socket.timeout, ConnectionRefusedError, RuntimeError)，
    server 拆线抛的 b'closed' 是 base ConnectionError（非 ConnectionRefusedError
    子类），漏网冒泡到 check_current_focus 的 restart_simulator，杀掉运行中的游戏。
    """

    def test_run_recovers_from_connection_error_b_closed(self):
        client = _client()
        session_mock = MagicMock()
        session_mock.exec.side_effect = [ConnectionError(b"closed"), b"ok"]

        with (
            patch.object(client, "session", return_value=session_mock),
            patch.object(client, "_Client__exec") as exec_mock,
            patch.object(client, "_Client__init_device") as init_device_mock,
            patch(
                "arknights_mower.utils.device.adb_client.core.query_mumu_adb_port",
                return_value=None,
            ),
            patch("arknights_mower.utils.device.adb_client.core.time.sleep"),
        ):
            result = client.run("screencap 2>/dev/null | gzip -1")

        self.assertEqual(result, b"ok")
        self.assertEqual(
            exec_mock.call_args_list[0].args[0], "disconnect 127.0.0.1:16928"
        )
        self.assertEqual(exec_mock.call_args_list[1].args[0], "connect 127.0.0.1:16928")
        init_device_mock.assert_called_once_with()

    def test_available_devices_excludes_offline_and_unauthorized(self):
        with patch("arknights_mower.utils.device.adb_client.core.Session") as session:
            session.return_value.devices_list.return_value = [
                ("offline-device", "offline"),
                ("unauthorized-device", "unauthorized"),
                ("online-device", "device"),
            ]
            self.assertEqual(_client()._Client__available_devices(), ["online-device"])

    def test_run_reraises_connection_error_after_retries(self):
        client = _client()
        session_mock = MagicMock()
        session_mock.exec.side_effect = ConnectionError(b"closed")

        with (
            patch.object(client, "session", return_value=session_mock),
            patch.object(client, "_Client__exec"),
            patch.object(client, "_Client__init_device"),
            patch("arknights_mower.utils.device.adb_client.core.time.sleep"),
            self.assertRaisesRegex(ConnectionError, "closed"),
        ):
            client.run("screencap 2>/dev/null | gzip -1")

    def test_run_helper_recovers_from_connection_error(self):
        client = _client()
        with (
            patch(
                "arknights_mower.utils.device.adb_client.core.Session"
            ) as session_cls,
            patch.object(client, "_Client__exec"),
            patch(
                "arknights_mower.utils.device.adb_client.core.query_mumu_adb_port",
                return_value=None,
            ),
            patch("arknights_mower.utils.device.adb_client.core.time.sleep"),
        ):
            session_cls.return_value.run.side_effect = [
                ConnectionError(b"closed"),
                b"0001",
            ]
            result = client.check_server_alive()

        self.assertTrue(result)


class TestInitDeviceWaitsForDevice(unittest.TestCase):
    """模拟器重启/更新后设备未立即在 adb 就绪：__init_device 等待/重发现端口再探测。

    此前只连接一次并立即检查一次，设备端点漂移或仍在注册时就误判失败。
    """

    def _client(self) -> Client:
        client = object.__new__(Client)
        client.device_id = None
        client.connect = None
        client.adb_bin = "adb"
        return client

    def test_succeeds_when_already_present_no_retry(self):
        client = self._client()
        client.device_id = "127.0.0.1:16928"
        with (
            patch.object(client, "_Client__exec"),
            patch.object(client, "_Client__connect_device"),
            patch.object(client, "refresh_target"),
            patch.object(
                client,
                "_Client__available_devices",
                return_value=["127.0.0.1:16928"],
            ),
            patch("arknights_mower.utils.device.adb_client.core.Session"),
            patch("arknights_mower.utils.device.adb_client.core.csleep") as csleep,
        ):
            client._Client__init_device()
        # 已就绪：仅初始 csleep(1)，未进入等待重试。
        csleep.assert_called_once_with(1)

    def test_waits_and_rediscovers_drifted_port(self):
        client = self._client()
        ready = {"flag": False}

        def choose_devices(devices=None):
            if ready["flag"]:
                client.device_id = "127.0.0.1:16416"
            return client.device_id

        def available_devices():
            return ["127.0.0.1:16416"] if ready["flag"] else []

        with (
            patch.object(client, "_Client__exec"),
            patch.object(client, "_Client__connect_device"),
            patch.object(client, "_Client__choose_devices", side_effect=choose_devices),
            patch.object(
                client, "_Client__available_devices", side_effect=available_devices
            ),
            patch(
                "arknights_mower.utils.device.adb_client.core.Session"
            ) as session_cls,
            patch("arknights_mower.utils.device.adb_client.core.csleep") as csleep,
        ):
            # 端口在等待期间才被重新发现并让设备上线
            session_cls.return_value.connect.side_effect = lambda *_: ready.update(
                flag=True
            )
            client._Client__init_device()

        # 重发现到新端口并建立连接
        session_cls.return_value.connect.assert_called_with("127.0.0.1:16416")
        # 等待窗口内重新探测：初始 csleep(1) + 至少一次 csleep(2)
        self.assertGreaterEqual(csleep.call_count, 2)

    def test_adopts_single_live_device_when_no_preferred_port(self):
        client = self._client()
        with (
            patch.object(client, "_Client__exec"),
            patch.object(client, "_Client__connect_device"),
            patch.object(config.conf, "adb", ""),
            patch.object(
                client,
                "_Client__available_devices",
                return_value=["127.0.0.1:16928"],
            ),
            patch(
                "arknights_mower.utils.device.adb_client.core.query_mumu_adb_port",
                return_value=None,
            ),
            patch("arknights_mower.utils.device.adb_client.core.Session"),
            patch("arknights_mower.utils.device.adb_client.core.csleep"),
        ):
            client._Client__init_device()
        # 未配置首选端口时，认领唯一存活设备
        self.assertEqual(client.device_id, "127.0.0.1:16928")

    def test_raises_when_device_never_registers(self):
        client = self._client()
        with (
            patch.object(client, "_Client__exec"),
            patch.object(client, "_Client__connect_device"),
            patch.object(client, "_Client__choose_devices", return_value=None),
            patch.object(client, "_Client__available_devices", return_value=[]),
            patch("arknights_mower.utils.device.adb_client.core.Session"),
            patch("arknights_mower.utils.device.adb_client.core.csleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Device connection failure"):
                client._Client__init_device()


if __name__ == "__main__":
    unittest.main()
