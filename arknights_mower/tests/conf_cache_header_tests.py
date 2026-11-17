"""`/conf` must not let any HTTP cache retain the sign-in password value.

The hook under test is applied to the application with ``after_request``, so this
suite exercises the hook itself with a minimal application: a full server import
re-imports numpy and cv2 through the route modules in this environment, which
corrupts cv2 for every later test in the process.
"""

import unittest

from flask import Flask, jsonify

from arknights_mower.views import network
from server import forbid_caching_sensitive_responses


class ConfigCacheHeaderTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.after_request(forbid_caching_sensitive_responses)

        @app.route("/conf", methods=["GET", "PATCH"])
        def conf():
            return jsonify({"skland_info": [{"password": "secret-value"}]})

        @app.route("/assets/main.js")
        def asset():
            return "console.log(1)"

        @app.route("/logs.zip")
        def logs():
            return "zip"

        self.client = app.test_client()

    def test_conf_forbids_caching(self):
        response = self.client.get("/conf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertIn("skland_info", response.get_json())

    def test_conf_write_forbids_caching_too(self):
        response = self.client.patch("/conf", json={"skland_enable": True})
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_other_routes_keep_their_cache_policy(self):
        self.assertNotEqual(
            self.client.get("/assets/main.js").headers.get("Cache-Control"),
            "no-store",
        )
        self.assertNotEqual(
            self.client.get("/logs.zip").headers.get("Cache-Control"), "no-store"
        )


def test_network_settings_needs_token_for_read_and_write(monkeypatch):
    app = Flask(__name__)
    app.token = "web-test-token"
    app.register_blueprint(network.network_bp)
    app.after_request(forbid_caching_sensitive_responses)
    values = {
        "github_token": "github_test_secret",
        "github_proxy": "",
        "http_proxy": "",
    }
    reads, writes = [], []

    def read():
        reads.append(True)
        return values

    def write(data):
        writes.append(data)
        return data

    monkeypatch.setattr(network.network_settings, "get_settings", read)
    monkeypatch.setattr(network.network_settings, "save_settings", write)
    client = app.test_client()
    for headers in ({}, {"token": "wrong"}):
        assert client.get("/network/settings", headers=headers).status_code == 403
        assert client.head("/network/settings", headers=headers).status_code == 403
        assert (
            client.post("/network/settings", headers=headers, json=values).status_code
            == 403
        )
    assert reads == writes == []

    headers = {"token": app.token, "X-Mower-Settings": "1"}
    response = client.get("/network/settings", headers=headers)
    assert response.json == {"ok": True, **values}
    assert response.headers["Cache-Control"] == "no-store"
    assert client.head("/network/settings", headers=headers).status_code == 200
    response = client.post("/network/settings", headers=headers, json=values)
    assert response.json == {"ok": True, **values}
    assert response.headers["Cache-Control"] == "no-store"
    assert writes == [values]
