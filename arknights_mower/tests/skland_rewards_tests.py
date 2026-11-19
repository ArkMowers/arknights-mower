import json
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
import requests

from arknights_mower.utils import skland_rewards
from arknights_mower.utils.skland_log import sign_role_key, skland_day

CURRENT_TS = str(int(datetime(2026, 11, 17, 16, 2, tzinfo=timezone.utc).timestamp()))


@pytest.fixture
def skland(monkeypatch):
    # Other tests can leave a client stub in the package during collection.
    source = Path(skland_rewards.__file__).with_name("skland.py")
    spec = spec_from_file_location("arknights_mower.utils.skland", source)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(skland_rewards, "skland", module)
    return module


def account(phone="13800138000", **settings):
    values = {
        "arknights_isCheck": True,
        "sign_in_official": True,
        "sign_in_bilibili": False,
        "endfield_isCheck": True,
        "sign_in_endfield_official": True,
        "sign_in_endfield_bilibili": False,
        **settings,
    }
    return SimpleNamespace(account=phone, password="example-password", **values)


def response(body, status_code=200):
    result = requests.Response()
    result.status_code = status_code
    result.encoding = "utf-8"
    result._content = json.dumps(body).encode("utf-8")
    return result


def bindings(*, arknights=(), endfield=()):
    return {
        "code": 0,
        "data": {
            "list": [
                {"appCode": "arknights", "bindingList": list(arknights)},
                {"appCode": "endfield", "bindingList": list(endfield)},
            ]
        },
    }


def skland_arknights_binding(uid, channel="官服"):
    return {"gameId": 1, "channelName": channel, "uid": uid}


def skland_endfield_binding(*role_ids):
    return {
        "gameId": 3,
        "channelName": "官服",
        "roles": [{"roleId": role_id, "serverId": "13"} for role_id in role_ids],
    }


def slot(index, item=None, count=0, *, done=False, available=False):
    return {
        "index": index,
        "done": done,
        "available": available,
        "rewards": [{"item": item, "count": count}] if item else [],
    }


def test_reads_both_monthly_sequences_with_per_account_signed_gets(monkeypatch, skland):
    first = account()
    second = account("13900138001", arknights_isCheck=False)
    excluded = account("13900138002", arknights_isCheck=False, endfield_isCheck=False)
    sessions = {
        first.account: {"cred": "account-a-cred", "sign_token": "account-a-token"},
        second.account: {"cred": "account-b-cred", "sign_token": "account-b-token"},
    }
    monkeypatch.setattr(skland, "_ensure_device_id", lambda: "test-device")
    monkeypatch.setattr(skland, "restore_cached_session", sessions.__getitem__)

    def reject_refresh(*_):
        raise AssertionError("Cached sessions should be reused")

    monkeypatch.setattr(skland, "refresh_session", reject_refresh)
    monkeypatch.setitem(skland.header, "cred", "concurrent-cred")
    requests_seen = []
    uid = "ark+first"
    arknights_url = f"{skland.sign_url}?{urlencode({'gameId': 1, 'uid': uid})}"
    arknights_role = {**skland_arknights_binding(uid), "nickName": "  阿米娅  "}
    endfield_binding = skland_endfield_binding("first")
    endfield_binding["roles"][0]["nickname"] = (
        f"管理员 {first.account} {first.password}"
    )
    arknights_calendar = {
        "code": 0,
        "data": {
            "currentTs": CURRENT_TS,
            "calendar": [
                {"resourceId": "bonus", "type": "first", "done": True},
                {"resourceId": "money", "type": "daily", "count": 100, "done": True},
                {"resourceId": "unknown", "type": "daily", "available": True},
                {"resourceId": "money", "type": "daily", "count": 200},
                {"resourceId": "money", "type": "daily"},
            ],
            "resourceInfoMap": {"money": {"name": "龙门币", "count": 111}},
        },
    }
    endfield_calendar = {
        "code": 0,
        "data": {
            "currentTs": CURRENT_TS,
            "hasToday": True,
            "calendar": [
                {"awardId": "coin", "done": True, "count": 777},
                None,
                {"awardId": "coin", "available": True},
                {"awardId": "prism"},
            ],
            "resourceInfoMap": {
                "coin": {"name": "折金票", "count": 5000},
                "prism": {"name": "协议棱柱"},
            },
            "first": [{"awardId": "bonus"}],
        },
    }

    def get(url, *, headers, timeout):
        cred = headers["cred"]
        role = headers.get("sk-game-role")
        requests_seen.append((url, cred, role))
        assert 0 < timeout <= 10
        assert headers["sign"]
        assert headers["dId"] == "test-device"
        assert headers["vName"] == skland.SKLAND_VERSION
        if url == skland.binding_url and cred == "account-a-cred":
            return response(
                bindings(
                    arknights=(
                        arknights_role,
                        skland_arknights_binding(uid),
                        skland_arknights_binding("disabled", "bilibili服"),
                    ),
                    endfield=(endfield_binding,),
                )
            )
        if url == skland.binding_url and cred == "account-b-cred":
            return response(bindings(endfield=(skland_endfield_binding("second"),)))
        if url == arknights_url:
            return response(arknights_calendar)
        if url == skland.sign_endfield_url:
            return response(endfield_calendar)
        raise AssertionError("Unexpected Skland request")

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", reject_refresh)
    rows, warnings = skland_rewards.fetch_pair_rewards([first, excluded, second])

    assert not warnings
    assert rows[0]["display_name"] == "阿米娅"
    assert rows[1]["display_name"].startswith("管理员 138****8000 ")
    assert first.password not in rows[1]["display_name"]
    assert "display_name" not in rows[2]
    assert uid not in json.dumps(rows)
    assert [(row["account"], row["game"], row["role_index"]) for row in rows] == [
        ("138****8000", "明日方舟官服", 1),
        ("138****8000", "终末地官服", 1),
        ("139****8001", "终末地官服", 1),
    ]
    assert [row["role_key"] for row in rows] == [
        sign_role_key(first.account, "明日方舟官服", uid),
        sign_role_key(first.account, "终末地官服", "first", "13"),
        sign_role_key(second.account, "终末地官服", "second", "13"),
    ]
    assert [row["signed_today"] for row in rows] == [False, True, True]
    assert [row["progress_date"] for row in rows] == ["2026-11-18"] * 3
    assert rows[0]["reward_slots"] == [
        slot(1, "龙门币", 100, done=True),
        slot(2, available=True),
        slot(3, "龙门币", 200),
        slot(4, "龙门币", 0),
    ]
    assert (
        rows[1]["reward_slots"]
        == rows[2]["reward_slots"]
        == [
            slot(1, "折金票", 5000, done=True),
            slot(2),
            slot(3, "折金票", 5000, available=True),
            slot(4, "协议棱柱", 0),
        ]
    )
    assert requests_seen == [
        (skland.binding_url, "account-a-cred", None),
        (arknights_url, "account-a-cred", None),
        (skland.sign_endfield_url, "account-a-cred", "3_first_13"),
        (skland.binding_url, "account-b-cred", None),
        (skland.sign_endfield_url, "account-b-cred", "3_second_13"),
    ]
    assert skland.header["cred"] == "concurrent-cred"


