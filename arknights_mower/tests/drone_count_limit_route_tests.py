from unittest.mock import MagicMock

import pytest

import server
from arknights_mower.utils import config
from arknights_mower.utils.config import weekly_plan_loader


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf(workshop_preset_migrated=True))
    monkeypatch.setattr(config, "plan", config.PlanModel())
    monkeypatch.setattr(config, "save_conf", MagicMock())
    monkeypatch.setattr(config, "save_plan", MagicMock())
    monkeypatch.setattr(weekly_plan_loader, "get_weekly_plan_manager", MagicMock())
    monkeypatch.setattr(server.app, "token", "drone-limit-test", raising=False)
    return server.app.test_client()


@pytest.mark.parametrize("url", ["/plan", "/conf"])
@pytest.mark.parametrize("limit", [0, 19, 20])
def test_drone_reserve_save_boundary(client, url, limit):
    original_conf = config.conf
    payload = {"drone_count_limit": limit}
    if url == "/plan":
        payload = {"advanced_settings": payload}
    response = client.post(url, json=payload, headers={"token": "drone-limit-test"})
    assert response.status_code == 200
    if url == "/plan":
        assert config.plan.advanced_settings["drone_count_limit"] == 20
        assert config.conf is original_conf
        config.save_plan.assert_called_once()
        config.save_conf.assert_not_called()
    else:
        assert config.conf.drone_count_limit == 20
        config.save_conf.assert_called_once()
        config.save_plan.assert_not_called()


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("token", [None, "wrong"])
def test_plan_requires_token_before_parsing_or_writing(
    client, monkeypatch, method, token
):
    def forbidden(*args, **kwargs):
        pytest.fail("未授权请求解析或写入排班")

    monkeypatch.setattr(config, "PlanModel", forbidden)
    monkeypatch.setattr(type(config.plan), "model_dump", forbidden)
    monkeypatch.setattr(config, "save_plan", forbidden)
    response = client.open(
        "/plan",
        method=method,
        json={"advanced_settings": {"drone_count_limit": 20}},
        headers={"token": token} if token else {},
    )
    assert response.status_code == 403


def test_plan_read_accepts_current_token(client):
    response = client.get("/plan", headers={"token": "drone-limit-test"})
    assert response.status_code == 200
    assert response.get_json() == config.plan.model_dump(exclude_none=True)


@pytest.mark.parametrize("limit", [0, 10, 19])
def test_plan_save_normalizes_legacy_drone_reserve(client, monkeypatch, limit):
    from arknights_mower.utils.config.plan_advanced import export_advanced_settings

    monkeypatch.setattr(config, "conf", config.Conf(drone_count_limit=limit))
    response = client.post(
        "/plan",
        json={
            "plan1": {"central": {"plans": [{"agent": "阿米娅"}]}},
            "advanced_settings": {
                **export_advanced_settings(config.conf),
                "drone_count_limit": limit,
            },
        },
        headers={"token": "drone-limit-test"},
    )
    assert response.status_code == 200
    assert config.plan.plan1.central.plans[0].agent == "阿米娅"
    assert config.plan.advanced_settings["drone_count_limit"] == 20
    assert config.conf.drone_count_limit == 20
    config.save_plan.assert_called_once()
    config.save_conf.assert_not_called()
