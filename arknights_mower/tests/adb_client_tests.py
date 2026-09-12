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
    """ADB 单次失败必须交回设备层，避免内部再发起三次重连。"""

    def test_run_propagates_connection_error_without_reconnecting(self):
        client = _client()
        session = MagicMock()
        session.exec.side_effect = ConnectionError(b"closed")
        with (
            patch.object(client, "session", return_value=session),
            patch.object(client, "reconnect") as reconnect,
            self.assertRaisesRegex(ConnectionError, "closed"),
        ):
            client.run("screencap")
        session.exec.assert_called_once_with("screencap")
        reconnect.assert_not_called()

    def test_run_returns_successful_response(self):
        client = _client()
        with patch.object(client, "session") as session:
            session.return_value.exec.return_value = b"ok"
            self.assertEqual(client.run("screencap"), b"ok")
            session.return_value.exec.assert_called_once_with("screencap")

    def test_server_check_does_not_retry_or_restart(self):
        client = _client()
        with (
            patch("arknights_mower.utils.device.adb_client.core.Session") as session,
            patch.object(client, "_Client__exec") as execute,
        ):
            session.return_value.run.side_effect = ConnectionError("closed")
            self.assertFalse(client.check_server_alive())
            session.return_value.run.assert_called_once_with("host:version")
            execute.assert_not_called()

    def test_available_devices_excludes_offline_and_unauthorized(self):
        with patch("arknights_mower.utils.device.adb_client.core.Session") as session:
            session.return_value.devices_list.return_value = [
                ("offline-device", "offline"),
                ("unauthorized-device", "unauthorized"),
                ("online-device", "device"),
            ]
            self.assertEqual(_client()._Client__available_devices(), ["online-device"])


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

    def test_first_connection_fails_without_waiting_for_missing_or_offline_device(self):
        from arknights_mower.utils.device.device import Device

        target = "127.0.0.1:16928"
        for devices in (
            [],
            [(target, "offline")],
            [(target, "unauthorized")],
            [("127.0.0.1:16416", "device")],
        ):
            with (
                self.subTest(devices=devices),
                patch.object(config.conf, "adb", target),
                patch.object(config.conf.simulator, "wait_time", 60),
                patch.object(Client, "_Client__check_adb", return_value=True),
                patch.object(Client, "_Client__exec"),
                patch(
                    "arknights_mower.utils.device.adb_client.core.query_mumu_adb_port",
                    return_value=None,
                ),
                patch(
                    "arknights_mower.utils.device.adb_client.core.Session"
                ) as session,
                patch("arknights_mower.utils.device.adb_client.core.csleep") as sleep,
            ):
                session.return_value.devices_list.return_value = devices
                with self.assertRaisesRegex(RuntimeError, "Device connection failure"):
                    Device(wait_for_device=False)
                # 只保留 ADB server 的初始探测延时，不耗完 60 秒的模拟器启动窗口。
                sleep.assert_called_once_with(1)

    def test_first_connection_uses_ready_device_without_waiting(self):
        target = "127.0.0.1:16928"
        with (
            patch.object(config.conf, "adb", target),
            patch.object(Client, "_Client__exec"),
            patch("arknights_mower.utils.device.adb_client.core.Session") as session,
            patch("arknights_mower.utils.device.adb_client.core.csleep") as sleep,
        ):
            session.return_value.devices_list.return_value = [(target, "device")]
            client = Client(adb_bin="adb", wait_for_device=False)
        self.assertEqual(client.device_id, target)
        sleep.assert_called_once_with(1)

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
