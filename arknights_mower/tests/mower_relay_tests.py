import asyncio
import base64
import json
from unittest.mock import Mock

import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestServer

from arknights_mower.utils.mower_relay import client, settings
from arknights_mower.utils.mower_relay.protocol import public_origin


@pytest.fixture
def relay(tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(settings, "settings_path", lambda: tmp_path / "relay.json")
    monkeypatch.setattr(server.app, "token", "instance-token", raising=False)
    monkeypatch.setattr(server.app, "static_folder", str(tmp_path))
    (tmp_path / "relay-ui.json").write_text(json.dumps({"build": "b" * 64}))
    instance = client.RelayClient(server.app)
    monkeypatch.setitem(server.app.extensions, "mower_relay", instance)
    yield instance
    instance.close()


def config(password):
    return dict(
        enabled=True,
        subdomain="example",
        credential="a" * 40,
        username="玩家",
        password=password,
    )


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("token", ["", "incorrect"])
def test_settings_reject_before_read_or_write(relay, monkeypatch, method, token):
    unexpected = Mock(
        side_effect=AssertionError("settings accessed before authorization")
    )
    monkeypatch.setattr(settings, "load", unexpected)
    r = relay.app.test_client().open(
        "/relay/settings", method=method, headers={"token": token}
    )
    assert r.status_code == 403
    unexpected.assert_not_called()


@pytest.mark.parametrize("secret", ["字", "x:" * 200])
def test_settings_save_and_authenticate(relay, monkeypatch, secret):
    apply = Mock()
    monkeypatch.setattr(relay, "start", apply)
    browser = relay.app.test_client()
    url = "/relay/settings"
    headers = {"token": relay.app.token, "X-Mower-Settings": "1"}
    assert (
        browser.post(
            url, json=config(secret), headers={"token": relay.app.token}
        ).status_code
        == 403
    )
    assert (
        browser.post(
            url,
            json=config(secret),
            headers={**headers, "Origin": "https://other.invalid"},
        ).status_code
        == 403
    )
    assert not settings.settings_path().exists()
    response = browser.post(url, json=config(secret), headers=headers)
    assert response.status_code == 200
    assert not {"credential", "password_hash", "password"}.intersection(response.json)
    assert settings.load()["password_hash"] != secret
    assert (
        browser.post(
            url, json={"password": "", "credential": ""}, headers=headers
        ).status_code
        == 200
    )
    assert apply.call_count == 2
    msg = {"id": "login", "username": "玩家", "password": secret}
    assert relay.authenticate(msg)["ok"]
    assert not relay.authenticate({**msg, "password": "incorrect"})["ok"]
    assert browser.get(url, headers=headers).json["password_saved"]


def test_dispatch_scope_and_instance_token(relay):
    def request(path, token):
        return relay.dispatch(
            {"id": "x", "method": "GET", "path": path, "headers": {"token": token}},
            public_origin("example"),
        )

    # This existing GET can be read locally without its own token decorator.
    for supplied in ("", "incorrect"):
        assert request("/getwatermark", supplied)["status"] == 403
    assert request("/getwatermark", relay.app.token)["status"] == 200
    for target in (
        "/relay/settings",
        "//elsewhere.invalid/status",
        "https://elsewhere.invalid/status",
    ):
        with pytest.raises(ValueError):
            request(target, relay.app.token)


def test_connection_login_dispatch_and_disable(relay, monkeypatch):
    import server
    from arknights_mower.utils.log_stream import LogStream

    stream = LogStream()
    stream.publish("relay log fixture")
    monkeypatch.setattr(server.log_stream, "serve", stream.serve)

    async def scenario():
        received = asyncio.get_running_loop().create_future()
        disconnected = asyncio.Event()

        async def connect(request):
            assert request.headers["X-Mower-Subdomain"] == "example"
            assert request.headers["Authorization"] == "Bearer " + "a" * 40
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            try:
                assert await ws.receive_json(timeout=3) == {
                    "op": "hello",
                    "version": 1,
                    "ui_build": "b" * 64,
                }
                await ws.send_json({"op": "ready", "version": 1, "ui_build": "b" * 64})
                await ws.send_json(
                    {
                        "op": "authenticate",
                        "id": "login",
                        "username": "玩家",
                        "password": "短",
                    }
                )
                assert (await ws.receive_json(timeout=3))["ok"]
                await ws.send_json(
                    {
                        "op": "request",
                        "id": "get",
                        "method": "GET",
                        "path": "/getwatermark",
                        "headers": {"token": relay.app.token},
                    }
                )
                response = await ws.receive_json(timeout=3)
                assert response["status"] == 200
                assert base64.b64decode(response["body"])
                await ws.send_json({"op": "ws_open", "id": "log", "path": "/log"})
                await ws.send_json(
                    {
                        "op": "ws_data",
                        "id": "log",
                        "data": json.dumps({"token": relay.app.token}),
                    }
                )
                record = await ws.receive_json(timeout=3)
                assert (
                    record["op"] == "ws_data"
                    and json.loads(record["data"])["data"] == "relay log fixture"
                )
                await ws.send_json({"op": "ws_close", "id": "log"})
                assert (await ws.receive_json(timeout=3))["op"] == "ws_close"
                received.set_result(True)
                assert (await ws.receive(timeout=4)).type == WSMsgType.CLOSE
            finally:
                disconnected.set()
            return ws

        test_app = web.Application()
        test_app.router.add_get("/__mower/connect", connect)
        async with TestServer(test_app) as gateway:
            monkeypatch.setattr(
                client,
                "CONNECT_URL",
                str(gateway.make_url("/__mower/connect")).replace("http:", "ws:"),
            )
            relay.start()
            assert relay._thread is None
            settings.save(config("短"))
            relay.start()
            await asyncio.wait_for(received, 5)
            assert relay.status()["state"] == "connected"
            settings.save({"enabled": False})
            relay.start()
            await asyncio.wait_for(disconnected.wait(), 5)
            await asyncio.to_thread(relay.close)
            assert not relay._thread.is_alive()

    asyncio.run(scenario())
