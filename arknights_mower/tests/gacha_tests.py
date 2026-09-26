"""No-network regression tests for Mower's independent headhunting module."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from arknights_mower.utils.gacha_provider import (
    GachaProvider,
    GachaRemoteError,
    GachaSessions,
    _data,
)
from arknights_mower.utils.gacha_records import GachaArchive, normalize_record
from arknights_mower.views import gacha as view


def fake_record(pos=0, char="char_001", rarity=5):
    return {
        "poolId": "pool-1",
        "poolName": "测试限定寻访",
        "charId": char,
        "charName": "测试干员",
        "rarity": rarity,
        "isNew": False,
        "gachaTs": "1770697079082",
        "pos": pos,
    }


class Response:
    def __init__(self, data, cookie=None, status=200):
        self._data = data
        self.cookies = {"ak-user-center": cookie} if cookie else {}
        self.status_code = status

    def json(self):
        return self._data


class FakeHttp:
    def __init__(self, post_replies, get_replies):
        self.headers = {}
        self.posts = list(post_replies)
        self.gets = list(get_replies)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        return self.posts.pop(0)

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, params, headers))
        return self.gets.pop(0)

    def close(self):
        pass


class GachaArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = GachaArchive(Path(self.temp.name) / "records.sqlite3")

    def test_identical_character_in_ten_pull_keeps_two_rows(self):
        account_id = self.store.ensure_account("40223311", "official", "博士")
        rows = [normalize_record(fake_record(pos), "normal") for pos in (0, 1)]
        self.assertNotEqual(rows[0]["id"], rows[1]["id"])
        self.assertEqual(self.store.append(account_id, rows), 2)
        self.assertEqual(self.store.append(account_id, rows), 0)
        summary = self.store.summary(account_id)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["six_star"], 2)
        self.assertEqual(summary["categories"]["normal"]["since_six"], 0)
        self.assertTrue(summary["history_incomplete"])

    def test_channels_are_separate_and_old_records_survive_new_sync(self):
        a = self.store.ensure_account("1001", "official", "官服角色")
        b = self.store.ensure_account("1001", "bilibili", "B服角色")
        record = normalize_record(fake_record(), "normal")
        self.store.append(a, [record], finished=True)
        self.store.append(b, [record])
        self.assertEqual(len(self.store.accounts()), 2)
        self.assertEqual(self.store.summary(a)["total"], 1)
        self.assertEqual(self.store.summary(b)["total"], 1)
        self.store.append(a, [], finished=True)
        self.assertEqual(self.store.summary(a)["total"], 1)
        self.assertEqual(len(self.store.export(b)["records"]), 1)

    def test_invalid_or_incomplete_data_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            normalize_record(
                {k: v for k, v in fake_record().items() if k != "pos"}, "normal"
            )


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = GachaArchive(Path(self.temp.name) / "gacha.db")

    def test_sms_login_both_channels_sync_and_dedup(self):
        client = FakeHttp(
            [
                Response({"status": 0}),  # send phone code has no data
                Response({"status": 0, "data": {"token": "account-token"}}),
                Response({"status": 0, "data": {"token": "oauth-token"}}),
                Response({"code": 0, "data": {"token": "u8-token"}}),
                Response(
                    {"code": 0}, cookie="private-cookie"
                ),  # role login has no data
            ],
            [
                Response(
                    {
                        "code": 0,
                        "data": {
                            "list": [
                                {
                                    "appCode": "arknights",
                                    "bindingList": [
                                        {
                                            "uid": "1001",
                                            "nickName": "官服博士",
                                            "channelName": "官服",
                                            "isOfficial": True,
                                        },
                                        {
                                            "uid": "1002",
                                            "nickName": "B服博士",
                                            "channelName": "bilibili服",
                                            "isOfficial": False,
                                        },
                                    ],
                                }
                            ]
                        },
                    }
                ),
                Response({"code": 0, "data": [{"id": "normal"}]}),
                Response(
                    {
                        "code": 0,
                        "data": {
                            "list": [fake_record(0), fake_record(1)],
                            "hasMore": False,
                        },
                    }
                ),
            ],
        )
        provider = GachaProvider(client)
        provider.send_code("13800000000")
        roles = provider.login("13800000000", "123456")
        self.assertEqual([role.channel for role in roles], ["official", "bilibili"])
        role = provider.select_role("1002", "bilibili")
        self.assertEqual(role.channel, "bilibili")
        result = provider.fetch_all(self.archive)
        self.assertEqual(result["added"], 2)
        self.assertEqual(result["warnings"], [])
        self.assertEqual(self.archive.summary("bilibili:1002")["total"], 2)
        self.assertEqual(self.archive.summary("bilibili:1002")["six_star"], 2)
        grant = [c for c in client.calls if "/oauth2/v2/grant" in c[1]][0]
        self.assertEqual(grant[2]["type"], 1)
        self.assertEqual(grant[2]["appCode"], "be36d44aa36bfb5b")
        history = [c for c in client.calls if c[1].endswith("/history")][0]
        self.assertEqual(history[3]["x-role-token"], "u8-token")
        self.assertIn("ak-user-center=private-cookie", history[3]["Cookie"])
        self.assertEqual(provider.current_role.uid, "1002")

    def test_auth_error_without_code_must_fail(self):
        with self.assertRaises(GachaRemoteError):
            _data(Response({"reason": "MissingCookie", "message": "未登录"}), "记录")

    def test_session_switch_and_logout(self):
        sessions = GachaSessions()
        one = GachaProvider(FakeHttp([], []))
        two = GachaProvider(FakeHttp([], []))
        first = sessions.add(one)
        second = sessions.add(two)
        self.assertEqual(len(sessions.list_public()), 2)
        sessions.remove(first)
        self.assertEqual(sessions.get(second), two)
        with self.assertRaises(ValueError):
            sessions.get(first)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Flask(__name__)
        self.app.token = "test-local-token"
        self.app.register_blueprint(view.gacha_bp)
        self.app.testing = True
        self.client = self.app.test_client()
        self.previous_archive = view.archive_instance
        self.previous_sessions = view.sessions
        view.archive_instance = GachaArchive(Path(self.temp.name) / "route.db")
        view.sessions = GachaSessions()
        self.addCleanup(self.restore)

    def restore(self):
        view.archive_instance = self.previous_archive
        view.sessions = self.previous_sessions

    def test_loopback_token_and_csrf_required(self):
        self.assertEqual(self.client.get("/gacha/accounts").status_code, 403)
        headers = {"token": "test-local-token"}
        self.assertEqual(
            self.client.get("/gacha/accounts", headers=headers).status_code, 200
        )
        self.assertEqual(
            self.client.get(
                "/gacha/accounts",
                headers=headers,
                environ_overrides={"REMOTE_ADDR": "192.0.2.4"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/gacha/logout", json={}, headers=headers).status_code,
            403,
        )
        bad_origin = {**headers, "X-Mower-Gacha": "1", "Origin": "https://evil.example"}
        self.assertEqual(
            self.client.post("/gacha/logout", json={}, headers=bad_origin).status_code,
            403,
        )

    def test_separate_account_history_and_export(self):
        account = view.archive_instance.ensure_account("001", "official", "博士")
        view.archive_instance.append(
            account, [normalize_record(fake_record(), "normal")]
        )
        headers = {"token": "test-local-token"}
        self.assertEqual(
            self.client.get(
                "/gacha/summary?account_id=official:001", headers=headers
            ).json["total"],
            1,
        )
        exported = self.client.get(
            "/gacha/export?account_id=official:001", headers=headers
        )
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(json.loads(exported.data)["format"], "mower-gacha-v1")
        self.assertNotIn("token", exported.data.decode())


class GachaV2Tests(unittest.TestCase):
    """Second-round regression coverage; no live credentials or outgoing SMS."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = GachaArchive(Path(self.temp.name) / "gacha.db")

    def test_password_login_reuses_existing_official_auth_chain(self):
        client = FakeHttp(
            [
                Response({"code": 0, "data": {"token": "pw-token"}}),
                Response({"code": 0, "data": {"token": "oauth-token"}}),
            ],
            [
                Response(
                    {
                        "code": 0,
                        "data": {
                            "list": [
                                {
                                    "appCode": "arknights",
                                    "bindingList": [
                                        {
                                            "uid": "9001",
                                            "nickname": "测试",
                                            "channelName": "官服",
                                            "isOfficial": True,
                                        },
                                    ],
                                },
                            ]
                        },
                    }
                )
            ],
        )
        provider = GachaProvider(client)
        roles = provider.login_password("13800000000", "fake-password")
        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].channel, "official")
        self.assertTrue(
            client.calls[0][1].endswith("/user/auth/v1/token_by_phone_password")
        )
        self.assertEqual(client.calls[0][2]["password"], "fake-password")
        self.assertEqual(provider.account_token, "pw-token")
        provider.close()
        self.assertEqual(provider.account_token, "")

    def test_five_star_pool_counts_and_filters(self):
        account = self.archive.ensure_account("9001", "official", "测试博士")
        six = fake_record(0, char="char_six", rarity=5)
        five = fake_record(1, char="char_five", rarity=4)
        five["isNew"] = True
        three = fake_record(2, char="char_three", rarity=2)
        self.archive.append(
            account,
            [
                normalize_record(six, "classic"),
                normalize_record(five, "classic"),
                normalize_record(three, "classic"),
            ],
            finished=True,
        )
        stats = self.archive.summary(account)
        self.assertEqual(stats["six_star"], 1)
        self.assertEqual(stats["five_star"], 1)
        self.assertEqual(stats["stars"]["3"], 1)
        self.assertEqual(stats["pools"][0]["count"], 3)
        self.assertEqual(stats["pools"][0]["six_star"], 1)
        self.assertEqual(stats["pools"][0]["five_star"], 1)
        self.assertEqual(len(self.archive.list_records(account, rarity=5)), 1)
        self.assertEqual(len(self.archive.list_records(account, rarity_min=5)), 2)
        self.assertEqual(len(self.archive.list_records(account, new_only=True)), 1)
        self.assertEqual(len(self.archive.list_records(account, pool_id="pool-1")), 3)
        self.assertEqual(len(self.archive.list_records(account, search="不存在")), 0)
        with self.assertRaises(ValueError):
            self.archive.list_records(account, rarity_min=7)

    def test_sms_cooldown_has_server_side_retry_time(self):
        from arknights_mower.utils.gacha_provider import GachaProvider as RealProvider

        app = Flask("sms-cooldown-test")
        app.testing = True
        app.token = "test-gacha-token"
        app.register_blueprint(view.gacha_bp)
        client = app.test_client()
        headers = {"token": "test-gacha-token", "X-Mower-Gacha": "1"}
        phone = "13900005551"
        self.addCleanup(lambda: view.sms_cooldowns.pop(phone, None))
        view.sms_cooldowns.pop(phone, None)
        with patch.object(RealProvider, "send_code", return_value=None) as fake_send:
            first = client.post(
                "/gacha/send-code", json={"phone": phone}, headers=headers
            )
            second = client.post(
                "/gacha/send-code", json={"phone": phone}, headers=headers
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json["retry_after_seconds"], 90)
        self.assertEqual(second.status_code, 429)
        self.assertTrue(1 <= second.json["retry_after_seconds"] <= 90)
        self.assertEqual(fake_send.call_count, 1)

    def test_password_endpoint_only_returns_masked_phone(self):
        from arknights_mower.utils.gacha_provider import GachaProvider as RealProvider
        from arknights_mower.utils.gacha_provider import Role

        app = Flask("password-local-test")
        app.testing = True
        app.token = "test-gacha-token"
        app.register_blueprint(view.gacha_bp)
        previous_sessions = view.sessions
        view.sessions = GachaSessions()
        self.addCleanup(lambda: setattr(view, "sessions", previous_sessions))
        headers = {"token": "test-gacha-token", "X-Mower-Gacha": "1"}
        with patch.object(
            RealProvider,
            "login_password",
            return_value=[Role("9001", "official", "测试", "官服")],
        ) as mocked:
            response = app.test_client().post(
                "/gacha/login-password",
                json={
                    "phone": "13800000000",
                    "password": "fake-password",
                },
                headers=headers,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["account"], "***0000")
        self.assertNotIn("fake-password", response.get_data(as_text=True))
        self.assertEqual(mocked.call_count, 1)


