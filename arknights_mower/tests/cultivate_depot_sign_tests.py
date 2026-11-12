"""cultivate_depot 森空岛签名 GET 使用 headers_factory（重试时重新签名）回归。

修复背景：签名头（含时间戳）在进入 request_with_retry 之前只算一次，第一次
请求超时后重试携带过期 timestamp，被服务端判「请勿修改设备本地时间」。
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# 只验证 cultivate_depot 自身对 request_with_retry 的调用方式，森空岛网络层
# 一律由 test double 控制（与其他测试同款 stub，规避导入链联网）。
# 但 cultivate_depot 的 info URL 常量来自 skland 真实模块：桩状态下导入拿到的是
# MagicMock 属性，URL 断言会随执行顺序漂移（单文件运行必挂）。这里清掉桩和可能
# 已按桩导入的 cultivate_depot，强制按真实模块重新导入，保证与运行顺序无关。
sys.modules.pop("arknights_mower.utils.skland", None)
sys.modules.pop("arknights_mower.solvers.cultivate_depot", None)

from arknights_mower.solvers import cultivate_depot  # noqa: E402
from arknights_mower.utils import skland  # noqa: E402,F401

PLAYER_URL = "https://zonai.skland.com/api/v1/game/cultivate/player?uid=100"
INFO_URL = "https://zonai.skland.com/api/v1/game/player/info?uid=100"
SIGN_TOKEN = "sign-token"


def _run_refresh():
    """驱动 cultivate().start() 走完「绑定列表 → 养成数据 → 基建信息」两处签名 GET。

    外部 I/O（认证、绑定列表、HTTP、落盘、统计）全部用 test double 控制为离线；
    第二处 info GET 通过让基建条件解析为空来触发。
    """
    conf = SimpleNamespace(
        skland_info=[SimpleNamespace(account="a", password="p", cultivate_select=True)]
    )
    binding = {
        "gameId": 1,
        "isOfficial": True,
        "uid": "100",
        "nickName": "博士",
        "channelName": "official",
        "channelMasterId": 1,
    }
    player_resp = {"code": 0, "data": {"characters": [], "items": None}}
    info_resp = {"code": 0, "data": {"building": {"name": "central"}}}
    responses = [
        MagicMock(json=lambda: player_resp),
        MagicMock(json=lambda: info_resp),
    ]
    factory_outputs = []
    with (
        patch("arknights_mower.solvers.cultivate_depot.config.conf", conf),
        patch(
            "arknights_mower.solvers.cultivate_depot.get_cred_by_token",
            return_value={"cred": "cred", "token": SIGN_TOKEN},
        ),
        patch("arknights_mower.solvers.cultivate_depot.log", return_value="token"),
        patch(
            "arknights_mower.solvers.cultivate_depot.get_binding_list",
            return_value=[binding],
        ),
        patch(
            "arknights_mower.solvers.cultivate_depot.get_sign_header",
            return_value={"sign": "fresh"},
        ) as sign,
        patch(
            "arknights_mower.solvers.cultivate_depot.request_with_retry",
            side_effect=responses,
        ) as request_mock,
        patch("arknights_mower.solvers.cultivate_depot.parse_roster"),
        patch("arknights_mower.solvers.cultivate_depot.atomic_write"),
        patch(
            "arknights_mower.utils.building_skills.parse_base_conditions",
            return_value={},
        ),
        patch(
            "arknights_mower.utils.mastery_recommendation.get_skill_data",
            return_value={"characters": {}, "items": {}},
        ),
        patch("arknights_mower.utils.growth.completed_manual_goals", return_value=[]),
        patch("arknights_mower.utils.growth.load_goals", return_value=[]),
        patch("arknights_mower.utils.growth.save_statistics"),
        patch("arknights_mower.utils.growth.remove_completed_goals"),
        patch(
            "arknights_mower.utils.mastery_db.has_synced_mastery_completion",
            return_value=False,
        ),
        patch(
            "arknights_mower.utils.mastery_db.complete_synced_mastery_plans",
            return_value=False,
        ),
        patch(
            "arknights_mower.utils.yituliu_sync.sync_after_cultivate",
            return_value=None,
        ),
    ):
        result = cultivate_depot.cultivate().start()
        # factory 只能在 patch 上下文内调用（内部走 get_sign_header）
        for call in request_mock.call_args_list:
            factory = call.kwargs["headers_factory"]
            assert callable(factory)
            factory_outputs.append(factory())
    return result, request_mock, sign, factory_outputs


def test_cultivate_player_get_re_signs_per_attempt():
    # 养成数据 GET：headers_factory 每次尝试现算签名头（用正确参数签名）
    result, request_mock, sign, factories = _run_refresh()
    assert result is True
    assert factories[0] == {"sign": "fresh"}
    # 语义与原单次签名一致：url/method/body/token 原样进签名
    assert sign.call_args_list[0].args == (
        PLAYER_URL,
        "get",
        {"gameId": 1, "uid": "100"},
        SIGN_TOKEN,
    )


def test_cultivate_player_info_get_re_signs_per_attempt():
    # 基建信息 GET（超时 10 秒）：同样使用 headers_factory 重签名
    result, request_mock, sign, factories = _run_refresh()
    assert result is True
    assert request_mock.call_count == 2
    info_call = request_mock.call_args_list[1]
    assert info_call.args == ("get", INFO_URL)
    assert info_call.kwargs["timeout"] == 10
    assert factories[1] == {"sign": "fresh"}
    assert sign.call_args_list[1].args == (INFO_URL, "get", None, SIGN_TOKEN)
