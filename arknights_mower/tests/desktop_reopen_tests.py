import sys
from pathlib import Path
from queue import Empty
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask

from arknights_mower.tests.manager_instance_controls_tests import manager as manager
from arknights_mower.tests.manager_instance_controls_tests import record
from arknights_mower.utils import instance_supervisor as supervisor
from arknights_mower.utils import manager_instances as controls
from arknights_mower.utils import path
from arknights_mower.utils import update_runtime as runtime


def test_manager_start_reopens_ready_instance_without_launching(manager, monkeypatch):
    existing = record(manager)
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [existing])
    send = Mock()
    monkeypatch.setattr(runtime, "send_instance_command", send)
    before = manager._storage_path.read_bytes()
    assert manager.get_instances()[0]["can_open_browser"] is True
    assert manager.start(0) == {"ok": True}
    assert manager.start(0) == {"ok": True}
    assert send.call_count == 2
    send.assert_called_with(existing, "show")
    controls.subprocess.Popen.assert_not_called()
    assert manager._storage_path.read_bytes() == before


@pytest.mark.parametrize("state", ["starting", "stopping", "unmanaged"])
def test_manager_does_not_reopen_unavailable_instance(manager, monkeypatch, state):
    existing = record(manager)
    if state == "starting":
        existing["ready"] = False
    elif state == "unmanaged":
        existing["managed"] = False
    else:
        runtime.write_json(runtime.state_dir() / "shutdown/registered.json", {})
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [existing])
    send = Mock()
    monkeypatch.setattr(runtime, "send_instance_command", send)
    assert manager.get_instances()[0]["can_open_browser"] is False
    assert manager.start(0)["ok"] is False
    send.assert_not_called()
    controls.subprocess.Popen.assert_not_called()


@pytest.mark.parametrize("managed", [False, True])
def test_background_desktop_processes_show_requests_without_replacing_window(
    tmp_path, monkeypatch, managed
):
    import webview_ui
    from arknights_mower import utils
    from arknights_mower.utils import crash_recovery, lifecycle, log, network

    conf = SimpleNamespace(
        webview=SimpleNamespace(tray=False, token="", port=0),
        start_automatically=False,
        resource_update=SimpleNamespace(enable=False),
    )
    config = Mock(conf=conf, stop_mower=Event(), updates_enabled=False)
    monkeypatch.setattr(utils, "config", config, raising=False)
    monkeypatch.setattr(path, "global_space", None)
    monkeypatch.setattr(path, "_data_dir", tmp_path)
    monkeypatch.setattr(sys, "argv", ["mower"])
    for name, value in {
        "MOWER_BACKGROUND": "1",
        "MOWER_MANAGED": "1" if managed else "0",
        "MOWER_RESTART_JOB": "",
        "MOWER_RESUME_RUN": "0",
        "MOWER_RESUME_MODE": "",
        "MOWER_UPDATE_REPLAN": "",
    }.items():
        monkeypatch.setenv(name, value)
    server = Mock(app=Flask(__name__))
    server._job_running.return_value = False
    server.resource_update.running.return_value = False
    server.stop.return_value = "true"
    monkeypatch.setitem(sys.modules, "server", server)
    registration = Mock(record={})
    messages = [["show"], ["show"]]
    registration.take_commands.side_effect = lambda: messages.pop(0)
    registration.shutdown_requested.side_effect = lambda: not messages
    monkeypatch.setattr(runtime, "RuntimeRegistration", lambda *a, **kw: registration)
    monkeypatch.setattr(runtime, "active_job", lambda: False)
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "runtime")
    monkeypatch.setattr(runtime, "unified_managers", lambda: [dict(kind="manager")])
    monkeypatch.setattr(crash_recovery, "status", lambda: {"active": False})
    monkeypatch.setattr(crash_recovery, "notice_path", lambda: None)
    monkeypatch.setattr(supervisor, "child_ready", Mock())
    monkeypatch.setattr(network, "is_port_in_use", Mock(side_effect=[False, True]))
    monkeypatch.setattr(lifecycle, "shutdown", lifecycle.Shutdown())
    monkeypatch.setattr(webview_ui, "start_http_server", Mock())
    monkeypatch.setattr(webview_ui, "exit_if_webview_backend_missing", Mock())
    monkeypatch.setattr(webview_ui, "desktop_port", lambda *a: 58000)
    monkeypatch.setattr(webview_ui, "close_child", Mock())
    monkeypatch.setattr(webview_ui, "close_channel", Mock())
    monkeypatch.setattr(webview_ui, "own_channel", Mock())
    for name in ("init_file_logging", "start_mp_listener"):
        monkeypatch.setattr(log, name, Mock())
    monkeypatch.setattr(webview_ui.mp, "Queue", Mock())
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    window, connection = Mock(), Mock()
    tray_queue = Mock()
    tray_queue.get.side_effect = Empty

    def start_child(kind, *args, **kwargs):
        return (window, connection) if kind == "window" else (Mock(), tray_queue)

    children = Mock(side_effect=start_child)
    monkeypatch.setattr(webview_ui, "start_desktop_child", children)
    webview_ui._run_desktop()
    assert [call.args[0] for call in children.call_args_list].count("window") == 1
    connection.send.assert_called_once_with("show")
    server.start.assert_not_called()


def test_windows_launcher_shows_existing_instance_before_ownership_lock(
    tmp_path, monkeypatch
):
    data = tmp_path / "data"
    monkeypatch.setattr(path, "_data_dir", data)
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "updates")
    instance = dict(id="existing", kind="instance", ready=True, space="account")
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [instance])
    send, launch = Mock(), Mock()
    monkeypatch.setattr(runtime, "send_instance_command", send)
    monkeypatch.setattr(supervisor, "supervise", launch)
    directory = data / "account/tmp/process-supervision"
    with supervisor.instance_lock(directory, timeout=0):
        assert supervisor.run_launcher(["account"]) == 0
    send.assert_called_once_with(instance, "show")
    launch.assert_not_called()


@pytest.mark.parametrize("unavailable", ["other", "not_ready", "stopping"])
def test_launcher_reopens_only_ready_matching_configuration(
    tmp_path, monkeypatch, unavailable
):
    monkeypatch.setattr(path, "_data_dir", tmp_path)
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "updates")
    instance = dict(id="existing", kind="instance", ready=True, space="account")
    if unavailable == "other":
        instance["space"] = "other"
    elif unavailable == "not_ready":
        instance["ready"] = False
    else:
        runtime.write_json(runtime.state_dir() / "shutdown/existing.json", {})
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [instance])
    send = Mock()
    monkeypatch.setattr(runtime, "send_instance_command", send)
    assert not supervisor.show_existing_instance(
        Path(tmp_path) / "account/tmp/process-supervision"
    )
    send.assert_not_called()
