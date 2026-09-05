import unittest
from unittest import mock

import server


class TestWebviewConn(unittest.TestCase):
    """连接获取：进程存活才返回 parent_conn，未启动/已退出返回 None。"""

    def test_returns_live_conn(self):
        process = mock.Mock()
        process.is_alive.return_value = True
        conn = mock.Mock()
        with (
            mock.patch.object(server.config, "webview_process", process, create=True),
            mock.patch.object(server.config, "parent_conn", conn, create=True),
        ):
            self.assertIs(server._webview_conn(), conn)

    def test_none_when_process_not_started(self):
        # 启动初期 webview_process 尚未创建，不应误取到连接
        with mock.patch.object(server.config, "webview_process", None, create=True):
            self.assertIsNone(server._webview_conn())

    def test_none_when_process_dead(self):
        process = mock.Mock()
        process.is_alive.return_value = False
        with mock.patch.object(server.config, "webview_process", process, create=True):
            self.assertIsNone(server._webview_conn())


class TestRequestTitleRefresh(unittest.TestCase):
    """标题刷新发送主进程的资源版本，不 recv；进程不可用或发送失败均静默。"""

    def test_sends_title_without_recv(self):
        process = mock.Mock()
        process.is_alive.return_value = True
        conn = mock.Mock()
        with (
            mock.patch.object(server.config, "webview_process", process, create=True),
            mock.patch.object(server.config, "parent_conn", conn, create=True),
            mock.patch(
                "arknights_mower.utils.resource_version.check_resource_update",
                return_value={"current_display": "2026.09.06"},
            ),
        ):
            server._request_title_refresh()
        conn.send.assert_called_once_with(("title", "2026.09.06"))
        conn.recv.assert_not_called()

    def test_noop_when_process_not_started(self):
        # 进程未创建时不抛异常、不发送
        with mock.patch.object(server.config, "webview_process", None, create=True):
            server._request_title_refresh()

    def test_noop_when_process_dead(self):
        process = mock.Mock()
        process.is_alive.return_value = False
        with mock.patch.object(server.config, "webview_process", process, create=True):
            server._request_title_refresh()

    def test_send_error_is_swallowed(self):
        # 子进程在发送瞬间退出（坏管道）时，异常被吞掉不外泄
        process = mock.Mock()
        process.is_alive.return_value = True
        conn = mock.Mock()
        conn.send.side_effect = OSError("broken pipe")
        with (
            mock.patch.object(server.config, "webview_process", process, create=True),
            mock.patch.object(server.config, "parent_conn", conn, create=True),
        ):
            server._request_title_refresh()


if __name__ == "__main__":
    unittest.main()
