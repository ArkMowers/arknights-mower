"""Concurrent network saves use only synthetic credentials and temporary files."""

import os
import queue
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from arknights_mower.utils import network_settings as network


@pytest.fixture
def settings(tmp_path, monkeypatch):
    path = tmp_path / "config/network.json"
    monkeypatch.setattr(network, "settings_path", lambda: path)
    monkeypatch.setattr(network, "_base_environment", None)
    monkeypatch.setattr(network, "_effective_settings", None)
    with patch.dict(os.environ):
        network.save_settings(
            {"http_proxy": "", "github_proxy": "", "github_token": "synthetic_token"}
        )
        yield path


def test_proxy_only_save_reads_token_after_entering_the_save_lock(
    settings, monkeypatch
):
    entered = threading.Event()
    lock = threading.RLock()

    class ObservedLock:
        def __enter__(self):
            if threading.current_thread() is not threading.main_thread():
                entered.set()
            lock.acquire()

        def __exit__(self, *args):
            lock.release()

    monkeypatch.setattr(network, "_environment_lock", ObservedLock())
    with ThreadPoolExecutor(max_workers=1) as pool:
        with network._environment_lock:
            pending = pool.submit(
                network.save_settings,
                {"http_proxy": "http://127.0.0.1:7897", "github_proxy": ""},
            )
            assert entered.wait(5)
            network.save_settings(
                {"http_proxy": "", "github_proxy": "", "github_token": ""}
            )
        result = pending.result(timeout=5)
    assert result["github_token"] == ""
    assert network.get_settings()["github_token"] == ""
    assert network.get_settings()["http_proxy"] == "http://127.0.0.1:7897"


def test_another_process_cannot_save_between_token_read_and_write(settings):
    script = """
import sys
from pathlib import Path
from arknights_mower.utils import network_settings as network
network.settings_path = lambda: Path(sys.argv[1])
read = network.get_settings
paused = False
def pause_after_read(*args, **kwargs):
    global paused
    result = read(*args, **kwargs)
    if not paused:
        paused = True
        print('read', flush=True)
        sys.stdin.readline()
    return result
network.get_settings = pause_after_read
network.save_settings({'http_proxy': 'http://127.0.0.1:7897', 'github_proxy': ''})
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(settings)],
        cwd=Path(__file__).resolve().parents[2],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    output = queue.Queue()
    reader = threading.Thread(
        target=lambda: output.put(process.stdout.readline()), daemon=True
    )
    reader.start()
    try:
        assert output.get(timeout=10).strip() == "read"
        with pytest.raises(TimeoutError):
            network.save_settings(
                {"http_proxy": "", "github_proxy": "", "github_token": ""}
            )
        assert network.get_settings()["github_token"] == "synthetic_token"
    finally:
        try:
            stdout, stderr = process.communicate("\n", timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
        reader.join(timeout=5)
    assert process.returncode == 0, stderr
    network.save_settings({"http_proxy": "", "github_proxy": "", "github_token": ""})
    assert network.get_settings()["github_token"] == ""


def test_proxy_only_save_preserves_token_and_explicit_replacement_wins(settings):
    values = {"http_proxy": "", "github_proxy": "https://mirror.example/"}
    assert network.save_settings(values)["github_token"] == "synthetic_token"
    values["github_token"] = "replacement_token"
    assert network.save_settings(values)["github_token"] == "replacement_token"


def test_busy_save_requires_current_web_token_before_entering_settings_save():
    from flask import Flask

    from arknights_mower.views.network import network_bp

    app = Flask(__name__)
    app.token = "synthetic_web_token"
    app.register_blueprint(network_bp)
    client = app.test_client()
    data = {"http_proxy": "", "github_proxy": "", "github_token": ""}
    with patch.object(network, "save_settings", side_effect=TimeoutError) as save:
        for token in (None, "invalid"):
            headers = {"X-Mower-Settings": "1"}
            if token:
                headers["token"] = token
            assert (
                client.post("/network/settings", json=data, headers=headers).status_code
                == 403
            )
        save.assert_not_called()
        response = client.post(
            "/network/settings",
            json=data,
            headers={"X-Mower-Settings": "1", "token": app.token},
        )
        assert response.status_code == 409
        assert response.get_json() == {
            "ok": False,
            "message": "网络配置正在保存，请稍后重试",
        }
        save.assert_called_once_with(data)
