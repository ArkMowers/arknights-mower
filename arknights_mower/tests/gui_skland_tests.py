from io import BytesIO
from unittest.mock import Mock

import pytest
from flask import Flask

from arknights_mower.utils.config import gui
from arknights_mower.views import gui as routes

_TOKEN = {"token": "skland-test"}
_PATH = "/gui/skland"
_DEFAULTS = {
    "account": None,
    "game": None,
    "detailView": "day",
    "statsAccount": None,
    "statsGame": None,
    "statsPreset": "month",
    "statsRange": None,
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(gui, "gui_path", tmp_path / "instance/config/gui.yml")
    app = Flask(__name__)
    app.token = _TOKEN["token"]
    app.register_blueprint(routes.gui_bp)
    return app.test_client()


def test_default_preferences_without_creating_files(client):
    response = client.get(_PATH, headers=_TOKEN)
    assert response.status_code == 200
    assert response.json == {"skland": _DEFAULTS}
    assert not gui.gui_path.parent.exists()


@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT"])
@pytest.mark.parametrize("headers", [{}, {"token": "another-instance"}])
def test_token_required_before_gui_storage_and_request_parsing(
    client, monkeypatch, method, headers
):
    forbidden = Mock(side_effect=AssertionError("Unauthorized GUI operation"))
    monkeypatch.setattr(gui, "read_gui_data", forbidden)
    monkeypatch.setattr(gui, "update_gui_data", forbidden)
    monkeypatch.setattr(routes, "_request_json", forbidden)
    body = BytesIO(b'{"skland":{"detailView":"rewards"}}')
    response = client.open(
        _PATH,
        method=method,
        headers=headers,
        content_type="application/json",
        environ_overrides={
            "CONTENT_LENGTH": "",
            "wsgi.input_terminated": True,
            "wsgi.input": body,
        },
    )
    assert response.status_code == 403
    assert body.tell() == 0
    forbidden.assert_not_called()


@pytest.mark.parametrize("method,status", [("GET", 200), ("PUT", 200), ("PATCH", 403)])
def test_preflight_is_read_only(client, monkeypatch, method, status):
    forbidden = Mock(side_effect=AssertionError("Preflight accessed GUI state"))
    monkeypatch.setattr(gui, "read_gui_data", forbidden)
    monkeypatch.setattr(gui, "update_gui_data", forbidden)
    monkeypatch.setattr(routes, "_request_json", forbidden)
    response = client.options(
        _PATH,
        headers={"Origin": "http://localhost", "Access-Control-Request-Method": method},
    )
    assert response.status_code == status
    forbidden.assert_not_called()


@pytest.mark.parametrize("preset", ["90", "week"])
def test_save_merges_only_supplied_preferences_in_current_instance(
    client, monkeypatch, preset
):
    gui.save_window_mode("maximized")
    first_path = gui.gui_path
    filters = {
        "account": "138****1000",
        "game": "明日方舟官服",
        "detailView": "rewards",
    }
    response = client.put(_PATH, headers=_TOKEN, json={"skland": filters})
    assert response.status_code == 200
    assert response.json == {"skland": {**_DEFAULTS, **filters}}

    selection = {
        "statsAccount": "139****2000",
        "statsGame": "终末地官服",
        "statsPreset": "custom",
        "statsRange": ["2025-12-31", "2026-11-18"],
    }
    response = client.put(_PATH, headers=_TOKEN, json={"skland": selection})
    expected = {**_DEFAULTS, **filters, **selection}
    assert response.json == {"skland": expected}
    assert gui.read_gui_data() == {"skland": expected, "window_mode": "maximized"}

    response = client.put(
        _PATH, headers=_TOKEN, json={"skland": {"statsPreset": preset}}
    )
    assert response.status_code == 200
    assert response.json == {
        "skland": {**expected, "statsPreset": preset, "statsRange": None}
    }
    assert client.get(_PATH, headers=_TOKEN).json == response.json

    monkeypatch.setattr(
        gui, "gui_path", first_path.parents[2] / "second/config/gui.yml"
    )
    assert client.get(_PATH, headers=_TOKEN).json == {"skland": _DEFAULTS}


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"selectedDate": "2026-11-18"},
        {"account": []},
        {"statsAccount": " "},
        {"statsGame": "x" * 129},
        {"detailView": "chart"},
        {"statsPreset": "quarter"},
        {"statsPreset": "custom"},
        {"statsPreset": "custom", "statsRange": ["2026-02-29", "2026-03-04"]},
        {"statsPreset": "custom", "statsRange": ["20261101", "2026-11-10"]},
        {"statsPreset": "custom", "statsRange": ["2026-11-10", "2026-11-01"]},
        {"statsPreset": "custom", "statsRange": ["2025-11-01", "2026-11-02"]},
    ],
)
def test_invalid_preference_leaves_saved_file_intact(client, value):
    gui.save_skland({"detailView": "failures"})
    previous = gui.gui_path.read_bytes()
    response = client.put(_PATH, headers=_TOKEN, json={"skland": value})
    assert response.status_code == 400
    assert gui.gui_path.read_bytes() == previous


def test_storage_failure_preserves_existing_file(client):
    gui.gui_path.parent.mkdir(parents=True)
    gui.gui_path.write_text("[", encoding="utf-8")
    assert client.get(_PATH, headers=_TOKEN).status_code == 503
    response = client.put(
        _PATH, headers=_TOKEN, json={"skland": {"detailView": "rewards"}}
    )
    assert response.status_code == 503
    assert gui.gui_path.read_text(encoding="utf-8") == "["


def test_server_saves_preferences_independent_of_profile_generation(
    client, monkeypatch
):
    import server
    from arknights_mower.utils import config_profiles

    monkeypatch.setattr(server.app, "token", _TOKEN["token"], raising=False)
    check = Mock(side_effect=AssertionError("GUI preferences are instance-specific"))
    monkeypatch.setattr(config_profiles, "check_generation", check)
    response = server.app.test_client().put(
        _PATH,
        headers={**_TOKEN, "X-Mower-Config-Generation": "previous"},
        json={"skland": {"detailView": "rewards"}},
    )
    assert response.status_code == 200
    assert response.json["skland"]["detailView"] == "rewards"
    check.assert_not_called()
    assert client.get(_PATH, headers=_TOKEN).json == response.json