class GachaV3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = GachaArchive(Path(self.temp.name) / "records.db")

    def test_pool_index_is_distinct_from_six_star_interval(self):
        account = self.archive.ensure_account("1001", "official", "博士")
        draws = []
        for i in range(12):
            row = fake_record(i, char=f"char_{i:03d}", rarity=5 if i in (2, 8) else 2)
            row["charName"] = "目标角色" if i == 8 else f"干员{i}"
            draws.append(normalize_record(row, "normal"))
        self.archive.append(account, draws)
        stats = self.archive.summary(account)
        pool = stats["pools"][0]
        first, target = pool["six_operators"]
        self.assertEqual(pool["count"], 12)
        self.assertEqual(first["pool_index"], 3)
        self.assertEqual(first["interval_count"], 3)
        self.assertFalse(first["interval_complete"])
        self.assertEqual(target["pool_index"], 9)
        self.assertEqual(target["interval_count"], 6)
        self.assertTrue(target["interval_complete"])
        self.assertEqual(target["after_count"], 3)
        self.assertTrue(stats["history_incomplete"])

    def test_local_skland_roster_requires_account_confirmation(self):
        from pathlib import Path

        from arknights_mower.utils.gacha_roster import roster_preview

        base = Path(self.temp.name)
        (base / "tmp").mkdir()
        p = base / "_internal/arknights_mower/data"
        p.mkdir(parents=True)
        (base / "tmp/cultivate.json").write_text(
            json.dumps(
                {
                    "code": 0,
                    "data": {
                        "characters": [
                            {
                                "id": "char_002_amiya",
                                "level": 50,
                                "evolvePhase": 2,
                                "potentialRank": 3,
                            },
                            {"id": "char_new_unknown", "level": 1, "evolvePhase": 0},
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        (p / "skill_data.json").write_text(
            json.dumps(
                {
                    "characters": {
                        "char_002_amiya": {
                            "name": "阿米娅",
                            "rarity": 5,
                            "profession": "CASTER",
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        result = roster_preview(base)
        self.assertTrue(result["available"])
        self.assertFalse(result["account_verified"])
        self.assertEqual(result["operator_count"], 1)
        self.assertEqual(result["unknown_id_count"], 1)
        self.assertEqual(result["operators"][0]["name"], "阿米娅")
        self.assertNotIn("uid", result)


class GachaManualRefreshTests(unittest.TestCase):
    def test_manual_roster_refresh_reuses_mower_endpoint_without_new_credentials(self):
        app = Flask("manual-roster-refresh")
        app.token = "local-only"
        app.testing = True
        app.register_blueprint(view.gacha_bp)
        client = app.test_client()
        headers = {"token": "local-only", "X-Mower-Gacha": "1"}
        fetched = []

        def fetch_existing_mower_skland():
            fetched.append("called")
            return {"success": True, "message": "数据拉取成功"}

        app.add_url_rule(
            "/cultivate-fetch",
            endpoint="cultivate_fetch",
            view_func=fetch_existing_mower_skland,
            methods=["GET"],
        )
        self.assertEqual(client.post("/gacha/refresh-roster", json={}).status_code, 403)
        with patch(
            "arknights_mower.utils.gacha_roster.roster_preview",
            return_value={
                "available": True,
                "account_verified": False,
                "operator_count": 2,
            },
        ):
            response = client.post("/gacha/refresh-roster", json={}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["operator_count"], 2)
        self.assertFalse(response.json["account_verified"])
        self.assertEqual(fetched, ["called"])


class GachaV5RosterTests(unittest.TestCase):
    def test_low_rarity_fallback_recovers_three_two_one_stars(self):
        from arknights_mower.utils.gacha_roster import roster_preview

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "tmp").mkdir()
            folder = base / "_internal/arknights_mower/data"
            folder.mkdir(parents=True)
            (folder / "skill_data.json").write_text(
                '{"characters":{}}', encoding="utf8"
            )
            characters = [
                {"id": "char_120_hibisc", "evolvePhase": 1, "level": 55},
                {"id": "char_501_durin", "evolvePhase": 0, "level": 30},
                {"id": "char_285_medic2", "evolvePhase": 0, "level": 30},
            ]
            (base / "tmp/cultivate.json").write_text(
                json.dumps({"data": {"characters": characters}}), encoding="utf8"
            )
            result = roster_preview(base)
            self.assertTrue(result["available"])
            self.assertEqual(result["operator_count"], 3)
            self.assertEqual(result["unknown_id_count"], 0)
            self.assertEqual({x["rarity"] for x in result["operators"]}, {1, 2, 3})
            self.assertFalse(result["account_verified"])

    def test_public_catalog_covers_low_rarity_ids(self):
        import json as _json

        catalog_path = (
            Path(__file__).resolve().parents[1] / "data" / "gacha_catalog.json"
        )
        catalog = _json.loads(catalog_path.read_text(encoding="utf8"))
        self.assertEqual(catalog["char_120_hibisc"]["rarity"], 3)
        self.assertEqual(catalog["char_501_durin"]["rarity"], 2)
        self.assertEqual(catalog["char_285_medic2"]["rarity"], 1)
        # Only uncommon records are shipped; reuse Mower's skill_data.json for
        # the existing catalog to avoid duplicating source game metadata.
        self.assertGreaterEqual(len(catalog), 60)
        complete = view.operator_catalog()["operators"]
        self.assertGreaterEqual(len(complete), 460)
        self.assertEqual(complete["char_120_hibisc"]["rarity"], 3)


if __name__ == "__main__":
    unittest.main()
