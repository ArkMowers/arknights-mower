import builtins
import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.tests.manager_instance_controls_tests import manager as manager
from arknights_mower.utils import software_update as update
from arknights_mower.utils import update_runtime as runtime


@pytest.mark.parametrize("entrypoint", ["manager.py", "webview_ui.py"])
def test_copied_update_launcher_runs_worker_before_gui_imports(
    tmp_path, monkeypatch, entrypoint
):
    source = Path(__file__).resolve().parents[2] / entrypoint
    copied = tmp_path / entrypoint
    copied.write_bytes(source.read_bytes())
    job = str(tmp_path / "job.json")
    worker = Mock()
    monkeypatch.setattr(sys, "argv", [str(copied), "--software-update-worker", job])
    monkeypatch.setitem(
        sys.modules,
        "arknights_mower.utils.software_update_worker",
        SimpleNamespace(main=worker),
    )
    original_import = builtins.__import__

    def import_without_application(name, *args, **kwargs):
        if name in {
            "webview",
            "webview_ui",
            "arknights_mower.utils.config",
            "arknights_mower.utils.manager_instances",
        }:
            pytest.fail(f"Update launcher imported application module: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_application)
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(copied), run_name="__main__")
    assert stopped.value.code is None
    worker.assert_called_once_with(job)


def test_manager_release_update_stages_its_launcher_and_shared_runtime(
    manager, tmp_path, monkeypatch
):
    root = tmp_path / "installation"
    (root / "_internal").mkdir(parents=True)
    (root / "_internal" / "runtime.dat").write_bytes(b"runtime")
    executable = root / "多开管理器.exe"
    executable.write_bytes(b"manager executable")
    (root / "config").mkdir()
    (root / "config" / "instances.json").write_text("private data")
    state = tmp_path / "updates"
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(runtime, "installation_root", lambda: root)
    monkeypatch.setattr(runtime, "state_dir", lambda: state)
    monkeypatch.setattr(update, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(update, "get_settings", lambda: {"background": False})
    monkeypatch.setattr(update, "info", lambda: {"blockers": []})
    monkeypatch.setattr(update.network_settings, "apply_http_proxy", lambda: None)
    monkeypatch.setattr(
        update.network_settings,
        "get_effective_settings",
        lambda: {"http_proxy": "", "github_proxy": ""},
    )
    plan = {
        "created_at": update.time.time(),
        "deployment": "release",
        "version": "v4.2.0",
        "channel": "stable",
    }
    monkeypatch.setitem(update._checks, "manager-release", plan)
    process = Mock(return_value=SimpleNamespace(pid=12345))
    monkeypatch.setattr(update.subprocess, "Popen", process)

    result = manager.start_mower_update("manager-release", False)

    work = state / "jobs" / result["id"]
    runner = work / "runner" / root.name
    assert process.call_args.args[0] == [
        str(runner / executable.name),
        "--software-update-worker",
        str(work / "job.json"),
    ]
    assert (runner / executable.name).read_bytes() == b"manager executable"
    assert (runner / "_internal" / "runtime.dat").read_bytes() == b"runtime"
    assert not (runner / "config").exists()
    assert process.call_args.kwargs["cwd"] == work
    assert process.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


@pytest.mark.parametrize("owner", ["manager", "unrelated", "none"])
def test_update_admission_with_no_running_instances(manager, monkeypatch, owner):
    monkeypatch.setattr(runtime, "frozen", lambda: True)
    monkeypatch.setattr(
        runtime, "installation_root", lambda: manager._storage_path.parent
    )
    registered = (
        []
        if owner == "none"
        else [
            dict(
                kind="manager",
                pid=os.getppid() if owner == "manager" else os.getpid() + 100,
            )
        ]
    )
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: registered)
    monkeypatch.setattr(update, "get_settings", lambda: {"background": False})
    result = manager.get_mower_update_info()
    assert result["instances"] == []
    assert bool(result["blockers"]) is (owner != "manager")


def test_empty_manager_submits_update_without_launching_an_instance(
    manager, monkeypatch
):
    manager.remove(0)
    submit = Mock(return_value={"ok": True, "id": "job"})
    monkeypatch.setattr(update, "submit", submit)
    assert manager.start_mower_update("checked", False) == {"ok": True, "id": "job"}
    submit.assert_called_once_with("checked", False)


@pytest.mark.parametrize("value", [None, 1, "false"])
def test_manager_rejects_invalid_restart_mode_before_submitting(
    manager, monkeypatch, value
):
    submit = Mock()
    monkeypatch.setattr(update, "submit", submit)
    with pytest.raises(ValueError, match="更新请求无效"):
        manager.start_mower_update("checked", value)
    submit.assert_not_called()