def test_refreshes_expired_binding_then_preserves_roles_after_http_failure(
    monkeypatch, skland
):
    item = account(arknights_isCheck=False)
    monkeypatch.setattr(skland, "_ensure_device_id", lambda: "test-device")
    monkeypatch.setattr(
        skland,
        "restore_cached_session",
        lambda _: {"cred": "expired-cred", "sign_token": "expired-token"},
    )
    refreshed = []

    def refresh(current):
        refreshed.append(current)
        return {"cred": "renewed-cred", "sign_token": "renewed-token"}

    def get(url, *, headers, timeout):
        if url == skland.binding_url:
            if headers["cred"] == "expired-cred":
                return response({"code": 1, "message": "用户未登录"})
            assert headers["cred"] == "renewed-cred"
            return response(
                bindings(endfield=(skland_endfield_binding("first", "second"),))
            )
        assert url == skland.sign_endfield_url
        assert headers["cred"] == "renewed-cred"
        status = 503 if headers["sk-game-role"] == "3_first_13" else 200
        return response(
            {"code": 0, "data": {"calendar": [], "currentTs": CURRENT_TS}}, status
        )

    monkeypatch.setattr(skland, "refresh_session", refresh)
    monkeypatch.setattr(requests, "get", get)
    rows, warnings = skland_rewards.fetch_pair_rewards([item])
    assert refreshed == [item]
    assert rows == [
        {
            "account": "138****8000",
            "game": "终末地官服",
            "role_index": 2,
            "role_key": sign_role_key(item.account, "终末地官服", "second", "13"),
            "reward_slots": [],
            "signed_today": None,
            "progress_date": "2026-11-18",
            "progress_ambiguous": True,
        }
    ]
    assert warnings == ["138****8000 · 终末地官服 · 角色 1 的本月奖励读取失败"]


def test_account_errors_are_redacted_and_do_not_prevent_other_accounts(
    monkeypatch, skland
):
    first = account()
    second = account("13900138001")
    monkeypatch.setattr(skland, "_ensure_device_id", lambda: "test-device")
    monkeypatch.setattr(skland, "restore_cached_session", lambda _: None)

    def refresh(item):
        if item is first:
            raise RuntimeError(f"{item.account} {item.password}")
        return {"cred": "second-cred", "sign_token": "second-token"}

    def get(url, *, headers, timeout):
        assert headers["cred"] == "second-cred"
        if url == skland.binding_url:
            return response(bindings(arknights=(skland_arknights_binding("role"),)))
        return response({"code": 0, "data": {"calendar": [], "currentTs": CURRENT_TS}})

    monkeypatch.setattr(skland, "refresh_session", refresh)
    monkeypatch.setattr(requests, "get", get)
    rows, warnings = skland_rewards.fetch_pair_rewards([first, second])
    assert rows == [
        {
            "account": "139****8001",
            "game": "明日方舟官服",
            "role_index": 1,
            "role_key": sign_role_key(second.account, "明日方舟官服", "role"),
            "reward_slots": [],
            "signed_today": None,
            "progress_date": "2026-11-18",
        }
    ]
    assert warnings == ["138****8000 的森空岛角色读取失败"]


