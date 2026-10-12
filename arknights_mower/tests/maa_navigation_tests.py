"""Activity navigation survives MAA task-directory precedence."""

import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    installed = tmp_path / "resource" / "tasks" / "tasks.json"
    installed.parent.mkdir(parents=True)
    installed.write_text('{"FightBegin": {"algorithm": "JustReturn"}}')
    hotfix = tmp_path / "cache/resource/tasks/hotfix/ocr_replace.json"
    hotfix.parent.mkdir(parents=True)
    hotfix.write_text('{"BattleStageNameHotfix": {"ocrReplace": [["YVV", "YW"]]}}')
    legacy = tmp_path / "cache/resource/tasks.json"
    legacy.write_text('{"Expired-8": {"algorithm": "JustReturn"}}')
    navigation = tmp_path / "cache/resource/tasks/tasks.json"
    payload = {"YW-8": {"algorithm": "JustReturn", "sub": ["YW-8@YW-OpenOpt"]}}
    response = MagicMock()
    response.__enter__.return_value.content = json.dumps(payload).encode()
    get = MagicMock(return_value=response)
    monkeypatch.setattr(base_schedule.requests, "get", get)
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    monkeypatch.setattr(base_schedule, "get_server_weekday", lambda: 0)
    monkeypatch.setattr(base_schedule, "battle_inventory_active", threading.Event())
    monkeypatch.setattr(base_schedule.config, "stop_maa", threading.Event())
    monkeypatch.setenv("MOWER_ANDROID", "0")
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(
            maa_path=str(tmp_path),
            maa_adb_path="configured-adb",
            maa_conn_preset="General",
            maa_stage_inventory_enable=False,
            maa_weekly_plan=[
                {"weekday": day, "stage": ["YW-8"], "medicine": 0}
                for day in ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
            ],
        ),
    )
    from arknights_mower.utils import maa_stage_inventory

    monkeypatch.setattr(
        maa_stage_inventory, "load_inventory_snapshot", lambda: ({}, None)
    )
    asst = MagicMock()
    asst.return_value.get_version.return_value = "v6.test"
    (tmp_path / "MaaCore.dll").write_bytes(b"offline core")
    monkeypatch.setattr(
        "arknights_mower.utils.maa_runtime.read_installed_version",
        MagicMock(return_value="v6.test"),
    )
    loaded = {}

    def load(*, path, incremental_path):
        loaded.clear()
        for root in (path, incremental_path):
            resource = Path(root) / "resource"
            directory = resource / "tasks"
            files = list(directory.rglob("*.json")) if directory.is_dir() else []
            if not directory.is_dir() and (resource / "tasks.json").is_file():
                files = [resource / "tasks.json"]
            layer = {}
            for file in files:
                tasks = json.loads(file.read_text())
                if layer.keys() & tasks.keys():
                    return False
                layer.update(tasks)
            loaded.update(layer)
        return True

    asst.load.side_effect = load
    asst.return_value.connect.return_value = True
    asst.return_value.running.return_value = False
    asst.return_value.append_task.side_effect = lambda kind, params: (
        17 if kind != "Fight" or params["stage"] in loaded else 0
    )
    monkeypatch.setitem(sys.modules, "asst", MagicMock())
    monkeypatch.setitem(sys.modules, "asst.asst", SimpleNamespace(Asst=asst))
    monkeypatch.setitem(
        sys.modules,
        "asst.utils",
        SimpleNamespace(InstanceOptionType=SimpleNamespace(touch_type=2), Message=int),
    )
    guard = MagicMock()
    monkeypatch.setattr(base_schedule, "guard_adb", guard)
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.MAA = None
    solver.device = SimpleNamespace(
        client=SimpleNamespace(adb_bin="verified-adb", device_id="USB-123")
    )
    solver.maybe_switch_expired_activity_plan = MagicMock()
    yield SimpleNamespace(
        solver=solver,
        asst=asst,
        navigation=navigation,
        payload=payload,
        response=response,
        get=get,
        guard=guard,
        loaded=loaded,
        hotfix=hotfix,
        legacy=legacy,
        installed=installed,
    )
    if solver.MAA is not None:
        solver.MAA.stop()


def test_navigation_loads_with_existing_hotfix_directory_and_dispatches(runtime):
    runtime.navigation.write_text('{"Previous-8": {"algorithm": "JustReturn"}}')
    before = {
        p: p.read_bytes() for p in (runtime.hotfix, runtime.legacy, runtime.installed)
    }
    runtime.solver.initialize_maa()
    runtime.solver.append_maa_task("Fight")
    assert json.loads(runtime.navigation.read_text()) == runtime.payload
    assert "YW-8" in runtime.loaded
    assert "Previous-8" not in runtime.loaded
    assert "BattleStageNameHotfix" in runtime.loaded
    assert runtime.solver.stages == ["YW-8"]
    assert {p: p.read_bytes() for p in before} == before
    runtime.guard.assert_called_once_with("verified-adb", timeout=10)


def test_duplicate_cached_tasks_are_reported_as_resource_load_failure(runtime):
    duplicate = runtime.hotfix.parent / "duplicate.json"
    duplicate.write_bytes(runtime.hotfix.read_bytes())
    with pytest.raises(RuntimeError, match="MAA.*资源加载失败"):
        runtime.solver.initialize_maa()
    runtime.asst.assert_not_called()
