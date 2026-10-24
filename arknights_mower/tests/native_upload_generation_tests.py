"""Native multipart uploads retain configuration generation admission."""

import json
from io import BytesIO

import pytest

from arknights_mower.tests.config_profiles_tests import storage as storage
from arknights_mower.utils import config
from arknights_mower.utils import config_profiles as profiles


@pytest.mark.parametrize(
    "route,field",
    [
        ("/import", "img"),
        ("/import?rescue=1", "img"),
        ("/sss-copilot", "copilot"),
    ],
)
@pytest.mark.parametrize("generation", [None, "previous-page", "current-page"])
def test_native_multipart_upload_checks_generation_before_writing(
    storage, monkeypatch, route, field, generation
):
    import server

    monkeypatch.setattr(server.app, "token", "upload-token", raising=False)
    monkeypatch.setattr(server, "get_path", storage)
    activated = profiles.create_profile("upload target", [], expected_generation="0")
    assert activated["generation"] != "0"
    paths = (
        config.plan_path,
        config.rescue_plan_path,
        storage("@app/sss.json"),
    )

    def snapshot():
        return [path.read_bytes() if path.exists() else None for path in paths]

    before = snapshot()
    content = (
        {"doc": {"title": "Uploaded copilot", "details": "Offline test"}, "opers": []}
        if field == "copilot"
        else {"plan1": {}, "conf": {"ling_xi": 2}}
    )
    headers = {"token": "upload-token"}
    if generation is not None:
        headers["X-Mower-Config-Generation"] = (
            activated["generation"] if generation == "current-page" else generation
        )
    response = server.app.test_client().post(
        route,
        headers=headers,
        data={field: (BytesIO(json.dumps(content).encode()), "upload.json")},
    )

    if generation != "current-page":
        assert response.status_code == 409
        assert response.json["code"] == "configuration_changed"
        assert snapshot() == before
        return

    assert response.status_code == 200
    if field == "copilot":
        assert response.json["title"] == "Uploaded copilot"
        assert json.loads(paths[2].read_bytes()) == content
        assert snapshot()[:2] == before[:2]
    else:
        assert response.text == "排班已加载"
        selected = 1 if "rescue=1" in route else 0
        assert json.loads(paths[selected].read_bytes())["conf"]["ling_xi"] == 2
        assert snapshot()[1 - selected] == before[1 - selected]
        assert snapshot()[2] == before[2]
