import unittest
from unittest.mock import MagicMock, patch

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


if __name__ == "__main__":
    unittest.main()
