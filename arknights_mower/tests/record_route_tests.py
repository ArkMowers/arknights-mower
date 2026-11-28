"""记录接口遵守实例访问边界。"""

import datetime
from unittest.mock import Mock

import pytest

import server


@pytest.fixture
def client(monkeypatch):
    clear_data = Mock()
    monkeypatch.setattr(server, "clear_data", clear_data)
    monkeypatch.setattr(server.app, "token", "record-route", raising=False)
    return server.app.test_client(), clear_data


def test_clear_data_rejects_request_without_token(client):
    web, clear_data = client

    response = web.delete("/record/clear-data", json={"date_time": 1000})

    assert response.status_code == 403
    clear_data.assert_not_called()


def test_clear_data_accepts_current_instance_token(client):
    web, clear_data = client

    response = web.delete(
        "/record/clear-data",
        headers={"token": "record-route"},
        json={"date_time": 1000},
    )

    assert response.status_code == 200
    clear_data.assert_called_once_with(datetime.datetime.fromtimestamp(1))
