"""Skland signing keeps configuration replacement separate from Stop."""

from threading import Event, Thread
from types import SimpleNamespace

import pytest

from arknights_mower.tests.config_profile_request_tests import (
    profile_run_intent as profile_run_intent,
)
from arknights_mower.tests.config_profiles_tests import storage as storage


@pytest.mark.parametrize("game", [1, 3], ids=["arknights", "endfield"])
def test_signing_allows_stop_while_refusing_configuration_replacement(
    profile_run_intent, storage, monkeypatch, game
):
    from arknights_mower.solvers import skland

    api = profile_run_intent
    account = api.config.conf.SKLandAccount(
        account="offline-account",
        arknights_isCheck=game == 1,
        endfield_isCheck=game == 3,
        sign_in_official=True,
        sign_in_endfield_official=True,
    )
    monkeypatch.setattr(api.config.conf, "skland_info", [account])
    monkeypatch.setattr(skland, "get_path", storage)
    monkeypatch.setattr(skland, "log", lambda account: "offline-login")
    monkeypatch.setattr(
        skland,
        "get_cred_by_token",
        lambda token: {"cred": "offline-cred", "token": "offline-token"},
    )
    monkeypatch.setattr(skland, "get_sign_header", lambda *args: {})
    monkeypatch.setattr(skland, "header", {})
    monkeypatch.setattr(
        skland,
        "get_binding_list",
        lambda token: [
            {
                "gameId": game,
                "uid": "offline-uid",
                "channelName": "官服",
                "roles": [{"roleId": "offline-role", "serverId": "offline-server"}],
            }
        ],
    )
    record = storage("@app/tmp/skland.csv")
    entered, release = Event(), Event()
    outcome = {}
    workers = []
    signing_responses = {
        1: {
            "code": 0,
            "data": {"awards": [{"resource": {"name": "offline-reward"}, "count": 1}]},
        },
        3: {
            "code": 0,
            "data": {
                "awardIds": [{"id": "offline-award", "count": 1}],
                "resourceInfoMap": {"offline-award": {"name": "offline-reward"}},
            },
        },
    }

    def post(url, **kwargs):
        assert url == (skland.sign_url if game == 1 else skland.sign_endfield_url)
        entered.set()
        assert release.wait(5)
        return SimpleNamespace(json=lambda: signing_responses[game])

    monkeypatch.setattr(skland.requests, "post", post)
    generation = api.profiles.current_generation()
    headers = {
        "token": "intent-test-token",
        "X-Mower-Settings": "1",
        "X-Mower-Config-Generation": generation,
    }

    def request(key, path, method="GET", **kwargs):
        def run():
            with api.server.app.test_client() as client:
                outcome[key] = client.open(
                    path, method=method, headers=headers, **kwargs
                )

        worker = Thread(target=run)
        workers.append(worker)
        worker.start()
        return worker

    request("sign", "/check-skland-sign")
    try:
        assert entered.wait(2)
        assert not record.exists()
        stop = request("stop", "/stop")
        profile = request(
            "profile",
            "/config-profiles",
            method="POST",
            json={"name": "blocked", "inherit": []},
        )
        backup = request(
            "backup",
            "/config-backup/import",
            method="POST",
            data=b"not parsed while signing",
        )
        for worker in (stop, profile, backup):
            worker.join(0.5)
        finished_during_signing = [
            not worker.is_alive() for worker in (stop, profile, backup)
        ]
        stopped_during_signing = api.config.stop_mower.is_set()
        busy_during_signing = api.server.configuration_profiles_busy()
    finally:
        release.set()
        for worker in workers:
            worker.join(3)
            assert not worker.is_alive()

    assert finished_during_signing == [True, True, True]
    assert stopped_during_signing
    assert busy_during_signing
    assert api.profiles.current_generation() == generation
    assert outcome["stop"].data == b"true"
    assert outcome["profile"].status_code == 409
    assert outcome["backup"].status_code == 409
    assert outcome["sign"].status_code == 200
    assert len(outcome["sign"].json) == 1
    assert "签到成功" in outcome["sign"].json[0]
    assert "offline-reward" in record.read_text(encoding="gbk")
    assert not api.server.configuration_profiles_busy()
    assert (
        api.client.post(
            "/config-profiles",
            headers=headers,
            json={"name": "after signing", "inherit": []},
        ).status_code
        == 200
    )