def test_bindings_without_enabled_channels_report_the_account_only(monkeypatch, skland):
    item = account(endfield_isCheck=False)
    monkeypatch.setattr(
        skland,
        "restore_cached_session",
        lambda _: {"cred": "test-cred", "sign_token": "test-token"},
    )
    monkeypatch.setattr(
        skland,
        "get_binding_list",
        lambda *args, **kwargs: [
            skland_arknights_binding("disabled", "bilibili服"),
            skland_endfield_binding("disabled"),
        ],
    )
    rows, warnings = skland_rewards.fetch_pair_rewards([item])
    assert rows == []
    assert warnings == ["138****8000 未读取到已启用区服的森空岛角色"]


def test_arknights_daily_record_matches_provider_date_in_utc_plus_eight(
    monkeypatch, skland
):
    item = account(endfield_isCheck=False)
    monkeypatch.setattr(skland, "_ensure_device_id", lambda: "test-device")
    monkeypatch.setattr(
        skland,
        "restore_cached_session",
        lambda _: {"cred": "test-cred", "sign_token": "test-token"},
    )
    record_ts = str(int(datetime(2026, 11, 17, 16, 1, tzinfo=timezone.utc).timestamp()))

    def get(url, *, headers, timeout):
        if url == skland.binding_url:
            return response(bindings(arknights=(skland_arknights_binding("role"),)))
        return response(
            {
                "code": 0,
                "data": {
                    "currentTs": CURRENT_TS,
                    "calendar": [{"type": "daily", "done": True}],
                    "records": [{"type": "daily", "ts": record_ts}],
                },
            }
        )

    monkeypatch.setattr(requests, "get", get)
    rows, warnings = skland_rewards.fetch_pair_rewards([item])
    assert not warnings
    assert rows[0]["signed_today"] is True
    assert rows[0]["progress_date"] == "2026-11-18"
    assert rows[0]["signed_dates"] == ["2026-11-18"]


def test_arknights_incomplete_history_does_not_date_the_claimed_prefix(
    monkeypatch, skland
):
    item = account(endfield_isCheck=False)
    record_ts = str(int(datetime(2026, 11, 17, 16, 1, tzinfo=timezone.utc).timestamp()))
    monkeypatch.setattr(
        skland_rewards,
        "_load_bindings",
        lambda _: (
            [skland_arknights_binding("role")],
            {"cred": "test-cred"},
            "test-token",
        ),
    )
    monkeypatch.setattr(
        skland,
        "request_with_retry",
        lambda *args, **kwargs: response(
            {
                "code": 0,
                "data": {
                    "currentTs": CURRENT_TS,
                    "calendar": [{"type": "daily", "done": True}] * 2,
                    "records": [{"type": "daily", "ts": record_ts}],
                },
            }
        ),
    )
    rows, warnings = skland_rewards.fetch_pair_rewards([item])
    assert not warnings
    assert rows[0]["signed_today"] is True
    assert "signed_dates" not in rows[0]


def test_arknights_no_available_slot_cannot_confirm_today_was_signed():
    entries = skland_rewards._calendar_entries(
        {
            "calendar": [
                {"type": "first", "available": True},
                {"type": "daily", "available": False, "done": True},
                {"type": "daily", "available": False, "done": False},
            ]
        },
        1,
    )
    today = skland_day(int(CURRENT_TS))
    assert skland_rewards._signed_today({}, 1, entries, today, []) is None
    entries[1]["available"] = True
    assert skland_rewards._signed_today({}, 1, entries, today, []) is False


def test_both_games_use_receipt_date_when_provider_time_is_missing(monkeypatch, skland):
    monkeypatch.setattr(skland, "_ensure_device_id", lambda: "test-device")
    monkeypatch.setattr(
        skland,
        "restore_cached_session",
        lambda _: {"cred": "test-cred", "sign_token": "test-token"},
    )

    def get(url, *, headers, timeout):
        if url == skland.binding_url:
            return response(
                bindings(
                    arknights=(skland_arknights_binding("ark"),),
                    endfield=(skland_endfield_binding("end"),),
                )
            )
        data = {"calendar": []}
        if url == skland.sign_endfield_url:
            data["hasToday"] = False
        return response({"code": 0, "data": data})

    receipt = datetime(2026, 11, 17, 16, 30, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(
        skland_rewards,
        "skland_day",
        lambda timestamp=None: skland_day(receipt if timestamp is None else timestamp),
    )
    monkeypatch.setattr(requests, "get", get)
    rows, warnings = skland_rewards.fetch_pair_rewards([account()])
    assert not warnings
    assert [row["signed_today"] for row in rows] == [None, False]
    assert [row["progress_date"] for row in rows] == ["2026-11-18", "2026-11-18"]
