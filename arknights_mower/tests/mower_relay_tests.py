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

    monkeypatch.setattr(server.config.conf.webview, "token", "instance-token")
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
    response = request("/item?kind=workshop-materials", relay.app.token)
    assert response["status"] == 200
    assert {"name": "聚合剂", "rarity": 5} in json.loads(
        base64.b64decode(response["body"])
    )
    for target in (
        "/relay/settings",
        "//elsewhere.invalid/status",
        "https://elsewhere.invalid/status",
    ):
        with pytest.raises(ValueError):
            request(target, relay.app.token)


def test_relay_conversation_operations_require_the_instance_token(relay, monkeypatch):
    import server

    item = "/ai/conversations/" + "a" * 32
    history = Mock()
    history.return_value.list.return_value = []
    monkeypatch.setattr(server, "active_chat_history", history)
    monkeypatch.setitem(server.app.config, "AI_ASSISTANT_ENABLED", True)

    def request(method, path, headers):
        return relay.dispatch(
            {"id": "history", "method": method, "path": path, "headers": headers},
            public_origin("example"),
        )

    for path, method in [
        ("/ai/conversations", "GET"),
        ("/ai/conversations", "DELETE"),
        (item, "GET"),
        (item, "DELETE"),
        (item + "/summary", "POST"),
        (item + "/turns/12/control", "POST"),
    ]:
        for headers in ({}, {"token": "invalid"}):
            assert request(method, path, headers)["status"] == 403
    history.assert_not_called()
    result = request("GET", "/ai/conversations", {"token": relay.app.token})
    assert result["status"] == 200
    assert json.loads(base64.b64decode(result["body"])) == {"conversations": []}
    for method, path in [
        ("POST", item),
        ("GET", item + "/summary"),
        ("GET", "/ai/settings"),
    ]:
        with pytest.raises(ValueError):
            request(method, path, {"token": relay.app.token})


def test_connection_login_dispatch_and_disable(relay, monkeypatch, tmp_path):
    import server
    from arknights_mower.agent import agent
    from arknights_mower.utils import config_profiles
    from arknights_mower.utils.ai_history import HistoryStore
    from arknights_mower.utils.log_stream import LogStream

    history = HistoryStore("test")
    history.path = tmp_path / "chat.sqlite3"
    monkeypatch.setitem(relay.app.config, "AI_ASSISTANT_ENABLED", True)
    monkeypatch.setattr(server, "active_chat_history", lambda: history)
    monkeypatch.setattr(
        config_profiles, "current_generation", lambda: "test-generation"
    )
    monkeypatch.setattr(
        agent, "ask_llm", lambda *args, **kwargs: iter(["fixture reply"])
    )
    stream = LogStream()
    stream.publish("relay log fixture")
    monkeypatch.setattr(server.log_stream, "serve", stream.serve)

    async def scenario():
        received = asyncio.get_running_loop().create_future()
        disconnected = asyncio.Event()

        async def connect(request):
            assert "X-Mower-Subdomain" not in request.headers
            assert request.headers["Authorization"] == "Bearer " + "a" * 40
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            try:
                assert await ws.receive_json(timeout=3) == {
                    "op": "hello",
                    "version": 1,
                    "ui_build": "b" * 64,
                }
                await ws.send_json(
                    {
                        "op": "ready",
                        "version": 1,
                        "ui_build": "b" * 64,
                        "subdomain": "example",
                    }
                )
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
                        "path": "/ai/conversations",
                        "headers": {
                            "token": relay.app.token,
                            "x-mower-config-generation": "test-generation",
                        },
                    }
                )
                response = await ws.receive_json(timeout=3)
                assert response["status"] == 200
                assert json.loads(base64.b64decode(response["body"])) == {
                    "conversations": []
                }
                await ws.send_json({"op": "ws_open", "id": "chat", "path": "/ws/chat"})
                for frame in (
                    {"token": relay.app.token},
                    {
                        "conversation_id": None,
                        "request_id": "first",
                        "generation": "test-generation",
                        "message": "first message",
                    },
                ):
                    await ws.send_json(
                        {"op": "ws_data", "id": "chat", "data": json.dumps(frame)}
                    )
                async with asyncio.timeout(3):
                    while True:
                        envelope = await ws.receive_json()
                        assert (envelope["op"], envelope["id"]) == ("ws_data", "chat")
                        frame = json.loads(envelope["data"])
                        assert "error" not in frame
                        if frame.get("done"):
                            break
                turn = history.read(history.list()[0]["id"])["turns"][0]
                assert (turn["user"], turn["assistant"]) == (
                    "first message",
                    "fixture reply",
                )
                await ws.send_json({"op": "ws_close", "id": "chat"})
                assert (await ws.receive_json(timeout=3))["op"] == "ws_close"
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
            settings.save(config("短"), token_ready=relay.token_ready)
            relay.start()
            await asyncio.wait_for(received, 5)
            assert relay.status()["state"] == "connected"
            assert relay.status()["url"] == public_origin("example")
            settings.save({"enabled": False}, token_ready=relay.token_ready)
            relay.start()
            await asyncio.wait_for(disconnected.wait(), 5)
            await asyncio.to_thread(relay.close)
            assert not relay._thread.is_alive()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "configured,temporary", [("", True), ("changed", False), ("instance-token", True)]
)
def test_enable_requires_active_configured_token(
    relay, monkeypatch, configured, temporary
):
    import server

    monkeypatch.setattr(server.config.conf.webview, "token", configured)
    monkeypatch.setitem(relay.app.config, "WEBVIEW_LOCAL_ONLY_NO_TOKEN", temporary)
    headers = {"token": relay.app.token, "X-Mower-Settings": "1"}
    browser = relay.app.test_client()
    assert browser.get("/relay/settings", headers=headers).json["token_ready"] is False
    assert (
        browser.post(
            "/relay/settings", headers=headers, json=config("密码")
        ).status_code
        == 400
    )
    assert not settings.settings_path().exists()
    settings.save(config("密码"), token_ready=True)
    relay.start()
    assert relay._thread is None
    assert (
        browser.post(
            "/relay/settings", headers=headers, json={"enabled": False}
        ).status_code
        == 200
    )
