"""界面偏好迁入实例 gui.yml，并与窗口进程串行更新。"""

import json
import subprocess
import sys
import time

import pytest
import yaml
from flask import Flask

from arknights_mower.utils import config, ui_state
from arknights_mower.utils.config import gui
from arknights_mower.views.ui_state import ui_state_bp


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(gui, "gui_path", tmp_path / "first/config/gui.yml")
    monkeypatch.setattr(ui_state.runtime, "state_dir", lambda: tmp_path / "updates")
    return tmp_path


def client():
    app = Flask(__name__)
    app.token = "gui-storage"
    app.register_blueprint(ui_state_bp)
    return app.test_client()


def test_authenticated_curve_exclusion_writes_gui_and_preserves_window_settings(
    storage,
):
    gui.save_window_mode("maximized")
    gui.save_close_preference("exit", True)
    response = client().patch(
        "/ui-state/mood-board",
        headers={"token": "gui-storage"},
        json={"hiddenLines": {"深海": ["歌蕾蒂娅"]}, "hiddenGroups": ["排除组"]},
    )
    assert response.status_code == 200
    data = yaml.safe_load(gui.gui_path.read_text())
    assert data["mood_board"]["hiddenLines"] == {"深海": ["歌蕾蒂娅"]}
    assert data["mood_board"]["hiddenGroups"] == ["排除组"]
    assert data["window_mode"] == "maximized"
    assert data["close_preference"] == {"choice": "exit", "remember": True}
    gui.save_window_mode("normal")
    assert ui_state.get_mood_board()["preferences"]["hiddenLines"] == {
        "深海": ["歌蕾蒂娅"]
    }
    assert not (storage / "updates/ui-state.json").exists()


def test_shared_legacy_preferences_seed_each_instance_once(storage, monkeypatch):
    legacy = storage / "updates/ui-state.json"
    legacy.parent.mkdir()
    content = json.dumps(
        {
            "mood_board": {"hiddenLines": {"一组": ["阿米娅"]}},
            "log_layout": {"task_height": 320},
        }
    ).encode()
    legacy.write_bytes(content)
    first = gui.gui_path
    assert ui_state.get_mood_board()["preferences"]["hiddenLines"] == {
        "一组": ["阿米娅"]
    }
    ui_state.save_mood_board({"hiddenLines": {}})
    assert ui_state.get_mood_board()["preferences"]["hiddenLines"] == {}
    monkeypatch.setattr(gui, "gui_path", storage / "second/config/gui.yml")
    assert ui_state.get_mood_board()["preferences"]["hiddenLines"] == {
        "一组": ["阿米娅"]
    }
    ui_state.save_log_layout({"task_height": 400})
    assert yaml.safe_load(first.read_text())["log_layout"]["task_height"] == 320
    assert legacy.read_bytes() == content


def test_existing_gui_preferences_win_over_legacy(storage):
    gui._update_gui_data(mood_board={"hiddenGroups": ["新组"]})
    legacy = storage / "updates/ui-state.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"mood_board": {"hiddenGroups": ["旧组"]}}))
    assert ui_state.get_mood_board()["preferences"]["hiddenGroups"] == ["新组"]


def test_failed_preference_write_keeps_original_gui(storage, monkeypatch):
    ui_state.save_mood_board({"hiddenGroups": ["保留"]})
    original = gui.gui_path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("readonly")

    monkeypatch.setattr(gui, "atomic_write", fail)
    response = client().patch(
        "/ui-state/mood-board",
        headers={"token": "gui-storage"},
        json={"hiddenGroups": []},
    )
    assert response.status_code == 400
    assert gui.gui_path.read_bytes() == original


@pytest.mark.parametrize("content", ["[", "[]", "false", "0"])
def test_invalid_gui_is_not_overwritten(storage, content):
    gui.gui_path.parent.mkdir(parents=True)
    gui.gui_path.write_text(content)
    response = client().patch(
        "/ui-state/mood-board",
        headers={"token": "gui-storage"},
        json={"hiddenGroups": []},
    )
    assert response.status_code == 400
    assert gui.gui_path.read_text() == content


@pytest.mark.parametrize(
    "url,method",
    [
        ("/log-layout", "GET"),
        ("/log-layout", "POST"),
        ("/mood-board", "GET"),
        ("/mood-board", "POST"),
        ("/mood-board", "PATCH"),
    ],
)
@pytest.mark.parametrize("token", [None, "wrong"])
def test_ui_preferences_reject_missing_or_invalid_token_before_file_access(
    storage, monkeypatch, url, method, token
):
    def forbidden(*args, **kwargs):
        pytest.fail("未授权请求读取或写入界面配置")

    monkeypatch.setattr(gui, "read_gui_data", forbidden)
    monkeypatch.setattr(gui, "update_gui_data", forbidden)
    response = client().open(
        "/ui-state" + url, method=method, headers={"token": token} if token else {}
    )
    assert response.status_code == 403
    assert not gui.gui_path.exists()


def test_window_process_waits_for_preference_transaction(storage):
    gui.save_window_mode("normal")
    attempted = storage / "attempted"
    code = """
import sys
from pathlib import Path
from arknights_mower.utils.config import gui
gui.gui_path = Path(sys.argv[1])
Path(sys.argv[2]).touch()
gui.save_window_mode('maximized')
"""
    process = None
    try:
        with ui_state.runtime.supervision_lock(
            gui.gui_path.parent.parent / "tmp/gui-config", timeout=5
        ):
            process = subprocess.Popen(
                [sys.executable, "-c", code, str(gui.gui_path), str(attempted)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.monotonic() + 10
            while not attempted.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert attempted.exists()
            with pytest.raises(subprocess.TimeoutExpired):
                process.communicate(timeout=0.15)
            config.atomic_write(
                gui.gui_path,
                lambda stream: yaml.safe_dump(
                    {"window_mode": "normal", "mood_board": {"hiddenGroups": ["保留"]}},
                    stream,
                    allow_unicode=True,
                ),
            )
        _, error = process.communicate(timeout=10)
        assert process.returncode == 0, error
        data = yaml.safe_load(gui.gui_path.read_text())
        assert data["window_mode"] == "maximized"
        assert data["mood_board"] == {"hiddenGroups": ["保留"]}
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
