"""设备发现、数据库清理和 AI 内部索引的日志保留各自业务含义。"""

import importlib
import logging
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from flask import Flask

from arknights_mower.utils import log


@pytest.fixture(autouse=True)
def isolated_logger(monkeypatch, caplog):
    monkeypatch.setattr(log.logger, "handlers", [caplog.handler])
    monkeypatch.setattr(log.logger, "propagate", False)
    caplog.set_level(logging.DEBUG, logger=log.logger.name)


@pytest.mark.parametrize("waiting", [False, True])
@pytest.mark.parametrize("device_state", ["target", "other", "absent"])
def test_adb_initialization_keeps_device_identifiers_in_debug(
    monkeypatch, caplog, waiting, device_state
):
    from arknights_mower.utils.device.adb_client import core

    client = object.__new__(core.Client)
    client.device_id = "127.0.0.1:16928"
    devices = {
        "target": [client.device_id, "USB-device"],
        "other": ["USB-device"],
        "absent": [],
    }[device_state]
    monkeypatch.setattr(
        core.config, "conf", SimpleNamespace(simulator=SimpleNamespace(wait_time=0))
    )
    monkeypatch.setattr(client, "_Client__exec", Mock())
    monkeypatch.setattr(client, "_Client__connect_device", Mock())
    monkeypatch.setattr(
        client, "_Client__choose_devices", Mock(return_value=client.device_id)
    )
    monkeypatch.setattr(
        client, "_Client__available_devices", Mock(return_value=devices)
    )
    monkeypatch.setattr(core, "Session", Mock())
    sleep = Mock()
    monkeypatch.setattr(core, "csleep", sleep)

    if device_state == "target":
        client._Client__init_device(wait_for_device=waiting)
    else:
        with pytest.raises(ConnectionError, match="Device connection failure"):
            client._Client__init_device(wait_for_device=waiting)

    assert sleep.call_args_list == (
        [call(1), call(2)] if waiting and device_state != "target" else [call(1)]
    )
    assert client.device_id == "127.0.0.1:16928"
    visible = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert (
        visible
        == {
            "target": ["ADB 已连接目标设备"],
            "other": [],
            "absent": ["ADB 未连接到任何设备"],
        }[device_state]
    )
    if devices:
        assert any(
            record.levelno == logging.DEBUG
            and record.getMessage() == f"ADB 可连接的设备：{'、'.join(devices)}"
            for record in caplog.records
        )
    assert any(record.levelno == logging.ERROR for record in caplog.records) == (
        device_state != "target"
    )


@pytest.fixture
def deletion(monkeypatch, tmp_path):
    from arknights_mower.views import db_admin

    path = tmp_path / "records.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE log (value TEXT);"
            "INSERT INTO log VALUES ('first'), ('second');"
            "CREATE TABLE inventory (value TEXT);"
            "INSERT INTO inventory VALUES ('stock');"
        )
    state = {"committed": False, "fail_commit": False}

    @contextmanager
    def connect():
        with sqlite3.connect(path) as connection:

            def commit():
                if state["fail_commit"]:
                    raise OSError("离线事务提交失败")
                connection.commit()
                state["committed"] = True

            yield SimpleNamespace(execute=connection.execute, commit=commit)

    monkeypatch.setattr(db_admin.record, "_conn", connect)
    app = Flask(__name__)
    app.token = "offline-instance-token"
    app.register_blueprint(db_admin.db_admin_bp)
    return SimpleNamespace(
        module=db_admin,
        client=app.test_client(),
        path=path,
        state=state,
        headers={"token": app.token},
    )


def test_database_deletion_logs_each_actual_count_after_commit(
    deletion, monkeypatch, caplog
):
    original_info = log.logger.info

    def after_commit(*args, **kwargs):
        assert deletion.state["committed"] is True
        original_info(*args, **kwargs)

    monkeypatch.setattr(log.logger, "info", after_commit)
    response = deletion.client.post(
        "/db-admin/delete",
        json={"categories": ["log", "inventory", "mastery_route"]},
        headers=deletion.headers,
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "deleted": {"log": 2, "inventory": 1, "mastery_route": 0}
    }
    with sqlite3.connect(deletion.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM log").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 0
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.INFO] == [
        "数据库清理完成：错误日志 2 条、仓库库存 1 条、专精路线配置 0 条"
    ]


