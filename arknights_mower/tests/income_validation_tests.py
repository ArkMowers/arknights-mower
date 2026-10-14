"""收益演算自动校验捕获的排班，不保存或同步外部名单。"""

import ast
import copy
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from flask import Flask, request

from arknights_mower.utils import config, schedule_roster
from arknights_mower.utils.operators import Operators, build_global_plan

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "plan", config.PlanModel())
    node = next(
        node
        for node in ast.parse((ROOT / "server.py").read_text()).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "validate_backup_plans_route"
    )
    node.decorator_list = []
    namespace = {
        "config": config,
        "request": request,
        "Operators": Operators,
        "build_global_plan": build_global_plan,
        "logger": MagicMock(),
    }
    exec(
        compile(ast.Module(body=[node], type_ignores=[]), "server.py", "exec"),
        namespace,
    )
    app = Flask(__name__)
    app.add_url_rule(
        "/validate-plan",
        view_func=namespace["validate_backup_plans_route"],
        methods=["POST"],
    )
    return app.test_client()


def simple_plan():
    return {
        "default": "plan1",
        "conf": {},
        "backup_plans": [],
        "plan1": {"central": {"plans": [{"agent": "能天使", "replacement": ["芬"]}]}},
    }


@pytest.mark.parametrize("mode", ["maximum", "custom"])
def test_explicit_roster_modes_skip_skland_and_preserve_live_configuration(
    client, monkeypatch, mode
):
    owned = MagicMock(side_effect=AssertionError("explicit roster read Skland"))
    monkeypatch.setattr(schedule_roster, "validate_owned_operators", owned)
    snapshot = simple_plan()
    snapshot["advanced_settings"] = {
        "resting_threshold": 0.7,
        "product_switching": {"enable": True},
    }
    before = copy.deepcopy(snapshot), config.plan.model_dump(), config.conf.model_dump()
    result = client.post(
        "/validate-plan", json={"plan": snapshot, "operatorMode": mode}
    ).json
    assert result["success"], result
    owned.assert_not_called()
    assert (snapshot, config.plan.model_dump(), config.conf.model_dump()) == before


def test_cached_roster_validation_is_read_only_and_blocks_worker_admission(
    client, monkeypatch
):
    owned = MagicMock(return_value="缓存名单校验失败")
    monkeypatch.setattr(schedule_roster, "validate_owned_operators", owned)
    result = client.post(
        "/validate-plan", json={"plan": simple_plan(), "operatorMode": "cache"}
    ).json
    assert not result["success"]
    assert result["message"] == "缓存名单校验失败"
    assert owned.call_args.kwargs == {"refresh": False}


def test_removed_backup_bindings_fail_before_calculation_and_restored_bindings_pass(
    client, monkeypatch
):
    monkeypatch.setattr(
        schedule_roster,
        "validate_owned_operators",
        MagicMock(side_effect=AssertionError("read Skland")),
    )
    snapshot = json.loads(
        (
            ROOT / "arknights_mower/tests/fixtures/income_backup_bindings.json"
        ).read_text()
    )
    snapshot["backup_plans"][0]["trigger"] = {
        "left": "op_data.operators['结城理'].is_working()",
        "operator": "==",
        "right": "False",
    }
    snapshot["advanced_settings"] = {"product_switching": {"enable": True}}
    result = client.post(
        "/validate-plan", json={"plan": snapshot, "operatorMode": "maximum"}
    ).json
    assert result["status"] == "failed", result
    assert "鸿雪下班" in result["message"]
    assert any(name in result["message"] for name in ("斯卡蒂", "幽灵鲨", "结城理")), (
        result
    )
    snapshot["backup_plans"][0]["plan"]["room_2_1"]["plans"] = copy.deepcopy(
        snapshot["plan1"]["room_2_1"]["plans"]
    )
    result = client.post(
        "/validate-plan", json={"plan": snapshot, "operatorMode": "maximum"}
    ).json
    assert result["success"], result


def test_snapshot_product_switching_uses_captured_advanced_settings(
    client, monkeypatch
):
    snapshot = simple_plan()
    snapshot["plan1"]["room_1_1"] = {"name": "制造站", "product": "gold", "plans": []}
    snapshot["backup_plans"] = [
        {
            "name": "切换产物",
            "conf": {},
            "task": {},
            "plan": {"room_1_1": {"name": "制造站", "product": "exp3", "plans": []}},
            "trigger": {"left": "True", "operator": "==", "right": "True"},
        }
    ]
    for enabled in (False, True):
        config.conf.product_switching.enable = not enabled
        snapshot["advanced_settings"] = {"product_switching": {"enable": enabled}}
        result = client.post(
            "/validate-plan", json={"plan": snapshot, "operatorMode": "maximum"}
        ).json
        assert result["success"] is enabled, result
        assert config.conf.product_switching.enable is not enabled


def test_incomplete_or_malformed_validation_does_not_report_success(
    client, monkeypatch
):
    monkeypatch.setattr(
        Operators,
        "validate_backup_plans",
        lambda *a, **kw: {
            "success": False,
            "status": "incomplete",
            "message": "允许启动",
        },
    )
    result = client.post(
        "/validate-plan", json={"plan": simple_plan(), "operatorMode": "maximum"}
    ).json
    assert result == {
        "success": False,
        "status": "incomplete",
        "message": "排班组合校验未完成，尚未开始演算。请简化副表条件后重试。",
    }
    result = client.post(
        "/validate-plan",
        json={"plan": {"default": "missing"}, "operatorMode": "maximum"},
    ).json
    assert result["success"] is False
    assert (
        client.post(
            "/validate-plan", json={"plan": simple_plan(), "operatorMode": "invalid"}
        ).status_code
        == 400
    )
