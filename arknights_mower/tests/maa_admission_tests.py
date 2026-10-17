import json
import sys
import threading
from datetime import datetime, timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.tests.maa_process_helpers import fake_sdk_worker  # noqa: E402
from arknights_mower.utils import maa_backup  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402


@pytest.fixture
def desktop(monkeypatch, tmp_path):
    monkeypatch.setattr("arknights_mower.utils.maa_process.MaaProcess", fake_sdk_worker)
    monkeypatch.setenv("MOWER_ANDROID", "0")
    monkeypatch.syspath_prepend(str(tmp_path))
    native = Mock()
    native.get_version.return_value = "v6.test"
    (tmp_path / "MaaCore.dll").write_bytes(b"offline core")
    monkeypatch.setattr(
        "arknights_mower.utils.maa_runtime.read_installed_version",
        Mock(return_value="v6.test"),
    )
    native.connect.return_value = True
    asst = Mock(return_value=native)
    asst.load.return_value = True
    package = ModuleType("asst")
    package.__path__ = []
    module = ModuleType("asst.asst")
    module.Asst = asst
    options = ModuleType("asst.utils")
    options.InstanceOptionType = SimpleNamespace(touch_type=2)
    for name, value in (
        ("asst", package),
        ("asst.asst", module),
        ("asst.utils", options),
    ):
        monkeypatch.setitem(sys.modules, name, value)
    conf = SimpleNamespace(
        maa_path=str(tmp_path),
        maa_touch_option="maatouch",
        maa_adb_path="adb",
        maa_conn_preset="General",
    )
    monkeypatch.setattr(base_schedule.config, "conf", conf)
    monkeypatch.setattr(base_schedule.config, "stop_maa", threading.Event())
    monkeypatch.setattr(base_schedule, "guard_adb", Mock())
    monkeypatch.setattr(base_schedule, "save_exception", Mock())
    log = Mock()
    monkeypatch.setattr(base_schedule, "logger", log)
    response = MagicMock()
    response.__enter__.return_value = response
    response.content = b'{"YW-8": {"algorithm": "JustReturn"}}'
    monkeypatch.setattr(base_schedule.requests, "get", Mock(return_value=response))
    resource = tmp_path / "resource"
    resource.mkdir()
    (resource / "tasks").mkdir()
    (resource / "version.json").write_text(
        json.dumps({"last_updated": "2026-10-10 01:00:00.000"})
    )
    scheduler = object.__new__(base_schedule.BaseSchedulerSolver)
    scheduler.MAA = None
    scheduler.device = SimpleNamespace(
        client=SimpleNamespace(adb_bin="adb", device_id="127.0.0.1:5555")
    )
    yield SimpleNamespace(
        scheduler=scheduler,
        asst=asst,
        native=native,
        response=response,
        root=tmp_path,
        log=log,
    )
    if scheduler.MAA is not None:
        scheduler.MAA.stop()


def test_rejected_resource_load_prevents_handle_creation(desktop):
    desktop.asst.load.return_value = False
    with pytest.raises(RuntimeError, match="资源加载失败") as raised:
        desktop.scheduler.initialize_maa()
    assert raised.value.operation == "load"
    desktop.asst.assert_not_called()
    desktop.native.connect.assert_not_called()
    assert desktop.scheduler.MAA is None


@pytest.mark.parametrize(
    "content, message",
    [
        (None, "配置文件不存在"),
        (b"broken", "配置文件格式无效"),
        (b"\xff", "配置文件格式无效"),
    ],
)
def test_rejected_resource_load_distinguishes_missing_and_invalid_config(
    desktop, content, message
):
    if content is not None:
        (desktop.root / "resource" / "config.json").write_bytes(content)
    desktop.asst.load.return_value = False
    with pytest.raises(maa_backup.MaaCallError, match=message) as raised:
        desktop.scheduler.initialize_maa()
    assert "访问被拒绝" not in str(raised.value)
    desktop.asst.assert_not_called()
    desktop.native.connect.assert_not_called()


