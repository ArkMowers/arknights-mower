"""request_with_retry 重签名（headers_factory）与重试日志回归。

修复背景：签名头（含时间戳）在进入重试循环之前只算一次，第一次请求超时后
重试携带过期 timestamp，被服务端判「请勿修改设备本地时间」；且重试全程无日志。
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

# 其他测试文件可能把 skland 整个模块 stub 成 MagicMock（规避导入链联网）；
# 这里强制重新导入真实模块，保证测的是真实现。
sys.modules.pop("arknights_mower.utils.skland", None)

from arknights_mower.utils import skland  # noqa: E402

URL = "https://zonai.skland.com/api/v1/game/player/binding"


def _fake_time(monotonic_values):
    """替身 time 模块：monotonic 按序取值，sleep 不真等待。"""

    def monotonic():
        if len(monotonic_values) > 1:
            return monotonic_values.pop(0)
        return monotonic_values[0]

    return patch.object(
        skland, "time", SimpleNamespace(sleep=lambda _s: None, monotonic=monotonic)
    )


# 只 patch requests.get/post（不整模块替换，保住 except 里的真实异常类）
GET = "requests.get"
POST = "requests.post"


def test_headers_factory_recomputed_per_attempt():
    # 第一次尝试超时 → 重试时 headers_factory 再次现算请求头（签名时间戳新鲜）
    factory = MagicMock(return_value={"sign": "fresh"})
    with (
        patch(GET, side_effect=[requests.exceptions.Timeout(), MagicMock()]) as get,
        _fake_time([0.0, 30.0]),
    ):
        resp = skland.request_with_retry(
            "get", URL, headers={"stale": True}, headers_factory=factory
        )
    assert get.call_count == 2
    assert factory.call_count == 2, "每次尝试（含第一次）都应重新取请求头"
    assert get.call_args.kwargs["headers"] == {"sign": "fresh"}


def test_static_headers_kept_without_factory():
    # 不传 headers_factory → 沿用静态 headers（登录类请求无时间戳，行为不变）
    with patch(POST, return_value=MagicMock()) as post:
        resp = skland.request_with_retry(
            "post", URL, json={"a": 1}, headers=skland.header_login
        )
    assert resp is post.return_value
    assert post.call_args.kwargs["headers"] is skland.header_login


def test_retry_emits_warning_before_retrying():
    # 重试前打 WARNING：含异常类型名（面向用户可读），成功后不再追加
    with (
        patch(GET, side_effect=[requests.exceptions.Timeout(), MagicMock()]),
        patch.object(skland.logger, "warning") as warning,
        _fake_time([0.0, 30.0]),
    ):
        skland.request_with_retry("get", URL, headers={}, headers_factory=dict)
    warning.assert_called_once()
    message = " ".join(str(arg) for arg in warning.call_args.args)
    assert "重试" in message
    assert "Timeout" in message


def test_gives_up_with_warning_before_final_raise():
    # 三次全部失败：重试 WARNING ×2 + 最终放弃 WARNING ×1，然后原样抛出
    with (
        patch(GET, side_effect=requests.exceptions.ConnectionError()),
        patch.object(skland.logger, "warning") as warning,
        _fake_time([0.0, 1.0, 2.0, 3.0]),
    ):
        with pytest.raises(requests.exceptions.ConnectionError):
            skland.request_with_retry("get", URL, headers={})
    assert warning.call_count == 3
    final_message = " ".join(str(arg) for arg in warning.call_args_list[-1].args)
    assert "放弃" in final_message
    assert "ConnectionError" in final_message


def test_immediate_success_logs_no_warning():
    # 一次成功 → 无 WARNING（WARNING 只覆盖可恢复异常情况）
    with (
        patch(GET, return_value=MagicMock()),
        patch.object(skland.logger, "warning") as warning,
    ):
        skland.request_with_retry("get", URL, headers={})
    warning.assert_not_called()