@pytest.mark.parametrize("headers", [{}, {"token": "different-instance-token"}])
def test_database_deletion_rejects_unauthorized_requests_before_parsing(
    deletion, monkeypatch, headers
):
    from flask import Request

    parse = Mock(side_effect=AssertionError("不应解析未授权请求"))
    connect = Mock(side_effect=AssertionError("不应读取未授权数据库"))
    monkeypatch.setattr(Request, "get_json", parse)
    monkeypatch.setattr(deletion.module.record, "_conn", connect)

    response = deletion.client.post(
        "/db-admin/delete", json={"categories": ["log"]}, headers=headers
    )

    assert response.status_code == 403
    parse.assert_not_called()
    connect.assert_not_called()


def test_database_commit_failure_never_logs_a_completed_deletion(deletion, caplog):
    deletion.state["fail_commit"] = True

    response = deletion.client.post(
        "/db-admin/delete", json={"categories": ["log"]}, headers=deletion.headers
    )

    assert response.status_code == 500
    assert [r for r in caplog.records if r.levelno == logging.INFO] == []
    with sqlite3.connect(deletion.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM log").fetchone()[0] == 2


@pytest.fixture
def agents(monkeypatch):
    agent = importlib.import_module("arknights_mower.agent.agent")
    rank = importlib.import_module("arknights_mower.agent.rank_activity_entries")
    captcha = importlib.import_module("arknights_mower.agent.tools.captcha_ocr_match")
    model = Mock()
    factory = Mock(return_value=model)
    monkeypatch.setattr(agent, "build_llm", factory)
    monkeypatch.setattr(captcha, "build_llm", factory)
    invocation = Mock(side_effect=lambda _key, messages: model.invoke(messages))
    monkeypatch.setattr(rank, "_invoke_with_budget", invocation)
    monkeypatch.setattr(
        rank,
        "pick_activity_entry",
        Mock(return_value='{"ranked":[{"index":1},{"index":0}]}'),
    )
    return SimpleNamespace(
        rank=rank, captcha=captcha, model=model, factory=factory, invocation=invocation
    )


@pytest.mark.parametrize("failure", [False, True])
def test_activity_rank_indices_stay_at_debug_and_keep_parse_or_fallback_result(
    agents, caplog, failure
):
    agents.model.invoke.return_value = SimpleNamespace(content='{"indices":[0,1]}')
    if failure:
        agents.model.invoke.side_effect = RuntimeError("离线排序失败")

    result = agents.rank.rank_activity_entries_with_agent(
        "AD-1", {}, [{"text": "AD-1"}, {"text": "活动入口"}], api_key="offline-test-key"
    )

    assert result == ([1, 0] if failure else [0, 1])
    indices = [r for r in caplog.records if "indices=" in r.getMessage()]
    assert len(indices) == (1 if failure else 2)
    assert all(r.levelno == logging.DEBUG for r in indices)
    agents.invocation.assert_called_once()
    assert agents.invocation.call_args.args[0] == "offline-test-key"


def test_captcha_model_indices_stay_at_debug_without_changing_click_order(
    agents, caplog
):
    agents.model.invoke.return_value = SimpleNamespace(content="[1,0]")

    result = agents.captcha.match_captcha_order(
        "开始", [{"word": "始"}, {"word": "开"}], api_key="offline-test-key"
    )

    assert result == [1, 0]
    responses = [r for r in caplog.records if r.getMessage().startswith("LLM 返回：")]
    assert len(responses) == 1
    assert responses[0].levelno == logging.DEBUG
    assert responses[0].getMessage() == "LLM 返回：[1,0]"