def test_rejected_resource_load_reports_read_denied_config(desktop, monkeypatch):
    from pathlib import Path

    original_open = Path.open
    config_file = desktop.root / "resource" / "config.json"

    def denied(path, *args, **kwargs):
        if path == config_file:
            raise PermissionError("denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    desktop.asst.load.return_value = False
    with pytest.raises(maa_backup.MaaCallError, match="访问被拒绝") as raised:
        desktop.scheduler.initialize_maa()
    assert str(config_file) in str(raised.value)
    desktop.asst.assert_not_called()
    desktop.native.connect.assert_not_called()


def test_download_is_loaded_before_success_is_reported(desktop):
    desktop.scheduler.initialize_maa()
    cached = desktop.root / "cache/resource/tasks/tasks.json"
    assert json.loads(cached.read_text()) == {"YW-8": {"algorithm": "JustReturn"}}
    desktop.asst.load.assert_called_once_with(
        path=desktop.root, incremental_path=desktop.root / "cache"
    )
    assert any(
        "MAA 资源加载成功" in str(call)
        and "v6.test" in str(call)
        and "2026-10-10 01:00:00.000" in str(call)
        for call in desktop.log.info.call_args_list
    )


def test_external_core_reload_uses_new_sdk_and_instance_options(desktop, monkeypatch):
    desktop.scheduler.initialize_maa()
    desktop.scheduler.MAA.stop()
    desktop.scheduler.release_maa()
    (desktop.root / "MaaCore.dll").write_bytes(b"updated offline core")
    native = Mock()
    native.get_version.return_value = "v6.test"
    new_asst = Mock(return_value=native)
    new_asst.load.return_value = True

    monkeypatch.setitem(sys.modules, "asst.asst", SimpleNamespace(Asst=new_asst))
    monkeypatch.setitem(
        sys.modules,
        "asst.utils",
        SimpleNamespace(InstanceOptionType=SimpleNamespace(touch_type=99)),
    )
    desktop.scheduler.initialize_maa()
    desktop.asst.load.assert_called_once()
    new_asst.load.assert_called_once()
    native.set_instance_option.assert_called_once_with(99, "maatouch")
    native.connect.assert_called_once_with("adb", "127.0.0.1:5555", "General")


@pytest.mark.parametrize(
    "payload", [b"<html>error</html>", b"[]", b"{}", b'{"error": "offline"}']
)
def test_invalid_download_preserves_existing_navigation(desktop, payload):
    cached = desktop.root / "cache/resource/tasks/tasks.json"
    cached.parent.mkdir(parents=True)
    previous = b'{"OLD": {"algorithm": "JustReturn"}}'
    cached.write_bytes(previous)
    desktop.response.content = payload
    desktop.scheduler.initialize_maa()
    assert cached.read_bytes() == previous
    desktop.asst.load.assert_called_once()
    desktop.log.error.assert_called_once()


def test_failed_atomic_write_preserves_existing_navigation(desktop, monkeypatch):
    from arknights_mower.utils import update_runtime

    cached = desktop.root / "cache/resource/tasks/tasks.json"
    cached.parent.mkdir(parents=True)
    previous = b'{"OLD": {"algorithm": "JustReturn"}}'
    cached.write_bytes(previous)
    monkeypatch.setattr(
        update_runtime, "replace_with_retry", Mock(side_effect=OSError("disk full"))
    )
    desktop.scheduler.initialize_maa()
    assert cached.read_bytes() == previous
    assert list(cached.parent.iterdir()) == [cached]
    desktop.log.error.assert_called_once()


@pytest.fixture
def android(desktop, monkeypatch):
    monkeypatch.setenv("MOWER_ANDROID", "1")
    package = ModuleType("mower_android")
    package.__path__ = []
    maa = ModuleType("mower_android.maa")
    maa.Asst = desktop.asst
    bridge = ModuleType("mower_android.bridge")
    bridge.Bridge = Mock()
    bridge.Bridge.return_value.call.return_value = True
    for name, value in (
        ("mower_android", package),
        ("mower_android.maa", maa),
        ("mower_android.bridge", bridge),
    ):
        monkeypatch.setitem(sys.modules, name, value)
    desktop.bridge = bridge.Bridge.return_value
    return desktop


def test_android_downloads_and_loads_navigation_before_connect(android):
    events = []
    base_schedule.requests.get.side_effect = lambda *a, **kw: (
        events.append("download") or android.response
    )
    android.bridge.call.side_effect = lambda *a, **kw: events.append("load") or True
    android.native.connect.side_effect = lambda: events.append("connect") or True
    android.scheduler.initialize_maa()
    assert events == ["download", "load", "connect"]
    android.bridge.call.assert_called_once_with(
        "maa_navigation", tasks={"YW-8": {"algorithm": "JustReturn"}}
    )
    android.asst.load.assert_not_called()


def test_android_load_failure_prevents_task_connection(android):
    android.bridge.call.return_value = False
    with pytest.raises(maa_backup.MaaCallError, match="资源加载失败"):
        android.scheduler.initialize_maa()
    android.native.connect.assert_not_called()
    android.native.append_task.assert_not_called()


def test_android_invalid_download_loads_previous_cached_navigation(android):
    cached = android.root / "cache/resource/tasks.json"
    cached.parent.mkdir(parents=True)
    cached.write_text('{"OLD": {"algorithm": "JustReturn"}}')
    android.response.content = b"invalid"
    android.scheduler.initialize_maa()
    android.bridge.call.assert_called_once_with(
        "maa_navigation", tasks={"OLD": {"algorithm": "JustReturn"}}
    )


@pytest.fixture
def run(monkeypatch, tmp_path):
    monkeypatch.setenv("MOWER_ANDROID", "0")
    conf = Conf(
        maa_stage_inventory_enable=False,
        maa_credit_fight=False,
        maa_mall_enable=False,
        visit_friend_enable=False,
    )
    for plan in conf.maa_weekly_plan:
        plan.stage = ["Annihilation", "YW-8"]
    monkeypatch.setattr(base_schedule.config, "conf", conf)
    monkeypatch.setattr(base_schedule.config, "stop_maa", threading.Event())
    monkeypatch.setattr(base_schedule.config, "stop_mower", threading.Event())
    monkeypatch.setattr(base_schedule, "get_server_weekday", lambda: 5)
    monkeypatch.setattr(base_schedule, "save_exception", Mock())
    monkeypatch.setattr(base_schedule, "send_message", Mock())
    from arknights_mower.utils import maa_stage_inventory

    monkeypatch.setattr(
        maa_stage_inventory, "load_inventory_snapshot", lambda: ({}, None)
    )
    native = Mock()
    native.append_task.side_effect = lambda task, params: (
        0 if params.get("stage") == "YW-8" else 4
    )
    native.start.return_value = True
    native.stop.return_value = True
    native.running.return_value = False
    scheduler = object.__new__(base_schedule.BaseSchedulerSolver)
    scheduler.MAA = maa_backup.VerifiedAsst(lambda callback: native, tmp_path, None)
    scheduler.device = MagicMock()
    scheduler.recog = MagicMock()
    scheduler.stages = []
    scheduler.tasks = [
        SimpleNamespace(time=datetime.now() + timedelta(hours=1), plan={})
    ]
    scheduler.last_execution = {"maa": None}
    scheduler.credit_fight = None
    for name in (
        "initialize_maa",
        "back_to_index",
        "_idle_sleep",
        "maybe_switch_expired_activity_plan",
        "rest_until_next_task",
    ):
        setattr(scheduler, name, Mock())
    return SimpleNamespace(scheduler=scheduler, native=native)


def test_rejected_stage_clears_partial_queue_without_recording_success(run):
    run.scheduler.maa_plan_solver()
    run.native.start.assert_not_called()
    run.native.stop.assert_called_once()
    assert run.scheduler.stages == ["Annihilation"]
    assert run.scheduler.last_execution["maa"] is None
    assert run.scheduler.MAA is None
    assert not base_schedule.battle_inventory_active.is_set()
    run.scheduler.device.exit.assert_not_called()
    assert any(
        "YW-8" in str(call) and "任务提交失败" in str(call)
        for call in base_schedule.send_message.call_args_list
    )


def test_rejected_start_clears_queue_without_recording_success(run):
    run.native.append_task.side_effect = None
    run.native.append_task.return_value = 4
    run.native.start.return_value = False
    run.scheduler.maa_plan_solver()
    run.native.stop.assert_called_once()
    assert run.scheduler.last_execution["maa"] is None
    assert run.scheduler.MAA is None
    assert any(
        "任务启动失败" in str(call)
        for call in base_schedule.send_message.call_args_list
    )


def test_stop_failure_preserves_original_stage_diagnostic(run):
    run.native.stop.side_effect = RuntimeError("stop rejected")
    run.scheduler.maa_plan_solver()
    assert any(
        "YW-8" in str(call) and "任务提交失败" in str(call)
        for call in base_schedule.send_message.call_args_list
    )
    assert run.scheduler.last_execution["maa"] is None


def test_cancellation_during_stop_propagates_without_idle_sleep(run):
    failure = base_schedule.MowerExit()
    run.native.stop.side_effect = failure
    with pytest.raises(base_schedule.MowerExit) as raised:
        run.scheduler.maa_plan_solver()
    assert raised.value is failure
    run.scheduler._idle_sleep.assert_not_called()
    assert run.scheduler.last_execution["maa"] is None


def test_accepted_plan_keeps_both_stages_and_records_execution(run):
    run.native.append_task.side_effect = [3, 4, 5, 6]
    run.scheduler.maa_plan_solver()
    run.native.start.assert_called_once()
    assert run.scheduler.stages == ["Annihilation", "YW-8"]
    assert run.scheduler.last_execution["maa"] is not None
    run.scheduler.rest_until_next_task.assert_called_once()


def test_android_bridge_failure_prevents_task_submission(android):
    android.bridge.call.side_effect = RuntimeError("bridge disconnected")
    with pytest.raises(RuntimeError, match="bridge disconnected"):
        android.scheduler.initialize_maa()
    android.native.connect.assert_not_called()
    android.native.append_task.assert_not_called()
